# Protocolo JSON

NEXORA entrega el resultado de su análisis como datos, en JSON, para que un programa no tenga que
interpretar texto escrito para personas ni deducir nada con expresiones regulares.

Esta página define los formatos, sus versiones y las reglas que cumplen. Cada formato tiene además
un **JSON Schema** en [`schemas/`](schemas/), y las pruebas validan con él la salida real.

## Formatos

| `schema` | Qué es | Lo produce | JSON Schema |
|----------|--------|------------|-------------|
| `nexora.diagnostics/1` | El resultado del análisis estático | `nex check --format json`, `nex run --format json`, `tooling.check_source` | [`nexora-diagnostics.schema.json`](schemas/nexora-diagnostics.schema.json) |
| `nexora.inspect/1` | El árbol de sintaxis, con tipos | `nex inspect`, `tooling.inspect_source` | [`nexora-inspect.schema.json`](schemas/nexora-inspect.schema.json) |
| `nexora.symbols/1` | Los nombres declarados y sus usos | `nex symbols --format json`, `tooling.get_symbols` | [`nexora-symbols.schema.json`](schemas/nexora-symbols.schema.json) |
| `nexora.context/1` | Un resumen técnico del programa | `nex context --format json`, `tooling.get_context` | [`nexora-context.schema.json`](schemas/nexora-context.schema.json) |
| `nexora.spec/1` | La especificación del lenguaje, o una sección | `tooling.get_language_spec` | [`nexora-spec.schema.json`](schemas/nexora-spec.schema.json) |
| `nexora.capabilities/1` | Qué es esta versión de NEXORA | `tooling.get_capabilities` | [`nexora-capabilities.schema.json`](schemas/nexora-capabilities.schema.json) |
| `nexora.result/1` | El resultado de comprobar o **ejecutar** un programa | `nexora.api`, el [playground](playground.md) | [`nexora-result.schema.json`](schemas/nexora-result.schema.json) |

Los seis primeros son de **análisis**: producirlos nunca ejecuta el programa. El último es el único
que puede proceder de una ejecución, y no lo usa ninguna herramienta de análisis.

Todas las herramientas del servidor [MCP](mcp.md) devuelven estos mismos documentos.

## Reglas comunes

### Cabecera

Los documentos que se refieren a un programa empiezan con los mismos cinco campos, en este orden:

| Campo | Tipo | Significado |
|-------|------|-------------|
| `schema` | texto | Nombre y versión del formato |
| `nexora_version` | texto | Versión de NEXORA que produjo el documento |
| `file` | texto | El nombre que se dio al código. Es una etiqueta: no tiene por qué ser una ruta |
| `ok` | booleano | `true` si el análisis estático no encontró errores |
| `diagnostics` | lista | Los diagnósticos, en el orden en que se encontraron |

`ok: true` significa "sin errores estáticos". **No** significa que el programa vaya a ejecutarse sin
fallos: una división por cero o un contrato incumplido solo aparecen al ejecutar.

### JSON limpio

Cuando se pide JSON (`--format json`):

- La salida estándar contiene **un único documento JSON** y nada más: ni avisos, ni mensajes
  decorativos, ni bloques de Markdown.
- Vale para cualquier entrada: un archivo inexistente, vacío, binario o que no es NEXORA produce
  igualmente un documento válido, con el error dentro de `diagnostics`.
- La codificación es UTF-8.
- El orden de los campos es estable y la salida es determinista: el mismo archivo produce siempre
  exactamente los mismos bytes.
- La salida de error queda vacía. La única excepción es `nex run --format json`, que escribe el
  documento **en la salida de error** (y solo si hay un fallo), porque la salida estándar pertenece
  al programa que se ejecuta.
- Un error interno de NEXORA no produce JSON: escribe `internal error: …` en la salida de error y
  termina con el código `70`. Un consumidor debe tratar "la salida no es JSON" como fallo de la
  herramienta, no del programa.

### Códigos de salida

