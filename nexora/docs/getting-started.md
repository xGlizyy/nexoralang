# Primeros pasos

Esta guía te lleva desde un archivo vacío hasta un programa con variables, tipos y funciones.
Solo usa características estables del lenguaje. Necesitas tener NEXORA [instalado](installation.md)
y el entorno virtual activado.

Todos los programas de esta página, y las salidas que se muestran, se comprueban en las pruebas
automatizadas del proyecto.

## 1. Tu primer programa

Crea un archivo de texto llamado `program.nex` con este contenido:

<!-- nex:run -->
```nex
fn main() -> Void {
    print("Hello from NEXORA")
}
```

Ejecútalo:

```bash
nex run program.nex
```

Verás:

```text
Hello from NEXORA
```

Qué significa cada parte:

- `fn main() -> Void { ... }` declara la función `main`. Todo programa empieza a ejecutarse por
  ella. `Void` indica que no devuelve ningún valor.
- `print(...)` escribe un valor en pantalla, seguido de un salto de línea.
- Las sentencias terminan al acabar la línea. No se usa punto y coma.
- Los archivos de NEXORA tienen la extensión `.nex` y se guardan como texto UTF-8.

## 2. Comprobar sin ejecutar

`nex check` analiza el programa y avisa de sus errores **sin ejecutarlo**:

```bash
nex check program.nex
```

```text
✓ Check passed: program.nex
```

`nex run` hace esa misma comprobación antes de empezar: un programa con errores nunca llega a
ejecutarse. `nex check` es útil mientras escribes, porque no produce ningún efecto.

## 3. Variables

`let` declara una variable y le da un valor:

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

Dos reglas importantes:

- **Las variables no cambian.** Una vez declarada, una variable conserva su valor. Si necesitas
  otro valor, declara otra variable.
- **Un nombre solo se declara una vez.** No puedes declarar dos variables con el mismo nombre si
  la primera sigue siendo visible.

Los comentarios empiezan con `//` y llegan hasta el final de la línea.

## 4. Tipos

Cada valor tiene un tipo. Hay cuatro tipos de valor:

| Tipo | Qué contiene | Ejemplos |
|------|--------------|----------|
| `Int` | Números enteros | `42`, `-7`, `1_000_000` |
| `Float` | Números con decimales | `3.14`, `0.5`, `10.0` |
| `Bool` | Verdadero o falso | `true`, `false` |
| `Text` | Texto | `"Hello"` |

NEXORA deduce el tipo de una variable a partir de su valor. También puedes escribirlo tú, y
entonces el lenguaje comprueba que el valor es de ese tipo:

<!-- nex:run -->
```nex
fn main() -> Void {
    let title = "Analytical Engine"      // Text, deducido
    let pages: Int = 25                  // Int, escrito
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

NEXORA **nunca convierte un tipo en otro por su cuenta**. Un entero y un decimal no se pueden
mezclar en una operación, y un número no se une a un texto con `+`. Cuando lo necesites, hay que
decirlo con una función de conversión:

<!-- nex:run -->
```nex
fn main() -> Void {
    let units = 3
    let price = 2.5
    let total = to_float(units) * price          // Int -> Float
    print("Total: " + to_text(total))            // Float -> Text
    print(to_int(total))                         // Float -> Int (descarta los decimales)
}
```

```text
Total: 7.5
7
```

La guía de [tipos](types.md) explica todas las reglas.

## 5. Funciones

Una función recibe valores (parámetros) y puede devolver un resultado. Cada parámetro declara su
tipo, y la función declara el tipo de lo que devuelve:

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

- `return` devuelve el resultado y termina la función.
- Una función que no devuelve nada usa `Void`, como `greet` y `main`.
- Las funciones pueden declararse en cualquier orden.

## 6. Decidir con `if`

`if` ejecuta un bloque solo si una condición es verdadera. `else` indica qué hacer en caso
contrario:

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

La condición tiene que ser un `Bool`: una comparación (`==`, `!=`, `<`, `<=`, `>`, `>=`), una
variable de tipo `Bool`, o una combinación con `and`, `or` y `not`.

La guía de [funciones](functions.md) explica el resto: rutas de retorno, recursividad y límites.

## 7. Leer un error

Cuando algo no es correcto, NEXORA lo explica con un diagnóstico. Este programa tiene un error:

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

Cómo leerlo:

| Parte | Significado |
|-------|-------------|
| `type error` | La clase de problema. Aquí, un error de tipos |
| `[E2011]` | El código del error. Es siempre el mismo para el mismo problema; puedes buscarlo en la [lista de códigos](diagnostics.md#todos-los-códigos) |
| `Type mismatch` | El título del error |
| `program.nex:2:20` | Archivo, línea y columna donde está el problema |
| `^^^^^^^^` | El fragmento exacto que causa el error |
| `Expected Int, found Text` | La explicación concreta |
| `= note:` | Información relacionada |
| `= hint:` | Cuando aparece, una corrección sugerida |

Un error con sugerencia: el nombre está mal escrito y existe uno parecido.

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

Algunos errores no pueden conocerse hasta ejecutar el programa, porque dependen de los valores.
Este programa supera `nex check`, pero falla al ejecutarse:

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

La guía de [diagnósticos](diagnostics.md) explica las categorías y todos los códigos.

## 8. Un programa completo

Con lo visto hasta aquí:

<!-- nex:run -->
```nex
// Calcula la nota media de tres exámenes y decide si se aprueba.

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

## Siguientes pasos

- Más programas, listos para ejecutar: [`examples/`](../examples/README.md).
- Las reglas, una por una: [tipos](types.md) y [funciones](functions.md).
- Escribir las reglas en el código, que es lo que distingue a NEXORA: [contratos](contracts.md)
  (lo que una función espera y promete) y [tipos refinados](types.md#tipos-refinados) (los valores
  que admite un tipo).
- La referencia completa del lenguaje: [especificación](language-spec.md).
- Lo que NEXORA todavía no puede hacer (bucles, listas, leer datos…): [limitaciones](limitations.md).
