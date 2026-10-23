# 0012 — Type model, patterns, iteration and verifiable evidence

- **Status:** proposal under review. **Not accepted yet.**
- **Date:** 2026-10-19.
- **Work branch:** `feature/server-hardening`.
- **Related to:** [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md), [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md), [0004](0004-contratos-en-ejecucion.md), [0005](0005-diagnosticos-y-esquemas-json.md), [0006](0006-requisitos-verificables.md), [0007](0007-contratos-estables-y-tipos-refinados.md), [0008](0008-ejemplos-y-nex-test.md), [0010](0010-var-y-while.md) and [0011](0011-operaciones-sobre-textos.md).
- **Replaces:** none.
- **Implementation:** none. This document does not change the language, roadmap or official constraints.

## Evidence conventions

This ADR relies on code reading and documentation review. **No program, test, build, installation, migration or query has been executed.** The following markers separate what has been observed from what is proposed:

- **[V]** observed in the code or in the repository documentation.
- **[D]** documentation claim, consistent with the code read, but not checked by execution.
- **[I]** technical inference.
- **[P]** proposal subject to approval.
- **[?]** open issue pending evidence or decision.

---

## A. Context, goals and principles

### A.1. Differential purpose

The [decision 0006](0006-requisitos-verificables.md) establishes the NEXORA proposal: requirements, constraints and validation conditions of a function are a verifiable part of the program, not merely a ticket, comment or instruction. [Decision 0007](0007-contratos-estables-y-tipos-refinados.md) stabilized contracts, explanations and refined types; [0008](0008-ejemplos-y-nex-test.md) added executable examples and `nex test`; [0010](0010-var-y-while.md) added loops with `invariant` and `decreases`; [0011](0011-operaciones-sobre-textos.md) added type functions with contracts.

NEXORA should not be presented as a language that proves programs are correct. Its defensible proposal is more concrete:

> Verifiable requirements are explicit data of the program and of the analysis; deterministic tools indicate what they can check, what they have checked and what they have not; and an edit that removes or relaxes a requirement is marked as a visible change.

### A.2. How it helps an AI

An AI working on code needs to answer questions that it cannot answer by reading text alone:

1. What requirements does this function have before touching it?
2. What types, contracts, constraints and dependencies are relevant?
3. What requirements may be affected by the change?
4. Does the proposed modification respect the known constraints?
5. What checks have been executed and with what result?
6. What remains unchecked or uncertain?
7. Can it demonstrate that it has not broken a requirement, or only assert it?

NEXORA can help with questions 1, 2, 3, 5 and 6 through structured data and deterministic tools. Question 4 is the responsibility of the agent writing the change. Questions 6 and 7 require an explicit evidence contract: **“there are no diagnostics” is not enough**. Question 7 does not authorize saying “verified” if only some executions were checked.

### A.3. Current capabilities, proposals and hypotheses

| Category | What it includes | Status |
|---|---|---|
| **Current capability** | Static types `Int`, `Float`, `Bool`, `Text`, `Void`; contracts `requires`/`ensures` checked on execution; refined types over builtins; `example`; `while` with `invariant`/`decreases`; `nex check`, `inspect`, `context`, `symbols`, `test`; JSON; read-only MCP; playground with worker | Implemented and documented **[V]/[D]** |
| **Proposal in this ADR** | Type algebra; lists; records; enums; `match`; exhaustiveness; `Option`/`Result`; explicit input; modules; evidence and impact of requirements | Design, not implemented **[P]** |
| **Research hypothesis** | That requirements in code and NEXORA tools cause an AI to detect more violations, weaken fewer requirements and require fewer corrections | **Not measured** **[?]** |

The distinction matters: a proposed capability must not be described as if it already exists; a hypothesis must not be presented as a result.

### A.4. Principles that must be preserved

1. **Explicit semantics.** Every construct has a written and checkable rule; no hidden conversions, mutations or effects are introduced.
2. **Useful and stable diagnostics.** Stable code, exact position, concrete label, notes and suggestion only when a rule exists to justify it.
3. **Honest verifiability.** Distinguish what has been checked statically, what has been checked at runtime, what has been inferred and what has not been checked. Never assert more than what has been checked.
4. **Defense in depth.** The guarantees of the language are not the guarantees of the environment. The playground is not a sandbox by itself.
5. **Language-tooling-documentation coherence.** A feature is not finished if the lexer, parser, checker, interpreter, diagnostics, CLI, JSON/MCP, documentation, examples, tests and playground do not reflect it.
6. **Incremental compatibility.** Existing programs must keep working; JSON schemas grow additively unless a different decision is made.
7. **One single way to write things.** No redundant sugar or unnecessary special cases; `Option`/`Result` must not be compiler exceptions.

### A.5. Out of scope

This ADR does not decide typeclasses, algebraic effects, concurrency, macros, `ai fn`, `tool fn`, compilation to JavaScript/WebAssembly, package registry, optimization or a date for 1.0. It also does not implement any decision.

---

## B. Type model

### B.1. Current state **[V]**

- Types are strings: `INT = "Int"`, `FLOAT`, `BOOL`, `TEXT`, `VOID`; `VALUE_TYPES = (INT, FLOAT, BOOL, TEXT)` in `nexora/src/nexora/values.py`.
- `TypeRef` only stores `name: str` in `ast_nodes.py`; it has no type arguments.
- `TypeDecl` only represents refined types: `name`, `base: TypeRef`, `condition: Expr`, `message`.
- `Signature` uses `params: tuple[tuple[str, str | None], ...]` and `return_type: str | None` in `checker.py`.
- `BUILTINS` is a dictionary of `Signature` with strings.
- `Symbol.type` is `str | None`; `CheckedProgram.types` is `dict[int, str]`.
- `RefinedType` stores `base: str`, `root: str` and `chain`.
- `binary_result(operator, left: str, right: str)` decides arithmetic by comparing strings.
- `parser._type` requires a single `IDENT`; the lexer has no `[` or `]` tokens.
- There is no `types.py`: type logic lives in `checker.py`.

**Observed consequence [I]:** `List[T]`, `Option[T]`, `Result[T,E]`, records and enums cannot be represented without changing the previous interfaces. The architecture document itself recognizes that compound types will require their own representation and that this is the deepest change in the checker.

### B.2. Proposal **[P]**

#### B.2.1. D01 — Internal representation of the type model **[P]**

> **Status: proposal pending approval.** Not accepted. This subsection defines D01 and does not reopen D02 (nominal vs. structural), D03 (generic scope and inference) or D04 (refinements): it only fixes how types are represented, identified, compared, presented and migrated. The names `Type`, `TypeExpr`, `type_repr`, `types.py`, etc. are provisional design names; **they do not exist today in the code** and must not be presented as implemented.

