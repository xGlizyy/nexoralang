# 0016 — Option and Result

- **Status:** accepted
- **Version:** 0.10.0 (state of the repository; not published in any package)
- **Date:** 2026-10-22
- **Working branch:** `feature/server-hardening`
- **Related to:** [decision 0006](0006-requisitos-verificables.md) (requirements are
  checked), [0011](0011-operaciones-sobre-textos.md) (functions that belong to a type) and
  [0014](0014-registros-nominales-inmutables.md) (nominal records). **It modifies
  none.**
- **Related to [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md):**
  it accepts its `Option` and `Result` part (C.2.4) **within the scope the language has today**, which
  is that of 0013: there are no user enums and no `match`, so these two types are implemented as
  built-in types with inspection functions. 0012 remains a proposal for the rest.
- **Implementation:** 0.10.0. The code is in `values.py` (the runtime representation),
  `types.py` (the `Option` and `Result` constructors of the model), `type_adapter.py` and `parser.py`
  (the text of the types), `checker.py` (the signatures and the inference), `prelude.py` (the pure
  functions) and `interpreter.py` (the constructors and the reads that can fail); the evidence is
  in the tests of the section "Planned regression tests".

## Context

A program needs to say two things that no value can say on its own: that **there is no**
value, and that **something failed**. Up to 0.9.0 NEXORA has no way of saying it: there are no
exceptions, there is no `null`, and the only way to report a failure is to stop the program.

That forces two bad things. A function that may find nothing has to return some arbitrary
value and report it some other way (an empty text, a `-1`), and its caller cannot tell
"it was not there" from "it was there and it was zero". And a function that can fail has to stop the
program, even if the failure is recoverable: a file that is not there today may be there tomorrow, and a
number that cannot be read does not have to prevent the program from continuing.

The design draft (`docs/fase-1-diseno.md` at the root of the repository) and
[decision 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) propose both
types: `Option[T]`, with `Some` and `None`, and `Result[T, E]`, with `Ok` and `Err`. 0012 wants them
as **ordinary enums** of the prelude, with `match` and exhaustiveness, and says that treating them as
special cases of the language would be "inconsistent and hard to extend".

## Decision

`Option[T]` and `Result[T, E]` are implemented as **built-in types** of the language, with the
functions the language already uses for what belongs to a type (`Text.length`, `List.get`), and **without
exceptions**.

### 1. The two types, and their two variants

`Option[T]` has `Some(value)` and `None`. `Result[T, E]` has `Ok(value)` and `Err(error)`. The
name of the variant is part of the value: `None` is never `Some(x)` and `Ok(x)` is never `Err(x)`,
even if the two payloads are equal.

### 2. They are recognized and read with functions

`Option.is_some`, `Option.is_none`, `Result.is_ok` and `Result.is_err` say which variant a
value is. `Option.unwrap_or` and `Result.unwrap_or` return the value or a default of the same type.
`Option.unwrap`, `Result.unwrap` and `Result.error` read the value without a default, and **fail with a
diagnostic** (`E3011`, `E3012`, `E3013`) when the variant does not carry it: there is no read that
returns a made-up value, and none that makes the program fail without saying why.

### 3. The type is given by the context

`T` and `E` are given by the context that expects the value: the annotation of a variable, the type of a
parameter, the result type of a function or the other side of a comparison. `None`, `Ok` and
`Err` written without that context do not have a complete type, and the analysis says so (`E2011`).

### 4. `None` is a name, not a reserved word

`None` is resolved as a built-in constant when the program does not declare a name like that. A
program that already used `None` as a name keeps working: its name wins.

### 5. There is no `?`

The propagation operator **is not implemented now**. It is decided here why, and what would be needed
to add it:

- Propagation needs the result type of the function that uses it and the error type of
  the expression to match exactly. The language has no type variables in declarations,
  so that match is checked but not deduced: propagating an `Err` of type `Text` from
  a function that returns `Result[Int, Error]` would be a type error, and not a conversion.
- Propagating an `Option` inside a function that returns `Option[T]` needs the same element
  type, with the same limitation.
- The propagated value has to **keep** the error: propagating is `return Err(error)`, and that is
  exactly what the `Err` that is already written does. Propagation only saves writing the
  check and the `return`, in exchange for a new syntactic form and new checking
  rules.

What is needed today can be written without a new form:

```nex
fn parse(text: Text) -> Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("not a whole number")
}
```

When the language has user enums and `match` (the complete 0012), propagation will have a
natural place and will be decided with them.

## Facts verified in the repository

| Fact | Where |
|------|-------|
| The `Option` and `Result` types were already in the model, without syntax | `types.py` (`OPTION`, `RESULT`, `option_of`, `result_of`) |
| Signatures with type variables already existed, with `unify` per call | `checker.py` (`ParametricSignature`, `_parametric_call`) |
| The expected type already reached the expressions, as in the empty list | `checker.py` (`_expression`, `_list_literal`) |
| The functions of a type are called with the name of the type | `checker.py` (`BUILTINS`), `prelude.py` (`IMPLEMENTATIONS`) |
| Values are printed with `format_value` and compared by value | `values.py` |

