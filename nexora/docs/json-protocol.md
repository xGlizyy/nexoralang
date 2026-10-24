# JSON protocol

NEXORA delivers the result of its analysis as data, in JSON, so that a program does not have to
interpret text written for people or deduce anything with regular expressions.

This page defines the formats, their versions and the rules they follow. Every format also has
a **JSON Schema** in [`schemas/`](schemas/), and the tests validate the real output with it.

## Formats

| `schema` | What it is | Produced by | JSON Schema |
|----------|------------|-------------|-------------|
| `nexora.diagnostics/1` | The result of the static analysis | `nex check --format json`, `nex run --format json`, `tooling.check_source` | [`nexora-diagnostics.schema.json`](schemas/nexora-diagnostics.schema.json) |
| `nexora.inspect/3` | The syntax tree, with types | `nex inspect`, `tooling.inspect_source` | [`nexora-inspect.schema.json`](schemas/nexora-inspect.schema.json) |
| `nexora.symbols/2` | The declared names and their uses | `nex symbols --format json`, `tooling.get_symbols` | [`nexora-symbols.schema.json`](schemas/nexora-symbols.schema.json) |
| `nexora.context/2` | A technical summary of the program | `nex context --format json`, `tooling.get_context` | [`nexora-context.schema.json`](schemas/nexora-context.schema.json) |
| `nexora.spec/2` | The specification of the language, or a section | `tooling.get_language_spec` | [`nexora-spec.schema.json`](schemas/nexora-spec.schema.json) |
| `nexora.capabilities/1` | What this version of NEXORA is | `tooling.get_capabilities` | [`nexora-capabilities.schema.json`](schemas/nexora-capabilities.schema.json) |
| `nexora.evidence/1` | What backs every clause of the program | `nex check --evidence --format json`, `tooling.get_evidence` | [`nexora-evidence.schema.json`](schemas/nexora-evidence.schema.json) |
| `nexora.result/1` | The result of checking or **running** a program | `nexora.api`, the [playground](playground.md) | [`nexora-result.schema.json`](schemas/nexora-result.schema.json) |
| `nexora.test/1` | The result of **evaluating** the examples of a program | `nex test --format json`, `nexora.api.test_source` | [`nexora-test.schema.json`](schemas/nexora-test.schema.json) |

The first seven are **analysis** formats: producing them never runs the program. The last two are
the only ones that can come from a run, and no analysis tool uses them.
`nexora.test/1` is defined in [decision 0008](decisions/0008-ejemplos-y-nex-test.md), section 6.

All the tools of the [MCP](mcp.md) server return these same documents.

## Common rules

### Header

The documents that refer to a program start with the same five fields, in this order:

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | text | Name and version of the format |
| `nexora_version` | text | Version of NEXORA that produced the document |
| `file` | text | The name given to the code. It is a label: it does not have to be a path |
| `ok` | boolean | `true` if the static analysis found no errors |
| `diagnostics` | list | The diagnostics, in the order in which they were found |

`ok: true` means "no static errors". It does **not** mean that the program will run without
failures: a division by zero or a broken contract only appears when running.

### Clean JSON

When JSON is asked for (`--format json`):

- The standard output contains **a single JSON document** and nothing else: no warnings, no
  decorative messages, no Markdown blocks.
- It holds for any input: a missing, empty or binary file, or one that is not NEXORA, still produces
  a valid document, with the error inside `diagnostics`.
- The encoding is UTF-8.
- The order of the fields is stable and the output is deterministic: the same file always produces
  exactly the same bytes.
- The standard error stays empty. The only exception is `nex run --format json`, which writes the
  document **to the standard error** (and only if there is a failure), because the standard output belongs
  to the program that runs.
- An internal error of NEXORA produces no JSON: it writes `internal error: …` to the standard error and
  ends with code `70`. A consumer must treat "the output is not JSON" as a failure of the
  tool, not of the program.

### Exit codes

| Code | Meaning | Is there a JSON document? |
|------|---------|---------------------------|
| `0` | The program has no static errors | Yes, with `ok: true` |
| `1` | The program has static errors | Yes, with `ok: false` |
| `2` | Wrong use of the command | No |
| `4` | The file could not be read | Yes, with an `E0001` or `E0002` diagnostic |
| `70` | Internal error of NEXORA | No |