**D01.1. Internal representation vs. textual presentation**

The source of truth must be a data structure, not a string. The string remains as one presentation form, never as the representation on which semantics are decided.

Responsibilities of the type model:

- build a type from the AST `TypeRef` and declarations
- compare types and decide assignability
- represent composed and refined types
- preserve a canonical textual form for JSON, diagnostics and tooling
- support migration while preserving compatibility

The representation must be explicit, structural and versionable. The textual form is a product of the model, not its definition.

**D01.2. Requirements for the model**

- type identity, equality and order must be explicit; they are not incidental properties of strings;
- type arguments must be first-class values in the model; e.g. `List[Int]`, `Option[Text]`;
- refined forms must be represented as a layer around a base type and a predicate;
- function types may be represented in the model before they become exposed as runtime values;
- string serialization must be canonical and deterministic for stable comparisons and diagnostics.

**D01.3. Equality and identity**

The model should separate:

- structural equality: same shape and same arguments;
- nominal identity: same declaration or same qualified name;
- canonical rendering: deterministic text for display and JSON.

Recommendation:

- primitive and built-in types compare structurally when appropriate;
- declared types use nominal identity with module-qualified names when modules exist;
- refined types compare by base type + predicate identity, not by text alone;
- composed types compare by constructor + arguments;
- function types do not become first-class values without explicit decision.

**D01.4. Canonical rendering and compatibility**

The current `type` field in JSON documents remains the canonical textual representation. It is not removed or redefined.

Additive rule:

- keep `type` as a human-readable and compatibility string;
- add a structured `type_repr` field when a tool needs to distinguish structure from text;
- `type_repr` is optional and additive; it may be ignored by older consumers;
- the exact vocabulary of `kind`, qualified names, arguments and structure is defined later, in coordination with D16 and schema versioning.

**D01.5. Migration plan**

The type model should be introduced in a single module without changing language syntax yet. The textual representation remains the presentation layer until the model is stable.

A safe migration path:

1. create a dedicated type module and representations;
2. keep the textual string as the compatibility layer;
3. migrate pure operations first: construction, identity, equivalence, root and display;
4. migrate the checker and interpreter after the model is stable;
5. add composed syntax later when the model is proven internally;
6. extend tooling and schemas at the end with additive `type_repr` fields.

**D01.6. Concrete impact areas**

The current components affected are:

- `values.py`: type constants and `VALUE_TYPES`; the new model must replace their use as the type table;
- `ast_nodes.py`: `TypeRef` and `TypeDecl`;
- `parser.py`: `_type` only accepts a single identifier; composed type syntax requires future changes;
- `checker.py`: `Signature`, `Symbol.type`, `CheckedProgram.types`, `RefinedType`, `binary_result` and assignability checks;
- `interpreter.py`: runtime value checks, contracts and refined checks;
- `diagnostics.py`: messages and positions that currently assume strings;
- `tooling.py` and `schemas.py`: `type` fields, type validation and schema documents;
- `cli.py`, `mcp_server.py` and the playground;
- documentation, examples and tests that refer to type strings.

**D01.7. Risk reduction strategy**

A low-risk migration reduces the impact of a large rewrite:

1. introduce the structured model in a single type module, without changing language syntax;
2. keep textual representation as the compatibility layer and initial value;
3. migrate the pure model operations first;
4. adapt the checker and interpreter afterward;
5. add compound types and `[...]` syntax only after the model is tested internally;
6. extend tooling and schemas last with additive `type_repr` fields.

**Future tests required (not executed in this task):**

- equality and difference of primitives, refinements, declarations and compounds;
- nesting (`List[Option[Int]]`) and wrong arity;
- canonical rendering and format stability;
- widening of refinements and rejection of the reverse direction without explicit construction;
- diagnosis with expected/found type and position;
- compatibility of `type` and validation of `type_repr` against schemas;
- regression of all existing programs and examples;
- performance of model operations on representative programs.

**D01.8. Alternatives and costs**

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| Keep strings and parse them when needed | Apparent minimum change | Equality, arity, unification and diagnosis are ad hoc; accumulated debt | Rejected as a foundation |
| Minimal structured algebra (`Type`/`TypeExpr`) | Correct, extensible, good for tooling | Requires migrating checker and tooling | **Recommended** |
| Structural model by default | Flexible | Weak identity and risky refactors | Deferred to D02 |
| Full Hindley-Milner | Fewer annotations | Complexity and difficult messages | Deferred; not an initial requirement |
| Typeclasses from the start | More expressive generics | Early resolution and complexity | Deferred |
| Formal verification of refinements | More guarantees | Outside the scope and current model | Not part of D01 |

Cost and complexity added by the recommended model:

- a type module and a deep change in `checker.py`;
- migration of signatures, symbols, expression types and refinements;
- adaptation of diagnostics, tooling and schemas;
- risk that the first version is too limited in generics, acceptable if the model permits growth.

Open risks:

- performance of comparison and substitution in large programs;
- ergonomics of inference and quality of messages;
- identity of declared types once modules exist;
- form and versioning of `type_repr`;
- equality of function types once they are introduced;
- possible need for type aliases and their relationship with identity.

**D01.9. Open questions of D01**

1. **Identity of declared types across files.** Recommendation: module-qualified name; exact form depends on D13. Open.
2. **`Void` as a type.** Recommendation: only as a function result; not as a value. Open to confirmation.
3. **Type alias.** Recommendation: an alias resolves to its canonical type and does not create new identity. Open; does not block D01.
4. **`Function` in the model.** Recommendation: represent the signature internally from the beginning, but do not expose it as a value type until functions are values. Open.
5. **`type_repr`.** Recommendation: additive, optional and versioned field; name and form are coordinated with D16. Open.
6. **Equality on type variables.** Recommendation: allow `==`/`!=` only for value types and not for functions. Open to confirmation.
7. **Scope of composed refinements.** Recommendation: represent them from D01; limit their predicates in D04. Open.

None of these questions prevents approving the main direction of D01; they are resolved during implementation or in decisions D02–D04 and D13/D16.

#### B.2.2. Compound types and generic constructors

- `List[T]`: built-in constructor, arity 1.
- `Option[T]`: prelude constructor, arity 1.
- `Result[T,E]`: prelude constructor, arity 2.
- User-defined records and enums have arity equal to the number of type parameters declared; initially they may be non-generic.
- Invariance by default on arguments: `List[Int]` is not assignable to `List[Text]`. Covariance is deferred until there is an explicit rule and, preferably, guaranteed immutability.
- No `Any`, no width subtyping and no implicit conversions.

