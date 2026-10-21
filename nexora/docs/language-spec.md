# Especificación del lenguaje NEXORA

- **Versión de la especificación:** 0.8
- **Implementación de referencia:** `nexora` 0.8.0 (este repositorio, directorio `nexora/`)
- **Estado:** describe exactamente lo que el intérprete hace hoy.

Este documento es la referencia del lenguaje: define la sintaxis y el significado de cada
construcción. Si el intérprete y este documento no coinciden, es un error que hay que corregir.

Cómo leer el estado de cada parte:

| Marca | Significado |
|-------|-------------|
| *(sin marca)* | **Implementado** y cubierto por pruebas |
| **Experimental** | Implementado y probado, pero su sintaxis o sus reglas pueden cambiar. En la versión 0.8 ninguna parte del lenguaje lo es |
| **Previsto** | No existe. Reunido en la sección 14; no forma parte del lenguaje |

Los cambios respecto a la versión 0.1 están en [`CHANGELOG.md`](../CHANGELOG.md) y sus motivos
en [`docs/decisions/`](decisions/README.md).

## 1. Filosofía

NEXORA explora cómo puede ser un lenguaje de programación cuando el código lo leen y lo escriben
tanto personas como herramientas automáticas. En esta versión esa idea se concreta en cinco
decisiones:

1. **Una sola forma de escribir cada cosa.** La sintaxis es pequeña y regular.
2. **Nada implícito.** No hay conversiones automáticas entre tipos ni valores "verdaderos" o
   "falsos" por convención. Todo cambio de tipo se escribe.
3. **Lo que puede comprobarse antes de ejecutar, se comprueba antes de ejecutar.** Nombres, ámbitos
   y tipos se verifican sin ejecutar el programa; lo que depende de los valores queda delimitado
   con precisión (sección 10).
4. **Las reglas forman parte del código.** Una función declara qué espera y qué promete
   (contratos, sección 9), un tipo puede declarar qué valores admite (tipos refinados,
   sección 4.4) y un bucle declara por qué termina y qué mantiene (sección 9.5). Cada regla puede llevar su explicación, y cuando se incumple el diagnóstico dice
   cuál, dónde y con qué valores ([decisión 0006](decisions/0006-requisitos-verificables.md)).
5. **Las herramientas reciben datos, no texto.** El programa y sus errores pueden obtenerse en JSON
   con un esquema versionado.

Las reglas del lenguaje son explícitas y deterministas. Ninguna depende de un modelo de IA, de
internet ni de un servicio externo: el mismo programa da siempre el mismo resultado.

Esta especificación no afirma que NEXORA sea más rápido, más seguro o mejor para la IA que otros
lenguajes. No existe ninguna medición que lo respalde.

## 2. Estructura léxica

### 2.1 Archivos

- Un programa es un único archivo de texto con extensión `.nex`.
- La codificación es UTF-8. Se acepta una marca de orden de bytes (BOM) inicial.
- Los finales de línea pueden ser `\n`, `\r\n` o `\r`.

### 2.2 Espacios, líneas y comentarios

- Los espacios y las tabulaciones separan elementos y no tienen otro significado. La sangría es libre.
- **El final de línea termina una sentencia.** No existe el punto y coma.
- Dentro de unos paréntesis `( )` los saltos de línea se ignoran: una expresión, una lista de
  argumentos o una lista de parámetros pueden ocupar varias líneas.
- Un comentario empieza con `//` y llega hasta el final de la línea. No hay comentarios de bloque.

### 2.3 Nombres

Un nombre empieza por una letra `a-z`, `A-Z` o `_` y continúa con letras, dígitos `0-9` o `_`.
Solo se admiten letras ASCII. Se distinguen mayúsculas de minúsculas.

### 2.4 Palabras clave y palabras reservadas

Palabras clave:

```
fn   let   var   return   if   else   while   for   in   true   false   and   or   not
requires   ensures   example   invariant   decreases   type   where
```

Palabras reservadas para versiones futuras. No pueden usarse como nombres y usarlas produce el
error `E1103`:

```
ai       assert   break    const    continue enum     import
match    pub      test     tool     try      uses
```

No son palabras reservadas, sino nombres predefinidos: los tipos `Int`, `Float`, `Bool`, `Text` y
`Void`; las funciones `print`, `to_text`, `to_float` y `to_int`; `result`, que solo tiene un
significado especial dentro de una cláusula `ensures`; y `value`, que solo lo tiene dentro de la
condición de un tipo refinado.

### 2.5 Literales

| Literal | Tipo | Ejemplos | Reglas |
|---------|------|----------|--------|
| Entero | `Int` | `0`, `42`, `1_000_000` | Dígitos decimales. `_` puede separar dos dígitos. Sin ceros a la izquierda (`007` es un error). Máximo `9223372036854775807` |
| Decimal | `Float` | `3.14`, `0.5`, `10.0` | Dígitos, un punto y más dígitos. Los dígitos son obligatorios a ambos lados del punto |
| Booleano | `Bool` | `true`, `false` | |
| Texto | `Text` | `"Hello"` | Entre comillas dobles, en una sola línea |

Los literales numéricos no llevan signo: `-5` es el operador `-` aplicado a `5`.

Secuencias de escape dentro de un texto:

| Escape | Significado |
|--------|-------------|
| `\n` | Salto de línea |
| `\t` | Tabulación |
| `\"` | Comilla doble |
| `\\` | Barra invertida |
| `\{` | Llave de apertura `{` |

