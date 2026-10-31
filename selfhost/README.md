# Self-hosted NEXORA

The NEXORA implementation written in NEXORA, following
[decision 0025](../nexora/docs/decisions/0025-interprete-autoalojado.md). The Python interpreter
runs it for now; it is the bootstrap, not the goal.

| Part | File | State |
|------|------|-------|
| Lexer | [`lexer.nex`](lexer.nex) | Done. Same tokens and lexical errors as `lexer.py` on every program of the repository and on the cases in [`lexer_cases/`](lexer_cases/), with the gaps below |
| Parser | [`parser.nex`](parser.nex) | Done. Same tree and same syntax errors as `parser.py` on every program of the repository and on the cases in [`parser_cases/`](parser_cases/), including error recovery, the limit of 100 errors and the nesting and depth limits |
| Checker | [`checker.nex`](checker.nex) | In progress. Everything of a single file, warnings included: functions, variables, loops, `if`, operators, lists, records, refined types (with an evaluator of conditions written in NEXORA), enums, `Option` and `Result`, `match` and `if let`, contracts, examples, `uses` and the capabilities of the built-ins, the "did you mean" hints and the warnings `W2001` to `W2003`. Same typed tree, errors and warnings as `checker.py` on the programs it supports, and on projects of modules (`project.nex`, below) |
| Interpreter | [`interpreter.nex`](interpreter.nex) | In progress. An abstract machine with an explicit stack of continuations that runs the typed tree: expressions, statements, functions with their `needs` and `promises`, loops with their `keeps` and `shrinks`, records, enums, `Option`/`Result`, `match`, `if let`, refined checks, the pure built-ins, the `example` clauses of `nex test` and the host (arguments, input and files, with the three rules of what the program declares, the user allows and the environment permits). It stops with the same diagnostic as `nex run` on 41 programs that fail on purpose, reports each example as `nex test` does on 16, and gives the same result as `nex run` on 61 host cases, among them `E3003` and the four limits of resources. Same output as `nex run` on 14 repository programs and on 6 programs written for it. `--max-text`, `--max-output`, `--max-input`, `--max-source` and `E3003` are done, and so are projects of modules; `--timeout` and `--max-memory` belong to the process, not to the program (see below) |

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
| Speed | About 2,500 steps per second, running on the Python interpreter. `fib(15)` is 50,318 steps and a loop of 3,000 turns 105,271. It is for checking the language, not for running programs: stage 4 of decision 0025 is about that. |

For the examples:

```bash
PYTHONPATH=nexora/src python selfhost/compare_examples.py FILE.nex [FILE.nex ...]
```

Both interpreters evaluate the `example` clauses of each program and, for each example, its status, the own calls that were
and were not evaluated (with their type, value and the reason), the diagnostic and what it printed are compared.
`interpreter_cases/examples/` holds programs written for it.

For the host:

```bash
PYTHONPATH=nexora/src python selfhost/compare_host.py
```

Each case in `compare_host.py` is a program with the options a user would give (`--allow-read`, `--allow-write`,
`--allow-network`, `--allow-process`), an input, arguments and limits, run by `nex run` and by
`interpreter.nex --run [options] FILE [arguments]`. The options are the grants, `--stdin FILE` (the input, read from a file
because the end of the real input cannot be told without stopping) and `--cwd DIRECTORY` (to resolve relative paths).

The limits of resources that the program can see are read as options: `--max-text CHARS` (`E3006`: a Text made by a
literal, `+`, `to_text`, `args`, `input` or `read_file` that is too long) and `--max-output BYTES` (`E3015`, after printing
what fits). `E3003` (a Float operation that does not fit) needs no option. The result of the operation is never
computed to find out, because on this interpreter an overflow would stop the interpreter itself: each operand is brought
to a scale where the rounding of the real operation can be decided (powers of two are exact), and the tests agree with
`nex run` at the edge of the range (`float_add_edge_tie` and `float_add_edge_below`).

The host has limits that come from the language and are not fixed here:

| Limit | Why |
|---|---|
| `Net.get` and `Process.run` are decided but not run | A capability is declared with a literal (`uses network "https://example.com"`), so this interpreter cannot declare what it does not know in advance. When every rule allows the operation it stops with `E0000`. |
| A file that does not exist ends this interpreter | There is no way to try to read a file and get a value back when it fails. `nex run` gives the program `E3010`. |
| The end of the input needs `--stdin` | `input()` cannot be asked whether there is a line left; at the end it stops the program that calls it. |
| `--max-output` with a character that is not ASCII | A Text has no code point, so the bytes of such a character cannot be counted. The run stops with `E0000` when it prints one under the limit. |
| `--timeout` and `--max-memory` | The operating system measures them on the process (a timer, `RLIMIT_AS`), and a program cannot read a clock or ask for the memory in use. Run the interpreter itself with them: `nex run selfhost/interpreter.nex --timeout 5 --max-memory ...`. Its own bound is the fuel of the machine. |
| `--max-input` and `--max-source` with a file that is not ASCII, or that has CRLF | Bytes are counted from the text: exact for ASCII, and the text is read with its line breaks normalised, so a CRLF file counts as if it had LF. A file with a character that is not ASCII stops the run with `E0000`. |
| Symbolic links are not followed | Paths are resolved by their text, there is no `realpath`. A link that points outside what is allowed is not noticed. |

