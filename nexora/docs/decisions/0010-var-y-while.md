# 0010 — Reassignable variables (`var`) and loops with requirements (`while`, `invariant`, `decreases`)

- **Status:** accepted. **Since 0.12, [decision 0019](0019-identidad-propia-del-lenguaje.md) renames
  and moves the loop clauses**: `keeps` (it was `invariant`) and `shrinks` (it was `decreases`), in
  the header of the loop, between its head and its body. Their rules (exactly one measure in a
  `while`, checked on every iteration) stand. Its programs are written in the syntax of their time,
  before 0.12: since 0.12 the language writes them as
  [decision 0019](0019-identidad-propia-del-lenguaje.md) describes, and `nex migrate` rewrites them.
- **Version:** 0.5.0
- **Related to:** [decision 0003](0003-funciones-retorno-e-if.md) (return paths),
  [0004](0004-contratos-en-ejecucion.md) (parameters in `ensures`),
  [0006](0006-requisitos-verificables.md) (the main line),
  [0007](0007-contratos-estables-y-tipos-refinados.md) (the guarantee of refined types and the
  form of the clauses) and [0008](0008-ejemplos-y-nex-test.md) (`nex test`). **It modifies
  none**: it keeps them, and this decision explains how.

## Context

Today every variable is immutable (`language-spec.md`, 5.1) and there are no loops: the only way to repeat
something is recursion, limited to 1000 nested calls (`E3004`, section 7.5). It is the first
point of "Planned" in the [roadmap](../roadmap.md): "They go together: one is no use without the other.
They remove the dependence on recursion."

| Need | Today | Problem |
|------|-------|---------|
| Adding the numbers from 1 to 5000 | A recursive function | `E3004`: more than 1000 nested calls |
| Repeating until a condition holds | Recursion with the state in the parameters | The limit is set by the implementation, not by the problem |
| Accumulating a result | A new variable at every step or a helper function | Code nobody would write in another language |

The design draft (`docs/fase-1-diseno.md`) proposed `var`, `while` and rule R3: "Everything is
immutable by default; only `var` allows reassigning". Both words have been reserved since 0.1.

### The problem that loops introduce

In the usual languages a loop is the place where it is easiest to get things wrong without anything
pointing it out: it does not end, it ends one iteration too early or too late, or it breaks in an intermediate iteration a rule
that the code took for granted. In NEXORA, also:

- **Until today every endless repetition ended in `E3004`.** With an ordinary `while`, `while true { }`
  would never end without exhausting either the stack or the memory. `nex run` and `nex test` would keep
  waiting, and an agent that runs `nex test` unsupervised would never receive the report.
- **A NEXORA program cannot read input** (section 8 of the specification). There is no
  correct program that needs an endless loop: there is no server or menu to wait for. A
  loop that does not end is always a defect.
- **The main line of the project** ([0006](0006-requisitos-verificables.md)) is that requirements
  are a verifiable part of the program. A function declares them with `requires` and `ensures`; a loop,
  which is the part of the code where they are most needed, would have none.

## Decision

### 1. `var`: a variable that can change its value

```text
var count = 0
var total: Int = 0
```

- Same form as `let`: `var` NAME [`:` TYPE] `=` EXPRESSION. It is always initialized when declared.
- **Its type is fixed.** It is inferred from the initial value or annotated, with the same rules as `let`
  (`E2011`, `E2012`). The value changes, never the type.
- Same scope rules as `let` (`language-spec.md`, 5.2): it exists from the next statement
  to the end of its block; no shadowing (`E2006`); a single namespace (`E2006`).
- `let` is still immutable. **What is immutable is what is written by default**; `var` signals in the
  declaration that the value can change further down.

### 2. Assignment

```text
count = count + 1
```

- It is a **statement**, not an expression. `a = b = 1` and `if x = 1 { }` are `E1101`.
- Only `=` exists. **There is no `+=`, `-=` or `++`**: one way of writing each thing.
- The value is evaluated and then stored.

