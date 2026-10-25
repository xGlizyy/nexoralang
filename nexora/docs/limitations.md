# Limitations

What NEXORA does **not** do in version 0.12.0, and the risks worth knowing before using it.
Nothing that appears here as "does not exist" works today, even if it is mentioned in the design
draft, in the roadmap or in a decision that is accepted and pending implementation.

## General status

NEXORA is an early-stage project (before version 1.0):

- The language may change incompatibly between versions.
- **It is not suitable for production use.**
- It has not been used by anyone outside its development, nor audited by third parties.
- Its performance has not been measured or compared with any other language.

## What the language does not have

| Missing | Consequence |
|---------|-------------|
| `break` and `continue`, and `for` over ranges or `Text` | Write a `while` with a counter; to leave early, the condition or `return`. A `for` only goes through a `List[T]` |
| The path analysis recognizing that a `for` always returns | It does not consider it a complete return path, even if all its iterations contain a `return`; if the loop is the last statement, a `return` has to be added after it |
| Compound assignments (`+=`, `++`) | Write `x = x + 1` |
| Reassigning a parameter or the iterator of a `for` | Copy it first into a `var` |
| A `while` without a measure (`shrinks`) | Every `while` declares why it ends; if a measure cannot be written, put an explicit maximum number of iterations (`shrinks limit - turns`). A `for` over a finite list does not need one |
| `if` as an expression | `if` cannot be used to give a variable its value |
| Indexing a list (`xs[i]`) or modifying its elements | Use `List.get(xs, i)` to read; `List.append` and `List.concat` create another list. There is no `List.set` and no mutation |
| A total variant of `List.get` | `List.get` requires `0 <= i and i < List.length(xs)` and fails with `E4001`; there is no `Option` to represent the absence |
| Lists with elements of different types, or empty ones without an expected type | All the elements have the same type. `[]` and `for x in []` need an expected type (`E2011`) |
| Refining a list (`type NonEmpty = List[Int] where ...`) | A refined type can only be built over `Int`, `Float`, `Bool`, `Text` or another refined type (`E2016`) |
| `List` functions beyond `length`, `get`, `append`, `concat` and `contains` | There is no `map`, `filter`, `fold`, sorting, `slice` or search for positions |
| Maps, enumerations and optionals | `List[T]` lists are immutable and finite; records (section 4.6 of the [specification](language-spec.md)) are immutable and have no methods, refinements or recursion. `Option[T]` and `Result[T, E]` (section 4.7) exist, but without `match` or `if let`: the variants are recognized with functions |
| User-defined types and generics | Lists use `List[T]`, but the program cannot declare generic types or generic functions |
| `trim`, case conversion, `split`, `replace`, search for positions | There are `Text.length`, `Text.slice`, `Text.contains`, `Text.starts_with`, `Text.ends_with` and the ordering between texts ([specification](language-spec.md), 8.1) |
| Graphemes and Unicode normalization | A character is a code point: an `e` with the combining accent counts 2, and two texts that look the same can be different for `==` |
| Alphabetical order according to the language | The order between texts is that of the code points: `"Z" < "a"` |
| Text interpolation | Use `+` and `to_text` |
| Reading numbers with spaces, `+`, separators or in other bases | `Int.parse` and `Float.parse` only read one form (`"-42"`, `"2.5e3"`) |
| Remainder operator (`%`) and powers | |
| Mathematical functions (root, rounding, absolute value…) | They have to be written |
| Data input: the network and external processes | A program can print, read its arguments and the standard input, and use the files that it declares with `uses` and that it is allowed with `--allow-read` or `--allow-write` ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)). There is no network and there are no external processes |
| Modules and imports | Modules and imports are implemented in 0.11.0 ([decision 0018](decisions/0018-modulos-e-importaciones.md)). The playground does not support them; `nex test` only evaluates the examples of the file it is given; there are no aliases and no selective imports. |
| Functions as values, anonymous functions, overloading, default values | |
| Warnings | Every diagnostic is an error. An unused variable produces no warning |
| Block comments, multi-line texts | |
| Hexadecimal literals or literals with an exponent (`1e-3`) | |

With these limitations NEXORA is useful for small computation programs and for studying the
language itself. It is not yet useful for writing applications.

## Limits of the implementation

| Limit | Value | What happens when it is exceeded |
|-------|-------|----------------------------------|
| Nested calls | 1000 (counting `main`) | Runtime error `E3004` |
| Nested calls with very deep expressions | Fewer than 1000 | The same error `E3004`; the message says how many there were |
| Nesting of parentheses, blocks, `else if`, unary operators or types (`List[...]`) | 64 levels | Error `E1105` |
| Depth of an expression (for example, terms of a sum) | 256 | Error `E1105` |
| Work of `nex check` checking constants against refined types | 100,000 evaluated condition nodes | Error `E2019`; the program does not run |
| Errors reported per stage and file | 100 | The analysis stops; the summary says so |
| Range of `Int` | 64-bit signed | Runtime error `E3002` |
| Smallest integer literal | `-9223372036854775807` | `-9223372036854775808` can only be obtained by computing it: `-9223372036854775807 - 1` |