Cualquier otra secuencia que empiece por `\` es un error (`E1003`). Una llave `{` sin escapar dentro
de un texto es un error (`E1005`): está reservada para la futura interpolación.

### 2.6 Símbolos

```
(  )  {  }  [  ]  ,  :  .  =  ->  +  -  *  /  ==  !=  <  <=  >  >=
```

Un `.` seguido de un dígito, dentro de un número, forma parte del número decimal (`1.5`). Cualquier
otro `.` es un símbolo, que solo es válido en una llamada cualificada como `Text.length(s)`
(sección 8.1).

Cualquier carácter que no forme parte de lo descrito en esta sección es un error (`E1001`); el
analizador nunca ignora un carácter desconocido.

## 3. Gramática

En notación EBNF. `NEWLINE` es uno o más finales de línea seguidos.

```ebnf
program    = { NEWLINE } { ( type_decl | record_decl | function ) { NEWLINE } } ;

type_decl  = "type" NAME "=" type "where" expression [ explanation ] end ;
record_decl = "type" NAME "=" "{" record_fields "}" ;
record_fields = record_field { "," record_field } ;
record_field = NAME ":" type ;
function   = "fn" NAME "(" [ params ] ")" "->" type { NEWLINE }
             "{" { NEWLINE } { contract } { statement end } "}" ;
params     = param { "," param } ;
param      = NAME ":" type ;
type       = NAME [ "[" type "]" ] ;
contract   = ( "requires" | "ensures" | "example" ) expression [ explanation ] end ;
explanation = "," TEXT ;

block      = "{" { NEWLINE } { statement end } "}" ;
end        = NEWLINE | (* nada, si lo siguiente es "}" *) ;

statement  = let | var | return | if | while | for | block | assignment | field_assignment | expression ;
let        = "let" NAME [ ":" type ] "=" expression ;
var        = "var" NAME [ ":" type ] "=" expression ;
return     = "return" [ expression ] ;
if         = "if" expression block [ "else" ( if | block ) ] ;
while      = "while" expression "{" { NEWLINE } { loop_clause } { statement end } "}" ;
for        = "for" NAME "in" expression "{" { NEWLINE } { loop_clause } { statement end } "}" ;
loop_clause = ( "invariant" | "decreases" ) expression [ explanation ] end ;
assignment = NAME "=" expression ;
field_assignment = NAME "." NAME "=" expression ;

expression     = or ;
or             = and { "or" and } ;
and            = comparison { "and" comparison } ;
comparison     = additive [ ( "==" | "!=" | "<" | "<=" | ">" | ">=" ) additive ] ;
additive       = multiplicative { ( "+" | "-" ) multiplicative } ;
multiplicative = unary { ( "*" | "/" ) unary } ;
unary          = ( "-" | "not" ) unary | primary ;
primary        = INT | FLOAT | TEXT | "true" | "false"
               | NAME
               | NAME "(" [ expression { "," expression } ] ")"
               | NAME "." NAME "(" [ expression { "," expression } ] ")"
               | NAME "." NAME
               | NAME "(" record_fields_values ")"
               | "[" [ expression { "," expression } ] "]"
               | "(" expression ")" ;
record_fields_values = record_value { "," record_value } ;
record_value = NAME ":" expression ;
```

Notas:

- En el nivel superior del archivo solo hay funciones y declaraciones de tipo, en cualquier orden.
  Un tipo no puede declararse dentro de una función (`E1101`).
- Una explicación (`explanation`) es un único texto literal no vacío, de una sola línea. Un texto
  vacío, formado solo por espacios o con un salto de línea (`\n`) es el error `E1101`.
- Las cláusulas `requires`, `ensures` y `example` van **al principio del cuerpo** de una función,
  antes de cualquier sentencia; `invariant` y `decreases`, al principio del cuerpo de un bucle. En
  cualquier otro lugar son el error `E1106`.
- `else` se escribe en la misma línea que la `}` que cierra el bloque anterior: `} else {`.
- Las comparaciones no se encadenan: `a < b < c` es un error de sintaxis (`E1101`). Se escribe
  `a < b and b < c`.
- Una asignación es una sentencia, no una expresión: `a = b = 1` e `if x = 1 { }` son errores de
  sintaxis (`E1101`). No existen `+=` ni `++`.
- No se admite una coma final en las listas de parámetros ni de argumentos.
- En una llamada cualificada (`NAME "." NAME "("`), el `.` va pegado a los dos nombres: sin espacios
  ni saltos de línea a sus lados (`E1101`). Entre el segundo nombre y el `(` puede haber espacios,
  como en cualquier llamada. Que el primer nombre sea un tipo con esa función lo comprueba el análisis
  estático (`E2008`, sección 8.1).
- Un registro se declara con `type` y unas llaves: `type Point = { x: Int, y: Int }`. Las llaves van
  en la misma línea que el `=`, y dentro de ellas se permite un salto de línea entre campos. Un
  registro tiene al menos un campo y no admite coma final (`E1101`).
- Un registro se construye con el nombre del tipo y los campos con nombre: `Point(x: 1, y: 2)`. El
  orden en que se escriben los campos no importa, pero cada uno se da una sola vez y todos están
  obligatorios (`E2023`).
- Leer un campo se escribe `valor.campo`. La raíz es siempre un nombre; sobre una llamada, una
  construcción, un grupo o una lista no se puede leer un campo (`E1101`). Las cadenas de acceso
  (`p.x.y`) no tienen un límite de longitud: cada paso intermedio tiene que ser un registro
  (`E2024`). El `.` va pegado a los dos nombres, como en una llamada cualificada.
- Un registro no cambia: `p.x = 1` es el error `E2025`. La forma existe para poder decirlo, no para
  poder hacerlo.
- Límites de tamaño: los paréntesis, los operadores unarios, los bloques, las cadenas `else if` y los
  tipos pueden anidarse hasta 64 niveles, y un árbol de expresión puede tener hasta 256 niveles (por
  ejemplo, una suma de 256 términos). Superarlos es el error `E1105`.
- Un tipo se escribe `NAME` o `NAME[T]`. En esta versión solo `List` admite argumentos de tipo, y
  exactamente uno. `List` sin argumento no es un tipo (`E2012`); `List[]`, `List[Int, Text]`,
  `List[Void]`, `Option[...]`, `Result[...]`, `Foo[...]` e `Int[...]` son errores de sintaxis
  (`E1101`). El anidamiento cuenta para el límite de 64 niveles.

## 4. Tipos de datos

| Tipo | Valores | Notas |
|------|---------|-------|
| `Int` | Enteros de `-9223372036854775808` a `9223372036854775807` | 64 bits con signo. Salirse del rango es un error de ejecución (`E3002`), nunca un resultado incorrecto |
| `Float` | Coma flotante IEEE 754 de 64 bits | No existen infinito ni NaN: una operación cuyo resultado no cabe es un error de ejecución (`E3003`). Existe el cero negativo (`-0.0`), que es igual a `0.0` y se escribe `-0.0` |
| `Bool` | `true`, `false` | |
| `Text` | Texto Unicode | Inmutable |
| `List[T]` | Secuencia inmutable y finita de valores de tipo `T` | `T` no puede ser `Void`; no hay covarianza (sección 4.5) |
| `Void` | Ningún valor | Solo puede ser el tipo de retorno de una función |
| Un registro | Los valores que se construyen con `Nombre(campo: valor, ...)` | Lo declara el programa: `type Point = { x: Int, y: Int }` (sección 4.6) |

`Int`, `Float`, `Bool` y `Text` son los **tipos de valor** integrados. `List[T]` es un tipo de valor
compuesto (sección 4.5); un programa también puede declarar tipos refinados sobre los integrados
(sección 4.4) y registros (sección 4.6). Los tipos de valor son los que puede
tener una variable, un parámetro o una expresión. `Void` no es un tipo de valor: una variable o un parámetro de tipo
`Void` es el error `E2012`, y usar una llamada a una función `Void` donde hace falta un valor es
el error `E2011`.

Escribir un nombre que no es un tipo donde se espera uno es el error `E2012`.

### 4.1 El sistema de tipos es estático

El tipo de **toda** expresión se determina sin ejecutar el programa, a partir de los literales, las
anotaciones y las firmas de las funciones. No existe ningún caso en el que el tipo de una expresión
dependa de un valor calculado, así que ningún error de tipos puede aparecer durante la ejecución.

### 4.2 Compatibilidad

**Un valor se acepta donde se espera un tipo solo si es de ese mismo tipo, o de un tipo refinado
construido sobre él** (sección 4.4). No hay tipos numéricos "más anchos" ni conversión automática:

- Un `Int` no se acepta donde se espera un `Float`, ni al revés.
- Ningún tipo se convierte a `Bool` ni a `Text` por sí solo.
- Un `Percent` (refinado sobre `Int`) se acepta donde se espera un `Int`. Un `Int` **no** se acepta
  donde se espera un `Percent`, salvo que sea una constante que cumple su condición.
- Los argumentos de `List` son **invariantes**: `List[Int]` no se acepta donde se espera
  `List[Text]`, y `List[Percent]` no se acepta donde se espera `List[Int]`, aunque cada `Percent`
  sea un `Int`. Un elemento refinado sí puede ensancharse a la base cuando la lista se construye
  con un tipo esperado (`let xs: List[Int] = [Percent(10), 20]`).

Esta regla se aplica por igual a la anotación de una variable, a los argumentos de una llamada, al
valor de un `return` y a los operandos de un operador.

### 4.3 Conversiones

Las únicas conversiones que existen son llamadas explícitas a funciones integradas:

| Función | Convierte | Regla |
|---------|-----------|-------|
| `to_float(value)` | `Int` → `Float` | Siempre posible. Los enteros de más de 53 bits se redondean al `Float` más cercano |
| `to_int(value)` | `Float` → `Int` | Descarta la parte decimal (redondea hacia cero): `to_int(3.9)` es `3`, `to_int(-3.9)` es `-3`. Si el resultado no cabe en un `Int`, error de ejecución `E3005` |
| `to_text(value)` | `Int`, `Float`, `Bool`, `Text` o `List[T]` → `Text` | El mismo texto que escribiría `print` (sección 8) |
| `Int.parse(text)` | `Text` → `Int` | Solo si `Int.can_parse(text)`; si no, `E4001` (sección 8.1) |
| `Float.parse(text)` | `Text` → `Float` | Solo si `Float.can_parse(text)`; si no, `E4001` (sección 8.1) |

No existe conversión desde `Text` hacia `Bool`, ni entre `Bool` y los números.

```nex
let count = 3
let price = 19.99
let total = to_float(count) * price        // correcto: Float * Float
print("Total: " + to_text(total))          // correcto: Text + Text
```

```nex
let total = count * price                  // E2011: Int y Float no se mezclan
print("Total: " + total)                   // E2011: '+' une Text con Text
```

### 4.4 Tipos refinados

Un tipo refinado es un tipo de valor más una condición que cumplen todos sus valores:

```text
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
```

Se declara en el nivel superior del archivo, antes o después de usarlo. `Percent` es el nombre,
`Int` es la **base** y lo que sigue a `where` es la **condición**. Detrás de la condición puede ir,
tras una coma, la explicación de la regla; aparece en los diagnósticos cuando la regla se incumple.

**La garantía.** Todo valor cuyo tipo es un tipo refinado cumple su condición, en cualquier punto
del programa. Para mantenerla, un valor solo puede llegar a tener un tipo refinado de dos formas:

| Forma | Ejemplo | Cuándo se comprueba | Si no se cumple |
|-------|---------|---------------------|-----------------|
| Una **constante** donde se espera el tipo | `let p: Percent = 20`, `discount(20)`, `return 20` | Sin ejecutar, en `nex check` | `E2017`, el programa no se ejecuta |
| La **comprobación explícita** `Percent(x)` | `let p = Percent(total / 2)` | Al ejecutar, cada vez que se evalúa | `E4003`, el programa se detiene ahí |

Una constante es un literal, opcionalmente con `-` o `not` delante o entre paréntesis. Comprobar una
constante cuesta tanto como las condiciones de toda la cadena de su tipo; si el total de un
programa supera 100 000 nodos de condición evaluados, el programa se rechaza con `E2019` en vez
de quedar comprobado a medias. Es un límite de la implementación, como los de la sección 3, y un
programa corriente queda muy por debajo. Cualquier
otro valor de la base (una variable, una operación, el resultado de una llamada) no se acepta donde
se espera el tipo refinado (`E2011`): hay que comprobarlo con `Percent(...)`. Así, cada punto donde
el programa puede detenerse por una regla está escrito en el código.

Reglas de la declaración:

- El nombre empieza por mayúscula (`E2016`) y no puede ser el de un tipo integrado (`E2016`), el de
  otro tipo (`E2016`), ni usarse para una función, un parámetro o una variable (`E2006`).
- La base es `Int`, `Float`, `Bool`, `Text` u otro tipo refinado. No puede ser una lista
  (`E2016`). Una cadena de tipos que no llega a un tipo integrado (`type A = B ...` y
  `type B = A ...`) es el error `E2016`.
- La condición es una expresión `Bool` (`E2011`). En ella solo existe el nombre `value`, que es el
  valor que se comprueba y tiene el tipo de la base (`E2005` para cualquier otro nombre).
- La condición no puede llamar a funciones del programa ni comprobar otros tipos refinados
  (`E2018`). Puede usar operadores, literales y las conversiones integradas. Un tipo refinado
  describe un valor y nada más; las reglas que dependen de otros datos se escriben con `requires`.

Uso de los valores:

- Un valor refinado se acepta donde se espera su base, o cualquier tipo de la cadena de bases: un
  `Percent` es un `Int`.
- En una operación cuenta como un valor de su base: `p + 1` es un `Int`, no un `Percent`, porque el
  resultado puede no cumplir la condición. Para volver a tener un `Percent` hay que comprobarlo.
- Dos tipos refinados distintos son tipos distintos aunque tengan la misma base y la misma
  condición.
- `Percent(x)` recibe exactamente un argumento de la misma base (`E2009`, `E2011`) y devuelve un
  `Percent`. El nombre de un tipo solo puede usarse así: escrito solo, sin paréntesis, es `E2011`.

**Refinar un tipo refinado.** `type Pass = Percent where value >= 50` exige las dos condiciones.
Se comprueban en orden, desde la base: primero la de `Percent` y después la de `Pass`. El
diagnóstico indica cuál de las dos es falsa.

<!-- nex:run -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
type Pass = Percent where value >= 50, "Passing starts at half"

fn grade(points: Int, total: Int) -> Percent {
    requires total > 0, "There is nothing to grade"
    return Percent(points * 100 / total)
}

fn main() -> Void {
    let minimum: Pass = 50
    let score = grade(42, 60)
    print(score)
    print(score >= minimum)
}
```

```text
70
true
```

Una constante que no cumple la condición se rechaza sin ejecutar nada:

<!-- nex:check-fails -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() -> Void {
    let discount: Percent = 120
    print(discount)
}
```

```text
type error[E2017]: Value outside refined type
 --> program.nex:4:29
  |
4 |     let discount: Percent = 120
  |                             ^^^ 120 is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 120
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: check failed with 1 error
```

Y un valor calculado que no la cumple detiene el programa en el punto donde se comprueba:

<!-- nex:fails exit=5 -->
```nex
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"

fn main() -> Void {
    let points = 130
    print(Percent(points))
}
```

```text
contract error[E4003]: Refinement violated
 --> program.nex:5:11
  |
5 |     print(Percent(points))
  |           ^^^^^^^^^^^^^^^ This value is not a valid Percent
  = note: The condition of 'Percent' is false: where value >= 0 and value <= 100
  = note: The value: 130
  = note: Reason: A percentage goes from 0 to 100

error: program.nex: the program stopped because a contract was broken
```

### 4.5 Listas

Una lista es una secuencia **inmutable y finita** de valores del mismo tipo. Su tipo se escribe
`List[T]`, donde `T` es el tipo de los elementos:

```nex
let numbers: List[Int] = [1, 2, 3]
let empty: List[Int] = []
let nested: List[List[Int]] = [[1], [2, 3]]
let words: List[Text] = ["a", "b"]
```

`T` puede ser `Int`, `Float`, `Bool`, `Text`, un tipo refinado u otra `List[...]`. No puede ser
`Void`: `List[Void]` es un error de sintaxis (`E1101`). El tipo es **invariante** en `T`:

- `List[Int]` y `List[Text]` son tipos distintos; no hay conversión de uno a otro.
- `List[Percent]` no se acepta donde se espera `List[Int]`, aunque `Percent` sea un `Int` refinado.
  La razón es que una operación que acepta `List[Int]` podría tratar sus elementos como `Int`
  cualesquiera, y una `List[Percent]` promete más que eso.
- Un elemento refinado sí puede ensancharse a su base al construir una lista con un tipo esperado:
  `let xs: List[Int] = [Percent(10), 20]`.

#### Literales e inferencia

`[a, b, c]` y `[]` son expresiones. Sin un tipo esperado, el **primer elemento** fija el tipo de
los demás; todos tienen que ser aceptables como ese tipo. Con un tipo esperado `List[T]`, todos los
elementos se comprueban contra `T`.

```nex
let numbers = [1, 2, 3]                 // List[Int]
let texts = ["a", "b"]                  // List[Text]
let nested = [[1], [2, 3]]              // List[List[Int]]
let empty: List[Int] = []               // el tipo esperado fija Int
```

Una lista vacía **necesita un tipo esperado**. No se inventa el tipo del elemento:

<!-- nex:body-fails codes=E2011 -->
```nex
let xs = []                             // no se sabe de qué tipo son los elementos
print([])                               // tampoco
```

El tipo esperado puede venir de una anotación, de un parámetro, del tipo de retorno, de una
asignación o del lado izquierdo de una igualdad (`a == []`). No se propaga del lado derecho al
izquierdo: `[] == a` es `E2011` aunque `a` tenga tipo. También se propaga a listas anidadas:
`let xs: List[List[Int]] = [[]]` es válido.

Todos los elementos de una lista tienen el mismo tipo. No se mezclan, por ejemplo, `Int` y `Text`:

<!-- nex:body-fails codes=E2011 -->
```nex
let mixed = [1, "a"]                    // Expected Int, found Text
```

#### Inmutabilidad, igualdad e impresión

Una lista no cambia. Una variable `var` puede pasar a apuntar a otra lista, pero la lista anterior
conserva sus elementos. `List.append` y `List.concat` construyen listas nuevas (sección 8.2).

`==` y `!=` comparan listas del **mismo tipo** de forma estructural: mismos elementos, en el mismo
orden, comparados recursivamente. El resultado es `Bool`. No hay orden (`<`, `<=`, `>`, `>=`) entre
listas.

`print` y `to_text` escriben la forma canónica con corchetes y sin comillas alrededor de los textos:
`[1, 2, 3]`, `[[1], [2, 3]]`, `[a, b]`, `[]`. Los diagnósticos pueden entrecomillar los textos para
distinguirlos; esa no es la salida de `print`. La impresión no escapa los textos: no es un formato de
serialización, y un texto que contenga `,` o `]` puede verse ambiguo.

<!-- nex:run -->
```nex
fn main() -> Void {
    let numbers = [1, 2, 3]
    let empty: List[Int] = []
    let nested = [[1], [2, 3]]
    print(numbers)
    print(empty)
    print(nested)
    print(numbers == [1, 2, 3])
    print(empty == [])
}
```

```text
[1, 2, 3]
[]
[[1], [2, 3]]
true
true
```

No hay sintaxis de índice (`xs[i]`) ni forma de modificar un elemento. Para leer una posición se
usa `List.get`; para añadir o unir listas, `List.append` y `List.concat` (sección 8.2). Un tipo
refinado no puede construirse sobre una lista en esta versión (`E2016`).

### 4.6 Registros

Un **registro** es un tipo que declara el programa, con campos **inmutables** y **obligatorios**, que
se construye dando a cada campo su valor por nombre.

<!-- nex:run -->
```nex
type Point = { x: Int, y: Int }
type Line = { from: Point, to: Point }

fn main() -> Void {
    let origin = Point(x: 0, y: 0)
    let end = Point(x: 3, y: 4)
    let segment = Line(from: origin, to: end)
    print(segment.from.x)
    print(segment)
}
```

```text
0
Line(from: Point(x: 0, y: 0), to: Point(x: 3, y: 4))
```

**Declaración.** `type Nombre = { campo: Tipo, ... }`. El nombre empieza por mayúscula, como el de
cualquier tipo, y no puede ser el de un tipo integrado ni el de otro tipo declarado (`E2016`). Cada
campo tiene un nombre y un tipo; dos campos del mismo registro no pueden llamarse igual (`E2016`).
El tipo de un campo puede ser un tipo integrado, `List[T]`, un tipo refinado u **otro registro**.

**Construcción.** `Nombre(campo: valor, ...)`. Los campos se pueden escribir en cualquier orden,
pero cada uno se da **una sola vez** y **todos** están obligatorios: un campo que falta, uno que se
repite o uno que el registro no tiene son el error `E2023`. El valor de un campo tiene que tener el
tipo del campo (`E2011`).

**Lectura.** `valor.campo`. La raíz es siempre un nombre: una variable, un parámetro o `result` dentro
de un `ensures`. Se pueden encadenar (`p.x.y`), sin límite de longitud, siempre que cada paso
intermedio sea un registro; si el valor no es un registro, o el registro no tiene ese campo, es el
error `E2024`. Un nombre de tipo no es un valor: `Point.x` no lee un campo, es una llamada cualificada
como las de la sección 8.1.

**Inmutabilidad.** Un registro no cambia: no hay ninguna forma de asignar a un campo. `p.x = 1` es el
error `E2025`.

**Identidad.** Un registro es **nominal**: su identidad es la de su declaración, no la de su nombre
ni la de sus campos. Dos registros con los mismos campos son tipos distintos, y un valor de uno no
se acepta donde se espera el otro (`E2011`). Dos valores del **mismo** registro se comparan **por
valor**, campo a campo: `Point(x: 1, y: 2) == Point(x: 1, y: 2)` es `true`.

**Referencias adelantadas y ciclos.** Un registro puede usar otro declarado más abajo, mientras el
grafo de dependencias no tenga ciclos. Un registro no puede contenerse a sí mismo, ni directamente
ni a través de otro registro ni de una lista: `type A = { a: A }` es el error `E2016`, y el mensaje
escribe el ciclo (`A -> B -> A`).

**Qué no hay.** Un registro no tiene métodos ni funciones propias, no se puede refinar, no admite
genéricos y no puede ser recursivo. Un tipo refinado no puede construirse sobre un registro
(`E2016`).

## 5. Variables y ámbitos

### 5.1 Declaración

```nex
let name = "NEXORA"           // tipo inferido: Text
let age: Int = 25             // tipo anotado
```

- `let` declara una variable y le da valor. Una variable siempre se inicializa al declararla.
- **Inferencia:** sin anotación, el tipo de la variable es el tipo de su valor.
- **Anotación:** con `: Tipo`, el valor tiene que ser exactamente de ese tipo. Si no lo es, el error
  es `E2011` y señala el valor. La variable conserva el tipo anotado, de modo que un único error no
  se repite en cada uso posterior.
- El valor no puede ser una llamada a una función `Void` (`E2011`).
- **Una variable `let` es inmutable.** No existe ninguna forma de cambiar su valor; `name = "x"` es el
  error `E2007`. Los parámetros de una función también son inmutables. Una variable que tiene que
  cambiar se declara con `var` (sección 5.3).

```nex
let age: Int = "twenty"       // E2011: Expected Int, found Text
let price: Float = 5          // E2011: Expected Float, found Int   (sugiere to_float)
let nothing = print("x")      // E2011: la llamada no produce un valor
let x: Void = 1               // E2012: una variable no puede ser Void
```

### 5.2 Ámbitos y resolución de nombres

- Cada función tiene su propio ámbito. Empieza con sus parámetros y **no ve las variables de quien
  la llama** ni de ninguna otra función. No existen variables globales.
- Cada bloque `{ }` (incluidos los de `if` y `else`) abre un ámbito dentro del que lo contiene. Un
  bloque interior puede leer las variables de los bloques exteriores de su misma función.
- Una variable existe desde la sentencia siguiente a su declaración hasta el final del bloque donde
  se declaró. No es visible dentro de su propia expresión inicial (`let x = x` es un error).
- Las funciones son visibles en todo el archivo, también antes de la línea en la que se declaran.
- **Un único espacio de nombres.** Funciones, parámetros y variables comparten los nombres: una
  variable o un parámetro no puede llamarse como una función del programa ni como una función
  integrada (`E2006`). Los nombres de los tipos refinados tampoco pueden usarse para otra cosa
  (`E2006`).
- **No hay ocultación de nombres (*shadowing*).** Declarar un nombre que ya es visible, sea del mismo
  bloque, de uno exterior o un parámetro, es el error `E2006`. Dos bloques hermanos sí pueden usar
  el mismo nombre, porque ninguno ve las variables del otro.
- Usar como valor un nombre que no existe es el error `E2005`. Usar una función sin llamarla
  (`let f = add`) es el error `E2011`: las funciones no son valores.

Consecuencia: dentro de una función, cada nombre significa una sola cosa de principio a fin.

### 5.3 Variables que cambian: `var` y la asignación

<!-- nex:body -->
```nex
var count = 0                 // tipo inferido: Int
var total: Float = 0.0        // tipo anotado
count = count + 1             // asignación
```

- `var` tiene la misma forma y las mismas reglas que `let` (inferencia, anotación, ámbito, sin
  ocultación). La diferencia es que su valor puede cambiarse después con una asignación.
- **El tipo de una `var` no cambia nunca.** El valor asignado tiene que ser compatible con él, con la
  regla de la sección 4.2 (`E2011`).
- Se puede asignar una `var` visible en ese punto, también desde un bloque interior. Asignar una
  variable `let` o un parámetro es el error `E2007`; un nombre que no es una variable visible,
  `E2005`.
- **Los parámetros no se pueden asignar.** Así, en `ensures` y en los diagnósticos tienen siempre el
  valor con el que se llamó a la función. Para cambiarlo, se copia: `var rest = n`.
- Una `var` de tipo refinado conserva la garantía de la sección 4.4: se le asigna una constante que
  cumple la condición (comprobada sin ejecutar, `E2017`) o un valor comprobado con `Tipo(x)`.
  `p = p + 1` es `E2011`; se escribe `p = Percent(p + 1)`.
- Una función no ve las variables de quien la llama, así que una `var` solo cambia desde su propia
  función: no hay estado compartido entre funciones.

```text
var p: Percent = 20
p = 30                 // correcto: constante que cumple la condición
p = 120                // E2017: 120 no es un Percent válido
p = p + 10             // E2011: un Int no es un Percent
p = Percent(p + 10)    // correcto: comprobado al ejecutar (E4003 si no se cumple)
```

<!-- nex:valid -->
```nex
fn main() -> Void {
    let total = 10
    if total > 5 {
        let double = total * 2   // lee 'total' del bloque exterior
        print(double)
    }
    // 'double' ya no existe aquí
}
```

## 6. Expresiones y operadores

### 6.1 Precedencia

De mayor a menor. Todos los operadores binarios asocian por la izquierda.

| Nivel | Operadores | Operandos | Resultado |
|-------|-----------|-----------|-----------|
| 1 | `-x` | `Int` o `Float` | El mismo tipo |
| 1 | `not x` | `Bool` | `Bool` |
| 2 | `*`  `/` | Dos `Int` o dos `Float` | El mismo tipo |
| 3 | `+`  `-` | Dos `Int` o dos `Float` | El mismo tipo |
| 3 | `+` | Dos `Text` | `Text` (concatenación) |
| 4 | `==`  `!=` | Dos valores del mismo tipo (`Int`, `Float`, `Bool` o `Text`) | `Bool` |
| 4 | `<`  `<=`  `>`  `>=` | Dos `Int`, dos `Float` o dos `Text` | `Bool` |
| 5 | `and` | Dos `Bool` | `Bool` |
| 6 | `or` | Dos `Bool` | `Bool` |

Los paréntesis agrupan: `(2 + 3) * 4`.

`not` tiene más precedencia que las comparaciones: `not a == b` significa `(not a) == b`. Para negar
una comparación se escribe `not (a == b)` o, mejor, `a != b`.

Cualquier combinación de tipos que no aparezca en la tabla es el error `E2011`. En particular:

- `Int` y `Float` no se mezclan, tampoco al comparar: `1 + 1.5` y `1 == 1.0` son errores.
- Los `Bool` no admiten aritmética ni orden: `true + 1` y `true < false` son errores.
- Los `Text` solo admiten `+`, `==`, `!=` y el orden (`<`, `<=`, `>`, `>=`) entre dos `Text`:
  `"a" * 2` y `"1" < 2` son errores.
- `and`, `or` y `not` solo aceptan `Bool`: `1 and 2` y `not 0` son errores.

### 6.2 Semántica

- **Orden de evaluación:** en una operación binaria se evalúa primero el operando izquierdo y
  después el derecho. Los argumentos de una llamada se evalúan de izquierda a derecha.
- **Cortocircuito:** `a and b` no evalúa `b` si `a` es `false`; `a or b` no evalúa `b` si `a` es
  `true`.
- **Igualdad:** dos `Text` son iguales si tienen exactamente los mismos caracteres (se distinguen
  mayúsculas). Dos `Float` se comparan por su valor IEEE 754.
- **Orden entre textos:** carácter a carácter, por punto de código Unicode. En la primera posición
  en que difieren, va antes el carácter de punto de código más bajo; si uno es el principio del
  otro, va antes el más corto. No depende del idioma ni de la configuración del sistema, y no es el
  orden alfabético de ningún idioma: `"Z" < "a"`, `"z" < "é"` y `"10" < "9"` son verdaderos. Nada
  se normaliza: una `é` escrita con un solo carácter es distinta de una `e` seguida del acento
  combinado (sección 8.1).
- **División entre enteros:** `/` entre dos `Int` devuelve un `Int` y descarta la parte decimal
  (redondea hacia cero): `7 / 2` es `3` y `-7 / 2` es `-3`. Para obtener decimales se dividen dos
  `Float`: `7.0 / 2.0` es `3.5`.
- **División por cero:** dividir por `0` o por `0.0` es el error de ejecución `E3001`.
- **Desbordamiento:** un resultado `Int` fuera de rango es `E3002`; un resultado `Float` que no
  cabe es `E3003`.

### 6.3 Condiciones

Una condición (la de un `if` o la de un contrato) tiene que ser de tipo `Bool`. Un número o un
texto no son una condición (`E2011`):

```nex
if count > 0 { ... }          // correcto
if count { ... }              // E2011: la condición debe ser Bool, es Int
```

### 6.4 Expresiones como sentencias

Una expresión usada como sentencia tiene que ser una llamada a una función `Void`. Cualquier otra
cosa es el error `E2010`, porque su valor se perdería: una operación suelta (`40 + 2`) o una
llamada cuyo resultado no se usa (`add(1, 2)`).

## 7. Funciones

### 7.1 Declaración

```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}
```

- Cada parámetro declara su tipo, que tiene que ser un tipo de valor.
- El tipo de retorno se escribe siempre. `Void` indica que la función no devuelve nada.
- Las funciones se declaran en el nivel superior del archivo, en cualquier orden. No pueden
  declararse dentro de otra función.
- No hay sobrecarga: dos funciones con el mismo nombre son el error `E2002`. Tampoco puede
  declararse una función con el nombre de una integrada (`E2002`).
- Dos parámetros con el mismo nombre son el error `E2006`. Un parámetro no puede llamarse `result`
  (`E2013`).
- No hay valores por defecto, argumentos con nombre, genéricos, clases ni funciones anónimas.

### 7.2 La función principal

<!-- nex:valid -->
```nex
fn main() -> Void {
    print("Hello from NEXORA")
}
```

Todo programa declara una función `main`, sin parámetros y con tipo de retorno `Void`. Es el punto
de entrada. Si falta, el error es `E2001`; con parámetros, `E2013`; con otro tipo de retorno,
`E2004`.

### 7.3 `return` y rutas de retorno

- En una función que devuelve un valor, `return expresión` termina la función con ese valor. El
  tipo de la expresión tiene que ser el tipo de retorno declarado (`E2011` si no).
- En una función `Void`, `return` sin valor termina la función antes de llegar al final.
  `return expresión` es el error `E2011`. Llegar al final del cuerpo también termina la función.
- Un `return` sin valor en una función que devuelve un valor es el error `E2011`.
- **Toda ruta devuelve.** Una función que devuelve un valor tiene que terminar con `return` por
  todos los caminos posibles; si alguno puede llegar al final del cuerpo, el error es `E2014`.
- Una sentencia situada después de un `return` en el mismo bloque no puede ejecutarse nunca y es el
  error `E2015`.

Cómo se decide si un bloque "siempre devuelve":

| Sentencia | Siempre devuelve si… |
|-----------|----------------------|
| `return` | Siempre |
| `if` sin `else` | Nunca (la condición puede ser falsa) |
| `if` … `else` … | Todas sus ramas siempre devuelven |
| Bloque `{ }` | Alguna de sus sentencias siempre devuelve |
| `while` | Nunca (su condición puede ser falsa desde el principio) |
| `for` | Nunca (la lista puede estar vacía) |
| Cualquier otra | Nunca |

El análisis no evalúa las condiciones: `if true { return 1 }` sin `else` se considera incompleto, y
una función cuyo único `return` está dentro de un bucle necesita otro después del bucle.

```nex
fn sign(n: Int) -> Int {          // correcto: las tres ramas devuelven
    if n < 0 {
        return -1
    } else if n == 0 {
        return 0
    } else {
        return 1
    }
}

