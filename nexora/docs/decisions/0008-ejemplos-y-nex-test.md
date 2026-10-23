# 0008 — Examples in functions (`example`) and the `nex test` command

- **Status:** accepted
- **Version:** 0.4.0

## Context

[Decision 0006](0006-requisitos-verificables.md) makes verifiable requirements the main
feature of NEXORA. 0.3 covers two kinds of requirement: what a value accepts
(refined types) and the relation between the input and the output of a function (contracts). The
third one is missing: **what concrete result a function must give for some concrete inputs**.

Contracts, moreover, are only checked in the calls that are executed: a function that no
`main` calls is never checked. And today, to know whether an edit broke something, you have to write
a `main` that exercises the code and read what it prints.

This is step 3 of the main line of the [roadmap](../roadmap.md#main-line-verifiable-requirements).

Terms used by this decision:

- **Example:** an `example` clause of a function.
- **Function of the example:** the function in whose body the clause is written.
- **Own call:** a call node, inside the expression of the example, to the function of the
  example (section 1.4).
- **Evaluating an example:** computing its expression by running the functions it calls. Only
  `nex test` does it.

## Decision

### 1. The `example` clause

```text
fn apply_discount(price: Cents, percent: Percent) -> Cents {
    requires percent < 100, "A full discount would make it free"
    ensures result <= price, "A discount never raises the price"

    example apply_discount(10000, 20) == 8000, "Twenty percent off"
    example apply_discount(999, 0) == 999

    return Cents(price * (100 - percent) / 100)
}
```

#### 1.1 Position

`example` is a clause at the start of the body, like `requires` and `ensures`: it goes before the
first statement, and the three can be mixed in any order. A function can have any number of
examples. An `example` clause after a statement is the existing error
`E1106` (*Misplaced contract clause*), whose message already names the concrete word:
`'example' must come at the start of a function body, before any other statement`.

#### 1.2 Form and grammar

```ebnf
contract = ( "requires" | "ensures" | "example" ) expression [ explanation ] end ;
```

The explanation follows exactly the rules of 0.3.1 for `requires`, `ensures` and `where`: a
single literal text, not empty, on a single line. Otherwise it is `E1101`.

`example` goes from reserved word to keyword.

#### 1.3 Type and visible names

- The expression is of type `Bool`. If it is not, static analysis gives `E2011` with the message
  `The condition of 'example' must be Bool, found Int`, the same format as `requires` and `ensures`.
- An example does not happen inside a call: **it does not see the parameters of its function nor `result`**.
  Using any of them is `E2005` (*Unknown variable*), with the suggestion
  `An example has no parameters: write its inputs as values, for example: double(2)`.
- It can use literals, operators, the built-in functions, **any function of the program** and
  refined type checks (`Percent(x)`).
- Constant arguments are checked against refined types without running, like any
  constant (`E2017`), and they count towards the work limit of the analysis (`E2019`).
- Consequence: a `Void` function cannot have valid examples, because a call to it does not
  produce any value that can be part of a `Bool` expression (`E2011`).

#### 1.4 The own call

An **own call** is a `Call` node that is in the syntax tree of the expression of the example
(in any position: as an operand, as an argument of another call, inside parentheses) and whose
name is that of the function of the example.

- NEXORA has no overloading: two functions cannot have the same name (`E2002`), and the name of a
  function cannot be that of a type (`E2006`). That is why the name identifies the function without any
  additional resolution rule.
- **One** is enough. There can be several, and they can be nested.
- A call that happens when running another function **does not count**: the text of the example is looked at, not its
  execution, because the analysis does not run anything (section 2).
- An own call with errors (number of arguments, types) counts as an own call: its error
  is its own (`E2009`, `E2011`), not `E2020`.

| Expression in an example of `f` | Does it have an own call? |
|--------------------------------|------------------------|
| `f(2) == 4` | Yes |
| `f(f(2)) == 16` | Yes, two |
| `f(1) + f(2) == 6` | Yes, two |
| `to_float(f(2)) > 3.5` | Yes |
| `g(f(2)) == 1` | Yes: `f(2)` is in the tree of the example |
| `g(2) == 4`, even if `g` calls `f` | No |
| `2 + 2 == 4` | No |

Without any own call: **`E2020`** (*Example without its function*, category `semantic`).
It points at the whole expression of the example; message `This example of 'f' never calls 'f'`; suggestion
`Write the call with its inputs, for example: example f(2) == 4`. If the expression, in addition, is not
`Bool`, both errors are reported: they are two different problems.

### 2. Analysing is not running

| Tool | What it does with the examples |
|-------------|---------------------------|
| `nex check`, `nex inspect`, `nex context`, `nex symbols` and the MCP server | They apply the rules of section 1. **They do not evaluate any example nor call any function** |
| `nex run` | Nothing. It runs `main` as always |
| `nex test` and `nexora.api.test_source` | They evaluate them |

0.3.1 put in writing that the analysis does not run the program; the only thing it evaluates is the
conditions of refined types over constants, which do not call functions of the program. This
decision does not change that boundary.

**Call graph.** The calls in an example **are not edges** of the call graph of
its function. An example of `f` that calls `f` does not make `f` recursive, and an example of `f` that calls
`g` does not make `f` "call" `g`. In `nex context`, `calls`, `called_by` and `recursive` do not change.
They are **references** to the called function in `nex symbols`: the name is used there.

### 3. Evaluation of the examples

#### 3.1 States

| State | Definition | Diagnostic |
|--------|------------|-------------|
| `passed` | The evaluation ends without a runtime error or a broken rule, and the expression is `true` | None |
| `failed` | The evaluation ends without a runtime error or a broken rule, and the expression is `false` | `E4004` |
| `error` | The evaluation stops because of a runtime error (`E3001`–`E3006`) or a broken rule (`E4001`–`E4003`) | The original one, with its code, plus a note |

They are mutually exclusive, and an `error` **never** turns into `failed`.

**`E4004`** (*Example failed*, new category **`test`**): it points at the expression of the example, with the
message `This example of 'f' is false`. The notes are, in this order: one for each own call that
returned a value (`f(2) returned 5`), in the order in which they were invoked (section 6.3), and, if it exists,
the explanation (`Reason: ...`).

**Note of an `error`:** the original diagnostic gets, as its last note,
`While evaluating example 2 of 'f', at line 14.` The rest of the diagnostic (code, position,
message, call chain) does not change.

#### 3.2 What is checked

Exactly the same as in `nex run`, at any depth: the `requires` and `ensures` of every
function called during the example (the one of the example and the others, even if `--function` does not
select them), the `Type(x)` checks, division by zero, overflows, the limit of
1000 nested calls. A `requires` violation in a nested call (the example of `f` calls
`g`, and `g` breaks the `requires` of `h`) is an `error` with the `E4001` that points at the call to `h` and
the usual call chain.

#### 3.3 Real isolation

Each example is evaluated with **a new interpreter**, in the order of the file (functions in the order
in which they are declared; within each one, examples in the order in which they are written). What that
guarantees, with the current architecture:

- **Own stack and variables.** The interpreter keeps the chain of calls in progress and does not empty it
  after an error; a new one per example prevents a failure from contaminating it. Variables live in
  environments created on every call.
- **Nothing else to share.** A NEXORA program has no global variables, cannot read nor
  write files, network or input, and its only effect is `print`, which is collected separately for
  each example. That is why an example cannot influence another.

What it does **not** guarantee: all the examples are evaluated in the same process, one after another. There is no
time or memory limit per example, nor any operating system isolation. A very
long computation delays the following ones; an endless recursion stops at the call limit
(`E3004`) and ends up in `error`.

#### 3.4 Continuing or stopping

After a `failed` or an `error` the next example is evaluated. What happens when evaluating an example is
classified like this. **The general rule is that code `70` corresponds to a failure of NEXORA, with a
single inherited exception, `MemoryError`**, described in the table and in the section "Open
questions":

| What happens | Origin | Result |
|---------------|--------|-----------|
| A runtime or rule diagnostic (`NexoraRuntimeError`: `E3001`–`E3006`, `E4001`–`E4003`) | The program | Example in `error`; it continues with the next one |
| The program exhausts the Python stack before the limit of 1000 calls (recursion inside very nested expressions) | The program | It becomes `E3004`, exactly as `Interpreter.run` does today with `RecursionError`. Example in `error`; it continues |
| `MemoryError` | The program | **Exception to the general rule.** `nex test` inherits the current behaviour of `nex run`, which does not catch `MemoryError` and lets it reach the internal error handler: it stops, without a report, with `70`. It is not a failure of NEXORA, but in 0.4.0 it is reported as one. See "Open questions". This behaviour changes with [decision 0009](0009-memoria-agotada.md) |
| Ctrl+C (`KeyboardInterrupt`) | Whoever uses the command | It stops, without a report, with `130`, like the other commands |
| Any other Python exception | **NEXORA** (a defect) | It stops, without a report, with `70` and the same internal error message as the other commands |

The report is only written when **all** the examples have finished. That is why, when `nex test`
stops, no partial report is left that could be taken as complete, neither in text nor in JSON.

### 4. The `nex test` command

```text
nex test <archivo> [--format text|json] [--function FUNCION]
```

1. **Static analysis.** The same as `nex check`, with a single difference: it does not require `main`
   (`E2001`). If there is a `main`, its rules are checked the same (`E2004`, `E2013`), but **it is not
   run**.
2. **With static errors nothing is evaluated:** state `not_run`, code `1`.
3. **Without errors**, the selected examples are evaluated: all of them, or those of the function of
   `--function`.
4. **`--function NAME`** selects the examples **declared in** that function. The functions that
   those examples call are run and checked as always (section 3.2).
   - Static errors are reported first: with errors it is not known for sure which functions
     exist.
   - If the function does not exist, it is a usage error: `error: <archivo> has no function named 'NOMBRE'`
     on the error output (with `Did you mean 'X'?` if there is a similar name), code `2`, without
     evaluating anything and without a document, not even with `--format json`, like any other usage
     error.
   - If the function exists and has no examples: state `no_examples`.
   - Deliberate difference with `nex symbols --function`, which with a non-existent name returns an
     empty list: `nex symbols` **describes**, and "there are no symbols with that name" is a correct
     answer; `nex test` **verifies**, and "nothing was tested because the name was wrong" cannot
     look like a result.
5. **Output:** nothing is written to the standard output until all the examples have finished
   (section 3.4). In text, the summary goes to the standard output and the diagnostics to the error output,
   as in `nex run`. In JSON, a single document on the standard output.
6. There are no more filters, nor parallel execution, nor a "Test" button in the playground in 0.4.0.

#### 4.1 Global state

| State | Definition | Exit code |
|--------|------------|------------------|
| `passed` | **At least one** example was evaluated and **all** ended in `passed` | `0` |
| `failed` | At least one example was evaluated and **some** ended in `failed` or `error` | `6` |
| `no_examples` | The analysis has no errors, but there was no selected example | `6` |
| `not_run` | Nothing was evaluated because the static analysis found errors, or because the file could not be read | `1`, or `4` if the file could not be read |

`no_examples` **is not a success**: a `0` means "tested and correct", and there nothing has been
tested.

#### 4.2 Exit codes

Checked against `nexora/src/nexora/cli.py` (0, 1, 2, 3, 4, 5, 70 and 130 exist; 6 is free).
All are kept and one is added:

| Code | In `nex test` |
|--------|---------------|
| `0` | State `passed` |
| `1` | State `not_run` because of static errors |
| `2` | Incorrect usage, including a non-existent function in `--function` |
| `4` | State `not_run` because the file could not be read, with the `E0001`/`E0002` in `diagnostics` (the same convention as `nex inspect`, `nex context` and `nex symbols`) |
| **`6`** | **New.** State `failed` or `no_examples`: the test was not passed |
| `70` | Internal error of NEXORA, or the program ran out of memory (`MemoryError`, exception inherited from `nex run`; section 3.4); without a report. This behaviour changes with [decision 0009](0009-memoria-agotada.md) |
| `130` | Interrupted with Ctrl+C; without a report |

`nex test` **does not return `3` nor `5`**: a runtime error or a broken rule during an example
is an example in `error`, with its original diagnostic, and the global code is `6`. `nex run` still
returns `3` and `5` as before.

### 5. Text format

```text
prices.nex: 5 examples in 3 functions
  apply_discount   2 passed
  as_percent       1 passed, 1 failed
  total            1 error

test error[E4004]: Example failed
  --> prices.nex:14:13
   |
14 |     example as_percent(1, 3) == 34, "Thirds round up"
   |             ^^^^^^^^^^^^^^^^^^^^^^ This example of 'as_percent' is false
   = note: as_percent(1, 3) returned 33
   = note: Reason: Thirds round up

runtime error[E3001]: Division by zero
  ...
   = note: While evaluating example 1 of 'total', at line 22.

error: prices.nex: 2 of 5 examples did not pass (1 failed, 1 error)
```

- Without examples: `prices.nex: no examples to run`, and on the error output
  `error: prices.nex: nothing was tested`.
- With `--function`: the summary says `examples of 'as_percent'`.
- The values of the own calls are shown in the notes of `E4004`. What an
  example printed is shown only if it did not pass.
- What does not change is **what** is reported; the exact wording is fixed when implementing and is covered
  by the tests.

### 6. JSON format: `nexora.test/1`

#### 6.1 Document

It follows the conventions of [JSON protocol](../json-protocol.md): the common header, objects that
can gain fields without changing version, fields that always appear (an absent value is `null`,
the field is never omitted), deterministic output and a JSON Schema generated from the code
(`docs/schemas/nexora-test.schema.json`).

| Field | Type | Meaning |
|-------|------|-------------|
| `schema` | `"nexora.test/1"` | |
| `nexora_version` | text | |
| `file` | text | As in the other formats |
| `ok` | boolean | As in the other formats: **the static analysis found no errors**. It says nothing about the examples |
| `diagnostics` | list | The **static** diagnostics (or the one of an unreadable file). Empty if `ok` |
| `status` | text | Global state (section 4.1): `passed`, `failed`, `no_examples` or `not_run` |
| `filter` | object | `{"function": text or null}`, like the `filter` of `nexora.symbols/1` |
| `summary` | object or `null` | `{"total", "passed", "failed", "error"}`, counting the selected examples. `null` if `not_run` |
| `examples` | list or `null` | One result per selected example, in the order of evaluation. `[]` if `no_examples`; `null` if `not_run` |

**`ok` versus `status`:** `ok: true` means that the program passes the static analysis;
`status: "passed"` means that, in addition, at least one example was evaluated and all of them passed. A document
with `ok: true` can have `status` `failed` or `no_examples`. `status: "passed"` implies `ok: true`.

#### 6.2 Result of an example

| Field | Type | Meaning |
|-------|------|-------------|
| `function` | text | The function of the example |
| `index` | integer ≥ 1 | Its position among the examples of that function, in the order of the text. Together with `function`, it identifies the example stably as long as the examples of that function are not reordered |
| `span` | position | The expression of the example (without the word `example` nor the explanation) |
| `expression` | text | The expression as written |
| `message` | text or `null` | The explanation |
| `status` | text | `passed`, `failed` or `error` |
| `values` | list | The own calls that were invoked, in the order in which they were invoked (section 6.3) |
| `not_evaluated` | list | The own calls that were never invoked, in the order of the text (section 6.3) |
| `diagnostic` | object or `null` | `null` if `passed`; the `E4004` if `failed`; the original diagnostic, with the note of the example, if `error`. Same format as in `nexora.diagnostics/1` |
| `output` | text | What was printed during the example; `""` if nothing |

#### 6.3 Own calls: `values` and `not_evaluated`

Each own call of the expression (section 1.4) appears **exactly once**, in one of the two
lists. An expression has no loops, so each call node is invoked at most once.
The calls to the function that happen inside the body of other functions, or inside the function itself
when it recurses, are not own calls and do not appear.

**Invoking** a call is entering the function, after having evaluated all its arguments and
before checking its `requires`. It is the moment that fixes the order.

**`values`: the calls that were invoked, in the real order of invocation.** The interpreter evaluates the
arguments of a call before invoking it, and the operands from left to right. That is why:

| Expression | Order in `values` |
|-----------|-------------------|
| `f(f(2)) == 16` | `f(2)`, then `f(f(2))`: the inner one is invoked and finishes before the outer one starts |
| `f(1) + f(2) == 6` | `f(1)`, then `f(2)` |
| `g(f(2)) == 1` | `f(2)` (the call to `g` is not an own call) |

| Field | Type | Meaning |
|-------|------|-------------|
| `call` | text | The call as written |
| `span` | position | Its position |
| `type` | text | Its type according to the static analysis: the return type of the function |
| `status` | text | `returned`: it returned a value. `stopped`: it was invoked, but returned nothing because the evaluation stopped inside it (its `requires`, its body, a function it called or its `ensures`) |
| `value` | text or `null` | If `returned`, the value written as in the code (`"33"`, `"2.5"`, `"true"`, `"\"text\""`). If `stopped`, `null` |

Since an evaluation stops at the first error, **at most one** entry of `values` is
`stopped`, and it is the last one of the list. The example, in that case, is in `error`.

**`not_evaluated`: the calls that were never invoked**, that is, that were not run
at all, **in the order of the text** (by the column where they start). A call that was
invoked is never here, even if it returned nothing: that one is in `values` as `stopped`.

| Field | Type | Meaning |
|-------|------|-------------|
| `call` | text | The call as written |
| `span` | position | Its position |
| `type` | text | Its type according to the static analysis |
| `reason` | text | `short_circuit`: it is in an operand that an `and` or an `or` did not need to evaluate. `stopped_before`: the evaluation stopped because of an error before getting to invoke it (in another call, in one of its arguments or in a previous operand) |

The reason is determined mechanically: when evaluating, each operand that `and` or `or` skip marks
as `short_circuit` the own calls it contains; at the end, the calls that were neither invoked
nor marked are `stopped_before`, which can only happen in an example in `error`.

**Three different cases, without ambiguity:**

| Situation | Where it appears |
|-----------|---------------|
| It was invoked and returned a value | `values`, `status: "returned"`, `value` with the value |
| It was invoked and returned nothing | `values`, `status: "stopped"`, `value: null` |
| It was not invoked | `not_evaluated`, with `reason` |

NEXORA has no null value: its values are `Int`, `Float`, `Bool` and `Text`, and a call to a
`Void` function cannot be part of an example (section 1.3). That is why a value of the language is never
written as `null`, and `value: null` only appears in a `stopped` call. The two lists can
be empty separately, but not at the same time: every example has at least one own call.

#### 6.4 Example documents

Five complete documents, valid according to the schema. Each one corresponds to a version of the file
`double.nex`; the line numbers are part of the example.

**1. All passed** — code `0`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(double(1)) == 4
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "passed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 2, "failed": 0, "error": 0},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 35},
      "expression": "double(double(1)) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(1)", "span": {"line": 4, "column": 20, "end_line": 4, "end_column": 29},
         "type": "Int", "status": "returned", "value": "2"},
        {"call": "double(double(1))", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 30},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    }
  ]
}
```

**2. A `failed` example** — code `6`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(3) == 7, "Three doubled is seven"
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "failed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 1, "failed": 1, "error": 0},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 27},
      "expression": "double(3) == 7",
      "message": "Three doubled is seven",
      "status": "failed",
      "values": [
        {"call": "double(3)", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 22},
         "type": "Int", "status": "returned", "value": "6"}
      ],
      "not_evaluated": [],
      "diagnostic": {
        "severity": "error", "category": "test", "code": "E4004", "message": "Example failed",
        "label": "This example of 'double' is false", "hint": null,
        "notes": ["double(3) returned 6", "Reason: Three doubled is seven"],
        "file": "double.nex", "line": 4, "column": 13, "end_line": 4, "end_column": 27
      },
      "output": ""
    }
  ]
}
```

