# NEXORA

A web-oriented programming language designed for AI-powered development.

State: There is an interpreter (version 0.11.0) that executes a subset of the language: static types, immutable (`let`) and reassignable (`var`) variables, functions with parameters and return values, `if`/`else`, recursion, `while` loops that declare why they terminate (`decreases`) and what they maintain (`invariant`), immutable lists `List[T]` with `List.length`, `List.get`, `List.append`, `List.concat` and `List.contains`, `for` loops on lists, immutable records (`type Point = { x: Int, y: Int }`) with nominal identity, program arguments (`args()`), standard input (`input()`) and files with explicit permissions (`uses read "path"` and `--allow-read=path`), operations on text (`Text.length`, `Text.slice`, `Int.parse`) which declares its requirements, contracts (`requires`, `ensures`), and refined types (`type Percent = Int where ...`), each rule with its explanation, examples in the functions (`example`) that `nex test` evaluates, and multi-file programs with `import "path/file.nex"`, one namespace per module, and `pub`. The rest of the design is not yet implemented.

What distinguishes NEXORA: a program's requirements are written in the code itself and checked deterministically ([decision 0006](nexora/docs/decisions/0006-verifiable-requirements.md)).

- [nexora/](nexora/): the core of the language. Interpreter, `nex` command, documentation ([nexora/docs/index.md](nexora/docs/index.md)), executable examples, and tests. It starts with [nexora/README.md](nexora/README.md).

- [.github/workflows/nexora-ci.yml](.github/workflows/nexora-ci.yml): Continuous integration of the core for GitHub Actions. It runs on every change to `main`, on Linux, Windows, and macOS.

- [docs/fase-1-diseno.md](docs/fase-1-diseno.md): Draft of the complete design (syntax, types, functions, and rules). It describes where the language is headed, not what works today.

- [ejemplos/tienda.nx](ejemplos/tienda.nx) and [ejemplos/soporte_ia.nx](ejemplos/soporte_ia.nx): Examples from the draft design. They use syntax that the interpreter doesn't yet support, so they can't be executed.

- [npm/](npm/): npm package (`nexora-lang`) that installs the `nex` command. Requires Python 3.11 or higher on the machine. Published on PyPI and npm.

- Website: <https://nexoralang.org>, with a guide (`/guide`) and the playground (`/playground`, disabled for now). Its server and webpage live in a separate private repository; this repository holds the language.

- [vscode-nexora/](vscode-nexora/): Visual Studio Code extension for the language: highlighting, diagnostics, navigation, and formatting. Its language server and formatter are those of the core ([decision 0017](nexora/docs/decisions/0017-un-editor-la-extension-de-vs-code.md)).

Tools for AI editors and agents (JSON parsing, `nex context`, `nex symbols`, Python API, and optional MCP server): [nexora/docs/ai-tooling.md](nexora/docs/ai-tooling.md). NEXORA does not call any AI models.

License: [MIT](LICENSE).
