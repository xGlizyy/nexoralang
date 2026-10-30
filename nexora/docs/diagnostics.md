# Diagnostics

A diagnostic is the way NEXORA reports a problem. All of them have the same structure,
a code that does not change and a category that says what kind of problem it is.
**Stability: stable for machine-readable fields** (`code`, `category`, severity, and source positions).
Human-readable wording may change ([stability policy](interface-stability.md)).

## Anatomy of a diagnostic

<!-- nex:check-fails -->
```nex
fn main() {
    let total = 10
    let total = 20
}
```

```text
semantic error[E2006]: Name already declared
 --> program.nex:3:9
  |
3 |     let total = 20
  |         ^^^^^ 'total' is already declared and still visible here
  = note: It was first declared at line 2, column 9.
  = hint: Choose a different name: a visible name cannot be declared again.

error: program.nex: check failed with 1 error
```

| Part | In the example | Meaning |
|------|----------------|---------|
| Category | `semantic` | What kind of problem it is and which stage found it |
| Severity | `error` | `error` stops the program; `warning` points at something that can be improved and does not |
| Code | `E2006` | Stable identifier of the problem |
| Title | `Name already declared` | Fixed text associated with the code |
| Position | `program.nex:3:9` | File, line and column. Both start at 1 |
| Marker | `^^^^^` | The exact affected fragment |
| Explanation | `'total' is already declared…` | What happens in this concrete case |
| `= note:` | | Related information: where something was declared, the signature of a function, the chain of calls |
| `= hint:` | | A suggested fix |

The last line (`error: …`) is a summary of the command, not a diagnostic.

Details:

- The column counts characters, not bytes, and a tab counts as one column.
- Some diagnostics have no position (for example, "the `main` function is missing").
- Messages are in English.
- **Suggestions only appear when there is a rule that backs them**: there is a conversion
  between the two types, there is a declared name very similar to the one written, or the message describes the
  correct form of the construct. If there is none, nothing is suggested.

## Categories

The category says at which stage the problem was found.

| Category | Meaning | When it is detected | `nex` ends with |
|----------|---------|---------------------|-----------------|
| `file` | The file could not be loaded | Before analyzing | `4` |
| `lexical` | The text contains something that does not belong to the language | Without running | `1` |
| `syntax` | The code does not follow the grammar | Without running | `1` |
| `semantic` | Names, scopes or structure of the program | Without running | `1` |
| `type` | Types | Without running | `1` |
| `runtime` | Depends on computed values | When running | `3` (with `nex test`, `6`) |
| `contract` | A rule that the program declares was broken: a `needs` or `promises` condition, a `keeps` or a measure of a loop, or the condition of a refined type | When running | `5` (with `nex test`, `6`) |
| `test` | An example evaluated by `nex test` turned out false | When running `nex test` | `6` |

The stages run in order and each one only runs if the previous one found no errors.
That is why a file with a syntax error does not show type errors at the same time: the syntax is fixed
first.

Within a stage all the independent errors found are reported, up to a
maximum of 100. Warnings are only reported when the file has no errors: they never stop the
program, and `nex check` still exits with `0` when they are the only diagnostic.

## All the codes

A code never changes its meaning. If it stops being used it is retired, not reused.

### File

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E0001` | Cannot read file | The file does not exist, it is a directory or there is no permission to read it | Check the path and the directory you run the command from |
| `E0002` | File is not valid UTF-8 | The file uses another encoding | Save it as UTF-8 |

### Lexical

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E1001` | Unexpected character | A character that does not belong to the language: `;`, `'`, `!`, `@`, accented letters in a name… | Remove it. Texts use double quotes; there is no semicolon |
| `E1002` | Unterminated string | The closing quote is missing on that line | Close the text. A text cannot span several lines |
| `E1003` | Invalid escape sequence | A `\` followed by a character that is not allowed | The escapes are `\n`, `\t`, `\"`, `\\` and `\{` |
| `E1004` | Invalid number literal | Badly written number (`007`, `1_`, `12abc`) or too large | Fix the number. The largest `Int` is `9223372036854775807` |
| `E1005` | Unescaped '{' in string | A `{` inside a text | Write `\{`. The brace is reserved for a future feature |

