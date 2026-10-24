# Functions

The formal definition is in the [specification](language-spec.md#7-functions). This guide
explains it with examples; all of them are checked by the tests of the project.

## Declaring a function

```nex
fn add(a: Int, b: Int) gives Int {
    return a + b
}
```

| Part | Rule |
|------|------|
| `fn add` | The name. It cannot be repeated or match that of a built-in function |
| `(a: Int, b: Int)` | The parameters. Each one declares its type, which has to be a value type |
| `gives Int` | The result type. A function that returns nothing has no `gives` |
| `{ ... }` | The body. Between the signature and the `{`, a function can declare its contracts and examples, one per line ([contracts](contracts.md)) |

Functions are declared at the top level of the file, in any order: a function can
call another one declared further down. Functions cannot be declared inside other functions.

## The `main` function

Every program has a `main` function, with no parameters and without `gives`. It is where
execution starts.

<!-- nex:run -->
```nex
fn main() {
    print(square(7))
}

fn square(n: Int) gives Int {
    return n * n
}
```

```text
49
```

## Calling a function

Arguments are assigned to the parameters by position. Before running the program it is
checked that the function exists, that the number of arguments matches and that each argument has
the type of its parameter.

<!-- nex:check-fails -->
```nex
fn add(a: Int, b: Int) gives Int {
    return a + b
}

fn main() {
    print(add(1))
    print(add(1, "2"))
    print(ad(1, 2))
}
```

```text
type error[E2009]: Wrong number of arguments
 --> program.nex:6:11
  |
6 |     print(add(1))
  |           ^^^^^^ 'add' takes 2 arguments, but 1 was given
  = note: Its signature is: fn add(a: Int, b: Int) gives Int

type error[E2011]: Type mismatch
 --> program.nex:7:18
  |
7 |     print(add(1, "2"))
  |                  ^^^ Expected Int, found Text
  = note: This is the argument for 'b' in: fn add(a: Int, b: Int) gives Int

semantic error[E2008]: Unknown function
 --> program.nex:8:11
  |
8 |     print(ad(1, 2))
  |           ^^ There is no function named 'ad'
  = hint: Did you mean 'add'?

error: program.nex: check failed with 3 errors
```

When it runs, a call evaluates its arguments from left to right, creates a new scope with
the parameters, runs the body and returns the value to the point of the call.

A function **does not see the variables of its caller**: only its parameters and what it declares in its
body. There are no global variables. Parameters, like variables, cannot change their value.

## Returning a value

In a function that returns a value, `return` is followed by an expression of the declared type:

<!-- nex:check-fails -->
```nex
fn label(count: Int) gives Text {
    return count
}

fn main() {
    print(label(3))
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:12
  |
2 |     return count
  |            ^^^^^ Expected Text, found Int
  = note: 'label' is declared to return Text.
  = hint: Convert the value explicitly with to_text(...).

error: program.nex: check failed with 1 error
```

The returned value **cannot be ignored**. Calling a function that returns something and not using the
result is an error (`E2010`):

<!-- nex:check-fails -->
```nex
fn add(a: Int, b: Int) gives Int {
    return a + b
}

fn main() {
    add(1, 2)
}
```

```text
semantic error[E2010]: Unused value
 --> program.nex:6:5
  |
6 |     add(1, 2)
  |     ^^^^^^^^^ The Int returned by 'add' is never used
  = hint: Store it with 'let name = ...' or pass it to a function.

error: program.nex: check failed with 1 error
```

## Functions that return nothing

A function without `gives` returns no value. It ends when it reaches the end of the body, or before with a
`return` without a value:

<!-- nex:run -->
```nex
fn report(score: Int) {
    if score < 0 {
        print("invalid score")
        return
    }
    print("score: " + to_text(score))
}

fn main() {
    report(-1)
    report(80)
}
```

```text
invalid score
score: 80
```

A call to a function without `gives` is a statement: its type is `Void`, so it cannot be stored in a
variable, printed or passed as an argument. In such a function, `return` followed by a value is an error
(`E2011`).

## `if` and `else`

`if` is a statement. The condition has to be of type `Bool`. `else` and `else if` are written on
the same line as the previous `}`.

<!-- nex:run -->
```nex
fn sign(n: Int) gives Int {
    if n < 0 {
        return -1
    } else if n == 0 {
        return 0
    } else {
        return 1
    }
}

fn main() {
    print(sign(-8))
    print(sign(0))
    print(sign(5))
}
```

```text
-1
0
1
```

Every block (`{ }`) has its own scope: a variable declared inside an `if` stops
existing when its block closes.

## Every path returns

A function that returns a value has to end with `return` on **every** possible
path. If any of them can reach the end of the body, the program is rejected before running:

<!-- nex:check-fails -->
```nex
fn sign(n: Int) gives Int {
    if n < 0 {
        return -1
    } else if n > 0 {
        return 1
    }
}

fn main() {
    print(sign(0))
}
```

```text
semantic error[E2014]: Missing return
 --> program.nex:1:4
  |
1 | fn sign(n: Int) gives Int {
  |    ^^^^ 'sign' must return a value of type Int, but its body can end without a 'return'
  = hint: Make sure every path through the function ends with 'return'. An 'if' without 'else' can be skipped, and a loop may not run at all.

error: program.nex: check failed with 1 error
```

How it is decided whether a block always returns:

| Statement | Always returns if… |
|-----------|--------------------|
| `return` | Always |
| `if` without a final `else` | Never: the condition may be false |
| `if` … `else` … | All its branches always return |
| A block `{ }` | One of its statements always returns |

The analysis looks at the structure, not at the values: `if true { return 1 }` without `else` is also rejected.

Code placed after a `return`, in the same block, can never run and is an
error (`E2015`).

## Recursion

A function can call itself, and two functions can call each other. To repeat something
many times a `while` loop is better ([contracts](contracts.md#loops-keeps-and-shrinks)): its
iterations are not calls and do not have the limit of 1000.

<!-- nex:run -->
```nex
fn factorial(n: Int) gives Int {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}

fn countdown(n: Int) {
    if n == 0 {
        print("liftoff")
        return
    }
    print(n)
    countdown(n - 1)
}

fn main() {
    print(factorial(10))
    countdown(3)
}
```

```text
3628800
3
2
1
liftoff
```

**Limit:** a program can have at most 1000 nested calls (counting `main`). A
recursion that does not reach its base case stops with a runtime error:

<!-- nex:fails exit=3 -->
```nex
fn forever(n: Int) gives Int {
    return forever(n + 1)
}

fn main() {
    print(forever(0))
}
```

```text
runtime error[E3004]: Too many nested calls
 --> program.nex:2:12
  |
2 |     return forever(n + 1)
  |            ^^^^^^^^^^^^^^ The program nested more than 1000 calls
  = note: In 'forever', called at line 2, column 12.
  = note: In 'forever', called at line 2, column 12.
  = note: In 'forever', called at line 2, column 12.
  = note: In 'forever', called at line 2, column 12.
  = note: In 'forever', called at line 2, column 12.
  = note: In 'forever', called at line 2, column 12.
  = note: ... and 993 more calls.
  = hint: A recursive function probably never reaches the case where it stops calling itself.

error: program.nex: the program stopped because of a runtime error
```

If the recursive calls are inside very nested expressions, the program can run out of
stack space before reaching 1000 calls. The error is the same (`E3004`) and the
message says how many calls there were.

## Names

Functions, parameters and variables share a single namespace, and a visible name is not
declared twice. Consequently:

<!-- nex:check-fails -->
```nex
fn area(width: Int, width: Int) gives Int {
    let area = width * width
    return area
}

fn main() {
    print(area(2, 3))
}
```

```text
semantic error[E2006]: Name already declared
 --> program.nex:1:21
  |
1 | fn area(width: Int, width: Int) gives Int {
  |                     ^^^^^ 'width' is already declared and still visible here
  = note: It was first declared at line 1, column 9.
  = hint: Choose a different name: a visible name cannot be declared again.

semantic error[E2006]: Name already declared
 --> program.nex:2:9
  |
2 |     let area = width * width
  |         ^^^^ 'area' is the name of a function and cannot be used for something else
  = hint: Choose a different name.

type error[E2011]: Type mismatch
 --> program.nex:3:12
  |
3 |     return area
  |            ^^^^ 'area' is a function, not a value
  = hint: Call it with parentheses: area(...)

error: program.nex: check failed with 3 errors
```

## Restrictions of this version

- There are no default values or named arguments.
- There is no overloading: two functions cannot have the same name.
- Functions are not values: they cannot be stored in variables or passed as arguments.
- There are no anonymous functions, generics, methods or classes.
- A parameter cannot be named `result` (that name is used in [contracts](contracts.md)).
- A trailing comma is not allowed in parameter or argument lists.
- `main` receives no parameters: the arguments of the command line are read with `args()`
  ([decision 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)).