fn broken(n: Int) -> Int {        // E2014: si n <= 0 se llega al final sin 'return'
    if n > 0 {
        return 1
    }
}
```

### 7.4 Llamadas

```nex
let result: Int = add(2, 3)
```

Una llamada se comprueba sin ejecutar el programa:

| Comprobación | Error |
|--------------|-------|
| La función existe | `E2008` |
| El número de argumentos coincide con el de parámetros | `E2009` |
| El tipo de cada argumento es el del parámetro correspondiente | `E2011` |
| Ningún argumento es una llamada a una función `Void` | `E2011` |

El tipo de una llamada es el tipo de retorno de la función.

Al ejecutarse, una llamada:

1. Evalúa los argumentos, de izquierda a derecha.
2. Crea un ámbito nuevo y asigna cada argumento a su parámetro, por posición.
3. Comprueba las cláusulas `requires`, en orden (sección 9).
4. Ejecuta el cuerpo hasta un `return` o hasta el final.
5. Comprueba las cláusulas `ensures`, en orden.
6. Devuelve el valor al punto de la llamada.

Los argumentos se pasan por valor y todos los valores son inmutables, así que una función no puede
modificar nada de quien la llama.

### 7.5 Recursividad

Una función puede llamarse a sí misma, y dos funciones pueden llamarse entre sí.

El número de llamadas anidadas está limitado a 1000 (contando `main`). Superarlo es el error de
ejecución `E3004`; el caso habitual es una recursividad que nunca alcanza su caso base. Con
expresiones muy profundamente anidadas el límite efectivo puede ser menor; el error es el mismo.
Para repetir algo muchas veces se usa un bucle (sección 9.5): sus vueltas no son llamadas y no
cuentan para este límite.

## 8. Funciones integradas

| Función | Firma | Descripción |
|---------|-------|-------------|
| `print` | `print(value) -> Void` | Escribe el valor seguido de un salto de línea en la salida estándar. Acepta un valor de cualquier tipo de valor |
| `to_text` | `to_text(value) -> Text` | Convierte cualquier valor en el texto que escribiría `print` |
| `to_float` | `to_float(value: Int) -> Float` | Convierte un entero en decimal |
| `to_int` | `to_int(value: Float) -> Int` | Convierte un decimal en entero descartando la parte decimal |

Texto que producen `print` y `to_text`:

| Tipo | Formato | Ejemplos |
|------|---------|----------|
| `Text` | El texto, sin comillas | `Hello` |
| `Int` | En decimal | `42`, `-7` |
| `Bool` | `true` o `false` | |
| `Float` | La representación decimal más corta que identifica el valor; siempre lleva punto decimal o exponente | `3.5`, `2.0`, `0.30000000000000004`, `1e+16` |
| `List[T]` | Corchetes, elementos separados por `, `, sin comillas alrededor de los textos | `[1, 2, 3]`, `[[1], [2]]`, `[]` |

`print` es la única forma que tiene un programa de producir un efecto. Un programa NEXORA no puede
leer archivos, abrir conexiones, ejecutar otros programas ni leer datos de entrada.

### 8.1 Funciones de un tipo: `Text.length`, `Int.parse`…

Algunas funciones integradas pertenecen a un tipo y se llaman con su nombre delante
([decisión 0011](decisions/0011-operaciones-sobre-textos.md)):

| Función | Qué hace | Requisitos |
|---------|----------|------------|
| `Text.length(text: Text) -> Int` | Número de caracteres | |
| `Text.slice(text: Text, start: Int, end: Int) -> Text` | Los caracteres desde `start` (incluido) hasta `end` (excluido) | `start >= 0`, `start <= end`, `end <= Text.length(text)` |
| `Text.contains(text: Text, part: Text) -> Bool` | Si `part` aparece en `text` | |
| `Text.starts_with(text: Text, part: Text) -> Bool` | Si `text` empieza por `part` | |
| `Text.ends_with(text: Text, part: Text) -> Bool` | Si `text` termina en `part` | |
| `Int.can_parse(text: Text) -> Bool` | Si `text` es un entero escrito según la gramática de abajo, dentro del rango de `Int` | |
| `Int.parse(text: Text) -> Int` | El entero escrito en `text` | `Int.can_parse(text)` |
| `Float.can_parse(text: Text) -> Bool` | Si `text` es un decimal escrito según la gramática de abajo, cuyo valor redondeado es finito | |
| `Float.parse(text: Text) -> Float` | El decimal escrito en `text`, redondeado al `Float` más cercano | `Float.can_parse(text)` |

- **Un carácter es un punto de código Unicode** y las posiciones empiezan en 0. `Text.length("año")`
  es 3. No se normaliza nada: una `e` seguida del acento combinado son dos caracteres.
- **Nombres.** No se reserva ningún nombre: `let length = Text.length(name)` es válido, y `Int`,
  `Float`, `Bool` y `Text` se pueden seguir usando como nombres de variable. Delante del punto solo
  puede ir un tipo con esa función; cualquier otra cosa es `E2008`, con una sugerencia (`length(t)`
  sugiere `Text.length`). Un programa no puede declarar funciones de un tipo.
- **Requisitos.** Antes de la operación se comprueban sus requisitos, en el orden de la tabla. El
  primero que no se cumple detiene el programa con `E4001`, como el `requires` de una función del
  programa. No hay índices negativos ni recortes silenciosos: `Text.slice("abc", 2, 9)` no devuelve
  `"c"`. `Int.parse` y `Float.parse` añaden una sugerencia según lo que falló.
- **Números escritos en un texto.** Una única forma, solo con caracteres ASCII:

  ```text
  entero    = [ "-" ] dígito { dígito }
  decimal   = [ "-" ] dígito { dígito } ( fracción [ exponente ] | exponente )
  fracción  = "." dígito { dígito }
  exponente = ( "e" | "E" ) [ "+" | "-" ] dígito { dígito }
  ```

  Sin espacios, sin `+` delante, sin `_` ni separadores, sin `inf` ni `nan`. Se admiten ceros a la
  izquierda (`"007"` es 7). `Float.can_parse("1")` es falso: un entero no es un decimal; se lee con
  `to_float(Int.parse("1"))`. Un valor demasiado pequeño se redondea a cero (`"1e-400"` es `0.0`);
  uno que se redondearía a infinito no se admite (`"1e309"`). Lo que escribe `to_text` siempre se
  puede volver a leer: `Int.parse(to_text(n)) == n` y `Float.parse(to_text(x)) == x`.

<!-- nex:run -->
```nex
fn main() -> Void {
    let name = "Ada Lovelace"
    let length = Text.length(name)
    print(length)
    print(Text.slice(name, 0, 3))
    print(Text.contains(name, "Love") and Text.ends_with(name, "lace"))
    print("Ada" < "ada")
    if Int.can_parse("042") {
        print(Int.parse("042") + 1)
    }
}
```

```text
12
Ada
true
true
43
```

Un requisito que no se cumple detiene el programa con su explicación y los valores de la llamada:

<!-- nex:fails exit=5 -->
```nex
fn main() -> Void {
    print(Int.parse("12a"))
}
```

```text
contract error[E4001]: Precondition violated
 --> program.nex:2:11
  |
