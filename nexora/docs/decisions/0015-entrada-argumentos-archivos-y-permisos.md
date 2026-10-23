# 0015 — Input, arguments, files and permissions

- **Status:** accepted
- **Version:** 0.9.0 (state of the repository; not published in any package)
- **Date:** 2026-10-21
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (only what has been checked runs), [0005](0005-diagnosticos-y-esquemas-json.md) (stable diagnostic
  codes), [0009](0009-memoria-agotada.md) (runtime errors),
  [0011](0011-operaciones-sobre-textos.md) (functions of a type) and
  [0014](0014-registros-nominales-inmutables.md) (nominal records). **It modifies none.**
- **Replaces:** none. **It neither modifies nor replaces
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)**: its input part (D11)
  and its effect system (`uses`) remain a proposal; this decision describes another way of
  doing the same thing, and only decides what is implemented.
- **Implementation:** 0.9.0. The code is in `capabilities.py` (the permission model, without the
  operating system), `host.py` (what a program can do besides computing), `parser.py`,
  `checker.py`, `interpreter.py`, `cli.py`, `api.py` and `worker.py`; the evidence is in the
  tests of the section "Planned regression tests".

## Context

Up to 0.8.0, NEXORA is a computation language: a program reads literals, calls its own and
built-in functions and writes with `print`. It reads nothing from outside. It is a deliberate decision, not
an oversight: [decision 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) makes
the interpreter run only checked programs, and the design draft
(`docs/fase-1-diseno.md` at the root of the repository) leaves input and effects for
later.

That limitation prevents writing real console applications: a program cannot receive the
arguments it is invoked with, read from a pipe, or open a data file.

The problem is not only adding a read function. It is doing it **without turning the interpreter into
something that can touch the system that runs it**. A language that reads files for whatever reason
is a security problem for whoever runs it: the playground of the website runs code from
visitors, and the MCP server analyzes code that comes from an assistant.

Hence the form decided here: **the program declares what it needs, whoever runs it
grants what they allow, and the environment decides what can be granted**. None of the three things
is enough on its own, and the interpreter checks all three on every access, not only at the start.

## Decision

### 1. What a program can do

Four built-in functions are added:

| Function | What it does | Permission |
|----------|--------------|------------|
| `args() -> List[Text]` | The arguments the program was run with | None: always allowed |
| `input() -> Text` | Reads **one line** from the standard input, without the line ending | None: always allowed |
| `read_file(path: Text) -> Text` | Reads a whole text file | `uses read` **and** authorization from whoever runs it |
| `write_file(path: Text, text: Text) -> Void` | Writes a text file (creates it if it does not exist) | `uses write` **and** authorization from whoever runs it |

`print` is still the standard output and does not change.

The arguments and the standard input **need no declaration**: they are the normal way of invoking
a console program, and they give access to nothing that whoever runs it has not already given. Files do, because
touching the disk is what is restricted.

### 2. How the program declares what it needs

A new declaration, at the top level of the file, next to functions and types:

```nexora
uses read "data/inputs.txt"
uses write "data/output.txt"
```

`uses` declares a **capability**: "my program needs to read this". Declaring grants nothing: it is
half of the model, not the permission.

The declaration is a path, written as a text literal. Relative paths are resolved
against the **working directory** of the process, which is where the program is expected to
run and where whoever runs it sees their files.

### 3. The permission model: the intersection

The effective capability of an operation is the **intersection** of three things:

1. **What the program declares**: a `uses read "path"` (or `uses write`) that covers the path.
2. **What whoever runs it grants**: `--allow-read=PATH` (or `--allow-write=PATH`) in the
   `nex run` command, repeatable.
3. **What the environment allows**: whether the runtime environment supports files.

All three have to be there. Consequences, which are the point of the decision:

- **Declaring does not grant.** A program with `uses read "secret.txt"` that runs without
  `--allow-read` gets a permission error, not the file.
- **Granting does not enable.** `--allow-read=secret.txt` does not allow reading it if the program does not
  declare it.
- **The environment has the last word.** In an environment that does not support files, no combination enables them.

