/* The runtime of the programs that selfhost/cgen.nex compiles (decision 0026).
 *
 * It is embedded, as it is, at the top of every generated C file. It does what the interpreter does that is not the program:
 * Int arithmetic with its checks, Text as a sequence of code points, the stack of calls and loops that explains an error, and
 * the text of a diagnostic exactly as `nex` writes it (diagnostics.py, `render`). C11 and the overflow builtins of GCC and
 * Clang are all it needs.
 */
/* The POSIX parts (signals, timers, limits of a process) are not declared by the headers of a system when the file is compiled as
 * strict C11 (musl, for instance); this asks for them. Windows has none of them and the code that uses them is left out there. */
#if !defined(_WIN32) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE 1
#endif
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* With -DRT_STATS the runtime counts what it does and prints the counts when the program ends (a tool for tuning it). */
#ifdef RT_STATS
static unsigned long long rt_stat[16];
static const char *const rt_stat_names[16] = {"allocations", "bytes", "collections", "field", "is_kind", "eq", "record_new",
                                              "variant_new", "list_new", "list_append", "calls", "text_compare", "", "", "", ""};
#define RT_COUNT(i) (rt_stat[i]++)
#define RT_COUNT_BY(i, n) (rt_stat[i] += (unsigned long long)(n))
/* How many times each function of the program was called. */
static const char *rt_fn_name[4096];
static unsigned long long rt_fn_count[4096];
static int rt_fn_total = 0;
static void rt_count_function(const char *name) {
    for (int i = 0; i < rt_fn_total; i++) {
        if (rt_fn_name[i] == name) { rt_fn_count[i]++; return; }
    }
    if (rt_fn_total < 4096) { rt_fn_name[rt_fn_total] = name; rt_fn_count[rt_fn_total++] = 1; }
}
static void rt_print_stats(void) {
    for (int i = 0; i < 16; i++) {
        if (rt_stat_names[i][0]) fprintf(stderr, "stat %-14s %llu\n", rt_stat_names[i], rt_stat[i]);
    }
    for (int round = 0; round < 25; round++) {
        int best = -1;
        for (int i = 0; i < rt_fn_total; i++) {
            if (best < 0 || rt_fn_count[i] > rt_fn_count[best]) best = i;
        }
        if (best < 0 || rt_fn_count[best] == 0) break;
        fprintf(stderr, "fn %-28s %llu\n", rt_fn_name[best], rt_fn_count[best]);
        rt_fn_count[best] = 0;
    }
}
#else
#define RT_COUNT(i) ((void)0)
#define RT_COUNT_BY(i, n) ((void)0)
#endif

typedef struct {
    const char *p;
    int64_t bytes;
    int64_t len; /* code points: what Text.length counts */
} rt_text;

/* The files of the program: the one that runs and the modules it imports. A diagnostic quotes the file of the function that
 * failed, so each one is kept with its path and its lines. */
static const char *rt_path = "";          /* the file the diagnostic being drawn is about */
static const char *const *rt_src = 0;
static int rt_src_lines = 0;
static const char *rt_entry = "";         /* the path the program was given, which `nex run` closes its report with */
static int rt_nfiles = 0;
static const char *const *rt_file_path = 0;
static const char *const *const *rt_file_lines = 0;
static const int *rt_file_count = 0;

/* Memory. A small block (up to 256 bytes) comes from a page of blocks of its size, and a free one is taken from a list in a few
 * instructions; a big one comes from malloc and is kept in a table. When a good deal has been allocated, the stack is searched
 * for what still points into a block (any word that does, whatever it is: the search is conservative), what those blocks point
 * to is searched in turn, and the rest is given back. A block of text bytes is `raw`: it points to nothing, so it is not
 * searched. */

#include <setjmp.h>
#include <time.h>
#ifdef _WIN32
#include <malloc.h>
#define rt_page_alloc(size) _aligned_malloc((size), (size))
#else
#define rt_page_alloc(size) aligned_alloc((size), (size))
#endif

#define RT_PAGE ((size_t)1 << 16)
#define RT_PAGE_HEADER ((size_t)8224) /* the header, then 4,096 marks and 4,096 "in use" bytes: the most blocks a page holds */
#define RT_SMALL_MAX 256
#define RT_CLASSES 16 /* sizes 16, 32, ... 256 */

typedef struct rt_page {
    struct rt_page *next;
    uint32_t size;
    uint32_t count;
    uint32_t inverse; /* 2^32 / size, to find which block an address is in without dividing */
    unsigned char raw;
} rt_page;

typedef struct { char *p; size_t size; unsigned char raw, mark; } rt_block; /* the big ones */

static rt_page *rt_pages = 0;
static void *rt_free_list[2][RT_CLASSES];
static rt_block *rt_blocks = 0;
static size_t rt_nblocks = 0, rt_cap_blocks = 0;
static size_t rt_since_gc = 0, rt_threshold = (size_t)48 << 20, rt_floor = (size_t)48 << 20;
static void *rt_stack_base = 0;

/* The addresses of the pages, to tell whether a word points into one. */
static uintptr_t *rt_page_set = 0;
static size_t rt_page_set_cap = 0, rt_page_set_count = 0;

typedef struct { char *p; size_t size; } rt_mark_item;
static rt_mark_item *rt_mark_stack = 0;
static size_t rt_mark_count = 0, rt_mark_cap = 0;

/* The exit status of the process: what a command-line tool written in NEXORA (nex.nex) sets with `exit_with`. */
static int rt_exit_status = 0;

/* What to write when memory runs out, if the program has one (the worker of the playground answers with a result that says so). */
static const char *rt_oom_reply = 0;
/* What a command-line tool writes on the standard error when memory runs out, and the status it ends with (nex run --max-memory). */
static const char *rt_oom_stderr = 0;

static void rt_out_of_memory(void) {
    if (rt_oom_stderr) {
        fflush(stdout);
        fputs(rt_oom_stderr, stderr);
        fputc('\n', stderr);
        exit(3);
    }
    if (rt_oom_reply) {
        fputs(rt_oom_reply, stdout);
        fflush(stdout);
        exit(0);
    }
    fputs("error: out of memory\n", stderr);
    exit(3);
}

static size_t rt_page_hash(uintptr_t page, size_t cap) { return (size_t)((page >> 16) * 0x9E3779B97F4A7C15ULL) & (cap - 1); }

static void rt_page_set_add(uintptr_t page) {
    if ((rt_page_set_count + 1) * 2 > rt_page_set_cap) {
        size_t cap = rt_page_set_cap ? rt_page_set_cap * 2 : 1024;
        uintptr_t *set = (uintptr_t *)calloc(cap, sizeof(uintptr_t));
        if (!set) rt_out_of_memory();
        for (size_t i = 0; i < rt_page_set_cap; i++) {
            if (rt_page_set[i]) {
                size_t at = rt_page_hash(rt_page_set[i], cap);
                while (set[at]) at = (at + 1) & (cap - 1);
                set[at] = rt_page_set[i];
            }
        }
        free(rt_page_set);
        rt_page_set = set;
        rt_page_set_cap = cap;
    }
    size_t at = rt_page_hash(page, rt_page_set_cap);
    while (rt_page_set[at]) at = (at + 1) & (rt_page_set_cap - 1);
    rt_page_set[at] = page;
    rt_page_set_count++;
}

static int rt_is_page(uintptr_t page) {
    if (!rt_page_set_cap) return 0;
    size_t at = rt_page_hash(page, rt_page_set_cap);
    while (rt_page_set[at]) {
        if (rt_page_set[at] == page) return 1;
        at = (at + 1) & (rt_page_set_cap - 1);
    }
    return 0;
}

static unsigned char *rt_page_marks(rt_page *page) { return (unsigned char *)page + sizeof(rt_page); }
/* Whether each block is in use: a free block holds the link of the list of free blocks, which must not be followed. */
static unsigned char *rt_page_in_use(rt_page *page) { return (unsigned char *)page + sizeof(rt_page) + 4096; }
static uint32_t rt_block_index(rt_page *page, uintptr_t address) {
    return (uint32_t)(((uint64_t)(address - (uintptr_t)page - RT_PAGE_HEADER) * page->inverse) >> 32);
}
static char *rt_page_first(rt_page *page) { return (char *)page + RT_PAGE_HEADER; }

static void rt_collect(void);

/* A new page of blocks of one size, all of them free. */
static void rt_new_page(int raw, int class_index) {
    rt_page *page = (rt_page *)rt_page_alloc(RT_PAGE);
    if (!page) {
        rt_collect();
        page = (rt_page *)rt_page_alloc(RT_PAGE);
        if (!page) rt_out_of_memory();
    }
    uint32_t size = (uint32_t)((class_index + 1) * 16);
    page->next = rt_pages;
    page->size = size;
    page->count = (uint32_t)((RT_PAGE - RT_PAGE_HEADER) / size);
    page->raw = (unsigned char)raw;
    page->inverse = (uint32_t)(((uint64_t)1 << 32) / size + 1);
    rt_pages = page;
    memset(rt_page_marks(page), 0, page->count);
    memset(rt_page_in_use(page), 0, page->count);
    rt_page_set_add((uintptr_t)page);
    char *at = rt_page_first(page);
    for (uint32_t i = page->count; i > 0; i--) {
        char *block = at + (size_t)(i - 1) * size;
        *(void **)block = rt_free_list[raw][class_index];
        rt_free_list[raw][class_index] = block;
    }
}

static int rt_block_order(const void *x, const void *y) {
    const rt_block *a = (const rt_block *)x, *b = (const rt_block *)y;
    return a->p < b->p ? -1 : (a->p > b->p ? 1 : 0);
}