## The command: `nex.nex`

[`nex.nex`](nex.nex) is `nex check`, `nex run` and `nex test` written in NEXORA, on top of the files of this directory, with the
messages of `nex`: [`render.nex`](render.nex) draws a diagnostic as `diagnostics.py` does, and [`titles.nex`](titles.nex) holds the
title and category of each code (generated from the Python table by `make_titles.py`; run it again when a code is added).

```bash
nex run selfhost/nex.nex --allow-read . --allow-write . -- check selfhost/project_cases/private_function/main.nex
nex run selfhost/nex.nex --allow-read . --allow-write . -- run [--allow-read PATH ...] [--stdin FILE] FILE [ARGUMENTS]
nex run selfhost/nex.nex --allow-read . --allow-write . -- test FILE [--function NAME]
PYTHONPATH=nexora/src python selfhost/compare_nex.py check|run|test FILE [FILE ...]
```

`compare_nex.py` joins what `nex` writes to the standard output and the standard error and compares it with what `nex.nex` writes:
the same text on 41 projects and programs for `check`, on 46 for `run` and on 15 for `test`.

| Limit | Why |
|---|---|
| No exit status, no standard error | A program has neither. Everything goes to the standard output, in the order `nex` writes it, and the process ends with status 0. |
| The input of `run` comes from `--stdin FILE` | A program cannot read the standard input without stopping at its end. |
| The output limit stops in the middle of a line | `print` writes whole lines, so what fit of that line is printed with a line break. |
| A file with syntax errors | Only its lexical and syntax errors are shown, as for the file that runs. `nex check` also checks the partial tree of an imported module. |

## Stage 3: the fixed point

```bash
PYTHONPATH=nexora/src python selfhost/fixed_point.py selfhost/fixed_point_cases/small.nex --levels 0,1,2
```

The same program runs at three levels and what it prints is compared: level 0 is `nex run`; level 1 is `interpreter.nex` run by
Python; level 2 is `interpreter.nex` run by `interpreter.nex`, run by Python. Both programs of
[`fixed_point_cases/`](fixed_point_cases/) print the same at the three levels.

| Measurement | Result |
|---|---|
| The checker in NEXORA checks the whole source of the interpreter (5 modules, ~13,000 lines) | 7 min 32 s on Python; the same diagnostics and the same typed tree as `checker.py` (`compare_project.py selfhost/interpreter.nex`) |
| `print(1 + 2)`, level 1 / level 2 | 0.4 s of Python for `nex run`; level 2 takes 17 min 51 s (level 1 takes 55,794 steps) |
| A record, a function and a list, level 2 | 24 min 16 s; the program takes 55 steps at level 2, which are 231,860 steps at level 1 |
| `fib(16)`, level 0 / level 1 | 0.4 s / 41 s, 81,428 steps: about 2,000 steps a second |

What they say about stage 4:

- A level costs two to three orders of magnitude over the one below: about 100 to 800 times from Python to level 1, and
  about 4,400 steps of level 1 for each step of level 2.
- Almost all of the time of level 2 is not the program but the interpreter checking its own source (the 7 and a half minutes
  above, run again by level 1) before it can run anything.
- Level 3, the interpreter running itself running itself, would need level 2 to check 13,000 lines at that speed. It was not run:
  by these numbers it is years, not hours. Without a faster way to execute NEXORA that does not go through Python (stage 4, which
  decision 0025 leaves open), the fixed point stops at level 2.

## The code generator to C (decision 0026)

[`cgen.nex`](cgen.nex) reads and checks a program (and the modules it imports) with the rest of this directory and writes the C of
an executable that needs neither Python nor the interpreter. It compiles `Int`, `Float`, `Bool` and `Text`, lists, records, enums,
`Option` and `Result`, `match` and `if let`, functions with `needs` and `promises`, refined types, `if`, `while` and `for` with
`keeps` and `shrinks`, modules, `args`, `input`, `read_file` and `write_file`, and the built-in functions of `Text`, `Int`, `Float`,
`List`, `Option` and `Result`. The executables take the options of `nex run` (`--allow-read`, `--allow-write`, `--max-text`,
`--max-output`, `--max-input`; `--max-source` has no meaning for them, they read no source). `Net.get` and `Process.run` decide as the
Python host does (URL, what the program declares, what the user allowed) and, when everything allows the operation, stop with a
diagnostic that says a compiled program cannot make it yet.

```bash
nex run selfhost/cgen.nex --allow-read . --allow-write . -- PROGRAM.nex OUTPUT.c
cc -std=c11 OUTPUT.c -o program
./program [--allow-read PATH ...] [--allow-write PATH ...] [-- ARGUMENTS]
```