### Syntax

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E1101` | Unexpected token | The code does not follow the grammar | The message says what was expected at that point |
| `E1102` | Unclosed block | The end of the file was reached with an unclosed `{` | Add the `}`. The note says where the block was opened |
| `E1103` | Reserved word | A word reserved for the future is used (`break`, `match`…) | That construct does not exist yet; choose another name or rewrite the code. For `break` and `continue` the suggestion explains how to express it with the condition of the loop, an `if` or `return` |
| `E1105` | Expression too deeply nested | More than 64 levels of nesting, or an expression of more than 256 levels | Split the code into variables or functions |
| `E1106` | Misplaced contract clause | `needs`, `promises`, `trust` or `example` inside the body of a function, or `keeps` or `shrinks` inside the body of a loop | Move the clause to the header: between the signature (or the head of the loop) and its `{` |
| `E1107` | Syntax before 0.12 | `requires`, `ensures`, `invariant` or `decreases`, the clause words of 0.11 ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)) | Write `needs`, `promises`, `keeps` or `shrinks` in the header; `nex migrate` rewrites a program of 0.11 |
| `E1108` | Arrow before the return type | `-> Type` after the parameters of a function ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)) | Write `gives Type`; a function that gives nothing has no `gives` |

### Semantic

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E2001` | Missing main function | The program does not declare `main` | Add `fn main() { ... }` |
| `E2002` | Duplicate function | Two functions with the same name, or with that of a built-in one | Rename one of them |
| `E2005` | Unknown variable | A name is used that is not declared or is no longer visible | Declare it first with `let`, or fix the name |
| `E2006` | Name already declared | A name is declared that is already visible, or that of a function | Choose another name |
| `E2007` | Cannot reassign variable | A new value is assigned to a variable declared with `let`, to a parameter or to the iterator of a `for` | Declare the variable with `var`; a parameter or the iterator are copied first into a `var` |
| `E2008` | Unknown function | A function that does not exist is called. Also in a qualified call (`Texto.length(t)`, `Text.lenght(t)`, `name.length()`) whose name in front of the dot is not a type with that function ([decision 0011](decisions/0011-operaciones-sobre-textos.md)) | Fix the name or declare the function. The functions of a type are called with its name: `Text.length(t)` |
| `E2010` | Unused value | A computed value that is lost: a loose operation or a call whose result is not used | Keep it with `let` or pass it to a function |
| `E2013` | Invalid parameter | `main` has parameters, or a parameter is named `result` | Remove the parameters of `main`, or change the name |
| `E2014` | Missing return | A function that returns a value can end without `return` | Make sure that all branches end with `return` |
| `E2015` | Unreachable code | Code placed after a `return` | Remove it or move it before the `return` |
| `E2016` | Invalid type declaration | A refined type with a lowercase name, a repeated one or one of a built-in type, a chain of types that does not end in a built-in type, or a base that is a list. Also a record with an invalid or repeated name, a repeated field, or a record that contains itself | Fix the name or the base; the message says which of the cases it is |
| `E2018` | Invalid refinement condition | The condition of a refined type calls a function of the program or checks another refined type | Write the rule with operators on `value`, or move it to a `needs` |
| `E2019` | Too many refinement checks | Checking the constants against their refined types exceeds the work limit of the analysis (100,000 condition nodes). It only happens with many constants of long chains of refined types | Use fewer constants of those types or shorter conditions |
| `E2020` | Example without its function | An example contains no call to its own function: its expression does not name it anywhere. A call that only happens inside another function does not count | Write the call with its inputs: `example f(2) == 4` |
| `E2021` | Missing loop measure | A `while` does not declare its measure (`shrinks`), or declares more than one. Without a measure, nothing says why the loop ends | Add `shrinks`, in the header of the loop, with an `Int` that goes down on every iteration and does not go below 0, for example `shrinks n - i` |
| `E2022` | Unsupported loop clause | A `for` declares `shrinks`, but it goes through a finite list and has no measure | Remove the `shrinks`; if you need invariants, write them with `keeps` |
| `E2026` | Missing capability declaration | A file, HTTPS origin or executable is used without declaring it with `uses` ([decisions 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md) and [0020](decisions/0020-red-y-procesos-externos.md)) | Declare it at the beginning of the file, for example `uses network "https://api.example.com"` |
| `E2025` | Cannot reassign a field | A field of a record, which is immutable, is assigned to ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) | Build another record with the value you want |
| `E2027` | Unknown module | The name of a module that the program does not import is used ([decision 0018](decisions/0018-modulos-e-importaciones.md)) | Declare it at the beginning of the file: `import "app/models.nex"` |
| `E2028` | Private name | A name of another module is used that this module does not declare with `pub` ([decision 0018](decisions/0018-modulos-e-importaciones.md)) | Write `pub` in front of the function or the type in the file that declares it |
| `E2029` | Circular import | Modules import each other, so that none can be analyzed before the one it needs ([decision 0018](decisions/0018-modulos-e-importaciones.md)) | Break the cycle: move what both share to a third module that both import |
| `E2030` | Module name clash | Two different files are imported as the same module, because they have the same name ([decision 0018](decisions/0018-modulos-e-importaciones.md)) | Rename one of the two files: the module takes its name from its file |
| `E2031` | Duplicate clause name | A clause name used twice in a function and its loops, or equal to a parameter or to `result` ([decision 0019](decisions/0019-identidad-propia-del-lenguaje.md)) | Give each clause its own name |

