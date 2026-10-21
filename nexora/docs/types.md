# Tipos

NEXORA tiene un sistema de tipos **estático**: el tipo de cada expresión se conoce sin ejecutar el
programa, y todos los errores de tipos los detecta `nex check`. Ningún error de tipos puede
aparecer mientras el programa se ejecuta.

La definición formal está en la [especificación](language-spec.md#4-tipos-de-datos). Esta guía la
explica con ejemplos; todos se comprueban en las pruebas del proyecto.

## Los tipos

| Tipo | Valores | Literales |
|------|---------|-----------|
| `Int` | Enteros de 64 bits con signo: de `-9223372036854775808` a `9223372036854775807` | `0`, `42`, `1_000_000` |
| `Float` | Coma flotante IEEE 754 de 64 bits | `3.14`, `0.5`, `10.0` |
| `Bool` | Verdadero o falso | `true`, `false` |
| `Text` | Texto Unicode, inmutable | `"Hello"` |
| `List[T]` | Secuencia inmutable y finita de valores de tipo `T` | `[1, 2, 3]`, `[]` (con un tipo esperado) |
| `Void` | Ningún valor | No tiene literales |

`Int`, `Float`, `Bool` y `Text` son los **tipos de valor** integrados. `List[T]` es un tipo de valor
compuesto, y un programa puede declarar tipos refinados sobre los integrados. `Void` solo puede
usarse como tipo de retorno de una función que no devuelve nada.

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

**Dos tipos son compatibles solo si son el mismo tipo, o si el valor es de un tipo refinado y se
espera su base.** No hay tipos numéricos "más anchos" ni conversiones automáticas:

- Un `Int` no se acepta donde se espera un `Float`, ni al revés.
- Ningún tipo se convierte a `Bool` ni a `Text` por sí solo.
- Un `Percent` (refinado sobre `Int`) se acepta donde se espera un `Int`; la dirección contraria
  exige construir el refinado.
- Los argumentos de `List` son invariantes: `List[Percent]` no se acepta donde se espera
  `List[Int]`, aunque cada `Percent` sea un `Int`.

La regla se aplica en los cuatro lugares donde un valor tiene que tener un tipo concreto:

| Lugar | Ejemplo incorrecto |
|-------|--------------------|
| La anotación de una variable | `let n: Int = 2.0` |
| Un argumento de una llamada | `half(4)` si `half` espera un `Float` |
| El valor de un `return` | `return "x"` en una función `-> Int` |
| Los operandos de un operador | `1 + 1.5` |

## Listas

Una lista es una secuencia **inmutable y finita** de valores del mismo tipo. Se escribe `List[T]`,
donde `T` es el tipo de sus elementos:

```nex
let numbers: List[Int] = [1, 2, 3]
let empty: List[Int] = []
let nested: List[List[Int]] = [[1], [2, 3]]
let words: List[Text] = ["a", "b"]
```

`T` puede ser `Int`, `Float`, `Bool`, `Text`, un tipo refinado u otra `List[...]`; no puede ser
`Void`. Los argumentos de `List` son **invariantes**: `List[Int]` y `List[Text]` son tipos
distintos, y `List[Percent]` no se acepta donde se espera `List[Int]`. Un elemento refinado sí
puede ensancharse a su base al construir la lista con un tipo esperado:
`let xs: List[Int] = [Percent(10), 20]`.

Sin un tipo esperado, el primer elemento fija el tipo de los demás. Una lista vacía necesita un
tipo esperado (una anotación, un parámetro, un retorno, una asignación o el lado izquierdo de una
igualdad, como `a == []`); `let xs = []` es `E2011`. El tipo no se propaga del lado derecho al
izquierdo de una igualdad: `[] == a` es `E2011`. Todos los elementos tienen que ser del mismo tipo:
`let xs = [1, "a"]` es `E2011`.

<!-- nex:run -->
```nex
fn main() -> Void {
    let xs = [1, 2, 3]
    print(xs)
    print(List.length(xs))
    print(List.get(xs, 1))
    print(List.append(xs, 4))
    print(List.contains(xs, 2))
    var total = 0
    for x in xs {
        total = total + x
    }
    print(total)
}
```

```text
[1, 2, 3]
3
2
[1, 2, 3, 4]
true
6
```

Una lista no cambia: `List.append` y `List.concat` construyen listas nuevas. `print` y `to_text`
escriben `[1, 2, 3]`, y `==`/`!=` comparan listas del mismo tipo de forma estructural. No hay
sintaxis de índice (`xs[i]`), mutación de elementos ni orden entre listas. Para leer una posición se
usa `List.get`, que exige un índice válido y detiene el programa con `E4001` si no lo es. Las cinco
funciones y el `for` están en la [especificación](language-spec.md), secciones 8.2 y 9.6.

No se puede refinar una lista en esta versión (`type NonEmpty = List[Int] ...` es `E2016`).

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
- **Textos.** Admiten `+`, `==`, `!=` y el orden (`<`, `<=`, `>`, `>=`) entre dos textos, carácter
  a carácter por punto de código Unicode: `"Z" < "a"` y `"10" < "9"` son verdaderos. Sus funciones
  (`Text.length`, `Text.slice`…) y la lectura de números (`Int.parse`, `Float.parse`) están en la
  [especificación](language-spec.md), sección 8.1.

## Casos inválidos

Cada una de estas líneas es un error de tipos (`E2011`), detectado sin ejecutar:

<!-- nex:body-fails codes=E2011 -->
```nex
let a = 10 + 2.5           // Int y Float no se mezclan
let b = 1 == 1.0           // tampoco al comparar
let c = true + 1           // un Bool no admite aritmética
let d = true < false       // ni orden
let e = "a" + 1            // '+' une Text con Text
let f = [1] == ["a"]       // las listas comparan elementos del mismo tipo
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
| `to_text(value)` | `Int`, `Float`, `Bool`, `Text` o `List[T]` | `Text` | El mismo texto que escribiría `print` |

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
| `List.get` con un índice fuera de la lista | `E4001` |
| `Percent(x)` con un valor que no cumple la condición de `Percent` | `E4003` |

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

## Tipos refinados

Un tipo refinado es un tipo de valor con una regla que cumplen todos sus valores:

<!-- nex:run -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
type Cents = Int where value >= 0, "An amount of money cannot be negative"

fn apply_discount(price: Cents, percent: Percent) -> Cents {
    ensures result <= price, "A discount never raises the price"
    return Cents(price * (100 - percent) / 100)
}

fn main() -> Void {
    print(apply_discount(2000, 15))
}
```

```text
1700
```

- `type Percent = Int where ...` declara el tipo: su **base** (`Int`) y su **condición**, en la que
  `value` es el valor que se comprueba. Tras una coma puede ir la explicación de la regla.
- Las firmas dicen ahora más que antes: `apply_discount` no acepta cualquier `Int` como porcentaje,
  y quien la llama lo ve sin leer el cuerpo.
- **Todo valor de tipo `Percent` cumple la condición de `Percent`.** Esa es la garantía, y se
  mantiene en todo el programa.

### Cómo entra un valor en un tipo refinado

Solo hay dos formas, y las dos están escritas en el código:

1. **Una constante.** `apply_discount(2000, 15)` pasa el literal `15` donde se espera un
   `Percent`. `nex check` evalúa la condición con ese valor **sin ejecutar el programa**, y si no se
   cumple el programa no llega a ejecutarse:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() -> Void {
    let discount: Percent = 150
    print(discount)
}
```

```text
type error[E2017]: Value outside refined type
 --> program.nex:4:29
  |
4 |     let discount: Percent = 150
  |                             ^^^ 150 is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 150
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: check failed with 1 error
```

2. **La comprobación explícita `Percent(x)`** para cualquier valor calculado. Se hace al ejecutar,
   y si la condición no se cumple el programa se detiene en esa línea (`E4003`, código de salida
   `5`). En el ejemplo de arriba, `Cents(...)` comprueba que el precio rebajado no es negativo.

Un valor calculado sin comprobar no se acepta donde se espera un tipo refinado, aunque su tipo sea
la base:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100

fn main() -> Void {
    let half = 100 / 2
    let discount: Percent = half
    print(discount)
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:5:29
  |
5 |     let discount: Percent = half
  |                             ^^^^ Expected Percent, found Int
  = note: 'discount' is declared as Percent.
  = hint: Check the value explicitly with Percent(...). The program stops there if the value does not satisfy the condition of Percent.

error: program.nex: check failed with 1 error
```

La razón es la misma que la de las [conversiones](#conversiones): nada cambia de tipo sin que el
código lo diga. Cada punto donde una regla puede detener el programa es una llamada `Percent(...)`
que se ve y se puede buscar.

### Usar valores refinados

- Un `Percent` se acepta en cualquier lugar donde se espera un `Int`: es un `Int` que además cumple
  una regla.
- Una operación con valores refinados da un valor de la base: `discount + 10` es un `Int`, porque
  puede valer 110.
- Dos tipos refinados diferentes son tipos diferentes, aunque tengan la misma base.
- Un tipo puede refinar otro tipo refinado: `type Pass = Percent where value >= 50` exige las dos
  condiciones.

### Lo que la condición puede usar

Solo `value`, literales, operadores y las conversiones integradas (`to_float`, `to_int`,
`to_text`). No puede llamar a funciones del programa (`E2018`): un tipo refinado describe un valor
por sí mismo. Una regla que depende de otros datos ("el descuento no puede superar el precio") es
una relación entre argumentos y se escribe como [contrato](contracts.md).

### Errores de los tipos refinados

| Situación | Código | Cuándo |
|-----------|--------|--------|
| Nombre en minúscula, repetido, de un tipo integrado o cadena de tipos sin fin | `E2016` | Sin ejecutar |
| Condición que no es `Bool`, o que usa otro nombre que `value` | `E2011`, `E2005` | Sin ejecutar |
| Condición que llama a una función del programa | `E2018` | Sin ejecutar |
| Constante que no cumple la condición | `E2017` | Sin ejecutar |
| Demasiadas constantes que comprobar (límite de trabajo del análisis) | `E2019` | Sin ejecutar |
| Valor calculado usado sin `Percent(...)` | `E2011` | Sin ejecutar |
| `Percent(x)` con un valor que no cumple la condición | `E4003` | Al ejecutar |

## Lo que no existe

Registros, mapas, enumeraciones, valores opcionales (`Option`, `Result`), alias de tipos sin
condición, genéricos de usuario y cualquier otro tipo compuesto que no sea `List[T]`. Las listas no
tienen sintaxis de índice ni mutación, y no se pueden refinar. Están en la
[hoja de ruta](roadmap.md) como trabajo previsto, y no funcionan hoy.
