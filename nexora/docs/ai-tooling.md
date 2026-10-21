# Herramientas automáticas e IA

NEXORA nace de una pregunta: cómo debería ser un lenguaje cuando el código lo escriben, lo leen y
lo revisan tanto personas como sistemas de inteligencia artificial. Esta página explica qué hay de
eso **hoy**, con precisión, y qué es todavía una intención.

## Qué es cada cosa

| | Qué incluye | Estado |
|-|-------------|--------|
| **Características del lenguaje** | Tipos estáticos sin conversiones implícitas, un solo significado por nombre, contratos y tipos refinados con la explicación de cada regla | Implementado |
| **Datos estructurados para herramientas** | Diagnósticos, árbol de sintaxis, símbolos y resumen del programa en JSON, con [esquemas versionados](json-protocol.md) | Implementado y probado |
| **API de Python** | El módulo `nexora.tooling`: las mismas salidas, sin pasar por la línea de comandos | Implementado y probado. **Experimental**: puede cambiar antes de la 1.0 |
| **Servidor MCP** | Un servidor opcional que ofrece el análisis como herramientas a un asistente compatible ([MCP](mcp.md)) | Implementado y probado con el cliente del SDK oficial. Comprobado a mano en una sesión de Claude Code; **en ningún otro asistente** |
| **Servidor de lenguaje (LSP)** | Integración con editores ([LSP](lsp.md)) | **Planificado. No existe** |
| **Objetivo de investigación** | Averiguar si estas decisiones facilitan que una herramienta automática entienda, genere o corrija código | **Sin evaluar** |
| **Integraciones con modelos de IA** | Llamadas a modelos, generación de código, asistente propio | **No existen** |

Lo que NEXORA **no** hace:

- No llama a ningún modelo de IA ni a ningún servicio externo. Funciona sin conexión.
- Ningún modelo interviene en decidir si un programa es válido. Las reglas son código determinista:
  el mismo archivo produce siempre el mismo resultado.
- No incluye ningún asistente, generador de código ni corrector automático.

Y lo que **no se puede afirmar**:

- No hay ninguna evaluación que muestre que una herramienta de IA obtenga mejores resultados con
  NEXORA que con otro lenguaje. No se ha hecho ese experimento.
- Las decisiones de diseño descritas aquí son hipótesis razonadas, no resultados medidos.

## Lo que el lenguaje ofrece a una herramienta

Cuatro salidas en JSON, pensadas para leerse sin interpretar texto escrito para personas. Ninguna
ejecuta el programa analizado.

| Salida | Comando | Esquema | Contiene |
|--------|---------|---------|----------|
| Diagnósticos | `nex check archivo.nex --format json` | `nexora.diagnostics/1` | Los errores, con código, categoría, posición y sugerencia |
| Estructura | `nex inspect archivo.nex` | `nexora.inspect/2` | El árbol de sintaxis, con el tipo de cada expresión |
| Símbolos | `nex symbols archivo.nex --format json` | `nexora.symbols/1` | Funciones, parámetros y variables, con su tipo, su ámbito y cada uso |
| Contexto | `nex context archivo.nex --format json` | `nexora.context/1` | Un resumen: firmas, contratos, quién llama a quién, características usadas |

Las dos últimas están explicadas en [Contexto estructurado](ai-context.md); los formatos, sus
versiones y sus reglas, en [Protocolo JSON](json-protocol.md).

### Cómo encajan las piezas

```text
                       ┌─ nex (línea de comandos)
lexer → parser →       │
checker  ──────────►  nexora.tooling  ──┼─ import nexora.tooling (Python)
(análisis, sin ejecutar)   (documentos JSON)   │
                       └─ nex-mcp (servidor MCP, opcional)
```

Las tres entradas llaman a las mismas funciones y devuelven los mismos documentos. No hay un segundo
analizador ni reglas duplicadas: lo que decide si un programa es válido es siempre el comprobador.

### Diagnósticos

<!-- nex:check-json -->
```nex
fn double(n: Int) -> Int {
    return n * 2
}

fn main() -> Void {
    let price = 2.5
    print(double(price))
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
      "label": "Expected Int, found Float",
      "hint": "Convert the Float explicitly with to_int(...), which drops the fractional part.",
      "notes": [
        "This is the argument for 'n' in: fn double(n: Int) -> Int"
      ],
      "file": "program.nex",
      "line": 7,
      "column": 18,
      "end_line": 7,
      "end_column": 23
    }
  ]
}
```

