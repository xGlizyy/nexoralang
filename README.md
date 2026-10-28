# NEXORA

An experimental programming language built around explicit requirements and checkable contracts.

NEXORA is its own language, with its own syntax, type checker and interpreter. The reference
interpreter is implemented in Python; programs are NEXORA programs, not Python translations.

**Version 0.14.0, published on PyPI and npm · Early-stage, pre-1.0.** The supported language is a
subset of the full design and may change incompatibly. NEXORA programs are not recommended for
production software. The public Playground is live in production at the same interpreter version;
that describes the hosted service, not the maturity of the language for production applications.

## What works today

- **Language and CLI:** static checking and interpretation, functions, lists, records, modules,
  `Option` and `Result`, refined types, examples, and function contracts. The CLI includes `run`,
  `check`, `test`, `inspect`, `context` and `symbols`. See the [implemented language and status](nexora/README.md).
- **Diagnostics:** type and syntax errors explain the problem and include stable codes and hints.
- **Editor support:** a shared Language Server Protocol (LSP) server provides diagnostics,
  completion, hover, navigation, rename, symbols, signature help and formatting. Ready-to-use
  configurations are available for [Neovim, Helix and Emacs](editor-integrations/); the
  [Visual Studio Code extension](vscode-nexora/) uses the same language tools. The LSP resolves
  relative imports across the open project and negotiates UTF-8, UTF-16 or UTF-32 positions with
  the editor.
- **Web Playground:** [write, check and run NEXORA online](https://nexoralang.org/playground),
  with multi-file projects, an explicit entry file and a statement-by-statement debugger. The
  production service runs NEXORA 0.14.0 in a Docker worker; network and external-process
  capabilities are unavailable to Playground programs.
- **AI tooling:** optional context and symbol tools, a Python API and an experimental MCP server.
  NEXORA does not call AI models. The MCP server's compatibility has only been checked with the
  official SDK client and manually in Claude Code; see [AI tooling](nexora/docs/ai-tooling.md).

The [design document](docs/fase-1-diseno.md) describes the larger language being explored. It is a
proposal, not a promise that every feature already runs. See the current [limitations](nexora/docs/limitations.md)
and [roadmap](nexora/docs/roadmap.md) before relying on a feature.

## Install

The interpreter needs Python 3.11 or newer. Install the published package from PyPI:

```bash
python -m pip install nexora-lang
nex --version
```

The `nexora-lang` package is also available on npm as a launcher; it still requires Python 3.11 or
newer. Installation details and troubleshooting are in the [NEXORA guide](nexora/docs/installation.md).

## First program

Save this as `hello.nex`:

```nex
fn main() {
    print("Hello from NEXORA")
}
```

Then run it:

```bash
nex run hello.nex
```

## Project map

- [`nexora/`](nexora/): reference interpreter, CLI, language server, documentation and tests.
- [`editor-integrations/`](editor-integrations/): configuration and syntax highlighting for Neovim,
  Helix and Emacs.
- [`vscode-nexora/`](vscode-nexora/): Visual Studio Code extension.
- [`npm/`](npm/): npm launcher for the Python interpreter.
- [`docs/fase-1-diseno.md`](docs/fase-1-diseno.md): proposed language design.
- [`docs/roadmap.md`](nexora/docs/roadmap.md): project roadmap.

The website and Playground server live in a separate private repository; the language implementation
and its documentation are here.

License: [MIT](LICENSE).
