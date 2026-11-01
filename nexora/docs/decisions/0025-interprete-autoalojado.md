# 0025 — A self-hosted interpreter written in NEXORA

- **Status:** accepted (2 November 2026); stage 4 is closed by [0026](0026-generador-a-c.md) and [0027](0027-herramientas-nativas-por-defecto.md).
- **Date:** 2026-10-31.
- **Decision owner:** NEXORA maintainer.
- **Affects:** the implementation strategy of the language, the language features needed to write
  its own tools, the meaning of "reference interpreter" and the roadmap.
- **Related to:** [0021](0021-alcance-nexora-1-0.md) (1.0 scope),
  [0023](0023-despliegue-aplicaciones.md) (runtime pins), [roadmap](../roadmap.md),
  [limitations](../limitations.md), [language specification](../language-spec.md).

## Executive summary

The maintainer wants NEXORA to stop depending on Python: the interpreter would be written in NEXORA
itself. This decision records how to get there in stages, what the language still lacks to make it
possible and, above all, what it does **not** solve.

A program in any language needs something underneath that executes it. An interpreter written in
NEXORA can only be started by another implementation that already exists. Until a second,
non-Python way to execute NEXORA exists, the Python interpreter stays in the loop as the bootstrap.
This decision therefore covers the work that is useful under either outcome (stages 0 to 3) and
leaves the removal of Python (stage 4) as an explicit, later decision.

## 1. Purpose and decision status

Moving the implementation language is cheaper before the language grows than after. The maintainer
prefers to pay that cost now.

This decision is **proposed**. It becomes accepted when the maintainer approves it. It does not
change the 1.0 scope of [0021](0021-alcance-nexora-1-0.md) until then, and it does not remove or
deprecate anything that exists.

## 2. Current baseline

- The reference interpreter is Python. The core of the pipeline is about 6,500 lines: lexer,
  parser, checker (the largest part), interpreter, types and syntax tree. The command line, the
  language server and the analysis tools are about 5,000 more.
- The PyPI package is Python. The npm package is a launcher that requires Python 3.11 or newer.
- The Playground runs the Python interpreter inside a Docker worker.
- Equivalence with published releases is already tested: golden files for the examples, the
  118-program corpus used for the 0.11.0 equivalence and the diagnostics table.

## 3. What a NEXORA program cannot express today

Source: section 13 of the language specification. Each item is classified by whether the
self-hosted interpreter needs it.

| Missing | Needed? | Why |
|---------|---------|-----|
| Maps | Yes | Environments, symbol tables, function tables. Without them every lookup is a linear scan of a list. |
| Remainder operator `%` | Yes | Hashing and position arithmetic. |
| Text operations beyond `length`, `slice`, `contains`, `starts_with` and `ends_with` | Yes | A lexer needs to classify a character (digit, letter, space) and to build texts without quadratic copying. The exact set is a stage 1 deliverable. |
| Reading the standard input to the end, and writing without a line break | Yes | Reading a source file and printing diagnostics are the interpreter's job. |
| A way to set the process exit code | Yes | The command line contract in section 11.5 of the specification. |
| Call depth beyond 1000 nested calls | **Yes, and it is the most dangerous item** | A recursive-descent parser and a tree-walking evaluator recurse in proportion to the nesting of the program they process, and each nested call of the interpreted program costs several calls of the interpreter. The limit `E3004` is today "a consequence of the current implementation, not a desired rule" (decisions index). |
| Functions as values | No | Dispatch can be done with `match` over enums. |
| Text interpolation, multi-line texts, block comments | No | Comfort only. |
| `break` and `continue`, `if` as an expression | No | Comfort only. |
| User generics | No | `List[T]` of records and enums is enough. |

Enums and exhaustive `match` (specification section 4.8) cover the largest need: tokens and syntax
tree nodes are exactly that. They are a prerequisite of this decision and are not repeated here.

Immutable lists are not a blocker but a cost: appending copies the list, so building a token list
is quadratic. This is acceptable for a bootstrap and must be measured before it is accepted as the
final design.

## 4. Decision

NEXORA will gain a **self-hosted implementation**, in these stages. Each stage ends with evidence,
and a stage does not start before the previous one is solid.

### Stage 0 — this decision

Agree on the plan, the equivalence criteria below and the prerequisites.

### Stage 1 — minimal language prerequisites

Add only what section 3 marks as needed, as separate, individually specified and tested language
changes under the compatibility policy. The call-depth limit is handled first, because it decides
whether the rest is feasible at all: either the limit is raised in a controlled way, or the
interpreter is written so that its recursion depth does not grow with the program it runs. The
choice is a stage 1 design question, to be answered with a measurement.

