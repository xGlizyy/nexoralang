# 0001 — Static types, without implicit conversions; `String` is renamed `Text`

- **Status:** accepted
- **Version:** 0.2.0

## Context

Version 0.1 already deduced the type of every expression, but it did not allow writing types, it had no
comparisons or logic, and it offered no way to go from one type to another: `1 + 1.5` was an
error with no solution inside the language.

## Decision

1. **Every type is known without running.** The type of an expression depends only on literals,
   annotations and signatures. No type error can appear while the program runs.
2. **Two types are compatible only if they are the same.** There are no subtypes and no numeric promotion:
   `Int` and `Float` do not mix in operations, comparisons, arguments or returns.
3. **Conversions are explicit calls**: `to_float`, `to_int` and `to_text`. There is no
   other.
4. **Division between `Int` values returns an `Int`**, rounding towards zero. The behaviour of
   0.1 is kept.
5. **Conditions are `Bool`.** A number or a text is not valid as a condition.
6. **Optional annotations** on `let` (`let age: Int = 25`); without an annotation, the type is inferred.
7. **The text type is called `Text`** instead of `String`.
8. Logical operators are words (`and`, `or`, `not`), as in the design draft.

## Reasons

- An implicit conversion can hide an error: `1 + 1.5` can be an accidental mix of units.
  If the conversion has to be written, the code says what it does and a tool
  that reads it does not have to know promotion rules.
- With a single compatibility rule ("the same type") error messages can be exact
  and propose the right conversion when it exists.
- Integer division that returns an integer avoids having the type of the result depend on the values.
  The alternative (always returning `Float`) would have turned `10 / 2` into `5.0` and would have made
  exact integer arithmetic impossible without another operator.
- `Text` is the name asked for in this phase; it describes the value for whoever does not come from another language.

## Alternatives ruled out

- **`Int` → `Float` promotion.** Convenient, but it is precisely the silent conversion that is
  to be avoided, and it loses precision with integers of more than 53 bits.
- **A separate integer division operator (`//`).** It adds syntax for something the type of the
  operands already expresses.
- **`!`, `&&`, `||`.** The draft had already chosen words; a single form is kept.
- **Comparing texts with `<`.** It requires defining an order (by Unicode code? by language?). It is
  postponed until that is decided.

## Incompatible changes and how to update

| Change | Effect | What to do |
|--------|--------|------------|
| `String` → `Text` | Error messages say `Text`. No 0.1 program wrote `String`, because there were no annotations, so there is no code to change | Nothing. Writing `String` in 0.2 produces `E2012` with the hint "The text type is called Text" |
| `and`, `or`, `not`, `if`, `else`, `return`, `requires`, `ensures` now have a meaning | They were already reserved words in 0.1, so no valid program used them as names | Nothing |
| `to_text`, `to_float`, `to_int` are built-in functions | A 0.1 program that declared a variable with one of those names now gives `E2006` | Rename the variable |

The four examples of version 0.1 run unchanged and give the same result.