**3. An `error` example because of a contract violation** — code `6`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(-1) == -2
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "failed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 1, "failed": 0, "error": 1},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 29},
      "expression": "double(-1) == -2",
      "message": null,
      "status": "error",
      "values": [
        {"call": "double(-1)", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 23},
         "type": "Int", "status": "stopped", "value": null}
      ],
      "not_evaluated": [],
      "diagnostic": {
        "severity": "error", "category": "contract", "code": "E4001", "message": "Precondition violated",
        "label": "This call breaks a 'requires' condition of 'double'", "hint": null,
        "notes": [
          "The condition at line 2 is false: requires n >= 0",
          "Reason: Only natural numbers",
          "It was called with: n = -1",
          "While evaluating example 2 of 'double', at line 4."
        ],
        "file": "double.nex", "line": 4, "column": 13, "end_line": 4, "end_column": 23
      },
      "output": ""
    }
  ]
}
```

The call `double(-1)` appears as `stopped`: it started, but its `requires` stopped it before
returning anything.

**4. No example selected** — code `6`.

```text
1  fn double(n: Int) -> Int {
2      return n * 2
3  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "no_examples",
  "filter": {"function": null},
  "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0},
  "examples": []
}
```

**5. Failed static analysis** — code `1`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example 2 + 2 == 4
4      return n * 2
5  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error", "category": "semantic", "code": "E2020", "message": "Example without its function",
      "label": "This example of 'double' never calls 'double'",
      "hint": "Write the call with its inputs, for example: example double(2) == 4",
      "notes": [],
      "file": "double.nex", "line": 3, "column": 13, "end_line": 3, "end_column": 23
    }
  ],
  "status": "not_run",
  "filter": {"function": null},
  "summary": null,
  "examples": null
}
```

