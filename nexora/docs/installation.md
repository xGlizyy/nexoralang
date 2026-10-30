# Installation

NEXORA is installed from the source code or from the registry: the `nexora-lang` package is
published on PyPI and on npm ([packages for pip and npm](#packages-for-pip-and-npm)).

## Requirements

- **Python 3.11 or newer.** Check it with `python --version` (on some systems, `python3 --version`).
- `pip` and the `venv` module, which come with Python. On Debian and Ubuntu they may have to be installed
  separately: `sudo apt install python3-venv python3-pip`.
- An internet connection **only during installation**, so that `pip` downloads the packaging
  tool (`setuptools`) and, if you are going to run the tests, `pytest`, `pytest-cov` and `ruff`.

The interpreter has no dependencies: it only uses the Python standard library. Once installed,
NEXORA works offline.

## What has been checked

| Environment | Status |
|-------------|--------|
| Windows 11, Python 3.12 | **Checked**: development-mode installation in a clean environment, installation from the built package, and full test suite |
| Windows 11, Node.js, npm package | **Checked**: `npm test` passes; the 0.14.1 tarball installs locally and reports the expected version |
| Linux (Ubuntu 24.04 on WSL 2), Python 3.12 | **Checked** on 17 October 2026: full test suite, with none skipped, with a non-root user; package built and installed from the file in a clean environment, and `nex run` used. Other distributions and Linux without WSL, not checked |
| Linux, Node.js, npm package | **Checked**: built with `npm pack`, installed from the file and used with `npx nex` on the previous published release |
| macOS | **Run** on `macos-latest` by the [continuous integration](testing.md#continuous-integration): test suite with Python 3.11, 3.12 and 3.13, the npm package and the server. On a local Mac, not checked |
| Python 3.11 and 3.13 | **Run** on Linux, Windows and macOS by the continuous integration, and **checked** by hand on Linux (3.11.17 and 3.13.16): full test suite, without installing the built package |

## Step-by-step installation

All the commands are run from the `nexora/` directory of the repository (the one that contains
`pyproject.toml`).

### 1. Create a virtual environment

```bash
python -m venv .venv
```

A virtual environment is a folder (`.venv`) with an isolated copy of Python. NEXORA is installed
inside it and does not touch the rest of the system.

### 2. Activate the environment

| System | Command |
|--------|---------|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Linux and macOS (bash, zsh) | `source .venv/bin/activate` |

It has to be activated in every new terminal. With the environment activated, the name `(.venv)` usually
appears at the beginning of the command line.

### 3. Install NEXORA

To use the language:

```bash
python -m pip install -e .
```

To work on the project (adds the testing and analysis tools):

```bash
python -m pip install -e ".[dev]"
```

The `-e` option installs in development mode: the `nex` command uses the files of
`src/` directly, so any change in the code takes effect without reinstalling.

### 4. Check the installation

```bash
nex --version
nex run examples/hello.nex
```

Expected result:

```text
NEXORA 0.15.0
Hello from NEXORA
```

## Where the `nex` command ends up

The `nex` command is installed **inside the virtual environment**, not system-wide. It is only
available in the terminals where the environment is activated.

Without activating the environment there are two alternatives:

| Alternative | Windows | Linux and macOS |
|-------------|---------|-----------------|
| Call the command by its path | `.venv\Scripts\nex.exe run program.nex` | `.venv/bin/nex run program.nex` |
| Use the Python module of the environment | `.venv\Scripts\python.exe -m nexora run program.nex` | `.venv/bin/python -m nexora run program.nex` |

`python -m nexora` does exactly the same as `nex`.

## Installing from a built package

The project can be packaged into an installable file (*wheel*). The one published on PyPI is
this very one: `python -m build` builds the two files that are uploaded to the registry.

```bash
python -m pip install build
python -m build
```

This creates two files in `dist/`: `nexora_lang-0.15.0-py3-none-any.whl` and `nexora_lang-0.15.0.tar.gz`. The
first one can be installed in any environment with Python 3.11 or newer:

```bash
python -m pip install dist/nexora_lang-0.15.0-py3-none-any.whl
```

The *wheel* contains only the interpreter and the `nex` command. The examples, the documentation and the
tests are in the `.tar.gz` file and in the repository.

## Packages for pip and npm

The `nex` command can be distributed in two ways. The package is called **`nexora-lang`** in both,
because the name `nexora` already belongs to other projects on PyPI and on npm. The command is still
`nex`.

Version 0.15.0 is published on PyPI and npm. For development versions, build the packages locally
using the instructions below and check that they install from the generated files and that the `nex`
command works.

| | pip | npm |
|-|-----|-----|
| Package | `nexora-lang` (directory `nexora/`) | `nexora-lang` (directory `npm/`, at the root of the repository) |
| What it contains | The interpreter and the `nex` and `nex-mcp` commands | A copy of the interpreter and a JavaScript launcher |
| What it needs | Python 3.11 or newer | Node.js 18 or newer **and Python 3.11 or newer** |
| Install | `pipx install nexora-lang` | `npm install -g nexora-lang` |

The npm package **does not remove the dependency on Python**: the interpreter is written in Python. The
launcher looks for a Python 3.11+ on the machine (`py -3` on Windows, `python3`, `python` and, on Windows,
the folders of the official installer), runs the interpreter included in the package with it, and passes
the arguments, the output and the exit code through unchanged. If it finds none it explains so and
ends with code `127`. The `NEXORA_PYTHON` variable lets you choose one. It does not include the MCP
server.

### Building and installing the npm package locally

From the `npm/` directory:

```bash
npm test                 # copies the interpreter into the package and runs the launcher tests
npm pack                 # builds nexora-lang-0.15.0.tgz
npm install -g ./nexora-lang-0.15.0.tgz
nex --version
```

### Publishing

It requires an account in each registry and is irreversible in practice (a published version cannot
be reused). Before that, the test suite has to pass.

```bash
# PyPI, from nexora/
python -m pip install build twine
python -m build
python -m twine upload dist/*

# npm, from npm/
npm login
npm publish
```

The credentials are entered when running those commands; they are not stored in the repository. Versions
0.9.0, 0.10.0 and 0.11.0 were published this way, with the test suite and the continuous integration
green. 0.12.0 too, from the files built in a clean copy of the tag `v0.12.0`: the same files that were
installed and tried before, checked by their SHA-256 before and after the upload. 0.12.1 too, from a
clean copy of the tag `v0.12.1`, with its files checked by their SHA-256 before the upload. Version
0.14.1 was built, checked and installed before upload; its SHA-256 sums are attached to the GitHub
release.

npm may scan a package after accepting a publish before making the version available. Wait for
`npm view nexora-lang version` to show the new version instead of retrying the same version; a repeated
publish can return `E409` for a version already being processed. See [npm's publish-time scanning
notice](https://github.blog/changelog/2026-07-28-npm-publish-time-malware-scanning-and-dual-use-metadata/).

## Common problems

| Symptom | Cause and fix |
|---------|---------------|
| `nex` is not recognized as a command | The virtual environment is not activated in that terminal. Activate it (step 2) or use the full path |
| On Windows, `python` opens the Microsoft Store or says Python was not found | Python is not installed, or only the Store shortcut exists. Install it from [python.org](https://www.python.org/downloads/) and open a new terminal |
| On Linux or macOS, `python` does not exist | Use `python3` to create the environment (`python3 -m venv .venv`). Once it is activated, `python` works |
| PowerShell refuses to run `Activate.ps1` ("running scripts is disabled") | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `nex` by its path without activating the environment |
| `pip` says `requires a different Python` | The Python version is older than 3.11. Create the environment with a newer version |
| `error: externally-managed-environment` | You are installing outside a virtual environment. Create and activate one (steps 1 and 2) |
| `The virtual environment was not created successfully because ensurepip is not available` | The `python3-venv` package is missing (Debian, Ubuntu) |
| `pip` cannot download `setuptools` | The installation needs internet the first time. Not afterwards |
| Accents or the `✓` symbol look wrong when redirecting the output on Windows | The output of `nex` is always UTF-8. Set the terminal to UTF-8: `[Console]::OutputEncoding = [Text.Encoding]::UTF8` in PowerShell |
| `nex --version` shows an old version | There is another installation of NEXORA in that environment. Reinstall with `python -m pip install -e .` |

## Uninstalling

```bash
python -m pip uninstall nexora-lang
```

Or simply delete the `.venv` folder: everything installed is inside it.
