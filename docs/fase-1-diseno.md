# NEXORA — Phase 1: Language design (v0.1)

Status: design draft. There is no compiler yet; nothing that appears here has been run.

## 1. Goal and principles

NEXORA is a general-purpose language, web-oriented first, meant for code that is written and reviewed by people and by AI models alike.

| # | Principle | Consequence in the design |
|---|-----------|---------------------------|
| P1 | One way to do each thing | Small and regular syntax, a single format, no equivalent shortcuts |
| P2 | Everything important is in the signature | Types, effects and errors are declared; there is no hidden behaviour |
| P3 | Failures are values | No `null` and no exceptions: `Option` and `Result` |
| P4 | The intention is verifiable | Contracts (`requires`, `ensures`) and examples (`example`) are part of the language |
| P5 | AI is part of the language | `ai fn` and `tool fn` with typed inputs and outputs |
| P6 | Web first | Compiles to JavaScript; WebAssembly later |

## 2. Lexicon

- Code files: extension `.nx`, UTF-8 encoding.
- Comments: `//` to the end of the line. `///` is a documentation comment and belongs to the declaration that follows it.
- Blocks with braces `{ }`. There is no semicolon: the line break ends the statement.
- A statement continues on the next line only if it is inside `( )` or `[ ]`, or if the next line starts with a binary operator (for example `|>`).
- Names (checked by the compiler):
  - `snake_case`: variables, functions, parameters, fields, modules.
  - `PascalCase`: types, `enum` variants, effects.
  - `UPPERCASE_WITH_UNDERSCORES`: constants.

Reserved words:

```
ai       and      assert   break    const    continue else     ensures
enum     example  false    fn       for      if       import   in
let      match    not      or       pub      requires return   test
tool     true     try      type     uses     var      where    while
```

`result` and `value` are contextual words: they only have a special meaning inside `ensures` and `where`.

Literals:

```nexora
42          1_000_000     0xFF        // Int
3.14        1.0e-3                    // Float
true        false                     // Bool
"Hello {name}"                        // String with interpolation
"""
Multi-line text
"""
[1, 2, 3]                             // List<Int>
["es": "Hola", "en": "Hello"]         // Map<String, String>
[:]                                   // empty Map
(1, "one")                            // tuple
()                                    // Unit
```

Strings always use double quotes. `{expr}` interpolates; `\{` writes a literal brace. Only primitive types can be interpolated; the rest are converted explicitly.

## 3. Data types

### 3.1 Primitives

| Type | Description |
|------|-------------|
| `Int` | 64-bit signed integer. Overflow is a `panic`, never a silent result |
| `Float` | IEEE 754 64-bit floating point |
| `Bool` | `true` or `false` |
| `String` | Immutable UTF-8 text |
| `Unit` | Absence of a value; its only value is `()` |

### 3.2 Compound

| Type | Description |
|------|-------------|
| `List<T>` | Ordered sequence |
| `Map<K, V>` | Dictionary |
| `Set<T>` | Set without duplicates |
| `(A, B, ...)` | Tuple; it is read by destructuring: `let (a, b) = pair` |
| `Option<T>` | `Some(value)` or `None`. It can be written `T?` |
| `Result<T, E>` | `Ok(value)` or `Err(error)` |
| `fn(A, B) -> C` | Function type |

All values are immutable: "modifying" a list or a record returns a new one. There is no mutable aliasing.

### 3.3 Records

```nexora
type User {
  id: Int
  name: String
  email: String?
}

let ana = User(id: 1, name: "Ana", email: None)
let ana_with_email = User(..ana, email: Some("ana@example.com"))
let name = ana.name
```

Fields are separated by a line break or a comma. When building a record the field names are required.

### 3.4 Enumerations (sum types)

```nexora
enum Shape {
  Circle(radius: Float)
  Rect(width: Float, height: Float)
  Empty
}

let figure = Shape.Circle(radius: 2.0)
```

Variants are always written qualified (`Shape.Circle`). The only exceptions are `Some`, `None`, `Ok` and `Err`.

### 3.5 Aliases and refined types

```nexora
type UserId = Int                                   // alias
type Percent = Int where value >= 0 and value <= 100  // refined
```

A refined type is its base type plus a condition:

- A literal is checked at compile time: `let p: Percent = 120` is a compile error.
- A dynamic value is converted with `Percent.from(n)`, which returns `Result<Percent, RefinementError>`.
- A `Percent` can be used where an `Int` is expected; not the other way round.

### 3.6 Generics

```nexora
type Page<T> {
  items: List<T>
  total: Int
}

fn first<T>(items: List<T>) -> T? { List.get(items, 0) }
```

Type arguments are not written in calls; they are inferred.

## 4. Variables

```nexora
let name = "Ana"          // immutable; inferred type
let age: Int = 30         // optional annotation
var count = 0             // mutable (it can be reassigned)
count = count + 1

const MAX_RETRIES: Int = 3   // only at module level; type required
```

