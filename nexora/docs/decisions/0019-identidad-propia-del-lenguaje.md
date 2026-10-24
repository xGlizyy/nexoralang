# 0019 — An identity of its own: promises, evidence and a syntax that says so

- **Status:** accepted. The design is accepted; nothing in this document is implemented, and
  phase 1 needs its own explicit authorization (8.11).
- **Version:** would start in 0.12.0
- **Date:** 2026-10-24 (accepted)
- **Incompatible:** yes. Every existing program with a function has to be migrated (sections 8
  and 12).
- **Revision:** 8, the accepted one. History: revision 2 answered the first review. Revision 3
  closed the ambiguities of the second: the two processing routes of `nex migrate` and mixed programs (8.2), what structural
  equivalence compares (8.4), how `nex impact` matches modules, functions and clauses, with examples
  (section 7), how comments and spacing survive a migration (8.5), the evidence model without `null`
  (section 5), and the accepted and rejected examples that phase 1 will turn into tests (4.3).
  A final audit of revision 3 corrected, without changing any decision: the rules and the fourth
  row of the routes of `nex migrate`, with its proof (8.2); the exact edits E5–E7 (8.5); a refusal
  without a valid reason (8.6); the rule for a conflict between static and observed evidence
  (5.5); the count of the acceptance cases (4.3); the marks of section 2; and the separation of
  the open questions (section 13).
- **Revision 4** records the answers of the person responsible for the project to the six
  questions of section 13. The status stayed **proposed**: the decision is accepted only by an
  explicit approval of this text, which came later, for revision 8 (Approval).
- **Revision 5** answers a review of revision 4 without changing any decision: the route of
  `nex migrate` when both checks pass, separating what is proved from what is audited, with a
  safety check (8.2.2); the exact ranges, order and cases of the edits (8.5); what is guaranteed
  about the order of clauses and examples (8.4.1); and what is checked, argued or only measured
  (8.4.2).
- **Revision 6** is the closing pass. It resolves the four technical details of section 13 (the
  order of the header, the lifetime of the 0.11 front end, modules named like a new keyword, the
  exit code of `nex impact`), adds how `nex migrate` writes files and the status of every
  guarantee (8.3), and changes no decision of the person responsible for the project.
- **Revision 7** corrects the findings of the final technical review without changing any
  decision: `trust` belongs to phase 1 everywhere (B1); the formatter fix of PR #6 is recorded
  (B2); 8.8 and 8.10 say the phase of each item (B3); T2 has an explicit corpus, harness and
  normalization (C1, 8.9.1); what `nex migrate` does on the first failed write (C2, G7); and
  what makes an acceptance case pass (C3, 4.3).
- **Revision 8** records five decisions of the person responsible for the project, taken after
  the review of revision 7: `nex migrate` keeps the permission bits of each file it replaces;
  its temporary files never end in `.nex` and are removed after the failures it detects; the
  tests inject failed writes and concurrent changes through an internal mechanism (8.9.2);
  `nexora.evidence/1` has a stable reason for an observed dimension that `nex check` never
  computes (5.3); and code `4` covers a file `nex migrate` cannot write (8.7.1). The first line
  of this list now matches section 12.

## Context

NEXORA already has a direction of its own: [decision 0006](0006-requisitos-verificables.md) made
verifiable requirements its main feature, and every version since has followed it.

Its **surface** does not show it. This is how a function is written today:

```nex
pub fn percentage(part: Int, whole: Int) -> Int {
    requires whole > 0, "A percentage of nothing is not defined"
    ensures result >= 0 and result <= 100
    return part * 100 / whole
}
```

`pub fn name(...) -> T {` is the signature of Rust. `requires` and `ensures` are the words of
Eiffel, JML and Dafny. `Some`, `None`, `Ok`, `Err` and `unwrap` are Rust. The part that is NEXORA's
own (the requirements and what backs them) looks like an add-on inside the body instead of the
centre of the language.

The person responsible for the project asked for an identity of its own, accepting incompatible
changes before 1.0, on three conditions: every change justified, nothing changed arbitrarily, and
new concepts realistic to implement. The direction was approved in the first two reviews, and
the decision was accepted as written in revision 8 (Approval).

### Evidence conventions

As in [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md), extended with a fourth
mark:

| Mark | Meaning |
|------|---------|
| **[V]** | Exists in the repository and was checked for this revision |
| **[P]** | Proposed by this decision. Does not exist |
| **[F]** | Future work this decision depends on or announces, outside its phases: it does not exist, and this decision does not design it |
| **[?]** | Not verified |

## 1. Where an identity can come from

Changing words does not make an identity. Replacing `fn` with `func` or `{ }` with `do … end` would
make NEXORA different from Rust and the same as Go or Ruby, and every renamed word costs every
reader, person or model, something to learn. Two rules follow:

1. **Different in concepts and in structure, familiar in primitives.** `if`, `while`, `let`, `+`,
   `Int` or `List` are understood by everyone, and by every language model, because they are common.
2. **Every change follows from a principle, not from a preference.** Every row of section 3 cites
   the principle that justifies it.

| # | Principle | What it means |
|---|-----------|---------------|
| **P1** | **The promise comes before the implementation.** | What a function needs and what it promises is part of its interface, written between the signature and the body |
| **P2** | **One vocabulary for obligations.** | A function *needs*, *gives* and *promises*; a loop *keeps* and *shrinks*; a program can *trust* something explicitly. Symbols stay for arithmetic and comparison |
| **P3** | **Every claim carries its evidence.** | A promise can have a stable name, and the language reports what backs it (section 5) |
| **P4** | **Nothing implicit, nothing silent.** | Already a rule ([0001](0001-tipos-estaticos-sin-conversiones-implicitas.md), [0016](0016-option-y-result.md)); it applies to names too: `unwrap` becomes `value` |

| Word | Where | Says | Today |
|------|-------|------|-------|
| `gives` | Function signature | The type of the value given back | `->` |
| `needs` | Function header | What the caller must guarantee | `requires` |
| `promises` | Function header | What the function guarantees about `result` | `ensures` |
| `example` | Function header | A concrete case that must hold | `example`, in the body |
| `keeps` | Loop header | A condition the loop keeps true | `invariant` |
| `shrinks` | Loop header | The measure that shrinks on every iteration | `decreases` |
| `trust` | Function header | An assumption the language states and does not check | — |

## 2. What exists, what is proposed and what is future work

