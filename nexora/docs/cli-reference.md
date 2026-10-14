# Referencia de la CLI

`nex` es la herramienta de línea de comandos de NEXORA. Esta página describe la versión
`nexora` 0.3.1. Una prueba automatizada comprueba que todos los comandos, opciones y códigos de
salida que acepta el programa están documentados aquí.

`python -m nexora` es equivalente a `nex` y acepta exactamente los mismos argumentos.

## Resumen

```text
nex run <archivo> [--format text|json]
nex check <archivo> [--format text|json]
nex inspect <archivo> [--format json]
nex context <archivo> [--format text|json]
nex symbols <archivo> [--format text|json] [--name NOMBRE] [--function FUNCION]
nex --version
nex --help
```

| Comando | Analiza | Ejecuta el programa | Escribe |
|---------|---------|---------------------|---------|
| `nex run` | Sí | Sí, si no hay errores estáticos | La salida del programa |
| `nex check` | Sí | **No** | El resultado del análisis |
| `nex inspect` | Sí | **No** | El árbol de sintaxis en JSON |
| `nex context` | Sí | **No** | Un resumen del programa |
| `nex symbols` | Sí | **No** | Los nombres declarados y dónde se usan |

Todos los comandos usan el mismo analizador léxico, el mismo parser y el mismo comprobador
estático. Lo que `nex check` acepta es exactamente lo que `nex run` ejecuta.

El servidor MCP opcional tiene su propio comando, `nex-mcp`, descrito en [Servidor MCP](mcp.md).

## El argumento `<archivo>`

- Es la ruta de **un** archivo `.nex`. Una ruta relativa se interpreta respecto al directorio
  desde el que se ejecuta el comando.
- El archivo tiene que estar codificado en UTF-8.
- La ruta se muestra en los diagnósticos tal como se escribió.
- **Un argumento nunca se interpreta como código.** No existe ninguna opción para pasar código
  NEXORA en la línea de comandos: el código siempre se lee de un archivo.
- Si el nombre del archivo empieza por `-`, sepáralo con `--`: `nex run -- -raro.nex`.

## `nex run`

Analiza el programa y, si no tiene errores, ejecuta su función `main`.

```bash
nex run examples/hello.nex
```

```text
Hello from NEXORA
```

- La salida del programa (lo que escribe `print`) va a la **salida estándar**.
- Los diagnósticos van a la **salida de error**.
- Un programa con errores léxicos, sintácticos, semánticos o de tipos **no se inicia**: no escribe
  nada.
- Si el programa falla durante la ejecución, lo que ya había escrito se conserva.

| Opción | Efecto |
|--------|--------|
| `--format text` | Por defecto. Los errores se escriben como texto para personas |
| `--format json` | Si el programa es inválido o falla, escribe un documento JSON en la **salida de error**. Si termina bien, no escribe nada adicional. La salida del programa no cambia |

## `nex check`

Analiza el programa **sin ejecutarlo**: sintaxis, nombres, ámbitos, tipos, rutas de retorno y las
condiciones de los contratos (que estén bien escritas, no que se cumplan).

```bash
nex check examples/hello.nex
```

```text
✓ Check passed: examples/hello.nex
```

- Si el programa es correcto, escribe la línea anterior en la salida estándar.
- Si no lo es, escribe los diagnósticos en la salida de error y una línea final con el número de
  errores.

| Opción | Efecto |
|--------|--------|
| `--format text` | Por defecto |
| `--format json` | Escribe **siempre** un único documento JSON en la **salida estándar**, sea el programa válido o no. No escribe nada en la salida de error |

`nex check` no detecta lo que depende de valores calculados: división por cero, desbordamiento,
recursividad sin fin ni contratos incumplidos. Eso solo se ve con `nex run`.

## `nex inspect`

Escribe en la salida estándar un documento JSON con la estructura del programa: funciones,
parámetros, contratos, sentencias y expresiones, con sus posiciones y sus tipos. **No ejecuta el
programa.**

```bash
nex inspect examples/hello.nex
```

| Opción | Efecto |
|--------|--------|
| `--format json` | Es el valor por defecto y el único disponible |

- Si el programa tiene errores semánticos o de tipos, el documento incluye el árbol y los errores.
- Si tiene errores de sintaxis, el documento incluye los errores, `"complete": false` y un árbol
  **parcial**: sin las sentencias que tienen un error y sin las funciones cuya declaración lo tiene.
- Si tiene errores léxicos, el documento incluye los errores y `"program": null`.

El formato está descrito en [`inspect-schema.md`](inspect-schema.md).

## `nex context`

Escribe un resumen del programa: funciones con sus firmas y contratos, variables y sus tipos, qué
función llama a cuál, qué características del lenguaje usa y los diagnósticos. **No ejecuta el
programa** y no interviene ningún modelo de IA.

```bash
nex context examples/contracts.nex
```

| Opción | Efecto |
|--------|--------|
| `--format text` | Por defecto. Un resumen breve para leer |
| `--format json` | Un único documento JSON (`nexora.context/1`) en la salida estándar, sea el programa válido o no |

