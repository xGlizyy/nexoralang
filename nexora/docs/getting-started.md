# Getting started

This guide takes you from an empty file to a program with variables, types and functions.
It only uses stable features of the language. You need NEXORA [installed](installation.md)
and the virtual environment activated.

All the programs of this page, and the outputs shown, are checked by the automated tests
of the project.

## 1. Your first program

Create a text file called `program.nex` with this content:

<!-- nex:run -->
```nex
fn main() -> Void {
    print("Hello from NEXORA")
}
```

Run it:

```bash
nex run program.nex
```

You will see:

```text
Hello from NEXORA
```

What each part means:

- `fn main() -> Void { ... }` declares the `main` function. Every program starts running
  there. `Void` means that it returns no value.
- `print(...)` writes a value to the screen, followed by a line break.
- Statements end at the end of the line. No semicolon is used.
- NEXORA files have the `.nex` extension and are saved as UTF-8 text.

## 2. Checking without running

`nex check` analyzes the program and reports its errors **without running it**:

```bash
nex check program.nex
```

```text
✓ Check passed: program.nex
```

`nex run` does that same check before starting: a program with errors never gets to
run. `nex check` is useful while you write, because it produces no effect.

## 3. Variables

`let` declares a variable and gives it a value:

<!-- nex:run -->
```nex
fn main() -> Void {
    let name = "Ada"
    let year = 1843
    print(name)
    print(year)
}
```

```text
Ada
1843
```

Two important rules:

- **`let` variables do not change.** Once declared, it keeps its value. A variable that has
  to change is declared with `var` and given another value with `=` (you will see it in section 6).
- **A name is declared only once.** You cannot declare two variables with the same name if
  the first one is still visible.

Comments start with `//` and run to the end of the line.

## 4. Types

Every value has a type. There are four value types:

| Type | What it holds | Examples |
|------|---------------|----------|
| `Int` | Whole numbers | `42`, `-7`, `1_000_000` |
| `Float` | Numbers with decimals | `3.14`, `0.5`, `10.0` |
| `Bool` | True or false | `true`, `false` |
| `Text` | Text | `"Hello"` |

NEXORA deduces the type of a variable from its value. You can also write it yourself, and
then the language checks that the value is of that type:

<!-- nex:run -->
```nex
fn main() -> Void {
    let title = "Analytical Engine"      // Text, deduced
    let pages: Int = 25                  // Int, written
    let price: Float = 19.99
    let available: Bool = true

    print(title)
    print(pages * 2)
    print(price / 2.0)
    print(pages > 20 and available)
}
```

```text
Analytical Engine
50
9.995
true
```

NEXORA **never converts one type into another on its own**. An integer and a decimal cannot be
mixed in an operation, and a number is not joined to a text with `+`. When you need it, you have to
say so with a conversion function:

<!-- nex:run -->
```nex
fn main() -> Void {
    let units = 3
    let price = 2.5
    let total = to_float(units) * price          // Int -> Float
    print("Total: " + to_text(total))            // Float -> Text
    print(to_int(total))                         // Float -> Int (drops the decimals)
}
```

```text
Total: 7.5
7
```

The guide on [types](types.md) explains all the rules.

## 5. Functions

A function receives values (parameters) and can return a result. Every parameter declares its
type, and the function declares the type of what it returns:

<!-- nex:run -->
```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn greet(name: Text) -> Void {
    print("Hello, " + name + "!")
}

fn main() -> Void {
    let result: Int = add(2, 3)
    print(result)
    greet("Ada")
}
```

```text
5
Hello, Ada!
```

- `return` returns the result and ends the function.
- A function that returns nothing uses `Void`, like `greet` and `main`.
- Functions can be declared in any order.

## 6. Deciding with `if`

`if` runs a block only if a condition is true. `else` says what to do
otherwise:

<!-- nex:run -->
```nex
fn describe(temperature: Int) -> Text {
    if temperature < 0 {
        return "freezing"
    } else if temperature < 20 {
        return "cool"
    } else {
        return "warm"
    }
}

fn main() -> Void {
    print(describe(-5))
    print(describe(12))
    print(describe(30))
}
```

