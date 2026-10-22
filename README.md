# NEXORA

A web-oriented programming language designed for AI-powered development.

State: There is an interpreter (version 0.10.0) that executes a subset of the language: static types, immutable (`let`) and reassignable (`var`) variables, functions with parameters and return values, `if`/`else`, recursion, `while` loops that declare why they terminate (`decreases`) and what they maintain (`invariant`), immutable lists `List[T]` with `List.length`, `List.get`, `List.append`, `List.concat` and `List.contains`, `for` loops on lists, immutable registers (`type Point = { x: Int, y: Int }`) with nominal identity, program arguments (`args()`), standard input (`input()`) and files with explicit permissions (`uses read "path"` and `--allow-read=path`), operations on text (`Text.length`, `Text.slice`, `Int.parse`) which declares its requirements, contracts (`requires`, `ensures`), and refined types (`type Percent = Int where ...`), each rule with its explanation, and examples in the functions (`example`) that `nex test` evaluates. The rest of the design is not yet implemented.

What distinguishes NEXORA: a program's requirements are written in the code itself and checked deterministically ([decision 0006](nexora/docs/decisions/0006-verifiable-requirements.md)).

- [nexora/](nexora/): the core of the language. Interpreter, `nex` command, documentation ([nexora/docs/index.md](nexora/docs/index.md)), executable examples, and tests. It starts with [nexora/README.md](nexora/README.md).

- [.github/workflows/nexora-ci.yml]: Continuous integration of the core for GitHub Actions. It runs on every change to `main`, on Linux, Windows, and macOS.

- [docs/fase-1-diseno.md]: Draft of the complete design (syntax, types, functions, and rules). It describes where the language is headed, not what works today.

- [ejemplos/tienda.nx] and [ejemplos/soporte_ia.nx]: Examples from the draft design. They use syntax that the interpreter doesn't yet support, so they can't be executed.

- [npm/]: npm package (`nexora-lang`) that installs the `nex` command. Requires Python 3.11 or higher on the machine. Published on PyPI and npm.

- [web/](web/): Language webpage, with the playground (`/playground`) and a guide (`/guide`).

- [server/](server/): Node.js server that hosts the webpage, user accounts (MySQL), and the playground API, which runs each program with the actual interpreter in a separate process. It has only been tested locally: [nexora/docs/playground.md](nexora/docs/playground.md).

- [vscode-nexora/](vscode-nexora/): Visual Studio Code extension for the language: highlighting, diagnostics, navigation, and formatting. Its language server and formatter are those of the core ([decision 0017](nexora/docs/decisions/0017-un-editor-la-extension-de-vs-code.md)).

Tools for AI editors and agents (JSON parsing, `nex context`, `nex symbols`, Python API, and optional MCP server): [nexora/docs/ai-tooling.md]. NEXORA does not call any AI models.

License: [MIT].

## Starting the server

Requires Node.js 22.23.2 or later on branch 22, or 24.18.1 or later on branch 24, and a MySQL or MariaDB database. Use the latest version of your branch.

```
cd server
`npm install`
`cp .env.example .env` # populates the database data
`npm run migrate` # creates the users, sessions, and oauth_accounts tables
`npm start`
```

... ## Login with Google and GitHub

This is optional: without credentials, the buttons lead to a warning, and email registration still works.

1. Create an OAuth application for each provider (the links are in `server/.env.example`).

2. Register `{PUBLIC_URL}/api/auth/google/callback` and `{PUBLIC_URL}/api/auth/github/callback` as the return URLs.

3. Copy the ID and secret of each application to `server/.env` and restart the server.
