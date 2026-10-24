# Structured context: `nex context` and `nex symbols`

Two tools for understanding a NEXORA program without reading it all or running it. They are intended
for someone who arrives at a new file and, above all, for an AI agent that will modify it: instead of
sending the entire code to a model and hoping it infers the structure, a summary calculated by the
language itself is provided.

Both share three properties, verified by tests (`tests/test_tooling.py`):

- **They do not run the program.** They use lexical, syntactic, and static analysis only.
- **No model is involved.** The same file always produces the same result.
- **They assume nothing.** Anything the analysis could not establish appears as `null` or is omitted.

## `nex context`

```bash
nex context program.nex
nex context program.nex --format json
```

For this program:

<!-- nex:context -->
```nex
fn unit_price(total_cents: Int, units: Int) gives Int
    needs units > 0
    promises result >= 0
{
    return total_cents / units
}

fn report(total_cents: Int, units: Int) {
    let price = unit_price(total_cents, units)
    print("Price: " + to_text(price))
}

fn main() {
    report(1200, 3)
}
```

`nex context program.nex` writes:

```text
program.nex | NEXORA 0.11.0 | 15 lines
Static analysis: no errors.
The program was not run to produce this summary.
Entry point: main

Functions (3):
  fn unit_price(total_cents: Int, units: Int) gives Int    [line 1]
      needs units > 0
      promises result >= 0
      called by: report
  fn report(total_cents: Int, units: Int)    [line 8]
      variables: price: Int
      calls: unit_price
      built-ins: print, to_text
      called by: main
  fn main()    [line 13]
      calls: report

Features used: arithmetic, comparisons, contracts, conversions, text_concatenation, user_functions

Notes:
  - Contracts ('needs', 'promises') are checked while the program runs, on the calls that execute; a 'trust' is never checked. This analysis verified their types, not that they hold.
  - Int / Int produces an Int: the fractional part is dropped. Division by zero is a runtime error (E3001) that static analysis does not detect.
```

### What it contains and how it is computed

| Data | Where it comes from |
|------|----------------------|
| Functions, parameters, return types | The syntax tree |
| Contracts, with their condition exactly as written | The file text, sliced by node position |
| Variables in each function, their type, and whether they can change (`mutable`, `true` for `var`) | The symbols recorded by the checker. If the variable has no annotation, it is the type inferred by the checker |
| `loops`: the loops in each function (`while` and `for`), with their condition or iterable, invariants, and measure exactly as written | The syntax tree and the file text. `kind` is `while` or `for`; for a `for`, `condition` is `x in xs`. `measure` is `null` for every `for` and when missing in a `while` (`E2021`) |
| `calls`, `called_by` | Calls the checker resolved. No text is searched: a call counts when the checker associated it with a function |
| `builtins_called` | Built-in functions called by each function, using their fully qualified names (`print`, `Text.length`). In the text output, the `needs` of each one appear underneath, with their explanation |
| `recursive` | Whether the function can reach itself again through those calls, directly or indirectly |
| `features` | Which constructs appear in the tree (see the next table) |
| `reserved_words_used` | Reserved words for unimplemented features that appear in the text |
| `diagnostics` | The same diagnostics as `nex check` |
| `notes` | Language rules that affect this specific program (see below) |

Features that `features` may list:

| Value | Appears when the program… |
|-------|---------------------------|
| `user_functions` | declares any function besides `main` |
| `conditionals` | uses `if` |
| `contracts` | has any `needs`, `promises` or `trust` clause |
| `recursion` | has any recursive function |
| `type_annotations` | annotates the type of any variable |
| `arithmetic` | uses `+ - * /` on numbers |
| `text_concatenation` | concatenates text with `+` |
| `comparisons` | uses `== != < <= > >=` |
| `logic` | uses `and`, `or`, or `not` |
| `conversions` | calls `to_text`, `to_float`, or `to_int` |
| `nested_blocks` | has a loose `{ }` block inside another |
| `refined_types` | declares any refined type |
| `examples` | has any `example` clause |
| `mutable_variables` | declares any variable with `var` |
| `loops` | uses `while` or `for` |
| `loop_invariants` | a loop declares a `keeps` |
| `text_operations` | calls a method on a type (`Text.length`, `Int.parse`…) or compares texts with `< <= > >=` |

The **notes** are not opinions about the code. Each one is a language rule that is added only if the
program contains the thing it refers to: that contracts are checked at runtime and have not been
proved, that each `while` checks its measure and loops check their invariants on every iteration if
there are loops, the limit on nested calls if there is recursion, that `Int / Int` drops the fractional
part if there is integer division, or which reserved words were used.