- `let` is the norm; `var` only when reassigning is needed.
- Every variable is initialized when declared.
- `var` does not exist at module level: there is no mutable global state.
- A name already visible in the same function cannot be redeclared (no *shadowing*).
- An unused variable is an error; it is discarded explicitly with `let _ = ...`.
- The only assignment is `=`; there is no `+=`, `++`, etc.

## 5. Functions

```nexora
fn add(a: Int, b: Int) -> Int {
  a + b
}
```

- The types of the parameters and the return type are required (`-> Unit` if it returns nothing).
- A block is worth its last expression. `return` is only used to leave early.
- Default values: `fn greet(name: String, greeting: String = "Hello") -> String`.
- Arguments can be passed by position or by name; the named ones go at the end: `greet("Ana", greeting: "Hi")`.
- Anonymous functions with the same keyword: `List.map(nums, fn(x) { x * 2 })`.
- There are no methods or classes. Functions live in modules and are chained with `|>`:

```nexora
let total = orders
  |> List.filter(fn(o) { o.paid })
  |> List.map(fn(o) { o.amount_cents })
  |> List.sum()
```

`x |> f(a)` is equivalent to `f(x, a)`.

### 5.1 Signature clauses

Between the return type and the body go the clauses, always in this order: `uses`, `requires`, `ensures`, `example`.

```nexora
/// Applies a discount to a price in cents.
pub fn apply_discount(price_cents: Int, percent: Percent) -> Int
  requires price_cents >= 0
  ensures result >= 0 and result <= price_cents
  example apply_discount(10_000, 20) == 8_000
{
  price_cents * (100 - percent) / 100
}
```

| Clause | Meaning |
|--------|---------|
| `uses Effect, ...` | Effects that the function can produce |
| `requires expr` | Precondition on the parameters |
| `ensures expr` | Postcondition; `result` is the returned value |
| `example expr` | `Bool` expression that must be true; `nexora test` runs it as a test |

In v0.1 contracts are checked at run time; breaking one is a `panic`.

### 5.2 Effects

A function without `uses` is pure: the same result for the same inputs and no external effect. To call a function with effects, the caller must declare those same effects.

| Effect | Allows |
|--------|--------|
| `Net` | Network |
| `Fs` | File system |
| `Db` | Database |
| `Dom` | Browser interface |
| `Time` | Reading the clock |
| `Random` | Randomness |
| `Log` | Writing logs |
| `Ai` | Calling an AI model |

```nexora
fn load_user(id: Int) -> Result<User, http.Error> uses Net {
  let response = try http.get("https://api.example.com/users/{id}")
  json.decode(response.body)
}
```

There is no `async`/`await`: the compiler generates asynchronous code from the effects.

### 5.3 Errors

- A recoverable error is a `Result<T, E>`. Ignoring a `Result` is a compile error.
- `try expr` returns the `Err` (or `None`) to the caller if the expression fails; it is only valid if the function returns a `Result` with the same error type (or an `Option`).
- `panic("message")` is for programming errors; it cannot be caught.

### 5.4 AI functions

An `ai fn` has no code: its body is a request to a model. The return type becomes the output schema and the response is validated against it, including refined types and `ensures`.

```nexora
/// Classifies a support ticket into a category.
ai fn classify(ticket: String) -> Result<Category, AiError>
  uses Ai
  example classify("I was charged twice") == Ok(Category.Billing)
{
  model: "fast"
  system: "You are a support ticket classifier."
  prompt: "Classify this ticket: {ticket}"
}
```

- It always returns `Result<T, AiError>` and declares `uses Ai`.
- `model` is an alias defined in the configuration of the project (`nexora.toml`), not the name of a provider.
- The `///` comment is required and is sent to the model as the description of the task.
- The `example` clauses are used as examples for the model and as evaluations (`nexora eval`), not as strict tests, because the output is not deterministic.

A `tool fn` is a normal function that a model can invoke. Its `///` is the description of the tool and its parameters are the input schema. An `ai fn` lists them in `tools:` and must also declare the effects of those tools.

```nexora
/// Returns the status of an order from its identifier.
tool fn order_status(order_id: Int) -> Result<String, http.Error> uses Net {
  let response = try http.get("https://api.example.com/orders/{order_id}")
  Ok(response.body)
}
```

## 6. Control flow

```nexora
let label = if age >= 18 { "adult" } else { "minor" }

let area = match shape {
  Shape.Circle(radius) -> 3.14159 * radius * radius
  Shape.Rect(width, height) -> width * height
  Shape.Empty -> 0.0
}

for item in items { log.info(item.name) }
for i in 0..10 { log.info("{i}") }      // 0 to 9
while count < 10 { count = count + 1 }
```

- `if` and `match` are expressions. Used as an expression, `if` needs `else`.
- The condition is always `Bool`; there are no implicit "truthy" or "falsy" values.
- `match` must cover all cases; `_` is the wildcard.
- `break` and `continue` inside loops. There is no ternary operator.

## 7. Operators

From highest to lowest precedence:

| Level | Operators | Notes |
|-------|-----------|-------|
| 1 | `f(x)`  `a.b` | Call and access |
| 2 | `-x`  `not x`  `try x` | Unary |
| 3 | `*`  `/`  `%` | `/` between `Int` is integer division |
| 4 | `+`  `-` | Only numerics of the same type |
| 5 | `..` | Range, end excluded |
| 6 | `==`  `!=`  `<`  `<=`  `>`  `>=` | Structural equality; they do not chain |
| 7 | `and` | |
| 8 | `or` | |
| 9 | `\|>` | Pipe |

`Int` and `Float` do not mix (`Int.to_float(x)`). Strings are not added with `+`: interpolation is used.

## 8. Modules

```nexora
import http
import app/models.{User, Order}
```

- A file is a module; its name is that of the file.
- Everything is private except what is marked with `pub`.
- Every type is also a namespace: `String.length(s)`, `Percent.from(n)`.
- Circular imports are not allowed.
- The entry point is `fn main() -> Unit` in `main.nx`.

Tests, in any module:

```nexora
test "the empty cart is an error" {
  assert cart_total([]) == Err(OrderError.EmptyCart)
}
```

## 9. Rules of the language

All of them are checked by the compiler; none is a style recommendation.

| # | Rule |
|---|------|
| R1 | `null` does not exist. Absence is expressed with `Option<T>` |
| R2 | Exceptions do not exist. Recoverable errors are `Result<T, E>` |
| R3 | Everything is immutable by default; only `var` allows reassigning |
| R4 | There are no implicit conversions (only exception: refined type to its base type) |
| R5 | A visible name cannot be redeclared (no *shadowing*) |
| R6 | Unused variables, imports and results are errors |
| R7 | `match` is exhaustive |
| R8 | Effects are declared with `uses` and propagate to the caller |
| R9 | Naming conventions are required |
| R10 | There is a single code format (`nexora fmt`), without options |
| R11 | Every `pub` declaration, `ai fn` and `tool fn` carries `///` documentation |
| R12 | Conditions are always `Bool` |
| R13 | There is no mutable global state |
| R14 | There are no circular imports |
| R15 | Every compiler error has a stable code, a position and a suggested fix, also in JSON, so that an AI can read it and fix it |

## 10. Summarized grammar (EBNF)

An indicative summary; the complete grammar is set when the parser is written.

```ebnf
program    = { import } { item } ;
import     = "import" path [ "." "{" NAME { "," NAME } "}" ] ;
path       = name { "/" name } ;

item       = [ "pub" ] ( const | type_decl | enum_decl | fn_decl ) | test ;
const      = "const" CONST_NAME ":" type "=" expr ;
type_decl  = "type" TypeName [ generics ]
             ( "{" fields "}" | "=" type [ "where" expr ] ) ;
enum_decl  = "enum" TypeName [ generics ] "{" variant { sep variant } "}" ;
variant    = TypeName [ "(" fields ")" ] ;
fields     = field { sep field } ;
field      = name ":" type ;
generics   = "<" TypeName { "," TypeName } ">" ;
sep        = "," | NEWLINE ;

fn_decl    = [ "ai" | "tool" ] "fn" name [ generics ] "(" [ params ] ")"
             "->" type { clause } ( block | ai_body ) ;
params     = param { "," param } ;
param      = name ":" type [ "=" expr ] ;
clause     = "uses" TypeName { "," TypeName }
           | "requires" expr | "ensures" expr | "example" expr ;
ai_body    = "{" { name ":" expr NEWLINE } "}" ;
test       = "test" STRING block ;

type       = type_path [ "<" type { "," type } ">" ] [ "?" ]
           | "(" [ type { "," type } ] ")"
           | "fn" "(" [ type { "," type } ] ")" "->" type ;
type_path  = [ name "." ] TypeName ;

block      = "{" { statement NEWLINE } [ expr ] "}" ;
statement  = "let" pattern [ ":" type ] "=" expr
           | "var" name [ ":" type ] "=" expr
           | name "=" expr
           | "return" [ expr ] | "break" | "continue"
           | "assert" expr
           | "for" pattern "in" expr block
           | "while" expr block
           | expr ;

expr       = if_expr | match_expr | lambda | binary ;
if_expr    = "if" expr block [ "else" ( if_expr | block ) ] ;
match_expr = "match" expr "{" { pattern "->" expr NEWLINE } "}" ;
lambda     = "fn" "(" [ name { "," name } ] ")" block ;
binary     = (* operators according to the table of section 7 *) ;
pattern    = "_" | name | literal
           | "(" pattern { "," pattern } ")"
           | [ TypeName "." ] TypeName [ "(" pattern { "," pattern } ")" ] ;
```

## 11. Out of scope of v0.1

Decisions postponed to later phases:

- Concurrency (running several operations with effects in parallel).
- Web interface components over the `Dom` effect.
- Standard library: the modules used in the examples (`http`, `json`, `log`, `List`, `String`) are illustrative.
- Interoperability with JavaScript and a package manager.
- Static verification of contracts.