(`3` and `5` are only produced by `nex run`: the program failed or broke a contract while running.)

### Positions

A position is an object with `line`, `column`, `end_line` and `end_column`.

- Lines and columns start at **1**.
- The end is **exclusive**: `column: 5, end_column: 8` covers columns 5, 6 and 7.
- The column counts **Unicode characters** (code points), not bytes or UTF-16 units. A
  tab counts as one column.
- In a diagnostic, the four values are `null` if the problem does not refer to a point in the
  file. A position is never made up.

### What is unknown is `null`

When the analysis could not establish a piece of data, the field is `null`. It is not filled with a
guess. For example: the type of an expression that contains an error, the tree of a program with
lexical errors, or the type of a parameter whose type is badly written.

### Partial analysis: `complete`

The inspection, symbols and context documents carry the `complete` field.

| `complete` | Means |
|------------|-------|
| `true` | The analysis covers the whole file (whether or not it has name or type errors) |
| `false` | There are syntax errors and the document describes **only the code that could be analyzed**; or there is no structure (lexical errors, unreadable file) |

With a partial analysis the statements that have an error and the functions whose declaration
has one are missing, and `diagnostics` contains only the syntax errors. No gap is filled: what is
missing, is missing. The details are in [the `nex inspect` schema](inspect-schema.md#document).

## Diagnostics

<!-- nex:check-json -->
```nex
fn double(n: Int) gives Int {
    return n * 2
}

fn main() {
    print(double("21"))
}
```

`nex check program.nex --format json`:

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.11.0",
  "file": "program.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "category": "type",
      "code": "E2011",
      "message": "Type mismatch",
      "label": "Expected Int, found Text",
      "hint": null,
      "notes": [
        "This is the argument for 'n' in: fn double(n: Int) gives Int"
      ],
      "file": "program.nex",
      "line": 6,
      "column": 18,
      "end_line": 6,
      "end_column": 22
    }
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `severity` | text | Always `"error"`: in this version there are no warnings |
| `category` | text | `file`, `lexical`, `syntax`, `semantic`, `type`, `runtime` or `contract` |
| `code` | text | Stable identifier: `E` and four digits. It never changes its meaning |
| `message` | text | Fixed title associated with the code |
| `label` | text | Explanation of this concrete case |
| `hint` | text or `null` | Suggested fix |
| `notes` | list of texts | Related information |
| `file` | text | The file |
| `line`, `column`, `end_line`, `end_column` | number or `null` | The affected fragment |

Correspondence with names common in other tools: `hint` is what is sometimes called
*suggestion*, and `notes` what is called *related information*. The names the format
was born with are kept so as not to break compatibility.

Guarantees about the content:

- **The codes are real.** Every code that can appear is in the registry of the language
  ([full list](diagnostics.md#all-the-codes)) and `tooling.get_capabilities` lists them.
- **A suggestion is not a guaranteed fix.** `hint` is a text for people, and it only
  appears when a rule of the language backs it (that conversion exists, there is a declared name
  that is similar). If it is `null`, NEXORA has nothing well-founded to suggest. A diagnostic never
  edits a file: the only command that writes a program is `nex migrate --write`, and only when asked.
- **Errors of the program and failures of NEXORA do not mix.** A diagnostic always describes
  the analyzed program. A defect of the tool is not a diagnostic (see "Clean JSON").
- What is stable is `code`, `category` and the positions. The wording of `message`, `label`, `hint` and
  `notes` is in English and may improve between versions: do not compare it as text.

## Evidence

`nex check --evidence --format json` and `tooling.get_evidence` return a `nexora.evidence/1` document:
what backs every `needs`, `promises`, `trust`, `keeps` and `shrinks` of the program
([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), section 5). It starts with the header
of every document, with the same `ok` and `diagnostics` as `nex check`, and adds:

| Field | Meaning |
|-------|---------|
| `computed` | Which dimensions the command computed besides the enforcement, which is always computed: `{"static": false, "observed": false}` in this version |
| `clauses` | One entry per clause, ordered by the path of its module and then as written in the file: the clauses of the header of each function, then those of its loops. `example` clauses have no entry. `null` when the program has errors |

Each entry:

```json
{
  "id": {"module": "", "function": "percentage", "name": "whole_positive", "kind": "needs",
         "stable": true},
  "condition": "whole > 0",
  "message": "A percentage of nothing is not defined",
  "enforcement": "checked",
  "static": {"status": "not_computed", "reason": "phase_not_implemented"},
  "observed": {"status": "not_computed", "reason": "analysis_only"},
  "summary": "checked"
}
```

| Field | Meaning |
|-------|---------|
| `id.module` | The path of the file, relative to the directory of the program and with `/`; `""` for the program itself |
| `id.function` | The function that declares the clause, without its module |
| `id.name`, `id.stable` | The name of the clause, or `null`. `stable` is `true` exactly when there is a name: within one version of the program, `(module, function, name)` then names exactly one clause. It does not say that the clause is the same in another version, or anything about its evidence ([decision 0019, addendum 1](decisions/0019-identidad-propia-del-lenguaje.md#addendum-1--details-of-nexoraevidence1-left-open-by-section-5-provisional)). A clause without a name has no identity of its own |
| `id.kind` | `needs`, `promises`, `trust`, `keeps` or `shrinks` |
| `condition`, `message` | The condition as written, and its explanation or `null` |
| `enforcement` | `checked`: the language evaluates the condition when the program runs, and a false one stops it. `trusted`: a `trust`, never evaluated |
| `static`, `observed` | Objects with a `status`, never `null`: `not_applicable` (this kind of clause can never have that dimension), `not_computed` with a `reason`, or `computed` |
| `summary` | One word, from a single dimension: in this version `checked`, or `trusted` for a `trust` |

The values of `reason` are `analysis_only` (the command only analyses: `observed` in `nex check`),
`phase_not_implemented` (`static`, which no version decides yet) and `static_errors` (reserved for
`nex test --evidence`, a later phase). A reason a
tool does not know means "not computed". The words `broken`, `proved` and `exemplified` of `summary`
belong to the later phases of the decision; this version never produces them.

`checked` does not say that a condition holds, and `trusted` does not say that anything checked it.

## Versions and compatibility

Every format carries its version in its own name: `nexora.context/2`.

| Change | Does the number change? | What whoever consumes it must do |
|--------|-------------------------|----------------------------------|
| A field is added to an object | No | Ignore the fields it does not know |
| A node kind is added to the tree, a value to `features`, an error code or a category | No | Handle unknown values without failing |
| A field is removed or renamed | **Yes** | Adapt to the new version |
| A field changes its type or its meaning | **Yes** | Adapt to the new version |

The schemas reflect this rule: they do not forbid additional fields.

History:

| Format | Since | Changes |
|--------|-------|---------|
| `nexora.diagnostics/1` | 0.1.0 | 0.2.0: `category` field and `schema` field. Current version: `nexora_version` field |
| `nexora.inspect/1` | 0.2.0 | `nexora_version` and `complete` fields; with syntax errors, `program` is a partial tree instead of `null` |
| `nexora.inspect/2` | 0.3.0 | The `type` field of an expression can be the name of a refined type (before, it was a closed list of five types). New `TypeDecl` node, `types` field in `Program` and `message` field in `Contract` |
| `nexora.inspect/2` | 0.8.0 | New nodes `RecordDecl`, `FieldDecl`, `RecordConstruction`, `FieldInitializer` and `FieldAccess`, the `FieldAssign` statement, the `records` field at the end of `Program`, and `type` can be the name of a record ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `nexora.context/1` | 0.8.0 | New `records` field: the records the program declares, with `name`, `fields`, `valid`, `line` and `reason`. `types` is still only for refined types ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `nexora.context/1` | 0.10.0 | New `capabilities` field: the capabilities the program declares with `uses`, with `capability` and `path`. `types` is still only for refined types and `records` only for records ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `nexora.inspect/2` | 0.11.0 | New `imports` field in `Program` (with the `ImportDecl` node), `public` field in `Function`, in `TypeDecl` and in `RecordDecl`, and `qualifier` field in `TypeRef` and in `RecordConstruction`: a program can be made of several files ([decision 0018](decisions/0018-modulos-e-importaciones.md)) |
| `nexora.context/1` | 0.11.0 | New `file` field in every function of `functions`: the file that declares it, relative to the program and with `/` ([decision 0018](decisions/0018-modulos-e-importaciones.md)) |
| `nexora.symbols/1` | 0.11.0 | New `file` field in every symbol: the file that declares it, relative to the program and with `/` ([decision 0018](decisions/0018-modulos-e-importaciones.md)) |
| `nexora.spec/2` | Unreleased | **Incompatible change:** the specification is now written in English. `language` is `"en"` (it was `"es"`), and the section ids come from the English headings (`7-functions` instead of `7-funciones`). The rest of the document does not change |
| `nexora.result/1` | Current version | |
| `nexora.test/1` | 0.4.0 | First version |
| `nexora.inspect/3` | Unreleased | **Incompatible change** ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), 8.8): `Function.header`, one ordered list of `Contract` and `Example`, replaces `contracts` and `examples`; `Function.return_type` is `null` when the function has no `gives`; `Contract.clause` is `needs`, `promises` or `trust`, `LoopClause.clause` is `keeps` or `shrinks`, and both have a `name` field ([inspect schema](inspect-schema.md)) |
| `nexora.context/2` | Unreleased | **Incompatible change** ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), 8.8): the `clause` of a contract is `needs`, `promises` or `trust` (it was `requires` or `ensures`), and every contract and loop clause has a `name` field, `null` when the clause has none |
| `nexora.symbols/2` | Unreleased | **Incompatible change** ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), 8.8): the contracts of the built-in functions use `needs` and `promises` |
| `nexora.capabilities/1` | Unreleased | Kept at `/1`: the contracts of the built-in functions keep `requires` and `ensures`, as published. `schemas` gains the value `nexora.evidence/1`; `keywords` and `reserved_words` describe the language of 0.12 (the four clause words of 0.11 are reserved words, `ai` and `tool` are not) |
| `nexora.evidence/1` | Unreleased | First version, with the enforcement dimension only ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), section 5) |

