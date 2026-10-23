# 0009 — A program that runs out of memory while running: diagnostic `E3007`

- **Status:** accepted
- **Version:** 0.4.0
- **Related to:** [decision 0008](0008-ejemplos-y-nex-test.md), in what it says about
  `MemoryError`: the `MemoryError` row of section 3.4, the `70` row of section 4.2 and the
  "Pending question" 1. **It does not modify 0008**; the notes that refer here are a separate
  documentation change (see "Separate documentation tasks").

## Context

When a program runs out of memory while it runs, each interface responds in a different way
(checked by simulating the `MemoryError` inside the interpreter):

| Interface | Today | Where |
|-----------|-------|-------|
| `nex run` | Code `70`: `internal error: NEXORA hit an unexpected problem (MemoryError: ). This is a bug in NEXORA, not in your program.` | The general handler of `cli.py:409-426` |
| `nex test` | Code `70`, without a report. It is the inherited exception that 0008 left written | 0008, 3.4; `run_example` lets it through (`interpreter.py:472-484`) |
| `api.run_source` | Status `memory_limit`, with what was written until then, a `message` and empty `diagnostics` | `api.py:135-139` |
| `api.test_source` | The exception reaches the caller | 0008, section 7 |

### The contract that exists, and what is kept

- **`70`**: "internal error of NEXORA: a failure of the tool, not of the program"
  (`cli-reference.md:247` and `271-276`, `language-spec.md:1026`, `diagnostics.md:252`), with memory
  as the only written exception. **It is kept** for the defects of NEXORA.
- **`memory_limit`**: public status of `nexora.result/1` (`api.py:52`, the schema,
  `playground.md:138`), on which the server and the playground depend. **It is kept**: status,
  `message` and partial output.
- **`nexora.test/1`**: an example that cannot finish stays as `error` with its diagnostic. **It is
  kept**; no new status is needed.

### What fails

1. The message of `nex run` and `nex test` blames NEXORA for something the program did.
2. `70` stops meaning a single thing for whoever automates.
3. `nex run --format json` writes no document.
4. `nex test` loses the whole report because of one example, while the equivalent case of the stack
   (`E3004`) leaves that example as `error` and continues.
5. The branch `api.py:135-136` does not run in the tests on Windows.

## Decision

### 1. Scope: only the execution of the program

`E3007` is produced **only** when the `MemoryError` appears while the interpreter runs the
program, that is, inside `Interpreter._guarded` (`interpreter.py:115-135`): during
`Interpreter.run` (`main` and everything it calls) or `Interpreter.evaluate_example` (the expression of an
example and everything it calls). That includes:

- the statements and expressions of the program, its calls, contracts and `Type(x)` checks;
- the built-in functions (`print`, `to_text`, `to_float`, `to_int`);
- the `write` function that the host passes to the interpreter and that `print` calls inside `_guarded`: a
  program that prints more than fits in memory runs out of memory because of its own output.

**They are not turned into `E3007`**, and their handling does not change:

| Where memory runs out | Handling (same as today) |
|-----------------------|--------------------------|
| When reading the file or analyzing (lexer, parser, checker, including the check of refined types on constants) | CLI: internal error, `70`. API: the exception reaches the caller. Worker: `memory_limit` without a diagnostic |
| When building or serializing the report, the JSON document or the diagnostic, after the execution | CLI: `70`. `run_source`: its current `except MemoryError` → `memory_limit` without a diagnostic. `test_source`: the exception reaches the caller |
| In the worker process itself, outside `run_source` | No changes (`worker.py:118-125`) |
| `nex check`, `nex inspect`, `nex context`, `nex symbols` and the MCP tool | They do not run programs: it does not affect them |

### 2. The diagnostic

| Field | Value |
|-------|-------|
| Code | `E3007` |
| Title | `Out of memory` |
| Category | `runtime` |
| Label | `The program needed more memory than is available.` |
| Suggestion | `Reduce the size of values created by the program, especially values that grow with each function call.` |
| Position | None, like the `E3004` for lack of stack |
| Notes | The chain of calls; in `nex test`, also the note of the example (0008, 3.1) |

### 3. The conversion and the state that is restored

`_guarded` catches `MemoryError` together with `RecursionError`, with these requirements:

1. **It is converted outside the `except` block.** The `except MemoryError` only records what happened; the
   `E3007` is raised afterwards, when the `MemoryError` and its traceback are no longer referenced. If it
   were raised inside, the `E3007` would keep the `MemoryError` in `__context__` (even if
   `from None` is used), and with it all the frames of the program and their values while the CLI or the API handle
   the error. Measured with a model of the frames: inside the `except`, 4 out of 4 values are still alive
   while the error exists; outside, 0 out of 4.
