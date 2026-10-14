# 0009 — Un programa que agota la memoria al ejecutarse: diagnóstico `E3007`

- **Estado:** aceptada
- **Versión:** 0.4.0
- **Relacionada con:** la [decisión 0008](0008-ejemplos-y-nex-test.md), en lo que dice sobre
  `MemoryError`: la fila `MemoryError` de la sección 3.4, la fila `70` de la sección 4.2 y la
  "Cuestión pendiente" 1. **No modifica la 0008**; las notas que remitan aquí son un cambio
  documental aparte (ver "Tareas documentales aparte").

## Contexto

Cuando un programa agota la memoria mientras se ejecuta, cada interfaz responde de una forma distinta
(comprobado simulando el `MemoryError` dentro del intérprete):

| Interfaz | Hoy | Dónde |
|----------|-----|-------|
| `nex run` | Código `70`: `internal error: NEXORA hit an unexpected problem (MemoryError: ). This is a bug in NEXORA, not in your program.` | El manejador general de `cli.py:409-426` |
| `nex test` | Código `70`, sin informe. Es la excepción heredada que la 0008 dejó escrita | 0008, 3.4; `run_example` lo deja pasar (`interpreter.py:472-484`) |
| `api.run_source` | Estado `memory_limit`, con lo escrito hasta entonces, un `message` y `diagnostics` vacío | `api.py:135-139` |
| `api.test_source` | La excepción llega a quien llama | 0008, sección 7 |

### El contrato que existe, y qué se conserva

- **`70`**: "error interno de NEXORA: un fallo de la herramienta, no del programa"
  (`cli-reference.md:247` y `271-276`, `language-spec.md:1026`, `diagnostics.md:252`), con la memoria
  como única excepción escrita. **Se conserva** para los defectos de NEXORA.
- **`memory_limit`**: estado público de `nexora.result/1` (`api.py:52`, el esquema,
  `playground.md:138`), del que dependen el servidor y el playground. **Se conserva**: estado,
  `message` y salida parcial.
- **`nexora.test/1`**: un ejemplo que no puede terminar queda en `error` con su diagnóstico. **Se
  conserva**; no hace falta ningún estado nuevo.

### Qué falla

1. El mensaje de `nex run` y `nex test` culpa a NEXORA de algo que hizo el programa.
2. `70` deja de significar una sola cosa para quien automatiza.
3. `nex run --format json` no escribe ningún documento.
4. `nex test` pierde el informe entero por un ejemplo, mientras que el caso equivalente de la pila
   (`E3004`) deja ese ejemplo en `error` y sigue.
5. La rama `api.py:135-136` no se ejecuta en las pruebas en Windows.

## Decisión

### 1. Alcance: solo la ejecución del programa

`E3007` se produce **solo** cuando el `MemoryError` aparece mientras el intérprete ejecuta el
programa, es decir, dentro de `Interpreter._guarded` (`interpreter.py:115-135`): durante
`Interpreter.run` (`main` y todo lo que llama) o `Interpreter.evaluate_example` (la expresión de un
ejemplo y todo lo que llama). Eso incluye:

- las sentencias y expresiones del programa, sus llamadas, contratos y comprobaciones `Tipo(x)`;
- las funciones integradas (`print`, `to_text`, `to_float`, `to_int`);
- la función `write` que el anfitrión pasa al intérprete y que `print` llama dentro de `_guarded`: un
  programa que imprime más de lo que cabe en memoria agota la memoria por su propia salida.

**No se convierten en `E3007`**, y su tratamiento no cambia:

| Dónde se agota la memoria | Tratamiento (igual que hoy) |
|---------------------------|-----------------------------|
| Al leer el archivo o al analizar (lexer, parser, comprobador, incluida la comprobación de tipos refinados sobre constantes) | CLI: error interno, `70`. API: la excepción llega a quien llama. Worker: `memory_limit` sin diagnóstico |
| Al construir o serializar el informe, el documento JSON o el diagnóstico, después de la ejecución | CLI: `70`. `run_source`: su `except MemoryError` actual → `memory_limit` sin diagnóstico. `test_source`: la excepción llega a quien llama |
| En el propio proceso del worker, fuera de `run_source` | Sin cambios (`worker.py:118-125`) |
| `nex check`, `nex inspect`, `nex context`, `nex symbols` y la herramienta MCP | No ejecutan programas: no les afecta |

