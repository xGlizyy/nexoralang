# 0005 — Diagnostic categories, versioned JSON schemas and exit code 5

- **Status:** accepted
- **Version:** 0.2.0

## Decision

1. **Every error code belongs to a category**: `file`, `lexical`, `syntax`, `semantic`,
   `type`, `runtime` or `contract`. The category says which stage found the problem.
2. **The header of a text diagnostic includes the category**:
   `type error[E2011]: Type mismatch` instead of `error[E2011]: Type mismatch`.
3. **Codes are not reused.** A code that stops being emitted is retired and stays documented.
4. **JSON documents carry a `schema` field** with a name and a version: `nexora.diagnostics/1`
   and `nexora.inspect/1`. The version only changes if a field is removed, renamed or changes its
   meaning.
5. **New command `nex inspect`**, which writes the syntax tree with types and positions.
6. **`nex run --format json`** writes the errors as JSON to the standard error.
7. **Exit code `5`** for a broken contract.
8. **Suggestions (`hint`) only appear when a rule supports them**: there is a
   conversion between the two types, there is a declared name similar to the one written, or the message
   describes the correct form of the construct.

## Reasons

- A tool can decide what to do with an error from its category without interpreting the text or
  memorizing ranges of codes.
- A versioned schema lets the format evolve without breaking whoever consumes it, and lets
  whoever consumes it know when it has to be reviewed.
- The tree that `nex inspect` shows is the same one that the checker and the interpreter use: there is
  no second representation that can drift.
- The rules of the language are still deterministic code. These outputs are data for
  external tools; no tool, and no model, takes part in deciding whether a
  program is valid.

## Incompatible changes and how to update

| Change | Who it affects | What to do |
|--------|----------------|------------|
| The text header starts with the category | Scripts that look for lines that **start** with `error[` | Look for `error[` at any position or, better, use `--format json` |
| The JSON of `nex check` adds `schema` and, in every diagnostic, `category` | Nobody who reads the JSON by field name; only whoever compares the whole document | Ignore unknown fields |
| A broken contract ends with code `5` | Nobody: contracts did not exist in 0.1 | — |
| `E1104` and `E2003` are no longer emitted | Whoever filtered by those codes | The situations they pointed at are now valid code |
| `E2004` no longer covers unknown return types | Whoever filtered by `E2004` | A type that does not exist is now `E2012`; `E2004` remains for "`main` must return `Void`" |

## Alternatives ruled out

- **Renumbering the codes by category** (for example, moving all the type ones to a range of their
  own). It would have broken the stability of the 0.1 codes; the category goes in a separate field.
- **A text format for `nex inspect`.** There is no clear use for it yet; only JSON is added.
