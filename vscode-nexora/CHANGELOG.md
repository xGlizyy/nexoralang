# Changelog

## 0.12.1

For NEXORA 0.12.1. The version follows the one of the language.

- The warnings of NEXORA (`W2001`, `W2002`, `W2003`) appear as warnings in the editor. They come from
  the language server of `nexora-lang`; the extension itself does not change.

## 0.12.0

For NEXORA 0.12.0 ([decision 0019](../nexora/docs/decisions/0019-identidad-propia-del-lenguaje.md)).
The version follows the one of the language. It has not been published on the marketplace.

- The highlighting is that of 0.12: `needs`, `gives`, `promises`, `trust`, `keeps` and `shrinks`
  are keywords. `requires`, `ensures`, `invariant` and `decreases` are shown as reserved words,
  because 0.12 rejects them (`E1107`). `ai` and `tool` are ordinary names.
- `->` is no longer shown as an operator but as an error, because it is not valid in 0.12
  (`E1108` before the result type).
- It needs `nexora-lang` 0.12.0 or newer for the language server. The diagnostics, the
  completion and the formatting come from that package.
- **Fixed:** the `.vsix` did not carry `vscode-languageclient`, which the extension loads when
  it starts. Installed from the package, it highlighted the code but could not start the language
  server or register its commands. The package now carries its production dependencies.

## 0.10.0

First release of the extension.

- Syntax highlighting for `.nex` files, with a TextMate grammar written over the real lexer.
- A language server, in Python, that answers with the same analysis the command line uses:
  diagnostics, completion, hover, go to definition, references, rename, document symbols,
  signature help and formatting.
- A formatter, also in the language itself, that rewrites a document with the canonical shape
  without changing what it means.
- The commands "Check the current file" and "Restart the language server".
