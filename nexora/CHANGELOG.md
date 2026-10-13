# Cambios

Registro de los cambios de NEXORA, con la versión más reciente primero.

Todas las versiones son anteriores a la 1.0: el lenguaje puede cambiar de forma incompatible
entre versiones. Cada cambio incompatible se indica aquí y se explica en `docs/decisions/`.

Este registro empieza con la versión 0.1.0, la primera que pudo ejecutarse. No hay versiones
publicadas en ningún repositorio de paquetes: los números identifican estados del código.

Cada versión agrupa sus cambios en estas secciones, cuando tienen contenido:

| Sección | Qué recoge |
|---------|------------|
| Añadido | Funcionalidades nuevas |
| Corregido | Defectos resueltos |
| Cambios incompatibles | Lo que puede hacer que un programa o un script existente deje de funcionar, y cómo actualizarlo |
| Retirado | Lo que deja de existir |
| Documentación | Cambios relevantes en la documentación |
| Limitaciones | Restricciones conocidas que conviene tener presentes |

## Sin publicar

Cambios posteriores a la 0.2.0: documentación, pruebas, calidad, playground y herramientas de
análisis. El lenguaje no cambia. El número de versión sigue siendo 0.2.0 hasta que se decida
publicar una nueva.

### Añadido

- **Licencia MIT** (`LICENSE`).
- **Paquete de npm** (`npm/`, nombre `nexora-lang`): instala el comando `nex` con un lanzador que
  ejecuta el intérprete incluido usando el Python 3.11+ de la máquina. Preparado y probado en
  local; **no publicado**.
- **`nex context`**: resumen de un programa (firmas, contratos, variables, llamadas entre
  funciones, características usadas, diagnósticos), en texto o JSON. No ejecuta el programa.
- **`nex symbols`**: funciones, parámetros y variables con su tipo, su ámbito, su declaración y
  cada uso, con los filtros `--name` y `--function`. No ejecuta el programa.
- **`nexora.tooling`**: API de Python con las mismas salidas (`check_source`, `inspect_source`,
  `get_symbols`, `get_context`, `get_language_spec`, `get_capabilities`). **Experimental.**
- **Servidor MCP opcional** (`nex-mcp`, `pip install -e ".[mcp]"`): siete herramientas de análisis
  para asistentes compatibles. No ejecuta código ni abre archivos indicados por quien llama.
  Probado de forma automática con el cliente del SDK oficial (versión 2.3.0) y, a mano, en una
  sesión de Claude Code 2.1.296 en Windows. No se ha probado en otros asistentes.
- Formatos `nexora.symbols/1`, `nexora.context/1`, `nexora.spec/1` y `nexora.capabilities/1`.
- JSON Schema de todos los formatos en `docs/schemas/`, generados desde el código y usados por las
  pruebas para validar la salida real.
- Campo `nexora_version` en los documentos `nexora.diagnostics/1` y `nexora.inspect/1`. Es un campo
  añadido: la versión del formato no cambia.
- Tareas de referencia para las herramientas de análisis (`tests/tooling_tasks.py`).
- **Análisis parcial con errores de sintaxis.** `nex inspect`, `nex symbols` y `nex context` (y sus
  equivalentes en Python y en MCP) describen el código que sí pudo analizarse, con el campo nuevo
  `complete` a `false`. Faltan las sentencias con errores y las funciones cuya declaración tiene
  uno. Un programa con errores de sintaxis sigue sin ejecutarse.

- **Playground**: página web que comprueba y ejecuta código con el intérprete real
  (`docs/playground.md`). Preparado para uso local; el aislamiento en contenedor para un servicio
  público está configurado pero **no probado**.
- `nexora.api`: `check_source` y `run_source`, para comprobar o ejecutar código en memoria con
  límites opcionales de salida y de longitud de texto. Esquema de resultado `nexora.result/1`.
- `python -m nexora.worker`: proceso de un solo uso que atiende una petición JSON.
- Diagnóstico `E3006` (texto demasiado largo), que solo aparece donde el entorno fija un límite.
- Código de salida `130` cuando la ejecución se interrumpe con Ctrl+C, en lugar de una traza de Python.
- Límite de 100 errores por etapa y archivo; el resumen del comando indica cuándo se alcanza.
- Ejemplos `arithmetic.nex` e `invalid/syntax_error.nex`.
- Pruebas: ejemplos con salida registrada, documentación ejecutable, seguridad y robustez.
- Medición de cobertura (`pytest-cov`) y análisis estático del código (`ruff`), como dependencias
  de desarrollo.
- Configuración para generar un paquete instalable con el código, la documentación, los ejemplos
  y las pruebas (`MANIFEST.in`).
- Flujo de integración continua para GitHub Actions. **No se ha ejecutado todavía.**

### Corregido

- Un número entero literal de más de 4300 cifras provocaba un error interno. Ahora es el
  diagnóstico `E1004`.
