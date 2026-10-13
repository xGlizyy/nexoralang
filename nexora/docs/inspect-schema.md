# Esquema de `nex inspect`

- **Nombre y versión del esquema:** `nexora.inspect/1`
- **Disponible desde:** `nexora` 0.2.0

`nex inspect archivo.nex` escribe en la salida estándar un único documento JSON con la estructura
del programa: funciones, parámetros, contratos, sentencias y expresiones, cada una con su posición
y, cuando se conoce, su tipo.

El comando **no ejecuta el programa**. Realiza el análisis léxico, sintáctico y estático, igual que
`nex check`. La salida solo contiene lo que está escrito en el archivo y lo que el análisis deduce
de él: no incluye rutas absolutas, variables de entorno ni ningún dato de la máquina.

Esta representación está pensada para que la consuman herramientas (editores, analizadores,
asistentes de IA). NEXORA no incluye ninguna de esas herramientas: solo proporciona los datos.

## Documento

```json
{
  "schema": "nexora.inspect/1",
  "nexora_version": "0.2.0",
  "file": "hello.nex",
  "ok": true,
  "diagnostics": [],
  "program": { "kind": "Program", "...": "..." }
}
```

| Campo | Tipo | Significado |
|-------|------|-------------|
| `schema` | texto | Nombre y versión de este formato |
| `nexora_version` | texto | Versión de NEXORA que produjo el documento. Campo añadido después de la 0.2.0 |
| `file` | texto | El archivo analizado, tal como se pasó al comando |
| `ok` | booleano | `true` si el programa no tiene errores estáticos |
| `diagnostics` | lista | Los errores encontrados, con el formato de la sección 11.4 de la [especificación](language-spec.md) |
| `complete` | booleano | `true` si el árbol cubre todo el archivo. `false` si es parcial o no existe. Campo añadido después de la 0.2.0 |
| `program` | nodo `Program` o `null` | El árbol de sintaxis |

El JSON Schema de este documento, generado desde el código, está en
[`schemas/nexora-inspect.schema.json`](schemas/nexora-inspect.schema.json); las reglas comunes a
todos los formatos, en [Protocolo JSON](json-protocol.md).

Cuándo está disponible `program`:

| Situación | `ok` | `complete` | `program` | Código de salida |
|-----------|------|------------|-----------|------------------|
| Programa válido | `true` | `true` | El árbol, con todos los tipos | `0` |
| Errores semánticos o de tipos | `false` | `true` | El árbol; las expresiones que no pudieron tiparse tienen `"type": null` | `1` |
| Errores de sintaxis | `false` | `false` | Un árbol **parcial** | `1` |
| Errores léxicos | `false` | `false` | `null` | `1` |
| El archivo no pudo leerse | `false` | `false` | `null` | `4` |

Un árbol parcial contiene lo que pudo analizarse:

- Falta cada **sentencia** que tiene un error de sintaxis; las demás sentencias de su bloque están.
- Falta cada **función** cuya declaración (nombre, parámetros o tipo de retorno) tiene un error.
- Un bloque que queda sin cerrar al final del archivo se conserva con las sentencias escritas; su
  posición termina donde termina el archivo.
- Los tipos se calculan igual, pero lo que dependa de una pieza que falta tiene `"type": null`.
- `diagnostics` contiene **solo los errores de sintaxis**. Los errores de nombres y de tipos no se
  comunican mientras la sintaxis sea incorrecta.

Todos los nodos de un árbol parcial están completos y cumplen este esquema: no hay nodos de error ni
campos a medias. Un programa con errores de sintaxis **nunca se ejecuta**, tenga o no árbol.

Hasta este cambio, `program` era `null` también con errores de sintaxis. Para saber si un programa
es válido hay que mirar `ok`, no si `program` existe.

Que `ok` sea `true` significa que el programa supera el análisis estático. No dice nada sobre lo
que ocurrirá al ejecutarlo: divisiones por cero, desbordamientos y contratos incumplidos solo se
detectan con `nex run`.

## Nodos

Todo nodo es un objeto con estos dos campos, siempre los primeros:

| Campo | Tipo | Significado |
|-------|------|-------------|
| `kind` | texto | El tipo de nodo, uno de los listados abajo |
| `span` | posición | El fragmento de código del que procede |

Una **posición** es un objeto `{"line", "column", "end_line", "end_column"}`. Líneas y columnas
empiezan en 1; la columna cuenta caracteres y la posición final queda excluida.

Los campos de cada nodo aparecen siempre, en el orden indicado. Un campo opcional sin valor es
`null`, nunca se omite.

### Declaraciones

| `kind` | Campos | Significado |
|--------|--------|-------------|
| `Program` | `functions`: lista de `Function` | El archivo completo |
| `Function` | `name`: texto · `name_span`: posición · `params`: lista de `Param` · `return_type`: `TypeRef` · `contracts`: lista de `Contract` · `body`: `Block` | Una función |
| `Param` | `name`: texto · `name_span`: posición · `type`: `TypeRef` | Un parámetro |
| `TypeRef` | `name`: texto | Un tipo escrito en el código: `Int`, `Float`, `Bool`, `Text` o `Void` |
| `Contract` | `clause`: `"requires"` o `"ensures"` · `condition`: expresión | Una cláusula de contrato (experimental) |