## Decisions taken here, and why

| Decision | Why |
|----------|-----|
| Two built-in types and not user enums | The language has no enums and no `match`. Adding them is another, bigger decision; meanwhile, these two give what is needed |
| The variants are named unqualified (`Some`, `Ok`, `Err`) | As in the rest of the language, a function name is a name; the qualified one is reserved for what belongs to a type (`Text.length`) |
| Inspection with functions and not with `match` | `match` does not exist: there are no two constructs competing for the same thing |
| `None` as a constant and not as a reserved word | It does not break the programs that already use that name |
| The reads that fail say so with a diagnostic | The project has no exceptions: a failure has to be a diagnostic, with its code and its position |
| No propagation for now | See decision 5 |

## What it does not guarantee

- There is no `match`, no `if let` and no `?`: inspection is done with functions.
- The type of a `None`, an `Ok` or an `Err` **written directly in a comparison** is not
  deduced: `Ok(1) == Ok(1)` needs the error type to be written in a variable first.
- The type of an argument of a function with type variables is not deduced from the other
  arguments: the language does not infer a type through the arguments of a call.
- `Option` and `Result` are not user enums: variants cannot be added, and a `match` on them
  is not exhaustive by construction.

## Out of scope

- User enums and `match` with exhaustiveness: they are the big part of 0012 and remain
  a proposal.
- `?` propagation: it will be decided later, with `match`.
- User generics: `Option[T]` and `Result[T, E]` are the only two types with arguments
  that the language accepts.
- `Option` and `Result` in contracts (`requires` and `ensures`) and in refinements: it has not been
  checked that the analysis can accept them.

## Alternatives ruled out

| Alternative | Why not |
|-------------|---------|
| Exceptions for the error | The language does not have them, and 0002 makes sure only what has been checked runs |
| A sentinel value (a `-1`, an empty text) | It does not tell the absence apart from the value, and it does not keep the error |
| `null` | It does not exist in the language, and it would not tell "there is none" from "there is a null value" |
| Treating `Option` and `Result` as records | A record has fields and no variants; `Some` and `None` would not be the same type |
| `Option` and `Result` as special cases of the analyzer | 0012 rejects it: it would be inconsistent and hard to extend |
| Adding `?` now | See decision 5: the language does not deduce the error type that has to be propagated |

## Compatibility

- Existing programs keep checking the same: the `Option` and `Result` types did not
  exist, so there was no `Option` and no `Result` that the new code could change.
- The names `Option`, `Result`, `Some`, `Ok` and `Err` become part of the language. A program that
  declared a function with one of those names would use the built-in one: it is the same case as `print` or
  `to_text`. `None` is the opposite case: the name of the program wins.
- The types with writable arguments go from being only `List[T]` to also being `Option[T]` and
  `Result[T, E]`. The canonical text of a type with arguments is still the one written by
  `display`: `Result[Int, Text]`, with a space after the comma.
- The specification moves to version 0.10 and the reference implementation to 0.10.0. The 0.9.0
  already published on npm is not touched.

## Required changes

- `types.py`: no substantive changes; the model already had both constructors. The documentation of the
  module no longer says that they are not enabled.
- `type_adapter.py`: accepts `Option[T]` and `Result[T, E]` in the canonical text.
- `parser.py`: `Option` and `Result` are type names with arguments, with their arity.
- `checker.py`: the signatures of the constructors and of the inspection functions; the expected type
  reaches the call; `None` is a constant; `_known_type` accepts both types.
- `values.py`: the runtime representation (`VariantValue`) and its printing.
- `prelude.py`: the pure inspection functions.
- `interpreter.py`: the constructors, the `None` constant and the three reads that can fail.
- `diagnostics.py`: `E3011`, `E3012` and `E3013`.

## Planned regression tests

| File | What it pins down |
|------|-------------------|
| `tests/test_option_result.py` | The four variants, their payloads, equality between variants, inspection, the reads that fail, the type errors and inference |
| `tests/test_type_lists.py` | That `Option` and `Result` are types, and that the canonical text is the expected one |
| `tests/test_type_lists_syntax.py` | That a badly written type with arguments is a syntax error |
| `tests/test_security.py` | That the built-in functions are exactly the documented ones |
| `tests/test_text_operations.py` | That every function of a type has an implementation |
| `examples/option_result.nex` | A complete program that uses both variants, and its recorded output |

## Relation to the previous decisions and the index

This decision implements the `Option` and `Result` part of
[0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) (C.2.4) **within the scope the
language has today**. It does not modify 0012, which remains a proposal for enums, `match`,
exhaustiveness, input and effects. It is added to the decision index as accepted.

## Questions that remain open

- What happens to `Option` and `Result` when the language has user enums and `match`? Do they
  remain built-in types, or do they become enums of the prelude, as 0012 says?
- Does `?` propagation make sense with enums and `match`? Which rules does it need?
- Should `Option` and `Result` be able to appear in contracts and in the conditions of a refined
  type?