| Código | Significado | ¿Hay documento JSON? |
|--------|-------------|----------------------|
| `0` | El programa no tiene errores estáticos | Sí, con `ok: true` |
| `1` | El programa tiene errores estáticos | Sí, con `ok: false` |
| `2` | Uso incorrecto del comando | No |
| `4` | El archivo no pudo leerse | Sí, con un diagnóstico `E0001` o `E0002` |
| `70` | Error interno de NEXORA | No |

(`3` y `5` solo los produce `nex run`: el programa falló o incumplió un contrato al ejecutarse.)

### Posiciones

Una posición es un objeto con `line`, `column`, `end_line` y `end_column`.

- Las líneas y las columnas empiezan en **1**.
- El final es **exclusivo**: `column: 5, end_column: 8` cubre las columnas 5, 6 y 7.
- La columna cuenta **caracteres Unicode** (puntos de código), no bytes ni unidades UTF-16. Una
  tabulación cuenta como una columna.
- En un diagnóstico, los cuatro valores son `null` si el problema no se refiere a un punto del
  archivo. Nunca se inventa una posición.

### Lo desconocido es `null`

Cuando el análisis no pudo establecer un dato, el campo vale `null`. No se rellena con una
suposición. Por ejemplo: el tipo de una expresión que contiene un error, el árbol de un programa con
errores léxicos, o el tipo de un parámetro cuyo tipo está mal escrito.

### Análisis parcial: `complete`

Los documentos de inspección, símbolos y contexto llevan el campo `complete`.

| `complete` | Significa |
|------------|-----------|
| `true` | El análisis cubre todo el archivo (tenga o no errores de nombres o de tipos) |
| `false` | Hay errores de sintaxis y el documento describe **solo el código que pudo analizarse**; o no hay estructura (errores léxicos, archivo ilegible) |

