# How to contribute to NEXORA

Thank you for your interest. This guide explains how to set up the environment, which checks a
change has to pass and how to keep the code, the specification and the examples in sync.

## Before you start

- **The project is distributed under the MIT licence** ([`LICENSE`](LICENSE)). By proposing a change
  you agree that your contribution is published under that same licence.
- **The repository is public** (<https://github.com/xGlizyy/nexoralang>) and its [issue
  tracker](https://github.com/xGlizyy/nexoralang/issues) is the contact channel. The steps of
  this guide that mention *pull requests* describe the intended flow.
- The project is at an early stage: the syntax may change. Before spending time on a
  new feature, check the [roadmap](docs/roadmap.md) and the
  [technical decisions](docs/decisions/README.md).

## Setting up the environment

You need Python 3.11 or newer. From the `nexora/` directory:

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on Linux and
macOS) and install the project with the development tools:

```bash
python -m pip install -e ".[dev]"
```

This installs `pytest`, `pytest-cov` and `ruff`. They are the only development dependencies; the
interpreter has no runtime dependency at all, and it must stay that way.

More detail and troubleshooting: [Installation](docs/installation.md).

## Checks that have to pass

Before proposing a change, all three have to finish without errors:

```bash
python -m ruff check src tests
python -m pytest
python -m pytest --cov
```

| Command | What it checks |
|---------|----------------|
| `python -m ruff check src tests` | Errors and oversights in the Python code |
| `python -m pytest` | All the tests: language, CLI, examples, documentation, security and robustness |
| `python -m pytest --cov` | The same, and it fails if coverage drops below the threshold set in `pyproject.toml` |

The same checks are defined in the continuous integration workflow
(`.github/workflows/nexora-ci.yml`, at the root of the repository).

What each test file covers: [Testing](docs/testing.md).

## Keeping everything in sync

In NEXORA the code, the specification, the examples and the documentation have to say the same thing.
Discipline is not trusted: **the tests fail if they get out of sync**.

| If you change… | You have to update… | Watched by |
|----------------|---------------------|------------|
| The behaviour of the language | `docs/language-spec.md` and the corresponding guide | `tests/test_docs.py` runs every program of the documentation and compares its output |
| The output of an example | The files of `tests/golden/examples/` | `tests/test_examples.py` |
| An error code | `_REGISTRY` in `diagnostics.py`, and the tables of `docs/language-spec.md` and `docs/diagnostics.md` | `tests/test_diagnostics.py`, `tests/test_docs.py` |
| A node of the syntax tree | `docs/inspect-schema.md` and the list in `tests/test_inspect.py` | `tests/test_inspect.py` |
| A command, an option or an exit code | `docs/cli-reference.md` | `tests/test_docs.py` |
| A keyword or a built-in function | A valid example in `examples/` that uses it | `tests/test_examples.py` |
| The version | Only `src/nexora/version.py` | `tests/test_docs.py`, `tests/test_cli.py` |
| A link or a heading of the documentation | The links that point to it | `tests/test_docs.py` |

### Programs in the documentation

A NEXORA code block in a Markdown file is checked if it is preceded by a marker
comment. For example:

````markdown
<!-- nex:run -->
```nex
fn main() -> Void {
    print("Hello")
}
```

```text
Hello
```
````

The available markers (`nex:run`, `nex:fails`, `nex:check-fails`, `nex:check-json`,
`nex:inspect`, `nex:valid`, `nex:body`, `nex:body-fails`) are described at the beginning of
`tests/test_docs.py`. A block that contains `fn main` and has no marker makes the tests fail.

### Updating recorded outputs

If a change modifies **on purpose** the output of an example or of a program of the documentation,
regenerate the files and **review the differences one by one** before accepting them:

```bash
# Linux and macOS
NEXORA_UPDATE_GOLDEN=1 python -m pytest tests/test_examples.py
NEXORA_UPDATE_DOCS=1 python -m pytest tests/test_docs.py
```

```powershell
# Windows (PowerShell)
$env:NEXORA_UPDATE_GOLDEN = "1"; python -m pytest tests/test_examples.py; $env:NEXORA_UPDATE_GOLDEN = $null
$env:NEXORA_UPDATE_DOCS = "1"; python -m pytest tests/test_docs.py; $env:NEXORA_UPDATE_DOCS = $null
```