In document 1, `double(1)` appears before `double(double(1))`: it was invoked first (section 6.3).
None of the five has a `main`: `nex test` does not require it (section 4).

**Fragments: calls not invoked.** They are not complete documents, but the result of an example
inside `examples`, to show the two reasons of `not_evaluated`. In a version of `double.nex` with
the example `double(1) == 3 and double(2) == 4` on line 3 (`failed`, because `double(1)` is `2`):

```json
{
  "function": "double",
  "index": 1,
  "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 46},
  "expression": "double(1) == 3 and double(2) == 4",
  "message": null,
  "status": "failed",
  "values": [
    {"call": "double(1)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
     "type": "Int", "status": "returned", "value": "2"}
  ],
  "not_evaluated": [
    {"call": "double(2)", "span": {"line": 3, "column": 32, "end_line": 3, "end_column": 41},
     "type": "Int", "reason": "short_circuit"}
  ],
  "diagnostic": {
    "severity": "error", "category": "test", "code": "E4004", "message": "Example failed",
    "label": "This example of 'double' is false", "hint": null,
    "notes": ["double(1) returned 2"],
    "file": "double.nex", "line": 3, "column": 13, "end_line": 3, "end_column": 46
  },
  "output": ""
}
```

And with the example `double(double(-1)) == 4` on line 3 (`error`: the inner call breaks the
`requires`, and the outer one is never invoked):

