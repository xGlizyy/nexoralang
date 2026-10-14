# Contexto estructurado: `nex context` y `nex symbols`

Dos herramientas para entender un programa NEXORA sin leerlo entero ni ejecutarlo. Están pensadas
para una persona que llega a un archivo nuevo y, sobre todo, para un agente de IA que va a
modificarlo: en lugar de enviar todo el código a un modelo y esperar que deduzca su estructura, se
le entrega un resumen calculado por el propio lenguaje.

Las dos comparten tres propiedades, comprobadas por pruebas (`tests/test_tooling.py`):

- **No ejecutan el programa.** Usan el análisis léxico, sintáctico y estático, nada más.
- **No interviene ningún modelo.** El mismo archivo produce siempre el mismo resultado.
- **No suponen nada.** Lo que el análisis no pudo establecer aparece como `null` o no aparece.

## `nex context`

```bash
nex context programa.nex
nex context programa.nex --format json
```

Para este programa:

<!-- nex:context -->
```nex
fn unit_price(total_cents: Int, units: Int) -> Int {
    requires units > 0
    ensures result >= 0
    return total_cents / units
}

fn report(total_cents: Int, units: Int) -> Void {
    let price = unit_price(total_cents, units)
    print("Price: " + to_text(price))
}

fn main() -> Void {
    report(1200, 3)
}
```

`nex context program.nex` escribe:

```text
program.nex | NEXORA 0.3.0 | 14 lines
Static analysis: no errors.
The program was not run to produce this summary.
Entry point: main

Functions (3):
  fn unit_price(total_cents: Int, units: Int) -> Int    [line 1]
      requires units > 0
      ensures result >= 0
      called by: report
  fn report(total_cents: Int, units: Int) -> Void    [line 7]
      variables: price: Int
      calls: unit_price
      built-ins: print, to_text
      called by: main
  fn main() -> Void    [line 12]
      calls: report

Features used: arithmetic, comparisons, contracts, conversions, text_concatenation, user_functions

Notes:
  - Contracts ('requires', 'ensures') are checked while the program runs, on the calls that execute. This analysis verified their types, not that they hold.
  - Int / Int produces an Int: the fractional part is dropped. Division by zero is a runtime error (E3001) that static analysis does not detect.
```

### Qué contiene y cómo se calcula

| Dato | De dónde sale |
|------|---------------|
| Funciones, parámetros, tipos de retorno | El árbol de sintaxis |
| Contratos, con su condición **tal como está escrita** | El texto del archivo, recortado por la posición del nodo |
| Variables de cada función y su tipo | Los símbolos que registra el comprobador. Si la variable no tiene anotación, es el tipo que el comprobador infirió |
| `calls`, `called_by` | Las llamadas que el comprobador resolvió. No se busca texto: una llamada cuenta cuando el comprobador la asoció a una función |
| `recursive` | Si la función puede alcanzarse a sí misma siguiendo esas llamadas, directa o indirectamente |
| `features` | Qué construcciones aparecen en el árbol (ver la tabla siguiente) |
| `reserved_words_used` | Palabras reservadas para características no implementadas que aparecen en el texto |
| `diagnostics` | Los mismos diagnósticos que `nex check` |
| `notes` | Reglas del lenguaje que afectan a este programa concreto (ver más abajo) |

Características que puede enumerar `features`:

| Valor | Aparece cuando el programa… |
|-------|-----------------------------|
| `user_functions` | declara alguna función además de `main` |
| `conditionals` | usa `if` |
| `contracts` | tiene alguna cláusula `requires` o `ensures` |
| `recursion` | tiene alguna función recursiva |
| `type_annotations` | anota el tipo de alguna variable |
| `arithmetic` | usa `+ - * /` sobre números |
| `text_concatenation` | une textos con `+` |
| `comparisons` | usa `== != < <= > >=` |
| `logic` | usa `and`, `or` o `not` |
| `conversions` | llama a `to_text`, `to_float` o `to_int` |
| `nested_blocks` | tiene un bloque `{ }` suelto dentro de otro |

Las **notas** no son opiniones sobre el código. Cada una es una regla del lenguaje que se añade
solo si el programa contiene aquello a lo que se refiere: que los contratos se comprueban al
ejecutar y no se han demostrado, el límite de llamadas anidadas si hay recursividad, que `Int / Int`
descarta los decimales si hay una división entera, o qué palabras reservadas se han usado.

### Formato JSON

Esquema `nexora.context/1`, descrito en
[`schemas/nexora-context.schema.json`](schemas/nexora-context.schema.json). Para un programa mínimo:

<!-- nex:context-json -->
```nex
fn double(n: Int) -> Int {
    return n * 2
}

fn main() -> Void {
    print(double(21))
}
```