Con un análisis parcial faltan las sentencias que tienen un error y las funciones cuya declaración
lo tiene, y `diagnostics` contiene solo los errores de sintaxis. No se rellena ningún hueco: lo que
falta, falta. Los detalles están en [el esquema de `nex inspect`](inspect-schema.md#documento).

## Diagnósticos

<!-- nex:check-json -->
```nex
fn double(n: Int) -> Int {
    return n * 2
}

fn main() -> Void {
    print(double("21"))
}
```

`nex check program.nex --format json`:

```json
{
  "schema": "nexora.diagnostics/1",
  "nexora_version": "0.2.0",
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
        "This is the argument for 'n' in: fn double(n: Int) -> Int"
      ],
      "file": "program.nex",
      "line": 6,
      "column": 18,
      "end_line": 6,
      "end_column": 22
    }
  ]
}
```

| Campo | Tipo | Significado |
|-------|------|-------------|
| `severity` | texto | Siempre `"error"`: en esta versión no existen avisos |
| `category` | texto | `file`, `lexical`, `syntax`, `semantic`, `type`, `runtime` o `contract` |
| `code` | texto | Identificador estable: `E` y cuatro cifras. Nunca cambia de significado |
| `message` | texto | Título fijo asociado al código |
| `label` | texto | Explicación de este caso concreto |
| `hint` | texto o `null` | Corrección sugerida |
| `notes` | lista de textos | Información relacionada |
| `file` | texto | El archivo |
| `line`, `column`, `end_line`, `end_column` | número o `null` | El fragmento afectado |

Correspondencia con nombres habituales en otras herramientas: `hint` es lo que a veces se llama
*suggestion*, y `notes` lo que se llama *related information*. Se conservan los nombres con los que
nació el formato para no romper la compatibilidad.

Garantías sobre el contenido:

- **Los códigos son reales.** Todo código que puede aparecer está en el registro del lenguaje
  ([lista completa](diagnostics.md#todos-los-códigos)) y `tooling.get_capabilities` los enumera.
- **Una sugerencia no es una corrección garantizada.** `hint` es un texto para personas, y solo
  aparece cuando una regla del lenguaje lo respalda (existe esa conversión, hay un nombre declarado
  parecido). Si es `null`, NEXORA no tiene nada fundamentado que sugerir. No hay ediciones
  automáticas: ninguna herramienta modifica un archivo.
- **Los errores del programa y los fallos de NEXORA no se mezclan.** Un diagnóstico describe siempre
  el programa analizado. Un defecto de la herramienta no es un diagnóstico (ver "JSON limpio").
- Lo estable es `code`, `category` y las posiciones. La redacción de `message`, `label`, `hint` y
  `notes` está en inglés y puede mejorar entre versiones: no la compares como texto.

## Versiones y compatibilidad

Cada formato lleva su versión en el propio nombre: `nexora.context/1`.

| Cambio | ¿Cambia el número? | Qué debe hacer quien lo consume |
|--------|--------------------|---------------------------------|
| Se añade un campo a un objeto | No | Ignorar los campos que no conozca |
| Se añade un tipo de nodo al árbol, un valor a `features`, un código de error o una categoría | No | Tratar los valores desconocidos sin fallar |
| Se elimina o se renombra un campo | **Sí** | Adaptarse a la nueva versión |
| Un campo cambia de tipo o de significado | **Sí** | Adaptarse a la nueva versión |

Los esquemas reflejan esta regla: no prohíben campos adicionales.

Historial:

| Formato | Desde | Cambios |
|---------|-------|---------|
| `nexora.diagnostics/1` | 0.1.0 | 0.2.0: campo `category` y campo `schema`. Versión actual: campo `nexora_version` |
| `nexora.inspect/1` | 0.2.0 | Versión actual: campos `nexora_version` y `complete`; con errores de sintaxis, `program` es un árbol parcial en vez de `null` |
| `nexora.result/1` | Versión actual | |
| `nexora.symbols/1`, `nexora.context/1`, `nexora.spec/1`, `nexora.capabilities/1` | Versión actual | |

Casi todos los cambios han sido campos añadidos. La excepción es `program` en `nexora.inspect/1`:
su tipo no cambia (árbol o `null`), pero con errores de sintaxis antes era `null` y ahora es un árbol
parcial. Se ha mantenido el número porque el formato solo existía en la 0.2.0, que no se ha
publicado, y porque el tipo del campo es el mismo; aun así es un **cambio de comportamiento**, y
está registrado como tal en el [historial de cambios](../CHANGELOG.md). Una herramienta que dedujera
"sintaxis correcta" de que `program` no fuera `null` debe pasar a mirar `ok` o `complete`.

## Los esquemas

Los archivos de [`schemas/`](schemas/) son JSON Schema (borrador 2020-12).

- **Se generan desde el código** (`src/nexora/schemas.py`); una prueba falla si un archivo no
  coincide con lo que el código define.
- La parte del esquema que describe el árbol de sintaxis se deriva de las propias clases de los
  nodos: un nodo no puede cambiar sin que cambie su esquema.
- Las pruebas validan con ellos los documentos reales de todos los ejemplos, y también los de
  entradas incorrectas (archivo vacío, texto que no es NEXORA, código truncado).
- El campo `$id` de cada esquema es solo un identificador: no hay nada publicado en esa dirección.

Para regenerarlos tras un cambio intencionado:

```bash
NEXORA_UPDATE_SCHEMAS=1 python -m pytest tests/test_tooling.py
```

(En PowerShell: `$env:NEXORA_UPDATE_SCHEMAS = "1"; python -m pytest tests/test_tooling.py; $env:NEXORA_UPDATE_SCHEMAS = $null`.)

Validar un documento con un esquema, en Python:

```python
import json, jsonschema

schema = json.load(open("docs/schemas/nexora-diagnostics.schema.json", encoding="utf-8"))
jsonschema.validate(document, schema)
```

`jsonschema` es una dependencia de desarrollo, no del lenguaje.

## Limitaciones

- No hay un formato para ediciones (posición y texto de reemplazo): las sugerencias son texto.
- Los diagnósticos de `nex run` en JSON van a la salida de error, no a la estándar.
- El árbol no existe si el programa tiene errores léxicos, y es parcial si tiene errores de sintaxis.
- Un programa es un único archivo: ningún formato describe relaciones entre archivos.
- Los textos para personas (`label`, `hint`, `notes`, las notas del contexto) están en inglés, y la
  especificación que devuelve `nexora.spec/1`, en español.
