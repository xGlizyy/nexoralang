# Esquema de `nex inspect`

- **Nombre y versión del esquema:** `nexora.inspect/2`
- **Disponible desde:** `nexora` 0.3.0 (la versión 1 existió en la 0.2.0; los cambios están en el
  [historial](#historial))

`nex inspect archivo.nex` escribe en la salida estándar un único documento JSON con la estructura
del programa: tipos refinados, funciones, parámetros, contratos, sentencias y expresiones, cada una con su posición
y, cuando se conoce, su tipo.

El comando **no ejecuta el programa**. Realiza el análisis léxico, sintáctico y estático, igual que
`nex check`. La salida solo contiene lo que está escrito en el archivo y lo que el análisis deduce
de él: no incluye rutas absolutas, variables de entorno ni ningún dato de la máquina.

Esta representación está pensada para que la consuman herramientas (editores, analizadores,
asistentes de IA). NEXORA no incluye ninguna de esas herramientas: solo proporciona los datos.

## Documento

```json
{
  "schema": "nexora.inspect/2",
  "nexora_version": "0.7.0",
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
que ocurrirá al ejecutarlo: divisiones por cero, desbordamientos, contratos incumplidos y valores
comprobados con `Tipo(x)` que no cumplen su condición solo se detectan con `nex run`.

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
| `Program` | `types`: lista de `TypeDecl` · `functions`: lista de `Function` · `records`: lista de `RecordDecl` · `uses`: lista de `UsesDecl` · `imports`: lista de `ImportDecl` | El archivo completo, con los tipos y las funciones en el orden en que aparecen. `records`, `uses` e `imports` van al final |
| `ImportDecl` | `path`: texto · `path_span`: posición | La declaración `import "app/models.nex"`, que solo puede aparecer al principio del archivo ([decisión 0018](decisions/0018-modulos-e-importaciones.md)) |
| `TypeDecl` | `name`: texto · `name_span`: posición · `base`: `TypeRef` · `condition`: expresión · `message`: texto o `null` · `public`: `true` o `false` | Un tipo refinado. `message` es la explicación escrita tras la coma; `public` es `true` cuando la declaración lleva `pub` |
| `RecordDecl` | `name`: texto · `name_span`: posición · `fields`: lista de `FieldDecl` · `public`: `true` o `false` | Un registro: `type Point = { x: Int, y: Int }`. `public` es `true` cuando la declaración lleva `pub` |
| `FieldDecl` | `name`: texto · `name_span`: posición · `type`: `TypeRef` | Un campo de un registro |
| `UsesDecl` | `capability`: `"read"` o `"write"` · `path`: texto · `path_span`: posición | La capacidad que el programa declara que necesita ([decisión 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `Function` | `name`: texto · `name_span`: posición · `params`: lista de `Param` · `return_type`: `TypeRef` · `contracts`: lista de `Contract` · `body`: `Block` · `examples`: lista de `Example` · `public`: `true` o `false` | Una función. `examples` es el último campo antes de `public`, que es `true` cuando la declaración lleva `pub` |
| `Example` | `condition`: expresión · `message`: texto o `null` | Una cláusula `example`. `nex inspect` nunca la evalúa |
| `Param` | `name`: texto · `name_span`: posición · `type`: `TypeRef` | Un parámetro |
| `TypeRef` | `name`: texto · `arguments`: lista de `TypeRef` · `qualifier`: texto o `null` | Un tipo escrito en el código: `Int`, `Float`, `Bool`, `Text`, `Void`, un tipo refinado o `List[T]`. `arguments` está vacío para un nombre sin corchetes; `List[Int]` tiene un argumento `Int`. `qualifier` es el módulo de un tipo de otro archivo, `null` en el resto: `models.Point` tiene `qualifier` `models` y `name` `Point` |
| `Contract` | `clause`: `"requires"` o `"ensures"` · `condition`: expresión · `message`: texto o `null` | Una cláusula de contrato. `message` es la explicación escrita tras la coma |
| `LoopClause` | `clause`: `"invariant"` o `"decreases"` · `condition`: expresión (`Bool` en un invariante, `Int` en una medida) · `message`: texto o `null` | Una cláusula del principio del cuerpo de un `While` o un `For` |

### Sentencias

| `kind` | Campos | Significado |
|--------|--------|-------------|
| `Block` | `statements`: lista de sentencias | Un bloque `{ }` |
| `Let` | `name`: texto · `name_span`: posición · `declared_type`: `TypeRef` o `null` · `value`: expresión | Declaración de variable inmutable. `declared_type` es `null` si el tipo se infiere |
| `Var` | Los mismos que `Let` | Declaración de una variable que puede cambiar de valor (`var`). Es un nodo distinto de `Let` para que una herramienta que no lo conoce lo note, en vez de tomarla por inmutable |
| `Return` | `value`: expresión o `null` | `return`, con o sin valor |
| `If` | `condition`: expresión · `then_block`: `Block` · `else_branch`: `Block`, `If` o `null` | Condicional. `else_branch` es otro `If` en un `else if` |
| `While` | `condition`: expresión · `clauses`: lista de `LoopClause`, en el orden del código · `body`: `Block` | Un bucle. `body` contiene las sentencias, sin las cláusulas |
| `For` | `name`: texto · `name_span`: posición · `iterable`: expresión · `clauses`: lista de `LoopClause`, en el orden del código · `body`: `Block` | Un `for` sobre una `List[T]`. El iterador y su posición van primero; `body` contiene las sentencias, sin las cláusulas |
| `ExprStatement` | `expression`: expresión | Una llamada usada como sentencia |
| `Assign` | `name`: texto · `name_span`: posición · `value`: expresión | Una asignación. Solo es válida sobre una variable `var`; sobre una `let` o un parámetro va acompañada del error `E2007` |
| `FieldAssign` | `target`: expresión · `name`: texto · `name_span`: posición · `value`: expresión | Una asignación a un campo de un registro. Un registro es inmutable, así que siempre va acompañada del error `E2025` |

### Expresiones

Además de sus campos, toda expresión termina con el campo `type`: el tipo que el análisis estático
le asigna (`"Int"`, `"Float"`, `"Bool"`, `"Text"`, `"Void"`, un tipo de lista como `"List[Int]"`,
el nombre de un tipo refinado que declara el programa, como `"Percent"`, o el nombre de un
registro, como `"Point"`), o `null` si no pudo
determinarlo porque la expresión contiene un error. Una llamada a una función que no devuelve
nada tiene tipo `"Void"`.

| `kind` | Campos (antes de `type`) | Significado |
|--------|--------------------------|-------------|
| `IntLiteral` | `value`: número entero | |
| `FloatLiteral` | `value`: número decimal | |
| `TextLiteral` | `value`: texto, con los escapes ya resueltos | |
| `BoolLiteral` | `value`: booleano | |
| `ListLiteral` | `elements`: lista de expresiones | Un literal de lista: `[1, 2, 3]` o `[]` |
| `Name` | `name`: texto | Uso de una variable, un parámetro, `result` (en `ensures`) o `value` (en la condición de un tipo refinado) |
| `Unary` | `operator`: `"-"` o `"not"` · `operand`: expresión | |
| `Binary` | `operator`: texto · `operator_span`: posición · `left`: expresión · `right`: expresión | `operator` es uno de `+ - * / == != < <= > >= and or` |
| `Group` | `expression`: expresión | Una expresión entre paréntesis |
| `Call` | `callee`: texto · `callee_span`: posición · `arguments`: lista de expresiones · `qualifier`: texto o `null` | Llamada a una función propia o integrada, o comprobación de un tipo refinado (`Percent(x)`), cuyo tipo es el del tipo refinado. En una llamada cualificada (`Text.length(s)`), `callee` es el nombre completo (`"Text.length"`), `callee_span` lo abarca entero y `qualifier` es el tipo (`"Text"`); en cualquier otra, `qualifier` es `null` |
| `RecordConstruction` | `name`: texto · `name_span`: posición · `fields`: lista de `FieldInitializer` · `qualifier`: texto o `null` | La construcción de un registro: `Point(x: 1, y: 2)`. Los campos van en el orden en que están escritos, que no tiene que ser el de la declaración. `qualifier` es el módulo de un registro de otro archivo, `null` en el resto |
| `FieldInitializer` | `name`: texto · `name_span`: posición · `value`: expresión | El valor que se da a un campo en una construcción |
| `FieldAccess` | `target`: expresión · `name`: texto · `name_span`: posición | La lectura de un campo: `p.x`. `target` es el valor del que se lee |

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
     "type": {"kind": "TypeRef", "span": "...", "name": "Int", "arguments": []}}
  ],
  "return_type": {"kind": "TypeRef", "span": "...", "name": "Int", "arguments": []},
  "contracts": [
    {"kind": "Contract", "span": "...", "clause": "requires",
     "condition": {"kind": "Binary", "span": "...", "operator": ">=", "operator_span": "...",
                   "left": {"kind": "Name", "span": "...", "name": "n", "type": "Int"},
                   "right": {"kind": "IntLiteral", "span": "...", "value": 0, "type": "Int"},
                   "type": "Bool"},
     "message": null}
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
versión 2, y otra comprueba que este documento los menciona todos.

### Historial

| Versión | Publicada en | Cambios |
|---------|--------------|---------|
| `nexora.inspect/2` | `nexora` 0.11.0 | Añadidos, sin cambiar la versión: el nodo `ImportDecl` (`path`, `path_span`) para la declaración `import "app/models.nex"`, el campo `imports` al final de `Program`, el campo `public` (`true` o `false`) al final de `TypeDecl`, `RecordDecl` y `Function`, y el campo `qualifier` (texto o `null`) al final de `TypeRef` y de `RecordConstruction` para los tipos y los registros de otro módulo, `models.Point` ([decisión 0018](decisions/0018-modulos-e-importaciones.md)). Un programa sin importaciones produce el mismo documento que en la 0.10.0, más `"imports": []`, `"public": false` en cada declaración y `"qualifier": null` en cada tipo |
| `nexora.inspect/2` | `nexora` 0.10.0 | Añadidos, sin cambiar la versión: el nodo `UsesDecl` (`capability`, `path`, `path_span`) para la declaración `uses read "ruta"`, y el campo `uses` al final de `Program` ([decisión 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `nexora.inspect/2` | `nexora` 0.8.0 | Añadidos, sin cambiar la versión: los nodos `RecordDecl` (`name`, `name_span`, `fields`), `FieldDecl` (`name`, `name_span`, `type`), `RecordConstruction` (`name`, `name_span`, `fields`), `FieldInitializer` (`name`, `name_span`, `value`) y `FieldAccess` (`target`, `name`, `name_span`); la sentencia `FieldAssign` (`target`, `name`, `name_span`, `value`); el campo `records` al final de `Program`; y `type` puede ser el nombre de un registro ([decisión 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `nexora.inspect/1` | `nexora` 0.2.0 | Primera versión |
| `nexora.inspect/2` | `nexora` 0.7.0 | Añadidos, sin cambiar la versión: `arguments` (lista de `TypeRef`) en `TypeRef`, que es `[]` cuando el tipo no lleva corchetes y tiene un argumento cuando el tipo es `List[Int]`; el nodo `ListLiteral` (`elements`: lista de expresiones) para `[a, b]` y `[]`; el nodo `For` (`name`, `name_span`, `iterable`, `clauses`, `body`) para `for x in xs`; y `type` puede ser `List[...]` ([decisión 0013](decisions/0013-listas-y-for.md)) |
| `nexora.inspect/2` | `nexora` 0.6.0 | Añadido, sin cambiar la versión: campo `qualifier` en `Call`, en todas las llamadas (`null` si no hay cualificador), después de `arguments` y antes de `type` ([decisión 0011](decisions/0011-operaciones-sobre-textos.md)). `callee` puede contener un punto (`"Text.length"`) en las llamadas cualificadas. Un programa sin ellas produce el mismo documento que en la 0.5.1, más `"qualifier": null` en cada `Call`; el documento valida también con el esquema de la 0.5.1 |
| `nexora.inspect/2` | `nexora` 0.5.0 | Añadidos, sin cambiar la versión: nodos `Var`, `While` y `LoopClause` ([decisión 0010](decisions/0010-var-y-while.md)). `Assign` aparece también en programas válidos. Un programa sin `var` ni bucles produce el mismo documento que en la 0.4.0 |
| `nexora.inspect/2` | `nexora` 0.4.0 | Añadidos, sin cambiar la versión: nodo `Example` y campo `examples` al final de `Function` ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `nexora.inspect/2` | `nexora` 0.3.0 | **Cambio incompatible:** el campo `type` de las expresiones deja de ser una lista cerrada (`Int`, `Float`, `Bool`, `Text`, `Void`) y puede ser el nombre de un tipo refinado. Añadidos: nodo `TypeDecl`, campo `types` en `Program`, campo `message` en `Contract` |