```json
{
  "schema": "nexora.context/1",
  "nexora_version": "0.3.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "executed": false,
  "lines": 7,
  "reserved_words_used": [],
  "analysed": true,
  "complete": true,
  "entry_point": "main",
  "types": [],
  "functions": [
    {
      "name": "double",
      "signature": "fn double(n: Int) -> Int",
      "params": [
        {
          "name": "n",
          "type": "Int"
        }
      ],
      "return_type": "Int",
      "span": {
        "line": 1,
        "column": 1,
        "end_line": 3,
        "end_column": 2
      },
      "contracts": [],
      "variables": [],
      "calls": [],
      "builtins_called": [],
      "called_by": [
        "main"
      ],
      "recursive": false
    },
    {
      "name": "main",
      "signature": "fn main() -> Void",
      "params": [],
      "return_type": "Void",
      "span": {
        "line": 5,
        "column": 1,
        "end_line": 7,
        "end_column": 2
      },
      "contracts": [],
      "variables": [],
      "calls": [
        "double"
      ],
      "builtins_called": [
        "print"
      ],
      "called_by": [],
      "recursive": false
    }
  ],
  "features": [
    "arithmetic",
    "user_functions"
  ],
  "notes": []
}
```

| Campo | Significado |
|-------|-------------|
| `schema`, `nexora_version`, `file`, `ok`, `diagnostics` | Cabecera común a todos los documentos ([protocolo JSON](json-protocol.md)) |
| `executed` | Siempre `false`: el programa no se ejecuta para producir el resumen |
| `lines` | Líneas del archivo |
| `analysed` | `false` si hay errores léxicos (o el archivo no pudo leerse): entonces no hay estructura que describir |
| `complete` | `true` si el resumen cubre todo el archivo. `false` si hay errores de sintaxis: el resumen es **parcial** |
| `entry_point` | `"main"`, o `null` si el programa no la declara |
| `functions` | Las funciones, en el orden del archivo. `null` si `analysed` es `false` |
| `features` | Características usadas, en orden alfabético. `null` si `analysed` es `false` |
| `reserved_words_used` | `null` si el texto ni siquiera pudo dividirse en tokens |
| `notes` | Reglas del lenguaje relevantes para este programa |

### Cuando el programa tiene errores

- **Errores semánticos o de tipos:** el resumen incluye la estructura y los diagnósticos. Un tipo mal
  escrito aparece como `null`, no se inventa.
- **Errores de sintaxis:** el resumen es **parcial** y `complete` es `false`. Describe el código que
  sí pudo analizarse. Faltan las sentencias que tienen un error y las funciones cuya declaración
  (la línea `fn …`) lo tiene; un bloque sin cerrar al final del archivo se conserva con lo escrito.
  Lo que dependa de una pieza que falta es desconocido: por ejemplo, el tipo de una variable
  calculada a partir de otra cuya declaración tiene un error aparece como `null`.
- Con un resumen parcial, **los diagnósticos son solo los de sintaxis**. Los errores de nombres y de
  tipos no se comunican hasta que la sintaxis es correcta, porque sobre un árbol con huecos
  describirían los huecos y no el programa.
- **Errores léxicos** (un texto sin cerrar, un carácter no válido): no hay árbol. `analysed` es
  `false`, `functions` y `features` son `null`, y el resumen se reduce a los diagnósticos.

Por ejemplo, un programa que usa construcciones que todavía no existen. Las dos sentencias con
error no forman parte del resumen:

<!-- nex:context -->
```nex
fn main() -> Void {
    var count = 0
    while count < 3 {
        print(count)
    }
}
```

```text
program.nex | NEXORA 0.3.0 | 6 lines
Static analysis: 2 errors.
The program was not run to produce this summary.
Partial summary: only the code that could be parsed is described.
Entry point: main

Functions (1):
  fn main() -> Void    [line 1]

Features used: none

Diagnostics:
  syntax E1103 at 2:5: 'var' is reserved for a future version of NEXORA and is not implemented yet
  syntax E1103 at 3:5: 'while' is reserved for a future version of NEXORA and is not implemented yet

Notes:
  - The program uses words reserved for features that are not implemented: var, while.
  - The program has syntax errors, so this summary is partial: it covers only the code that could be parsed. Statements with errors, and functions whose declaration has errors, are missing, and a type that depends on them is unknown.
```

### Límites

- **Un solo archivo.** No hay módulos, así que no hay contexto entre archivos.
- **No dice qué hace el programa.** Describe su estructura. Para saber qué imprime hay que ejecutarlo
  (`nex run`).
- **No ve lo que depende de valores.** Que `ok` sea `true` no significa que el programa no vaya a
  dividir por cero ni a incumplir un contrato.
