# envreport

Asks another program for information and reports on it. It runs `python --version`, reads the version and says whether it
is one that NEXORA supports (CPython 3.11 or newer).

```bash
nex run envreport.nex --allow-process python
nex test envreport.nex
```

The output does not depend on the machine, as long as its Python is a supported one:

```
interpreter: python
major: 3
supported: true
check: 42
```

- The program declares `uses process "python"`: it runs that executable and nothing else. Without the declaration `nex check`
  fails with `E2026`. Without `--allow-process python` it stops with `E3008` before starting anything.
- `Process.run` starts the executable directly, without a shell, and returns its standard output. A process runs with the
  permissions of whoever started `nex`: the grant is not a sandbox (see [SECURITY.md](../../../SECURITY.md)).
- `nex test` evaluates the 13 `example` clauses of the pure functions that read and compare the version. They never start a
  process.
