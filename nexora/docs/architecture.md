# Architecture

How the NEXORA interpreter is built. It describes the code as it is today
(`src/nexora/`, about 1500 lines of Python without external dependencies).

## Flow

```text
        .nex file
             |
             |  cli.py reads the file as UTF-8
             v
   +-------------------+
   |  1. Lexer         |  lexer.py        text -> tokens             errors: lexical
   +-------------------+
             |  list of tokens
             v
   +-------------------+
   |  2. Parser        |  parser.py       tokens -> AST              errors: syntax
   +-------------------+
             |  AST (ast_nodes.py)
             v
   +-------------------+
   |  3. Checker       |  checker.py      names, scopes, types,      errors: semantic, type
   |                   |                  return paths
   +-------------------+
             |  CheckedProgram (AST + functions + types)
             |
             +----------------------> nex check    reports and ends
             +----------------------> nex inspect  writes the AST as JSON and ends
             +----------------------> nex context, nex symbols, MCP server
             |                        (tooling.py: summary and symbols, and ends)
             |
             v
   +-------------------+
   |  4. Interpreter   |  interpreter.py  walks the AST              errors: runtime, contract
   +-------------------+
             |
             v
        standard output
```

Rules of the flow:

- **Each stage only runs if the previous one found no errors.** That way the same error is not
  reported twice in different forms.
- **Stages 1 to 3 run nothing of the program.** `nex check`, `nex inspect`, `nex context`,
  `nex symbols` and the MCP server end there.
- **The interpreter only accepts a `CheckedProgram`**, which only the checker produces. A
  program cannot be run without being checked.
- `pipeline.analyze()` chains stages 1 to 3 and is what every command and every
  tool uses. That is why `check`, `inspect`, `context`, `symbols` and `run` see exactly the same
  program.

## Modules

| Module | Responsibility | Depends on |
|--------|----------------|------------|
| `version.py` | The version number. The only place where it is defined | — |
| `diagnostics.py` | `Span`, `Source`, `Diagnostic`, the registry of codes and categories, and the text format | — |
| `values.py` | Names of the types, limits of `Int` and how a value is written | — |
| `types.py` | Structured type model: primitives, `List[T]`, refined types, records and type variables; identity, compatibility, substitution and unification | — |
| `type_adapter.py` | Bridge between the type names of the checker and the model; it only resolves the enabled types | `types`, `values` |
| `tokens.py` | Token kinds, keywords and reserved words | `diagnostics` |
| `lexer.py` | Text → tokens | `tokens`, `diagnostics`, `values` |
| `ast_nodes.py` | The nodes of the tree and their conversion to JSON | `diagnostics` |
| `parser.py` | Tokens → AST, with error recovery | `ast_nodes`, `tokens`, `diagnostics` |
| `checker.py` | Static analysis. **The only place that decides which type rule applies to each expression**; the model of `types.py` defines identity and compatibility | `ast_nodes`, `diagnostics`, `values`, `types`, `type_adapter` |
| `interpreter.py` | Execution, contracts and runtime errors | `ast_nodes`, `checker`, `diagnostics`, `prelude`, `values`, `capabilities` |
| `prelude.py` | The functions of a type (`Text.length`, `Int.parse`, `List.get`…): their contracts, written in NEXORA, their implementations and the grammar of numbers written in a text | `ast_nodes`, `diagnostics`, `lexer`, `parser`, `values` |
| `capabilities.py` | The permission model: what a program declares, what whoever runs it grants and the comparison of two paths. **It does not touch the operating system** | — |
| `host.py` | What a program can do besides computing: its arguments, its input and the files it can use, with the check of the three permissions. **The only module that opens files** | `capabilities` |
| `pipeline.py` | Chains lexer, parser and checker | All three |
| `api.py` | Checking or running code in memory, with optional limits. The interface for whoever integrates NEXORA into another program | `pipeline`, `interpreter`, `checker`, `tokens`, `diagnostics` |
| `worker.py` | Single-use process that handles a JSON request; used by the [playground](playground.md) | `api` |
| `tooling.py` | The analysis tools: JSON documents of diagnostics, tree, symbols, context, specification and capabilities. **It never runs a program**: from the interpreter it only takes the constant of the call limit | `pipeline`, `checker`, `parser`, `ast_nodes`, `tokens`, `values`, `diagnostics` |
| `schemas.py` | The JSON Schemas of all the formats; the tree part is derived from the classes of `ast_nodes` | `ast_nodes`, `diagnostics` |
| `mcp_server.py` | **Optional** MCP server. The only module that imports the MCP SDK; it validates the arguments and delegates to `tooling` | `tooling` |
| `cli.py` | Arguments, reading the file, output formats, exit codes, and the permissions granted to the program | `pipeline`, `interpreter`, `tooling`, `diagnostics`, `capabilities`, `host` |
| `__main__.py` | Allows `python -m nexora` | `cli` |

