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

Compiled with `--trusted --cli` (`nex.nex OUTPUT.c --trusted --cli` to `cgen.nex`), the executable is used as the command is, with no
options of the runtime: `nex check FILE`, `nex run [OPTIONS] FILE [ARGUMENTS]`, `nex test FILE`, `nex --version`. Every argument belongs to
the tool, and the tool may read and write the files it is asked to; the program that `nex run` starts has its own host, with the
permissions given by `--allow-read` and the others, as in Python (`NEXORA_NEX_CLI=1` makes `compare_nex.py` call it that way). The output of the program is written while it runs (a C function,
`stream_text`, instead of collecting it and printing it at the end), so a prompt appears before `input()` waits and what a program
printed is not lost when `--timeout` stops it; the part of a line that fits in `--max-output` is written without a line break, as Python
does. `--timeout` and `--max-memory` exist on Linux (`--timeout` on any POSIX system), as in Python, and anywhere else they are the same
usage error with status 2; `--max-memory` stops the program with E3007, worded as this implementation words it. `nex inspect FILE` writes the `nexora.inspect/3` document: the syntax tree that the checker returns, with the type it gave each expression
(`report.nex`, `node_json`), byte for byte what Python writes on 29 programs, including files with syntax errors (the partial tree is
checked anyway, its errors dropped, as Python does) and a file that does not exist. `compare_limits.py`
(run on Linux, with an executable built with `zig cc -target x86_64-linux-musl -static`) compares 13 cases of the limits of `run`: all equal,
and `compare_nex.py` and `compare_stdin.py` are equal for that executable too.

`compare_nex.py` runs both and compares them. Run by Python, `nex.nex` has no standard error and no exit status, so what `nex` writes
to both streams is compared with its standard output. Against the executable (`NEXORA_NEX=path`), the standard output, the standard
error and the exit status are compared one by one, and `NEXORA_FORMAT=json` adds `--format json`: `check`, `run` and `test` are equal
on 29 programs and projects (texts), and `check` and `run` with `--format json` too, byte for byte, including a file that does not exist.

In the executable `nex.nex` does what `nex` does on the outside: the diagnostics and the summary of a failure go to the standard error,
the results to the standard output, and the process ends with the status of `nex` (0, 1 invalid program, 2 usage, 3 the program failed,
4 unreadable file, 5 a contract was broken, 6 a test did not pass; 70 for what this implementation cannot do yet; 130 for Ctrl+C in
`migrate --write`). It has every command of the Python `nex`:

| Command | Where it is | Checked against Python with |
|---|---|---|
| `check`, `run`, `test`, `--version`, `--format json`, `--timeout`, `--max-memory` | [`nex.nex`](nex.nex) | `compare_nex.py`, `compare_limits.py`, `compare_stdin.py` |
| `inspect` | the `nexora.inspect/3` tree, [`report.nex`](report.nex) | 29 programs, byte for byte |
| `context [--format text\|json]` | [`context.nex`](context.nex), `nexora.context/2`, also for a program of several modules | `compare_context.py`: 96 programs (examples, programs with errors, projects, a lexical error, a syntax error, a missing file), text and JSON |
| `symbols [--name N] [--function F]` | [`symbols.nex`](symbols.nex), `nexora.symbols/2`; the checker records every name, its type, its scope and every use while it checks (`Sym`, `SymRef` in [`checker.nex`](checker.nex)); the built-ins are generated from Python by [`make_builtins.py`](make_builtins.py) | `compare_symbols.py`: 96 programs, 570 runs with and without the filters |
| `test --format json` | [`testdoc.nex`](testdoc.nex), `nexora.test/1`; the machine already recorded the calls an example made | `compare_test.py`: 55 programs, 113 runs (also `--function` with a name that does not exist, with the suggestion of `difflib`) |
| `debug` | `debug_command` in [`nex.nex`](nex.nex) on the session of the debugger of the worker (`debug_start_hosted`, `debug_advance`); the commands come from the controlling terminal (`CONIN$` or `/dev/tty`) | `compare_debug_cli.py`: 21 programs, 294 scripted sessions |
| `migrate [--write]` | [`legacy.nex`](legacy.nex) (the front end of 0.11), [`migrate.nex`](migrate.nex) (the edits), `migrate_command` in [`nex.nex`](nex.nex) (the routes, the checks and the writing of the files, with C functions for the system) | `compare_migrate.py`: the 118 programs of the 0.11 corpus of decision 0019, as they are, with CRLF, with CR, with a byte-order mark, without and with `--write`, comparing the files afterwards |

