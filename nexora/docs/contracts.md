# Contratos

> **Estado: estable desde la versión 0.3.0.** La posición de las cláusulas, el nombre `result` y la
> explicación tras una coma son definitivos ([decisión 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)).

Un contrato es una condición que una función declara como parte de sí misma:

- **`requires`**: lo que la función **espera** de quien la llama (condición previa).
- **`ensures`**: lo que la función **promete** al terminar (condición posterior).

Los contratos se evalúan con las reglas normales del lenguaje. Son deterministas y no interviene
ningún modelo de IA.

La definición formal está en la [especificación](language-spec.md#9-contratos). Todos los ejemplos
de esta página se comprueban en las pruebas del proyecto.

Para las reglas que describen **un valor** y no una llamada ("un porcentaje va de 0 a 100"), NEXORA
tiene [tipos refinados](types.md#tipos-refinados). Los contratos y los tipos refinados se
complementan: un tipo dice qué valores son válidos en cualquier parte del programa, y un contrato
dice qué relación tienen los argumentos y el resultado de una función concreta.

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
- Detrás de la condición puede ir, tras una coma, la **explicación** de la regla (sección
  siguiente).

## La explicación de una regla

Una condición dice *qué* se exige; su explicación dice *por qué*. Se escribe tras una coma, como un
texto:

```text
requires amount <= balance, "An account cannot go below zero"
```

La explicación no cambia lo que se comprueba. Cuando la condición es falsa, aparece en el
diagnóstico como `Reason: ...`, justo después de la condición, y las herramientas la reciben como
dato (`message` en `nex inspect` y en `nex context`). Así, quien incumple la regla, sea una persona
o un agente, no tiene que deducir de dónde sale:

<!-- nex:fails exit=5 -->
```nex
fn withdraw(balance: Int, amount: Int) -> Int {
    requires amount > 0, "A withdrawal moves some money"
    requires amount <= balance, "An account cannot go below zero"
    ensures result >= 0, "The balance after a withdrawal is never negative"
    return balance - amount
}

fn main() -> Void {
    print(withdraw(100, 30))
    print(withdraw(100, 300))
}
```

```text
70
contract error[E4001]: Precondition violated
  --> program.nex:10:11
   |
10 |     print(withdraw(100, 300))
   |           ^^^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'withdraw'
   = note: The condition at line 3 is false: requires amount <= balance
   = note: Reason: An account cannot go below zero
   = note: It was called with: balance = 100, amount = 300

error: program.nex: the program stopped because a contract was broken
```

Es opcional. Conviene escribirla cuando la condición no se explica sola: `requires b != 0.0` no la
necesita; `requires amount <= balance` sí, porque la regla es del negocio, no de la aritmética. Es
una sola frase: un texto vacío o con un salto de línea es un error (`E1101`).

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

### Las funciones del lenguaje también tienen `requires`

Las funciones de un tipo que no siempre tienen respuesta (`Text.slice`, `Int.parse`,
`Float.parse`) declaran sus `requires` en NEXORA, con su explicación, y fallan con el mismo `E4001`
([especificación](language-spec.md), sección 8.1). Quien llama puede trasladar el requisito a su
propia función:

<!-- nex:run -->
```nex
fn quantity(written: Text) -> Int {
    requires Int.can_parse(written), "The quantity has to be written as a whole number"
    return Int.parse(written)
}

fn main() -> Void {
    print(quantity("12") * 2)
}
```

```text
24
```

`nex symbols` muestra los requisitos de cada función integrada en su campo `contracts`, así que una
herramienta sabe antes de ejecutar nada que `Int.parse` exige `Int.can_parse`.

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

## Ejemplos (`example`)

Un contrato dice qué relación cumplen siempre la entrada y la salida. Un **ejemplo** dice qué resultado
concreto da la función con unas entradas concretas. Se escribe junto a los contratos, con la misma
forma, y lo evalúa `nex test` ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)):

<!-- nex:test exit=0 -->
```nex
fn double(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    example double(2) == 4, "Two doubled"
    example double(double(1)) == 4
    return n * 2
}
```

```text
program.nex: 2 examples in 1 function
  double   2 passed
✓ 2 examples passed: program.nex
```

- La expresión es `Bool` y tiene que llamar a su propia función, escrita en la propia expresión
  (`E2020` si no lo hace). No ve los parámetros ni `result`: las entradas y el resultado se escriben
  como valores.
- `nex check` y las demás herramientas de análisis **nunca** evalúan un ejemplo. `nex run` los
  ignora. `nex test` no exige `main` y no lo ejecuta.
- Cada ejemplo se evalúa por separado, comprobando los contratos de todo lo que se ejecuta.

Si un ejemplo resulta falso, `nex test` dice qué devolvió la función y termina con el código `6`:

<!-- nex:test exit=6 -->
```nex
fn double(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    example double(3) == 7, "Three doubled is seven"
    example double(-1) == -2
    return n * 2
}
```

```text
program.nex: 2 examples in 1 function
  double   1 failed, 1 error

test error[E4004]: Example failed
 --> program.nex:3:13
  |
3 |     example double(3) == 7, "Three doubled is seven"
  |             ^^^^^^^^^^^^^^ This example of 'double' is false
  = note: double(3) returned 6
  = note: Reason: Three doubled is seven

contract error[E4001]: Precondition violated
 --> program.nex:4:13
  |
4 |     example double(-1) == -2
  |             ^^^^^^^^^^ This call breaks a 'requires' condition of 'double'
  = note: The condition at line 2 is false: requires n >= 0
  = note: Reason: Only natural numbers
  = note: It was called with: n = -1
  = note: While evaluating example 2 of 'double', at line 4.

error: program.nex: 2 of 2 examples did not pass (1 failed, 1 error)
```

