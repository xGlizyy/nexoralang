# 0003 — Functions with an explicit `return`, a single namespace and `if` as a statement

- **Status:** accepted
- **Version:** 0.2.0

## Decision

1. **Functions with typed parameters and a required return type.** No overloading, default
   values, generics or anonymous functions.
2. **The value is always returned with `return`.** The design draft proposed that a block
   be worth its last expression; that is not adopted in this version.
3. **Every path returns.** The static analysis rejects a function that can end without
   `return` (`E2014`) and code placed after a `return` (`E2015`). The analysis is structural:
   it does not evaluate conditions.
4. **A single namespace and no shadowing.** Functions, parameters and variables share
   names; a visible name is not declared again.
5. **Functions are not values.** They can only be called.
6. **A returned value cannot be ignored** (`E2010`).
7. **`if` / `else if` / `else` as a statement.** It was not in the list of this phase, but it is added.
8. **Recursion allowed**, with a maximum of 1000 nested calls (`E3004`).

## Reasons

- An explicit `return` makes visible where a function ends and allows checking the return
  paths with a simple rule. With "the last expression is the value", the rule of `E2010`
  (unused value) and that of the implicit return would conflict.
- With a single namespace, every name in a function means a single thing. This
  makes reading simpler for a person and for a tool: there is no need to work out which `x` is
  which.
- **Why `if`:** without conditionals, a recursive function cannot stop, the rule "every
  path returns" has no paths to check and `ensures` would never have more than one path. The
  comparisons and the `Bool` values would not be good for anything but printing either. It is the minimal
  construct that makes the others useful.
- The call limit turns an endless recursion into a clear diagnostic instead of a
  crash of the interpreter.

## Alternatives ruled out

- **Loops (`while`).** They need reassignable variables (`var`), which do not exist. They are postponed together.
- **`if` as an expression.** It forces defining the type of a block; it is postponed.
- **Allowing returned values to be ignored.** It contradicts the rule that already exists for loose expressions.

## Known limits

- The path analysis does not reason about values: `if true { return 1 }` without `else` is rejected.
- The limit of 1000 calls depends on the implementation (the interpreter walks the tree
  recursively) and can be lower with very nested expressions.
- At most 64 levels of chained `else if`.

## Compatibility

No incompatible changes: in 0.1 only `main` could be declared, and every 0.1 program is still
valid. The codes `E1104` and `E2003`, which warned that these constructs did not exist,
are retired.