2 |     print(Int.parse("12a"))
  |           ^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'Int.parse'
  = note: The condition of the built-in function is false: requires Int.can_parse(text)
  = note: Reason: Only a whole number within the range of Int can be read as an Int
  = note: It was called with: text = "12a"
  = hint: Check the text first with Int.can_parse(...), and call Int.parse only when it is true.

error: program.nex: the program stopped because a contract was broken
```

### 8.2 Funciones de `List`

Las listas tienen cinco funciones integradas. Son funciones de un tipo, como las de la sección
8.1, y se llaman con `List.` delante. Su firma usa una variable de tipo `T` que no se escribe en el
programa: cada llamada la liga con el tipo de sus argumentos. No son genéricos de usuario y no se
puede declarar una función así.

| Función | Firma | Qué hace | Requisitos |
|---------|-------|----------|------------|
| `List.length` | `List.length(xs: List[T]) -> Int` | Número de elementos | |
| `List.get` | `List.get(xs: List[T], i: Int) -> T` | Elemento en la posición `i`, empezando en 0 | `0 <= i and i < List.length(xs)` |
| `List.append` | `List.append(xs: List[T], x: T) -> List[T]` | Lista nueva con `x` al final | |
| `List.concat` | `List.concat(xs: List[T], ys: List[T]) -> List[T]` | Lista nueva con los elementos de `xs` y después los de `ys` | |
| `List.contains` | `List.contains(xs: List[T], x: T) -> Bool` | Si algún elemento es estructuralmente igual a `x` | |

- **`List.length`** es total. `List.length([])` no compila si la lista vacía no tiene un tipo
  esperado (`E2011`); `let xs: List[Int] = []` y `List.length(xs)` sí.
- **`List.get`** es parcial. El índice empieza en 0 y tiene que estar dentro de la lista. Un índice
  negativo, igual a la longitud o mayor detiene el programa con `E4001`, también si es una constante:
  `nex check` no demuestra el contrato. No hay índices negativos desde el final ni recortes
  silenciosos. La comprobación lleva la explicación «An index must be inside the list».
- **`List.append` y `List.concat`** no modifican sus argumentos: construyen una lista nueva. El tipo
  del resultado conserva el elemento de las listas de entrada. Una lista vacía literal en un
  argumento necesita un tipo esperado, porque la firma paramétrica no lo fija antes de leer los
  argumentos: `List.append([], 1)` y `List.concat([1], [])` son `E2011`.
- **`List.contains`** usa igualdad estructural, no búsqueda de subtextos: `List.contains(["ab"], "b")`
  es `false`. La lista y el valor tienen que tener el mismo tipo de elemento; un `Int` no se busca
  en una `List[Text]`.
- Los argumentos se comprueban como en cualquier llamada: número (`E2009`), tipo (`E2011`) y, si
  procede, el contrato al ejecutar (`E4001`). Una función de `List` desconocida es `E2008`, con
  sugerencia si se parece a una de las cinco.

<!-- nex:run -->
```nex
fn main() -> Void {
    let xs = [10, 20, 30]
    print(List.length(xs))
    print(List.get(xs, 1))
    print(List.append(xs, 40))
    print(List.concat(xs, [40, 50]))
    print(List.contains(xs, 20))
    print(List.contains(xs, 25))
}
```

```text
3
20
[10, 20, 30, 40]
[10, 20, 30, 40, 50]
true
false
```

Fuera de estas cinco funciones no hay `map`, `filter`, `fold`, ordenación, `slice` ni una variante
total de `List.get`. Llegarán, si se deciden, con `Option`/`Result` y las demás decisiones
pendientes.

## 9. Contratos

Un contrato expresa una condición que una función **espera** de quien la llama o una condición que
**promete** cumplir. Los contratos son deterministas y se evalúan con las mismas reglas que
cualquier otra expresión; no interviene ningún modelo de IA.

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
```

