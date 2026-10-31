/* The runtime of the programs that selfhost/cgen.nex compiles (decision 0026).
 *
 * It is embedded, as it is, at the top of every generated C file. It does what the interpreter does that is not the program:
 * Int arithmetic with its checks, Text as a sequence of code points, the stack of calls and loops that explains an error, and
 * the text of a diagnostic exactly as `nex` writes it (diagnostics.py, `render`). C11 and the overflow builtins of GCC and
 * Clang are all it needs.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    const char *p;
    int64_t bytes;
    int64_t len; /* code points: what Text.length counts */
} rt_text;

static const char *rt_path = "";
static const char **rt_src = 0;
static int rt_src_lines = 0;

static void *rt_alloc(size_t n) {
    void *p = malloc(n ? n : 1);
    if (!p) {
        fputs("error: out of memory\n", stderr);
        exit(3);
    }
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
    char *p = (char *)rt_alloc((size_t)(a.bytes + b.bytes + 1));
    memcpy(p, a.p, (size_t)a.bytes);
    memcpy(p + a.bytes, b.p, (size_t)b.bytes);
    p[a.bytes + b.bytes] = 0;
    t.p = p;
    t.bytes = a.bytes + b.bytes;
    t.len = a.len + b.len;
    return t;
}

static int rt_text_compare(rt_text a, rt_text b) {
    int64_t n = a.bytes < b.bytes ? a.bytes : b.bytes;
    int c = memcmp(a.p, b.p, (size_t)n);
    if (c != 0) return c < 0 ? -1 : 1;
    return a.bytes < b.bytes ? -1 : (a.bytes > b.bytes ? 1 : 0);
}

static rt_text rt_int_text(int64_t n) {
    char buffer[32];
    int len = snprintf(buffer, sizeof buffer, "%lld", (long long)n);
    char *p = (char *)rt_alloc((size_t)len + 1);
    memcpy(p, buffer, (size_t)len + 1);
    rt_text t = {p, len, len};
    return t;
}

static rt_text rt_bool_text(bool b) {
    return b ? rt_lit("true") : rt_lit("false");
}

/* The text of a value as a diagnostic shows it: a Text is quoted and escaped (parser.quote). */
static rt_text rt_quote(rt_text s) {
    char *p = (char *)rt_alloc((size_t)(s.bytes * 2 + 3));
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

/* Output */

static void rt_print(rt_text t) {
    fwrite(t.p, 1, (size_t)t.bytes, stdout);
    fputc('\n', stdout);
}

/* The stack of calls and loops, which is what an error explains itself with. */

enum { RT_CALL, RT_COND, RT_MEASURE, RT_BODY };

typedef struct {
    int kind;
    const char *name;
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
    char *p = (char *)rt_alloc((size_t)n + 1);
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
        b->cap = (b->n + n + 1) * 2;
        b->p = (char *)realloc(b->p, b->cap);
        if (!b->p) exit(3);
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
    rt_render(category, "error", code, title, label, hint, &notes, line, column, end_line, end_column);
    fputc('\n', stderr);
    bool contract = strcmp(category, "contract") == 0;
    fprintf(stderr, "error: %s: the program stopped because %s\n", rt_path,
            contract ? "a contract was broken" : "of a runtime error");
    exit(contract ? 5 : 3);
}

#define RT_SPAN int64_t l, int64_t c, int64_t el, int64_t ec

static void rt_runtime(const char *code, const char *title, const char *label, const char *hint, RT_SPAN) {
    rt_notes own = {{0}, 0};
    rt_fail("runtime", code, title, label, hint, &own, 0, l, c, el, ec);
}

static void rt_overflow(RT_SPAN) {
    rt_runtime("E3002", "Integer overflow", "The result of this operation does not fit in an Int",
               "Int holds whole numbers from -9223372036854775808 to 9223372036854775807.", l, c, el, ec);
}

/* Int arithmetic: every result is checked, and each operator names the span an error points at. */

static int64_t rt_add(int64_t a, int64_t b, RT_SPAN) {
    int64_t r;
    if (__builtin_add_overflow(a, b, &r)) rt_overflow(l, c, el, ec);
    return r;
}

static int64_t rt_sub(int64_t a, int64_t b, RT_SPAN) {
    int64_t r;
    if (__builtin_sub_overflow(a, b, &r)) rt_overflow(l, c, el, ec);
    return r;
}

static int64_t rt_mul(int64_t a, int64_t b, RT_SPAN) {
    int64_t r;
    if (__builtin_mul_overflow(a, b, &r)) rt_overflow(l, c, el, ec);
    return r;
}

/* The first span is the whole operation, the second the right-hand side. */
static int64_t rt_div(int64_t a, int64_t b, RT_SPAN, int64_t rl, int64_t rc, int64_t rel, int64_t rec) {
    if (b == 0) {
        rt_runtime("E3001", "Division by zero", "The right-hand side of this division is zero", "", rl, rc, rel, rec);
    }
    if (a == INT64_MIN && b == -1) rt_overflow(l, c, el, ec);
    return a / b;
}

static int64_t rt_neg(int64_t a, RT_SPAN) {
    if (a == INT64_MIN) rt_overflow(l, c, el, ec);
    return -a;
}

/* Entering and leaving a function. The call that would be the 1,001st nested stops the program. */

static int rt_enter(const char *name, int64_t line, int64_t column, int64_t end_line, int64_t end_column) {
    if (rt_calls >= RT_MAX_CALLS) {
        rt_notes own = {{0}, 0};
        rt_fail("runtime", "E3004", "Too many nested calls", "The program nested more than 1000 calls",
                "A recursive function probably never reaches the case where it stops calling itself.", &own, 0, line,
                column, end_line, end_column);
    }
    int saved = rt_top;
    rt_frames[rt_top].kind = RT_CALL;
    rt_frames[rt_top].name = name;
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
    rt_frames[rt_top].line = line;
    rt_frames[rt_top].column = turn;
    rt_top++;
}

static void rt_pop(void) {
    rt_top--;
}

/* The program: the path it was compiled from and its source, for the lines a diagnostic quotes. */
static void rt_init(const char *path, const char **lines, int count) {
    rt_path = path;
    rt_src = lines;
    rt_src_lines = count;
}
