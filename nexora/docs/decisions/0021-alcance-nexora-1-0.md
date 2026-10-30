# 0021 — NEXORA 1.0 product scope and release criteria

- **Status:** accepted.
- **Date:** 2026-10-28.
- **Decision owner:** NEXORA maintainer.
- **Affects:** language scope, public interfaces, compatibility guarantees, supported platforms and
  the 1.0 release gate.
- **Related to:** [limitations](../limitations.md), [roadmap](../roadmap.md),
  [language specification](../language-spec.md), [security policy](../../../SECURITY.md).

## Executive summary

This decision defines NEXORA 1.0 as a **stable language and toolchain for small, single-process CLI
applications and local automation written and run by trusted operators**.

The scope includes checked execution, local modules, executable examples, explicit host
capabilities and a documented CLI. It excludes web servers, GUI applications, high-concurrency or
high-performance workloads, safety-critical use and treating the local interpreter as a sandbox.

This decision does not require every item in the design draft. A feature is part of 1.0 only when it
is named in the normative specification or required by an approved reference application.

## 1. Purpose and decision status

NEXORA needs a bounded promise for its first stable release. “1.0” should tell a user what kinds of
programs the project intends to support, which interfaces will remain compatible and what evidence
must exist before release.

This is the accepted product boundary for planning NEXORA 1.0. It describes the intended release
scope, not the current capabilities of 0.13.0. A release is not 1.0 until every gate in this
decision has evidence and the maintainer approves the release.

## 2. Current baseline

NEXORA 0.13.0 has its own syntax, static checker and reference interpreter. The CLI can check, run
and test programs. The implemented language includes local modules, arguments, standard input,
lists, records, `Option`, `Result`, refined types and runtime-checked contracts. Local file access,
outbound HTTPS GET and external process execution require declarations and explicit CLI grants.

The current project also has:

- Published Python and npm packages. The npm package launches the Python interpreter; it does not
  bundle a separate NEXORA runtime.
- A language server and configurations for multiple editors. Import resolution and UTF-16 position
  handling remain limitations.
- An experimental Python API and MCP integration.
- A public Playground with Check, Run and a debugger, using a Docker-backed worker. Its operational
  verification is not an adversarial container-escape audit.

Current limitations relevant to the 1.0 scope:

- No inbound HTTP server, concurrency model or broad framework/package ecosystem.
- No general execution-time or memory budget for the local CLI.
- Runtime-checked contracts are not static proofs. `trust` clauses are not verified.
- The local interpreter is not an OS sandbox. An explicitly permitted child process runs with the
  invoking user's OS permissions.
- The project is pre-1.0; the supported language and APIs may change incompatibly.

These facts define the starting point, not the release promise. The [limitations](../limitations.md)
and [roadmap](../roadmap.md) remain the detailed source for feature-by-feature status and must be
kept consistent with this decision.

## 3. Target users and product promise

### Target users

Developers who want to create small, inspectable tools for their own workstation, team or controlled
automation environment. They can review the source and understand which local capabilities a program
will use before granting them.

### Product promise

For a program using the documented 1.0 subset, NEXORA will:

1. Check the program before execution and report stable diagnostic identifiers for errors.
2. Execute it with the reference interpreter on the supported platforms.
3. Provide repeatable examples and a test command for checking expected program behavior.
4. Require explicit declarations and grants for supported host capabilities.
5. Preserve the meaning of documented language features across 1.x releases, subject to the
   compatibility policy below.

This promise does not mean that every program is correct, that contracts are formally proven, that
the interpreter is a sandbox, or that the program is immune to resource exhaustion.

## 4. Supported application profiles

| Profile | 1.0 status | Boundary |
|---------|--------------------|----------|
| Developer, administrative and personal CLI tools | In scope | A user starts a process, supplies arguments or input, and receives output or a documented file change |
| Local automation and short batch jobs | In scope | Intended for controlled inputs and trusted code; time-consuming work must have a documented cancellation path |
| Small multi-file programs | In scope | Uses local NEXORA modules; the 1.0 promise does not include a public third-party package registry |
| File transformation | In scope, with explicit grants | The program declares file access and the CLI operator grants the required paths |
| Outbound HTTPS GET | In scope, with explicit grants | The request is limited to the declared HTTPS origin; it is not a general HTTP client or server |
| External process invocation | In scope, with explicit grants | The executable is declared and granted; its effects are those available to the local user |
| Web servers, APIs and multi-user services | Out of scope | No inbound listener, service lifecycle, concurrency, deployment framework or availability target |
| GUI, mobile, embedded, kernel or hard real-time software | Out of scope | No corresponding UI toolkit, runtime target or timing guarantee |
| High-throughput or highly concurrent workloads | Out of scope | No latency, throughput or performance parity target is established |
| Safety-critical or formally verified software | Out of scope | Contracts, refinements and type checking do not constitute a proof of correctness |
| Arbitrary untrusted-code execution | Out of scope for the local runtime | Use an independently secured OS boundary; the language permission model is not a sandbox |

