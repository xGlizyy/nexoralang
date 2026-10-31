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

typedef struct { int64_t n; rv *items; } rt_list;
typedef struct { const char *name; int n; const char *const *names; rv *f; } rt_record;
/* `owner` is the enum a variant belongs to, or "" for the variants of Option and Result. */
typedef struct { const char *owner; const char *kind; int n; rv *a; } rt_variant;

static rv rt_unit(void) { rv v; v.tag = RT_UNIT; v.u.i = 0; return v; }
static rv rt_int(int64_t n) { rv v; v.tag = RT_INT; v.u.i = n; return v; }
static rv rt_float(double x) { rv v; v.tag = RT_FLOAT; v.u.f = x; return v; }
static rv rt_bool(bool b) { rv v; v.tag = RT_BOOL; v.u.b = b; return v; }
static rv rt_txt(rt_text t) { rv v; v.tag = RT_TEXT; v.u.t = t; return v; }
static rv rt_str(const char *s) { return rt_txt(rt_lit(s)); }
static bool rt_truth(rv v) { return v.u.b; }

static rv *rt_copy_values(const rv *items, int64_t n) {
    rv *copy = (rv *)rt_alloc((size_t)(n > 0 ? n : 1) * sizeof(rv));
    for (int64_t i = 0; i < n; i++) copy[i] = items[i];
    return copy;
}

static rv rt_list_from(const rv *items, int64_t n) {
    rt_list *l = (rt_list *)rt_alloc(sizeof(rt_list));
    l->n = n;
    l->items = rt_copy_values(items, n);
    rv v;
    v.tag = RT_LIST;
    v.u.o = l;
    return v;
}

static rv rt_record_new(const char *name, const char *const *names, int n, const rv *fields) {
    rt_record *r = (rt_record *)rt_alloc(sizeof(rt_record));
    r->name = name;
    r->n = n;
    r->names = names;
    r->f = rt_copy_values(fields, n);
    rv v;
    v.tag = RT_RECORD;
    v.u.o = r;
    return v;
}

static rv rt_variant_new(const char *owner, const char *kind, int n, const rv *args) {
    rt_variant *x = (rt_variant *)rt_alloc(sizeof(rt_variant));
    x->owner = owner;
    x->kind = kind;
    x->n = n;
    x->a = rt_copy_values(args, n);
    rv v;
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
    char *copy = (char *)rt_alloc((size_t)n + 1);
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

static void rt_print(rv v) {
    rt_text t = rt_show(v, false);
    fwrite(t.p, 1, (size_t)t.bytes, stdout);
    fputc('\n', stdout);
}

/* Equality and order, as the interpreter has them. */

static bool rt_eq(rv a, rv b) {
    if (a.tag != b.tag) return false;
    switch (a.tag) {
    case RT_UNIT: return true;
    case RT_INT: return a.u.i == b.u.i;
    case RT_FLOAT: return a.u.f == b.u.f;
    case RT_BOOL: return a.u.b == b.u.b;
    case RT_TEXT: return rt_text_compare(a.u.t, b.u.t) == 0;
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

static rv rt_add(rv a, rv b, RT_SPAN) {
    if (a.tag == RT_INT) {
        int64_t r;
        if (__builtin_add_overflow(a.u.i, b.u.i, &r)) rt_overflow(l, c, el, ec);
        return rt_int(r);
    }
    if (a.tag == RT_FLOAT) return rt_float_checked(a.u.f + b.u.f, l, c, el, ec);
    return rt_txt(rt_concat(a.u.t, b.u.t));
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
    return v.tag == RT_VARIANT && strcmp(rt_as_variant(v)->kind, kind) == 0;
}

static rv rt_arg(rv v, int i) { return rt_as_variant(v)->a[i]; }

static rv rt_field(rv v, const char *name) {
    rt_record *r = rt_as_record(v);
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

static int64_t rt_byte_of_point(rt_text t, int64_t point) {
    int64_t byte = 0, seen = 0;
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
    char *p = (char *)rt_alloc((size_t)(to - from) + 1);
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
    char *copy = (char *)rt_alloc((size_t)t.bytes + 1);
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
    rt_list *x = rt_as_list(list);
    rv *items = (rv *)rt_alloc((size_t)(x->n + 1) * sizeof(rv));
    for (int64_t i = 0; i < x->n; i++) items[i] = x->items[i];
    items[x->n] = item;
    rv out = rt_list_from(items, x->n + 1);
    return out;
}

static rv rt_list_concat(rv a, rv b) {
    rt_list *x = rt_as_list(a), *y = rt_as_list(b);
    rv *items = (rv *)rt_alloc((size_t)(x->n + y->n + 1) * sizeof(rv));
    for (int64_t i = 0; i < x->n; i++) items[i] = x->items[i];
    for (int64_t i = 0; i < y->n; i++) items[x->n + i] = y->items[i];
    return rt_list_from(items, x->n + y->n);
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