### 9.1 Reglas

- Las cláusulas van al principio del cuerpo, una por línea, antes de cualquier sentencia. Puede
  haber varias de cada tipo y en cualquier orden.
- La condición de una cláusula tiene que ser de tipo `Bool` (`E2011`).
- **`requires`** es una condición previa. En ella son visibles los parámetros de la función y
  ningún otro nombre: ni las variables del cuerpo ni `result`.
- **`ensures`** es una condición posterior. En ella son visibles los parámetros y, si la función
  devuelve un valor, `result`, que es **el valor devuelto por la función** y tiene su tipo de
  retorno. En una función `Void` no existe `result`.
- Los parámetros son inmutables, así que en `ensures` tienen el mismo valor que al entrar.
- `result` es un nombre contextual: solo significa "el valor devuelto" dentro de `ensures`. En el
  cuerpo de una función es un nombre de variable como cualquier otro. Un parámetro no puede
  llamarse `result` (`E2013`).
- Una condición puede llamar a funciones.
- Detrás de la condición puede ir, tras una coma, **la explicación de la regla**: un texto que dice
  por qué existe. No cambia lo que se comprueba; aparece en el diagnóstico cuando la condición es
  falsa, como `Reason: ...`.

<!-- nex:fails exit=5 -->
```nex
fn withdraw(balance: Int, amount: Int) -> Int {
    requires amount > 0, "A withdrawal moves some money"
    requires amount <= balance, "An account cannot go below zero"
    ensures result == balance - amount
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

### 9.2 Qué se comprueba y cuándo

| Momento | Qué se comprueba |
|---------|------------------|
| Sin ejecutar (`nex check`) | Que cada condición esté bien formada: nombres visibles, tipos correctos, resultado `Bool` |
| Al ejecutar, en cada llamada | `requires`: después de asignar los argumentos y **antes** de ejecutar el cuerpo |
| Al ejecutar, en cada llamada | `ensures`: **después** de calcular el valor de retorno, antes de entregarlo a quien llamó |

Si la condición es falsa, el programa se detiene con un diagnóstico de contrato:

- **`E4001` Precondition violated.** La posición señalada es **la llamada**: quien llama no cumplió
  lo que la función exige. El diagnóstico muestra la cláusula incumplida y los valores de los
  argumentos. El cuerpo de la función no llega a ejecutarse.
- **`E4002` Postcondition violated.** La posición señalada es **la cláusula `ensures`**: la función
  no cumplió lo que promete. El diagnóstico muestra el valor devuelto y los argumentos.

<!-- nex:fails exit=5 -->
```nex
fn divide(a: Float, b: Float) -> Float {
    requires b != 0.0
    return a / b
}

fn main() -> Void {
    print(divide(1.0, 0.0))
}
```

```text
contract error[E4001]: Precondition violated
 --> program.nex:7:11
  |
7 |     print(divide(1.0, 0.0))
  |           ^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'divide'
  = note: The condition at line 2 is false: requires b != 0.0
  = note: It was called with: a = 1.0, b = 0.0

error: program.nex: the program stopped because a contract was broken
```

Si evaluar la condición produce por sí mismo un error de ejecución (por ejemplo, una división por
cero dentro de la condición), el error que se comunica es ese (`E3xxx`), no una violación de
contrato.

### 9.3 Garantías que **no** ofrece

- **No hay verificación estática de contratos.** `nex check` comprueba los tipos de las
  condiciones, no que se cumplan. Un programa que pasa `nex check` puede incumplir un contrato al
  ejecutarse. `nex check` nunca afirma que un contrato se cumple.
- Un contrato solo se comprueba **en las llamadas que realmente se ejecutan**. Un contrato que
  ninguna ejecución ha incumplido no está demostrado.
- No se comprueba que las condiciones sean "puras": una condición puede llamar a una función que
  use `print`.
- Los contratos no se pueden desactivar: se comprueban siempre.

Desde la versión 0.3 la sintaxis de los contratos es estable: las cláusulas van al principio del
cuerpo, el valor devuelto se llama `result` y la explicación va tras una coma. Los motivos están en
la [decisión 0007](decisions/0007-contratos-estables-y-tipos-refinados.md).

### 9.4 Ejemplos (`example`)

Un ejemplo es una cláusula más del principio del cuerpo, junto a `requires` y `ensures`: dice qué
resultado concreto da la función con unas entradas concretas. La definición completa (estados,
formato del informe, códigos de salida) está en la [decisión 0008](decisions/0008-ejemplos-y-nex-test.md).

```text
fn double(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    example double(2) == 4, "Two doubled"
    return n * 2
}
```

- La expresión es de tipo `Bool` (`E2011`) y puede llevar su explicación tras una coma.
- **Tiene que contener una llamada propia**: una llamada a su función escrita en la propia expresión
  (`double(2)`, también anidada, como en `double(double(1))`). Sin ella, `E2020`. Una llamada que
  solo ocurre dentro de otra función no cuenta.
- No ve los parámetros ni `result` (`E2005`): sus entradas y el resultado esperado se escriben como
  valores. Puede usar cualquier función del programa, las integradas y comprobaciones `Tipo(x)`.
- **El análisis nunca evalúa un ejemplo.** `nex check`, `nex inspect`, `nex context` y `nex symbols`
  comprueban que esté bien escrito y nada más; las llamadas de un ejemplo no forman parte del grafo
  de llamadas de la función. `nex run` los ignora.
- **Solo `nex test` los evalúa**, cada uno en un intérprete nuevo, comprobando los contratos de todas
  las funciones que se ejecutan. Un ejemplo termina en `passed` (vale `true`), `failed` (vale
  `false`: `E4004`, categoría `test`) o `error` (un error de ejecución o una regla incumplida, que
  conserva su código y gana una nota con el ejemplo que lo provocó).

### 9.5 Bucles: `while`, `invariant` y `decreases`

Un bucle repite su cuerpo mientras su condición es `true`. Como una función, declara al principio
de su cuerpo los requisitos que lo hacen correcto, y el intérprete los comprueba en cada vuelta
([decisión 0010](decisions/0010-var-y-while.md)):

<!-- nex:run -->
```nex
fn sum_to(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    ensures result == n * (n + 1) / 2
    var total = 0
    var i = 0
    while i < n {
        invariant total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        decreases n - i, "Each turn moves i one step closer to n"
        i = i + 1
        total = total + i
    }
    return total
}

