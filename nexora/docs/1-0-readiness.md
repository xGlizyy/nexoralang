# NEXORA 1.0 readiness

Where the project stands against the release gate of [decision 0021](decisions/0021-alcance-nexora-1-0.md),
section 8. It was written on 2026-11-06 from what is in the repository; each row names the evidence it rests on.
The decision is the source of the criteria, this page is the status and the work that is left. Nothing here
lowers a criterion.

| Status | It means that… |
|--------|----------------|
| **Met** | The evidence the gate asks for exists and runs in CI |
| **Partial** | Some of the evidence exists; what is missing is stated |
| **Open** | Nothing of the evidence exists yet |

## The gates

| Gate | Status | What there is | What is missing |
|------|--------|---------------|-----------------|
| Normative specification | **Met** | [Specification 0.14](language-spec.md) covers enums, exhaustive `match` and the `?` operator, and every normative section has executable examples (`tests/test_docs.py`) | Declaring the 1.0 specification: a freeze of the syntax, with the version number it will carry |
| Reference applications | **Partial** | Three applications in [`reference-apps/`](../reference-apps/README.md): `textstats` (a pure CLI), `csvsummary` (files and three modules) and `envreport` (a granted process). `tests/test_reference_apps.py` checks, tests and runs them, failures included, and the CI job `reference-apps` does it with the built wheel in a clean environment on Linux, Windows and macOS with Python 3.11 to 3.13 | The maintainer's review of the three applications, and the decisions on what they found (below). The gate asks for HTTPS or a process as the granted capability: `envreport` covers the process, none covers HTTPS |
| Stable CLI | **Met** | [Interface stability policy](interface-stability.md); versioned JSON with schemas generated from the code and checked against real output (`tests/test_tooling.py`); CLI tests (`tests/test_cli.py`) on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13; `tests/test_cli_compatibility.py` pins the options, exit status and diagnostic codes of `check`, `run` and `test` by name | Nothing planned |
| Module behavior | **Met** | Resolution, visibility and cycles are specified and tested (`tests/test_modules.py`, including the cycle cases); the language server resolves relative imports across the open project (`tests/test_lsp.py`) | Nothing planned. The reference applications will exercise it again |
| Runtime control | **Met** | `--timeout`, `--max-output`, `--max-input`, `--max-text`, `--max-source` and `--max-memory`; a loop that never ends stops with `E4006`; POSIX timeouts clean up the child process group (`tests/test_cli.py`, `tests/test_loops.py`, `tests/test_out_of_memory.py`) | Nothing planned |
| Capability security | **Partial** | File, network and process access need a declaration and a grant (`tests/test_security.py`); [SECURITY.md](../../SECURITY.md) says plainly that the local runtime is not a sandbox | The reviewed threat model of the local CLI that the gate names. Today the threat model is only mentioned, not written |
| Platform support | **Partial** | CI runs the whole suite on Linux, Windows and macOS with Python 3.11, 3.12 and 3.13 | See below: Python 3.14 is in the target and not in CI, the runners are `*-latest` and not the versions the decision names, and there is no dated native smoke record on a real Linux or macOS machine |
| Package artifacts | **Partial** | CI builds the package, installs the wheel in a clean environment and runs `nex --version` and `nex run`; the npm package is packed and installed | The source distribution is built but never installed; no check that the versions and the metadata of the wheel, the source distribution and the npm package agree; hashes of the artifacts are not published with a tag |
| Release integrity | **Open** | A changelog (`CHANGELOG.md`); [compatibility policy](compatibility.md) | A migration guide from 0.x to 1.0, a policy for yanking a compromised artifact, and the release checklist that is attached to each tag |
| Documentation accuracy | **Partial** | `tests/test_docs.py` keeps the documents tied to the implementation | Decision 0021 itself has statements that are no longer true (see its amendments). A pass over README, roadmap, limitations and installation before the release |
| Support process | **Met** | Public security policy, with response targets and the list of supported releases | Keeping the table of supported releases current |
| Release blockers | **Open** | None recorded | A release issue list reviewed with no open P0 or P1 |

Five of the twelve gates are met, five are partial and two are open. The work that is left is concentrated in the
review of the reference applications, the platform evidence and the release process; the language itself is not
what is holding 1.0 back, apart from the findings below.

## What the reference applications found

Writing the three applications is what the gate is for: they show what a real tool needs and the language does not
give it. Each of these has to be settled before the 1.0 subset is frozen, either by adding it or by saying in the
specification that it is out of 1.0 (the list is also in the [applications' README](../reference-apps/README.md)):

1. **A program cannot choose its exit status.** `csvsummary` reports a bad file with `error: ...` and ends with
   status 0. For tools that are used in scripts this is the most important of the findings.
2. **`input()` cannot tell the end of the input**: reading with nothing left stops the program with `E3009`.
3. **`write_file` does not create folders.**
4. **`Ok(...)` and `Err(...)` cannot be written in an `example`**, only read with `Result.value` and `Result.error`.
5. **List literals and expressions have to fit on one line**, and there is no `\r` escape in a text.

None of them blocks writing the applications, and the first one is the only one that I would call a gap in the
promise; the rest are limits to document.

## What is left, in order

1. **Review the three reference applications** (`reference-apps/`), decide the findings above, and add an application
   whose capability is HTTPS if the maintainer wants both capabilities covered. Whatever the applications need and the
   language lacks is resolved before the freeze; whatever they do not need stays out of 1.0.
2. **Platform evidence.** Decide Python 3.14 (below), pin the runner versions the decision names, and record a
   native smoke test on Windows 11, Ubuntu 24.04 and macOS 14 or newer with its date.
3. **The threat model of the local CLI**, as a document under `docs/`, reviewed against `tests/test_security.py`.
4. **Package evidence**: install the source distribution too, check that the three artifacts agree on version and
   metadata, and publish their hashes with each tag.
5. **Release process**: migration guide, yank policy and release checklist.
6. ~~CLI compatibility suite~~ Done: `tests/test_cli_compatibility.py`.
7. **Freeze**: declare the 1.0 specification once 1 to 6 are done, and review the open issues for P0 and P1.

## Decisions that are the maintainer's

These are not mine to settle, and each changes what the gates ask for:

1. **Python 3.14.** Decision 0021 lists CPython 3.11 to 3.14, `pyproject.toml` and CI stop at 3.13. Either add
   3.14 to the CI matrix and the classifiers (recommended: it is a cheap change if the suite passes), or amend the
   decision to 3.11 to 3.13.
2. **The native tools in the promise.** The product promise says programs run "with the reference interpreter".
   Since [decision 0027](decisions/0027-herramientas-nativas-por-defecto.md) the native `nex` is the default of
   the tools, and the Python implementation remains the reference that the native one is compared with. The 1.0
   text should say which of the two the 1.0 promise is about, and whether the native packages need their own
   support matrix.
3. **Support period.** The security policy supports only the latest release of each component. Decide whether 1.0
   keeps that or commits to a window for the last 1.x minor.
