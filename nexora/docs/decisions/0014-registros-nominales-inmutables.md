# 0014 — Immutable nominal records

- **Status:** accepted
- **Version:** 0.8.0 (state of the repository; not published in any package). The decision was
  accepted with 0.7.0 and implemented in 0.8.0.
- **Date:** 2026-10-21
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (static
  types), [0003](0003-funciones-retorno-e-if.md) (a single namespace),
  [0005](0005-diagnosticos-y-esquemas-json.md) (diagnostics and JSON schemas),
  [0007](0007-contratos-estables-y-tipos-refinados.md) (refined types),
  [0011](0011-operaciones-sobre-textos.md) (functions of a type),
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) (the proposal from which
  D02 comes) and [0013](0013-listas-y-for.md) (lists, `for` and the type model). **It modifies
  none.**
- **Replaces:** none. **It neither modifies nor replaces
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) nor
  [0013](0013-listas-y-for.md)**: 0012 is still a proposal for the rest of its
  content and 0013 still accepts only D01, D08 and D09.
- **Implementation:** stage I6 (immutable nominal records), in 0.8.0. The code is in
  `types.py`, `type_adapter.py`, `ast_nodes.py`, `parser.py`, `checker.py`, `interpreter.py`,
  `values.py`, `tooling.py`, `schemas.py` and `diagnostics.py`; the evidence is in the tests of the
  section "Regression tests".

## Context

[Decision 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) proposes, among
other things, user records, and its decision **D02** recommends that they be **nominal**:
two records with the same fields are not interchangeable if they are different declarations.
[0013](0013-listas-y-for.md) accepted only the part of 0012 that was implemented (D01, D08 and
D09) and left records, enums, patterns, `Option`/`Result`, `type_repr` and user generics
as a proposal. Today the language has refined types (`type Percent = Int where ...`),
`List[T]` lists and `for`, but no data structure of its own: the specification says so
(`docs/language-spec.md`, "There are no records, maps, enumerations, `Option`, `Result`…") and so do the
guides on limits (`docs/limitations.md`).

The repository requires code, specification, examples, schemas and tests to say the same thing, and
a decision not to be rewritten: if something is revisited, another one that replaces it is added and both
say so. This ADR follows that pattern: it does not touch 0012 or 0013; it explains which part of D02 is decided
now and with what scope.

The technical problem to solve is not the syntax, but **identity**. The
checker reasons today with type strings (`"Int"`, `"List[Int]"`, `"Percent"`), and the
structured model of `types.py` tells the identity of a refined type by its **name**. For a
record that is not enough: a record is declared in a file, and its identity must be that of its
**declaration**, not that of its name or that of its fields. Without that distinction, two records with the
same name in different programs (or two fields with the same name and different types) would
be confused, and the interpreter —which compares values at run time— could not know whether two values
are of the same type.

## Decision

**One way of declaring and using immutable nominal records** is decided, and nothing more. The decision
accepts the part of **D02** of 0012 that is described here, and nothing else of 0012.

### 1. What a record is

A record is a **nominal type declared by the user**, with **immutable** and
**required** fields, that is built with **named** fields.

```nexora
type Point = { x: Int, y: Int }

fn main() -> Void {
    let p = Point(x: 1, y: 2)
    print(p.x)
}
```

Properties:

- **Nominal.** The identity is that of its declaration. `Point` and `Line` are different types even if
  they have the same fields, and even if it has the same name in different programs.
- **Immutable.** There is no way to change a field. A record is built once and no longer
  changes.
- **With required fields.** There are no default values or optional fields: a construction
  must give **all** the fields, **only once** each.
- **Without methods.** A record only has fields. There are no functions associated with a user
  type: `Text.length` and `List.length` are still the only qualified functions, and they
  belong to built-in types.
- **A value.** A record can be compared with `==` and `!=`, printed, passed to a function,
  returned from a function, stored in a variable and put in a list.

### 2. Syntax

**Declaration.** `type Name = { field: Type, ... }`.

- The `{` goes **on the same line as the `=`**. If there is a line break between `=` and `{`, it is a
  syntax error (`E1101`).
- **Inside** the braces line breaks are allowed, between fields:

  ```nexora
  type Point = {
      x: Int,
      y: Int
  }
  ```

- **There are no empty records**: `type Point = {}` is a syntax error (`E1101`). A record
  has at least one field.
- **There is no trailing comma**, neither in the declaration nor in the construction, as in lists and in
  calls (`[1, 2,]` and `f(1, 2,)` are already syntax errors).
