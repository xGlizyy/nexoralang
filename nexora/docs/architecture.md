# Arquitectura

Cómo está construido el intérprete de NEXORA. Describe el código tal como es hoy
(`src/nexora/`, unas 1500 líneas de Python sin dependencias externas).

## Flujo

```text
        archivo .nex
             |
             |  cli.py lee el archivo como UTF-8
             v
   +-------------------+
   |  1. Lexer         |  lexer.py        texto -> tokens            errores: lexical
   +-------------------+
             |  lista de tokens
             v
   +-------------------+
   |  2. Parser        |  parser.py       tokens -> AST              errores: syntax
   +-------------------+
             |  AST (ast_nodes.py)
             v
   +-------------------+
   |  3. Checker       |  checker.py      nombres, ámbitos, tipos,   errores: semantic, type
   |                   |                  rutas de retorno
   +-------------------+
             |  CheckedProgram (AST + funciones + tipos)
             |
             +----------------------> nex check    informa y termina
             +----------------------> nex inspect  escribe el AST en JSON y termina
             +----------------------> nex context, nex symbols, servidor MCP
             |                        (tooling.py: resumen y símbolos, y termina)
             |
             v
   +-------------------+
   |  4. Interpreter   |  interpreter.py  recorre el AST             errores: runtime, contract
   +-------------------+
             |
             v
        salida estándar
```

Reglas del flujo:

- **Cada etapa solo se ejecuta si la anterior no encontró errores.** Así un mismo error no se
  comunica dos veces con formas distintas.
- **Las etapas 1 a 3 no ejecutan nada del programa.** `nex check`, `nex inspect`, `nex context`,
  `nex symbols` y el servidor MCP terminan ahí.
- **El intérprete solo acepta un `CheckedProgram`**, que únicamente produce el comprobador. No se
  puede ejecutar un programa sin comprobar.
- `pipeline.analyze()` encadena las etapas 1 a 3 y es lo que usan todos los comandos y todas las
  herramientas. Por eso `check`, `inspect`, `context`, `symbols` y `run` ven exactamente el mismo
  programa.

## Módulos

| Módulo | Responsabilidad | Depende de |
|--------|-----------------|------------|
| `version.py` | El número de versión. Único lugar donde se define | — |
| `diagnostics.py` | `Span`, `Source`, `Diagnostic`, el registro de códigos y categorías, y el formato de texto | — |
| `values.py` | Nombres de los tipos, límites de `Int` y cómo se escribe un valor | — |
| `tokens.py` | Tipos de token, palabras clave y palabras reservadas | `diagnostics` |
| `lexer.py` | Texto → tokens | `tokens`, `diagnostics`, `values` |
| `ast_nodes.py` | Los nodos del árbol y su conversión a JSON | `diagnostics` |
| `parser.py` | Tokens → AST, con recuperación de errores | `ast_nodes`, `tokens`, `diagnostics` |
| `checker.py` | Análisis estático. **Único lugar con las reglas de tipos** | `ast_nodes`, `diagnostics`, `values` |
| `interpreter.py` | Ejecución, contratos y errores de ejecución | `ast_nodes`, `checker`, `diagnostics`, `values` |
| `pipeline.py` | Encadena lexer, parser y checker | Los tres |
| `api.py` | Comprobar o ejecutar código en memoria, con límites opcionales. La interfaz para quien integra NEXORA en otro programa | `pipeline`, `interpreter`, `checker`, `tokens`, `diagnostics` |
| `worker.py` | Proceso de un solo uso que atiende una petición JSON; lo usa el [playground](playground.md) | `api` |
| `tooling.py` | Las herramientas de análisis: documentos JSON de diagnósticos, árbol, símbolos, contexto, especificación y capacidades. **Nunca ejecuta un programa**: del intérprete solo toma la constante del límite de llamadas | `pipeline`, `checker`, `parser`, `ast_nodes`, `tokens`, `values`, `diagnostics` |
| `schemas.py` | Los JSON Schema de todos los formatos; la parte del árbol se deriva de las clases de `ast_nodes` | `ast_nodes`, `diagnostics` |
| `mcp_server.py` | Servidor MCP **opcional**. Único módulo que importa el SDK de MCP; valida los argumentos y delega en `tooling` | `tooling` |
| `cli.py` | Argumentos, lectura del archivo, formatos de salida, códigos de salida | `pipeline`, `interpreter`, `tooling`, `diagnostics` |
| `__main__.py` | Permite `python -m nexora` | `cli` |