Only the entry points touch the operating system: `cli.py` reads the file and writes to the
terminal, `worker.py` reads a request from its standard input, `mcp_server.py` talks over the standard input
and output, and `tooling.py` reads a single fixed file (the specification of the project), without
any argument influencing the path. The lexer, the
parser, the checker and the interpreter work with text and structures in memory; the interpreter
receives a `write` function for the output, which allows testing it without a terminal. A test
(`tests/test_security.py`) checks that those modules do not import `os`, `pathlib` or `subprocess`.

The only exception is `host.py`: it is the module that gives a program its arguments, its input
and the files it can use, and that is why it is the only one that opens files. The interpreter does not import it:
it receives a *host* and asks it ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)).
The permission model, in `capabilities.py`, does not touch the operating system: it only compares paths.

## The pieces, one by one

### Lexer

It goes through the text character by character and produces tokens with their position (`Span`: line and column of
start and of end).

- **It ignores nothing silently**: every character is part of a token, a space, a comment, or an
  error.
- **Line endings**: it emits a `NEWLINE` token, which is what ends a statement. Inside
  parentheses it does not emit it, so that an expression can span several lines.
- **Recovery**: if a `)` is missing and a word appears that cannot be inside parentheses
  (`let`, `fn`, `if`, a brace…), it closes the line where it was left open, so that the parser
  reports the error on the right line and can continue.
- After an error it continues, to report several in one pass (up to 100).

### Parser

Recursive descent for declarations and statements; *precedence climbing* for expressions (a
single function, `_expression`, with the `_PRECEDENCE` table).

- **Error recovery**: a wrong statement raises `ParseError`, which is caught at the
  block level; the parser skips to the end of the line and continues. At the file level, it skips to
  the next `fn`.
- **Limits**: it counts the nesting (`MAX_NESTING`, 64) and the depth of each expression
  (`MAX_EXPRESSION_DEPTH`, 256). They exist so that no accepted program can exhaust the Python
  stack in the following stages, which walk the tree recursively.
- It recognizes invalid constructs (an assignment `x = 1`, a misplaced contract
  clause) to be able to reject them with a precise message.

### AST

Immutable data classes (`@dataclass(frozen=True)`), one per construct of the language. Every
node carries its `span`.

**The names of the fields of these classes are the names of the fields of the JSON of
`nex inspect`** (`to_dict` walks them by reflection). Renaming a field changes the public
schema. The tests of `tests/test_inspect.py` pin the exact list.

### Checker

It walks the AST once and verifies names, scopes, types and return paths.

- **Two passes over the functions**: first it collects all the signatures, then it checks the
  bodies. That is why a function can call another one declared further down.
- **Scopes**: a chain of `_Scope` objects, one per block.
- **Types**: `_expression` returns the type of each expression as text (`"Int"`, `"Text"`…) or
  `None` if the expression has an error. `None` silences the derived errors: an unknown
  name is reported once, not in every operation that uses it.
- **Return paths**: `_block` and `_statement` return `True` if they always end with `return`.
- The computed types are stored in a dictionary (`id(node)` → type) that `nex inspect` uses.
- The built-in functions are described in the `BUILTINS` table, with the same form (`Signature`)
  as the functions of the program.

### Interpreter

It walks the AST of an already checked program. It neither generates nor evaluates Python code.

- **Values**: a NEXORA value is a Python `int`, `float`, `bool` or `str`.
- **Environments**: a chain of `Environment` objects, one per block. Every call starts a
  new environment, without access to that of its caller.
- **`return`**: statements return a `_Returned` object that goes up through the blocks to the
  call. Exceptions are not used for the normal flow.
