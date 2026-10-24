# Contracts

> **Status: stable since version 0.3.0.** The position of the clauses, the name `result` and the
> explanation after a comma are final ([decision 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)).

A contract is a condition that a function declares as part of itself:

- **`requires`**: what the function **expects** from its caller (precondition).
- **`ensures`**: what the function **promises** when it ends (postcondition).

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

- The clauses go **at the beginning of the body**, one per line, before any statement.
  There can be several of each kind.
- The condition has to be of type `Bool`.
- In `requires` only **the parameters** of the function are visible.
- In `ensures` the parameters and **`result`** are visible; `result` is the value returned by the function
  and has its return type. In a `Void` function `result` does not exist.
- Parameters do not change their value, so in `ensures` they are worth the same as on entry.
- A condition can call functions.
- `result` only has this meaning inside `ensures`. In the body it is an ordinary name.
  A parameter cannot be named `result`.
- After the condition there may be, after a comma, the **explanation** of the rule (next
  section).

## The explanation of a rule

A condition says *what* is required; its explanation says *why*. It is written after a comma, as a
text:

```text
requires amount <= balance, "An account cannot go below zero"
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

It is optional. It is worth writing it when the condition does not explain itself: `requires b != 0.0` does not
need it; `requires amount <= balance` does, because the rule belongs to the business, not to arithmetic. It is
a single sentence: an empty text or one with a line break is an error (`E1101`).

## When each thing is checked

| Moment | What is checked |
|--------|-----------------|
| Without running (`nex check`) | That the condition is well written: visible names, correct types, `Bool` result |
| When running, on **every** call | `requires`: after receiving the arguments and **before** running the body |
| When running, on **every** call | `ensures`: **after** computing the return value |

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

## When `requires` does not hold

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

### The functions of the language also have `requires`

The functions of a type that do not always have an answer (`Text.slice`, `Int.parse`,
`Float.parse`) declare their `requires` in NEXORA, with their explanation, and fail with the same `E4001`
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
tool knows before running anything that `Int.parse` requires `Int.can_parse`.

## When `ensures` does not hold

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
`error`: it never got to answer, because the call breaks the `requires`; it keeps the `E4001` and gains
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

## Loops: `invariant` and `decreases`

A `while` loop declares its requirements at the beginning of its body, just like a function
([decision 0010](decisions/0010-var-y-while.md)):

- **`decreases`** (exactly one): the **measure**, an `Int` that never goes below 0 and that decreases on
  every iteration. It is the reason why the loop ends, written in the code.
- **`invariant`** (as many as needed): a condition that holds before every evaluation of the
  condition of the loop; that is, on arrival, after every iteration and on exit.

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
explanation after a comma. A loop without `decreases` does not pass `nex check` (`E2021`).

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
| False `requires` condition | `E4001` | `contract` | `5` |
| False `ensures` condition | `E4002` | `contract` | `5` |
| False `invariant` in a loop | `E4005` | `contract` | `5` |
| Measure (`decreases`) that does not decrease or is negative | `E4006` | `contract` | `5` |
| Loop without a measure, or with more than one | `E2021` | `semantic` | `1` (it does not run) |
| Badly typed condition | `E2011` | `type` | `1` (it does not run) |
| Clause outside the beginning of the body | `E1106` | `syntax` | `1` (it does not run) |
| Explanation that is empty, longer than one line or not a text | `E1101` | `syntax` | `1` (it does not run) |

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
- **A condition that can never hold is accepted.** `requires n > 0 and n < 0` passes `nex check`;
  the violation appears on the first call.
- **It is not checked that conditions have no effects.** A condition can call a
  function that uses `print`.
- **They cannot be turned off.** They are always checked, and every check has a running
  cost.
- There are no conditions on values "before" and "after" a function: parameters do not change,
  so in `ensures` they have the value the function was called with. Invariants only exist in
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
[`decisions/0004`](decisions/0004-contratos-en-ejecucion.md) and
[`decisions/0007`](decisions/0007-contratos-estables-y-tipos-refinados.md).