Almost all the changes have been added fields. The exceptions are `nexora.inspect/3`, `nexora.context/2`
and `nexora.symbols/2`, whose fields change meaning with the syntax of 0.12, and `nexora.spec/2`, which
changes the value of `language` and the section ids: all four change the number. The other exception is `program` in `nexora.inspect/1`:
its type does not change (tree or `null`), but with syntax errors it used to be `null` and now it is a partial
tree. The number was kept because the format only existed in 0.2.0, which has not been
published, and because the type of the field is the same; even so it is a **change of behaviour**, and
it is recorded as such in the [change history](../CHANGELOG.md). A tool that deduced
"correct syntax" from `program` not being `null` must switch to looking at `ok` or `complete`.

## The schemas

The files of [`schemas/`](schemas/) are JSON Schema (draft 2020-12).

- **They are generated from the code** (`src/nexora/schemas.py`); a test fails if a file does not
  match what the code defines.
- The part of the schema that describes the syntax tree is derived from the classes of the
  nodes themselves: a node cannot change without its schema changing.
- The tests validate with them the real documents of all the examples, and also those of
  wrong inputs (empty file, text that is not NEXORA, truncated code).
- The `$id` field of each schema is only an identifier: nothing is published at that address.

To regenerate them after an intended change:

```bash
NEXORA_UPDATE_SCHEMAS=1 python -m pytest tests/test_tooling.py
```

(In PowerShell: `$env:NEXORA_UPDATE_SCHEMAS = "1"; python -m pytest tests/test_tooling.py; $env:NEXORA_UPDATE_SCHEMAS = $null`.)

Validating a document with a schema, in Python:

```python
import json, jsonschema

schema = json.load(open("docs/schemas/nexora-diagnostics.schema.json", encoding="utf-8"))
jsonschema.validate(document, schema)
```

`jsonschema` is a development dependency, not one of the language.

## Limitations

- There is no format for edits (position and replacement text): suggestions are text.
- The diagnostics of `nex run` in JSON go to the standard error, not to the standard output.
- The tree does not exist if the program has lexical errors, and it is partial if it has syntax errors.
- The documents describe the entry file of a program; of the files it imports, they only give the `file`
  of each function and symbol.
- The texts for people (`label`, `hint`, `notes`, the notes of the context) and the specification
  returned by `nexora.spec/2` are in English.