fn main() -> Void {
    print(sum_to(10000))
}
```

```text
50005000
```

| Cláusula | Cuántas | Qué declara | Tipo |
|----------|---------|-------------|------|
| `decreases` | **Exactamente una** | La **medida**: un entero que nunca baja de 0 y disminuye en cada vuelta. Es la razón por la que el bucle termina | `Int` |
| `invariant` | Cero o más | Una condición que se cumple antes de cada evaluación de la condición del bucle: al llegar, después de cada vuelta y, por tanto, al salir | `Bool` |

Reglas:

- **Todo `while` declara su medida.** Sin `decreases`, o con más de una, es el error `E2021`.
- La condición del bucle es `Bool` (`E2011`), y la medida, `Int` (`E2011`).
- Las cláusulas ven lo que es visible donde está el bucle (parámetros, `let`, `var`), no lo que
  declara su cuerpo. Llevan una explicación opcional tras una coma, como los contratos.
- Cada vuelta abre un ámbito nuevo: lo declarado en el cuerpo existe solo durante esa vuelta. Lo que
  tiene que sobrevivir entre vueltas se declara con `var` antes del bucle.
- Un `return` dentro del cuerpo termina la función.
- Las vueltas no son llamadas: el bucle no añade una llamada y no consume el límite de 1000, aunque
  las llamadas dentro del cuerpo sí cuentan.
- No existen `break` ni `continue` (siguen reservadas).

Cada vez que se ejecuta un bucle:

1. Se comprueban los `invariant`, en orden. Uno falso detiene el programa: **`E4005`**.
2. Se evalúa la condición. Si es `false`, el bucle termina.
3. Se evalúa la medida. Si es negativa, o no es estrictamente menor que en la vuelta anterior de esa
   misma ejecución del bucle, el programa se detiene: **`E4006`**.
4. Se ejecuta el cuerpo y se vuelve al paso 1.

Así, **todo bucle termina, o se detiene con un diagnóstico que dice por qué no lo hacía**: una medida
entera que no baja de 0 no puede disminuir para siempre. No hay límites de tiempo: el mismo programa
da siempre el mismo resultado. El diagnóstico dice en qué vuelta ocurrió y con qué valores:

<!-- nex:fails exit=5 -->
```nex
fn count_even(limit: Int) -> Int {
    var i = 0
    var even = 0
    while i < limit {
        decreases limit - i, "Each turn moves i one step closer to limit"
        if i / 2 * 2 == i {
            even = even + 1
            i = i + 1
        }
    }
    return even
}

fn main() -> Void {
    print(count_even(10))
}
```

```text
contract error[E4006]: Loop measure did not decrease
 --> program.nex:5:19
  |
5 |         decreases limit - i, "Each turn moves i one step closer to limit"
  |                   ^^^^^^^^^ The measure was 9 and is still 9
  = note: The measure at line 5: decreases limit - i
  = note: Reason: Each turn moves i one step closer to limit
  = note: Before turn 3 of the loop at line 4.
  = note: The values: limit = 10, i = 1, even = 1
  = note: In 'count_even', called at line 15, column 11.

error: program.nex: the program stopped because a contract was broken
```

Cualquier otro error que se produzca dentro de un bucle (`E3xxx`, `E4xxx`) gana una nota por cada
bucle que lo contiene, del más interior al más exterior: `In turn 3 of the loop at line 6.`

**Lo que no garantiza.** Que un bucle termine pronto: una medida inicial de mil millones permite mil
millones de vueltas. Que la medida y los invariantes sean los adecuados: se comprueba lo escrito, en
las vueltas que se ejecutan. Nada de esto se demuestra sin ejecutar.

### 9.6 Bucles `for` sobre listas

Un `for` recorre una lista inmutable y declara el nombre que toma cada elemento. La parte
implementada la acepta la [decisión 0013](decisions/0013-listas-y-for.md); la
[0012](decisions/0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) sigue siendo la
propuesta para el resto:

<!-- nex:run -->
```nex
fn total(xs: List[Int]) -> Int {
    var sum = 0
    for x in xs {
        invariant sum >= 0, "The total is never negative"
        sum = sum + x
    }
    return sum
}

fn main() -> Void {
    print(total([1, 2, 3, 4]))
}
```

```text
10
```

La lista se escribe con corchetes y su tipo dice el tipo de los elementos: `[1, 2, 3]` es
`List[Int]`. Una lista no cambia: `List.append(xs, x)` y `List.concat(xs, ys)` construyen una lista
nueva. La sintaxis y los literales están en la sección 4.5, y las funciones en la 8.2.

Reglas:

- **El iterable se evalúa una vez**, antes de la primera comprobación de invariantes y de cualquier
  vuelta, y debe ser `List[T]` (`E2011`). No se recorre un `Text` ni un `Int`, y no hay `for` sobre
  rangos. Una lista vacía literal como iterable (`for x in []`) no tiene tipo esperado y es `E2011`;
  para recorrer una lista vacía se usa una variable anotada:
  `let xs: List[Int] = []` y `for x in xs`.
- **El iterador es inmutable y de tipo `T`.** Se declara en el mismo `for`, no antes, y no puede
  recibir un valor nuevo (`E2007`). Tampoco puede ocultar un nombre visible (`E2006`). No es visible
  después del bucle. Cada vuelta abre un entorno nuevo: lo que el cuerpo declara existe solo durante
  esa vuelta, y las asignaciones a una `var` exterior sí se conservan.
- **No lleva `decreases`.** La lista es finita por construcción; un `decreases` en un `for` es el
  error `E2022`. Un `for` puede declarar cero o más `invariant`, con la misma semántica que en un
  `while`: se comprueban antes de cada vuelta y una vez después de la última. En una lista vacía se
  comprueba una vez, antes de la primera vuelta que no llega a ejecutarse; no hay una comprobación
  adicional separada. Un invariante debe ser `Bool` (`E2011`) y, si es falso, el programa se detiene
  con `E4005`.
- Las cláusulas ven lo que es visible donde está el `for`, nunca el iterador.
- Un `return` dentro del cuerpo termina la función. El análisis de rutas no considera que un `for`
  siempre devuelve, aunque todas sus vueltas contengan un `return`: si el bucle es la última
  sentencia, la función necesita un `return` después.
- No hay `break` ni `continue`: siguen reservadas (`E1103`).
- Las vueltas no son llamadas: el bucle no añade una llamada y no consume el límite de 1000, aunque
  las llamadas dentro del cuerpo sí cuentan.

**Lo que no garantiza.** Que el cuerpo termine pronto: una lista enorme tarda lo que tarda. El
playground impone un tiempo máximo; `nex run` no. Que los invariantes sean los adecuados: se
comprueban al ejecutar las vueltas que ocurren, no se demuestran.

## 10. Errores: antes de ejecutar y durante la ejecución

### 10.1 Etapas

La herramienta procesa un programa en cuatro etapas. Cada una solo se realiza si la anterior no
encontró errores:

| Etapa | Qué hace | Categoría de sus errores |
|-------|----------|--------------------------|
| 1. Análisis léxico | Divide el texto en tokens | `lexical` |
| 2. Análisis sintáctico | Construye el árbol de sintaxis (AST) | `syntax` |
| 3. Análisis estático | Comprueba nombres, ámbitos, tipos y rutas de retorno | `semantic`, `type` |
| 4. Ejecución | Recorre el AST | `runtime`, `contract`; con `nex test`, también `test` |

`nex check` y `nex inspect` realizan las etapas 1 a 3 y **no ejecutan el programa**: ninguna
sentencia ni ninguna función se ejecuta. Lo único que la etapa 3 evalúa son las condiciones de los
tipos refinados sobre las constantes escritas en el código (sección 4.4). Esas condiciones solo
pueden usar `value`, literales, operadores y conversiones integradas, no llaman a funciones del
programa, y el trabajo total está acotado (`E2019`). Tampoco evalúan los ejemplos (sección 9.4).
`nex run` realiza las cuatro etapas, y nunca inicia un programa que tenga algún error de las etapas
1 a 3. `nex test` también, pero en la etapa 4 evalúa los ejemplos en lugar de `main`, y en la etapa 3
no exige `main`.

### 10.2 Lo que se detecta antes de ejecutar

Todo lo siguiente lo comunica `nex check`, sin ejecutar una sola sentencia:

- Caracteres, números, textos y escapes mal escritos.
- Código que no sigue la gramática.
- Ausencia de `main`, funciones duplicadas, parámetros o declaraciones no válidas.
- Nombres que no existen, nombres declarados dos veces, asignaciones a variables `let`, a
  parámetros o al iterador de un `for`.
- Llamadas a funciones inexistentes o con un número de argumentos incorrecto.
- **Todos los errores de tipos**: anotaciones, asignaciones, operadores, argumentos, valores de
  retorno, condiciones, condiciones de contratos y de bucles, medidas y uso de `Void` como valor.
- Bucles `while` sin medida, o con más de una, y un `decreases` en un `for`.
- Declaraciones de tipos refinados mal formadas, y **toda constante que no cumple la condición del
  tipo refinado donde se usa** (`E2017`).
- Funciones que pueden terminar sin `return`, y código inalcanzable tras un `return`.
- Valores calculados y nunca usados.

### 10.3 Lo que solo puede detectarse al ejecutar

Estas propiedades dependen de los valores calculados y **no se comprueban estáticamente**; el
análisis estático no afirma nada sobre ellas:

| Error | Código |
|-------|--------|
| División por cero | `E3001` |
| Resultado `Int` fuera de rango | `E3002` |
| Resultado `Float` fuera de rango | `E3003` |
| Más de 1000 llamadas anidadas (recursividad sin fin) | `E3004` |
| `to_int` de un valor que no cabe en un `Int` | `E3005` |
| Un `Text` más largo que el límite del entorno, si este fija uno | `E3006` |
| El programa agota la memoria disponible | `E3007` |
| Condición `requires` falsa, también la de una función de un tipo (`Text.slice`, `Int.parse`, `List.get`…, sección 8) | `E4001` |
| Condición `ensures` falsa | `E4002` |
| Un valor comprobado con `Percent(x)` que no cumple la condición de su tipo | `E4003` |
| Un `invariant` falso | `E4005` |
| Una medida (`decreases`) negativa o que no disminuye | `E4006` |

El análisis no decide si un programa termina. Al ejecutarse, una recursividad sin fin se detiene con
`E3004` y un bucle sin fin, con `E4006`.

Estos son los **únicos** errores que puede producir la ejecución de un programa aceptado por
`nex check`. Cuando se produce uno, el programa se detiene en ese punto: la salida ya escrita se
conserva y no se ejecuta nada más.

## 11. Diagnósticos

Todo error tiene un código estable, una categoría, un título fijo, una explicación concreta y,
cuando existe, la posición exacta en el archivo. Las líneas y las columnas empiezan en 1; la
columna cuenta caracteres (no bytes) y una tabulación cuenta como una columna.

### 11.1 Formato de texto

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let age: Int = "twenty"
}
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

- La primera línea es `<categoría> error[<código>]: <título>`.
- La explicación concreta va junto al marcador `^`, que subraya el fragmento afectado.
- Las líneas `= note:` dan información relacionada (dónde se declaró algo, la firma de una
  función, la cadena de llamadas).
- La línea `= hint:` sugiere una corrección. **Solo aparece cuando existe una regla que la
  fundamenta**: una conversión que existe entre esos dos tipos, un nombre declarado muy parecido al
  escrito, o la forma correcta de una construcción. Si no la hay, no se sugiere nada.

Los mensajes están en inglés. Un mismo archivo puede producir varios diagnósticos en una sola
pasada: tras un error de sintaxis el analizador continúa en la sentencia o función siguiente, y el
análisis estático comunica todos los errores independientes que encuentra. Cada etapa comunica
como máximo 100 errores por archivo; al alcanzar ese número se detiene, y el resumen final del
comando lo indica.

La última línea que escriben `nex check` y `nex run` cuando hay errores (`error: archivo: …`) es
un resumen del comando, no un diagnóstico.

### 11.2 Categorías

| Categoría | Significado | Se detecta |
|-----------|-------------|------------|
| `file` | El archivo no pudo cargarse | Antes de analizar |
| `lexical` | El texto contiene algo que no es un token del lenguaje | Sin ejecutar |
| `syntax` | Los tokens no siguen la gramática | Sin ejecutar |
| `semantic` | Nombres, ámbitos o estructura del programa | Sin ejecutar |
| `type` | Tipos | Sin ejecutar |
| `runtime` | Depende de los valores calculados | Al ejecutar |
| `contract` | Una regla que el programa declara se incumplió: `requires`, `ensures`, la condición de un tipo refinado, un `invariant` o una medida | Al ejecutar |
| `test` | Un ejemplo evaluado por `nex test` resultó falso | Al ejecutar `nex test` |

### 11.3 Códigos de error

Un código nunca cambia de significado. Si deja de usarse se retira, no se reutiliza.

| Código | Título | Categoría | Cuándo aparece |
|--------|--------|-----------|----------------|
| `E0001` | Cannot read file | `file` | El archivo no existe o no puede leerse |
| `E0002` | File is not valid UTF-8 | `file` | El archivo no está codificado en UTF-8 |
| `E1001` | Unexpected character | `lexical` | Un carácter que no pertenece al lenguaje (`;`, `'`, `!`, `@`…) |
| `E1002` | Unterminated string | `lexical` | Un texto sin comilla de cierre en su línea |
| `E1003` | Invalid escape sequence | `lexical` | Un escape desconocido, como `\q` |
| `E1004` | Invalid number literal | `lexical` | Número mal escrito o fuera de rango: `007`, `1_`, `12abc` |
| `E1005` | Unescaped '{' in string | `lexical` | Una `{` sin escapar dentro de un texto |
| `E1101` | Unexpected token | `syntax` | El código no sigue la gramática; el mensaje dice qué se esperaba |
| `E1102` | Unclosed block | `syntax` | Falta una `}` al llegar al final del archivo |
| `E1103` | Reserved word | `syntax` | Se usa una palabra reservada para una versión futura |
| `E1105` | Expression too deeply nested | `syntax` | Se superan los límites de anidamiento de la sección 3 |
| `E1106` | Misplaced contract clause | `syntax` | `requires`, `ensures` o `example` fuera del principio del cuerpo de una función, o `invariant` o `decreases` fuera del principio del cuerpo de un bucle |
| `E2001` | Missing main function | `semantic` | El programa no declara `main` |
| `E2002` | Duplicate function | `semantic` | Dos funciones con el mismo nombre, o con el de una integrada |
| `E2004` | Invalid return type | `type` | `main` declara un tipo de retorno distinto de `Void` |
| `E2005` | Unknown variable | `semantic` | Se usa un nombre que no está declarado o no es visible |
| `E2006` | Name already declared | `semantic` | Se declara un nombre que ya es visible, o el de una función |
| `E2007` | Cannot reassign variable | `semantic` | Se intenta dar un valor nuevo a una variable declarada con `let`, a un parámetro o al iterador de un `for` |
| `E2008` | Unknown function | `semantic` | Se llama a una función que no existe |
| `E2009` | Wrong number of arguments | `type` | Una llamada no pasa tantos argumentos como parámetros hay |
| `E2010` | Unused value | `semantic` | Un valor calculado que se pierde |
| `E2011` | Type mismatch | `type` | Un tipo no es el que exige la regla correspondiente |
| `E2012` | Invalid type | `type` | Un nombre que no es un tipo, `List` sin argumento, `Void` donde hace falta un tipo de valor, o un argumento de tipo que no existe |
| `E2013` | Invalid parameter | `semantic` | `main` con parámetros, o un parámetro llamado `result` |
| `E2014` | Missing return | `semantic` | Una función que devuelve un valor puede terminar sin `return` |
| `E2015` | Unreachable code | `semantic` | Código situado después de un `return` |
| `E2016` | Invalid type declaration | `semantic` | Un tipo refinado con nombre en minúscula, repetido o de un tipo integrado, una cadena de tipos sin fin, o una base que es una lista. También un registro con nombre inválido o repetido, un campo repetido, o un registro que se contiene a sí mismo |
| `E2017` | Value outside refined type | `type` | Una constante usada como valor de un tipo refinado no cumple su condición |
| `E2018` | Invalid refinement condition | `semantic` | La condición de un tipo refinado llama a una función del programa o comprueba otro tipo refinado |
| `E2019` | Too many refinement checks | `semantic` | Comprobar las constantes contra sus tipos refinados supera el límite de trabajo del análisis (sección 4.4) |
| `E2020` | Example without its function | `semantic` | Un ejemplo no contiene ninguna llamada a su función (sección 9.4) |
| `E2021` | Missing loop measure | `semantic` | Un `while` sin `decreases`, o con más de uno (sección 9.5) |
| `E2022` | Unsupported loop clause | `semantic` | Un `decreases` en un `for`, que no lo admite (sección 9.6) |
| `E2023` | Invalid record construction | `type` | Una construcción de un registro a la que le falta un campo, le sobra uno o se le da dos veces el mismo (sección 4.6) |
| `E2024` | Invalid field access | `type` | Se lee un campo de un valor que no es un registro, o de un registro que no tiene ese campo (sección 4.6) |
| `E2025` | Cannot reassign a field | `semantic` | Se asigna a un campo de un registro, que es inmutable (sección 4.6) |
| `E3001` | Division by zero | `runtime` | División por cero |
| `E3002` | Integer overflow | `runtime` | Un resultado `Int` fuera del rango de 64 bits |
| `E3003` | Float result out of range | `runtime` | Un resultado `Float` demasiado grande |
| `E3004` | Too many nested calls | `runtime` | Más de 1000 llamadas anidadas |
| `E3005` | Conversion out of range | `runtime` | `to_int` de un `Float` que no cabe en un `Int` |
| `E3006` | Text too long | `runtime` | Un `Text` construido con `+` supera el límite fijado por el entorno. `nex run` no fija ninguno; el playground sí |
| `E3007` | Out of memory | `runtime` | El programa agota la memoria mientras se ejecuta. Sin posición ([decisión 0009](decisions/0009-memoria-agotada.md)) |
| `E4001` | Precondition violated | `contract` | Una condición `requires` es falsa en una llamada |
| `E4002` | Postcondition violated | `contract` | Una condición `ensures` es falsa al terminar una función |
| `E4003` | Refinement violated | `contract` | Un valor comprobado con `Tipo(x)` no cumple la condición del tipo refinado |
| `E4005` | Loop invariant violated | `contract` | Un `invariant` es falso antes de una vuelta o después de la última de su bucle (sección 9.5 y 9.6) |
| `E4006` | Loop measure did not decrease | `contract` | La medida de un bucle es negativa o no es menor que en la vuelta anterior (sección 9.5) |
| `E4004` | Example failed | `test` | Un ejemplo evaluado por `nex test` vale `false` (sección 9.4) |

