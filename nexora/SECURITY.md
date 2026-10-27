# Security

This document explains what NEXORA protects today, what it does **not** protect, and how to report a problem.

NEXORA is an early-stage project that has not been audited. **We do not claim that it is safe
to run untrusted code with it.**

## Supported versions

Only the most recent version. Earlier versions are not maintained.

## How to report a vulnerability

**The private contact channel is the *Report a vulnerability* button in the *Security* tab of the
repository** (<https://github.com/xGlizyy/nexoralang/security/advisories/new>): the report reaches
whoever maintains the project privately, and it is only made public when there is a fix. The
*Private vulnerability reporting* feature is enabled in the repository (*Settings → Code security*).

> **Pending for whoever maintains the project:** state here a response time that can really
> be met, and replace this block with the new channel if it is ever decided to change it.

Until then, if you have direct access to whoever maintains the project, tell them privately.
**Do not describe a vulnerability in a public channel** before there is a fix.

A good report includes:

- The version (`nex --version`), the operating system and the Python version.
- The smallest `.nex` program or command that reproduces the problem.
- What happens and what impact it has.

There is no bug bounty programme.

## What is in scope

Any way of achieving, **through a `.nex` file or
through the arguments of `nex`**, any of the following is considered a security problem:

- Running Python code or system commands without the program's `uses process` declaration and the
  matching `--allow-process` grant.
- Reading or writing files, accessing a network origin, or starting a process **without** the matching
  `uses` declaration, explicit CLI grant and environment permission.
- Letting a program running in the web Playground or through the in-memory API access files, the
  network or external processes.
- Making `nex check` or `nex inspect` run the program they analyze.
- Having a text of the program interpreted as code instead of being treated as data.

Also of interest, although less serious, is any input that causes an internal error
(`internal error`, exit code `70`) or an unexpected exit of the process.

## What the design protects

These properties follow from how the language is built and **are checked by automated
tests** (`tests/test_security.py`, `tests/test_robustness.py`):

| Property | How it is achieved | What the test checks |
|----------|--------------------|----------------------|
| External actions are explicit | File, network and process operations require a program declaration, a user grant and a host that enables them. The API defaults to `NoHost`; the Playground worker uses it too | Missing declarations and grants fail; worker tests verify it does not accept permission fields |
| The interpreter does not evaluate Python code | It walks its own syntax tree. It does not use `eval`, `exec` or `compile` | The source code of every module is analyzed and any call to those functions is rejected |
| The analysis does not run | `nex check` and `nex inspect` end before the execution stage | A program that prints, divides by zero and enters infinite recursion is analyzed without any of that happening |
| Arguments are not code | `nex` only accepts file paths. There is no option to pass code | Arguments shaped like code are treated as names of files that do not exist |
| The language core does not touch the system | The parser, checker and interpreter ask `host.py`; only the CLI grants local operations | Core modules do not import system, network or process APIs |
| File writes are explicit | `write_file` requires `uses write`, `--allow-write` and an enabled local host | File permission tests verify all three parts are required |
| No external dependencies | Only the Python standard library is used | The list of dependencies is empty, and the modules only import from a closed list |
| Wrong inputs do not make the interpreter crash | Limits on nesting, on depth and on the number of errors | Truncated, mutated, random, binary, huge or extremely nested files produce diagnostics, not exceptions |

## What is **not** protected

- **NEXORA is not a sandbox.** The interpreter is a normal Python program,
  which runs with the permissions of whoever launches it. The properties above depend on the
  interpreter having no defects; there is no second barrier (process isolation, restriction of
  system calls) if it has them.
- **A process explicitly allowed by `--allow-process` runs with the user's operating-system
  permissions.** It can access files, the network and other resources available to that user; command
  and argument choices are not a sandbox boundary. Do not grant this permission to untrusted code.
  On Windows, a timeout stops the direct process but may not stop child processes it started.
- **An explicitly allowed network origin is not isolated from local services.** Only HTTPS requests to
  the declared origin are made, but if that origin resolves to a private address, the CLI does not
  block it. Only grant network access to programs you trust.
- **There is no limit on running time.** A program can take a long time.
- **There is no memory limit.** A program can build very large texts by concatenation.
  The limit of 1000 nested calls bounds recursion, not memory use.
- **There is no limit on the size of the input file**, nor on the size of the output.
- **The tests with random inputs are limited.** They go through a few thousand cases generated with
  a fixed seed. They are not an exhaustive search and do not replace an audit.
- **No external audit has been done**, nor any security analysis with specialized
  tools.
- **The output of a program is not filtered.** A program can write terminal control
  sequences. If you show the output of an untrusted program in a terminal, keep it in mind.

Consequently: running an unknown NEXORA program should not be able to read your files or
run other programs, but **it can use CPU and memory without limit**. If you need to run
untrusted code, do it inside an isolation provided by the operating system
(a container, a virtual machine, system resource limits).

## Supply chain

- The interpreter has no runtime dependencies.
- The development dependencies (`pytest`, `pytest-cov`, `ruff`) and the packaging one
  (`setuptools`) are downloaded from PyPI on installation. They are not pinned to exact versions or verified
  by *hash*.
- The packages of this project are published as `nexora-lang`, on PyPI and on npm. Any package
  called `nexora`, or any other name, on PyPI or another index **does not come from this project**.
