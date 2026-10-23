# 0007 — Stable contracts, explanation of the rules and refined types

- **Status:** accepted
- **Version:** 0.3.0
- **Replaces:** the provisional part of [0004](0004-contratos-en-ejecucion.md) (position of the
  clauses and the name `result`), which goes from experimental to stable.

## Context

[Decision 0006](0006-requisitos-verificables.md) makes verifiable requirements the
main feature of NEXORA and sets an order of work. This decision covers its steps 1, 2 and
5: stabilizing contracts, attaching an explanation to every rule and adding refined types.

Up to 0.2 contracts were experimental: their position in the code and the name `result`
could change. A feature that is presented as the main one cannot be in that situation.
Besides, a rule without an explanation forces whoever breaks it to work out why it exists, and
contracts only describe functions: there was no way to say that a value, wherever it is, meets
a rule.

## Decision

### 1. Contracts are stable

1. **The clauses go at the beginning of the body**, as in 0.2. They do not move to the signature.
2. **The returned value is called `result`** inside `ensures`. It is a contextual name, not a
   keyword: outside `ensures` it is an ordinary name. A parameter cannot be named
   `result` (`E2013`).
3. The rest stays as in [0004](0004-contratos-en-ejecucion.md): `requires` only sees the
   parameters, `ensures` also sees `result`, and whether the conditions hold is checked when
   running (`E4001` points at the call; `E4002`, at the clause).

### 2. Every rule can carry its explanation

```text
requires amount <= balance, "An account cannot go below zero"
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
```

- After the condition, after a comma, a single non-empty text literal.
- It does not change what is checked. It appears in the diagnostic as `Reason: ...` when the rule is
  broken, and tools receive it as data (`message` in `nex inspect` and in
  `nex context`).
- It is optional: making it required would fill the code with texts that repeat the condition.

### 3. Refined types

```text
type Percent = Int where value >= 0 and value <= 100
```

1. **A refined type is a base and a condition on `value`.** The base is a built-in type or
   another refined type.
2. **The guarantee: every value of a refined type meets its condition.** For it to hold without
   checking anything on every use, a value can only enter the type through two doors:
   - **A constant**, which `nex check` checks without running (`E2017`).
   - **The explicit check `Percent(x)`**, which is done when running and stops the program if
     the value does not meet the condition (`E4003`, category `contract`, exit code 5).
3. **Widening is free; narrowing is written.** A `Percent` is used where an `Int` is expected. An
   `Int` that is not a constant is not accepted where a `Percent` is expected (`E2011`); the message
   says to check it with `Percent(...)`.
4. **Operations return the base.** `p + 1` is an `Int`: the result can go out of range.
5. **The condition only talks about the value.** It can use `value`, literals, operators and the
   built-in conversions. It cannot call functions of the program or check other refined
   types (`E2018`).
6. **They can be chained.** `type Pass = Percent where value >= 50` requires both conditions, and they are
   checked starting from the base.
7. Type names start with an uppercase letter (`E2016`) and cannot be used for anything else (`E2006`).

## Reasons

- **Why `result` and not another form.** Three alternatives were considered:

  | Alternative | Why not |
  |-------------|---------|
  | Naming the result in the signature (`-> total: Int`) | It adds a second way of writing the return type, and the name is only useful in `ensures` |
  | A new keyword (`return` as a value, `out`) | `return` already means "leave"; giving a word two meanings goes against the rule of a single form |
  | Keeping `result` | It is what already worked, it reads without explanation and it breaks no program |

  `result` is kept, and declared stable.

- **Why the clauses stay in the body.** Moving them to the signature (as in the draft) would require
  line-continuation rules between the signature and the brace, and it would break every program with
  contracts to gain only a visual difference.
- **Why a comma and a text for the explanation.** It is the shortest form that needs no
  new word, and it resembles the assertions with a message of other languages. A text literal, and not
  an expression, so that a tool can read it without running anything.
- **Why two entry doors and not a check on every assignment.** If an `Int` were
  accepted where a `Percent` is expected and silently checked when passed, any line
  could stop the program without the code saying so. With `Percent(x)` every point where a
  rule can stop the program is written and can be searched for. It is the same idea as the
  explicit conversions of [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md).
- **Why constants are accepted without `Percent(...)`.** Their value is known without running, so
  the check is done by `nex check` and the error appears before running. Writing `Percent(20)`
  would add no information.
- **Why the condition cannot call functions.** A function could receive a value of the
  type itself and create a circular check, or depend on more than the value. Keeping it
  as an expression on `value` makes it evaluable by `nex check` for constants and makes it
  readable as data. Rules that depend on other values are written with `requires`.
- **Why `Percent(x)` stops the program instead of returning an error.** There is no `Result` in
  the language. When there is, a form that returns the error as a value can be added without changing
  this one.

## What it does not guarantee

- `nex check` does not reason about computed values: a `Percent(n + 2)` can pass the check
  and fail when running (`E4003`). Only constants are checked without running.
- It does not prove that a function with `-> Percent` never fails; it guarantees that, if it returns, what it
  returns meets the condition.
- Contracts are still checked only on the calls that run.

## Alternatives ruled out

- **Aliases without a condition (`type UserId = Int`).** They bring no checkable rule and would be a
  second way of naming the same type. They are rejected with a message that explains it (`E1101`).
- **Implicit check on assignment.** Ruled out for the reasons explained above.
- **Read-only refined types without inheritance (without chains).** Chaining allows reusing a
  rule (`Pass` over `Percent`) without copying it; the cost of implementing it is small.

## Incompatible changes

- `type` and `where` go from reserved words to keywords. No valid 0.2 program
  could use them as names, so none stops working.
- `nex inspect` changes to `nexora.inspect/2`: the `type` field of an expression can be the name
  of a refined type, `Program` has the `types` field and `Contract` has `message`.
- No valid 0.2 program changes its behaviour.