Códigos retirados (existieron en la versión 0.1 y ya no se emiten):

| Código retirado | Título | Motivo |
|-----------------|--------|--------|
| E1104 | Unsupported syntax | Avisaba de que los parámetros y las anotaciones de tipo no existían; ahora existen |
| E2003 | Unsupported function declaration | Avisaba de que solo podía declararse `main`; ahora se admiten funciones propias |

### 11.4 Formato JSON

`nex check archivo.nex --format json` escribe un único documento JSON en la salida estándar.
`nex run archivo.nex --format json` escribe el mismo documento en la salida de error, solo si el
programa es inválido o falla.

Para el programa de la sección 11.1:

<!-- nex:check-json -->
```nex
fn main() -> Void {
    let age: Int = "twenty"
}
```

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.8.0",
  "file": "program.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "category": "type",
      "code": "E2011",
      "message": "Type mismatch",
      "label": "Expected Int, found Text",
      "hint": null,
      "notes": [
        "'age' is declared as Int."
      ],
      "file": "program.nex",
      "line": 2,
      "column": 20,
      "end_line": 2,
      "end_column": 28
    }
  ]
}
```

| Campo | Tipo | Significado |
|-------|------|-------------|
| `schema` | texto | Nombre y versión del formato |
| `file` | texto | El archivo analizado, tal como se pasó al comando |
| `ok` | booleano | `true` si no hay diagnósticos |
| `diagnostics` | lista | Los diagnósticos, en el orden en que se encontraron |
| `severity` | texto | Siempre `"error"` en esta versión |
| `category` | texto | Una de las categorías de la sección 11.2 |
| `code` | texto | Código estable (sección 11.3) |
| `message` | texto | Título fijo del código |
| `label` | texto | Explicación concreta de este caso |
| `hint` | texto o `null` | Corrección sugerida, si existe una fundamentada |
| `notes` | lista de textos | Información relacionada |
| `line`, `column` | número o `null` | Inicio del fragmento señalado |
| `end_line`, `end_column` | número o `null` | Final del fragmento (columna final excluida) |

Los cuatro campos de posición son `null` cuando el diagnóstico no se refiere a un punto del archivo
(por ejemplo, `E2001`). El número de versión de `schema` solo cambia si un campo se elimina, se
renombra o cambia de significado; añadir campos no lo cambia.

La representación del programa (`nex inspect`) está descrita en
[`inspect-schema.md`](inspect-schema.md).

### 11.5 Códigos de salida de `nex`

| Código | Significado |
|--------|-------------|
| `0` | Correcto |
| `1` | El programa tiene errores léxicos, sintácticos, semánticos o de tipos |
| `2` | Uso incorrecto de la línea de comandos |
| `3` | El programa falló durante la ejecución |
| `4` | El archivo no pudo leerse |
| `5` | El programa incumplió durante la ejecución una regla que declara: un contrato, la condición de un tipo refinado, un invariante o la medida de un bucle |
| `6` | `nex test`: algún ejemplo no pasó, o no había ningún ejemplo que evaluar |
| `70` | Error interno de NEXORA (un fallo de la herramienta, no del programa). Un programa que agota la memoria al ejecutarse no da `70`, sino el diagnóstico `E3007` ([decisión 0009](decisions/0009-memoria-agotada.md)) |
| `130` | Interrumpido con Ctrl+C |

Los comandos, sus opciones y sus formatos de salida están descritos en la
[referencia de la CLI](cli-reference.md).

## 12. Ejemplos

Los programas de esta sección, y los de las secciones anteriores que incluyen una función `main`,
se ejecutan en las pruebas automatizadas; la salida mostrada es la real.

### 12.1 Programas válidos

<!-- nex:run -->
```nex
fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn main() -> Void {
    let result: Int = add(2, 3)
    print(result)
}
```

```text
5
```

<!-- nex:run -->
```nex
fn factorial(n: Int) -> Int {
    requires n >= 0
    ensures result >= 1
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}