### JSON format

Schema `nexora.context/2`, described in
[`schemas/nexora-context.schema.json`](schemas/nexora-context.schema.json). For a minimal program:

<!-- nex:context-json -->
```nex
fn double(n: Int) gives Int {
    return n * 2
}

fn main() {
    print(double(21))
}
```

```json
{
  "schema": "nexora.context/2",
  "nexora_version": "0.11.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "executed": false,
  "lines": 7,
  "reserved_words_used": [],
  "analysed": true,
  "complete": true,
  "entry_point": "main",
  "types": [],
  "records": [],
  "capabilities": [],
  "functions": [
    {
      "name": "double",
      "signature": "fn double(n: Int) gives Int",
      "params": [
        {
          "name": "n",
          "type": "Int"
        }
      ],
      "return_type": "Int",
      "span": {
        "line": 1,
        "column": 1,
        "end_line": 3,
        "end_column": 2
      },
      "contracts": [],
      "variables": [],
      "calls": [],
      "builtins_called": [],
      "called_by": [
        "main"
      ],
      "recursive": false,
      "examples": [],
      "loops": [],
      "file": "program.nex"
    },
    {
      "name": "main",
      "signature": "fn main()",
      "params": [],
      "return_type": "Void",
      "span": {
        "line": 5,
        "column": 1,
        "end_line": 7,
        "end_column": 2
      },
      "contracts": [],
      "variables": [],
      "calls": [
        "double"
      ],
      "builtins_called": [
        "print"
      ],
      "called_by": [],
      "recursive": false,
      "examples": [],
      "loops": [],
      "file": "program.nex"
    }
  ],
  "features": [
    "arithmetic",
    "user_functions"
  ],
  "notes": []
}
```

| Field | Meaning |
|-------|---------|
| `schema`, `nexora_version`, `file`, `ok`, `diagnostics` | Common header for all documents ([JSON protocol](json-protocol.md)) |
| `executed` | Always `false`: the program is not run to produce the summary |
| `lines` | Number of lines in the file |
| `analysed` | `false` if there are lexical errors (or the file could not be read): then there is no structure to describe |
| `complete` | `true` if the summary covers the entire file. `false` if there are syntax errors: the summary is **partial** |
| `entry_point` | `"main"`, or `null` if the program does not declare one |
| `functions` | The functions, in file order. `null` if `analysed` is `false` |
| `features` | Used features, in alphabetical order. `null` if `analysed` is `false` |
| `reserved_words_used` | `null` if the text could not even be split into tokens |
| `notes` | Language rules relevant to this program |

### When the program has errors

- **Semantic or type errors:** the summary includes the structure and the diagnostics. A misspelled type appears as `null`; it is not invented.
- **Syntax errors:** the summary is **partial** and `complete` is `false`. It describes only the code that could be analyzed. Statements with errors and functions whose declaration (the `fn …` line) has an error are missing; a block left unclosed at the end of the file is kept with what was written. Anything depending on a missing piece is unknown; for example, the type of a variable computed from another whose declaration has an error appears as `null`.
- With a partial summary, **diagnostics are only syntax diagnostics**. Name and type errors are not reported until the syntax is correct, because describing gaps over a tree with holes would describe the gaps rather than the program.
- **Lexical errors** (an unterminated string, an invalid character): there is no tree. `analysed` is `false`, `functions` and `features` are `null`, and the summary is reduced to the diagnostics.

For example, a program that uses features that do not yet exist. The two erroneous statements are not part of the summary:

<!-- nex:context -->
```nex
fn main() {
    let items = 3
    break
    let first = match
}
```

```text
program.nex | NEXORA 0.11.0 | 5 lines
Static analysis: 2 errors.
The program was not run to produce this summary.
Partial summary: only the code that could be parsed is described.
Entry point: main

Functions (1):
  fn main()    [line 1]
      variables: items: Int

Features used: none

Diagnostics:
  syntax E1103 at 3:5: 'break' is reserved for a future version of NEXORA and is not implemented yet
  syntax E1103 at 4:17: 'match' is reserved for a future version of NEXORA and cannot be used here

Notes:
  - The program uses words reserved for features that are not implemented: break, match.
  - The program has syntax errors, so this summary is partial: it covers only the code that could be parsed. Statements with errors, and functions whose declaration has errors, are missing, and a type that depends on them is unknown.
```

### Limits

