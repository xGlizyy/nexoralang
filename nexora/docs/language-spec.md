# NEXORA language specification

- **Specification version:** 0.13
- **Reference implementation:** `nexora` 0.14.1 (this repository, directory `nexora/`)
- **Status:** describes exactly what the interpreter of 0.13 does. The syntax of 0.12 comes from
  [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md); a program written for 0.11 is
  rewritten with `nex migrate` ([CLI reference](cli-reference.md#nex-migrate)).

This document is the reference for the language: it defines the syntax and the meaning of every
construct. If the interpreter and this document disagree, that is a bug to be fixed.

How to read the status of each part:

| Mark | Meaning |
|------|---------|
| *(no mark)* | **Implemented** and covered by tests |
| **Experimental** | Implemented and tested, but its syntax or its rules may change. In version 0.8 no part of the language is |
| **Planned** | Does not exist. Gathered in section 14; not part of the language |

The changes since version 0.1 are in [`CHANGELOG.md`](../CHANGELOG.md) and their reasons
in [`docs/decisions/`](decisions/README.md).

## 1. Philosophy

NEXORA explores what a programming language can look like when its code is read and written by
people and by automated tools alike. In this version that idea takes the shape of five
decisions:

1. **One way to write each thing.** The syntax is small and regular.
2. **Nothing implicit.** There are no automatic conversions between types and no values that are
   "true" or "false" by convention. Every change of type is written down.
3. **What can be checked before running is checked before running.** Names, scopes and types are
   verified without running the program; what depends on values is precisely delimited
   (section 10).
4. **The rules are part of the code.** A function declares what it expects and what it promises
   (contracts, section 9), a type can declare which values it accepts (refined types,
   section 4.4) and a loop declares why it ends and what it keeps true (section 9.5). Every rule can carry its explanation, and when it is broken the diagnostic says
   which one, where and with which values ([decision 0006](decisions/0006-requisitos-verificables.md)).
5. **Tools receive data, not text.** The program and its errors can be obtained as JSON
   with a versioned schema.

The rules of the language are explicit and deterministic. None depends on an AI model, on the
internet or on an external service: the same program always gives the same result.

This specification does not claim that NEXORA is faster, safer or better for AI than other
languages. There is no measurement that supports it.

## 2. Lexical structure

### 2.1 Files

- A program is a single text file with the `.nex` extension.
- The encoding is UTF-8. A leading byte order mark (BOM) is accepted.
- Line endings may be `\n`, `\r\n` or `\r`.

### 2.2 Spaces, lines and comments

- Spaces and tabs separate elements and have no other meaning. Indentation is free.
- **The end of a line ends a statement.** There is no semicolon.
- Inside parentheses `( )` line breaks are ignored: an expression, an argument list or a
  parameter list may span several lines.
- A comment starts with `//` and runs to the end of the line. There are no block comments.

### 2.3 Names

A name starts with a letter `a-z`, `A-Z` or `_` and continues with letters, digits `0-9` or `_`.
Only ASCII letters are allowed. Names are case-sensitive.

### 2.4 Keywords and reserved words

Keywords:

```
fn   let   var   return   if   else   while   for   in   true   false   and   or   not
gives   needs   promises   trust   example   keeps   shrinks   type   where   uses   import   pub
```

Words reserved for future versions. They cannot be used as names, and using them produces the
error `E1103`:

```
assert   break    const    continue enum     match    test     try
```

The clause words of 0.11, `requires`, `ensures`, `invariant` and `decreases`, are not keywords and
cannot be names either. Where a name is declared (`let`, `var`, `fn`, a parameter) or where a
statement or a clause starts, which is where the syntax of 0.11 wrote them, they are the error
`E1107`, whose hint is `nex migrate`; inside an expression, as any keyword there, `E1101`. They stay
reserved only in the versions 0.12.x
([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), section 9). `ai` and `tool`,
reserved until 0.11, are ordinary names.

These are not reserved words but predefined names: the types `Int`, `Float`, `Bool`, `Text` and
`Void`; the functions `print`, `to_text`, `to_float`, `to_int`, `args`, `input`, `read_file`,
`write_file`, `Net.get` and `Process.run`; `result`, which only has a special meaning inside a `promises` clause; and
`value`, which only has one inside the condition of a refined type.

### 2.5 Literals

| Literal | Type | Examples | Rules |
|---------|------|----------|-------|
| Integer | `Int` | `0`, `42`, `1_000_000` | Decimal digits. `_` may separate two digits. No leading zeros (`007` is an error). Maximum `9223372036854775807` |
| Decimal | `Float` | `3.14`, `0.5`, `10.0` | Digits, a dot and more digits. Digits are required on both sides of the dot |
| Boolean | `Bool` | `true`, `false` | |
| Text | `Text` | `"Hello"` | Between double quotes, on a single line |

Numeric literals have no sign: `-5` is the `-` operator applied to `5`.

Escape sequences inside a text:

| Escape | Meaning |
|--------|---------|
| `\n` | Line break |
| `\t` | Tab |
| `\"` | Double quote |
| `\\` | Backslash |
| `\{` | Opening brace `{` |

Any other sequence that starts with `\` is an error (`E1003`). An unescaped brace `{` inside
a text is an error (`E1005`): it is reserved for future interpolation.

### 2.6 Symbols

```
(  )  {  }  [  ]  ,  :  .  =  +  -  *  /  ==  !=  <  <=  >  >=
```

`->` is read as one symbol, but no construct of 0.12 uses it: after the parameters of a function it
is the error `E1108` (the result type is written with `gives`), and anywhere else `E1101`.

A `.` followed by a digit, inside a number, is part of the decimal number (`1.5`). Any
other `.` is a symbol, which is only valid in a qualified call such as `Text.length(s)`
(section 8.1).

Any character that is not part of what this section describes is an error (`E1001`); the
analyzer never ignores an unknown character.

## 3. Grammar

In EBNF notation. `NEWLINE` is one or more consecutive line endings.

```ebnf
program    = { NEWLINE } { import_decl } { ( type_decl | record_decl | uses_decl | function ) { NEWLINE } } ;

import_decl = "import" TEXT ;
type_decl  = [ "pub" ] "type" NAME "=" type "where" expression [ explanation ] end ;
record_decl = [ "pub" ] "type" NAME "=" "{" record_fields "}" ;
record_fields = record_field { "," record_field } ;
record_field = NAME ":" type ;
uses_decl  = "uses" ( "read" | "write" ) TEXT ;
function   = [ "pub" ] "fn" NAME "(" [ params ] ")" [ "gives" type ] body ;
body       = block                                          (* no header clauses *)
           | NEWLINE header_clause { header_clause } block ;
header_clause = ( "needs" | "promises" ) [ clause_name ] expression [ explanation ] NEWLINE
              | "trust" [ clause_name ] expression explanation NEWLINE   (* explanation required *)
              | "example" expression [ explanation ] NEWLINE ;           (* no name *)
clause_name = NAME ":" ;
params     = param { "," param } ;
param      = NAME ":" type ;
type       = [ NAME "." ] NAME [ "[" type "]" ] ;
explanation = "," TEXT ;

block      = "{" { NEWLINE } { statement end } "}" ;
end        = NEWLINE | (* nothing, if what follows is "}" *) ;

statement  = let | var | return | if | while | for | block | assignment | field_assignment | expression ;
let        = "let" NAME [ ":" type ] "=" expression ;
var        = "var" NAME [ ":" type ] "=" expression ;
return     = "return" [ expression ] ;
if         = "if" expression block [ "else" ( if | block ) ] ;
while      = "while" expression loop_body ;
for        = "for" NAME "in" expression loop_body ;
loop_body  = block                                          (* no header clauses *)
           | NEWLINE loop_clause { loop_clause } block ;
loop_clause = ( "keeps" | "shrinks" ) [ clause_name ] expression [ explanation ] NEWLINE ;
assignment = NAME "=" expression ;
field_assignment = NAME "." NAME "=" expression ;

expression     = or ;
or             = and { "or" and } ;
and            = comparison { "and" comparison } ;
comparison     = additive [ ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) additive ] ;
additive       = multiplicative { ( "+" | "-" ) multiplicative } ;
multiplicative = unary { ( "*" | "/" ) unary } ;
unary          = ( "-" | "not" ) unary | primary ;
primary        = INT | FLOAT | TEXT | "true" | "false"
               | NAME
               | NAME "(" [ expression { "," expression } ] ")"
               | NAME "." NAME "(" [ expression { "," expression } ] ")"
               | NAME "." NAME
               | NAME "(" record_fields_values ")"
               | "[" [ expression { "," expression } ] "]"
               | "(" expression ")" ;
record_fields_values = record_value { "," record_value } ;
record_value = NAME ":" expression ;
```

Notes:

- At the top level of the file there are only imports, functions and type declarations.
  Imports go **before** any other declaration, one per line; anywhere else they are the error
  `E1101`. A type cannot be declared inside a function (`E1101`).
- A file is a module (section 7.6). `import "app/models.nex"` declares that the program uses the
  file `app/models.nex`, and `pub` marks what a module makes visible from outside: `pub fn`,
  `pub type` (both refined types and records) and nothing else. Everything else is private
  to the file that declares it.
- An explanation (`explanation`) is a single non-empty text literal, on one line. A text that is
  empty, made only of spaces or containing a line break (`\n`) is the error `E1101`.
- **The header.** The clauses of a function (`needs`, `promises`, `trust`, `example`) go between its
  signature and the `{` of its body, and those of a loop (`keeps`, `shrinks`) between its head and its
  `{`. Inside a body they are the error `E1106`. Where the `{` goes:
  - Without clauses, on the line of the signature or of the head of the loop: `fn main() {`. A `{`
    alone on the next line is the error `E1101`.
  - With clauses, the signature or the head ends its line, each clause takes its own line, and the
    `{` goes **alone on the line after the last clause**. A `{` on the line of a clause is the error
    `E1101`.
  - Blank lines and comment lines may appear between the signature, the clauses and the `{`:
    they are not tokens.
- **Clause names.** `needs`, `promises`, `trust`, `keeps` and `shrinks` may carry a name before
  their condition: `needs fits: part <= 92233720368547758`. A name is written in lowercase (`E1101`
  otherwise) and cannot be a keyword (`E1101`). It is unique within the function, its loops included,
  and different from the parameters and from `result` (`E2031`). A name is not a variable: no
  expression can use it. Names are optional. An `example` has no name (`E1101`).
- **The result type** is written after `gives`: `fn add(a: Int, b: Int) gives Int`. A function that
  gives nothing has no `gives`. `->` before the result type is the error `E1108`, and `gives Void`
  is the error `E2012`.
- `else` is written on the same line as the `}` that closes the previous block: `} else {`.
- Comparisons do not chain: `a < b < c` is a syntax error (`E1101`). Write
  `a < b and b < c`.
- An assignment is a statement, not an expression: `a = b = 1` and `if x = 1 { }` are syntax
  errors (`E1101`). There is no `+=` or `++`.
- A trailing comma is not allowed in parameter or argument lists.
- In a qualified call (`NAME "." NAME "("`), the `.` is attached to both names: no spaces or
  line breaks on either side (`E1101`). Between the second name and the `(` there may be spaces,
  as in any call. Whether the first name is a type with that function, or a module that makes
  that function public, is checked by the static analysis (`E2008` and `E2027`, sections 8.1 and 7.6).
  If the second name is followed by `(` and by named fields, what is built is a record
  of the module: `models.Point(x: 1, y: 2)`.
- A record is declared with `type` and braces: `type Point = { x: Int, y: Int }`. The braces go
  on the same line as the `=`, and inside them a line break is allowed between fields. A
  record has at least one field and does not allow a trailing comma (`E1101`).
- A capability is declared with `uses`, at the top level of the file: `uses read "data.txt"`. It declares
  what the program needs, it does not grant it: whoever runs it has to allow it separately, and the
  environment has to support it (section 8.3). The path is a text literal and cannot be
  empty.
- A record is built with the name of the type and the named fields: `Point(x: 1, y: 2)`. The
  order in which the fields are written does not matter, but each one is given only once and all of them are
  required (`E2023`).
- Reading a field is written `value.field`. The root is always a name; a field cannot be read
  from a call, a construction, a group or a list (`E1101`). Access chains
  (`p.x.y`) have no length limit: every intermediate step has to be a record
  (`E2024`). The `.` is attached to both names, as in a qualified call.
- A record does not change: `p.x = 1` is the error `E2025`. The form exists so that it can be said, not so that
  it can be done.
- Size limits: parentheses, unary operators, blocks, `else if` chains and
  types can be nested up to 64 levels, and an expression tree can have up to 256 levels (for
  example, a sum of 256 terms). Exceeding them is the error `E1105`.
- A type is written `NAME`, `MODULE "." NAME`, or either of them with arguments in square
  brackets. In this version only `List` accepts type arguments, and exactly one; a type from
  another module accepts none, because it cannot be `List` (`E2012`). `List` without an argument is not a
  type (`E2012`); `List[]`, `List[Int, Text]`, `List[Void]`, `Option[...]`, `Result[...]`, `Foo[...]`
  and `Int[...]` are syntax errors (`E1101`). Nesting counts towards the 64-level limit.

## 4. Data types

| Type | Values | Notes |
|------|--------|-------|
| `Int` | Integers from `-9223372036854775808` to `9223372036854775807` | 64-bit signed. Going out of range is a runtime error (`E3002`), never a wrong result |
| `Float` | IEEE 754 64-bit floating point | There is no infinity and no NaN: an operation whose result does not fit is a runtime error (`E3003`). Negative zero (`-0.0`) exists; it is equal to `0.0` and is written `-0.0` |
| `Bool` | `true`, `false` | |
| `Text` | Unicode text | Immutable |
| `List[T]` | Immutable, finite sequence of values of type `T` | `T` cannot be `Void`; there is no covariance (section 4.5) |
| `Void` | No value | The type of a call to a function that has no `gives`. It is never written in a program |
| A record | The values built with `Name(field: value, ...)` | Declared by the program: `type Point = { x: Int, y: Int }` (section 4.6) |

`Int`, `Float`, `Bool` and `Text` are the built-in **value types**. `List[T]` is a compound value
type (section 4.5); a program can also declare refined types over the built-in ones
(section 4.4) and records (section 4.6). Value types are the ones a variable, a parameter or an
expression can have. `Void` is not a value type: writing it, as the type of a variable or of a
parameter or after `gives`, is the error `E2012` (`List[Void]` is `E1101`), and using a call to a
function without `gives` where a value is needed is the error `E2011`.

Writing a name that is not a type where a type is expected is the error `E2012`.

### 4.1 The type system is static

The type of **every** expression is determined without running the program, from the literals, the
annotations and the signatures of the functions. There is no case in which the type of an expression
depends on a computed value, so no type error can appear while the program runs.

### 4.2 Compatibility

**A value is accepted where a type is expected only if it is of that same type, or of a refined type
built on it** (section 4.4). There are no "wider" numeric types and no automatic conversion:

- An `Int` is not accepted where a `Float` is expected, nor the other way round.
- No type converts to `Bool` or to `Text` on its own.
- A `Percent` (refined over `Int`) is accepted where an `Int` is expected. An `Int` is **not** accepted
  where a `Percent` is expected, unless it is a constant that meets its condition.
- The arguments of `List` are **invariant**: `List[Int]` is not accepted where
  `List[Text]` is expected, and `List[Percent]` is not accepted where `List[Int]` is expected, even though every `Percent`
  is an `Int`. A refined element can be widened to its base when the list is built
  with an expected type (`let xs: List[Int] = [Percent(10), 20]`).

This rule applies equally to the annotation of a variable, to the arguments of a call, to the
value of a `return` and to the operands of an operator.

### 4.3 Conversions

The only conversions that exist are explicit calls to built-in functions:

| Function | Converts | Rule |
|----------|----------|------|
| `to_float(value)` | `Int` → `Float` | Always possible. Integers of more than 53 bits are rounded to the nearest `Float` |
| `to_int(value)` | `Float` → `Int` | Drops the decimal part (rounds towards zero): `to_int(3.9)` is `3`, `to_int(-3.9)` is `-3`. If the result does not fit in an `Int`, runtime error `E3005` |
| `to_text(value)` | `Int`, `Float`, `Bool`, `Text` or `List[T]` → `Text` | The same text that `print` would write (section 8) |
| `Int.parse(text)` | `Text` → `Int` | Only if `Int.can_parse(text)`; otherwise, `E4001` (section 8.1) |
| `Float.parse(text)` | `Text` → `Float` | Only if `Float.can_parse(text)`; otherwise, `E4001` (section 8.1) |

There is no conversion from `Text` to `Bool`, nor between `Bool` and numbers.

```nex
let count = 3
let price = 19.99
let total = to_float(count) * price        // correct: Float * Float
print("Total: " + to_text(total))          // correct: Text + Text
```

```nex
let total = count * price                  // E2011: Int and Float do not mix
print("Total: " + total)                   // E2011: '+' joins Text with Text
```

### 4.4 Refined types

A refined type is a value type plus a condition that all its values meet:

```text
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
```

It is declared at the top level of the file, before or after it is used. `Percent` is the name,
`Int` is the **base** and what follows `where` is the **condition**. After the condition there may be,
after a comma, the explanation of the rule; it appears in the diagnostics when the rule is broken.

**The guarantee.** Every value whose type is a refined type meets its condition, at any point
of the program. To keep it, a value can only come to have a refined type in two ways:

| Way | Example | When it is checked | If it is not met |
|-----|---------|--------------------|------------------|
| A **constant** where the type is expected | `let p: Percent = 20`, `discount(20)`, `return 20` | Without running, in `nex check` | `E2017`, the program does not run |
| The **explicit check** `Percent(x)` | `let p = Percent(total / 2)` | When running, every time it is evaluated | `E4003`, the program stops there |

A constant is a literal, optionally with `-` or `not` in front of it or in parentheses. Checking a
constant costs as much as the conditions of the whole chain of its type; if the total for a
program exceeds 100,000 evaluated condition nodes, the program is rejected with `E2019` instead
of being left half checked. It is a limit of the implementation, like those of section 3, and an
ordinary program stays far below it. Any
other value of the base (a variable, an operation, the result of a call) is not accepted where
the refined type is expected (`E2011`): it has to be checked with `Percent(...)`. That way, every point where
the program can stop because of a rule is written in the code.

Rules of the declaration:

- The name starts with an uppercase letter (`E2016`) and cannot be that of a built-in type (`E2016`), that of
  another type (`E2016`), nor be used for a function, a parameter or a variable (`E2006`).
- The base is `Int`, `Float`, `Bool`, `Text` or another refined type. It cannot be a list
  (`E2016`). A chain of types that does not reach a built-in type (`type A = B ...` and
  `type B = A ...`) is the error `E2016`.
- The condition is a `Bool` expression (`E2011`). Only the name `value` exists in it; it is the
  value being checked and has the type of the base (`E2005` for any other name).
- The condition cannot call functions of the program or check other refined types
  (`E2018`). It can use operators, literals and the built-in conversions. A refined type
  describes a value and nothing more; rules that depend on other data are written with `needs`.

Using the values:

- A refined value is accepted where its base is expected, or any type in the chain of bases: a
  `Percent` is an `Int`.
- In an operation it counts as a value of its base: `p + 1` is an `Int`, not a `Percent`, because the
  result may not meet the condition. To have a `Percent` again it has to be checked.
- Two different refined types are different types even if they have the same base and the same
  condition.
- `Percent(x)` receives exactly one argument of the same base (`E2009`, `E2011`) and returns a
  `Percent`. The name of a type can only be used this way: written alone, without parentheses, it is `E2011`.

**Refining a refined type.** `type Pass = Percent where value >= 50` requires both conditions.
They are checked in order, starting from the base: first that of `Percent` and then that of `Pass`. The
diagnostic says which of the two is false.

<!-- nex:run -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
type Pass = Percent where value >= 50, "Passing starts at half"

fn grade(points: Int, total: Int) gives Percent
    needs total > 0, "There is nothing to grade"
{
    return Percent(points * 100 / total)
}

fn main() {
    let minimum: Pass = 50
    let score = grade(42, 60)
    print(score)
    print(score >= minimum)
}
```

```text
70
true
```

A constant that does not meet the condition is rejected without running anything:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() {
    let discount: Percent = 120
    print(discount)
}
```

```text
type error[E2017]: Value outside refined type
 --> program.nex:4:29
  |
4 |     let discount: Percent = 120
  |                             ^^^ 120 is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 120
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: check failed with 1 error
```

And a computed value that does not meet it stops the program at the point where it is checked:

<!-- nex:fails exit=5 -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() {
    let points = 130
    print(Percent(points))
}
```

```text
contract error[E4003]: Refinement violated
 --> program.nex:5:11
  |
5 |     print(Percent(points))
  |           ^^^^^^^^^^^^^^^ This value is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 130
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: the program stopped because a contract was broken
```

### 4.5 Lists

A list is an **immutable and finite** sequence of values of the same type. Its type is written
`List[T]`, where `T` is the type of the elements:

```nex
let numbers: List[Int] = [1, 2, 3]
let empty: List[Int] = []
let nested: List[List[Int]] = [[1], [2, 3]]
let words: List[Text] = ["a", "b"]
```

`T` can be `Int`, `Float`, `Bool`, `Text`, a refined type or another `List[...]`. It cannot be
`Void`: `List[Void]` is a syntax error (`E1101`). The type is **invariant** in `T`:

- `List[Int]` and `List[Text]` are different types; there is no conversion from one to the other.
- `List[Percent]` is not accepted where `List[Int]` is expected, even though `Percent` is a refined `Int`.
  The reason is that an operation that accepts `List[Int]` could treat its elements as arbitrary
  `Int` values, and a `List[Percent]` promises more than that.
- A refined element can be widened to its base when a list is built with an expected type:
  `let xs: List[Int] = [Percent(10), 20]`.

#### Literals and inference

`[a, b, c]` and `[]` are expressions. Without an expected type, the **first element** sets the type of
the rest; all of them have to be acceptable as that type. With an expected type `List[T]`, all the
elements are checked against `T`.

```nex
let numbers = [1, 2, 3]                 // List[Int]
let texts = ["a", "b"]                  // List[Text]
let nested = [[1], [2, 3]]              // List[List[Int]]
let empty: List[Int] = []               // the expected type sets Int
```

An empty list **needs an expected type**. The type of the element is not made up:

<!-- nex:body-fails codes=E2011 -->
```nex
let xs = []                             // the type of the elements is unknown
print([])                               // neither is it here
```

The expected type can come from an annotation, from a parameter, from the return type, from an
assignment or from the left-hand side of an equality (`a == []`). It does not propagate from the right-hand side to the
left: `[] == a` is `E2011` even if `a` has a type. It also propagates into nested lists:
`let xs: List[List[Int]] = [[]]` is valid.

All the elements of a list have the same type. `Int` and `Text`, for example, do not mix:

<!-- nex:body-fails codes=E2011 -->
```nex
let mixed = [1, "a"]                    // Expected Int, found Text
```

#### Immutability, equality and printing

A list does not change. A `var` variable can come to point to another list, but the previous list
keeps its elements. `List.append` and `List.concat` build new lists (section 8.2).

`==` and `!=` compare lists of the **same type** structurally: same elements, in the same
order, compared recursively. The result is `Bool`. There is no ordering (`<`, `<=`, `>`, `>=`) between
lists.

`print` and `to_text` write the canonical form with square brackets and no quotes around texts:
`[1, 2, 3]`, `[[1], [2, 3]]`, `[a, b]`, `[]`. Diagnostics may quote texts to tell them
apart; that is not the output of `print`. Printing does not escape texts: it is not a serialization
format, and a text that contains `,` or `]` may look ambiguous.

<!-- nex:run -->
```nex
fn main() {
    let numbers = [1, 2, 3]
    let empty: List[Int] = []
    let nested = [[1], [2, 3]]
    print(numbers)
    print(empty)
    print(nested)
    print(numbers == [1, 2, 3])
    print(empty == [])
}
```

```text
[1, 2, 3]
[]
[[1], [2, 3]]
true
true
```

There is no index syntax (`xs[i]`) and no way to modify an element. To read a position,
use `List.get`; to add to lists or join them, `List.append` and `List.concat` (section 8.2). A refined
type cannot be built over a list in this version (`E2016`).

### 4.6 Records

A **record** is a type that the program declares, with **immutable** and **required** fields, and that
is built by giving each field its value by name.

<!-- nex:run -->
```nex
type Point = { x: Int, y: Int }
type Line = { from: Point, to: Point }

fn main() {
    let origin = Point(x: 0, y: 0)
    let end = Point(x: 3, y: 4)
    let segment = Line(from: origin, to: end)
    print(segment.from.x)
    print(segment)
}
```

```text
0
Line(from: Point(x: 0, y: 0), to: Point(x: 3, y: 4))
```

**Declaration.** `type Name = { field: Type, ... }`. The name starts with an uppercase letter, like that of
any type, and cannot be that of a built-in type or that of another declared type (`E2016`). Every
field has a name and a type; two fields of the same record cannot have the same name (`E2016`).
The type of a field can be a built-in type, `List[T]`, a refined type or **another record**.

**Construction.** `Name(field: value, ...)`. The fields can be written in any order,
but each one is given **only once** and **all** of them are required: a missing field, a repeated
one or one that the record does not have is the error `E2023`. The value of a field has to have the
type of the field (`E2011`).

**Reading.** `value.field`. The root is always a name: a variable, a parameter or `result` inside
a `promises`. Reads can be chained (`p.x.y`), with no length limit, as long as every intermediate
step is a record; if the value is not a record, or the record does not have that field, it is the
error `E2024`. A type name is not a value: `Point.x` does not read a field, it is a qualified call
like those of section 8.1.

**Immutability.** A record does not change: there is no way to assign to a field. `p.x = 1` is the
error `E2025`.

**Identity.** A record is **nominal**: its identity is that of its declaration, not that of its name
or of its fields. Two records with the same fields are different types, and a value of one is not
accepted where the other is expected (`E2011`). Two values of the **same** record are compared **by
value**, field by field: `Point(x: 1, y: 2) == Point(x: 1, y: 2)` is `true`.

**Forward references and cycles.** A record can use another one declared further down, as long as the
dependency graph has no cycles. A record cannot contain itself, neither directly
nor through another record or a list: `type A = { a: A }` is the error `E2016`, and the message
writes out the cycle (`A -> B -> A`).

**What there is not.** A record has no methods or functions of its own, cannot be refined, does not accept
generics and cannot be recursive. A refined type cannot be built over a record
(`E2016`).

### 4.7 Option and Result

Two types of the language say what a value cannot say on its own: that **there is no** value
(`Option[T]`) or that **something failed** (`Result[T, E]`). Both have two variants, and **the variant is
part of the value**: `None` is never `Some(x)` and `Ok(x)` is never `Err(x)`, even if the two payloads are
equal.

Both exist so that a program can say "there is nothing" or "this failed" **without exceptions**: an
`Option` or a `Result` is a value that is returned, stored, compared and printed.

**`Option[T]`.** `T` is the type of the value that is there when there is one.

- `Some(value)` builds the variant with a value. Its type is `Option[T]`, where `T` is the type of
  `value`.
- `None` is the variant without a value. Its type is `Option[T]`, and `T` is given by **the context that expects the
  value**: the annotation of a variable, the type of a parameter, the result type of a
  function or the other side of a comparison. Without that context, `None` has no type, and it is the error
  `E2011` ("Cannot infer the type of None without an expected type").

**`Result[T, E]`.** `T` is the type of the value that is obtained and `E` that of the error that is received.

- `Ok(value)` builds the successful variant. Its type is `Result[T, E]`: `T` is the type of `value`
  and `E` is given by the context that expects the result.
- `Err(error)` builds the variant with an error. Its type is `Result[T, E]`: `E` is the type of
  `error` and `T` is given by the context that expects the result.

The error is stored **as is**: `Err("the file is missing")` carries that text, and when it is read it is still
that text.

**Inspection.** Each variant is recognized without exceptions:

| Function | Returns |
|----------|---------|
| `Option.is_some(x)` | `true` if `x` is a `Some` |
| `Option.is_none(x)` | `true` if `x` is a `None` |
| `Result.is_ok(x)` | `true` if `x` is an `Ok` |
| `Result.is_err(x)` | `true` if `x` is an `Err` |

**Reading the value.** `Option.value_or(x, fallback)` returns the value of `x` if it is a `Some`, and
`fallback` if it is a `None`; the fallback has the same type as the value. `Result.value_or(x, fallback)`
does the same with an `Ok` and an `Err`. (Until 0.11 these functions were called `unwrap_or`, and
those of the next paragraph `unwrap`: the old names are the error `E2008`.)

`Option.value(x)`, `Result.value(x)` and `Result.error(x)` read the value **without** a fallback: if the
variant does not carry that value, the program stops with a diagnostic (`E3011`, `E3012` or `E3013`).
There is no read that returns a made-up value, and none that makes the program fail without saying
why.

**Equality.** Two values of these types are compared by variant and by value: `Some(1) == Some(1)`
is `true` and `None == None` is `true`; `None == Some(1)`, `Ok(1) == Err(1)` and `Some(1) == Some(2)`
are `false`.

**How they are printed.** `Some(1)`, `None`, `Ok(1)` and `Err(boom)`, with the text unquoted, like the
fields of a record. In diagnostics the text is quoted: `Err("boom")`.

**What there is not.** There is no `match`, no `if let`, no `?` and no user enums: an `Option` or a
`Result` is recognized with the functions above and read with `value_or`, or with `value` when it is
known which variant it has. The type of a `None` or of an empty list that is an **argument** of a function with
type variables is not deduced from the other arguments: the language does not infer a type through
the arguments of a call. Give the type in a variable first.

## 5. Variables and scopes

### 5.1 Declaration

```nex
let name = "NEXORA"           // inferred type: Text
let age: Int = 25             // annotated type
```

- `let` declares a variable and gives it a value. A variable is always initialized when it is declared.
- **Inference:** without an annotation, the type of the variable is the type of its value.
- **Annotation:** with `: Type`, the value has to be exactly of that type. If it is not, the error
  is `E2011` and it points at the value. The variable keeps the annotated type, so that a single error is not
  repeated at every later use.
- The value cannot be a call to a function without `gives` (`E2011`).
- **A `let` variable is immutable.** There is no way to change its value; `name = "x"` is the
  error `E2007`. The parameters of a function are immutable too. A variable that has to
  change is declared with `var` (section 5.3).

```nex
let age: Int = "twenty"       // E2011: Expected Int, found Text
let price: Float = 5          // E2011: Expected Float, found Int   (suggests to_float)
let nothing = print("x")      // E2011: the call does not produce a value
let x: Void = 1               // E2012: a variable cannot be Void
```

### 5.2 Scopes and name resolution

- Every function has its own scope. It starts with its parameters and **does not see the variables of its
  caller** nor those of any other function. There are no global variables.
- Every `{ }` block (including those of `if` and `else`) opens a scope inside the one that contains it. An
  inner block can read the variables of the outer blocks of its own function.
- A variable exists from the statement after its declaration to the end of the block where
  it was declared. It is not visible inside its own initial expression (`let x = x` is an error).
- Functions are visible in the whole file, also before the line where they are declared.
- **A single namespace.** Functions, parameters and variables share names: a
  variable or a parameter cannot be named like a function of the program or like a built-in
  function (`E2006`). The names of refined types cannot be used for anything else either
  (`E2006`).
- **There is no name shadowing.** Declaring a name that is already visible, whether from the same
  block, from an outer one or a parameter, is the error `E2006`. Two sibling blocks can use
  the same name, because neither sees the variables of the other.
- Using as a value a name that does not exist is the error `E2005`. Using a function without calling it
  (`let f = add`) is the error `E2011`: functions are not values.

Consequence: inside a function, every name means a single thing from beginning to end.

### 5.3 Variables that change: `var` and assignment

<!-- nex:body -->
```nex
var count = 0                 // inferred type: Int
var total: Float = 0.0        // annotated type
count = count + 1             // assignment
```

- `var` has the same form and the same rules as `let` (inference, annotation, scope, no
  shadowing). The difference is that its value can be changed later with an assignment.
- **The type of a `var` never changes.** The assigned value has to be compatible with it, under the
  rule of section 4.2 (`E2011`).
- A `var` visible at that point can be assigned, also from an inner block. Assigning a
  `let` variable or a parameter is the error `E2007`; a name that is not a visible variable,
  `E2005`.
- **Parameters cannot be assigned.** That way, in `promises` and in diagnostics they always have the
  value the function was called with. To change it, copy it: `var rest = n`.
- A `var` of a refined type keeps the guarantee of section 4.4: it is assigned a constant that
  meets the condition (checked without running, `E2017`) or a value checked with `Type(x)`.
  `p = p + 1` is `E2011`; write `p = Percent(p + 1)`.
- A function does not see the variables of its caller, so a `var` only changes from its own
  function: there is no state shared between functions.

```text
var p: Percent = 20
p = 30                 // correct: constant that meets the condition
p = 120                // E2017: 120 is not a valid Percent
p = p + 10             // E2011: an Int is not a Percent
p = Percent(p + 10)    // correct: checked when running (E4003 if it is not met)
```

<!-- nex:valid -->
```nex
fn main() {
    let total = 10
    if total > 5 {
        let double = total * 2   // reads 'total' from the outer block
        print(double)
    }
    // 'double' no longer exists here
}
```

## 6. Expressions and operators

### 6.1 Precedence

From highest to lowest. All binary operators associate to the left.

| Level | Operators | Operands | Result |
|-------|-----------|----------|--------|
| 1 | `-x` | `Int` or `Float` | The same type |
| 1 | `not x` | `Bool` | `Bool` |
| 2 | `*`  `/` | Two `Int` or two `Float` | The same type |
| 3 | `+`  `-` | Two `Int` or two `Float` | The same type |
| 3 | `+` | Two `Text` | `Text` (concatenation) |
| 4 | `==`  `!=` | Two values of the same type (`Int`, `Float`, `Bool` or `Text`) | `Bool` |
| 4 | `<`  `<=`  `>`  `>=` | Two `Int`, two `Float` or two `Text` | `Bool` |
| 5 | `and` | Two `Bool` | `Bool` |
| 6 | `or` | Two `Bool` | `Bool` |

Parentheses group: `(2 + 3) * 4`.

`not` has higher precedence than comparisons: `not a == b` means `(not a) == b`. To negate
a comparison, write `not (a == b)` or, better, `a != b`.

Any combination of types that does not appear in the table is the error `E2011`. In particular:

- `Int` and `Float` do not mix, not even when comparing: `1 + 1.5` and `1 == 1.0` are errors.
- `Bool` values allow neither arithmetic nor ordering: `true + 1` and `true < false` are errors.
- `Text` values only allow `+`, `==`, `!=` and ordering (`<`, `<=`, `>`, `>=`) between two `Text`:
  `"a" * 2` and `"1" < 2` are errors.
- `and`, `or` and `not` only accept `Bool`: `1 and 2` and `not 0` are errors.

### 6.2 Semantics

- **Order of evaluation:** in a binary operation the left operand is evaluated first and
  then the right one. The arguments of a call are evaluated from left to right.
- **Short circuit:** `a and b` does not evaluate `b` if `a` is `false`; `a or b` does not evaluate `b` if `a` is
  `true`.
- **Equality:** two `Text` values are equal if they have exactly the same characters (case is
  significant). Two `Float` values are compared by their IEEE 754 value.
- **Ordering between texts:** character by character, by Unicode code point. At the first position
  where they differ, the character with the lower code point comes first; if one is the beginning of the
  other, the shorter one comes first. It does not depend on the language or on the system configuration, and it is not the
  alphabetical order of any language: `"Z" < "a"`, `"z" < "é"` and `"10" < "9"` are true. Nothing
  is normalized: an `é` written as a single character is different from an `e` followed by the combining
  accent (section 8.1).
- **Integer division:** `/` between two `Int` returns an `Int` and drops the decimal part
  (rounds towards zero): `7 / 2` is `3` and `-7 / 2` is `-3`. To get decimals, divide two
  `Float` values: `7.0 / 2.0` is `3.5`.
- **Division by zero:** dividing by `0` or by `0.0` is the runtime error `E3001`.
- **Overflow:** an `Int` result out of range is `E3002`; a `Float` result that does not
  fit is `E3003`.

### 6.3 Conditions

A condition (that of an `if` or that of a contract) has to be of type `Bool`. A number or a
text is not a condition (`E2011`):

```nex
if count > 0 { ... }          // correct
if count { ... }              // E2011: the condition must be Bool, it is Int
```

### 6.4 Expressions as statements

An expression used as a statement has to be a call to a function without `gives`. Anything else
is the error `E2010`, because its value would be lost: a loose operation (`40 + 2`) or a
call whose result is not used (`add(1, 2)`).

## 7. Functions

### 7.1 Declaration

```nex
fn add(a: Int, b: Int) gives Int {
    return a + b
}
```

- Every parameter declares its type, which has to be a value type.
- The result type is written after `gives`. A function without `gives` returns nothing: a call to it
  is of type `Void`, and it can only be a statement. `Void` itself is never written (`gives Void`
  is `E2012`).
- Between the signature and the body, a function can declare its contracts (`needs`, `promises`,
  `trust`) and its examples (`example`): the header of section 3, whose meaning is in section 9.
- Functions are declared at the top level of the file, in any order. They cannot
  be declared inside another function.
- There is no overloading: two functions with the same name are the error `E2002`. A function
  cannot be declared with the name of a built-in one either (`E2002`).
- Two parameters with the same name are the error `E2006`. A parameter cannot be named `result`
  (`E2013`).
- There are no default values, named arguments, generics, classes or anonymous functions.

### 7.2 The main function

<!-- nex:valid -->
```nex
fn main() {
    print("Hello from NEXORA")
}
```

Every program declares a `main` function, with no parameters and without `gives`. It is the entry
point. If it is missing, the error is `E2001`; with parameters, `E2013`; with a `gives`, `E2004`.

### 7.3 `return` and return paths

- In a function that returns a value, `return expression` ends the function with that value. The
  type of the expression has to be the declared return type (`E2011` otherwise).
- In a function without `gives`, `return` without a value ends the function before reaching the end.
  `return expression` is the error `E2011`. Reaching the end of the body also ends the function.
- A `return` without a value in a function that returns a value is the error `E2011`.
- **Every path returns.** A function that returns a value has to end with `return` on
  every possible path; if any of them can reach the end of the body, the error is `E2014`.
- A statement placed after a `return` in the same block can never run and is the
  error `E2015`.

How it is decided whether a block "always returns":

| Statement | Always returns if… |
|-----------|--------------------|
| `return` | Always |
| `if` without `else` | Never (the condition may be false) |
| `if` … `else` … | All its branches always return |
| Block `{ }` | One of its statements always returns |
| `while` | Never (its condition may be false from the start) |
| `for` | Never (the list may be empty) |
| Any other | Never |

The analysis does not evaluate conditions: `if true { return 1 }` without `else` is considered incomplete, and
a function whose only `return` is inside a loop needs another one after the loop.

```nex
fn sign(n: Int) gives Int {          // correct: the three branches return
    if n < 0 {
        return -1
    } else if n == 0 {
        return 0
    } else {
        return 1
    }
}

fn broken(n: Int) gives Int {        // E2014: if n <= 0 the end is reached without 'return'
    if n > 0 {
        return 1
    }
}
```

### 7.4 Calls

```nex
let result: Int = add(2, 3)
```

A call is checked without running the program:

| Check | Error |
|-------|-------|
| The function exists | `E2008` |
| The number of arguments matches the number of parameters | `E2009` |
| The type of every argument is that of the corresponding parameter | `E2011` |
| No argument is a call to a function without `gives` | `E2011` |

The type of a call is the return type of the function.

When it runs, a call:

1. Evaluates the arguments, from left to right.
2. Creates a new scope and assigns each argument to its parameter, by position.
3. Checks the `needs` clauses, in order (section 9).
4. Runs the body until a `return` or until the end.
5. Checks the `promises` clauses, in order. A `trust` clause is never evaluated.
6. Returns the value to the point of the call.

Arguments are passed by value and all values are immutable, so a function cannot
modify anything of its caller.

### 7.5 Recursion

A function can call itself, and two functions can call each other.

The number of nested calls is limited to 1000 (counting `main`). Exceeding it is the runtime
error `E3004`; the usual case is a recursion that never reaches its base case. With
very deeply nested expressions the effective limit can be lower; the error is the same.
To repeat something many times, use a loop (section 9.5): its iterations are not calls and do not
count towards this limit.

### 7.6 Modules and imports

A `.nex` file is a module (decision 0018). The program that runs is the file that is
passed to `nex run` (the **entry file**), and the other files it imports are part of the
same program: they are analyzed and run with it.

**Declaring a module.** The first line of a file can be an import, and before
any other declaration:

```nexora
import "app/models.nex"
```

- The path is a text literal and has to end in `.nex`; otherwise, it is the error `E1101`.
- The path is **relative to the file that contains it**, not to the folder from which the
  command is run: the program depends on where it is, not on where it is started from.
- Imports go before any other declaration, one per line. Anywhere else, or
  after a function, they are the error `E1101`.
- A file is read only once, even if several files import it. Circular imports are the
  error `E2029`; two files with the same name in different folders are the error `E2030`,
  because the module takes its name from its file. A file that does not exist or cannot be read is the
  error `E0001`, on the line of the `import`.

**The name of a module.** It is the name of its file without the extension: `app/models.nex` is the
module `models`. There are no aliases (`as`) and no selective imports: the whole file is imported and
its names are used qualified with the module in front.

**What a module makes visible.** Everything a module declares is **private**, except what
carries `pub`: `pub fn`, `pub type` (both refined types and records). The entry
file is the exception: its functions and its types are its own and do not carry `pub`. Using from another
file a name that its module does not make public is the error `E2028`.

**How the names of another module are used.** Qualified, with the module in front:

```nexora
import "app/models.nex"

fn main() {
    let p: models.Point = models.Point(x: 3, y: 4)
    print(models.area(p))
}
```

| Written as | Meaning | Error if it does not exist |
|------------|---------|----------------------------|
| `models.area(p)` | Calls the function `area` that the module `models` makes public | `E2008`, or `E2028` if it is private |
| `models.Point` | The type `Point` of the module `models`, in an annotation or as an argument | `E2012` |
| `models.Point(x: 1, y: 2)` | Builds a value of the record `Point` of the module `models` | `E2023`, or `E2028` if it is private |
| `models` before the `.` without being an imported module | — | `E2027` |

The dot is attached to both names, as in a call or when reading a field: `models.Point`
is correct and `models . Point` is the error `E1101`.

Inside a module its functions are called by their simple name: a function of `models` writes
`area(p)`, not `models.area(p)`. The names of two different modules do not get mixed up because each
one declares its own with its own module in front, and a record keeps its own identity
even if two modules declare a `Point` (section 4.6).

**When modules are read.** When the program is analyzed, not when it runs: modules
are part of the program (section 10.1). A module is always analyzed after the ones it imports, so
that the names it uses already exist when its body is checked.

**What the analysis and the tools do with modules.** `nex check`, `nex run` and `nex test`
analyze the entry file and all the ones it imports, and every error is shown with the file that
has it. `nex test` only evaluates the examples of the entry file: those of a module are not
run. `nex inspect` describes the entry file, where the names that come from a module appear as
qualified. `nex symbols` and `nex context` also list the names and functions of the imported
modules, each with the file that declares it, and `nex check --evidence` lists the clauses of every
file of the program (section 9.3).

**What this version does not support.**

- Aliases (`import "app/models.nex" as m`) or selective imports
  (`import { area } from ...`).
- Importing from outside the folder tree of the program: there is no search path, no packages and no
  versions. Two modules from two different projects cannot be combined.
- Re-exporting: a module cannot make public the names of another one.
- Importing from the playground, from the MCP server or from an editor without files: those
  environments receive the program as text and have no files next to it, so an `import` is the
  error `E0001`.
- Capabilities (`uses`, section 8.3) are not inherited: every file declares its own, and a
  module that reads a file has to declare it itself.

## 8. Built-in functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `print` | `print(value)` | Writes the value followed by a line break to the standard output. Accepts a value of any value type |
| `to_text` | `to_text(value) gives Text` | Converts any value into the text that `print` would write |
| `to_float` | `to_float(value: Int) gives Float` | Converts an integer into a decimal |
| `to_int` | `to_int(value: Float) gives Int` | Converts a decimal into an integer by dropping the decimal part |

Text produced by `print` and `to_text`:

| Type | Format | Examples |
|------|--------|----------|
| `Text` | The text, without quotes | `Hello` |
| `Int` | In decimal | `42`, `-7` |
| `Bool` | `true` or `false` | |
| `Float` | The shortest decimal representation that identifies the value; it always has a decimal point or an exponent | `3.5`, `2.0`, `0.30000000000000004`, `1e+16` |
| `List[T]` | Square brackets, elements separated by `, `, no quotes around texts | `[1, 2, 3]`, `[[1], [2]]`, `[]` |

`print` writes to the standard output. The other effects a program can have are those of
section 8.3: reading its arguments and the standard input, and the files it declares and is allowed
to use. A NEXORA program cannot open connections or run other programs.

### 8.1 Functions of a type: `Text.length`, `Int.parse`…

Some built-in functions belong to a type and are called with its name in front
([decision 0011](decisions/0011-operaciones-sobre-textos.md)):

| Function | What it does | Requirements |
|----------|--------------|--------------|
| `Text.length(text: Text) gives Int` | Number of characters | |
| `Text.slice(text: Text, start: Int, end: Int) gives Text` | The characters from `start` (included) to `end` (excluded) | `start >= 0`, `start <= end`, `end <= Text.length(text)` |
| `Text.contains(text: Text, part: Text) gives Bool` | Whether `part` appears in `text` | |
| `Text.starts_with(text: Text, part: Text) gives Bool` | Whether `text` starts with `part` | |
| `Text.ends_with(text: Text, part: Text) gives Bool` | Whether `text` ends with `part` | |
| `Int.can_parse(text: Text) gives Bool` | Whether `text` is an integer written according to the grammar below, within the range of `Int` | |
| `Int.parse(text: Text) gives Int` | The integer written in `text` | `Int.can_parse(text)` |
| `Float.can_parse(text: Text) gives Bool` | Whether `text` is a decimal written according to the grammar below, whose rounded value is finite | |
| `Float.parse(text: Text) gives Float` | The decimal written in `text`, rounded to the nearest `Float` | `Float.can_parse(text)` |

- **A character is a Unicode code point** and positions start at 0. `Text.length("año")`
  is 3. Nothing is normalized: an `e` followed by the combining accent is two characters.
- **Names.** No name is reserved: `let length = Text.length(name)` is valid, and `Int`,
  `Float`, `Bool` and `Text` can still be used as variable names. Only a type with that function can go
  in front of the dot; anything else is `E2008`, with a suggestion (`length(t)`
  suggests `Text.length`). A program cannot declare functions of a type.
- **Requirements.** Before the operation its requirements are checked, in the order of the table. The
  first one that is not met stops the program with `E4001`, like the `needs` of a function of the
  program. There are no negative indices and no silent truncation: `Text.slice("abc", 2, 9)` does not return
  `"c"`. `Int.parse` and `Float.parse` add a suggestion depending on what failed.
- **Numbers written in a text.** A single form, with ASCII characters only:

  ```text
  integer   = [ "-" ] digit { digit }
  decimal   = [ "-" ] digit { digit } ( fraction [ exponent ] | exponent )
  fraction  = "." digit { digit }
  exponent  = ( "e" | "E" ) [ "+" | "-" ] digit { digit }
  ```

  No spaces, no leading `+`, no `_` or separators, no `inf` or `nan`. Leading zeros are
  allowed (`"007"` is 7). `Float.can_parse("1")` is false: an integer is not a decimal; it is read with
  `to_float(Int.parse("1"))`. A value that is too small is rounded to zero (`"1e-400"` is `0.0`);
  one that would round to infinity is not accepted (`"1e309"`). What `to_text` writes can always
  be read back: `Int.parse(to_text(n)) == n` and `Float.parse(to_text(x)) == x`.

<!-- nex:run -->
```nex
fn main() {
    let name = "Ada Lovelace"
    let length = Text.length(name)
    print(length)
    print(Text.slice(name, 0, 3))
    print(Text.contains(name, "Love") and Text.ends_with(name, "lace"))
    print("Ada" < "ada")
    if Int.can_parse("042") {
        print(Int.parse("042") + 1)
    }
}
```

```text
12
Ada
true
true
43
```

A requirement that is not met stops the program with its explanation and the values of the call:

<!-- nex:fails exit=5 -->
```nex
fn main() {
    print(Int.parse("12a"))
}
```

```text
contract error[E4001]: Precondition violated
 --> program.nex:2:11
  |
2 |     print(Int.parse("12a"))
  |           ^^^^^^^^^^^^^^^^ This call breaks a 'needs' condition of 'Int.parse'
  = note: The condition of the built-in function is false: needs Int.can_parse(text)
  = note: Reason: Only a whole number within the range of Int can be read as an Int
  = note: It was called with: text = "12a"
  = hint: Check the text first with Int.can_parse(...), and call Int.parse only when it is true.

error: program.nex: the program stopped because a contract was broken
```

### 8.2 `List` functions

Lists have five built-in functions. They are functions of a type, like those of section
8.1, and are called with `List.` in front. Their signature uses a type variable `T` that is not written in the
program: each call binds it to the type of its arguments. They are not user generics and a
function like that cannot be declared.

| Function | Signature | What it does | Requirements |
|----------|-----------|--------------|--------------|
| `List.length` | `List.length(xs: List[T]) gives Int` | Number of elements | |
| `List.get` | `List.get(xs: List[T], i: Int) gives T` | Element at position `i`, starting at 0 | `0 <= i and i < List.length(xs)` |
| `List.append` | `List.append(xs: List[T], x: T) gives List[T]` | New list with `x` at the end | |
| `List.concat` | `List.concat(xs: List[T], ys: List[T]) gives List[T]` | New list with the elements of `xs` and then those of `ys` | |
| `List.contains` | `List.contains(xs: List[T], x: T) gives Bool` | Whether some element is structurally equal to `x` | |

- **`List.length`** is total. `List.length([])` does not compile if the empty list has no expected
  type (`E2011`); `let xs: List[Int] = []` and `List.length(xs)` do.
- **`List.get`** is partial. The index starts at 0 and has to be inside the list. A
  negative index, or one equal to or greater than the length, stops the program with `E4001`, also if it is a constant:
  `nex check` does not prove the contract. There are no negative indices counting from the end and no silent
  truncation. The check carries the explanation "An index must be inside the list".
- **`List.append` and `List.concat`** do not modify their arguments: they build a new list. The type
  of the result keeps the element of the input lists. A literal empty list as an
  argument needs an expected type, because the parametric signature does not set it before reading the
  arguments: `List.append([], 1)` and `List.concat([1], [])` are `E2011`.
- **`List.contains`** uses structural equality, not a search for substrings: `List.contains(["ab"], "b")`
  is `false`. The list and the value have to have the same element type; an `Int` is not searched for
  in a `List[Text]`.
- The arguments are checked as in any call: number (`E2009`), type (`E2011`) and, where
  applicable, the contract when running (`E4001`). An unknown `List` function is `E2008`, with a
  suggestion if it resembles one of the five.

<!-- nex:run -->
```nex
fn main() {
    let xs = [10, 20, 30]
    print(List.length(xs))
    print(List.get(xs, 1))
    print(List.append(xs, 40))
    print(List.concat(xs, [40, 50]))
    print(List.contains(xs, 20))
    print(List.contains(xs, 25))
}
```

```text
3
20
[10, 20, 30, 40]
[10, 20, 30, 40, 50]
true
false
```

Apart from these five functions there is no `map`, `filter`, `fold`, sorting, `slice` or total variant
of `List.get`. They will come, if they are decided, with `Option`/`Result` and the other pending
decisions.

### 8.3 Input, arguments and host capabilities

A program can receive data from outside: the arguments it was run with, the standard
input, files, HTTPS responses and output from an external process. Arguments and standard input
are allowed by default. Files, network requests and process execution are **not**: each operation
has to be declared and granted by the user, and the host must enable it.

| Function | Signature | What it does |
|----------|-----------|--------------|
| `args` | `args() gives List[Text]` | The arguments the program was run with, in order |
| `input` | `input() gives Text` | Reads **one line** from the standard input, without the line ending |
| `read_file` | `read_file(path: Text) gives Text` | Reads a whole text file |
| `write_file` | `write_file(path: Text, text: Text)` | Writes a text file, and creates it if it does not exist |
| `Net.get` | `Net.get(url: Text) gives Text` | Reads a bounded UTF-8 response from an HTTPS GET request |
| `Process.run` | `Process.run(command: Text, arguments: List[Text]) gives Text` | Runs one executable directly and returns its standard output |

**Arguments.** `nex run program.nex -- one two` gives the program the arguments `one` and `two`.
`args()` returns a `List[Text]`, empty if there are none. Arguments need no
declaration: they give access to nothing that whoever runs the program has not already given.

**Standard input.** `input()` reads a line and returns it without the line ending. An empty
line returns the empty text. When there is nothing left to read, the program stops with
`E3009`: it is not possible to read "until the end" without stopping, and there is no way to tell the end from an
empty line.

**Files, network and processes.** A program declares what it needs with `uses`, at the top level of the file:

```nexora
uses read "data/inputs.txt"
uses write "data/output.txt"
uses network "https://api.example.com"
uses process "python"
```

The effective capability is the **intersection** of three things:

1. **What the program declares**: `uses read` or `uses write` for a path, `uses network` for an HTTPS
   origin, or `uses process` for an executable.
2. **What whoever runs it grants**: the matching `--allow-read`, `--allow-write`, `--allow-network`
   or `--allow-process` option in `nex run`; each option can be repeated.
3. **What the environment allows**: whether the host permits that operation.

All three have to be there. Declaring does not grant; granting does not enable an undeclared target;
and a restricted environment has the last word. A missing declaration is `E2026`; a missing user
grant or a host that denies the operation is `E3008`.

`nex check` reports a missing declaration when a literal path, URL or executable is not covered: it
is `E2026`. This is a help, not the security. If the value is computed, the analysis cannot know it
and does not report the missing declaration; the host makes the decision on every operation.

**Paths.** Relative paths are resolved against the **working directory** of the process.
Confinement is applied to the **resolved** path: a `..` that leaves the granted scope and a
symbolic link that points outside it are of no use. The comparison is by segments, so
that `data2` is not inside `data`. On Windows, a path with backslashes has to be
written with doubled backslashes (`"C:\\data"`) or with forward slashes (`"C:/data"`), which
work on both systems.

**Network.** `Net.get` only makes HTTPS GET requests to the exact declared and granted origin, on
port 443. It does not follow redirects or use configured proxies. Each request has a five-second
timeout and reads at most one MiB. The response has to be UTF-8 text. A network or process failure
stops the program with `E3014`.

**Processes.** `Process.run` starts the declared and granted executable directly, without a shell,
with the given list of text arguments and no standard input. It returns standard output only for exit
status zero; otherwise the diagnostic includes the exit status and standard error. It runs for at
most five seconds, limits standard output and standard error to one MiB each and receives a small
environment. The executable still runs with the local user's operating-system permissions. On
Windows, if it starts child processes, a timeout only guarantees that the direct process is stopped;
those children may remain running.

**Restricted environments.** The web Playground worker uses `NoHost`, and the worker protocol has
no fields to grant files, network origins or processes. It rejects these operations with `E3008`,
even when a program declares them. The production Docker worker also has no network interface. The
MCP server only analyzes: it never runs a program.

### 8.4 The functions of `Option` and `Result`

The two variants of each type (section 4.7) are built with `Some`, `None`, `Ok` and `Err`, and they are
recognized and read with these functions:

| Function | Signature | What it does |
|----------|-----------|--------------|
| `Some` | `Some(value: T) gives Option[T]` | The variant of `Option` that has a value |
| `None` | `None`: `Option[T]` | The variant of `Option` without a value; `T` is given by the context |
| `Ok` | `Ok(value: T) gives Result[T, E]` | The variant of `Result` that succeeded |
| `Err` | `Err(error: E) gives Result[T, E]` | The variant of `Result` that failed; `T` is given by the context |
| `Option.is_some` | `Option.is_some(x: Option[T]) gives Bool` | Whether `x` has a value |
| `Option.is_none` | `Option.is_none(x: Option[T]) gives Bool` | Whether `x` has no value |
| `Option.value_or` | `Option.value_or(x: Option[T], fallback: T) gives T` | The value of `x`, or `fallback` if it has none |
| `Option.value` | `Option.value(x: Option[T]) gives T` | The value of `x`; if it has none, `E3011` |
| `Result.is_ok` | `Result.is_ok(x: Result[T, E]) gives Bool` | Whether `x` succeeded |
| `Result.is_err` | `Result.is_err(x: Result[T, E]) gives Bool` | Whether `x` failed |
| `Result.value_or` | `Result.value_or(x: Result[T, E], fallback: T) gives T` | The value of `x`, or `fallback` if it failed |
| `Result.value` | `Result.value(x: Result[T, E]) gives T` | The value of `x`; if it failed, `E3012` |
| `Result.error` | `Result.error(x: Result[T, E]) gives E` | The error of `x`; if it succeeded, `E3013` |

`Option.value`, `Result.value` and `Result.error` **read the value without a fallback**: if the variant does not carry it, the program stops with
a diagnostic that says which variant it had (`E3011`, `E3012`, `E3013`). None of them returns a
made-up value.

The type of `T` and of `E` is set by the **context**: the annotation of a variable, the type of a
parameter, the result type of a function or the other side of a comparison. Without that context,
`None`, `Ok` and `Err` do not have a complete type, and it is the error `E2011`.

## 9. Contracts

A contract expresses a condition that a function **expects** from its caller or a condition that it
**promises** to meet. Contracts are deterministic and are evaluated with the same rules as
any other expression; no AI model is involved.

```nex
fn divide(a: Float, b: Float) gives Float
    needs b != 0.0
{
    return a / b
}

fn absolute(value: Int) gives Int
    promises result >= 0
{
    if value < 0 {
        return -value
    }
    return value
}
```

### 9.1 Rules

- The clauses go in the header of the function: between its signature and the `{` of its body, one
  per line (section 3). There can be several of each kind, in any order, and mixed with the
  `example` clauses (section 9.4).
- The condition of a clause has to be of type `Bool` (`E2011`).
- **`needs`** is a precondition. The parameters of the function are visible in it, and
  no other name: neither the variables of the body nor `result`.
- **`promises`** is a postcondition. The parameters are visible in it and, if the function
  has `gives`, `result`, which is **the value returned by the function** and has its result
  type. In a function without `gives`, `result` does not exist (`E2005`).
- **`trust`** states a condition the function relies on and the language **does not check**. The
  parameters are visible in it, as in `needs`, and no other name. Its condition is checked for
  being a well-written `Bool` and is **never evaluated**: not when the program runs, not by
  `nex check`, not by `nex test`. It cannot fail and cannot stop the program, and removing every
  `trust` clause from a program does not change what it does. Its explanation is required
  (`E1101` without it): it is the only thing behind the condition.
- Parameters are immutable, so in `promises` they have the same value as on entry.
- `result` is a contextual name: it only means "the returned value" inside `promises`. In the
  body of a function it is a variable name like any other. A parameter cannot be
  named `result` (`E2013`).
- A condition can call functions.
- After the condition there may be, after a comma, **the explanation of the rule**: a text that says
  why it exists. It does not change what is checked; it appears in the diagnostic when the condition is
  false, as `Reason: ...`.
- **A clause can have a name**, written before its condition: `needs positive: n > 0`. The name is
  unique within the function and its loops, and different from the parameters and from `result`
  (`E2031`); it is not a variable. A diagnostic of a named clause names it:
  `This call breaks needs 'positive' of 'f'`. The rules of the names are in section 3.

<!-- nex:fails exit=5 -->
```nex
fn withdraw(balance: Int, amount: Int) gives Int
    needs amount > 0, "A withdrawal moves some money"
    needs amount <= balance, "An account cannot go below zero"
    promises result == balance - amount
{
    return balance - amount
}

fn main() {
    print(withdraw(100, 30))
    print(withdraw(100, 300))
}
```

```text
70
contract error[E4001]: Precondition violated
  --> program.nex:11:11
   |
11 |     print(withdraw(100, 300))
   |           ^^^^^^^^^^^^^^^^^^ This call breaks a 'needs' condition of 'withdraw'
   = note: The condition at line 3 is false: needs amount <= balance
   = note: Reason: An account cannot go below zero
   = note: It was called with: balance = 100, amount = 300

error: program.nex: the program stopped because a contract was broken
```

### 9.2 What is checked and when

| Moment | What is checked |
|--------|-----------------|
| Without running (`nex check`) | That every condition is well formed: visible names, correct types, `Bool` result, and the names of the clauses |
| When running, on every call | `needs`: after assigning the arguments and **before** running the body, in order |
| When running, on every call | `promises`: **after** computing the return value, before handing it to the caller, in order |
| Never | `trust`: its condition is not evaluated |

If the condition of a `needs` or a `promises` is false, the program stops with a contract diagnostic:

- **`E4001` Precondition violated.** The position pointed at is **the call**: the caller did not meet
  what the function needs. The diagnostic shows the broken clause and the values of the
  arguments. The body of the function never runs.
- **`E4002` Postcondition violated.** The position pointed at is **the `promises` clause**: the function
  did not meet what it promises. The diagnostic shows the returned value and the arguments.

<!-- nex:fails exit=5 -->
```nex
fn divide(a: Float, b: Float) gives Float
    needs b != 0.0
{
    return a / b
}

fn main() {
    print(divide(1.0, 0.0))
}
```

```text
contract error[E4001]: Precondition violated
 --> program.nex:8:11
  |
8 |     print(divide(1.0, 0.0))
  |           ^^^^^^^^^^^^^^^^ This call breaks a 'needs' condition of 'divide'
  = note: The condition at line 2 is false: needs b != 0.0
  = note: It was called with: a = 1.0, b = 0.0

error: program.nex: the program stopped because a contract was broken
```

If evaluating the condition itself produces a runtime error (for example, a division by
zero inside the condition), the error reported is that one (`E3xxx`), not a contract
violation.

### 9.3 Guarantees it does **not** give

- **There is no static verification of contracts.** `nex check` checks the types of the
  conditions, not that they hold. A program that passes `nex check` can break a contract when
  it runs. `nex check` never claims that a contract holds.
- A contract is only checked **on the calls that actually run**. A contract that
  no run has broken is not proven.
- It is not checked that conditions are "pure": a condition can call a function that
  uses `print`.
- `needs` and `promises` cannot be turned off: they are always checked.
- **A `trust` is neither proved nor checked.** The language does not evaluate it when running, does
  not decide it before running and does not observe it in examples. A tool, a report or a document
  must never present a `trust` clause as verified.

**What backs each clause.** `nex check --evidence` reports, for every `needs`, `promises`, `trust`,
`keeps` and `shrinks` of the program, whether the language evaluates it when the program runs:
`checked` for all of them except `trust`, which is `trusted`. It runs nothing, and `checked` does not
say that a condition holds, only that a false one stops the program. The format is
`nexora.evidence/1` ([JSON protocol](json-protocol.md#evidence)); deciding a `needs` at its call sites
and observing the clauses in the examples are later phases of
[decision 0019](decisions/0019-identidad-propia-del-lenguaje.md) (section 5) and do not exist in this
version.

The syntax of contracts was stable from version 0.3
([decision 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)) to 0.11, with the
clauses at the beginning of the body. Version 0.12 moves them to the header and renames them
([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)): `needs` keeps the rules of
`requires`, `promises` those of `ensures`, and `trust` is new. The returned value is still called
`result` and the explanation still goes after a comma.

### 9.4 Examples (`example`)

An example is one more clause of the header, next to `needs` and `promises`: it says what
concrete result the function gives with some concrete inputs. The complete definition (statuses,
report format, exit codes) is in [decision 0008](decisions/0008-ejemplos-y-nex-test.md); its place
in the header, in [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md).

<!-- nex:valid -->
```nex
fn double(n: Int) gives Int
    needs n >= 0, "Only natural numbers"
    example double(2) == 4, "Two doubled"
{
    return n * 2
}

fn main() {
    print(double(2))
}
```

- The expression is of type `Bool` (`E2011`) and can carry its explanation after a comma. An
  example has no name (`E1101`).
- Its place among the other clauses of the header has no effect: examples are never evaluated by a
  call, only by `nex test`, in the order in which they are written.
- **It has to contain a call of its own**: a call to its function written in the expression itself
  (`double(2)`, also nested, as in `double(double(1))`). Without it, `E2020`. A call that
  only happens inside another function does not count.
- It does not see the parameters or `result` (`E2005`): its inputs and the expected result are written as
  values. It can use any function of the program, the built-in ones and `Type(x)` checks.
- **The analysis never evaluates an example.** `nex check`, `nex inspect`, `nex context` and `nex symbols`
  check that it is well written and nothing more; the calls of an example are not part of the call
  graph of the function. `nex run` ignores them.
- **Only `nex test` evaluates them**, each one in a fresh interpreter, checking the contracts of all
  the functions that run. An example ends as `passed` (it is `true`), `failed` (it is
  `false`: `E4004`, category `test`) or `error` (a runtime error or a broken rule, which
  keeps its code and gains a note with the example that caused it).

### 9.5 Loops: `while`, `keeps` and `shrinks`

A loop repeats its body while its condition is `true`. Like a function, it declares in its header,
between its head and its `{`, the requirements that make it correct, and the interpreter checks them on
every iteration ([decision 0010](decisions/0010-var-y-while.md); their place and their words since
0.12, [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)):

<!-- nex:run -->
```nex
fn sum_to(n: Int) gives Int
    needs n >= 0, "Only natural numbers"
    promises result == n * (n + 1) / 2
{
    var total = 0
    var i = 0
    while i < n
        keeps total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        shrinks n - i, "Each turn moves i one step closer to n"
    {
        i = i + 1
        total = total + i
    }
    return total
}

fn main() {
    print(sum_to(10000))
}
```

```text
50005000
```

| Clause | How many | What it declares | Type |
|--------|----------|------------------|------|
| `shrinks` | **Exactly one** | The **measure**: an integer that never goes below 0 and decreases on every iteration. It is the reason why the loop ends | `Int` |
| `keeps` | Zero or more | An **invariant**: a condition that holds before every evaluation of the loop condition: on arrival, after every iteration and, therefore, on exit | `Bool` |

Rules:

- **Every `while` declares its measure.** Without `shrinks`, or with more than one, it is the error `E2021`.
- The condition of the loop is `Bool` (`E2011`), and the measure, `Int` (`E2011`).
- The clauses see what is visible where the loop is (parameters, `let`, `var`), not what
  its body declares. They carry an optional explanation after a comma and an optional name, like
  contracts; a name is unique within the function, its header included (`E2031`).
- Every iteration opens a new scope: what is declared in the body exists only during that iteration. What
  has to survive between iterations is declared with `var` before the loop.
- A `return` inside the body ends the function.
- Iterations are not calls: the loop does not add a call and does not use up the limit of 1000, although
  the calls inside the body do count.
- There is no `break` or `continue` (they remain reserved).

Every time a loop runs:

1. The `keeps` clauses are checked, in order. A false one stops the program: **`E4005`**.
2. The condition is evaluated. If it is `false`, the loop ends.
3. The measure is evaluated. If it is negative, or it is not strictly smaller than in the previous iteration of that
   same run of the loop, the program stops: **`E4006`**.
4. The body runs and the loop goes back to step 1.

So **every loop ends, or stops with a diagnostic that says why it would not**: an integer measure
that does not go below 0 cannot decrease forever. There are no time limits: the same program
always gives the same result. The diagnostic says in which iteration it happened and with which values:

<!-- nex:fails exit=5 -->
```nex
fn count_even(limit: Int) gives Int {
    var i = 0
    var even = 0
    while i < limit
        shrinks limit - i, "Each turn moves i one step closer to limit"
    {
        if i / 2 * 2 == i {
            even = even + 1
            i = i + 1
        }
    }
    return even
}

fn main() {
    print(count_even(10))
}
```

```text
contract error[E4006]: Loop measure did not decrease
 --> program.nex:5:17
  |
5 |         shrinks limit - i, "Each turn moves i one step closer to limit"
  |                 ^^^^^^^^^ The measure was 9 and is still 9
  = note: The measure at line 5: shrinks limit - i
  = note: Reason: Each turn moves i one step closer to limit
  = note: Before turn 3 of the loop at line 4.
  = note: The values: limit = 10, i = 1, even = 1
  = note: In 'count_even', called at line 16, column 11.

error: program.nex: the program stopped because a contract was broken
```

Any other error that happens inside a loop (`E3xxx`, `E4xxx`) gains a note for every
loop that contains it, from the innermost to the outermost: `In turn 3 of the loop at line 6.`

**What it does not guarantee.** That a loop ends soon: an initial measure of a billion allows a billion
iterations. That the measure and the invariants are the right ones: what is written is checked, on
the iterations that run. None of this is proven without running.

### 9.6 `for` loops over lists

A `for` goes through an immutable list and declares the name that each element takes. The
implemented part is accepted by [decision 0013](decisions/0013-listas-y-for.md);
[0012](decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) is still the
proposal for the rest:

<!-- nex:run -->
```nex
fn total(xs: List[Int]) gives Int {
    var sum = 0
    for x in xs
        keeps sum >= 0, "The total is never negative"
    {
        sum = sum + x
    }
    return sum
}

fn main() {
    print(total([1, 2, 3, 4]))
}
```

```text
10
```

The list is written with square brackets and its type gives the type of the elements: `[1, 2, 3]` is
`List[Int]`. A list does not change: `List.append(xs, x)` and `List.concat(xs, ys)` build a new
list. The syntax and the literals are in section 4.5, and the functions in 8.2.

Rules:

- **The iterable is evaluated once**, before the first check of the invariants and before any
  iteration, and it must be `List[T]` (`E2011`). A `Text` or an `Int` cannot be iterated, and there is no `for` over
  ranges. A literal empty list as the iterable (`for x in []`) has no expected type and is `E2011`;
  to go through an empty list, use an annotated variable:
  `let xs: List[Int] = []` and `for x in xs`.
- **The iterator is immutable and of type `T`.** It is declared in the `for` itself, not before, and it cannot
  receive a new value (`E2007`). It cannot shadow a visible name either (`E2006`). It is not visible
  after the loop. Every iteration opens a new environment: what the body declares exists only during
  that iteration, and assignments to an outer `var` are kept.
- **It has no `shrinks`.** The list is finite by construction; a `shrinks` in a `for` is the
  error `E2022`. A `for` can declare zero or more `keeps` clauses, with the same semantics as in a
  `while`: they are checked before every iteration and once after the last one. On an empty list they are
  checked once, before the first iteration, which never runs; there is no separate additional
  check. An invariant must be `Bool` (`E2011`) and, if it is false, the program stops
  with `E4005`.
- The clauses see what is visible where the `for` is, never the iterator.
- A `return` inside the body ends the function. The path analysis does not consider that a `for`
  always returns, even if all its iterations contain a `return`: if the loop is the last
  statement, the function needs a `return` after it.
- There is no `break` or `continue`: they remain reserved (`E1103`).
- Iterations are not calls: the loop does not add a call and does not use up the limit of 1000, although
  the calls inside the body do count.

**What it does not guarantee.** That the body ends soon: a huge list takes as long as it takes. The
playground imposes a maximum time; `nex run` does not. That the invariants are the right ones: they are
checked on the iterations that run, they are not proven.

## 10. Errors: before running and while running

### 10.1 Stages

The tool processes a program in four stages. Each one only runs if the previous one did not
find errors:

| Stage | What it does | Category of its errors |
|-------|--------------|------------------------|
| 1. Lexical analysis | Splits the text into tokens | `lexical` |
| 2. Syntax analysis | Builds the syntax tree (AST) | `syntax` |
| 3. Static analysis | Checks names, scopes, types and return paths | `semantic`, `type` |
| 4. Execution | Walks the AST | `runtime`, `contract`; with `nex test`, also `test` |

`nex check` and `nex inspect` run stages 1 to 3 and **do not run the program**: no
statement and no function runs. The only thing stage 3 evaluates is the conditions of
refined types on the constants written in the code (section 4.4). Those conditions can only
use `value`, literals, operators and built-in conversions, they do not call functions of the
program, and the total work is bounded (`E2019`). They do not evaluate examples either (section 9.4),
and no stage ever evaluates a `trust` (section 9.1). `nex check --evidence` is the same analysis.
`nex migrate` runs stages 1 to 3 twice, with the front end of 0.11 and with that of 0.12, and never
runs the program either.
`nex run` runs the four stages, and never starts a program that has any error from stages
1 to 3. `nex test` does too, but in stage 4 it evaluates the examples instead of `main`, and in stage 3
it does not require `main`.

### 10.2 What is detected before running

All of the following is reported by `nex check`, without running a single statement:

- Badly written characters, numbers, texts and escapes.
- Code that does not follow the grammar.
- A missing `main`, duplicate functions, invalid parameters or declarations.
- Names that do not exist, names declared twice, assignments to `let` variables, to
  parameters or to the iterator of a `for`.
- Calls to functions that do not exist or with a wrong number of arguments.
- **All type errors**: annotations, assignments, operators, arguments, return
  values, conditions, conditions of contracts and of loops, measures and use of `Void` as a value.
- `while` loops without a measure, or with more than one, and a `shrinks` in a `for`.
- Badly formed refined type declarations, and **every constant that does not meet the condition of the
  refined type where it is used** (`E2017`).
- Functions that can end without `return`, and unreachable code after a `return`.
- Values that are computed and never used.

### 10.3 What can only be detected when running

These properties depend on computed values and **are not checked statically**; the
static analysis claims nothing about them:

| Error | Code |
|-------|------|
| Division by zero | `E3001` |
| `Int` result out of range | `E3002` |
| `Float` result out of range | `E3003` |
| More than 1000 nested calls (endless recursion) | `E3004` |
| `to_int` of a value that does not fit in an `Int` | `E3005` |
| A `Text` longer than the limit of the environment, if it sets one | `E3006` |
| The program runs out of available memory | `E3007` |
| A false `needs` condition, also that of a function of a type (`Text.slice`, `Int.parse`, `List.get`…, section 8) | `E4001` |
| A false `promises` condition | `E4002` |
| A value checked with `Percent(x)` that does not meet the condition of its type | `E4003` |
| A false `keeps` | `E4005` |
| A measure (`shrinks`) that is negative or does not decrease | `E4006` |

The analysis does not decide whether a program ends. When it runs, an endless recursion stops with
`E3004` and an endless loop, with `E4006`.

These are the **only** errors that running a program accepted by
`nex check` can produce. When one happens, the program stops at that point: the output already written
is kept and nothing else runs.

## 11. Diagnostics

Every error has a stable code, a category, a fixed title, a concrete explanation and,
when it exists, the exact position in the file. Lines and columns start at 1; the
column counts characters (not bytes) and a tab counts as one column.

### 11.1 Text format

<!-- nex:check-fails -->
```nex
fn main() {
    let age: Int = "twenty"
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:20
  |
2 |     let age: Int = "twenty"
  |                    ^^^^^^^^ Expected Int, found Text
  = note: 'age' is declared as Int.

error: program.nex: check failed with 1 error
```

- The first line is `<category> <severity>[<code>]: <title>`, with `error` or `warning` as the
  severity.
- The concrete explanation goes next to the `^` marker, which underlines the affected fragment.
- The `= note:` lines give related information (where something was declared, the signature of a
  function, the chain of calls).
- The `= hint:` line suggests a fix. **It only appears when there is a rule that
  supports it**: a conversion that exists between those two types, a declared name very similar to the
  one written, or the correct form of a construct. If there is none, nothing is suggested.

Messages are in English. A single file can produce several diagnostics in one
pass: after a syntax error the parser continues at the next statement or function, and the
static analysis reports all the independent errors it finds. Every stage reports
at most 100 errors per file; when it reaches that number it stops, and the final summary of the
command says so.

Warnings are reported only for a file without errors: on top of an error they would describe a
program that is already rejected. They use `warning[W…]`, they are written to the standard error
like errors, and `nex check` still exits with 0 when they are the only diagnostic.

The last line that `nex check` and `nex run` write when there are errors (`error: file: …`) is
a summary of the command, not a diagnostic.

### 11.2 Categories

| Category | Meaning | Detected |
|----------|---------|----------|
| `file` | The file could not be loaded | Before analyzing |
| `lexical` | The text contains something that is not a token of the language | Without running |
| `syntax` | The tokens do not follow the grammar | Without running |
| `semantic` | Names, scopes or structure of the program | Without running |
| `type` | Types | Without running |
| `runtime` | Depends on computed values | When running |
| `contract` | A rule that the program declares was broken: `needs`, `promises`, the condition of a refined type, a `keeps` or a measure | When running |
| `test` | An example evaluated by `nex test` turned out false | When running `nex test` |

### 11.3 Diagnostic codes

A code never changes its meaning. If it stops being used it is retired, not reused. Codes that
start with `E` are errors and stop the program; codes that start with `W` are warnings and never
do.

| Code | Title | Category | When it appears |
|------|-------|----------|-----------------|
| `E0001` | Cannot read file | `file` | The file does not exist or cannot be read |
| `E0002` | File is not valid UTF-8 | `file` | The file is not encoded in UTF-8 |
| `E1001` | Unexpected character | `lexical` | A character that does not belong to the language (`;`, `'`, `!`, `@`…) |
| `E1002` | Unterminated string | `lexical` | A text without a closing quote on its line |
| `E1003` | Invalid escape sequence | `lexical` | An unknown escape, such as `\q` |
| `E1004` | Invalid number literal | `lexical` | A badly written or out-of-range number: `007`, `1_`, `12abc` |
| `E1005` | Unescaped '{' in string | `lexical` | An unescaped `{` inside a text |
| `E1101` | Unexpected token | `syntax` | The code does not follow the grammar; the message says what was expected |
| `E1102` | Unclosed block | `syntax` | A `}` is missing when the end of the file is reached |
| `E1103` | Reserved word | `syntax` | A word reserved for a future version is used |
| `E1105` | Expression too deeply nested | `syntax` | The nesting limits of section 3 are exceeded |
| `E1106` | Misplaced contract clause | `syntax` | `needs`, `promises`, `trust` or `example` inside the body of a function, or `keeps` or `shrinks` inside the body of a loop |
| `E1107` | Syntax before 0.12 | `syntax` | `requires`, `ensures`, `invariant` or `decreases`, the clause words of 0.11, where a name is declared or a statement or clause starts (decision 0019). Only in the versions 0.12.x |
| `E1108` | Arrow before the return type | `syntax` | `-> Type` after the parameters of a function (decision 0019). Only in the versions 0.12.x |
| `E2001` | Missing main function | `semantic` | The program does not declare `main` |
| `E2002` | Duplicate function | `semantic` | Two functions with the same name, or with that of a built-in one |
| `E2004` | Invalid return type | `type` | `main` has a `gives` |
| `E2005` | Unknown variable | `semantic` | A name is used that is not declared or not visible |
| `E2006` | Name already declared | `semantic` | A name is declared that is already visible, or that of a function |
| `E2007` | Cannot reassign variable | `semantic` | An attempt to give a new value to a variable declared with `let`, to a parameter or to the iterator of a `for` |
| `E2008` | Unknown function | `semantic` | A function that does not exist is called |
| `E2009` | Wrong number of arguments | `type` | A call does not pass as many arguments as there are parameters |
| `E2010` | Unused value | `semantic` | A computed value that is lost |
| `E2011` | Type mismatch | `type` | A type is not the one the corresponding rule requires |
| `E2012` | Invalid type | `type` | A name that is not a type, `List` without an argument, `Void` written as a type (also `gives Void`), or a type argument that does not exist |
| `E2013` | Invalid parameter | `semantic` | `main` with parameters, or a parameter named `result` |
| `E2014` | Missing return | `semantic` | A function that returns a value can end without `return` |
| `E2015` | Unreachable code | `semantic` | Code placed after a `return` |
| `E2016` | Invalid type declaration | `semantic` | A refined type with a lowercase name, a repeated one or one of a built-in type, an endless chain of types, or a base that is a list. Also a record with an invalid or repeated name, a repeated field, or a record that contains itself |
| `E2017` | Value outside refined type | `type` | A constant used as a value of a refined type does not meet its condition |
| `E2018` | Invalid refinement condition | `semantic` | The condition of a refined type calls a function of the program or checks another refined type |
| `E2019` | Too many refinement checks | `semantic` | Checking the constants against their refined types exceeds the work limit of the analysis (section 4.4) |
| `E2020` | Example without its function | `semantic` | An example contains no call to its function (section 9.4) |
| `E2021` | Missing loop measure | `semantic` | A `while` without `shrinks`, or with more than one (section 9.5) |
| `E2022` | Unsupported loop clause | `semantic` | A `shrinks` in a `for`, which does not accept it (section 9.6) |
| `E2023` | Invalid record construction | `type` | A construction of a record that is missing a field, has an extra one or is given the same one twice (section 4.6) |
| `E2024` | Invalid field access | `type` | A field is read from a value that is not a record, or from a record that does not have that field (section 4.6) |
| `E2025` | Cannot reassign a field | `semantic` | A field of a record, which is immutable, is assigned to (section 4.6) |
| `E2026` | Missing capability declaration | `semantic` | A file, HTTPS origin or executable is used without declaring it with `uses` (section 8.3) |
| `E2027` | Unknown module | `semantic` | The name of a module that the program does not import is used (section 7.6) |
| `E2028` | Private name | `semantic` | A name of another module is used that this module does not declare with `pub` (section 7.6) |
| `E2029` | Circular import | `semantic` | Modules import each other, so that none can be analyzed before the one it needs (section 7.6) |
| `E2030` | Module name clash | `semantic` | Two different files are imported as the same module, because they have the same name (section 7.6) |
| `E2031` | Duplicate clause name | `semantic` | A clause name used twice in a function and its loops, or equal to a parameter or to `result` (decision 0019) |
| `W2001` | Unused variable | `semantic` | A variable, parameter or iterator is declared and its value is never read. A name that only receives assignments is unused too |
| `W2002` | Variable never reassigned | `semantic` | A variable is declared with `var` and never receives a new value: `let` says what the program means |
| `W2003` | Name is not snake_case | `semantic` | A variable, parameter, iterator or private function is not written in `snake_case`. Type names keep PascalCase, and public functions and their parameters keep the spelling of their interface |
| `E3001` | Division by zero | `runtime` | Division by zero |
| `E3002` | Integer overflow | `runtime` | An `Int` result out of the 64-bit range |
| `E3003` | Float result out of range | `runtime` | A `Float` result that is too large |
| `E3004` | Too many nested calls | `runtime` | More than 1000 nested calls |
| `E3005` | Conversion out of range | `runtime` | `to_int` of a `Float` that does not fit in an `Int` |
| `E3006` | Text too long | `runtime` | A `Text` built with `+` exceeds the limit set by the environment. `nex run` sets none; the playground does |
| `E3007` | Out of memory | `runtime` | The program runs out of memory while it runs. No position ([decision 0009](decisions/0009-memoria-agotada.md)) |
| `E3008` | Permission denied | `runtime` | The program tries to use a file, network origin or process that is not declared, granted or enabled by the host (section 8.3) |
| `E3009` | No more input | `runtime` | `input()` is called when the standard input has already ended (section 8.3) |
| `E3010` | File error | `runtime` | The file could be used, but it could not be read or written: it does not exist, it is not UTF-8 text, or the operating system prevented it |
| `E3011` | Option has no value | `runtime` | `Option.value` is called with a `None`: the variant does not carry the value (section 8.4) |
| `E3012` | Result is an error | `runtime` | `Result.value` is called with an `Err`: the variant does not carry the value (section 8.4) |
| `E3013` | Result is not an error | `runtime` | `Result.error` is called with an `Ok`: the variant does not carry the error (section 8.4) |
| `E3014` | External operation failed | `runtime` | An HTTPS request or an external process failed, exceeded its limit or produced invalid text (section 8.3) |
| `E4001` | Precondition violated | `contract` | A `needs` condition is false in a call |
| `E4002` | Postcondition violated | `contract` | A `promises` condition is false when a function ends |
| `E4003` | Refinement violated | `contract` | A value checked with `Type(x)` does not meet the condition of the refined type |
| `E4005` | Loop invariant violated | `contract` | A `keeps` is false before an iteration or after the last one of its loop (sections 9.5 and 9.6) |
| `E4006` | Loop measure did not decrease | `contract` | The measure of a loop is negative or is not smaller than in the previous iteration (section 9.5) |
| `E4004` | Example failed | `test` | An example evaluated by `nex test` is `false` (section 9.4) |

Retired codes (they existed in version 0.1 and are no longer emitted):

| Retired code | Title | Reason |
|--------------|-------|--------|
| E1104 | Unsupported syntax | It warned that parameters and type annotations did not exist; now they exist |
| E2003 | Unsupported function declaration | It warned that only `main` could be declared; now user functions are allowed |

### 11.4 JSON format

`nex check file.nex --format json` writes a single JSON document to the standard output.
`nex run file.nex --format json` writes the same document to the standard error, only if the
program is invalid or fails.

For the program of section 11.1:

<!-- nex:check-json -->
```nex
fn main() {
    let age: Int = "twenty"
}
```

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.14.1",
  "file": "program.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "category": "type",
      "code": "E2011",
      "message": "Type mismatch",
      "label": "Expected Int, found Text",
      "hint": null,
      "notes": [
        "'age' is declared as Int."
      ],
      "file": "program.nex",
      "line": 2,
      "column": 20,
      "end_line": 2,
      "end_column": 28
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | text | Name and version of the format |
| `file` | text | The analyzed file, as it was passed to the command |
| `ok` | boolean | `true` if there are no errors. A warning does not make it false |
| `diagnostics` | list | The diagnostics, in the order in which they were found |
| `severity` | text | `"error"` or `"warning"` |
| `category` | text | One of the categories of section 11.2 |
| `code` | text | Stable code (section 11.3) |
| `message` | text | Fixed title of the code |
| `label` | text | Concrete explanation of this case |
| `hint` | text or `null` | Suggested fix, if there is a well-founded one |
| `notes` | list of texts | Related information |
| `line`, `column` | number or `null` | Start of the fragment pointed at |
| `end_line`, `end_column` | number or `null` | End of the fragment (end column excluded) |

The four position fields are `null` when the diagnostic does not refer to a point in the file
(for example, `E2001`). The version number of `schema` only changes if a field is removed,
renamed or changes its meaning; adding fields does not change it.

The representation of the program (`nex inspect`) is described in
[`inspect-schema.md`](inspect-schema.md).

### 11.5 Exit codes of `nex`

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | The program has lexical, syntax, semantic or type errors |
| `2` | Wrong use of the command line |
| `3` | The program failed while running |
| `4` | The file could not be read |
| `5` | While running, the program broke a rule that it declares: a contract, the condition of a refined type, an invariant or the measure of a loop |
| `6` | `nex test`: some example did not pass, or there was no example to evaluate |
| `70` | Internal error of NEXORA (a failure of the tool, not of the program). A program that runs out of memory while running does not give `70`, but the diagnostic `E3007` ([decision 0009](decisions/0009-memoria-agotada.md)) |
| `130` | Interrupted with Ctrl+C |

The commands, their options and their output formats are described in the
[CLI reference](cli-reference.md).

## 12. Examples

The programs of this section, and those of the previous sections that include a `main` function,
are run by the automated tests; the output shown is the real one.

### 12.1 Valid programs

<!-- nex:run -->
```nex
fn add(a: Int, b: Int) gives Int {
    return a + b
}

fn main() {
    let result: Int = add(2, 3)
    print(result)
}
```

```text
5
```

<!-- nex:run -->
```nex
fn factorial(n: Int) gives Int
    needs n >= 0
    promises result >= 1
{
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}

fn main() {
    let n = 10
    print("factorial: " + to_text(factorial(n)))
    print(to_float(n) / 4.0)
    print(n > 5 and not (n == 7))
}
```

```text
factorial: 3628800
2.5
true
```

In [`examples/`](../examples/README.md) there are more programs, all of them run by the tests:

| File | What it shows | `nex run` ends with |
|------|---------------|---------------------|
| `hello.nex` | The first program | `0` |
| `variables.nex` | Variables, texts, blocks and scopes | `0` |
| `arithmetic.nex` | Precedence, integer and decimal division, limits of `Int` | `0` |
| `types.nex` | Inference, annotations, comparisons, logic and conversions | `0` |
| `functions.nex` | Functions, `if`/`else`, recursion | `0` |
| `contracts.nex` | Contracts that hold | `0` |
| `loops.nex` | `var` variables and loops with their measure and their invariants | `0` |
| `lists.nex` | Immutable lists `List[T]`, their functions and a `for` with invariants | `0` |
| `invalid/syntax_error.nex` | Syntax errors (wrong on purpose) | `1` |
| `invalid/name_errors.nex` | Name and structure errors (wrong on purpose) | `1` |
| `invalid/type_errors.nex` | Type errors (wrong on purpose) | `1` |
| `failing/runtime_error.nex` | An error that only appears when running | `3` |
| `failing/contract_violation.nex` | A contract broken while running | `5` |
| `failing/loop_measure.nex` | A loop that would not end: its measure stops decreasing | `5` |

### 12.2 Invalid programs

| Code | Error | Reason |
|------|-------|--------|
| `let = "Hello"` | `E1101` | The name of the variable is missing |
| `let x = (1 + 2` | `E1101` | `)` is missing |
| `let x = 1; let y = 2` | `E1001` | `;` does not exist in the language |
| `let x = 1 < 2 < 3` | `E1101` | Comparisons do not chain |
| `break` | `E1103` | `break` is a reserved word |
| `for x in 3 { }` | `E2011` | A `for` only goes through a `List[T]` |
| `for x in xs` with the header `shrinks 1` | `E2022` | A `for` has no measure |
| `for x in xs { x = 1 }` | `E2007` | The iterator of a `for` is immutable |
| `print(total)` without declaring `total` | `E2005` | Unknown variable |
| `let x = 1` and then `let x = 2` | `E2006` | The name is already declared |
| `let x = 1` and then `x = 2` | `E2007` | A `let` variable does not change; declare it with `var` |
| `while i < n { i = i + 1 }` | `E2021` | The measure is missing: `shrinks n - i` |
| `let age: Int = "twenty"` | `E2011` | `Int` was expected and the value is `Text` |
| `let total = 10 + 2.5` | `E2011` | `Int` and `Float` do not mix |
| `let ok = true + 1` | `E2011` | A `Bool` does not allow arithmetic |
| `let same = 1 == 1.0` | `E2011` | Only values of the same type are compared |
| `let xs = []` | `E2011` | An empty list needs an expected type |
| `let xs = [1, "a"]` | `E2011` | All the elements of a list have the same type |
| `let xs: List[Int] = [1]` and `let ys: List[Text] = xs` | `E2011` | The arguments of `List` are invariant |
| `if count { }` with `count` of type `Int` | `E2011` | The condition must be `Bool` |
| `let x: String = "a"` | `E2012` | The type is called `Text` |
| `let xs: List = []` | `E2012` | `List` needs a type argument |
| `type NonEmpty = List[Int] where value == value` | `E2016` | A refined type cannot have a list as its base |
| `print(read_file("data.txt"))` without `uses read` | `E2026` | The program does not declare that it needs that file |
| `print(input())` with no input to read | `E3009` | The standard input has ended |
| `type Point = { x: Int, y: Int }` and `Point(x: 1)` | `E2023` | The field `y` is missing |
| `type Point = { x: Int }` and `Point(x: 1, y: 2)` | `E2023` | The record has no field `y` |
| `type Point = { x: Int }` and `Point(x: 1, x: 2)` | `E2023` | The field `x` is given twice |
| `type Point = { x: Int }` and `Point(x: "a")` | `E2011` | The field `x` is of type `Int` |
| `type Point = { x: Int }` and `let p = Point(x: 1)` and then `p.y` | `E2024` | The record has no field `y` |
| `type Point = { x: Int }` and `let p = Point(x: 1)` and then `p.x = 2` | `E2025` | A record is immutable |
| `type A = { a: A }` | `E2016` | A record cannot contain itself |
| `add(1)` with `add(a: Int, b: Int)` | `E2009` | An argument is missing |
| `add(1, "2")` | `E2011` | The second argument must be `Int` |
| `add(1, 2)` as a statement | `E2010` | The returned value is not used |
| `launch()` without declaring `launch` | `E2008` | The function does not exist |
| A `gives Int` function without `return` on some path | `E2014` | A `return` is missing |
| `return "x"` in a `gives Int` function | `E2011` | The returned value is not of the declared type |
| `needs n` with `n` of type `Int` | `E2011` | The condition of a contract must be `Bool` |
| `print(10 / 0)` | `E3001` | Division by zero (detected when running) |
| `divide(1.0, 0.0)` with `needs b != 0.0` | `E4001` | Broken contract (detected when running) |
| `List.get([1, 2], 2)` | `E4001` | Index outside the list (detected when running) |
| A file without `fn main` | `E2001` | The entry point is missing |

## 13. Known limitations

These are real limitations of this version, not bugs:

- There are two forms of loop: `while`, which always declares its measure (`shrinks`), and `for` over a
  `List[T]`, which does not need one. There is no `break` or `continue`, and no compound assignments (`+=`).
- `List[T]` lists are immutable and finite. There is no index syntax (`xs[i]`), no mutation of
  elements, no `List.set`, `map`, `filter`, sorting or total variant of `List.get`: to read
  a position, use `List.get`, which requires a valid index and stops the program with `E4001` if it
  is not.
- All the elements of a list have the same type. `[]` and `for x in []` need an expected
  type (`E2011`). A list cannot be refined (`type NonEmpty = List[Int] ...` is `E2016`).
- The path analysis does not consider that a `for` always returns, even if all its iterations
  contain a `return`: if the `for` is the last statement, the function needs a `return` after it.
- The measure of a `while` is an `Int`: there are no compound measures (pairs, texts).
- Parameters cannot be reassigned.
- `if` is a statement, not an expression: it cannot be used as a value.
- There are no maps, enumerations or `for` over ranges or `Text`. Records (section 4.6) have
  immutable fields and allow no methods, refinements or recursion. `List[T]` lists are
  immutable and finite. For `Option` and `Result` (section 4.7) there is no `match` or `if let`: the
  variants are recognized with functions, and the value is read with `value_or` or `value`.
- The operations on texts are those of section 8.1: there is no `trim`, case conversion, `split`,
  `replace` or search for positions. A character is a code point: graphemes are not counted.
- There is no remainder operator (`%`).
- The requirements of the functions of a type are checked when running, like those of the program:
  `nex check` does not warn that `Text.slice("abc", 0, 5)` is going to fail.
- There is no text interpolation, no multi-line texts and no block comments.
- Literals only allow decimal notation: there is no hexadecimal and no exponents (`1e-3`).
- The minimum integer `-9223372036854775808` cannot be written as a literal. It can be obtained:
  `-9223372036854775807 - 1`.
- A variable, parameter or iterator that is declared and never used gives `W2001`; it is not an
  error. A `var` that is never reassigned gives `W2002`, and a name outside `snake_case` gives
  `W2003`. These are the only warnings: no other quality problem is reported.
- `print` receives a single argument and always adds a line break.
- Input and files are those of section 8.3. It is not possible to read "until the end" of the
  standard input without stopping (`input()` fails with `E3009`), there are no directories or files that are not
  text, no direct environment-variable access and no HTTP methods other than GET.
- A program is the entry file plus the files it imports (section 7.6). There are no module
  aliases, no selective imports, no search path outside the folder tree of the program,
  no packages, no versions and no re-exporting. A module only runs as part of another one: there is no
  command that starts a module directly, and `nex test` only evaluates the examples of the entry
  file.
- Contracts are not verified statically (section 9.3). Of refined types, only
  constants are checked without running.
- The condition of a refined type cannot call functions of the program.
- There are no type aliases without a condition (`type Id = Int`): a refined type always carries `where`. A
  record (section 4.6) is declared without `where`, because its fields carry no condition.
- `nex inspect` only has JSON output. With lexical errors it has no tree; with syntax errors the
  tree is partial (`complete` is `false`) and leaves out the parts that have them.
- The formatter is only reachable through the language server (`nexora-lsp`): there is no `nex`
  command for it ([LSP](lsp.md)).

The complete list, with the limits of the implementation and the known risks, is in
[Limitations](limitations.md).

## 14. Planned features (not implemented)

Nothing of what follows works today. It is the direction of the design, taken from the draft
`docs/fase-1-diseno.md` at the root of the repository, and it may change:

- `for` over ranges, `break` and `continue`.
- `if` and `match` as expressions.
- Text interpolation (`"Hello {name}"`), for which the `{` is already reserved.
  - Maps and enumerations. Records (section 4.6), `List[T]` lists and the two types
    `Option[T]` and `Result[T, E]` (section 4.7) already exist, but not user generics
    (`fn f[T]`), higher-order functions or functions as values.
- Static verification of contracts, and test blocks (`test`) outside functions.
- A broader effect system. Declared effects (`uses`) exist for files, HTTPS origins and external
  processes (section 8.3), but a module does not declare what it needs and the rest of the language
  has no effect propagation.
- Direct environment-variable access and HTTP methods other than GET.
- There is no integration with AI models, and no design for one: what exists are the structured
  representations (`nex inspect`, diagnostics in JSON) that an external tool could consume. The
  words `ai` and `tool`, reserved for it until 0.11, are ordinary names since 0.12
  ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), section 9).
- Deciding a `needs` without running, at the call sites whose arguments are constants, and
  reporting what the examples observe of each clause (`nex test --evidence`): later phases of
  [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md).

### Differences from the design draft

This specification takes precedence over the draft in what is already implemented:

| Aspect | Draft `fase-1-diseno.md` | This specification |
|--------|--------------------------|--------------------|
| File extension | `.nx` | `.nex` |
| Text type | `String` | `Text` |
| "No value" type | `Unit` | `Void` |
| Joining texts | Not allowed; interpolation is used | `+` joins two `Text`, because interpolation does not exist yet |
| Value of a function | The last expression of the block | Always with `return` |
| Contracts | Between the signature and the body | Between the signature and the body (since 0.12; at the beginning of the body until 0.11), with an optional name and an optional explanation after a comma |
| Examples | `example` between the signature and the body; `nexora test` | `example` between the signature and the body, with the same rules as contracts but without a name; `nex test` |
| Dynamic value to refined type | `Percent.from(n)`, which returns a `Result` | `Percent(n)`, which stops the program with `E4003` if the condition is not met |
| Aliases without a condition | `type UserId = Int` | They do not exist |
| Conversion between numbers | `Int.to_float(x)` | `to_float(x)`, `to_int(x)` |
| Unused variables | They are an error | A warning (`W2001`): they never stop the program |
| Loops | `while` and `for`, without requirements | `while` with a required measure (`shrinks`) and `for` over `List[T]`; both with optional invariants (`keeps`), checked on every iteration |
| Naming conventions | Required (`snake_case`…) | A warning (`W2003`) for values and private functions; public interfaces keep their spelling |
| Input | An `Input` record with `main(input)` | `args()` and `input()`, without changing the form of `main` (section 8.3) |
| Files | No rule: the program can read them | They have to be declared with `uses` and allowed with `--allow-read` (section 8.3) |