```json
{
  "function": "double",
  "index": 1,
  "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 36},
  "expression": "double(double(-1)) == 4",
  "message": null,
  "status": "error",
  "values": [
    {"call": "double(-1)", "span": {"line": 3, "column": 20, "end_line": 3, "end_column": 30},
     "type": "Int", "status": "stopped", "value": null}
  ],
  "not_evaluated": [
    {"call": "double(double(-1))", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 31},
     "type": "Int", "reason": "stopped_before"}
  ],
  "diagnostic": {
    "severity": "error", "category": "contract", "code": "E4001", "message": "Precondition violated",
    "label": "This call breaks a 'requires' condition of 'double'", "hint": null,
    "notes": [
      "The condition at line 2 is false: requires n >= 0",
      "Reason: Only natural numbers",
      "It was called with: n = -1",
      "While evaluating example 1 of 'double', at line 3."
    ],
    "file": "double.nex", "line": 3, "column": 20, "end_line": 3, "end_column": 30
  },
  "output": ""
}
```

### 7. Python API

`nexora.tooling` promises in its documentation that **nothing is executed** ("Nothing is executed"), and the
MCP server relies on that promise. The evaluation goes in **`nexora.api`**, the module that already runs
code in memory with `run_source`, and it follows its conventions (code as text, `filename` only as a
name, no file opened, result as a dictionary ready for `json.dumps`):