En los dos formatos el resumen va a la salida estándar e incluye los diagnósticos del programa. La
única excepción: si el archivo no puede leerse y el formato es `text`, el error se escribe en la
salida de error y no hay resumen. Con errores de sintaxis el resumen es parcial y lo indica; con errores léxicos no hay estructura que resumir y el resumen se
reduce a los diagnósticos. Detalles en [Contexto estructurado](ai-context.md).

## `nex symbols`

Lista las funciones, parámetros y variables que declara el programa, con su tipo, su ámbito, la
posición de su declaración y la de cada uso. **No ejecuta el programa.**

```bash
nex symbols examples/functions.nex
nex symbols examples/functions.nex --name factorial --format json
```

| Opción | Efecto |
|--------|--------|
| `--format text` | Por defecto |
| `--format json` | Un único documento JSON (`nexora.symbols/1`) en la salida estándar |
| `--name NOMBRE` | Solo los símbolos con ese nombre |
| `--function FUNCION` | Solo esa función y lo que se declara dentro de ella |

Un filtro que no coincide con nada no es un error: la lista queda vacía (`No symbols match.`). Detalles en
[Contexto estructurado](ai-context.md#nex-symbols).

## `nex --version`

```bash
nex --version
```

```text
NEXORA 0.3.1
```

## `nex --help`

`nex --help` muestra los comandos y los códigos de salida. Cada comando tiene su propia ayuda:
`nex run --help`, `nex check --help`, `nex inspect --help`, `nex context --help`,
`nex symbols --help`.

## Formatos de salida

| Formato | Para quién | Dónde se describe |
|---------|------------|-------------------|
| `text` | Personas | [Diagnósticos](diagnostics.md) |
| `json` (diagnósticos) | Programas. Esquema `nexora.diagnostics/1` | [Especificación, sección 11.4](language-spec.md#114-formato-json) |
| `json` (inspección) | Programas. Esquema `nexora.inspect/2` | [`inspect-schema.md`](inspect-schema.md) |
| `json` (contexto y símbolos) | Programas. Esquemas `nexora.context/1` y `nexora.symbols/1` | [Contexto estructurado](ai-context.md) |

Las reglas comunes a todos los documentos JSON y sus JSON Schema están en
[Protocolo JSON](json-protocol.md).

Toda la salida se escribe en **UTF-8**, sea cual sea la configuración de la terminal.

Dónde aparece cada cosa:

| Comando | Salida estándar | Salida de error |
|---------|-----------------|-----------------|
| `nex run` | Lo que escribe el programa | Diagnósticos (texto o JSON) |
| `nex check` | `✓ Check passed: …` | Diagnósticos |
| `nex check --format json` | El documento JSON | Nada |
| `nex inspect` | El documento JSON | Nada |
| `nex context`, `nex symbols` | El resumen o la lista (texto o JSON), con los diagnósticos | Nada, salvo el error de un archivo ilegible en formato `text` |

## Códigos de salida

| Código | Significado | Comandos |
|--------|-------------|----------|
| `0` | Correcto | Todos |
| `1` | El programa tiene errores léxicos, sintácticos, semánticos o de tipos | `run`, `check`, `inspect`, `context`, `symbols` |
| `2` | Uso incorrecto de la línea de comandos | Todos |
| `3` | El programa falló durante la ejecución (categoría `runtime`) | `run` |
| `4` | El archivo no existe, no puede leerse o no es UTF-8 | `run`, `check`, `inspect`, `context`, `symbols` |
| `5` | El programa incumplió un contrato durante la ejecución (categoría `contract`) | `run` |
| `70` | Error interno de NEXORA: un fallo de la herramienta, no del programa | Todos |
| `130` | Interrumpido con Ctrl+C | Todos |

El código de salida nunca es `0` si el programa no se ejecutó correctamente.

Si el lector de la salida se cierra antes de tiempo (por ejemplo, `nex run programa.nex | head -1`),
`nex` termina en silencio con código `0`: no es un error del programa.

## Límites

- Cada etapa del análisis comunica como máximo 100 errores por archivo. Si se alcanza el límite,
  la línea final lo indica.
- Como máximo 1000 llamadas anidadas durante la ejecución.
- Como máximo 64 niveles de anidamiento de paréntesis, bloques u operadores unarios, y 256 niveles
  en una expresión.

## Variables de entorno

| Variable | Efecto |
|----------|--------|
| `NEXORA_DEBUG` | Si está definida con cualquier valor no vacío, un error interno muestra la traza completa de Python en vez del mensaje resumido. Sirve para investigar fallos del propio intérprete |

## Errores internos

Un error interno (código `70`) significa que NEXORA ha fallado, no tu programa. Se muestra así:

```text
internal error: NEXORA hit an unexpected problem (...).
This is a bug in NEXORA, not in your program. Run the command again with the environment variable NEXORA_DEBUG=1 to see the details.
```

Si ves uno, es un defecto que merece un aviso: consulta [cómo contribuir](../CONTRIBUTING.md).
