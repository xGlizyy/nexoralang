# Roadmap

What is done, what is being done and what is left. There are no dates: each thing starts when the
previous one is solid.

## Criteria

| Status | It means that… |
|--------|----------------|
| **Completed and verified** | It works, it has automated tests that pass and its documentation describes its real behaviour |
| **In development** | It partly exists; what is missing is stated |
| **Planned** | It does not exist. There is a clear idea of what to build |
| **Under research** | It does not exist and it is not decided what it should be like, or whether it should exist |

A file existing does not count. A feature is only "completed" if it can be run and
there is a test that fails if it stops working.

## NEXORA 1.0 scope

NEXORA 1.0 targets small, single-process CLI tools and local automation written and run by trusted
operators. Web servers and multi-user services are out of scope. The accepted [product scope and
release criteria](decisions/0021-alcance-nexora-1-0.md) define the platform target, stable interfaces
and evidence required for a 1.0 release. Roadmap items are not automatically 1.0 blockers unless
that decision or an approved reference application requires them.

## Completed and verified

| Item | How it is verified |
|------|--------------------|
| Lexer and parser, with error recovery | `tests/test_lexer.py`, `tests/test_parser.py` |
| Types `Int`, `Float`, `Bool`, `Text`, `Void`; inference and annotations | `tests/test_types.py` |
| Immutable **lists** `List[T]`, with literals, equality and `List.length`, `List.get`, `List.append`, `List.concat` and `List.contains` | `tests/test_type_lists_syntax.py`, `tests/test_type_lists_values.py`, `tests/test_type_lists_functions.py` |
| Arithmetic, comparisons and logical operators | `tests/test_types.py`, `tests/test_interpreter.py` |
| Explicit conversions (`to_float`, `to_int`, `to_text`) | `tests/test_types.py` |
| Immutable (`let`) and reassignable (`var`) variables, blocks and scopes | `tests/test_checker.py`, `tests/test_loops.py` |
| **`while` loops** with their measure (`shrinks`) and invariants (`keeps`), checked on every iteration | `tests/test_loops.py` |
| **`for` over lists**, with an immutable iterator, invariants and per-iteration scopes | `tests/test_for.py` |
| **Operations on texts**: `Text.length`, `Text.slice`, searching, ordering between texts and reading numbers (`Int.parse`, `Float.parse`), with their requirements checked on every call | `tests/test_text_operations.py` |
| Functions with parameters, `return`, return paths, recursion | `tests/test_functions.py` |
| `if` / `else if` / `else` | `tests/test_functions.py` |
| **Contracts** (`needs`, `promises`, `trust`) in the header of the function since 0.12; before, `requires` and `ensures` from 0.3.0 | `tests/test_contracts.py` |
| **`nex migrate`**, which rewrites a 0.11 program in the syntax of 0.12, and the equivalence with the published 0.11.0 of the migrated programs (0.12.0, [decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)) | `tests/test_migrate_edits.py`, `tests/test_migrate_files.py`, `tests/test_migrate_cli.py`, `tests/test_equivalence_011.py` |
| **`nex check --evidence`**: the enforcement of every clause, as text and as `nexora.evidence/1` (0.12.0) | `tests/test_evidence.py` |
| **Explanation of every rule**, shown in the diagnostic when it is broken | `tests/test_contracts.py`, `tests/test_refined_types.py` |
| **Refined types** (`type ... where ...`): constants checked without running, `Type(x)` when running, chains of types | `tests/test_refined_types.py` |
| **Examples in functions** (`example`), evaluated with `nex test` | `tests/test_example_clauses.py`, `tests/test_nex_test.py` |
| Running out of memory while running as an error of the program (`E3007`) | `tests/test_out_of_memory.py` |
| No loop keeps repeating forever: it stops with `E4006`, also in `nex test` | `tests/test_loops.py` |
| Static analysis separate from execution | `tests/test_checker.py`, `tests/test_security.py` |
| Interpreter | `tests/test_interpreter.py` |
| Diagnostics with code, category and position, as text and JSON | `tests/test_diagnostics.py`, `tests/test_cli.py` |
| **Warnings**: unused variables, a `var` that is never reassigned and names outside `snake_case`, without stopping the program | `tests/test_warnings.py` |
| Commands `nex run`, `nex check`, `nex inspect` | `tests/test_cli.py` |
| JSON representation of the program (`nexora.inspect/3`) | `tests/test_inspect.py` |
| Symbols and references (`nex symbols`) and summary of the program (`nex context`) | `tests/test_tooling.py` |
| Versioned JSON formats, with JSON Schemas generated from the code | `tests/test_tooling.py` validates the real output with them |
| Partial tree, symbols and summary when the program has syntax errors | `tests/test_tooling.py`, including the program cut at every character |
| Reference tasks for the analysis tools | `tests/test_tooling_tasks.py` |
| Runnable examples with recorded output | `tests/test_examples.py` |
| **Public web Playground (NEXORA 0.14.0)** | Live at [nexoralang.org/playground](https://nexoralang.org/playground); supports Check, Run, multi-file projects, entry-file selection and statement debugging with breakpoints. Staging and production passed the release verifier; interpreter debugger coverage is in `tests/test_worker.py` |
| Documentation in sync with the implementation | `tests/test_docs.py` |
| Resistance to wrong, huge or truncated inputs | `tests/test_robustness.py` |
| Package installable locally | Checked by hand on Windows; see [testing](testing.md#packaging) |
| **Other editor clients for the LSP** | Neovim, Helix and Emacs configs and LSP smoke-tested; Neovim/Emacs highlighting and the generated Helix grammar are checked, with token catalogs tied to the lexer and checker ([LSP](lsp.md#other-editors)) |

## In development

| Item | What there is | What is missing |
|------|---------------|-----------------|
| **VS Code extension distribution** | The 0.14.0 VSIX is attached to the GitHub release | It is not listed on the Visual Studio Code Marketplace |
| **Python API** (`nexora.tooling`) | Implemented and tested (`tests/test_tooling.py`) | Declaring it stable. Today it is experimental and may change |
| **MCP server** (optional) | Seven analysis tools, tested with the client of the official SDK (`tests/test_mcp.py`). Checked by hand once in Claude Code. It does not run code | Testing it in other assistants. Including the specification in the installable package |
| **Continuous integration** | GitHub Actions runs the Python test suite on Python 3.11, 3.12 and 3.13 on Linux, Windows and macOS | Manual smoke checks on native Linux and macOS machines remain (see platform verification below) |
| **Optional values and results** | `Option[T]` and `Result[T, E]`, with `Some`, `None`, `Ok` and `Err`, and the functions that recognize the variant and read the value. No `match` or `?` | `match`, `if let` and the `?` operator, when there are user enums |
| **Verification on other platforms** | Checked on Windows 11 with Python 3.12; run on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13 by the continuous integration | Checking it on macOS and on Linux on a real machine, not only on the runners |
| **Readiness for contributors** | MIT licence, contribution guide, security policy, code of conduct, public repository with its issue tracker | Defining a private contact channel |

## Main line: verifiable requirements

The feature that distinguishes NEXORA is that the requirements of a function are a verifiable part
of the program ([decision 0006](decisions/0006-requisitos-verificables.md)). It is the
priority of the project. Its work goes in this order, and each step starts when the previous one is
solid:

| # | Step | Status |
|---|------|--------|
| 1 | **Stabilizing contracts** (`requires`, `ensures`): fixing their position in the code and the name `result`, and no longer marking them as experimental | **Completed in 0.3.0** ([decision 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)) |
| 2 | **A natural-language explanation attached to every condition**, which appears in the diagnostic when the condition is broken | **Completed in 0.3.0**, in contracts and in refined types |
| 3 | **Concrete cases in the function (`example`)** and a command that runs them without writing `main` | **Completed in 0.4.0** ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| 4 | **Warning when an edit removes or weakens a requirement** | Under research: it is not decided how to detect that a condition is weaker than another one |
| 5 | **Refined types** (`type Percent = Int where ...`) | **Completed in 0.3.0** over the built-in types. Refining records is missing: it is not implemented |
| 5b | **Loop requirements**: the measure (`decreases`) and the invariants (`invariant`), with their explanation, checked on every iteration | **Completed in 0.5.0** ([decision 0010](decisions/0010-var-y-while.md)) |
| 6 | **Evaluating whether requirements in the code help an AI agent** not to break them | Planned; see the last row of [Under research](#under-research) |
| 7 | **Promises with an identity, and what backs each one** ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)): the clauses in the header of the function, names, `trust`, and the evidence of every clause | **Phase 1 completed in 0.12.0**: the syntax, `nex migrate` and the enforcement (`nex check --evidence`). Planned: what the examples observe (`nex test --evidence`, 0.13.0), `nex impact` (0.15.0) and deciding a `needs` at the call sites with constants (later) |

Until step 6 gives results, the feature is a hypothesis and is not presented as a
proven advantage.

## Planned

The rest of the language, in the order in which it would make sense to tackle it. It moves forward together with the main
line; when a point of this list is needed for a step of the main line, it goes
first:

1. ~~**Operations on texts**~~: done in 0.6.0 ([decision 0011](decisions/0011-operaciones-sobre-textos.md)).
2. ~~**A first compound type: lists**~~: done in 0.7.0, with `for` over lists ([decision 0013](decisions/0013-listas-y-for.md)). The type model and lists are described in the [specification](language-spec.md), sections 4.5, 8.2 and 9.6.
3. ~~**Records**~~: done in 0.8.0, with nominal identity and immutable fields ([decision 0014](decisions/0014-registros-nominales-inmutables.md)); they are described in the [specification](language-spec.md), section 4.6. What remains is **optional values** (`Option`, `Result`), to represent the absence of a
   value and errors without exceptions.
4. ~~**Data input and host capabilities**~~: arguments, standard input and files in 0.9.0 ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)); bounded HTTPS reads and explicitly granted external processes in 0.13.0 ([decision 0020](decisions/0020-red-y-procesos-externos.md)).
5. ~~**Modules and imports**~~: done in 0.11.0 ([decision 0018](decisions/0018-modulos-e-importaciones.md)).
6. ~~**Warnings** (unused variables, a `var` that never changes) and naming conventions~~:
   done in 0.12.1 (`W2001`, `W2002`, `W2003`).
7. **More tolerant analysis**: keeping the functions whose declaration has an error, and giving
   structure also with lexical errors. The partial tree with syntax errors already exists.
8. ~~**Language server (LSP)** and **formatter**~~: done with the VS Code extension
   ([decision 0017](decisions/0017-un-editor-la-extension-de-vs-code.md)). The 0.14.0 LSP resolves
   relative imports across the open project and negotiates UTF-8, UTF-16 and UTF-32 positions.
   Remaining editor-specific limitations are in [LSP](lsp.md#limitations).

## Original design phases

Current implementation status of the phases in the original design document. This list records
historical project phases; it does not expand the accepted 1.0 scope above.

| Idea | Open question |
|------|---------------|
| Static verification of contracts | Which part can be proven without a full prover, and without giving false guarantees? |
| Weakened requirements between two versions of a function | How to know, without a prover, that a new condition is weaker than the previous one? Is it enough to warn when a condition disappears or changes? |
| Declared effects (`uses`) | Is the burden of annotating them worth it? |
| Functions resolved by an AI model (`ai fn`, `tool fn`) | Can a deterministic language incorporate an operation that is not, and how is it tested? |
| Structured edits in diagnostics | Which format would allow applying a fix automatically and safely? |
| **The central hypothesis of the project** | When an AI modifies a function, are more violations detected if the requirements are written in the code than if they are only in the instruction? **It has not been evaluated.** The experiment is described in [decision 0006](decisions/0006-requisitos-verificables.md#how-we-will-know-whether-it-works); the [reference tasks](ai-tooling.md#reference-tasks) are its starting point |
| Running programs through MCP | With which isolation and under which explicit activation? Today the server only analyzes |
| Compilation to JavaScript or WebAssembly | The original draft proposed it; today only an interpreter exists, and the playground runs on the server |

## History of phases

| Phase | Goal | Result |
|-------|------|--------|
| 1 | Core: lexer, parser, interpreter, CLI, diagnostics | Completed (version 0.1.0) |
| 2 | Type system, functions, contracts, JSON outputs | Completed (version 0.2.0); contracts remain experimental |
| 3 | Documentation, tests and quality | Implemented; CI runs the Python suite on Python 3.11, 3.12 and 3.13 across Linux, Windows and macOS. Native Linux/macOS smoke checks remain |
| 4 | Playground: web editor that runs with the real interpreter | Live in production at NEXORA 0.14.0; multi-file projects and statement debugger are available. Docker isolation passed the staging and production release verifier |
| 5 | Tools for agents: JSON protocol, `nex context`, `nex symbols`, Python API, MCP server | Implemented and tested locally, also the language server of the editor; no AI model has been evaluated |
| 6 | Verifiable requirements: stable contracts, explanation of the rules and refined types | Completed (version 0.3.0). Examples (step 3) arrived in 0.4.0; steps 4 and 6 of the [main line](#main-line-verifiable-requirements) remain |
| 7 | Repetition without recursion: `var` and loops that declare why they end and what they keep true | Completed (version 0.5.0) |
| 8 | An identity of its own: promises in the header, `trust`, evidence per clause and `nex migrate` ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), phase 1) | Completed (version 0.12.0), with the equivalence tests against the published 0.11.0 green in the continuous integration. Phases 2 to 4 of the decision remain |

The website of the project (<https://nexoralang.org>, whose code is in a separate private repository)
shows a summarized version of this roadmap. This document is the reference.