### Sentencias

| `kind` | Campos | Significado |
|--------|--------|-------------|
| `Block` | `statements`: lista de sentencias | Un bloque `{ }` |
| `Let` | `name`: texto · `name_span`: posición · `declared_type`: `TypeRef` o `null` · `value`: expresión | Declaración de variable. `declared_type` es `null` si el tipo se infiere |
| `Return` | `value`: expresión o `null` | `return`, con o sin valor |
| `If` | `condition`: expresión · `then_block`: `Block` · `else_branch`: `Block`, `If` o `null` | Condicional. `else_branch` es otro `If` en un `else if` |
| `ExprStatement` | `expression`: expresión | Una llamada usada como sentencia |
| `Assign` | `name`: texto · `name_span`: posición · `value`: expresión | Una asignación. Siempre va acompañada del error `E2007` |

### Expresiones

Además de sus campos, toda expresión termina con el campo `type`: el tipo que el análisis estático
le asigna (`"Int"`, `"Float"`, `"Bool"`, `"Text"` o `"Void"`), o `null` si no pudo determinarlo
porque la expresión contiene un error. Una llamada a una función que no devuelve nada tiene tipo
`"Void"`.

| `kind` | Campos (antes de `type`) | Significado |
|--------|--------------------------|-------------|
| `IntLiteral` | `value`: número entero | |
| `FloatLiteral` | `value`: número decimal | |
| `TextLiteral` | `value`: texto, con los escapes ya resueltos | |
| `BoolLiteral` | `value`: booleano | |
| `Name` | `name`: texto | Uso de una variable, un parámetro o `result` |
| `Unary` | `operator`: `"-"` o `"not"` · `operand`: expresión | |
| `Binary` | `operator`: texto · `operator_span`: posición · `left`: expresión · `right`: expresión | `operator` es uno de `+ - * / == != < <= > >= and or` |
| `Group` | `expression`: expresión | Una expresión entre paréntesis |
| `Call` | `callee`: texto · `callee_span`: posición · `arguments`: lista de expresiones | Llamada a una función propia o integrada |

## Ejemplo

Para este programa:

```nex
fn double(n: Int) -> Int {
    requires n >= 0
    return n * 2
}
```

el nodo de la función es (se omiten las posiciones interiores para abreviar):

```json
{
  "kind": "Function",
  "span": {"line": 1, "column": 1, "end_line": 4, "end_column": 2},
  "name": "double",
  "name_span": {"line": 1, "column": 4, "end_line": 1, "end_column": 10},
  "params": [
    {"kind": "Param", "span": "...", "name": "n", "name_span": "...",
     "type": {"kind": "TypeRef", "span": "...", "name": "Int"}}
  ],
  "return_type": {"kind": "TypeRef", "span": "...", "name": "Int"},
  "contracts": [
    {"kind": "Contract", "span": "...", "clause": "requires",
     "condition": {"kind": "Binary", "span": "...", "operator": ">=", "operator_span": "...",
                   "left": {"kind": "Name", "span": "...", "name": "n", "type": "Int"},
                   "right": {"kind": "IntLiteral", "span": "...", "value": 0, "type": "Int"},
                   "type": "Bool"}}
  ],
  "body": {
    "kind": "Block", "span": "...",
    "statements": [
      {"kind": "Return", "span": "...",
       "value": {"kind": "Binary", "span": "...", "operator": "*", "operator_span": "...",
                 "left": {"kind": "Name", "span": "...", "name": "n", "type": "Int"},
                 "right": {"kind": "IntLiteral", "span": "...", "value": 2, "type": "Int"},
                 "type": "Int"}}
    ]
  }
}
```

## Estabilidad y evolución

El esquema lleva un nombre y un número de versión en el campo `schema`.

- **El número de versión cambia** cuando un campo o un tipo de nodo se elimina, se renombra o
  cambia de significado. Un programa que lea la versión 1 puede dejar de funcionar con la 2.
- **El número de versión no cambia** cuando se añade un campo a un nodo o un tipo de nodo nuevo
  (por ejemplo, al añadir una construcción al lenguaje). Las herramientas deben ignorar los campos
  y los tipos de nodo que no conozcan.
- El orden de los campos es estable dentro de una versión, y la salida es determinista: el mismo
  archivo produce siempre el mismo documento.

Una prueba automatizada (`tests/test_inspect.py`) fija la lista exacta de nodos y campos de la
versión 1, y otra comprueba que este documento los menciona todos.

Los contratos son experimentales: el nodo `Contract` y el campo `contracts` pueden cambiar, y en
ese caso cambiará el número de versión.

### Historial

| Versión | Publicada en | Cambios |
|---------|--------------|---------|
| `nexora.inspect/1` | `nexora` 0.2.0 | Primera versión |
