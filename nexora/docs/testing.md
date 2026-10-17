# Pruebas

Cómo se comprueba que NEXORA hace lo que dice su documentación, cómo ejecutar esas comprobaciones
y qué **no** cubren.

## Ejecutar las comprobaciones

Con el entorno virtual activado y las herramientas de desarrollo instaladas
(`python -m pip install -e ".[dev]"`), desde el directorio `nexora/`:

```bash
python -m ruff check src tests     # análisis estático del código Python
python -m pytest                   # todas las pruebas
python -m pytest --cov             # pruebas con medición de cobertura
```

Opciones útiles:

```bash
python -m pytest tests/test_parser.py          # un solo archivo
python -m pytest -k recursion                  # las pruebas cuyo nombre contiene "recursion"
python -m pytest -x                            # detenerse en el primer fallo
python -m pytest --cov --cov-report=html       # informe navegable en htmlcov/index.html
```

La batería completa tarda unos tres minutos. Las pruebas no necesitan conexión a internet.

## Última medición

Realizada el 15 de octubre de 2026, en Windows 11 con Python 3.12.10:

| Comprobación | Resultado |
|--------------|-----------|
| `python -m ruff check src tests` | Sin errores |
| `python -m pytest` | 1600 pruebas superadas, 4 omitidas, 0 fallos |
| Cobertura de líneas y ramas (`--cov`) | 94,48 % |
| Umbral configurado (`fail_under` en `pyproject.toml`) | 90 % |
| Pruebas del servidor web (`node --test "test/*.test.js"`, en `servidor/`) | 112 superadas, 0 fallos |

Las 112 pruebas del servidor son las de esta medición y las de `v0.6.0`. Después del tag, el commit
`cb709ff` añadió `servidor/test/playground-config.test.js`: en `main`, en el commit `7c87027`,
`npm test` en `servidor/` da 130 superadas y 0 fallos (15 de octubre de 2026, Windows 11, Node
24.21.0). Esa ejecución solo repitió las pruebas del servidor; el resto de la tabla no se volvió a
medir. En la rama `fix/playground-container-lifecycle`, que añade
`servidor/test/playground-containers.test.js`, `npm test` da 154 superadas y 0 fallos en cada una
de seis ejecuciones en el commit `d5585099`, y 325 superadas y 0 fallos en cada una de seis
ejecuciones después de añadir las pruebas del formato de la orden de contenedor y de la imagen
local (16 de octubre de 2026, Windows 11, Node 24.21.0). Las pruebas del formato solo analizan la
orden; las del ciclo de vida usan un Docker falso. No se ejecutó ningún contenedor real.

Las cuatro pruebas omitidas necesitan funciones de POSIX que Windows no tiene: una comprueba un
archivo sin permiso de lectura (el mismo caso se cubre en Windows simulando el error), y tres
comprueban los límites de memoria y de CPU que el proceso del playground pide al sistema operativo.
En Windows se omiten; en Linux se ejecutan y pasan (siguiente apartado).

### Linux

Realizada el 17 de octubre de 2026 en Ubuntu 24.04 sobre WSL 2 (núcleo 6.18), con un usuario que
no es root (uid 1000), con Node.js 24.11.1. Se ejecutó sobre una copia, en el sistema de archivos de
Linux (no en `/mnt/c`), del árbol de trabajo de la rama `fix/playground-container-lifecycle` en el
commit `237184b`. En `nexora/` y `npm/` ese árbol no tenía cambios sin commit; en `servidor/` y
`web/` tenía cambios en curso, sin commit (páginas de la web, CAPTCHA y sus pruebas), que entran en
la cifra de `npm test` en `servidor/`:

| Comprobación | Resultado |
|--------------|-----------|
| `python -m ruff check src tests` | Sin errores |
| `python -m pytest --cov`, Python 3.12.3 | 1604 pruebas superadas, **0 omitidas**, 0 fallos; cobertura del 94,48 % |
| `python -m pytest` (sin `--cov`), Python 3.11.17 y 3.13.16 | 1604 superadas, 0 omitidas, 0 fallos en cada versión |
| `npm test` en `npm/` | 12 superadas, 0 fallos |
| `npm test` en `servidor/`, con el árbol de trabajo descrito arriba | 355 superadas, 0 fallos, en cada una de dos ejecuciones |
| Paquete de pip: `python -m build`, instalación del wheel con `--no-index` en un entorno limpio, `nex run` y `nex --version` | Sin errores |
| Paquete de npm: `npm pack`, instalación desde el archivo y `npx nex run` | Sin errores |

Las cuatro pruebas de POSIX se ejecutaron por primera vez y pasaron: el archivo sin permiso de
lectura da `E0001`, y los límites de memoria, de tiempo real y de CPU terminan el programa. Esos
límites se probaron con `tests/test_worker.py`, que lanza el worker directamente como proceso, sin
contenedor y sin pasar por el servidor.

`ruff`, la cobertura, las pruebas de `npm/` y `servidor/` y los paquetes se comprobaron solo con
Python 3.12.3; con 3.11 y 3.13 solo se ejecutó `pytest`. Python 3.11 y 3.13 se instalaron con `uv`;
Ubuntu solo trae la 3.12. Las pruebas del servidor necesitan el entorno de `nexora/.venv` (en Linux,
`nexora/.venv/bin/python`), igual que en Windows.