El primer ejemplo es `failed` (`E4004`): la función respondió, pero no lo esperado. El segundo es
`error`: no llegó a responder, porque la llamada incumple el `requires`; conserva el `E4001` y gana
una nota con el ejemplo que lo provocó.

Un archivo sin ejemplos no se da por probado:

<!-- nex:test exit=6 -->
```nex
fn double(n: Int) -> Int {
    return n * 2
}
```

```text
program.nex: no examples to run
error: program.nex: nothing was tested
```

## Bucles: `invariant` y `decreases`

Un bucle `while` declara sus requisitos al principio de su cuerpo, igual que una función
([decisión 0010](decisions/0010-var-y-while.md)):

- **`decreases`** (exactamente una): la **medida**, un `Int` que nunca baja de 0 y que disminuye en
  cada vuelta. Es la razón por la que el bucle termina, escrita en el código.
- **`invariant`** (las que haga falta): una condición que se cumple antes de cada evaluación de la
  condición del bucle; es decir, al llegar, después de cada vuelta y al salir.

<!-- nex:run -->
```nex
fn gcd(a: Int, b: Int) -> Int {
    requires a >= 0 and b >= 0, "Only natural numbers"
    requires a > 0 or b > 0, "gcd(0, 0) is not defined"
    var x = a
    var y = b
    while y != 0 {
        invariant x >= 0 and y >= 0
        decreases y, "The remainder is always smaller than the divisor"
        let remainder = x - x / y * y
        x = y
        y = remainder
    }
    return x
}

fn main() -> Void {
    print(gcd(1071, 462))
}
```

```text
21
```

Las cláusulas ven lo que es visible donde está el bucle, no lo que declara su cuerpo, y llevan su
explicación tras una coma. Un bucle sin `decreases` no supera `nex check` (`E2021`).

El intérprete las comprueba **en cada vuelta**. Un invariante falso es `E4005`; una medida negativa
o que no es menor que en la vuelta anterior es `E4006`. Así, ningún bucle se queda repitiendo para
siempre: o termina, o se detiene y dice en qué vuelta y con qué valores. El diagnóstico lleva la
explicación de la regla, como el de un contrato:

<!-- nex:fails exit=5 -->
```nex
fn average(total: Int, count: Int) -> Int {
    requires count > 0, "There is nothing to average"
    var quotient = 0
    var rest = total
    while rest >= count {
        invariant quotient * count + rest == total, "No unit is lost while dividing"
        decreases rest
        rest = rest - count
        quotient = quotient + 2
    }
    return quotient
}

fn main() -> Void {
    print(average(10, 3))
}
```

```text
contract error[E4005]: Loop invariant violated
 --> program.nex:6:19
  |
6 |         invariant quotient * count + rest == total, "No unit is lost while dividing"
  |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ This condition is false
  = note: The condition at line 6 is false: invariant quotient * count + rest == total
  = note: Reason: No unit is lost while dividing
  = note: After turn 1 of the loop at line 5.
  = note: The values: total = 10, count = 3, quotient = 2, rest = 7
  = note: In 'average', called at line 15, column 11.

error: program.nex: the program stopped because a contract was broken
```

## Códigos y salida

| Situación | Código | Categoría | `nex run` termina con |
|-----------|--------|-----------|-----------------------|
| Condición `requires` falsa | `E4001` | `contract` | `5` |
| Condición `ensures` falsa | `E4002` | `contract` | `5` |
| `invariant` falso en un bucle | `E4005` | `contract` | `5` |
| Medida (`decreases`) que no disminuye o es negativa | `E4006` | `contract` | `5` |
| Bucle sin medida, o con más de una | `E2021` | `semantic` | `1` (no se ejecuta) |
| Condición mal tipada | `E2011` | `type` | `1` (no se ejecuta) |
| Cláusula fuera del principio del cuerpo | `E1106` | `syntax` | `1` (no se ejecuta) |
| Explicación vacía, de más de una línea o que no es un texto | `E1101` | `syntax` | `1` (no se ejecuta) |

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
- No hay condiciones sobre valores "antes" y "después" de una función: los parámetros no cambian,
  así que en `ensures` tienen el valor con el que se llamó. Los invariantes existen solo en los
  bucles. Las reglas sobre los valores de un tipo se escriben con
  [tipos refinados](types.md#tipos-refinados).
- **Una medida garantiza que el bucle termina, no que termine pronto.** Una medida inicial de mil
  millones permite mil millones de vueltas.

## Por qué existen

Los requisitos de una función forman parte verificable del programa: esa es la característica que
distingue a NEXORA ([decisión 0006](decisions/0006-requisitos-verificables.md)). Un requisito que
solo está en una instrucción en lenguaje natural no lo comprueba nadie y se pierde en la siguiente
edición; escrito como contrato, se comprueba en cada llamada y dice quién lo incumplió.

Que eso ayude de verdad a las personas y a las herramientas de IA, y cuánto, **no se ha medido**:
es una hipótesis de trabajo, no un resultado.

Las decisiones de diseño y sus alternativas están en
[`decisions/0004`](decisions/0004-contratos-en-ejecucion.md) y
[`decisions/0007`](decisions/0007-contratos-estables-y-tipos-refinados.md).