### 2. El diagnóstico

| Campo | Valor |
|-------|-------|
| Código | `E3007` |
| Título | `Out of memory` |
| Categoría | `runtime` |
| Etiqueta | `The program needed more memory than is available.` |
| Sugerencia | `Reduce the size of values created by the program, especially values that grow with each function call.` |
| Posición | Ninguna, como el `E3004` por falta de pila |
| Notas | La cadena de llamadas; en `nex test`, además, la nota del ejemplo (0008, 3.1) |

### 3. La conversión y el estado que se restaura

`_guarded` captura `MemoryError` junto a `RecursionError`, con estos requisitos:

1. **Se convierte fuera del bloque `except`.** El `except MemoryError` solo anota lo ocurrido; el
   `E3007` se lanza después, cuando el `MemoryError` y su traceback ya no están referenciados. Si se
   lanzara dentro, el `E3007` conservaría el `MemoryError` en `__context__` (aunque se use
   `from None`), y con él todos los marcos del programa y sus valores mientras la CLI o la API manejan
   el error. Medido con un modelo de los marcos: dentro del `except`, 4 de 4 valores siguen vivos
   mientras existe el error; fuera, 0 de 4.
2. **Se restaura el límite de recursividad de Python**, el único estado global que toca el
   intérprete. Ya lo hace el `finally` de `_guarded`, y no cambia.
3. **El resto del estado es local del intérprete y se descarta con él**: `_stack` (la cadena de
   llamadas), `_invoked` y `_short_circuited` (las llamadas observadas de un ejemplo) y los entornos
   de variables. El intérprete solo lee el programa analizado (`CheckedProgram`) que comparten los
   ejemplos; no escribe en él.
4. **Nada más sobrevive al ejemplo**: `run_example` devuelve un `ExampleRun` con el diagnóstico (solo
   texto), las llamadas propias observadas y la salida recogida, sin ninguna referencia al intérprete
   ni a la excepción.
5. **Excepción de emergencia: si la propia conversión agota la memoria.** Crear el diagnóstico
   necesita un poco de memoria. Si en ese momento tampoco la hay, ese segundo `MemoryError` sale de
   `_guarded` sin convertir, porque no se puede garantizar que haya memoria para construir ni el
   diagnóstico ni el informe. Recibe el tratamiento de hoy: `70` en la CLI, `memory_limit` sin
   diagnóstico en `run_source` (su `except MemoryError` actual) y la excepción hacia quien llama en
   `test_source`. Es una salida de emergencia ante un fallo dentro de otro fallo, **no un cambio
   general del contrato**: en todo `MemoryError` del programa que deje memoria para convertirlo, el
   comportamiento es el de la sección 4. Nunca se convierte en un estado falso.

**Cuándo se considera segura la continuación con el ejemplo siguiente.**

Esta decisión no da por supuesto que un `MemoryError` deje el proceso intacto. La continuación se
apoya en la arquitectura actual: cada ejemplo usa un intérprete nuevo (0008, 3.3), el único estado
global que toca el intérprete es el límite de recursividad de Python, y el requisito 1 hace que los
valores del programa que falló dejen de estar referenciados.

Solo se considera segura si las pruebas 6 a 9 verifican estas cuatro propiedades:

| Prueba | Propiedad |
|--------|-----------|
| 6 | El `E3007` tiene `__context__` y `__cause__` vacíos: no conserva el `MemoryError` ni su traceback |
| 7 | El intérprete que falló queda libre: una referencia débil a él está vacía después de `gc.collect()` |
| 8 | El límite de recursividad de Python es el mismo antes y después del ejemplo |
| 9 | El ejemplo siguiente se evalúa de forma independiente, sin estado heredado: con su propia salida, sin la cadena de llamadas del anterior y con el programa analizado sin cambios |

**Condición para implementar.** Estas propiedades se han comprobado con un modelo, no con el
intérprete. Las pruebas 6 a 9 son las primeras que se escriben. Si alguna falla o no puede cumplirse
(por ejemplo, si el intérprete que falló no queda libre), la implementación se detiene y se informa
antes de continuar. Sin esas cuatro pruebas en verde, `nex test` y `test_source` no siguen con el
ejemplo siguiente tras un `E3007`.

