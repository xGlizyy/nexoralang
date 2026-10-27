# NEXORA

**A new programming language, with its own syntax and rules, that explores how to structure
programs so that they are easier to analyze for people and for automated tools.**

This directory contains the core of the language: its reference interpreter, the command-line
tool `nex`, the specification, the examples and the tests.

<!-- nex:run -->
```nex
type Grade = Float where value >= 0.0 and value <= 100.0, "A grade goes from 0 to 100"

fn average(total: Int, count: Int) gives Grade
    needs count > 0, "An average needs at least one mark"
{
    return Grade(to_float(total) / to_float(count))
}

fn main() {
    let mean = average(270, 4)
    if mean >= 50.0 {
        print("Passed with " + to_text(mean))
    } else {
        print("Failed")
    }
}
```

```text
Passed with 67.5
```

## Vision and motivation

Most languages were designed for a person to give instructions to a machine.
Today code is also generated, read and reviewed by artificial intelligence systems.
NEXORA starts from a question: **what should a language designed for that shared work look like?**

In this version, the question takes the shape of design decisions that can be checked:

- **Nothing implicit.** There are no automatic conversions between types; every change of type is written down.
- **One name, one meaning.** Inside a function a name is neither redefined nor shadowed.
- **What can be checked before running is checked before.** All type errors are
  detected without running the program.
- **The rules are part of the code.** It is the feature that distinguishes NEXORA: a function
  declares what it expects and what it promises (contracts), a type declares which values it accepts (refined
  types), and every rule can carry its explanation. When a rule is broken, the diagnostic
  says which one, where, with which values and why it exists
  ([decision 0006](docs/decisions/0006-requisitos-verificables.md)).
- **Tools receive data, not text.** The program and its errors can be obtained as JSON,
  with a versioned schema.

These decisions are a **working hypothesis**. There is no evaluation that shows that
they make the work of an AI tool easier, and this project does not claim that NEXORA is faster,
safer, more productive or better than any other language.

NEXORA neither includes nor calls any AI model. Its rules are deterministic code that works
offline. What there is and what there is not, precisely: [Automated tools and AI](docs/ai-tooling.md).

## Status

**Version 0.12.1. Early-stage project**, before 1.0: the language may change
incompatibly and it is not suitable for production use.

| Status | What it includes |
|--------|------------------|
| **Implemented and tested** | Static types `Int`, `Float`, `Bool`, `Text` and `Void`, with inference and annotations · immutable **lists** `List[T]`, with `List.length`, `List.get`, `List.append`, `List.concat`, `List.contains` and `for` over lists · immutable **records** (`type Point = { x: Int, y: Int }`), with nominal identity · **`Option[T]` and `Result[T, E]`** · **modules** (`import "path/file.nex"`, `pub`) · **refined types** (`type Percent = Int where ...`): constants are checked without running and the rest with `Percent(x)` when running · **arguments** (`args()`) and **standard input** (`input()`) · **files** with explicit permissions (`uses read "path"` and `--allow-read=path`) · **contracts** (`needs`, `promises`) in the header of the function, checked when running, and `trust`, which is never checked · **examples** in functions (`example`), evaluated with `nex test` · explanation of every rule in the diagnostics · immutable (`let`) and reassignable (`var`) variables, and scopes · **`while` loops** with their measure (`shrinks`) and invariants (`keeps`), checked on every iteration · **operations on texts** (`Text.length`, `Text.slice`, ordering, `Int.parse`), each function with its requirements · arithmetic, comparisons and logic · explicit conversions · functions with parameters and `return` · `if` / `else` · recursion · static analysis of names, types and return paths · commands `run`, `check`, `inspect`, `context`, `symbols` and `test` · diagnostics with code and category, as text and JSON · versioned JSON formats with JSON Schema |
| **Experimental** | Python API `nexora.tooling` · optional MCP server (tested with the SDK client and, by hand, in Claude Code; in no other assistant) · web [playground](docs/playground.md), only locally |
| **Planned** (does not exist) | `break` and `continue`, `for` over ranges or `Text`, maps, user generics, network and external processes |
| **Under research** (does not exist) | Static verification of contracts, AI features inside the language, and the evaluation of the hypothesis of the project |

Detail: [roadmap](docs/roadmap.md) and [limitations](docs/limitations.md).

## Requirements

- Python 3.11 or newer.
- Nothing else to use the language: the interpreter only uses the Python standard library.
- An internet connection only during installation.

## Installation

From this directory (`nexora/`):

```bash
python -m venv .venv
```

Activate the virtual environment:

| System | Command |
|--------|---------|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Linux and macOS | `source .venv/bin/activate` |

Install and check:

```bash
python -m pip install -e .
nex --version
```

```text
NEXORA 0.12.1
```

The `nex` command is installed inside the virtual environment, not system-wide: it is only
available with the environment activated. `python -m nexora` does the same as `nex`.

Checked on Windows 11 with Python 3.12 and on Linux (Ubuntu 24.04 on WSL 2) with Python 3.11, 3.12
and 3.13. It has not been tested on a real Mac yet. Complete guide,
alternatives and troubleshooting: [Installation](docs/installation.md).

## First program

Save this in a file `program.nex`:

<!-- nex:run -->
```nex
fn square(n: Int) gives Int {
    return n * n
}

fn main() {
    let side = 12
    print("Side: " + to_text(side))
    print("Area: " + to_text(square(side)))
}
```

Run it:

```bash
nex run program.nex
```

```text
Side: 12
Area: 144
```

If the program has an error, NEXORA explains it **before running anything**:

<!-- nex:check-fails -->
```nex
fn square(n: Int) gives Int {
    return n * n
}

fn main() {
    print(square(2.5))
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:6:18
  |
6 |     print(square(2.5))
  |                  ^^^ Expected Int, found Float
  = note: This is the argument for 'n' in: fn square(n: Int) gives Int
  = hint: Convert the Float explicitly with to_int(...), which drops the fractional part.

error: program.nex: check failed with 1 error
```

Next step: [Getting started](docs/getting-started.md), a guide that goes through variables, types,
functions and how to read an error.

## Commands

| Command | What it does |
|---------|--------------|
| `nex run file.nex` | Analyzes the program and, if it has no errors, runs it |
| `nex check file.nex` | Checks syntax, names and types **without running** the program |
| `nex inspect file.nex` | Writes the structure of the program as JSON, **without running it** |
| `nex context file.nex` | Summarizes the program: signatures, contracts, calls, features. **Without running it** |
| `nex symbols file.nex` | Lists functions, parameters and variables, and where each one is used. **Without running it** |
| `nex test file.nex` | Evaluates the examples (`example`) of the functions, each one separately. It does not require `main` or run it |
| `nex --version` | Shows the version |
| `nex --help` | Shows the help |

`nex check`, `nex run`, `nex context`, `nex symbols` and `nex test` accept `--format json` to deliver the
result as data.

| Exit code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | The program has errors (detected without running) |
| `2` | Wrong use of the command |
| `3` | The program failed while running |
| `4` | The file could not be read |
| `5` | The program broke a contract |
| `6` | `nex test`: some example did not pass, or there was no example to evaluate |
| `70` | Internal error of NEXORA |
| `130` | Interrupted with Ctrl+C |

Complete reference: [CLI](docs/cli-reference.md).

## Structure for people and for tools

The same analysis produces two readings. One for people: the text diagnostic of the previous
section. And another for programs, with `nex check program.nex --format json`: the same error as
data, with a code that does not change (`E2011`), a category (`type`), the exact position from
start to end and, when there is a well-founded fix, a suggestion.

`nex inspect` also delivers the complete syntax tree, with the type of every expression;
`nex symbols`, every declared name and its uses; and `nex context`, a short summary of the program.
None of these commands runs the program, and no AI model is involved in any of them.

```bash
nex context examples/contracts.nex
nex symbols examples/functions.nex --name factorial
nex check examples/invalid/type_errors.nex --format json
```

The same outputs are available from Python (`nexora.tooling`, experimental) and, optionally,
as tools for an MCP-compatible assistant:

```bash
python -m pip install -e ".[mcp]"
nex-mcp
```

The MCP server only analyzes: it does not run programs or open files. It has been tested with the client
of the official SDK and, by hand, in a Claude Code session; not in other assistants. The language server for editors (`nexora-lsp`) is described in [LSP](docs/lsp.md).

| | |
|-|-|
| [Automated tools and AI](docs/ai-tooling.md) | What there is, what there is not, the Python API and the cycle of an agent |
| [Structured context](docs/ai-context.md) | `nex context` and `nex symbols` |
| [JSON protocol](docs/json-protocol.md) | Formats, versions and JSON Schema |
| [MCP server](docs/mcp.md) | Installation, tools, configuration and security |
| [LSP](docs/lsp.md) | The language server that the VS Code extension uses |

## Examples

In [`examples/`](examples/README.md) there are valid programs, programs with errors detected
without running and programs that fail when running. All of them run in the tests, which compare their
output with the recorded one.

```bash
nex run examples/functions.nex
nex check examples/invalid/type_errors.nex
nex run examples/failing/contract_violation.nex
```

## Tests

With the virtual environment activated and the development tools installed
(`python -m pip install -e ".[dev]"`):

```bash
python -m pytest                 # all the tests
python -m pytest --cov           # with coverage measurement
python -m ruff check src tests   # static analysis of the code
```

What they cover and how to read them: [Testing](docs/testing.md).

## Documentation

| | |
|-|-|
| [Index](docs/index.md) | All the pages |
| [Getting started](docs/getting-started.md) | Tutorial |
| [Types](docs/types.md) · [Functions](docs/functions.md) · [Contracts](docs/contracts.md) | Language guides |
| [Specification](docs/language-spec.md) | Formal reference: grammar, types, semantics |
| [CLI](docs/cli-reference.md) · [Diagnostics](docs/diagnostics.md) | Reference of the tool and of the errors |
| [Architecture](docs/architecture.md) | How the interpreter is built |
| [Limitations](docs/limitations.md) · [Roadmap](docs/roadmap.md) | What is missing |
| [Changes](CHANGELOG.md) · [Decisions](docs/decisions/README.md) | History and reasons |

All the example programs of the documentation run in the tests, and the output
shown is compared with the real one.

## Contributing

The project is public: <https://github.com/xGlizyy/nexoralang>. Issues and contributions
are handled in its [issue tracker](https://github.com/xGlizyy/nexoralang/issues).

- [How to contribute](CONTRIBUTING.md): development environment, how to add a feature and which
  checks must pass.
- [Security](SECURITY.md): what the project protects, what it does not, and how to report a problem.
- [Code of conduct](CODE_OF_CONDUCT.md).

## Licence

[MIT](LICENSE).