fn main() -> Void {
    let n = 10
    print("factorial: " + to_text(factorial(n)))
    print(to_float(n) / 4.0)
    print(n > 5 and not (n == 7))
}
```

```text
factorial: 3628800
2.5
true
```

En [`examples/`](../examples/README.md) hay más programas, todos ejecutados por las pruebas:

| Archivo | Qué muestra | `nex run` termina con |
|---------|-------------|-----------------------|
| `hello.nex` | El primer programa | `0` |
| `variables.nex` | Variables, textos, bloques y ámbitos | `0` |
| `arithmetic.nex` | Precedencia, división entera y decimal, límites de `Int` | `0` |
| `types.nex` | Inferencia, anotaciones, comparaciones, lógica y conversiones | `0` |
| `functions.nex` | Funciones, `if`/`else`, recursividad | `0` |
| `contracts.nex` | Contratos que se cumplen | `0` |
| `loops.nex` | Variables `var` y bucles con su medida y sus invariantes | `0` |
| `lists.nex` | Listas inmutables `List[T]`, sus funciones y un `for` con invariantes | `0` |
| `invalid/syntax_error.nex` | Errores de sintaxis (incorrecto a propósito) | `1` |
| `invalid/name_errors.nex` | Errores de nombres y estructura (incorrecto a propósito) | `1` |
| `invalid/type_errors.nex` | Errores de tipos (incorrecto a propósito) | `1` |
| `failing/runtime_error.nex` | Un error que solo aparece al ejecutar | `3` |
| `failing/contract_violation.nex` | Un contrato incumplido al ejecutar | `5` |
| `failing/loop_measure.nex` | Un bucle que no terminaría: su medida deja de disminuir | `5` |

### 12.2 Programas inválidos

| Código | Error | Motivo |
|--------|-------|--------|
| `let = "Hello"` | `E1101` | Falta el nombre de la variable |
| `let x = (1 + 2` | `E1101` | Falta `)` |
| `let x = 1; let y = 2` | `E1001` | `;` no existe en el lenguaje |
| `let x = 1 < 2 < 3` | `E1101` | Las comparaciones no se encadenan |
| `break` | `E1103` | `break` es una palabra reservada |
| `for x in 3 { }` | `E2011` | Un `for` solo recorre una `List[T]` |
| `for x in xs { decreases 1 }` | `E2022` | Un `for` no lleva medida |
| `for x in xs { x = 1 }` | `E2007` | El iterador de un `for` es inmutable |
| `print(total)` sin declarar `total` | `E2005` | Variable desconocida |
| `let x = 1` y después `let x = 2` | `E2006` | El nombre ya está declarado |
| `let x = 1` y después `x = 2` | `E2007` | Una variable `let` no cambia; se declara con `var` |
| `while i < n { i = i + 1 }` | `E2021` | Falta la medida: `decreases n - i` |
| `let age: Int = "twenty"` | `E2011` | Se esperaba `Int` y el valor es `Text` |
| `let total = 10 + 2.5` | `E2011` | `Int` y `Float` no se mezclan |
| `let ok = true + 1` | `E2011` | Un `Bool` no admite aritmética |
| `let same = 1 == 1.0` | `E2011` | Solo se comparan valores del mismo tipo |
| `let xs = []` | `E2011` | Una lista vacía necesita un tipo esperado |
| `let xs = [1, "a"]` | `E2011` | Todos los elementos de una lista tienen el mismo tipo |
| `let xs: List[Int] = [1]` y `let ys: List[Text] = xs` | `E2011` | Los argumentos de `List` son invariantes |
| `if count { }` con `count` de tipo `Int` | `E2011` | La condición debe ser `Bool` |
| `let x: String = "a"` | `E2012` | El tipo se llama `Text` |
| `let xs: List = []` | `E2012` | `List` necesita un argumento de tipo |
| `type NonEmpty = List[Int] where value == value` | `E2016` | Un tipo refinado no puede tener una lista como base |
| `type Point = { x: Int, y: Int }` y `Point(x: 1)` | `E2023` | Falta el campo `y` |
| `type Point = { x: Int }` y `Point(x: 1, y: 2)` | `E2023` | El registro no tiene ningún campo `y` |
| `type Point = { x: Int }` y `Point(x: 1, x: 2)` | `E2023` | El campo `x` está dado dos veces |
| `type Point = { x: Int }` y `Point(x: "a")` | `E2011` | El campo `x` es de tipo `Int` |
| `type Point = { x: Int }` y `let p = Point(x: 1)` y después `p.y` | `E2024` | El registro no tiene ningún campo `y` |
| `type Point = { x: Int }` y `let p = Point(x: 1)` y después `p.x = 2` | `E2025` | Un registro es inmutable |
| `type A = { a: A }` | `E2016` | Un registro no puede contenerse a sí mismo |
| `add(1)` con `add(a: Int, b: Int)` | `E2009` | Falta un argumento |
| `add(1, "2")` | `E2011` | El segundo argumento debe ser `Int` |
| `add(1, 2)` como sentencia | `E2010` | El valor devuelto no se usa |
| `launch()` sin declarar `launch` | `E2008` | La función no existe |
| Una función `-> Int` sin `return` en alguna ruta | `E2014` | Falta un `return` |
| `return "x"` en una función `-> Int` | `E2011` | El valor devuelto no es del tipo declarado |
| `requires n` con `n` de tipo `Int` | `E2011` | La condición de un contrato debe ser `Bool` |
| `print(10 / 0)` | `E3001` | División por cero (se detecta al ejecutar) |
| `divide(1.0, 0.0)` con `requires b != 0.0` | `E4001` | Contrato incumplido (se detecta al ejecutar) |
| `List.get([1, 2], 2)` | `E4001` | Índice fuera de la lista (se detecta al ejecutar) |
| Un archivo sin `fn main` | `E2001` | Falta el punto de entrada |

## 13. Limitaciones conocidas

Son limitaciones reales de esta versión, no fallos:

- Hay dos formas de bucle: `while`, que siempre declara su medida (`decreases`), y `for` sobre una
  `List[T]`, que no la necesita. No hay `break` ni `continue`, ni asignaciones compuestas (`+=`).
- Las listas `List[T]` son inmutables y finitas. No hay sintaxis de índice (`xs[i]`), mutación de
  elementos, `List.set`, `map`, `filter`, ordenación ni una variante total de `List.get`: para leer
  una posición se usa `List.get`, que exige un índice válido y detiene el programa con `E4001` si no
  lo es.
- Todos los elementos de una lista tienen el mismo tipo. `[]` y `for x in []` necesitan un tipo
  esperado (`E2011`). No se puede refinar una lista (`type NonEmpty = List[Int] ...` es `E2016`).
- El análisis de rutas no considera que un `for` siempre devuelve, aunque todas sus vueltas
  contengan un `return`: si el `for` es la última sentencia, la función necesita un `return` después.
- La medida de un `while` es un `Int`: no hay medidas compuestas (pares, textos).
- Los parámetros no pueden reasignarse.
- `if` es una sentencia, no una expresión: no puede usarse como valor.
- No hay mapas, enumeraciones, `Option`, `Result` ni `for` sobre rangos o `Text`. Los registros
  (sección 4.6) tienen campos inmutables y no admiten métodos, refinamientos ni recursión. Las
  listas `List[T]` son inmutables y finitas. Los registros tienen una
  [decisión 0014](decisions/0014-registros-nominales-inmutables.md) aceptada que todavía no está
  implementada.
- Las operaciones sobre textos son las de la sección 8.1: no hay `trim`, mayúsculas, `split`,
  `replace` ni búsqueda de posiciones. Un carácter es un punto de código: no se cuentan grafemas.
- No hay operador de resto (`%`).
- Los requisitos de las funciones de un tipo se comprueban al ejecutar, como los del programa:
  `nex check` no avisa de que `Text.slice("abc", 0, 5)` va a fallar.
- No hay interpolación de textos, textos de varias líneas ni comentarios de bloque.
- Los literales solo admiten notación decimal: no hay hexadecimal ni exponentes (`1e-3`).
- El entero mínimo `-9223372036854775808` no puede escribirse como literal. Sí puede obtenerse:
  `-9223372036854775807 - 1`.
- Una variable o un parámetro declarados y nunca usados no producen ningún aviso.
- No existen avisos (*warnings*): todo diagnóstico es un error.
- `print` recibe un solo argumento y siempre añade un salto de línea.
- El programa no puede leer datos de entrada (teclado, argumentos o archivos).
- Un programa es un único archivo: no hay módulos ni importaciones.
- Los contratos no se verifican estáticamente (sección 9.3). De los tipos refinados, solo se
  comprueban sin ejecutar las constantes.
- La condición de un tipo refinado no puede llamar a funciones del programa.
- No hay alias de tipos sin condición (`type Id = Int`): un tipo refinado siempre lleva `where`. Un
  registro (sección 4.6) se declara sin `where`, porque sus campos no llevan condición.
- `nex inspect` solo tiene salida JSON, y no muestra el árbol si el programa tiene errores léxicos
  o sintácticos.
- No hay formateador, servidor de lenguaje ni otras herramientas.

La lista completa, con los límites de la implementación y los riesgos conocidos, está en
[Limitaciones](limitations.md).

## 14. Funcionalidades previstas (no implementadas)

Nada de lo que sigue funciona hoy. Es la dirección del diseño, tomada del borrador
`docs/fase-1-diseno.md` de la raíz del repositorio, y puede cambiar:

- `for` sobre rangos, `break` y `continue`.
- `if` y `match` como expresiones.
- Interpolación de textos (`"Hello {name}"`), para la que ya está reservada la `{`.
- Mapas, enumeraciones, `Option` y `Result`. Los registros (sección 4.6) y las listas `List[T]`
  ya existen, pero no los genéricos de usuario (`fn f[T]`), las funciones de orden superior ni las
  funciones como valores.
- Verificación estática de contratos, y bloques de prueba (`test`) fuera de las funciones.
- Efectos declarados (`uses`), módulos e importaciones.
- Características relacionadas con IA (`ai fn`, `tool fn`). No existe ninguna integración con
  modelos de IA: lo que hay son las representaciones estructuradas (`nex inspect`, diagnósticos en
  JSON) que una herramienta externa podría consumir.

### Diferencias con el borrador de diseño

Esta especificación manda sobre el borrador en lo que ya está implementado:

| Aspecto | Borrador `fase-1-diseno.md` | Esta especificación |
|---------|-----------------------------|---------------------|
| Extensión de archivo | `.nx` | `.nex` |
| Tipo de texto | `String` | `Text` |
| Tipo "sin valor" | `Unit` | `Void` |
| Concatenar textos | No permitido; se usa interpolación | `+` une dos `Text`, porque la interpolación aún no existe |
| Valor de una función | La última expresión del bloque | Siempre con `return` |
| Contratos | Entre la firma y el cuerpo | Al principio del cuerpo, con una explicación opcional tras una coma |
| Ejemplos | `example` entre la firma y el cuerpo; `nexora test` | Al principio del cuerpo, con las mismas reglas que los contratos; `nex test` |
| Valor dinámico a tipo refinado | `Percent.from(n)`, que devuelve un `Result` | `Percent(n)`, que detiene el programa con `E4003` si no se cumple la condición (no existe `Result`) |
| Alias sin condición | `type UserId = Int` | No existen |
| Conversión entre números | `Int.to_float(x)` | `to_float(x)`, `to_int(x)` |
| Variables sin usar | Son un error | No se comprueba todavía |
| Bucles | `while` y `for`, sin requisitos | `while` con medida obligatoria (`decreases`) y `for` sobre `List[T]`; ambos con invariantes opcionales, comprobados en cada vuelta |
| Convenciones de nombres | Obligatorias (`snake_case`…) | No se comprueban todavía |