The Playground is a separate hosted evaluation surface. Its Docker worker and its operational
controls do not expand the set of applications supported by the local NEXORA runtime.

## 5. Features and interfaces included in 1.0

### Language and CLI

The 1.0 specification must enumerate the exact supported syntax and semantics. The initial stable
CLI surface is:

- `nex check` for static analysis.
- `nex run` for checked execution.
- `nex test` for executable examples.
- The documented exit codes, options, diagnostic codes/categories and stable machine-readable
  output formats for those commands.
- Local imports and their resolution rules.

The built-in test contract for 1.0 is `nex test` evaluating examples declared in NEXORA source.
This does not promise fixtures, mocks, a package-level test framework or a coverage tool for user
applications. If one of the approved reference applications needs those facilities, that need must
be resolved before the 1.0 scope is frozen.

Stable diagnostic codes, categories and structured fields must not change incompatibly in 1.x.
Human-readable message wording may improve, while the diagnostic identifier and machine-readable
contract remain stable.

### Editor tooling

The 1.0 release will support the core language server and the official VS Code extension. The
supported LSP feature set will include diagnostics, completion,
hover, definition/references, rename, symbols, signature help and formatting. In-scope local imports
must resolve, and positions must follow negotiated LSP encoding (including UTF-16 clients).

The Neovim, Helix and Emacs configurations may be documented as community-supported/best-effort
integrations, with tested client versions listed. The local statement debugger is available as
`nex debug` in the CLI. DAP and debugger integration through the language server are not included
in 1.0. The hosted Playground also retains its statement debugger.

### Experimental interfaces

These interfaces may remain experimental in 1.0 if that status is visible in their docs and package
metadata:

- Python APIs beyond the documented CLI entry points.
- MCP server and assistant-specific configurations.
- LSP methods and editor integrations not named in the supported feature set.
- Playground APIs, compiler backends, registries and frameworks not listed in this decision.

## 6. 1.0 support target

| Component | 1.0 support target |
|-----------|------------------------------|
| Python | CPython 3.11–3.14; every listed minor must pass CI and clean artifact-install tests |
| Windows | Windows 11, x86-64 |
| Linux | Ubuntu 24.04 LTS, x86-64 |
| macOS | macOS 14 or newer, Apple Silicon and Intel only if both are included in CI and native smoke testing |
| Node.js for npm | Node.js releases in Active or Maintenance LTS at the 1.0 release; publish the exact supported majors |
| PyPI | `nexora-lang` installs the interpreter and CLI into a supported Python environment |
| npm | `nexora-lang` is a launcher; a compatible Node.js version and supported Python runtime are both required |

This is the accepted support target, not a claim that NEXORA 0.13.0 has been verified on every listed
machine. Before 1.0, publish the exact Python and Node.js versions. Remove a runtime version when it
falls outside upstream security support, or document a short transition period. Architectures and
operating systems absent from the final matrix remain unsupported rather than implicitly supported.

Each OS family requires a native installation and smoke test in addition to CI. CI must test every
Python/OS pair that the project claims to support; a job on `*-latest` alone does not define a
versioned OS support promise.

## 7. Compatibility and lifecycle policy

1. **Before 1.0:** syntax and semantics can change incompatibly. Provide a migration guide from
   0.13.0 and automate a migration when the transformation is safe and deterministic.
2. **Within 1.x:** documented stable language features and CLI behavior retain their meaning. A
   breaking change to either requires a new major version.
3. **Bug fixes:** correcting behavior contrary to the published specification is a bug fix, even if
   a program relied on the old behavior. The release notes must explain the impact, and a regression
   test must pin the corrected rule.
4. **Diagnostics:** identifiers, categories, positions and fields marked stable are compatible
   surfaces; editorial wording is not byte-for-byte stable.
5. **JSON:** each public format has an explicit schema version. Incompatible shape changes require a
   new schema version.
6. **Deprecation:** removal of a stable feature requires a deprecation notice, migration guidance
   and a major version change.
7. **Support period:** before 1.0, publish which versions receive bug and security fixes and how
   long a release remains supported. Do not imply an SLA or maintenance term the project cannot meet.

## 8. 1.0 release gate

All criteria below must pass before calling the release generally available.