- Un archivo que no es NEXORA (por ejemplo, un binario) producía un error por carácter, sin límite.
- Cuando la pila se agotaba por llamadas recursivas dentro de expresiones muy anidadas, el mensaje
  de `E3004` afirmaba que se habían superado 1000 llamadas aunque no fuera así. Ahora indica
  cuántas había.
- Si el lector de la salida se cerraba antes de tiempo (`nex run … | head -1`), se mostraba un
  error interno. Ahora `nex` termina en silencio.

### Cambios incompatibles

- El paquete de Python pasa a llamarse `nexora-lang` (antes `nexora`), porque `nexora` ya existe en
  PyPI. El comando (`nex`) y el módulo (`import nexora`) no cambian. Cómo actualizar una
  instalación en modo desarrollo: `python -m pip uninstall nexora` y `python -m pip install -e .`.
  Los archivos generados se llaman ahora `nexora_lang-0.2.0…`, y el extra opcional se instala con
  `nexora-lang[mcp]`.
- En el documento de `nex inspect`, con errores de sintaxis, `program` es ahora un árbol parcial y
  no `null`. Sigue siendo `null` con errores léxicos o si el archivo no puede leerse. Cómo
  actualizar: para saber si un programa es válido, usa `ok`; para saber si el árbol cubre todo el
  archivo, usa `complete`. El nombre del formato (`nexora.inspect/1`) no cambia; el motivo está en
  `docs/json-protocol.md`.
- Los ejemplos incorrectos a propósito se han movido: `examples/errors.nex` es ahora
  `examples/invalid/name_errors.nex`; `type_errors.nex` está en `examples/invalid/`;
  `runtime_error.nex` y `contract_violation.nex`, en `examples/failing/`.

### Retirado

- La función interna `values.type_name`, que no se usaba desde la 0.2.0.

### Documentación

- Nuevas guías: instalación, primeros pasos, tipos, funciones, contratos, CLI, diagnósticos,
  herramientas automáticas e IA, arquitectura, pruebas, limitaciones y hoja de ruta.
- `CONTRIBUTING.md`, `SECURITY.md` y `CODE_OF_CONDUCT.md`.
- Todos los programas de la documentación se ejecutan en las pruebas y su salida se compara con
  la real.

### Limitaciones

- El proyecto sigue sin repositorio público y sin canal de contacto.
- Solo se ha comprobado en Windows 11 con Python 3.12.

## 0.2.0

Sistema de tipos, funciones, contratos (experimentales) y salidas estructuradas para herramientas.

### Añadido

- **Tipos:** anotaciones en `let` (`let age: Int = 25`), con inferencia cuando se omiten.
- **Operadores:** comparaciones `== != < <= > >=` y lógicos `and`, `or`, `not`.
- **Conversiones explícitas:** `to_float`, `to_int`, `to_text`.
- **Funciones** con parámetros tipados, tipo de retorno y `return`. Recursividad, con un máximo de
  1000 llamadas anidadas.
- **`if` / `else if` / `else`** como sentencia.
- **Contratos (experimental):** `requires` y `ensures`, con `result`.
- **Análisis estático** de tipos de argumentos y de retorno, rutas de retorno (`E2014`), código
  inalcanzable (`E2015`) y valores devueltos sin usar.
- **`nex inspect`:** el árbol de sintaxis en JSON, con tipos y posiciones (`nexora.inspect/1`).
- **`nex run --format json`:** errores en JSON por la salida de error.
- **Categoría** en cada diagnóstico (`file`, `lexical`, `syntax`, `semantic`, `type`, `runtime`,
  `contract`) y campo `schema` en los documentos JSON (`nexora.diagnostics/1`).
- Cadena de llamadas en los diagnósticos de ejecución.
- Códigos nuevos: `E1106`, `E2012`–`E2015`, `E3004`, `E3005`, `E4001`, `E4002`.
- Código de salida `5`: contrato incumplido.

### Cambios incompatibles

- El tipo de texto se llama **`Text`** (antes `String`). Solo cambia en los mensajes: en 0.1 no se
  podían escribir tipos.
- La cabecera de los diagnósticos de texto incluye la categoría:
  `type error[E2011]: …` en lugar de `error[E2011]: …`.
- `to_text`, `to_float` y `to_int` ya no pueden usarse como nombres de variable.
- Un tipo de retorno desconocido es ahora `E2012` (antes `E2004`).
- Requiere Python 3.11 o superior (antes 3.10).

### Retirado

- `E1104` y `E2003`, que avisaban de que los parámetros, las anotaciones y las funciones propias no
  existían.

### Compatibilidad

Los cuatro programas de ejemplo de 0.1 se ejecutan sin cambios y producen la misma salida.

## 0.1.0

Primera versión ejecutable: función `main`, variables inmutables con `let`, tipos `Int`, `Float`,
`Bool` y `String`, aritmética, bloques, comentarios, `print`, y los comandos `nex run` y
`nex check`.
