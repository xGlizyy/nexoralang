# 0006 — Distinguishing feature: requirements are a verifiable part of the program

- **Status:** accepted
- **Version:** none yet. This decision sets a direction; it does not change the language by itself.

## Context

The design draft gathers many ideas (contracts, effects, `ai fn`, diagnostics in JSON,
regular syntax) and the roadmap phrases the central hypothesis in general terms: whether these
decisions "make the work of AI tools easier". Put like that, it cannot be checked
and it does not help choose what to build first. A concrete problem is needed.

### The chosen problem

When a function is written or modified with the help of an AI, **the requirements live in natural
language**: in the instruction the model receives, in a conversation, in a ticket or in a
comment. Four concrete failures come from that:

| Failure | Example |
|---------|---------|
| **Nobody checks them** | Someone asks "the discount can never raise the price" and nothing warns if the generated code breaks it |
| **They get lost between edits** | The next person or the next model that touches the function does not see the original conversation and can break the requirement without knowing it |
| **They are ambiguous** | "The percentage is valid" allows several readings; a written condition allows only one |
| **They make review more expensive** | Whoever reviews has to rebuild the intention before being able to judge whether the code meets it |

What an instruction in natural language cannot give is a mechanical answer to the question:
**"does this code still meet what was asked?"**

## Decision

The feature that distinguishes NEXORA is this:

> **The requirements, constraints and validation conditions of a function are written
> in the program itself, next to the function, and a deterministic tool checks whether they
> hold.** An instruction in natural language can explain them, but it is not the only place
> where they exist.

All the work on the language is ordered according to that feature. Concretely:

1. **A requirement that can be checked is written as a condition in the code**, not only in the
   instruction or in a comment. There are four kinds:

   | Kind | Question it answers | Mechanism |
   |------|---------------------|-----------|
   | Precondition | What does the function need to work? | `requires` |
   | Postcondition | What does the function promise when it ends? | `ensures` |
   | Constraint on data | Which values are valid for a type? | Refined types (`where`), planned |
   | Concrete case | What should it give with these inputs? | `example`, planned |

2. **The natural-language explanation accompanies the condition; it does not replace it.** A requirement
   can carry a sentence that says why it exists, and that sentence appears in the diagnostic when it is
   broken. A sentence without a condition does not count as a requirement.
3. **The check is deterministic.** No AI model decides whether a requirement holds: the
   same program with the same inputs always gives the same result.
4. **Every violation says which requirement failed, who broke it and with which values**: the
   call (precondition) or the function (postcondition). As text for people and as JSON for
   tools.
5. **Requirements are visible before editing.** `nex context` and `nex inspect` deliver them as
   data, so an agent receives them as constraints of the work and does not have to deduce them.
6. **Removing or weakening a requirement is a visible change.** If an edit deletes or relaxes a
   condition so that the program "passes", the tool must point it out, just as it points out an error.
7. **NEXORA never says that a requirement "holds" if it has only checked it on some
   runs.** Checking at run time detects violations; it does not prove that there are none.

## An example with what exists today

The instruction in natural language would be: *"Apply a discount to a price in cents. The
percentage goes from 0 to 100, and the result can never be negative or greater than the price."* In
NEXORA those requirements are written in the function:

<!-- nex:run -->
```nex
fn apply_discount(price_cents: Int, percent: Int) -> Int {
    requires price_cents >= 0
    requires percent >= 0 and percent <= 100
    ensures result >= 0 and result <= price_cents
    return price_cents * (100 - percent) / 100
}

fn main() -> Void {
    print(apply_discount(10000, 20))
    print(apply_discount(999, 0))
}
```

```text
8000
999
```

If a later edit, made by a person or by a model, changes the sign and turns the
discount into a surcharge, the requirement is still there even though the original instruction is no longer
anywhere. The program stops and says which promise was broken and with which values:

<!-- nex:fails exit=5 -->
```nex
fn apply_discount(price_cents: Int, percent: Int) -> Int {
    requires price_cents >= 0
    requires percent >= 0 and percent <= 100
    ensures result >= 0 and result <= price_cents
    return price_cents * (100 + percent) / 100
}

fn main() -> Void {
    print(apply_discount(10000, 20))
    print(apply_discount(999, 0))
}
```

```text
contract error[E4002]: Postcondition violated
 --> program.nex:4:5
  |
4 |     ensures result >= 0 and result <= price_cents
  |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 'apply_discount' breaks its own 'ensures' condition
  = note: 'apply_discount' finished, but its condition is false: ensures result >= 0 and result <= price_cents
  = note: It returned: result = 12000
  = note: It was called with: price_cents = 10000, percent = 20
  = note: In 'apply_discount', called at line 9, column 11.

error: program.nex: the program stopped because a contract was broken
```

