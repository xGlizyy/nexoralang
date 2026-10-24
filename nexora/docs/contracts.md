# Contracts

> **Status: since version 0.12** the clauses go in the header of the function, between its
> signature and its body, and are called `needs`, `promises` and `trust`
> ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)). From 0.3 to 0.11 they were
> `requires` and `ensures`, at the beginning of the body
> ([decision 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)); `nex migrate` rewrites a
> program of 0.11. The name `result` and the explanation after a comma do not change.

A contract is a condition that a function declares as part of itself:

- **`needs`**: what the function **expects** from its caller (precondition).
- **`promises`**: what the function **promises** when it ends (postcondition).
- **`trust`**: something the function **relies on** and the language does **not** check (see
  [`trust`](#trust-what-the-language-does-not-check)).

Contracts are evaluated with the normal rules of the language. They are deterministic and no
AI model is involved.

The formal definition is in the [specification](language-spec.md#9-contracts). All the examples
of this page are checked by the tests of the project.

For the rules that describe **a value** and not a call ("a percentage goes from 0 to 100"), NEXORA
has [refined types](types.md#refined-types). Contracts and refined types
complement each other: a type says which values are valid anywhere in the program, and a contract
says what relation the arguments and the result of a concrete function have.

## An example

<!-- nex:run -->
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

fn main() {
    print(divide(9.0, 2.0))
    print(absolute(-42))
}
```

```text
4.5
42
```

## Rules

- The clauses go **in the header**: after the signature, one per line, and the `{` of the body goes
  alone on the line after the last one. There can be several of each kind, in any order.
- The condition has to be of type `Bool`.
- In `needs` and `trust` only **the parameters** of the function are visible.
- In `promises` the parameters and **`result`** are visible; `result` is the value returned by the
  function and has its result type. In a function without `gives`, `result` does not exist.
- Parameters do not change their value, so in `promises` they are worth the same as on entry.
- A condition can call functions.
- `result` only has this meaning inside `promises`. In the body it is an ordinary name.
  A parameter cannot be named `result`.
- After the condition there may be, after a comma, the **explanation** of the rule (next
  section).
- A clause can have a **name**, before its condition: `needs fits: part <= 92233720368547758`. It
  is written in lowercase, it is unique within the function and its loops, and it cannot be a
  parameter or `result` (`E2031`). It is not a variable: no expression uses it. When the clause
  is broken, the diagnostic names it: `This call breaks needs 'fits' of 'percentage'`. Names are
  optional.

## The explanation of a rule

A condition says *what* is required; its explanation says *why*. It is written after a comma, as a
text:

```text
needs amount <= balance, "An account cannot go below zero"
```

The explanation does not change what is checked. When the condition is false, it appears in the
diagnostic as `Reason: ...`, right after the condition, and tools receive it as
data (`message` in `nex inspect` and in `nex context`). That way, whoever breaks the rule, whether a person
or an agent, does not have to work out where it comes from:

<!-- nex:fails exit=5 -->
```nex
fn withdraw(balance: Int, amount: Int) gives Int
    needs amount > 0, "A withdrawal moves some money"
    needs amount <= balance, "An account cannot go below zero"
    promises result >= 0, "The balance after a withdrawal is never negative"
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

It is optional, except in a `trust`. It is worth writing it when the condition does not explain itself:
`needs b != 0.0` does not need it; `needs amount <= balance` does, because the rule belongs to the
business, not to arithmetic. It is a single sentence: an empty text or one with a line break is an
error (`E1101`).

## When each thing is checked

| Moment | What is checked |
|--------|-----------------|
| Without running (`nex check`) | That the condition is well written: visible names, correct types, `Bool` result |
| When running, on **every** call | `needs`: after receiving the arguments and **before** running the body |
| When running, on **every** call | `promises`: **after** computing the return value |
| Never | `trust`: its condition is not evaluated |

`nex check` rejects a badly typed condition without running anything:

<!-- nex:check-fails -->
```nex
fn half(n: Int) gives Int
    needs n
    promises result == "small"
{
    return n / 2
}

fn main() {
    print(half(8))
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:11
  |
2 |     needs n
  |           ^ The condition of 'needs' must be Bool, found Int
  = hint: A number is not a condition. Compare it explicitly, for example: x != 0

type error[E2011]: Type mismatch
 --> program.nex:3:21
  |
3 |     promises result == "small"
  |                     ^^ Cannot apply '==' to Int and Text
  = hint: Both sides of '==' must have the same type.

error: program.nex: check failed with 2 errors
```

## When `needs` does not hold

The program stops **before** running the body of the function. The diagnostic points at **the
call**, because the caller is the one who breaks it, and it shows the condition and the values received:

<!-- nex:fails exit=5 -->
```nex
fn divide(a: Float, b: Float) gives Float
    needs b != 0.0
{
    return a / b
}

fn average(total: Float, count: Float) gives Float {
    return divide(total, count)
}

fn main() {
    print(average(90.0, 4.0))
    print(average(90.0, 0.0))
}
```

```text
22.5
contract error[E4001]: Precondition violated
 --> program.nex:8:12
  |
8 |     return divide(total, count)
  |            ^^^^^^^^^^^^^^^^^^^^ This call breaks a 'needs' condition of 'divide'
  = note: The condition at line 2 is false: needs b != 0.0
  = note: It was called with: a = 90.0, b = 0.0
  = note: In 'average', called at line 13, column 11.

error: program.nex: the program stopped because a contract was broken
```

Without the contract, the same program would fail with a division by zero inside `divide`. With it,
the error says which rule was broken and from where.

<a id="the-functions-of-the-language-also-have-requires"></a>

### The functions of the language also have `needs`

The functions of a type that do not always have an answer (`Text.slice`, `Int.parse`,
`Float.parse`) declare their `needs` in NEXORA, with their explanation, and fail with the same `E4001`
([specification](language-spec.md), section 8.1). The caller can move the requirement to its
own function:

<!-- nex:run -->
```nex
fn quantity(written: Text) gives Int
    needs Int.can_parse(written), "The quantity has to be written as a whole number"
{
    return Int.parse(written)
}

fn main() {
    print(quantity("12") * 2)
}
```

```text
24
```

`nex symbols` shows the requirements of every built-in function in its `contracts` field, so a
tool knows before running anything that `Int.parse` needs `Int.can_parse`.

## When `promises` does not hold

The diagnostic points at **the clause**, because it is the function that does not meet what it promises, and
it shows the returned value:

<!-- nex:fails exit=5 -->
```nex
fn discount(price: Int, percent: Int) gives Int
    needs percent >= 0
    promises result <= price
{
    return price * (100 + percent) / 100
}

fn main() {
    print(discount(200, 0))
    print(discount(200, 25))
}
```

```text
200
contract error[E4002]: Postcondition violated
 --> program.nex:3:5
  |
3 |     promises result <= price
  |     ^^^^^^^^^^^^^^^^^^^^^^^^ 'discount' breaks its own 'promises' condition
  = note: 'discount' finished, but its condition is false: promises result <= price
  = note: It returned: result = 250
  = note: It was called with: price = 200, percent = 25
  = note: In 'discount', called at line 10, column 11.

error: program.nex: the program stopped because a contract was broken
```

Here the contract has found a real bug in the body: it adds the percentage instead of subtracting it.

## `trust`: what the language does not check

A `trust` states a condition the function relies on and NEXORA **does not check**. It is written like
a `needs`, with an explanation that is required: the explanation is the only thing behind it.

<!-- nex:run -->
```nex
fn hours_slept(minutes: Int) gives Int
    needs minutes >= 0, "Time does not run backwards"
    trust plausible: minutes < 1440, "The sensor sends one night at a time"
{
    return minutes / 60
}

fn main() {
    print(hours_slept(450))
    print(hours_slept(5000))
}
```

```text
7
83
```

- Its condition is checked for being a well-written `Bool`, and it sees only the parameters.
- It is **never evaluated**: not on a call, not by `nex check`, not by `nex test`. It cannot fail and
  cannot stop the program: `hours_slept(5000)` runs, although the trusted condition is false.
  Removing every `trust` from a program does not change what it does.
- A trusted condition is **neither proved nor checked**. A tool, a report or a document must never
  present it as verified.

Use it to write down an assumption that a person vouches for and that the program cannot or should
not check on every call; when the rule can be checked, write a `needs`.

## What backs each clause

`nex check --evidence` says, for every clause of the program, whether the language evaluates it when
the program runs ([CLI reference](cli-reference.md#--evidence)):

```text
program.nex: 2 promises in 1 function (computed: enforcement)
  hours_slept
    needs minutes >= 0    checked
    trust plausible       trusted
```

`checked` means that a false condition stops the program, not that it is never false; `trusted`,
that nothing checks it. It runs nothing. Deciding a `needs` without running, and counting what the
examples observe, are later phases of [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md).

## Examples (`example`)

A contract says which relation the input and the output always meet. An **example** says what concrete
result the function gives with some concrete inputs. It is written next to the contracts, with the same
form, and `nex test` evaluates it ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)):

<!-- nex:test exit=0 -->
```nex
fn double(n: Int) gives Int
    needs n >= 0, "Only natural numbers"
    example double(2) == 4, "Two doubled"
    example double(double(1)) == 4
{
    return n * 2
}
```

```text
program.nex: 2 examples in 1 function
  double   2 passed
✓ 2 examples passed: program.nex
```

- The expression is `Bool` and has to call its own function, written in the expression itself
  (`E2020` if it does not). It does not see the parameters or `result`: the inputs and the result are written
  as values.
- `nex check` and the other analysis tools **never** evaluate an example. `nex run`
  ignores them. `nex test` does not require `main` and does not run it.
- Every example is evaluated separately, checking the contracts of everything that runs.

If an example turns out false, `nex test` says what the function returned and ends with code `6`:

<!-- nex:test exit=6 -->
```nex
fn double(n: Int) gives Int
    needs n >= 0, "Only natural numbers"
    example double(3) == 7, "Three doubled is seven"
    example double(-1) == -2
{
    return n * 2
}
```

```text
program.nex: 2 examples in 1 function
  double   1 failed, 1 error

test error[E4004]: Example failed
 --> program.nex:3:13
  |
3 |     example double(3) == 7, "Three doubled is seven"
  |             ^^^^^^^^^^^^^^ This example of 'double' is false
  = note: double(3) returned 6
  = note: Reason: Three doubled is seven

contract error[E4001]: Precondition violated
 --> program.nex:4:13
  |
4 |     example double(-1) == -2
  |             ^^^^^^^^^^ This call breaks a 'needs' condition of 'double'
  = note: The condition at line 2 is false: needs n >= 0
  = note: Reason: Only natural numbers
  = note: It was called with: n = -1
  = note: While evaluating example 2 of 'double', at line 4.

error: program.nex: 2 of 2 examples did not pass (1 failed, 1 error)
```

The first example is `failed` (`E4004`): the function answered, but not what was expected. The second one is
`error`: it never got to answer, because the call breaks the `needs`; it keeps the `E4001` and gains
a note with the example that caused it.

A file without examples is not taken as tested:

<!-- nex:test exit=6 -->
```nex
fn double(n: Int) gives Int {
    return n * 2
}
```

```text
program.nex: no examples to run
error: program.nex: nothing was tested
```

<a id="loops-invariant-and-decreases"></a>

## Loops: `keeps` and `shrinks`

A `while` loop declares its requirements in its header, between its condition and its `{`, just like
a function ([decision 0010](decisions/0010-var-y-while.md); the words and the place since 0.12,
[decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)):

- **`shrinks`** (exactly one): the **measure**, an `Int` that never goes below 0 and that decreases on
  every iteration. It is the reason why the loop ends, written in the code.
- **`keeps`** (as many as needed): an **invariant**, a condition that holds before every evaluation
  of the condition of the loop; that is, on arrival, after every iteration and on exit.

<!-- nex:run -->
```nex
fn gcd(a: Int, b: Int) gives Int
    needs a >= 0 and b >= 0, "Only natural numbers"
    needs a > 0 or b > 0, "gcd(0, 0) is not defined"
{
    var x = a
    var y = b
    while y != 0
        keeps x >= 0 and y >= 0
        shrinks y, "The remainder is always smaller than the divisor"
    {
        let remainder = x - x / y * y
        x = y
        y = remainder
    }
    return x
}

fn main() {
    print(gcd(1071, 462))
}
```

```text
21
```

The clauses see what is visible where the loop is, not what its body declares, and they carry their
explanation after a comma and, optionally, a name. A loop without `shrinks` does not pass
`nex check` (`E2021`). A `for` takes `keeps` but no `shrinks` (`E2022`): its list is finite.

The interpreter checks them **on every iteration**. A false invariant is `E4005`; a measure that is negative
or is not smaller than in the previous iteration is `E4006`. That way, no loop keeps repeating
forever: either it ends, or it stops and says in which iteration and with which values. The diagnostic carries the
explanation of the rule, like that of a contract:

<!-- nex:fails exit=5 -->
```nex
fn average(total: Int, count: Int) gives Int
    needs count > 0, "There is nothing to average"
{
    var quotient = 0
    var rest = total
    while rest >= count
        keeps quotient * count + rest == total, "No unit is lost while dividing"
        shrinks rest
    {
        rest = rest - count
        quotient = quotient + 2
    }
    return quotient
}

fn main() {
    print(average(10, 3))
}
```

```text
contract error[E4005]: Loop invariant violated
 --> program.nex:7:15
  |
7 |         keeps quotient * count + rest == total, "No unit is lost while dividing"
  |               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ This condition is false
  = note: The condition at line 7 is false: keeps quotient * count + rest == total
  = note: Reason: No unit is lost while dividing
  = note: After turn 1 of the loop at line 6.
  = note: The values: total = 10, count = 3, quotient = 2, rest = 7
  = note: In 'average', called at line 17, column 11.

error: program.nex: the program stopped because a contract was broken
```

## Codes and output

| Situation | Code | Category | `nex run` ends with |
|-----------|------|----------|---------------------|
| False `needs` condition | `E4001` | `contract` | `5` |
| False `promises` condition | `E4002` | `contract` | `5` |
| False `keeps` in a loop | `E4005` | `contract` | `5` |
| Measure (`shrinks`) that does not decrease or is negative | `E4006` | `contract` | `5` |
| Loop without a measure, or with more than one | `E2021` | `semantic` | `1` (it does not run) |
| Badly typed condition | `E2011` | `type` | `1` (it does not run) |
| Clause inside a body instead of the header | `E1106` | `syntax` | `1` (it does not run) |
| Explanation that is empty, longer than one line or not a text, or a `trust` without one | `E1101` | `syntax` | `1` (it does not run) |
| A clause name used twice, or equal to a parameter or `result` | `E2031` | `semantic` | `1` (it does not run) |
| `requires`, `ensures`, `invariant` or `decreases`, the words of 0.11 | `E1107` | `syntax` | `1` (it does not run) |

If evaluating the condition itself produces an error (for example, a division by zero inside
the condition), the error reported is that one (`runtime`, exit code `3`), not a contract
violation.

## Limitations

What contracts do **not** do. It is important not to attribute to them more guarantees than they have:

- **They are not proven.** `nex check` checks that a condition is well written, not that it
  holds. A program that passes `nex check` can break a contract when it runs.
- **Only the calls that run are checked.** A program ending without violations
  means that that run, with those values, met the contracts. It says nothing about other
  values.
- **A condition that can never hold is accepted.** `needs n > 0 and n < 0` passes `nex check`;
  the violation appears on the first call.
- **It is not checked that conditions have no effects.** A condition can call a
  function that uses `print`.
- **They cannot be turned off.** `needs` and `promises` are always checked, and every check has a
  running cost. A `trust` is never checked (see above).
- There are no conditions on values "before" and "after" a function: parameters do not change,
  so in `promises` they have the value the function was called with. Invariants only exist in
  loops. The rules on the values of a type are written with
  [refined types](types.md#refined-types).
- **A measure guarantees that the loop ends, not that it ends soon.** An initial measure of a
  billion allows a billion iterations.

## Why they exist

The requirements of a function are a verifiable part of the program: that is the feature that
distinguishes NEXORA ([decision 0006](decisions/0006-requisitos-verificables.md)). A requirement that
is only in an instruction in natural language is checked by nobody and gets lost in the next
edit; written as a contract, it is checked on every call and says who broke it.

Whether that really helps people and AI tools, and how much, **has not been measured**:
it is a working hypothesis, not a result.

The design decisions and their alternatives are in
[`decisions/0004`](decisions/0004-contratos-en-ejecucion.md),
[`decisions/0007`](decisions/0007-contratos-estables-y-tipos-refinados.md) and, for the syntax of 0.12
and `trust`, [`decisions/0019`](decisions/0019-identidad-propia-del-lenguaje.md).