Solo los puntos de entrada tocan el sistema operativo: `cli.py` lee el archivo y escribe en la
terminal, `worker.py` lee una petición de su entrada estándar, `mcp_server.py` habla por la entrada
y la salida estándar, y `tooling.py` lee un único archivo fijo (la especificación del proyecto), sin
que ningún argumento influya en la ruta. El lexer, el
parser, el comprobador y el intérprete trabajan con texto y estructuras en memoria; el intérprete
recibe una función `write` para la salida, lo que permite probarlo sin terminal. Una prueba
(`tests/test_security.py`) comprueba que esos módulos no importan `os`, `pathlib` ni `subprocess`.

## Las piezas, una a una

### Lexer

Recorre el texto carácter a carácter y produce tokens con su posición (`Span`: línea y columna de
inicio y de fin).

- **No ignora nada en silencio**: todo carácter es parte de un token, espacio, comentario, o un
  error.
- **Finales de línea**: emite un token `NEWLINE`, que es lo que termina una sentencia. Dentro de
  paréntesis no lo emite, para que una expresión pueda ocupar varias líneas.
- **Recuperación**: si falta un `)` y aparece una palabra que no puede estar entre paréntesis
  (`let`, `fn`, `if`, una llave…), cierra la línea donde se quedó abierta, para que el parser
  señale el error en la línea correcta y pueda seguir.
- Tras un error continúa, para comunicar varios en una pasada (hasta 100).

### Parser

Descenso recursivo para declaraciones y sentencias; *precedence climbing* para expresiones (una
sola función, `_expression`, con la tabla `_PRECEDENCE`).

- **Recuperación de errores**: una sentencia incorrecta lanza `ParseError`, que se captura a nivel
  de bloque; el parser salta hasta el final de la línea y continúa. A nivel de archivo, salta hasta
  el siguiente `fn`.
- **Límites**: cuenta el anidamiento (`MAX_NESTING`, 64) y la profundidad de cada expresión
  (`MAX_EXPRESSION_DEPTH`, 256). Existen para que ningún programa aceptado pueda agotar la pila de
  Python en las etapas siguientes, que recorren el árbol de forma recursiva.
- Reconoce construcciones no válidas (una asignación `x = 1`, una cláusula de contrato fuera de
  sitio) para poder rechazarlas con un mensaje preciso.

### AST

Clases de datos inmutables (`@dataclass(frozen=True)`), una por construcción del lenguaje. Todo
nodo lleva su `span`.

**Los nombres de los campos de estas clases son los nombres de los campos del JSON de
`nex inspect`** (`to_dict` los recorre por reflexión). Renombrar un campo cambia el esquema
público. Las pruebas de `tests/test_inspect.py` fijan la lista exacta.

### Checker

Recorre el AST una vez y verifica nombres, ámbitos, tipos y rutas de retorno.

- **Dos pasadas sobre las funciones**: primero recoge todas las firmas, después comprueba los
  cuerpos. Por eso una función puede llamar a otra declarada más abajo.
- **Ámbitos**: una cadena de objetos `_Scope`, uno por bloque.
- **Tipos**: `_expression` devuelve el tipo de cada expresión como texto (`"Int"`, `"Text"`…) o
  `None` si la expresión tiene un error. `None` silencia los errores derivados: un nombre
  desconocido se comunica una vez, no en cada operación que lo usa.
- **Rutas de retorno**: `_block` y `_statement` devuelven `True` si siempre terminan con `return`.
- Los tipos calculados se guardan en un diccionario (`id(nodo)` → tipo) que usa `nex inspect`.
- Las funciones integradas se describen en la tabla `BUILTINS`, con la misma forma (`Signature`)
  que las funciones del programa.

### Interpreter

Recorre el AST de un programa ya comprobado. No genera ni evalúa código Python.

- **Valores**: un valor de NEXORA es un `int`, `float`, `bool` o `str` de Python.
- **Entornos**: una cadena de objetos `Environment`, uno por bloque. Cada llamada empieza un
  entorno nuevo, sin acceso al de quien llama.