- The **name** of the record follows the rules of type names: it starts with an uppercase letter, it is not
  that of a built-in type (`Int`, `Float`, `Bool`, `Text`, `Void`), it is not already declared and it is not
  used for a function, a parameter or a variable. Breaking these rules is `E2016` (name) and
  `E2006` (name in use), the same codes and with the same meaning they already have.
- A **field** is written `name: Type`. Two fields of the same record cannot have the same name
  (`E2016`). The name of a field is any name of the language: there is no uppercase rule for
  fields, because the values of the language do not have one.
- The **type** of a field is any type of the language: a built-in type, `List[T]`, a refined
  type or **another record**. A type that does not exist is `E2012`; `Void` as the type of a field is
  `E2012`.

**Construction.** `Name(field: value, ...)`.

- The fields can be given **in any order**; the order of the text does not matter.
- Each field is given **only once**. A repeated field is `E2023`.
- All the fields are required. A missing field is `E2023`, **one for each field that is
  missing**.
- A field that the record does not have is `E2023`.
- The values are written **with the name of the field**: `Point(1, 2)` is a syntax error
  (`E1101`). There is no positional construction.
- The form is `Name(...)`, the same as a call, and the analyzer tells one from the other by the
  name: a record name can only be a construction.

**Reading a field.** `value.field`, and access chains `a.b.c` **without a fixed length
limit**, as long as every intermediate step is a valid record.

- The **root** of the chain is always a **name**: a variable, a parameter or `result` inside
  an `ensures`. There is no field access on a call, a construction, a group or a
  list: `f().x` and `(p).x` are syntax errors (`E1101`).
- No general postfix system is introduced: `p.x` is the only way to read a field, and
  only when the root is a name.
- `Point.x` is **not** a field access: `Point` is a type, not a value. The form is still
  the usual qualified call, with its usual diagnostic.

**Assigning to a field.** `value.field = expression`.

- Records are immutable: assigning to an existing field is `E2025`.
- The form only exists to be able to say that it cannot be done: the analyzer does not run the assignment.

### 3. Nominal identity and type model

The identity of a record is **opaque** and **by declaration**: it does not depend on the name or on the
fields.

- `types.py` adds a **`Nominal`** variant: name, fields and **identity**. Two `Nominal` are the
  same type if and only if they have **the same identity**. `types.equal` compares by identity, not
  by name or by fields.
- The identity is an **opaque token** (`RecordIdentity`), which the checker creates once per
  declaration and which travels in the `CheckedProgram` to the interpreter. The interpreter does **not**
  rebuild the identity from the name: it uses the one the checker gives it.
- `types.py` gains the branches that `Nominal` is missing in `equal`, `display`, `to_data`, `widen`,
  `root` and `substitute`, and `type_adapter.py` gains a `register_record` and the way to resolve a
  record name. Without those branches, a record would not be compared, would not be presented and would not
  fit in the model.
- `Nominal` does **not** appear in any JSON document: the `type` field of expressions is still
  the **canonical name** of the type (`"Point"`), as it already is with refined types.

**Equality of values.** It is decided by the value, not by the name:

- Two values of the **same** nominal type are compared **by value**: field by field, in the order of
  the declaration. `Point(x: 1, y: 2) == Point(x: 1, y: 2)` is `true`.
- Two values of **different nominal types** are not compared: it is a static error `E2011`, never
  a `false` at run time.
- A record value and a value of another type are not either: `E2011`.

**Printing.** `format_value` and `show_value` are reused, and with them the difference
that already exists between **printing** and **describing** is kept:

| Form | Text | Where |
|------|------|-------|
| `format_value` | `Point(x: 1, y: 2)` | what `print` writes, what `to_text` returns |
| `show_value` | `Point(x: "a", y: 2)` | diagnostics, `nex test`, `nexora.test/1` |

That is: in the printing form texts are **not** quoted, as in a list;
in the diagnostic form they **are**, so that it can be read as source code.

### 4. Checking

The checker does three things it did not do before.

**Resolution of the fields.** The types of the fields are resolved **after** reading all the
declarations, so that a record can use another one **declared further down** (forward
reference). A record declaration **cannot** be refined with another one (`type Meters = Point
where ...` is `E2016`, just as a refined type cannot have a list as its base today).

**Detection of cycles.** A record cannot contain itself, neither directly nor
indirectly, nor through a list:

```nexora
type D = { d: D }              // E2016: direct cycle
type A = { b: B }              // E2016: indirect cycle A -> B -> A
type B = { a: A }              // E2016: indirect cycle A -> B -> A
type C = { items: List[C] }    // E2016: the cycle still exists through the list
```

A cycle produces **a single** `E2016`, in the declaration where the cycle starts, with a note that
writes out the chain (`A -> B -> A`). `List` does not break the cycle: `List[C]` contains values of `C`, and
`C` contains a `List[C]`.

**Construction, reading and assignment.** The checker resolves the name of the record, checks
that the construction gives exactly its fields, checks the type of each value (`E2011` per field
that does not fit), checks that the root of a read is a record (`E2024`) and that the field
exists (`E2024`), and checks that a field is not assigned to (`E2025`).

The type of a record is a **value type**: it can be the type of a variable, of a
parameter, of the return of a function or of a field of another record. A record **cannot**
be the base of a refined type in this version.

### 5. Diagnostics

**Three new codes** are used. All three are free today (the last `semantic` code in use is
`E2022`), and all three are registered in `diagnostics.py` with the title and the category of this table,
which is the same that `docs/language-spec.md` and `docs/diagnostics.md` will have:

| Code | Title | Category | What it means |
|------|-------|----------|---------------|
| `E2023` | Invalid record construction | `type` | A well-formed construction but with the wrong fields: one is missing, there is an extra one or one is repeated |
| `E2024` | Invalid field access | `type` | A field is read and the value is not a record, or the record does not have that field, or an intermediate step of the chain is not a record |
| `E2025` | Cannot reassign a field | `semantic` | An existing field of a record, which is immutable, is assigned to |

The codes that already exist **do not change their meaning**:

| Code | Category | Use in records |
|------|----------|----------------|
| `E1101` | `syntax` | `type Point = {}`, `Point(1, 2)`, `{` on a line other than that of the `=`, trailing comma, field access on a call or a group |
| `E2005` | `semantic` | The root of an access or of an assignment is not declared |
| `E2006` | `semantic` | The name of a record is used for a function, a parameter or a variable |
| `E2011` | `type` | The type of a field value is not that of the field; a record where another type is expected; two different records compared |
| `E2012` | `type` | The type of a field is not a type, or is `Void` |
| `E2016` | `semantic` | Invalid record name (lowercase, built-in, repeated), repeated field, or cycle of records |

`E2016` keeps its title ("Invalid type declaration") and its category (`semantic`); what
this ADR does is **extend its documented description** to the cases of records, which is the same
meaning applied to the new construct. `E1101` keeps its title ("Unexpected token"): the
message says what was expected, as always.

**One diagnostic per problem, in a stable order.** A problem that can be determined on its own
is reported once. The concrete rules:

- In a construction, the fields that the record **does not have** are reported **in the order in which
  they are written**; the **repeated** ones, in the order in which they are written; the **missing** ones, in the
  **order of the declaration**.
- The **type** of each field value is checked separately: a value with the wrong type
  is an `E2011` of its own, and it does not mix with the errors in the form of the construction.
- In an **assignment** to an existing field **only** `E2025` is reported: **no** `E2011` is
  added for the type of the assigned value. The value is still checked inside (if it uses a
  name that does not exist, its `E2005` comes out), but it is not compared with the type of the field.
- If the root **does not exist**, the diagnostic is `E2005` and there is nothing else. If the root exists but
  **is not a record**, or the field **does not exist**, the diagnostic is `E2024`: the access error
  **takes precedence** over the immutability one, because without the field there is nothing to assign.

### 6. Tools and schemas

`Program.types` and `context.types` **are still only for refined types**. They do not mix: the
name `types` already means that in the repository, and `tooling._type_entries()` assumes that each
entry has `base` and `condition`. Records go in **new and separate** fields:

| Document | New field | Content | Version |
|----------|-----------|---------|---------|
| `nexora.inspect/2` | `Program.records` | The `RecordDecl` nodes of the tree | **No change** (`/2`) |
| `nexora.context/1` | `records` | One object per record: `name`, `fields` (name and type of each field), `valid`, `line`, `reason` | **No change** (`/1`) |

`valid` says whether the declaration can be used: it is `true` when the name, the fields and the types
are correct and the record is not in a cycle; it is `false` when the declaration has an error,
and `reason` says which one. `records` is `null` when the text has no structure, like `types`.

The `features` list of `nexora.context/1` gains the value `records` when the program declares
records. `nexora.symbols/1` **does not change**: symbols are functions, parameters and variables, and
a record name is not a value.