Lo que una herramienta puede hacer con esto sin leer el texto del mensaje:

- Saber **si** el programa es válido (`ok`) y **qué clase** de problema tiene (`category`).
- Identificar el problema con un código que no cambia entre versiones (`code`).
- Localizar el fragmento exacto, de principio a fin (`line`, `column`, `end_line`, `end_column`).
- Ofrecer la corrección sugerida cuando existe (`hint`); cuando es `null`, el lenguaje no tiene
  ninguna sugerencia fundamentada y no inventa una.

### Estructura del programa

`nex inspect` devuelve el mismo árbol que usan el comprobador y el intérprete, no una
representación aparte. Para el programa más pequeño posible:

<!-- nex:inspect -->
```nex
fn main() -> Void {
    print(1 + 2)
}
```

```json
{
  "schema": "nexora.inspect/2",
  "nexora_version": "0.8.0",
  "file": "program.nex",
  "ok": true,
  "diagnostics": [],
  "complete": true,
  "program": {
    "kind": "Program",
    "span": {
      "line": 1,
      "column": 1,
      "end_line": 4,
      "end_column": 1
    },
    "types": [],
    "functions": [
      {
        "kind": "Function",
        "span": {
          "line": 1,
          "column": 1,
          "end_line": 3,
          "end_column": 2
        },
        "name": "main",
        "name_span": {
          "line": 1,
          "column": 4,
          "end_line": 1,
          "end_column": 8
        },
        "params": [],
        "return_type": {
          "kind": "TypeRef",
          "span": {
            "line": 1,
            "column": 14,
            "end_line": 1,
            "end_column": 18
          },
          "name": "Void",
          "arguments": []
        },
        "contracts": [],
        "body": {
          "kind": "Block",
          "span": {
            "line": 1,
            "column": 19,
            "end_line": 3,
            "end_column": 2
          },
          "statements": [
            {
              "kind": "ExprStatement",
              "span": {
                "line": 2,
                "column": 5,
                "end_line": 2,
                "end_column": 17
              },
              "expression": {
                "kind": "Call",
                "span": {
                  "line": 2,
                  "column": 5,
                  "end_line": 2,
                  "end_column": 17
                },
                "callee": "print",
                "callee_span": {
                  "line": 2,
                  "column": 5,
                  "end_line": 2,
                  "end_column": 10
                },
                "arguments": [
                  {
                    "kind": "Binary",
                    "span": {
                      "line": 2,
                      "column": 11,
                      "end_line": 2,
                      "end_column": 16
                    },
                    "operator": "+",
                    "operator_span": {
                      "line": 2,
                      "column": 13,
                      "end_line": 2,
                      "end_column": 14
                    },
                    "left": {
                      "kind": "IntLiteral",
                      "span": {
                        "line": 2,
                        "column": 11,
                        "end_line": 2,
                        "end_column": 12
                      },
                      "value": 1,
                      "type": "Int"
                    },
                    "right": {
                      "kind": "IntLiteral",
                      "span": {
                        "line": 2,
                        "column": 15,
                        "end_line": 2,
                        "end_column": 16
                      },
                      "value": 2,
                      "type": "Int"
                    },
                    "type": "Int"
                  }
                ],
                "qualifier": null,
                "type": "Void"
              }
            }
          ]
        },
        "examples": []
      }
    ],
    "records": []
  }
}
```

Cada nodo indica qué es (`kind`), de dónde sale (`span`) y, en las expresiones, qué tipo tiene
(`type`). Todos los nodos y campos están descritos en [`inspect-schema.md`](inspect-schema.md).

## API de Python

El módulo `nexora.tooling` ofrece el análisis a otro programa de Python, sin lanzar un proceso ni
interpretar la salida de la terminal. **Es experimental**: está probado, pero sus nombres pueden
cambiar antes de la versión 1.0. El resto de módulos (`lexer`, `parser`, `checker`…) son internos.

