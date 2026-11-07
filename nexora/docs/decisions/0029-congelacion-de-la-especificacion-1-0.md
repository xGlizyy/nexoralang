# 0029 — Freezing the 1.0 specification

- **Status:** accepted.
- **Date:** 2026-11-07.
- **Decision owner:** NEXORA maintainer, who delegated this decision to the assistant of the working session of that day
  ("tienes mi consentimiento absoluto" to finish the gates of 1.0). Each choice below says why, so that the maintainer can
  replace it with another decision.
- **Related to:** [0021](0021-alcance-nexora-1-0.md) (the scope and the release gate of 1.0), [0027](0027-herramientas-nativas-por-defecto.md)
  (the native tools), [0024](0024-enumeraciones-y-match-exhaustivo.md) and [0028](0028-operador-de-propagacion.md) (the last
  features of the subset), and the [1.0 readiness](../1-0-readiness.md) page.

## 1. Context

Decision 0021 set what has to be true before 1.0 and left to the maintainer five open choices, listed in the readiness page: the
findings of the reference applications, which implementation the promise covers, the support period, Python 3.14, and the
platforms. It also said that the 1.0 specification is declared once the other gates are met. They are, except for what this
decision settles (see the readiness page for the evidence of each gate).

## 2. Decision

### 2.1 The specification is frozen and is version 1.0

1. The specification of 1.0 is the text of the specification 0.14 as of this decision: its grammar, its semantics, its built-in
   functions, its diagnostic codes and its exit codes. **Its version number is 1.0.** No rule was changed to give it that number.
2. The reference implementation that first carries the number is the release 1.0.0. Until the maintainer publishes it, the
   implementation 0.15.x conforms to specification 1.0, and the specification says so.
3. **What is frozen** and how it is pinned, by `release/check_freeze.nex` (a program written in NEXORA) against the files of
   `release/frozen/`, in the continuous integration of every change to the specification:

   | Part | Rule after the freeze |
   |------|-----------------------|
   | The grammar (section 3) and the keywords and reserved words (2.4) | The same, line by line. A new production or a new keyword is a deliberate act with its own decision and the frozen file in the same change |
   | The built-in functions (section 8), the diagnostic codes with title and category (11.3), the exit codes (11.5) | Every frozen line stays. New ones are additions, allowed in a minor version, and are written into the frozen files |

4. After 1.0 the [compatibility policy](../compatibility.md) is the rule: a backward-compatible addition is a minor version of
   the specification (1.y); an incompatible change needs 2.0 after a deprecation. The stable CLI, the JSON schemas and the exit
   codes keep following [interface stability](../interface-stability.md).

### 2.2 The five findings of the reference applications are outside 1.0

