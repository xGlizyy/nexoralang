# 0013 — Lists, `for` over lists and the type model that supports them

- **Status:** accepted. **Since 0.12 the invariants of a `for` are written `keeps`**, in the header
  of the loop ([decision 0019](0019-identidad-propia-del-lenguaje.md)); a `for` still has no
  measure. Its programs are written in the syntax of their time, before 0.12: since 0.12 the
  language writes them as [decision 0019](0019-identidad-propia-del-lenguaje.md) describes, and `nex
  migrate` rewrites them.
- **Version:** 0.7.0 (state of the repository; not published in any package)
- **Date:** 2026-10-21
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (no
  implicit conversions), [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (only what has been checked runs), [0003](0003-funciones-retorno-e-if.md) (a single
  namespace), [0004](0004-contratos-en-ejecucion.md) (`requires` at run time),
  [0005](0005-diagnosticos-y-esquemas-json.md) (diagnostics and JSON schemas),
  [0007](0007-contratos-estables-y-tipos-refinados.md) (refined types),
  [0010](0010-var-y-while.md) (`var`, `while` and invariants) and
  [0011](0011-operaciones-sobre-textos.md) (functions of a type). **It modifies none.**
- **Replaces:** none. **It neither modifies nor replaces
  [decision 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)**: 0012 is still
  a proposal for the rest of its content. This document only accepts the parts
  D01, D08 and D09 that are already implemented and tested, within the scope detailed below.
- **Implementation:** stages I1–I5 of the lists and `for` increment. The code is in
  `types.py`, `type_adapter.py`, `checker.py`, `parser.py`, `interpreter.py`, `prelude.py` and the
  tools; the evidence is in the tests of the section "Regression tests".

## Context

[Decision 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) is a broad
proposal: type model, records, enumerations, patterns, `Option`/`Result`, lists, `for`,
data input, modules and verifiable evidence. When it was written there was no
implementation of any of those parts, and its header says so. Since then
three concrete parts have been implemented, by stages and with tests:

1. a structured type model, built next to the existing checker (D01);
2. immutable lists `List[T]`, with literals, equality and five functions (D08);
3. `for x in xs { ... }` over a `List[T]` (D09).

The code and the documentation could not keep disagreeing: the specification did not describe
lists or the `List` functions, the roadmap presented them as pending and 0012 still
said there was no implementation. At the same time, accepting the whole of 0012 would be false: records,
enumerations, `Option`/`Result`, `type_repr`, user generics and the rest of the proposal do not
exist.

The rule of the repository is that a decision is not rewritten: if it is revisited, another one is added. That is why
this ADR does not edit 0012. 0012 keeps its proposal status and its historical text; 0013
accepts only the implemented subset and leaves the rest where it is.

## Decision

**D01, D08 and D09 are accepted within the implemented scope described below**. Nothing that
does not appear here is considered accepted by this ADR.

### 1. D01 — Type model, within the implemented scope

It is accepted that the semantics of types is decided on a structured representation, not on
string comparison, and that the canonical string remains the public presentation form.

**Representation.** `types.py` defines a base type `Type` and five immutable variants:

| Variant | What it represents | Current scope |
|---------|--------------------|---------------|
| `Primitive` | `Int`, `Float`, `Bool`, `Text`, `Void` | The five built-in names |
| `Constructor` | Name, arity and stable identity of a constructor | `List` (arity 1); `Option` and `Result` only as reserved internal forms |
| `Application` | A constructor applied to positional arguments | `List[T]`, nested as deep as the parser allows |
| `Refined` | A nominal refined type, with a name, a base and a reference to its declaration | The refined types that 0007 already accepted |
| `TypeVariable` | A first-order variable, identified by an integer | Only for the internal signatures of the `List` functions; the language does not allow writing it |

The operations of the model are `equal` (identity), `assignable` (compatibility), `widen` and
`root` (widening and root type), `substitute` and `unify` (first-order substitution and
unification), `display` (canonical text) and `to_data` (internal form for tests and tracing). `to_data`
is **not** a public contract: it appears in no JSON document and has no schema. The `type` field
of the JSON documents is still the canonical text.

`type_adapter.py` is the bridge between the names the checker uses and the model. It resolves
primitives, refined types and the canonical form `List[T]`; it rejects `None`, foreign objects and any
form that is not canonical. `Option`, `Result`, records and any other constructor are left
out: the adapter does not resolve them.

**Identity and compatibility.** Two types are the same if they are the same primitive, the same
application with the same arguments in order, the same refined type name or the same type
variable. A refined type is accepted where its base is expected, or any base in its chain; the
opposite direction requires building the refined value explicitly and checking its condition when
running. The arguments of a constructor are **invariant**: `List[Int]` is not `List[Text]` and
`List[Percent]` is not `List[Int]`, even though `Percent` widens to `Int`.

**Unification.** The signatures of the `List` functions use an internal type variable. Each
call binds it to the types of its arguments through first-order unification. There are no
user generics, automatic generalization, typeclasses or higher-rank types.

**Refinements.** The semantics of 0007 does not change: constants are checked without running and
computed values enter with `Type(x)` when running. In this version a refined type can only
be built over `Int`, `Float`, `Bool`, `Text` or another refined type; refining a list is `E2016`.
This leaves pending the part of D01/D04 that would allow refining compound types.

**Diagnostics.** The rules already migrated to the model build their diagnostics from the
values of the model. The rules not migrated yet keep their string representation and
their messages. `type_repr` is not introduced and the version of no schema changes: the part of
D01.8 that proposed that field is still not accepted.

**What is not accepted from D01.** User-declared types with their own constructors
(records and enumerations), functions as values, user generics, type
aliases and `type_repr` are not accepted. Neither is the complete replacement of the checker by the model: the
checker still uses its strings for the non-migrated rules, and the adapter accompanies those
strings. It is a partial and deliberate migration, not a total rewrite.

### 2. D08 — Lists, within the implemented scope

**Type and values.** `List[T]` is an **immutable and finite** sequence of values of type `T`. `T`
can be `Int`, `Float`, `Bool`, `Text`, a refined type or another `List[...]`; `Void` cannot be an
element (`List[Void]` is `E1101`). The type is invariant in `T`.

**Syntax.** `List[T]` is written in any position where a type is written: annotation of
`let`/`var`, parameter, return, type of a refined type (even though refining it is `E2016`) and
`nex inspect`. The parser limits type nesting to 64 levels (`E1105`). `List` without an
argument is not a type (`E2012`); `Option[...]`, `Result[...]`, `Foo[...]`, `Int[...]`,
`List[...]` with more than one argument and `List[Void]` are syntax errors (`E1101`).

**Literals and inference.** `[a, b, c]` and `[]` are expressions. Without an expected type, the first
element sets the type of the rest; all of them must be acceptable as that type. With an expected type
`List[T]`, all the elements are checked against `T`. That is why `[Percent(10), 20]` without an annotation
fails (the first element sets `Percent`), while `let xs: List[Int] = [Percent(10), 20]`
accepts the widening of each element to `Int`.

An empty list **needs an expected type**: an annotation, a parameter, a return, an
assignment, the left-hand side of an equality or a function that sets the type of the argument. `let xs = []`
and `print([])` are `E2011`; `a == []` works, but `[] == a` does not infer the type of the right-hand side. The
expected type also propagates into nested lists: `let xs: List[List[Int]] = [[]]` is valid.

**Equality.** `==` and `!=` compare lists of the **same type** structurally: same elements,
in the same order, compared recursively. The result is `Bool`. There is no ordering (`<`, `<=`, `>`,
`>=`) between lists. Two lists of different element types are not compared (`E2011`).

**Representation and printing.** At run time a list is an immutable Python tuple. `print` and
`to_text` write the canonical form with square brackets, without quotes around texts:
`[1, 2, 3]`, `[[1], [2, 3]]`, `[a, b]`, `[]`. `show_value`, which the diagnostics use, does quote
texts. There is no index syntax (`xs[i]`) and no mutation of elements.

**Functions.** Exactly these five are accepted, with the type variable `T` bound on each
call:

| Function | Signature | Behaviour |
|----------|-----------|-----------|
| `List.length` | `List.length(xs: List[T]) -> Int` | Number of elements; total |
| `List.get` | `List.get(xs: List[T], i: Int) -> T` | Element at position `i`, starting at 0; partial |
| `List.append` | `List.append(xs: List[T], x: T) -> List[T]` | New list with `x` at the end; does not change `xs` |
| `List.concat` | `List.concat(xs: List[T], ys: List[T]) -> List[T]` | New list with the elements of `xs` and then those of `ys`; changes neither |
| `List.contains` | `List.contains(xs: List[T], x: T) -> Bool` | Whether some element is structurally equal to `x` |

`List.get` declares `requires 0 <= i and i < List.length(xs)` with the explanation "An index must be
inside the list". A negative index, or one equal to or greater than the length, stops the program with `E4001`;
there are no negative indices counting from the end and no silent truncation. The check is at run time,
also when the index is a constant: `nex check` does not prove the contract. A literal empty list
as an argument of `List.*` needs an expected type, because the parametric signatures do not
set the element before reading the arguments; for example, `List.append([], 1)` and
`List.concat([1], [])` are `E2011`.

**What is not accepted from D08.** There is no `List.set`, `map`, `filter`, `fold`, sorting, `slice` or
any other function; there is no `Option` for a total variant of `List.get`; there are no
mutable, lazy or infinite lists; there is no syntactic indexing; lists cannot be refined.

### 3. D09 — `for` over lists, within the implemented scope

**Syntax.** `for x in xs { clauses statements }`. It is a statement, not an expression. `x` is the
iterator; `xs` is the iterable; the clauses are zero or more `invariant` and, syntactically,
`decreases` (which in a `for` is always `E2022`).

**Evaluation.** The iterable is evaluated **only once**, before the first check of the
invariants and before any iteration. It must have type `List[T]`; an `Int`, `Float`, `Bool` or
`Text` is `E2011`. A literal empty list as the iterable (`for x in []`) has no expected type and is
`E2011`; to go through an empty list an annotated variable has to be used, for example
`let xs: List[Int] = []`.

**Iterator and scopes.** The iterator is immutable and has the type of the element `T`. It is declared in the
`for` itself, not before, and it cannot shadow a visible name (`E2006`). Assigning a value to it is
`E2007`. It is not visible after the loop. Every iteration runs the body in a new environment: the
variables declared in the body do not keep their value between iterations; assignments to a `var`
of the outer scope are kept. The clauses see the names visible where the `for` is,
never the iterator.

**Invariants.** A `for` can declare zero or more `invariant` clauses. Each one must be `Bool` (`E2011`).
They are checked before every iteration and once after the last one, with the same semantics as in a
`while`. On an empty list they are checked once, before the first iteration, which never
runs; there is no separate additional check. A false invariant stops the program with
`E4005` and the notes give the iteration and the values.

**Measure, exit and termination.** There is no `decreases`: the list is finite by construction, and a
`decreases` is `E2022`. There is no `break` or `continue`; they remain reserved words (`E1103`).
A `return` inside the body ends the function. Loops can be nested. Iterations are not
calls: the loop does not add a call and does not use up the limit of 1000, although the calls inside the
body do count. Termination is structural (the
list is finite), but speed is not promised: a huge list takes as long as it takes, and `nex run` has no
time limit.

**Return paths.** The path analysis does not consider that a `for` always returns, even if all
its iterations contain a `return`. A function that returns a value needs a `return` after
the loop if the `for` is the last statement. It is the current behaviour and it is documented as such;
if it is to be changed, that will be another decision.

**What is not accepted from D09.** There is no `for` over ranges, `Text`, maps or lazy iterators;
there is no `break`/`continue`; there are no user type variables and no higher-order functions that
receive the body of the loop.

### 4. What this ADR does not accept from 0012

So that there is no doubt, these are **outside** this acceptance, and remain a proposal in 0012:

- records, enumerations and patterns (D02, D05, D06, D07);
- `Option`, `Result` and their syntax, their values and their functions;
- `type_repr` and any change of the JSON schemas towards a structured type;
- user generics, generic functions and functions as values (D03);
- refinements over lists, records or any compound type (D04 in the part not
  implemented);
- data input, modules, verifiable evidence and the security gate (E, F, H, I);
- the 1.0 criteria and the sequence of decisions that depend on all of the above (K, L).

0012 is still the place where those parts are discussed. 0013 does not approve them by omission.

## Reasons

- **Coherence.** The repository requires code, specification, examples, schemas and tests to say
  the same thing. Accepting only what is implemented and documenting it is the only way to comply without pretending
  that the whole proposal is done.
- **Traceability.** Every accepted part has tests that fail if it stops working. 0013 can
  cite them; 0012, on the other hand, describes things that do not exist.
- **Preserving history.** Rewriting 0012 would erase the record that it was a proposal and
  that its scope was much larger. 0013 leaves that record intact and explains the relation.
- **Incrementality.** The structured model was introduced next to the checker, with an adapter,
  instead of rewriting it entirely. That decision reduces the risk and lets the non-migrated rules
  keep working with their strings.

## What it does not guarantee

- That a list is cheap: immutability implies copies in `append` and `concat`; the cost has not been
  measured.
- That `List.get` is total: it is still partial and requires a valid index.
- That the invariants of a `for` are the right ones: they are checked on the iterations that
  happen, they are not proven.
- That a `for` ends soon: it is only guaranteed that the list is finite.
- That the type model covers all future types: it only covers those that exist today.
- That accepted programs are free of runtime errors: division by zero, overflow,
  broken contracts and `List.get` out of range still exist.

## Out of scope

Besides what is listed in section 4, these are out of this decision: higher-order
functions over lists, ordered equality, covariance, type aliases, custom
printing, structured serialization of types and any optimization of the interpreter.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| Accepting the whole of 0012 | It would accept records, enums, `Option`/`Result`, `type_repr` and generics that do not exist; it would turn a proposal into a false promise |
| Leaving 0012 as the only reference and not creating 0013 | The code would be left without an accepted decision backing it; the documentation would keep saying there is no implementation |
| Rewriting 0012 to mark what is implemented | It violates the rule that decisions are not rewritten and erases the historical context |
| Mutable lists | They introduce aliasing and complicate equality, contracts and termination; they are postponed |
| A total `List.get` returning a default value | It makes up a value and hides the error; the total variant will come with `Option`, which does not exist yet |
| `for` over ranges or `Text` in the first version | It adds special cases and types that do not exist; it is postponed |
| `break`/`continue` from the start | They break reasoning about invariants and termination; they are postponed |

## Compatibility

**Programs.** No program valid in 0.6.0 stops being so or changes its result. `for` and `in`
were already reserved words and now they are keywords; `[` and `]` were unexpected characters and
now they are symbols. The uses whose diagnostic changes were already invalid. `List`, `length`, `get`,
`append`, `concat` and `contains` are not reserved as names: the new functions are called
qualified (`List.length`), like those of `Text` in 0011. A program can still declare a
refined type called `List`; `List[Int]` always means the built-in list.

**Tools.** The changes are additive and do not change the version of the schemas:

- `nex inspect`: `arguments` in `TypeRef` (`[]` for a name without square brackets), the `ListLiteral` node and
  the `For` node; the `type` field of an expression can be `List[...]`.
- `nex context`: `loops` includes `for`, with `kind: "for"`, `condition` equal to `x in xs` and
  `measure: null`.
- `nex symbols`: the iterator appears as an immutable variable, with its type and its scope.
- `nex inspect` and `nex context` still do not run the program.

**Version.** The state of the repository moves to `0.7.0`. It is not declared published: there is no tag and no
published package. `CHANGELOG.md` presents it as the state of the repository and keeps separate the changes
of `servidor/` and `web/`, which are not part of this decision.

## Required changes

- Specification 0.7: section 4.5 (lists), 8.2 (`List` functions), 9.6 (`for`), tables of types,
  compatibility, conversions, diagnostics and limitations.
- Guides: `types.md` (lists and functions), `limitations.md` (real limits) and `index.md`.
- Roadmap: lists and `for` stop being pending.
- Architecture: the type model is no longer "types are texts".
- Tools: document the additive fields in `inspect-schema.md`, `ai-context.md` and
  `ai-tooling.md`.
- `CHANGELOG.md` and `version.py` to `0.7.0`.

## Regression tests

The implementation relies on these tests, which run in the full suite:

| File | What it pins down |
|------|-------------------|
| `tests/test_type_lists_syntax.py` | Tokens `[`/`]`, grammar of `List[T]`, nesting, syntax errors, `TypeRef.arguments` and the limit of 64 levels |
| `tests/test_type_lists_values.py` | Literals, inference, empty lists, homogeneity, invariance, widening of refined types, equality, printing, immutability and `main` without lists |
| `tests/test_type_lists_functions.py` | Arity and types of the five functions, contract of `List.get`, results, immutability of `append`/`concat` and structural search |
| `tests/test_for.py` | Syntax, order, single evaluation, empty list, type of the iterator, scopes, immutability, `return`, nesting, invariants, `E2022`, reserved words and tools |
| `tests/test_parser.py`, `tests/test_inspect.py`, `tests/test_tooling.py` | Nodes, schemas and documents of the tools |
| `tests/test_examples.py`, `tests/test_docs.py` | `examples/lists.nex`, its recorded outputs and the programs of the documentation |

The runnable example is [`examples/lists.nex`](../../examples/lists.nex), with its output in
`tests/golden/examples/lists.run.stdout`. The full suite and `ruff check .` were run when
closing this increment; the real result is recorded in the report of the change, not in this ADR.

## Relation to 0012 and the index

- 0012 **is not rewritten**. Its header ("not accepted", "implementation: none") describes the
  moment when it was written; 0013 explains which parts have been implemented and accepted since
  then.
- 0013 neither replaces nor repeals 0012: it complements it for the implemented subset.
- The index [`README.md`](README.md) records 0012 as a proposal and 0013 as accepted.
