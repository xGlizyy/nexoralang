# 0011 — Operations on texts: functions associated with a type that declare their requirements

- **Status:** accepted. **Since 0.12 the requirements of the functions of a type are called
  `needs`** ([decision 0019](0019-identidad-propia-del-lenguaje.md)), in their diagnostics and in
  `nexora.symbols/2`; `nexora.capabilities/1` keeps `requires`, the word it was published with. What
  they require and when they are checked stand. Its programs are written in the syntax of their
  time, before 0.12: since 0.12 the language writes them as
  [decision 0019](0019-identidad-propia-del-lenguaje.md) describes, and `nex migrate` rewrites them.
- **Version:** 0.6.0
- **Related to:** [decision 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (no
  implicit conversions), [0003](0003-funciones-retorno-e-if.md) (a single namespace),
  [0004](0004-contratos-en-ejecucion.md) (`requires` checked at run time),
  [0005](0005-diagnosticos-y-esquemas-json.md) (versioned JSON schemas),
  [0006](0006-requisitos-verificables.md) (the main line),
  [0007](0007-contratos-estables-y-tipos-refinados.md) (refined types) and
  [0010](0010-var-y-while.md) (loop notes). **It modifies none.**

## Context

It is the first point of "Planned" in the [roadmap](../roadmap.md): "Operations on texts:
length, order comparison, conversion from text to number". Today a `Text` can only be joined with
`+`, compared with `==` and `!=`, and obtained with `to_text`.

| Need | Today | Problem |
|------|-------|---------|
| Knowing whether a text is empty or too long | Only by comparing with `""` | A refined type cannot say that a text has at most 20 characters |
| Sorting or comparing two names | `<` on `Text` is `E2011` | — |
| Reading a number written in a text | Impossible | When there is data input (point 4 of "Planned") everything will arrive as text |
| Keeping part of a text | Impossible | — |

### Two problems that have to be solved

**Operations that do not always have an answer.** The slice of `"abc"` between positions 2 and 9
does not exist, and `"12a"` is not a number. The usual languages choose between:

| Choice | Example | Problem |
|--------|---------|---------|
| Making up an answer | `"abc"[2:9]` gives `"c"` in Python; `parseInt("12a")` gives `12` in JavaScript | The error goes unnoticed and appears far from its cause |
| Throwing an exception | `int("12a")` in Python | The condition that has to be met is written nowhere in the program |
| Returning an optional value | `"12a".parse::<i32>()` in Rust | It requires `Option` or `Result`, which NEXORA does not have yet (point 3 of "Planned") |

NEXORA already has a way of saying "this function only makes sense if…": `requires`. What did not
exist is **the functions of the language itself** using it.

**Names.** NEXORA has a single namespace without shadowing (decision 0003, point 4): a
variable or a parameter cannot be named like a function, not even a built-in one (`E2006`). With
flat names such as `length`, `slice` or `contains`, which are very common variable names, every
new function would forbid a name, and every version that added functions could invalidate programs
that are correct today. Besides, NEXORA has no overloading: `length` could not serve both for
texts and for lists (point 2 of "Planned").

## Decision

### 1. What a `Text` is

- **A `Text` is a sequence of Unicode scalar values** (code points from U+0000 to U+10FFFF,
  without the surrogates U+D800–U+DFFF). In this document, "character" always means that.
- **No `Text` can contain a lone surrogate.** A program is read as strict UTF-8
  (`E0002` if it is not), the only escapes are `\n`, `\t`, `\"`, `\\` and `\{`, and no operation
  of this decision can create one: `Text.slice` cuts between characters, never inside one.
- **Nothing is ever normalized.** NEXORA applies no NFC, NFD or any other normalization form,
  neither when reading the program, nor when comparing, nor when searching. A text is exactly the sequence of
  characters written or computed.
- Positions start at 0. A slice is given by its start, included, and its end, excluded.
- Neither bytes nor UTF-16 units are used: no result depends on how the implementation stores the
  text.

### 2. Comparing texts

| Operator | Between two `Text` | Today |
|----------|--------------------|-------|
| `==`, `!=` | Equality character by character (without normalizing) | It already exists; it does not change |
| `<`, `<=`, `>`, `>=` | **New**: lexicographic order by code point | `E2011` |

**The exact order.** To compare `a` and `b` they are traversed together from position 0:

1. At the first position where they differ, the text whose character has the lower code point
   comes first.
2. If they do not differ in any position of the shorter one, the shorter one comes first. The empty text comes before
   any other.
3. If they have the same length and do not differ, they are equal.

| Expression | Value | Why |
|------------|-------|-----|
| `"ab" < "abc"` | `true` | `"ab"` is the beginning of `"abc"` |
| `"" < "a"` | `true` | The empty one comes before any other |
| `"Z" < "a"` | `true` | `Z` is U+005A and `a` is U+0061 |
| `"z" < "é"` | `true` | `é` (U+00E9) is after all the ASCII letters |
| `"10" < "9"` | `true` | Characters are compared, not numbers: `1` comes before `9` |
| `"é" == "é"` written one as U+00E9 and the other as `e` + U+0301 | `false` | Nothing is normalized |

- **It does not depend on the language or on the system configuration**: the same program gives the same
  result on any machine. It is not the alphabetical order of any language.
- A `Text` still cannot be compared with another type: `"1" < 2` is `E2011`, with the suggestion to
  convert one of the two sides.
- A refined type with base `Text` is compared as its base, as already happens with `==`.

### 3. Functions associated with a type: `Type.function(…)`

The new functions belong to a built-in type and are called with the name of the type in front:

```text
let size = Text.length(name)
let initials = Text.slice(name, 0, 2)
if Int.can_parse(input) {
    let n = Int.parse(input)
}
```

#### 3.1 The form

```text
qualified_call = TypeName "." name "(" [ arguments ] ")"
```

- **In front of the dot goes the name of a built-in type** that has functions: today `Text`, `Int` and
  `Float`. `Bool` has none yet.
- **After it goes the name of one of its functions**, and the call always carries parentheses: a function
  is not a value (decision 0003, point 5).
- **A single way of writing it**: the dot is attached to the name of the type and to that of the function, and there is
  a single dot. `Text . length(t)` and `Text.length.x(t)` are syntax errors. Between the name of the
  function and the `(` there may be spaces, as in any call (`f (1)` is already valid). How the
  dot is read, precisely: section 3.4.
- The full name of the function is `Text.length`. That is how it appears in diagnostics, in
  contracts and in tools.

#### 3.2 The functions

| Function | What it does | Requirements (`requires`) |
|----------|--------------|---------------------------|
| `Text.length(text: Text) -> Int` | Number of characters | None |
| `Text.slice(text: Text, start: Int, end: Int) -> Text` | The characters from `start` (included) to `end` (excluded) | Three (section 5.2) |
| `Text.contains(text: Text, part: Text) -> Bool` | Whether `part` appears in `text` | None |
| `Text.starts_with(text: Text, part: Text) -> Bool` | Whether `text` starts with `part` | None |
| `Text.ends_with(text: Text, part: Text) -> Bool` | Whether `text` ends with `part` | None |
| `Int.can_parse(text: Text) -> Bool` | Whether `text` is an integer written according to section 6 | None |
| `Int.parse(text: Text) -> Int` | The integer written in `text` | `Int.can_parse(text)` |
| `Float.can_parse(text: Text) -> Bool` | Whether `text` is a decimal written according to section 6 | None |
| `Float.parse(text: Text) -> Float` | The decimal written in `text` | `Float.can_parse(text)` |

- `Int.parse` and `Float.parse` belong to the type they **produce**, not to the one they receive: they read as "an
  `Int` from a text".
- The arguments are checked without running like those of any function (`E2009`, `E2011`). An
  argument of a refined type with base `Text` or `Int` is accepted where its base is expected.
- There is no `trim`, `upper`, `split`, `replace` or search for positions: `split` needs lists and the
  rest will be decided when there are programs that need it.

#### 3.3 What does not change

- **No name is reserved.** `let length = Text.length(name)` is valid: unqualified `length`
  still means a single thing, the variable, and `Text.length` is another one. A name of the program cannot
  contain a dot, so a qualified name never matches one of the program.
- **`Int`, `Float`, `Bool` and `Text` can still be used as variable and parameter names**,
  as today. NEXORA already tells types and values apart by the position in which they appear: this program is
  valid in 0.5.1 and it still is:

  ```text
  fn twice(Text: Int) -> Int {
      return Text * 2
  }
  ```

  The position in front of the dot is a type position, like that of an annotation
  (`let label: Text = "a"`). Since a value can never be followed by a dot, `Text.length(s)`
  means the function of the type even if there is a variable called `Text` (section 9 and test 17).
- **The namespace rule (decision 0003) does not change**: qualified names do not enter the
  namespace of functions, parameters and variables.
- **`print`, `to_text`, `to_float` and `to_int` stay as they are**, unqualified. The two
  forms will coexist. If qualified equivalents are added, it will be in another decision.

#### 3.4 How the dot is read

**Lexer.**

1. Texts and comments are read as today: a `.` inside them is not a token.
2. When reading a number, a `.` **followed by a digit** is part of the decimal number, as today
   (`1.5`).
3. **Any other `.` is the new token `DOT`.** Today that same `.` is the lexical error `E1001`.
   Examples: the one of `Text.length`, the one of `1.length` (the `1` is an integer and the `.` a `DOT`), the one of `.5` and
   the second one of `1.5.2`.
4. As today, line breaks inside parentheses produce no token; outside them, they end the
   statement.

**Parser.** The `DOT` is only valid in one place: in an expression, between two names,
as part of the call `name DOT name "(" … ")"`.

1. The parser builds that call **whenever it finds that form**, without knowing yet whether the
   first name is a type, a variable or a module: `Text.length(s)`, `name.length()` and
   `geometry.area(c)` are parsed the same way. What they mean is decided by the checker.
2. Both names have to touch the dot: the column where the first one ends is that of the dot, and the
   one after the dot is that of the second, on the same line. It is checked with the positions of
   the tokens, because inside parentheses a line break leaves no token.
3. **Distribution of errors.** The parser gives `E1101` when the **form** is wrong; the
   checker gives `E2008` when the form is correct but the **name** does not exist or is not a type. The
   complete table is in section 9.

**Valid programs of 0.5.1.** No valid program contains a `DOT`, because in 0.5.1 a `.`
outside a number, a text or a comment was always `E1001`. Their sequence of tokens, their tree, their
checking and their execution do not change (section 10). Only the diagnostics of programs that were already
invalid change.

### 4. The built-in functions declare their requirements, in NEXORA

This is what makes these functions NEXORA's and not a copy of those of another language.
**Every function that may have no answer declares when it has one, with a `requires` written in
NEXORA and with its explanation**, exactly like a function of the program. These are them, complete:

```text
fn Text.length(text: Text) -> Int
    ensures result >= 0, "A text never has a negative number of characters"

fn Text.slice(text: Text, start: Int, end: Int) -> Text
    requires start >= 0, "A slice cannot start before the first character"
    requires start <= end, "A slice cannot end before it starts"
    requires end <= Text.length(text), "A slice cannot end after the last character"
    ensures Text.length(result) == end - start, "The slice has exactly end - start characters"

fn Int.parse(text: Text) -> Int
    requires Int.can_parse(text), "Only a whole number within the range of Int can be read as an Int"

fn Float.parse(text: Text) -> Float
    requires Float.can_parse(text), "Only a decimal number that fits in a Float can be read as a Float"
```

- The explanations name the range on purpose: `"99999999999999999999"` is written as an
  integer and still cannot be read, because it does not fit in an `Int`. An explanation that only
  talked about the form would be false for that case.
- **The notation `fn Text.length(text: Text) -> Int` of this block is the way signatures
  are shown**, the same one that diagnostics and `nex symbols` use. It is not a declaration a program
  can write: a program cannot declare functions of a type (section 9).
- **The conditions** (what goes after `requires` and `ensures`) are written in NEXORA and parsed
  as expressions with the real parser when the interpreter is loaded.
  A test checks that all of them have type `Bool`, that they only use their parameters, `result` (in
  `ensures`) and built-in functions without `requires`, and that **none can fail when evaluated**: they do not
  divide, do not overflow and only call `Text.length`, `Int.can_parse` and `Float.can_parse`, which have an
  answer for any text.
- The caller can move the requirement: `requires Int.can_parse(code)` in a function of the program
  uses the same condition, and a refined type can say
  `type Code = Text where Text.length(value) == 3, "A code has exactly three characters"`.
- The earlier functions (`print`, `to_text`, `to_float`, `to_int`) have no `requires`, and `to_int`
  still gives `E3005` outside the range of `Int`.

### 5. Exact behaviour of each function

#### 5.1 `Text.length`, `Text.contains`, `Text.starts_with`, `Text.ends_with`

They count and compare characters (section 1), without normalizing and distinguishing uppercase from lowercase.
They have an answer for any text, also the empty one.

| Call | Value | Rule |
|------|-------|------|
| `Text.length("")` | `0` | |
| `Text.length("año")` | `3` | `ñ` is one character |
| `Text.length` of an `e` followed by the combining accent U+0301 | `2` | Two characters, even though they look like one |
| `Text.length` of the family emoji 👨‍👩‍👧‍👦 | `7` | Four people joined by three U+200D |
| `Text.contains("hello", "ell")` | `true` | |
| `Text.contains("hello", "")` | `true` | **The empty text appears in any text**, at any position |
| `Text.contains("", "")` | `true` | |
| `Text.contains("", "a")` | `false` | |
| `Text.contains("Hello", "hello")` | `false` | Case-sensitive |
| `Text.starts_with("hello", "he")` | `true` | |
| `Text.starts_with("hello", "")` | `true` | Every text starts with the empty one |
| `Text.starts_with("he", "hello")` | `false` | `part` longer than `text` |
| `Text.ends_with("hello", "lo")` | `true` | |
| `Text.ends_with("hello", "")` | `true` | Every text ends with the empty one |
| `Text.ends_with("", "a")` | `false` | |

Equivalences that always hold (with `n = Text.length(t)` and `m = Text.length(p)`):
`Text.starts_with(t, p) == (m <= n and Text.slice(t, 0, m) == p)` and
`Text.ends_with(t, p) == (m <= n and Text.slice(t, n - m, n) == p)`.

#### 5.2 `Text.slice`

`Text.slice(text, start, end)` returns the characters at positions `start`, `start + 1`, …,
`end - 1`. Its three `requires` define when it has an answer:
`0 <= start <= end <= Text.length(text)`. **There are no negative indices that count from the end, and no
silent truncation**: outside those limits, the call stops with `E4001`.

| Call | Result | Rule |
|------|--------|------|
| `Text.slice("hello", 1, 3)` | `"el"` | Start included, end excluded |
| `Text.slice("hello", 0, 5)` | `"hello"` | The whole text |
| `Text.slice("hello", 2, 2)` | `""` | `start == end`: empty slice |
| `Text.slice("hello", 5, 5)` | `""` | An empty slice at the end is valid |
| `Text.slice("", 0, 0)` | `""` | The only slice of the empty text |
| `Text.slice("año", 1, 2)` | `"ñ"` | Characters are counted, not bytes |
| `Text.slice("hello", -1, 2)` | `E4001` | `requires start >= 0` |
| `Text.slice("hello", 3, 1)` | `E4001` | Inverted range: `requires start <= end` |
| `Text.slice("hello", 0, 6)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("hello", 6, 6)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("", 0, 1)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("hello", -3, -1)` | `E4001` | `requires start >= 0`: it does not count from the end |
| `Text.slice("abc", -1, 9)` | `E4001` for `start >= 0` | If several fail, the first one in the written order is reported |

`Text.length(Text.slice(t, a, b)) == b - a` and
`Text.slice(t, 0, k) + Text.slice(t, k, Text.length(t)) == t` always hold for every `k` between `0` and
`Text.length(t)`.

### 6. How a number is written in a text

#### 6.1 The grammar

A single form, not depending on the language or on the system configuration. All the characters are
ASCII; `digit` is only `0`–`9`.

```text
integer   = [ "-" ] digit { digit }
decimal   = [ "-" ] digit { digit } ( fraction [ exponent ] | exponent )
fraction  = "." digit { digit }
exponent  = ( "e" | "E" ) [ "+" | "-" ] digit { digit }
```

- **`Int.can_parse(t)`** is true if and only if the whole of `t` matches the rule `integer` **and** its value
  is between -9223372036854775808 (−2⁶³) and 9223372036854775807 (2⁶³ − 1), both included: the range of
  `Int` (`values.py`, `INT_MIN` and `INT_MAX`; `language-spec.md`, section 4).
- **`Float.can_parse(t)`** is true if and only if the whole of `t` matches the rule `decimal` **and** its
  value, rounded to the nearest `Float`, is finite.
- **Nothing** outside the grammar is accepted: no spaces (nor tabs, line breaks or
  non-breaking spaces) at the beginning, at the end or in the middle, no `+` in front of the number, no `_`, no
  thousands separators, no other decimal comma, no digits that are not ASCII, no prefixes (`0x`, `0b`),
  no special values (`inf`, `Infinity`, `nan`, `NaN`).
- The length of the text limits nothing: as many digits and leading zeros as there are are accepted.
  Only the value counts.

#### 6.2 Cases

| Text | `Int.can_parse` | `Float.can_parse` | Notes |
|------|-----------------|-------------------|-------|
| `"0"`, `"42"`, `"-7"` | yes | no | |
| `"007"` | yes (7) | no | Leading zeros allowed |
| `"0000000000000000000000000042"` | yes (42) | no | Leading zeros do not count towards the range |
| `"-0"` | yes (0) | no | `Int` has no negative zero |
| `"9223372036854775807"` | yes | no | The largest `Int` |
| `"-9223372036854775808"` | yes | no | The smallest `Int`. As a literal it cannot be written (`E1004`); only by computing it, `-9223372036854775807 - 1` |
| `"9223372036854775808"` | **no** | no | One more than the largest `Int` |
| `"-9223372036854775809"` | **no** | no | One less than the smallest `Int` |
| `"99999999999999999999"` | **no** | no | Well written, but out of range |
| `"+5"` | no | no | No `+` in front |
| `" 5"`, `"5 "`, `"5\n"` | no | no | No spaces |
| `""`, `"-"` | no | no | No digits |
| `"1_000"`, `"1,000"` | no | no | No separators, even though the literals of the code accept `_` |
| `"٣"`, `"１"` | no | no | Only ASCII digits |
| `"0x10"` | no | no | |
| `"1.5"`, `"-0.25"`, `"0.0"` | no | yes | |
| `"-0.0"` | no | yes (`-0.0`) | It keeps the sign of zero |
| `"1e3"`, `"1e+16"`, `"2.5E-3"` | no | yes | Exponents, even though the literals of the code do not accept them |
| `"1"` | yes | **no** | An integer is not a decimal (section 6.3) |
| `".5"`, `"5."`, `"1e"`, `"1e+"` | no | no | Digits are missing |
| `"+1.5"`, `"1,5"`, `" 1.5"` | no | no | |
| `"inf"`, `"Infinity"`, `"nan"`, `"NaN"` | no | no | No special values |
| `"1e309"` | no | **no** | Rounded, it would be infinity: it does not fit in a `Float` |
| `"1e-400"` | no | yes (`0.0`) | Too small: it is rounded to zero, like any `Float` |
| `"-1e-400"` | no | yes (`-0.0`) | Rounding to zero keeps the sign |
| `"5e-324"` | no | yes | The smallest positive `Float` |
| `"2.4703282292062328e-324"` | no | yes (`5e-324`) | Above half of the smallest positive: it is rounded to it |
| `"2.4703282292062327e-324"` | no | yes (`0.0`) | Below that half: it is rounded to zero |
| `"1.7976931348623157e308"` | no | yes | The largest finite `Float` |
| `"1.7976931348623158e308"` | no | yes (the largest finite) | Larger than the maximum, but it rounds to it: the rounded value decides, not the written one |
| `"1.7976931348623159e308"` | no | **no** | It would round to infinity |

#### 6.3 Rules that follow

- **`Float.can_parse("1")` is false on purpose**: `Int` and `Float` do not mix (decision 0001). To
  read `"1"` as a `Float`, write `to_float(Int.parse("1"))`.
- **`Float.parse` gives the `Float` nearest to the written value** (rounding to nearest, ties to
  even, as in the IEEE 754 standard). `Float.parse("0.1")` is not exactly a tenth, just like the
  literal `0.1`.
- **`Int.parse` never gives `E3002` or `E3005`.** A text out of range makes `Int.can_parse` false, so
  the call stops before, with the `E4001` of its `requires` and the suggestion of section 7.2. It is
  different from `to_int`, which converts a `Float` and gives `E3005` out of range (unchanged).
- **`Float.parse` never returns an infinity or `NaN`**: they do not exist in NEXORA, and a text that would give
  one makes `Float.can_parse` false.
- **Guaranteed round trip.** For every `Int` `n`, `Int.parse(to_text(n)) == n`. For every `Float`
  `x`, `Float.parse(to_text(x)) == x`, also for `-0.0`. That is why exponents are accepted: it is how
  `to_text` writes very large or very small `Float` values (`1e+16`).
- **Asymmetry with literals, on purpose**: the source code accepts `1_000_000` and does not accept `1e3`;
  texts the other way round. Literals are for people writing a program; texts, for
  reading data and for the round trip of `to_text`.

#### 6.4 Huge texts, rounding and limits of `Float`

**Cost.** The four functions of this section have a cost proportional to the length of the text,
and use no more memory than a fixed amount besides the text itself:

| Function | How it is guaranteed |
|----------|----------------------|
| `Int.can_parse`, `Int.parse` | The text is traversed once to check the grammar; leading zeros are ignored; **if more than 19 digits remain, the value is out of range without converting anything**, and if 19 or fewer remain they are converted and compared with the limits. An integer of more than 19 digits is never built |
| `Float.can_parse`, `Float.parse` | The grammar is checked in one pass, and only then is it converted with a correctly rounding algorithm that accepts mantissas and exponents of any length: a huge exponent gives infinity (not accepted) or zero (accepted) |

- **Note for the implementation:** in Python, `int()` on a text of more than 4300 digits raises
  `ValueError`, and `int()` and `float()` accept spaces, `_`, `+`, `inf` and `nan`. That is why the grammar
  is checked first and the whole text of an `Int` is never converted. An input of millions of
  digits cannot produce an internal error.
- **Measured** with Python 3.12.10 on Windows 11, in this revision: texts of 10 million characters
  (10 million digits, of leading zeros, of mantissa or of exponent) are resolved in between
  17 and 58 ms, without noticeable additional memory. The tests do not check times (`limitations.md`:
  performance has not been measured as a guarantee); they check that the answer is correct and that there is no
  internal error.

**Rounding of `Float.parse`.**

- **Correct rounding to nearest, ties to even** (IEEE 754, *round half to even*): the
  result is the `Float` nearest to the exact written value, considering all its digits. The
  reference implementation uses the conversion of CPython, which is correct when
  `sys.float_repr_style` is `"short"` (checked: it is); a test requires it.
- **Finite maximum**: an exact value is accepted if and only if its rounding is finite. The threshold is the
  midpoint between the largest finite `Float` and 2¹⁰²⁴: below it, it rounds to the maximum; at the midpoint or
  above, to infinity, and `Float.can_parse` is false.
- **Underflow**: values smaller than half of the smallest positive `Float` (5e-324) are
  rounded to zero; those larger than that half, to 5e-324 or to a subnormal. At the exact midpoint, the
  tie to even gives zero. Zero keeps its sign: `"-1e-400"` gives `-0.0`.
- **No read fails because of rounding**: `Float.can_parse` is only false because of the grammar or because the
  rounding would be infinite.

### 7. When the requirements are checked and what happens if they fail

#### 7.1 Order of evaluation of a call to a built-in function

1. The arguments are evaluated, from left to right. An error when evaluating one stops the call with
   that error; the requirements are never checked.
2. The `requires` are checked, **in the order in which they are written** in section 4. The first one that
   turns out false stops the program with `E4001`; the following ones are not evaluated.
3. Only if all of them hold is the operation performed.

The `ensures` of the built-in functions **are not evaluated when running**: the
implementation meets them, and the tests verify it with many values. They are written to inform the
caller, and the tools mark them as not checked when running (section 7.4).

Inside `and` and `or`, a call that does not need to be evaluated is not evaluated, and neither are its requirements:
`Int.can_parse(t) and Int.parse(t) > 0` never calls `Int.parse` if the text is not an integer.

#### 7.2 The diagnostic

The same `E4001` (`Precondition violated`, category `contract`, exit code `5`) that a
function of the program gives, with the position of the call:

```text
contract error[E4001]: Precondition violated
 --> program.nex:4:11
  |
4 |     print(Text.slice(word, 2, 9))
  |           ^^^^^^^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'Text.slice'
  = note: The condition of the built-in function is false: requires end <= Text.length(text)
  = note: Reason: A slice cannot end after the last character
  = note: It was called with: text = "abc", start = 2, end = 9
  = note: In 'shorten', called at line 9, column 11.
```

| Field | Content |
|-------|---------|
| Position | The whole call, from the name of the type to the `)` (as in the `E4001` of a function of the program) |
| Label | `This call breaks a 'requires' condition of '<Type.function>'` |
| Notes, in order | `The condition of the built-in function is false: requires <condition>` · `Reason: <explanation>` · `It was called with: <parameter> = <value>, …` (texts in quotes) · the chain of calls · the loop notes of decision 0010 |
| Suggestion | Only in `Int.parse` and `Float.parse`, according to the following table. None in `Text.slice` |

**Suggestions of `Int.parse` and `Float.parse`.** They say what to do in each case, they do not repeat the condition.
When they talk about the range of `Int`, they use the same text that `E3002` and `E3005` already use:

| Function | Case | Suggestion |
|----------|------|------------|
| `Int.parse` | The text does not match the rule `integer` | `Check the text first with Int.can_parse(...), and call Int.parse only when it is true.` |
| `Int.parse` | It matches the rule, but it is out of range | `Int holds whole numbers from -9223372036854775808 to 9223372036854775807.` |
| `Float.parse` | The text matches the rule `integer` (for example `"1"`) | `This text is a whole number: read it with to_float(Int.parse(...)).` |
| `Float.parse` | It matches neither of the two rules | `Check the text first with Float.can_parse(...), and call Float.parse only when it is true.` |
| `Float.parse` | It matches the rule `decimal`, but rounded it would be infinity | `The number is too large for a Float.` |

The suggestion is chosen with the same grammar of section 6, without evaluating anything else: it cannot fail
or contradict the condition.

There are two differences from the `E4001` of a function of the program, and both are because the
function belongs to the language: the first note says `of the built-in function` instead of `at line N`,
because it has no line in the file; and `Int.parse` and `Float.parse` can carry a suggestion, because the
language knows what failed. A function of the program cannot declare suggestions, and this decision does not
change that.

#### 7.3 In each interface

| Interface | Behaviour |
|-----------|-----------|
| `nex run` | Code `5`, the diagnostic of section 7.2 |
| `nex run --format json` | `nexora.diagnostics/1` document with the `E4001`; `notes` and `hint` contain the same |
| `nex test` | The example stays as `error` with the `E4001` and the note of the example; the others are evaluated |
| `api.run_source` and the playground | Status `contract_violation` with the diagnostic |
| `Type(x)` when running | If the condition of a refined type calls a built-in function that breaks a requirement: `E4001`, with the note `While checking that a value is a valid <Type>…` that already exists |
| `nex check` on constants of refined types | The `E2017` that already exists ("cannot be checked against the condition"), with the cause in a note |
| Inside the `requires` or the `ensures` of a function of the program | Like any error when evaluating a contract: the `E4001` of the built-in function |

#### 7.4 In the tools (representation R1)

**`nex inspect` (`nexora.inspect/2`).** The `Call` node gains the `qualifier` field:

| Field | Unqualified call (`print(x)`, `double(2)`, `Percent(x)`) | Qualified call (`Text.length(s)`) |
|-------|---------------------------------------------------------|-----------------------------------|
| `callee` | `"print"` (as today) | `"Text.length"`: the full name |
| `callee_span` | The name (as today) | The whole `Text.length` |
| `arguments`, `span`, `type` | As today | As in any call |
| `qualifier` | **`null`** | `"Text"` |

- **`qualifier` is present in all calls**, with `null` when there is no qualifier. It is the
  rule all nodes already follow: every field always appears, with `null` if it has no value
  (`declared_type` in `Let`, `message` in `Contract`). A consumer can rely on the key.
- **It goes after `arguments` and before `type`.** The fields that already exist keep their relative
  order, as is already checked for the `examples` field that 0.4.0 added to `Function`
  (`tests/test_example_clauses.py`); test 20 does the same for `Call`.

**Why a new version is not needed.** These are three different things, and all three have been checked:

| Level | What is asked | Result |
|-------|---------------|--------|
| **Protocol** | Does the versioning policy allow it? | Yes. `json-protocol.md`, "Versions and compatibility": "A field is added to an object: the number does not change", and the consumer must "ignore the fields it does not know". `test_inspect.py` says the same: only removing or renaming requires a new version. Precedents: `examples` in `Function` (0.4.0) and the loop nodes (0.5.0) |
| **Schema** | Does the new output validate with the schema of 0.5.1? | Yes, checked in this revision with `jsonschema` and the current schema: the 9 programs of `examples/` with `"qualifier": null` added to every `Call`, and a program with a `Text.length` call written as R1 would write it. The schema does not use `additionalProperties` and `callee` is `{"type": "string"}`, without a pattern |
| **Interpretation** | Can a consumer of `nexora.inspect/2` misunderstand the new output? | No, checked with a consumer that resolves every `callee` against the functions of the program and the `builtins` list of `nex symbols`, in a program with a parameter called `length`. With the list of 0.5.1, `Text.length` stays "unknown", never attributed to the parameter `length`; with the new list, "built-in". Unlike `var` in 0010, where a new field would have made a `var` be read as a `let` and that is why a new node was created, here no name of the program can contain a dot |

**Observable changes in the JSON output**, even though the version does not change:

- **Every `Call` has one more key**, `qualifier`, also in the programs that do not use the new
  syntax. Whoever compares whole documents byte by byte will see the difference. In this repository:
  `EXPECTED_FIELDS` of `test_inspect.py` (the exact list of fields per node) and the recorded outputs
  in `ai-tooling.md`, which are updated.
- **Function names with a dot appear** in `callee` and in `builtins_called`, only in the programs
  that use the new syntax.
- **A consumer that has written its own list of built-in functions** will see names it does not
  know. No document promises a closed list: the current list is in the `builtins` field of
  `nex symbols` and in `get_capabilities()`, which gives it in `language.builtins`. The same would happen with
  any new built-in function, with any way of naming it. `nex context` does not expose that
  list: it only names, in `builtins_called`, the ones the program calls.
- **Existing consumers**: only in this repository (`tooling.py`, the MCP server, which forwards the
  document, the tests and the documents with recorded outputs). The web server, the website and the
  npm package do not read `nex inspect`. There are no published consumers.

**`nex symbols`.** Every built-in function of the `builtins` list is described with its full name and
gains the `contracts` field, empty if it has none. `get_capabilities()` publishes the same list in
`language.builtins`; `nex context` does not expose `builtins`:

```json
{
  "name": "Text.slice",
  "signature": "fn Text.slice(text: Text, start: Int, end: Int) -> Text",
  "params": [{"name": "text", "type": "Text"}, {"name": "start", "type": "Int"}, {"name": "end", "type": "Int"}],
  "return_type": "Text",
  "contracts": [
    {"clause": "requires", "condition": "start >= 0",
     "message": "A slice cannot start before the first character", "checked_at_run_time": true},
    {"clause": "ensures", "condition": "Text.length(result) == end - start",
     "message": "The slice has exactly end - start characters", "checked_at_run_time": false}
  ]
}
```

- The same field names as the contracts of the functions of the program, without `line`, and with
  `checked_at_run_time`: `true` in `requires`, `false` in `ensures`. That way an agent does not take as checked
  what is not checked.
- `builtins_called` of `nex context` contains the full names (`["Text.length", "print"]`), and
  `calls` and `called_by` do not change: they only contain functions of the program.
- `features` gains the value `text_operations` when the program compares texts by order or calls
  any of the nine functions.
- `nex context` as text shows, under the `built-ins:` line of each function, the `requires` of the
  built-in functions it calls, with their explanation.
- The variables and parameters of the program are described as always: a `length` variable is one more
  symbol, unrelated to `Text.length`.
- Everything is added fields or values: `nexora.symbols/1` and `nexora.context/1` keep their version.

### 8. What can go in front of the dot: types, modules and methods

The form `name.function(…)` has, in the design of NEXORA, three possible uses. This decision sets the
first one, reserves the second one and leaves the third one out, without closing it:

| Use | Example | What goes in front of the dot | Status |
|-----|---------|-------------------------------|--------|
| **Function of a type** | `Text.length(name)` | The name of a **built-in type**, which starts with an uppercase letter (types always start with an uppercase letter, `E2016`) | **This decision** |
| **Function of a module** | `geometry.area(circle)` | The name of a **module**, in lowercase | Future (point 5 of "Planned"). Today it is an error (section 9) |
| **Method of a value** | `name.length()` | A **value** (a variable or an expression) | **Outside the current design**. Today it is an error (section 9) |

- **Functions of a type.** They are resolved by the name of the type, in the type position. Today only
  built-in types have functions. When there are lists, `List.length(xs)` and `List.get(xs, i)` will use
  the same form without changing the syntax. Whether user types (records) can declare their
  own functions (`fn Point.distance(a: Point, b: Point) -> Float`) will be decided when they exist.
- **Functions of a module.** When there are modules, a lowercase name in front of the dot will be an
  imported module. Uppercase for types and lowercase for modules: the two things are not
  confused. This decision defines nothing about modules.
- **Methods of a value.** They are not part of the current design, and this decision **does not declare them
  impossible**. If a future decision adds them, it will have to solve how they are told apart from the
  functions of a module and of a type when the name in front of the dot could be both: for
  example, a variable called `Text` (allowed, section 3.3) in front of `.length()`. The rule of a
  single namespace already guarantees that a variable and a module cannot have the same name, which
  leaves that door open.

### 9. Diagnostics

No new code is created. `E1101` (`Unexpected token`, from the parser) is given when
the **form** is wrong; `E2008` (`Unknown function`, from the checker) when the form `name.name(…)`
is correct but the name in front is not a type with that function (section 3.4). Both keep
their title and their category.

**Correct form, wrong name: `E2008`**

| Situation | Example | Label | Suggestion or note |
|-----------|---------|-------|--------------------|
| Function that the type does not have | `Text.lenght(t)` | `'Text' has no function named 'lenght'` | `Did you mean 'Text.length'?`; note with the functions of `Text` |
| Built-in type without functions | `Bool.parse(t)` | `'Bool' has no function named 'parse'` | Note: `Bool has no functions yet.` |
| Refined type in front of the dot | `Percent.parse(t)` | `'Percent' has no functions of its own` | If its base type has functions: `A value of Percent can be passed to the functions of its base type, Int.` (with the refined type and its base in each case) |
| Type that does not exist | `Texto.length(t)` | `There is no type named 'Texto'` | `Did you mean 'Text'?` |
| Lowercase name that is nothing | `geometry.area(c)` | `There is no type named 'geometry'` | Note: `Before the '.' goes the name of a type, such as Text. Modules are not part of NEXORA yet.` |
| A value in front of the dot | `name.length()` | `'name' is a variable: values have no functions of their own` | `Call the function of its type: Text.length(name)`, if its type has that function |
| A function in front of the dot | `print.x(1)` | `'print' is a function, not a type` | |
| The unqualified function | `length(t)` | `There is no function named 'length'` (today's label) | `Did you mean 'Text.length'?` |

**Wrong form: `E1101`**

| Situation | Example | Label | Suggestion or note |
|-----------|---------|-------|--------------------|
| Without parentheses | `let f = Text.length` | `Expected '(' to call 'Text.length'` | `A function is not a value: call it, as in Text.length(...).` |
| Without a name after the dot | `Text.(t)`; `Text.` at the end of the file or followed by a line break outside parentheses | `Expected the name of a function after 'Text.'` | |
| Spaces around the dot | `Text . length(t)`; also `Text` and `.length(t)` separated by a line break inside parentheses | `Write 'Text.length' without spaces around the '.'` | |
| More than one dot | `Text.length.x(t)` | `Expected '(' after 'Text.length', found '.'` | Note: `A qualified name has one '.': Type.function` |
| Declaring a function of a type | `fn Text.length(t: Text) -> Int { … }` | Today's one when the `(` is missing after the name of the function, pointing at the `.` | `Only the language defines functions of a type, such as Text.length. Choose a name without '.'.` |
| A dot anywhere else | `.length(t)` at the beginning of an expression; `1.length`; `.5`; `1.5.2`; `Text.length(s).x`; `Text` at the end of a line outside parentheses and `.length(t)` on the next one | The one the parser already gives for an unexpected symbol at that point, with the `.` described as `'.'`: for example `Expected a value or an expression, found '.'` at the beginning of an expression | |

**Other cases**

| Example | Result |
|---------|--------|
| `Text.length (s)` | Valid: between the name of the function and the `(` there may be spaces, as in any call |
| `Text.length(t)` as a statement | `E2010` (unused value), like any call that returns a value |

### 10. Today's valid programs do not change

- **Today a `.` can only appear in a valid program inside a decimal number, a text or
  a comment.** Anywhere else it is the lexical error `E1001`. The lexer reads
  numbers, texts and comments before considering a loose `.`, and that does not change. Therefore,
  **the sequence of tokens of every program valid in 0.5.1 is identical**, and with it its tree, its
  checking and its execution.
- The only observable difference in a valid program is the field `"qualifier": null` in the
  `Call` nodes of `nex inspect` (section 7.4).
- The programs that today have a loose `.` are still invalid; only the diagnostic changes (for
  example, `x.y` goes from `E1001` to `E1101` or `E2008`).
- No name is reserved: no valid program stops being so.

## Reasons

- **Coherence with the main line** ([0006](0006-requisitos-verificables.md)): if requirements
  are a verifiable part of the program, they must also be part of the language. A built-in
  function is not an exception to the rule.
- **A single mechanism**: the same word, the same diagnostic and the same tool format
  for the conditions of the user and those of the language.
- **No new function breaks a program**: a qualified name cannot match one of the
  program, neither today nor when lists or `Option` arrive.
- **Functions are grouped by type**: whoever writes `Text.` knows where to look, and a tool
  can list the functions of a type.
- **Without waiting for `Option`**: `Int.can_parse` + `Int.parse` is safe today, and when `Option` exists
  a variant that returns it can be added without changing these.
- **Determinism**: neither the order, nor the form of numbers, nor the length depend on the system.

## What it does not guarantee

- **The length is not what a person sees as "a letter".** An `e` with the combining accent has
  length 2, and a family emoji, 7. Two texts that look the same can be different for `==`.
- **The order is not alphabetical** in any language: it is that of the code points. It is useful to sort
  reproducibly, not to show sorted lists to a person (`"Zoe" < "ana"`).
- **The requirements are checked when running**, like those of the functions of the program. `nex check` does not
  warn that `Text.slice("abc", 0, 5)` is going to fail, even if its arguments are constants.
- **`Float.parse` rounds**: the `Float` it returns may not be exactly the written number.
- **A variable called `Text` is valid** and may confuse whoever reads `Text.length(s)` near
  it. The analyzer is not confused (section 3.3); for people, a future warning (point 6 of
  "Planned") could point it out.

## Out of scope

- Text interpolation, `trim`, case conversion, `split`, `replace`, search for positions.
- Going through a text with `for` (it will come with lists).
- Unicode normalization and language-dependent comparison.
- Reading numbers in other bases, with separators or with spaces.
- Checking the requirements of the built-in functions without running.
- Qualified functions for user types, modules and methods of values (section 8).
- Qualified versions of `print`, `to_text`, `to_float` and `to_int`.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| **A.** Reserved flat names (`length`, `slice`, `parse_int`) | It forbids very common variable names and does not let lists have their own `length` without overloading |
| **B.** Letting a variable shadow the built-in function | It contradicts decision 0003: the same name would mean two things depending on where it is read |
| **D.** Methods on values (`t.length()`) | It requires member access, chaining and a way of naming the value in contracts; it deserves its own decision (section 8) |
| **E.** Unusual flat names (`text_length`) | Every version that adds functions would reserve new names and could invalidate programs; the namespace would grow with every type |
| Forbidding `Int`, `Float`, `Bool` and `Text` as variable names | It is not necessary (section 3.3) and it would be an incompatible change without a technical reason |
| `callee: "length"` with `qualifier: "Text"` in `nex inspect` | A consumer that ignored `qualifier` would believe that something called `length` is called, which can be a variable of the program. It would require `nexora.inspect/3` |
| Silent truncation (`slice` as in Python) | It hides the error; it contradicts the rule of not making up answers |
| Negative indices that count from the end | A negative index computed by mistake would turn into a valid result |
| A new error code for each built-in function | More codes to learn for the same thing: a broken precondition |
| `Int.parse` returning `0` if the text is not a number | A valid value that does not mean what it seems |
| Accepting spaces or `+` in numbers | Several ways of writing the same thing; removing spaces will be an explicit operation |
| Counting bytes or UTF-16 units | The length would depend on the representation |
| Normalizing texts | It would change the data without the program asking for it, and the chosen form would be arbitrary |
| Order according to the language of the system | The same program would give different results on different machines |
| Waiting for `Option` | It would block point 1 of the roadmap behind point 3 for no reason |

## Compatibility

- **No program valid in 0.5.1 stops being so or changes its result** (section 10). No name
  is reserved.
- **Diagnostics of invalid programs**: those that contain a loose `.` go from `E1001` to `E1101`
  or `E2008` (section 9).
- **The suggestion of `E2011` changes when one side is a `Text` and the other a number**: now it says to
  convert one of the two sides (`to_text(...)` converts a number into a text, `Int.parse(...)` reads
  a number from a text) instead of saying that the operator only compares `Int` and `Float`. The code, the
  title and the category do not change, and it only happens in a program that was already invalid. It can be seen in
  `tests/golden/examples/invalid__type_errors.run.stderr`. Ordering two `Text` no longer gives `E2011`.
- **`nexora.inspect/2`**: `qualifier` field added to `Call`, without changing the version (section 7.4).
  A new row in the history of `inspect-schema.md`.
- **`nexora.symbols/1`**: `contracts` field and qualified names in `builtins`. **`nexora.context/1`**:
  qualified names in `builtins_called` and the value `text_operations` in `features`. Without changing the
  version of either of the two.
- **`nexora.diagnostics/1`**: no format changes.

## Required changes if it is approved

| Where | What |
|-------|------|
| `tokens.py`, `lexer.py` | The `.` token outside numbers, with its position to check that it has no spaces around it |
| `parser.py` | The qualified call and the syntax errors of section 9 |
| `ast_nodes.py` | The `qualifier` field of `Call` |
| `checker.py` | The functions of the types, their resolution, the diagnostics of section 9 and the ordering between texts |
| `prelude.py` (new) | The contracts of section 4, written in NEXORA and parsed with the real parser |
| `interpreter.py` | The new functions and the checking of their `requires` and suggestions (section 7) |
| `tooling.py`, `schemas.py` | `qualifier`, `contracts`, `text_operations` and the regenerated schemas |
| `docs/language-spec.md`, `docs/types.md`, `docs/diagnostics.md`, `docs/inspect-schema.md`, `docs/ai-context.md`, `docs/limitations.md` | The syntax, the rules and the functions |
| `examples/texts.nex` | An example that uses all of them, with its recorded output |
| `web/guide.html`, `web/js/playground/syntax.js` | The guide, and highlighting `Type.function` |

## Regression tests

**Semantics**

1. `Text.length`, `Text.contains`, `Text.starts_with` and `Text.ends_with`: every row of section 5.1.
2. `Text.slice`: every row of section 5.2, and the two equivalences for all the cuts of several
   texts with characters outside ASCII.
3. Comparison: every row of section 2; `E2011` between a `Text` and another type; a refined type with
   base `Text` is compared as its base.
4. `Int.can_parse` and `Float.can_parse`: every row of section 6.2. Texts of 1,000,000 digits,
   of leading zeros followed by a small number, of mantissa and of exponent (section 6.4):
   correct answer and no internal error, which is what would fail if a text of more than 4300 digits were
   converted with `int()`. Without measuring times.
5. Rounding and round trip: the extremes of `Int`; `-0.0`; the two midpoints of section 6.4
   written with all their digits (the exact half of the smallest positive gives `0.0`, and the midpoint between
   the largest finite and 2¹⁰²⁴ is not accepted); `sys.float_repr_style == "short"`; and a battery of random
   values with a fixed seed in which `Float.parse(to_text(x)) == x`.

**Requirements**

6. Every broken `requires` gives `E4001` with the label, the exact notes of section 7.2 and the
   position of the call; with several broken, the first one is reported. Every row of the table of
   suggestions, including `Int.parse` with a text out of range (`E4001` with the suggestion of the range,
   never `E3002` or `E3005`).
7. An error when evaluating an argument is reported before any requirement.
8. `and` and `or` do not evaluate the requirements of a call that is not needed.
9. The contracts of section 4 are parsed without errors, have type `Bool` and cannot fail when
   evaluated; the `ensures` hold in all the cases of tests 1 to 5.
10. Every row of the table of section 7.3, including `Type(x)`, `E2017` and `nex test`.

**Qualified calls**

11. Valid calls: every function of section 3.2 as an expression, as an argument of another call,
    inside `requires`, `ensures`, `invariant`, `decreases`, `example` and the condition of a refined
    type.
12. Unknown qualifiers: `Texto.length`, `geometry.area`, `Percent.parse`, `Bool.parse`,
    `print.x`, with the code, the label and the suggestion of section 9.
13. Functions that do not exist: `Text.lenght` (with its suggestion), `Int.length`, and unqualified `length(t)`
    (it suggests `Text.length`).
14. Syntax errors with the dot: every `E1101` row of section 9, including `Text.` at the end
    of the file and before a line break, `Text . length(t)`, `Text` and `.length(t)` separated by a
    line break inside and outside parentheses, `Text.length.x(t)`, `Text.length(s).x`, `1.length`,
    `.5`, `1.5.2` and the declaration `fn Text.length(...)`. And that `Text.length (s)` is valid.
15. A value in front of the dot: `name.length()` gives `E2008` with the suggestion `Text.length(name)`.
16. A variable or a parameter called `length`, `slice` or `contains` is valid and coexists with
    `Text.length` in the same function.
17. A variable or a parameter called `Text` or `Int` is valid, and `Text.length(s)` calls the function
    of the type even if that variable is visible.
18. Valid programs do not change: for every program of `examples/` and of the documentation, the
    sequence of tokens, the output and the diagnostics are those of 0.5.1, and `nex inspect` only adds
    `"qualifier": null`.
19. The program cut at every character (the robustness test that already exists) includes qualified
    calls and never produces an internal failure.

**Tools**

20. `nex inspect`: `qualifier` present in all calls (`null` or the type), after
    `arguments` and before `type`; the fields that already existed keep their order (`EXPECTED_FIELDS` of
    `test_inspect.py` gains `qualifier`); the document validates with the new schema and with that of 0.5.1,
    with and without qualified calls; a consumer that resolves `callee` against the functions of the
    program and the `builtins` list never attributes `Text.length` to a variable or a parameter `length`.
21. `nex symbols`: qualified names in `builtins` and `contracts` with `checked_at_run_time`;
    `get_capabilities()`: the same list with `contracts`. `nex context`: qualified names in
    `builtins_called`, the value `text_operations` in `features` and the `requires` of the built-in
    functions called in the text output. Every document validated with its schema.

## Review

### Answers to the previous reviews

| # | Topic | Answer | Where |
|---|-------|--------|-------|
| 1 | Names of the new functions | Alternative C: functions qualified by their type | Section 3 |
| 2 | `_` in the numbers of a text | No: outside the grammar | Sections 6.1 and 6.2 |
| 3 | Leading zeros | Yes: `"007"` is a valid integer of value 7 | Section 6.2 |
| 4 | `"1e-400"` | Yes, as `0.0` (and `"-1e-400"` as `-0.0`); a non-finite result, like that of `"1e309"`, no | Section 6.2 |
| 5 | Suggestion when reading numbers | Yes, different depending on what failed | Section 7.2 |
| 6 | The `ensures` of the built-in functions | They are kept as information, with `checked_at_run_time: false`, and the tests check them | Sections 7.1 and 7.4; test 9 |
| 7 | `Int`, `Float`, `Bool` and `Text` as variable names | They are still allowed; forbidding them is not necessary | Section 3.3; test 17 |
| 8 | `nex inspect` | R1: `callee` with the full name and `qualifier` in all calls (`null` if there is none), without changing the version | Section 7.4 |
| 9 | Methods on values | Outside the current design, without declaring them impossible | Section 8 |

### Fixes of the last review

| Problem | Fix |
|---------|-----|
| The contracts were shown as `fn Text.length(...)` and it was said that they are parsed with the real parser, but a program cannot declare functions like that | Section 4: that notation is the way of showing signatures; what is parsed are the conditions, as expressions. Section 9: a diagnostic for whoever tries to declare `fn Text.length` |
| "No spaces or line breaks around the dot" did not say what happens with a line break outside parentheses, which ends the statement earlier | Section 3.4 (new): how the dot is tokenized and parsed. Section 9: every line break case, with its diagnostic |
| `1.length` appeared with a fixed message, but the message depends on where the dot appears | Section 9: "a dot anywhere else" gives the `E1101` the parser already gives in that context |
| The suggestion for a refined type named `Int` whatever its base was | Section 9: it names the base of each case, and only if that base has functions |
| A row said "what is not an error" and included a case that gives `E2010` | Section 9: "Other cases" |
| The cost of huge texts and the rounding guarantees were missing | Section 6.4 (new), with measurements; edge cases added to the table of section 6.2; tests 4 and 5 |
| The compatibility of `nex inspect` did not separate protocol, schema and output | Section 7.4: three levels checked, and the observable changes separately |
| "The current list is in `builtins` of `nex symbols` and `nex context`", and the title "`nex symbols` and `nex context`", attributed to `nex context` a list and a field that it does not expose | Section 7.4, the compatibility section and test 21: `builtins` and `contracts` in `nex symbols` and in `get_capabilities()` (`language.builtins`); `nex context` only names in `builtins_called` the functions called and shows their `requires` in the text output. The scope of the decision does not change: it is where each field is named, not which fields there are |
| A code fragment split across two lines (section 3.3) | Joined |
| The compatibility section did not list the change of the suggestion of `E2011` when ordering a `Text` with a number, which did happen | Compatibility section: the text of the suggestion is recorded as an observable change. The scope does not change: `E2011` is still the same code, with the same title and the same category |

### Approval

Approved as written: alternative C (functions qualified by their type), representation R1
in `nex inspect`, methods on values outside the current design and no flat name reserved.
