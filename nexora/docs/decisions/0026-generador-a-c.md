# 0026 — A code generator to C, written in NEXORA

- **Status:** accepted (2 November 2026, with [0027](0027-herramientas-nativas-por-defecto.md)).
- **Date:** 2026-10-31.
- **Decision owner:** NEXORA maintainer.
- **Affects:** stage 4 of decision 0025 (leaving Python), the meaning of "the reference
  implementation", the tools a user needs to build a NEXORA program into an executable.
- **Related to:** 0025 (the self-hosted interpreter, in stages; this decision takes its stage 4; it is
  proposed in [PR #42](https://github.com/xGlizyy/nexoralang/pull/42)),
  [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) (only what has been checked runs),
  [0015](0015-entrada-argumentos-archivos-y-permisos.md) (capabilities and limits).

## Executive summary

The self-hosted interpreter of decision 0025 reaches a fixed point at level 2 and no further:
each level costs two to three orders of magnitude more than the one below, and level 3 would
take years (measurements in section 2). A faster interpreter in NEXORA does not remove Python from
under it. A second way to execute NEXORA that is not Python does.

This decision chooses that second way: **a code generator, written in NEXORA, that emits C**.
The generated C is compiled by the C compiler the system already has, and the result is an
executable that needs neither Python nor the interpreter. Python stays only as the first
bootstrap: once the generator exists, it compiles itself, and from then on the compiler of NEXORA
is an executable made from NEXORA.

The code that is written is NEXORA. C is an output format, like the text a formatter writes. The
one piece of C the project keeps by hand is the runtime of the generated programs, a single header
(`selfhost/runtime/nexora_rt.h`) that the generator puts at the top of every file it writes; it is
embedded in the generator as data (`runtime_text.nex`, generated from the header) so that the
generator needs no file at run time.

## 1. Purpose and status

Decision 0025 left stage 4 open because it "reintroduces the question of which language is
underneath", and asked for real measurements first. They exist now, and this decision answers.
It is **proposed**: nothing in the language changes until the maintainer accepts it, and the
interpreters of decision 0025 stay as they are, the reference for what a program must do.

## 2. What the measurements say

From `selfhost/README.md` (stage 3):

| Measurement | Result |
|---|---|
| `fib(16)`, `nex run` / interpreter written in NEXORA | 0.4 s / 41 s (about 2,000 steps a second) |
| The checker in NEXORA checks the whole interpreter (~13,000 lines) | 7 min 32 s |
| Level 2 (the interpreter run by itself) for a program of 55 steps | 24 min 16 s |
| Level 3 | not run; years by the same ratios |

Two things follow. A faster interpreter would still be a program that something else executes,
so it moves the fixed point one level further and no more. And the cost is spread over the
whole pipeline (lexer, parser, checker, interpreter), not in one place, so a cache or a better
data structure gains a constant, not an order of magnitude.

## 3. Decision

### 3.1 The pipeline

```
program.nex ── lexer, parser, checker, project loader (selfhost/*.nex) ──▶ typed tree
typed tree ── generator (selfhost/cgen.nex) ──▶ program.c
program.c ── the system's C compiler (cc) ──▶ executable
```

Everything up to the typed tree already exists in NEXORA and is checked against the Python
implementation. The new part is the generator and the runtime it emits.

**Status (2026-10-31).** Stages 1 to 6 below are written and checked in `selfhost/`: the generator `cgen.nex`, the runtime (with a
conservative garbage collector), `compare_cgen.py` and `bootstrap.py`. 46 programs, the 16 examples of the repository, 13 projects of
modules and 58 cases of the host and the limits `--max-text`, `--max-output` and `--max-input` build with a C compiler and give the
same output, diagnostics and exit status as `nex run`. The compiler compiles itself: from Python alone it takes about 40 minutes, and
the executable built from the C that Python wrote compiles `cgen.nex` into byte-identical C, twice. `selfhost/seed/cgen.c` keeps that C,
so the compiler can be rebuilt with a C compiler and no NEXORA run by Python (this answers the last open question). The same generator
builds `nex.nex` as a native `nex check`, `nex run` and `nex test`. At that date `Net.get` and `Process.run` ran nothing (they made the
same permission decisions and then said that a compiled program could not make the operation yet); they do since the release `native-v0.15.0`. The C compiler used was `zig cc`, from a
virtual environment. Speed (2026-11-01): the native `nex` runs the programs of `selfhost/bench/` in 0.33 to 1.02 times the time of the Python implementation, and the compiler compiles itself in 28 seconds (it took 6 minutes), so the self-hosted implementation is no longer slower than the one it is meant to replace.

### 3.2 What the generated program must do

The executable has to behave as `nex run` does, including what goes wrong: the same output and,
when the program fails, the same diagnostic with the same code, label, hint, notes and position
(decision 0005). So:

- **Integers** are 64 bits; every `+`, `-`, `*` and `/` checks the range and stops with `E3002`
  and `E3001` as the interpreter does. The generator uses the compiler's overflow builtins.
- **Floats** are IEEE doubles and stop with `E3003` where the interpreter does; the tests of the
  interpreter at the edge of the range (`float_add_edge_tie` and its siblings) are reused.
- **Text** is a sequence of code points: `Text.length` and `Text.slice` count them, not bytes.
  The runtime keeps text as UTF-8 with a length in code points.
- **Memory.** Programs are short-lived and the language has no mutation of shared values, so the
  first version allocates from an arena and frees it at exit. A program that runs out of memory
  stops with `E3007`. A collector is a later decision, with its own measurement.
- **Calls** are counted, and the 1,001st nested call stops with `E3004`, as the interpreter does.
- **Contracts** (`needs`, `promises`, `keeps`, `shrinks`, refined types) are compiled in; they are
  not removed in an optimised build, because a broken rule is part of the behaviour of a program.
- **Diagnostics.** The generator embeds, for each place that can fail, the data of the
  diagnostic (code, label, hint, notes, span) and the lines of source it quotes; the runtime
  renders it with the text `nex` uses. The titles of the codes come from `selfhost/titles.nex`.
- **The host** (arguments, input, files, network, processes) is implemented in the runtime with
  the same three rules of decision 0015, and the limits of resources the program can see
  (`--max-text`, `--max-output`, `--max-input`) become options of the executable. `--timeout`
  and `--max-memory` stay with the operating system, as in `selfhost/README.md`.

### 3.3 How it is built and checked

Stage by stage, each one usable on its own and compared with the interpreter written in Python,
as the earlier ones were:

1. **Integers, booleans, text, functions, `if`, `while`, `for`, `print`.** `compare_cgen.py` runs
   a program with `nex run` and as an executable and compares the output and the diagnostic.
2. Records, lists, enums, `match`, `Option` and `Result`.
3. Contracts, refined types, `example` and `nex test`.
4. The host and the limits.
5. Modules (the linker of `project.nex` already makes one tree of them).
6. **The generator compiles itself** (`nex.nex` as an executable). Its output on a program is
   compared with that of the interpreter: that is the fixed point of decision 0025, now
   reachable, and from there the executable is the compiler.

### 3.4 What Python still does

Until stage 6 the generator is run by the Python interpreter, as every other part of the
self-hosted code. After stage 6 the first executable of the compiler is built once with Python,
and every later one with itself. Python then is a bootstrap that can be thrown away, and the
project can keep a prebuilt executable (or its generated C, which is plain text and can be
reviewed) as the seed.

## 4. Alternatives considered

| Alternative | Why not |
|---|---|
| Make the interpreter in NEXORA faster (module cache, better data structures) | Useful and cheap, but Python stays underneath: it does not do what the maintainer asked. The numbers above say it gains a constant. |
| A bytecode virtual machine | Needs the VM written in some language that is not Python; decision 0025 ruled out a native runtime in another language as the first option because it keeps a second language in the project for good. |
| Emit machine code directly (an x86-64 and ARM64 backend) | No dependency on a C compiler, but a backend for each architecture and a binary format for each system is a project of its own, and it is much harder to review than C. |
| Emit WebAssembly or JavaScript | Both need a runtime written in another language (a browser, `node`). Possible as extra targets later; they do not remove the dependency, they move it. |
| Emit LLVM IR | A very good target, but it makes LLVM a build dependency, which is far bigger than a C compiler. |

## 5. What it does not solve

- It needs **a C compiler** to build a program. Almost every system has one, and none is shipped
  with NEXORA. A user who only runs programs with `nex run` is not affected.
- It does not make **the first** executable of the compiler without Python: that one is built
  with it, once.
- C compilers differ in small ways. The generator uses only what C11 and the overflow builtins of
  GCC and Clang give, and the tests run with both where they are available.
- The language does not change: a program means what it meant. If the generator needs something
  the language lacks (the rule of decision 0025, section 4), it is proposed on its own.

## 6. Risks

| Risk | Mitigation |
|---|---|
| The generated program differs from the interpreter in a corner (overflow, text, order of evaluation) | A differential test per stage against `nex run`, with the same cases the interpreter already passes |
| Messages and positions of runtime errors drift | They are data embedded by the generator and rendered by one function, the one tested for `nex.nex` |
| Arena memory is not enough for a long program | Measured before stage 6; a collector is its own decision |
| The generator is as slow as the rest of the self-hosted code until stage 6 | It only has to run once per program; the cost it pays is the 7 minutes of checking, not of running |

## 7. Open questions

- Which C compiler is the reference for the tests: `cc` of the system, or one fixed (GCC or Clang)?
- Does the runtime keep text as UTF-8 with a count of code points, or as an array of code points?
  The first is smaller and faster to print; the second makes `Text.slice` constant.
- (Answered) The generated C is kept in the repository as the seed of stage 6: `selfhost/seed/cgen.c`.

## 8. Update of 1 November 2026: what was built

This section records results; it does not change the decision or its status, which is for the maintainer.

- The generator, the runtime and the compiler that compiles itself exist in `selfhost/` and reach a fixed
  point (the C written by the compiler built from it is the same text again). The seed is
  `selfhost/seed/cgen.c`. The measurements of speed and of equivalence with `nex` are in `selfhost/README.md`.
- The generator also builds the Playground worker (`selfhost/worker.nex`): the debugger on the abstract
  machine of the interpreter, projects loaded from memory, a host that allows nothing, and the limits of
  the process. It runs on the public site since 1 November 2026, in an image with that executable only.
  What was compared with the Python worker, what differs and what is not proved are in
  [the Playground page](../playground.md#the-native-worker).
- Python is still needed once, to produce the first compiler; every later one is built with itself. Python
  remains the reference implementation for the language and for the command-line tool.