| Gate | Acceptance criteria | Evidence |
|------|---------------------|----------|
| Normative specification | Every 1.0 feature has grammar, semantics, type rules, runtime behavior and error cases documented; draft-only features are clearly marked | Specification review; executable examples; conformance tests |
| Reference applications | At least three reviewed apps cover a pure CLI, local files/modules and one explicitly granted capability (HTTPS or process execution) | Each app installs, checks, tests and runs from a clean environment on the supported OS matrix |
| Stable CLI | `check`, `run` and `test`, options, exit behavior, stable diagnostics and JSON contracts are covered | CLI compatibility suite and schema validation on every supported runtime |
| Module behavior | Local import resolution, visibility, cycles and error paths are specified and tested consistently in CLI and supported LSP workflows | Multi-module conformance corpus; editor integration checks |
| Runtime control | There is a documented interrupt/timeout path for expensive execution; output is bounded where captured; child processes are cleaned up after timeout or cancellation | Tests for timeout, Ctrl+C, output overflow, child cleanup and OS-specific memory behavior |
| Capability security | File, network and process operations require the documented declaration, grant and host capability; no sandbox claim is made for the local CLI | Security regression suite; reviewed threat model; no unresolved release-blocking security findings |
| Platform support | Full suite and package installation pass for every declared Python/OS pair; native smoke test on each supported OS family | CI artifacts and dated native test record |
| Package artifacts | Wheel, source distribution and npm package install from built artifacts; versions and metadata agree | Clean-environment artifact tests; hashes; tagged source commit |
| Release integrity | Changelog, migration guide, package hashes and a policy for yanking compromised artifacts are published; immutable package versions are never silently replaced | Release checklist attached to each tag |
| Documentation accuracy | README, specification, roadmap, limitations, installation, security and editor docs agree with the released implementation | Link checks; runnable docs examples; release review |
| Support process | Supported releases, issue reporting and vulnerability response process are public and realistic | Published support and security policies |
| Release blockers | No open P0 or P1 defect remains in the supported scope | Reviewed release issue list and maintainer sign-off |

### Severity definitions for the release gate

- **P0 — stop release:** data loss/corruption; an operation occurs without its required grant; a
  supported program can escape the documented host boundary; widespread inability to install or
  execute the supported subset.
- **P1 — fix before 1.0:** incorrect checking or execution for an in-scope program; a reproducible
  crash on ordinary supported input; broken compatibility, migration, or package installation on a
  supported platform.
- **P2 — may ship with a documented limitation:** behavior outside the agreed scope, cosmetic
  defects, or a missing feature that no approved reference application requires.

Coverage is evidence, not a release guarantee by itself. Keep the current 90% threshold, but require
the semantic, platform, security and artifact evidence above as separate gates.

## 9. Resource, security and Playground boundaries

### Local applications

NEXORA is not a sandbox. `Process.run` inherits the local user's permissions. An HTTPS grant
authorizes the declared origin; it does not provide process isolation or make malicious source safe.
The 1.0 product documentation must tell users to run only trusted programs or to use OS isolation
for untrusted code.

NEXORA 1.0 will provide a configurable wall-time bound and a documented interruption path. Captured
output must have a limit. Memory enforcement may be platform-specific; where the OS cannot enforce
it, the limitation and recommended controls must be stated. These controls reduce accidental
resource exhaustion; they are not a security boundary.

### Public Playground

The Playground is a separately operated service that executes submitted source. Its launch gate is
stricter than the local-language 1.0 gate: it requires container hardening, no network access for the
worker, resource limits, lifecycle cleanup, staging and production verification, and a separate
security review before claiming resistance to adversarial container escape. Passing ordinary
Check/Run/Debug smoke tests is not an escape audit.

## 10. Explicitly deferred

The following are not automatic 1.0 requirements. Each needs a concrete user case and a separate
design decision:

- User-defined generics, enums and exhaustive `match`.
- Maps, additional collection operations, range/text iteration, `break` and `continue`.
- A third-party package registry, dependency solver and lockfile.
- Inbound HTTP, web frameworks, long-running services, asynchronous execution and concurrency.
- Native compilation, a stable Python API, a stable MCP API or AI model execution.
- Static proof of contracts or claims that NEXORA prevents bugs better than other approaches.

A deferred feature moves into scope only if the product owner approves its use case, semantics,
implementation cost and effect on the release gates. The full design draft is not a release checklist.

## 11. Risks and mitigations

| Risk | Mitigation in this decision |
|------|------------------------------|
| “1.0” is mistaken for a universal general-purpose language | Publish the narrow use cases and exclusions beside the version |
| Users infer the local CLI is safe for untrusted source | State plainly that it is not a sandbox; keep OS isolation separate |
| Platform promises exceed actual testing | Gate each supported OS/Python pair on CI and native clean-install evidence |
| Language changes break existing programs | Normative spec, 1.x compatibility policy, migration guide and regression corpus |
| A missing library feature makes the target apps impractical | Select reference applications before freezing the 1.0 subset; add only features those apps need |
| Playground smoke checks are mistaken for a security audit | Maintain a separate hosted-service threat model and audit gate |
| Public docs contradict each other | Make documentation consistency a release gate and maintain one source of truth for feature status |

## 12. Resolution

NEXORA 1.0 targets small CLI applications and local automation written and run by trusted operators.
Web servers and multi-user services are out of scope. The support target is CPython 3.11\u20133.14 on
Windows 11 x86-64, Ubuntu 24.04 LTS x86-64 and macOS 14+ on each architecture that passes CI and
native smoke testing. File access, outbound HTTPS GET and process invocation remain in scope behind
explicit declarations and operator grants.

The roadmap is subordinate to this boundary: a planned feature is not automatically a 1.0 blocker
unless this decision or an approved reference application requires it. If the project later chooses
web services as a target, it must record a superseding decision covering the runtime, concurrency,
standard library, deployment and security model before expanding the 1.0 scope.