Whoever grants does so **explicitly, automatably and reproducibly**: the exact command is the
permission. There are no interactive permissions, no "do you want to allow this file?", no warning that
depends on an answer: the same program, with the same command, always behaves the same.

Reading and writing are granted **separately**: `--allow-read` does not enable writing, nor
the other way round.

### 4. How paths are confined

Confinement is applied to the **resolved** path, never to the written text:

- The path of the program and the granted path are resolved with `os.path.realpath`, which follows
  symbolic links and Windows directory junctions. A path that does not exist yet (when
  writing) is resolved on its existing part.
- The comparison is between resolved paths and **by segments**, so that `data/secret` does not
  slip into a scope `data` just because the text starts the same.
- A `..` that leaves the scope is resolved outside it, and therefore it is not covered.
- A symbolic link inside the scope that points outside is resolved outside it, and therefore it
  is not covered either.

**A text prefix is not checked.** A text prefix is not a confinement: `data2` is not
inside `data`, and a symbolic link can point anywhere. The textual check
is only used in the static analysis, as a help, never as a security boundary.

### 5. What the static analysis does and what the interpreter does

`nex check` can warn about what is seen in the text:

- A call to `read_file` or `write_file` **without** a `uses` declaration that covers it is the error
  `E2026`. When the path of the call is a literal and no declaration covers it, it also
  warns; if the path is not a literal (it depends on a variable), the analysis cannot know it and does not
  warn.

That is a **help**, not the security. The real boundary is applied by the interpreter, on every access:

- If the environment does not support files, `read_file` and `write_file` fail with `E3008`, even if the
  program declares the capability and whoever runs it has granted the permission.
- If the declaration or the authorization is missing, the same: `E3008`.

A program with `E2026` never runs, because the static analysis is mandatory
(decision 0002). A program without `E2026` that tries something not allowed stops at run time, with
`E3008`. Both paths are closed.

### 6. Restricted environments

| Environment | Files | Arguments | Standard input |
|-------------|-------|-----------|----------------|
| `nex run` | Only with `--allow-read` / `--allow-write` and with the declaration of the program | Those passed after `--` | That of the process |
| `nex test` | Same as `nex run` (the examples run) | Those passed after `--` | That of the process |
| The playground worker | **Never** | Those the visitor sends, if the protocol supports them | The one the visitor sends |
| The MCP server | **Never** (it only analyzes, it does not run) | — | — |

In the worker, the protocol **has no** permission fields: even if a request tries to grant them,
they are ignored, and the program gets `E3008` when it touches a file. The playground is public: there is
no way for a visitor to turn it into an environment with access to files.

### 7. The standard input and its end

`input()` reads a line and returns its text without the line ending. An empty line returns the
empty text. When there is nothing left to read, `input()` is a runtime error `E3009`: the
program stops and says so. Reading "until the end" without stopping cannot be expressed yet; when
`Option` or a function that returns all the lines exists, it will be added.

### 8. Arguments

`nex run program.nex -- one two` gives the program the arguments `one` and `two`. Without `--`, there are no
arguments. `args()` returns a `List[Text]`, in the order in which they were passed.

### 9. The option without a path, which is not included

Granting general access ("to any path") **is not included** in this decision. If it were ever
included, it would have to be an explicit option, with a visible warning on every run,
and it would still be impossible in the playground and in MCP. It is not implemented by accident: there is
no way to grant it.

## Facts verified in the repository

