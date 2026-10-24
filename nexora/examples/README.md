# Examples

Reference programs of NEXORA. Each one has a concrete goal, described in the comment
on its first line.

All of them are run by the automated tests (`tests/test_examples.py`), which compare their output,
their diagnostics and their exit code, character by character, with the files in
`tests/golden/examples/`. If a change in the language alters the behaviour of an example, the
tests fail.

Run any of them from the `nexora/` directory:

```bash
nex run examples/hello.nex
```

## Valid

They pass `nex check` and `nex run` ends with code `0`.

| File | What it shows |
|------|---------------|
| [`hello.nex`](hello.nex) | The first program |
| [`variables.nex`](variables.nex) | Variables, texts, blocks and scopes |
| [`arithmetic.nex`](arithmetic.nex) | Precedence, integer and decimal division, limits of `Int` |
| [`types.nex`](types.nex) | Inference, annotations, comparisons, logic and conversions |
| [`functions.nex`](functions.nex) | Functions, `if` / `else`, recursion |
| [`contracts.nex`](contracts.nex) | `needs`, `promises` and `trust` clauses in the header of a function, with their names and explanations |
| [`checked_examples.nex`](checked_examples.nex) | Functions with their own examples (`example`), which `nex test` evaluates |
| [`refined_types.nex`](refined_types.nex) | Refined types with `where`: constants checked without running and explicit check with `Percent(x)` |
| [`loops.nex`](loops.nex) | `var` variables and `while` loops with their measure (`shrinks`) and their invariants (`keeps`), checked on every iteration |
| [`texts.nex`](texts.nex) | Texts: `Text.length`, `Text.slice` and searching inside a text, the order between texts and reading numbers with `Int.parse` and `Float.parse`, each with its requirements |
| [`lists.nex`](lists.nex) | Immutable lists `List[T]`: length, access by index with its requirement, new lists with `List.append` and `List.concat`, `List.contains`, and a `for` that goes through the list with its `keeps` |
| [`records.nex`](records.nex) | Immutable nominal records: declaration, construction with named fields in any order, reading fields and access chains, equality by value, a record inside another one and a list of records |
| [`option_result.nex`](option_result.nex) | `Option[T]` and `Result[T, E]`: `Some`, `None`, `Ok` and `Err`, the functions that recognize the variant, reading the value with and without a default, and equality between variants |
| [`console.nex`](console.nex) | A console program: the arguments it was run with and the standard input, with `args()` and `input()` |
| [`files.nex`](files.nex) | Reading and writing a file, with the capability that the program declares (`uses`) and the permission that has to be granted (`--allow-read`, `--allow-write`) |
| [`modules/main.nex`](modules/main.nex) | Modules: a file that imports another one (`import "models.nex"`), and how its names are used from the program: qualified (`models.Point`, `models.area(p)`), with `pub` for what the module makes visible |
| [`modules/models.nex`](modules/models.nex) | The module that the previous one imports: a record, a refined type, public functions and a private function. Run on its own it ends with `1`: a module is not a program, it has no `main` |

## Invalid (`invalid/`)

Wrong on purpose. The error is detected **without running**: `nex check` and `nex run` end with
code `1` and the program never starts.

| File | Category of the errors |
|------|------------------------|
| [`invalid/syntax_error.nex`](invalid/syntax_error.nex) | `syntax`: the text does not follow the grammar |
| [`invalid/name_errors.nex`](invalid/name_errors.nex) | `semantic`: names, unused values, return paths |
| [`invalid/type_errors.nex`](invalid/type_errors.nex) | `type`: incompatible types |
| [`invalid/refinement_errors.nex`](invalid/refinement_errors.nex) | `semantic` and `type`: badly declared refined types and values that do not meet their condition |

## Fail when running (`failing/`)

They pass `nex check`, because the failure depends on values that are only known when running.

| File | What happens | `nex run` ends with |
|------|--------------|---------------------|
| [`failing/runtime_error.nex`](failing/runtime_error.nex) | Division by zero | `3` |
| [`failing/contract_violation.nex`](failing/contract_violation.nex) | A `needs` condition is false | `5` |
| [`failing/refinement_violation.nex`](failing/refinement_violation.nex) | A computed value does not meet the condition of a refined type | `5` |
| [`failing/loop_measure.nex`](failing/loop_measure.nex) | A loop that would not end: its measure stops decreasing | `5` |
| [`failing/parse_number.nex`](failing/parse_number.nex) | Reads a number from a text that is not one: it breaks the `needs` of `Int.parse`, with a suggestion | `5` |