| Función | Devuelve |
|---------|----------|
| `check_source(source, filename="source.nex")` | Documento `nexora.diagnostics/1` |
| `inspect_source(source, filename="source.nex")` | Documento `nexora.inspect/2` |
| `get_symbols(source, filename="source.nex", *, name=None, function=None)` | Documento `nexora.symbols/1` |
| `get_context(source, filename="source.nex")` | Documento `nexora.context/1` |
| `get_language_spec(section=None)` | Documento `nexora.spec/1`: el índice de la especificación, o una sección |
| `get_capabilities()` | Documento `nexora.capabilities/1`: palabras clave, tipos, funciones integradas, códigos de error, límites |
| `render_context(document)`, `render_symbols(document)` | El texto que escriben `nex context` y `nex symbols` |

```python
from nexora.tooling import check_source

result = check_source('fn main() -> Void {\n    print(total)\n}', "demo.nex")
print(result["ok"])                        # False
print(result["diagnostics"][0]["code"])    # E2005
```

- Reciben el **código como texto** y devuelven diccionarios que se convierten a JSON sin más.
  `filename` es solo una etiqueta: no se abre ningún archivo.
- **Ninguna ejecuta el programa**, ni escribe en disco, ni usa la red.
- Un programa con errores no lanza una excepción: devuelve `ok: False` y los diagnósticos.
- `ToolingError` se lanza solo por un argumento incorrecto (por ejemplo, una sección que no existe).
- `get_language_spec` lee la especificación del proyecto. Solo está disponible con NEXORA instalado
  desde el código fuente; desde un paquete *wheel* responde `available: False`.

Para **ejecutar** un programa desde Python existe otro módulo, `nexora.api` (`run_source`), que es
el que usa el [playground](playground.md). Está separado a propósito: las herramientas de análisis
no pueden ejecutar nada.

## El ciclo de un agente

El uso para el que están pensadas estas herramientas:

1. **Obtener las reglas** de la fuente oficial: `get_capabilities` y `get_language_spec`.
2. **Obtener el contexto** del programa: `nex context`, y `nex symbols` para lo que vaya a tocar.
3. **Escribir o modificar** el código. Esto lo hace el agente; NEXORA no interviene.
4. **Analizar**: `nex check --format json`.
5. **Leer los diagnósticos**: código, categoría, posición exacta, sugerencia si la hay.
6. **Corregir** y volver al paso 4, hasta que `ok` sea `true` o se agote el número de intentos que
   el agente tenga fijado.

Todo lo que NEXORA aporta en ese ciclo es determinista y comprobable. Ni genera el código, ni aplica
correcciones, ni decide cuándo parar. Y que `ok` sea `true` significa que el programa cumple las
reglas estáticas, no que haga lo que se pretendía: eso solo lo dicen la ejecución y las pruebas.

Un agente puede recorrer el ciclo con la línea de comandos, con la API de Python o, si su asistente
es compatible, con el [servidor MCP](mcp.md).

## Tareas de referencia

`tests/tooling_tasks.py` define nueve tareas que una persona o un agente necesita resolver sobre un
programa, cada una con la herramienta que la responde y la respuesta esperada:

| Tarea | Herramienta |
|-------|-------------|
| Listar las funciones y sus firmas | `get_context` |
| Averiguar el tipo de una variable sin anotación | `get_symbols` |
| Saber quién llama a una función y qué promete, antes de cambiarla | `get_context` |
| Encontrar cada uso de un parámetro | `get_symbols` |
| Decir si un programa es válido y, si no, qué falla, dónde y con qué sugerencia | `check_source` |
| Distinguir cuál de dos versiones de un programa es válida | `check_source` |
| Consultar en la especificación qué significa un código de error | `get_language_spec` |
| Localizar en qué llamada se incumple un contrato | `nexora.api.run_source` (**ejecuta** el programa) |
| Reconocer lo que el análisis estático **no** puede decir | `get_context` |

`tests/test_tooling_tasks.py` comprueba las nueve contra las herramientas reales. Las dos últimas
son deliberadas: el programa de referencia llama a una función con un valor que incumple su
contrato. El análisis estático responde `ok: true` y avisa en una nota de que los contratos no se han
demostrado; encontrar el incumplimiento exige ejecutar el programa, cosa que las herramientas de
análisis (y el servidor MCP) no hacen.