#### B.2.3. Type variables and initial limits of genericity

- Explicit declaration: `fn f[T](x: T) -> T`, `type Box[T] = { value: T }`.
- No typeclasses in the first version.
- In the body of a generic function, a type variable `T` may only:
  - be passed to another function expecting `T`;
  - be returned;
  - be stored in a structure that accepts `T`;
  - be compared with `==`/`!=` only if structural equality is decided to be total for all value types. Recommendation: allow it for value types, not functions.
- Arithmetic on `T`, field access on `T`, ordering of `T` and any operation that requires a restriction are not permitted. This is a deliberate and documentable limitation.
- No higher-rank types, no Hindley-Milner generalization and no polymorphic recursion without annotation.

#### B.2.4. Nominal vs. structural types

For records and enums, the recommendation is **nominal**:

- type identity is its declaration (module + name), not the shape of its fields;
- two records with the same fields are not interchangeable;
- advantages: stable contracts, clear messages, controlled evolution, better base for agents and impact detection;
- disadvantages: no width subtyping; conversion between equivalent shapes must be explicit.

This is preferred over structural typing because NEXORA is about preserving contracts and honest evidence; weak identities complicate analysis and AI tooling.

**D02.1. Synthetic representation and compatibility**

The type model must support:

- canonical names for declared types;
- qualified names for modules;
- field and constructor names;
- type arguments in record/enum declarations;
- `void` as a special result type and not as a value;
- a `type_repr` representation that can be serialized without losing semantic structure.

**D02.2. Relationship with refining**

A refined type is not a new nominal type. It is a refinement of an existing type with a predicate, a label and a source span. It remains valid if the base type is valid. This still leaves open how strong the predicate language is for compound types, but it should remain a layer and not a different identity.

**D02.3. Allowed and deferred decisions**

- allowed in D01: type algebra, canonical names, additive `type_repr`, nominal identity for user types, type parameters, no implicit conversions;
- deferred: methods, traits, `Any`, structural subtyping, open records, polymorphic recursion, full higher-rank types.

**D02.4. Evidence pending**

- no implementation yet;
- no migration test of a project with records and enums;
- no checked ergonomics for user-defined nominal types;
- no final decision on `type_repr` vocabulary.

#### B.2.5. Records and enums in the planned model

- Records: `type Person = { name: Text, age: Int }`.
- Enums: `enum Result[T, E] { Ok(T), Err(E) }`.
- Constructors become ordinary values in the type system and comparison can use nominal identity.
- Pattern matching should work on constructors and record fields.
- No implicit widening or conversion between user-defined records and same-shape values.

**Impact on diagnostics**

- expected type and found type will be expressed using the new model;
- errors about missing fields or wrong constructors refer to the nominal declaration;
- JSON output should expose both `type` and `type_repr` so tools can compare structure without losing human readability.

### B.3. Alternatives

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| Type algebra with nominal records | Clear, stable, good for tooling | Requires migration | **Recommended** |
| Structural records by default | Less ceremony | Weaker contracts, more aliasing confusion | Deferred |
| Simple strings + ad hoc validation | Fast start | Deep structural debt | Rejected |
| Typeclasses from the beginning | Weaker restrictions on genericity | Complexity and semantics drift | Deferred |

### B.4. Consequences

**Positive:** better typing for compound data and tooling; clearer diagnostics; strong base for modules and requirements.

**Negative:** deeper migration of checker and schemas; more AST and parser work; more decisions needed for genericity and refinements.

### B.5. Evidence pending **[?]**

- no implementation of user-defined records/enums;
- no proof that nominal typing preserves the intended use of contracts;
- no benchmark of equality and canonical rendering in large programs;
- no evaluation of the cost of generic constructors in the checker.

---

## C. Patterns, exhaustiveness and sum types

### C.1. State of the art **[V]**

- There are no `match` expressions, enums or user-defined records yet.
- `if` is present and can be used for branching.
- There are type refinements, but not a pattern language.
- No `break`, `continue` or `for` loops exist.
- The language is currently built around `while`, `requires` and `ensures`.

### C.2. Proposed design **[P]**

#### C.2.1. Enums and constructors

- `enum` creates a nominal sum type with named constructors.
- Constructor names are in the same namespace as functions and types when needed.
- Constructor arity is explicit; `Some(T)` and `None` are ordinary enum variants.
- Example: `enum Option[T] { Some(T), None }`.
- Use `match` to discriminate over variants.

#### C.2.2. Patterns

Initial pattern grammar:

- literal;
- wildcard `_`;
- variable;
- constructor (`Some(x)`, `None`, `Ok(v)`, `Err(e)`);
- record (`Person { name: n, age: a }`);
- list (`[]`, `[x, ...rest]`, `[a, b]`);
- blocks and expressions in pattern positions are deferred.

`match` expression:

```text
match value {
    Some(x) => ...
    None => ...
}
```

Rules:

- `match` is an expression, not just a statement;
- each arm is a block or single expression;
- the expression must return a single result type overall;
- patterns are linear and not repeated;
- only one binding per variable path, unless the language later allows aliases;
- constructors, records and lists are patterns, not values;
- the first version should avoid guard clauses; guards are deferred.

#### C.2.3. Exhaustiveness and uncovered cases

- `match` as an expression requires exhaustiveness.
- Utility algorithm (Maranget style) over constructors:
  - `Bool`: `true`/`false`;
  - enums: all constructors;
  - records: all fields;
  - lists: `[]` and `cons`;
  - `Int`/`Text`: require wildcard;
  - refinements: require wildcard unless proven;
  - nested cases: recurse.
- Diagnosis with **witness**: “missing `None`”, “missing `Err(_)`”, “missing `[]`”.
- Pattern unreachable or redundant: decide between error and warning. Initial recommendation: error, because warnings infrastructure does not exist yet; revisit once available.
- If the checker accepts a `match`, the interpreter must not encounter an unmanaged case; if it does, it is an internal error.

#### C.2.4. `Option` and `Result`

They must be built on enums and `match`, not as exceptions of the language:

- `Option[T]` and `Result[T,E]` are ordinary enums in the prelude.
- There is no implicit `unwrap` and no exceptions.
- `?` for error propagation is deferred; first use `match`.
- Partial functions (`List.get`, `List.head`) declare `requires` and follow the current contract model; when `Option` exists, total variants may be added (`List.get_option`) without changing the semantics of partial functions.
- Contracts may use `Option`/`Result` as types; `ensures` may return `Ok(...)`/`Err(...)`.

