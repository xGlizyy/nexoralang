# 0024 — Enumerations and exhaustive matching

- **Status:** accepted and implemented in the 0.16.0 development line.
- **Date:** 2026-10-30.
- **Related to:** [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md), which proposed
  enums and pattern matching, and [0016](0016-option-y-result.md), which introduced `Option` and `Result`.
- **Implementation:** parser, checker and interpreter support closed user enums with named payloads,
  `match` expressions, `if let`, nested patterns and static exhaustiveness checks. `Option`, `Result`
  and `Bool` use the same coverage analysis. LSP, formatter, JSON inspection and CLI diagnostics
  expose the new syntax and errors.

## Decision

NEXORA supports closed, nominal enum types declared with `type Name = enum { ... }`. Variants may
carry immutable named payload fields. Matching is an expression; `if let` is a conditional statement.
Bindings exist only in their arm or branch.

Matches over finite types (`Bool`, enums, `Option` and `Result`) must cover every value, including
nested payload cases. Matches over open types require a wildcard or binding. Guards and or-patterns
are deferred. A match arm the checker can prove unreachable is an error. Diagnostics E2032–E2035
identify missing cases, invalid patterns, unreachable arms and invalid constructors.

User enums are not generic in this version. Built-in `Option[T]` and `Result[T, E]` remain generic and
are matched exhaustively with the same syntax. There is no `?` propagation operator.