**Qué mide y qué no.** Mide que las herramientas deterministas responden correctamente a esas
preguntas. **No mide ningún modelo de IA.** Que un agente escriba mejor NEXORA con estas herramientas
que sin ellas no se ha evaluado, y no se afirma.

Una evaluación así tendría que hacerse fuera de este repositorio (que no llama a ningún modelo), y
para ser honesta necesitaría: un conjunto de tareas fijado de antemano, las mismas tareas con y sin
herramientas, varios intentos por tarea, un criterio de éxito automático (el programa pasa
`nex check` y produce la salida esperada con `nex run`) y la publicación de todos los resultados,
también los malos.

## Garantías de estas salidas

Comprobadas por pruebas automatizadas:

| Garantía | Prueba |
|----------|--------|
| Cada documento cumple su JSON Schema, también con entradas incorrectas | `tests/test_tooling.py` |
| La CLI, la API de Python y el servidor MCP devuelven el mismo documento | `tests/test_tooling.py`, `tests/test_mcp.py` |
| Ninguna herramienta de análisis ejecuta el programa, abre archivos ajenos ni usa la red | `tests/test_security.py`, `tests/test_mcp.py` |
| La salida es siempre JSON válido, también para archivos inexistentes o que no son NEXORA | `tests/test_cli.py`, `tests/test_robustness.py` |
| Los campos y su orden son los documentados | `tests/test_inspect.py`, `tests/test_cli.py` |
| Las posiciones coinciden con el texto del archivo | `tests/test_inspect.py`, `tests/test_diagnostics.py` |
| El mismo archivo produce exactamente la misma salida | `tests/test_inspect.py`, `tests/test_cli.py` |
| Ni `check` ni `inspect` ejecutan el programa | `tests/test_security.py` |
| Los ejemplos JSON de esta página son la salida real | `tests/test_docs.py` |

## Versiones de los esquemas

Cada documento lleva un campo `schema` con nombre y número de versión.

- El número **cambia** si un campo o un tipo de nodo se elimina, se renombra o cambia de significado.
- El número **no cambia** si se añaden campos o tipos de nodo. Una herramienta debe ignorar lo que
  no conozca.

Las reglas completas, el historial y los archivos JSON Schema están en
[Protocolo JSON](json-protocol.md).

## Limitaciones

- **Con errores de sintaxis el árbol es parcial** (`"complete": false`): faltan las sentencias que
  tienen un error y las funciones cuya declaración lo tiene, y solo se comunican los errores de
  sintaxis. Sirve para inspeccionar código a medio escribir, con esa salvedad.
- **Con errores léxicos no hay árbol** (`"program": null`): un texto sin cerrar o un carácter no
  válido impiden todo el análisis.
- **Los comentarios no aparecen en el árbol.**
- **No hay información entre archivos**: un programa es un único archivo.
- **No se puede aplicar una corrección automáticamente.** `hint` es un texto para personas, no una
  edición estructurada con posición y texto de reemplazo.
- **Los mensajes están en inglés** y su redacción puede cambiar; lo estable es el código.
- **El JSON de `nex run` solo aparece si hay un fallo**, y va a la salida de error.
- **No hay servidor de lenguaje ni formateador.** El [LSP](lsp.md) está planificado, no implementado.
- **La API de Python es experimental**, y los demás módulos son internos y pueden cambiar sin aviso.
- **El servidor MCP solo se ha probado en un asistente** (Claude Code, una sesión manual), además
  de las pruebas automáticas con el cliente del SDK.
- **No se ha evaluado ningún modelo de IA** con estas herramientas.
- Los nodos `Contract` y `TypeDecl` son estables desde `nexora.inspect/2`.

## Casos de uso que esto permite

Usos para los que estas salidas son suficientes, sin que NEXORA incluya ninguno:

- Un editor que subraye los errores en su posición exacta y muestre la sugerencia.
- Un script de integración continua que rechace cambios según la categoría de los errores.
- Una herramienta que liste las funciones de un programa con sus firmas y contratos.
- Un asistente de IA externo que, tras generar código, ejecute `nex check --format json`, lea los
  códigos y posiciones, y corrija el programa en un bucle, con el intérprete —y no el modelo— como
  árbitro de si el resultado es válido.

Este último es el escenario que motiva el diseño. Que funcione mejor que con otros lenguajes es
justo lo que queda por comprobar.