### C.3. Alternatives

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| Enums + `match` + exhaustiveness | General, consistent, base for `Option`/`Result` | More initial work | **Recommended** |
| Special `Option`/`Result` | Less initial work | Inconsistent and hard to extend | Rejected |
| `match` as a statement only | Closer to current `if` | Worse ergonomics for `Option`/`Result` | Deferred; expression preferred |
| Optional exhaustiveness | Fewer initial errors | Leaves cases unmanaged | Rejected for `match` expression |
| Guards/or-patterns from the start | More expressive | Complicates exhaustiveness and reachability | Deferred |

### C.4. Consequences

**Positive:** `Option`/`Result` without special cases; safer code; diagnostics for missing cases; strong base for evidence of variant coverage.

**Negative:** complexity of the exhaustiveness algorithm; need for new AST nodes, tokens and diagnostics; risk of difficult messages; `match` as expression requires deciding its relationship with `if` statements.

### C.5. Evidence pending **[?]**

- no implementation or proof of the exhaustiveness algorithm;
- no validation of the ergonomics of `match` expression versus statement form;
- no decision on how `_` should be treated if it is still allowed as an identifier today;
- no measurement of the cost of nested patterns;
- no proof of the quality of witness messages for non-exhaustiveness.

---

## D. Collections and iteration

### D.1. Current state **[V]**

- There are no lists, maps, tuples or records.
- There is no `for`; `while` is used with a counter.
- Every `while` requires `decreases` (`E2021`) and may have `invariant`; the measure and invariants are checked at runtime (`E4005`, `E4006`).
- There is no `break` or `continue`.
- There is no time or memory limit in `nex`; the playground has timeout and limits.
- Recursive function termination is not proven statically; the call depth is limited to 1000 (`E3004`).

### D.2. Proposal **[P]**

#### D.2.1. Lists

- `List[T]` nominal, immutable and finite.
- Literals: `[1, 2, 3]`, `[]`; `[]` requires annotation if it cannot be inferred.
- Essential operations: `List.length`, `List.get`, `List.append`, `List.concat`, `List.contains`.
- `List.get(xs, i)` is partial and declares `requires 0 <= i and i < List.length(xs)`; the contract is checked at runtime. When `Option` exists, a total variant may be added.
- No element mutation; `var` may reassign the variable to another list, but not mutate the original list.
- Structural equality; `to_text`/`print` with canonical representation.

#### D.2.2. `for` over lists

```text
for x in xs {
    ...
}
```

- `xs` is evaluated once and must be `List[T]`.
- `x` is immutable and has type `T`.
- The body is a block with its own scope.
- It does not require `decreases`: a list is finite by construction.
- It may have `invariant` (same semantics as `while`), but not `decreases`.
- There is no `break` or `continue` in the first version.
- No `for` over ranges or `Text`; that would require `Range` or an explicit conversion and would be a special case.

#### D.2.3. Termination and guarantees

| Guarantee | Type | What may be asserted |
|---|---|---|
| `for` over `List[T]` immutable and finite | Structural | Terminates if the list is finite; does not promise speed |
| `while` with `decreases` | At runtime | The measure is checked; it is not proven statically |
| Recursion | Execution limit | Stops with `E3004`; no termination proof |
| Program terminates but takes time | Documented | May consume time/memory; playground times out; `nex` does not |
| Division by zero, overflow | At runtime | Not detected statically |

**Important:** “terminates” does not mean “terminates quickly.” A `for` over a huge list may take time. The playground cuts it off; `nex` has no time limit. This must not be promised more strongly.

#### D.2.4. `break` and `continue`

Recommendation: **do not introduce them initially**.

Reasons:

- `continue` is relatively simple, but adds a control path that invariants must tolerate.
- `break` invalidates the reasoning “the loop ended because the condition is false”; any postcondition depending on the exit condition becomes invalid.
- To make `break` verifiable, an explicit exit condition or loop value would be needed, which is another construct.
- There is no demonstrated need; it can be written with `while`, condition or `return`.

If added later, they must have documented semantics, interaction with `invariant` and tests proving they do not break termination.

### D.3. Alternatives

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| Immutable lists | No aliasing; simple contracts and termination | Copy cost; may be slow | **Recommended** |
| Mutable lists | Intuitive performance | Aliasing, contracts and termination become complex | Deferred |
| `for` over ranges | Convenient | Another special case; no `Range` type | Deferred |
| Iterators/lazy evaluation | Powerful | Termination and effects are hard to reason about | Deferred |
| `break`/`continue` from the start | Familiar | Breaks invariant reasoning | Deferred |

### D.4. Consequences

**Positive:** clear and terminating iteration; lists as base for `Input`, stdlib and data; `for` without mandatory measure; fewer special cases.

**Negative:** immutability may cost; some algorithms are more verbose without `break`; `List.get` partial requires contracts; the stdlib will need more functions.

### D.5. Evidence pending **[?]**

- no measurement of the cost of immutable lists in the interpreter;
- no validation that `for` without `break`/`continue` is sufficient for the target tasks;
- no decision on the internal representation (tuple, persistent list, etc.);
- no proof of the ergonomics of partial `List.get` versus `Option`;
- no measured impact of `for` on the playground.

---

## E. Input, effects and testability

### E.1. Current state **[V]**

- A NEXORA program can only compute and write with `print`; there is no keyboard input, arguments, files or network access.
- `main` cannot have parameters (`E2013`) and must return `Void` (`E2004`).
- The playground executes the worker in an empty environment; there is no global server state.
- `nex test` evaluates `example` without executing `main`.
- The interpreter does not use `eval` or `exec`; security tests check this.

### E.2. Proposal **[P]**

#### E.2.1. Explicit input

Introduce a prelude type `Input`:

```text
type Input = {
    args: List[Text],
    stdin: Text,
}
```

The program may declare:

- `fn main() -> Void` (compatibility), or
- `fn main(input: Input) -> Void`.

The runtime builds `Input` with arguments and standard input. There is no global `read_line()`, environment variables, files or network.

- `nex run file.nex -- arg1 arg2` and standard input feed `Input`.
- `nex test` builds an empty `Input` by default; functions requiring input are tested by passing an explicitly built `Input` in an `example` when records exist.
- The playground adds an `input` field to the request and passes it to the worker; it still has no access to files/network.
- `Text.lines(text) -> List[Text]` or an equivalent stdlib operation processes `stdin`; no special case for `Input`.

#### E.2.2. Input errors

- Missing or invalid input is represented by `Option`/`Result` when available; otherwise, by contracts and valid values.
- No language exceptions are thrown.
- `Int.parse`/`Float.parse` already have `requires` and `E4001`; this model is kept.
- Input errors must be data, not hidden effects.

#### E.2.3. Explicit effects without a formal effect system

In the first version, no algebraic effect system is introduced. The following remain explicit:

- `print`: output.
- `Input`: input injected as a parameter.
- Runtime errors: `E3001`–`E4006`, documented.
- No files, network, processes, environment variables or clock.

An effects system (`uses`) may be explored later; it is not necessary for the differential proposal and would add annotation cost.

### E.3. Alternatives

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| Explicit `Input` | Testable, reproducible, safe | Changes `main` or requires two forms | **Recommended** |
| Global `read_line()` | Convenient | Hidden state, not testable, unsafe | Rejected |
| `IO` monad | Explicit effects | Too heavy for the current language | Deferred |
| Effects system `uses` | Documents effects | Annotation burden and analysis cost | Deferred |
| Environment variables | Convenient for configuration | Secrets and nondeterminism | Rejected for the language |

### E.4. Consequences

**Positive:** reproducible tests; playground with controlled input; no global state; a base for `nex test` on functions with input.

**Negative:** two ways to define `main`; need for `Input` and records; interactive/streaming input is not covered; stdlib needs text operations.

### E.5. Evidence pending **[?]**

- exact `Input` API is not approved;
- no decision between `stdin: Text` and `stdin: List[Text]`;
- no validation of compatibility between `main()` and `main(input)`;
- no playground input interface designed;
- no measured cost of injecting input into `nex test`.

---

## F. Modules and visibility

### F.1. Current state **[V]**

- A program is a single file.
- `nex context` and `nex symbols` describe a single file.
- There are no imports, exports, visibility, namespaces or project concept.
- The checker resolves names in a single global space plus local scopes.
- `nex inspect`, `context`, `symbols` and MCP have no module concept.

### F.2. Problems to solve before implementation

1. **Imports and exports:** what is imported, under what name and how it is resolved.
2. **Visibility:** `pub`/private; what is exported by default.
3. **Dependencies and cycles:** graph, topological order, cycle rejection.
4. **Name resolution:** qualified names, `from` imports, aliases, conflicts.
5. **Project organization:** root, manifest, paths, stdlib.
6. **Caches and invalidation:** content hash, interface fingerprint, dependency graph.
7. **Tools:** `inspect` per file, `context`/`symbols` per project, stable IDs, graph.
8. **Security:** stdlib imports vs. user code; no arbitrary file access.

### F.3. Proposal **[P]**

- **File = module.** Default name: the file name; optional `module a.b.c` declaration.
- **Imports:** `import a.b.c`, `from a.b.c import f, Type`, alias `import a.b.c as c`.
- **Visibility:** `pub` on functions and types; private by default. No `pub` on local variables.
- **No wildcard imports** in the first version; no re-export; no cycles.
- **Resolution:** qualified names by default; `from` introduces names; conflicts = error.
- **Project:** root detected by `nexora.toml` (or `nex.project`) with name/version; no package registry in 1.0. Stdlib modules resolve from the installation.
- **Order:** acyclic graph, topological order; no module initialization with effects (only declarations).
- **Cache:** not implemented in the first phase; designed with content hash + interface fingerprint + dependency graph. Conservative invalidation: if a public interface changes, dependent modules are reanalyzed.
- **Tools:** `nex inspect` remains file-based; `nex context`/`symbols` accept file or project; add `module`, `imports`, `exports`, `dependencies`, `dependents`, `cycles`.

### F.4. Tool impact

| Tool | Today | With modules |
|---|---|---|
| `nex inspect` | AST of one file | AST of one file + `module`, `imports`; still local |
| `nex context` | Summary of one file | Summary of project or file; call graph between modules; public API |
| `nex symbols` | Symbols of one file | Symbols of the project; IDs with module; visibility; filters |
| MCP | 7 file-level tools | Add `project_context`; the rest keep compatibility |
| JSON | File-level schemas | Additive fields; new project schema if needed |

### F.5. Safe implementation sequence

1. **Now:** decide module semantics, visibility, cycles, resolution and manifest shape.
2. **After type/pattern work:** add `module`/`import`/`from`/`pub` to the lexer/parser/AST.
3. **Checker:** module table, resolution, visibility, cycles.
4. **Project loader:** root, manifest, topological order, stdlib.
5. **Tools:** project-level context/symbols, IDs, graph.
6. **Cache:** only when project analysis is stable and measurable.

### F.6. Alternatives

| Alternative | Advantages | Disadvantages | Consequence |
|---|---|---|---|
| File = module, explicit imports | Clear, tool-friendly | More syntax | **Recommended** |
| Implicit modules by path | Less syntax | Collisions and ambiguity | Rejected |
| Flat global namespace | Simple | Does not scale | Rejected for 1.0 |
| Allowed cycles | Flexible | Initialization and analysis complexity | Rejected initially |
| Package registry | Ecosystem | Out of scope | Deferred |
| Wildcard imports | Convenient | Conflicts and difficult analysis | Deferred |

### F.7. Consequences

**Positive:** stdlib possible; real projects; graph for AI; explicit public API.

**Negative:** deep change in checker, tooling, schemas and CLI; need for manifest and cache; risk of resolution complexity.

### F.8. Evidence pending **[?]**

- no validated design of manifest or name resolution;
- no measured cost of project analysis;
- no tested cache invalidation;
- no decision if `nex inspect` should accept projects or only files;
- no evaluation of impact on the playground (which executes a single file).

---

## G. Vertical architecture of features

### G.1. Layers that must remain coherent

For each new feature, the change must pass through these layers:

| Layer | Artifacts | What it must satisfy |
|---|---|---|
| Lexical | `tokens.py`, `lexer.py` | Tokens, reserved words, positions |
| Syntax | `ast_nodes.py`, `parser.py` | Immutable nodes with `Span`, error recovery |
| Types | `checker.py` | Rules, signatures, symbols, return paths, diagnostics |
| Execution | `interpreter.py` | Semantics, values, runtime errors, contracts |
| Diagnostics | `diagnostics.py` | Stable codes, category, label, notes, suggestion |
| CLI | `cli.py` | Command, formats, exit codes |
| JSON/MCP | `schemas.py`, `tooling.py`, `mcp_server.py` | Schema, document, parity, read-only |
| Documentation | `language-spec.md`, topical docs, ADR | Semantics and limits |
| Examples | `examples/`, docs | Executable and with expected output |
| Tests | `tests/` | Positive, negative, boundary and regression |
| Playground | `worker.py`, `server/src/playground/` | Same semantics, same limits, same security |

### G.2. Definition of “finished”

A feature is finished when:

1. It has semantics written in the specification and in an ADR or design document.
2. The lexer/parser recognize it and produce nodes with position.
3. The checker types it and diagnoses its errors.
4. The interpreter executes it with the documented semantics.
5. It has stable diagnostic codes and messages with position.
6. `nex check`, `inspect`, `context` and `symbols` represent it correctly.
7. JSON schemas are updated additively and validate the real output.
8. The CLI, API and MCP return the same document when they share a capability.
9. There are executable examples and synchronized docs.
10. There are positive, negative, boundary and regression tests.
11. The playground executes it with the same limits and without weakening safety.
12. Existing programs continue to work or a documented migration exists.

### G.3. How to avoid tooling falling behind

- **Schema first:** design the node/JSON form before implementing the parser so checker and tooling do not invent incompatible shapes.
- **Parity test:** every feature must have a test comparing CLI/API/MCP and interpreter output.
- **`capabilities.features`:** declare what is supported and what is not, so an agent cannot hallucinate.
- **Executable docs:** examples in the specification are run in tests; otherwise the mismatch is detected.
- **Prohibition of empty fields:** if a tool cannot represent a feature, the feature is not finished.
- **Schema review:** any new field is added at the end; any removal requires a schema version bump.

### G.4. Phase matrix

| Phase | Lexer/parser | Types | Interpreter | Diagnostics | CLI/JSON/MCP | Docs/examples | Tests | Playground |
|---|---|---|---|---|---|---|---|---|
| Base types | — | `Type` | — | type codes | `type_repr` | spec | unit tests | — |
| Lists + `for` | `[` `]`, `for` | `List[T]`, `for` | immutable lists | index/type errors | inspect/context/symbols | examples | boundaries | yes |
| Records | `type X = { ... }` | nominal, fields | immutable values | field errors | symbols/fields | examples | negatives | yes |
| Enums + `match` | `enum`, `=>`, patterns | variants, exhaustiveness | match | witnesses | inspect/context | examples | exhaustiveness | yes |
| `Option`/`Result` | — | prelude | constructors | — | requirements | examples | contracts | yes |
| Input | `Input` | record | `main(input)` | invalid input | API/worker | examples | reproducibility | input |
| Modules | `module`, `import`, `pub` | module table | load | cycles/visibility | project_context | project | graph | limits |

---

## H. AI-assisted development and evidence

### H.1. Current state **[V]/[D]**

- The CLI, Python API and MCP share `tooling.py`; MCP is read-only.
- `nex context` delivers signatures, contracts, variables, calls, callers, examples and loops.
- `nex symbols` delivers symbols, references, types and builtins with contracts.
- `nex inspect` delivers the AST with types as strings.
- `tests/tooling_tasks.py` defines nine reference tasks; `tests/test_tooling_tasks.py` checks them against the real tools.
- There is no ID-based requirements document, no impact analysis, no `checked`/`not_checked` evidence, no stable symbol IDs, no project graph and no structured types.
- The Python API is experimental; schemas are versioned and additive.

### H.2. Incremental proposal **[P]**

| Step | What to add | Depends on | Value for the agent |
|---|---|---|---|
| 1 | structured `type_repr` + stable IDs in `inspect`/`symbols`/`context` | Type model | stable references and machine-readable types |
| 2 | `nexora.requirements/1`: inventory of contracts, refinements and examples with ID, condition, explanation, span, provenance, checking status and dependencies | Types + contracts | understand requirements before editing |
| 3 | `evidence`: `checked`, `not_checked`, `assumptions`, `source_hash`, `tool_version` | Steps 1-2 | honesty about what was checked |
| 4 | `nexora.impact/1`: semantic diff, affected requirements, certainty level, checks and limits | Requirements + call graph | identify impact of a change |
| 5 | `nexora.project_context/1`: modules, imports, exports, dependencies, cycles, public API | Modules | analysis of real projects |
| 6 | `capabilities.features`: support/no-support matrix | Everything | avoid hallucinations |

No duplication is proposed for `nexora_check` (already exists), `nexora_types` (just extend `inspect`/`symbols`) or `nexora_run` in MCP (execution must be explicit and isolated).

### H.3. Identifying affected requirements

Impact analysis must combine:

- **Signature changes:** parameters, return value, types, visibility.
- **Contract changes:** `requires`/`ensures` added, removed or modified.
- **Refinement changes:** condition, base, chain.
- **Body changes:** calls, variables, branches, loops.
- **Call graph:** direct and transitive callers.
- **Propagation of requirements:** an `ensures` of one function may be an implicit `requires` of its callers; the analysis must state this, not invent it.
- **Certainty level:** `definitely_removed`, `definitely_added`, `changed_unproved`, `possibly_weakened`, `possibly_strengthened`, `unchanged`.
- **Honesty rule:** do not use `proved_weakened` unless a decidable fragment proves it.

### H.4. Explaining relationships and separating evidence

An impact document should include:

```json
{
  "schema": "nexora.impact/1",
  "base": {"source_hash": "…"},
  "current": {"source_hash": "…"},
  "changes": [
    {"kind": "contract_removed", "requirement_id": "…:requires:0", "assessment": "definitely_removed"},
    {"kind": "contract_changed", "requirement_id": "…:ensures:0", "assessment": "possibly_weakened",
     "reason": "the condition text changed; implication is not proved"}
  ],
  "affected": {"definitely": ["…"], "possibly": ["…"], "unknown": ["…"]},
  "checks": [
    {"name": "types", "status": "passed"},
    {"name": "exhaustiveness", "status": "passed"},
    {"name": "contracts", "status": "not_checked", "reason": "requires execution"}
  ],
  "limitations": ["weakening is conservative; only a decidable fragment is proved"]
}
```

The separation is mandatory:

- **Verified:** what a deterministic tool has checked.
- **Inferred:** what is deduced from the graph or diff, with its certainty level.
- **Unresolved:** what depends on execution, human decisions or undecidable properties.

### H.5. Diagnostics, coverage and regressions

- Diagnostics with stable code, position and `related`.
- Coverage of requirements, not just coverage of code: which contracts were exercised in `nex test`/`nex run`.
- Regressions: comparison of diagnoses/results between versions.
- `nex test` may report which examples cover which requirements; it must not claim total coverage.
- An agent must be able to see “0 diagnostics” and “contracts not checked” at the same time.

### H.6. Compatible changes without claiming correctness

The tools may:

- provide constraints and requirements;
- propose a structured diff;
- point out conflicts;
- execute authorized checks;
- return evidence and limits.

The tools **must not**:

- apply changes without authorization;
- say “correct” or “verified” without evidence;
- hide that a contract was checked only at runtime;
- execute untrusted code through MCP.

### H.7. Empirical evaluation plan

Start from the nine tasks in `tests/tooling_tasks.py` and extend to families:

| Family | Task | What it measures |
|---|---|---|
| A. Modification with requirements | Change a formula while preserving `ensures` | Preservation |
| B. Invariants | Change a loop while preserving `invariant`/`decreases` | Reasoning |
| C. Deliberate regression | Introduce a bug that violates a contract | Detection |
| D. Understanding | Who calls whom and what do they promise? | Tool use |
| E. Weakening temptation | “Make it pass”; the easy path is deleting a contract | Honesty |
| F. Multi-file | Change a function used in several modules | Impact |

**Conditions:** reference language with tests; NEXORA without tools; NEXORA with static tools; NEXORA with tools + execution; reference with equivalent contracts/tests.

**Metrics:** violated requirements detected/not detected; false positives; contracts removed/weakened; task success; time/tokens/calls; diagnostic quality; honesty.

**Controls:** models fixed by version, temperature/budget fixed, repetitions, randomized order, blind evaluator, hidden tests, publication of all results, pre-registration of thresholds.

**Publication criteria:** do not claim superiority without data; publish negative results; separate hypotheses, observations and conclusions; indicate limits (sample, model, task, novelty of NEXORA).

**Nothing of this has been executed.** There are no results.

---

## I. Security and isolation

### I.1. Guarantees of the language vs. guarantees of the environment

| Level | Guarantee | Limit |
|---|---|---|
| Language | No files, network, processes, environment variables, `eval` or `exec`; only computation and `print` | A bug in the interpreter could break it |
| `nex` CLI | Executes with the user’s permissions | No time/memory limit; not a sandbox |
| Playground worker | Separate process per request; empty environment; `-I`; output/text limits; external timeout | Not a sandbox; on Windows there are no POSIX limits |
| Container | Configuration such as `--network none`, `--read-only`, `--cap-drop ALL`, `--user 65534`, etc. | **Not tested**; depends on Docker/kernel |
| Service | Origin, rate limit, size, CSP, output as text | Does not eliminate exhaustion or defect risks |

### I.2. Risks of the playground

- **Resource exhaustion:** time, memory, CPU, output; external timeout helps, but is not isolation.
- **Interpreter bug:** malicious code could exploit a flaw; the language is not a sandbox.
- **Container:** escaping the container or kernel; badly configured Docker; mutable image by tag; privileged Docker daemon.
- **Server user:** being in the `docker` group is equivalent to administrator privileges; a compromise of the web server controls the machine.
- **Cache/cleanup:** orphaned containers after a crash; the server does not look for them on startup.
- **Output injection:** output is treated as text and written with `textContent`; this must be preserved.
- **CSRF/origin:** `Origin` validation is required; CORS limited.
- **Abuse:** rate limit per client, but IPv6/distributed networks; no CAPTCHA in the playground.
- **Secrets:** the worker must continue with an empty environment; never pass `.env` or credentials.

### I.3. Tests required before public exposure

Not executed in this task:

1. POSIX limits for memory, CPU, files, processes and wall-clock on Linux/macOS.
2. Worker in a container: no network, read-only, unprivileged user, `--init`, memory/CPU/PIDs limits.
3. Timeout and cleanup of containers; `docker rm -f` and confirmation with `docker ps`.
4. Server crash and orphaned containers.
5. Missing image and `--pull never`.
6. Concurrency and queue; 503 `busy`.
7. Origin/CORS/CSP; output with HTML/JS.
8. Fuzzing of parser/checker/interpreter and truncated input.
9. Memory exhaustion during analysis and execution.
10. Real isolation with Docker/kernel versions; validating the command is not enough.

### I.4. Deployment gate

The playground must remain disabled by default (`PLAYGROUND_ENABLED=false`) and must not be exposed publicly until the previous list is completed. In production, the server already requires the accepted container command if the playground is active; even so, **configuring the command does not prove isolation**. **[V]/[D]**

---

## J. Decisions, alternatives and open questions

> No new decision in this table is approved. “Previously decided” refers to ADRs already accepted that this document does not reopen.

| ID | Topic | Proposed recommendation | Alternatives | Reason | Cost/risk | Pending evidence | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| D01 | Internal representation of types | Structured model `Type` + `TypeExpr`; strings only for presentation; structural/nominal identity; additive `type_repr` | Keep strings; HM/typeclasses from the start | Correctness, nested types, diagnostics and tooling | High (checker/tooling migration) | Prototype of equality/display, migration, performance and `type_repr` stability | — | **Proposal pending approval** |
| D02 | Nominal vs. structural records | Nominal by default; structural explicit later | Structural by default | Stable contracts, clear messages | Medium | Ergonomics, migration | D01 | Proposal |
| D03 | Generics and inference | First-order parameters; no typeclasses; local inference + unification | HM; typeclasses; no generics | Balance of power and cost | High | Usability, messages | D01 | Proposal |
| D04 | Refinements over compounds | Pure/total predicates; static constants + `T(x)` | Full contracts; formal verification | Keep current guarantee and honesty | Medium | Predicate language, performance | D01 | Proposal |
| D05 | Enums/tagged unions | `type X[T] = enum { ... }`; namespaced constructors | global `enum`; sealed classes; special cases | Generality and consistency | Medium | Ergonomics, collisions | D01 | Proposal |
| D06 | Pattern matching | expression `match` with patterns and blocks | statement `match`; visitor | Base for `Option`/`Result` | High | Ergonomics, AST, parser | D05 | Proposal |
| D07 | Exhaustiveness | Mandatory; witness; unreachable is initial error | Optional; warning | Avoid unmanaged cases | Medium | Quality of witnesses, false positives | D06 | Proposal |
| D08 | Lists | Immutable, finite, `List[T]` | Mutable; persistent; lazy | No aliasing; simple termination | Medium | Performance, memory | D01 | Proposal |
| D09 | `for` and termination | `for` over `List[T]`; optional `invariant`; no `decreases` | Ranges; iterators; `for` with measure | Clear structural termination | Medium | Sufficiency, performance | D08 | Proposal |
| D10 | `break`/`continue` | Do not introduce initially | Introduce both; only `continue` | Avoid breaking invariants/exit semantics | Low/medium | Real demand, exit semantics | D09 | Proposal |
| D11 | Input | Explicit `Input`; `main()` or `main(input)` | global `read_line`; IO monad | Testability and safety | Low/medium | API, stdin, playground | D08, D02 | Proposal |
| D12 | Errors | `Option`/`Result` as enums; `?` later | Exceptions; only contracts | Consistency and composition | Medium | Ergonomics, `?` | D05-D07 | Proposal |
| D13 | Modules | File = module; `import`/`from`; `pub`; no cycles | Implicit; flat; cycles | Real projects and stdlib | High | Resolution, tooling, cache | D01-D12 | Proposal |
| D14 | Project and cache | Minimal manifest; cache by content + interface + graph | No project; cache by mtime | Project analysis | Medium | Invalidation, performance | D13 | Proposal |
| D15 | Requirements and impact | `requirements` + `impact` + `evidence`; read-only | Extend only `context` | Differential proposal | Medium | Precision/recall, ergonomics | D01, D06, D13 | Proposal |
| D16 | IDs and schemas | IDs by declaration path; additive JSON; `type_repr` | IDs by line; no IDs | Stability for agents | Medium | Compatibility, migration | D15 | Proposal |
| D17 | Security/playground | Disabled by default; isolation gate; limits | Public exposure already; process-only | Executing third-party code | High | Isolation tests | — | Proposal |
| D18 | Scope of 1.0 | Core + modules + stdlib + tools + security; LSP/REPL optional | Everything; fixed date | Consistency and quality | High | Acceptance criteria | All | Proposal |
| D19 | Runtime contracts | Maintain 0004/0007: checked on execution, not proved | Formal verification | Already decided | — | — | — | Previously decided |
| D20 | Interpreter only runs checked programs | Maintain 0002 | Execute without checker | Already decided | — | — | — | Previously decided |
| D21 | Requirements as differential feature | Maintain 0006; hypothesis still unmeasured | Another feature | Already decided | — | Evaluation H.7 | — | Previously decided direction, hypothesis pending |

