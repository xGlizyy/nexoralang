# Diagnósticos

Un diagnóstico es la forma en que NEXORA comunica un problema. Todos tienen la misma estructura,
un código que no cambia y una categoría que dice qué clase de problema es.

## Anatomía de un diagnóstico

<!-- nex:check-fails -->
```nex
fn main() -> Void {
    let total = 10
    let total = 20
}
```

```text
semantic error[E2006]: Name already declared
 --> program.nex:3:9
  |
3 |     let total = 20
  |         ^^^^^ 'total' is already declared and still visible here
  = note: It was first declared at line 2, column 9.
  = hint: Choose a different name: a visible name cannot be declared again.

error: program.nex: check failed with 1 error
```

| Parte | En el ejemplo | Significado |
|-------|---------------|-------------|
| Categoría | `semantic` | Qué clase de problema es y qué etapa lo encontró |
| Severidad | `error` | En esta versión, siempre `error`. No existen avisos |
| Código | `E2006` | Identificador estable del problema |
| Título | `Name already declared` | Texto fijo asociado al código |
| Posición | `program.nex:3:9` | Archivo, línea y columna. Ambas empiezan en 1 |
| Marcador | `^^^^^` | El fragmento exacto afectado |
| Explicación | `'total' is already declared…` | Qué ocurre en este caso concreto |
| `= note:` | | Información relacionada: dónde se declaró algo, la firma de una función, la cadena de llamadas |
| `= hint:` | | Una corrección sugerida |

La última línea (`error: …`) es un resumen del comando, no un diagnóstico.

Detalles:

- La columna cuenta caracteres, no bytes, y una tabulación cuenta como una columna.
- Algunos diagnósticos no tienen posición (por ejemplo, "falta la función `main`").
- Los mensajes están en inglés.
- **Las sugerencias solo aparecen cuando hay una regla que las respalda**: existe una conversión
  entre los dos tipos, hay un nombre declarado muy parecido al escrito, o el mensaje describe la
  forma correcta de la construcción. Si no la hay, no se sugiere nada.

## Categorías

La categoría indica en qué etapa se encontró el problema.

| Categoría | Significado | Cuándo se detecta | `nex` termina con |
|-----------|-------------|-------------------|-------------------|
| `file` | El archivo no pudo cargarse | Antes de analizar | `4` |
| `lexical` | El texto contiene algo que no pertenece al lenguaje | Sin ejecutar | `1` |
| `syntax` | El código no sigue la gramática | Sin ejecutar | `1` |
| `semantic` | Nombres, ámbitos o estructura del programa | Sin ejecutar | `1` |
| `type` | Tipos | Sin ejecutar | `1` |
| `runtime` | Depende de los valores calculados | Al ejecutar | `3` (con `nex test`, `6`) |
| `contract` | Se incumplió una regla que el programa declara: una condición `requires` o `ensures`, o la condición de un tipo refinado | Al ejecutar | `5` (con `nex test`, `6`) |
| `test` | Un ejemplo evaluado por `nex test` resultó falso | Al ejecutar `nex test` | `6` |

Las etapas se ejecutan en orden y cada una solo se realiza si la anterior no encontró errores.
Por eso un archivo con un error de sintaxis no muestra a la vez errores de tipos: se corrige
primero la sintaxis.

Dentro de una etapa se comunican todos los errores independientes que se encuentran, hasta un
máximo de 100.

## Todos los códigos

Un código no cambia nunca de significado. Si deja de usarse se retira, no se reutiliza.

### Archivo

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E0001` | Cannot read file | El archivo no existe, es un directorio o no hay permiso para leerlo | Revisa la ruta y el directorio desde el que ejecutas el comando |
| `E0002` | File is not valid UTF-8 | El archivo usa otra codificación | Guárdalo como UTF-8 |

### Léxicos

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E1001` | Unexpected character | Un carácter que no pertenece al lenguaje: `;`, `'`, `!`, `@`, letras acentuadas en un nombre… | Elimínalo. Los textos usan comillas dobles; no hay punto y coma |
| `E1002` | Unterminated string | Falta la comilla de cierre en esa línea | Cierra el texto. Un texto no puede ocupar varias líneas |
| `E1003` | Invalid escape sequence | Un `\` seguido de un carácter no admitido | Los escapes son `\n`, `\t`, `\"`, `\\` y `\{` |
| `E1004` | Invalid number literal | Número mal escrito (`007`, `1_`, `12abc`) o demasiado grande | Corrige el número. El mayor `Int` es `9223372036854775807` |
| `E1005` | Unescaped '{' in string | Una `{` dentro de un texto | Escribe `\{`. La llave está reservada para una característica futura |