There is no time or memory limit: a program can take long or use memory without the
interpreter stopping it. No program keeps repeating something forever: an endless
recursion stops with `E3004` and an endless loop, with `E4006` (its measure stops decreasing). But a
program that ends can take a long time: a branching recursion (`fib(40)`) or a loop
with a huge initial measure. It can be interrupted with Ctrl+C. `nex test` has no time limits
per example either. If Python runs out of memory while the program runs, the program
ends with the error `E3007`; but on Linux the system can kill the process first, without any
message ([decision 0009](decisions/0009-memoria-agotada.md)).

## Performance

The interpreter walks the syntax tree directly, without compiling. It is a reference
implementation, meant to be correct and easy to understand, not fast. Its speed **has not been
measured**, and no claim is made about it.

## Contracts and refined types

Stable since 0.3.0. Their limits, in detail, in [contracts](contracts.md#limitations) and in
[refined types](types.md#refined-types):

- Contracts are checked when running, on the calls that run. They are not proven.
- `nex check` does not claim that a contract holds.
- Of refined types, `nex check` only checks constants. A computed value is checked
  with `Percent(x)` when running, and `nex check` does not claim that it will meet the condition.
- The condition of a refined type cannot call functions of the program.
- There are no type aliases without a condition, and no way of checking a value without stopping the program if
  it fails (there is no `Result`).
- They cannot be turned off.

## Tools

- The only stable interface is the command line. The Python API (`nexora.tooling`) is
  **experimental**; the rest of the modules of `src/nexora/` are internal and may change without notice.
- There is no debugger. The language server and the formatter exist and the VS Code extension uses
  them, but the server does not resolve imports yet: in the editor, a file that uses `import` gets
  `E0001` ([LSP](lsp.md#limitations)).
- With syntax errors, `nex inspect`, `nex context` and `nex symbols` return a **partial**
  structure: the statements with errors are missing and so is, entirely, any function whose declaration has
  one; and only the syntax errors are reported. With lexical errors (an unclosed text, an
  invalid character) they return no structure. They never include comments.
- `nex context` and `nex symbols` describe the entry file; the names that come from a module appear in
  it as qualified.
- The suggestions of the diagnostics are text for people, not edits that can be applied
  automatically.
- The MCP server is tested automatically with the client of the official SDK. In a real
  assistant it has only been checked **once, by hand, in Claude Code**; in no other. It only analyzes: it does not run programs. It depends on version 2 of the Python MCP SDK. Its
  limits, in [MCP server](mcp.md#limitations).
- The specification is only available to the tools (`get_language_spec`) if NEXORA was
  installed from the source code; the *wheel* package does not include the documentation.
- NEXORA does not call any AI model, and **no model has been evaluated** with these tools.
  What there is are structured and deterministic data:
  [Automated tools and AI](ai-tooling.md).

## Security

A NEXORA program can compute, write text, read its arguments and the standard input, and
use the files that it declares with `uses` and that it is allowed with `--allow-read` or `--allow-write`.
It has no construct to use the network or run other programs, and the tests
check that the interpreter does not use `eval` or `exec`. Even so:

- **NEXORA is not a sandbox.** It runs inside a normal Python process,
  with the permissions of whoever launches it.
- **There are no time or memory limits** when using `nex`. A malicious program can make
  the process use resources.
- The [playground](playground.md) does run each program in a separate process with time,
  output and size limits, but **that is not a sandbox either**: the container isolation
  is configured and **has not been tested**. The CPU, file and process limits of the operating
  system exist on Linux and macOS, and have been checked on both; the memory limit of the
  operating system is only enforced on Linux: on macOS, the kernel accepts it and does not apply it. It is not
  deployed on any server.
- The MCP server does not run programs, but it runs with the permissions of whoever starts it.
- It has not been audited.

Do not run untrusted NEXORA programs in an environment where excessive use of
resources is a problem. The exact scope is in [`SECURITY.md`](../SECURITY.md).

## Platforms

Checked on Windows 11 with Python 3.12, and on Linux (Ubuntu 24.04 on WSL 2) with Python 3.11,
3.12 and 3.13; also run on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13 by the
[continuous integration](testing.md#continuous-integration). Other distributions and Linux without WSL have not
been tested; see [Installation](installation.md#what-has-been-checked).

## Project

- It is distributed under the MIT licence: without warranty of any kind.
- The repository is public: <https://github.com/xGlizyy/nexoralang>. There is no private contact
  channel, nor a release process beyond the one documented in
  [Installation](installation.md#publishing).
- The continuous integration runs on every change to `main`, on Linux, Windows and macOS, but there is
  no written rule of what is merged: every change is reviewed by hand.
- The examples of `ejemplos/*.nx` and the document `docs/fase-1-diseno.md`, at the root of the
  repository, describe an earlier and broader design. They use a syntax that the interpreter does **not**
  accept. The valid reference is the [specification](language-spec.md).