The front end of 0.11 is not a second implementation. 0.11 and 0.12 share the lexer; they differ in the words (`requires`, `ensures`,
`invariant`, `decreases` become `needs`, `promises`, `keeps`, `shrinks`; `->` becomes `gives` and `-> Void` disappears), in where the
clauses go (inside the block in 0.11, in the header in 0.12) and in `Option.unwrap`/`unwrap_or`. `legacy.nex` turns the tokens of a file of
0.11 into the tokens of the 0.12 file that says the same, with the positions the words had, and the parser and the checker of 0.12 do the
rest; the messages of 0.12 are written back with the words of 0.11 (`old_wording`) when the command shows what 0.11 said. The plan of the
edits reads the tokens of 0.11 as the lexer made them (`legacy.plain`).

`debug` reads the commands from the file named by `NEXORA_DEBUG_CONSOLE` when that variable is set (that is how it is tested); without it,
from the terminal, so the program keeps the standard input for `input()`. `--timeout` counts the time the program runs, not the time at the
prompt. `symbols`, `context` and `migrate` check a program of several modules with the exports of the modules it imports and nothing
else (`visible_to` in [`project.nex`](project.nex)); an `import` of a file that does not exist or is not UTF-8 is E0001 or E0002 at the
import, as in Python.

Three functions make `err`, the status and the reasons possible, `err`, `exit_with` and `file_problem`: NEXORA has no way to write on the
standard error, to set a status or to ask why a file cannot be read, so the definitions in `nex.nex` (what Python runs) write to the
standard output and set nothing, and `cgen.nex` replaces them with C ones (so it does with the reading of the commands of the debugger, the
time limit while they are read, the exact reading of a file, and the operations of `migrate --write`: write beside the original, copy the
permissions, replace with one rename, remove, and note Ctrl+C).

