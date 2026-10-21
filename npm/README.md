# nexora-lang

The `nex` command of the NEXORA programming language, installable with npm.

NEXORA is a new language at an early stage (version 0.7.0, before 1.0). It is not ready for
production use and its syntax may change.

## Requirements

- Node.js 18 or newer.
- **Python 3.11 or newer.** NEXORA's interpreter is written in Python. This package contains the
  interpreter and a small launcher that runs it with the Python already on your machine. It does
  not download or install Python.

## Install

```bash
npm install -g nexora-lang
nex --version
```

Without installing:

```bash
npx nexora-lang --version
```

## Use

```nex
fn main() -> Void {
    print("Hello from NEXORA")
}
```

```bash
nex run hello.nex        # check the program and run it
nex check hello.nex      # check it without running it
nex context hello.nex    # summarise it
nex --help
```

The commands, options, output and exit codes are those of the interpreter; the launcher adds none
of its own, with one exception: it exits with code `127` when it cannot find a suitable Python.

## Choosing the Python

The launcher tries `py -3` (Windows only), `python3` and `python`, in that order, and uses the first
one that is version 3.11 or newer. On Windows, if none of them works, it also looks in the folders
the official Python installer uses. To use a specific one, set `NEXORA_PYTHON`:

```bash
NEXORA_PYTHON=/usr/bin/python3.12 nex --version
```

## What is not included

- The optional MCP server (`nex-mcp`), which needs extra Python packages. Install NEXORA with pip
  for that.
- The documentation and the examples.

## The same command with pip

If you already use Python, this installs the same interpreter without Node.js:

```bash
pipx install nexora-lang      # or: python -m pip install nexora-lang
```

## Licence

MIT.