- **Modules are included.** When the program uses `import`, the summary also describes the functions of the imported modules, each with the `file` that declares it ([decision 0018](decisions/0018-modulos-e-importaciones.md)).
- **It does not say what the program does.** It describes its structure. To know what it prints, you must run it (`nex run`).
- **It cannot see what depends on values.** That `ok` is `true` does not mean the program will not divide by zero or violate a contract.
- **With syntax errors the summary is partial**, and a function whose declaration has an error disappears entirely. With lexical errors there is no structure.
- **Comments are not included.**
- Notes and messages are in English.

## `nex symbols`

Lists the functions, parameters, and variables declared by a program, and **where each one is used**.

```bash
nex symbols program.nex
nex symbols program.nex --name units
nex symbols program.nex --function unit_price --format json
```

| Option | Effect |
|--------|--------|
| `--name NAME` | Only symbols with that name |
| `--function FUNCTION` | Only that function and what is declared inside it |
| `--format json` | The `nexora.symbols/2` document instead of plain text |

On the first program on this page, `nex symbols program.nex --format json` returns (shown with a shorter program for brevity):

<!-- nex:symbols-json -->
```nex
fn main() {
    let total = 2 + 3
    print(total)
}
```

```json
{
  "schema": "nexora.symbols/2",
  "nexora_version": "0.11.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "complete": true,
  "filter": {
    "name": null,
    "function": null
  },
  "symbols": [
    {
      "name": "main",
      "category": "function",
      "type": "Void",
      "function": null,
      "declaration": {
        "line": 1,
        "column": 4,
        "end_line": 1,
        "end_column": 8
      },
      "scope": null,
      "references": [],
      "mutable": false,
      "assignments": [],
      "signature": "fn main()",
      "params": [],
      "return_type": "Void",
      "file": "program.nex"
    },
    {
      "name": "total",
      "category": "variable",
      "type": "Int",
      "function": "main",
      "declaration": {
        "line": 2,
        "column": 9,
        "end_line": 2,
        "end_column": 14
      },
      "scope": {
        "line": 1,
        "column": 11,
        "end_line": 4,
        "end_column": 2
      },
      "references": [
        {
          "line": 3,
          "column": 11,
          "end_line": 3,
          "end_column": 16
        }
      ],
      "mutable": false,
      "assignments": [],
      "file": "program.nex"
    }
  ],
  "builtins": [
    {
      "name": "Err",
      "signature": "fn Err(error: E) gives Result[T, E]",
      "params": [
        {
          "name": "error",
          "type": "E"
        }
      ],
      "return_type": "Result[T, E]",
      "contracts": []
    },
    {
      "name": "Float.can_parse",
      "signature": "fn Float.can_parse(text: Text) gives Bool",
      "params": [
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Float.parse",
      "signature": "fn Float.parse(text: Text) gives Float",
      "params": [
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Float",
      "contracts": [
        {
          "clause": "needs",
          "condition": "Float.can_parse(text)",
          "message": "Only a decimal number that fits in a Float can be read as a Float",
          "checked_at_run_time": true
        }
      ]
    },
    {
      "name": "Int.can_parse",
      "signature": "fn Int.can_parse(text: Text) gives Bool",
      "params": [
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Int.parse",
      "signature": "fn Int.parse(text: Text) gives Int",
      "params": [
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Int",
      "contracts": [
        {
          "clause": "needs",
          "condition": "Int.can_parse(text)",
          "message": "Only a whole number within the range of Int can be read as an Int",
          "checked_at_run_time": true
        }
      ]
    },
    {
      "name": "List.append",
      "signature": "fn List.append(xs: List[T], x: T) gives List[T]",
      "params": [
        {
          "name": "xs",
          "type": "List[T]"
        },
        {
          "name": "x",
          "type": "T"
        }
      ],
      "return_type": "List[T]",
      "contracts": []
    },
    {
      "name": "List.concat",
      "signature": "fn List.concat(xs: List[T], ys: List[T]) gives List[T]",
      "params": [
        {
          "name": "xs",
          "type": "List[T]"
        },
        {
          "name": "ys",
          "type": "List[T]"
        }
      ],
      "return_type": "List[T]",
      "contracts": []
    },
    {
      "name": "List.contains",
      "signature": "fn List.contains(xs: List[T], x: T) gives Bool",
      "params": [
        {
          "name": "xs",
          "type": "List[T]"
        },
        {
          "name": "x",
          "type": "T"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "List.get",
      "signature": "fn List.get(xs: List[T], i: Int) gives T",
      "params": [
        {
          "name": "xs",
          "type": "List[T]"
        },
        {
          "name": "i",
          "type": "Int"
        }
      ],
      "return_type": "T",
      "contracts": [
        {
          "clause": "needs",
          "condition": "0 <= i and i < List.length(xs)",
          "message": "An index must be inside the list",
          "checked_at_run_time": true
        }
      ]
    },
    {
      "name": "List.length",
      "signature": "fn List.length(xs: List[T]) gives Int",
      "params": [
        {
          "name": "xs",
          "type": "List[T]"
        }
      ],
      "return_type": "Int",
      "contracts": []
    },
    {
      "name": "Ok",
      "signature": "fn Ok(value: T) gives Result[T, E]",
      "params": [
        {
          "name": "value",
          "type": "T"
        }
      ],
      "return_type": "Result[T, E]",
      "contracts": []
    },
    {
      "name": "Option.is_none",
      "signature": "fn Option.is_none(value: Option[T]) gives Bool",
      "params": [
        {
          "name": "value",
          "type": "Option[T]"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Option.is_some",
      "signature": "fn Option.is_some(value: Option[T]) gives Bool",
      "params": [
        {
          "name": "value",
          "type": "Option[T]"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Option.value",
      "signature": "fn Option.value(value: Option[T]) gives T",
      "params": [
        {
          "name": "value",
          "type": "Option[T]"
        }
      ],
      "return_type": "T",
      "contracts": []
    },
    {
      "name": "Option.value_or",
      "signature": "fn Option.value_or(value: Option[T], fallback: T) gives T",
      "params": [
        {
          "name": "value",
          "type": "Option[T]"
        },
        {
          "name": "fallback",
          "type": "T"
        }
      ],
      "return_type": "T",
      "contracts": []
    },
    {
      "name": "Result.error",
      "signature": "fn Result.error(value: Result[T, E]) gives E",
      "params": [
        {
          "name": "value",
          "type": "Result[T, E]"
        }
      ],
      "return_type": "E",
      "contracts": []
    },
    {
      "name": "Result.is_err",
      "signature": "fn Result.is_err(value: Result[T, E]) gives Bool",
      "params": [
        {
          "name": "value",
          "type": "Result[T, E]"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Result.is_ok",
      "signature": "fn Result.is_ok(value: Result[T, E]) gives Bool",
      "params": [
        {
          "name": "value",
          "type": "Result[T, E]"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Result.value",
      "signature": "fn Result.value(value: Result[T, E]) gives T",
      "params": [
        {
          "name": "value",
          "type": "Result[T, E]"
        }
      ],
      "return_type": "T",
      "contracts": []
    },
    {
      "name": "Result.value_or",
      "signature": "fn Result.value_or(value: Result[T, E], fallback: T) gives T",
      "params": [
        {
          "name": "value",
          "type": "Result[T, E]"
        },
        {
          "name": "fallback",
          "type": "T"
        }
      ],
      "return_type": "T",
      "contracts": []
    },
    {
      "name": "Some",
      "signature": "fn Some(value: T) gives Option[T]",
      "params": [
        {
          "name": "value",
          "type": "T"
        }
      ],
      "return_type": "Option[T]",
      "contracts": []
    },
    {
      "name": "Text.contains",
      "signature": "fn Text.contains(text: Text, part: Text) gives Bool",
      "params": [
        {
          "name": "text",
          "type": "Text"
        },
        {
          "name": "part",
          "type": "Text"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Text.ends_with",
      "signature": "fn Text.ends_with(text: Text, part: Text) gives Bool",
      "params": [
        {
          "name": "text",
          "type": "Text"
        },
        {
          "name": "part",
          "type": "Text"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "Text.length",
      "signature": "fn Text.length(text: Text) gives Int",
      "params": [
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Int",
      "contracts": [
        {
          "clause": "promises",
          "condition": "result >= 0",
          "message": "A text never has a negative number of characters",
          "checked_at_run_time": false
        }
      ]
    },
    {
      "name": "Text.slice",
      "signature": "fn Text.slice(text: Text, start: Int, end: Int) gives Text",
      "params": [
        {
          "name": "text",
          "type": "Text"
        },
        {
          "name": "start",
          "type": "Int"
        },
        {
          "name": "end",
          "type": "Int"
        }
      ],
      "return_type": "Text",
      "contracts": [
        {
          "clause": "needs",
          "condition": "start >= 0",
          "message": "A slice cannot start before the first character",
          "checked_at_run_time": true
        },
        {
          "clause": "needs",
          "condition": "start <= end",
          "message": "A slice cannot end before it starts",
          "checked_at_run_time": true
        },
        {
          "clause": "needs",
          "condition": "end <= Text.length(text)",
          "message": "A slice cannot end after the last character",
          "checked_at_run_time": true
        },
        {
          "clause": "promises",
          "condition": "Text.length(result) == end - start",
          "message": "The slice has exactly end - start characters",
          "checked_at_run_time": false
        }
      ]
    },
    {
      "name": "Text.starts_with",
      "signature": "fn Text.starts_with(text: Text, part: Text) gives Bool",
      "params": [
        {
          "name": "text",
          "type": "Text"
        },
        {
          "name": "part",
          "type": "Text"
        }
      ],
      "return_type": "Bool",
      "contracts": []
    },
    {
      "name": "args",
      "signature": "fn args() gives List[Text]",
      "params": [],
      "return_type": "List[Text]",
      "contracts": []
    },
    {
      "name": "input",
      "signature": "fn input() gives Text",
      "params": [],
      "return_type": "Text",
      "contracts": []
    },
    {
      "name": "print",
      "signature": "fn print(value: Int | Float | Bool | Text)",
      "params": [
        {
          "name": "value",
          "type": "Int | Float | Bool | Text"
        }
      ],
      "return_type": "Void",
      "contracts": []
    },
    {
      "name": "read_file",
      "signature": "fn read_file(path: Text) gives Text",
      "params": [
        {
          "name": "path",
          "type": "Text"
        }
      ],
      "return_type": "Text",
      "contracts": []
    },
    {
      "name": "to_float",
      "signature": "fn to_float(value: Int) gives Float",
      "params": [
        {
          "name": "value",
          "type": "Int"
        }
      ],
      "return_type": "Float",
      "contracts": []
    },
    {
      "name": "to_int",
      "signature": "fn to_int(value: Float) gives Int",
      "params": [
        {
          "name": "value",
          "type": "Float"
        }
      ],
      "return_type": "Int",
      "contracts": []
    },
    {
      "name": "to_text",
      "signature": "fn to_text(value: Int | Float | Bool | Text) gives Text",
      "params": [
        {
          "name": "value",
          "type": "Int | Float | Bool | Text"
        }
      ],
      "return_type": "Text",
      "contracts": []
    },
    {
      "name": "write_file",
      "signature": "fn write_file(path: Text, text: Text)",
      "params": [
        {
          "name": "path",
          "type": "Text"
        },
        {
          "name": "text",
          "type": "Text"
        }
      ],
      "return_type": "Void",
      "contracts": []
    }
  ]
}
```

