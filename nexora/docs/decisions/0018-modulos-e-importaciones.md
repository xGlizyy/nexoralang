# 0018 — Modules and imports

- **Status:** accepted. Its programs are written in the syntax of their time, before 0.12: since
  0.12 the language writes them as [decision 0019](0019-identidad-propia-del-lenguaje.md) describes,
  and `nex migrate` rewrites them.
- **Version:** 0.11.0 (state of the repository; not published in any package)
- **Date:** 2026-10-22
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (only what has been checked runs), [0005](0005-diagnosticos-y-esquemas-json.md) (diagnostics
  have a stable code) and [0014](0014-registros-nominales-inmutables.md) (records are
  nominal). **It modifies none.**
- **Related to the design draft:** it implements its §8 ("Modules") and its rule R14 (no
  circular imports) **within the scope the language has today**. The draft is from v0.1 and
  writes another syntax; here the one that fits the current language is decided.
- **Implementation:** 0.11.0. The module loader is in `modules.py`; the rest of the work
  is in `tokens.py`, `ast_nodes.py`, `parser.py`, `checker.py`, `pipeline.py`, `interpreter.py`,
  `cli.py` and `lsp.py`. The evidence is in `tests/test_modules.py` and in the examples of
  `examples/modules/`.

## Context

A NEXORA program is **a single file**. Everything the language has today fits in one
file, and that is why the language has no modules: it did not need them.