```text
nexora.api.test_source(source, filename="playground.nex", *, function=None) -> dict
```

- It returns **the same `nexora.test/1` document** as `nex test --format json`.
- `function` does the same as `--function`. If the function does not exist (and the analysis has no
  errors), it raises `nexora.tooling.ToolingError("unknown_function", ...)`, the same pattern that
  `get_language_spec` uses for a non-existent section (`"unknown_section"`).
- An internal error is not turned into a document: the exception reaches the caller, who decides.
- It does not accept limits (`limits`) in 0.4.0. `run_source` has them for the playground, which will not have
  a "Test" button in this version; they will be added with it, with the same `Limits` class.
- `nexora.tooling` and the MCP server do **not** gain any test function.

### 8. Analysis tools

- **`nex inspect`:** new node `Example` with the fields `condition` (expression) and `message` (text or
  `null`), and new field `examples` (list of `Example`) in `Function`, **at the end**, after `body`.
  The format **is still `nexora.inspect/2`**, because of the written contract, not for convenience:
  - [Schema of `nex inspect`](../inspect-schema.md), "Stability and evolution": *the version
    number does not change when a field is added to a node or a new node type*, and *tools
    must ignore the fields and node types they do not know*.
    [JSON protocol](../json-protocol.md) says the same, and the schemas do not forbid additional
    fields.
  - The same document requires that *the order of the fields be stable within a version*. Adding
    `examples` **at the end** of `Function` leaves all the existing fields in the same order.
  - No existing field changes type or meaning: `Contract.clause` is still
    `requires` or `ensures`, and `type` in the expressions still has the values of 0.3. What is
    new only appears inside the new field.
  - Contrast: 0.3.0 did move to `/2` because it changed the meaning of an existing field (`type`
    stopped being a closed list of five types). Nothing like that happens here.
  - Checkable consequence: a consumer written for 0.3.1 that follows the rule of ignoring what it
    does not know reads any program as before, whether it has examples or not (case 38 of the matrix).