The new nodes of the tree are `RecordDecl`, `FieldDecl`, `RecordConstruction`, `FieldInitializer`,
`FieldAccess` and `FieldAssign`. The schema of the tree is **derived from the classes** (`schemas.py`), so
that the new nodes appear in the schema without extra work; `Program.records` is one more field
of `Program`, and `Program` keeps the order of its fields (the new fields go at the end, as
was done with `Function.examples`).

**Compatibility of the schemas, checked and not claimed.** What the policy of the
repository (`docs/json-protocol.md`) says is directional: *a new document must be accepted by an
old consumer*, which ignores the fields it does not know. That **holds**: no schema of the
repository sets `additionalProperties` (`tests/test_tooling.py:96` checks it), so a
document with `records` validates against the old schema. What that policy does **not** say is that a
document **saved** with 0.7.0 validates against the new schema: with `Program.records` and
`context.records` as required fields, **it does not validate**. It is the same case that already happened when
in 0.3.0 `Program.types` was added to the tree without changing the number of `nexora.inspect/2`, and it is
what will be recorded in the history of `docs/json-protocol.md`. No compatibility that has not been checked
is promised.

The versions of the formats **do not change**: `nexora.inspect/2`, `nexora.context/1`,
`nexora.symbols/1`, `nexora.diagnostics/1`, `nexora.test/1` and `nexora.result/1` stay the same. Fields
and node kinds are added, which is an additive change. `nexora.capabilities/1` does not change either:
its `types` are the names of the **built-in** types, and a record belongs to the user.

### 7. What this ADR does not accept from 0012

These remain outside, and are still a proposal in 0012:

- **enums**, `match`, patterns and **exhaustiveness** (D05, D06, D07);
- `Option`, `Result` and their syntax;
- **user generics** and generic functions (D03);
- **refinements** over records or over any compound type (D04);
- data **input**, **modules** and verifiable evidence (E, F, H, I);
- `type_repr`, the serialization of values in JSON and any change of the schemas towards a structured
  type;
- **recursive records**, **refined record types**, **methods**, **mutation** of
  fields, **structural records** and the **type parameters** of a
  record.

## Facts verified in the repository

These points were checked in the code, they are not deduced:

| Fact | Where |
|------|-------|
| `E2023`, `E2024` and `E2025` are not used; `E2022` is the last `semantic` code | `src/nexora/diagnostics.py:74-127` |
| The registry of codes, their titles and their categories is the **only** source; the specification and `docs/diagnostics.md` are compared with it | `tests/test_diagnostics.py:103-106`, `tests/test_docs.py:294-299` |
| Every registered code has to be **used** in the source code | `tests/test_diagnostics.py:128-133` |
| The prefixes per category: `semantic` and `type` both use `E2` | `tests/test_diagnostics.py:120-125` |
| `Program.types` and `context.types` are for refined types, and `_type_entries()` uses `base` and `condition` | `src/nexora/tooling.py:371-385` |
| `ast.Program` is built positionally in one more place (`interpreter.py:685`), so the new field needs a default value | `src/nexora/ast_nodes.py:252-255` |
| `unparse` ends in `node.callee`, `_evaluate` ends in `_call` and `_skipped` does not know the new nodes: all three need branches | `src/nexora/interpreter.py:477-496, 638-656, 659-676` |
| `types.equal`, `display`, `to_data`, `widen`, `root` and `substitute` have no branch for a nominal user type | `src/nexora/types.py:196-219, 224-234, 255-280, 346-382` |
| `type_adapter` resolves names with `_resolve_name` and only knows primitives and refined types | `src/nexora/type_adapter.py:46-51, 162-167` |
| The parser sends **every** `IDENT . IDENT` to the qualified call, and the diagnostic "Expected '(' to call…" is the one that has to be kept | `src/nexora/parser.py:630-636, 672-692` |
| The recovery of the parser synchronizes with the next `fn` or `type` that starts a line: a broken record declaration does not break the recovery | `src/nexora/parser.py:209-214` |
| The lexer emits a `NEWLINE` token per line break and does **not** change with braces: a multi-line declaration is solved in the parser, without touching the lexer | `src/nexora/lexer.py:154-171` |
| `type` inside a function is already `E1101` | `src/nexora/parser.py:463-468` |
| `result` only exists in an `ensures` of a function that returns a value | `src/nexora/checker.py:789-798` |
| The schemas do not set `additionalProperties` | `tests/test_tooling.py:96` |
| The compatibility policy and its history | `docs/json-protocol.md:176-205` |
| The qualified call diagnostics that have to be preserved | `tests/test_text_operations.py:402, 412` |

