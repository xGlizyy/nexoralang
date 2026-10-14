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

Realizada el 14 de octubre de 2026, en Windows 11 con Python 3.12.10:

| Comprobación | Resultado |
|--------------|-----------|
| `python -m ruff check src tests` | Sin errores |
| `python -m pytest` | 1039 pruebas superadas, 4 omitidas, 0 fallos |
| Cobertura de líneas y ramas (`--cov`) | 93,25 % |
| Umbral configurado (`fail_under` en `pyproject.toml`) | 90 % |
| Pruebas del servidor web (`node --test "test/*.test.js"`, en `servidor/`) | 98 superadas, 0 fallos |

Las cuatro pruebas omitidas necesitan funciones de POSIX que Windows no tiene, y **no se han
ejecutado nunca**: una comprueba un archivo sin permiso de lectura (el mismo caso se cubre en
Windows simulando el error), y tres comprueban los límites de memoria y de CPU que el proceso del
playground pide al sistema operativo.

La cobertura bajó respecto a la medición anterior (99,56 %) porque dos módulos nuevos se prueban
lanzándolos como procesos aparte, que la medición no sigue: `worker.py` y `mcp_server.py`.

Estas cifras son una fotografía de ese día. Para conocer las actuales, ejecuta los comandos.

### Cobertura por componente

| Módulo | Líneas y ramas cubiertas |
|--------|--------------------------|
| `lexer.py` | 100 % |
| `parser.py` | 99 % |
| `checker.py` | 100 % |
| `interpreter.py` | 100 % |
| `diagnostics.py` | 98 % |
| `cli.py` | 97 % |
| `api.py` | 97 % |
| `tooling.py` | 97 % |
| `ast_nodes.py`, `pipeline.py`, `schemas.py`, `tokens.py`, `values.py` | 100 % |
| `mcp_server.py` | 30 % medido (ver abajo) |
| `__main__.py`, `worker.py` | 0 % medido (ver abajo) |

Lo que queda sin cubrir, y por qué:

- **`worker.py` y `mcp_server.py`** se prueban de verdad, pero como procesos aparte:
  `tests/test_worker.py` lanza el proceso y le envía peticiones, y `tests/test_mcp.py` arranca el
  servidor y habla con él por el protocolo MCP. La medición no sigue a los procesos hijos, así que
  su porcentaje no refleja lo que se ejecuta.
- **`tooling.py`**: el recorte de una condición de contrato escrita en varias líneas y dos mensajes
  de la presentación en texto de `nex symbols`.
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
| `test_lexer.py` | 45 | Tokens, literales, comentarios, finales de línea, posiciones, caracteres inválidos, textos sin cerrar |
| `test_parser.py` | 68 | Programas válidos, precedencia, forma del árbol, cada error de sintaxis con su posición, recuperación tras un error, límites de anidamiento |
| `test_checker.py` | 56 | `main`, variables, ámbitos, declaraciones duplicadas, llamadas, orden de las etapas |
| `test_types.py` | 139 | Inferencia, anotaciones, cada operador con cada combinación de tipos, conversiones, condiciones |
| `test_functions.py` | 56 | Parámetros, argumentos, retornos, rutas de retorno, `if` / `else`, funciones `Void`, recursividad y su límite |
| `test_contracts.py` | 41 | `requires` y `ensures` que se cumplen y que fallan, tipos de las condiciones, `result`, contenido de los diagnósticos |
| `test_interpreter.py` | 47 | Salida de los programas, aritmética entera y decimal, desbordamiento, división por cero |
| `test_diagnostics.py` | 16 | Formato de texto, formato JSON, y que el registro de códigos coincide con la especificación |
| `test_inspect.py` | 8 | El esquema JSON de `nex inspect`: nodos, campos, tipos y posiciones |
| `test_cli.py` | 74 | Comandos, opciones, códigos de salida y formatos; también con el comando real en un proceso aparte, desde otros directorios |
| `test_examples.py` | 39 | Cada programa de `examples/`: salida, diagnósticos y código de salida, comparados con los registrados |
| `test_docs.py` | 129 | Cada programa de la documentación y su salida; enlaces; versión; que la referencia de la CLI y la lista de códigos están completas |
| `test_security.py` | 68 | Que el intérprete no evalúa código Python, qué puede hacer un programa, qué módulos puede importar cada archivo, que las herramientas de análisis no ejecutan |
| `test_robustness.py` | 78 | Entradas truncadas, mutadas, aleatorias, binarias, enormes o muy anidadas; regresiones de defectos reales |
| `test_api.py` | 30 | Comprobar y ejecutar código en memoria (`nexora.api`), con sus límites de salida y de texto |
| `test_worker.py` | 23 | El proceso de un solo uso del playground: peticiones válidas e inválidas, límites, entorno |
| `test_tooling.py` | 72 | Los JSON Schema y que la salida real los cumple; símbolos, referencias y contexto; el análisis parcial con errores de sintaxis, incluido un programa cortado en cada carácter; que el análisis no ejecuta ni abre archivos; que la CLI y la API devuelven lo mismo |
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

Genera `dist/nexora_lang-0.4.0-py3-none-any.whl` (el intérprete y el comando `nex`) y
`dist/nexora_lang-0.4.0.tar.gz` (además: documentación, ejemplos y pruebas).

Comprobado el 14 de octubre de 2026 en Windows 11 con Python 3.12:

| Comprobación | Resultado |
|--------------|-----------|
| Instalar el `.whl` en un entorno virtual nuevo, sin acceso a la red (`pip install --no-index`) | Correcto; no instala ninguna otra dependencia |
| `nex --version`, `nex run` y `python -m nexora check` desde ese entorno | Correcto |
| Extraer el `.tar.gz` en una carpeta vacía, crear un entorno, `pip install -e ".[dev]"` | Correcto |
| `ruff` y la batería completa de pruebas en esa copia limpia | Sin errores; mismas pruebas que en el repositorio |

La segunda comprobación equivale a partir de un clon limpio: demuestra que el paquete de código
fuente contiene todo lo necesario para instalar, probar y documentar el proyecto.

El paquete no se publica en ningún repositorio.

## Integración continua

En la raíz del repositorio, `.github/workflows/nexora-ci.yml` define las mismas comprobaciones para
GitHub Actions: análisis del código, pruebas con cobertura y generación del paquete, en Linux,
Windows y macOS con Python 3.11, 3.12 y 3.13.

**Ese flujo no se ha ejecutado nunca**: el proyecto no tiene todavía un repositorio en GitHub. No
se sabe si pasa en Linux, en macOS ni en otras versiones de Python hasta que se ejecute. Por eso el
`README` no muestra ninguna insignia de estado.

## Lo que las pruebas no cubren

- **Otras plataformas.** Solo se han ejecutado en Windows 11 con Python 3.12.
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
- **El aislamiento del playground con contenedor** y sus límites POSIX no se han ejecutado.
- **La web del proyecto** (`web/`): el playground y la guía tienen pruebas en `servidor/test/`
  (lógica del editor, API, enlaces); el aspecto visual y el resto de páginas, no.
- **La instalación del paquete en un entorno limpio** no se ha repetido desde que se añadieron las
  herramientas de análisis. El paquete se genera sin errores e incluye los esquemas y el comando
  `nex-mcp`, pero la comprobación completa de [Empaquetado](#empaquetado) es anterior.