The runtime of the generated programs is one header, [`runtime/nexora_rt.h`](runtime/nexora_rt.h): values as one tagged type, checked
`Int` arithmetic, `Text` as code points, the stack of calls and loops that explains an error, the text of a diagnostic as `nex` writes
it, the host with the three rules of decision 0015, and a conservative garbage collector (the stack is searched for words that point
into a block of memory; text bytes are not searched). `runtime_text.nex` is that header as data for the generator (`make_runtime.py`
writes it; run it again after changing the header). `NEXORA_GC_FLOOR=2000` makes the collector run constantly, which is how it is
tested.

```bash
NEXORA_CC="cc" PYTHONPATH=nexora/src python selfhost/compare_cgen.py selfhost/cgen_cases/*.nex
NEXORA_CC="cc" PYTHONPATH=nexora/src python selfhost/compare_cgen.py --host
```

`compare_cgen.py` compiles each program, runs it and `nex run`, and compares the standard output, the standard error and the exit
status: the 46 programs of [`cgen_cases/`](cgen_cases/) (each runtime error, a broken `needs`, `promises`, `keeps`, `shrinks` and
refined type, with the chain of calls and loops in the notes), all 16 examples of the repository, 13 projects of modules and 18 cases of the host are equal.

### The compiler compiles itself

[`bootstrap.py`](bootstrap.py) builds the compiler as an executable and checks the fixed point:

1. Python runs `cgen.nex` on its own source and writes C (generation 0, about 17 minutes).
2. A C compiler turns it into an executable, the first compiler (45 seconds).
3. That executable compiles `cgen.nex` and writes C (generation 1, no Python, about 6 minutes).
4. Generation 1 is the same text as generation 0, byte by byte (2,141,337 bytes). Then the C compiler builds the second compiler from
   it, and that one writes the same C again (generation 2: `bootstrap.py --seed` runs all of it from a C file).

[`seed/cgen.c`](seed/cgen.c) is the C of generation 1, kept so that a machine with a C compiler and nothing else can rebuild the
compiler: `NEXORA_CC=cc python selfhost/bootstrap.py --seed selfhost/seed/cgen.c` (Python only drives the steps; it runs no NEXORA).
It has to be replaced when `cgen.nex` or the runtime change: `bootstrap.py` says when the seed is older than the source, and
generation 1 is the new seed. The same
generator compiles `nex.nex`, and that executable is `nex check`, `nex run` and `nex test`: it writes the same text as `nex` on
43 programs for `check`, 46 for `run` and 15 for `test` (`NEXORA_NEX=path compare_nex.py ...`), and it checks a program in 0.08 s
where the Python implementation takes seconds. Compiled by the first compiler, 76 programs of the batteries above give the same
result as `nex run` in 73 seconds.

| Limit | Why |
|---|---|
| The very first compiler needs Python once | Generation 0 was written by the interpreter; the seed keeps its result. |
| `Net.get`, `Process.run` do not run | They need a TLS library and a process supervisor; the permission decisions are the same as `nex run`'s. |
| The collector is conservative | A word that looks like a pointer keeps a block alive; it never frees what is in use, but it may keep what is not. |
| The compiler needs a large stack for deep recursion | A NEXORA program can nest 1,000 calls; the default stack of the system is enough for the programs tested. |

## Projects of modules

[`project.nex`](project.nex) follows `modules.py` (decision 0018): it reads the program that runs and, before it, the files it
imports (each one once, relative to the file that has the import), orders them so that the imports of a module come first,
reports the cycles (`E2029`) and the two files with one name (`E2030`) on the import that causes them, and checks the modules
one after the other. `checker.nex` checks a module by itself, with its own names bare, and gives the next ones its `Export`: the
same tables with every name qualified by the module, and the names that module did not mark with `pub` listed apart (`E2028`).
Then `link` makes one program of the modules: each node that names something of its own module gets a `target` and each
declaration a `key`, with the name qualified, which is what the analysis of `checker.py` records, and the interpreter resolves
calls, records and refined types by it.

```bash
PYTHONPATH=nexora/src python selfhost/compare_project.py selfhost/project_cases/*/main.nex   # checker and loader
PYTHONPATH=nexora/src python selfhost/compare_interpreter.py selfhost/project_cases/run_*/main.nex   # run
```

`project_cases/` has one directory per case, with its `main.nex` and the modules it imports. 26 projects give the same modules,
diagnostics and typed tree as `modules.load`, 13 run with the same output and diagnostics as `nex run`, and `nex test` gives the
same result on the example of the repository that imports a module.

| Limit | Why |
|---|---|
| A file that cannot be read (`E0001`) is not reported | A missing file ends this interpreter, as for `read_file`. |
| A module that has lexical or syntax errors | The project is skipped, as a file by itself is. |
| A module that calls itself with its own name in front (`models.area` inside `models.nex`) | Its own names are bare while it is checked; `checker.py` accepts it. |

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

The stop condition of decision 0025, stage 1 is therefore **not** triggered: the bounded-recursion
option works.

## Language gaps found so far

Each one is a real limitation hit while writing the lexer. The decision 0025 rule applies: nothing
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
