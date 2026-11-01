# 0027 — The native tools are the default way to use NEXORA

- **Status:** accepted.
- **Date:** 2026-11-02.
- **Decision owner:** NEXORA maintainer.
- **Affects:** how NEXORA is installed and documented; the meaning of "the reference implementation"; stages 3 and 4 of decision 0025.
- **Related to:** [0025](0025-interprete-autoalojado.md) (the self-hosted interpreter), [0026](0026-generador-a-c.md) (the generator to C),
  [0015](0015-entrada-argumentos-archivos-y-permisos.md) (capabilities and limits), [0020](0020-red-y-procesos-externos.md) (network and processes).

## 1. Context

Decision 0025 left two stages open: the fixed point (3) and leaving Python (4). Decision 0026 took stage 4 with a generator to C written in
NEXORA. That work is now complete enough to be used:

- `nex` (`check`, `run`, `test`, `inspect`, `context`, `format`, `check --evidence` and the rest of the commands), the language server
  (`nexora-lsp`), the MCP server (`nex-mcp`), the formatter (`nexora-format`) and the Playground worker (`nexora-worker`) exist as programs written in NEXORA.
- Each one was compared with the Python implementation on the same inputs, with no difference in output, diagnostics or exit status: formatter on
  381 files, language server on 228 files and 184,698 messages (UTF-8, UTF-16 and UTF-32 positions, LF and CRLF), MCP server against the
  server of the MCP SDK, and `Process.run` and `Net.get` with the limits of decision 0020.
- The compiler compiles itself to a fixed point, and `selfhost/seed/cgen.c` rebuilds it with a C compiler alone.
- Release `native-v0.15.0` publishes the five programs for Linux (x64 and arm64), macOS (x64 and arm64) and Windows (x64), each with its checksum.
  Every package is built from the seed by the continuous integration and runs a program before it is published.

## 2. Decision

1. **The native tools are the default way to use NEXORA.** The installation instructions and the guides lead with the programs of the
   `native-v*` releases. A person needs no Python to check, run, test, format or serve NEXORA.
2. **The Python implementation stays**, as the reference for the language and the way to install through `pip` and `npm`. It is not removed and
   its behaviour does not change: `pip install nexora-lang` installs the same command as before.
3. **Python is a bootstrap, not a dependency.** It is needed once, to produce the first compiler; the seed in the repository makes even that
   optional. Stage 4 of decision 0025 is closed by this decision and decision 0026.
4. **Equivalence is the contract.** A difference between the native tools and the Python implementation is a defect, found by the
   `selfhost/compare_*.py` programs that the continuous integration runs. Which of the two is wrong is decided by the specification.
5. **No cryptography of our own.** HTTPS uses the TLS of the system (SChannel on Windows, OpenSSL or LibreSSL opened when needed on the other
   systems), and always verifies the certificate and the host name.

## 3. What this does not do

- It does not make the `nex` of `pip` call the native program. That is a later decision, because a defect of the runtime would then reach
  people who installed the Python package.
- It does not remove the Python implementation from the project, the server, or the continuous integration.
- It does not publish the native programs in a package manager. They are files of a release, checked by their `.sha256`.

## 4. Known limits

- The collector of the runtime is not safe yet on Windows when a C compiler inlines functions. The programs for Windows are built with
  `-fno-inline`, the way that was checked. The cause is not found.
- The macOS programs are built and smoke-tested by the continuous integration (`run`, `check` and the worker); the comparison suites run on
  Linux and Windows.
- A program that is run with `--timeout` or `--max-memory` relies on the operating system, as `selfhost/README.md` says.

## 5. Consequences

- The installation page and the README show the native programs first and pip and npm second.
- Reports of a difference between the two implementations are accepted as defects with high priority.
- Any later change of the default (the `pip` command calling the native program, or removing the Python implementation) needs its own decision.