Stage 1 has an explicit stop condition. The depth measurement writes a small recursive NEXORA
program shaped like a parser and evaluator and records the largest nesting it can process. If the
result cannot handle the deepest program in the corpus and neither raising the limit nor bounding
the recursion is acceptable under the compatibility policy, the plan stops there and the maintainer
reopens this decision, with the alternatives of section 4.1 on the table.

Nothing outside section 3 is added "for the interpreter". A feature that the self-hosted code does
not use is not part of this stage.

### Stage 2 — the front end, then the interpreter, in NEXORA

Written in this order, each one usable on its own:

1. Lexer.
2. Parser, producing the same tree as `nex inspect`.
3. Checker, producing the same diagnostics (codes, positions and text).
4. Interpreter, including contracts, `example` and the resource limits.

The command line, the language server and the analysis tools stay in Python for the whole of this
stage. They are not part of the interpreter's contract.

### Stage 3 — fixed point

The NEXORA interpreter, run by the Python one, runs its own source and produces the same output as
the Python interpreter does. Then it runs itself running itself, with the same result.

### Stage 4 — leaving Python (not decided here)

The self-hosted interpreter running on the Python interpreter is much slower than the Python
interpreter alone. Removing Python from the loop needs a second way to execute NEXORA that is not
Python: a bytecode virtual machine or a code generator written in some other language, or a
generator that emits a self-contained executable. This is a separate decision, because it
reintroduces the question of which language is underneath. It is taken once stages 2 and 3 give
real measurements.

## 4.1 Alternatives considered

| Alternative | Why it was not chosen |
|-------------|-----------------------|
| A native runtime written in another language (for example Rust) that replaces the Python interpreter first | It removes Python sooner and runs faster, and it does not depend on new language features. The maintainer ruled it out because the goal is for the implementation to be written in NEXORA itself, not in a different host language. Its cost is that it keeps a second language in the project permanently. It stays available as an option for stage 4. |
| Keep the Python interpreter and stop | Cheapest, and the 1.0 scope of [0021](0021-alcance-nexora-1-0.md) does not require anything else. Ruled out by the maintainer's goal of not depending on Python. |
| Compile NEXORA to JavaScript or WebAssembly | Listed as under research in the roadmap. It moves execution to another platform instead of removing the dependency on a host language, and it is a larger design. |
| Write the whole toolchain, including the command line and the language server, in NEXORA at once | Those parts need file system, process and protocol features the language does not have, and they are not part of the interpreter's contract. They are deferred. |

## 5. Equivalence criteria

The self-hosted implementation is accepted as equal to the reference only when, for the whole
test corpus:

1. It accepts and rejects the same programs.
2. For every rejected program it reports the same diagnostics: code, severity, position and message.
3. For every accepted program it produces the same standard output, standard error and exit code,
   including runtime errors and contract violations.
4. `nex inspect` output for the same program is identical, ignoring only fields documented as
   implementation details.
5. The golden files and the 118-program corpus pass without changes to their expected output.

A difference is a bug in the new implementation unless the specification says otherwise. A
specification change needs its own decision.

## 6. What this does not do

- It does not remove Python from the project at the end of stages 0 to 3.
- It does not make NEXORA faster. It will be slower until stage 4.
- It does not change the 1.0 scope, the supported platforms or the public interfaces of
  [0021](0021-alcance-nexora-1-0.md).
- It does not move the Playground, the npm launcher or the language server.

## 7. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| The call-depth limit makes the interpreter unusable on moderately nested programs | Measure it in stage 1, before writing the parser. Stop the plan there if neither option works. |
| Quadratic list building makes even small programs slow | Measure on the corpus in stage 1. Add a text builder or a list operation if the numbers justify it. |
| The language grows features only the interpreter uses | The rule of section 4, stage 1: nothing outside section 3. |
| Two implementations drift apart | Section 5 criteria run in the continuous integration for every change to either one. |
| The bootstrap stays forever | Stage 4 is a recorded open decision, with the reason stated. |
| The work competes with the 1.0 gates | Stages are independent of 0021. The maintainer decides the order. |

## 8. Explicitly deferred

- The choice of the non-Python way to execute NEXORA (stage 4).
- Moving the command line, the language server and the analysis tools.
- Performance work on the self-hosted interpreter.
- A package for the self-hosted interpreter.

## 9. Resolution

Proposed. To accept it, the maintainer approves the staged plan and the criteria of section 5. Stage
1 starts with the call-depth measurement.