### Sintácticos

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E1101` | Unexpected token | El código no sigue la gramática | El mensaje dice qué se esperaba en ese punto |
| `E1102` | Unclosed block | Se llegó al final del archivo con una `{` sin cerrar | Añade la `}`. La nota indica dónde se abrió el bloque |
| `E1103` | Reserved word | Se usa una palabra reservada para el futuro (`var`, `while`, `match`…) | Esa construcción no existe todavía; elige otro nombre o reescribe el código |
| `E1105` | Expression too deeply nested | Más de 64 niveles de anidamiento, o una expresión de más de 256 niveles | Divide el código en variables o funciones |
| `E1106` | Misplaced contract clause | `requires` o `ensures` fuera del principio del cuerpo de una función | Mueve la cláusula a las primeras líneas de la función |

### Semánticos

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E2001` | Missing main function | El programa no declara `main` | Añade `fn main() -> Void { ... }` |
| `E2002` | Duplicate function | Dos funciones con el mismo nombre, o con el de una integrada | Cambia el nombre de una |
| `E2005` | Unknown variable | Se usa un nombre que no está declarado o que ya no es visible | Decláralo antes con `let`, o corrige el nombre |
| `E2006` | Name already declared | Se declara un nombre que ya es visible, o el de una función | Elige otro nombre |
| `E2007` | Cannot reassign variable | Se intenta cambiar el valor de una variable o de un parámetro | Declara una variable nueva con otro nombre |
| `E2008` | Unknown function | Se llama a una función que no existe | Corrige el nombre o declara la función |
| `E2010` | Unused value | Un valor calculado que se pierde: una operación suelta o una llamada cuyo resultado no se usa | Guárdalo con `let` o pásalo a una función |
| `E2013` | Invalid parameter | `main` tiene parámetros, o un parámetro se llama `result` | Quita los parámetros de `main`, o cambia el nombre |
| `E2014` | Missing return | Una función que devuelve un valor puede terminar sin `return` | Asegúrate de que todas las ramas terminan con `return` |
| `E2015` | Unreachable code | Código situado después de un `return` | Elimínalo o muévelo antes del `return` |
| `E2016` | Invalid type declaration | Un tipo refinado con nombre en minúscula, repetido o de un tipo integrado, o una cadena de tipos que no termina en un tipo integrado | Corrige el nombre o la base; el mensaje dice cuál de los casos es |
| `E2018` | Invalid refinement condition | La condición de un tipo refinado llama a una función del programa o comprueba otro tipo refinado | Escribe la regla con operadores sobre `value`, o pásala a un `requires` |
| `E2019` | Too many refinement checks | Comprobar las constantes contra sus tipos refinados supera el límite de trabajo del análisis (100 000 nodos de condición). Solo ocurre con muchas constantes de cadenas largas de tipos refinados | Usa menos constantes de esos tipos o condiciones más cortas |
| `E2020` | Example without its function | Un ejemplo no contiene ninguna llamada a su propia función: su expresión no la nombra en ningún punto. Una llamada que solo ocurre dentro de otra función no cuenta | Escribe la llamada con sus entradas: `example f(2) == 4` |

### De tipos

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E2004` | Invalid return type | `main` declara un tipo de retorno distinto de `Void` | Escribe `fn main() -> Void` |
| `E2009` | Wrong number of arguments | La llamada no pasa tantos argumentos como parámetros tiene la función | La nota muestra la firma de la función |
| `E2011` | Type mismatch | Un tipo no es el que exige la regla: anotación, operador, argumento, retorno, condición, o un `Void` usado como valor | El mensaje indica el tipo esperado y el encontrado. Convierte de forma explícita si existe una conversión |
| `E2012` | Invalid type | Un nombre que no es un tipo, o `Void` donde hace falta un tipo de valor | Los tipos son `Int`, `Float`, `Bool`, `Text` y `Void`, y los tipos refinados que declara el programa |
| `E2017` | Value outside refined type | Una constante usada como valor de un tipo refinado no cumple su condición. Las notas muestran la condición, el valor y la explicación de la regla | Cambia el valor, o revisa la regla si era incorrecta |

### De ejecución

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E3001` | Division by zero | El divisor vale cero | Comprueba el divisor antes de dividir, o declara un `requires` |
| `E3002` | Integer overflow | Un resultado `Int` no cabe en 64 bits | Usa valores menores, o `Float` si no necesitas exactitud |
| `E3003` | Float result out of range | Un resultado `Float` es demasiado grande | Revisa la operación |
| `E3004` | Too many nested calls | Más de 1000 llamadas anidadas, o la pila se agotó antes | Suele ser una recursividad que no alcanza su caso base |
| `E3005` | Conversion out of range | `to_int` de un `Float` que no cabe en un `Int` | Comprueba el valor antes de convertir |
| `E3006` | Text too long | Un texto construido con `+` supera el límite del entorno donde se ejecuta. Solo ocurre donde se fija un límite, como el playground | Construye textos más cortos |
| `E3007` | Out of memory | El programa necesitó más memoria de la disponible mientras se ejecutaba. No señala ninguna posición; las notas muestran la cadena de llamadas | Reduce el tamaño de los valores que crea el programa, sobre todo los que crecen en cada llamada |

