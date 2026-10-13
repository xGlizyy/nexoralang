# Tipos

NEXORA tiene un sistema de tipos **estático**: el tipo de cada expresión se conoce sin ejecutar el
programa, y todos los errores de tipos los detecta `nex check`. Ningún error de tipos puede
aparecer mientras el programa se ejecuta.

La definición formal está en la [especificación](language-spec.md#4-tipos-de-datos). Esta guía la
explica con ejemplos; todos se comprueban en las pruebas del proyecto.

## Los cinco tipos

| Tipo | Valores | Literales |
|------|---------|-----------|
| `Int` | Enteros de 64 bits con signo: de `-9223372036854775808` a `9223372036854775807` | `0`, `42`, `1_000_000` |
| `Float` | Coma flotante IEEE 754 de 64 bits | `3.14`, `0.5`, `10.0` |
| `Bool` | Verdadero o falso | `true`, `false` |
| `Text` | Texto Unicode, inmutable | `"Hello"` |
| `Void` | Ningún valor | No tiene literales |

`Int`, `Float`, `Bool` y `Text` son los **tipos de valor**: los que puede tener una variable, un
parámetro o una expresión. `Void` solo puede usarse como tipo de retorno de una función que no
devuelve nada.

Detalles de cada uno:

- **`Int`**: un resultado fuera de rango no "da la vuelta": detiene el programa con el error `E3002`.
- **`Float`**: algunas fracciones decimales no son exactas (`0.1 + 0.2` es `0.30000000000000004`).
  No existen infinito ni NaN: una operación cuyo resultado no cabe detiene el programa (`E3003`).
  Existe el cero negativo (`-0.0`), que es igual a `0.0`.
- **`Text`**: se escribe entre comillas dobles, en una sola línea. Los escapes son `\n`, `\t`,
  `\"`, `\\` y `\{`. Una llave `{` sin escapar es un error: está reservada.
- Un literal numérico no lleva signo: `-5` es el operador `-` aplicado a `5`.

## Inferencia y anotaciones

Sin anotación, una variable toma el tipo de su valor:

<!-- nex:body -->
```nex
let name = "NEXORA"      // Text
let age = 25             // Int
let price = 19.99        // Float
let active = true        // Bool
```

Con anotación, el valor tiene que ser **exactamente** de ese tipo:

<!-- nex:body -->
```nex
let name: Text = "NEXORA"
let age: Int = 25
let price: Float = 19.99
let active: Bool = true
```

Si no lo es, el error señala el valor:

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let price: Float = 5
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:24
  |
2 |     let price: Float = 5
  |                        ^ Expected Float, found Int
  = note: 'price' is declared as Float.
  = hint: Convert the Int explicitly with to_float(...).

error: program.nex: check failed with 1 error
```

La sugerencia (`hint`) aparece porque existe una conversión de `Int` a `Float`. Cuando no existe
ninguna conversión entre los dos tipos, no se sugiere nada.

## La regla de compatibilidad

**Dos tipos son compatibles solo si son el mismo tipo.** No hay excepciones: no hay tipos
"más amplios" ni conversiones automáticas.

La regla se aplica en los cuatro lugares donde un valor tiene que tener un tipo concreto:

| Lugar | Ejemplo incorrecto |
|-------|--------------------|
| La anotación de una variable | `let n: Int = 2.0` |
| Un argumento de una llamada | `half(4)` si `half` espera un `Float` |
| El valor de un `return` | `return "x"` en una función `-> Int` |
| Los operandos de un operador | `1 + 1.5` |

## Operadores

| Operadores | Operandos | Resultado |
|------------|-----------|-----------|
| `+`  `-`  `*`  `/` | Dos `Int` o dos `Float` | El mismo tipo |
| `+` | Dos `Text` | `Text` (los une) |
| `-x` | `Int` o `Float` | El mismo tipo |
| `==`  `!=` | Dos valores del mismo tipo | `Bool` |
| `<`  `<=`  `>`  `>=` | Dos `Int` o dos `Float` | `Bool` |
| `and`  `or` | Dos `Bool` | `Bool` |
| `not x` | `Bool` | `Bool` |

La precedencia, de mayor a menor: `-x` y `not`; `*` y `/`; `+` y `-`; comparaciones; `and`; `or`.
Los paréntesis agrupan.

<!-- nex:run -->
```nex
fn main() -> Void {
    print(2 + 3 * 4)                    // 14: '*' antes que '+'
    print((2 + 3) * 4)                  // 20
    print(7 / 2)                        // 3: Int / Int es Int
    print(7.0 / 2.0)                    // 3.5
    print("Nex" + "ora")
    print(3 > 2 and not (1 == 2))
    print(true or false and false)      // 'and' antes que 'or'
}
```

```text
14
20
3
3.5
Nexora
true
true
```

Cosas que conviene saber:

- **División entre enteros.** `Int / Int` devuelve un `Int` y descarta los decimales, redondeando
  hacia cero: `7 / 2` es `3` y `-7 / 2` es `-3`. Para obtener decimales, divide dos `Float`.
- **Comparaciones.** No se encadenan: `a < b < c` es un error de sintaxis. Se escribe
  `a < b and b < c`.
- **`not`** se aplica antes que las comparaciones: `not a == b` significa `(not a) == b`. Para
  negar una comparación escribe `not (a == b)` o `a != b`.
- **`and` y `or`** no evalúan su lado derecho si el izquierdo ya decide el resultado.
- **Textos.** Solo admiten `+`, `==` y `!=`. No se pueden ordenar con `<`.

## Casos inválidos

Cada una de estas líneas es un error de tipos (`E2011`), detectado sin ejecutar:

<!-- nex:body-fails codes=E2011 -->
```nex
let a = 10 + 2.5           // Int y Float no se mezclan
let b = 1 == 1.0           // tampoco al comparar
let c = true + 1           // un Bool no admite aritmética
let d = true < false       // ni orden
let e = "a" + 1            // '+' une Text con Text
let f = "a" < "b"          // los textos no se ordenan
let g = 1 and 2            // 'and' necesita dos Bool
let h = not 0              // 'not' necesita un Bool
let i = -"text"            // '-' necesita un número
```

Una condición tiene que ser un `Bool`; un número no vale:

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let count = 3
    if count {
        print("some")
    }
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:3:8
  |
3 |     if count {
  |        ^^^^^ The condition of 'if' must be Bool, found Int
  = hint: A number is not a condition. Compare it explicitly, for example: x != 0

error: program.nex: check failed with 1 error
```

Usar un nombre que no es un tipo, o `Void` donde hace falta un tipo de valor, es el error `E2012`:

<!-- nex:body-fails codes=E2012 -->
```nex
let a: String = "x"        // el tipo de texto se llama Text
let b: Void = 1            // una variable no puede ser Void
```

## Conversiones

Las únicas conversiones son llamadas a estas tres funciones:

| Función | De | A | Regla |
|---------|----|---|-------|
| `to_float(value)` | `Int` | `Float` | Siempre posible. Los enteros de más de 53 bits se redondean al `Float` más cercano |
| `to_int(value)` | `Float` | `Int` | Descarta los decimales (redondea hacia cero). Si el resultado no cabe en un `Int`, error de ejecución `E3005` |
| `to_text(value)` | `Int`, `Float`, `Bool` o `Text` | `Text` | El mismo texto que escribiría `print` |

<!-- nex:run -->
```nex
fn main() -> Void {
    print(to_float(7) / 2.0)
    print(to_int(3.9))
    print(to_int(-3.9))
    print("items: " + to_text(42))
    print("ready: " + to_text(true))
    print(to_text(2.0))
}
```

```text
3.5
3
-3
items: 42
ready: true
2.0
```

No existe ninguna conversión de `Text` a número, ni entre `Bool` y los números.

Cada función de conversión acepta solo su tipo de origen:

<!-- nex:body-fails codes=E2011 -->
```nex
let a = to_float(1.5)      // espera un Int
let b = to_int(1)          // espera un Float
let c = to_int("12")       // no hay conversión desde Text
```

## `Void`

`Void` significa "ningún valor". Una llamada a una función `Void` no puede usarse donde hace falta
un valor:

<!-- nex:body-fails codes=E2011 -->
```nex
let nothing = print("x")           // no hay valor que guardar
print(print("x"))                  // ni que pasar como argumento
```

## Lo que se comprueba al ejecutar

El sistema de tipos garantiza que cada operación recibe valores del tipo correcto. No puede
garantizar nada que dependa del **valor** concreto. Estas situaciones se detectan al ejecutar:

| Situación | Error |
|-----------|-------|
| División por cero | `E3001` |
| Resultado `Int` fuera de rango | `E3002` |
| Resultado `Float` demasiado grande | `E3003` |
| `to_int` de un `Float` que no cabe en un `Int` | `E3005` |

<!-- nex:fails exit=3 -->
```nex
fn main() -> Void {
    let largest = 9223372036854775807
    print(largest)
    print(largest + 1)
}
```

```text
9223372036854775807
runtime error[E3002]: Integer overflow
 --> program.nex:4:11
  |
4 |     print(largest + 1)
  |           ^^^^^^^^^^^ The result of this operation does not fit in an Int
  = hint: Int holds whole numbers from -9223372036854775808 to 9223372036854775807.

error: program.nex: the program stopped because of a runtime error
```

## Lo que no existe

Listas, registros, valores opcionales, tipos definidos por el usuario, genéricos y cualquier otro
tipo compuesto. Están en la [hoja de ruta](roadmap.md) como trabajo previsto, y no funcionan hoy.