```text
freezing
cool
warm
```

The condition has to be a `Bool`: a comparison (`==`, `!=`, `<`, `<=`, `>`, `>=`), a
variable of type `Bool`, or a combination with `and`, `or` and `not`.

### Repeating with `while`

`while` repeats a block while its condition is true. What changes from one iteration to the next is
declared with `var`. Every loop says, with `decreases`, why it ends: a number that goes down on every
iteration and never goes below 0.

<!-- nex:run -->
```nex
fn main() -> Void {
    var count = 3
    while count > 0 {
        decreases count, "One step closer to zero on every turn"
        print(count)
        count = count - 1
    }
    print("liftoff")
}
```

```text
3
2
1
liftoff
```

If the number does not go down (for example, because you forget `count = count - 1`), the program does not
hang: it stops on the second iteration and tells you which values it had. [Contracts](contracts.md#loops-invariant-and-decreases)
also explain `invariant`, to say what stays true on every iteration.

The guide on [functions](functions.md) explains the rest: return paths, recursion and limits.

## 7. Reading an error

When something is not correct, NEXORA explains it with a diagnostic. This program has an error:

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let age: Int = "twenty"
    print(age)
}
```

```bash
nex check program.nex
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:20
  |
2 |     let age: Int = "twenty"
  |                    ^^^^^^^^ Expected Int, found Text
  = note: 'age' is declared as Int.

error: program.nex: check failed with 1 error
```

How to read it:

| Part | Meaning |
|------|---------|
| `type error` | The kind of problem. Here, a type error |
| `[E2011]` | The code of the error. It is always the same for the same problem; you can look it up in the [list of codes](diagnostics.md#all-the-codes) |
| `Type mismatch` | The title of the error |
| `program.nex:2:20` | File, line and column where the problem is |
| `^^^^^^^^` | The exact fragment that causes the error |
| `Expected Int, found Text` | The concrete explanation |
| `= note:` | Related information |
| `= hint:` | When it appears, a suggested fix |

An error with a suggestion: the name is misspelled and a similar one exists.

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let total = 10
    print(totl)
}
```

```text
semantic error[E2005]: Unknown variable
 --> program.nex:3:11
  |
3 |     print(totl)
  |           ^^^^ There is no variable named 'totl' here
  = hint: Did you mean 'total'?

error: program.nex: check failed with 1 error
```

Some errors cannot be known until the program runs, because they depend on the values.
This program passes `nex check`, but it fails when it runs:

<!-- nex:fails exit=3 -->
```nex
fn main() -> Void {
    let items = 12
    let people = 3 - 3
    print("Sharing...")
    print(items / people)
}
```

```text
Sharing...
runtime error[E3001]: Division by zero
 --> program.nex:5:19
  |
5 |     print(items / people)
  |                   ^^^^^^ The right-hand side of this division is zero

error: program.nex: the program stopped because of a runtime error
```

The guide on [diagnostics](diagnostics.md) explains the categories and all the codes.

## 8. A complete program

With what you have seen so far:

<!-- nex:run -->
```nex
// Computes the average mark of three exams and decides whether they are passed.

fn average(a: Int, b: Int, c: Int) -> Float {
    return to_float(a + b + c) / 3.0
}

fn verdict(mean: Float) -> Text {
    if mean >= 50.0 {
        return "passed"
    }
    return "failed"
}

fn main() -> Void {
    let mean = average(62, 48, 71)
    print("Mean: " + to_text(mean))
    print("Result: " + verdict(mean))
}
```

```text
Mean: 60.333333333333336
Result: passed
```

## Next steps

- More programs, ready to run: [`examples/`](../examples/README.md).
- The rules, one by one: [types](types.md) and [functions](functions.md).
- Writing the rules in the code, which is what distinguishes NEXORA: [contracts](contracts.md)
  (what a function expects and promises) and [refined types](types.md#refined-types) (the values
  a type accepts).
- The complete reference of the language: [specification](language-spec.md).
- What NEXORA cannot do yet (maps, enumerations…): [limitations](limitations.md).
