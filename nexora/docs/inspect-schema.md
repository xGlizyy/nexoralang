# `nex inspect` schema

- **Name and version of the schema:** `nexora.inspect/2`
- **Available since:** `nexora` 0.3.0 (version 1 existed in 0.2.0; the changes are in the
  [history](#history))

`nex inspect file.nex` writes to the standard output a single JSON document with the structure
of the program: refined types, functions, parameters, contracts, statements and expressions, each one with its position
and, when it is known, its type.

The command **does not run the program**. It performs the lexical, syntax and static analysis, like
`nex check`. The output only contains what is written in the file and what the analysis deduces
from it: it includes no absolute paths, no environment variables and no data about the machine.

This representation is meant to be consumed by tools (editors, analyzers,
AI assistants). NEXORA includes none of those tools: it only provides the data.

## Document

```json
{
  "schema": "nexora.inspect/2",
  "nexora_version": "0.7.0",
  "file": "hello.nex",
  "ok": true,
  "diagnostics": [],
  "program": { "kind": "Program", "...": "..." }
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `schema` | text | Name and version of this format |
| `nexora_version` | text | Version of NEXORA that produced the document. Field added after 0.2.0 |
| `file` | text | The analyzed file, as it was passed to the command |
| `ok` | boolean | `true` if the program has no static errors |
| `diagnostics` | list | The errors found, with the format of section 11.4 of the [specification](language-spec.md) |
| `complete` | boolean | `true` if the tree covers the whole file. `false` if it is partial or does not exist. Field added after 0.2.0 |
| `program` | `Program` node or `null` | The syntax tree |

The JSON Schema of this document, generated from the code, is in
[`schemas/nexora-inspect.schema.json`](schemas/nexora-inspect.schema.json); the rules common to
all formats, in [JSON protocol](json-protocol.md).

When `program` is available:

| Situation | `ok` | `complete` | `program` | Exit code |
|-----------|------|------------|-----------|-----------|
| Valid program | `true` | `true` | The tree, with all the types | `0` |
| Semantic or type errors | `false` | `true` | The tree; the expressions that could not be typed have `"type": null` | `1` |
| Syntax errors | `false` | `false` | A **partial** tree | `1` |
| Lexical errors | `false` | `false` | `null` | `1` |
| The file could not be read | `false` | `false` | `null` | `4` |

A partial tree contains what could be analyzed:

- Every **statement** that has a syntax error is missing; the other statements of its block are there.
- Every **function** whose declaration (name, parameters or return type) has an error is missing.
- A block left unclosed at the end of the file is kept with the statements written; its
  position ends where the file ends.
- Types are computed the same way, but what depends on a missing piece has `"type": null`.
- `diagnostics` contains **only the syntax errors**. Name and type errors are not
  reported while the syntax is wrong.

All the nodes of a partial tree are complete and meet this schema: there are no error nodes or
half-filled fields. A program with syntax errors **never runs**, whether it has a tree or not.

Until this change, `program` was `null` also with syntax errors. To know whether a program
is valid, look at `ok`, not at whether `program` exists.

`ok` being `true` means that the program passes the static analysis. It says nothing about what
will happen when it runs: divisions by zero, overflows, broken contracts and values
checked with `Type(x)` that do not meet their condition are only detected with `nex run`.

## Nodes

Every node is an object with these two fields, always the first ones:

| Field | Type | Meaning |
|-------|------|---------|
| `kind` | text | The kind of node, one of those listed below |
| `span` | position | The fragment of code it comes from |

A **position** is an object `{"line", "column", "end_line", "end_column"}`. Lines and columns
start at 1; the column counts characters and the end position is excluded.

The fields of each node always appear, in the order given. An optional field without a value is
`null`, it is never omitted.

### Declarations

| `kind` | Fields | Meaning |
|--------|--------|---------|
| `Program` | `types`: list of `TypeDecl` · `functions`: list of `Function` · `records`: list of `RecordDecl` · `uses`: list of `UsesDecl` · `imports`: list of `ImportDecl` | The whole file, with the types and the functions in the order in which they appear. `records`, `uses` and `imports` go at the end |
| `ImportDecl` | `path`: text · `path_span`: position | The declaration `import "app/models.nex"`, which can only appear at the beginning of the file ([decision 0018](decisions/0018-modulos-e-importaciones.md)) |
| `TypeDecl` | `name`: text · `name_span`: position · `base`: `TypeRef` · `condition`: expression · `message`: text or `null` · `public`: `true` or `false` | A refined type. `message` is the explanation written after the comma; `public` is `true` when the declaration carries `pub` |
| `RecordDecl` | `name`: text · `name_span`: position · `fields`: list of `FieldDecl` · `public`: `true` or `false` | A record: `type Point = { x: Int, y: Int }`. `public` is `true` when the declaration carries `pub` |
| `FieldDecl` | `name`: text · `name_span`: position · `type`: `TypeRef` | A field of a record |
| `UsesDecl` | `capability`: `"read"` or `"write"` · `path`: text · `path_span`: position | The capability that the program declares it needs ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `Function` | `name`: text · `name_span`: position · `params`: list of `Param` · `return_type`: `TypeRef` · `contracts`: list of `Contract` · `body`: `Block` · `examples`: list of `Example` · `public`: `true` or `false` | A function. `examples` is the last field before `public`, which is `true` when the declaration carries `pub` |
| `Example` | `condition`: expression · `message`: text or `null` | An `example` clause. `nex inspect` never evaluates it |
| `Param` | `name`: text · `name_span`: position · `type`: `TypeRef` | A parameter |
| `TypeRef` | `name`: text · `arguments`: list of `TypeRef` · `qualifier`: text or `null` | A type written in the code: `Int`, `Float`, `Bool`, `Text`, `Void`, a refined type or `List[T]`. `arguments` is empty for a name without square brackets; `List[Int]` has one argument `Int`. `qualifier` is the module of a type from another file, `null` otherwise: `models.Point` has `qualifier` `models` and `name` `Point` |
| `Contract` | `clause`: `"requires"` or `"ensures"` · `condition`: expression · `message`: text or `null` | A contract clause. `message` is the explanation written after the comma |
| `LoopClause` | `clause`: `"invariant"` or `"decreases"` · `condition`: expression (`Bool` in an invariant, `Int` in a measure) · `message`: text or `null` | A clause at the beginning of the body of a `While` or a `For` |

### Statements

| `kind` | Fields | Meaning |
|--------|--------|---------|
| `Block` | `statements`: list of statements | A `{ }` block |
| `Let` | `name`: text · `name_span`: position · `declared_type`: `TypeRef` or `null` · `value`: expression | Declaration of an immutable variable. `declared_type` is `null` if the type is inferred |
| `Var` | The same as `Let` | Declaration of a variable that can change its value (`var`). It is a node different from `Let` so that a tool that does not know it notices, instead of taking it for immutable |
| `Return` | `value`: expression or `null` | `return`, with or without a value |
| `If` | `condition`: expression · `then_block`: `Block` · `else_branch`: `Block`, `If` or `null` | Conditional. `else_branch` is another `If` in an `else if` |
| `While` | `condition`: expression · `clauses`: list of `LoopClause`, in the order of the code · `body`: `Block` | A loop. `body` contains the statements, without the clauses |
| `For` | `name`: text · `name_span`: position · `iterable`: expression · `clauses`: list of `LoopClause`, in the order of the code · `body`: `Block` | A `for` over a `List[T]`. The iterator and its position go first; `body` contains the statements, without the clauses |
| `ExprStatement` | `expression`: expression | A call used as a statement |
| `Assign` | `name`: text · `name_span`: position · `value`: expression | An assignment. It is only valid on a `var` variable; on a `let` or a parameter it comes with the error `E2007` |
| `FieldAssign` | `target`: expression · `name`: text · `name_span`: position · `value`: expression | An assignment to a field of a record. A record is immutable, so it always comes with the error `E2025` |

### Expressions

Besides its fields, every expression ends with the `type` field: the type that the static analysis
assigns to it (`"Int"`, `"Float"`, `"Bool"`, `"Text"`, `"Void"`, a list type such as `"List[Int]"`,
the name of a refined type that the program declares, such as `"Percent"`, or the name of a
record, such as `"Point"`), or `null` if it could not
determine it because the expression contains an error. A call to a function that returns
nothing has type `"Void"`.

| `kind` | Fields (before `type`) | Meaning |
|--------|------------------------|---------|
| `IntLiteral` | `value`: integer number | |
| `FloatLiteral` | `value`: decimal number | |
| `TextLiteral` | `value`: text, with the escapes already resolved | |
| `BoolLiteral` | `value`: boolean | |
| `ListLiteral` | `elements`: list of expressions | A list literal: `[1, 2, 3]` or `[]` |
| `Name` | `name`: text | Use of a variable, a parameter, `result` (in `ensures`) or `value` (in the condition of a refined type) |
| `Unary` | `operator`: `"-"` or `"not"` · `operand`: expression | |
| `Binary` | `operator`: text · `operator_span`: position · `left`: expression · `right`: expression | `operator` is one of `+ - * / == != < <= > >= and or` |
| `Group` | `expression`: expression | An expression in parentheses |
| `Call` | `callee`: text · `callee_span`: position · `arguments`: list of expressions · `qualifier`: text or `null` | Call to a user or built-in function, or check of a refined type (`Percent(x)`), whose type is that of the refined type. In a qualified call (`Text.length(s)`), `callee` is the full name (`"Text.length"`), `callee_span` covers it entirely and `qualifier` is the type (`"Text"`); in any other, `qualifier` is `null` |
| `RecordConstruction` | `name`: text · `name_span`: position · `fields`: list of `FieldInitializer` · `qualifier`: text or `null` | The construction of a record: `Point(x: 1, y: 2)`. The fields go in the order in which they are written, which does not have to be that of the declaration. `qualifier` is the module of a record from another file, `null` otherwise |
| `FieldInitializer` | `name`: text · `name_span`: position · `value`: expression | The value given to a field in a construction |
| `FieldAccess` | `target`: expression · `name`: text · `name_span`: position | Reading a field: `p.x`. `target` is the value it is read from |

## Example

For this program:

```nex
fn double(n: Int) -> Int {
    requires n >= 0
    return n * 2
}
```

the node of the function is (the inner positions are omitted for brevity):

```json
{
  "kind": "Function",
  "span": {"line": 1, "column": 1, "end_line": 4, "end_column": 2},
  "name": "double",
  "name_span": {"line": 1, "column": 4, "end_line": 1, "end_column": 10},
  "params": [
    {"kind": "Param", "span": "...", "name": "n", "name_span": "...",
     "type": {"kind": "TypeRef", "span": "...", "name": "Int", "arguments": []}}
  ],
  "return_type": {"kind": "TypeRef", "span": "...", "name": "Int", "arguments": []},
  "contracts": [
    {"kind": "Contract", "span": "...", "clause": "requires",
     "condition": {"kind": "Binary", "span": "...", "operator": ">=", "operator_span": "...",
                   "left": {"kind": "Name", "span": "...", "name": "n", "type": "Int"},
                   "right": {"kind": "IntLiteral", "span": "...", "value": 0, "type": "Int"},
                   "type": "Bool"},
     "message": null}
  ],
  "body": {
    "kind": "Block", "span": "...",
    "statements": [
      {"kind": "Return", "span": "...",
       "value": {"kind": "Binary", "span": "...", "operator": "*", "operator_span": "...",
                 "left": {"kind": "Name", "span": "...", "name": "n", "type": "Int"},
                 "right": {"kind": "IntLiteral", "span": "...", "value": 2, "type": "Int"},
                 "type": "Int"}}
    ]
  }
}
```

## Stability and evolution

The schema carries a name and a version number in the `schema` field.

- **The version number changes** when a field or a node kind is removed, renamed or
  changes its meaning. A program that reads version 1 may stop working with version 2.
- **The version number does not change** when a field is added to a node or a new node kind is added
  (for example, when a construct is added to the language). Tools must ignore the fields
  and node kinds they do not know.
- The order of the fields is stable within a version, and the output is deterministic: the same
  file always produces the same document.

An automated test (`tests/test_inspect.py`) pins the exact list of nodes and fields of
version 2, and another one checks that this document mentions all of them.

### History

| Version | Published in | Changes |
|---------|--------------|---------|
| `nexora.inspect/2` | `nexora` 0.11.0 | Added, without changing the version: the `ImportDecl` node (`path`, `path_span`) for the declaration `import "app/models.nex"`, the `imports` field at the end of `Program`, the `public` field (`true` or `false`) at the end of `TypeDecl`, `RecordDecl` and `Function`, and the `qualifier` field (text or `null`) at the end of `TypeRef` and of `RecordConstruction` for the types and records of another module, `models.Point` ([decision 0018](decisions/0018-modulos-e-importaciones.md)). A program without imports produces the same document as in 0.10.0, plus `"imports": []`, `"public": false` in every declaration and `"qualifier": null` in every type |
| `nexora.inspect/2` | `nexora` 0.10.0 | Added, without changing the version: the `UsesDecl` node (`capability`, `path`, `path_span`) for the declaration `uses read "path"`, and the `uses` field at the end of `Program` ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `nexora.inspect/2` | `nexora` 0.8.0 | Added, without changing the version: the nodes `RecordDecl` (`name`, `name_span`, `fields`), `FieldDecl` (`name`, `name_span`, `type`), `RecordConstruction` (`name`, `name_span`, `fields`), `FieldInitializer` (`name`, `name_span`, `value`) and `FieldAccess` (`target`, `name`, `name_span`); the statement `FieldAssign` (`target`, `name`, `name_span`, `value`); the `records` field at the end of `Program`; and `type` can be the name of a record ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `nexora.inspect/1` | `nexora` 0.2.0 | First version |
| `nexora.inspect/2` | `nexora` 0.7.0 | Added, without changing the version: `arguments` (list of `TypeRef`) in `TypeRef`, which is `[]` when the type has no square brackets and has one argument when the type is `List[Int]`; the `ListLiteral` node (`elements`: list of expressions) for `[a, b]` and `[]`; the `For` node (`name`, `name_span`, `iterable`, `clauses`, `body`) for `for x in xs`; and `type` can be `List[...]` ([decision 0013](decisions/0013-listas-y-for.md)) |
| `nexora.inspect/2` | `nexora` 0.6.0 | Added, without changing the version: the `qualifier` field in `Call`, in all calls (`null` if there is no qualifier), after `arguments` and before `type` ([decision 0011](decisions/0011-operaciones-sobre-textos.md)). `callee` can contain a dot (`"Text.length"`) in qualified calls. A program without them produces the same document as in 0.5.1, plus `"qualifier": null` in every `Call`; the document also validates with the schema of 0.5.1 |
| `nexora.inspect/2` | `nexora` 0.5.0 | Added, without changing the version: the nodes `Var`, `While` and `LoopClause` ([decision 0010](decisions/0010-var-y-while.md)). `Assign` also appears in valid programs. A program without `var` or loops produces the same document as in 0.4.0 |
| `nexora.inspect/2` | `nexora` 0.4.0 | Added, without changing the version: the `Example` node and the `examples` field at the end of `Function` ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `nexora.inspect/2` | `nexora` 0.3.0 | **Incompatible change:** the `type` field of expressions stops being a closed list (`Int`, `Float`, `Bool`, `Text`, `Void`) and can be the name of a refined type. Added: the `TypeDecl` node, the `types` field in `Program`, the `message` field in `Contract` |