| Fact | Where |
|------|-------|
| The interpreter only runs checked programs; `run` receives a `CheckedProgram` | `src/nexora/interpreter.py`, `src/nexora/pipeline.py` |
| The stages of the language do not touch the operating system: only the CLI, `__main__` and the worker can import `os`, `pathlib` or `subprocess` | `tests/test_security.py:61-78` |
| The MCP server only analyzes: none of its seven tools runs a program | `src/nexora/mcp_server.py:11`, `:72` |
| The playground worker is a separate process that receives a JSON and returns another one; its protocol has no permission fields | `src/nexora/worker.py:9-17` |
| The output of the program is written by the function the interpreter receives (`run(checked, write)`), not by the interpreter | `src/nexora/interpreter.py:112-118`, `src/nexora/cli.py:253` |
| `print` and the conversions are resolved in the interpreter, and the functions of a type in `prelude.py` | `src/nexora/interpreter.py:590-632`, `src/nexora/prelude.py:145` |
| Diagnostic codes have their number and their category in a single registry, and the tests compare the registry with the specification and with `docs/diagnostics.md` | `src/nexora/diagnostics.py:74`, `tests/test_diagnostics.py:103`, `tests/test_docs.py:294` |
| The last codes in use are `E2022` (semantic) and `E3007` (runtime) | `src/nexora/diagnostics.py:74-127` |
| The grammar is that of `docs/language-spec.md`, section 3, and the lexer already recognizes `//` as a comment | `docs/language-spec.md:126-195`, `src/nexora/lexer.py` |
| The playground runs every program in a separate process, with time and output limits | `servidor/src/playground/worker.js`, `servidor/src/playground/router.js` |
| 0012 proposes an `Input` record and `main(input)`, and postpones the `uses` effect system | `docs/decisions/0012-…md:605-624`, `:642`, `:988` |

## Decisions taken here, and why

| Decision | Reason |
|----------|--------|
| Arguments and standard input are not declared | They give access to nothing that whoever runs the program has not already given; declaring them would be noise |
| Files are declared with `uses` | It is what the program says it needs: readable, reviewable and checkable by the static analysis |
| The effective capability is an intersection of three | None of the three is enough on its own; a single decision (of the program, of whoever runs it or of the environment) never enables on its own |
| Paths are confined on the resolved path | A text prefix is not a confinement: `..` and symbolic links get around it |
| The real check is done by the interpreter, not by the analysis | The static analysis can be fooled; the interpreter is the boundary |
| `--allow-read` and `--allow-write` are independent | Reading and writing are not the same, and an application that only reads does not need write permission |
| The option without a path is not included | General access to a disk from a language is not a capability granted for convenience |
| The playground and MCP do not support files, without exception | The playground runs code from visitors; MCP analyzes code from an assistant |
| `input()` fails when it reaches the end | Returning an empty text would not tell the end from an empty line, and a program that reads in a loop would never end |
| `uses` is a declaration, not an expression | It is a property of the program, not a value: it cannot go through a parameter or be built at run time |

## What it does not guarantee

- That the static analysis detects every misuse: only what is seen in the text. Security
  does not depend on it.
- That path confinement holds for a file system that changes while the program
  runs (a `..` resolved at one moment and another at another).
- That reading a granted file is safe in itself: the content belongs to the file, and the program
  can interpret it as it likes.
- That `input()` can read "until the end" without stopping.
- That there is isolation against the network, processes or environment variables: they do not exist
  yet.
- That programs with access to files are safe on a public server: that is why the
  playground does not support them.

## Out of scope

- The network, external processes and environment variables.
- Interactive per-file permissions and warnings that depend on an answer.
- Writing to a directory, creating directories, renaming or deleting: only reading and writing a
  text file.
- Files that are not text (binary).
- Access to the network, to sockets or to environment variables.
- `Option`, `Result` and the other constructs of 0012.
- Modules and imports.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| An `Input` record with `main(input)`, as 0012 proposes | It changes the form of `main` and makes every program that reads nothing declare a parameter it does not use; besides, it postpones the problem of permissions, which is the hard one |
| Declaring the permission only in the program | The program could ask for whatever it wanted; whoever runs it could deny nothing |
| Granting only from whoever runs it | Whoever runs it cannot know what the program is going to read; granting "everything" out of caution is the opposite of explicit |
| A text prefix check | `data2` slips into `data`, and a symbolic link inside the scope can point outside. It is not a confinement |
| Granting access to any path with an option | It is general access to the disk with one word; whoever runs it stops controlling what happens |
| An interactive warning per file | It depends on an answer: it is neither automatable nor reproducible, and on a server there is nobody to answer |
| Letting the static analysis be the security | It can be fooled: computed paths, literals built at run time, or a path that changes between the analysis and the execution |