Then run `python -m pytest` without those variables. Regenerating is not a way to "fix" a
failing test: if the output changed without you meaning it to, you have found a bug.

## Adding a feature to the language

Follow this order. Every step leaves something that can be checked.

1. **Decide and document.** If it is a design decision or an incompatible change, add a
   document to `docs/decisions/` (next free number) with the reason, the alternatives
   ruled out and the effect on existing programs.
2. **Write the specification.** Add the syntax to the EBNF grammar of `docs/language-spec.md`
   and describe its meaning: types, possible errors, and what is checked before and while
   running.
3. **Implement by stages**, in this order: `tokens.py` and `lexer.py`, `ast_nodes.py`, `parser.py`,
   `checker.py`, `interpreter.py`. The table "Where to add things" of
   [Architecture](docs/architecture.md#where-to-add-things) says what to touch in each case.
4. **Respect the separation of stages.** The rules for names and types go **only** in `checker.py`.
   The interpreter does not repeat them; it only checks what depends on the values.
5. **Write the tests** together with each stage: valid cases, invalid cases and edge cases.
6. **Add an example** in `examples/` and register it in `tests/test_examples.py` and in
   `examples/README.md`.
7. **Update the guides** (`docs/`), the `CHANGELOG.md` and, where applicable, `docs/limitations.md` and
   `docs/roadmap.md`.

A feature is not finished until it works, has tests and its documentation describes
its real behaviour. Do not document as existing something that is only planned.

## Modifying the specification

- `docs/language-spec.md` describes **what the interpreter does today**. What is planned goes in its section
  14 and in `docs/roadmap.md`.
- A change of the specification without a change of code is only valid if it corrects a text that did not
  describe the real behaviour well.
- The EBNF grammar has to correspond to the parser. If you add a rule to the grammar, add a
  parser test that exercises it.
- Keep the three status marks: implemented, **experimental** and **planned**.

## Adding a diagnostic

1. Choose the next free code of its range: `E10xx` lexical, `E11xx` syntax, `E2xxx`
   semantic or type, `E3xxx` runtime, `E4xxx` contract.
2. **Never reuse a code**, not even a retired one (`E1104`, `E2003`).
3. Add it to `_REGISTRY` in `src/nexora/diagnostics.py`, with its title and its category.
4. Document it in the tables of `docs/language-spec.md` (section 11.3) and of `docs/diagnostics.md`.
5. Write a test that triggers it and checks code, position and message.

Criteria for the message:

- The title (`CODES`) is fixed and short. The concrete explanation goes in `label`.
- Say what was expected and what was found.
- Point at the smallest fragment that identifies the problem.
- Add a suggestion (`hint`) **only if there is a rule that backs it**. A suggestion that can
  be wrong is worse than none.
- A user error must never be shown as a Python traceback, and a defect of the interpreter
  must never be shown as a user error.

## Code style

- Python 3.11, without external dependencies in `src/`.
- Whatever `ruff` accepts with the configuration of `pyproject.toml`. There is no required formatter.
- Names and comments of the code in English, like the messages of the language. The documentation, in
  English too.
- Comments explain the why, not what the code already says.
- Small modules with one responsibility. Only `cli.py` touches the operating system.
- Do not use `eval`, `exec` or anything that runs code from text: there is a test that prevents it.

## Tests

- Every test checks one behaviour: a result, a diagnostic or an exit code.
  Do not write tests that only walk through code.
- If you fix a defect, first add a test that reproduces it (the regression ones are in
  `tests/test_robustness.py`).
- Also test what has to **fail**, and that it fails with the right diagnostic.
- The behaviour of the CLI is tested through the real command, in a separate process, as well as
  through direct calls.

## Proposing the change

In the public repository:

1. Create a branch from the main one.
2. Make small, related changes.
3. Check that the three checks pass locally.
4. Describe in the proposal what changes, why, and how you tested it.
5. Add an entry in `CHANGELOG.md`, in the "Unreleased" section.

## Reporting a bug

Include the version (`nex --version`), the operating system, the smallest `.nex` program that
reproduces the problem, what you expected and what happened. If the message starts with
`internal error:`, run again with the environment variable `NEXORA_DEBUG=1` and attach the traceback.

Security problems are reported as [`SECURITY.md`](SECURITY.md) says, not in a public
issue.

## Conduct

Taking part in the project is governed by the [code of conduct](CODE_OF_CONDUCT.md).