2. **The Python recursion limit is restored**, the only global state the
   interpreter touches. The `finally` of `_guarded` already does it, and that does not change.
3. **The rest of the state is local to the interpreter and is discarded with it**: `_stack` (the chain of
   calls), `_invoked` and `_short_circuited` (the observed calls of an example) and the variable
   environments. The interpreter only reads the analyzed program (`CheckedProgram`) that the
   examples share; it does not write to it.
4. **Nothing else survives the example**: `run_example` returns an `ExampleRun` with the diagnostic (text
   only), the observed own calls and the collected output, without any reference to the interpreter
   or to the exception.
5. **Emergency exception: if the conversion itself runs out of memory.** Creating the diagnostic
   needs a bit of memory. If at that moment there is none either, that second `MemoryError` leaves
   `_guarded` unconverted, because it cannot be guaranteed that there is memory to build either the
   diagnostic or the report. It gets today's handling: `70` in the CLI, `memory_limit` without a
   diagnostic in `run_source` (its current `except MemoryError`) and the exception to the caller in
   `test_source`. It is an emergency exit in the face of a failure inside another failure, **not a general change
   of the contract**: in every `MemoryError` of the program that leaves memory to convert it, the
   behaviour is that of section 4. It is never turned into a false status.

**When continuing with the next example is considered safe.**

This decision does not take for granted that a `MemoryError` leaves the process intact. Continuing
relies on the current architecture: every example uses a new interpreter (0008, 3.3), the only
global state the interpreter touches is the Python recursion limit, and requirement 1 makes the
values of the program that failed stop being referenced.

It is only considered safe if tests 6 to 9 verify these four properties:

| Test | Property |
|------|----------|
| 6 | The `E3007` has empty `__context__` and `__cause__`: it does not keep the `MemoryError` or its traceback |
| 7 | The interpreter that failed is freed: a weak reference to it is empty after `gc.collect()` |
| 8 | The Python recursion limit is the same before and after the example |
| 9 | The next example is evaluated independently, without inherited state: with its own output, without the chain of calls of the previous one and with the analyzed program unchanged |

**Condition for implementing.** These properties have been checked with a model, not with the
interpreter. Tests 6 to 9 are the first ones written. If any fails or cannot be met
(for example, if the interpreter that failed is not freed), the implementation stops and it is reported
before continuing. Without those four tests green, `nex test` and `test_source` do not continue with the
next example after an `E3007`.

### 4. The observable contract, before and after

Only what is within scope changes (section 1).

| Interface | Before | After |
|-----------|--------|-------|
| `nex run`: exit code | `70` | **`3`** |
| `nex run`: standard output | What the program printed before the failure | **The same** |
| `nex run`: standard error | `internal error: … This is a bug in NEXORA, not in your program.` | `runtime error[E3007]: Out of memory`, with the chain of calls, and `error: <file>: the program stopped because of a runtime error` |
| `nex run --format json` | No document; internal error text on the standard error | `nexora.diagnostics/1` document with the `E3007` on the standard error, like any runtime error |
| `nex test`: exit code | `70` | **`6`** (`failed`) |
| `nex test`: report | None | Complete: the example as `error` and the others evaluated |
| `nex test --format json` | No document | Valid `nexora.test/1`: the example with `status: "error"`, `diagnostic` = `E3007` with the note of the example, `values` with the own call in progress as `stopped` and `output` with what was printed until the failure. `summary.error` counts it |
| `api.run_source`: `status` | `memory_limit` | **`memory_limit`** |
| `api.run_source`: `output` | What was written until the failure | **The same** |
| `api.run_source`: `message` | `The program needed more memory than this environment allows and was stopped.` | **The same** |
| `api.run_source`: `diagnostics` | `[]` | `[E3007]` |
| `api.test_source` | Raises `MemoryError` | Returns the `nexora.test/1` document described above |
| Worker (`action: run`) | `memory_limit`, empty `diagnostics` | `memory_limit` with the `E3007` (it is the answer of `run_source`) |
| Server and playground | They receive `memory_limit` | The same; they can ignore the new diagnostic |

`run_source` chooses the status by the code: `E3007` → `memory_limit`; the rest of the category
`runtime` → `runtime_error`; `contract` → `contract_violation`. Its `except MemoryError` is kept
for memory that runs out outside the interpreter.

