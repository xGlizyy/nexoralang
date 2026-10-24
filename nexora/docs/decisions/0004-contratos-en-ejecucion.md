# 0004 — Contracts at the beginning of the body, checked at run time

- **Status:** accepted. It was experimental in 0.2;
  [decision 0007](0007-contratos-estables-y-tipos-refinados.md) declares it stable in 0.3.0 without
  changing its syntax. **Since 0.12, [decision 0019](0019-identidad-propia-del-lenguaje.md) replaces
  the position and the words of the clauses**: they go in the header of the function, between its
  signature and its body, and are called `needs` (it was `requires`) and `promises` (it was
  `ensures`). What they mean and when they are checked stand. Its programs are written in the syntax
  of their time, before 0.12: since 0.12 the language writes them as
  [decision 0019](0019-identidad-propia-del-lenguaje.md) describes, and `nex migrate` rewrites them.
- **Version:** 0.2.0

## Decision

1. A function can declare preconditions (`requires`) and postconditions (`ensures`).
2. **The clauses are written at the beginning of the body**, before any statement. The design
   draft placed them between the signature and the opening brace.
3. A condition is an ordinary `Bool` expression. In `requires` only the parameters are visible; in
   `ensures`, the parameters and `result`.
4. `result` is a contextual name: it only means "the returned value" inside `ensures`. A
   parameter cannot be named `result`.
5. **`nex check` checks the types of the conditions. Whether they hold is checked when running**, on
   every call: `requires` before the body, `ensures` after computing the return value.
6. A false condition stops the program with a diagnostic of category `contract`:
   - `E4001` points at **the call** (the caller breaks it).
   - `E4002` points at **the clause** (the function breaks it).
7. The process ends with exit code `5`, different from that of a runtime error (`3`).

## Reasons

- The syntax proposed for this phase is followed. Inside the body, the clauses need no
  special line-continuation rules, and `E1106` can detect a misplaced clause.
- Assigning the blame (call or function) is what tells a contract apart from an `if` that prints an
  error: the diagnostic says who has to fix their code.
- The values of the arguments and of `result` are included in the diagnostic because they are exactly
  what is needed to understand why the condition was false.
- Checking at run time is what can be done correctly today. A partial static verification
  that sometimes said "it holds" without being able to prove it would be worse than not having it.

## What it does not guarantee

- It does not prove that a contract always holds. It only checks the calls that run.
- `nex check` never says that a contract holds; only that it is well formed. There is a test
  (`test_check_does_not_claim_a_contract_holds`) with a condition that can never hold, which passes
  `nex check` and fails when it runs.
- It does not check that a condition has no effects: it can call a function that uses `print`.
- Contracts cannot be turned off.

## Alternatives ruled out

- **Clauses between the signature and the body** (draft). It remains a possible future change.
- **Static verification.** Out of scope: it would require a prover or a range analysis.
- **Treating the violation as an ordinary runtime error.** It would lose the distinction between
  "the program did an impossible operation" and "the program broke what it itself declares".

## Possible incompatible changes

Since it is experimental, the position of the clauses, the name `result` and the corresponding nodes
of the `nex inspect` schema may change (which would change the version of the schema).

> Resolved in [decision 0007](0007-contratos-estables-y-tipos-refinados.md): the position of the
> clauses and the name `result` are kept and become stable.
