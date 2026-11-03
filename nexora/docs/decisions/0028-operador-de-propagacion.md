# 0028 — The `?` propagation operator

- **Status:** accepted and implemented in the development line after 0.15.0.
- **Date:** 2026-11-03.
- **Related to:** [0016](0016-option-y-result.md), which introduced `Option` and `Result` without a way to
  pass a failure upwards, and [0024](0024-enumeraciones-y-match-exhaustivo.md), which added `match` and
  `if let` and explicitly left `?` out.

## Context

Since 0024 a program can handle every case of an `Option` or a `Result` with an exhaustive `match`. That is
the right tool when the two cases deserve different work, but most code that calls a function that can fail
only wants to say "if this failed, I fail the same way". With `match` that costs four lines per call, and the
alternative, `Option.value` and `Result.value`, stops the program. The ergonomic gap pushes people toward the
partial reads that this language set out to avoid.

## Decision

A postfix operator `expression?`:

1. On a `Some(v)` or an `Ok(v)` its value is `v`.
2. On a `None` or an `Err(e)` it ends the enclosing function, which gives that `None` or `Err(e)` unchanged.
3. It is checked statically: the operand has to be an `Option` or a `Result`, and the function has to give a
   type that can carry the early return. An `Option` needs `Option[_]`. A `Result[_, E]` needs `Result[_, E]`
   with the **same** `E`. Anything else is `E2036`, with a hint to use `match` or `if let`.
4. It is valid only in the statements of a function body, never in a clause, an `example` or the condition of
   a refined type, because those conditions do not return.
5. The `promises` of the function are checked on the early return, like on any `return`.

## What is deliberately not included

- **No conversion of the error.** Rust converts the error with `From`; NEXORA has no traits, and an implicit
  conversion would hide where an error changes type. A function that needs another `E` uses `match`.
- **No `?` between `Option` and `Result`.** Mixing them would need a rule for which error an absence becomes.
- **No `?` in `main`.** `main` gives nothing, so there is nothing to return; the program has to decide what
  to print or how to stop.

## Consequences

- The grammar gains one token (`?`) and one postfix level between the primary expressions and the prefix
  operators. A program that worked before has no `?`, because it was a lexical error (`E1001`): nothing that
  was valid changes meaning.
- The reference interpreter implements the early return with an internal signal caught at the function
  boundary. The self-hosted compiler has to implement the same rule (see the parity checks in `selfhost/`).
