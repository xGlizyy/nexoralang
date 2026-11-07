# NEXORA 1.0 readiness

Where the project stands against the release gate of [decision 0021](decisions/0021-alcance-nexora-1-0.md),
section 8. It was written on 2026-11-06 and brought up to date on 2026-11-07 from what is in the repository; each row
names the evidence it rests on. The decision is the source of the criteria, this page is the status and the work that is
left. Nothing here lowers a criterion.

| Status | It means that… |
|--------|----------------|
| **Met** | The evidence the gate asks for exists and runs in CI |
| **Partial** | Some of the evidence exists; what is missing is stated |
| **Open** | Nothing of the evidence exists yet |

## The gates

| Gate | Status | What there is | What is missing |
|------|--------|---------------|-----------------|
| Normative specification | **Met** | [Specification 1.0](language-spec.md), frozen by [decision 0029](decisions/0029-congelacion-de-la-especificacion-1-0.md): it covers enums, exhaustive `match` and the `?` operator, and every normative section has executable examples (`tests/test_docs.py`). `release/check_freeze.nex`, a program written in NEXORA, pins its grammar, keywords, built-in functions, diagnostic codes and exit codes against `release/frozen/` in `nexora-release.yml` and in `tests/test_release_tools.py` | Nothing planned |
| Reference applications | **Met** | Three applications in [`reference-apps/`](../reference-apps/README.md): `textstats` (a pure CLI), `csvsummary` (files and three modules) and `envreport` (a granted process). `tests/test_reference_apps.py` checks, tests and runs them, failures included, and the job `reference-apps` does it with the built wheel in a clean environment on Linux, Windows and macOS with Python 3.11 to 3.14. They were reviewed on 2026-11-07 in Python and in the native `nex` (the same output in 17 runs), and their five findings are settled in decision 0029: outside 1.0, each with its way round | Nothing planned. HTTPS is not a fourth application: the gate asks for HTTPS **or** a process, and `envreport` is the process |
| Stable CLI | **Met** | [Interface stability policy](interface-stability.md); versioned JSON with schemas generated from the code and checked against real output (`tests/test_tooling.py`); CLI tests (`tests/test_cli.py`) on Linux, Windows and macOS with Python 3.11 to 3.14; `tests/test_cli_compatibility.py` pins the options, exit status and diagnostic codes of `check`, `run` and `test` by name | Nothing planned |
| Module behavior | **Met** | Resolution, visibility and cycles are specified and tested (`tests/test_modules.py`, including the cycle cases); the language server resolves relative imports across the open project (`tests/test_lsp.py`); the reference applications and the release tools use modules | Nothing planned |
| Runtime control | **Met** | `--timeout`, `--max-output`, `--max-input`, `--max-text`, `--max-source` and `--max-memory`; a loop that never ends stops with `E4006`; POSIX timeouts clean up the child process group (`tests/test_cli.py`, `tests/test_loops.py`, `tests/test_out_of_memory.py`) | Nothing planned |
| Capability security | **Met** | File, network and process access need a declaration and a grant (`tests/test_security.py`); [SECURITY.md](../../SECURITY.md) says plainly that the local runtime is not a sandbox; the [threat model](threat-model.md) of the local CLI is written and reviewed (2026-11-07), and each of its rows is backed by `tests/test_threat_model.py` and, for the Python and the native `nex`, by `tests/test_threat_model_rows.py`. Checking the native `nex` found a symbolic-link defect, fixed and released as `native-v0.15.2` | The maintainer's own reading of the threat model, which replaces the delegated review if they want it independent. It does not change the criteria |
| Platform support | **Met** | The CI runs the whole suite and the reference applications on `ubuntu-24.04`, `windows-2025` and `macos-15` with Python 3.11, 3.12, 3.13 and 3.14, and `pyproject.toml` lists 3.14. [Platform support](platform-support.md) has the dated records: `nexora-platform.yml` downloaded the native release on four systems, verified its SHA-256 and used it (run [42397018291](https://github.com/xGlizyy/nexoralang/actions/runs/42397018291), 2026-11-07), and the tools were used by hand on a real Windows 11 and on Ubuntu 24.04 | Nothing planned. GitHub has no x86-64 Windows 11 image: `windows-2025` is Windows Server 2025 (the same build as Windows 11 24H2), and the native tools were also run on a real Windows 11 |
| Package artifacts | **Met** | `nexora-release.yml` builds the wheel, the source distribution and the npm package once and checks them with `release/check_artifacts.nex`: the same name, version and licence, the same SHA-256 for each of the modules of the interpreter in the three, and a `SHA256SUMS` that lists them. It installs the source distribution in a clean environment (also in `nexora-ci.yml`, with the wheel and the npm package), and it tests that a wrong tag or version, a changed module, a missing or doubled artifact and a changed hash each fail with status 5. [Release process](release-process.md) | Nothing planned. The step that attaches the files and `SHA256SUMS` to the release of a tag runs for a tag `v*`, and no such tag has been pushed since it was added: the first tag is its first run (the native release already attaches its `.sha256`) |
| Release integrity | **Met** | A changelog (`CHANGELOG.md`); [compatibility policy](compatibility.md); [migration guide](migration-guide.md) from every 0.x version; [yank policy](yanking.md); the [release checklist](../release/RELEASE_CHECKLIST.md), which `nexora-release.yml` attaches to the release of each tag | Nothing planned |
| Documentation accuracy | **Met** | `tests/test_docs.py` keeps the documents tied to the implementation; decision 0021 has its amendments (the last one of 2026-11-07); README, roadmap, limitations, installation, deployment and testing were read against the code and say 1.0, Python 3.11 to 3.14 and the pinned runners | Nothing planned |
| Support process | **Met** | Public security policy, with response targets, the list of supported releases and the known issue of the native tools | Keeping the table of supported releases current |
| Release blockers | **Met** | The issue list was reviewed on 2026-11-07: there are no open issues, the labels `P0` and `P1` exist, and none is open on any issue. The two defects of the native `nex` that the release tools found (a silent process could fail with status -9 on Linux and macOS, and `--` reached the program as an argument) were fixed by pull request #65 and released as `native-v0.15.3`, checked on the published programs on Linux and Windows | Nothing planned. A P0 or P1 found later blocks the release (the checklist asks for it) |

All twelve gates are met.

## What is left, in order

1. ~~Merge the pull request #65 and release `native-v0.15.3`.~~ Done on 2026-11-07, with the maintainer's authorization.
2. **Merge the pull request #63**, which has the reference applications, the compatibility suite, the threat model, the release
   tools, the 1.0 specification and this page.
3. **Release 1.0.0** when the maintainer decides: the checklist in [`release/RELEASE_CHECKLIST.md`](../release/RELEASE_CHECKLIST.md),
   with `1.0.0` as the version of `src/nexora/version.py`, of `npm/package.json` and of the supported releases table. The first tag
   is the first run of the step that attaches `SHA256SUMS`.
4. **Optional: the maintainer's own reading** of the threat model and of decision 0029. They were done by the assistant under the
   maintainer's delegation, and say so; the maintainer can replace either with another decision.

## How the five open choices were settled

The five choices that decision 0021 left to the maintainer, settled by [decision 0029](decisions/0029-congelacion-de-la-especificacion-1-0.md)
(section 2) and open to being replaced by another decision:

1. **Python 3.14** is in the CI matrix and in `pyproject.toml`.
2. **The promise is about the specification**; the Python implementation is the reference and the native tools conform to it, each
   with its own support matrix.
3. **Support period:** unchanged, the latest published release of each component.
4. **The findings of the reference applications** are outside 1.0, each documented with its way round and each an addition for a
   later 1.x.
5. **The platforms:** Ubuntu 24.04, Windows 11 (evidence on Windows Server 2025 and on a real Windows 11) and macOS 14 or newer on
   Apple Silicon (tested on `macos-15`).
