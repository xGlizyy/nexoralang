# Automated tools and AI

NEXORA comes from a question: what a language should look like when code is written, read and
reviewed by people and by artificial intelligence systems alike. This page explains what there is of
that **today**, precisely, and what is still an intention.

## What each thing is

| | What it includes | Status |
|-|------------------|--------|
| **Features of the language** | Static types without implicit conversions, a single meaning per name, contracts and refined types with the explanation of every rule | Implemented |
| **Structured data for tools** | Diagnostics, syntax tree, symbols and summary of the program as JSON, with [versioned schemas](json-protocol.md) | Implemented and tested |
| **Python API** | The `nexora.tooling` module: the same outputs, without going through the command line | Implemented and tested. **Experimental**: it may change before 1.0 |
| **MCP server** | An optional server that offers the analysis as tools to a compatible assistant ([MCP](mcp.md)) | Implemented and tested with the client of the official SDK. Checked by hand in a Claude Code session; **in no other assistant** |
| **Language server (LSP)** | Integration with editors ([LSP](lsp.md)): diagnostics, completion, hover, navigation, rename and formatting | Implemented and tested (`nexora-lsp`). Used by the VS Code extension; it does not resolve imports yet |
| **Research goal** | Finding out whether these decisions make it easier for an automated tool to understand, generate or fix code | **Not evaluated** |
| **Integrations with AI models** | Calls to models, code generation, an assistant of its own | **They do not exist** |

What NEXORA does **not** do:

- It calls no AI model and no external service. It works offline.
- No model takes part in deciding whether a program is valid. The rules are deterministic code:
  the same file always produces the same result.
- It includes no assistant, code generator or automatic fixer.

And what **cannot be claimed**:

- There is no evaluation that shows that an AI tool gets better results with
  NEXORA than with another language. That experiment has not been done.
- The design decisions described here are reasoned hypotheses, not measured results.

## What the language offers a tool

Four JSON outputs, meant to be read without interpreting text written for people. None
runs the analyzed program.