| Limit | Why |
|---|---|
| Run by Python, no exit status and no standard error | A program has neither: the functions above only exist in the executable. |
| `debug` shows at most 64 frames of the call stack, and ends the list with `… (more frames)` | The snapshot of the debugger of the worker is capped; Python writes them all. |
| `context` and `symbols` cut the text of a condition of a module from the file of the program | Python does the same (it uses the source of the analysis, not the one of the module): the executable repeats it so the output is equal. |
| `migrate` orders the modules by the text of their path, not by the absolute path | NEXORA cannot ask for the absolute path. It is the same order when the modules are beside the program. |
| `migrate` on Windows with an entry written with `\` | The paths of the imports are resolved with `/`; write the path with `/`. |
| `migrate --write` does not inject failures | The hooks of Python (`Files`) are for its tests. Failures of the system, and Ctrl+C between two files, are reported with the three lists. |
| `run` reads the standard input one line at a time, and `--max-input` is not applied to it yet | `--stdin FILE` still works and keeps the limit. A program cannot test for the end of the input without stopping at it, so a C function (`read_stdin_line`) answers with no line at the end. `compare_stdin.py` runs 3 programs with 8 inputs (LF, CRLF, no final break, none, empty lines, Unicode): all equal (Python in UTF-8 mode: on Windows `nex` decodes the input with the code page of the console). |
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

### Speed

The native `nex` (`nex.nex` compiled by this generator) is as fast as the Python implementation on the programs of
[`bench/`](bench/): `bench.py` runs each one with both and shows the ratio (native time over Python time, so below 1 is faster):

| Program | Python | Native | Ratio |
|---|---|---|---|
| `fib(22)`, recursion | 0.77 s | 0.73 s | 0.96 |
| a loop of 150,000 turns | 1.91 s | 1.95 s | 1.02 |
| records and enums with `match` | 1.80 s | 1.53 s | 0.85 |
| building and adding up lists | 0.42 s | 0.14 s | 0.33 |
| text built and cut character by character | 0.71 s | 0.35 s | 0.49 |

Checking the 13,000 lines of the compiler itself takes 3.5 s (Python: 1.7 s), and the compiler compiles itself in 28 s. These
numbers came from five changes, each worth a large factor, and a profile (`-DRT_STATS`, which counts allocations, calls and each
function) found every one of them:

- Expressions that call no function of the program are worked out in one step by recursion instead of by the abstract machine.
- A list shares a growing buffer with the lists made from it by adding to the end, so adding copies nothing (a loop that built a
  list of n items was quadratic).
- `Text.slice` finds a code point without reading the text from its start: the lexer cut one character at a time and was quadratic
  in the size of the source (checking 6,000 lines took 17 s, it takes 0.3 s).
- Values are zeroed: an `rv` is 32 bytes and wrote 16, and the rest kept old addresses, which made the collector believe that chains
  of dead machines were alive.
- For the files of `selfhost/` only, the accessors of the syntax tree and the update of a variable are done in C (`--trusted` also
  leaves out the frames of calls, which only exist to explain the errors of a program). The NEXORA definitions are the reference:
  they are what Python runs, and the comparisons check that both agree.

### The compiler compiles itself

[`bootstrap.py`](bootstrap.py) builds the compiler as an executable and checks the fixed point:

1. Python runs `cgen.nex` on its own source and writes C (generation 0, about 17 minutes).
2. A C compiler turns it into an executable, the first compiler (about a minute).
3. That executable compiles `cgen.nex` and writes C (generation 1, no Python, 28 seconds).
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

## The worker of the playground (decision 0026)

[`worker.nex`](worker.nex) is the process that answers the requests of nexoralang.org, written in NEXORA and compiled by the
compiler above to one static executable. It has the protocol of `python -I -m nexora.worker` (`nexora/src/nexora/worker.py`): a
line of JSON on the standard input and one `nexora.result/1` on the standard output for `info`, `check` and `run`, and the
`nexora.debug/1` lines of a debug session (`step`, `continue`, `stop`, `set_breakpoints`), so the web server does not change.

- A request carries one program or a project of up to 32 files; [`project.nex`](project.nex) loads it from memory with the paths
  and the `E0001` of the Python worker. A run has no files, no network, no processes and no input, and the debugger has the host of
  `NoHost`; the messages are the same.
- The debugger needs nothing but the machine of [`interpreter.nex`](interpreter.nex): it is a value that moves one step at a
  time, so the session stops before the statement of a block that is next on its stack (`debug_start`, `debug_advance`).
- [`info.nex`](info.nex) (keywords, builtins, version) is generated from Python by [`make_info.py`](make_info.py); run it when the
  language changes. The runtime applies the limits of the Python worker to itself on POSIX (address space, CPU and wall clock
  seconds, no files, no processes) and answers `memory_limit` if memory runs out. Inside a container it also reads the memory
  limit of its cgroup and keeps its own address space 12.5% below it, so that a program that uses too much gets `memory_limit`
  instead of being killed by the kernel without a word (a 256 MB cgroup: `memory_limit` in 0.3 s, no OOM kill).
- [`compare_worker.py`](compare_worker.py) sends 121 requests to both workers and compares the answers (`duration_ms` aside, the
  executable has no clock; the server measures it); [`compare_debug.py`](compare_debug.py) drives 35 debug sessions on both and
  compares every line. Both run against a Linux executable built with `zig cc -target x86_64-linux-musl -static` too
  (`NEXORA_NO_ISOLATE=1` lets the reference worker find `nexora` through `PYTHONPATH`).
- The image of the playground (`servidor/playground/Dockerfile.native` of the server repository) builds it from `seed/cgen.c`
  with a C compiler and nothing else, and contains only the executable.

| Difference | Why |
|---|---|
| `duration_ms` is 0 | A NEXORA program has no clock. |
| A request that is not understood is answered with `internal_error` and exit status 0 | A NEXORA program has no exit status; the server discards the answer because it has no `action`. |
| A debug controller that disconnects ends the worker with `E3009` instead of silently | There is no way to test for the end of the input. |

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