### 4. El contrato observable, antes y después

Solo cambia lo que está dentro del alcance (sección 1).

| Interfaz | Antes | Después |
|----------|-------|---------|
| `nex run`: código de salida | `70` | **`3`** |
| `nex run`: salida estándar | Lo que el programa imprimió antes del fallo | **Igual** |
| `nex run`: salida de error | `internal error: … This is a bug in NEXORA, not in your program.` | `runtime error[E3007]: Out of memory`, con la cadena de llamadas, y `error: <archivo>: the program stopped because of a runtime error` |
| `nex run --format json` | Sin documento; texto de error interno en la salida de error | Documento `nexora.diagnostics/1` con el `E3007` en la salida de error, como cualquier error de ejecución |
| `nex test`: código de salida | `70` | **`6`** (`failed`) |
| `nex test`: informe | Ninguno | Completo: el ejemplo en `error` y los demás evaluados |
| `nex test --format json` | Sin documento | `nexora.test/1` válido: el ejemplo con `status: "error"`, `diagnostic` = `E3007` con la nota del ejemplo, `values` con la llamada propia en curso como `stopped` y `output` con lo impreso hasta el fallo. `summary.error` lo cuenta |
| `api.run_source`: `status` | `memory_limit` | **`memory_limit`** |
| `api.run_source`: `output` | Lo escrito hasta el fallo | **Igual** |
| `api.run_source`: `message` | `The program needed more memory than this environment allows and was stopped.` | **Igual** |
| `api.run_source`: `diagnostics` | `[]` | `[E3007]` |
| `api.test_source` | Lanza `MemoryError` | Devuelve el documento `nexora.test/1` descrito arriba |
| Worker (`action: run`) | `memory_limit`, `diagnostics` vacío | `memory_limit` con el `E3007` (es la respuesta de `run_source`) |
| Servidor y playground | Reciben `memory_limit` | Igual; pueden ignorar el diagnóstico nuevo |

`run_source` elige el estado por el código: `E3007` → `memory_limit`; el resto de la categoría
`runtime` → `runtime_error`; `contract` → `contract_violation`. Su `except MemoryError` se conserva
para la memoria que se agote fuera del intérprete.

### 5. El cambio en `api.test_source`

- **Durante la evaluación de un ejemplo** (dentro del alcance): deja de lanzar `MemoryError`. El
  ejemplo queda en `error` con `E3007`, se evalúan los siguientes y se devuelve el documento, con
  `status` global `failed`.
- **Fuera de la evaluación** (al analizar o al construir el documento): no cambia; la excepción llega
  a quien llama, como dice la 0008, sección 7.
- **Excepción de emergencia** (sección 3, requisito 5): si la propia conversión agota la memoria, el
  segundo `MemoryError` también llega a quien llama, porque no se puede garantizar la construcción del
  documento. No cambia el contrato general de `test_source`.
- No se añaden `limits` a `test_source` (0008, sección 7).

### 6. El código `70`

Pasa a significar "defecto de NEXORA" sin la excepción heredada: un `MemoryError` dentro del
alcance ya no llega al manejador general. Los `MemoryError` fuera del alcance (sección 1) siguen
llegando a él y dando `70`, como hoy.

## Motivos

- **Es un fallo del programa.** Se comporta como los otros agotamientos de recursos que ya son
  diagnósticos `runtime`: `E3004` (la pila) y `E3006` (un texto más largo que el límite).
- **Coherencia sin romper nada.** La CLI y `nex test` pasan a tratarlo como lo trata la API, y la API
  conserva todo lo que promete: solo gana el diagnóstico que le faltaba.
- **Un solo sitio.** El intérprete, donde ya está el caso de la pila; las interfaces lo reciben por el
  camino que ya usan para los errores de ejecución.
- **`70` vuelve a ser fiable** en el caso que más lo confundía.

## Lo que no garantiza

- **Que el sistema avise.** En Linux, con la sobreasignación de memoria, el sistema puede matar el
  proceso (SIGKILL) sin que Python llegue a dar un `MemoryError`; entonces no hay `E3007` ni mensaje
  alguno. Sin un límite como el `RLIMIT_AS` del worker, NEXORA no puede evitarlo.
