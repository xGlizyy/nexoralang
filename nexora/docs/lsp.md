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

## What it offers

| LSP feature | Method |
|-------------|--------|
| Diagnostics, with the code, the position and the hint | `textDocument/publishDiagnostics`, sent after opening, changing or saving a document |
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
- **No execution:** the server only analyses. It never runs a program nor opens other files.
- **Errors in a request** are answered with a JSON-RPC error (`-32603`); the server keeps running.

## Limitations

- **Imports are not resolved.** The server analyses the text the editor sends, without the files
  beside it. A file that uses `import` gets `E0001` ("This program imports modules, and they cannot
  be read here"), and the names of the imported modules are not known. `nex check` on the file
  does resolve them.
- **Columns are counted in Unicode characters.** LSP counts them, by default, in UTF-16 units, and
  the server does not negotiate the encoding. Positions are exact for text in the basic plane; on a
  line with characters outside it (an emoji, for example), the columns after that character are off.
- **With a lexical error** (an unclosed text, the most common thing while typing one) there is no
  syntax tree: diagnostics still work, but *hover*, navigation and symbols have nothing to show
  until the error is fixed. With syntax errors they work on the partial tree, and a function whose
  declaration has an error is missing.
- **The formatter is only reachable through the server.** There is no `nex` command for it.
- It has only been used with the VS Code extension; not with other editors.

## Without an editor

A script can get the same diagnostics with exact positions by running
`nex check file.nex --format json` ([JSON protocol](json-protocol.md)).
