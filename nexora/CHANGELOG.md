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

## 0.4.0 — Ejemplos y `nex test`

Tercer paso de la línea principal: una función puede llevar casos concretos de lo que debe dar, y
`nex test` los comprueba sin escribir `main`. Implementa la
[decisión 0008](docs/decisions/0008-ejemplos-y-nex-test.md) y la
[decisión 0009](docs/decisions/0009-memoria-agotada.md).

### Añadido

- **Ejemplos en las funciones:** `example double(2) == 4, "Two doubled"`, una cláusula del principio
  del cuerpo junto a `requires` y `ensures`. Es una expresión `Bool` que tiene que llamar a su propia
  función (`E2020` si no lo hace) y que no ve los parámetros ni `result`. El análisis nunca la evalúa.
- **`nex test`**: evalúa los ejemplos, cada uno en un intérprete nuevo, comprobando los contratos de
  todo lo que se ejecuta. No exige `main` ni lo ejecuta. Opciones `--format text|json` y
  `--function FUNCION`. Cada ejemplo termina en `passed`, `failed` (`E4004`, categoría nueva `test`) o
  `error` (el diagnóstico original, con una nota que identifica el ejemplo).
- Código de salida `6`: algún ejemplo no pasó, o no había ningún ejemplo que evaluar.
- Formato `nexora.test/1` y `nexora.api.test_source`, que devuelve el mismo documento.
- `nex inspect`: nodo `Example` y campo `examples` al final de `Function` (sigue siendo
  `nexora.inspect/2`). `nex context`: campo `examples` y valor `examples` en `features`.
- Ejemplo `examples/checked_examples.nex`.
- **`E3007` (Out of memory):** un programa que agota la memoria mientras se ejecuta recibe un
  diagnóstico de ejecución, con la cadena de llamadas, en vez de un error interno. En `nex test`, el
  ejemplo queda en `error` y se evalúan los siguientes. `nexora.api.run_source` sigue respondiendo
  `memory_limit`, con el mismo mensaje, y ahora con el `E3007` en `diagnostics`.

### Corregido

- **Las pruebas de npm y del servidor no se ejecutaban con Node 18 y 20.** `node --test` solo expande
  patrones como `"test/*.test.js"` desde Node 21, así que con las versiones que declaran los paquetes
  no encontraba ningún archivo. Los scripts nombran ahora cada archivo, y una prueba comprueba que no
  falte ninguno. La integración continua prueba npm con Node 18, 20 y 22, y el servidor con Node 20.6
  y 22.

### Cambios incompatibles

- `example` pasa de palabra reservada a palabra clave. Ningún programa válido podía usarla como
  nombre.
- **`nex run` con un programa que agota la memoria termina con `3`, no con `70`**, y la salida de
  error muestra `runtime error[E3007]` en vez de `internal error`. Con `--format json` escribe el
  documento `nexora.diagnostics/1`. El código `70` vuelve a significar solo un defecto de NEXORA.
  Un script que trate `70` como "falta de memoria" debe mirar el código `E3007`.

### Limitaciones

- `nex test` no tiene límite de tiempo ni de memoria por ejemplo.
- `E3007` solo aparece si Python llega a quedarse sin memoria. En Linux, el sistema puede matar el
  proceso antes, sin ningún mensaje.
- Una memoria agotada fuera de la ejecución (al analizar el programa o al construir un informe)
  sigue terminando con `70`.

## 0.3.1 — Revisión de los tipos refinados

Resultado de intentar romper las garantías de la 0.3.0. La garantía principal resistió: ningún
camino permite que un valor llegue a un tipo refinado sin cumplir su condición, y la comprobación
sin ejecutar y la ejecución coinciden en los casos límite (`-0.0`, redondeo de `Float`, división
por cero evitada con `and`, desbordamiento). Esos ataques forman parte ahora de las pruebas.
La revisión encontró cuatro defectos alrededor de esa garantía, corregidos aquí.

### Corregido

- **`nex check` podía tardar demasiado con tipos refinados.** Cada constante evalúa las condiciones
  de toda la cadena de su tipo, así que el trabajo crecía con tipos × condiciones × constantes: un
  programa válido de 60 KB tardaba 2,5 s y agotaba el tiempo del playground (2 s). Ahora el
  trabajo está acotado a 100 000 nodos de condición evaluados; por encima, el programa se rechaza
  con el código nuevo `E2019` en vez de quedar comprobado a medias. El mismo programa se rechaza
  ahora en 0,18 s, y uno corriente se comprueba en centésimas.