- **Distinguir la causa dentro de la ejecución.** Un defecto de NEXORA que agotara la memoria mientras
  ejecuta un programa se informaría como `E3007`: las dos causas son indistinguibles desde dentro. La
  cadena de llamadas ayuda a investigarlo.
- **Que el informe sea pequeño.** Las llamadas propias que devolvieron un valor antes del fallo
  conservan ese valor en `values`, como hoy. Un valor enorme puede hacer enorme el informe, o agotar
  la memoria al construirlo; en ese caso se aplica la sección 1 (fuera del alcance).
- **Un límite de memoria en `nex run`.** No se añade ninguno.

## Fuera del alcance

Esta decisión no cambia estos comportamientos:

- **El defecto del protocolo del worker:** con un `MemoryError` fuera de `run_source`, responde
  `"action": "run"` aunque la petición fuera `check` (`worker.py:121`).
- **La memoria agotada al analizar**, que sigue dando `70` en la CLI.
- **La conversión de `RecursionError`**, que hoy se hace dentro del `except` con `from None`.
- **Un límite de tamaño para los valores de `values`** en el informe de `nex test`.

## Alternativas descartadas

- **Corregir solo el mensaje y seguir con `70`.** Mantiene un código con dos significados, sin JSON y
  sin informe en `nex test`.
- **Un código de salida nuevo, sin diagnóstico.** Más superficie y menos información (sin cadena de
  llamadas ni sugerencia), y no resuelve `nex test`.
- **Que la API haga como la CLI.** Rompe `memory_limit`, un contrato público del playground.
- **Un estado nuevo en `nexora.test/1`.** `error` con su diagnóstico ya lo describe.
- **Convertir cualquier `MemoryError` del proceso en `E3007`.** Atribuiría al programa memoria agotada
  por el análisis o por los informes de NEXORA.

## Compatibilidad

- **Cambio visible:** en un programa que agota la memoria al ejecutarse, el código de salida pasa de
  `70` a `3` (`nex run`) o a `6` (`nex test`), con un texto distinto en la salida de error. Es un
  cambio incompatible y se anuncia como tal en la 0.4.0 ("Cuestiones resueltas", 1).
- **`nexora.diagnostics/1`:** gana un código. Sin cambio de versión (Protocolo JSON).
- **`nexora.result/1`:** `memory_limit` igual; `diagnostics` puede tener un elemento en ese estado.
  Añadido, sin cambio de versión.
- **`nexora.test/1`:** sin cambio de formato.
- **Servidor y playground:** sin cambios necesarios.

## Cambios necesarios si se aprueba

| Archivo | Cambio |
|---------|--------|
| `nexora/src/nexora/diagnostics.py` | `"E3007": ("Out of memory", RUNTIME)` |
| `nexora/src/nexora/interpreter.py` | `_guarded`: `except MemoryError` que solo anota, y `E3007` lanzado fuera del `except` (sección 3); docstring de `run_example` |
| `nexora/src/nexora/api.py` | `run_source`: `E3007` → `memory_limit` con el diagnóstico; se conserva `except MemoryError`. Docstrings de `run_examples` y `test_source` |
| `nexora/src/nexora/cli.py` | Comentario de `EXIT_INTERNAL_ERROR` y epílogo de `--help` |
| `nexora/docs/language-spec.md`, `diagnostics.md`, `cli-reference.md`, `playground.md` | `E3007`; `70` sin la excepción; `memory_limit` con su diagnóstico |
| `nexora/docs/schemas/*` | Regenerar (los enums de categorías no cambian) |

Esta tabla no incluye la decisión 0008, el CHANGELOG ni el número de versión: no forman parte de la
implementación. Tampoco incluye la incorporación de esta decisión al repositorio: la 0009 y su
entrada en `nexora/docs/decisions/README.md` se añadieron juntas, con las notas de la 0008, en un
cambio documental previo y separado de la implementación.

## Tareas documentales aparte

No forman parte de la implementación. Cada una tiene su propia autorización:

| Tarea | Estado | Contenido |
|-------|--------|-----------|
| Notas de remisión en la 0008 | Hechas, en el mismo cambio documental que incorpora la 0009, antes de la implementación | "Este comportamiento cambia con la decisión 0009" en la fila `MemoryError` de la sección 3.4 y en la fila `70` de la 4.2, y "Resuelta en la decisión 0009" en la "Cuestión pendiente" 1, con el enlace a la 0009. Ningún otro texto de la 0008 cambia |
| CHANGELOG | Hecho, en la entrada de la 0.4.0 ("Cuestiones resueltas", 1) | El cambio en "Cambiado" y en "Cambios incompatibles" (`70` → `3` y `70` → `6`) |

## Pruebas de regresión

Todas provocan el `MemoryError` sustituyendo una función interna (como `tests/test_nex_test.py:205-213`),
sin agotar memoria real ni depender de la máquina. Las pruebas 6 a 9 se escriben primero (sección 3,
"Condición para implementar").

**Alcance**

1. Un `MemoryError` durante una llamada del programa da `NexoraRuntimeError` con `E3007`, sin
   posición, con la cadena de llamadas y con la etiqueta y la sugerencia de la sección 2.
2. Un `MemoryError` dentro de `print`, en la función `write` del anfitrión, también da `E3007`.
3. Un `MemoryError` al analizar (sustituyendo `pipeline.analyze`) **no** da `E3007`: `nex run` y
   `nex test` dan `70`, y `test_source` lanza.
4. Un `MemoryError` al construir el informe (sustituyendo `api.test_document`) **no** da `E3007`:
   `nex test` da `70` y no escribe nada en la salida estándar.
5. Si la propia conversión vuelve a dar `MemoryError`, sale de `_guarded` sin convertir:
   `run_source` responde `memory_limit` sin diagnóstico, `nex run` da `70` y `test_source` lanza.

**Estado y continuación**

6. El `E3007` tiene `__context__` y `__cause__` vacíos.
7. Tras `run_example` con `E3007`, el intérprete que falló queda libre: una referencia débil a él está
   vacía después de `gc.collect()`.
8. El límite de recursividad de Python es el mismo antes y después.
9. Con dos ejemplos, el primero con `E3007` y el segundo correcto: el segundo pasa, con su propia
   salida, sin cadena de llamadas heredada, y el programa analizado no ha cambiado.

**Contrato de cada interfaz**

10. `nex run`: código `3`, `runtime error[E3007]`, conserva lo impreso antes y no contiene
    `internal error`.
11. `nex run --format json`: documento `nexora.diagnostics/1` válido con `E3007`.
12. `nex test`: código `6` e informe completo, en texto y en JSON (válido según
    `nexora-test.schema.json`), con el ejemplo en `error`, su nota, `values` y `output`.
13. `api.run_source`: `memory_limit`, el `message` de siempre, la salida parcial y `diagnostics` =
    `[E3007]`. Cubre `api.py:135-136` en todas las plataformas.
14. `api.test_source`: devuelve el documento; no lanza.
15. Worker (solo POSIX): la prueba actual de `RLIMIT_AS` (`test_worker.py:108`) sigue dando
    `memory_limit` y además comprueba el `E3007`.

**Un `MemoryError` del programa frente a un error interno real**

16. Con el mismo punto de inyección que la prueba 1, un `KeyError` sigue siendo un error interno:
    `nex run` y `nex test` dan `70` con el mensaje `This is a bug in NEXORA`, `nex test` no escribe
    ningún informe, y `run_source` y `test_source` lanzan `KeyError`.
17. Las pruebas actuales de errores internos (`test_cli.py`, `test_nex_test.py`) siguen pasando sin
    cambios.

**Documentación**

18. Las pruebas que exigen que cada código registrado esté documentado (`test_docs.py`,
    `test_diagnostics.py`) incluyen `E3007`.

Se sustituyen dos pruebas que hoy fijan el comportamiento que esta decisión cambia:
`test_memory_error_is_not_caught_by_the_engine` y `test_cli_memory_error_keeps_the_inherited_code_70`,
ambas en `test_nex_test.py`.

## Cuestiones resueltas

1. **La versión de publicación: 0.4.0.** `nex test` aparece en la 0.4.0, de modo que ninguna versión
   publicada ha devuelto `70` en ese caso: el cambio `70` → `6` no rompe nada. El único cambio
   incompatible es el de `nex run` (`70` → `3`), que ya se comportaba así en la 0.3.1. Publicarlo en la 0.4.0
   evita fijar en una versión un comportamiento que ya se sabía que iba a cambiar.
