# Types

NEXORA has a **static** type system: the type of every expression is known without running the
program, and all type errors are detected by `nex check`. No type error can
appear while the program runs.

The formal definition is in the [specification](language-spec.md#4-data-types). This guide
explains it with examples; all of them are checked by the tests of the project.

## The types

| Type | Values | Literals |
|------|--------|----------|
| `Int` | 64-bit signed integers: from `-9223372036854775808` to `9223372036854775807` | `0`, `42`, `1_000_000` |
| `Float` | IEEE 754 64-bit floating point | `3.14`, `0.5`, `10.0` |
| `Bool` | True or false | `true`, `false` |
| `Text` | Unicode text, immutable | `"Hello"` |
| `List[T]` | Immutable and finite sequence of values of type `T` | `[1, 2, 3]`, `[]` (with an expected type) |
| A record | The values built with `Name(field: value, ...)` | `Point(x: 1, y: 2)` |
| `Void` | No value | It has no literals |

`Int`, `Float`, `Bool` and `Text` are the built-in **value types**. `List[T]` is a compound value
type, and a program can declare refined types over the built-in ones and records. `Void`
can only be used as the return type of a function that returns nothing.

Details of each one:

- **`Int`**: a result out of range does not "wrap around": it stops the program with the error `E3002`.
- **`Float`**: some decimal fractions are not exact (`0.1 + 0.2` is `0.30000000000000004`).
  There is no infinity and no NaN: an operation whose result does not fit stops the program (`E3003`).
  Negative zero (`-0.0`) exists, and it is equal to `0.0`.
- **`Text`**: it is written between double quotes, on a single line. The escapes are `\n`, `\t`,
  `\"`, `\\` and `\{`. An unescaped brace `{` is an error: it is reserved.
- A numeric literal has no sign: `-5` is the `-` operator applied to `5`.

## Inference and annotations

Without an annotation, a variable takes the type of its value:

<!-- nex:body -->
```nex
let name = "NEXORA"      // Text
let age = 25             // Int
let price = 19.99        // Float
let active = true        // Bool
```

With an annotation, the value has to be **exactly** of that type:

<!-- nex:body -->
```nex
let name: Text = "NEXORA"
let age: Int = 25
let price: Float = 19.99
let active: Bool = true
```

If it is not, the error points at the value:

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let price: Float = 5
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:24
  |
2 |     let price: Float = 5
  |                        ^ Expected Float, found Int
  = note: 'price' is declared as Float.
  = hint: Convert the Int explicitly with to_float(...).

error: program.nex: check failed with 1 error
```

The suggestion (`hint`) appears because there is a conversion from `Int` to `Float`. When there is
no conversion between the two types, nothing is suggested.

## The compatibility rule

**Two types are compatible only if they are the same type, or if the value is of a refined type and
its base is expected.** There are no "wider" numeric types and no automatic conversions:

- An `Int` is not accepted where a `Float` is expected, nor the other way round.
- No type converts to `Bool` or to `Text` on its own.
- A `Percent` (refined over `Int`) is accepted where an `Int` is expected; the opposite direction
  requires building the refined value.
- The arguments of `List` are invariant: `List[Percent]` is not accepted where
  `List[Int]` is expected, even though every `Percent` is an `Int`.

The rule applies in the four places where a value has to have a concrete type:

| Place | Wrong example |
|-------|---------------|
| The annotation of a variable | `let n: Int = 2.0` |
| An argument of a call | `half(4)` if `half` expects a `Float` |
| The value of a `return` | `return "x"` in a `-> Int` function |
| The operands of an operator | `1 + 1.5` |

## Lists

A list is an **immutable and finite** sequence of values of the same type. It is written `List[T]`,
where `T` is the type of its elements:

```nex
let numbers: List[Int] = [1, 2, 3]
let empty: List[Int] = []
let nested: List[List[Int]] = [[1], [2, 3]]
let words: List[Text] = ["a", "b"]
```

`T` can be `Int`, `Float`, `Bool`, `Text`, a refined type or another `List[...]`; it cannot be
`Void`. The arguments of `List` are **invariant**: `List[Int]` and `List[Text]` are different
types, and `List[Percent]` is not accepted where `List[Int]` is expected. A refined element can
be widened to its base when the list is built with an expected type:
`let xs: List[Int] = [Percent(10), 20]`.

Without an expected type, the first element sets the type of the rest. An empty list needs an
expected type (an annotation, a parameter, a return, an assignment or the left-hand side of an
equality, as in `a == []`); `let xs = []` is `E2011`. The type does not propagate from the right-hand side to the
left-hand side of an equality: `[] == a` is `E2011`. All the elements have to be of the same type:
`let xs = [1, "a"]` is `E2011`.

<!-- nex:run -->
```nex
fn main() -> Void {
    let xs = [1, 2, 3]
    print(xs)
    print(List.length(xs))
    print(List.get(xs, 1))
    print(List.append(xs, 4))
    print(List.contains(xs, 2))
    var total = 0
    for x in xs {
        total = total + x
    }
    print(total)
}
```

```text
[1, 2, 3]
3
2
[1, 2, 3, 4]
true
6
```

A list does not change: `List.append` and `List.concat` build new lists. `print` and `to_text`
write `[1, 2, 3]`, and `==`/`!=` compare lists of the same type structurally. There is no
index syntax (`xs[i]`), no mutation of elements and no ordering between lists. To read a position,
use `List.get`, which requires a valid index and stops the program with `E4001` if it is not. The five
functions and the `for` are in the [specification](language-spec.md), sections 8.2 and 9.6.

A list cannot be refined in this version (`type NonEmpty = List[Int] ...` is `E2016`).

## Operators

| Operators | Operands | Result |
|-----------|----------|--------|
| `+`  `-`  `*`  `/` | Two `Int` or two `Float` | The same type |
| `+` | Two `Text` | `Text` (joins them) |
| `-x` | `Int` or `Float` | The same type |
| `==`  `!=` | Two values of the same type | `Bool` |
| `<`  `<=`  `>`  `>=` | Two `Int` or two `Float` | `Bool` |
| `and`  `or` | Two `Bool` | `Bool` |
| `not x` | `Bool` | `Bool` |

Precedence, from highest to lowest: `-x` and `not`; `*` and `/`; `+` and `-`; comparisons; `and`; `or`.
Parentheses group.

<!-- nex:run -->
```nex
fn main() -> Void {
    print(2 + 3 * 4)                    // 14: '*' before '+'
    print((2 + 3) * 4)                  // 20
    print(7 / 2)                        // 3: Int / Int is Int
    print(7.0 / 2.0)                    // 3.5
    print("Nex" + "ora")
    print(3 > 2 and not (1 == 2))
    print(true or false and false)      // 'and' before 'or'
}
```

```text
14
20
3
3.5
Nexora
true
true
```

Things worth knowing:

- **Integer division.** `Int / Int` returns an `Int` and drops the decimals, rounding
  towards zero: `7 / 2` is `3` and `-7 / 2` is `-3`. To get decimals, divide two `Float` values.
- **Comparisons.** They do not chain: `a < b < c` is a syntax error. Write
  `a < b and b < c`.
- **`not`** applies before comparisons: `not a == b` means `(not a) == b`. To
  negate a comparison write `not (a == b)` or `a != b`.
- **`and` and `or`** do not evaluate their right-hand side if the left-hand side already decides the result.
- **Texts.** They allow `+`, `==`, `!=` and ordering (`<`, `<=`, `>`, `>=`) between two texts, character
  by character by Unicode code point: `"Z" < "a"` and `"10" < "9"` are true. Their functions
  (`Text.length`, `Text.slice`…) and reading numbers (`Int.parse`, `Float.parse`) are in the
  [specification](language-spec.md), section 8.1.

## Invalid cases

Each of these lines is a type error (`E2011`), detected without running:

<!-- nex:body-fails codes=E2011 -->
```nex
let a = 10 + 2.5           // Int and Float do not mix
let b = 1 == 1.0           // not even when comparing
let c = true + 1           // a Bool does not allow arithmetic
let d = true < false       // nor ordering
let e = "a" + 1            // '+' joins Text with Text
let f = [1] == ["a"]       // lists compare elements of the same type
let g = 1 and 2            // 'and' needs two Bool
let h = not 0              // 'not' needs a Bool
let i = -"text"            // '-' needs a number
```

A condition has to be a `Bool`; a number is not valid:

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let count = 3
    if count {
        print("some")
    }
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:3:8
  |
3 |     if count {
  |        ^^^^^ The condition of 'if' must be Bool, found Int
  = hint: A number is not a condition. Compare it explicitly, for example: x != 0

error: program.nex: check failed with 1 error
```

Using a name that is not a type, or `Void` where a value type is needed, is the error `E2012`:

<!-- nex:body-fails codes=E2012 -->
```nex
let a: String = "x"        // the text type is called Text
let b: Void = 1            // a variable cannot be Void
```

## Conversions

The only conversions are calls to these three functions:

| Function | From | To | Rule |
|----------|------|----|------|
| `to_float(value)` | `Int` | `Float` | Always possible. Integers of more than 53 bits are rounded to the nearest `Float` |
| `to_int(value)` | `Float` | `Int` | Drops the decimals (rounds towards zero). If the result does not fit in an `Int`, runtime error `E3005` |
| `to_text(value)` | `Int`, `Float`, `Bool`, `Text` or `List[T]` | `Text` | The same text that `print` would write |

<!-- nex:run -->
```nex
fn main() -> Void {
    print(to_float(7) / 2.0)
    print(to_int(3.9))
    print(to_int(-3.9))
    print("items: " + to_text(42))
    print("ready: " + to_text(true))
    print(to_text(2.0))
}
```

```text
3.5
3
-3
items: 42
ready: true
2.0
```

There is no conversion from `Text` to a number, nor between `Bool` and numbers.

Each conversion function only accepts its source type:

<!-- nex:body-fails codes=E2011 -->
```nex
let a = to_float(1.5)      // expects an Int
let b = to_int(1)          // expects a Float
let c = to_int("12")       // there is no conversion from Text
```

## `Void`

`Void` means "no value". A call to a `Void` function cannot be used where a
value is needed:

<!-- nex:body-fails codes=E2011 -->
```nex
let nothing = print("x")           // there is no value to store
print(print("x"))                  // nor to pass as an argument
```

## What is checked when running

The type system guarantees that every operation receives values of the right type. It cannot
guarantee anything that depends on the concrete **value**. These situations are detected when running:

| Situation | Error |
|-----------|-------|
| Division by zero | `E3001` |
| `Int` result out of range | `E3002` |
| `Float` result too large | `E3003` |
| `to_int` of a `Float` that does not fit in an `Int` | `E3005` |
| `List.get` with an index outside the list | `E4001` |
| `Percent(x)` with a value that does not meet the condition of `Percent` | `E4003` |

<!-- nex:fails exit=3 -->
```nex
fn main() -> Void {
    let largest = 9223372036854775807
    print(largest)
    print(largest + 1)
}
```

```text
9223372036854775807
runtime error[E3002]: Integer overflow
 --> program.nex:4:11
  |
4 |     print(largest + 1)
  |           ^^^^^^^^^^^ The result of this operation does not fit in an Int
  = hint: Int holds whole numbers from -9223372036854775808 to 9223372036854775807.

error: program.nex: the program stopped because of a runtime error
```

## Refined types

A refined type is a value type with a rule that all its values meet:

<!-- nex:run -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
type Cents = Int where value >= 0, "An amount of money cannot be negative"

fn apply_discount(price: Cents, percent: Percent) -> Cents {
    ensures result <= price, "A discount never raises the price"
    return Cents(price * (100 - percent) / 100)
}

fn main() -> Void {
    print(apply_discount(2000, 15))
}
```

```text
1700
```

- `type Percent = Int where ...` declares the type: its **base** (`Int`) and its **condition**, in which
  `value` is the value being checked. After a comma there may be the explanation of the rule.
- Signatures now say more than before: `apply_discount` does not accept any `Int` as a percentage,
  and its caller sees it without reading the body.
- **Every value of type `Percent` meets the condition of `Percent`.** That is the guarantee, and it
  holds in the whole program.

### How a value enters a refined type

There are only two ways, and both are written in the code:

1. **A constant.** `apply_discount(2000, 15)` passes the literal `15` where a
   `Percent` is expected. `nex check` evaluates the condition with that value **without running the program**, and if it is not
   met the program never runs:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() -> Void {
    let discount: Percent = 150
    print(discount)
}
```

```text
type error[E2017]: Value outside refined type
 --> program.nex:4:29
  |
4 |     let discount: Percent = 150
  |                             ^^^ 150 is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 150
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: check failed with 1 error
```

2. **The explicit check `Percent(x)`** for any computed value. It is done when running,
   and if the condition is not met the program stops on that line (`E4003`, exit code
   `5`). In the example above, `Cents(...)` checks that the discounted price is not negative.

A computed value that has not been checked is not accepted where a refined type is expected, even if its type is
the base:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100

fn main() -> Void {
    let half = 100 / 2
    let discount: Percent = half
    print(discount)
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:5:29
  |
5 |     let discount: Percent = half
  |                             ^^^^ Expected Percent, found Int
  = note: 'discount' is declared as Percent.
  = hint: Check the value explicitly with Percent(...). The program stops there if the value does not satisfy the condition of Percent.

error: program.nex: check failed with 1 error
```

The reason is the same as that of [conversions](#conversions): nothing changes type without the
code saying so. Every point where a rule can stop the program is a `Percent(...)` call
that can be seen and searched for.

### Using refined values

- A `Percent` is accepted anywhere an `Int` is expected: it is an `Int` that also meets
  a rule.
- An operation with refined values gives a value of the base: `discount + 10` is an `Int`, because
  it may be 110.
- Two different refined types are different types, even if they have the same base.
- A type can refine another refined type: `type Pass = Percent where value >= 50` requires both
  conditions.

### What the condition can use

Only `value`, literals, operators and the built-in conversions (`to_float`, `to_int`,
`to_text`). It cannot call functions of the program (`E2018`): a refined type describes a value
by itself. A rule that depends on other data ("the discount cannot exceed the price") is
a relation between arguments and is written as a [contract](contracts.md).

### Errors of refined types

| Situation | Code | When |
|-----------|------|------|
| Lowercase name, repeated, of a built-in type or an endless chain of types | `E2016` | Without running |
| Condition that is not `Bool`, or that uses a name other than `value` | `E2011`, `E2005` | Without running |
| Condition that calls a function of the program | `E2018` | Without running |
| Constant that does not meet the condition | `E2017` | Without running |
| Too many constants to check (work limit of the analysis) | `E2019` | Without running |
| Computed value used without `Percent(...)` | `E2011` | Without running |
| `Percent(x)` with a value that does not meet the condition | `E4003` | When running |

## `Option` and `Result`: when there is no value, or when something fails

Two types of the language say what a value cannot say on its own: that **there is no** value
(`Option[T]`) or that **something failed** (`Result[T, E]`). Both have two variants, and the variant is
part of the value: `None` is never `Some(x)` and `Ok(x)` is never `Err(x)`, even if the two payloads are
equal.

No exceptions are needed: an `Option` or a `Result` is a value that is returned, stored,
compared and printed.

### `Option[T]`: there may be nothing

<!-- nex:run -->
```nex
fn find(names: List[Text], wanted: Text) -> Option[Int] {
    var index = 0
    while index < List.length(names) {
    decreases List.length(names) - index, "Each turn looks at one more name"
        if List.get(names, index) == wanted {
            return Some(index)
        }
        index = index + 1
    }
    return None
}

fn main() -> Void {
    let names = ["ada", "grace"]
    print(Option.unwrap_or(find(names, "grace"), -1))
    print(Option.unwrap_or(find(names, "nobody"), -1))
}
```

```text
1
-1
```

`Some(value)` is the variant that has a value and `None` the one that does not. The type of what is there when there is something
is written in the type of the `Option`:

<!-- nex:body -->
```nex
let found: Option[Int] = Some(42)
let missing: Option[Int] = None
```

`None` needs the context to say which `Option` it is: without an annotation, a parameter or a result
type, the analysis does not know which `Option` it is about and says so (`E2011`).

To recognize the variant and to read the value:

<!-- nex:body -->
```nex
let found: Option[Int] = Some(42)
if Option.is_some(found) {
    print(Option.unwrap_or(found, 0))
}
```

`Option.unwrap_or(x, default)` returns the value of `x` if it has one, and `default` otherwise. `Option.unwrap(x)`
reads the value without a default: if there is none, the program stops with `E3011` and says so.

### `Result[T, E]`: something can fail

<!-- nex:run -->
```nex
fn parse(text: Text) -> Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("not a whole number")
}

fn main() -> Void {
    print(Result.unwrap_or(parse("42"), -1))
    print(Result.error(parse("forty two")))
}
```

```text
42
not a whole number
```

`Ok(value)` is the variant that succeeded and `Err(error)` the one that failed. The error is stored **as
is**: `Err("not a whole number")` carries that text.

The type of the error and that of the value are given by the context. The result type of the function is what
sets them:

<!-- nex:body -->
```nex
let number: Result[Int, Text] = Ok(1)
```

And to recognize the variant and read what it carries:

<!-- nex:body -->
```nex
let failed: Result[Int, Text] = Err("boom")
if Result.is_err(failed) {
    print(Result.error(failed))
}
```

`Result.unwrap_or(x, default)` returns the value of `x` if it succeeded, and `default` if it failed.
`Result.unwrap(x)` and `Result.error(x)` read without a default: if the variant does not carry that, the program
stops with `E3012` or `E3013`.

### Which of the two

- `Option` when what is missing is **what was being looked for**: a search, an optional value of a
  record, the first line of a text.
- `Result` when what happened is **a failure**: a read that could not be done, a text that is not a
  number, a division by zero.

An `Option` does not carry the reason for the absence; a `Result` does. If the caller needs to know why
something is missing, it is a `Result`.

### What there is not

There is no `match`, no `if let`, no `?` operator and no user enums: the variants are recognized
with the functions above and the value is read with `unwrap_or` when it is known which one it is.

## Records

A **record** is a type that the program declares, with **immutable** and **required** fields.
It is declared with `type` and braces:

```nex
type Point = { x: Int, y: Int }
```

The name starts with an uppercase letter, like that of any type, and cannot be that of a built-in type
or that of another declared type (`E2016`). The type of a field can be a built-in type, `List[T]`,
a refined type or **another record**.

It is built by giving each field its value **by name**:

```nex
let p = Point(x: 1, y: 2)
```

The fields can be written in any order, but each one is given **only once** and **all** of them
are required: a missing field, a repeated one or one that the record does not have is the
error `E2023`. The value of a field has to have the type of the field (`E2011`).

Fields are read with a dot, and the root is always a name:

```nex
print(p.x)
```

Reads can be chained (`segment.to.x`), with no length limit, as long as every intermediate step is
a record; if the value is not a record, or the record does not have that field, it is the error `E2024`.

A record **does not change**: there is no way to assign to a field. `p.x = 1` is the error `E2025`.

A record is **nominal**: its identity is that of its declaration, not that of its name or of its
fields. Two records with the same fields are different types, and a value of one is not accepted
where the other is expected (`E2011`). Two values of the **same** record are compared **by value**,
field by field.

A record cannot contain itself, neither directly nor through another record or a
list: it is the error `E2016`, and the message writes out the cycle (`A -> B -> A`).

### Errors of records

| Situation | Code | When |
|-----------|------|------|
| Lowercase name, repeated, of a built-in type, a repeated field or a cycle | `E2016` | Without running |
| The type of a field does not exist, or is `Void` | `E2012` | Without running |
| A field is missing, there is an extra one or one is repeated | `E2023` | Without running |
| The value of a field does not have the type of the field | `E2011` | Without running |
| A field is read from something that is not a record, or from a record without that field | `E2024` | Without running |
| A field is assigned to | `E2025` | Without running |

## What does not exist

Maps, enumerations, type aliases without a condition,
user generics and any other compound type that is not `List[T]`, `Option[T]`, `Result[T, E]` or a record. Lists
have no index syntax and no mutation, and they cannot be refined; records do not allow methods,
refinements or recursion. They are in the [roadmap](roadmap.md) as planned work, and they do not
work today.
