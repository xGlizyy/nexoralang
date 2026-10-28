# Language Server Protocol (LSP)

**Status: implemented.** NEXORA includes a language server, `nexora-lsp`, which the
[VS Code extension](../../vscode-nexora/README.md) uses. It was added with the editor work
([decision 0017](decisions/0017-un-editor-la-extension-de-vs-code.md)) and is tested by
`tests/test_lsp.py`; the formatter it uses, by `tests/test_formatter.py`.

It does not re-implement the language. Every answer comes from the same stages the command line
uses (lexer, parser and checker), so the diagnostics an editor shows are the ones `nex check`
gives, with the same codes and the same texts.

## Starting it

It speaks LSP over standard input and output. It is installed with the `nexora-lang` package and
needs nothing else: it only uses the Python standard library.

```bash
nexora-lsp
python -m nexora.lsp
```

The two commands are the same server. An editor starts it as a child process; it is not meant to
be run by hand.

## Other editors

Any editor with an LSP client can use the same `nexora-lsp` process. Install the Python package
in an environment visible to the editor first:

```bash
python -m pip install nexora-lang
```

The editor must be able to find `nexora-lsp` on its `PATH`. The ready-to-use client configurations
are in [`editor-integrations/`](../../editor-integrations/):

- **Neovim 0.11 or newer** ([LSP config](https://neovim.io/doc/user/lsp)): copy the three files
  under `neovim/` into the matching directories below your Neovim config directory (`stdpath("config")`):
  `lsp/nexora.lua`, `ftdetect/nexora.vim` and `syntax/nexora.vim`. Add this to `init.lua`:
  ```lua
  vim.lsp.enable("nexora")
  ```
- **Helix** ([language config](https://docs.helix-editor.com/languages.html)): append
  `helix/languages.toml` to `languages.toml` in the Helix config directory, then fetch and build
  its Tree-sitter grammar once from a terminal:
  ```sh
  hx --grammar fetch
  hx --grammar build
  ```
  These commands need Git and a C compiler. Restart Helix after the build. The grammar provides
  coloring only; the NEXORA language server remains responsible for diagnostics and language features.
- **Emacs 29 or newer** ([Eglot manual](https://www.gnu.org/software/emacs/manual/html_node/eglot/)):
  load `emacs/nexora-eglot.el` from your Emacs config, for example with
  `(load "/path/to/nexora-eglot.el")`. It defines a small NEXORA major mode with lexical
  highlighting and starts Eglot for `.nex` files. Eglot is included with Emacs 29+; on older
  Emacs versions, install Eglot separately.

Each configuration associates `.nex` files with the same `nexora-lsp` command. The Neovim and
Emacs highlighters and the Helix Tree-sitter grammar color tokens; they do not define or execute
NEXORA. The lexer, parser, checker and interpreter in `nexora-lang` remain the language authority.

## What it offers

| LSP feature | Method |
|-------------|--------|
| Diagnostics (errors and warnings), with the code, the position and the hint | `textDocument/publishDiagnostics`, sent after opening, changing or saving a document |
| Completion: keywords, built-in functions, names in scope and reserved words | `textDocument/completion` |
| *Hover* with the type of a value or the signature of a function | `textDocument/hover` |
| Go to definition, find references, highlight | `textDocument/definition`, `textDocument/references`, `textDocument/documentHighlight` |
| Rename a function, a parameter or a variable | `textDocument/prepareRename`, `textDocument/rename` |
| Document symbols | `textDocument/documentSymbol` |
| Signature help | `textDocument/signatureHelp` |
| Formatting, whole document or a range | `textDocument/formatting`, `textDocument/rangeFormatting` |

- **Synchronization:** full. The editor sends the whole text on every change, and the analysis is
  computed once per version of the document.
- **No `main` needed:** a file without `main` is analysed as `nex test` analyses it, so a module
  does not get `E2001`.
- **No execution:** the server only analyses and never runs a program. It reads files named by
  relative imports using the same rules as the CLI.
- **Errors in a request** are answered with a JSON-RPC error (`-32603`); the server keeps running.
- **Imports:** resolved relative to the importing file with the same module loader as `nex check`.
  Open editor buffers take precedence over disk contents. Imported declarations support hover,
  definition, references and rename across the open project.
- **Position encoding:** negotiated with the client. UTF-16 is the default; UTF-8 and UTF-32 are
  also supported. Source columns are converted at the protocol boundary.

## Limitations

- **Closed imported files** are read from disk. The server does not watch external filesystem
  changes; save or edit an open dependent document to refresh its analysis.
- **With a lexical error** (an unclosed text, the most common thing while typing one) there is no
  syntax tree: diagnostics still work, but *hover*, navigation and symbols have nothing to show
  until the error is fixed. With syntax errors they work on the partial tree, and a function whose
  declaration has an error is missing.
- **The formatter is only reachable through the server.** There is no `nex` command for it.
- The configurations and syntax highlighters have been smoke-tested with Neovim 0.12.6, Helix
  25.07.1 and Emacs 31.1_1. Report editor-specific issues with the editor version and LSP log.

## Without an editor

A script can get the same diagnostics with exact positions by running
`nex check file.nex --format json` ([JSON protocol](json-protocol.md)).