The three [reference applications](../../reference-apps/README.md) were reviewed on 2026-11-07 (section 4). They found five
things that a real tool needs and the language does not give it. **None of them is in 1.0; each is documented with its way
round** ([limitations](../limitations.md#what-10-does-not-include), specification section 13):

| Finding | Way round in 1.0 | Why it can wait |
|---------|------------------|-----------------|
| A program cannot choose its exit status | Print the error and end normally, or end with a contract that the program breaks on purpose (status 5) | An `exit(code)` function only adds a name; it is the first addition planned after 1.0 |
| `input()` cannot test for the end of the input | Read from a file or from the arguments | A new function; no valid program changes |
| `write_file` does not create folders | The folder has to exist | An opt-in function; `write_file` keeps failing with `E3010`, so no program that works changes |
| `Ok(...)` and `Err(...)` cannot be written in an `example` | `Result.value` and `Result.error` | Accepting more programs in an `example` |
| A list literal and an expression fit on one line | Build with `List.append`; split with a helper | Accepting more programs |

The reason to leave them out is the one the compatibility policy gives: each of them only turns an error into something that works,
or adds a name, so it can arrive in a 1.y without breaking a program that works on 1.0. Putting them in now would be five
language changes, in two implementations, at the moment of declaring that the language does not change. The first one is
the one to do first: a tool for scripts that cannot fail is a real gap in the promise, and the decision says so instead of
hiding it.

The gate asks for an application with "one explicitly granted capability (HTTPS or process execution)". `envreport` covers
process execution; HTTPS is covered by the tests of the host (`tests/test_network_process.py`) and, for the native tools, by
`selfhost/compare_host_run.py --network`, which reads real pages in continuous integration, so no fourth application is added.

### 2.3 Which implementation the promise is about

The 1.0 promise is about the **language specification**, and two implementations conform to it:

- **The Python implementation** (`nexora-lang` on PyPI and npm) is the reference: where the two disagree, the specification
  decides, and when the specification is silent the Python behaviour is the answer until the specification says it.
- **The native tools** (the five programs of each `native-v*` release) are the default way to use NEXORA
  ([0027](0027-herramientas-nativas-por-defecto.md)). Equivalence is their contract: a difference from the Python
  implementation is a defect, found by the comparison suites that run in continuous integration. This decision adds to it the
  rows of the [threat model](../threat-model.md), which run on both.
- The native packages have their own support matrix: Linux x86-64 and arm64, macOS Apple Silicon and Intel, and Windows x86-64,
  each with a `.sha256`. The release workflow builds and smoke-tests all five; the [platform support](../platform-support.md)
  page says what was checked and when.

### 2.4 Support period

**Unchanged:** only the latest published release of each component receives fixes, before and after 1.0. A window for the last
minor of 1.x is a commitment that one maintainer cannot keep without a second pair of hands, and a promise that is broken is
worse than one that is not made. It is reviewed with the first 1.y release.

### 2.5 Python 3.14 and the platforms

1. **CPython 3.11 to 3.14.** 3.14 is in the continuous integration matrix (the tests, the reference applications and the platform
   smoke test) and in the classifiers of `pyproject.toml`.
2. **The runners are pinned to the systems that decision 0021 names**: `ubuntu-24.04`, `windows-2025` and `macos-14`, not
   `*-latest`. GitHub offers no x86-64 Windows 11 image: `windows-2025` is Windows Server 2025, which shares its kernel and its API
   with Windows 11, so the CI on it is evidence for the API and not for the desktop. The native smoke test on a real Windows 11
   is recorded with its date in the platform support page.
3. **macOS: Apple Silicon is the target** (macOS 14 or newer, `macos-14`). Intel is built, smoke-tested on `macos-15-intel` and
   published, but is not in the target of 1.0: the decision's condition for it (both architectures in the CI of the whole suite) is
   not met, and it is better to say so than to promise it.

## 3. What this does not do

- It does not release 1.0.0. The maintainer publishes it when they decide to, through the
  [release process](../release-process.md); the gates of [readiness](../1-0-readiness.md) say whether he can.
- It does not freeze the human-readable text of messages, nor the experimental interfaces (LSP, MCP, the Python API).
- It does not add any feature. The only changes to the language text are the version number, the statement of the freeze and
  section 13.

## 4. Review of the reference applications

Done on 2026-11-07 by the assistant, under the delegation above. Each application was read, its `README` compared with what it
does, and `nex check`, `nex test` and `nex run` were run on all of them, in the Python implementation and in the native `nex`
built from this tree on Linux: the same standard output, the same standard error and the same status in the 17 runs
(`check` and `test` of each application, two runs of `textstats`, seven of `csvsummary` with the sample, four bad files, no grants
and a path outside what it declares, and two of `envreport`, with and without its grant). The tests of the repository check them too (`tests/test_reference_apps.py`, in
continuous integration on three systems and four Pythons). The findings are the five of section 2.2. The review found nothing
that blocks the freeze.

## 5. Consequences

- The specification says 1.0 and that it is frozen; `get_language_spec` reports `1.0`.
- A change to the frozen parts fails `nexora-release.yml` until it is made on purpose, with its decision and the frozen files.
- The migration guide says that moving to 1.0 changes nothing in a program that compiles with 0.12 or later.
- The readiness page has every gate with its evidence; the ones that still need something say what.