Each symbol has:

| Field | Meaning |
|-------|---------|
| `name` | The name |
| `category` | `function`, `parameter`, or `variable` |
| `type` | Its type; for a function, its return type. `null` if it was misspelled in the code |
| `function` | The function where it is declared. `null` if the symbol is a function |
| `declaration` | The declaration position |
| `scope` | The block where it is visible. `null` in a function, which is visible throughout the file |
| `references` | Position of each use that the checker resolved to this symbol, including assignments |
| `mutable` | `true` only for a variable declared with `var` |
| `assignments` | Position of each assignment that gives it a new value. Empty for anything that is not a `var` |
| `signature`, `params`, `return_type` | Only for functions |

`builtins` lists separately the functions provided by the language (`print`, `to_text`…, and type methods, with their fully qualified names: `Text.length`, `Int.parse`…), which do not have a declaration in the file. Each one carries `contracts`: its `needs` and `promises`, with the condition written in NEXORA, its explanation, and `checked_at_run_time`, which is `true` for `needs` (checked at each call) and `false` for `promises` (the implementation guarantees them and tests verify them, but the program does not check them). `nexora.capabilities/1` lists the same contracts with the words it was published with, `requires` and `ensures`. A variable named `length` is just another symbol, unrelated to `Text.length` ([decision 0011](decisions/0011-operaciones-sobre-textos.md)).

How it is computed: the checker records each declaration as it processes it and, each time it resolves a name according to the language's scoping rules, it annotates that position on the corresponding symbol. That is why two variables with the same name in different blocks are two different symbols, each with its own references. **Nothing is inferred from the name** of a variable or a function.

Limits:

- No index and no search beyond the program and the modules it imports: a file that nothing imports is not seen.
- A name that could not be resolved (an `E2005` error) is not a reference to any symbol.
- With syntax errors, the list is partial (`complete` is `false`): it only includes declarations in the code that could be analyzed.
- `symbols` is `null` if there are lexical errors.

## From Python

```python
from nexora.tooling import get_context, get_symbols

context = get_context(source_text, "programa.nex")
symbols = get_symbols(source_text, "programa.nex", function="unit_price")
```

They return exactly the same documents as the commands. See
[Automatic tools and AI](ai-tooling.md#python-api).
