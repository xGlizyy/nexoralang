# Language Server Protocol (LSP)

**Status: planned. It is not implemented.** NEXORA does not include an LSP server, and no editor
has integration with the language today.

This page gathers the evaluation that was made and what would be needed, so that whoever implements it does not start
from scratch.

## Why it has not been implemented yet

It was evaluated at the end of the tooling phase and it was decided not to deliver a half-done version. A
program that returns diagnostics without respecting the protocol is not an LSP server, and one that
respects it needs to solve three things well, of which only one is partly solved today:

1. **Positions.** LSP measures columns, by default, in UTF-16 units and from 0. NEXORA
   measures them in Unicode characters and from 1. The conversion is simple for ASCII text, but it has to
   be exact also with characters outside the basic plane (emojis), and it requires negotiating the
   encoding with the editor.
2. **Half-written code.** An editor sends the document on every keystroke, almost always with
   errors. **Partly solved:** with syntax errors NEXORA already delivers a partial tree and
   partial symbols. Two gaps remain: a function whose declaration has an error disappears
   entirely, and with a lexical error (an unclosed quote, the most common thing while typing a text)
   there is no structure, so *hover* and "go to definition" would disappear at that moment.
3. **Life cycle.** Document versions, discarding stale results, cancellation and orderly
   shutdown. It is protocol work that needs its own tests.

Priority went to what already brings value to tools and agents: the [JSON protocol](json-protocol.md),
the [structured context](ai-context.md) and the [MCP server](mcp.md).

## What already exists and would be reused

An LSP server would not need any new logic of the language:

| LSP feature | Source in NEXORA | Enough today? |
|-------------|------------------|---------------|
| Diagnostics (`textDocument/publishDiagnostics`) | `tooling.check_source`: code, category, start and end position, suggestion | Yes |
| *Hover* with the type of an expression | The type of each node in `tooling.inspect_source` | Yes; partial with syntax errors, nothing with lexical errors |
| Signature of a function | `signature` in `tooling.get_symbols` | Yes |
| Go to definition | `declaration` and `references` in `tooling.get_symbols`, resolved by the checker | Yes; partial with syntax errors, nothing with lexical errors |
| Find references | `references` | Yes, within the file |
| Document symbols | `tooling.get_symbols` | Yes |
| Completion | — | **No.** Completing only keywords would be a fake completion; it requires knowing which names are visible at a point of the code, and that needs analysis with errors |

## Planned architecture

```text
Editor  ⇄  LSP server (new module, optional)  ⇄  nexora.tooling  ⇄  lexer, parser, checker
```

- A separate module, `src/nexora/lsp_server.py`, with its dependency declared as optional
  (`pip install "nexora-lang[lsp]"`), like the MCP server. The core would not depend on it.
- A library that implements the protocol (for example `pygls`), so as not to write the
  JSON-RPC transport by hand. Its current version and interface would have to be checked before starting.
- Full document synchronization (the editor sends the whole text on every change): the
  programs are single-file and small, and the analysis is fast.
- A position conversion function, with its own tests, in a single place.
- No execution: the server would only analyze.

## Prerequisites

In this order:

1. **Complete the error tolerance.** The partial tree with syntax errors already exists
   (`complete: false`). What is missing is keeping the functions with an incomplete declaration and having the
   lexer recover from an unclosed text.
2. **Conversion of positions to UTF-16**, with tests.
3. The server, starting with diagnostics only, with protocol tests: initialization, opening,
   versioned changes, closing a document and shutting down the server.
4. *Hover* and definition, once point 1 is solved.

## Meanwhile

An editor or a script can get the diagnostics with exact positions today by running
`nex check file.nex --format json` on save. It is not LSP and does not pretend to be.
