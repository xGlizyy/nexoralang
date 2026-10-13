# Contratos — experimental

> **Estado: experimental.** Los contratos están implementados y probados, pero su sintaxis y sus
> reglas pueden cambiar de forma incompatible en versiones futuras. No forman parte de la guía de
> [primeros pasos](getting-started.md).

Un contrato es una condición que una función declara como parte de sí misma:

- **`requires`**: lo que la función **espera** de quien la llama (condición previa).
- **`ensures`**: lo que la función **promete** al terminar (condición posterior).

Los contratos se evalúan con las reglas normales del lenguaje. Son deterministas y no interviene
ningún modelo de IA.

La definición formal está en la [especificación](language-spec.md#9-contratos--experimental). Todos
los ejemplos de esta página se comprueban en las pruebas del proyecto.

## Un ejemplo

<!-- nex:run -->
```nex
fn divide(a: Float, b: Float) -> Float {
    requires b != 0.0
    return a / b
}

fn absolute(value: Int) -> Int {
    ensures result >= 0
    if value < 0 {
        return -value
    }
    return value
}

fn main() -> Void {
    print(divide(9.0, 2.0))
    print(absolute(-42))
}
```

```text
4.5
42
```

## Reglas

- Las cláusulas van **al principio del cuerpo**, una por línea, antes de cualquier sentencia.
  Puede haber varias de cada tipo.
- La condición tiene que ser de tipo `Bool`.
- En `requires` solo son visibles **los parámetros** de la función.
- En `ensures` son visibles los parámetros y **`result`**, que es el valor devuelto por la función
  y tiene su tipo de retorno. En una función `Void` no existe `result`.
- Los parámetros no cambian de valor, así que en `ensures` valen lo mismo que al entrar.
- Una condición puede llamar a funciones.
- `result` solo tiene este significado dentro de `ensures`. En el cuerpo es un nombre corriente.
  Un parámetro no puede llamarse `result`.

## Cuándo se comprueba cada cosa

| Momento | Qué se comprueba |
|---------|------------------|
| Sin ejecutar (`nex check`) | Que la condición esté bien escrita: nombres visibles, tipos correctos, resultado `Bool` |
| Al ejecutar, en **cada** llamada | `requires`: después de recibir los argumentos y **antes** de ejecutar el cuerpo |
| Al ejecutar, en **cada** llamada | `ensures`: **después** de calcular el valor de retorno |

`nex check` rechaza una condición mal tipada sin ejecutar nada:

<!-- nex:check-fails -->
```nex
fn half(n: Int) -> Int {
    requires n
    ensures result == "small"
    return n / 2
}

fn main() -> Void {
    print(half(8))
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:2:14
  |
2 |     requires n
  |              ^ The condition of 'requires' must be Bool, found Int
  = hint: A number is not a condition. Compare it explicitly, for example: x != 0

type error[E2011]: Type mismatch
 --> program.nex:3:20
  |
3 |     ensures result == "small"
  |                    ^^ Cannot apply '==' to Int and Text
  = hint: Both sides of '==' must have the same type.

error: program.nex: check failed with 2 errors
```

## Cuando `requires` no se cumple

El programa se detiene **antes** de ejecutar el cuerpo de la función. El diagnóstico señala **la
llamada**, porque quien llama es quien incumple, y muestra la condición y los valores recibidos:

<!-- nex:fails exit=5 -->
```nex
fn divide(a: Float, b: Float) -> Float {
    requires b != 0.0
    return a / b
}

fn average(total: Float, count: Float) -> Float {
    return divide(total, count)
}

fn main() -> Void {
    print(average(90.0, 4.0))
    print(average(90.0, 0.0))
}
```

```text
22.5
contract error[E4001]: Precondition violated
 --> program.nex:7:12
  |
7 |     return divide(total, count)
  |            ^^^^^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'divide'
  = note: The condition at line 2 is false: requires b != 0.0
  = note: It was called with: a = 90.0, b = 0.0
  = note: In 'average', called at line 12, column 11.

error: program.nex: the program stopped because a contract was broken
```

Sin el contrato, el mismo programa fallaría con una división por cero dentro de `divide`. Con él,
el error dice qué regla se incumplió y desde dónde.

## Cuando `ensures` no se cumple

El diagnóstico señala **la cláusula**, porque es la función la que no cumple lo que promete, y
muestra el valor devuelto:

<!-- nex:fails exit=5 -->
```nex
fn discount(price: Int, percent: Int) -> Int {
    requires percent >= 0
    ensures result <= price
    return price * (100 + percent) / 100
}

fn main() -> Void {
    print(discount(200, 0))
    print(discount(200, 25))
}
```

```text
200
contract error[E4002]: Postcondition violated
 --> program.nex:3:5
  |
3 |     ensures result <= price
  |     ^^^^^^^^^^^^^^^^^^^^^^^ 'discount' breaks its own 'ensures' condition
  = note: 'discount' finished, but its condition is false: ensures result <= price
  = note: It returned: result = 250
  = note: It was called with: price = 200, percent = 25
  = note: In 'discount', called at line 9, column 11.

error: program.nex: the program stopped because a contract was broken
```

Aquí el contrato ha encontrado un fallo real del cuerpo: suma el porcentaje en vez de restarlo.

## Códigos y salida

| Situación | Código | Categoría | `nex run` termina con |
|-----------|--------|-----------|-----------------------|
| Condición `requires` falsa | `E4001` | `contract` | `5` |
| Condición `ensures` falsa | `E4002` | `contract` | `5` |
| Condición mal tipada | `E2011` | `type` | `1` (no se ejecuta) |
| Cláusula fuera del principio del cuerpo | `E1106` | `syntax` | `1` (no se ejecuta) |

Si evaluar la condición produce por sí mismo un error (por ejemplo, una división por cero dentro
de la condición), el error comunicado es ese (`runtime`, código de salida `3`), no una violación
de contrato.

## Limitaciones

Lo que los contratos **no** hacen. Es importante no atribuirles más garantías de las que tienen:

- **No se demuestran.** `nex check` comprueba que una condición está bien escrita, no que se
  cumpla. Un programa que supera `nex check` puede incumplir un contrato al ejecutarse.
- **Solo se comprueban las llamadas que se ejecutan.** Que un programa termine sin violaciones
  significa que esa ejecución, con esos valores, cumplió los contratos. No dice nada sobre otros
  valores.
- **Una condición imposible de cumplir se acepta.** `requires n > 0 and n < 0` supera `nex check`;
  la violación aparece en la primera llamada.
- **No se comprueba que las condiciones carezcan de efectos.** Una condición puede llamar a una
  función que use `print`.
- **No se pueden desactivar.** Se comprueban siempre, y cada comprobación tiene un coste de
  ejecución.
- No hay invariantes, contratos sobre tipos ni condiciones sobre valores "antes" y "después":
  no hacen falta mientras todos los valores sean inmutables.

## Por qué existen

NEXORA explora si hacer explícita la intención de una función, en una forma que una máquina puede
evaluar, ayuda a las personas y a las herramientas a entender y validar el código. Los contratos
son un primer experimento en esa dirección. Que esa ayuda sea real, y cuánta, **no se ha medido**:
es una hipótesis de trabajo, no un resultado.

Las decisiones de diseño y sus alternativas están en
[`decisions/0004`](decisions/0004-contratos-en-ejecucion.md).