**No se ejecutó Docker** ni ninguna de las comprobaciones de
[aislamiento del playground](playground.md#comprobar-el-aislamiento), que siguen pendientes.

Después, el 17 de octubre de 2026, en la rama `feature/server-hardening`, solo se ejecutó
`npm test` en `servidor/`. El servidor (antispam, límites por cliente, freno del inicio de sesión,
borrado de sesiones caducadas, cabeceras de seguridad y tipografías propias) ya estaba en los
commits `a8a956b`, `cda0ee9` y `a160829`; la web (gestor de consentimiento, formularios de cuenta,
páginas legales en borrador y documentación ampliada) y sus pruebas seguían sin commit. Una cifra
anterior de ese mismo día, 522 superadas, solo en Windows, corresponde a un estado previo del trabajo.

| Árbol | Windows 11, Node 24.21.0 | Ubuntu 24.04.5 en WSL 2, Node 24.11.1 |
|-------|--------------------------|---------------------------------------|
| `a160829` sin los cambios sin commit | 492 superadas, 0 fallos (una ejecución) | No se ejecutó |
| `a160829` con los cambios sin commit (auditoría) | **565 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | **565 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones |
| El mismo árbol tras las correcciones de la auditoría | **567 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | **567 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones |
| `dce6061` con las correcciones de la revisión visual, sin commit | **575 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |

En Linux se usó una copia nueva del árbol de trabajo, comprobada archivo por archivo con SHA-256, con
las dependencias instaladas con `npm ci` y el intérprete de `nexora/.venv` (Python 3.12.3). La fila
de 567 se ejecutó en Linux antes de añadir este apartado: esa copia solo difería del árbol en este
archivo.

Las ocho pruebas nuevas de la última fila cubren `GET /api/playground/status` con el playground
activado y desactivado (sin arrancar el worker); que la página desactivada solo pregunta `/status`,
no envía nada al pulsar Run o Check y conserva el código guardado; que Run y Check no envían nada
mientras el servidor no confirme que el playground está activado (sin respuesta, con una respuesta
que no entiende o con un error del servicio); que en un servidor anterior sin `/status` decide
`/info`, como antes; que una conexión perdida después se sigue avisando al pulsar Run; y que las
páginas legales en borrador llevan `noindex`.

Son pruebas automatizadas: la base de datos MySQL, las respuestas de Google reCAPTCHA y el navegador
están simulados (el gestor de consentimiento y los formularios se ejecutan en un DOM mínimo,
`servidor/test/fixtures/mini-dom.js`). **Siguen pendientes las comprobaciones reales**: contra un
MySQL real, con claves reales de reCAPTCHA, en un navegador con esos servicios reales, detrás de
nginx y con las cabeceras del servidor de producción. Tampoco se ejecutó Docker. La web sí se revisó
a mano en el navegador, sin esos servicios ([Revisión visual de la web](#revisión-visual-de-la-web)).

La cobertura bajó respecto a la medición anterior (99,56 %) porque dos módulos nuevos se prueban
lanzándolos como procesos aparte, que la medición no sigue: `worker.py` y `mcp_server.py`.

Estas cifras son una fotografía de ese día. Para conocer las actuales, ejecuta los comandos.

### Revisión visual de la web

El 17 de octubre de 2026 se revisó la web en Chrome (escritorio, 1912×948) y en Microsoft Edge 155
sin interfaz, controlado por CDP, a 320×640, 360×740, 390×844, 820×1180, 1366×768 y 1440×900. El
servidor de prueba arrancó sin `servidor/.env` y con la base de datos en un puerto cerrado, para que
no pudiera leer ni escribir en MySQL (al arrancar borra las sesiones caducadas), con el playground
desactivado. Tras las correcciones se repitió a 320×640, 360×740, 390×844 y 1366×768: ninguna
página se desborda en horizontal, los controles del playground, del registro y del inicio de sesión
se ven enteros al recorrerlos con Tab, y el registro cabe en 1366×768.

**No se comprobó**: el playground activado en el navegador (sí en las pruebas automatizadas), los
mensajes reales de inicio de sesión y de registro, que necesitan la base de datos, Firefox, Safari,
lectores de pantalla ni reCAPTCHA con claves reales.

### Cobertura por componente

| Módulo | Líneas y ramas cubiertas |
|--------|--------------------------|
| `lexer.py` | 100 % |
| `parser.py` | 99 % |
| `checker.py` | 99 % |
| `interpreter.py` | 99 % |
| `diagnostics.py` | 98 % |
| `cli.py` | 92 % |
| `api.py` | 100 % |
| `tooling.py` | 96 % |
| `ast_nodes.py`, `pipeline.py`, `prelude.py`, `schemas.py`, `tokens.py`, `values.py` | 100 % |
| `mcp_server.py` | 30 % medido (ver abajo) |
| `__main__.py`, `worker.py` | 0 % medido (ver abajo) |

Lo que queda sin cubrir, y por qué:

- **`worker.py` y `mcp_server.py`** se prueban de verdad, pero como procesos aparte:
  `tests/test_worker.py` lanza el proceso y le envía peticiones, y `tests/test_mcp.py` arranca el
  servidor y habla con él por el protocolo MCP. La medición no sigue a los procesos hijos, así que
  su porcentaje no refleja lo que se ejecuta.
- **`tooling.py`**: en la salida de texto, el camino de un programa que no llegó a analizarse, el
  bloque de los tipos refinados de `nex context`, una cláusula de bucle escrita sin explicación, y
  los dos mensajes de `nex symbols` cuando no hay símbolos que mostrar.
- **`__main__.py`** (dos líneas) se ejecuta en todas las pruebas que lanzan `python -m nexora` en
  un proceso aparte, pero la medición no sigue a los procesos hijos.
- **`cli.py`**: la rama que se ejecuta si la terminal no permite cambiar la codificación a UTF-8, y
  la que redirige la salida cuando el lector se cierra. La segunda se prueba con un proceso real,
  fuera de la medición.
- **`diagnostics.py`**: la petición de una línea que no existe en el archivo.
- Las ramas defensivas del intérprete que solo se alcanzarían con un defecto del comprobador están
  excluidas de la medición de forma explícita en `pyproject.toml`.

**Una cobertura alta no demuestra que el programa sea correcto.** Indica que casi todo el código se
ejecuta en alguna prueba; no que se hayan probado todas las combinaciones de entradas.

## Qué comprueba cada archivo

| Archivo | Pruebas | Qué comprueba |
|---------|---------|---------------|
| `test_lexer.py` | 51 | Tokens, literales, comentarios, finales de línea, posiciones, caracteres inválidos, textos sin cerrar |
| `test_parser.py` | 68 | Programas válidos, precedencia, forma del árbol, cada error de sintaxis con su posición, recuperación tras un error, límites de anidamiento |
| `test_checker.py` | 56 | `main`, variables, ámbitos, declaraciones duplicadas, llamadas, orden de las etapas |
| `test_types.py` | 140 | Inferencia, anotaciones, cada operador con cada combinación de tipos, conversiones, condiciones |
| `test_refined_types.py` | 68 | Tipos refinados (`type Name = Base where condition`): que las constantes los comprueba el análisis estático (`E2017`) y cualquier otro valor solo al comprobarlo con `Name(x)` mientras el programa corre (`E4003`) |
| `test_functions.py` | 56 | Parámetros, argumentos, retornos, rutas de retorno, `if` / `else`, funciones `Void`, recursividad y su límite |
| `test_contracts.py` | 50 | `requires` y `ensures` que se cumplen y que fallan, tipos de las condiciones, `result`, contenido de los diagnósticos |
| `test_example_clauses.py` | 43 | La cláusula `example` tal y como la ve el análisis estático: sintaxis, tipos, nombres, la regla de llamada propia y el grafo de llamadas. No evalúa ningún ejemplo ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `test_text_operations.py` | 181 | Las funciones de un tipo (`Text.length`, `Int.parse`…) y el orden entre textos: cada caso de la decisión, sus requisitos y sugerencias, textos enormes, redondeo y límites de `Float`, la sintaxis del punto y sus errores, que los programas de la 0.5.1 no cambian, y `inspect`, `symbols`, `context` y las capacidades ([decisión 0011](decisions/0011-operaciones-sobre-textos.md)) |
| `test_loops.py` | 96 | `var`, asignaciones, bucles con su medida y sus invariantes: análisis, cada diagnóstico con su vuelta y sus valores, que ningún bucle se queda colgado (tampoco en `nex test`), y lo que muestran `inspect`, `symbols` y `context` ([decisión 0010](decisions/0010-var-y-while.md)) |
| `test_interpreter.py` | 47 | Salida de los programas, aritmética entera y decimal, desbordamiento, división por cero |
| `test_out_of_memory.py` | 20 | Un programa que se queda sin memoria mientras corre: el `E3007`. El `MemoryError` se provoca a propósito, así que ninguna prueba agota la memoria real ([decisión 0009](decisions/0009-memoria-agotada.md)) |
| `test_diagnostics.py` | 16 | Formato de texto, formato JSON, y que el registro de códigos coincide con la especificación |
| `test_inspect.py` | 9 | El esquema JSON de `nex inspect`: nodos, campos, tipos y posiciones |
| `test_cli.py` | 74 | Comandos, opciones, códigos de salida y formatos; también con el comando real en un proceso aparte, desde otros directorios |
| `test_examples.py` | 68 | Cada programa de `examples/`: salida, diagnósticos y código de salida, comparados con los registrados |
| `test_nex_test.py` | 46 | La evaluación de ejemplos: el motor, `nexora.api.test_source` y el comando `nex test`, con los casos de la matriz de la decisión ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `test_docs.py` | 163 | Cada programa de la documentación y su salida; enlaces; versión; que la referencia de la CLI y la lista de códigos están completas |
| `test_security.py` | 70 | Que el intérprete no evalúa código Python, qué puede hacer un programa, qué módulos puede importar cada archivo, que las herramientas de análisis no ejecutan |
| `test_robustness.py` | 86 | Entradas truncadas, mutadas, aleatorias, binarias, enormes o muy anidadas; regresiones de defectos reales |
| `test_api.py` | 38 | Comprobar y ejecutar código en memoria (`nexora.api`), con sus límites de salida y de texto |
| `test_worker.py` | 23 | El proceso de un solo uso del playground: peticiones válidas e inválidas, límites, entorno |
| `test_tooling.py` | 81 | Los JSON Schema y que la salida real los cumple; símbolos, referencias y contexto; el análisis parcial con errores de sintaxis, incluido un programa cortado en cada carácter; que el análisis no ejecuta ni abre archivos; que la CLI y la API devuelven lo mismo |
| `test_tooling_tasks.py` | 19 | Las nueve [tareas de referencia](ai-tooling.md#tareas-de-referencia) contra las herramientas reales |
| `test_mcp.py` | 35 | El servidor MCP por su protocolo real: inicio, descubrimiento de herramientas, llamadas, argumentos rechazados, que ninguna herramienta ejecuta código, cierre |

`test_mcp.py` necesita el SDK de MCP, que forma parte de las dependencias de desarrollo. Si no está
instalado, sus pruebas se omiten.

## Cómo están hechas

### Tres niveles

1. **Unitarias.** Llaman a una etapa (lexer, parser, comprobador, intérprete) y comprueban su
   resultado: tokens, forma del árbol, códigos de error, salida.
2. **De integración.** Llaman a `cli.main` con una lista de argumentos y un archivo temporal, y
   comprueban salida estándar, salida de error y código de salida.
3. **De extremo a extremo.** Lanzan el comando real (`python -m nexora`, y el ejecutable `nex`
   instalado) en un proceso aparte, como haría una persona.

### Salidas registradas

`tests/golden/examples/` guarda, para cada ejemplo, lo que escriben `nex run` y `nex check`. Las
pruebas comparan carácter a carácter. Así un cambio que altere un mensaje, una posición o un
resultado no pasa inadvertido.

### Documentación ejecutable

Los bloques de código NEXORA de los archivos Markdown llevan un comentario marcador
(`<!-- nex:run -->`, `<!-- nex:check-fails -->`…) que indica cómo comprobarlos. `test_docs.py`
ejecuta cada uno y compara la salida que muestra la documentación con la real. Un programa
completo sin marcador hace fallar las pruebas. Los marcadores están descritos al principio de
`tests/test_docs.py` y en [`CONTRIBUTING.md`](../CONTRIBUTING.md#programas-en-la-documentación).

### Listas que no pueden desincronizarse

Hay pruebas cuyo único fin es impedir que dos descripciones de lo mismo diverjan:

| Qué | Dónde está descrito | Se compara con |
|-----|---------------------|----------------|
| Códigos de error, títulos y categorías | `docs/language-spec.md`, `docs/diagnostics.md` | El registro de `diagnostics.py` |
| Nodos y campos del árbol | `docs/inspect-schema.md` | Las clases de `ast_nodes.py` |
| Comandos, opciones y códigos de salida | `docs/cli-reference.md` | El analizador de argumentos de `cli.py` |
| Versión | `README.md` y otras páginas | `version.py` y el paquete instalado |
| Ejemplos | `examples/README.md` | Los archivos de `examples/` |
| Palabras clave y funciones integradas | Los ejemplos válidos | `tokens.py`, `checker.py` |

### Pruebas con entradas generadas

`test_robustness.py` somete al intérprete a entradas que nadie escribiría a propósito:

- Cada ejemplo válido, cortado en **cada** carácter y con **cada** elemento eliminado.
- 3000 secuencias aleatorias de elementos del lenguaje y 1500 mutaciones de programas válidos, con
  una semilla fija para que el resultado sea reproducible.
- Archivos de bytes aleatorios a través de la línea de comandos.
- Programas enormes y con anidamiento extremo.

La condición es siempre la misma: el resultado tiene que ser un programa aceptado o diagnósticos de
NEXORA. Una excepción de Python es un fallo de la prueba.

### Regresiones

Cada defecto real encontrado tiene una prueba que lo reproduce, con el prefijo `test_regression_`
en `test_robustness.py`:

| Defecto | Prueba |
|---------|--------|
| Un entero literal de más de 4300 cifras provocaba un error interno | `test_regression_very_long_integer_literal` |
| Un archivo binario producía un error por carácter, sin límite | `test_regression_a_binary_file_does_not_produce_one_error_per_byte` |
| El mensaje de pila agotada afirmaba "más de 1000 llamadas" sin ser cierto | `test_regression_stack_exhaustion_is_not_described_as_a_thousand_calls` |
| En el JSON de `nex inspect`, un campo de los contratos sustituía al tipo de nodo | `test_regression_contract_field_does_not_overwrite_the_node_kind` |

Y, en `test_cli.py`, el cierre anticipado del lector de la salida
(`test_process_reader_that_stops_early`), que antes se mostraba como error interno.

## Empaquetado

No es una prueba automatizada de la batería; se comprueba a mano con estos pasos.

```bash
python -m pip install build
python -m build
```

Genera `dist/nexora_lang-0.6.0-py3-none-any.whl` (el intérprete y el comando `nex`) y
`dist/nexora_lang-0.6.0.tar.gz` (además: documentación, ejemplos y pruebas).

Comprobado el 15 de octubre de 2026 para la 0.6.0, con los dos paquetes generados a partir del
commit `5324619` (el de `v0.6.0`), en Windows 11 con Python 3.12.10:

| Comprobación | Resultado |
|--------------|-----------|
| Instalar el `.whl` en un entorno virtual nuevo, sin acceso a la red (`pip install --no-index`) | Correcto; no instala ninguna otra dependencia |
| `nex --version`, `nex run` y `python -m nexora check` desde ese entorno | Correcto |
| Extraer el `.tar.gz` en una carpeta vacía, crear un entorno, `pip install -e ".[dev]"` | Correcto |
| `ruff` y la batería completa de pruebas (`pytest --cov`) en esa copia limpia | Sin errores: 1600 pruebas superadas y 4 omitidas (las de POSIX), cobertura del 94,48 % |

Esas cifras son de la copia extraída del `.tar.gz`. En el propio repositorio, la batería completa no
se repitió sobre el commit `5324619`.

La segunda comprobación equivale a partir de un clon limpio: demuestra que el paquete de código
fuente contiene todo lo necesario para instalar, probar y documentar el proyecto.

El paquete no se publica en ningún repositorio.

## Integración continua

En la raíz del repositorio, `.github/workflows/nexora-ci.yml` define las mismas comprobaciones para
GitHub Actions: análisis del código, pruebas con cobertura y generación del paquete, en Linux,
Windows y macOS con Python 3.11, 3.12 y 3.13.

**Ese flujo no se ha ejecutado nunca**: el proyecto no tiene todavía un repositorio en GitHub. En
Linux, las pruebas se han ejecutado a mano ([Linux](#linux)); en macOS, y en Windows con Python 3.11
y 3.13, no se sabe si pasan. Por eso el
`README` no muestra ninguna insignia de estado.

## Lo que las pruebas no cubren

- **Otras plataformas.** Se han ejecutado en Windows 11 con Python 3.12 y en Linux (Ubuntu 24.04
  sobre WSL 2) con Python 3.11, 3.12 y 3.13. macOS, otras distribuciones y Linux sin WSL, no.
- **Rendimiento.** No hay pruebas de velocidad ni de consumo de memoria.
- **Tiempo y memoria sin límite.** Un programa puede tardar o consumir memoria indefinidamente; no
  hay pruebas sobre ello porque el intérprete no lo impide.
- **Exhaustividad.** Las pruebas con entradas generadas son una muestra de unos miles de casos, no
  una demostración.
- **Corrección de los contratos.** Se prueba que los contratos se comprueban cuando deben, no que
  demuestren nada sobre un programa.
- **Los bloques de documentación sin `fn main` y sin marcador** (fragmentos que ilustran una regla)
  no se ejecutan.
- **El servidor MCP dentro de un asistente real.** Las pruebas automáticas usan el cliente del SDK.
  Hay una única comprobación manual con Claude Code, descrita en
  [Servidor MCP](mcp.md#comprobación-en-claude-code).
- **Ningún modelo de IA.** Las tareas de referencia miden las herramientas deterministas.
- **El aislamiento del playground con contenedor** no se ha ejecutado. Los límites POSIX del worker,
  lanzado como proceso sin contenedor, sí, en Linux.
- **La web del proyecto** (`web/`): el playground y la guía tienen pruebas en `servidor/test/`
  (lógica del editor, API, enlaces); el aspecto visual y el resto de páginas, no.
- **La instalación del paquete en un entorno limpio** no se ha repetido desde que se añadieron las
  herramientas de análisis. El paquete se genera sin errores e incluye los esquemas y el comando
  `nex-mcp`, pero la comprobación completa de [Empaquetado](#empaquetado) es anterior.