### J.1. Open questions requiring approval

1. Is D01 approved as the base algebra, even if implementation is phased?
2. Nominal records D02 or explore structural typing first?
3. User generics in 1.0 or only generic builtins?
4. `match` as expression or statement? `if` as expression too?
5. Mandatory exhaustiveness in `match` expression and error on unreachable cases?
6. Immutable lists D08 or mutability required for the expected use case?
7. `for` with `invariant` from the start? `break`/`continue` outside 1.0?
8. `Input` with `stdin: Text` or `stdin: List[Text]`? Two forms of `main`?
9. Modules with `nexora.toml`? Prohibited cycles? Wildcard imports?
10. What part of detecting weakened requirements is sufficient for 1.0?
11. Should a warning system be introduced for unreachable patterns/unused variables?
12. What LSP/formatter/REPL level is required for 1.0 and which may be 1.x?
13. What budget and models are used in empirical evaluation?
14. Who approves the security gate for the playground?

---

## K. Criteria for NEXORA 1.0

### K.1. Essential

| Area | Verifiable criterion |
|---|---|
| Semantics | Every documented construction has specification, examples and tests; no “half-finished” constructs |
| Types | Builtins + lists + records + enums + `Option`/`Result` + agreed generics; stable errors; `type_repr` |
| Contracts/refinements | Stable `requires`/`ensures`; refinements over compounds; examples; `nex test`; documented limits |
| Modules | File = module; imports/exports/visibility; cycles rejected; project analyzable |
| Diagnostics | Stable codes; positions; notes; justified suggestions; no duplicates; docs synchronized |
| Tools | CLI/API/MCP parity for analysis; `requirements`/`impact`/`evidence`; MCP without execution |
| Formatter/tooling | Canonical idempotent formatter; `nex fmt --check`; LSP may be 1.x if declared |
| Documentation | Spec + guides + executable examples; documentation tests |
| Tests | Unit, integration, boundaries, regression, security, basic fuzzing |
| Security | Threat model; playground disabled by default; isolation gate; no known P0 |
| Compatibility | Existing programs keep working; migration guide; additive schemas |
| Performance | Baseline measured; no unsupported claims |

### K.2. Optional improvements

- Full LSP (minimum may be diagnosis via CLI/JSON).
- REPL.
- Formatter with more style options.
- Typeclasses.
- `uses` effects system.
- `ai fn`/`tool fn`.
- Concurrency.
- Compilation to JS/WASM.
- Package registry.
- Interpreter optimization.
- Maps, tuples, ranges, interpolation.

### K.3. Rule of honesty for 1.0

1.0 does not mean “no errors” or “formal verification.” It means the core is coherent, documented, tested, distinguishes what is checked from what is not, and does not promise more than it can. **No date is fixed.**

---

## L. Decision sequence

### L.1. Recommended order

| Step | Decisions | Why | Can run in parallel with |
|---|---|---|---|
| 1 | Principles A + D01 (type algebra) | Blocks compound types, patterns, lists and tooling | Principles review, security |
| 2 | D02 (nominal), D03 (generics), D04 (refinements) | Define the shape of data and guarantees | D05-D07 (enum/pattern design) |
| 3 | D05 (enums), D06 (`match`), D07 (exhaustiveness) | Blocks `Option`/`Result` and part of the stdlib | D08-D09 (list/`for` design) |
| 4 | D08 (lists), D09 (`for`), D10 (`break`/`continue`) | Base of iteration and data | D11-D12 (input/error design) |
| 5 | D11 (input), D12 (`Option`/`Result`) | Real programs and testability | D13-D14 (module design) |
| 6 | D13 (modules), D14 (project/cache) | Stdlib and project analysis | D15-D16 (requirements/ID design) |
| 7 | D15 (requirements/impact), D16 (IDs/schemas) | Differential proposal and tools | D17 (security) |
| 8 | D17 (security/playground) | Gate to public exposure | All |
| 9 | D18 (1.0 scope) | Closes the set | All |

### L.2. What blocks what

- **D01** blocks D02-D09, D12-D16.
- **D05-D07** block D12 (`Option`/`Result`).
- **D08-D09** block D11 (input with lists) and part of the stdlib.
- **D13-D14** block `project_context`, stdlib and project analysis.
- **D15-D16** depend on D01, D05-D07 and, for projects, D13.
- **D17** is independent but acts as the gate for exposing the playground.
- **D18** depends on everything.

### L.3. What can be explored in parallel without locking the design

- **Diagnostics and formatter:** can be designed with the current syntax and adapted later; they must not close type decisions.
- **Empirical evaluation H.7:** can prepare the harness and tasks with current capabilities; no need to wait for modules.
- **Playground security I.3:** can be planned and executed in a controlled environment; it does not change the language.
- **Documentation and examples:** can prepare drafts; not published until approval.
- **Stdlib design:** can be drafted on paper; implementation depends on modules and types.

### L.4. Conditions for moving to implementation

1. The responsible party explicitly approves D01 and principles A.
2. Open questions in J.1 are resolved or explicitly deferred.
3. In a separate authorized change, `roadmap.md`, `limitations.md`, `language-spec.md` and the ADR index are updated.
4. A phased implementation plan is created with acceptance criteria (G.2).
5. It is confirmed that no date or unsupported capability has been promised.

**This ADR does not modify the official roadmap.** Updating the roadmap and ADR index is pending approval.
