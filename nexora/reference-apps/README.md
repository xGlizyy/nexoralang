# Reference applications

Three programs that are the evidence for the NEXORA 1.0 subset ([decision 0021](../docs/decisions/0021-alcance-nexora-1-0.md),
gate "Reference applications"). Each one is a real tool, small enough to read in one sitting, and each one covers a
different part of what 1.0 promises.

| Application | Profile | What it shows |
|-------------|---------|---------------|
| [`textstats`](textstats/) | A pure command-line tool | Arguments and standard input, texts, lists, records, `Option`, `match`, refined types, contracts and `example` clauses. It declares no capability |
| [`csvsummary`](csvsummary/) | Local files and modules | Three files (`main.nex`, `csv.nex`, `stats.nex`), `import` and `pub`, `Result` for errors, and `read_file` and `write_file` inside the folders it declares with `uses read` and `uses write` |
| [`envreport`](envreport/) | One explicitly granted capability | `uses process`, `Process.run`, and what happens without the grant (`E3008`) and without the declaration (`E2026`) |

## How they are verified

`tests/test_reference_apps.py` checks, tests and runs each application through the real command, in a separate process,
and compares the standard output, the standard error and the exit code with what the README of the application says. It
also covers the failures: a bad input, a missing grant, a path outside what the program declares.

In continuous integration the job `reference-apps` builds the wheel, installs it in a new virtual environment and runs
those tests with `nex` from that environment, on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13. To do the same
by hand:

```bash
python -m venv /tmp/clean && /tmp/clean/bin/python -m pip install nexora/dist/*.whl
NEXORA_APPS_PYTHON=/tmp/clean/bin/python python -m pytest nexora/tests/test_reference_apps.py
```

## What writing them showed

Building the applications is what the gate is for: it finds what a real tool needs and the language does not give it.
These are the findings. They were settled when the 1.0 specification was frozen: each one is outside 1.0, documented with its way
round, and can arrive in a later 1.x without breaking a program that works on 1.0
([decision 0029](../docs/decisions/0029-congelacion-de-la-especificacion-1-0.md), section 2.2; [limitations](../docs/limitations.md#what-10-does-not-include)).

- **A program cannot choose its exit status.** `csvsummary` reports a bad file by printing `error: ...` and ending normally,
  with status 0. A tool used in a script needs a way to fail.
- **`input()` cannot tell the end of the input.** Reading when there is nothing left stops the program with `E3009`
  (`textstats` documents it), and there is no way to test for it first.
- **`write_file` does not create folders.** `csvsummary` needs its `out/` folder to exist.
- **A `Result` or an `Option` can only be written in an `example` through the functions that read it** (`Result.value`,
  `Result.error`): `Ok(...)` and `Err(...)` have no type of their own there.
- **A list literal and an expression have to fit on one line.** Long tables are built with `List.append`.
- **There is no `\r` escape in a text.** `csvsummary` does not need it, because `read_file` turns CRLF into LF.

## Review

Reviewed on 2026-11-07 (decision 0029, section 4). Each application was read, its README compared with what it does, and `nex check`,
`nex test` and `nex run` were run in the Python implementation and in the native `nex` built from the same tree on Linux: the same
standard output, the same standard error and the same status in all 17 runs, failures included (the sample and four bad files of
`csvsummary`, no grants, a path outside what it declares, and `envreport` with and without its grant). The review found nothing that
blocks the freeze of 1.0.

The release tools of this repository are written in NEXORA too (`release/check_artifacts.nex`, `release/check_freeze.nex`), and
they are the fourth and fifth programs that a real need made. Writing the first one, which runs `mkdir`, `tar`, `unzip` and
`sha256sum` with `Process.run` and takes its arguments after `--`, found two defects of the native `nex` (a silent command could
fail with status -9, and `--` reached the program as an argument), fixed in `native-v0.15.3`.
