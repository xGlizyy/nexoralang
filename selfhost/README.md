# Self-hosted NEXORA

The NEXORA implementation written in NEXORA, following
[decision 0024](../nexora/docs/decisions/0024-interprete-autoalojado.md). The Python interpreter
runs it for now; it is the bootstrap, not the goal.

| Part | File | State |
|------|------|-------|
| Lexer | [`lexer.nex`](lexer.nex) | Done. Same tokens and lexical errors as `lexer.py` on every program of the repository and on the cases in [`lexer_cases/`](lexer_cases/), with the gaps below |
| Parser | [`parser.nex`](parser.nex) | Done. Same tree and same syntax errors as `parser.py` on every program of the repository and on the cases in [`parser_cases/`](parser_cases/), including error recovery, the limit of 100 errors and the nesting and depth limits |
| Checker | [`checker.nex`](checker.nex) | In progress. Everything of a single file, warnings included: functions, variables, loops, `if`, operators, lists, records, refined types (with an evaluator of conditions written in NEXORA), enums, `Option` and `Result`, `match` and `if let`, contracts, examples, `uses` and the capabilities of the built-ins, the "did you mean" hints and the warnings `W2001` to `W2003`. Same typed tree, errors and warnings as `checker.py` on the programs it supports; modules are next |
| Interpreter | [`interpreter.nex`](interpreter.nex) | In progress. An abstract machine with an explicit stack of continuations that runs the typed tree: expressions, statements, functions with their `needs` and `promises`, loops with their `keeps` and `shrinks`, records, enums, `Option`/`Result`, `match`, `if let`, refined checks and the pure built-ins. It stops with the same diagnostic as `nex run` (code, message, hint, notes with the chain of calls and loops, and position) on 41 programs that fail on purpose. Same output as `nex run` on 14 repository programs and on 6 programs written for it. The examples (`nex test`), the host functions (files, input, network, processes), the limits of resources and modules are next |

## Checking a part against the Python implementation

```bash
PYTHONPATH=nexora/src python selfhost/compare_lexer.py FILE.nex [FILE.nex ...]
```

Both lexers run on the same text, and tokens (kind, lexeme, span, decoded text literals) and
lexical errors (code, message, hint, span) are compared. A difference is a bug in the self-hosted
code unless it is listed under "Language gaps".

For the parser:

```bash
PYTHONPATH=nexora/src python selfhost/compare_parser.py selfhost/parser_cases/*.txt
```

Each line of a cases file is an expression; both parsers read it and the tree (as JSON) or the first
syntax error is compared. For whole programs, including the syntax errors a program can have:

```bash
PYTHONPATH=nexora/src python selfhost/compare_programs.py FILE.nex [FILE.nex ...]
```

`parser_cases/programs/` holds malformed programs that exercise recovery, headers, declarations, the
old 0.11 syntax and the size limits. A file with lexical errors is skipped: the lexer is checked on
its own.

For the checker:

```bash
PYTHONPATH=nexora/src python selfhost/compare_checker.py FILE.nex [FILE.nex ...]
```

Both checkers read the program and the typed tree (what `nex inspect` shows), the errors and the
warnings are compared. A program that uses something the NEXORA checker does not know yet is reported as
*unsupported* by it and skipped, and the summary says why.
`checker_cases/` holds programs with type errors that exercise each error path of this slice.

On Windows, give `PYTHONPATH` a single entry: its separator is `;`, and `nexora/src:selfhost` is read as
one path that does not exist, so Python finds another copy of `nexora`.

For the interpreter:

```bash
PYTHONPATH=nexora/src python selfhost/compare_interpreter.py FILE.nex [FILE.nex ...]
```

Each program is run by `nex run` and by the interpreter written in NEXORA, and what they print is compared, and, when the
program stops with a runtime error or a broken contract, the diagnostic: code, message, hint, notes and position.
`interpreter_cases/` holds programs written for it, and `interpreter_cases/failing/` one program for each way of failing.

What the first runs show:

| | |
|---|---|
| Call depth | A program that nests 997 calls runs and prints what `nex run` prints. The machine keeps what is left to do in a linked stack, so the depth of the program does not use the depth of the interpreter. A recursive evaluator would have stopped at about 250. |
| Speed | About 2,500 steps per second, running on the Python interpreter. `fib(15)` is 50,318 steps and a loop of 3,000 turns 105,271. It is for checking the language, not for running programs: stage 4 of decision 0024 is about that. |

## Stage 1 measurement: call depth

[`measure/depth.nex`](measure/depth.nex) builds and evaluates a nested expression with a recursive
`enum`, one NEXORA call per tree level.

| Nesting | Result |
|---------|--------|
| 499 | Works (about 0.3 s) |
| 500 | `E3004`, too many nested calls |

Each level costs two calls (`build` and `eval_expr`), so the limit of 1,000 calls is reached at
exactly 500. Plain recursion is cheap; the limit is the only obstacle.

What this means for the plan:

- **Parser and checker.** The language already bounds source nesting: the Python parser refuses
  more than 64 levels of parentheses, unary operators and blocks (`MAX_NESTING`) and expression
  trees deeper than 256 (`MAX_EXPRESSION_DEPTH`). Bounded recursion is therefore feasible for them,
  at a few calls per level, if the self-hosted parser enforces the same limits. The deepest tree in
  the repository's `.nex` files is 11 nodes.
- **Interpreter.** This is the real problem. An interpreted program may nest 1,000 calls, and each
  one costs several calls of a recursive evaluator, so a recursive evaluator tops out around 200 to
  250 interpreted calls. The evaluator has to keep its own stack of frames in a list, so that the
  depth of the interpreted program does not use the depth of the interpreter.

The stop condition of decision 0024, stage 1 is therefore **not** triggered: the bounded-recursion
option works.

## Language gaps found so far

Each one is a real limitation hit while writing the lexer. The decision 0024 rule applies: nothing
is added to the language except what the self-hosted code needs.

| Gap | Effect | Workaround used |
|-----|--------|-----------------|
| No `\r` escape and no character-from-code-point function | A carriage return cannot be written or recognised, so a CRLF file is not lexed like the Python lexer does | None. CRLF files differ |
| No code point of a character, no letter test | E1001 shows non-printable characters quoted instead of `U+XXXX`, and misses the "Names use the letters a-z" hint for non-ASCII letters | None. Only such characters differ |
| A line break continues an expression only inside `( )`, not inside `[ ]` | Long list literals do not fit on several lines | Wrap the list in parentheses |
| A field can only be read from a name, not from a call result | `List.get(tokens, i).kind` is rejected | Bind the call to a `let` first |
| `uses read` needs a literal path | Reading a file named by an argument needs `uses read "."` and `--allow-read .` | Declare the working directory |

Found while writing the parser, and fixed in the checker (not a language change): a record of an
imported module whose field type was another type of the same module was rejected with `E2012`
(`'Token' is not a type`), because the field types of every module's records were resolved with the
prefix of the module being checked. They are now resolved relative to the module that declares the
record (`tests/test_modules.py`). A genuine error inside an imported record is still reported
under the importing file's name, with the position of the imported one.

Differences the parser still has with `parser.py`, both from missing text functions: the explanation
of a clause counts as empty only if it is made of spaces, tabs and line breaks (Python's `strip()`
knows every Unicode space), and the lowercase check of a clause name is ASCII only, which is all a
name can be.

None of these blocks the lexer. The first two are the first candidates for stage 1 of the plan,
together with maps and `%`, which the lexer did not need.
