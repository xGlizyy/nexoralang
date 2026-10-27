# CLI reference

`nex` is the command-line tool of NEXORA. This page describes version
`nexora` 0.13.0. An automated test checks that all the commands, options and exit
codes that the program accepts are documented here.

`python -m nexora` is equivalent to `nex` and accepts exactly the same arguments.

## Summary

```text
nex run <file> [--format text|json] [--allow-read PATH] [--allow-write PATH] [--allow-network ORIGIN] [--allow-process COMMAND] [-- arguments...]
nex check <file> [--format text|json] [--evidence]
nex inspect <file> [--format json]
nex context <file> [--format text|json]
nex symbols <file> [--format text|json] [--name NAME] [--function FUNCTION]
nex test <file> [--format text|json] [--function FUNCTION] [--allow-read PATH] [--allow-write PATH] [--allow-network ORIGIN] [--allow-process COMMAND]
nex migrate <file> [--write]
nex --version
nex --help
```

| Command | Analyzes | Runs the program | Writes |
|---------|----------|------------------|--------|
| `nex run` | Yes | Yes, if there are no static errors | The output of the program |
| `nex check` | Yes | **No** | The result of the analysis |
| `nex inspect` | Yes | **No** | The syntax tree as JSON |
| `nex context` | Yes | **No** | A summary of the program |
| `nex symbols` | Yes | **No** | The declared names and where they are used |
| `nex test` | Yes | Its examples, not `main` | The result of each example |
| `nex migrate` | Yes, with the front ends of 0.11 and of 0.12 | **No** | The migrated text; with `--write`, the files of the program |

All the commands use the same lexer, the same parser and the same static
checker. What `nex check` accepts is exactly what `nex run` runs.

The optional MCP server has its own command, `nex-mcp`, described in [MCP server](mcp.md).

## The `<file>` argument

- It is the path of **one** `.nex` file. A relative path is interpreted relative to the directory
  from which the command is run.
- The file has to be encoded in UTF-8.
- The path is shown in the diagnostics as it was written.
- **An argument is never interpreted as code.** There is no option to pass NEXORA code
  on the command line: the code is always read from a file.
- If the file name starts with `-`, separate it with `--`: `nex run -- -odd.nex`.

## `nex run`

Analyzes the program and, if it has no errors, runs its `main` function.

```bash
nex run examples/hello.nex
```

```text
Hello from NEXORA
```

- The output of the program (what `print` writes) goes to the **standard output**.
- The diagnostics go to the **standard error**.
- A program with lexical, syntax, semantic or type errors **does not start**: it writes
  nothing.
- If the program fails while running, what it had already written is kept.

| Option | Effect |
|--------|--------|
| `--format text` | Default. Errors are written as text for people |
| `--format json` | If the program is invalid or fails, it writes a JSON document to the **standard error**. If it ends well, it writes nothing extra. The output of the program does not change |
| `--allow-read PATH` | Allows the program to read the files of that path. It can be repeated. A program also has to declare it with `uses read` |
| `--allow-write PATH` | Allows the program to write the files of that path. It can be repeated. A program also has to declare it with `uses write` |
| `--allow-network ORIGIN` | Allows HTTPS GET requests to an exact origin, such as `https://api.example.com`. It can be repeated. The program also has to declare `uses network` |
| `--allow-process COMMAND` | Allows this executable to run. It can be repeated. The program also has to declare `uses process` |
| `-- one two` | The arguments of the program. They are written after `--` and the program reads them with `args()` |

Permissions are explicit and reproducible: files, network origins and executables are the
intersection of what the program declares (`uses`), what the command allows (`--allow-read`,
`--allow-write`, `--allow-network`, `--allow-process`) and what the environment supports. Declaring does not grant, and granting does not enable
([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)).

## `nex check`

Analyzes the program **without running it**: syntax, names, scopes, types, return paths and the
conditions of the contracts (that they are well written, not that they hold).

```bash
nex check examples/hello.nex
```

```text
✓ Check passed: examples/hello.nex
```

- If the program is correct, it writes the line above to the standard output.
- If it is not, it writes the diagnostics to the standard error and a final line with the number of
  errors.
- A correct program with warnings writes them to the standard error and a final line with the
  number of warnings to the standard output. It still exits with `0`.

| Option | Effect |
|--------|--------|
| `--format text` | Default |
| `--format json` | It **always** writes a single JSON document to the **standard output**, whether the program is valid or not. It writes nothing to the standard error |
| `--evidence` | Also reports what backs every `needs`, `promises`, `trust`, `keeps` and `shrinks` of the program. With `--format json`, the document is `nexora.evidence/1` instead of `nexora.diagnostics/1` |

### `--evidence`

The evidence of a clause has three dimensions ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md),
section 5). `nex check --evidence` runs nothing, so it only computes one of them, the
**enforcement**: whether the language evaluates the clause when the program runs.

```text
percentage.nex: 4 promises in 1 function (computed: enforcement)
  percentage
    needs whole_positive    checked
    needs part_inside       checked
    needs fits              checked
    promises in_range       checked
```