| Capability | Mark | Where, or phase |
|------------|------|-----------------|
| `requires`, `ensures`, `example` at the start of a function body; `invariant`, `decreases` at the start of a loop body | **[V]** | `parser.py`; `ast_nodes.py`: `Function.contracts` and `Function.examples` are **separate lists**, so the relative order of a contract and an example is not recorded; `While.clauses`, `For.clauses` |
| Contracts and loop clauses checked on every call or iteration that runs (`E4001`, `E4002`, `E4003`) | **[V]** | `interpreter.py`; spec 9.2 |
| `nex check` decides refined conditions **on constants**, without running, with a work limit (`E2017`, `E2019`) | **[V]** | `checker.py`; spec 4.4 |
| `nex check` decides a `requires` at a call with constant arguments | **Does not exist** | [0011](0011-operaciones-sobre-textos.md), "What it does not guarantee" |
| `nex test` evaluates every `example`, each with a new interpreter, checking every contract it reaches | **[V]** | `api.test_source`; [0008](0008-ejemplos-y-nex-test.md) |
| `nex test` records which contracts an example reached | **Does not exist** | The fields of an example result in `nexora.test/1` ([0008](0008-ejemplos-y-nex-test.md), 6.2) have no such record |
| The formatter keeps comments | **[V]** since PR #6 (commit `bdc4ada`, in `main`). It works on the physical lines of the text and keeps comments, blank lines and line endings; its tests check, for every example program, that each line keeps its tokens and its comment. It does not know the 0.12 layout, which is phase 1 work (8.10), and a text with a byte-order mark is still left unformatted, as before | `formatter.py`, `lsp.py`; `tests/test_formatter.py`, `tests/test_lsp.py` |
| Header clauses, `gives`, `keeps`, `shrinks`, `trust` (syntax, type check, never evaluated, enforcement `trusted`), names of clauses, `nex migrate`, `nex check --evidence` (enforcement only), new format versions | **[P]** | Phase 1 |
| The observed dimension, `nex test --evidence` | **[P]** | Phase 2 |
| `nex impact` | **[P]** | Phase 3 |
| Static decision of `needs` at call sites with constants | **[P]** | Phase 4 |
| A formatter that keeps comments | **Done** (PR #6, `bdc4ada`). It was a separate, blocking fix; the precondition of phase 1 that depended on it is met (8.11) | 8.10 |
| The acceptance tests of 4.3 and the equivalence tests of 8.9 | **[P]**. **None exists and none has been run** | Phase 1 (8.11) |
| A survey of contract and evidence features in other languages | **[F]** | Before any public claim of novelty (section 11) |

## 3. Every current feature, reviewed

| Feature | Today **[V]** | Verdict | Proposed **[P]** | Principle and reason |
|---------|---------------|---------|------------------|----------------------|
| Function signature | `fn f(x: Int) -> Int` | **Redesign** | `fn f(x: Int) gives Int` | P2. `->` is the most recognisably borrowed piece |
| `fn` | `fn` | Keep | — | Rule 1: short, frequent, understood by every reader |
| No return value | `-> Void` | **Redesign** | No `gives` | P2. "Gives nothing" is said by not saying `gives` |
| Precondition | `requires`, in the body | **Rename and move** | `needs`, in the header | P1, P2 |
| Postcondition | `ensures`, in the body | **Rename and move** | `promises`, in the header | P1, P2 |
| Examples | `example`, in the body | **Move** | `example`, in the header | P1. The word already says what it does |
| Loop invariant | `invariant`, in the body | **Rename and move** | `keeps`, in the header | P1, P2 |
| Loop measure | `decreases`, in the body | **Rename and move** | `shrinks`, in the header | P1, P2 |
| Names of clauses | — | **New** | `needs name: …` | P3 (section 7) |
| Explicit assumptions | — | **New** | `trust name: …, "reason"` | P3, P4 (5.3) |
| Variables | `let`, `var` | Keep | — | Rule 1 |
| Control flow | `if`, `else`, `while`, `for … in`, `return` | Keep | — | Rule 1 |
| Logic, arithmetic, comparison | `and`, `or`, `not`; `+ - * /`; `== != < <= > >=` | Keep | — | Already P2 |
| Blocks, comments | `{ }`, `//` | Keep | — | Braces help error recovery of partial trees; section 10 |
| Refined types | `type Percent = Int where value >= 0` | Keep | — | Already promise first |
| Records | `type Point = { x: Int, y: Int }`, `Point(x: 1, y: 2)`, `p.x` | Keep | — | [0014](0014-registros-nominales-inmutables.md) |
| Lists, functions of a type | `List[T]`, `[1, 2]`, `Text.length(s)` | Keep | — | Rule 1; [0011](0011-operaciones-sobre-textos.md) |
| `Option`, `Result`, `Some`, `None`, `Ok`, `Err`, `is_some`… | as today | Keep | — | Rule 1: known to people and models |
| Reading a value | `Option.unwrap(x)`, `Option.unwrap_or(x, d)`; the same for `Result` | **Rename** | `Option.value(x)`, `Option.value_or(x, d)`; the same for `Result` | P4. Pairs with the existing `Result.error(x)` |
| Modules | `import "path.nex"`, `pub`, `module.name` | Keep | — | [0018](0018-modulos-e-importaciones.md) |
| Capabilities | `uses read "path"` | Keep | — | [0015](0015-entrada-argumentos-archivos-y-permisos.md) |
| Built-ins and `main` | `print`, `to_text`, `args`, `input`… ; `fn main() -> Void` | Keep; `main` follows the signature | `fn main()` | — |
| Diagnostic codes | `E1101`… | Keep, add four | 8.7 | [0005](0005-diagnosticos-y-esquemas-json.md) |
| Reserved words | `ai`, `assert`, `break`, `const`, `continue`, `enum`, `match`, `test`, `tool`, `try` | Review | Section 9 | — |

## 4. Syntax **[P]**

### 4.1 Grammar

Only the rules that change; the rest of [the specification](../language-spec.md#3-grammar) stays.
As there, `NEWLINE` is one or more consecutive line endings, and comments are not tokens: a blank
line or a line with only a comment adds nothing to the token sequence.

```ebnf
function      = [ "pub" ] "fn" NAME "(" [ params ] ")" [ "gives" type ] function_body ;
function_body = "{" { NEWLINE } { statement end } "}"                                (* no clauses *)
              | NEWLINE header_clause { header_clause } "{" { NEWLINE } { statement end } "}" ;
header_clause = ( "needs" | "promises" ) [ NAME ":" ] expression [ "," TEXT ] NEWLINE
              | "trust" [ NAME ":" ] expression "," TEXT NEWLINE        (* explanation required *)
              | "example" expression [ "," TEXT ] NEWLINE ;              (* no name *)

while         = "while" expression loop_body ;
for           = "for" NAME "in" expression loop_body ;
loop_body     = "{" { NEWLINE } { statement end } "}"                                (* no clauses *)
              | NEWLINE loop_clause { loop_clause } "{" { NEWLINE } { statement end } "}" ;
loop_clause   = ( "keeps" | "shrinks" ) [ NAME ":" ] expression [ "," TEXT ] NEWLINE ;
```

Rules the grammar alone does not express:

- **Where the `{` goes.** Without clauses, on the line of the signature or of the loop. With
  clauses, alone after the last clause. Blank lines and comment lines may appear between the
  signature, the clauses and the `{`.
- **Every `while` has exactly one `shrinks`** (`E2021`, as today). `while c {` parses, and the
  checker reports the missing measure; in practice a valid `while` always has a header.
- **`shrinks` in a `for` is `E2022`**, as today; `keeps` is allowed.
- **Clause names** are lowercase `NAME`s, unique within the function **including its loops**, and
  different from the parameters and from `result` (`E2031`). The name of a clause is not a variable:
  it cannot be used in an expression.
- **Names are optional in 0.12.0**, in every function. The direction is to require them in the
  clauses of `pub` functions (section 13, answer 3), but that obligation is **not** part of this
  decision and is not in force in any phase of it. Activating it needs its own decision, which must
  fix: the version where it applies, the diagnostic code and its message, the migration policy
  (`nex migrate` never invents names: they are chosen by a person), and, if NEXORA has warnings
  by then, a period in which a missing name is a warning before it is an error.
- **Visibility**, unchanged from [9.1 of the specification](../language-spec.md#91-rules): `needs`
  and `trust` see the parameters; `promises` sees the parameters and, if the function has `gives`,
  `result`; a loop clause sees what is visible where the loop is. Anything else is `E2005`.
- **`main`** has no `gives` (`E2004` otherwise, as a `main` with a return type other than `Void` is
  today **[V]**). `Void` is not written: `gives Void` is `E2012`, with the hint
  `A function that gives nothing has no 'gives'`.
- The new keywords cannot be names (`E1101`, as for any keyword).

### 4.2 Examples

**A function with clauses.**

```text
pub fn percentage(part: Int, whole: Int) gives Int
    needs whole_positive: whole > 0, "A percentage of nothing is not defined"
    needs part_inside: part >= 0 and part <= whole, "The part has to be inside the whole"
    needs fits: part <= 92233720368547758, "part * 100 has to fit in an Int"
    promises in_range: result >= 0 and result <= 100
    example percentage(3, 12) == 25
    example percentage(12, 12) == 100
{
    return part * 100 / whole
}
```

**A function and a loop.**

```text
fn sum_to(n: Int) gives Int
    needs natural: n >= 0, "Only natural numbers"
    needs small: n <= 3037000499, "n * (n + 1) has to fit in an Int"
    promises gauss: result == n * (n + 1) / 2
    example sum_to(4) == 10
{
    var total = 0
    var i = 0
    while i < n
        keeps partial_sum: total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        shrinks steps_left: n - i, "Each turn moves i one step closer to n"
    {
        i = i + 1
        total = total + i
    }
    return total
}
```

`3037000499` is the largest `n` for which `n * (n + 1)` fits in an `Int`; without `small`, a call
with a valid `natural` could stop with `E3002` while evaluating `gauss` or the invariant.

**Functions without clauses, a function that gives nothing, a `for` and `Option`.**

```text
fn find(names: List[Text], wanted: Text) gives Option[Int] {
    var index = 0
    while index < List.length(names)
        shrinks remaining: List.length(names) - index, "Each turn looks at one more name"
    {
        if List.get(names, index) == wanted {
            return Some(index)
        }
        index = index + 1
    }
    return None
}

fn show_all(names: List[Text]) {
    for name in names {
        print(name)
    }
}

fn main() {
    print(Option.value_or(find(["ada", "grace"], "grace"), -1))
    show_all(["ada", "grace"])
}
```

**An assumption.**

```text
fn parse_age(text: Text) gives Int
    needs digits: Int.can_parse(text), "Only whole numbers"
    trust plausible: Int.parse(text) < 150, "Ages come from a form that already limits them"
{
    return Int.parse(text)
}
```

The same functions **today**, which pass `nex check` in 0.11:

<!-- nex:valid -->
```nex
fn percentage(part: Int, whole: Int) -> Int {
    requires whole > 0, "A percentage of nothing is not defined"
    requires part >= 0 and part <= whole, "The part has to be inside the whole"
    requires part <= 92233720368547758, "part * 100 has to fit in an Int"
    ensures result >= 0 and result <= 100
    example percentage(3, 12) == 25
    example percentage(12, 12) == 100
    return part * 100 / whole
}

fn find(names: List[Text], wanted: Text) -> Option[Int] {
    var index = 0
    while index < List.length(names) {
        decreases List.length(names) - index, "Each turn looks at one more name"
        if List.get(names, index) == wanted {
            return Some(index)
        }
        index = index + 1
    }
    return None
}

fn show_all(names: List[Text]) -> Void {
    for name in names {
        print(name)
    }
}

fn main() -> Void {
    print(percentage(3, 12))
    print(Option.unwrap_or(find(["ada", "grace"], "grace"), -1))
    show_all(["ada", "grace"])
}
```

### 4.3 Acceptance cases for phase 1 **[P]**

These cases are the **acceptance criteria** of the syntax. Phase 1 turns each one into an automated
test; until then they are a specification. **None of these tests exists, and none has been run.**
The codes `E1107`, `E1108`, `E2031` and the new messages are proposals (8.7).

There are **30 cases: 12 that must be accepted (A1–A12) and 18 that must be rejected (R1–R18)**.

**When a case passes.** Each case is run with the 0.12 commands, in their JSON form:

| Kind | Passes when |
|------|-------------|
| Accepted, every case | `nex test --format json` gives `"ok": true` and an empty `diagnostics`: the static analysis without `main` found nothing |
| Accepted, a program with `main` (A3) | Also: `nex check` exits `0` with nothing on the standard error |
| Accepted, a program with `example` clauses (A1, A2, A11) | Also: `nex test` gives `"status": "passed"`, every example `passed` |
| Rejected | The diagnostics of `nex check --format json` (of `nex test --format json` for a program without `main`) include the code of the table, on the line of the construct it names, and the program is not accepted. Other diagnostics are allowed only when they follow from the same construct |

**Fragments.** A fragment with `…` is completed into a full program when the test is written, in
phase 1: the smallest program in which the construct of the case is the only thing being checked,
so that an accepted case has no diagnostic and a rejected case has the expected one. The completed
programs are part of the review of the phase 1 tests.

**Must be accepted.**

| # | Program (fragment) | Why |
|---|--------------------|-----|
| A1 | `percentage` (4.2) | Clauses, names, explanations and examples in the header; `{` alone |
| A2 | `sum_to` (4.2) | A `while` with `keeps` and `shrinks`; names shared by the function and its loop |
| A3 | `find`, `show_all` and `main` (4.2) | No clauses; no `gives`; a `for` without clauses |
| A4 | `parse_age` (4.2) | `trust` with its explanation |
| A5 | `fn f(x: Int) gives Int {` … `}` | No clauses: `{` on the signature line |
| A6 | `fn log(x: Int) {` … `}` | No `gives`: gives nothing |
| A7 | `fn g(x: Int) gives Int` / `    needs x > 0` / `{` … | An unnamed clause |
| A8 | `fn g(x: Int) gives Int` / `    // why` / `    needs x > 0` / (blank line) / `    promises result > 0` / `{` … | Comment and blank lines in the header |
| A9 | `fn g(x: Int) gives Int` / `    needs ok: (x > 0 and` / `        x < 10)` / `{` … | A condition across lines inside parentheses, as allowed today **[V]** |
| A10 | `for x in xs` / `    keeps seen: count >= 0` / `{` … | A `for` with a header |
| A11 | `fn h(x: Int) gives Int` / `    example h(1) == 2` / `{` … | A header with only an example |
| A12 | `pub fn …` with clauses | `pub` before `fn`, unchanged |

**Must be rejected.**

| # | Program (fragment) | Code | Why |
|---|--------------------|------|-----|
| R1 | `fn f(x: Int) gives Int` / `{` … (no clauses) | `E1101` | Without clauses the `{` goes on the signature line. Message: `Without header clauses, '{' goes on the line of the signature` |
| R2 | `fn f(x: Int) -> Int {` | `E1108` | The old arrow |
| R3 | `requires x > 0` (anywhere) | `E1107` | The old word |
| R4 | `fn f(x: Int) gives Int {` / `    needs x > 0` … | `E1106` | A clause inside the body |
| R5 | … / `    needs x > 0 {` | `E1101` | The `{` goes alone after the last clause |
| R6 | `while i < n {` / `    shrinks n - i` … | `E1106` | A loop clause inside the body |
| R7 | `while i < n {` with no `shrinks` anywhere | `E2021` | Every `while` declares its measure (today's rule) |
| R8 | `for x in xs` / `    shrinks 1` / `{` … | `E2022` | A `for` has no measure (today's rule) |
| R9 | `needs a: x > 0` and `promises a: result > 0` in one function | `E2031` | Duplicate clause name |
| R10 | `fn f(x: Int) …` / `    needs x: x > 0` | `E2031` | A clause name equal to a parameter |
| R11 | `needs result > 0` | `E2005` | `result` is not visible in `needs` (today's rule) |
| R12 | `fn log(x: Int)` / `    promises result > 0` / `{` … | `E2005` | No `gives`, so no `result` |
| R13 | `fn main() gives Int {` | `E2004` | `main` gives nothing |
| R14 | `fn f() gives Void {` | `E2012` | `Void` is not written |
| R15 | `trust t: x > 0` (no explanation) | `E1101` | A `trust` states its reason |
| R16 | `example e: f(1) == 1` | `E1101` | Examples have no name |
| R17 | `let needs = 3` | `E1101` | A keyword is not a name |
| R18 | `needs x + 1` | `E2011` | A clause is a `Bool` (today's rule) |

## 5. The evidence model **[P]**

### 5.1 Three dimensions

The evidence of a clause is not one state. It is the answer to three independent questions, and
each answer comes from a different source:

| Dimension | Question | Source | Requires running? | Phase |
|-----------|----------|--------|-------------------|-------|
| **Enforcement** | Does the language evaluate this clause when the program runs? | The kind of clause, in the text | No | 1 |
| **Static** | At which call sites was the clause decided without running? | The static analysis, with the evaluator of constants: `nex check --evidence`, and `nex test --evidence`, which runs the same analysis before any example **[V]** | No | 4 |
| **Observed** | What happened when the examples reached it? | `nex test --evidence` | Only the examples | 2 |

`example` clauses are **not** promises and have no evidence entry: they are the means of the
observed dimension, and their own results are those of `nex test` (`passed`, `failed`, `error`) **[V]**.

### 5.2 Applicability

| Clause | Enforcement | Static | Observed |
|--------|-------------|--------|----------|
| `needs` | `checked` | applicable (per call site) | applicable |
| `promises` | `checked` | **not applicable**: deciding it is proving the body | applicable |
| `keeps` | `checked` | not applicable | applicable |
| `shrinks` | `checked` | not applicable | applicable: one evaluation is one check of the measure at an iteration (non-negative and lower than before), as today |
| `trust` | `trusted` | not applicable | **not applicable**: it is never evaluated |

### 5.3 Not applicable is not the same as not computed

Each dimension is an object with a `status`, never `null`:

| `status` | Meaning | Example |
|----------|---------|---------|
| `"not_applicable"` | This dimension can never have a value for this kind of clause | `static` of a `promises`; `observed` of a `trust` |
| `"not_computed"` | It could have a value, but the command that produced the document did not compute it. A `reason` field says why, with one of the stable values below | `observed` in `nex check --evidence`; `static` before phase 4 |
| `"computed"` | The value is present, in the fields of 5.4 | — |

The values of `reason`, stable within `nexora.evidence/1`:

| `reason` | Meaning | Produced by |
|----------|---------|-------------|
| `"analysis_only"` | The command only analyses the program; observing a clause needs running examples, which it never does | `observed` in `nex check --evidence`, in every phase |
| `"phase_not_implemented"` | The phase that computes this dimension is not implemented in this version | `static` before phase 4, in `nex check --evidence` and `nex test --evidence` |
| `"static_errors"` | The program has static errors, so `nex test` ran nothing | `observed` in `nex test --evidence` when its status is `not_run` |

A new reason is an added value, as the JSON protocol allows; a consumer that does not know one
treats it as "not computed".

The document also says, at its top level, which dimensions the command computed:
`"computed": {"static": false, "observed": true}`.

### 5.4 How each dimension is computed

**Static** (phase 4), for a `needs`. Every call to the function in the text of the program is a
*call site*, including calls inside `example` clauses, inside the conditions of other clauses, and
from other modules of the same program. The condition of a refined type cannot call a function of
the program (`E2018` **[V]**), so it holds no call site. At each call site the condition is decided only if every argument is a constant, in the sense
of [spec 4.4](../language-spec.md#44-refined-types) (a literal, optionally with `-` or `not` in
front of it or in parentheses **[V]**), and the condition only uses parameters; it is evaluated with the evaluator that already decides refined
conditions on constants **[V]**, under the same work limit:

| Result at a call site | When |
|-----------------------|------|
| `proved` | Evaluated, and true |
| `refuted` | Evaluated, and false: the static error `E2032`, so a program that runs has none |
| `undecided` | Anything else: a non-constant argument, a call inside the condition, or the work limit reached |

The computed value is `{"call_sites": N, "proved": p, "refuted": r, "undecided": u}`.
**`N = 0` is a valid result**, and it is not evidence of anything: a function that nobody calls has
no call site where its `needs` could be decided. Nothing is inferred from the absence of a call or
of a counterexample.

**Observed** (phase 2). The unit is one **example run**: one evaluation of one selected example by
`nex test` **[V]**, in any function: an example of `f` that calls `g` observes the clauses of `g`
too. For each pair (clause, example run), exactly one of:

| Outcome | When |
|---------|------|
| `not_reached` | The clause was never evaluated during that example, including when the example stopped before reaching it |
| `held` | The clause was evaluated at least once, and every evaluation was true |
| `failed` | One evaluation was false. Evaluation stops at that point **[V]**, so it is the last one, and the example ends in `error` |

The computed value is
`{"examples_run": E, "examples_held": h, "examples_failed": f, "examples_not_reached": E - h - f, "evaluations": v}`,
where `v` counts every evaluation of the clause in every example run (a clause in a recursive
function or a loop is evaluated many times in one example). A clause that held in an example whose
expression was false (`failed` in `nex test`) still `held`: the example result and the clause
outcome are different facts. With `--function`, only the selected examples run **[V]**, and
`examples_run` counts only those.

Two cases without observations, which are not the same:

| Case | `observed` | Summary, when nothing else applies |
|------|------------|-------------------------------------|
| `nex test` ran, but no example was selected (its status `no_examples` **[V]**) | `computed`, with `examples_run` `0` and every count `0` | `checked` |
| `nex test` ran nothing because of static errors (its status `not_run` **[V]**) | `not_computed`, reason `static_errors` | `checked` |

In both, `checked` only says that the clause is evaluated when the program runs; neither turns an
absence of examples into evidence.

### 5.5 The summary word

One word per clause, derived from the dimensions by the first rule that applies. **Each word names
the single dimension it comes from**, so the summary never mixes a static fact, an observation and a
declaration:

| Order | Summary | Comes from | Condition |
|-------|---------|------------|-----------|
| 1 | `broken` | Observed | `examples_failed > 0` |
| 2 | `trusted` | Enforcement | The clause is `trust` |
| 3 | `proved` | Static | Static computed, `call_sites >= 1` and `proved == call_sites` |
| 4 | `exemplified` | Observed | Observed computed and `examples_held > 0` |
| 5 | `checked` | Enforcement | Anything else |

- `trusted` cannot compete with any other row: a `trust` clause has neither a static nor an observed
  dimension (5.2).
- A `needs` that is `proved` and also held in examples is summarized `proved`; the dimensions keep
  both facts.
- **A conflict is a defect, not a result.** A conflict exists only in a document where both static
  and observed were computed, and only **at one call site**: an evaluation of a `needs` failed at a
  call site whose static result is `proved`. The call site of the failure is known, because `E4001`
  points at the call **[V]** (spec 9.2). Then the evaluator of constants and the interpreter disagree
  about the same call with the same constants; the command stops as an internal error (code `70`)
  instead of choosing one. As for any internal error of `nex test` **[V]**
  ([0008](0008-ejemplos-y-nex-test.md), 3.4), it writes **no** evidence document and no partial
  report, in text or JSON, so no summary is derived; the `E4001` of that example is not reported as
  an example in `error`. The internal error message names the clause, the call site, its static
  result and the failed evaluation. Before phase 4 the static dimension is never computed, so no
  conflict can occur. A failure at an `undecided` call site is **not** a conflict: static
  evidence says nothing about that call, and the summary is `broken` by rule 1. Static evidence never
  covers a call that is not in the text of the program, and observed evidence never covers a call no
  example reached.
- The summary depends on what was computed: the same clause can be `checked` in
  `nex check --evidence` and `exemplified` in `nex test --evidence`. That is why the document
  carries `computed` (5.3).

What the words do not claim: `exemplified` is "held in these examples", not "holds"; `checked` is
"a violation stops the program", not "never violated"; `proved` is "decided at every call site of
this program", not for callers that do not exist yet.

### 5.6 `trust`

A `trust` clause states something the program relies on and the language does not check. Its
condition is type-checked (`Bool`, `E2011`) and never evaluated, so it cannot fail and cannot stop
the program. Its explanation is required. Removing every `trust` clause from a program does not
change what it does.

**A trusted condition is neither proved nor checked.** NEXORA does not evaluate it when running,
does not decide it before running, in any phase, and does not observe it in examples (5.2). The
evidence word `trusted` says exactly that: the only thing behind the condition is the explanation
written by a person. A tool, a report or a document must never present a `trust` clause as
verified.

### 5.7 Data model: `nexora.evidence/1`

One entry per `needs`, `promises`, `keeps`, `shrinks` and `trust` of every function, in the order
of the file. In `nex test --evidence` for `percentage` (4.2), before phase 4:

```json
{
  "id": {"module": "", "function": "percentage", "name": "whole_positive", "kind": "needs",
         "stable": true},
  "condition": "whole > 0",
  "message": "A percentage of nothing is not defined",
  "enforcement": "checked",
  "static": {"status": "not_computed", "reason": "phase_not_implemented"},
  "observed": {"status": "computed", "examples_run": 2, "examples_held": 2, "examples_failed": 0,
               "examples_not_reached": 0, "evaluations": 2},
  "summary": "exemplified"
}
```

With phase 4, `static` would be `{"status": "computed", "call_sites": 2, "proved": 2, "refuted": 0,
"undecided": 0}` (the two calls in the examples) and `summary` would be `proved`. For
`promises in_range`, `static` is always `{"status": "not_applicable"}`. A `trust` has
`"enforcement": "trusted"`, both other dimensions `not_applicable`, and `summary` `trusted`.

### 5.8 Reports

`nex check --evidence` (phase 1; runs nothing):

```text
percentage.nex: 4 promises in 1 function (computed: enforcement)
  percentage
    needs whole_positive    checked
    needs part_inside       checked
    needs fits              checked
    promises in_range       checked
```

`nex test --evidence` (phase 2; runs only the examples):

```text
percentage.nex: 4 promises in 1 function, 2 examples run (computed: enforcement, observed)
  percentage
    needs whole_positive    exemplified   held in 2 of 2 examples
    needs part_inside       exemplified   held in 2 of 2 examples
    needs fits              exemplified   held in 2 of 2 examples
    promises in_range       exemplified   held in 2 of 2 examples
```

The boundary of [0008](0008-ejemplos-y-nex-test.md) does not move: the analysis never runs anything.

## 6. What the checker can guarantee for `percentage`

| Property | Guaranteed by | When |
|----------|---------------|------|
| Every clause is a well-typed `Bool`; names are unique; `result` appears only in `promises` | `nex check` | Before running: types **[V]** today, names **[P]** |
| `whole > 0`, `0 <= part <= whole` and `part <= 92233720368547758` hold before the body runs | The interpreter evaluates every `needs` before the body; a false one stops the call with `E4001` **[V]** | Every call, at run time |
| The division by `whole` cannot be `E3001` | Follows from the previous row | Every call that reaches the body |
| `part * 100` cannot be `E3002` | Follows from `fits`: `92233720368547758 * 100 = 9223372036854775800`, below the `Int` maximum `9223372036854775807` | Every call that reaches the body |
| `0 <= result <= 100` | Evaluated when the function returns; a false one stops with `E4002` **[V]** | Every call that returns |
| That the promise **always** holds | **Nothing.** It is true by arithmetic, but NEXORA does not prove promises: its evidence is `checked`, and `exemplified` after `nex test --evidence` | — |
| That a call with constant arguments meets the `needs` | Phase 4 only: `percentage(3, 12)` would be `proved` at that call site | Before running, with phase 4 |

Without `fits`, a call that meets the other two `needs` (`part = whole = 100000000000000000`) stops
with `E3002` in `part * 100` before the promise is evaluated; checked for this revision with the
0.11 interpreter. Integer division of non-negative numbers rounds down: `percentage(1, 3)` is `33`.

## 7. Identity and `nex impact` **[P]**

### 7.1 Identities and normal forms

| Entity | Identity within one version | Unique because |
|--------|-----------------------------|----------------|
| Module | Its path relative to the directory of the entry file, with `/`, as [0018](0018-modulos-e-importaciones.md) reports it; `""` for the entry file | One file, one path |
| Function | `(module, name)` | `E2002` **[V]** |
| Named clause | `(module, function, name)`; its kind is an attribute | `E2031` **[P]** |
| Unnamed clause | No identity. It is described by `(module, function, kind, normalized condition)`, which may repeat | — |
| Example | No identity. It is described by `(module, function, normalized expression)`, which may repeat | — |

The **normalized form** of a condition or expression is its sequence of tokens (type and value),
without whitespace or comments. Two conditions are *equal* when their normalized forms are equal.
No other comparison exists: not meaning, not equivalence.

### 7.2 Matching algorithm

`nex impact before.nex after.nex` requires both programs to pass `nex check` in the new syntax
(code `1` otherwise; a program in the old syntax gets the hint `nex migrate`). Then, in order:

1. **Declared renames** are read first:
   `--rename-module OLD=NEW`, `--rename-function MOD:OLD=MOD2:NEW`, `--rename-clause MOD:FN:OLD=NEW`.
   Each old identity may appear at most once and each new one at most once; an old identity that
   does not exist in `before`, a new one that does not exist in `after`, or a target that is also
   matched by name is a usage error (code `2`). Declared renames are applied before anything else
   and reported as `declared`.
2. **Modules** are matched by equal path. Unmatched ones are `added` or `removed`, with everything
   they contain. A moved file is never inferred.
3. **Functions** of matched modules are matched by equal name. Unmatched ones are `added` or
   `removed`, with all their clauses. A renamed function is never inferred.
4. **Named clauses** of matched functions are matched by equal name. For the unmatched ones, a
   clause rename is **inferred only** when an unmatched old clause and an unmatched new clause have
   the same kind and an equal condition, and **each is the only such candidate of the other**. Then
   it is `renamed (inferred)`. If a clause has more than one candidate, every clause involved is
   reported as `ambiguous`, with the candidates, and none of them is matched: the person declares the
   right pairs with `--rename-clause`. The rest are `added` or `removed`.
5. **Unnamed clauses** of matched functions are grouped by kind and normalized condition. For each
   group with `k` old and `m` new clauses, `min(k, m)` are `unchanged` and the difference is
   `added` or `removed`. An edited unnamed clause is therefore one `removed` and one `added`: without
   a name, an edit cannot be told apart from a replacement, and the report says so.
6. **A clause that gains or loses a name** (unnamed old, named new, same kind and equal condition) is
   `named (inferred)` under the same uniqueness rule as step 4, and `ambiguous` otherwise.
7. **Examples** are matched like unnamed clauses, by normalized expression.
8. **Attributes** of matched entities are compared: condition (`condition_changed`), explanation
   (`explanation_changed`), kind (`kind_changed`), header of the function or of one of its loops
   (`location_changed`), parameters or `gives` (`signature_changed`), `pub` (`visibility_changed`).

The report is ordered by module path, then function name, then clause name or normalized
condition, all compared by code point, so the same two programs always give the same report.
Exit codes: `0` when the comparison is done, whatever it found, including ambiguities; `1`, `2`
and `4` as in the other commands. The JSON format is `nexora.impact/1`.

### 7.3 Examples

| # | Change (in function `percentage` unless said) | Report |
|---|-----------------------------------------------|--------|
| I1 | `needs fits: part <= 92233720368547758` becomes `needs fits: part <= 1000000` | `fits`: `condition_changed`, with both conditions |
| I2 | `needs fits:` renamed `needs no_overflow:`, same condition | `fits` → `no_overflow`: `renamed (inferred)` |
| I3 | `needs a: whole > 0` and `needs b: whole > 0` (same condition) renamed `c` and `d` | `a`, `b`, `c`, `d`: `ambiguous` (each old clause has two candidates). With `--rename-clause :percentage:a=c --rename-clause :percentage:b=d`: two `renamed (declared)` |
| I4 | The function is renamed `share` | Function `percentage` `removed` and `share` `added`, each with its clauses. With `--rename-function :percentage=:share`: function `renamed (declared)`, and its clauses compared as in I1–I3 |
| I5 | An unnamed `needs whole > 0` becomes `needs whole >= 1` | One `removed` (`whole > 0`) and one `added` (`whole >= 1`) |
| I6 | An unnamed `needs whole > 0` becomes `needs whole_positive: whole > 0` | `named (inferred)` |
| I7 | `app/models.nex` moves to `app/shapes.nex` | Every function of `app/models.nex` `removed` and of `app/shapes.nex` `added`. With `--rename-module app/models.nex=app/shapes.nex`: compared function by function |
| I8 | `needs fits` becomes `promises fits` with the same condition | `fits`: `kind_changed` |

What it never says: whether a changed condition is weaker or stronger, whether two different
conditions are equivalent, or whether the program behaves the same.

## 8. Migration **[P]**

### 8.1 One syntax, not two

The new parser accepts only the new syntax. Accepting both would double the parser, the formatter,
the language server, the highlighting and the tests, and leave two ways of writing the same thing.

### 8.2 Two routes, decided per program

`nex migrate` works on a whole program: the entry file and every module it imports, all or nothing
in its checks: every file is checked, and re-read, before any file is written (G7). Writing several
files is not atomic (section 11).

```text
nex migrate program.nex            # shows the migrated text and the list of edits; writes nothing
nex migrate program.nex --write    # writes, only if every check of 8.3 passed
```

It first checks the **whole program** with both front ends: the frozen 0.11 front end (lexer,
parser and checker, carried only for this command) and the 0.12 one. Both use the rules of the
analysis without `main` that `nex test` already uses (`require_main=False` in `pipeline.analyze`
**[V]**), so that a module that is only a library can be migrated on its own.

| 0.11 check | 0.12 check | Route | Result |
|------------|------------|-------|--------|
| Passes | Fails | **Migrate** | 8.3 to 8.6; code `0` when written or shown |
| Fails | Passes | **Already migrated** | Nothing is edited, nothing is written; it says so; code `0` |
| Fails | Fails | **Refuse** | Code `1`. It prints, per file, which syntax markers it found (8.2.1) and the diagnostics of both front ends, and writes nothing |
| Passes | Passes | **Nothing to migrate**, after two safety checks | No file contains a function (8.2.2). Nothing is edited or written. The tool still refuses, with code `1`, a program that imports a module named like a new keyword (8.2.2), and parses every file with both parsers and compares the trees (8.4): if they are equal, code `0`; if not, the program is read differently by the two versions and it is **refused** with code `1`. In every case it writes nothing |

A program that mixes the two syntaxes, in one file or across files, passes neither check and is
refused: neither route accepts it, and nothing is chosen for the person.

#### 8.2.1 Markers, for the diagnosis only

To explain a refusal, each file is described by the tokens it contains, without deciding anything:

| Marker | Old | New |
|--------|-----|-----|
| Tokens | `->`; the keywords `requires`, `ensures`, `invariant`, `decreases` | `gives`, `needs`, `promises`, `keeps`, `shrinks`, `trust` used as keywords by the 0.12 parser |

A file with both kinds is reported as *mixed*; with none, as *neutral* (only types, imports or
`uses`). The markers explain; the route is decided only by the two checks of 8.2.

#### 8.2.2 When both checks pass

**What is shown.** A program with a function cannot pass both checks:

| # | Premise | Evidence |
|---|---------|----------|
| 1 | A file contains only imports, `uses`, refined types, records and functions | The rule `program` of the 0.11 grammar **[V]** (spec 3); 0.12 keeps it (section 3) **[P]** |
| 2 | In 0.11 every function signature contains the token `->`, on the line of the `)` | The rule `function` requires `"->" type` **[V]** (spec 3); `fn main() {` is `E1101`, and `)` on one line with `->` on the next is `E1101` **[V]**, both checked for this decision |
| 3 | In 0.12 no token `->` is valid | The 0.12 grammar (4.1) has no `->`: `E1108` after the parameters, `E1101` anywhere else **[P]** |

From 2 and 3, a program that passes both has no function. That part is a proof from the two
grammars, and it depends only on premise 3 being implemented as written.

**What is audited, not proved.** Whether a program without functions needs an edit or means
something different in 0.12. Every difference this decision introduces, against every construct
that can exist without functions:

| Difference 0.11 → 0.12 | Where it could appear without functions | Effect on the two checks |
|------------------------|------------------------------------------|--------------------------|
| Six new keywords | A field name, a module name written in a type (`needs.Point`), a name inside a refined condition | Fails 0.12 (`E1101`): not "both". **Exception**: a module imported and never written, whose file is named like a keyword (`import "m/needs.nex"`). In 0.11 the same case with a reserved word passes, and the module cannot be used (`import "mods/match.nex"` passes; writing `match.T` is `E1101`) **[V]**. 0.12 does the same (section 13, detail 10), so the program can pass both checks. `nex migrate` **refuses** it in the routes "migrate" and "nothing to migrate" (8.6): no edit would be wrong, but the module could never be used again by its name, and the file has to be renamed by a person |
| `ai`, `tool` released | A field or module name | Fails 0.11 (`E1103`, reserved today): not "both" |
| `requires`, `ensures`, `invariant`, `decreases` reserved for one version | — | Keywords in 0.11, so they cannot be names there: no case |
| `->` and `Void` | `Void` in a field or as the base of a refined type | Fails 0.11 already (`E2012`) **[V]** (spec 11.3): not "both" |
| `unwrap` and `unwrap_or` renamed | A refined condition: it may call built-in functions (`E2018` forbids only functions of the program **[V]**; a `where` with `Option.unwrap_or` passes in 0.11, checked) | Fails 0.12 (`E2008`): not "both" |
| `value` and `value_or` added | A refined condition | Fails 0.11 (`E2008`): not "both" |
| Header clauses, names, `trust`, evidence | Only in functions and loops | No case |

So, as far as this decision defines 0.12, a program that passes both needs no edit. What cannot be
shown before 0.12 exists is that its implementation reads those constructs exactly as 0.11 does.
The route covers that safely: it writes nothing in any case, it compares the trees and refuses if
they differ, and it claims nothing about behaviour. A difference in evaluation that leaves the trees
equal (for example, a refined condition evaluated differently) is **not** detected by the tool; only
the tests T2 and T3 of 8.9 measure it, on their corpus. If a function or an applicable edit is ever
found in a program that passed both checks, premise 3 is broken: code `70`, nothing written.

Cases that would refute these rules, and what the rules say:

| Program | 0.11 | 0.12 | Route |
|---------|------|------|-------|
| `type R = { needs: Int }` | Passes | Fails | Migrate, then refused: a keyword used as a name (8.6) |
| `type P = Int where Option.unwrap_or(Some(value), 0) > 0` | Passes **[V]** | Fails | Migrate, with E4 |
| `type R = { tool: Int }` | Fails | Passes | Already migrated, nothing written |
| `import "m/needs.nex"`, never used, in a file with only types | Passes | Passes (section 13, detail 10) | Refused (8.6), nothing written |

### 8.3 Guarantees

| # | Guarantee | How it is enforced |
|---|-----------|--------------------|
| G1 | The migrate route only runs on programs that pass the 0.11 check | 8.2 |
| G2 | The text changes only through the edits of 8.5; every byte outside them is identical | The output is built from the original text and the list of edits of 8.5, never re-rendered. The formatter is not used: it re-indents lines and changes the spacing between tokens, which G2 does not allow outside the edits. Before writing, the tool compares every byte outside the edits with the original (8.5.4) |
| G3 | **Structural equivalence** (8.4) between the original and the migrated program | Checked for every file before writing. If it fails, nothing is written: code `70`, because the edits of 8.5 are designed to preserve it |
| G4 | The migrated program passes the 0.12 check | Checked before writing. If it fails, nothing is written: code `70` |
| G5 | Refusal instead of guessing | The refusals of 8.6: nothing is written, every reason is listed with its position, code `1` |
| G6 | Determinism and idempotence | The same input gives the same output; running it on its own output takes the route "already migrated" |
| G7 | Nothing is written unless every file of the program passed G1–G5 and the final re-read | All edits and outputs are computed in memory first. Then **every** file is read again and compared with the bytes that were migrated, before any file is replaced; if one differs, the migration is refused (8.6) and **no file is written**. Only then is each output written, file by file in the order of their paths: to a **temporary file** in the same directory, created only if no file with that name exists, whose name is the name of the original, a random part and `.tmp`, so that it **never ends in `.nex`**; the temporary file receives the **permission bits** of the original; then it is put in place of the original with one rename. A change made to a file after that final re-read is **not** detected and is overwritten. Replacing several files is **not** one atomic transaction: each rename is separate (section 11). **On the first failed write** (creating or writing the temporary file, copying the permission bits, or the rename): `nex migrate` stops and does not try the other files; it deletes the temporary file of the failed one if it exists; it does not restore the files already replaced; it prints three lists (the files replaced, the file that failed with the system's error, and the files not written) and exits with code `4` (8.7.1). An interruption the tool receives (Ctrl+C) is handled the same way, with the code `130` every `nex` command already uses. After a crash or a power cut nothing is cleaned up: a temporary file may be left behind; its name does not end in `.nex`, so no program imports it and `nex migrate` never reads it |

#### 8.3.1 What each guarantee is today

Nothing of `nex migrate` exists. Each property is in one of four states, and none is more than its
state says:

| Property | Specified here | Can be checked mechanically once implemented | Only argued | Needs real tests |
|----------|----------------|-----------------------------------------------|-------------|------------------|
| G1 Valid 0.11 input | Yes (8.2) | Yes: the frozen 0.11 check | — | T6 |
| G2 Bytes outside the edits | Yes (8.5) | Yes: the comparison of 8.5.4, on every file | — | T4, and the cases M1–M12 |
| G3 Structural equivalence | Yes (8.4) | Yes: the comparison of trees | — | T1 |
| G4 Valid 0.12 output | Yes | Yes: the 0.12 check | — | T1, T8 |
| G5 Refusals | Yes (8.6) | Yes, each refusal is a rule on the text or the tree | — | T5 |
| G6 Determinism and idempotence | Yes | Partly: idempotence by running it again | — | T7 |
| G7 Writing | Yes | Partly: the re-read before writing, and the removal of the temporary file after a detected failure | — | T5 for a changed file and T9 for failed writes, both through the injection of 8.9.2; a crash or a power cut cannot be injected (section 11) |
| Semantic equivalence | As intent (8.4.2) | **No**: there is no 0.12 specification to compare with | Yes | — |
| Behaviour after migration | No | **No** | — | T2, T3, and only on their corpus |

None of T1–T9 or M1–M12 exists or has been run.

### 8.4 What structural equivalence means

**Structural equivalence** is equality of syntax trees after a fixed mapping. The original is parsed
by the 0.11 parser and the result by the 0.12 parser; each tree is passed through the mapping below;
the two results must be equal, field by field. It compares only what the 0.11 tree records.

| Element | Compared | Normalized before comparing | Not compared |
|---------|----------|-----------------------------|--------------|
| Positions (`span`, `name_span`, line, column) | No | — | Always: lines move |
| Declarations, their order, names, parameters, types, `pub`, imports, `uses` | Yes, exactly | — | — |
| Result type | Yes | 0.11 `Void` and 0.12 "no `gives`" are the same value | — |
| Clauses of a function | Yes: kind, condition tree, explanation, in their order among themselves | Kind: `requires` = `needs`, `ensures` = `promises` | — |
| Examples of a function | Yes: expression tree, explanation, in their order among themselves | — | Their order relative to the clauses (8.4.1) |
| Loop clauses | Yes: kind, expression tree, explanation, in their order | `invariant` = `keeps`, `decreases` = `shrinks` | — |
| Clause names | Yes | The 0.11 tree has none; every 0.12 name must be absent | — |
| Calls | Yes: callee, qualifier, arguments | `Option.unwrap` = `Option.value`, `Option.unwrap_or` = `Option.value_or`, and the same for `Result` | — |
| Statements and expressions of the bodies | Yes, exactly | — | — |
| Comments and whitespace | No: they are not in the tree | — | Covered by G2 |

#### 8.4.1 The order of clauses and examples

The 0.11 tree keeps contracts and examples in **separate lists** (`Function.contracts`,
`Function.examples` **[V]**). The order in which they are interleaved in the text is not in the tree,
so structural equivalence **does not cover it**, and nothing in this decision claims that it does.

What is guaranteed during a migration: the interleaving in the text is kept, because no edit moves
a clause or an example line (8.5); G2 checks it byte by byte, and T4 measures it on the corpus. A
migration that swapped an example and a clause would pass G3 and fail G2.

Whether it matters: in 0.11 it does not change behaviour. The order **among** the `requires` is
observable, because a condition may call a function that prints: `requires noisy(1)` and
`requires noisy(2)` print `1` and `2` in that order **[V]** (checked for this decision); that order
is in the list of contracts and is compared. An example is never evaluated by a call, only by
`nex test`, so its position among the clauses changes nothing at run time.

**Decided** (section 13, detail 9): **the 0.12 tree and `nexora.inspect/3` keep the header as one
ordered list**, in the order of the source file. `Function` has a field `header`, a list of items
`needs`, `promises`, `trust` and `example`, each with its `kind`, instead of the two lists
`contracts` and `examples`. Loops already keep their clauses in one list (`clauses` **[V]**).

- Why: the header is one block of the interface (P1), and a tool that shows it, the evidence report
  ("in the order of the file", 5.7) and `nex impact` (`location_changed`, 7.2) must show it as it
  is written. Two lists would lose an order that the text has.
- Consequences: `inspect/3` removes `contracts` and `examples` from `Function` and adds `header`;
  it was already a new version (8.8), so no further version is needed. Behaviour does not change:
  the `needs` are still evaluated in their order, and the examples are still evaluated only by
  `nex test`, in their order.
- For migration: structural equivalence projects `header` onto two lists (its clauses in order, its
  examples in order) and compares them with the two lists of the 0.11 tree. The interleaving itself
  is checked only by G2, never by G3.

#### 8.4.2 What is shown, what is argued and what is measured

| Property | Status | Basis |
|----------|--------|-------|
| **Structural equivalence** (8.4) | **Checked mechanically**, per file, by `nex migrate` (G3) once it exists **[P]** | Equality of trees under the mapping; it says nothing about meaning |
| **Text outside the edits** (G2) | **Checked mechanically**, per file, byte by byte **[P]** | 8.5.4 |
| **Semantic equivalence**: the mapped pairs mean the same | **Argued, not shown.** The 0.12 specification does not exist yet, so there is nothing to compare with: the argument is that this decision gives each mapped pair the same rules (`needs` keeps the rules of `requires` in spec 9, evaluated in the same order; `promises` those of `ensures`; `keeps` and `shrinks` those of `invariant` and `decreases`; `gives T` is `-> T`; `value` and `value_or` behave as `unwrap` and `unwrap_or`). The 0.12 specification has to adopt those rules; until it does, this is a statement of intent | This decision |
| **Behavioural preservation**: the same exit code, output and diagnostic codes | **Measured, not guaranteed**, and only on the corpus of 8.9 (T2, T3), once those tests exist. Messages are compared through the correspondence of 8.9.1: their text changes on purpose (`needs` instead of `requires`), so the standard error is **not** byte-identical | T2, T3 |

None of T1–T9 exists or has been run. `nex migrate` prints only what it checked:
*"structure verified; text outside the edits verified; behaviour not checked by this command"*.

### 8.5 Edits, comments and spacing

#### 8.5.1 Coordinates

- The file is read as `nex` reads it **[V]** (`cli.py`): bytes decoded as strict UTF-8, with a
  byte-order mark accepted and removed (`utf-8-sig`); invalid UTF-8 is not migrated (exit `4`, as
  today). The **text** is the decoded result without the mark.
- A **line ending** is `\r\n`, `\n` or a lone `\r`, as the lexer reads them **[V]** (`lexer.py`:
  each one is one line end; space and tab are the only other whitespace; a comment ends before
  `\r`, `\n` or the end of the text). All three were checked to pass `nex check` in 0.11.
- A **position** is an offset in the text, counted in characters: the lexer counts columns in
  characters, a tab is one column **[V]**. `(line, column)` is turned into an offset with the same
  line endings.
- Every edit is a half-open range `[a, b)` of the original text and its replacement. An insertion
  has `a = b`.

#### 8.5.2 The edits

| Edit | Range `[a, b)` | Replaced by |
|------|-----------------|-------------|
| E1 | The token `->` | `gives` |
| E2 | For `-> Void`: from the end of `)` to the end of `Void`. Only spaces, tabs and those two tokens are in it: `->` is on the line of `)` (8.2.2, premise 2), and a comment would end the line | nothing |
| E3 | The token `requires`, `ensures`, `invariant` or `decreases` | `needs`, `promises`, `keeps` or `shrinks` |
| E4 | The name `unwrap` or `unwrap_or` after `Option.` or `Result.`, where the 0.11 checker resolved the call to the built-in type | `value` or `value_or` |
| E5a | With clauses, when the `{` that opens the body is on the line of the token before it (every loop **[V]**, and functions written so): from the end of that token to the end of `{` | nothing |
| E5b | With clauses, when the `{` is the first thing on its line and only spaces or tabs follow it: the whole line, from its first character to the end of its line ending | nothing |
| E5c | With clauses, when the `{` is the first thing on its line and a comment follows it: from the `{` to the start of the comment | nothing |
| E6 | With clauses: an insertion at the end of the line ending of the line `L` that holds the last token of the last clause | The leading spaces and tabs of the line that holds the `fn` token (or `pub`, when present; or the `while`/`for` token), then `{`, then the line ending of `L` |
| E7 | Without clauses, when the 0.11 `{` is the first thing on its line and only spaces or tabs follow it (valid in 0.11 **[V]**): two parts, (a) that whole line, line ending included, and (b) an insertion at the end of the last token of the signature (`Void` or the result type) | (a) nothing; (b) ` {` |

`L` always has a line ending: a clause ends with one by the grammar, and anything that would put
the body on the line of the last clause is refused (8.6).

#### 8.5.3 Order and overlap

All edits are computed on the original text, never on a partly edited one. Their ranges never
overlap:

- E1, E3 and E4 cover single tokens, all different.
- E1 and E2 never both apply: one is for `-> T`, the other for `-> Void`.
- E2 ends at the end of `Void`; E5a then starts at the end of `Void` and E7(b) inserts there. They
  touch at one point and share no character.
- E5 covers only the `{`, the whitespace before or after it, or its own line; E6 is after the last
  clause, so after every E5; E7 only exists without clauses, so never with E5 or E6.
- E3 and E4 are inside clause or body lines; E5b and E7(a) delete lines that contain only a `{` and
  whitespace.

The output is built by sorting the edits by `a`, copying the original text between them and writing
each replacement. An insertion at a point where a deletion ends goes after it. If two edits ever
overlap, the tool has a defect: code `70`, nothing written.

#### 8.5.4 Checking G2

Before writing, for every gap between two consecutive edits, the characters of the original text
and of the output are compared; since both are encoded as UTF-8 and the byte-order mark, if any, is
written back as it was, equal characters are equal bytes. A difference is a defect: code `70`,
nothing written.

#### 8.5.5 Cases

These are the expected results that define the edits; phase 1 turns them into tests (T4). **None
has been run.** `⏎` is `\n`, `␍⏎` is `\r\n`, `␍` a lone `\r`.

| # | Original | Migrated | Edits | What happens to comments and blank lines |
|---|----------|----------|-------|------------------------------------------|
| M1 | `fn f(x: Int) -> Int { // entry⏎`<br>`    requires x > 0⏎`<br>`    return x⏎`<br>`}⏎` | `fn f(x: Int) gives Int // entry⏎`<br>`    needs x > 0⏎`<br>`{⏎`<br>`    return x⏎`<br>`}⏎` | E1, E5a, E3, E6 | The comment text and its line are kept; it moves **one column right**: E1 adds three characters before it and E5a removes two |
| M2 | `fn g(x: Int) -> Int {⏎`<br>`    // input⏎`<br>`    requires x > 0⏎`<br>`⏎`<br>`    ensures result > 0 // positive⏎`<br>`    // body⏎`<br>`    return x⏎`<br>`}⏎` | `fn g(x: Int) gives Int⏎`<br>`    // input⏎`<br>`    needs x > 0⏎`<br>`⏎`<br>`    promises result > 0 // positive⏎`<br>`{⏎`<br>`    // body⏎`<br>`    return x⏎`<br>`}⏎` | E1, E5a, E3 ×2, E6 | `// input`, the blank line and `// body` keep their line and column; `// positive` keeps its line and moves **one column right**, because E3 writes `promises` (8 characters) for `ensures` (7) before it. `// input` and the blank line are now in the header, `// body` in the body |
| M3 | `fn h(x: Int) -> Int␍⏎`<br>`{␍⏎`<br>`    requires x > 0␍⏎`<br>`    return x␍⏎`<br>`}␍⏎` | `fn h(x: Int) gives Int␍⏎`<br>`    needs x > 0␍⏎`<br>`{␍⏎`<br>`    return x␍⏎`<br>`}␍⏎` | E1, E5b, E3, E6 | No comments. The inserted line ends with `\r\n`, copied from the clause line |
| M4 | `fn k(x: Int) -> Int⏎`<br>`    {   // checks⏎`<br>`    requires x > 0⏎`<br>`    return x⏎`<br>`}⏎` | `fn k(x: Int) gives Int⏎`<br>`    // checks⏎`<br>`    needs x > 0⏎`<br>`{⏎`<br>`    return x⏎`<br>`}⏎` | E1, E5c, E3, E6 | The comment keeps its text and its line, now in the header; it moves **four columns left** (`{` and three spaces deleted); the indentation before it is kept |
| M5 | `fn log(x: Int) -> Void {⏎`<br>`    requires x > 0⏎`<br>`    print(x)⏎`<br>`}⏎` | `fn log(x: Int)⏎`<br>`    needs x > 0⏎`<br>`{⏎`<br>`    print(x)⏎`<br>`}⏎` | E2, E5a, E3, E6 | — E2 and E5a touch at the end of `Void` |
| M6 | `fn one() -> Int // unit⏎`<br>`{⏎`<br>`    return 1⏎`<br>`}⏎` | `fn one() gives Int { // unit⏎`<br>`    return 1⏎`<br>`}⏎` | E1, E7 | The comment keeps its text and its line; it moves **five columns right**: E1 adds three characters and E7(b) inserts two before it |
| M7 | `fn one() -> Int⏎`<br>`// doc⏎`<br>`{⏎`<br>`    return 1⏎`<br>`}⏎` | `fn one() gives Int {⏎`<br>`// doc⏎`<br>`    return 1⏎`<br>`}⏎` | E1, E7 | The comment keeps its line and column, and is now the first line of the body |
| M8 | `    while i < n {⏎`<br>`        decreases n - i⏎`<br>`        i = i + 1⏎`<br>`    }⏎` | `    while i < n⏎`<br>`        shrinks n - i⏎`<br>`    {⏎`<br>`        i = i + 1⏎`<br>`    }⏎` | E5a, E3, E6 | The inserted `{` copies the four spaces before `while` |
| M9 | A file whose lines end with a lone `\r` | Inserted lines end with `\r` | As above | As above |
| M10 | A file that starts with a byte-order mark | The mark is written back first, unchanged | As above | As above |
| M11 | A file whose last line has no line ending (`}` at the end) | That line is unchanged, still without a line ending | None there | — |
| M12 | Indentation with tabs | E6 copies the tabs | E6 | — |

Where a comment can end up, in general: a comment line or a blank line between the signature and
the body is never edited, so it keeps its line and column, on the side of the inserted `{` given by
M2 and M7. A comment at the end of a line that has edits before it (E1, E3, E4, E5a, E5c, E7(b))
keeps its text and its line, and moves by exactly the **net** number of characters those edits add
or remove before it (M1: +3 − 2; M2: +1; M4: −4; M6: +3 + 2). The rules never claim that such a
comment keeps its column.

### 8.6 Refusals

Each refusal names the file, the line and what the person has to do. Nothing is written.

| Case | Why it cannot be decided | Message (draft) |
|------|--------------------------|-----------------|
| A clause on the same line as the `{` (`fn f(x: Int) -> Int { requires x > 0`), valid in 0.11 **[V]** | E5 and E6 would have to split a line | `Put 'requires' on its own line, then run nex migrate again` |
| The last clause followed by `}` on the same line (`fn g(x: Int) -> Void { requires x > 0 }`), valid in 0.11 **[V]** | The same | The same |
| Without clauses, a 0.11 `{` first on its line and followed by a comment (`{ // note`) | E7(a) would delete the comment, or the comment would have to go to the signature line or stay alone after the `{`: a choice about where it belongs | `Move this comment, then run nex migrate again` |
| Without clauses, a 0.11 `{` first on its line and followed by a statement (`{ return 1`), valid in 0.11 **[V]** | E7(a) would delete the statement | `Put the first statement on its own line, then run nex migrate again` |
| A name equal to `needs`, `gives`, `promises`, `keeps`, `shrinks` or `trust` (variable, parameter, function, field), or an imported module whose file is named like one of them, **whether or not the program writes its name** | The new name is the person's choice | `'needs' is a keyword from 0.12: rename it` (for a module: `rename the file 'needs.nex'`) |
| A file whose bytes differ, in the final re-read of G7, from those that were migrated | The edits were computed for other bytes. Only changes made before that re-read are detected (G7) | `This file changed while it was being migrated: run nex migrate again` |
| The program is not a 0.11 program and not a 0.12 program | 8.2 | The diagnostics of both front ends |

### 8.7 Diagnostics

| Code | When | Message (draft) | Lifetime |
|------|------|-----------------|----------|
| `E1107` | `requires`, `ensures`, `invariant` or `decreases` | `'requires' is the syntax before 0.12: write 'needs' in the header of the function` + hint `nex migrate` | One minor version |
| `E1108` | `->` after the parameters | `Write 'gives Int' instead of '-> Int'` | One minor version |
| `E1106` (existing **[V]**) | A header clause inside a body | New text: `'needs' goes between the signature and the body` | Permanent |
| `E2031` | A clause name used twice in a function, or equal to a parameter or `result` | `The promise name 'fits' is used twice in 'percentage'` | Permanent |
| `E2032` | A `needs` refuted at a call site (phase 4) | `This call does not meet needs 'whole_positive' of 'percentage'` | Permanent |

`E1107`, `E1108`, `E2031` and `E2032` are free today **[V]** (`E1104` is retired, not free).

#### 8.7.1 Exit codes of `nex migrate`

| Code | When |
|------|------|
| `0` | The migrated text was shown or written; or the program was already migrated, or had nothing to migrate (8.2) |
| `1` | Refused (8.2, 8.6): nothing written |
| `2` | Wrong command-line usage |
| `4` | A file of the program could not be read, as for every command; or, with `--write`, a file could not be written (G7) |
| `70` | A defect of the tool (G3, G4, overlapping edits, 8.2.2): nothing written |
| `130` | Interrupted with Ctrl+C; with `--write`, handled as in G7 |

Code `4` keeps its meaning for every existing command: `cli-reference.md` documents it per
command ("the file does not exist, cannot be read or is not UTF-8" for `run`, `check`, `inspect`,
`context`, `symbols` and `test` **[V]**). For `nex migrate`, a new command, the row added in phase 1
says that it also covers a file that could not be written. No existing contract changes.

### 8.8 Formats

Each format comes in the phase that first produces it (8.11):

| Format | Change | New version |
|--------|--------|-------------|
| `nexora.inspect` | `Function.header`, one ordered list of `needs`, `promises`, `trust` and `example` items, replaces `contracts` and `examples` (8.4.1); `LoopClause.clause` takes `keeps`, `shrinks`; new field `name`; `Function.return_type` is `null` when there is no `gives` | **`/3`**: fields are removed and change meaning ([json-protocol.md](../json-protocol.md)). Phase 1 |
| `nexora.context` | The same clause names, plus `name` | **`/2`**. Phase 1 |
| `nexora.symbols` | Built-in contracts with the new clause names | **`/2`**. Phase 1 |
| `nexora.diagnostics`, `nexora.test` | New codes and clause names in messages: `E1107`, `E1108`, `E2031` in phase 1; `E2032` in phase 4 | `/1` |
| `nexora.evidence` | New. Phase 1 produces it with the enforcement dimension (`nex check --evidence`); phase 2 fills `observed` and phase 4 `static`, in the same fields (5.3) | `/1`, from phase 1 |
| `nexora.impact` | New | `/1`, from phase 3 |

### 8.9 Equivalence tests **[P]**

To be written in phase 1 and run before 0.12.0 is published. They compare the published **0.11.0**
package, installed from PyPI in its own environment, with the new version running the migrated
program. **None exists and none has been run.**

| Test | Corpus | Compared | Passes when |
|------|--------|----------|-------------|
| T1 Structural | Every file of the corpus | 8.4 | Equal for every file |
| T2 Behaviour | The corpus of 8.9.1 | As defined in 8.9.1 | Equal for every program of the corpus |
| T3 Examples | Every program with `example` | The `status` of every example in `nex test --format json` | Equal |
| T4 Text | Every file | The original and the migrated text outside the edits of 8.5 | Byte-identical |
| T5 Refusals | One program per row of 8.6 | Code `1`, the message and its position; nothing written | Always |
| T6 Routes | One program per row of 8.2, including mixed files and mixed programs | The route taken and the code | As in 8.2 |
| T7 Idempotence | The migrated corpus | `nex migrate` on its own output | Route "already migrated", no edits |
| T8 Acceptance | Every case of 4.3 | Accepted, or rejected with its code | As in 4.3 |
| T9 Failed writes | A program of three files, with a failure injected (8.9.2) at each step of G7 for the first, the second and the last file: creating or writing the temporary file, copying the permission bits, the rename; and an interruption | The three lists, the exit code, the files on disk and the temporary files left | Code `4` (`130` for the interruption); the files before the failed one are replaced, the failed one and the later ones are unchanged; no temporary file is left |

The release notes may say "the N programs of the corpus give the same results after migration",
with N, and nothing broader.

#### 8.9.1 The corpus, the harness and the comparison of T2

**Corpus.** A list of files written in phase 1 and kept with the tests, fixed at the commit where
phase 1 starts, so that T2 always runs on the same programs:

| Source | What enters | What does not |
|--------|-------------|---------------|
| `nexora/examples/` | Every program that passes the 0.11 check, with the run settings `tests/test_examples.py` already records for it **[V]** (expected exit code, standard input, arguments, own working directory) | The programs that do not pass the 0.11 check: `nex migrate` refuses them, so they belong to T5 and T6 |
| The documentation | Every block `tests/test_docs.py` runs **[V]**, with the behaviour its marker states (`nex:run`, `nex:fails`, `nex:test`…) | Blocks without a marker, and `nex:check-fails` blocks (T5, T6) |
| The test files | Only programs copied, in phase 1, into the corpus list, each with its run settings and a reviewed reason | Every other string inside a test file: many are fragments or invalid on purpose |

**Harness.** Each program of the corpus runs twice, with the same settings: once with the published
0.11.0 package on the original, and once with 0.12 on the migrated program. The settings are the
command (`run` or `test`), the arguments after the file, the text on the standard input, the grants
(`--allow-read`, `--allow-write`), and a working directory: a fresh copy of the files the program
uses, as `tests/test_examples.py` already does for `files.nex` **[V]**. A program that reads or
writes files runs in its own copy, so the two runs cannot see each other's output.

**Comparison.**

| What | Rule |
|------|------|
| Exit code | Equal |
| Standard output | Byte-identical |
| Each diagnostic: code and category | Equal, in the same order |
| Each diagnostic: position | The 0.11 position, carried to the migrated text through the edits of 8.5, equals the 0.12 position. A position inside a range that an edit replaced is carried to the start of its replacement |
| Line numbers inside a message or note (for example `The condition at line 2 is false`, `at line 14`) | Carried through the edits in the same way |
| Words inside a message or note | Equal after the correspondence below |

**Correspondence of diagnostics.** No such table exists today. This decision fixes what it has to
contain; the exact message texts of 0.12 are written in phase 1, and the table with them:

| 0.11 text | 0.12 text | Where it appears |
|-----------|-----------|------------------|
| `requires` | `needs` | The kind of a clause in notes (`requires n >= 0`), in labels (`a 'requires' condition`) |
| `ensures` | `promises` | The same |
| `invariant` | `keeps` | Loop diagnostics |
| `decreases` | `shrinks` | Loop diagnostics |
| `Option.unwrap`, `Option.unwrap_or`, `Result.unwrap`, `Result.unwrap_or` | `Option.value`, `Option.value_or`, `Result.value`, `Result.value_or` | Diagnostics that name the function |
| A result type `Void` | The wording phase 1 chooses for a function that gives nothing | Messages about the result of a function |

Every other word must be equal. A difference that this table does not explain makes T2 fail; it is
added to the table only with a reason, in the review of the phase 1 tests.

#### 8.9.2 Injecting failures in the tests

Every file operation of `nex migrate` (reading, creating, writing, copying the permission bits,
renaming, deleting) goes through one internal interface that the tests can replace. The
replacement can, deterministically, without timing or threads:

- make the N-th operation of a kind fail with a given system error;
- change the bytes of a file between the first read and the re-read of G7;
- raise an interruption at a given step.

It is a mechanism of the tests only: no command-line option, environment variable or public
function (`nexora.api`, `nexora.tooling`) reaches it, and it is not documented as part of `nex`.
T5 (a changed file) and T9 (failed writes) use it. A crash or a power cut cannot be injected this
way, and section 11 keeps saying so.

### 8.10 Implementation impact and blocking work

| Component | Change | Phase | Size |
|-----------|--------|-------|------|
| `formatter.py`: keep comments | **Done** in PR #6 (`bdc4ada`), before phase 1, with its own tests | Before phase 1 | — |
| `tokens.py`, `lexer.py` | Six keywords; four words reserved for one version | 1 | Small |
| `parser.py`, `ast_nodes.py` | Header clauses (`needs`, `promises`, `trust`, `example`), loop clauses, names, `gives`, functions without a result type, `Function.header` | 1 | Medium |
| `checker.py` | Clauses from the header, `E2031`, `trust` (type-checked, never evaluated), absence of `gives` | 1 | Medium |
| `checker.py` | Static decision at call sites, `E2032` | 4 | Medium |
| `interpreter.py` | Clause names in diagnostics | 1 | Small |
| `interpreter.py` | Per-clause observation for `nex test --evidence` | 2 | Small |
| `prelude.py` | Built-in contracts in the new words; `value`, `value_or` | 1 | Small |
| Frozen 0.11 front end for `nex migrate` | A copy of lexer, parser and checker, isolated; removed in 0.13.0 (section 13, detail 8) | 1 | Medium |
| `tooling.py`, `schemas.py`, `cli.py` | `inspect/3`, `context/2`, `symbols/2`, `nexora.evidence/1` with enforcement; the commands `nex migrate` and `nex check --evidence` | 1 | Large |
| `tooling.py`, `schemas.py`, `cli.py` | The command `nex test --evidence`; the observed dimension | 2 | Medium |
| `tooling.py`, `schemas.py`, `cli.py` | The command `nex impact`; `nexora.impact/1` | 3 | Medium |
| `formatter.py`, `lsp.py` | The new layout of headers | 1 | Medium |
| VS Code grammar, web highlighting | New keywords | 1 | Small |
| `docs/`, examples, golden outputs, tests | Migrated with `nex migrate` and checked with 8.9 | 1 | Large |
| Decisions `0001`–`0018` | Not rewritten: they are records. A note at the top of each says the syntax changed in 0019 | 1 | Small |

### 8.11 Phases

Unchanged from revision 2, except that phase 1 had a blocking precondition, now met (PR #6).

| Phase | Version | Content | Starts when |
|-------|---------|---------|-------------|
| 1 | 0.12.0 | Sections 3, 4, 8 and 9, except the move of 9.1, which does not depend on any phase; `trust` complete (5.6); `nex check --evidence` with enforcement only; the tests of 4.3 and 8.9 | This decision is accepted (2026-10-24) **and** the person responsible for the project authorizes phase 1 explicitly: the acceptance alone does not start it. The formatter condition is **met** since PR #6 (`bdc4ada`) |
| 2 | 0.13.0 | The observed dimension and `nex test --evidence` | Phase 1 published |
| 3 | 0.14.0 | `nex impact` | Phase 2 published |
| 4 | later | Static decision at call sites (5.4), `E2032` | Phase 2, and its exact rules accepted |

## 9. Reserved words

| Word | Today **[V]** | Proposal | Why |
|------|---------------|----------|-----|
| `needs`, `gives`, `promises`, `keeps`, `shrinks`, `trust` | Free | Keywords | Section 4. `nex migrate` refuses programs that use them as names |
| `requires`, `ensures`, `invariant`, `decreases` | Keywords | Reserved for one minor version, then free | So that the old syntax gets `E1107` |
| `break`, `continue`, `enum`, `match`, `const`, `try`, `assert`, `test` | Reserved | Keep reserved | Still possible features |
| `ai`, `tool` | Reserved | **Released** (section 13, answer 4): ordinary names from 0.12.0 | They come from the early draft (`ejemplos/*.nx`); no integration with AI has an approved design. If one is designed, it gets its own decision, and reserving a word again would be an incompatible change of that decision |

The two drafts in `ejemplos/` describe a different language (`system:` prompts, `test "…"` blocks,
`log.info`). **Approved** (section 13, answer 5): move them to `docs/history/`, kept and marked as
the 2026 draft.

### 9.1 What the move of `ejemplos/` depends on

Searched for this revision in both repositories and on the published website **[V]**. The move is
**not done**: it needs changes outside the documentation, which have to be approved first.

| Where | Today | Needed when the files move |
|-------|-------|----------------------------|
| Deployment workflow of the website (private repository) | Packs `docs ejemplos nexora/examples` of the language | Remove `ejemplos`: `git archive` fails on a path that does not exist, so **every deployment would fail**. `docs/history/` is already inside `docs` |
| The web server (private repository) | Serves the folder at `/ejemplos/…`; `https://nexoralang.org/ejemplos/tienda.nx` and `…/soporte_ia.nx` answer `200` | Keep the published addresses with a permanent redirect to the new place, or let them end in `404`: a choice for the person responsible |
| Deployment guide (private repository) | Mentions `ejemplos` among the packed folders | Update the text |
| Continuous integration of the language (`.github/workflows/nexora-ci.yml`) | `ejemplos/**` in its path filter | Remove it (harmless if left, since `docs/**` covers the new place) |
| `README.md` (root) | Links to both files | Point to `docs/history/` |
| `docs/limitations.md` | Mentions `ejemplos/*.nx` | The same |

Order: the private repository has to stop packing `ejemplos` **before** the submodule points to a
commit without it. The move does not depend on phase 1, and phase 1 does not depend on it.

## 10. Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| Keep the syntax and only add the concepts | Ruled out by the person responsible for the project |
| Rename every keyword (`fn` → `func`, `let` → `val`…) | Rule 2: no principle supports it |
| Indentation instead of braces; `do … end` | Worse recovery of partial trees; no gain in identity |
| Keep `requires`/`ensures` and only move them | It would look like Dafny; the vocabulary of P2 ties functions, loops and assumptions together |
| `returns T` | Used by Dafny and Solidity; not in the family of P2 |
| A single evidence state per clause | 5.1: the facts are independent |
| `null` for "not applicable" and "not computed" | 5.3: a consumer could not tell them apart |
| Inferring renames of functions or modules | 7.2: no evidence can back the guess |
| Choosing one candidate when a clause rename is ambiguous | 7.2: the tool would invent a fact |
| Moving the clause lines in `nex migrate` | Moving the `{` keeps every clause line and comment byte-identical (8.5) |
| Re-rendering the program in `nex migrate` | It would change spacing and indentation outside the edits (G2) |
| Detecting the syntax of a program from its tokens | 8.2: a 0.11 program can use `needs` as a name; only the two checks decide |
| Accepting both syntaxes for a while | 8.1 |
| Unicode symbols; renaming `Option`/`Result` | Hard to type and search; rule 1 |

## 11. What it does not guarantee

- **Uniqueness of every piece.** Header contracts exist in Eiffel, Dafny and SPARK. What is
  proposed as NEXORA's own is the combination: named promises as the unit every tool reports on,
  independent evidence dimensions per promise, explicit trust, and impact reports for agents.
  **[?]** Not surveyed exhaustively ([F], section 2).
- **That the new words help language models.** `needs`/`promises` are rarer in training data than
  `requires`/`ensures`. **[?]** To be measured (the plan of
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md), H.7), not assumed.
- **Proof.** Only a `proved` call site is decided, and only from phase 4, only with constants.
- **Behaviour after migration** outside the corpus of 8.9, and semantic equivalence in general:
  comparing trees shows that the structure is the same, not that the meaning is (8.4.2).
- **A failure in the middle of writing several files.** G7 checks and re-reads every file before
  writing any and replaces each file with one rename, but the migration of several files is not
  one atomic transaction: an interruption, a crash, a power cut or an input/output error (a full
  disk, a denied permission) between two renames can leave a program with some files migrated and
  others not. On an error it can see, `nex migrate` stops at the first failed write and lists
  the files replaced, the one that failed and the ones not written (G7); after a crash or a power
  cut it cannot say anything. It never restores the files already replaced: there is no rollback.
  Such a program mixes both syntaxes, so `nex migrate` refuses it afterwards (8.2) and the person
  has to restore it, for example from version control. `nex migrate` lists the files before
  writing them.
- **Concurrent changes.** The final re-read of G7 detects a change made to a file before it, not
  after it: a change made between that re-read and the rename of the file is overwritten without a
  warning. It is a check, not a lock.
- **File metadata.** A replaced file is a new file. It keeps the **permission bits** of the
  original (G7); its owner, group, timestamps, access-control lists and extended attributes are
  not guaranteed to be those of the original. **[?]** On Windows the permission bits that the
  standard library exposes cover little more than the read-only attribute: what is kept there has
  to be checked when it is implemented.
- **Temporary files after a crash.** They are removed after every failure `nex migrate` detects,
  including an interruption, but not after a crash or a power cut. A file left behind has a name
  that does not end in `.nex`, so it is never imported or migrated; the person deletes it.

## 12. Compatibility

- Every program with a function is incompatible with 0.12.0; a module with only types, imports
  and `uses` can be valid in both (8.2.2). `nex migrate` converts a program under the routes,
  guarantees and refusals of section 8.
- The published packages (0.9.0, 0.10.0, 0.11.0 on PyPI and npm) do not change. 0.12.0 is
  published only after phase 1 and the tests of 8.9.
- Tools that read JSON move to `inspect/3`, `context/2`, `symbols/2`.
- The website, the guide, the playground examples and the highlighting are updated in the same
  release.

## 13. Questions for the person responsible, and their answers

The six questions that only the person responsible for the project could decide, as they were
asked, and the answers given in revision 4. Answering them did not accept the decision; it was
accepted later, by a separate approval of revision 8 (Approval).

| # | Question | Answer | Where it is reflected |
|---|----------|--------|------------------------|
| 1 | **Vocabulary**: `needs`, `gives`, `promises`, `keeps`, `shrinks`, `trust`. | Accepted as proposed, including `trust`, documenting that a trusted condition is neither proved nor checked | Section 1; 5.6 |
| 2 | **`fn`**: kept by rule 1. | Kept. No word of its own to declare functions | Section 3 |
| 3 | **Names of clauses**: optional (proposal), or required in `pub` functions. | Optional now. The direction is to require them in `pub` functions, not in force yet; activating it needs a version, a diagnostic, a migration policy and, if applicable, a period of warnings. No names are invented automatically, and phase 1 does not change | 4.1 |
| 4 | **`ai` and `tool`**: release them, or keep them reserved. | Released as ordinary names | Section 9 |
| 5 | **`ejemplos/`**: move the drafts to `docs/history/`. | Approved, keeping them and marking them as the 2026 drafts, after searching for references; the move waits for the changes of 9.1 | 9.1 |
| 6 | **Version number** of phase 1: 0.12.0, or a larger jump to mark the new syntax. | 0.12.0, with the later phases unchanged | 8.11 |

Technical details, resolved in the closing pass (revision 6) so that none of them is left open.
None changes a decision of the person responsible for the project:

| # | Detail | Resolution | Consequence |
|---|--------|------------|-------------|
| 7 | Exit code of `nex impact` with ambiguities | `0`: the comparison was done. The JSON document carries the number of ambiguities, so a gate in continuous integration can fail on it without a special exit code | No new option or code |
| 8 | How long the 0.11 front end is carried | Only in 0.12.x, together with `E1107` and `E1108`; all three are removed in 0.13.0 | Migrating a 0.11 program after 0.13.0 needs `nex migrate` from a 0.12.x release |
| 9 | The order of a header that mixes clauses and examples | One ordered list, `Function.header`, in `inspect/3` (8.4.1) | A change in `inspect/3`, which was already a new version; none in behaviour |
| 10 | A module whose file is named like a new keyword | 0.12 does what 0.11 does with a reserved word **[V]**: the import is accepted and the module cannot be named. `nex migrate` refuses such a program (8.6) | A person renames the file; no new diagnostic code |

## Approval

Approved as written: revision 8, on 2026-10-24, by the person responsible for the project,
together with the answers recorded in section 13.

The approval accepts the documented design. It does **not** authorize starting phase 1 or
implementing NEXORA 0.12, publishing packages, deploying the website or publishing the
extension: each needs its own explicit authorization. Nothing in this decision is implemented.

## Addendum 1 — Details of `nexora.evidence/1` left open by section 5 (provisional)

- **Status:** provisional, kept by the person responsible for the project on 2026-10-24 while
  phase 1 is reviewed. It adds to the decision and changes nothing in it: the text above is the
  approved record and is not rewritten.
- **Why:** section 5.7 shows one entry of the format, and 5.8 one text report. Implementing
  `nex check --evidence` in phase 1 needed four details they do not fix. They are recorded here, with
  what each one means and what it does not promise. `nexora.evidence/1` has not been published, so
  any of them can still change without a new version; once 0.12.0 is published, changing one is a
  change of the format, with the rules of [the JSON protocol](../json-protocol.md#versions-and-compatibility).

| # | Detail | Choice | What it does not promise |
|---|--------|--------|--------------------------|
| A1 | The name of the list of entries | `clauses` | Nothing beyond the name. It follows the grammar (4.1: `header_clause`, `loop_clause`). The text report of 5.8 counts the same entries as "promises", a word of the report, not of the format, and not the kind `promises` |
| A2 | `id.stable` | `true` exactly when the clause has a name, `false` when it has none | See below |
| A3 | A function of an imported module in the text report | Its name followed by the path of its module: `area (lib/geo.nex)`; a function of the entry file, by its name alone | The text report is for people and is not a format: a tool reads `id.module` and `id.function` from the JSON document |
| A4 | `nexora.evidence/1` among the `schemas` of `nexora.capabilities/1` | Listed, since it is an analysis format: producing it never runs the program | Listing it adds a value to a list, as an added error code or value of `features` does: `nexora.capabilities/1` keeps its number, and a consumer handles values it does not know |

**The exact meaning of `stable` (A2).** It says whether the entry has an identity of its own in
the sense of 7.1, and nothing else:

- `true`: the clause has a name. Within **one version** of the program, `(id.module, id.function,
  id.name)` names exactly one clause: a function is unique in its module (`E2002`), and a clause name
  is unique in its function and its loops (`E2031`). It is the identity that the matching of 7.2
  compares, by equal names, when it exists (phase 3).
- `false`: the clause has no name. It has no identity (7.1): several entries of a function may
  have the same kind and the same condition, and none of them can be told apart from the others
  across versions.

`stable` does **not** promise that:

- the clause is the same in another version of the program. Two versions are only matched by equal
  names, and a matched clause may have another condition or explanation (`condition_changed`,
  `explanation_changed` in 7.2);
- the identity survives renaming the clause, its function or its module, or moving the file:
  none of these is inferred (7.2, steps 2 to 4, except the inferred clause rename of step 4);
- the condition holds, or anything about its evidence: that is the business of `enforcement`,
  `static`, `observed` and `summary`;
- the position of the entry in `clauses` is stable: the order follows the files and their text.