## Compatibility

**Programs.** No program valid in 0.8.0 stops being so or changes its result. `print`,
`to_text`, `to_float`, `to_int` and the functions of `Text`, `Int`, `Float` and `List` stay the same. The
programs that do not use the new functions are not affected: `args()` returns an empty list and `input()` reads from the standard input, which is what
the process already did.

**Tools.** The changes are additive and do not change the number of any JSON format: a
`UsesDecl` node, one more field in `Program`, and the new field of `nexora.context/1`. The schemas are
regenerated; a new document validates against the old schema, which ignores the fields it does not know.

**Codes.** Four are added: `E2026` (the declaration of a capability is missing), `E3008` (permission
denied) and `E3009` (no input left). The previous ones do not change their meaning.

## Required changes

- **Lexicon and syntax**: the `uses` declaration, its two forms, and the grammar of `docs/language-spec.md`
  (section 3).
- **Type**: the `UsesDecl` node, the `uses` field in `Program`, and the four functions in the registry
  of the built-in ones.
- **Checking**: the declarations, the error `E2026` when a call has no declaration that
  covers it, and the table of diagnostics.
- **Interpreter**: `args`, `input`, `read_file` and `write_file`, with the permission check on
  every access.
- **Permissions**: the model of the intersection and path confinement, in a separate module that
  does not touch the system: the interpreter asks, the environment grants.
- **CLI**: `--allow-read` and `--allow-write` in `nex run` and `nex test`, and the arguments after `--`.
- **Restricted environments**: the playground worker without access to files, and MCP the same.
- **Tools**: `nexora.context/1` with the declared capabilities, and `nexora.inspect/2` with the
  new node.
- **Documentation**: the specification, `docs/diagnostics.md`, `types.md`, `limitations.md`,
  `docs/playground.md`, `docs/cli-reference.md` and the guide of the site.
- **Examples**: a program that reads arguments and an authorized file, and one that fails without permission.

## Planned regression tests

| File | What it pins down |
|------|-------------------|
| `tests/test_input_arguments.py` | Empty and multiple arguments, with spaces and with Unicode; `args()` without arguments |
| `tests/test_input_stdin.py` | Several lines, an empty line, the end of the input (`E3009`), and that the input is read once and in order |
| `tests/test_permissions_files.py` | Declarations, granted and denied permissions, reading without writing and writing without reading, paths outside the scope, `..`, absolute paths, symbolic links, and the error `E3008` at run time |
| `tests/test_permissions_static.py` | The error `E2026` of the static analysis and its absence when the declaration covers the path |
| `tests/test_permissions_environments.py` | That the worker and MCP always reject access to files, and that the playground cannot grant it |
| `tests/test_security.py` | That the stages of the language still do not touch the system, and that the permission module is the only one that does |

## Relation to the previous decisions and the index

- [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) does not change: the program still
  does not run if it has static errors, and a program without a capability declaration does not pass the
  analysis.
- [0005](0005-diagnosticos-y-esquemas-json.md) does not change: the new codes follow the same
  registry, with their category and their fixed text.
- [0014](0014-registros-nominales-inmutables.md) does not change: records are values, and a
  record can be saved in a file like any other text.
- [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) **is not rewritten**: its
  input part (D11) and its effect system remain a proposal. This decision describes
  another way of solving the same thing, and only decides what is implemented. 0012 is still the
  reference for the rest of its content.
- The index [`README.md`](README.md) will record 0015 when it is accepted.

## Questions that remain open

1. **Reading until the end.** `input()` fails when it reaches the end; there is no way to read all the
   lines. It will be solved with `Option` or with a function that returns the list, when they exist.
2. **The form of the declaration.** `uses read "path"` is a list of paths. When there are modules,
   the path could be relative to the module, and that has to be decided then.
3. **The visible warning of the option without a path.** None is included; if one ever is, the
   form of the warning is also still to be decided.
4. **Directories.** Today only files are read and written, not directories. Extending it changes the
   confinement model and would be another decision.