- **`nex context`:** new field `examples` in each function, at the end (`condition`, `message`,
  `line`), and new value `examples` in `features`. The format is still `nexora.context/1`.
- **`nex symbols`:** the calls of an example are references to the called functions.
- **Diagnostics:** `E2020` (`semantic`), `E4004` (`test`) and the new category `test`. Adding a
  code or a category does not change the version of `nexora.diagnostics/1` (JSON protocol). The API uses
  the category `contract` to choose the state `contract_violation` in `run_source`; `E4004` only
  appears in `nexora.test/1` and, with its own category, cannot be confused with a contract.

## Reasons

- **Why in the function and not in a separate test file.** The requirement stays next to the code
  that meets it: whoever edits the function, person or agent, has it in front of them. It is the idea of
  contracts.
- **Why a call in the tree, and not "that the execution goes through the function".** The second one can only
  be known by running, and the analysis does not run. The first one is checked by looking at the tree.
- **Why exactly one call is not required, nor that it be at the root.** `f(f(2)) == 16` and
  `f(1) + f(2) == 6` are natural examples; requiring more protects nothing.
- **Why they do not see the parameters.** An example is a closed case. If it depended on the values of
  a call, it would be an `ensures`.
- **Why `failed` and `error` are not mixed.** "The function returns something else" and "the function never got
  to return anything" are fixed in different ways.
- **Why the category `test`.** A false example did not stop anything: the result is not the expected one.
  With `contract`, whoever filters by category would confuse it with a broken contract.
- **Why `no_examples` ends with `6`.** A `0` means "tested and correct".
- **Why the report only at the end.** It is the only way for an internal error not to leave half a
  report that looks complete.

## What it does not guarantee

- Examples check **the written cases**, not all of them. For general rules there are contracts
  and refined types.
- There is no time or memory limit per example (section 3.3).
- There are no tests outside the functions (`test` blocks of the draft), nor approximate comparison for
  `Float`: `==` is exact.

## Alternatives ruled out

- **`test "name" { ... }` blocks** (design draft). They need statements and `assert`, and they separate
  the case from the function. They can be added later without changing `example`.