## Decisions taken here, and why

| Decision | Reason |
|----------|--------|
| **Opaque identity by declaration**, not by name | It is what makes two records with the same name and the same fields different types. It is D02, and it is what the interpreter needs to compare values |
| `Program.records` and `context.records` **separate** from `types` | `types` already means "refined types" in the code and in the documentation; mixing it would change the meaning of an existing field and would break `_type_entries()` |
| **No new version** of the JSON formats | Adding fields and node kinds is an additive change, which is what the policy of the repository says |
| Access chains **without a fixed limit** | The limit of two levels was arbitrary: what matters is that every intermediate step is a record, and the analyzer checks that |
| The root of the access has to be **a name** | `f().x` and `(p).x` have no clear reading, and the current parser already rejects them with `E1101`; keeping it avoids touching diagnostics that do not need it |
| `E2023` and `E2024` are of category `type`; `E2025` is `semantic` | An error in the form of a construction or of an access is a type problem; immutability is a rule of the program, like the reassignment of a variable (`E2007`, `semantic`) |
| `E2025` does **not** add an `E2011` for the value | If the field cannot be assigned, the type of the value is irrelevant: two errors for a single problem |
| The access error **takes precedence** over the immutability one | If the field does not exist, there is nothing immutable to mutate: a single diagnostic, and the one that explains the real problem |
| No trailing comma | It is what lists and calls of the language already do; an exception would be a difference that brings nothing |
| `List[Point]` **is** allowed | It is the same `List[T]` type as always, with a new element type; the model and the analyzer already do it without extra work |
| A **refined type cannot be refined** with a record | Refinements over compound types (D04) are not implemented; it is said explicitly instead of letting the analyzer guess |

## What it does not guarantee

- That field access is fast: the cost of the representation has not been measured.
- That records can be compared with each other with `<` or `>`: there is no ordering; only `==` and `!=`.
- That a record can be refined, have methods or allow recursion: none of that is implemented.
- That the identity of a record survives a change of name or of fields: it is the identity of
  **that declaration**, and that is why a change in the declaration is a change of type.
- That accepted programs are free of runtime errors: division
  by zero, overflow, broken contracts and `List.get` out of range still exist.
- That the type model covers future types: it covers only those that exist today.

## Out of scope

Besides what is listed in section 7, these are out: higher-order functions over
records, ordered equality, type aliases, custom printing, structured
serialization of values, implicit conversion between records with the same shape, the
serialization to JSON of values at run time and any optimization of the interpreter.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| Accepting the whole of 0012 | It would accept enums, `match`, `Option`/`Result`, `type_repr` and generics that do not exist; it would turn a proposal into a false promise |
| Rewriting 0012 to mark what is implemented | It violates the rule that decisions are not rewritten and erases the historical context |
| Leaving 0012 as the only reference and not creating this one | The code and the documentation would be left without a decision that backs them |
| Putting records in `Program.types` and `context.types` | It would change the meaning of an existing field, would force `nexora.inspect/3` and would break `_type_entries()`, which assumes `base` and `condition` |
| Identity by name (`"Point" == "Point"`) | Two different declarations with the same name would be confused; the interpreter could not know whether two values are of the same type |
| **Structural** records (two records with the same fields are the same type) | It contradicts D02 and makes adding a field to a record break the others |
| A fixed limit of two levels in the access | It is arbitrary: what matters is that every intermediate step is a record, and the analyzer decides that |
| Field access on a call or a construction | It has no clear reading and would require a general postfix system, which is postponed |
| `E2023` and `E2024` of category `semantic` | They are type problems, not name problems: the type of the value or of the field is what is wrong |
| A trailing comma allowed | It would break coherence with the lists and calls of the language |
| Requiring a `Void` return type or a `main` with records | There is no reason; records are values like the others |

## Compatibility

**Programs.** No program valid in 0.7.0 stops being so or changes its result. The grammar
only grows: `type Name = { ... }` was not valid code before (it was `E1101`), and `a.b` without
parentheses afterwards was also `E1101` ("Expected '(' to call 'a.b'"), except when `a` was the
name of a type, which is the case that is kept **exactly the same**. A program that today uses
`Text.length` (with or without parentheses) does not change: the form of the qualified call is decided by
tokens, not by the name. The only observable difference is that `p.x`, where `p` is a variable
that is not a type, goes from being `E1101` to being a field access (or an `E2024`/`E2005` if the
variable does not exist or is not a record). The uses whose diagnostic changes were already invalid.

