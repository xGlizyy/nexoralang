# 0017 — One editor: the VS Code extension

- **Status:** accepted
- **Version:** 0.10.0 (state of the repository; the extension is distributed separately, in its own `.vsix`)
- **Date:** 2026-10-22
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0005](0005-diagnosticos-y-esquemas-json.md) (diagnostics
  have a stable code and category) and [0013](0013-listas-y-for.md) (the type model that
  supports the checking). **It modifies neither.**
- **Implementation:** the language server and the formatter are in the core
  (`nexora/src/nexora/lsp.py` and `nexora/src/nexora/formatter.py`), and the extension, in TypeScript, in
  `vscode-nexora/`. The evidence is in `tests/test_lsp.py`, `tests/test_formatter.py` and
  `tests/test_vscode_extension.py`.

## Context

NEXORA is used today from the command line (`nex check`, `nex run`, `nex test`) and from the
browser (the playground). The tool every programmer starts from is missing: the editor.

Writing an editor for NEXORA without the analyzer would mean writing an analyzer twice. The
language already has everything an editor needs: a lexer, a parser, a
checker of names and types with its diagnostics, and a symbol table with the
references of every name. [Decision 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
already requires everything that runs to go through the checker; an editor that did not use it
would give different diagnostics from those of the command line, and two truths about the same
program.

## Decision

### 1. The language server is a Python process of the package itself

`python -m nexora.lsp` speaks LSP over the standard input and output. It is the same pattern as
the [MCP server](../mcp.md) of the project, and it uses the standard library: it needs nothing
installed to work.

The server **does not reimplement the language**. Everything it answers comes from
`pipeline.analyze`, the same path that `nex check` uses, so the code of a diagnostic
(E2011, E3004…), its category, its position and its suggestion are the same.

### 2. The extension is TypeScript and only talks to the server

`vscode-nexora/` is an ordinary VS Code extension: the protocol client, the
language, the grammar and the commands. It contains not a single line of language analysis.

### 3. The grammar is written over the real lexer

The TextMate grammar names the keywords, the types, the built-in functions and the
reserved words **that the language has today**, and a test checks that the grammar and the
lexer do not drift apart. A `.nex` file is recognized without anyone declaring it.

### 4. The formatter lives in the language, not in the extension

`nexora/src/nexora/formatter.py` rewrites a program with the canonical shape. It works on
the **tokens of the lexer**, never on the text: only indentation and spacing change, so
the program means the same. It does not join or split lines (the language is written line by
line), it does not rewrite the inside of a text and it does not touch comments.

A formatter in the extension would have been a formatter in TypeScript, with a second
lexer to maintain.

### 5. What the editor offers

| | |
|---|---|
| Diagnostics | Those of `nex check`, in the *Problems* panel |
| Completion | Keywords, built-in functions, the names in scope and the reserved words |
| Hover | The type of a value and the signature of a function |
| Go to definition, references, rename | On functions, parameters and variables |
| Document symbols | Functions and variables, with their type |
| Signature help | The parameters of the function being called |
| Formatter | Whole document or selection; optionally on save |

## Facts verified in the repository

| Fact | Where |
|------|-------|
| The checker knows the type of every expression and every symbol with its references | `checker.py` (`CheckedProgram`) |
| Diagnostics have a code, category, position and suggestion | `diagnostics.py` |
| The MCP server is already an external process of the package itself | `mcp_server.py` |
| The grammar and the manifest are checked against the lexer | `tests/test_vscode_extension.py` |

## Decisions taken here, and why

| Decision | Why |
|----------|-----|
| The server in Python, the extension in TypeScript | Reusing the analyzer is what makes the diagnostics the same; the extension is what VS Code expects |
| No Python dependencies | The server is written with the standard library: a server that does not need installing is a server that always works |
| The formatter in the core | A single formatter, reusable from the command line, and one that by construction does not break the syntax |
| The grammar checked against the lexer | If the language adds a keyword, the test fails until the grammar names it |
| The server decides the format | The extension only decides whether it is used: the canonical format is a decision of the language |

## What it does not guarantee

- The analyzer does not yet resolve the members of a record by type, so navigation and
  renaming do not reach the fields of a record.
- There is no completion with type variables: the error type of an `Ok` is given by the context, and the
  formatter makes nothing up.
- The formatter does not reformat a text, does not move comments and does not rewrite the structure of
  a program: only indentation and spacing.
- The extension does not bring the `nexora` package installed: a Python with the package is needed
  (or the `nexora.python.path` setting).

## Out of scope

- Other editors (Neovim, Emacs, JetBrains): the server speaks LSP, so what is missing is the
  client, not the server.
- A language server for the MCP server: it is another protocol and another integration.
- Formatting comments, or rewriting the inside of a text.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| Writing the analyzer in TypeScript | It would be a second analyzer, with other diagnostics; the project already has its own |
| The server in Node, with the analyzer invoked as a separate process | Every answer would cost a process and an analysis; the server in Python has the analyzer in the same memory |
| A formatter in the extension | It would duplicate the formatter and would be the only one that does not know the grammar of the language |
| Highlighting written by hand without checking it | The grammar would drift from the language at the first new keyword |

## Compatibility

- The language does not change: the formatter only rewrites the shape, and the tests check that
  the tokens of a formatted program are the same as before formatting it.
- The diagnostics of the editor are those of the command line, with the same codes.
- The extension does not modify the package that is published: it lives in `vscode-nexora/` and is distributed
  as a separate `.vsix`.

## Required changes

- `nexora/src/nexora/lsp.py`: the language server.
- `nexora/src/nexora/formatter.py`: the formatter.
- `nexora/pyproject.toml`: the `nexora-lsp` command.
- `vscode-nexora/`: the extension, with its icon (the same brand as the site) and what the marketplace
  asks for: licence, banner, description, categories and keywords.
- `nexora/tests/test_lsp.py`, `test_formatter.py`, `test_vscode_extension.py`: the tests.

## Planned regression tests

| File | What it pins down |
|------|-------------------|
| `tests/test_lsp.py` | That the diagnostics of the server are those of `nex check`, and that completion, hover, definition, references, rename, symbols, signature and formatting answer what they should |
| `tests/test_formatter.py` | That the formatter does not change what a program means (the same tokens), that it is idempotent and that it copes with all the examples of the repository |
| `tests/test_vscode_extension.py` | That the manifest and the grammar follow the lexer |

## Relation to the previous decisions and the index

It is added to the decision index as accepted. It modifies none: it uses the analyzer that the
previous decisions defined.

## Questions that remain open

- Should the server resolve the fields of a record by type, so that navigation
  reaches them? It depends on the analyzer, not on the editor.
- A formatter that reorganizes blocks, like the one some languages have? The language
  is written line by line and with one block per construct; reorganizing it would be deciding about the
  language, not about the tool.