- **Evaluating the examples in `nex check`, or in `nex run` before `main`.** They would break the boundary between
  analysing and running.
- **Reusing the `Contract` node with `clause: "example"`.** It would change the meaning of a field that
  tools already read; a new node is an addition.
- **`test_source` in `nexora.tooling`.** It would break the promise of that module (section 7).

## Compatibility

- `example` goes from reserved word to keyword. No valid program could use it as a
  name.
- `nex run`, `nex check` and the analysis tools do not change with programs without examples.
- Formats: `nexora.test/1` is new. `nexora.inspect/2` and `nexora.context/1` gain fields at the end of
  their objects. `nexora.diagnostics/1` gains a category and two codes. None changes version.
- Exit codes: `6` is added; no existing one changes meaning.

## Conditions to implement it

What the implementation needs and does not exist today. It does not change any previous decision:

1. **The analysis without `main`.** `pipeline.analyze` and the checker need a way of skipping
   `E2001` that only `nex test` uses.
2. **Examples outside the call graph.** When checking an example, the checker must record
   the references (for `nex symbols`) but not the calls (`CheckedProgram.calls`).
3. **Evaluating an expression without a call.** The interpreter only knows how to run `main`. It needs to evaluate
   an expression with an empty environment, with the same adjustment of the Python recursion limit and
   the same conversion of `RecursionError` into `E3004` that `Interpreter.run` does (section 3.4).
4. **Observing the own calls.** For `values` and `not_evaluated`, the interpreter has to be able to
   record, for the own call nodes of the expression, the moment of their invocation and their value,
   and mark as `short_circuit` those of an operand that `and` or `or` skip, without changing how anything
   is evaluated.
5. **The output per example.** A `print` collector per example.

## Design test matrix

They will be written before the implementation and must fail until it exists. "Unit" are tests of the
checker and of the interpreter; "CLI" uses `nex test`; "API" uses `test_source`; "Docs" are examples of
the documentation checked by `tests/test_docs.py`.