**Tools.** The changes are additive and do not change the version of the schemas:

- `nex inspect`: nodes `RecordDecl`, `FieldDecl`, `RecordConstruction`, `FieldInitializer`,
  `FieldAccess` and `FieldAssign`; the `records` field in `Program`; the `type` field of an expression
  can be the name of a record.
- `nex context`: the `records` field, with `name`, `fields`, `valid`, `line` and `reason`; the value
  `records` in `features`.
- `nex symbols`: no changes.
- `nex inspect` and `nex context` still do not run the program.

**Version.** The implementation of this stage will move the state of the repository to `0.8.0` and the
specification to `0.8`, following what 0013 did with 0.7.0. It is not declared published: there
is no tag and no published package. Accepting this decision **changes no version**: the
implementation changes it, and it is still pending authorization.

## Required changes

- **Specification** (`docs/language-spec.md`): grammar of the declaration and the construction of
  records, access chain, immutability, nominal equality, printing, the table of types and the
  table of diagnostics with the three new codes, and the section on limitations.
- **Diagnostics** (`docs/diagnostics.md`): one row for each new code, with the same title
  as the registry.
- **Guides**: `types.md` (records), `limitations.md` (what still does not exist) and `index.md`.
- **Roadmap** (`docs/roadmap.md`): records stop being pending.
- **Architecture** (`docs/architecture.md`): the type model is no longer only "refined types".
- **JSON protocol** (`docs/json-protocol.md`): the new fields in the change history and the
  real direction of compatibility.
- **Inspection schema** (`docs/inspect-schema.md`): `Program.records` and the rows of the new
  nodes.
- **Code**: `types.py`, `type_adapter.py`, `ast_nodes.py`, `parser.py`, `checker.py`,
  `interpreter.py`, `values.py`, `tooling.py`, `schemas.py`, `diagnostics.py`.
- **`CHANGELOG.md`**, `version.py` and `pyproject.toml` to `0.8.0`.
- **Decision index** (`docs/decisions/README.md`): the row of this 0014, as **accepted** (it already
  is when this ADR is accepted).

## Planned regression tests

The implementation relies on these tests, which run in the full suite:

| File | What it pins down |
|------|-------------------|
| `tests/test_records_syntax.py` | Grammar of the declaration and the construction, required and named fields, multi-line, `{` on its line, empty record, trailing comma, forward references, recovery of the parser |
| `tests/test_records_types.py` | Nominal identity, fields and their types, cycles (direct, indirect and through `List`), `List[Point]`, refinement with a record, value and reference types |
| `tests/test_records_values.py` | Construction, reading, access chains, equality by value, `E2011` between different types, immutability and `E2025`, `result.x` in an `ensures` |
| `tests/test_records_diagnostics.py` | The three new codes: title, category, message, position and order; the precedence of the access error over the immutability one |
| `tests/test_records_tools.py` | `Program.records`, `context.records` with `valid`, `features`, the new nodes in the schema and the documents against their schema |
| `tests/test_text_operations.py`, `tests/test_parser.py`, `tests/test_tooling.py`, `tests/test_docs.py` | What must not change: the qualified call diagnostics, the tree, the documents and the coherence of the documentation |

The runnable example is `examples/records.nex`, with its recorded output in
`tests/golden/examples/records.run.stdout`. The full suite (`pytest -q`), `ruff check .`,
`npm test --prefix npm` and `git show --check` are run when closing the increment; the real result
is recorded in the report of the change, not in this ADR.

## Relation to 0012 and the index

- 0012 **is not rewritten**. Its header ("not accepted", "implementation: none") describes the
  moment when it was written; this ADR explains which part of D02 is decided and with what scope.
- This ADR neither replaces nor repeals 0012: it complements it for the part of D02 that this
  document decides.
- 0013 still accepts only D01, D08 and D09. This ADR neither modifies nor replaces 0013.
- The index [`README.md`](README.md) records 0014 as **accepted**, with the implementation
  pending.

## Questions that remain open

These do not block the decision. The trailing comma (**not** allowed, for coherence with lists and
calls) and the version (`0.8.0` for the repository and `0.8` for the specification, when it is
implemented) are resolved when this ADR is accepted. Only one implementation question
remains open:

1. **The reason of an invalid record in `context.records`.** The `reason` field carries the text of the
   diagnostic that explains why the declaration cannot be used. The exact form of that text is
   an implementation detail, as long as it is the same string the person sees in the error.