| Output | Command | Schema | Contains |
|--------|---------|--------|----------|
| Diagnostics | `nex check file.nex --format json` | `nexora.diagnostics/1` | The errors, with code, category, position and suggestion |
| Structure | `nex inspect file.nex` | `nexora.inspect/3` | The syntax tree, with the type of every expression |
| Symbols | `nex symbols file.nex --format json` | `nexora.symbols/2` | Functions, parameters and variables, with their type, their scope and every use |
| Context | `nex context file.nex --format json` | `nexora.context/2` | A summary: signatures, contracts, who calls whom, features used |
| Evidence | `nex check file.nex --evidence --format json` | `nexora.evidence/1` | What backs every clause: `checked` or `trusted` ([JSON protocol](json-protocol.md#evidence)) |

The last two are explained in [Structured context](ai-context.md); the formats, their
versions and their rules, in [JSON protocol](json-protocol.md).

### How the pieces fit

```text
                       ┌─ nex (command line)
lexer → parser →       │
checker  ──────────►  nexora.tooling  ──┼─ import nexora.tooling (Python)
(analysis, no run)        (JSON documents)    │
                       └─ nex-mcp (MCP server, optional)
```

The three entry points call the same functions and return the same documents. There is no second
analyzer and no duplicated rules: what decides whether a program is valid is always the checker.

### Diagnostics

<!-- nex:check-json -->
```nex
fn double(n: Int) gives Int {
    return n * 2
}

fn main() {
    let price = 2.5
    print(double(price))
}
```

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
      "label": "Expected Int, found Float",
      "hint": "Convert the Float explicitly with to_int(...), which drops the fractional part.",
      "notes": [
        "This is the argument for 'n' in: fn double(n: Int) gives Int"
      ],
      "file": "program.nex",
      "line": 7,
      "column": 18,
      "end_line": 7,
      "end_column": 23
    }
  ]
}
```

What a tool can do with this without reading the text of the message:

- Know **whether** the program is valid (`ok`) and **what kind** of problem it has (`category`).
- Identify the problem with a code that does not change between versions (`code`).
- Locate the exact fragment, from start to end (`line`, `column`, `end_line`, `end_column`).
- Offer the suggested fix when there is one (`hint`); when it is `null`, the language has
  no well-founded suggestion and does not make one up.

### Structure of the program

`nex inspect` returns the same tree that the checker and the interpreter use, not a separate
representation. For the smallest possible program:

<!-- nex:inspect -->
```nex
fn main() {
    print(1 + 2)
}
```

```json
{
  "schema": "nexora.inspect/3",
  "nexora_version": "0.11.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "complete": true,
  "program": {
    "kind": "Program",
    "span": {
      "line": 1,
      "column": 1,
      "end_line": 4,
      "end_column": 1
    },
    "types": [],
    "functions": [
      {
        "kind": "Function",
        "span": {
          "line": 1,
          "column": 1,
          "end_line": 3,
          "end_column": 2
        },
        "name": "main",
        "name_span": {
          "line": 1,
          "column": 4,
          "end_line": 1,
          "end_column": 8
        },
        "params": [],
        "return_type": null,
        "header": [],
        "body": {
          "kind": "Block",
          "span": {
            "line": 1,
            "column": 11,
            "end_line": 3,
            "end_column": 2
          },
          "statements": [
            {
              "kind": "ExprStatement",
              "span": {
                "line": 2,
                "column": 5,
                "end_line": 2,
                "end_column": 17
              },
              "expression": {
                "kind": "Call",
                "span": {
                  "line": 2,
                  "column": 5,
                  "end_line": 2,
                  "end_column": 17
                },
                "callee": "print",
                "callee_span": {
                  "line": 2,
                  "column": 5,
                  "end_line": 2,
                  "end_column": 10
                },
                "arguments": [
                  {
                    "kind": "Binary",
                    "span": {
                      "line": 2,
                      "column": 11,
                      "end_line": 2,
                      "end_column": 16
                    },
                    "operator": "+",
                    "operator_span": {
                      "line": 2,
                      "column": 13,
                      "end_line": 2,
                      "end_column": 14
                    },
                    "left": {
                      "kind": "IntLiteral",
                      "span": {
                        "line": 2,
                        "column": 11,
                        "end_line": 2,
                        "end_column": 12
                      },
                      "value": 1,
                      "type": "Int"
                    },
                    "right": {
                      "kind": "IntLiteral",
                      "span": {
                        "line": 2,
                        "column": 15,
                        "end_line": 2,
                        "end_column": 16
                      },
                      "value": 2,
                      "type": "Int"
                    },
                    "type": "Int"
                  }
                ],
                "qualifier": null,
                "type": "Void"
              }
            }
          ]
        },
        "public": false
      }
    ],
    "records": [],
    "uses": [],
    "imports": []
  }
}
```

Every node says what it is (`kind`), where it comes from (`span`) and, in expressions, what type it has
(`type`). All the nodes and fields are described in [`inspect-schema.md`](inspect-schema.md).

## Python API

The `nexora.tooling` module offers the analysis to another Python program, without starting a process or
interpreting the output of the terminal. **It is experimental**: it is tested, but its names may
change before version 1.0. The rest of the modules (`lexer`, `parser`, `checker`…) are internal.

| Function | Returns |
|----------|---------|
| `check_source(source, filename="source.nex")` | `nexora.diagnostics/1` document |
| `inspect_source(source, filename="source.nex")` | `nexora.inspect/3` document |
| `get_symbols(source, filename="source.nex", *, name=None, function=None)` | `nexora.symbols/2` document |
| `get_context(source, filename="source.nex")` | `nexora.context/2` document |
| `get_evidence(source, filename="source.nex")` | `nexora.evidence/1` document: what backs every clause; only the enforcement is computed |
| `get_language_spec(section=None)` | `nexora.spec/2` document: the index of the specification, or a section |
| `get_capabilities()` | `nexora.capabilities/1` document: keywords, types, built-in functions, error codes, limits |
| `render_context(document)`, `render_symbols(document)` | The text that `nex context` and `nex symbols` write |

```python
from nexora.tooling import check_source