| Target | Result |
|--------|--------|
| A `var` variable visible at that point (also from an inner block) | Correct |
| A `let` variable | `E2007`, with a note that points at the declaration and the suggestion to use `var` |
| A parameter | `E2007` (section 3) |
| A name that is not a visible variable | As today: `E2005` |

The value has to be compatible with the type of the variable, with the usual rule
(`language-spec.md`, 4.2).

### 3. Parameters remain immutable

A parameter cannot be reassigned (`E2007`). It is what keeps the rule of contracts "in
`ensures` [the parameters] have the same value as on entry" (9.1) and makes the note "It was called
with: …" of the diagnostics tell the truth. Whoever needs to change it writes `var n = start`.

### 4. Refined types keep their guarantee

An assignment to a variable of a refined type comes through one of the two paths that already exist
(`language-spec.md`, 4.4):

```text
var p: Percent = 20
p = 30                 // constant: checked without running (E2017 if it does not hold)
p = Percent(p + 10)    // explicit check: when running (E4003 if it does not hold)
p = p + 10             // E2011: an Int is not a Percent; the suggestion proposes Percent(...)
```

The constants of assignments count towards the same analysis budget (`E2019`).

### 5. `while`, with its requirements at the beginning of the body

```text
fn sum_to(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    ensures result == n * (n + 1) / 2
    var total = 0
    var i = 0
    while i < n {
        invariant total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        decreases n - i, "Each turn moves i one step closer to n"
        i = i + 1
        total = total + i
    }
    return total
}
```

A loop is `while` CONDITION `{` CLAUSES STATEMENTS `}`. The clauses go at the beginning of the body,
one per line, with the form of the contracts of a function: an expression and, after a comma, the
optional explanation.

| Clause | How many | What it declares | Type |
|--------|----------|------------------|------|
| `decreases` | **Exactly one** | The **measure**: a quantity that does not go below 0 and that decreases on every iteration. It is the reason why the loop ends | `Int` |
| `invariant` | Zero or more | A condition that holds **before every evaluation of the condition** of the loop: on arrival, after every iteration and, therefore, on exit | `Bool` |

Rules:

- **Every loop declares its measure.** A `while` without `decreases` is `E2021`; with two or more, `E2021`.
- The clauses see everything that is visible at the point of the loop (parameters, `let`, `var`) and nothing
  declared inside the body. They can call functions, like contracts.
- `invariant` and `decreases` outside the beginning of the body of a `while` are `E1106`, just like
  `requires`, `ensures` and `example` outside the beginning of a function. And the other way round: `requires`,
  `ensures` and `example` inside a `while` are `E1106`.
- The condition of the loop is `Bool` (`E2011`).
- **Every iteration opens a new scope**: what is declared inside the body exists only in that iteration.
- A `return` inside the body ends the function, as in any block; the current iteration
  is not completed and nothing else of the loop is checked.
- **Iterations are not calls.** They do not count towards the limit of 1000 calls and do not use the
  Python stack: the interpreter runs the loop iteratively.
- There is no `break`, `continue` or `for` (they remain reserved; see "Out of scope").

### 6. What is checked on every iteration

The interpreter runs a `while` like this:

1. It checks the `invariant` clauses, in order. If one is false: **`E4005` Loop invariant violated**.
2. It evaluates the condition. If it is `false`, the loop ends.
3. It evaluates the measure. If it is negative, or if it is not **strictly smaller** than the measure of the
   previous iteration of this same run of the loop: **`E4006` Loop measure did not decrease**.
4. It runs the body, in a new scope, and goes back to step 1.

Consequences:

- **A loop always ends, or stops with a diagnostic that says why it would not.** The
  measure is an integer that does not go below 0 and goes down on every iteration; it cannot do so indefinitely. It is a
  mathematical argument, not a time limit: the same program always gives the same result.
- The invariant is also checked on exit: the code that follows the loop can rely on it.
- The measure is compared with that of the previous iteration of **that run** of the loop. An inner loop
  starts its comparison again every time it is entered.
- As in contracts, if evaluating a clause produces a runtime error (`E3xxx`), the error
  that is reported is that one.

### 7. The diagnostics of a loop say in which iteration and with which values

