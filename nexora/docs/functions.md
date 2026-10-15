# Funciones

La definición formal está en la [especificación](language-spec.md#7-funciones). Esta guía la
explica con ejemplos; todos se comprueban en las pruebas del proyecto.

## Declarar una función

```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}
```

| Parte | Regla |
|-------|-------|
| `fn add` | El nombre. No puede repetirse ni coincidir con el de una función integrada |
| `(a: Int, b: Int)` | Los parámetros. Cada uno declara su tipo, que tiene que ser un tipo de valor |
| `-> Int` | El tipo de retorno. Se escribe siempre; `Void` si la función no devuelve nada |
| `{ ... }` | El cuerpo |

Las funciones se declaran en el nivel superior del archivo, en cualquier orden: una función puede
llamar a otra declarada más abajo. No se pueden declarar funciones dentro de otras funciones.

## La función `main`

Todo programa tiene una función `main`, sin parámetros y con tipo de retorno `Void`. Es donde
empieza la ejecución.

<!-- nex:run -->
```nex
fn main() -> Void {
    print(square(7))
}

fn square(n: Int) -> Int {
    return n * n
}
```

```text
49
```

## Llamar a una función

Los argumentos se asignan a los parámetros por posición. Antes de ejecutar el programa se
comprueba que la función existe, que el número de argumentos coincide y que cada argumento tiene
el tipo de su parámetro.

<!-- nex:check-fails -->
```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn main() -> Void {
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
  = note: Its signature is: fn add(a: Int, b: Int) -> Int

type error[E2011]: Type mismatch
 --> program.nex:7:18
  |
7 |     print(add(1, "2"))
  |                  ^^^ Expected Int, found Text
  = note: This is the argument for 'b' in: fn add(a: Int, b: Int) -> Int

semantic error[E2008]: Unknown function
 --> program.nex:8:11
  |
8 |     print(ad(1, 2))
  |           ^^ There is no function named 'ad'
  = hint: Did you mean 'add'?

error: program.nex: check failed with 3 errors
```

Al ejecutarse, una llamada evalúa sus argumentos de izquierda a derecha, crea un ámbito nuevo con
los parámetros, ejecuta el cuerpo y devuelve el valor al punto de la llamada.

Una función **no ve las variables de quien la llama**: solo sus parámetros y lo que declare en su
cuerpo. No existen variables globales. Los parámetros, como las variables, no pueden cambiar de valor.

## Devolver un valor

En una función que devuelve un valor, `return` va seguido de una expresión del tipo declarado:

<!-- nex:check-fails -->
```nex
fn label(count: Int) -> Text {
    return count
}

fn main() -> Void {
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

El valor devuelto **no puede ignorarse**. Llamar a una función que devuelve algo y no usar el
resultado es un error (`E2010`):

<!-- nex:check-fails -->
```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn main() -> Void {
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

## Funciones `Void`

Una función `Void` no devuelve ningún valor. Termina al llegar al final del cuerpo, o antes con un
`return` sin valor:

<!-- nex:run -->
```nex
fn report(score: Int) -> Void {
    if score < 0 {
        print("invalid score")
        return
    }
    print("score: " + to_text(score))
}

fn main() -> Void {
    report(-1)
    report(80)
}
```

```text
invalid score
score: 80
```

Una llamada a una función `Void` es una sentencia: no puede guardarse en una variable, imprimirse
ni pasarse como argumento. En una función `Void`, `return` seguido de un valor es un error (`E2011`).

## `if` y `else`

`if` es una sentencia. La condición tiene que ser de tipo `Bool`. `else` y `else if` se escriben en
la misma línea que la `}` anterior.

<!-- nex:run -->
```nex
fn sign(n: Int) -> Int {
    if n < 0 {
        return -1
    } else if n == 0 {
        return 0
    } else {
        return 1
    }
}

fn main() -> Void {
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

Cada bloque (`{ }`) tiene su propio ámbito: una variable declarada dentro de un `if` deja de
existir al cerrarse su bloque.

## Toda ruta devuelve

Una función que devuelve un valor tiene que terminar con `return` por **todos** los caminos
posibles. Si alguno puede llegar al final del cuerpo, el programa se rechaza antes de ejecutarse:

<!-- nex:check-fails -->
```nex
fn sign(n: Int) -> Int {
    if n < 0 {
        return -1
    } else if n > 0 {
        return 1
    }
}

fn main() -> Void {
    print(sign(0))
}
```

```text
semantic error[E2014]: Missing return
 --> program.nex:1:4
  |
1 | fn sign(n: Int) -> Int {
  |    ^^^^ 'sign' must return a value of type Int, but its body can end without a 'return'
  = hint: Make sure every path through the function ends with 'return'. An 'if' without 'else' can be skipped, and a loop may not run at all.

error: program.nex: check failed with 1 error
```

Cómo se decide si un bloque devuelve siempre:

| Sentencia | Siempre devuelve si… |
|-----------|----------------------|
| `return` | Siempre |
| `if` sin `else` final | Nunca: la condición puede ser falsa |
| `if` … `else` … | Todas sus ramas siempre devuelven |
| Un bloque `{ }` | Alguna de sus sentencias siempre devuelve |

El análisis mira la estructura, no los valores: `if true { return 1 }` sin `else` también se rechaza.

El código situado después de un `return`, en el mismo bloque, no puede ejecutarse nunca y es un
error (`E2015`).

## Recursividad

Una función puede llamarse a sí misma, y dos funciones pueden llamarse entre sí. Para repetir algo
muchas veces es mejor un bucle `while` ([contratos](contracts.md#bucles-invariant-y-decreases)): sus
vueltas no son llamadas y no tienen el límite de 1000.

<!-- nex:run -->
```nex
fn factorial(n: Int) -> Int {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}

fn countdown(n: Int) -> Void {
    if n == 0 {
        print("liftoff")
        return
    }
    print(n)
    countdown(n - 1)
}

fn main() -> Void {
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

**Límite:** un programa puede tener como máximo 1000 llamadas anidadas (contando `main`). Una
recursividad que no alcanza su caso base se detiene con un error de ejecución:

<!-- nex:fails exit=3 -->
```nex
fn forever(n: Int) -> Int {
    return forever(n + 1)
}

fn main() -> Void {
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

Si las llamadas recursivas están dentro de expresiones muy anidadas, el programa puede quedarse
sin espacio de pila antes de llegar a las 1000 llamadas. El error es el mismo (`E3004`) y el
mensaje indica cuántas llamadas había.

## Nombres

Funciones, parámetros y variables comparten un único espacio de nombres, y un nombre visible no se
declara dos veces. En consecuencia:

<!-- nex:check-fails -->
```nex
fn area(width: Int, width: Int) -> Int {
    let area = width * width
    return area
}

fn main() -> Void {
    print(area(2, 3))
}
```

```text
semantic error[E2006]: Name already declared
 --> program.nex:1:21
  |
1 | fn area(width: Int, width: Int) -> Int {
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

## Restricciones de esta versión

- No hay valores por defecto ni argumentos con nombre.
- No hay sobrecarga: dos funciones no pueden llamarse igual.
- Las funciones no son valores: no se pueden guardar en variables ni pasar como argumentos.
- No hay funciones anónimas, genéricos, métodos ni clases.
- Un parámetro no puede llamarse `result` (ese nombre se usa en los [contratos](contracts.md)).
- No se admite una coma final en las listas de parámetros o de argumentos.
- `main` no recibe argumentos de la línea de comandos.