Where this decision points, with a syntax that is **only illustrative and not decided**: every
condition with its explanation, a type that carries its own constraint and a concrete case that is
checked without writing `main`.

```text
type Percent = Int where value >= 0 and value <= 100

fn apply_discount(price_cents: Int, percent: Percent) -> Int {
    requires price_cents >= 0           "A price cannot be negative"
    ensures result <= price_cents       "A discount never raises the price"
    example apply_discount(10000, 20) == 8000
    return price_cents * (100 - percent) / 100
}
```

## What exists and what is missing

| Piece | Status |
|-------|--------|
| `requires` and `ensures`, checked on every call ([0004](0004-contratos-en-ejecucion.md)) | Implemented; **experimental** |
| Attribution of the violation (`E4001` to the call, `E4002` to the function) with the values | Implemented |
| Contracts visible to tools in `nex context` and `nex inspect` | Implemented |
| Contract diagnostics in JSON (`nexora.diagnostics/1`) | Implemented |
| Natural-language explanation attached to every condition | Does not exist |
| Concrete cases in the function (`example`) and a command that runs them | Does not exist; planned |
| Refined types (`where`) | Does not exist; it needs records or user-defined types first |
| Warning when an edit removes or weakens a requirement | Does not exist; it is not decided how to detect "weakening" |
| Evaluation of whether this really helps an AI | **It has not been done** |

> **Update (0.3.0).** [Decision 0007](0007-contratos-estables-y-tipos-refinados.md)
> implements three pieces of this table: contracts stop being experimental, every condition
> can carry its explanation and refined types exist over the built-in types. The up-to-date status
> is in the [roadmap](../roadmap.md#main-line-verifiable-requirements).

## How we will know whether it works

The feature is a hypothesis until it is measured. The minimal experiment:

- A set of tasks in which an agent modifies functions that have requirements.
- Two variants of each task: the requirements **only in the instruction**, or **also in the
  code** as conditions.
- Measures:
  - Edits that break a requirement and are detected before being delivered.
  - Edits that break a requirement and are not detected.
  - False alarms: requirements reported as broken when they are not.
  - Requirements removed or relaxed by the agent so that the program passes.

The [reference tasks](../ai-tooling.md#reference-tasks) are the starting point. Until
there are results, no page of the project should claim that NEXORA improves work with AI.

## What it does not aim to be

- **It is not formal verification.** It does not prove that a requirement holds for all inputs;
  it detects violations on the calls that run.
- **It does not replace tests.** A requirement says what must be true; a test chooses with which
  inputs to check it. Both are needed.
- **It does not make the AI write correct code.** It makes incorrect code noticeable, and
  noticeable early and with an explanation.
- **It does not cover all requirements.** Performance, user experience or style are not
  expressed as conditions on values.
- **It is not a new idea on its own.** Contracts have existed in other languages for
  decades. What NEXORA proposes is to make them the centre of work with AI: required in
  the unit that is edited, delivered as data to the tools, with the blame assigned and without
  a model deciding anything.

## Alternatives ruled out as the distinguishing feature

| Alternative | Why it is not the main feature |
|-------------|--------------------------------|
| **Functions resolved by a model (`ai fn`, `tool fn`)** | They are not deterministic, they already exist as libraries in other languages and they do not solve the problem of checking the code. They remain under research |
| **Declared effects (`uses`)** | Useful to know what a function touches, but secondary: they do not say whether the result is correct |
| **Diagnostics and outputs in JSON** | They already exist and are necessary, but they are the means through which requirements are communicated, not the end |
| **A syntax "easier for AI"** | It cannot be claimed without an experiment, and it brings nothing that a tool can check |

## Consequences

The order of work of the roadmap that has to do with this feature becomes the
following (in the [roadmap](../roadmap.md#main-line-verifiable-requirements), with the
status of each step):

1. Stabilize contracts and take them out of experimental (position in the code and name `result`).
2. Attach a natural-language explanation to every condition and show it in the diagnostic.
3. Concrete cases in the function (`example`) and a command that runs them without `main`.
4. Detect when an edit removes or weakens a requirement.
5. Refined types, when user-defined types exist.
6. The evaluation experiment, before presenting the feature as a proven advantage.

The website and the general documentation must present NEXORA starting from this problem, without claiming
results that have not been measured yet.
