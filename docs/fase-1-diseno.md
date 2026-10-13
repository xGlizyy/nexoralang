# NEXORA — Fase 1: Diseño del lenguaje (v0.1)

Estado: borrador de diseño. Todavía no existe compilador; nada de lo que aparece aquí se ha ejecutado.

## 1. Objetivo y principios

NEXORA es un lenguaje de propósito general, orientado primero a la web, pensado para que el código lo escriban y lo revisen tanto personas como modelos de IA.

| # | Principio | Consecuencia en el diseño |
|---|-----------|---------------------------|
| P1 | Una sola forma de hacer cada cosa | Sintaxis pequeña y regular, formato único, sin atajos equivalentes |
| P2 | Todo lo importante está en la firma | Tipos, efectos y errores se declaran; no hay comportamiento oculto |
| P3 | Los fallos son valores | Sin `null` y sin excepciones: `Option` y `Result` |
| P4 | La intención es verificable | Contratos (`requires`, `ensures`) y ejemplos (`example`) forman parte del lenguaje |
| P5 | La IA es parte del lenguaje | `ai fn` y `tool fn` con entradas y salidas tipadas |
| P6 | Web primero | Compila a JavaScript; WebAssembly más adelante |

## 2. Léxico

- Archivos de código: extensión `.nx`, codificación UTF-8.
- Comentarios: `//` hasta fin de línea. `///` es un comentario de documentación y pertenece a la declaración que le sigue.
- Bloques con llaves `{ }`. No hay punto y coma: el salto de línea termina la sentencia.
- Una sentencia continúa en la línea siguiente solo si está dentro de `( )` o `[ ]`, o si la línea siguiente empieza por un operador binario (por ejemplo `|>`).
- Nombres (lo comprueba el compilador):
  - `snake_case`: variables, funciones, parámetros, campos, módulos.
  - `PascalCase`: tipos, variantes de `enum`, efectos.
  - `MAYUSCULAS_CON_GUION`: constantes.

Palabras reservadas:

```
ai       and      assert   break    const    continue else     ensures
enum     example  false    fn       for      if       import   in
let      match    not      or       pub      requires return   test
tool     true     try      type     uses     var      where    while
```

`result` y `value` son palabras contextuales: solo tienen significado especial dentro de `ensures` y `where`.

Literales:

```nexora
42          1_000_000     0xFF        // Int
3.14        1.0e-3                    // Float
true        false                     // Bool
"Hola {name}"                         // String con interpolación
"""
Texto de varias líneas
"""
[1, 2, 3]                             // List<Int>
["es": "Hola", "en": "Hello"]         // Map<String, String>
[:]                                   // Map vacío
(1, "uno")                            // tupla
()                                    // Unit
```

Las cadenas usan siempre comillas dobles. `{expr}` interpola; `\{` escribe una llave literal. Solo se pueden interpolar tipos primitivos; el resto se convierte de forma explícita.

## 3. Tipos de datos

### 3.1 Primitivos

| Tipo | Descripción |
|------|-------------|
| `Int` | Entero con signo de 64 bits. El desbordamiento es un `panic`, nunca un resultado silencioso |
| `Float` | Coma flotante IEEE 754 de 64 bits |
| `Bool` | `true` o `false` |
| `String` | Texto UTF-8 inmutable |
| `Unit` | Ausencia de valor; su único valor es `()` |

### 3.2 Compuestos

| Tipo | Descripción |
|------|-------------|
| `List<T>` | Secuencia ordenada |
| `Map<K, V>` | Diccionario |
| `Set<T>` | Conjunto sin duplicados |
| `(A, B, ...)` | Tupla; se lee por desestructuración: `let (a, b) = par` |
| `Option<T>` | `Some(valor)` o `None`. Se puede escribir `T?` |
| `Result<T, E>` | `Ok(valor)` o `Err(error)` |
| `fn(A, B) -> C` | Tipo función |

Todos los valores son inmutables: "modificar" una lista o un registro devuelve uno nuevo. No existe aliasing mutable.

### 3.3 Registros

```nexora
type User {
  id: Int
  name: String
  email: String?
}

let ana = User(id: 1, name: "Ana", email: None)
let ana_con_email = User(..ana, email: Some("ana@example.com"))
let nombre = ana.name
```

Los campos se separan con salto de línea o coma. Al construir un registro los nombres de campo son obligatorios.

### 3.4 Enumeraciones (tipos suma)

```nexora
enum Shape {
  Circle(radius: Float)
  Rect(width: Float, height: Float)
  Empty
}

let figura = Shape.Circle(radius: 2.0)
```

Las variantes se escriben siempre cualificadas (`Shape.Circle`). Las únicas excepciones son `Some`, `None`, `Ok` y `Err`.

### 3.5 Alias y tipos refinados

```nexora
type UserId = Int                                   // alias
type Percent = Int where value >= 0 and value <= 100  // refinado
```

Un tipo refinado es su tipo base más una condición:

- Un literal se comprueba al compilar: `let p: Percent = 120` es un error de compilación.
- Un valor dinámico se convierte con `Percent.from(n)`, que devuelve `Result<Percent, RefinementError>`.
- Un `Percent` se puede usar donde se espera un `Int`; al revés no.

### 3.6 Genéricos

```nexora
type Page<T> {
  items: List<T>
  total: Int
}

fn first<T>(items: List<T>) -> T? { List.get(items, 0) }
```

Los argumentos de tipo no se escriben en las llamadas; se infieren.

## 4. Variables

```nexora
let name = "Ana"          // inmutable; tipo inferido
let age: Int = 30         // anotación opcional
var count = 0             // mutable (se puede reasignar)
count = count + 1

const MAX_RETRIES: Int = 3   // solo a nivel de módulo; tipo obligatorio
```

- `let` es lo normal; `var` solo cuando hace falta reasignar.
- Toda variable se inicializa al declararla.
- `var` no existe a nivel de módulo: no hay estado global mutable.
- No se puede redeclarar un nombre ya visible en la misma función (sin *shadowing*).
- Una variable sin usar es un error; se descarta de forma explícita con `let _ = ...`.
- La única asignación es `=`; no hay `+=`, `++`, etc.

## 5. Funciones

```nexora
fn add(a: Int, b: Int) -> Int {
  a + b
}
```

- Los tipos de los parámetros y el tipo de retorno son obligatorios (`-> Unit` si no devuelve nada).
- Un bloque vale lo que su última expresión. `return` se usa solo para salir antes.
- Valores por defecto: `fn greet(name: String, greeting: String = "Hola") -> String`.
- Los argumentos pueden pasarse por posición o por nombre; los nombrados van al final: `greet("Ana", greeting: "Buenas")`.
- Funciones anónimas con la misma palabra clave: `List.map(nums, fn(x) { x * 2 })`.
- No hay métodos ni clases. Las funciones viven en módulos y se encadenan con `|>`:

```nexora
let total = orders
  |> List.filter(fn(o) { o.paid })
  |> List.map(fn(o) { o.amount_cents })
  |> List.sum()
```

`x |> f(a)` equivale a `f(x, a)`.

### 5.1 Cláusulas de la firma

Entre el tipo de retorno y el cuerpo van las cláusulas, siempre en este orden: `uses`, `requires`, `ensures`, `example`.

```nexora
/// Aplica un descuento a un precio en céntimos.
pub fn apply_discount(price_cents: Int, percent: Percent) -> Int
  requires price_cents >= 0
  ensures result >= 0 and result <= price_cents
  example apply_discount(10_000, 20) == 8_000
{
  price_cents * (100 - percent) / 100
}
```

| Cláusula | Significado |
|----------|-------------|
| `uses Efecto, ...` | Efectos que la función puede producir |
| `requires expr` | Precondición sobre los parámetros |
| `ensures expr` | Postcondición; `result` es el valor devuelto |
| `example expr` | Expresión `Bool` que debe ser cierta; `nexora test` la ejecuta como prueba |

En v0.1 los contratos se comprueban en ejecución; incumplir uno es un `panic`.

### 5.2 Efectos

Una función sin `uses` es pura: mismo resultado para las mismas entradas y ningún efecto externo. Para llamar a una función con efectos, quien llama debe declarar esos mismos efectos.

| Efecto | Permite |
|--------|---------|
| `Net` | Red |
| `Fs` | Sistema de archivos |
| `Db` | Base de datos |
| `Dom` | Interfaz del navegador |
| `Time` | Leer el reloj |
| `Random` | Aleatoriedad |
| `Log` | Escribir registros |
| `Ai` | Llamar a un modelo de IA |

```nexora
fn load_user(id: Int) -> Result<User, http.Error> uses Net {
  let response = try http.get("https://api.example.com/users/{id}")
  json.decode(response.body)
}
```

No hay `async`/`await`: el compilador genera código asíncrono a partir de los efectos.

### 5.3 Errores

- Un error recuperable es un `Result<T, E>`. Ignorar un `Result` es un error de compilación.
- `try expr` devuelve el `Err` (o `None`) a quien llama si la expresión falla; solo es válido si la función devuelve un `Result` con el mismo tipo de error (o un `Option`).
- `panic("mensaje")` es para errores de programación; no se puede capturar.

### 5.4 Funciones de IA

Una `ai fn` no tiene código: su cuerpo es una petición a un modelo. El tipo de retorno se convierte en el esquema de salida y la respuesta se valida contra él, incluidos los tipos refinados y los `ensures`.

```nexora
/// Clasifica un ticket de soporte en una categoría.
ai fn classify(ticket: String) -> Result<Category, AiError>
  uses Ai
  example classify("Me han cobrado dos veces") == Ok(Category.Billing)
{
  model: "fast"
  system: "Eres un clasificador de tickets de soporte."
  prompt: "Clasifica este ticket: {ticket}"
}
```