| # | Case | Input (summarized) | Expected result | Level |
|---|------|--------------------|--------------------|-------|
| 1 | Valid example | `example double(2) == 4` | `passed`; `values` with `"4"`; `status: passed`; code `0` | Unit, CLI, Docs |
| 2 | False expression | `example double(2) == 5` | `failed`, `E4004` on the expression, notes `double(2) returned 4`; code `6` | Unit, CLI, Docs |
| 3 | Without own call | in `double`: `example 2 + 2 == 4` | `nex check`: `E2020` on the whole expression. `nex test`: `not_run`, code `1` | Unit, CLI |
| 4 | Call only from another function | in `double`: `example quad(1) == 4`, and `quad` calls `double` | `E2020` | Unit |
| 5 | Several own calls | `double(double(1)) == 4`, `double(1) + double(2) == 6` | `passed`; `values` in order of invocation: `double(1)` before `double(double(1))`; `double(1)` before `double(2)` | Unit, API |
| 6 | Non-`Bool` expression | `example double(2)` | `E2011` `The condition of 'example' must be Bool, found Int`; no `E2020` | Unit |
| 7 | Not `Bool` and without own call | `example 2 + 2` | `E2011` and `E2020` | Unit |
| 8 | Uses a parameter or `result` | `example double(n) == 4`, `example result == 4` | `E2005` with its own suggestion | Unit |
| 9 | Explanation | `example double(2) == 4, "Two doubled"` | `message` in `nex inspect`, `nex context` and the document; `Reason:` in `E4004` if it fails | Unit, API |
| 10 | Malformed explanation | empty, only spaces, with `\n`, or not textual | `E1101` | Unit |
| 11 | Misplaced clause | `example` after a statement | `E1106` with `'example' must come at the start...` | Unit |
| 12 | Broken `requires` | `requires n >= 0` and `example double(-1) == -2` | `error`, `E4001` on the call, note of the example at the end, `values` with `double(-1)` `stopped` and `value: null`; code `6` | Unit, CLI, API |
| 13 | Broken `ensures` | `ensures result > n` and `example double(0) == 0` | `error`, `E4002` on the clause, note of the example | Unit, CLI |
| 14 | Contract broken in a nested call | example of `f` → `g` → `h`, and `g` breaks the `requires` of `h` | `error`, `E4001` on the call to `h`, call chain and note of the example of `f` | Unit |
| 15 | Runtime error | example that reaches a division by zero in another function | `error`, `E3001` in that function, note of the example | Unit, CLI |
| 16 | Broken refined type | `example f(Percent(150 - 1)) == 1` | `error`, `E4003`, note of the example | Unit |
| 17 | Constant outside the refined type | `example f(150) == 1` with a `Percent` parameter | `E2017` without running; `not_run` | Unit |
| 18 | Different results | three examples: `failed`, `passed`, `error` | the three evaluated, in order; `summary` `3/1/1/1`; `status: failed`; code `6` | Unit, CLI, API |
| 19 | Isolation | an example causes `E3004` because of endless recursion (it stops at the NEXORA limit of 1000 calls, which is deterministic) and the next one is valid | the first one `error`, the second `passed`, with its clean stack and its own `output` | Unit |
| 20 | Short circuit | `example double(1) == 3 and double(2) == 4` | `failed`; `double(1)` in `values`; `double(2)` in `not_evaluated` with `reason: short_circuit` | Unit, API |
| 21 | `print` output | the function prints during the example | `output` contains it; in text it is only shown if it does not pass | CLI, API |
| 22 | Valid filter | `--function triple` with examples in `double` and `triple`; `triple` calls `double` | only those of `triple`; the `requires` of `double` is still checked | CLI, API |
| 23 | Non-existent filter | `--function nope` | usage message with a suggestion, code `2`, without a document; in the API, `ToolingError("unknown_function")` | CLI, API |
| 24 | Function without examples | `--function helper`, which has none | `no_examples`, `examples: []`, code `6` | CLI |
| 25 | File without examples | no function has them | `no_examples`, text `no examples to run`, code `6` | CLI, Docs |
| 26 | Static errors | any error of the analysis | `not_run`, `summary` and `examples` `null`, code `1`; with a non-existent `--function`, also `1` | CLI, API |
| 27 | Unreadable file | non-existent path | `not_run`, `E0001`, code `4` | CLI |
| 28 | Without `main` | only functions with examples | `nex test` evaluates them; `nex check` still reports `E2001` | CLI |
| 29 | `main` present | a `main` that prints | it is not run: its output does not appear | CLI |
| 30 | JSON schema | all the previous documents | they meet `nexora-test.schema.json`; `ok`, `status`, `summary` and `examples` consistent with each other | API, CLI |
| 31 | Internal error | a Python exception simulated in the interpreter during the second example | code `70`, internal error message, nothing on the standard output (neither text nor JSON) | CLI |
| 32 | Call graph | example of `f` that calls `f` and `g` | `nex context`: `f` is not `recursive`, `calls` of `f` does not include `g`; `nex symbols`: both are references | Unit |
| 33 | The analysis does not run | example that would give `E3001`, or that prints | `nex check`, `nex inspect` and `nex context` finish without evaluating it nor printing anything | CLI |
| 34 | `nex inspect` and `nex context` | function with two examples | `Example` with `condition` and `message`, `examples` at the end of `Function`; `examples` in `context` and in `features` | Unit |
| 35 | Call not invoked after an error | `example double(double(-1)) == 4` | `error`; `double(-1)` in `values` as `stopped`; `double(double(-1))` in `not_evaluated` with `reason: stopped_before` | Unit, API |
| 36 | `RecursionError` during an example | two examples; during the first one, the test makes the interpreter raise `RecursionError` (replacing an internal function, as `test_refined_types.py` already does with `broken_rule`) | the first one in `error` with `E3004`; the second one evaluated and `passed`; global code `6`, **not** `70`. It does not depend on the Python recursion limit, on the real depth of the stack nor on time | Unit, CLI |
| 37 | Ctrl+C | interruption during an example | code `130`, without a report | CLI |
| 38 | Compatibility of `nexora.inspect/2` | a program with examples | the document validates against the `nexora.inspect/2` schema of 0.3.1 (without the new fields), and all the previous fields keep their order | Unit |

## Decisions closed in the review

1. **`nex check` still requires `main` (`E2001`).** A file with only functions and examples passes
   `nex test` and does not pass `nex check`. It is consistent with what `nex check` promises: that the program
   can be run with `nex run`, and without `main` it cannot. `nex test` does not require `main` because it does not
   run the program, only its examples. A way of checking "libraries" without `main` (for
   example, `nex check --library`) is left for a future decision, if needed.
2. **`no_examples` ends with `6`**, the same code as `failed`: both mean "the test was not
   passed". Nothing was found in the current contract that forces another code. Whoever needs to
   tell them apart reads `status` in the JSON document.

## Open questions

1. **`MemoryError` and code `70`.** `MemoryError` is caused by the program, not by NEXORA, but today
   `nex run` treats it as an internal error (`70`): it does not catch it and it reaches the general handler of
   `cli.py`. The API, on the other hand, turns it into the state `memory_limit` (`api.py`, `worker.py`).
   - In 0.4.0, `nex test` **inherits** the behaviour of `nex run` (section 3.4). It is the only
     exception to the rule that `70` corresponds to a failure of NEXORA, and it is written as such.
   - The consistent thing is to decide it for all the commands at once, for example with a runtime
     diagnostic of its own for running out of memory. That decision also affects `nex run` and is
     **out of the scope of 0.4.0**, for a future decision.
   - Resolved in [decision 0009](0009-memoria-agotada.md).
