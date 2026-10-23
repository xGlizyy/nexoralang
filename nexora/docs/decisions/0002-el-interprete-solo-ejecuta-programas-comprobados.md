# 0002 — The interpreter only runs checked programs

- **Status:** accepted
- **Version:** 0.2.0

## Context

In 0.1 the interpreter repeated the name and type checks that the static checker already did,
"just in case" it was given a program that had not been checked. With functions, returns and
contracts, keeping two copies of the same rules would have duplicated the logic and opened the door
to the two copies drifting apart.

## Decision

- The rules for names, scopes and types live in a single module: `checker.py`.
- The checker returns a `CheckedProgram`, and **that is the only thing the interpreter accepts**.
- The interpreter only checks what cannot be known before running: division by zero,
  overflow, out-of-range conversions, call depth and contracts.
- If the interpreter finds something the checker should have rejected, it is a defect of
  NEXORA and it is reported as an internal error (exit code 70), not as an error of the program.

The four stages end up like this:

| Stage | Module | Depends on |
|-------|--------|------------|
| Lexical analysis | `lexer.py` | — |
| Syntax analysis | `parser.py` | tokens |
| Static analysis | `checker.py` | AST |
| Execution | `interpreter.py` | `CheckedProgram` |

`pipeline.analyze` chains the first three and is what every command uses (`run`, `check`,
`inspect`), so all three see exactly the same program.

## Reasons

- A single definition of each rule: what `nex check` accepts is exactly what `nex run`
  runs.
- The list of possible runtime errors is short and closed (section 10.3 of the specification),
  and it can be documented as a guarantee.

## Consequences

- The module is still called `checker.py`; it was not renamed to `type_checker.py` because it also
  checks names, scopes and return paths.
- The 0.1 tests that ran the interpreter without going through the checker are gone. Their
  coverage now comes from the checker tests.
- No visible changes for whoever uses the language.