- **What it checks**: only what cannot be known before: division by zero, range of `Int` and of
  `Float`, call depth and contracts. It does not repeat the name or type checks.
- **Call stack**: `_stack` keeps the function and the call point, to add the chain of
  calls to the diagnostics.
- **Recursion limit**: `MAX_CALL_DEPTH` (1000). It also temporarily raises the Python recursion
  limit and catches `RecursionError`, which it turns into the diagnostic `E3004`, and
  `MemoryError`, which it turns into `E3007` outside the `except` block (decision 0009).

## How errors are represented

There are three kinds of failure, and they are kept separate:

| Kind | What it is | How it is represented | What whoever uses `nex` sees |
|------|------------|-----------------------|------------------------------|
| Error of the program, detected without running | Lexical, syntax, semantic or type | `Diagnostic` objects returned in a list | Diagnostics; exit code `1` |
| Error of the program, when running | Division by zero, broken contract… | `NexoraRuntimeError` exception with a `Diagnostic` | Diagnostic; code `3` or `5` |
| Defect of NEXORA | Any other Python exception | It is not caught in the stages | `internal error: …`; code `70` |

A `Diagnostic` is data: code, explanation, position, suggestion and notes. The title and the
category come from the `_REGISTRY` of `diagnostics.py`, from the code. `render`
turns it into text and `to_dict` into JSON; both formats come from the same object.

`cli.main` catches any unexpected exception and presents it as an internal error. With
`NEXORA_DEBUG=1` it lets it through, to see the traceback.

The "impossible" branches of the interpreter (`raise TypeError`, `raise LookupError`) are not errors of the
user: if they are reached, the checker has let something through that it should not have, and it is an internal error.

## Where to add things

| To add… | Touch |
|---------|-------|
| A keyword or a symbol | `tokens.py` (and `lexer.py` if it is a new symbol) |
| A statement | Node in `ast_nodes.py` → `_statement` in `parser.py` → `_statement` in `checker.py` (types and whether it "always returns") → `_statement` in `interpreter.py` |
| An operator | `tokens.py`, `lexer.py`, the `_PRECEDENCE` table of `parser.py`, `binary_result` in `checker.py` and `_binary` in `interpreter.py` |
| A type | `values.py` (name and format), `types.py` and `type_adapter.py` if it has structure, `KNOWN_TYPES` and the rules in `checker.py`, and its representation in `interpreter.py` |
| A built-in function | The `BUILTINS` table of `checker.py` and `_call` in `interpreter.py`. If it belongs to a type (`Text.length`), its name carries the type in front in `BUILTINS`, and its implementation and its contracts go in `prelude.py` |
| An error | An entry in `_REGISTRY` (`diagnostics.py`) and a row in the tables of `language-spec.md` and `diagnostics.md` |
| An option or a command | `_build_parser` in `cli.py` and `cli-reference.md` |

In every case: the specification first, an example in `examples/` if it is a new
feature, and tests. [`CONTRIBUTING.md`](../CONTRIBUTING.md) details the process, and the tests fail
if any of the lists above gets out of sync.

## Decisions that shape the architecture

- **An interpreter that walks the tree.** It is the simplest way to have a correct and
  checkable semantics. It is not fast, and it limits the recursion depth. Its performance has not been measured.
- **The canonical type is a text; the semantics lives in a structured model.** The text is still
  the stable form of the specification, of the AST and of the JSON documents. To reason
  about identity, compatibility, unification and compound types, the checker builds objects
  of `types.py` through `type_adapter.py`. The migration is incremental: the rules that do not yet
  use the model keep their string representation. `List[T]` is the first compound type that
  uses this path, and records use it with an identity of their own: that of their declaration, which the
  checker creates and the interpreter inherits from the `CheckedProgram` ([decision 0014](decisions/0014-registros-nominales-inmutables.md)). The rest of proposal 0012 is not implemented.
- **The static analysis is mandatory.** It allows the interpreter to be small and the list of
  runtime errors to be short and closed.
- **The AST is the public interface of `nex inspect`.** It couples the JSON schema to the internal classes;
  in exchange there are no two representations to keep equal.

The reasons for each one are in [`decisions/`](decisions/README.md).