### 5. The change in `api.test_source`

- **During the evaluation of an example** (within scope): it stops raising `MemoryError`. The
  example stays as `error` with `E3007`, the following ones are evaluated and the document is returned, with
  overall `status` `failed`.
- **Outside the evaluation** (when analyzing or when building the document): it does not change; the exception reaches
  the caller, as 0008, section 7, says.
- **Emergency exception** (section 3, requirement 5): if the conversion itself runs out of memory, the
  second `MemoryError` also reaches the caller, because the construction of the
  document cannot be guaranteed. It does not change the general contract of `test_source`.
- No `limits` are added to `test_source` (0008, section 7).

### 6. Code `70`

It comes to mean "defect of NEXORA" without the inherited exception: a `MemoryError` within
scope no longer reaches the general handler. The `MemoryError`s outside the scope (section 1) still
reach it and give `70`, as today.

## Reasons

- **It is a failure of the program.** It behaves like the other resource exhaustions that are already
  `runtime` diagnostics: `E3004` (the stack) and `E3006` (a text longer than the limit).
- **Coherence without breaking anything.** The CLI and `nex test` come to treat it as the API treats it, and the API
  keeps everything it promises: it only gains the diagnostic it was missing.
- **A single place.** The interpreter, where the case of the stack already is; the interfaces receive it through the
  path they already use for runtime errors.
- **`70` becomes reliable again** in the case that confused it the most.

## What it does not guarantee

- **That the system warns.** On Linux, with memory overcommit, the system can kill the
  process (SIGKILL) without Python getting to raise a `MemoryError`; then there is no `E3007` and no message
  at all. Without a limit like the `RLIMIT_AS` of the worker, NEXORA cannot prevent it.
- **Telling the cause apart within the execution.** A defect of NEXORA that ran out of memory while
  running a program would be reported as `E3007`: the two causes are indistinguishable from inside. The
  chain of calls helps to investigate it.
- **That the report is small.** The own calls that returned a value before the failure
  keep that value in `values`, as today. A huge value can make the report huge, or run out of
  memory when building it; in that case section 1 applies (out of scope).
- **A memory limit in `nex run`.** None is added.

## Out of scope

This decision does not change these behaviours:

- **The defect of the worker protocol:** with a `MemoryError` outside `run_source`, it answers
  `"action": "run"` even if the request was `check` (`worker.py:121`).
- **Memory running out when analyzing**, which still gives `70` in the CLI.
- **The conversion of `RecursionError`**, which today is done inside the `except` with `from None`.
- **A size limit for the values of `values`** in the report of `nex test`.

## Alternatives ruled out

- **Fixing only the message and keeping `70`.** It keeps a code with two meanings, without JSON and
  without a report in `nex test`.
- **A new exit code, without a diagnostic.** More surface and less information (no chain of
  calls or suggestion), and it does not solve `nex test`.
- **Having the API do what the CLI does.** It breaks `memory_limit`, a public contract of the playground.
- **A new status in `nexora.test/1`.** `error` with its diagnostic already describes it.
- **Turning any `MemoryError` of the process into `E3007`.** It would attribute to the program memory exhausted
  by the analysis or by the reports of NEXORA.

## Compatibility

- **Visible change:** in a program that runs out of memory while running, the exit code goes from
  `70` to `3` (`nex run`) or to `6` (`nex test`), with a different text on the standard error. It is an
  incompatible change and it is announced as such in 0.4.0 ("Resolved questions", 1).
- **`nexora.diagnostics/1`:** it gains a code. No version change (JSON protocol).
- **`nexora.result/1`:** `memory_limit` the same; `diagnostics` can have one element in that status.
  Added, without a version change.
- **`nexora.test/1`:** no format change.
- **Server and playground:** no changes needed.

## Required changes if it is approved

| File | Change |
|------|--------|
| `nexora/src/nexora/diagnostics.py` | `"E3007": ("Out of memory", RUNTIME)` |
| `nexora/src/nexora/interpreter.py` | `_guarded`: an `except MemoryError` that only records, and `E3007` raised outside the `except` (section 3); docstring of `run_example` |
| `nexora/src/nexora/api.py` | `run_source`: `E3007` → `memory_limit` with the diagnostic; `except MemoryError` is kept. Docstrings of `run_examples` and `test_source` |
| `nexora/src/nexora/cli.py` | Comment of `EXIT_INTERNAL_ERROR` and epilogue of `--help` |
| `nexora/docs/language-spec.md`, `diagnostics.md`, `cli-reference.md`, `playground.md` | `E3007`; `70` without the exception; `memory_limit` with its diagnostic |
| `nexora/docs/schemas/*` | Regenerate (the enums of categories do not change) |

