# Technical decisions

Record of the design decisions of NEXORA: what was decided, why, what was ruled out and what
changes for whoever already has programs written. Every decision has a number and is not rewritten: if
a decision is revisited, another one that replaces it is added and both say so.

A decision keeps the syntax of its time: its programs are not rewritten when the language changes.
Since 0.12 the syntax is the one of [0019](0019-identidad-propia-del-lenguaje.md), and the decisions
whose rules it replaces say so at the top.

| No. | Decision | Status | Incompatible with 0.1 |
|-----|----------|--------|-----------------------|
| [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) | Static types, without implicit conversions; `String` is renamed `Text` | Accepted | Yes |
| [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) | The interpreter only runs checked programs | Accepted | No |
| [0003](0003-funciones-retorno-e-if.md) | Functions with an explicit `return`, a single namespace and `if` as a statement | Accepted (the form of the result type replaced by 0019 in 0.12) | No |
| [0004](0004-contratos-en-ejecucion.md) | Contracts at the beginning of the body, checked at run time | Accepted (stable since 0007; position and words replaced by 0019 in 0.12) | No |
| [0005](0005-diagnosticos-y-esquemas-json.md) | Diagnostic categories, versioned JSON schemas and exit code 5 | Accepted | Yes |
| [0006](0006-requisitos-verificables.md) | Distinguishing feature: requirements are a verifiable part of the program | Accepted | No |
| [0007](0007-contratos-estables-y-tipos-refinados.md) | Stable contracts, explanation of the rules and refined types | Accepted (the syntax of contracts replaced by 0019 in 0.12) | No |
| [0008](0008-ejemplos-y-nex-test.md) | Examples in functions (`example`) and the `nex test` command | Accepted (the place of `example` replaced by 0019 in 0.12) | No |
| [0009](0009-memoria-agotada.md) | A program that runs out of memory while running: diagnostic `E3007` | Accepted | Yes |
| [0010](0010-var-y-while.md) | Reassignable variables (`var`) and loops with requirements (`while`, `invariant`, `decreases`) | Accepted (`keeps` and `shrinks`, in the header, since 0019 in 0.12) | Yes |
| [0011](0011-operaciones-sobre-textos.md) | Operations on texts: functions associated with a type (`Text.length`, `Int.parse`) that declare their requirements | Accepted (the requirements are called `needs` since 0019 in 0.12) | No |
| [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) | Type model, records, patterns, enumerations, `Option`/`Result`, lists, `for`, input, modules and verifiable evidence | Proposed (not accepted; 0013 accepts only D01, D08 and D09 within the implemented scope) | No |
| [0013](0013-listas-y-for.md) | `List[T]` lists, `for` over lists and the type model that supports them: accepts D01, D08 and D09 within the implemented scope | Accepted (`keeps` in a `for` since 0019 in 0.12) | No |
| [0014](0014-registros-nominales-inmutables.md) | Immutable nominal records: `type X = { ... }` declaration, construction with named fields, field access and nominal identity by declaration | Accepted | No |
| [0015](0015-entrada-argumentos-archivos-y-permisos.md) | Input, arguments, files and permissions: `args()`, `input()`, `read_file()`, `write_file()`, `uses` declarations and permissions granted by whoever runs the program | Accepted | No |
| [0016](0016-option-y-result.md) | `Option[T]` and `Result[T, E]`: `Some`, `None`, `Ok` and `Err`, with functions that recognize the variant and read the value, without exceptions | Accepted (`value` and `value_or` since 0019 in 0.12) | No |
| [0017](0017-un-editor-la-extension-de-vs-code.md) | One editor: the VS Code extension, with its language server and its formatter, built on the analyzer of the language itself | Accepted | No |
| [0018](0018-modulos-e-importaciones.md) | Modules and imports: `import "path/file.nex"`, one namespace per file, privacy with `pub` and circular imports forbidden | Accepted | No |
| [0019](0019-identidad-propia-del-lenguaje.md) | An identity of its own: promises in the header (`needs`, `promises`, `gives`), named promises, evidence per promise, `trust`, `nex migrate` and `nex impact` | Accepted. Phase 1 published in 0.12.0; phases 2 to 4 not started | Yes |

## Possible incompatible changes in the future

Decisions that will probably have to be revisited and that would affect existing programs:

- **Unused variables and naming conventions.** The design draft treats them as errors.
  They are warnings since 0.12.0 (`W2001` and `W2003`), so a program that is valid today stays
  valid. Making them errors would be an incompatible change.
- **`+` between texts (0001).** It exists because there is no interpolation. When there is, it could be withdrawn.
- **`if` as an expression (0003).** If `if` comes to produce a value, the rule of "expression used
  as a statement" (`E2010`) will have to be revisited.
- **Limit of 1000 nested calls.** It is a consequence of the current implementation, not a
  desired rule of the language.