- Devuelve siempre `Result<T, AiError>` y declara `uses Ai`.
- `model` es un alias definido en la configuración del proyecto (`nexora.toml`), no un nombre de proveedor.
- El comentario `///` es obligatorio y se envía al modelo como descripción de la tarea.
- Los `example` se usan como ejemplos para el modelo y como evaluaciones (`nexora eval`), no como pruebas estrictas, porque la salida no es determinista.

Una `tool fn` es una función normal que un modelo puede invocar. Su `///` es la descripción de la herramienta y sus parámetros son el esquema de entrada. Una `ai fn` las lista en `tools:` y debe declarar también los efectos de esas herramientas.

```nexora
/// Devuelve el estado de un pedido a partir de su identificador.
tool fn order_status(order_id: Int) -> Result<String, http.Error> uses Net {
  let response = try http.get("https://api.example.com/orders/{order_id}")
  Ok(response.body)
}
```

## 6. Control de flujo

```nexora
let label = if age >= 18 { "adulto" } else { "menor" }

let area = match shape {
  Shape.Circle(radius) -> 3.14159 * radius * radius
  Shape.Rect(width, height) -> width * height
  Shape.Empty -> 0.0
}

for item in items { log.info(item.name) }
for i in 0..10 { log.info("{i}") }      // 0 a 9
while count < 10 { count = count + 1 }
```

- `if` y `match` son expresiones. Usado como expresión, `if` necesita `else`.
- La condición es siempre `Bool`; no hay valores "verdaderos" o "falsos" implícitos.
- `match` debe cubrir todos los casos; `_` es el comodín.
- `break` y `continue` dentro de bucles. No hay operador ternario.

## 7. Operadores

De mayor a menor precedencia:

| Nivel | Operadores | Notas |
|-------|-----------|-------|
| 1 | `f(x)`  `a.b` | Llamada y acceso |
| 2 | `-x`  `not x`  `try x` | Unarios |
| 3 | `*`  `/`  `%` | `/` entre `Int` es división entera |
| 4 | `+`  `-` | Solo numéricos del mismo tipo |
| 5 | `..` | Rango, fin excluido |
| 6 | `==`  `!=`  `<`  `<=`  `>`  `>=` | Igualdad estructural; no se encadenan |
| 7 | `and` | |
| 8 | `or` | |
| 9 | `\|>` | Tubería |

No se mezclan `Int` y `Float` (`Int.to_float(x)`). Las cadenas no se suman con `+`: se usa interpolación.

## 8. Módulos

```nexora
import http
import app/models.{User, Order}
```

- Un archivo es un módulo; su nombre es el del archivo.
- Todo es privado salvo lo marcado con `pub`.
- Cada tipo es también un espacio de nombres: `String.length(s)`, `Percent.from(n)`.
- No se permiten importaciones circulares.
- El punto de entrada es `fn main() -> Unit` en `main.nx`.

Pruebas, en cualquier módulo:

```nexora
test "el carrito vacío es un error" {
  assert cart_total([]) == Err(OrderError.EmptyCart)
}
```

## 9. Reglas del lenguaje

Todas las comprueba el compilador; ninguna es una recomendación de estilo.

| # | Regla |
|---|-------|
| R1 | No existe `null`. La ausencia se expresa con `Option<T>` |
| R2 | No existen excepciones. Los errores recuperables son `Result<T, E>` |
| R3 | Todo es inmutable por defecto; solo `var` permite reasignar |
| R4 | No hay conversiones implícitas (única excepción: tipo refinado a su tipo base) |
| R5 | No se puede redeclarar un nombre visible (sin *shadowing*) |
| R6 | Variables, importaciones y resultados sin usar son errores |
| R7 | `match` es exhaustivo |
| R8 | Los efectos se declaran con `uses` y se propagan a quien llama |
| R9 | Las convenciones de nombres son obligatorias |
| R10 | Hay un único formato de código (`nexora fmt`), sin opciones |
| R11 | Toda declaración `pub`, `ai fn` y `tool fn` lleva documentación `///` |
| R12 | Las condiciones son siempre `Bool` |
| R13 | No hay estado global mutable |
| R14 | No hay importaciones circulares |
| R15 | Cada error del compilador tiene código estable, posición y corrección sugerida, también en JSON, para que una IA pueda leerlo y arreglarlo |

## 10. Gramática resumida (EBNF)

Resumen orientativo; la gramática completa se fija al escribir el analizador.

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
binary     = (* operadores según la tabla de la sección 7 *) ;
pattern    = "_" | name | literal
           | "(" pattern { "," pattern } ")"
           | [ TypeName "." ] TypeName [ "(" pattern { "," pattern } ")" ] ;
```

## 11. Fuera del alcance de v0.1

Decisiones aplazadas a fases posteriores:

- Concurrencia (ejecutar varias operaciones con efectos en paralelo).
- Componentes de interfaz web sobre el efecto `Dom`.
- Biblioteca estándar: los módulos usados en los ejemplos (`http`, `json`, `log`, `List`, `String`) son ilustrativos.
- Interoperabilidad con JavaScript y gestor de paquetes.
- Verificación estática de contratos.
