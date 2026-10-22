# Changelog

## 0.10.0

First release of the extension.

- Syntax highlighting for `.nex` files, with a TextMate grammar written over the real lexer.
- A language server, in Python, that answers with the same analysis the command line uses:
  diagnostics, completion, hover, go to definition, references, rename, document symbols,
  signature help and formatting.
- A formatter, also in the language itself, that rewrites a document with the canonical shape
  without changing what it means.
- The commands "Check the current file" and "Restart the language server".