/* The big block that holds an address, or -1. The table is sorted while a collection runs. */
static long rt_find_block(const char *address) {
    long lo = 0, hi = (long)rt_nblocks - 1, found = -1;
    while (lo <= hi) {
        long mid = (lo + hi) / 2;
        if (rt_blocks[mid].p <= address) { found = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    if (found >= 0 && address < rt_blocks[found].p + rt_blocks[found].size) return found;
    return -1;
}

static void rt_mark_push(char *p, size_t size) {
    if (rt_mark_count == rt_mark_cap) {
        rt_mark_cap = rt_mark_cap ? rt_mark_cap * 2 : 4096;
        rt_mark_stack = (rt_mark_item *)realloc(rt_mark_stack, rt_mark_cap * sizeof(rt_mark_item));
        if (!rt_mark_stack) rt_out_of_memory();
    }
    rt_mark_stack[rt_mark_count].p = p;
    rt_mark_stack[rt_mark_count].size = size;
    rt_mark_count++;
}

/* Marks what a word points to, if it points into a block that is in use. */
static void rt_mark_word(uintptr_t word) {
    uintptr_t page_address = word & ~(uintptr_t)(RT_PAGE - 1);
    if (rt_is_page(page_address)) {
        rt_page *page = (rt_page *)page_address;
        if (word < page_address + RT_PAGE_HEADER) return;
        size_t index = rt_block_index(page, word);
        if (index >= page->count || !rt_page_in_use(page)[index]) return;
        unsigned char *mark = &rt_page_marks(page)[index];
        if (!*mark) {
            *mark = 1;
            if (!page->raw) rt_mark_push(rt_page_first(page) + index * page->size, page->size);
        }
        return;
    }
    if (rt_nblocks == 0) return;
    long found = rt_find_block((const char *)word);
    if (found >= 0 && !rt_blocks[found].mark) {
        rt_blocks[found].mark = 1;
        if (!rt_blocks[found].raw) rt_mark_push(rt_blocks[found].p, rt_blocks[found].size);
    }
}

static void rt_mark_words(const char *lo, const char *hi) {
    uintptr_t start = ((uintptr_t)lo + sizeof(void *) - 1) & ~(uintptr_t)(sizeof(void *) - 1);
    for (uintptr_t at = start; at + sizeof(void *) <= (uintptr_t)hi; at += sizeof(void *)) {
        rt_mark_word(*(const uintptr_t *)at);
    }
}

static void rt_collect(void) {
    RT_COUNT(2);
#ifdef RT_STATS
    clock_t gc_started = clock();
#endif
    if (!rt_stack_base) { rt_since_gc = 0; return; }
    if (rt_nblocks > 1) qsort(rt_blocks, rt_nblocks, sizeof(rt_block), rt_block_order);
    for (size_t i = 0; i < rt_nblocks; i++) rt_blocks[i].mark = 0;
    jmp_buf registers;
    setjmp(registers);
    const char *here = (const char *)&registers;
    const char *base = (const char *)rt_stack_base;
    if (here < base) rt_mark_words(here, base + sizeof(void *)); else rt_mark_words(base, here + sizeof registers);
    while (rt_mark_count > 0) {
        rt_mark_item item = rt_mark_stack[--rt_mark_count];
        rt_mark_words(item.p, item.p + item.size);
    }
    size_t live = 0;
#ifdef RT_STATS
    {
        size_t sizes[8] = {0}, counts[8] = {0};
        int distinct = 0;
        for (size_t i = 0; i < rt_nblocks; i++) {
            if (!rt_blocks[i].mark) continue;
            int at = -1;
            for (int k = 0; k < distinct; k++) if (sizes[k] == rt_blocks[i].size) at = k;
            if (at < 0 && distinct < 8) { sizes[distinct] = rt_blocks[i].size; at = distinct++; }
            if (at >= 0) counts[at]++;
        }
        fprintf(stderr, "  live big blocks by size:");
        for (int k = 0; k < distinct; k++) fprintf(stderr, " %zu x%zu", sizes[k], counts[k]);
        fprintf(stderr, "\n");
    }
#endif
    /* The big blocks that nothing points to are freed. */
    size_t kept = 0;
    for (size_t i = 0; i < rt_nblocks; i++) {
        if (rt_blocks[i].mark) {
            live += rt_blocks[i].size;
            rt_blocks[kept++] = rt_blocks[i];
        } else {
            free(rt_blocks[i].p);
        }
    }
    rt_nblocks = kept;
    /* The small ones are put back on the lists of free blocks, and the marks are cleared. */
    for (int r = 0; r < 2; r++) {
        for (int c = 0; c < RT_CLASSES; c++) rt_free_list[r][c] = 0;
    }
    for (rt_page *page = rt_pages; page; page = page->next) {
        unsigned char *marks = rt_page_marks(page);
        unsigned char *in_use = rt_page_in_use(page);
        int class_index = (int)(page->size / 16) - 1;
        char *first = rt_page_first(page);
        for (uint32_t i = page->count; i > 0; i--) {
            if (marks[i - 1]) {
                marks[i - 1] = 0;
                live += page->size;
            } else {
                char *block = first + (size_t)(i - 1) * page->size;
                in_use[i - 1] = 0;
                *(void **)block = rt_free_list[page->raw][class_index];
                rt_free_list[page->raw][class_index] = block;
            }
        }
    }
    rt_since_gc = 0;
    rt_threshold = live > rt_floor ? live : rt_floor;
#ifdef RT_STATS
    fprintf(stderr, "gc: live %zu bytes, %zu big blocks, %.1f ms\n", live, rt_nblocks, (double)(clock() - gc_started) * 1000.0 / CLOCKS_PER_SEC);
#endif
}

/* NEXORA_GC_FLOOR=<bytes> makes it collect much more often, which is how the collector is tested. */
static void rt_gc_start(void *stack_base) {
    rt_stack_base = stack_base;
#ifdef RT_STATS
    atexit(rt_print_stats);
#endif
    const char *floor = getenv("NEXORA_GC_FLOOR");
    if (floor) {
        rt_floor = (size_t)atol(floor);
        rt_threshold = rt_floor;
    }
}

static void *rt_alloc_kind(size_t n, int raw, int zero) {
    if (n == 0) n = 1;
    if (rt_since_gc > rt_threshold) rt_collect();
    RT_COUNT(0);
    RT_COUNT_BY(1, n);
    if (n <= RT_SMALL_MAX) {
        int class_index = (int)((n + 15) / 16) - 1;
        void *p = rt_free_list[raw][class_index];
        if (!p) {
            rt_new_page(raw, class_index);
            p = rt_free_list[raw][class_index];
        }
        rt_free_list[raw][class_index] = *(void **)p;
        {
            rt_page *page = (rt_page *)((uintptr_t)p & ~(uintptr_t)(RT_PAGE - 1));
            rt_page_in_use(page)[rt_block_index(page, (uintptr_t)p)] = 1;
        }
        size_t size = (size_t)(class_index + 1) * 16;
        if (zero) memset(p, 0, size);
        rt_since_gc += size;
        return p;
    }
    char *p = (char *)(zero ? calloc(1, n) : malloc(n));
    if (!p) {
        rt_collect();
        p = (char *)(zero ? calloc(1, n) : malloc(n));
        if (!p) rt_out_of_memory();
    }
    if (rt_nblocks == rt_cap_blocks) {
        rt_cap_blocks = rt_cap_blocks ? rt_cap_blocks * 2 : 4096;
        rt_blocks = (rt_block *)realloc(rt_blocks, rt_cap_blocks * sizeof(rt_block));
        if (!rt_blocks) rt_out_of_memory();
    }
    rt_block *block = &rt_blocks[rt_nblocks++];
    block->p = p;
    block->size = n;
    block->raw = (unsigned char)raw;
    block->mark = 0;
    rt_since_gc += n;
    return p;
}

static void *rt_alloc(size_t n) { return rt_alloc_kind(n, 0, 1); }
/* A block that its caller fills at once: it is not cleared. */
static void *rt_alloc_scan(size_t n) { return rt_alloc_kind(n, 0, 0); }
static void *rt_alloc_raw(size_t n) { return rt_alloc_kind(n, 1, 0); }

/* A raw block that grows: the new one is a copy, and the old one is left for the collector. */
static void *rt_grow_raw(void *old, size_t old_size, size_t size) {
    void *p = rt_alloc_raw(size);
    if (old) memcpy(p, old, old_size < size ? old_size : size);
    return p;
}

/* Text */

static int64_t rt_count_points(const char *p, int64_t bytes) {
    int64_t n = 0;
    for (int64_t i = 0; i < bytes; i++) {
        if (((unsigned char)p[i] & 0xC0) != 0x80) n++;
    }
    return n;
}

static rt_text rt_lit(const char *s) {
    rt_text t;
    t.p = s;
    t.bytes = (int64_t)strlen(s);
    t.len = rt_count_points(s, t.bytes);
    return t;
}

static rt_text rt_concat(rt_text a, rt_text b) {
    rt_text t;
    char *p = (char *)rt_alloc_raw((size_t)(a.bytes + b.bytes + 1));
    memcpy(p, a.p, (size_t)a.bytes);
    memcpy(p + a.bytes, b.p, (size_t)b.bytes);
    p[a.bytes + b.bytes] = 0;
    t.p = p;
    t.bytes = a.bytes + b.bytes;
    t.len = a.len + b.len;
    return t;
}

static int rt_text_compare(rt_text a, rt_text b) {
    RT_COUNT(11);
    if (a.p == b.p && a.bytes == b.bytes) return 0;
    int64_t n = a.bytes < b.bytes ? a.bytes : b.bytes;
    int c = memcmp(a.p, b.p, (size_t)n);
    if (c != 0) return c < 0 ? -1 : 1;
    return a.bytes < b.bytes ? -1 : (a.bytes > b.bytes ? 1 : 0);
}

static rt_text rt_int_text(int64_t n) {
    char buffer[32];
    int len = snprintf(buffer, sizeof buffer, "%lld", (long long)n);
    char *p = (char *)rt_alloc_raw((size_t)len + 1);
    memcpy(p, buffer, (size_t)len + 1);
    rt_text t = {p, len, len};
    return t;
}

static rt_text rt_bool_text(bool b) {
    return b ? rt_lit("true") : rt_lit("false");
}

/* The text of a value as a diagnostic shows it: a Text is quoted and escaped (parser.quote). */
static rt_text rt_quote(rt_text s) {
    char *p = (char *)rt_alloc_raw((size_t)(s.bytes * 2 + 3));
    int64_t n = 0;
    p[n++] = '"';
    for (int64_t i = 0; i < s.bytes; i++) {
        char c = s.p[i];
        if (c == '\\') { p[n++] = '\\'; p[n++] = '\\'; }
        else if (c == '"') { p[n++] = '\\'; p[n++] = '"'; }
        else if (c == '\n') { p[n++] = '\\'; p[n++] = 'n'; }
        else if (c == '\t') { p[n++] = '\\'; p[n++] = 't'; }
        else p[n++] = c;
    }
    p[n++] = '"';
    p[n] = 0;
    rt_text t = {p, n, rt_count_points(p, n)};
    return t;
}

/* The stack of calls and loops, which is what an error explains itself with. */

enum { RT_CALL, RT_COND, RT_MEASURE, RT_BODY };

typedef struct {
    int kind;
    const char *name;
    int file; /* the file of the function, for a call */
    int64_t line;
    int64_t column; /* for a call; for a loop, the turn */
} rt_frame;

#define RT_MAX_FRAMES 200000
#define RT_MAX_CALLS 1000
#define RT_TRACE 6

static rt_frame rt_frames[RT_MAX_FRAMES];
static int rt_top = 0;
static int rt_calls = 0;

/* Pieces of text built for a note. */

typedef struct {
    char *items[128];
    int count;
} rt_notes;

static char *rt_format(const char *format, ...);

static void rt_note(rt_notes *notes, char *text) {
    if (notes->count < 128) notes->items[notes->count++] = text;
}

#include <stdarg.h>

static char *rt_format(const char *format, ...) {
    va_list args;
    va_start(args, format);
    va_list again;
    va_copy(again, args);
    int n = vsnprintf(0, 0, format, args);
    va_end(args);
    char *p = (char *)rt_alloc_raw((size_t)n + 1);
    vsnprintf(p, (size_t)n + 1, format, again);
    va_end(again);
    return p;
}

/* A buffer for what a note shows: "a = 1, b = \"x\"". */

typedef struct {
    char *p;
    size_t n, cap;
    int pairs;
} rt_buf;

static void rt_buf_add(rt_buf *b, const char *s, size_t n) {
    if (b->n + n + 1 > b->cap) {
        size_t cap = (b->n + n + 1) * 2;
        b->p = (char *)rt_grow_raw(b->p, b->cap, cap);
        b->cap = cap;
    }
    memcpy(b->p + b->n, s, n);
    b->n += n;
    b->p[b->n] = 0;
}

static void rt_buf_pair(rt_buf *b, const char *name, rt_text shown) {
    if (b->pairs++ > 0) rt_buf_add(b, ", ", 2);
    rt_buf_add(b, name, strlen(name));
    rt_buf_add(b, " = ", 3);
    rt_buf_add(b, shown.p, (size_t)shown.bytes);
}

static void rt_buf_int(rt_buf *b, const char *name, int64_t v) { rt_buf_pair(b, name, rt_int_text(v)); }
static void rt_buf_bool(rt_buf *b, const char *name, bool v) { rt_buf_pair(b, name, rt_bool_text(v)); }
static void rt_buf_text(rt_buf *b, const char *name, rt_text v) { rt_buf_pair(b, name, rt_quote(v)); }

/* "The values: a = 1" or "It was called with: a = 1", or nothing when there are no pairs. */
static void rt_buf_note(rt_notes *notes, const char *prefix, rt_buf *b) {
    if (b->pairs > 0) rt_note(notes, rt_format("%s%s", prefix, b->p));
}

static char *rt_loop_note(const rt_frame *f) {
    if (f->kind == RT_COND) {
        if (f->column == 0) return rt_format("Before the first turn of the loop at line %lld.", (long long)f->line);
        return rt_format("After turn %lld of the loop at line %lld.", (long long)f->column, (long long)f->line);
    }
    if (f->kind == RT_MEASURE) return rt_format("Before turn %lld of the loop at line %lld.", (long long)f->column, (long long)f->line);
    return rt_format("In turn %lld of the loop at line %lld.", (long long)f->column, (long long)f->line);
}

static bool rt_is_loop_note(const char *s) {
    return strstr(s, " of the loop at line ") != 0;
}

/* The notes of an error: its own, the calls that led to it (innermost first, the first `skip` left out) and the loops it left
 * (innermost first). Both lists stop at six entries, as the interpreter cuts them. */
static void rt_all_notes(rt_notes *out, rt_notes *own, int skip) {
    rt_notes calls = {{0}, 0}, loops = {{0}, 0};
    int total = 0, skipped = 0, loop_count = 0;
    bool more_added = false;
    for (int i = 0; i < own->count; i++) {
        if (rt_is_loop_note(own->items[i])) loop_count++;
    }
    for (int i = rt_top - 1; i >= 0; i--) {
        const rt_frame *f = &rt_frames[i];
        if (f->kind == RT_CALL) {
            if (skipped < skip) {
                skipped++;
            } else if (f->line > 0) {
                total++;
                if (total <= RT_TRACE) {
                    rt_note(&calls, rt_format("In '%s', called at line %lld, column %lld.", f->name, (long long)f->line,
                                              (long long)f->column));
                }
            }
        } else if (!more_added) {
            if (loop_count < RT_TRACE) {
                rt_note(&loops, rt_loop_note(f));
                loop_count++;
            } else {
                rt_note(&loops, rt_format("... and more loops."));
                more_added = true;
            }
        }
    }
    for (int i = 0; i < own->count; i++) rt_note(out, own->items[i]);
    for (int i = 0; i < calls.count; i++) rt_note(out, calls.items[i]);
    if (total > RT_TRACE) {
        int hidden = total - RT_TRACE;
        rt_note(out, rt_format("... and %d more call%s.", hidden, hidden == 1 ? "" : "s"));
    }
    for (int i = 0; i < loops.count; i++) rt_note(out, loops.items[i]);
}

/* A diagnostic, drawn as render() does: the line it points at, carets under the span, the notes and the hint. */

static const char *rt_src_line(int64_t line) {
    if (line < 1 || line > rt_src_lines) return "";
    return rt_src[line - 1];
}

static void rt_spaces(FILE *out, int n) {
    for (int i = 0; i < n; i++) fputc(' ', out);
}

static int rt_digits(int64_t n) {
    char buffer[32];
    return snprintf(buffer, sizeof buffer, "%lld", (long long)n);
}

static void rt_render(const char *category, const char *severity, const char *code, const char *title, const char *label,
                      const char *hint, rt_notes *notes, int64_t line, int64_t column, int64_t end_line,
                      int64_t end_column) {
    fprintf(stderr, "%s %s[%s]: %s\n", category, severity, code, title);
    if (line <= 0) {
        fprintf(stderr, " --> %s\n  = %s\n", rt_path, label);
        for (int i = 0; i < notes->count; i++) fprintf(stderr, "  = note: %s\n", notes->items[i]);
        if (hint && hint[0]) fprintf(stderr, "  = hint: %s\n", hint);
        return;
    }
    const char *text = rt_src_line(line);
    int gutter = rt_digits(line);
    int64_t text_points = rt_count_points(text, (int64_t)strlen(text));
    int64_t width = end_line == line ? end_column - column : text_points - column + 1;
    if (width < 1) width = 1;
    rt_spaces(stderr, gutter);
    fprintf(stderr, "--> %s:%lld:%lld\n", rt_path, (long long)line, (long long)column);
    rt_spaces(stderr, gutter);
    fputs(" |\n", stderr);
    fprintf(stderr, "%lld | %s\n", (long long)line, text);
    rt_spaces(stderr, gutter);
    fputs(" | ", stderr);
    /* The space in front of the carets copies a tab as a tab, so they line up whatever the terminal draws. */
    const char *q = text;
    for (int64_t i = 0; i < column - 1; i++) {
        if (*q) {
            fputc(*q == '\t' ? '\t' : ' ', stderr);
            q++;
            while (((unsigned char)*q & 0xC0) == 0x80) q++;
        } else {
            fputc(' ', stderr);
        }
    }
    for (int64_t i = 0; i < width; i++) fputc('^', stderr);
    fprintf(stderr, " %s\n", label);
    for (int i = 0; i < notes->count; i++) {
        rt_spaces(stderr, gutter);
        fprintf(stderr, " = note: %s\n", notes->items[i]);
    }
    if (hint && hint[0]) {
        rt_spaces(stderr, gutter);
        fprintf(stderr, " = hint: %s\n", hint);
    }
}

/* An error of the program: the diagnostic, then the line `nex run` closes with, and the exit status of `nex run`. */
static void rt_fail(const char *category, const char *code, const char *title, const char *label, const char *hint,
                    rt_notes *own, int skip, int64_t line, int64_t column, int64_t end_line, int64_t end_column) {
    rt_notes notes = {{0}, 0};
    rt_all_notes(&notes, own, skip);
    fflush(stdout);
    {
        /* The file of the function that was running: the caller's when the first `skip` calls are left out. */
        int index = 0, seen = 0;
        for (int i = rt_top - 1; i >= 0; i--) {
            if (rt_frames[i].kind == RT_CALL) {
                if (seen == skip) { index = rt_frames[i].file; break; }
                seen++;
            }
        }
        if (index >= 0 && index < rt_nfiles) {
            rt_path = rt_file_path[index];
            rt_src = rt_file_lines[index];
            rt_src_lines = rt_file_count[index];
        }
    }
    rt_render(category, "error", code, title, label, hint, &notes, line, column, end_line, end_column);
    fputc('\n', stderr);
    bool contract = strcmp(category, "contract") == 0;
    fprintf(stderr, "error: %s: the program stopped because %s\n", rt_entry,
            contract ? "a contract was broken" : "of a runtime error");
    exit(contract ? 5 : 3);
}

#define RT_SPAN int64_t l, int64_t c, int64_t el, int64_t ec

static void rt_runtime(const char *code, const char *title, const char *label, const char *hint, RT_SPAN) {
    rt_notes own = {{0}, 0};
    rt_fail("runtime", code, title, label, hint, &own, 0, l, c, el, ec);
}


/* Values. Every value of a program is an `rv`: the type was checked before, so the generated code does not carry it, and
 * what a value is (an Int, a record, a variant) is read from its tag when it is shown, compared or matched. */

#include <math.h>

enum { RT_UNIT, RT_INT, RT_FLOAT, RT_BOOL, RT_TEXT, RT_LIST, RT_RECORD, RT_VARIANT };

typedef struct rv {
    int tag;
    union {
        int64_t i;
        double f;
        bool b;
        rt_text t;
        void *o;
    } u;
} rv;

/* A list is a count and a view of a buffer of items. The buffer is shared by the lists that were made from each other by adding to
 * the end: `used` says how much of it some list already sees, so a list that sees all of it can be given one more item without
 * copying anything, and an older list, which sees less, is never changed. */
typedef struct { int64_t used, cap; rv items[]; } rt_listbuf;
typedef struct { int64_t n; rv *items; rt_listbuf *buf; } rt_list;
typedef struct { const char *name; int n; const char *const *names; rv f[]; } rt_record;
/* `owner` is the enum a variant belongs to, or "" for the variants of Option and Result. */
typedef struct { const char *owner; const char *kind; int n; rv a[]; } rt_variant;

static rv rt_unit(void) { rv v = {0}; v.tag = RT_UNIT; v.u.i = 0; return v; }
static rv rt_int(int64_t n) { rv v = {0}; v.tag = RT_INT; v.u.i = n; return v; }
static rv rt_float(double x) { rv v = {0}; v.tag = RT_FLOAT; v.u.f = x; return v; }
static rv rt_bool(bool b) { rv v = {0}; v.tag = RT_BOOL; v.u.b = b; return v; }
static rv rt_txt(rt_text t) { rv v = {0}; v.tag = RT_TEXT; v.u.t = t; return v; }
static rv rt_str(const char *s) { return rt_txt(rt_lit(s)); }
static bool rt_truth(rv v) { return v.u.b; }

static rv *rt_copy_values(const rv *items, int64_t n) {
    rv *copy = (rv *)rt_alloc((size_t)(n > 0 ? n : 1) * sizeof(rv));
    for (int64_t i = 0; i < n; i++) copy[i] = items[i];
    return copy;
}

static rt_listbuf *rt_new_listbuf(int64_t cap) {
    rt_listbuf *buf = (rt_listbuf *)rt_alloc(sizeof(rt_listbuf) + (size_t)(cap > 0 ? cap : 1) * sizeof(rv));
    buf->used = 0;
    buf->cap = cap;
    return buf;
}

static rv rt_list_view(rt_listbuf *buf, int64_t n) {
    RT_COUNT(8);
    rt_list *l = (rt_list *)rt_alloc(sizeof(rt_list));
    l->n = n;
    l->buf = buf;
    l->items = buf ? buf->items : 0;
    rv v = {0};
    v.tag = RT_LIST;
    v.u.o = l;
    return v;
}

static rv rt_list_from(const rv *items, int64_t n) {
    if (n == 0) return rt_list_view(0, 0);
    rt_listbuf *buf = rt_new_listbuf(n);
    for (int64_t i = 0; i < n; i++) buf->items[i] = items[i];
    buf->used = n;
    return rt_list_view(buf, n);
}

static rv rt_record_new(const char *name, const char *const *names, int n, const rv *fields) {
    RT_COUNT(6);
    rt_record *r = (rt_record *)rt_alloc_scan(sizeof(rt_record) + (size_t)n * sizeof(rv));
    r->name = name;
    r->n = n;
    r->names = names;
    for (int i = 0; i < n; i++) r->f[i] = fields[i];
    rv v = {0};
    v.tag = RT_RECORD;
    v.u.o = r;
    return v;
}

/* A variant with no payload (`None`, a unit case of an enum) is always the same value, so there is one of each, never freed. */
typedef struct { const char *owner, *kind; rt_variant *value; } rt_nullary_entry;
static rt_nullary_entry rt_nullary[256];
static int rt_nullary_count = 0;

static rv rt_variant_new(const char *owner, const char *kind, int n, const rv *args) {
    RT_COUNT(7);
    if (n == 0) {
        for (int i = 0; i < rt_nullary_count; i++) {
            if (rt_nullary[i].owner == owner && rt_nullary[i].kind == kind) {
                rv shared = {0};
                shared.tag = RT_VARIANT;
                shared.u.o = rt_nullary[i].value;
                return shared;
            }
        }
        if (rt_nullary_count < 256) {
            rt_variant *x = (rt_variant *)malloc(sizeof(rt_variant));
            if (!x) rt_out_of_memory();
            x->owner = owner;
            x->kind = kind;
            x->n = 0;
            rt_nullary[rt_nullary_count].owner = owner;
            rt_nullary[rt_nullary_count].kind = kind;
            rt_nullary[rt_nullary_count].value = x;
            rt_nullary_count++;
            rv first = {0};
            first.tag = RT_VARIANT;
            first.u.o = x;
            return first;
        }
    }
    rt_variant *x = (rt_variant *)rt_alloc_scan(sizeof(rt_variant) + (size_t)n * sizeof(rv));
    x->owner = owner;
    x->kind = kind;
    x->n = n;
    for (int i = 0; i < n; i++) x->a[i] = args[i];
    rv v = {0};
    v.tag = RT_VARIANT;
    v.u.o = x;
    return v;
}

static rt_list *rt_as_list(rv v) { return (rt_list *)v.u.o; }
static rt_record *rt_as_record(rv v) { return (rt_record *)v.u.o; }
static rt_variant *rt_as_variant(rv v) { return (rt_variant *)v.u.o; }

/* A Float as its shortest text that reads back as the same number, as Python's repr writes it. */
static rt_text rt_float_text(double x) {
    char buf[64], digits[32];
    int prec, k = 0, exponent;
    if (x == 0.0) return signbit(x) ? rt_lit("-0.0") : rt_lit("0.0");
    for (prec = 1; prec <= 17; prec++) {
        snprintf(buf, sizeof buf, "%.*e", prec - 1, x);
        if (strtod(buf, 0) == x) break;
    }
    const char *p = buf;
    bool negative = false;
    if (*p == '-') { negative = true; p++; }
    for (; *p && *p != 'e'; p++) {
        if (*p != '.') digits[k++] = *p;
    }
    digits[k] = 0;
    exponent = atoi(p + 1);
    while (k > 1 && digits[k - 1] == '0') digits[--k] = 0;
    char out[96];
    int n = 0;
    if (negative) out[n++] = '-';
    if (exponent >= -4 && exponent < 16) {
        if (exponent >= 0) {
            for (int i = 0; i <= exponent; i++) out[n++] = i < k ? digits[i] : '0';
            out[n++] = '.';
            if (k > exponent + 1) {
                for (int i = exponent + 1; i < k; i++) out[n++] = digits[i];
            } else {
                out[n++] = '0';
            }
        } else {
            out[n++] = '0';
            out[n++] = '.';
            for (int i = 0; i < -exponent - 1; i++) out[n++] = '0';
            for (int i = 0; i < k; i++) out[n++] = digits[i];
        }
    } else {
        out[n++] = digits[0];
        if (k > 1) {
            out[n++] = '.';
            for (int i = 1; i < k; i++) out[n++] = digits[i];
        }
        n += snprintf(out + n, sizeof out - (size_t)n, "e%c%02d", exponent < 0 ? '-' : '+', abs(exponent));
    }
    out[n] = 0;
    char *copy = (char *)rt_alloc_raw((size_t)n + 1);
    memcpy(copy, out, (size_t)n + 1);
    rt_text t = {copy, n, n};
    return t;
}

/* The text of a value: what `print` writes and `to_text` gives, or, when `shown`, how a diagnostic writes it (a Text quoted). */
static void rt_show_into(rt_buf *b, rv v, bool shown) {
    rt_text t;
    switch (v.tag) {
    case RT_UNIT:
        return;
    case RT_INT:
        t = rt_int_text(v.u.i);
        break;
    case RT_FLOAT:
        t = rt_float_text(v.u.f);
        break;
    case RT_BOOL:
        t = rt_bool_text(v.u.b);
        break;
    case RT_TEXT:
        t = shown ? rt_quote(v.u.t) : v.u.t;
        break;
    case RT_LIST: {
        rt_list *l = rt_as_list(v);
        rt_buf_add(b, "[", 1);
        for (int64_t i = 0; i < l->n; i++) {
            if (i > 0) rt_buf_add(b, ", ", 2);
            rt_show_into(b, l->items[i], shown);
        }
        rt_buf_add(b, "]", 1);
        return;
    }
    case RT_RECORD: {
        rt_record *r = rt_as_record(v);
        rt_buf_add(b, r->name, strlen(r->name));
        rt_buf_add(b, "(", 1);
        for (int i = 0; i < r->n; i++) {
            if (i > 0) rt_buf_add(b, ", ", 2);
            rt_buf_add(b, r->names[i], strlen(r->names[i]));
            rt_buf_add(b, ": ", 2);
            rt_show_into(b, r->f[i], shown);
        }
        rt_buf_add(b, ")", 1);
        return;
    }
    default: {
        rt_variant *x = rt_as_variant(v);
        if (x->owner[0]) {
            rt_buf_add(b, x->owner, strlen(x->owner));
            rt_buf_add(b, ".", 1);
            rt_buf_add(b, x->kind, strlen(x->kind));
        } else {
            rt_buf_add(b, x->kind, strlen(x->kind));
        }
        if (x->n > 0 && (x->owner[0] || strcmp(x->kind, "None") != 0)) {
            rt_buf_add(b, "(", 1);
            for (int i = 0; i < x->n; i++) {
                if (i > 0) rt_buf_add(b, ", ", 2);
                rt_show_into(b, x->a[i], shown);
            }
            rt_buf_add(b, ")", 1);
        }
        return;
    }
    }
    rt_buf_add(b, t.p, (size_t)t.bytes);
}

static rt_text rt_show(rv v, bool shown) {
    rt_buf b = {0, 0, 0, 0};
    rt_buf_add(&b, "", 0);
    rt_show_into(&b, v, shown);
    rt_text t = {b.p, (int64_t)b.n, 0};
    t.len = rt_count_points(t.p, t.bytes);
    return t;
}

static rt_text rt_format_value(rv v) { return rt_show(v, false); }

static void rt_buf_val(rt_buf *b, const char *name, rv v) { rt_buf_pair(b, name, rt_show(v, true)); }

/* The limits of resources the user may give (`--max-text`, `--max-output`, `--max-input`); zero is no limit. */
static int64_t rt_max_text = 0, rt_max_output = 0, rt_max_input = 0;
static int64_t rt_written = 0, rt_input_bytes = 0;

/* The program stopped by a limit of the environment: the diagnostic has no position, and `nex run` ends with it alone. */
static void rt_limit_fail(const char *label) {
    fflush(stdout);
    rt_notes none = {{0}, 0};
    rt_path = rt_entry;
    rt_render("runtime", "error", "E3015", "Resource limit exceeded", label, "", &none, 0, 0, 0, 0);
    exit(3);
}

static void rt_emit(const char *data, size_t n) {
    if (rt_max_output > 0) {
        int64_t room = rt_max_output - rt_written;
        if ((int64_t)n > room) {
            /* What fits is printed, without cutting a character in two, and then the program stops. */
            size_t keep = (size_t)(room > 0 ? room : 0);
            while (keep > 0 && keep < n && (((unsigned char)data[keep]) & 0xC0) == 0x80) keep--;
            fwrite(data, 1, keep, stdout);
            rt_limit_fail(rt_format("output limit exceeded (%lld)", (long long)rt_max_output));
        }
        rt_written += (int64_t)n;
    }
    fwrite(data, 1, n, stdout);
}

static void rt_print(rv v) {
    rt_text t = rt_show(v, false);
    rt_buf b = {0, 0, 0, 0};
    rt_buf_add(&b, t.p, (size_t)t.bytes);
    rt_buf_add(&b, "\n", 1);
    rt_emit(b.p, b.n);
}

/* Equality and order, as the interpreter has them. */

static bool rt_eq(rv a, rv b) {
    RT_COUNT(5);
    if (a.tag != b.tag) return false;
    switch (a.tag) {
    case RT_UNIT: return true;
    case RT_INT: return a.u.i == b.u.i;
    case RT_FLOAT: return a.u.f == b.u.f;
    case RT_BOOL: return a.u.b == b.u.b;
    case RT_TEXT: return a.u.t.bytes == b.u.t.bytes && (a.u.t.p == b.u.t.p || memcmp(a.u.t.p, b.u.t.p, (size_t)a.u.t.bytes) == 0);
    case RT_LIST: {
        rt_list *x = rt_as_list(a), *y = rt_as_list(b);
        if (x->n != y->n) return false;
        for (int64_t i = 0; i < x->n; i++) {
            if (!rt_eq(x->items[i], y->items[i])) return false;
        }
        return true;
    }
    case RT_RECORD: {
        rt_record *x = rt_as_record(a), *y = rt_as_record(b);
        if (strcmp(x->name, y->name) != 0 || x->n != y->n) return false;
        for (int i = 0; i < x->n; i++) {
            if (!rt_eq(x->f[i], y->f[i])) return false;
        }
        return true;
    }
    default: {
        rt_variant *x = rt_as_variant(a), *y = rt_as_variant(b);
        if (strcmp(x->owner, y->owner) != 0 || strcmp(x->kind, y->kind) != 0 || x->n != y->n) return false;
        for (int i = 0; i < x->n; i++) {
            if (!rt_eq(x->a[i], y->a[i])) return false;
        }
        return true;
    }
    }
}

static bool rt_less(rv a, rv b) {
    if (a.tag != b.tag) return false;
    if (a.tag == RT_INT) return a.u.i < b.u.i;
    if (a.tag == RT_FLOAT) return a.u.f < b.u.f;
    if (a.tag == RT_TEXT) return rt_text_compare(a.u.t, b.u.t) < 0;
    return false;
}

/* Arithmetic. Each operator names the span an error points at. */

static void rt_overflow(RT_SPAN) {
    rt_runtime("E3002", "Integer overflow", "The result of this operation does not fit in an Int",
               "Int holds whole numbers from -9223372036854775808 to 9223372036854775807.", l, c, el, ec);
}

static void rt_float_range(RT_SPAN) {
    rt_runtime("E3003", "Float result out of range", "The result of this operation is too large for a Float", "", l, c, el, ec);
}

static rv rt_float_checked(double r, RT_SPAN) {
    if (!isfinite(r)) rt_float_range(l, c, el, ec);
    return rt_float(r);
}

/* A Text longer than the limit of the environment stops the program, wherever it was made. */
static rv rt_check_text(rv v, RT_SPAN) {
    if (rt_max_text > 0 && v.tag == RT_TEXT && v.u.t.len > rt_max_text) {
        rt_runtime("E3006", "Text too long",
                   rt_format("This Text is longer than the environment limit of %lld characters", (long long)rt_max_text),
                   "Use a smaller Text value or increase the environment's text limit.", l, c, el, ec);
    }
    return v;
}

static rv rt_str_at(const char *s, RT_SPAN) { return rt_check_text(rt_str(s), l, c, el, ec); }
static rv rt_to_text(rv v, RT_SPAN) { return rt_check_text(rt_txt(rt_format_value(v)), l, c, el, ec); }

static rv rt_add(rv a, rv b, RT_SPAN) {
    if (a.tag == RT_INT) {
        int64_t r;
        if (__builtin_add_overflow(a.u.i, b.u.i, &r)) rt_overflow(l, c, el, ec);
        return rt_int(r);
    }
    if (a.tag == RT_FLOAT) return rt_float_checked(a.u.f + b.u.f, l, c, el, ec);
    return rt_check_text(rt_txt(rt_concat(a.u.t, b.u.t)), l, c, el, ec);
}

static rv rt_sub(rv a, rv b, RT_SPAN) {
    if (a.tag == RT_INT) {
        int64_t r;
        if (__builtin_sub_overflow(a.u.i, b.u.i, &r)) rt_overflow(l, c, el, ec);
        return rt_int(r);
    }
    return rt_float_checked(a.u.f - b.u.f, l, c, el, ec);
}

static rv rt_mul(rv a, rv b, RT_SPAN) {
    if (a.tag == RT_INT) {
        int64_t r;
        if (__builtin_mul_overflow(a.u.i, b.u.i, &r)) rt_overflow(l, c, el, ec);
        return rt_int(r);
    }
    return rt_float_checked(a.u.f * b.u.f, l, c, el, ec);
}

/* The first span is the whole operation, the second the right-hand side. */
static rv rt_div(rv a, rv b, RT_SPAN, int64_t rl, int64_t rc, int64_t rel, int64_t rec) {
    if (a.tag == RT_INT) {
        if (b.u.i == 0) rt_runtime("E3001", "Division by zero", "The right-hand side of this division is zero", "", rl, rc, rel, rec);
        if (a.u.i == INT64_MIN && b.u.i == -1) rt_overflow(l, c, el, ec);
        return rt_int(a.u.i / b.u.i);
    }
    if (b.u.f == 0.0) rt_runtime("E3001", "Division by zero", "The right-hand side of this division is zero", "", rl, rc, rel, rec);
    return rt_float_checked(a.u.f / b.u.f, l, c, el, ec);
}

static rv rt_neg(rv a, RT_SPAN) {
    if (a.tag == RT_FLOAT) return rt_float(-a.u.f);
    if (a.u.i == INT64_MIN) rt_overflow(l, c, el, ec);
    return rt_int(-a.u.i);
}

/* Patterns, fields and loops over lists. */

static bool rt_is_kind(rv v, const char *kind) {
    RT_COUNT(4);
    if (v.tag != RT_VARIANT) return false;
    const char *own = rt_as_variant(v)->kind;
    return own == kind || strcmp(own, kind) == 0;
}

static rv rt_arg(rv v, int i) { return rt_as_variant(v)->a[i]; }

static rv rt_field(rv v, const char *name) {
    RT_COUNT(3);
    rt_record *r = rt_as_record(v);
    for (int i = 0; i < r->n; i++) {
        if (r->names[i] == name) return r->f[i];
    }
    for (int i = 0; i < r->n; i++) {
        if (strcmp(r->names[i], name) == 0) return r->f[i];
    }
    return rt_unit();
}

static int64_t rt_list_len(rv v) { return rt_as_list(v)->n; }
static rv rt_list_at(rv v, int64_t i) { return rt_as_list(v)->items[i]; }

/* The `needs` of a built-in function that is false: the same E4001 as for a function of the program. */
static void rt_builtin_needs(const char *callee, const char *condition, const char *reason, int count,
                             const char *const *names, const rv *args, const char *hint, RT_SPAN) {
    rt_notes own = {{0}, 0};
    rt_note(&own, rt_format("The condition of the built-in function is false: needs %s", condition));
    rt_note(&own, rt_format("Reason: %s", reason));
    rt_buf b = {0, 0, 0, 0};
    for (int i = 0; i < count; i++) rt_buf_val(&b, names[i], args[i]);
    rt_note(&own, rt_format("It was called with: %s", b.p ? b.p : ""));
    rt_fail("contract", "E4001", "Precondition violated",
            rt_format("This call breaks a 'needs' condition of '%s'", callee), hint, &own, 0, l, c, el, ec);
}

/* Text */

/* Where the code point number `point` starts, as a byte. A text that is all ASCII (as many bytes as code points) needs no search. For
 * another one that is long, a table of where every 32nd code point starts is made once and kept for the last such text, so that
 * the lexer, which cuts one character at a time out of the same source, does not read the text from its start every time. */
static const char *rt_index_text = 0;
static int64_t rt_index_bytes = 0;
static int64_t *rt_index_offsets = 0;

static int64_t rt_byte_of_point(rt_text t, int64_t point) {
    if (t.len == t.bytes) return point;
    int64_t byte = 0, seen = 0;
    if (t.bytes >= 256) {
        if (rt_index_text != t.p || rt_index_bytes != t.bytes) {
            free(rt_index_offsets);
            rt_index_offsets = (int64_t *)malloc((size_t)(t.len / 32 + 2) * sizeof(int64_t));
            if (!rt_index_offsets) rt_out_of_memory();
            int64_t points = 0;
            for (int64_t i = 0; i < t.bytes; i++) {
                if (((unsigned char)t.p[i] & 0xC0) != 0x80) {
                    if (points % 32 == 0) rt_index_offsets[points / 32] = i;
                    points++;
                }
            }
            rt_index_text = t.p;
            rt_index_bytes = t.bytes;
        }
        if (point >= t.len) return t.bytes;
        seen = (point / 32) * 32;
        byte = rt_index_offsets[point / 32];
    }
    while (byte < t.bytes && seen < point) {
        byte++;
        while (byte < t.bytes && (((unsigned char)t.p[byte]) & 0xC0) == 0x80) byte++;
        seen++;
    }
    return byte;
}

static rv rt_text_slice(rv text, rv start, rv end, RT_SPAN) {
    static const char *const names[] = {"text", "start", "end"};
    rv args[3];
    args[0] = text;
    args[1] = start;
    args[2] = end;
    rt_text t = text.u.t;
    if (start.u.i < 0) {
        rt_builtin_needs("Text.slice", "start >= 0", "A slice cannot start before the first character", 3, names, args, "", l, c, el, ec);
    }
    if (start.u.i > end.u.i) {
        rt_builtin_needs("Text.slice", "start <= end", "A slice cannot end before it starts", 3, names, args, "", l, c, el, ec);
    }
    if (end.u.i > t.len) {
        rt_builtin_needs("Text.slice", "end <= Text.length(text)", "A slice cannot end after the last character", 3, names, args, "", l, c, el, ec);
    }
    int64_t from = rt_byte_of_point(t, start.u.i), to = rt_byte_of_point(t, end.u.i);
    char *p = (char *)rt_alloc_raw((size_t)(to - from) + 1);
    memcpy(p, t.p + from, (size_t)(to - from));
    p[to - from] = 0;
    rt_text out = {p, to - from, end.u.i - start.u.i};
    return rt_txt(out);
}

static bool rt_has(rt_text t, rt_text part) {
    if (part.bytes == 0) return true;
    for (int64_t i = 0; i + part.bytes <= t.bytes; i++) {
        if (memcmp(t.p + i, part.p, (size_t)part.bytes) == 0) return true;
    }
    return false;
}

static rv rt_text_contains(rv t, rv part) { return rt_bool(rt_has(t.u.t, part.u.t)); }

static rv rt_text_starts(rv t, rv part) {
    return rt_bool(part.u.t.bytes <= t.u.t.bytes && memcmp(t.u.t.p, part.u.t.p, (size_t)part.u.t.bytes) == 0);
}

static rv rt_text_ends(rv t, rv part) {
    return rt_bool(part.u.t.bytes <= t.u.t.bytes &&
                   memcmp(t.u.t.p + t.u.t.bytes - part.u.t.bytes, part.u.t.p, (size_t)part.u.t.bytes) == 0);
}

/* Numbers written in a text (decision 0011): `-?[0-9]+` for an Int, and a decimal with a fraction or an exponent for a Float. */

static bool rt_is_integer_text(rt_text t) {
    int64_t i = 0;
    if (i < t.bytes && t.p[i] == '-') i++;
    if (i >= t.bytes) return false;
    for (; i < t.bytes; i++) {
        if (t.p[i] < '0' || t.p[i] > '9') return false;
    }
    return true;
}

static bool rt_int_value(rt_text t, int64_t *out) {
    if (!rt_is_integer_text(t)) return false;
    int64_t i = 0;
    bool negative = false;
    if (t.p[0] == '-') { negative = true; i = 1; }
    unsigned long long limit = negative ? 9223372036854775808ULL : 9223372036854775807ULL, value = 0;
    for (; i < t.bytes; i++) {
        unsigned digit = (unsigned)(t.p[i] - '0');
        if (value > (limit - digit) / 10) return false;
        value = value * 10 + digit;
    }
    *out = negative ? (int64_t)(0 - value) : (int64_t)value;
    return true;
}

static bool rt_is_decimal_text(rt_text t) {
    int64_t i = 0;
    if (i < t.bytes && t.p[i] == '-') i++;
    int64_t digits = 0;
    while (i < t.bytes && t.p[i] >= '0' && t.p[i] <= '9') { i++; digits++; }
    if (digits == 0 || i >= t.bytes) return false;
    bool fraction = false;
    if (t.p[i] == '.') {
        i++;
        int64_t more = 0;
        while (i < t.bytes && t.p[i] >= '0' && t.p[i] <= '9') { i++; more++; }
        if (more == 0) return false;
        fraction = true;
    }
    if (i == t.bytes) return fraction;
    if (t.p[i] != 'e' && t.p[i] != 'E') return false;
    i++;
    if (i < t.bytes && (t.p[i] == '+' || t.p[i] == '-')) i++;
    int64_t exponent = 0;
    while (i < t.bytes && t.p[i] >= '0' && t.p[i] <= '9') { i++; exponent++; }
    return exponent > 0 && i == t.bytes;
}

static bool rt_float_value(rt_text t, double *out) {
    if (!rt_is_decimal_text(t)) return false;
    char *copy = (char *)rt_alloc_raw((size_t)t.bytes + 1);
    memcpy(copy, t.p, (size_t)t.bytes);
    copy[t.bytes] = 0;
    double x = strtod(copy, 0);
    if (isinf(x)) return false;
    *out = x;
    return true;
}

static rv rt_int_can_parse(rv t) { int64_t n; return rt_bool(rt_int_value(t.u.t, &n)); }
static rv rt_float_can_parse(rv t) { double x; return rt_bool(rt_float_value(t.u.t, &x)); }

static rv rt_int_parse(rv t, RT_SPAN) {
    static const char *const names[] = {"text"};
    int64_t n;
    if (!rt_int_value(t.u.t, &n)) {
        rt_builtin_needs("Int.parse", "Int.can_parse(text)", "Only a whole number within the range of Int can be read as an Int", 1,
                         names, &t, rt_is_integer_text(t.u.t)
                             ? "Int holds whole numbers from -9223372036854775808 to 9223372036854775807."
                             : "Check the text first with Int.can_parse(...), and call Int.parse only when it is true.",
                         l, c, el, ec);
    }
    return rt_int(n);
}

static rv rt_float_parse(rv t, RT_SPAN) {
    static const char *const names[] = {"text"};
    double x;
    if (!rt_float_value(t.u.t, &x)) {
        const char *hint = "Check the text first with Float.can_parse(...), and call Float.parse only when it is true.";
        if (rt_is_integer_text(t.u.t)) hint = "This text is a whole number: read it with to_float(Int.parse(...)).";
        else if (rt_is_decimal_text(t.u.t)) hint = "The number is too large for a Float.";
        rt_builtin_needs("Float.parse", "Float.can_parse(text)",
                         "Only a decimal number that fits in a Float can be read as a Float", 1, names, &t, hint, l, c, el, ec);
    }
    return rt_float(x);
}

static rv rt_to_float(rv n) { return rt_float((double)n.u.i); }

/* The span of the argument is the one an out-of-range conversion points at. */
static rv rt_to_int(rv x, RT_SPAN) {
    if (x.u.f >= 9223372036854775808.0 || x.u.f < -9223372036854775808.0) {
        rt_runtime("E3005", "Conversion out of range", rt_format("%s is outside the range of Int", rt_float_text(x.u.f).p),
                   "Int holds whole numbers from -9223372036854775808 to 9223372036854775807.", l, c, el, ec);
    }
    return rt_int((int64_t)x.u.f);
}

/* Lists */

static rv rt_list_get(rv list, rv index, RT_SPAN) {
    static const char *const names[] = {"xs", "i"};
    rv args[2];
    args[0] = list;
    args[1] = index;
    rt_list *x = rt_as_list(list);
    if (index.u.i < 0 || index.u.i >= x->n) {
        rt_builtin_needs("List.get", "0 <= i and i < List.length(xs)", "An index must be inside the list", 2, names, args, "", l, c, el, ec);
    }
    return x->items[index.u.i];
}

static rv rt_list_append(rv list, rv item) {
    RT_COUNT(9);
    rt_list *x = rt_as_list(list);
    rt_listbuf *buf = x->buf;
    static int no_share = -1;
    if (no_share < 0) no_share = getenv("NEXORA_NO_SHARE") != 0;
    if (!no_share && buf && x->n == buf->used && buf->used < buf->cap) {
        buf->items[buf->used++] = item;
        return rt_list_view(buf, x->n + 1);
    }
    rt_listbuf *copy = rt_new_listbuf(x->n < 4 ? 8 : x->n * 2);
    for (int64_t i = 0; i < x->n; i++) copy->items[i] = x->items[i];
    copy->items[x->n] = item;
    copy->used = x->n + 1;
    return rt_list_view(copy, x->n + 1);
}

static rv rt_list_concat(rv a, rv b) {
    rt_list *x = rt_as_list(a), *y = rt_as_list(b);
    if (y->n == 0) return a;
    if (x->n == 0) return b;
    rt_listbuf *buf = x->buf;
    if (buf && x->n == buf->used && buf->used + y->n <= buf->cap) {
        for (int64_t i = 0; i < y->n; i++) buf->items[buf->used + i] = y->items[i];
        buf->used += y->n;
        return rt_list_view(buf, x->n + y->n);
    }
    rt_listbuf *copy = rt_new_listbuf((x->n + y->n) * 2);
    for (int64_t i = 0; i < x->n; i++) copy->items[i] = x->items[i];
    for (int64_t i = 0; i < y->n; i++) copy->items[x->n + i] = y->items[i];
    copy->used = x->n + y->n;
    return rt_list_view(copy, x->n + y->n);
}

static rv rt_list_contains(rv list, rv item) {
    rt_list *x = rt_as_list(list);
    for (int64_t i = 0; i < x->n; i++) {
        if (rt_eq(x->items[i], item)) return rt_bool(true);
    }
    return rt_bool(false);
}

/* Option and Result */

static rv rt_some(rv x) { return rt_variant_new("", "Some", 1, &x); }
static rv rt_none(void) { return rt_variant_new("", "None", 0, 0); }
static rv rt_ok(rv x) { return rt_variant_new("", "Ok", 1, &x); }
static rv rt_err(rv x) { return rt_variant_new("", "Err", 1, &x); }

static rv rt_option_value(rv v, RT_SPAN) {
    if (rt_is_kind(v, "Some")) return rt_arg(v, 0);
    rt_runtime("E3011", "Option has no value", "This Option has no value",
               "Check it with Option.is_none(...) before reading it, or use Option.value_or(...) to give a value for the case of no value.",
               l, c, el, ec);
    return rt_unit();
}

static rv rt_result_value(rv v, RT_SPAN) {
    if (rt_is_kind(v, "Err")) {
        rt_runtime("E3012", "Result is an error", rt_format("This Result is an error: %s", rt_show(rt_arg(v, 0), true).p),
                   "Check it with Result.is_err(...) before reading it, or use Result.value_or(...) to give a value for the case of error.",
                   l, c, el, ec);
    }
    return rt_arg(v, 0);
}

static rv rt_result_error(rv v, RT_SPAN) {
    if (rt_is_kind(v, "Ok")) {
        rt_runtime("E3013", "Result is not an error", "This Result is not an error",
                   "Check it with Result.is_ok(...) before reading the error.", l, c, el, ec);
    }
    return rt_arg(v, 0);
}

/* A refined type: the value is let through only if it satisfies the condition of every type in its chain. */
static void rt_refine_fail(const char *written, const char *declared, const char *condition, rv value, const char *reason,
                           RT_SPAN) {
    rt_notes own = {{0}, 0};
    if (strcmp(written, declared) == 0) {
        rt_note(&own, rt_format("The condition of '%s' is false: where %s", written, condition));
    } else {
        rt_note(&own, rt_format("'%s' refines '%s', and the condition of '%s' is false: where %s", written, declared, declared,
                                condition));
    }
    rt_note(&own, rt_format("The value: %s", rt_show(value, true).p));
    if (reason && reason[0]) rt_note(&own, rt_format("Reason: %s", reason));
    rt_fail("contract", "E4003", "Refinement violated", rt_format("This value is not a valid %s", written), "", &own, 0, l, c, el, ec);
}

/* Entering and leaving a function. The call that would be the 1,001st nested stops the program. */

#ifdef RT_NO_FRAMES
/* A tool of selfhost/ compiled for speed: calls and loops keep no frames, so an error is not explained by them. */
static int rt_enter(const char *name, int file, int64_t line, int64_t column, int64_t end_line, int64_t end_column) {
    (void)name; (void)file; (void)line; (void)column; (void)end_line; (void)end_column;
    return 0;
}
static void rt_leave(int saved) { (void)saved; }
static void rt_push_loop(int kind, int64_t line, int64_t turn) { (void)kind; (void)line; (void)turn; }
static void rt_pop(void) {}
#else
static int rt_enter(const char *name, int file, int64_t line, int64_t column, int64_t end_line, int64_t end_column) {
    RT_COUNT(10);
#ifdef RT_STATS
    rt_count_function(name);
#endif
    if (rt_calls >= RT_MAX_CALLS) {
        rt_notes own = {{0}, 0};
        rt_fail("runtime", "E3004", "Too many nested calls", "The program nested more than 1000 calls",
                "A recursive function probably never reaches the case where it stops calling itself.", &own, 0, line,
                column, end_line, end_column);
    }
    int saved = rt_top;
    rt_frames[rt_top].kind = RT_CALL;
    rt_frames[rt_top].name = name;
    rt_frames[rt_top].file = file;
    rt_frames[rt_top].line = line;
    rt_frames[rt_top].column = column;
    rt_top++;
    rt_calls++;
    return saved;
}

static void rt_leave(int saved) {
    rt_top = saved;
    rt_calls--;
}

static void rt_push_loop(int kind, int64_t line, int64_t turn) {
    rt_frames[rt_top].kind = kind;
    rt_frames[rt_top].name = "";
    rt_frames[rt_top].file = 0;
    rt_frames[rt_top].line = line;
    rt_frames[rt_top].column = turn;
    rt_top++;
}

static void rt_pop(void) {
    rt_top--;
}
#endif

/* The accessors of the syntax tree (parser.Node), written in C. The compiler and the interpreter of selfhost/ are programs that
 * read that tree all the time, and each of these functions is small enough that the frame of a call costs more than the work.
 * cgen.nex puts them in place of the NEXORA functions of the same name in those files only; the NEXORA definitions say what they
 * do and are what runs under Python, and the comparisons check that the two agree. */

static bool rt_intr_is(rv v, const char *kind) { return v.tag == RT_VARIANT && strcmp(rt_as_variant(v)->kind, kind) == 0; }

static rv rt_intr_kind_of(rv node) {
    if (rt_intr_is(node, "Obj")) return rt_arg(node, 0);
    return rt_str("");
}

static rv rt_intr_null(void) { return rt_variant_new("parser.Node", "Null", 0, 0); }

static rv rt_intr_index_of(rv names, rv name) {
    rt_list *list = rt_as_list(names);
    for (int64_t i = 0; i < list->n; i++) {
        rt_text a = list->items[i].u.t, b = name.u.t;
        if (a.bytes == b.bytes && (a.p == b.p || memcmp(a.p, b.p, (size_t)a.bytes) == 0)) return rt_int(i);
    }
    return rt_int(-1);
}

static rv rt_intr_field_at(rv names, rv values, rv name) {
    int64_t at = rt_intr_index_of(names, name).u.i;
    if (at < 0) return rt_intr_null();
    return rt_as_list(values)->items[at];
}

static rv rt_intr_field(rv node, rv name) {
    if (!rt_intr_is(node, "Obj")) return rt_intr_null();
    return rt_intr_field_at(rt_arg(node, 1), rt_arg(node, 2), name);
}

/* The same list with one item replaced. */
static rv rt_intr_replace_val(rv vals, rv at, rv value) {
    rt_list *x = rt_as_list(vals);
    if (x->n == 0) return vals;
    rt_listbuf *copy = rt_new_listbuf(x->n);
    for (int64_t i = 0; i < x->n; i++) copy->items[i] = i == at.u.i ? value : x->items[i];
    copy->used = x->n;
    return rt_list_view(copy, x->n);
}

/* `assign` of the interpreter: the environment is a list of frames, each a record of names and values (in that order). The
 * innermost frame that has the name gets the new value; the new frame is made like the old one. */
static rv rt_intr_assign(rv env, rv name, rv value) {
    rt_list *frames = rt_as_list(env);
    int64_t found = -1, place = -1;
    for (int64_t i = frames->n - 1; i >= 0 && found < 0; i--) {
        rt_record *frame = rt_as_record(frames->items[i]);
        rt_list *names = rt_as_list(frame->f[0]);
        for (int64_t k = 0; k < names->n; k++) {
            rt_text a = names->items[k].u.t, b = name.u.t;
            if (a.bytes == b.bytes && (a.p == b.p || memcmp(a.p, b.p, (size_t)a.bytes) == 0)) { found = i; place = k; break; }
        }
    }
    if (found < 0) return env;
    rt_record *old = rt_as_record(frames->items[found]);
    rv fields[2];
    fields[0] = old->f[0];
    fields[1] = rt_intr_replace_val(old->f[1], rt_int(place), value);
    rv frame = rt_record_new(old->name, old->names, 2, fields);
    rt_listbuf *copy = rt_new_listbuf(frames->n);
    for (int64_t i = 0; i < frames->n; i++) copy->items[i] = i == found ? frame : frames->items[i];
    copy->used = frames->n;
    return rt_list_view(copy, frames->n);
}

/* The code of the first character of a text, and the character of a code (selfhost/json.nex). */
static rv rt_intr_code_of(rv text) {
    rt_text t = text.u.t;
    if (t.bytes == 0) return rt_int(0);
    const unsigned char *p = (const unsigned char *)t.p;
    int64_t code;
    if (p[0] < 0x80) code = p[0];
    else if ((p[0] >> 5) == 6 && t.bytes >= 2) code = ((p[0] & 0x1F) << 6) | (p[1] & 0x3F);
    else if ((p[0] >> 4) == 14 && t.bytes >= 3) code = ((p[0] & 0x0F) << 12) | ((p[1] & 0x3F) << 6) | (p[2] & 0x3F);
    else if ((p[0] >> 3) == 30 && t.bytes >= 4)
        code = ((int64_t)(p[0] & 0x07) << 18) | ((p[1] & 0x3F) << 12) | ((p[2] & 0x3F) << 6) | (p[3] & 0x3F);
    else code = -1;
    return rt_int(code);
}

static rv rt_intr_char_from_code(rv code) {
    int64_t c = code.u.i;
    char buffer[5];
    int n = 0;
    if (c < 0 || c > 0x10FFFF || (c >= 0xD800 && c <= 0xDFFF)) return rt_str("");
    if (c < 0x80) { buffer[n++] = (char)c; }
    else if (c < 0x800) { buffer[n++] = (char)(0xC0 | (c >> 6)); buffer[n++] = (char)(0x80 | (c & 0x3F)); }
    else if (c < 0x10000) {
        buffer[n++] = (char)(0xE0 | (c >> 12)); buffer[n++] = (char)(0x80 | ((c >> 6) & 0x3F)); buffer[n++] = (char)(0x80 | (c & 0x3F));
    } else {
        buffer[n++] = (char)(0xF0 | (c >> 18)); buffer[n++] = (char)(0x80 | ((c >> 12) & 0x3F));
        buffer[n++] = (char)(0x80 | ((c >> 6) & 0x3F)); buffer[n++] = (char)(0x80 | (c & 0x3F));
    }
    buffer[n] = 0;
    char *copy = (char *)rt_alloc_raw((size_t)n + 1);
    memcpy(copy, buffer, (size_t)n + 1);
    rt_text t = {copy, n, 1};
    return rt_txt(t);
}

/* The limits the worker of the playground puts on itself (nexora/src/nexora/worker.py, `_apply_os_limits`): the address space,
 * the seconds of CPU and of the clock, and no files, no core and no processes. The host (the container) imposes them too; this
 * makes them a fact of the process. A value of 0 leaves that limit alone. They are POSIX: on Windows nothing is applied. */
#ifndef _WIN32
#include <signal.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

#ifndef _WIN32
/* The memory a container gives its processes, if the system says so (cgroup v2, then v1): 0 when there is no limit. A process that
 * crosses it is killed by the kernel with nothing said; limiting the address space a little below makes the allocation fail
 * inside the program, which can answer. */
static int64_t rt_read_limit(const char *path) {
    FILE *file = fopen(path, "r");
    char text[64];
    if (!file) return 0;
    if (!fgets(text, sizeof text, file)) { fclose(file); return 0; }
    fclose(file);
    if (text[0] < '0' || text[0] > '9') return 0; /* "max" */
    long long value = atoll(text);
    return value > 0 && value < ((long long)1 << 50) ? (int64_t)value : 0;
}

static int64_t rt_cgroup_limit(void) {
    char line[512], path[600];
    FILE *file = fopen("/proc/self/cgroup", "r");
    if (file) {
        while (fgets(line, sizeof line, file)) {
            if (strncmp(line, "0::", 3) != 0) continue;
            size_t n = strlen(line);
            while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
            snprintf(path, sizeof path, "/sys/fs/cgroup%s/memory.max", line + 3);
            int64_t value = rt_read_limit(path);
            if (value) { fclose(file); return value; }
        }
        fclose(file);
    }
    int64_t value = rt_read_limit("/sys/fs/cgroup/memory.max");
    if (value) return value;
    return rt_read_limit("/sys/fs/cgroup/memory/memory.limit_in_bytes");
}
#endif

static rv rt_intr_apply_limits(rv memory, rv cpu, rv wall, rv reply) {
    rt_text r = reply.u.t;
    char *copy = (char *)malloc((size_t)r.bytes + 1);
    if (copy) {
        memcpy(copy, r.p, (size_t)r.bytes);
        copy[r.bytes] = 0;
        rt_oom_reply = copy;
    }
#ifndef _WIN32
    struct rlimit limit;
    int64_t space = memory.u.i;
    int64_t container = rt_cgroup_limit();
    if (container > 0) {
        int64_t room = container - container / 8;
        if (room >= ((int64_t)64 << 20) && (space <= 0 || space > room)) space = room;
    }
    if (space > 0) { limit.rlim_cur = limit.rlim_max = (rlim_t)space; setrlimit(RLIMIT_AS, &limit); }
    if (cpu.u.i > 0) { limit.rlim_cur = limit.rlim_max = (rlim_t)cpu.u.i; setrlimit(RLIMIT_CPU, &limit); }
    limit.rlim_cur = limit.rlim_max = 0;
    setrlimit(RLIMIT_FSIZE, &limit);
    setrlimit(RLIMIT_CORE, &limit);
#ifdef RLIMIT_NPROC
    setrlimit(RLIMIT_NPROC, &limit);
#endif
    if (wall.u.i > 0) alarm((unsigned)wall.u.i);
#else
    (void)memory; (void)cpu; (void)wall;
#endif
    return rt_unit();
}

/* The JSON of a text (selfhost/json.nex, `escaped`) and the join of many texts (selfhost/parser.nex, `join_texts`), each in one
 * pass: building them one piece at a time copies the text again at every piece, which for the output of a program is the
 * longest thing the worker writes. */
static rv rt_intr_json_escaped(rv text) {
    rt_text t = text.u.t;
    char *out = (char *)rt_alloc_raw((size_t)t.bytes * 6 + 3);
    size_t n = 0;
    int64_t points = 2;
    out[n++] = '"';
    for (int64_t i = 0; i < t.bytes; i++) {
        unsigned char c = (unsigned char)t.p[i];
        const char *escape = 0;
        char hex[8];
        if (c == '"') escape = "\\\"";
        else if (c == '\\') escape = "\\\\";
        else if (c == 10) escape = "\\n";
        else if (c == 9) escape = "\\t";
        else if (c == 13) escape = "\\r";
        else if (c == 8) escape = "\\b";
        else if (c == 12) escape = "\\f";
        else if (c < 32) { snprintf(hex, sizeof hex, "\\u%04x", c); escape = hex; }
        if (escape) {
            size_t k = strlen(escape);
            memcpy(out + n, escape, k);
            n += k;
            points += (int64_t)k;
        } else {
            out[n++] = (char)c;
            if ((c & 0xC0) != 0x80) points++;
        }
    }
    out[n++] = '"';
    out[n] = 0; /* a Text is also read as a C string (file names) */
    rt_text r = {out, (int64_t)n, points};
    return rt_txt(r);
}

static rv rt_intr_join_texts(rv items, rv separator) {
    int64_t count = rt_list_len(items);
    rt_text s = separator.u.t;
    size_t total = 0;
    int64_t points = 0;
    for (int64_t i = 0; i < count; i++) {
        rt_text piece = rt_list_at(items, i).u.t;
        total += (size_t)piece.bytes;
        points += piece.len;
    }
    if (count > 1) {
        total += (size_t)s.bytes * (size_t)(count - 1);
        points += s.len * (count - 1);
    }
    char *out = (char *)rt_alloc_raw(total + 1);
    size_t n = 0;
    for (int64_t i = 0; i < count; i++) {
        if (i > 0) { memcpy(out + n, s.p, (size_t)s.bytes); n += (size_t)s.bytes; }
        rt_text piece = rt_list_at(items, i).u.t;
        memcpy(out + n, piece.p, (size_t)piece.bytes);
        n += (size_t)piece.bytes;
    }
    out[n] = 0;
    rt_text r = {out, (int64_t)n, points};
    return rt_txt(r);
}

/* Three things a command-line tool written in NEXORA needs and the language does not have (selfhost/nex.nex): a line on the
 * standard error, the exit status of the process, and the reason why a file cannot be read ("" when it can). */
static rv rt_intr_eprint(rv text) {
    rt_text t = text.u.t;
    fflush(stdout); /* what was printed before reaches the terminal before the error does */
    fwrite(t.p, 1, (size_t)t.bytes, stderr);
    fputc('\n', stderr);
    return rt_unit();
}

static rv rt_intr_exit_with(rv code) {
    rt_exit_status = (int)code.u.i;
    return rt_unit();
}

static rv rt_intr_file_problem(rv path) {
    rt_text t = path.u.t;
    char *name = (char *)malloc((size_t)t.bytes + 1);
    if (!name) return rt_str("");
    memcpy(name, t.p, (size_t)t.bytes);
    name[t.bytes] = 0;
    errno = 0;
    FILE *file = fopen(name, "rb");
    free(name);
    if (file) { fclose(file); return rt_str(""); }
    const char *reason = strerror(errno);
    size_t n = strlen(reason);
    char *copy = (char *)rt_alloc_raw(n + 1);
    memcpy(copy, reason, n + 1);
    rt_text r = {copy, (int64_t)n, (int64_t)n};
    return rt_txt(r);
}

/* One line of the standard input for the program a tool runs (selfhost/interpreter.nex, `read_stdin_line`): a list with the line, without
 * its line break, or an empty list at the end of the input. */
static rv rt_intr_read_stdin_line(void) {
    fflush(stdout);
    size_t cap = 128, n = 0;
    char *line = (char *)rt_alloc_raw(cap);
    int ch;
    bool any = false;
    while ((ch = getc(stdin)) != EOF) {
        any = true;
        if (ch == '\n') break;
        if (n + 2 > cap) {
            char *bigger = (char *)rt_alloc_raw(cap * 2);
            memcpy(bigger, line, n);
            line = bigger;
            cap *= 2;
        }
        line[n++] = (char)ch;
    }
    if (!any) return rt_list_from(0, 0);
    if (n > 0 && line[n - 1] == '\r') n--;
    line[n] = 0;
    int64_t points = 0;
    for (size_t i = 0; i < n; i++) if (((unsigned char)line[i] & 0xC0) != 0x80) points++;
    rt_text t = {line, (int64_t)n, points};
    rv item = rt_txt(t);
    return rt_list_from(&item, 1);
}

/* `nex run --timeout` and `--max-memory` (selfhost/nex.nex). The time limit is a timer that stops the process with the message of
 * the diagnostic and status 3; it counts from `start_timeout`, as Python's counts from the run. Both answer whether the system can do it
 * (the timer needs POSIX, the address-space limit needs Linux), which is what Python's usage errors say. */
static const char *rt_timeout_text = 0, *rt_timeout_message = 0;

#ifndef _WIN32
#include <sys/time.h>
static void rt_on_timeout(int sig) {
    (void)sig;
    fflush(stdout);
    if (rt_timeout_message) {
        size_t n = strlen(rt_timeout_message);
        if (write(2, rt_timeout_message, n) < 0) { /* nothing to do */ }
        if (write(2, "\n", 1) < 0) { /* nothing to do */ }
    }
    _exit(3);
}
#endif

static char *rt_copy_text(rt_text t) {
    char *copy = (char *)malloc((size_t)t.bytes + 1);
    if (!copy) return 0;
    memcpy(copy, t.p, (size_t)t.bytes);
    copy[t.bytes] = 0;
    return copy;
}

static rv rt_intr_prepare_timeout(rv seconds, rv message) {
#ifdef _WIN32
    (void)seconds; (void)message;
    return rt_bool(false);
#else
    rt_timeout_text = rt_copy_text(seconds.u.t);
    rt_timeout_message = rt_copy_text(message.u.t);
    return rt_bool(true);
#endif
}

static rv rt_intr_start_timeout(void) {
#ifndef _WIN32
    if (!rt_timeout_text) return rt_unit();
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = rt_on_timeout;
    sigemptyset(&action.sa_mask);
    sigaction(SIGALRM, &action, 0);
    double value = strtod(rt_timeout_text, 0);
    struct itimerval timer;
    timer.it_interval.tv_sec = 0;
    timer.it_interval.tv_usec = 0;
    timer.it_value.tv_sec = (time_t)value;
    timer.it_value.tv_usec = (suseconds_t)((value - (double)(time_t)value) * 1e6);
    if (timer.it_value.tv_sec == 0 && timer.it_value.tv_usec == 0) timer.it_value.tv_usec = 1;
    setitimer(ITIMER_REAL, &timer, 0);
#endif
    return rt_unit();
}

static rv rt_intr_set_memory_limit(rv bytes, rv message) {
#if defined(__linux__)
    struct rlimit limit;
    limit.rlim_cur = limit.rlim_max = (rlim_t)bytes.u.i;
    if (setrlimit(RLIMIT_AS, &limit) != 0) return rt_bool(false);
    rt_oom_stderr = rt_copy_text(message.u.t);
    return rt_bool(true);
#else
    (void)bytes; (void)message;
    return rt_bool(false);
#endif
}

/* What a program printed, written as it is printed (selfhost/interpreter.nex): without a line break of its own. */
static rv rt_intr_can_stream(void) { return rt_bool(true); }

static rv rt_intr_stream_text(rv text) {
    rt_text t = text.u.t;
    fwrite(t.p, 1, (size_t)t.bytes, stdout);
    return rt_unit();
}

static rv rt_intr_byte_length(rv text) { return rt_int(text.u.t.bytes); }

static rv rt_intr_text_of(rv node) { return rt_intr_is(node, "Str") ? rt_arg(node, 0) : rt_str(""); }
static rv rt_intr_items_of(rv node) { return rt_intr_is(node, "Items") ? rt_arg(node, 0) : rt_list_from(0, 0); }
static rv rt_intr_is_null(rv node) { return rt_bool(rt_intr_is(node, "Null")); }
static rv rt_intr_flag_of(rv node) { return rt_intr_is(node, "Flag") ? rt_arg(node, 0) : rt_bool(false); }
static rv rt_intr_int_of(rv node) { return rt_intr_is(node, "Whole") ? rt_arg(node, 0) : rt_int(0); }

/* The host: what the program may do besides computing. A program declares what it needs (`uses read "data"`), the user allows it
 * with options of the executable (`--allow-read data`), and both have to cover a path for the program to use it (decision 0015). */

#ifdef _WIN32
#include <direct.h>
#define rt_getcwd _getcwd
#else
#include <unistd.h>
#define rt_getcwd getcwd
#endif
#include <errno.h>

#define RT_MAX_SCOPES 64
static const char *rt_declared_kind[RT_MAX_SCOPES], *rt_declared_path[RT_MAX_SCOPES];
static int rt_declared = 0;
static const char *rt_granted_kind[RT_MAX_SCOPES], *rt_granted_path[RT_MAX_SCOPES];
static int rt_granted = 0;
static const char *const *rt_args_list = 0;
static int rt_args_count = 0;

static void rt_declare(const char *kind, const char *path) {
    if (rt_declared < RT_MAX_SCOPES) {
        rt_declared_kind[rt_declared] = kind;
        rt_declared_path[rt_declared] = path;
        rt_declared++;
    }
}

/* A path split in its root and its segments, with `.` and `..` resolved and without touching the file system. */
typedef struct {
    char root[8];
    char *seg[128];
    int n;
} rt_parts;

static void rt_split(const char *path, rt_parts *p) {
    size_t len = strlen(path);
    char *text = (char *)rt_alloc_raw(len + 1);
    for (size_t i = 0; i <= len; i++) text[i] = path[i] == '\\' ? '/' : path[i];
    p->root[0] = 0;
    p->n = 0;
    char *cursor = text;
    if (text[0] == '/') {
        strcpy(p->root, "/");
        cursor = text + 1;
    } else if (len > 1 && text[1] == ':') {
        p->root[0] = (text[0] >= 'a' && text[0] <= 'z') ? (char)(text[0] - 32) : text[0];
        p->root[1] = ':';
        p->root[2] = 0;
        cursor = text + 2;
    }
    char *start = cursor;
    for (;; cursor++) {
        if (*cursor == '/' || *cursor == 0) {
            bool last = *cursor == 0;
            *cursor = 0;
            if (start[0] != 0 && strcmp(start, ".") != 0) {
                if (strcmp(start, "..") == 0) {
                    if (p->n > 0 && strcmp(p->seg[p->n - 1], "..") != 0) p->n--;
                    else if (p->root[0] == 0 && p->n < 128) p->seg[p->n++] = start;
                } else if (p->n < 128) {
                    p->seg[p->n++] = start;
                }
            }
            start = cursor + 1;
            if (last) break;
        }
    }
}

static const char *rt_absolute(const char *path) {
    bool absolute = path[0] == '/' || path[0] == '\\' || (strlen(path) > 1 && path[1] == ':');
    if (absolute) return path;
    char cwd[1024];
    if (!rt_getcwd(cwd, sizeof cwd)) return path;
    return rt_format("%s/%s", cwd, path);
}

static bool rt_inside(const char *scope, const char *path) {
    if (scope[0] == 0) return false;
    rt_parts inner, outer;
    rt_split(rt_absolute(scope), &inner);
    rt_split(rt_absolute(path), &outer);
    if (strcmp(inner.root, outer.root) != 0 || outer.n < inner.n) return false;
    for (int i = 0; i < inner.n; i++) {
        if (strcmp(inner.seg[i], outer.seg[i]) != 0) return false;
    }
    return true;
}

/* Why the program may not use a path, or 0 when it may. */
static const char *rt_denied(const char *kind, const char *path) {
#ifdef RT_CLI
    /* A command-line tool (nex.nex) reads and writes the files it is asked to; what the program it runs may do is its own host. */
    (void)kind; (void)path;
    return 0;
#endif
    bool declared = false, granted = false;
    for (int i = 0; i < rt_declared; i++) {
        if (strcmp(rt_declared_kind[i], kind) == 0 && rt_inside(rt_declared_path[i], path)) declared = true;
    }
    if (!declared) return rt_format("this program does not declare that it needs to %s '%s'", kind, path);
    for (int i = 0; i < rt_granted; i++) {
        if (strcmp(rt_granted_kind[i], kind) == 0 && rt_inside(rt_granted_path[i], path)) granted = true;
    }
    if (!granted) return rt_format("'%s' is not among the paths the user allowed to %s", path, kind);
    return 0;
}

static void rt_denied_fail(const char *message, const char *kind, RT_SPAN) {
    rt_runtime("E3008", "Permission denied", message,
               strcmp(kind, "read") == 0
                   ? "A program reads a file when it declares it with 'uses read' and the user allows it with --allow-read."
                   : "A program writes a file when it declares it with 'uses write' and the user allows it with --allow-write.",
               l, c, el, ec);
}

static bool rt_valid_utf8(const unsigned char *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        unsigned char b = s[i];
        size_t more = b < 0x80 ? 0 : (b >> 5) == 6 ? 1 : (b >> 4) == 14 ? 2 : (b >> 3) == 30 ? 3 : 99;
        if (more == 99) return false;
        for (size_t k = 1; k <= more; k++) {
            if (i + k >= n || (s[i + k] & 0xC0) != 0x80) return false;
        }
        i += more + 1;
    }
    return true;
}

static rv rt_read_file(rv path, RT_SPAN) {
    const char *name = path.u.t.p;
    const char *why = rt_denied("read", name);
    if (why) rt_denied_fail(why, "read", l, c, el, ec);
    FILE *f = fopen(name, "rb");
    if (!f) {
        rt_runtime("E3010", "File error", rt_format("The file '%s' could not be read: %s", name, strerror(errno)), "", l, c, el, ec);
    }
    size_t cap = 4096, n = 0;
    unsigned char *data = (unsigned char *)rt_alloc_raw(cap);
    int ch;
    while ((ch = fgetc(f)) != EOF) {
        if (n + 1 >= cap) {
            cap *= 2;
            data = (unsigned char *)rt_grow_raw(data, cap / 2, cap);
        }
        data[n++] = (unsigned char)ch;
    }
    fclose(f);
    /* Universal line breaks, as Python reads a text file: \r\n and \r become \n. */
    size_t out = 0;
    for (size_t i = 0; i < n; i++) {
        if (data[i] == '\r') {
            data[out++] = '\n';
            if (i + 1 < n && data[i + 1] == '\n') i++;
        } else {
            data[out++] = data[i];
        }
    }
    data[out] = 0;
    if (!rt_valid_utf8(data, out)) {
        rt_runtime("E3010", "File error", rt_format("The file '%s' is not UTF-8 text", name),
                   "NEXORA reads text files: the file has to be saved as UTF-8.", l, c, el, ec);
    }
    rt_text t = {(const char *)data, (int64_t)out, rt_count_points((const char *)data, (int64_t)out)};
    return rt_check_text(rt_txt(t), l, c, el, ec);
}

static rv rt_write_file(rv path, rv text, RT_SPAN) {
    const char *name = path.u.t.p;
    const char *why = rt_denied("write", name);
    if (why) rt_denied_fail(why, "write", l, c, el, ec);
    FILE *f = fopen(name, "w");
    if (!f) {
        rt_runtime("E3010", "File error", rt_format("The file '%s' could not be written: %s", name, strerror(errno)), "", l, c, el, ec);
    }
    fwrite(text.u.t.p, 1, (size_t)text.u.t.bytes, f);
    fclose(f);
    return rt_unit();
}

static rv rt_input(RT_SPAN) {
    fflush(stdout); /* what was printed reaches whoever answers this input (a controller that waits for it) */
    size_t cap = 128, n = 0;
    char *line = (char *)rt_alloc_raw(cap);
    int ch;
    bool any = false;
    /* The line is read in one piece of at most the room left in the input, or of what a Text may be (four bytes a character). */
    int64_t remaining = rt_max_input > 0 ? rt_max_input - rt_input_bytes : -1;
    int64_t piece = remaining >= 0 ? remaining + 1 : -1;
    if (rt_max_text > 0) {
        int64_t text_piece = 4 * (rt_max_text + 1) + 1;
        if (piece < 0 || text_piece < piece) piece = text_piece;
    }
    int64_t raw = 0;
    while ((piece < 0 || raw < piece) && (ch = fgetc(stdin)) != EOF) {
        any = true;
        raw++;
        if (ch == '\n') break;
        if (n + 1 >= cap) {
            cap *= 2;
            line = (char *)rt_grow_raw(line, cap / 2, cap);
        }
        line[n++] = (char)ch;
    }
    if (any && remaining >= 0 && raw > remaining) {
        rt_limit_fail(rt_format("input limit exceeded (%lld)", (long long)rt_max_input));
    }
    if (any) rt_input_bytes += raw;
    if (!any) {
        rt_runtime("E3009", "No more input", "There is no more input to read", "The standard input ended. Check it before reading again.",
                   l, c, el, ec);
    }
    if (n > 0 && line[n - 1] == '\r') n--;
    line[n] = 0;
    rt_text t = {line, (int64_t)n, rt_count_points(line, (int64_t)n)};
    return rt_check_text(rt_txt(t), l, c, el, ec);
}

/* `Net.get` and `Process.run`. The decisions are the ones of the Python host (an HTTPS URL without credentials and on port 443;
 * what the program declares and what the user allowed). Doing the request or starting the process needs a TLS library and a
 * process supervisor that these executables do not have yet, so when every rule allows the operation the program stops with a
 * diagnostic that says so, instead of pretending. */

/* The origin an HTTPS URL goes to, as urlsplit and the idna codec read it, or 0 when it is not one this host admits. */
static const char *rt_origin(const char *url, int *port_out) {
    size_t n = strlen(url);
    if (n < 8 || (url[0] | 32) != 'h' || (url[1] | 32) != 't' || (url[2] | 32) != 't' || (url[3] | 32) != 'p' ||
        (url[4] | 32) != 's' || url[5] != ':' || url[6] != '/' || url[7] != '/') return 0;
    const char *authority = url + 8;
    size_t end = 0;
    while (authority[end] && authority[end] != '/' && authority[end] != '?' && authority[end] != '#') end++;
    char *text = (char *)rt_alloc_raw(end + 1);
    memcpy(text, authority, end);
    text[end] = 0;
    char *at = strrchr(text, '@');
    char *hostport = text;
    if (at) {
        for (char *c = text; c < at; c++) {
            if (*c != ':') return 0;
        }
        hostport = at + 1;
    }
    for (char *c = hostport; *c; c++) {
        if ((unsigned char)*c < 0x21 || (unsigned char)*c > 0x7e || *c == '[' || *c == ']') return 0;
    }
    char *colon = strrchr(hostport, ':');
    int port = 443;
    if (colon) {
        *colon = 0;
        const char *digits = colon + 1;
        if (digits[0]) {
            long value = 0;
            for (const char *c = digits; *c; c++) {
                if (*c < '0' || *c > '9') return 0;
                value = value * 10 + (*c - '0');
                if (value > 65535) return 0;
            }
            port = (int)value;
        }
    }
    if (port != 443 || hostport[0] == 0) return 0;
    size_t length = strlen(hostport);
    size_t label = 0;
    for (size_t i = 0; i <= length; i++) {
        if (i == length || hostport[i] == '.') {
            if ((label < 1 && !(i == length && length > 0 && hostport[length - 1] == '.')) || label > 63) return 0;
            label = 0;
        } else {
            label++;
        }
    }
    for (size_t i = 0; i < length; i++) {
        if (hostport[i] >= 'A' && hostport[i] <= 'Z') hostport[i] = (char)(hostport[i] + 32);
    }
    *port_out = port;
    return rt_format("https://%s", hostport);
}

static bool rt_scope_allows_origin(const char *scope, const char *origin) {
    int a, b;
    const char *declared = rt_origin(scope, &a);
    const char *wanted = rt_origin(origin, &b);
    return declared && wanted && strcmp(declared, wanted) == 0;
}

static bool rt_has_scope(const char *const *kinds, const char *const *paths, int count, const char *kind, const char *origin) {
    for (int i = 0; i < count; i++) {
        if (strcmp(kinds[i], kind) == 0 && rt_scope_allows_origin(paths[i], origin)) return true;
    }
    return false;
}

static rv rt_net_get(rv url, RT_SPAN) {
    int port;
    const char *origin = rt_origin(url.u.t.p, &port);
    static const char *hint = "A program needs 'uses network' and the matching --allow-network origin; the environment may still deny network access.";
    if (!origin) {
        rt_runtime("E3014", "External operation failed", "only HTTPS URLs without credentials and on port 443 are allowed", "", l, c, el, ec);
    }
    if (!rt_has_scope(rt_declared_kind, rt_declared_path, rt_declared, "network", origin)) {
        rt_runtime("E3008", "Permission denied", rt_format("this program does not declare network access to '%s'", origin), hint, l, c, el, ec);
    }
    if (!rt_has_scope(rt_granted_kind, rt_granted_path, rt_granted, "network", origin)) {
        rt_runtime("E3008", "Permission denied", rt_format("'%s' is not among the network origins the user allowed", origin), hint, l, c, el, ec);
    }
    rt_runtime("E3014", "External operation failed", "HTTPS requests are not available in a program built by the C generator yet",
               "Run the program with `nex run`, which can make them.", l, c, el, ec);
    return rt_unit();
}

static bool rt_has_command(const char *const *kinds, const char *const *paths, int count, const char *command) {
    for (int i = 0; i < count; i++) {
        if (strcmp(kinds[i], "process") == 0 && strcmp(paths[i], command) == 0) return true;
    }
    return false;
}

static rv rt_process_run(rv command, RT_SPAN) {
    const char *name = command.u.t.p;
    static const char *hint = "A program needs 'uses process' and the matching --allow-process command; the environment may still deny external processes.";
    if (!rt_has_command(rt_declared_kind, rt_declared_path, rt_declared, name)) {
        rt_runtime("E3008", "Permission denied", rt_format("this program does not declare permission to run '%s'", name), hint, l, c, el, ec);
    }
    if (!rt_has_command(rt_granted_kind, rt_granted_path, rt_granted, name)) {
        rt_runtime("E3008", "Permission denied", rt_format("'%s' is not among the commands the user allowed", name), hint, l, c, el, ec);
    }
    rt_runtime("E3014", "External operation failed", "external processes are not available in a program built by the C generator yet",
               "Run the program with `nex run`, which can start them.", l, c, el, ec);
    return rt_unit();
}

static rv rt_args(RT_SPAN) {
    rv *items = (rv *)rt_alloc((size_t)(rt_args_count > 0 ? rt_args_count : 1) * sizeof(rv));
    for (int i = 0; i < rt_args_count; i++) items[i] = rt_check_text(rt_str(rt_args_list[i]), l, c, el, ec);
    return rt_list_from(items, rt_args_count);
}

/* The command line of an executable is the one of `nex run`: the options of the user, then `--`, then the arguments of the
 * program. */
static void rt_options(int argc, char **argv) {
#ifdef RT_CLI
    /* Every argument belongs to the tool: `nex run --max-output 5 file` is not an option of the runtime. */
    rt_args_list = (const char *const *)(argv + 1);
    rt_args_count = argc - 1;
    return;
#endif
    int i = 1;
    for (; i < argc; i++) {
        const char *a = argv[i];
        if (strcmp(a, "--") == 0) { i++; break; }
        if ((strcmp(a, "--max-text") == 0 || strcmp(a, "--max-output") == 0 || strcmp(a, "--max-input") == 0) && i + 1 < argc) {
            int64_t value = (int64_t)atoll(argv[i + 1]);
            if (value <= 0) {
                fprintf(stderr, "error: %s must be greater than zero\n", a);
                exit(2);
            }
            if (strcmp(a, "--max-text") == 0) rt_max_text = value;
            else if (strcmp(a, "--max-output") == 0) rt_max_output = value;
            else rt_max_input = value;
            i++;
            continue;
        }
        const char *kind = strcmp(a, "--allow-read") == 0 ? "read" : strcmp(a, "--allow-write") == 0 ? "write"
                         : strcmp(a, "--allow-network") == 0 ? "network" : strcmp(a, "--allow-process") == 0 ? "process" : 0;
        if (kind && i + 1 < argc) {
            if (rt_granted < RT_MAX_SCOPES) {
                rt_granted_kind[rt_granted] = kind;
                rt_granted_path[rt_granted] = argv[i + 1];
                rt_granted++;
            }
            i++;
        } else {
            break;
        }
    }
    rt_args_list = (const char *const *)(argv + i);
    rt_args_count = argc - i;
}

/* The program: the path it was given and the files it is made of, for the lines a diagnostic quotes. */
static void rt_setup(const char *entry, int count, const char *const *paths, const char *const *const *lines, const int *counts) {
    rt_entry = entry;
    rt_nfiles = count;
    rt_file_path = paths;
    rt_file_lines = lines;
    rt_file_count = counts;
    if (count > 0) {
        rt_path = paths[0];
        rt_src = lines[0];
        rt_src_lines = counts[0];
    }
}