- **Una condición de tipo mal escrita producía errores falsos en cada uso del tipo** ("Cannot apply
  '+' to Bad and Int", "Expected Bad, found Int"). Las condiciones se comprueban ahora antes que las
  firmas, y un tipo con la condición incorrecta queda fuera sin más errores.
- **Un error de ejecución dentro de una condición no decía dónde se pidió la comprobación.** Si
  `Huge(n)` desbordaba dentro de la condición de `Huge`, el diagnóstico señalaba la declaración del
  tipo y nada más. Ahora añade la nota `While checking that a value is a valid Huge, at line …`.
- **Una explicación con `\n` rompía el formato de texto del diagnóstico.** Una explicación es ahora
  una sola línea: un `\n` en ella es el error `E1101`.

### Documentación

- La especificación (sección 10.1), la guía del servidor MCP y la descripción de
  `analysis_executes_code` decían que el análisis "no ejecuta nada". Ahora dicen con precisión lo
  que hace: no ejecuta el programa, pero evalúa las condiciones de los tipos refinados sobre las
  constantes, sin llamadas a funciones del programa y con el trabajo acotado.
- Nuevo límite en el documento de capacidades (`get_capabilities()` en Python y en el servidor
  MCP): `max_refinement_steps`.

## 0.3.0 — Contratos y tipos refinados

Consolida la característica que distingue a NEXORA: los requisitos forman parte verificable del
programa ([decisión 0006](docs/decisions/0006-requisitos-verificables.md)). Los contratos dejan de
ser experimentales, cada regla puede llevar su explicación y llegan los tipos refinados. Los motivos
de cada elección están en la [decisión 0007](docs/decisions/0007-contratos-estables-y-tipos-refinados.md).

Esta versión incluye también todo lo hecho después de la 0.2.0 que no llegó a publicarse con otro
número: documentación, pruebas, playground y herramientas de análisis.

### Añadido

- **Tipos refinados:** `type Percent = Int where value >= 0 and value <= 100`. Todo valor de un
  tipo refinado cumple su condición:
  - Una constante usada como valor del tipo se comprueba **sin ejecutar** (`E2017`).
  - Cualquier otro valor se comprueba explícitamente con `Percent(x)`, al ejecutar (`E4003`,
    categoría `contract`, código de salida `5`).
  - Un valor refinado se acepta donde se espera su base; una operación con él da un valor de la
    base.
  - Un tipo puede refinar otro (`type Pass = Percent where value >= 50`); se comprueban las dos
    condiciones, desde la base.
  - La condición solo puede usar `value`, literales, operadores y conversiones integradas
    (`E2018`).
- **Explicación de las reglas:** `requires amount <= balance, "An account cannot go below zero"`.
  Sirve en `requires`, `ensures` y `where`, y aparece en el diagnóstico como `Reason: ...` cuando
  la regla se incumple.
- Códigos nuevos: `E2016` (declaración de tipo no válida), `E2017` (constante fuera del tipo
  refinado), `E2018` (condición de refinamiento no válida) y `E4003` (refinamiento incumplido).
- `nex context` lista los tipos refinados (campo `types`) y la explicación de cada contrato (campo
  `message`). Característica nueva en `features`: `refined_types`.
- Ejemplos `refined_types.nex`, `invalid/refinement_errors.nex` y
  `failing/refinement_violation.nex`.
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

- **`type` y `where` son palabras clave** (antes, palabras reservadas). Ningún programa válido de la
  0.2 podía usarlas como nombres, así que ninguno deja de funcionar.
- **`nex inspect` pasa a `nexora.inspect/2`.** El campo `type` de una expresión puede ser el nombre
  de un tipo refinado, no solo `Int`, `Float`, `Bool`, `Text` o `Void`. Añadidos: nodo `TypeDecl`,
  campo `types` en `Program` y campo `message` en `Contract`. Cómo actualizar: aceptar cualquier
  texto en `type` y comprobar `schema`.
- Los contratos dejan de ser experimentales: su sintaxis no cambia, pero a partir de ahora solo
  cambiará siguiendo las reglas de los cambios incompatibles.
- El paquete de Python pasa a llamarse `nexora-lang` (antes `nexora`), porque `nexora` ya existe en
  PyPI. El comando (`nex`) y el módulo (`import nexora`) no cambian. Cómo actualizar una
  instalación en modo desarrollo: `python -m pip uninstall nexora` y `python -m pip install -e .`.
  Los archivos generados se llaman ahora `nexora_lang-0.3.0…`, y el extra opcional se instala con
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
- Especificación 0.3: sección 4.4 (tipos refinados), contratos estables (sección 9) y códigos
  nuevos. Guías de tipos y contratos ampliadas. Decisiones 0006 y 0007.

### Limitaciones

- De los tipos refinados, `nex check` solo comprueba las constantes; un valor calculado se comprueba
  al ejecutar. No existe forma de comprobarlo sin detener el programa si falla (no hay `Result`).
- No hay alias de tipos sin condición.
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