`E4005` and `E4006` are of category `contract` (exit code `5`, like `E4001`–`E4003`):

```text
contract error[E4006]: Loop measure did not decrease
  --> examples/failing/loop_measure.nex:11:19
   |
11 |         decreases limit - i, "Each turn moves i one step closer to limit"
   |                   ^^^^^^^^^ The measure was 9 and is still 9
   = note: The measure at line 11: decreases limit - i
   = note: Reason: Each turn moves i one step closer to limit
   = note: Before turn 3 of the loop at line 10.
   = note: The values: limit = 10, i = 1, even = 1
   = note: In 'count_even', called at line 21, column 11.
```

| Field | `E4005` Loop invariant violated | `E4006` Loop measure did not decrease |
|-------|--------------------------------|---------------------------------------|
| Position | The condition of the `invariant` clause | The expression of the `decreases` clause |
| Label | `This condition is false` | `The measure was A and is now B` · `The measure was A and is still A` · `The measure is B; it must be 0 or more` |
| Notes, in order | `The condition at line N is false: invariant …` · `Reason: …` (if it has an explanation) · `Before the first turn of the loop at line L.` or `After turn K of the loop at line L.` · `The values: …` · the chain of calls | `The measure at line N: decreases …` · `Reason: …` (if it has an explanation) · `Before turn K of the loop at line L.` · `The values: …` · the chain of calls |

The order follows that of contracts (`E4001`): first the rule and its reason, then when and with which
values. An invariant is checked before evaluating the condition, so at that moment it is not known
whether the loop is going to exit: the note says after which iteration, not whether it was the last one.

**`The values:`** shows the variables and parameters visible at the point of the loop, in the
order in which they were declared, with the format of the values of contracts (texts, in
quotes). It is what a person or an agent needs to know which iteration failed and why, without
adding `print` to debug. It does not include what is declared inside the body, which does not exist between iterations.

**Other errors inside a loop.** Any runtime diagnostic (`E3xxx` or `E4xxx`) produced
inside the body, the condition or the clauses of a loop gains a note at the end, one for each
loop that contains it, from the innermost to the outermost: `In turn K of the loop at line L.` (in the
body), `Before turn K …` (in the measure) or `Before the first turn …` / `After turn K …` (in the
condition or in an invariant). Like the chain of calls, at most six are shown; if there are more,
a note `... and more loops.` No other field changes.

### 8. Return paths and unreachable code

The rule of [decision 0003](0003-funciones-retorno-e-if.md) does not evaluate conditions, and it is kept:

| Statement | Always returns if… |
|-----------|--------------------|
| `while` | **Never** (the condition may be false from the start) |
| Assignment | Never |

- A function with a value whose only `return` is inside a `while` is `E2014`.
- The code after a loop is never unreachable (`E2015` does not apply): every loop ends.
- `E2015` does apply inside the body, after a `return`.

### 9. New and changed diagnostics

| Code | Title | Category | When |
|------|-------|----------|------|
| `E2021` | Missing loop measure | `semantic` | A `while` without `decreases`, or with more than one. Suggestion for the missing case: `Add 'decreases <expression>' with an Int that gets smaller on every turn and never goes below 0, for example 'decreases n - i'.` |
| `E4005` | Loop invariant violated | `contract` | Section 6, step 1 |
| `E4006` | Loop measure did not decrease | `contract` | Section 6, step 3 |

`E1106` (Misplaced contract clause) also covers misplaced `invariant` and `decreases`; its title
does not change. `E2007` keeps its code and title; its label and its suggestion change:

| Case | Label | Suggestion |
|------|-------|------------|
| `let` variable | `'x' was declared with 'let' and cannot be given a new value` | `Declare it with 'var' if its value has to change.` |
| Parameter | `'n' is a parameter and cannot be given a new value` | `Copy it into a variable: 'var name = n'.` |

### 10. What does not change

- **Function contracts:** `requires` and `ensures` still see only the parameters and `result`.
- **Examples:** they do not see variables; their evaluation does not change.
- **Functions:** they do not see the variables of their caller. Without anonymous functions or global
  variables, a `var` only changes from its own function: there is no shared state.
