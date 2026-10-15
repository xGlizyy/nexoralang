# 0011 — Operaciones sobre textos: funciones asociadas a un tipo que declaran sus requisitos

- **Estado:** aceptada
- **Versión:** 0.6.0
- **Relacionada con:** la [decisión 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (sin
  conversiones implícitas), la [0003](0003-funciones-retorno-e-if.md) (un único espacio de nombres),
  la [0004](0004-contratos-en-ejecucion.md) (`requires` comprobado en ejecución), la
  [0005](0005-diagnosticos-y-esquemas-json.md) (esquemas JSON versionados), la
  [0006](0006-requisitos-verificables.md) (la línea principal), la
  [0007](0007-contratos-estables-y-tipos-refinados.md) (tipos refinados) y la
  [0010](0010-var-y-while.md) (notas de bucle). **No modifica ninguna.**

## Contexto

Es el primer punto de "Planificado" en la [hoja de ruta](../roadmap.md): "Operaciones sobre textos:
longitud, comparación de orden, conversión de texto a número". Hoy un `Text` solo se puede unir con
`+`, comparar con `==` y `!=`, y obtener con `to_text`.

| Necesidad | Hoy | Problema |
|-----------|-----|----------|
| Saber si un texto está vacío o es demasiado largo | Solo comparando con `""` | Un tipo refinado no puede decir que un texto tiene como mucho 20 caracteres |
| Ordenar o comparar dos nombres | `<` sobre `Text` es `E2011` | — |
| Leer un número escrito en un texto | Imposible | Cuando haya entrada de datos (punto 4 de "Planificado") todo llegará como texto |
| Quedarse con una parte de un texto | Imposible | — |

### Dos problemas que hay que resolver

**Las operaciones que no siempre tienen respuesta.** El trozo de `"abc"` entre las posiciones 2 y 9
no existe, y `"12a"` no es un número. Los lenguajes habituales eligen entre:

| Elección | Ejemplo | Problema |
|----------|---------|----------|
| Inventar una respuesta | `"abc"[2:9]` da `"c"` en Python; `parseInt("12a")` da `12` en JavaScript | El error pasa desapercibido y aparece lejos de su causa |
| Lanzar una excepción | `int("12a")` en Python | La condición que hay que cumplir no está escrita en ninguna parte del programa |
| Devolver un valor opcional | `"12a".parse::<i32>()` en Rust | Exige `Option` o `Result`, que NEXORA todavía no tiene (punto 3 de "Planificado") |

NEXORA ya tiene una forma de decir "esta función solo tiene sentido si…": `requires`. Lo que no
existía es que **las funciones del propio lenguaje** la usaran.

**Los nombres.** NEXORA tiene un único espacio de nombres sin ocultación (decisión 0003, punto 4): una
variable o un parámetro no puede llamarse como una función, tampoco como una integrada (`E2006`). Con
nombres planos como `length`, `slice` o `contains`, que son nombres de variable muy habituales, cada
función nueva prohibiría un nombre, y cada versión que añadiera funciones podría invalidar programas
que hoy son correctos. Además, NEXORA no tiene sobrecarga: `length` no podría servir a la vez para los
textos y para las listas (punto 2 de "Planificado").

## Decisión

### 1. Qué es un `Text`

- **Un `Text` es una secuencia de valores escalares Unicode** (puntos de código de U+0000 a U+10FFFF,
  sin los sustitutos U+D800–U+DFFF). En este documento, "carácter" significa siempre eso.
- **Ningún `Text` puede contener un sustituto aislado.** Un programa se lee como UTF-8 estricto
  (`E0002` si no lo es), los únicos escapes son `\n`, `\t`, `\"`, `\\` y `\{`, y ninguna operación
  de esta decisión puede crear uno: `Text.slice` corta entre caracteres, nunca dentro de uno.
- **No se normaliza nada, nunca.** NEXORA no aplica NFC, NFD ni ninguna otra forma de normalización
  ni al leer el programa, ni al comparar, ni al buscar. Un texto es exactamente la secuencia de
  caracteres escrita o calculada.
- Las posiciones empiezan en 0. Un trozo se indica con su principio incluido y su final excluido.
- No se usan bytes ni unidades UTF-16: ningún resultado depende de cómo guarde el texto la
  implementación.

### 2. Comparar textos

| Operador | Entre dos `Text` | Hoy |
|----------|------------------|-----|
| `==`, `!=` | Igualdad carácter a carácter (sin normalizar) | Ya existe; no cambia |
| `<`, `<=`, `>`, `>=` | **Nuevo**: orden lexicográfico por punto de código | `E2011` |

**El orden exacto.** Para comparar `a` y `b` se recorren a la vez desde la posición 0:

1. En la primera posición en la que difieren, va antes el texto cuyo carácter tiene el punto de código
   más bajo.
2. Si no difieren en ninguna posición del más corto, va antes el más corto. El texto vacío va antes
   que cualquier otro.
3. Si tienen la misma longitud y no difieren, son iguales.

| Expresión | Valor | Por qué |
|-----------|-------|---------|
| `"ab" < "abc"` | `true` | `"ab"` es el principio de `"abc"` |
| `"" < "a"` | `true` | El vacío va antes que cualquier otro |
| `"Z" < "a"` | `true` | `Z` es U+005A y `a` es U+0061 |
| `"z" < "é"` | `true` | `é` (U+00E9) está después de todas las letras ASCII |
| `"10" < "9"` | `true` | Se comparan caracteres, no números: `1` va antes que `9` |
| `"é" == "é"` escritos uno como U+00E9 y otro como `e` + U+0301 | `false` | No se normaliza |

- **No depende del idioma ni de la configuración del sistema**: el mismo programa da el mismo
  resultado en cualquier máquina. No es el orden alfabético de ningún idioma.
- Un `Text` sigue sin poder compararse con otro tipo: `"1" < 2` es `E2011`, con la sugerencia de
  convertir uno de los dos lados.
- Un tipo refinado con base `Text` se compara como su base, como ya ocurre con `==`.

### 3. Funciones asociadas a un tipo: `Tipo.función(…)`

Las funciones nuevas pertenecen a un tipo integrado y se llaman con el nombre del tipo delante:

```text
let size = Text.length(name)
let initials = Text.slice(name, 0, 2)
if Int.can_parse(input) {
    let n = Int.parse(input)
}
```

#### 3.1 La forma

```text
llamada_cualificada = NombreDeTipo "." nombre "(" [ argumentos ] ")"
```

- **Delante del punto va el nombre de un tipo integrado** que tenga funciones: hoy `Text`, `Int` y
  `Float`. `Bool` no tiene ninguna todavía.
- **Detrás va el nombre de una de sus funciones**, y la llamada lleva siempre paréntesis: una función
  no es un valor (decisión 0003, punto 5).
- **Una sola forma de escribirla**: el punto va pegado al nombre del tipo y al de la función, y hay un
  solo punto. `Text . length(t)` y `Text.length.x(t)` son errores de sintaxis. Entre el nombre de la
  función y el `(` puede haber espacios, como en cualquier llamada (`f (1)` ya es válido). Cómo se lee
  el punto, con precisión: sección 3.4.
- El nombre completo de la función es `Text.length`. Así aparece en los diagnósticos, en los
  contratos y en las herramientas.

#### 3.2 Las funciones

| Función | Qué hace | Requisitos (`requires`) |
|---------|----------|-------------------------|
| `Text.length(text: Text) -> Int` | Número de caracteres | Ninguno |
| `Text.slice(text: Text, start: Int, end: Int) -> Text` | Los caracteres desde `start` (incluido) hasta `end` (excluido) | Tres (sección 5.2) |
| `Text.contains(text: Text, part: Text) -> Bool` | Si `part` aparece en `text` | Ninguno |
| `Text.starts_with(text: Text, part: Text) -> Bool` | Si `text` empieza por `part` | Ninguno |
| `Text.ends_with(text: Text, part: Text) -> Bool` | Si `text` termina en `part` | Ninguno |
| `Int.can_parse(text: Text) -> Bool` | Si `text` es un entero escrito según la sección 6 | Ninguno |
| `Int.parse(text: Text) -> Int` | El entero escrito en `text` | `Int.can_parse(text)` |
| `Float.can_parse(text: Text) -> Bool` | Si `text` es un decimal escrito según la sección 6 | Ninguno |
| `Float.parse(text: Text) -> Float` | El decimal escrito en `text` | `Float.can_parse(text)` |

- `Int.parse` y `Float.parse` pertenecen al tipo que **producen**, no al que reciben: se leen como "un
  `Int` a partir de un texto".
- Los argumentos se comprueban sin ejecutar como los de cualquier función (`E2009`, `E2011`). Un
  argumento de un tipo refinado con base `Text` o `Int` se acepta donde se espera su base.
- No hay `trim`, `upper`, `split`, `replace` ni búsqueda de posiciones: `split` necesita listas y el
  resto se decidirá cuando haya programas que lo necesiten.

#### 3.3 Qué no cambia

- **No se reserva ningún nombre.** `let length = Text.length(name)` es válido: `length` sin cualificar
  sigue significando una sola cosa, la variable, y `Text.length` es otra. Un nombre del programa no
  puede contener un punto, así que un nombre cualificado nunca coincide con uno del programa.
- **`Int`, `Float`, `Bool` y `Text` se pueden seguir usando como nombres de variable y de parámetro**,
  como hoy. NEXORA ya distingue tipos y valores por la posición en que aparecen: este programa es
  válido en la 0.5.1 y lo sigue siendo:

  ```text
  fn twice(Text: Int) -> Int {
      return Text * 2
  }
  ```

  La posición delante del punto es una posición de tipo, igual que la de una anotación
  (`let label: Text = "a"`). Como un valor nunca puede ir seguido de un punto, `Text.length(s)`
  significa la función del tipo aunque exista una variable llamada `Text` (sección 9 y prueba 17).
- **La regla del espacio de nombres (decisión 0003) no cambia**: los nombres cualificados no entran en
  el espacio de nombres de funciones, parámetros y variables.
- **`print`, `to_text`, `to_float` y `to_int` siguen como están**, sin cualificar. Convivirán las dos
  formas. Si se añaden equivalentes cualificados, será en otra decisión.

#### 3.4 Cómo se lee el punto

**Analizador léxico.**

1. Los textos y los comentarios se leen como hoy: un `.` dentro de ellos no es un token.
2. Al leer un número, un `.` **seguido de un dígito** forma parte del número decimal, como hoy
   (`1.5`).
3. **Cualquier otro `.` es el token nuevo `DOT`.** Hoy ese mismo `.` es el error léxico `E1001`.
   Ejemplos: el de `Text.length`, el de `1.length` (el `1` es un entero y el `.` un `DOT`), el de `.5` y
   el segundo de `1.5.2`.
4. Como hoy, los saltos de línea dentro de paréntesis no producen token; fuera de ellos, terminan la
   sentencia.

**Analizador sintáctico.** El `DOT` solo es válido en un sitio: en una expresión, entre dos nombres,
como parte de la llamada `nombre DOT nombre "(" … ")"`.

1. El analizador construye esa llamada **siempre que encuentra esa forma**, sin saber todavía si el
   primer nombre es un tipo, una variable o un módulo: `Text.length(s)`, `name.length()` y
   `geometry.area(c)` se analizan igual. Lo que significan lo decide el comprobador.
2. Los dos nombres tienen que tocar el punto: la columna en que acaba el primero es la del punto, y la
   siguiente a la del punto es la del segundo, en la misma línea. Se comprueba con las posiciones de
   los tokens, porque dentro de paréntesis un salto de línea no deja token.
3. **Reparto de los errores.** El analizador sintáctico da `E1101` cuando la **forma** está mal; el
   comprobador da `E2008` cuando la forma es correcta pero el **nombre** no existe o no es un tipo. La
   tabla completa está en la sección 9.

**Programas válidos de la 0.5.1.** Ningún programa válido contiene un `DOT`, porque en la 0.5.1 un `.`
fuera de un número, un texto o un comentario era siempre `E1001`. Su secuencia de tokens, su árbol, su
comprobación y su ejecución no cambian (sección 10). Solo cambian los diagnósticos de programas que ya
eran inválidos.

### 4. Las funciones integradas declaran sus requisitos, en NEXORA

Esto es lo que hace que estas funciones sean de NEXORA y no una copia de las de otro lenguaje.
**Cada función que puede no tener respuesta declara cuándo la tiene, con un `requires` escrito en
NEXORA y con su explicación**, exactamente igual que una función del programa. Son estas, completas:

```text
fn Text.length(text: Text) -> Int
    ensures result >= 0, "A text never has a negative number of characters"

fn Text.slice(text: Text, start: Int, end: Int) -> Text
    requires start >= 0, "A slice cannot start before the first character"
    requires start <= end, "A slice cannot end before it starts"
    requires end <= Text.length(text), "A slice cannot end after the last character"
    ensures Text.length(result) == end - start, "The slice has exactly end - start characters"

fn Int.parse(text: Text) -> Int
    requires Int.can_parse(text), "Only a whole number within the range of Int can be read as an Int"

fn Float.parse(text: Text) -> Float
    requires Float.can_parse(text), "Only a decimal number that fits in a Float can be read as a Float"
```

- Las explicaciones nombran el rango a propósito: `"99999999999999999999"` está escrito como un
  número entero y aun así no puede leerse, porque no cabe en un `Int`. Una explicación que solo
  hablara de la forma sería falsa para ese caso.
- **La notación `fn Text.length(text: Text) -> Int` de este bloque es la forma en que se muestran las
  firmas**, la misma que usan los diagnósticos y `nex symbols`. No es una declaración que un programa
  pueda escribir: un programa no puede declarar funciones de un tipo (sección 9).
- **Las condiciones** (lo que va detrás de `requires` y `ensures`) se escriben en NEXORA y se analizan
  como expresiones con el analizador real al cargar el intérprete.
  Una prueba comprueba que todas tienen tipo `Bool`, que solo usan sus parámetros, `result` (en
  `ensures`) y funciones integradas sin `requires`, y que **ninguna puede fallar al evaluarse**: no
  dividen, no desbordan y solo llaman a `Text.length`, `Int.can_parse` y `Float.can_parse`, que tienen
  respuesta para cualquier texto.
- Quien llama puede trasladar el requisito: `requires Int.can_parse(code)` en una función del programa
  usa la misma condición, y un tipo refinado puede decir
  `type Code = Text where Text.length(value) == 3, "A code has exactly three characters"`.
- Las funciones de antes (`print`, `to_text`, `to_float`, `to_int`) no tienen `requires`, y `to_int`
  sigue dando `E3005` fuera del rango de `Int`.

### 5. Comportamiento exacto de cada función

#### 5.1 `Text.length`, `Text.contains`, `Text.starts_with`, `Text.ends_with`

Cuentan y comparan caracteres (sección 1), sin normalizar y distinguiendo mayúsculas de minúsculas.
Tienen respuesta para cualquier texto, también el vacío.

| Llamada | Valor | Regla |
|---------|-------|-------|
| `Text.length("")` | `0` | |
| `Text.length("año")` | `3` | `ñ` es un carácter |
| `Text.length` de una `e` seguida del acento combinado U+0301 | `2` | Dos caracteres, aunque se vean como uno |
| `Text.length` del emoji de familia 👨‍👩‍👧‍👦 | `7` | Cuatro personas unidas por tres U+200D |
| `Text.contains("hello", "ell")` | `true` | |
| `Text.contains("hello", "")` | `true` | **El texto vacío aparece en cualquier texto**, en cualquier posición |
| `Text.contains("", "")` | `true` | |
| `Text.contains("", "a")` | `false` | |
| `Text.contains("Hello", "hello")` | `false` | Distingue mayúsculas |
| `Text.starts_with("hello", "he")` | `true` | |
| `Text.starts_with("hello", "")` | `true` | Todo texto empieza por el vacío |
| `Text.starts_with("he", "hello")` | `false` | `part` más largo que `text` |
| `Text.ends_with("hello", "lo")` | `true` | |
| `Text.ends_with("hello", "")` | `true` | Todo texto termina en el vacío |
| `Text.ends_with("", "a")` | `false` | |

Equivalencias que se cumplen siempre (con `n = Text.length(t)` y `m = Text.length(p)`):
`Text.starts_with(t, p) == (m <= n and Text.slice(t, 0, m) == p)` y
`Text.ends_with(t, p) == (m <= n and Text.slice(t, n - m, n) == p)`.

#### 5.2 `Text.slice`

`Text.slice(text, start, end)` devuelve los caracteres de las posiciones `start`, `start + 1`, …,
`end - 1`. Sus tres `requires` definen cuándo tiene respuesta:
`0 <= start <= end <= Text.length(text)`. **No hay índices negativos que cuenten desde el final, ni
recortes silenciosos**: fuera de esos límites, la llamada se detiene con `E4001`.

| Llamada | Resultado | Regla |
|---------|-----------|-------|
| `Text.slice("hello", 1, 3)` | `"el"` | Principio incluido, final excluido |
| `Text.slice("hello", 0, 5)` | `"hello"` | El texto entero |
| `Text.slice("hello", 2, 2)` | `""` | `start == end`: trozo vacío |
| `Text.slice("hello", 5, 5)` | `""` | Un trozo vacío al final es válido |
| `Text.slice("", 0, 0)` | `""` | El único trozo del texto vacío |
| `Text.slice("año", 1, 2)` | `"ñ"` | Se cuentan caracteres, no bytes |
| `Text.slice("hello", -1, 2)` | `E4001` | `requires start >= 0` |
| `Text.slice("hello", 3, 1)` | `E4001` | Rango invertido: `requires start <= end` |
| `Text.slice("hello", 0, 6)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("hello", 6, 6)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("", 0, 1)` | `E4001` | `requires end <= Text.length(text)` |
| `Text.slice("hello", -3, -1)` | `E4001` | `requires start >= 0`: no cuenta desde el final |
| `Text.slice("abc", -1, 9)` | `E4001` por `start >= 0` | Si fallan varios, se informa el primero en el orden escrito |

Siempre se cumple `Text.length(Text.slice(t, a, b)) == b - a` y
`Text.slice(t, 0, k) + Text.slice(t, k, Text.length(t)) == t` para todo `k` entre `0` y
`Text.length(t)`.

### 6. Cómo se escribe un número en un texto

#### 6.1 La gramática

Una única forma, sin depender del idioma ni de la configuración del sistema. Todos los caracteres son
ASCII; `dígito` es solo `0`–`9`.

```text
entero    = [ "-" ] dígito { dígito }
decimal   = [ "-" ] dígito { dígito } ( fracción [ exponente ] | exponente )
fracción  = "." dígito { dígito }
exponente = ( "e" | "E" ) [ "+" | "-" ] dígito { dígito }
```

- **`Int.can_parse(t)`** es verdadero si y solo si `t` entero cumple la regla `entero` **y** su valor
  está entre -9223372036854775808 (−2⁶³) y 9223372036854775807 (2⁶³ − 1), ambos incluidos: el rango de
  `Int` (`values.py`, `INT_MIN` e `INT_MAX`; `language-spec.md`, sección 4).
- **`Float.can_parse(t)`** es verdadero si y solo si `t` entero cumple la regla `decimal` **y** su
  valor, redondeado al `Float` más cercano, es finito.
- No se admite **nada** fuera de la gramática: ni espacios (tampoco tabuladores, saltos de línea ni
  espacios no separables) al principio, al final o en medio, ni `+` delante del número, ni `_`, ni
  separadores de miles, ni otra coma decimal, ni dígitos que no sean ASCII, ni prefijos (`0x`, `0b`),
  ni valores especiales (`inf`, `Infinity`, `nan`, `NaN`).
- La longitud del texto no limita nada: se admiten tantos dígitos y ceros a la izquierda como haya.
  Solo cuenta el valor.

#### 6.2 Casos

| Texto | `Int.can_parse` | `Float.can_parse` | Notas |
|-------|-----------------|-------------------|-------|
| `"0"`, `"42"`, `"-7"` | sí | no | |
| `"007"` | sí (7) | no | Ceros a la izquierda permitidos |
| `"0000000000000000000000000042"` | sí (42) | no | Los ceros a la izquierda no cuentan para el rango |
| `"-0"` | sí (0) | no | `Int` no tiene cero negativo |
| `"9223372036854775807"` | sí | no | El mayor `Int` |
| `"-9223372036854775808"` | sí | no | El menor `Int`. Como literal no puede escribirse (`E1004`); solo calculándolo, `-9223372036854775807 - 1` |
| `"9223372036854775808"` | **no** | no | Uno más que el mayor `Int` |
| `"-9223372036854775809"` | **no** | no | Uno menos que el menor `Int` |
| `"99999999999999999999"` | **no** | no | Bien escrito, pero fuera del rango |
| `"+5"` | no | no | Sin `+` delante |
| `" 5"`, `"5 "`, `"5\n"` | no | no | Sin espacios |
| `""`, `"-"` | no | no | Sin dígitos |
| `"1_000"`, `"1,000"` | no | no | Sin separadores, aunque los literales del código admitan `_` |
| `"٣"`, `"１"` | no | no | Solo dígitos ASCII |
| `"0x10"` | no | no | |
| `"1.5"`, `"-0.25"`, `"0.0"` | no | sí | |
| `"-0.0"` | no | sí (`-0.0`) | Conserva el signo del cero |
| `"1e3"`, `"1e+16"`, `"2.5E-3"` | no | sí | Exponentes, aunque los literales del código no los admitan |
| `"1"` | sí | **no** | Un entero no es un decimal (sección 6.3) |
| `".5"`, `"5."`, `"1e"`, `"1e+"` | no | no | Faltan dígitos |
| `"+1.5"`, `"1,5"`, `" 1.5"` | no | no | |
| `"inf"`, `"Infinity"`, `"nan"`, `"NaN"` | no | no | Sin valores especiales |
| `"1e309"` | no | **no** | Redondeado sería infinito: no cabe en un `Float` |
| `"1e-400"` | no | sí (`0.0`) | Demasiado pequeño: se redondea a cero, como cualquier `Float` |
| `"-1e-400"` | no | sí (`-0.0`) | El redondeo a cero conserva el signo |
| `"5e-324"` | no | sí | El menor `Float` positivo |
| `"2.4703282292062328e-324"` | no | sí (`5e-324`) | Por encima de la mitad del menor positivo: se redondea a él |
| `"2.4703282292062327e-324"` | no | sí (`0.0`) | Por debajo de esa mitad: se redondea a cero |
| `"1.7976931348623157e308"` | no | sí | El mayor `Float` finito |
| `"1.7976931348623158e308"` | no | sí (el mayor finito) | Mayor que el máximo, pero se redondea a él: decide el valor redondeado, no el escrito |
| `"1.7976931348623159e308"` | no | **no** | Se redondearía a infinito |

#### 6.3 Reglas que se derivan

- **`Float.can_parse("1")` es falso a propósito**: `Int` y `Float` no se mezclan (decisión 0001). Para
  leer `"1"` como `Float` se escribe `to_float(Int.parse("1"))`.
- **`Float.parse` da el `Float` más cercano al valor escrito** (redondeo al más cercano, con empate al
  par, como el estándar IEEE 754). `Float.parse("0.1")` no es exactamente un décimo, igual que el
  literal `0.1`.
- **`Int.parse` nunca da `E3002` ni `E3005`.** Un texto fuera del rango hace falso `Int.can_parse`, así
  que la llamada se detiene antes, con el `E4001` de su `requires` y la sugerencia de la sección 7.2. Es
  distinto de `to_int`, que convierte un `Float` y da `E3005` fuera del rango (sin cambios).
- **`Float.parse` nunca devuelve un infinito ni `NaN`**: no existen en NEXORA, y un texto que daría
  uno hace falso `Float.can_parse`.
- **Ida y vuelta garantizada.** Para todo `Int` `n`, `Int.parse(to_text(n)) == n`. Para todo `Float`
  `x`, `Float.parse(to_text(x)) == x`, también para `-0.0`. Por eso se admiten exponentes: es como
  `to_text` escribe los `Float` muy grandes o muy pequeños (`1e+16`).
- **Asimetría con los literales, a propósito**: el código fuente admite `1_000_000` y no admite `1e3`;
  los textos al revés. Los literales son para personas que escriben un programa; los textos, para
  leer datos y para la ida y vuelta de `to_text`.

#### 6.4 Textos enormes, redondeo y límites de `Float`

**Coste.** Las cuatro funciones de esta sección tienen un coste proporcional a la longitud del texto,
y no usan más memoria que una cantidad fija además del propio texto:

| Función | Cómo se garantiza |
|---------|-------------------|
| `Int.can_parse`, `Int.parse` | Se recorre el texto una vez para comprobar la gramática; se ignoran los ceros a la izquierda; **si quedan más de 19 dígitos, el valor está fuera del rango sin convertir nada**, y si quedan 19 o menos se convierten y se comparan con los límites. Nunca se construye un entero de más de 19 dígitos |
| `Float.can_parse`, `Float.parse` | Se comprueba la gramática en un recorrido, y solo después se convierte con un algoritmo de redondeo correcto que admite mantisas y exponentes de cualquier longitud: un exponente enorme da infinito (no admitido) o cero (admitido) |

- **Nota para la implementación:** en Python, `int()` sobre un texto de más de 4300 dígitos lanza
  `ValueError`, y `int()` y `float()` admiten espacios, `_`, `+`, `inf` y `nan`. Por eso la gramática
  se comprueba antes y nunca se convierte el texto entero de un `Int`. Una entrada de millones de
  dígitos no puede producir un error interno.
- **Medido** con Python 3.12.10 en Windows 11, en esta revisión: textos de 10 millones de caracteres
  (10 millones de dígitos, de ceros a la izquierda, de mantisa o de exponente) se resuelven en entre
  17 y 58 ms, sin memoria adicional apreciable. Las pruebas no comprueban tiempos (`limitations.md`:
  el rendimiento no se ha medido como garantía); comprueban que la respuesta es correcta y que no hay
  error interno.

**Redondeo de `Float.parse`.**

- **Redondeo correcto al más cercano, con empate al par** (IEEE 754, *round half to even*): el
  resultado es el `Float` más cercano al valor exacto escrito, considerando todos sus dígitos. La
  implementación de referencia usa la conversión de CPython, que es correcta cuando
  `sys.float_repr_style` es `"short"` (comprobado: lo es); una prueba lo exige.
- **Máximo finito**: un valor exacto se admite si y solo si su redondeo es finito. El umbral es el punto
  medio entre el mayor `Float` finito y 2¹⁰²⁴: por debajo se redondea al máximo; en el punto medio o por
  encima, a infinito, y `Float.can_parse` es falso.
- **Subdesbordamiento**: los valores menores que la mitad del menor `Float` positivo (5e-324) se
  redondean a cero; los mayores que esa mitad, a 5e-324 o a un subnormal. En el punto medio exacto, el
  empate al par da cero. El cero conserva el signo: `"-1e-400"` da `-0.0`.
- **Ninguna lectura falla por redondear**: `Float.can_parse` solo es falso por la gramática o porque el
  redondeo sería infinito.

### 7. Cuándo se comprueban los requisitos y qué ocurre si fallan

#### 7.1 Orden de evaluación de una llamada a una función integrada

1. Se evalúan los argumentos, de izquierda a derecha. Un error al evaluar uno detiene la llamada con
   ese error; los requisitos no se llegan a comprobar.
2. Se comprueban los `requires`, **en el orden en que están escritos** en la sección 4. El primero que
   resulte falso detiene el programa con `E4001`; los siguientes no se evalúan.
3. Solo si todos se cumplen, se realiza la operación.

Los `ensures` de las funciones integradas **no se evalúan al ejecutar**: los cumple la
implementación, y las pruebas lo verifican con muchos valores. Están escritos para informar a quien
llama, y las herramientas los marcan como no comprobados al ejecutar (sección 7.4).

Dentro de `and` y `or`, una llamada que no hace falta evaluar no se evalúa, y sus requisitos tampoco:
`Int.can_parse(t) and Int.parse(t) > 0` no llega a llamar a `Int.parse` si el texto no es un entero.

#### 7.2 El diagnóstico

El mismo `E4001` (`Precondition violated`, categoría `contract`, código de salida `5`) que da una
función del programa, con la posición de la llamada:

```text
contract error[E4001]: Precondition violated
 --> program.nex:4:11
  |
4 |     print(Text.slice(word, 2, 9))
  |           ^^^^^^^^^^^^^^^^^^^^^^ This call breaks a 'requires' condition of 'Text.slice'
  = note: The condition of the built-in function is false: requires end <= Text.length(text)
  = note: Reason: A slice cannot end after the last character
  = note: It was called with: text = "abc", start = 2, end = 9
  = note: In 'shorten', called at line 9, column 11.
```

| Campo | Contenido |
|-------|-----------|
| Posición | La llamada entera, desde el nombre del tipo hasta el `)` (como en `E4001` de una función del programa) |
| Etiqueta | `This call breaks a 'requires' condition of '<Tipo.función>'` |
| Notas, en orden | `The condition of the built-in function is false: requires <condición>` · `Reason: <explicación>` · `It was called with: <parámetro> = <valor>, …` (los textos entre comillas) · la cadena de llamadas · las notas de bucle de la decisión 0010 |
| Sugerencia | Solo en `Int.parse` y `Float.parse`, según la tabla siguiente. Ninguna en `Text.slice` |

**Sugerencias de `Int.parse` y `Float.parse`.** Dicen qué hacer en cada caso, no repiten la condición.
Cuando hablan del rango de `Int`, usan el mismo texto que ya usan `E3002` y `E3005`:

| Función | Caso | Sugerencia |
|---------|------|------------|
| `Int.parse` | El texto no cumple la regla `entero` | `Check the text first with Int.can_parse(...), and call Int.parse only when it is true.` |
| `Int.parse` | Cumple la regla, pero está fuera del rango | `Int holds whole numbers from -9223372036854775808 to 9223372036854775807.` |
| `Float.parse` | El texto cumple la regla `entero` (por ejemplo `"1"`) | `This text is a whole number: read it with to_float(Int.parse(...)).` |
| `Float.parse` | No cumple ninguna de las dos reglas | `Check the text first with Float.can_parse(...), and call Float.parse only when it is true.` |
| `Float.parse` | Cumple la regla `decimal`, pero redondeado sería infinito | `The number is too large for a Float.` |

La sugerencia se elige con la misma gramática de la sección 6, sin evaluar nada más: no puede fallar
ni contradecir la condición.

Las diferencias con el `E4001` de una función del programa son dos, y las dos se deben a que la
función es del lenguaje: la primera nota dice `of the built-in function` en lugar de `at line N`,
porque no tiene línea en el archivo; y `Int.parse` y `Float.parse` pueden llevar sugerencia, porque el
lenguaje sabe qué falló. Una función del programa no puede declarar sugerencias, y esta decisión no lo
cambia.

#### 7.3 En cada interfaz

| Interfaz | Comportamiento |
|----------|----------------|
| `nex run` | Código `5`, el diagnóstico de la sección 7.2 |
| `nex run --format json` | Documento `nexora.diagnostics/1` con el `E4001`; `notes` y `hint` contienen lo mismo |
| `nex test` | El ejemplo queda en `error` con el `E4001` y la nota del ejemplo; se evalúan los demás |
| `api.run_source` y el playground | Estado `contract_violation` con el diagnóstico |
| `Tipo(x)` al ejecutar | Si la condición de un tipo refinado llama a una función integrada que incumple un requisito: `E4001`, con la nota `While checking that a value is a valid <Tipo>…` que ya existe |
| `nex check` sobre constantes de tipos refinados | El `E2017` que ya existe ("cannot be checked against the condition"), con la causa en una nota |
| Dentro del `requires` o el `ensures` de una función del programa | Como cualquier error al evaluar un contrato: el `E4001` de la función integrada |

#### 7.4 En las herramientas (representación R1)

**`nex inspect` (`nexora.inspect/2`).** El nodo `Call` gana el campo `qualifier`:

| Campo | Llamada sin cualificar (`print(x)`, `double(2)`, `Percent(x)`) | Llamada cualificada (`Text.length(s)`) |
|-------|---------------------------------------------------------------|----------------------------------------|
| `callee` | `"print"` (como hoy) | `"Text.length"`: el nombre completo |
| `callee_span` | El nombre (como hoy) | Todo `Text.length` |
| `arguments`, `span`, `type` | Como hoy | Como en cualquier llamada |
| `qualifier` | **`null`** | `"Text"` |

- **`qualifier` está presente en todas las llamadas**, con `null` cuando no hay cualificador. Es la
  regla que ya siguen todos los nodos: cada campo aparece siempre, con `null` si no tiene valor
  (`declared_type` en `Let`, `message` en `Contract`). Un consumidor puede contar con la clave.
- **Va después de `arguments` y antes de `type`.** Los campos que ya existen conservan su orden
  relativo, como ya se comprueba para el campo `examples` que la 0.4.0 añadió a `Function`
  (`tests/test_example_clauses.py`); la prueba 20 hace lo mismo para `Call`.

**Por qué no hace falta una versión nueva.** Son tres cosas distintas, y las tres se han comprobado:

| Nivel | Qué se pregunta | Resultado |
|-------|-----------------|-----------|
| **Protocolo** | ¿Lo permite la política de versiones? | Sí. `json-protocol.md`, "Versiones y compatibilidad": "Se añade un campo a un objeto: no cambia el número", y quien consume debe "ignorar los campos que no conozca". `test_inspect.py` lo dice igual: solo eliminar o renombrar exige versión nueva. Precedentes: `examples` en `Function` (0.4.0) y los nodos de bucle (0.5.0) |
| **Esquema** | ¿Valida la salida nueva con el esquema de la 0.5.1? | Sí, comprobado en esta revisión con `jsonschema` y el esquema actual: los 9 programas de `examples/` con `"qualifier": null` añadido a cada `Call`, y un programa con una llamada `Text.length` escrita como la escribiría R1. El esquema no usa `additionalProperties` y `callee` es `{"type": "string"}`, sin patrón |
| **Interpretación** | ¿Puede un consumidor de `nexora.inspect/2` entender mal la salida nueva? | No, comprobado con un consumidor que resuelve cada `callee` contra las funciones del programa y la lista `builtins` de `nex symbols`, en un programa con un parámetro llamado `length`. Con la lista de la 0.5.1, `Text.length` queda "desconocida", nunca atribuida al parámetro `length`; con la lista nueva, "integrada". A diferencia de `var` en la 0010, donde un campo nuevo habría hecho leer un `var` como un `let` y por eso se creó un nodo nuevo, aquí ningún nombre del programa puede contener un punto |

**Cambios observables en la salida JSON**, aunque no cambie la versión:

- **Todo `Call` tiene una clave más**, `qualifier`, también en los programas que no usan la sintaxis
  nueva. Quien compare documentos completos byte a byte verá la diferencia. En este repositorio:
  `EXPECTED_FIELDS` de `test_inspect.py` (la lista exacta de campos por nodo) y las salidas registradas
  en `ai-tooling.md`, que se actualizan.
- **Aparecen nombres de función con punto** en `callee` y en `builtins_called`, solo en los programas
  que usan la sintaxis nueva.
- **Un consumidor que tenga escrita su propia lista de funciones integradas** verá nombres que no
  conoce. Ningún documento promete una lista cerrada: la lista vigente está en `builtins` de
  `nex symbols` y `nex context` y en `get_capabilities()`. Le pasaría lo mismo con cualquier función
  integrada nueva, con cualquier forma de nombrarla.
- **Consumidores existentes**: solo en este repositorio (`tooling.py`, el servidor MCP, que reenvía el
  documento, las pruebas y los documentos con salidas registradas). El servidor web, la web y el
  paquete npm no leen `nex inspect`. No hay consumidores publicados.

**`nex symbols` y `nex context`.** Cada función integrada de la lista `builtins` se describe con su
nombre completo y gana el campo `contracts`, vacío si no tiene ninguno:

```json
{
  "name": "Text.slice",
  "signature": "fn Text.slice(text: Text, start: Int, end: Int) -> Text",
  "params": [{"name": "text", "type": "Text"}, {"name": "start", "type": "Int"}, {"name": "end", "type": "Int"}],
  "return_type": "Text",
  "contracts": [
    {"clause": "requires", "condition": "start >= 0",
     "message": "A slice cannot start before the first character", "checked_at_run_time": true},
    {"clause": "ensures", "condition": "Text.length(result) == end - start",
     "message": "The slice has exactly end - start characters", "checked_at_run_time": false}
  ]
}
```

- Mismos nombres de campo que los contratos de las funciones del programa, sin `line`, y con
  `checked_at_run_time`: `true` en `requires`, `false` en `ensures`. Así un agente no da por comprobado
  lo que no se comprueba.
- `builtins_called` de `nex context` contiene los nombres completos (`["Text.length", "print"]`), y
  `calls` y `called_by` no cambian: solo contienen funciones del programa.
- `features` gana el valor `text_operations` cuando el programa compara textos por orden o llama a
  alguna de las nueve funciones.
- `nex context` en texto muestra, bajo la línea `built-ins:` de cada función, los `requires` de las
  funciones integradas que llama, con su explicación.
- Las variables y los parámetros del programa se describen como siempre: una variable `length` es un
  símbolo más, sin relación con `Text.length`.
- Todo son campos o valores añadidos: `nexora.symbols/1` y `nexora.context/1` conservan su versión.

### 8. Qué puede ir delante del punto: tipos, módulos y métodos

La forma `nombre.función(…)` tiene, en el diseño de NEXORA, tres usos posibles. Esta decisión fija el
primero, reserva el segundo y deja el tercero fuera, sin cerrarlo:

| Uso | Ejemplo | Qué va delante del punto | Estado |
|-----|---------|-------------------------|--------|
| **Función de un tipo** | `Text.length(name)` | El nombre de un **tipo integrado**, que empieza por mayúscula (los tipos siempre empiezan por mayúscula, `E2016`) | **Esta decisión** |
| **Función de un módulo** | `geometry.area(circle)` | El nombre de un **módulo**, en minúscula | Futuro (punto 5 de "Planificado"). Hoy es un error (sección 9) |
| **Método de un valor** | `name.length()` | Un **valor** (una variable o una expresión) | **Fuera del diseño actual**. Hoy es un error (sección 9) |

- **Funciones de un tipo.** Se resuelven por el nombre del tipo, en la posición de tipo. Hoy solo los
  tipos integrados tienen funciones. Cuando haya listas, `List.length(xs)` y `List.get(xs, i)` usarán
  la misma forma sin cambiar la sintaxis. Que los tipos del usuario (registros) puedan declarar sus
  propias funciones (`fn Point.distance(a: Point, b: Point) -> Float`) se decidirá cuando existan.
- **Funciones de un módulo.** Cuando haya módulos, un nombre en minúscula delante del punto será un
  módulo importado. Mayúscula para los tipos y minúscula para los módulos: las dos cosas no se
  confunden. Esta decisión no define nada de los módulos.
- **Métodos de un valor.** No forman parte del diseño actual, y esta decisión **no los declara
  imposibles**. Si una decisión futura los añade, tendrá que resolver cómo se distinguen de las
  funciones de un módulo y de un tipo cuando el nombre delante del punto pudiera ser las dos cosas: por
  ejemplo, una variable llamada `Text` (permitida, sección 3.3) delante de `.length()`. La regla de un
  único espacio de nombres ya garantiza que una variable y un módulo no podrán llamarse igual, lo que
  deja esa puerta abierta.

### 9. Diagnósticos

No se crea ningún código nuevo. `E1101` (`Unexpected token`, del analizador sintáctico) se da cuando
la **forma** está mal; `E2008` (`Unknown function`, del comprobador) cuando la forma `nombre.nombre(…)`
es correcta pero el nombre de delante no es un tipo con esa función (sección 3.4). Los dos conservan
su título y su categoría.

**Forma correcta, nombre incorrecto: `E2008`**

| Situación | Ejemplo | Etiqueta | Sugerencia o nota |
|-----------|---------|----------|-------------------|
| Función que el tipo no tiene | `Text.lenght(t)` | `'Text' has no function named 'lenght'` | `Did you mean 'Text.length'?`; nota con las funciones de `Text` |
| Tipo integrado sin funciones | `Bool.parse(t)` | `'Bool' has no function named 'parse'` | Nota: `Bool has no functions yet.` |
| Tipo refinado delante del punto | `Percent.parse(t)` | `'Percent' has no functions of its own` | Si su tipo base tiene funciones: `A value of Percent can be passed to the functions of its base type, Int.` (con el tipo refinado y su base de cada caso) |
| Tipo que no existe | `Texto.length(t)` | `There is no type named 'Texto'` | `Did you mean 'Text'?` |
| Nombre en minúscula que no es nada | `geometry.area(c)` | `There is no type named 'geometry'` | Nota: `Before the '.' goes the name of a type, such as Text. Modules are not part of NEXORA yet.` |
| Un valor delante del punto | `name.length()` | `'name' is a variable: values have no functions of their own` | `Call the function of its type: Text.length(name)`, si su tipo tiene esa función |
| Una función delante del punto | `print.x(1)` | `'print' is a function, not a type` | |
| La función sin cualificar | `length(t)` | `There is no function named 'length'` (la etiqueta de hoy) | `Did you mean 'Text.length'?` |

**Forma incorrecta: `E1101`**

| Situación | Ejemplo | Etiqueta | Sugerencia o nota |
|-----------|---------|----------|-------------------|
| Sin paréntesis | `let f = Text.length` | `Expected '(' to call 'Text.length'` | `A function is not a value: call it, as in Text.length(...).` |
| Sin nombre detrás del punto | `Text.(t)`; `Text.` al final del archivo o seguido de un salto de línea fuera de paréntesis | `Expected the name of a function after 'Text.'` | |
| Espacios alrededor del punto | `Text . length(t)`; también `Text` y `.length(t)` separados por un salto de línea dentro de paréntesis | `Write 'Text.length' without spaces around the '.'` | |
| Más de un punto | `Text.length.x(t)` | `Expected '(' after 'Text.length', found '.'` | Nota: `A qualified name has one '.': Type.function` |
| Declarar una función de un tipo | `fn Text.length(t: Text) -> Int { … }` | La de hoy cuando falta el `(` tras el nombre de la función, señalando el `.` | `Only the language defines functions of a type, such as Text.length. Choose a name without '.'.` |
| Un punto en cualquier otro sitio | `.length(t)` al principio de una expresión; `1.length`; `.5`; `1.5.2`; `Text.length(s).x`; `Text` al final de una línea fuera de paréntesis y `.length(t)` en la siguiente | La que el analizador ya da para un símbolo inesperado en ese punto, con el `.` descrito como `'.'`: por ejemplo `Expected a value or an expression, found '.'` al principio de una expresión | |

**Otros casos**

| Ejemplo | Resultado |
|---------|-----------|
| `Text.length (s)` | Válido: entre el nombre de la función y el `(` puede haber espacios, como en cualquier llamada |
| `Text.length(t)` como sentencia | `E2010` (valor sin usar), como cualquier llamada que devuelve un valor |

### 10. Los programas válidos de hoy no cambian

- **Hoy un `.` solo puede aparecer en un programa válido dentro de un número decimal, de un texto o de
  un comentario.** En cualquier otro sitio es el error léxico `E1001`. El analizador léxico lee los
  números, los textos y los comentarios antes de considerar un `.` suelto, y eso no cambia. Por tanto,
  **la secuencia de tokens de todo programa válido en la 0.5.1 es idéntica**, y con ella su árbol, su
  comprobación y su ejecución.
- La única diferencia observable en un programa válido es el campo `"qualifier": null` en los nodos
  `Call` de `nex inspect` (sección 7.4).
- Los programas que hoy tienen un `.` suelto siguen siendo inválidos; solo cambia el diagnóstico (por
  ejemplo, `x.y` pasa de `E1001` a `E1101` o `E2008`).
- No se reserva ningún nombre: ningún programa válido deja de serlo.

## Motivos

- **Coherencia con la línea principal** ([0006](0006-requisitos-verificables.md)): si los requisitos
  forman parte verificable del programa, deben formar parte también del lenguaje. Una función
  integrada no es una excepción a la regla.
- **Un único mecanismo**: la misma palabra, el mismo diagnóstico y el mismo formato de herramientas
  para las condiciones del usuario y las del lenguaje.
- **Ninguna función nueva rompe un programa**: un nombre cualificado no puede coincidir con uno del
  programa, ni hoy ni cuando lleguen las listas o `Option`.
- **Las funciones se agrupan por tipo**: quien escribe `Text.` sabe dónde buscar, y una herramienta
  puede listar las funciones de un tipo.
- **Sin esperar a `Option`**: `Int.can_parse` + `Int.parse` es seguro hoy, y cuando exista `Option`
  se podrá añadir una variante que lo devuelva sin cambiar estas.
- **Determinismo**: ni el orden, ni la forma de los números, ni la longitud dependen del sistema.

## Lo que no garantiza

- **La longitud no es lo que una persona ve como "una letra".** Una `e` con el acento combinado tiene
  longitud 2, y un emoji de familia, 7. Dos textos que se ven iguales pueden ser distintos para `==`.
- **El orden no es alfabético** en ningún idioma: es el de los puntos de código. Sirve para ordenar de
  forma reproducible, no para mostrar listas ordenadas a una persona (`"Zoe" < "ana"`).
- **Los requisitos se comprueban al ejecutar**, como los de las funciones del programa. `nex check` no
  avisa de que `Text.slice("abc", 0, 5)` va a fallar, aunque sus argumentos sean constantes.
- **`Float.parse` redondea**: el `Float` que devuelve puede no ser exactamente el número escrito.
- **Una variable llamada `Text` es válida** y puede confundir a quien lea `Text.length(s)` cerca de
  ella. El analizador no se confunde (sección 3.3); para las personas, un aviso futuro (punto 6 de
  "Planificado") podría señalarlo.

## Fuera del alcance

- Interpolación de textos, `trim`, mayúsculas, `split`, `replace`, búsqueda de posiciones.
- Recorrer un texto con `for` (llegará con las listas).
- Normalización Unicode y comparación según el idioma.
- Leer números en otras bases, con separadores o con espacios.
- Comprobar sin ejecutar los requisitos de las funciones integradas.
- Funciones cualificadas para los tipos del usuario, módulos y métodos de valores (sección 8).
- Versiones cualificadas de `print`, `to_text`, `to_float` y `to_int`.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|------------|
| **A.** Nombres planos (`length`, `slice`, `parse_int`) reservados | Prohíbe nombres de variable muy habituales y no deja que las listas tengan su propia `length` sin sobrecarga |
| **B.** Que una variable oculte la función integrada | Contradice la decisión 0003: un mismo nombre significaría dos cosas según dónde se lea |
| **D.** Métodos sobre los valores (`t.length()`) | Exige acceso a miembros, encadenamiento y una forma de nombrar el valor en los contratos; merece una decisión propia (sección 8) |
| **E.** Nombres planos poco habituales (`text_length`) | Cada versión que añada funciones reservaría nombres nuevos y podría invalidar programas; el espacio de nombres crecería con cada tipo |
| Prohibir `Int`, `Float`, `Bool` y `Text` como nombres de variable | No es necesario (sección 3.3) y sería un cambio incompatible sin motivo técnico |
| `callee: "length"` con `qualifier: "Text"` en `nex inspect` | Un consumidor que ignore `qualifier` creería que se llama a algo llamado `length`, que puede ser una variable del programa. Exigiría `nexora.inspect/3` |
| Recortar en silencio (`slice` como en Python) | Oculta el error; contradice la regla de no inventar respuestas |
| Índices negativos que cuentan desde el final | Un índice negativo calculado por error se convertiría en un resultado válido |
| Un código de error nuevo para cada función integrada | Más códigos que aprender para lo mismo: una condición previa incumplida |
| `Int.parse` que devuelve `0` si el texto no es un número | Un valor válido que no significa lo que parece |
| Aceptar espacios o `+` en los números | Varias formas de escribir lo mismo; quitar espacios será una operación explícita |
| Contar bytes o unidades UTF-16 | La longitud dependería de la representación |
| Normalizar los textos | Cambiaría los datos sin que el programa lo pida, y la forma elegida sería arbitraria |
| Orden según el idioma del sistema | El mismo programa daría resultados distintos en máquinas distintas |
| Esperar a tener `Option` | Bloquearía el punto 1 de la hoja de ruta tras el 3 sin necesidad |

## Compatibilidad

- **Ningún programa válido en la 0.5.1 deja de serlo ni cambia de resultado** (sección 10). No se
  reserva ningún nombre.
- **Diagnósticos de programas inválidos**: los que contienen un `.` suelto pasan de `E1001` a `E1101`
  o `E2008` (sección 9).
- **`nexora.inspect/2`**: campo `qualifier` añadido a `Call`, sin cambiar la versión (sección 7.4).
  Una fila nueva en el historial de `inspect-schema.md`.
- **`nexora.symbols/1` y `nexora.context/1`**: campo `contracts` y nombres cualificados en `builtins`;
  valor `text_operations` en `features`. Sin cambiar la versión.
- **`nexora.diagnostics/1`**: sin cambios de formato.

## Cambios necesarios si se aprueba

| Dónde | Qué |
|-------|-----|
| `tokens.py`, `lexer.py` | El token `.` fuera de los números, con su posición para comprobar que no lleva espacios alrededor |
| `parser.py` | La llamada cualificada y los errores de sintaxis de la sección 9 |
| `ast_nodes.py` | El campo `qualifier` de `Call` |
| `checker.py` | Las funciones de los tipos, su resolución, los diagnósticos de la sección 9 y el orden entre textos |
| `prelude.py` (nuevo) | Los contratos de la sección 4, escritos en NEXORA y analizados con el analizador real |
| `interpreter.py` | Las funciones nuevas y la comprobación de sus `requires` y sugerencias (sección 7) |
| `tooling.py`, `schemas.py` | `qualifier`, `contracts`, `text_operations` y los esquemas regenerados |
| `docs/language-spec.md`, `docs/types.md`, `docs/diagnostics.md`, `docs/inspect-schema.md`, `docs/ai-context.md`, `docs/limitations.md` | La sintaxis, las reglas y las funciones |
| `examples/texts.nex` | Un ejemplo que usa todas, con su salida registrada |
| `web/guide.html`, `web/js/playground/syntax.js` | La guía, y resaltar `Tipo.función` |

## Pruebas de regresión

**Semántica**

1. `Text.length`, `Text.contains`, `Text.starts_with` y `Text.ends_with`: cada fila de la sección 5.1.
2. `Text.slice`: cada fila de la sección 5.2, y las dos equivalencias para todos los cortes de varios
   textos con caracteres fuera de ASCII.
3. Comparación: cada fila de la sección 2; `E2011` entre un `Text` y otro tipo; un tipo refinado de
   base `Text` se compara como su base.
4. `Int.can_parse` y `Float.can_parse`: cada fila de la sección 6.2. Textos de 1 000 000 de dígitos,
   de ceros a la izquierda seguidos de un número pequeño, de mantisa y de exponente (sección 6.4):
   respuesta correcta y ningún error interno, que es lo que fallaría si se convirtiera con `int()` un
   texto de más de 4300 dígitos. Sin medir tiempos.
5. Redondeo e ida y vuelta: los extremos de `Int`; `-0.0`; los dos puntos medios de la sección 6.4
   escritos con todos sus dígitos (la mitad exacta del menor positivo da `0.0`, y el punto medio entre
   el mayor finito y 2¹⁰²⁴ no se admite); `sys.float_repr_style == "short"`; y una batería de valores
   aleatorios con semilla fija en la que `Float.parse(to_text(x)) == x`.

**Requisitos**

6. Cada `requires` incumplido da `E4001` con la etiqueta, las notas exactas de la sección 7.2 y la
   posición de la llamada; con varios incumplidos, se informa el primero. Cada fila de la tabla de
   sugerencias, incluido `Int.parse` con un texto fuera del rango (`E4001` con la sugerencia del rango,
   nunca `E3002` ni `E3005`).
7. Un error al evaluar un argumento se informa antes que cualquier requisito.
8. `and` y `or` no evalúan los requisitos de una llamada que no hacen falta.
9. Los contratos de la sección 4 se analizan sin errores, tienen tipo `Bool` y no pueden fallar al
   evaluarse; los `ensures` se cumplen en todos los casos de las pruebas 1 a 5.
10. Cada fila de la tabla de la sección 7.3, incluidos `Tipo(x)`, `E2017` y `nex test`.

**Llamadas cualificadas**

11. Llamadas válidas: cada función de la sección 3.2 como expresión, como argumento de otra llamada,
    dentro de `requires`, `ensures`, `invariant`, `decreases`, `example` y de la condición de un tipo
    refinado.
12. Cualificadores desconocidos: `Texto.length`, `geometry.area`, `Percent.parse`, `Bool.parse`,
    `print.x`, con el código, la etiqueta y la sugerencia de la sección 9.
13. Funciones inexistentes: `Text.lenght` (con su sugerencia), `Int.length`, y `length(t)` sin
    cualificar (sugiere `Text.length`).
14. Errores de sintaxis con el punto: cada fila de `E1101` de la sección 9, incluidos `Text.` al final
    del archivo y antes de un salto de línea, `Text . length(t)`, `Text` y `.length(t)` separados por un
    salto de línea dentro y fuera de paréntesis, `Text.length.x(t)`, `Text.length(s).x`, `1.length`,
    `.5`, `1.5.2` y la declaración `fn Text.length(...)`. Y que `Text.length (s)` es válido.
15. Un valor delante del punto: `name.length()` da `E2008` con la sugerencia `Text.length(name)`.
16. Una variable o un parámetro llamado `length`, `slice` o `contains` es válido y convive con
    `Text.length` en la misma función.
17. Una variable o un parámetro llamado `Text` o `Int` es válido, y `Text.length(s)` llama a la función
    del tipo aunque esa variable sea visible.
18. Los programas válidos no cambian: para cada programa de `examples/` y de la documentación, la
    secuencia de tokens, la salida y los diagnósticos son los de la 0.5.1, y `nex inspect` solo añade
    `"qualifier": null`.
19. El programa cortado en cada carácter (la prueba de robustez que ya existe) incluye llamadas
    cualificadas y nunca produce un fallo interno.

**Herramientas**

20. `nex inspect`: `qualifier` presente en todas las llamadas (`null` o el tipo), después de
    `arguments` y antes de `type`; los campos que ya existían conservan su orden (`EXPECTED_FIELDS` de
    `test_inspect.py` gana `qualifier`); el documento valida con el esquema nuevo y con el de la 0.5.1,
    con y sin llamadas cualificadas; un consumidor que resuelve `callee` contra las funciones del
    programa y la lista `builtins` nunca atribuye `Text.length` a una variable o un parámetro `length`.
21. `nex symbols` y `nex context`: nombres cualificados en `builtins`, `contracts` con
    `checked_at_run_time`, `builtins_called` y `features`, validados con sus esquemas; `nex context` en
    texto muestra los `requires` de las funciones integradas llamadas.

## Revisión

### Respuestas a las revisiones anteriores

| # | Tema | Respuesta | Dónde |
|---|------|-----------|-------|
| 1 | Nombres de las funciones nuevas | Alternativa C: funciones cualificadas por su tipo | Sección 3 |
| 2 | `_` en los números de un texto | No: fuera de la gramática | Secciones 6.1 y 6.2 |
| 3 | Ceros a la izquierda | Sí: `"007"` es un entero válido de valor 7 | Sección 6.2 |
| 4 | `"1e-400"` | Sí, como `0.0` (y `"-1e-400"` como `-0.0`); un resultado no finito, como el de `"1e309"`, no | Sección 6.2 |
| 5 | Sugerencia en la lectura de números | Sí, distinta según lo que falló | Sección 7.2 |
| 6 | Los `ensures` de las funciones integradas | Se conservan como información, con `checked_at_run_time: false`, y las pruebas los comprueban | Secciones 7.1 y 7.4; prueba 9 |
| 7 | `Int`, `Float`, `Bool` y `Text` como nombres de variable | Se siguen permitiendo; no es necesario prohibirlos | Sección 3.3; prueba 17 |
| 8 | `nex inspect` | R1: `callee` con el nombre completo y `qualifier` en todas las llamadas (`null` si no hay), sin cambiar de versión | Sección 7.4 |
| 9 | Métodos sobre valores | Fuera del diseño actual, sin declararlos imposibles | Sección 8 |

### Correcciones de la última revisión

| Problema | Corrección |
|----------|------------|
| Los contratos se mostraban como `fn Text.length(...)` y se decía que se analizan con el analizador real, pero un programa no puede declarar funciones así | Sección 4: esa notación es la forma de mostrar las firmas; lo que se analiza son las condiciones, como expresiones. Sección 9: diagnóstico para quien intente declarar `fn Text.length` |
| "Sin espacios ni saltos de línea alrededor del punto" no decía qué pasa con un salto de línea fuera de paréntesis, que termina la sentencia antes | Sección 3.4 (nueva): cómo se tokeniza y se analiza el punto. Sección 9: cada caso de salto de línea, con su diagnóstico |
| `1.length` aparecía con un mensaje fijo, pero el mensaje depende de dónde aparece el punto | Sección 9: "un punto en cualquier otro sitio" da el `E1101` que el analizador ya da en ese contexto |
| La sugerencia para un tipo refinado nombraba `Int` fuera cual fuera su base | Sección 9: nombra la base de cada caso, y solo si esa base tiene funciones |
| Una fila decía "lo que no es un error" e incluía un caso que da `E2010` | Sección 9: "Otros casos" |
| Faltaban el coste de los textos enormes y las garantías de redondeo | Sección 6.4 (nueva), con mediciones; casos límite añadidos a la tabla de la sección 6.2; pruebas 4 y 5 |
| La compatibilidad de `nex inspect` no separaba protocolo, esquema y salida | Sección 7.4: tres niveles comprobados, y los cambios observables aparte |
| Un fragmento de código partido entre dos líneas (sección 3.3) | Unido |

### Aprobación

Aprobada tal como está escrita: alternativa C (funciones cualificadas por su tipo), representación R1
en `nex inspect`, métodos sobre valores fuera del diseño actual y ningún nombre plano reservado.