This table does not include decision 0008, the CHANGELOG or the version number: they are not part of the
implementation. Nor does it include adding this decision to the repository: 0009 and its
entry in `nexora/docs/decisions/README.md` were added together, with the notes of 0008, in a
previous documentation change separate from the implementation.

## Separate documentation tasks

They are not part of the implementation. Each one has its own authorization:

| Task | Status | Content |
|------|--------|---------|
| Reference notes in 0008 | Done, in the same documentation change that adds 0009, before the implementation | "This behaviour changes with decision 0009" in the `MemoryError` row of section 3.4 and in the `70` row of 4.2, and "Resolved in decision 0009" in the "Pending question" 1, with the link to 0009. No other text of 0008 changes |
| CHANGELOG | Done, in the 0.4.0 entry ("Resolved questions", 1) | The change in "Changed" and in "Incompatible changes" (`70` → `3` and `70` → `6`) |

## Regression tests

All of them cause the `MemoryError` by replacing an internal function (like `tests/test_nex_test.py:205-213`),
without exhausting real memory or depending on the machine. Tests 6 to 9 are written first (section 3,
"Condition for implementing").

**Scope**

1. A `MemoryError` during a call of the program gives `NexoraRuntimeError` with `E3007`, without a
   position, with the chain of calls and with the label and the suggestion of section 2.
2. A `MemoryError` inside `print`, in the `write` function of the host, also gives `E3007`.
3. A `MemoryError` when analyzing (replacing `pipeline.analyze`) does **not** give `E3007`: `nex run` and
   `nex test` give `70`, and `test_source` raises.
4. A `MemoryError` when building the report (replacing `api.test_document`) does **not** give `E3007`:
   `nex test` gives `70` and writes nothing to the standard output.
5. If the conversion itself raises `MemoryError` again, it leaves `_guarded` unconverted:
   `run_source` answers `memory_limit` without a diagnostic, `nex run` gives `70` and `test_source` raises.

**State and continuation**

6. The `E3007` has empty `__context__` and `__cause__`.
7. After `run_example` with `E3007`, the interpreter that failed is freed: a weak reference to it is
   empty after `gc.collect()`.
8. The Python recursion limit is the same before and after.
9. With two examples, the first one with `E3007` and the second one correct: the second one passes, with its own
   output, without an inherited chain of calls, and the analyzed program has not changed.

**Contract of each interface**

10. `nex run`: code `3`, `runtime error[E3007]`, keeps what was printed before and does not contain
    `internal error`.
11. `nex run --format json`: valid `nexora.diagnostics/1` document with `E3007`.
12. `nex test`: code `6` and complete report, as text and as JSON (valid according to
    `nexora-test.schema.json`), with the example as `error`, its note, `values` and `output`.
13. `api.run_source`: `memory_limit`, the usual `message`, the partial output and `diagnostics` =
    `[E3007]`. It covers `api.py:135-136` on all platforms.
14. `api.test_source`: returns the document; it does not raise.
15. Worker (POSIX only): the current test of `RLIMIT_AS` (`test_worker.py:108`) still gives
    `memory_limit` and also checks the `E3007`.

**A `MemoryError` of the program versus a real internal error**

16. With the same injection point as test 1, a `KeyError` is still an internal error:
    `nex run` and `nex test` give `70` with the message `This is a bug in NEXORA`, `nex test` writes no
    report, and `run_source` and `test_source` raise `KeyError`.
17. The current tests of internal errors (`test_cli.py`, `test_nex_test.py`) still pass without
    changes.

**Documentation**

18. The tests that require every registered code to be documented (`test_docs.py`,
    `test_diagnostics.py`) include `E3007`.

Two tests that today pin the behaviour this decision changes are replaced:
`test_memory_error_is_not_caught_by_the_engine` and `test_cli_memory_error_keeps_the_inherited_code_70`,
both in `test_nex_test.py`.

## Resolved questions

1. **The release version: 0.4.0.** `nex test` appears in 0.4.0, so no published
   version has returned `70` in that case: the `70` → `6` change breaks nothing. The only incompatible
   change is that of `nex run` (`70` → `3`), which already behaved that way in 0.3.1. Publishing it in 0.4.0
   avoids pinning in a version a behaviour that was already known to be going to change.