### Type

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E2004` | Invalid return type | `main` has a `gives` | Write `fn main() {` |
| `E2009` | Wrong number of arguments | The call does not pass as many arguments as the function has parameters | The note shows the signature of the function |
| `E2011` | Type mismatch | A type is not the one the rule requires: annotation, assignment, operator, argument, return, condition, element of a list, iterable of a `for`, measure of a loop (`Int`), or a call to a function without `gives` used as a value | The message says the expected type and the one found. Convert explicitly if a conversion exists |
| `E2012` | Invalid type | A name that is not a type, `List` without an argument, a type argument that does not exist, or `Void` written as a type (also `gives Void`) | The types are `Int`, `Float`, `Bool`, `Text` and `List[T]`, the refined types that the program declares and its records. `Void` is never written: a function that gives nothing has no `gives` |
| `E2023` | Invalid record construction | A construction of a record that is missing a field, has an extra one or is given the same one twice ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) | Give each field once, with the name of the field |
| `E2024` | Invalid field access | A field is read from a value that is not a record, or from a record that does not have that field ([decision 0014](decisions/0014-registros-nominales-inmutables.md)) | The message says which fields the record has |
| `E2017` | Value outside refined type | A constant used as a value of a refined type does not meet its condition. The notes show the condition, the value and the explanation of the rule | Change the value, or review the rule if it was wrong |

### Runtime

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E3001` | Division by zero | The divisor is zero | Check the divisor before dividing, or declare a `needs` |
| `E3002` | Integer overflow | An `Int` result does not fit in 64 bits | Use smaller values, or `Float` if you do not need exactness |
| `E3003` | Float result out of range | A `Float` result is too large | Review the operation |
| `E3004` | Too many nested calls | More than 1000 nested calls, or the stack ran out before | It is usually a recursion that does not reach its base case |
| `E3005` | Conversion out of range | `to_int` of a `Float` that does not fit in an `Int` | Check the value before converting |
| `E3006` | Text too long | A Text value exceeds the limit of the environment where it runs. It only happens where a limit is set, such as `nex run --max-text` or the Playground | Build shorter texts |
| `E3007` | Out of memory | The program needed more memory than was available while it ran. It points at no position; the notes show the chain of calls | Reduce the size of the values the program creates, above all those that grow on every call |
| `E3008` | Permission denied | The program tries to use a file, network origin or process that is not declared, granted or enabled by the environment | Declare the capability, use the matching `--allow-*` option and run in an enabled host |
| `E3009` | No more input | `input()` was called when the standard input had already ended | Check that there is more input before reading, or end the program |
| `E3010` | File error | The file could be used, but it could not be read or written: it does not exist, it is not UTF-8 text, or the operating system prevented it | Check the path and that the file is UTF-8 text |
| `E3011` | Option has no value | `Option.value` was called with a `None`: the variant does not carry the value ([decision 0016](decisions/0016-option-y-result.md)) | Check first with `Option.is_none(...)`, or use `Option.value_or(x, fallback)` |
| `E3012` | Result is an error | `Result.value` was called with an `Err`: the variant does not carry the value | Check first with `Result.is_err(...)`, or use `Result.value_or(x, fallback)` |
| `E3013` | Result is not an error | `Result.error` was called with an `Ok`: the variant does not carry the error | Check first with `Result.is_ok(...)` |
| `E3014` | External operation failed | An HTTPS request or external process failed, exceeded its limit or produced invalid text | Check the URL or command and its output; the limits are described in section 8.3 of the specification |
| `E3015` | Resource limit exceeded | A configured `nex run` source, input, output or wall-clock budget was exceeded | Increase the matching `--max-*` or `--timeout` budget, or reduce the program's use |
| `E3015` | Resource limit exceeded | A configured `nex run` source, input, output or wall-clock budget was exceeded | Increase the matching `--max-*` or `--timeout` budget, or reduce the program's use |

### Contract

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E4001` | Precondition violated | A call does not meet a `needs` condition, of a function of the program or of a function of a type (`Text.slice`, `Int.parse`, `List.get`). It points at the call | Fix the arguments, or check the condition before calling (`Int.can_parse` before `Int.parse`, a valid index before `List.get`) |
| `E4002` | Postcondition violated | A function does not meet its own `promises` condition. It points at the clause | Fix the body of the function (or the condition, if it was wrong) |
| `E4003` | Refinement violated | A value checked with `Type(x)` does not meet the condition of the refined type. It points at the check | Fix the computation that produces the value, or check it first with an `if` |
| `E4005` | Loop invariant violated | A `keeps` is false before an iteration or after the last one: on arrival, after an iteration or when the list of a `for` runs out. It points at the clause; the notes say after which iteration and with which values | Fix the body of the loop, or the invariant if it did not describe what the loop keeps true |
| `E4006` | Loop measure did not decrease | The measure (`shrinks`) of a `while` is negative, or is not smaller than in the previous iteration: the loop was not going to end. It points at the measure; the label gives both values and the notes, the iteration and the variables | Make every iteration move towards the end of the loop, or fix the measure |

### Test

Only produced by `nex test` ([decision 0008](decisions/0008-ejemplos-y-nex-test.md)).

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `E4004` | Example failed | An example was evaluated without errors, but it is `false`. It points at the expression of the example; the notes give what each call to the function returned and the explanation of the example | Fix the function, or the example if the expected result was the wrong one |

An example that stops because of a runtime error or a broken rule does not give `E4004`: it gives the
diagnostic of that error, with one more note that says which example caused it.

When the broken rule has an explanation, the diagnostic shows it in a `Reason: ...` note.

### Warnings

A warning describes an improvement, not a failure. It has its own `W` code and the same fields
as an error.

| Code | Title | What it means | What to do |
|------|-------|---------------|------------|
| `W2001` | Unused variable | A variable, parameter or iterator is declared and its value is never read. A variable that only receives assignments is unused too | Remove it, or use its value. A parameter that must keep its position can be named `_` |
| `W2002` | Variable never reassigned | `var` declares a value that can change, but this one never does | Declare it with `let`, which says that it does not change |
| `W2003` | Name is not snake_case | A variable, parameter, iterator or private function does not follow `snake_case` | Write it in `snake_case`. Type names keep PascalCase, and a public function and its parameters keep the spelling of their interface |

Warnings appear after the errors of the same file, and a file with errors has none. The
`--format json` document keeps them in `diagnostics`, with `"severity": "warning"`, and `ok`
stays `true`.

### Retired codes

`E1104` and `E2003` existed in version 0.1 and are no longer emitted: they warned that parameters,
type annotations and user functions did not exist. Their numbers will not be reused.

## Runtime diagnostics

A runtime error includes the chain of calls that led to it, from the most recent to the
oldest:

<!-- nex:fails exit=3 -->
```nex
fn share(total: Int, people: Int) gives Int {
    return total / people
}

fn report(people: Int) {
    print(share(100, people))
}

fn main() {
    report(4)
    report(0)
}
```

```text
25
runtime error[E3001]: Division by zero
 --> program.nex:2:20
  |
2 |     return total / people
  |                    ^^^^^^ The right-hand side of this division is zero
  = note: In 'share', called at line 6, column 11.
  = note: In 'report', called at line 11, column 5.

error: program.nex: the program stopped because of a runtime error
```

At most six calls are shown; if there are more, a note says how many are left out.

An error that happens inside a loop adds a note for every loop that contains it, from the
innermost to the outermost, at most six: `In turn 3 of the loop at line 6.` If the error is in
a clause or in the condition, the note says `Before turn …` or `After turn …`.

## JSON format

With `--format json` the diagnostics are delivered as data, so that a program does not have to
interpret the text above. For the first example of this page:

<!-- nex:check-json -->
```nex
fn main() {
    let total = 10
    let total = 20
}
```

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.15.0",
  "file": "program.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "category": "semantic",
      "code": "E2006",
      "message": "Name already declared",
      "label": "'total' is already declared and still visible here",
      "hint": "Choose a different name: a visible name cannot be declared again.",
      "notes": [
        "It was first declared at line 2, column 9."
      ],
      "file": "program.nex",
      "line": 3,
      "column": 9,
      "end_line": 3,
      "end_column": 14
    }
  ]
}
```

Every field is described in the [specification, section 11.4](language-spec.md#114-json-format),
and its use by tools in [Automated tools and AI](ai-tooling.md).

## Internal errors

If NEXORA fails because of a defect of its own, it does not present it as an error of your program: it shows a
message that starts with `internal error:` and ends with exit code `70`. It has no
`E…` code or category. It is described in the [CLI reference](cli-reference.md#internal-errors).