- **Values:** they are still immutable. `var` changes which value a name refers to.

### 11. Tools

| Format | Change | Version |
|--------|--------|---------|
| `nexora.inspect/2` | New nodes `Var` (fields of `Let`), `While` (`condition`, `clauses`, `body`) and `LoopClause` (`clause`: `"invariant"` or `"decreases"`, `condition`, `message`; as in `Contract`, it is not called `kind` because that is the name of the node kind). All the clauses are stored, in the order of the code, so that a program with two measures can be represented. `Assign` does not change its fields; its description no longer says that it always comes with `E2007` | Still `/2`: only node kinds are added, like `Example` in 0.4.0 |
| `nexora.symbols/1` | Fields `mutable` (`true` only for `var`) and `assignments` (the position of each assignment, which is also in `references`) in every symbol | No change: added fields |
| `nexora.context/1` | `mutable` field in every variable; `loops` field at the end of every function, with `line`, `condition`, `invariants` and `measure` (each clause with `condition` as written, `message` and `line`; `measure` is `null` only if it is missing); values `mutable_variables`, `loops` and `loop_invariants` in `features`; with loops, the note: `Every loop declares a measure ('decreases') that is checked on every turn: a loop ends, or stops with E4006. Invariants are checked before every evaluation of the loop condition (E4005). This analysis verified their types, not that they hold.` | No change: added fields and values |
| `nexora.diagnostics/1`, `nexora.result/1`, `nexora.test/1` | Only new codes | No change |

A `Var` node instead of a `mutable` field in `Let`: a tool written for 0.4 notices an
unknown node kind, but silently ignores a new field and would treat the variable as
immutable.

## Reasons

- **It removes a limit of the implementation of the language.** The limit of 1000 calls stops deciding
  which programs can be written.
- **No loop hangs.** It is solved deterministically, without time limits that
  depend on the machine, and that is why `nex test` and `nex run` always end with a result when
  the program uses loops. For an agent that runs `nex test` unsupervised it is the difference
  between receiving a report and receiving nothing.
- **The loop explains why it is correct.** The measure and the invariant are the two arguments that are
  used to reason about a loop; here they are written in the code, with their explanation, and they are
  checked. It is [decision 0006](0006-requisitos-verificables.md) applied to the place where it is most
  needed.
- **The diagnostics say the iteration and the values.** A failure on iteration 4 of 10 is understood without
  debugging.
- **Coherent with what exists.** The clauses have the form, the position and the kind of
  explanation of `requires`/`ensures`; the errors are `contract` with exit `5`.
- **Immutable is still the norm**, and no existing rule is weakened (parameters, refined
  types, scopes).

## What it does not guarantee

- **That a program ends soon.** An initial measure of `1_000_000_000` allows a billion
  iterations. The guarantee is that the loop ends or stops with `E4006`, not that it does so in a reasonable
  time. It does not cover recursion either: a recursive function can still take a long time
  (`fib(40)`), as today.
- **That the measure or the invariant are the right ones.** What is written is checked, on the
  iterations that run. A trivial invariant (`invariant true`) always holds.
- **Static verification.** None of this is proven without running; `nex check` checks that the
  clauses are well formed.
- **That a `var` ever changes.** Warnings do not exist.

## Out of scope

- `break` and `continue`. With a required measure, leaving early breaks nothing, but every exit is
  another point where the invariant has to hold; it will be decided when it is needed.
- `for` and ranges, which wait for lists.
- Compound assignments (`+=`) and increments.
- Measures that are not an `Int` (pairs, texts).
- A time limit in `nex test` for slow recursion.
- `if` as an expression.

## Alternatives ruled out

- **A `while` without a measure, as in other languages.** It was the first draft of this decision. It leaves
  programs that do not end without an answer, in a language in which they are never correct, and it forces
  `nex test` to depend on a time limit.
- **A fixed limit of iterations.** It breaks correct programs that need many, and the number does not
  explain anything.
- **A time limit.** It depends on the machine: the same program would give different results.
- **Deducing the measure without writing it.** It works in the simple cases and fails without explanation in
  the others; a rule that sometimes applies on its own is harder to understand than one that is always
  written. Written, besides, it is one more requirement that an agent cannot delete without it being noticed.