- **Con errores de sintaxis el resumen es parcial**, y una función cuya declaración tiene un error
  desaparece entera. Con errores léxicos no hay estructura.
- **Los comentarios no se incluyen.**
- Las notas y los mensajes están en inglés.

## `nex symbols`

Lista las funciones, parámetros y variables que declara un programa, y **dónde se usa cada uno**.

```bash
nex symbols programa.nex
nex symbols programa.nex --name units
nex symbols programa.nex --function unit_price --format json
```

| Opción | Efecto |
|--------|--------|
| `--name NOMBRE` | Solo los símbolos con ese nombre |
| `--function FUNCION` | Solo esa función y lo que se declara dentro de ella |
| `--format json` | El documento `nexora.symbols/1` en vez de texto |

Sobre el primer programa de esta página, `nex symbols program.nex --format json` devuelve (se
muestra con un programa más corto para abreviar):

<!-- nex:symbols-json -->
```nex
fn main() -> Void {
    let total = 2 + 3
    print(total)
}
```

```json
{
  "schema": "nexora.symbols/1",
  "nexora_version": "0.3.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "complete": true,
  "filter": {
    "name": null,
    "function": null
  },
  "symbols": [
    {
      "name": "main",
      "category": "function",
      "type": "Void",
      "function": null,
      "declaration": {
        "line": 1,
        "column": 4,
        "end_line": 1,
        "end_column": 8
      },
      "scope": null,
      "references": [],
      "signature": "fn main() -> Void",
      "params": [],
      "return_type": "Void"
    },
    {
      "name": "total",
      "category": "variable",
      "type": "Int",
      "function": "main",
      "declaration": {
        "line": 2,
        "column": 9,
        "end_line": 2,
        "end_column": 14
      },
      "scope": {
        "line": 1,
        "column": 19,
        "end_line": 4,
        "end_column": 2
      },
      "references": [
        {
          "line": 3,
          "column": 11,
          "end_line": 3,
          "end_column": 16
        }
      ]
    }
  ],
  "builtins": [
    {
      "name": "print",
      "signature": "fn print(value: Int | Float | Bool | Text) -> Void",
      "params": [
        {
          "name": "value",
          "type": "Int | Float | Bool | Text"
        }
      ],
      "return_type": "Void"
    },
    {
      "name": "to_float",
      "signature": "fn to_float(value: Int) -> Float",
      "params": [
        {
          "name": "value",
          "type": "Int"
        }
      ],
      "return_type": "Float"
    },
    {
      "name": "to_int",
      "signature": "fn to_int(value: Float) -> Int",
      "params": [
        {
          "name": "value",
          "type": "Float"
        }
      ],
      "return_type": "Int"
    },
    {
      "name": "to_text",
      "signature": "fn to_text(value: Int | Float | Bool | Text) -> Text",
      "params": [
        {
          "name": "value",
          "type": "Int | Float | Bool | Text"
        }
      ],
      "return_type": "Text"
    }
  ]
}
```

Cada símbolo tiene:

| Campo | Significado |
|-------|-------------|
| `name` | El nombre |
| `category` | `function`, `parameter` o `variable` |
| `type` | Su tipo; en una función, su tipo de retorno. `null` si está mal escrito en el código |
| `function` | La función donde se declara. `null` si el símbolo es una función |
| `declaration` | Posición de la declaración |
| `scope` | El bloque donde es visible. `null` en una función, que es visible en todo el archivo |
| `references` | Posición de cada uso que el comprobador resolvió a este símbolo |
| `signature`, `params`, `return_type` | Solo en las funciones |

`builtins` enumera aparte las funciones que proporciona el lenguaje (`print`, `to_text`…), que no
tienen declaración en el archivo.

Cómo se calcula: el comprobador registra cada declaración al procesarla y, cada vez que resuelve un
nombre con las reglas de ámbito del lenguaje, anota esa posición en el símbolo correspondiente. Por
eso dos variables con el mismo nombre en bloques distintos son dos símbolos distintos, cada uno con
sus referencias. **Nada se deduce del nombre** de una variable o de una función.

Límites:

- Sin índice ni búsqueda entre archivos: el lenguaje todavía es de un solo archivo.
- Un nombre que no se pudo resolver (un error `E2005`) no es referencia de ningún símbolo.
- Con errores de sintaxis la lista es parcial (`complete` es `false`): solo incluye lo declarado en
  el código que pudo analizarse.
- `symbols` es `null` si hay errores léxicos.

## Desde Python

```python
from nexora.tooling import get_context, get_symbols

context = get_context(source_text, "programa.nex")
symbols = get_symbols(source_text, "programa.nex", function="unit_price")
```

Devuelven exactamente los mismos documentos que los comandos. Ver
[Herramientas automáticas e IA](ai-tooling.md#api-de-python).
