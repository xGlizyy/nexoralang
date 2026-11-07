# Platform support

The systems and the Python versions that NEXORA 1.0 supports, how each one is checked, and the dated evidence. The target is
the one of [decision 0021](decisions/0021-alcance-nexora-1-0.md) (section 6) as settled by
[decision 0029](decisions/0029-congelacion-de-la-especificacion-1-0.md) (section 2.5). "Supported" here means that the
whole test suite passes in continuous integration on it, and that the programs people download were used on it.

## The target

| Part | Target | Checked by |
|------|--------|------------|
| Python (the reference implementation) | CPython 3.11, 3.12, 3.13 and 3.14 | `nexora-ci.yml`: the whole suite, the reference applications and a clean install of the wheel, on every Python and every system below |
| Linux | Ubuntu 24.04 LTS, x86-64 | The runner `ubuntu-24.04`; the native `linux-x64` package; Ubuntu 24.04 on WSL 2, by hand |
| Windows | Windows 11, x86-64 | The runner `windows-2025` (Windows Server 2025: the same kernel and API as Windows 11, and GitHub has no x86-64 Windows 11 image); the native `windows-x64` package on a real Windows 11, by hand |
| macOS | macOS 14 or newer, Apple Silicon | The runner `macos-15`; the native `macos-arm64` package |
| Native tools (`nex`, `nexora-lsp`, `nex-mcp`, the formatter, the worker) | Linux x86-64 and arm64, macOS Apple Silicon and Intel, Windows x86-64 | `nexora-native-release.yml` builds and runs the five packages of each `native-v*` release; `nexora-platform.yml` downloads them, verifies their SHA-256 and uses them |

**Not in the target:** macOS on Intel for the Python implementation (the native package for it is built, smoke-tested and
published, but the whole suite does not run on it), Windows on ARM, 32-bit systems, other Linux distributions and architectures
for the Python tests. They may work; nothing here promises it.

## How it is checked

- **Every change** runs the suite of `nexora-ci.yml` on `ubuntu-24.04`, `windows-2025` and `macos-15` with each of the four Pythons,
  and the job `reference-apps` runs the three [reference applications](../reference-apps/README.md) from a wheel installed in a clean
  environment on the same twelve combinations.
- **Every change to the native tools** runs `nexora-selfhost.yml`: the seed is the fixed point of the sources and the native tools give
  the same output as the Python ones on the programs of the repository.
- **`nexora-platform.yml`**, by hand, every Monday, for every tag and for changes to the workflow, is the smoke test of what people
  download: on each system it fetches the latest `native-v*` release, checks the SHA-256 of the package against its `.sha256`, and uses
  the tools; and on every Python it installs the wheel built from the commit in a clean environment and runs a program. The summary of
  each job names the system, its version, the date and what ran. That summary is the record.

## Records

Dated, by hand, on real machines (CI records are in the summaries of the runs of `nexora-platform.yml`, linked below them):

| Date | System | What | Result |
|------|--------|------|--------|
| 2026-11-07 | Windows 11 Pro 10.0.26200 x86-64 | `native-v0.15.2` (`nex.exe`), checked against its published `.sha256`: the 29 scenarios of `tests/test_threat_model_rows.py` that run on Windows, including a directory junction | 29 passed, 4 skipped (links that need a privilege, and POSIX path semantics) |
| 2026-11-07 | Ubuntu 24.04 (WSL 2) x86-64 | `native-v0.15.2` (`nex`), checked against its published `.sha256`: the same 66 scenarios in Python and native, symbolic links included | 66 passed |
| 2026-11-07 | Ubuntu 24.04 (WSL 2) x86-64 | `nex` built from the seed of the fixes of the pull request that follows `native-v0.15.2`: 70 scenarios (Python and native), 60 runs of a silent process, the arguments after `--`, the release check of the three artifacts | 70 passed; 0 failures in 60; same arguments; check passed |
| 2026-11-07 | Windows 11 Pro 10.0.26200 x86-64 | The reference implementation 0.15.x on Python 3.12: the whole suite | 3630 passed, 23 skipped (platform) |

The run of `nexora-platform.yml` that checks every system of the target at once is linked from the readiness page when it passes.