- **An optional measure.** It would allow endless loops again, and its absence would not be noticed.
- **Making any variable reassignable.** It breaks R3 and the rule that every name means a
  single thing (5.2).
- **Allowing parameters to be reassigned.** It would change their meaning in `ensures` and in the diagnostics.
- **Assignment as an expression.** It allows `if x = 1`, a classic error.
- **Contextual words instead of keywords.** `invariant` and `decreases` could remain
  names outside a loop, but `invariant(x)` at the beginning of a loop would be ambiguous between
  a clause and a call. Keywords, like `requires` and `ensures`.

## Compatibility

- **Incompatible change:** `invariant` and `decreases` become keywords. A program that
  uses them as the name of a variable, parameter or function stops being valid (`E1101`); they are renamed.
- `var` and `while` go from reserved words to keywords: before, using them was `E1103`.
- **`E2007`:** same code and title; new label and suggestion.
- **JSON formats:** only additions (section 11). No version changes.
- **Playground:** syntax highlighting gains `var`, `while`, `invariant` and `decreases`.

## Required changes

| File | Change |
|------|--------|
| `nexora/src/nexora/tokens.py` | `var`, `while`, `invariant`, `decreases` as keywords |
| `nexora/src/nexora/ast_nodes.py` | `Var`, `While`, `LoopClause` |
| `nexora/src/nexora/parser.py` | `var`; `while` with its clauses; `E1106` for misplaced clauses |
| `nexora/src/nexora/checker.py` | Mutability of symbols; assignment; `while` and its clauses; `E2021`; return paths |
| `nexora/src/nexora/interpreter.py` | `Environment.assign`; iterative `while` with the checks of section 6; notes of iteration and values |
| `nexora/src/nexora/diagnostics.py` | `E2021`, `E4005`, `E4006` |
| `nexora/src/nexora/tooling.py`, `schemas.py` | Section 11 |
| `nexora/docs/*` | Specification, diagnostics, `inspect` schema, tools, limitations, roadmap |
| `nexora/examples/loops.nex` | New example |
| `web/js/playground/syntax.js` | Keywords |

## Regression tests

**Syntax**

1. `var`, assignment and `while` with clauses are parsed with the new nodes.
2. `var` and `while` no longer give `E1103`; `break`, `continue` and `for` do.
3. `invariant` or `decreases` outside the beginning of a `while`, and `requires`/`ensures`/`example` inside
   one, give `E1106`.
4. `a = b = 1` and `if x = 1 { }` give `E1101`; `let invariant = 1` gives `E1101`.

**Checking**

5. Assigning to a `var` of the same block and of an outer one is correct.
6. Assigning to a `let` or to a parameter gives `E2007` with the label and the suggestion of section 9.
7. Assignments of another type (`E2011`) and to refined types (section 4), including the `E2019` budget.
8. `while` without `decreases` or with two gives `E2021`; a measure that is not `Int`, an invariant or condition that is not `Bool`,
   `E2011`.
9. The clauses do not see what is declared inside the body (`E2005`).
10. Return paths (section 8).

**Execution**

11. A loop of 100,000 iterations ends with the correct result and without `E3004`.
12. What is declared inside the body does not survive the iteration.
13. A measure that does not go down, that goes up and that becomes negative: `E4006` with each label, the iteration and
    the values.
14. An invariant that is false on arrival, in an intermediate iteration and on exit: `E4005` with each note.
15. An inner loop starts the comparison of the measure again on every entry.
16. An `E3001` inside two nested loops carries the two iteration notes, from the inside out; with
    more than six loops, the seventh note is `... and more loops.`
17. `return` inside a loop ends the function and its `ensures` are checked.
18. `while true { decreases 1 }` stops with `E4006` on the second iteration; `nex test` with an
    example like that ends with the example as `error` and continues with the others.

**Tools and documentation**

19. `nex inspect`, `nex symbols` and `nex context` (section 11), validated with their schemas.
20. The documentation tests run the new examples.