| Word | Meaning |
|------|---------|
| `checked` | A `needs`, `promises`, `keeps` or `shrinks`: when the program runs, a false condition stops it. It does not say that the condition is never false |
| `trusted` | A `trust`: the language never evaluates its condition. Only the explanation written by a person is behind it |

A clause without a name is shown by its condition. A function of a module is followed by the path of
its file, relative to the program. `example` clauses are not promises and are not listed: `nex test`
evaluates them.

The program has to pass the check: with errors, `--evidence` reports them as `nex check` does, with
the same exit code, and the JSON document has `clauses` set to `null`.

`nex check` does not detect what depends on computed values: division by zero, overflow,
endless recursion or broken contracts. That is only seen with `nex run`.

## `nex inspect`

Writes to the standard output a JSON document with the structure of the program: functions,
parameters, contracts, statements and expressions, with their positions and their types. **It does not run the
program.**

```bash
nex inspect examples/hello.nex
```

| Option | Effect |
|--------|--------|
| `--format json` | It is the default value and the only one available |

- If the program has semantic or type errors, the document includes the tree and the errors.
- If it has syntax errors, the document includes the errors, `"complete": false` and a
  **partial** tree: without the statements that have an error and without the functions whose declaration has one.
- If it has lexical errors, the document includes the errors and `"program": null`.

The format is described in [`inspect-schema.md`](inspect-schema.md).

## `nex context`

Writes a summary of the program: functions with their signatures and contracts, variables and their types, which
function calls which, which features of the language it uses and the diagnostics. **It does not run the
program** and no AI model is involved.

```bash
nex context examples/contracts.nex
```

| Option | Effect |
|--------|--------|
| `--format text` | Default. A short summary to read |
| `--format json` | A single JSON document (`nexora.context/2`) on the standard output, whether the program is valid or not |

In both formats the summary goes to the standard output and includes the diagnostics of the program. The
only exception: if the file cannot be read and the format is `text`, the error is written to the
standard error and there is no summary. With syntax errors the summary is partial and says so; with lexical errors there is no structure to summarize and the summary is
reduced to the diagnostics. Details in [Structured context](ai-context.md).

## `nex symbols`

Lists the functions, parameters and variables that the program declares, with their type, their scope, the
position of their declaration and that of each use. **It does not run the program.**

```bash
nex symbols examples/functions.nex
nex symbols examples/functions.nex --name factorial --format json
```

| Option | Effect |
|--------|--------|
| `--format text` | Default |
| `--format json` | A single JSON document (`nexora.symbols/2`) on the standard output |
| `--name NAME` | Only the symbols with that name |
| `--function FUNCTION` | Only that function and what is declared inside it |

A filter that matches nothing is not an error: the list is empty (`No symbols match.`). Details in
[Structured context](ai-context.md#nex-symbols).

## `nex test`

Analyzes the program and, if it has no errors, evaluates the `example` clauses of its functions, each
one separately ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)). **It does not require `main` and never
runs it.** During every example the contracts and refined types of all the
functions that run are checked.

```bash
nex test examples/checked_examples.nex
nex test examples/checked_examples.nex --function apply_discount --format json
```

| Option | Effect |
|--------|--------|
| `--format text` | Default. The summary goes to the standard output; the examples that do not pass, to the standard error |
| `--format json` | A single JSON document (`nexora.test/1`) on the standard output |
| `--function FUNCTION` | Only the examples declared in that function |

Every example ends as `passed`, `failed` (`E4004`) or `error` (the original diagnostic, with a note
that identifies the example). The overall result is:

| Status | When | Exit code |
|--------|------|-----------|
| `passed` | At least one example was evaluated and all passed | `0` |
| `failed` | Some example ended as `failed` or `error` | `6` |
| `no_examples` | The program is correct, but there was no selected example | `6`: nothing has been tested |
| `not_run` | The program has static errors (code `1`) or the file could not be read (code `4`) | `1` or `4` |

- With static errors nothing is evaluated, and they are reported before any problem with
  `--function`.
- **A function that does not exist in `--function` is a usage error** (code `2`): a message on the standard
  error, without a JSON document. It is different from `nex symbols --function`, which describes and returns an
  empty list; `nex test` verifies, and testing nothing because of a misspelled name cannot look like a
  result.
- **Nothing is written until all the examples have finished.** If `nex test` is interrupted (Ctrl+C,
  code `130`) or hits an internal error (code `70`), it leaves no partial report.
- What a function prints during an example is only shown if the example does not pass; in JSON it is
  always there, in the `output` field.

## `nex migrate`

Rewrites a program written for NEXORA 0.11 in the syntax of 0.12
([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md), section 8). It works on the whole
program: the file and every module it imports.

```bash
nex migrate program.nex            # shows the edits and the migrated text; writes nothing
nex migrate program.nex --write    # replaces the files, only if every check passed
```

The program is checked with the frozen front end of 0.11 and with the one of 0.12, without
requiring `main`:

| 0.11 | 0.12 | What happens | Exit code |
|------|------|--------------|-----------|
| Passes | Fails | The edits are computed; the text outside them, the structure and the check of 0.12 of the result are verified | `0` |
| Fails | Passes | The program is already migrated: nothing is edited | `0` |
| Fails | Fails | Refused: the markers of each file and the diagnostics of both front ends | `1` |
| Passes | Passes | Nothing to migrate, if both read the files the same way; refused otherwise, or if a module is named like a new keyword | `0` or `1` |

A case the tool cannot decide for the person (a clause on the line of the `{`, a name that is a
keyword in 0.12…) is refused with its file, line and column, and nothing is written (code `1`). If a
check that the edits are designed to pass does not pass, it is a defect of NEXORA: code `70`, and
nothing is written.

With `--write`, every file is read again before any is replaced; if one changed, nothing is written
(code `1`). Then each file is written, in the order of the paths, to a temporary file beside it
(whose name never ends in `.nex`) with the permission bits of the original, and put in its place
with one rename. Replacing several files is **not** one transaction: on the first failed write
(code `4`) or an interruption (Ctrl+C, code `130`), it stops, removes the temporary file of that file
and lists the files replaced, the file that failed and the files not written. The files already
replaced stay replaced. A crash or a power cut is not handled: a temporary file may be left behind.

The command says only what it checked: *structure verified; text outside the edits verified;
behaviour not checked by this command*.

## `nex --version`

```bash
nex --version
```

```text
NEXORA 0.13.0
```

## `nex --help`

`nex --help` shows the commands and the exit codes. Every command has its own help:
`nex run --help`, `nex check --help`, `nex inspect --help`, `nex context --help`,
`nex symbols --help`.

## Output formats

| Format | For whom | Where it is described |
|--------|----------|-----------------------|
| `text` | People | [Diagnostics](diagnostics.md) |
| `json` (diagnostics) | Programs. Schema `nexora.diagnostics/1` | [Specification, section 11.4](language-spec.md#114-json-format) |
| `json` (inspection) | Programs. Schema `nexora.inspect/3` | [`inspect-schema.md`](inspect-schema.md) |
| `json` (context and symbols) | Programs. Schemas `nexora.context/2` and `nexora.symbols/2` | [Structured context](ai-context.md) |
| `json` (tests) | Programs. Schema `nexora.test/1` | [Decision 0008](decisions/0008-ejemplos-y-nex-test.md), section 6 |

The rules common to all JSON documents and their JSON Schemas are in
[JSON protocol](json-protocol.md).

All the output is written in **UTF-8**, whatever the configuration of the terminal.

Where each thing appears:

| Command | Standard output | Standard error |
|---------|-----------------|----------------|
| `nex run` | What the program writes | Diagnostics (text or JSON) |
| `nex check` | `✓ Check passed: …` | Diagnostics |
| `nex check --format json` | The JSON document | Nothing |
| `nex inspect` | The JSON document | Nothing |
| `nex context`, `nex symbols` | The summary or the list (text or JSON), with the diagnostics | Nothing, except the error of an unreadable file in `text` format |
| `nex test` | The summary, or the JSON document | The examples that do not pass, the diagnostics and the usage errors |

## Exit codes

| Code | Meaning | Commands |
|------|---------|----------|
| `0` | Success | All |
| `1` | The program has lexical, syntax, semantic or type errors; `nex migrate`: refused, nothing written | `run`, `check`, `inspect`, `context`, `symbols`, `test`, `migrate` |
| `2` | Wrong use of the command line | All |
| `3` | The program failed while running (category `runtime`) | `run` |
| `4` | The file does not exist, cannot be read or is not UTF-8; for `nex migrate`, also a file of the program that could not be written | `run`, `check`, `inspect`, `context`, `symbols`, `test`, `migrate` |
| `5` | While running, the program broke a rule that it declares: a contract, a refined type, an invariant or the measure of a loop (category `contract`) | `run` |
| `6` | Some example did not pass (`failed` or `error`), or there was no example to evaluate | `test` |
| `70` | Internal error of NEXORA: a failure of the tool, not of the program. A program that runs out of memory while running gives `3` in `run` and `6` in `test`, with the diagnostic `E3007` | All |
| `130` | Interrupted with Ctrl+C | All |

The exit code is never `0` if the program did not run correctly.

If the reader of the output closes early (for example, `nex run program.nex | head -1`),
`nex` ends silently with code `0`: it is not an error of the program.

## Limits

- Every stage of the analysis reports at most 100 errors per file. If the limit is reached,
  the final line says so.
- At most 1000 nested calls while running.
- At most 64 levels of nesting of parentheses, blocks or unary operators, and 256 levels
  in an expression.

## Environment variables

| Variable | Effect |
|----------|--------|
| `NEXORA_DEBUG` | If it is set to any non-empty value, an internal error shows the full Python traceback instead of the summarized message. It is useful to investigate failures of the interpreter itself |

## Internal errors

An internal error (code `70`) means that NEXORA has failed, not your program. It is shown like this:

```text
internal error: NEXORA hit an unexpected problem (...).
This is a bug in NEXORA, not in your program. Run the command again with the environment variable NEXORA_DEBUG=1 to see the details.
```

If you see one, it is a defect worth reporting: see [how to contribute](../CONTRIBUTING.md).