### De contrato

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E4001` | Precondition violated | Una llamada no cumple una condición `requires`. Señala la llamada | Corrige los argumentos, o comprueba la condición antes de llamar |
| `E4002` | Postcondition violated | Una función no cumple su propia condición `ensures`. Señala la cláusula | Corrige el cuerpo de la función (o la condición, si era incorrecta) |
| `E4003` | Refinement violated | Un valor comprobado con `Tipo(x)` no cumple la condición del tipo refinado. Señala la comprobación | Corrige el cálculo que produce el valor, o compruébalo antes con un `if` |

### De prueba

Solo los produce `nex test` ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)).

| Código | Título | Qué significa | Qué hacer |
|--------|--------|---------------|-----------|
| `E4004` | Example failed | Un ejemplo se evaluó sin errores, pero vale `false`. Señala la expresión del ejemplo; las notas dan lo que devolvió cada llamada a la función y la explicación del ejemplo | Corrige la función, o el ejemplo si el resultado esperado era el incorrecto |

Un ejemplo que se detiene por un error de ejecución o por una regla incumplida no da `E4004`: da el
diagnóstico de ese error, con una nota más que dice qué ejemplo lo provocó.

Cuando la regla incumplida tiene explicación, el diagnóstico la muestra en una nota `Reason: ...`.

### Códigos retirados

`E1104` y `E2003` existieron en la versión 0.1 y ya no se emiten: avisaban de que los parámetros,
las anotaciones de tipo y las funciones propias no existían. Sus números no se reutilizarán.

## Diagnósticos de ejecución

Un error de ejecución incluye la cadena de llamadas que llevó hasta él, de la más reciente a la
más antigua:

<!-- nex:fails exit=3 -->
```nex
fn share(total: Int, people: Int) -> Int {
    return total / people
}

fn report(people: Int) -> Void {
    print(share(100, people))
}

fn main() -> Void {
    report(4)
    report(0)
}
```

```text
25
runtime error[E3001]: Division by zero
 --> program.nex:2:20
  |
2 |     return total / people
  |                    ^^^^^^ The right-hand side of this division is zero
  = note: In 'share', called at line 6, column 11.
  = note: In 'report', called at line 11, column 5.

error: program.nex: the program stopped because of a runtime error
```

Se muestran como máximo seis llamadas; si hay más, una nota indica cuántas se omiten.

## Formato JSON

Con `--format json` los diagnósticos se entregan como datos, para que un programa no tenga que
interpretar el texto anterior. Para el primer ejemplo de esta página:

<!-- nex:check-json -->
```nex
fn main() -> Void {
    let total = 10
    let total = 20
}
```

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.4.0",
  "file": "program.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "category": "semantic",
      "code": "E2006",
      "message": "Name already declared",
      "label": "'total' is already declared and still visible here",
      "hint": "Choose a different name: a visible name cannot be declared again.",
      "notes": [
        "It was first declared at line 2, column 9."
      ],
      "file": "program.nex",
      "line": 3,
      "column": 9,
      "end_line": 3,
      "end_column": 14
    }
  ]
}
```

Cada campo está descrito en la [especificación, sección 11.4](language-spec.md#114-formato-json),
y su uso por herramientas en [Herramientas automáticas e IA](ai-tooling.md).

## Errores internos

Si NEXORA falla por un defecto propio, no lo presenta como un error de tu programa: muestra un
mensaje que empieza por `internal error:` y termina con el código de salida `70`. No tiene código
`E…` ni categoría. Está descrito en la [referencia de la CLI](cli-reference.md#errores-internos).