- **`return`**: las sentencias devuelven un objeto `_Returned` que sube por los bloques hasta la
  llamada. No se usan excepciones para el flujo normal.
- **Lo que comprueba**: solo lo que no puede saberse antes: división por cero, rango de `Int` y de
  `Float`, profundidad de llamadas y contratos. No repite las comprobaciones de nombres ni de tipos.
- **Pila de llamadas**: `_stack` guarda la función y el punto de llamada, para añadir la cadena de
  llamadas a los diagnósticos.
- **Límite de recursividad**: `MAX_CALL_DEPTH` (1000). Además eleva temporalmente el límite de
  recursión de Python y captura `RecursionError`, que convierte en el diagnóstico `E3004`, y
  `MemoryError`, que convierte en `E3007` fuera del bloque `except` (decisión 0009).

## Cómo se representan los errores

Hay tres clases de fallo, y se mantienen separadas:

| Clase | Qué es | Cómo se representa | Qué ve quien usa `nex` |
|-------|--------|--------------------|------------------------|
| Error del programa, detectado sin ejecutar | Léxico, sintáctico, semántico o de tipos | Objetos `Diagnostic` devueltos en una lista | Diagnósticos; código de salida `1` |
| Error del programa, al ejecutar | División por cero, contrato incumplido… | Excepción `NexoraRuntimeError` con un `Diagnostic` | Diagnóstico; código `3` o `5` |
| Defecto de NEXORA | Cualquier otra excepción de Python | No se captura en las etapas | `internal error: …`; código `70` |

Un `Diagnostic` es un dato: código, explicación, posición, sugerencia y notas. El título y la
categoría salen del registro `_REGISTRY` de `diagnostics.py`, a partir del código. `render` lo
convierte en texto y `to_dict` en JSON; ambos formatos proceden del mismo objeto.

`cli.main` captura cualquier excepción inesperada y la presenta como error interno. Con
`NEXORA_DEBUG=1` la deja pasar, para ver la traza.

Las ramas "imposibles" del intérprete (`raise TypeError`, `raise LookupError`) no son errores del
usuario: si se alcanzan, el comprobador ha dejado pasar algo que no debía, y es un error interno.

## Dónde añadir cosas

| Para añadir… | Hay que tocar |
|--------------|---------------|
| Una palabra clave o un símbolo | `tokens.py` (y `lexer.py` si es un símbolo nuevo) |
| Una sentencia | Nodo en `ast_nodes.py` → `_statement` en `parser.py` → `_statement` en `checker.py` (tipos y si "siempre devuelve") → `_statement` en `interpreter.py` |
| Un operador | `tokens.py`, `lexer.py`, la tabla `_PRECEDENCE` de `parser.py`, `binary_result` en `checker.py` y `_binary` en `interpreter.py` |
| Un tipo | `values.py` (nombre y formato), `KNOWN_TYPES` y las reglas en `checker.py`, y su representación en `interpreter.py` |
| Una función integrada | La tabla `BUILTINS` de `checker.py` y `_call` en `interpreter.py` |
| Un error | Una entrada en `_REGISTRY` (`diagnostics.py`) y una fila en las tablas de `language-spec.md` y `diagnostics.md` |
| Una opción o un comando | `_build_parser` en `cli.py` y `cli-reference.md` |

En todos los casos: la especificación primero, un ejemplo en `examples/` si es una característica
nueva, y pruebas. [`CONTRIBUTING.md`](../CONTRIBUTING.md) detalla el proceso, y las pruebas fallan
si alguna de las listas anteriores queda sin sincronizar.

## Decisiones que condicionan la arquitectura

- **Intérprete que recorre el árbol.** Es la forma más simple de tener una semántica correcta y
  comprobable. No es rápida, y limita la profundidad de recursión. No se ha medido su rendimiento.
- **Los tipos son textos.** Suficiente para cinco tipos sin estructura. Los tipos compuestos
  (listas, registros) exigirán una representación propia: es el cambio más profundo que tiene por
  delante el comprobador.
- **El análisis estático es obligatorio.** Permite que el intérprete sea pequeño y que la lista de
  errores de ejecución sea corta y cerrada.
- **El AST es la interfaz pública de `nex inspect`.** Acopla el esquema JSON a las clases internas;
  a cambio no hay dos representaciones que mantener iguales.

Los motivos de cada una están en [`decisions/`](decisions/README.md).