As soon as a project grows, one file falls short, and the style of solving it by importing
pieces of code from somewhere else has a cost that is not only about length: the analyzer cannot
know which names exist, so it cannot check anything. A program that imports code from
somewhere else is not checked, and [decision 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
does not allow running what is not checked.

The design draft (`docs/fase-1-diseno.md` at the root of the repository) anticipates it in its §8:

```nexora
import http
import app/models.{User, Order}
```

- A file is a module; its name is that of the file.
- Everything is private except what is marked with `pub`.
- Every type is also a namespace.
- Circular imports are not allowed.
- The entry point is `fn main()` in the file that runs.

The [specification](../language-spec.md) records it as a known limitation (§13: "A program is a
single file: there are no modules or imports") and as a planned feature (§14).

## Decision

Modules are implemented as **a file is a module**, with the imports at the beginning
of the file, one namespace per module and privacy with `pub`.

### 1. The syntax

```
import "app/models.nex"
```

An import is a **top-level declaration** and goes **before any other
declaration** of the file, as in the draft (`program = { import } { item }`).

The path is a **text literal**, with the extension of the file, and it is resolved **relative to the
file that imports**, not relative to the working directory:

- It is a text literal, and not a word, because the language already treats paths that way: the
  capabilities are declared `uses read "data.txt"`, with a text literal and with the path written.
- The extension is written because the language does not guess: `List` is not `List[T]`, and a file is not
  a file without a name.
- The path is relative to the file that imports, and not to the working directory, because a program
  has to depend on where it is, not on where it is run from.

What there is **not** in this version: the aliases (`import "x.nex" as y`) and the selective import
(`import "x.nex".{A, B}`) of the draft. They are explained further down.

### 2. The namespace

An import binds a **namespace** to the name of the imported file, without its extension:

```
import "app/models.nex"
...
let p = models.Point(x: 1, y: 2)
```

The names of a module are used **qualified**: `models.add(1, 2)`, `models.Point(...)`,
`models.Percent`. A module never drops its names into the scope of whoever imports it.

The name of the namespace is that of the file without the extension. If two imported modules
had the same name, it is an error (`E2030`): renaming the file solves it, and the language
does not decide yet what a module whose name does not match its file is called.

### 3. Privacy

Everything a module declares is **private** unless it marks it with `pub`:

```
pub fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn helper(x: Int) -> Int {
    return x * 2
}
```

`models.add` can be called from outside; `models.helper` cannot, and calling it is an error (`E2028`).

`pub` applies to functions and to types, including records: `pub type Point = { x:
Int, y: Int }` makes the record and its constructor public.

The file that runs is the exception: its names are those of the program, and all of them are
visible, because they are its entry point.

### 4. Circular imports

They are not allowed, and they are an error (`E2029`), with the modules involved in the message. It is
rule R14 of the draft.

A module A imports B and B imports A: there is no order in which both can be defined, and
allowing it would give two different readings of the same program depending on where you start.

### 5. Types cross modules

A record of another module is a record like any other, and **nominal**: the record
`Point` of the module `models` is not the same type as a `Point` of another module, and a value of one is not
accepted where the other is expected.

In the analysis, the names of a module are qualified (`models.Point`), so that two
modules can declare records with the same name without the analyzer mixing them up. The
name that whoever writes the code sees is the one they write: `models.Point`.

### 6. What is loaded, and when

Modules are loaded when the program is **analyzed**, not when it runs: they are part of the
program, and the program has to be checked before running (decision 0002).

The loader (`modules.py`) resolves the paths, reads the files, analyzes each module only once
(every file is read once, even if several import it) and detects cycles.

A module that cannot be read is a diagnostic, with the same code the command
line uses when the main program cannot be read (`E0001`).

### 7. The scope of this version

What **works**:

- `import "path/file.nex"` at the beginning of the file.
- One namespace per module, with qualified names.
- `pub` and privacy.
- The records and functions of other modules, with their nominal identity.
- Circular imports, detected and explained.

What does **not** work yet, and why:

- **Aliases and selective import.** The draft has them; here they are not there, because both are
  needed for the same reason: to keep two modules with the same name from getting in each other's way. With the
  namespace and the name of the file, a clash is a clear error, not a silent
  conflict. When it is needed, an alias is one more keyword and one more rule.
- **The playground.** The playground receives the program as text and runs it in a container; it does not
  have the files next to it, so a program with imports cannot run there.
  The limitation is written in the documentation of the playground.
- **The examples (`example`) of the imported modules.** They are checked, because the module is
  analyzed entirely, but `nex test` only runs those of the file it was given.
- **`nex inspect`** only describes the tree of the file it was given (with its `imports`); the
  tree of the imported modules does not appear. **`nex symbols` and `nex context`** do include the
  names and functions of the imported modules, each one with a new `file` field, at the end
  of the object (decision 0008, §8): the file that declares it, with the path relative to the program and `/`
  as the separator, never the absolute path of the machine. The schemas record it: `nexora.inspect/2`
  (`imports`, `public`, `qualifier`), and the `file` field in `nexora.context/1` and `nexora.symbols/1`.

## Facts verified in the repository

| Fact | Where |
|------|-------|
| `import` and `pub` were already reserved for this | `tokens.py` (`RESERVED_WORDS`) |
| The design draft already proposes modules and their syntax | `docs/fase-1-diseno.md` (§8, R14) |
| The specification already marks it as a limitation and as planned | `docs/language-spec.md` (§13, §14) |
| The analyzer already resolves the qualified calls of a type | `checker.py` (`_qualified_call`), `parser.py` (`_qualified_call`) |
| The interpreter already resolves functions by name | `interpreter.py` (`_call`) |
| Paths are already declared with text literals | `parser.py` (`_uses_declaration`), the example `uses read "data.txt"` |
| The command line already reads the program from a file | `cli.py` (`_load`) |

## Decisions taken here, and why

| Decision | Why |
|----------|-----|
| The path is a text literal, with the extension | Like `uses read "data.txt"`: the language writes paths, it does not guess them |
| The path is relative to the file that imports | A program depends on where it is, not on where it is run from |
| One namespace per module | The names of another module are not dropped into the scope of whoever imports: there are no silent clashes |
| The namespace is the name of the file | It is what the draft says, and no extra keyword is needed |
| `pub` and nothing else | Everything private by default is the safest; the draft says the same |
| Circular imports are an error | R14 of the draft: there is no possible order of definition |
| Modules are loaded when analyzing | They are part of the program: what is not checked does not run (decision 0002) |
| The internal name of types is qualified | Records are nominal: two `Point` from different modules are different types |
| No aliases or selective import | They are needed for the same thing, and they can be added later without breaking anything |
| The playground does not support them | It receives the program as text; it does not have the files next to it |

## What it does not guarantee

- There are no aliases, no selective import and no `import *`: the names of a module are used
  qualified and only qualified.
- There are no packages, no module registries and no search paths: the only way to import is
  a path relative to a file.
- There is no `main` per module: the entry point is that of the file that runs, and an imported
  module does not need one.
- The tree of the imported modules is not seen in `nex inspect`; their names and functions are seen in
  `nex symbols` and `nex context`, with the file that declares them.
- The playground does not run programs with imports.
- Two imported modules with the same file name are an error; there is no way to rename them
  when importing them.

## Out of scope

- Aliases and selective import: they will be decided when there are two modules with the same name.
- `pub` on type refinements and on contracts.
- A package or dependency manager: the language has neither a `cargo` nor an `npm`; the
  imports are paths to files.
- Nested modules (a module inside another one) and standard libraries as modules.
- `match` and user enums: they are still the big part of
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md), which is still a proposal.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| `import models` (a word, as in the draft) | The language writes paths with text literals; a word would leave the extension and the directory open to interpretation |
| `import models.nex` without quotes | A path without quotes is indistinguishable from a name; the language has that ambiguity nowhere |
| Bringing the names into the scope of whoever imports (`from x import y`) | The names of two modules would get in each other's way; the namespace makes the clash visible |
| A single flat namespace for the whole program | A `Point` of one module and another of another would be the same name, and records are nominal |
| A `main` per module and the one that runs chosen by name | There is no way to know which module is the entry one without another rule; the file that runs says so |
| Loading the modules when running | What is not checked does not run (decision 0002): the module is part of the program |
| Ignoring cycles and leaving them for execution | Two readings of the same program depending on where you start; the error has to come out before |
| Leaving modules until after enums and `match` | Modules do not need `match`: they are a namespace and a name resolution, and the type checking already knows how to do it |

## Compatibility

- The programs that already exist keep checking the same: there were no imports, so there
  is no program whose result changes.
- `import` and `pub` become keywords of the language. Before they were reserved words, which
  could already not be used as names: a program that used `import` as a name did not compile
  before, and it still does not compile, with the same code (`E1103`).
- The names of modules are qualified in the analysis: a type that used to be called
  `Point` and was written `Point` is still written the same way, and now it can be called `models.Point`
  if it comes from a module.
- The specification moves to version 0.11 and the reference implementation to 0.11.0. The
  0.10.0 already published on npm and on PyPI is not touched.

## Required changes

- `tokens.py`: `import` and `pub` go from reserved words to keywords.
- `ast_nodes.py`: `ImportDecl`; `Program.imports`; the `public` field of functions,
  records and refined types.
- `parser.py`: the import declarations, `pub`, and qualified types
  (`models.Point`).
- `checker.py`: the prefix of the names of a module, privacy, the qualified calls
  to a module and qualified types.
- `modules.py` (new): the loader, the import graph and the detection of cycles.
- `pipeline.py`: the analysis of a program with its modules.
- `interpreter.py`: the public functions of the imported modules, with their qualified name.
- `cli.py` and `lsp.py`: the loader, with the directory of the file as the base.
- `diagnostics.py`: `E2027` (unknown module), `E2028` (private name), `E2029` (circular
  import) and `E2030` (two modules with the same name).

## Planned regression tests

| File | What it pins down |
|------|-------------------|
| `tests/test_modules.py` | The syntax, the namespace, privacy, cycles, records across modules, relative paths and the read error |
| `tests/test_modules_syntax.py` | That a badly written import is a syntax error |
| `examples/modules/` | A program with modules, and its recorded output |
| `tests/test_diagnostics.py` | That the four new codes have a text, a position and a suggestion |

## Relation to the previous decisions and the index

It is added to the decision index as accepted. It modifies none: it uses the analyzer and the
interpreter that the previous decisions defined, and modules are the part of the design
draft that was missing.

## Questions that remain open

- Do aliases and selective import come with `match` and enums, or before? Rule R6
  of the draft says that an unused import is an error: does an
  import whose only use is a type count as unused?
- Can a module declare a `main`? Today it is ignored, because the entry point is that of the
  file that runs.
- Should the path of an import be able to be an identifier (`import math`) as well as a
  literal? It would be shorter, and less explicit.
- Are the refined types and contracts of a public module checked the same way as the private ones?
  Today yes, because the module is analyzed entirely.