result = check_source('fn main() {\n    print(total)\n}', "demo.nex")
print(result["ok"])                        # False
print(result["diagnostics"][0]["code"])    # E2005
```

- They receive the **code as text** and return dictionaries that convert to JSON as they are.
  `filename` is only a label: no file is opened.
- **None of them runs the program**, writes to disk or uses the network.
- A program with errors does not raise an exception: it returns `ok: False` and the diagnostics.
- `ToolingError` is only raised for a wrong argument (for example, a section that does not exist).
- `get_language_spec` reads the specification of the project. It is only available with NEXORA installed
  from the source code; from a *wheel* package it answers `available: False`.

To **run** a program from Python there is another module, `nexora.api` (`run_source`), which is
the one the [playground](playground.md) uses. It is separate on purpose: the analysis tools
cannot run anything.

## The cycle of an agent

The use these tools are meant for:

1. **Getting the rules** from the official source: `get_capabilities` and `get_language_spec`.
2. **Getting the context** of the program: `nex context`, and `nex symbols` for what it is going to touch.
3. **Writing or modifying** the code. The agent does this; NEXORA takes no part.
4. **Analyzing**: `nex check --format json`.
5. **Reading the diagnostics**: code, category, exact position, suggestion if there is one.
6. **Fixing** and going back to step 4, until `ok` is `true` or the number of attempts that
   the agent has set runs out.

Everything NEXORA brings to that cycle is deterministic and checkable. It neither generates the code, nor applies
fixes, nor decides when to stop. And `ok` being `true` means that the program meets the
static rules, not that it does what was intended: only running it and testing it say that.

An agent can go through the cycle with the command line, with the Python API or, if its assistant
is compatible, with the [MCP server](mcp.md).

## Reference tasks

`tests/tooling_tasks.py` defines nine tasks that a person or an agent needs to solve on a
program, each one with the tool that answers it and the expected answer:

| Task | Tool |
|------|------|
| List the functions and their signatures | `get_context` |
| Find out the type of a variable without an annotation | `get_symbols` |
| Know who calls a function and what it promises, before changing it | `get_context` |
| Find every use of a parameter | `get_symbols` |
| Say whether a program is valid and, if not, what fails, where and with which suggestion | `check_source` |
| Tell which of two versions of a program is valid | `check_source` |
| Look up in the specification what an error code means | `get_language_spec` |
| Locate in which call a contract is broken | `nexora.api.run_source` (it **runs** the program) |
| Recognize what the static analysis can **not** say | `get_context` |

`tests/test_tooling_tasks.py` checks all nine against the real tools. The last two
are deliberate: the reference program calls a function with a value that breaks its
contract. The static analysis answers `ok: true` and warns in a note that the contracts have not been
proven; finding the violation requires running the program, which the analysis tools
(and the MCP server) do not do.

**What it measures and what it does not.** It measures that the deterministic tools answer those
questions correctly. **It measures no AI model.** Whether an agent writes better NEXORA with these tools
than without them has not been evaluated, and it is not claimed.

An evaluation like that would have to be done outside this repository (which calls no model), and
to be honest it would need: a set of tasks fixed in advance, the same tasks with and without
tools, several attempts per task, an automatic success criterion (the program passes
`nex check` and produces the expected output with `nex run`) and the publication of all the results,
the bad ones too.

## Guarantees of these outputs

Checked by automated tests:

| Guarantee | Test |
|-----------|------|
| Every document meets its JSON Schema, also with wrong inputs | `tests/test_tooling.py` |
| The CLI, the Python API and the MCP server return the same document | `tests/test_tooling.py`, `tests/test_mcp.py` |
| No analysis tool runs the program, opens other files or uses the network | `tests/test_security.py`, `tests/test_mcp.py` |
| The output is always valid JSON, also for missing files or files that are not NEXORA | `tests/test_cli.py`, `tests/test_robustness.py` |
| The fields and their order are the documented ones | `tests/test_inspect.py`, `tests/test_cli.py` |
| The positions match the text of the file | `tests/test_inspect.py`, `tests/test_diagnostics.py` |
| The same file produces exactly the same output | `tests/test_inspect.py`, `tests/test_cli.py` |
| Neither `check` nor `inspect` runs the program | `tests/test_security.py` |
| The JSON examples of this page are the real output | `tests/test_docs.py` |

## Versions of the schemas

Every document carries a `schema` field with a name and a version number.

- The number **changes** if a field or a node kind is removed, renamed or changes its meaning.
- The number **does not change** if fields or node kinds are added. A tool must ignore what it
  does not know.

The complete rules, the history and the JSON Schema files are in
[JSON protocol](json-protocol.md).

## Limitations

- **With syntax errors the tree is partial** (`"complete": false`): the statements that
  have an error and the functions whose declaration has one are missing, and only the syntax errors
  are reported. It is useful to inspect half-written code, with that caveat.
- **With lexical errors there is no tree** (`"program": null`): an unclosed text or an invalid
  character prevents the whole analysis.
- **Comments do not appear in the tree.**
- **Across files there is little information**: the documents describe the entry file, and of the
  modules it imports they only give the `file` of each function and symbol.
- **A fix cannot be applied automatically.** `hint` is a text for people, not a
  structured edit with a position and replacement text.
- **Messages are in English** and their wording may change; what is stable is the code.
- **The JSON of `nex run` only appears if there is a failure**, and it goes to the standard error.
- **The language server does not resolve imports**, and the formatter is only reachable through it: there is no `nex` command for it ([LSP](lsp.md#limitations)).
- **The Python API is experimental**, and the other modules are internal and may change without notice.
- **The MCP server has only been tested in one assistant** (Claude Code, a manual session), besides
  the automated tests with the SDK client.
- **No AI model has been evaluated** with these tools.
- The `TypeDecl` node is stable since `nexora.inspect/2`. `Contract` changed in `nexora.inspect/3`: it is an item of `Function.header`, with the clause words of 0.12 and a `name` ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)).

## Use cases this allows

Uses for which these outputs are enough, without NEXORA including any of them:

- An editor that underlines errors at their exact position and shows the suggestion.
- A continuous integration script that rejects changes according to the category of the errors.
- A tool that lists the functions of a program with their signatures and contracts.
- An external AI assistant that, after generating code, runs `nex check --format json`, reads the
  codes and positions, and fixes the program in a loop, with the interpreter —and not the model— as
  the judge of whether the result is valid.

The last one is the scenario that motivates the design. Whether it works better than with other languages is
exactly what remains to be checked.
