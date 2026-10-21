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

Realizada el 21 de octubre de 2026, en Windows 11 con Python 3.12.10:

| Comprobación | Resultado |
|--------------|-----------|
| `python -m ruff check src tests` | Sin errores |
| `python -m pytest` | 2285 pruebas superadas, 9 omitidas, 0 fallos |
| Cobertura de líneas y ramas (`--cov`) | 94,59 % |
| Umbral configurado (`fail_under` en `pyproject.toml`) | 90 % |
| Pruebas del servidor web (`node --test "test/*.test.js"`, en `servidor/`) | 821 superadas, 0 fallos |

Las 821 pruebas del servidor son las de esta medición. Antes, la tabla traía 112, las mismas de
`v0.6.0`. Después del tag, el commit
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

Las otras cinco se omiten en esta medición: dos ejemplos que necesitan un *host* (la entrada
estándar y los archivos) no se comparan con la API, y tres pruebas de los enlaces simbólicos se
omiten porque en Windows hacen falta privilegios para crearlos (la de la unión de directorios se
ejecuta solo cuando el sistema la permite).

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
| `75661aa` con la fase 1 de la auditoría de producción, sin commit | **643 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con las correcciones de la revisión de la fase 1 | **658 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con la prueba del arranque real | **659 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con las guardas de las pruebas de integración | **701 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con el registro atómico y las guardas revisadas | **721 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol sin `DROP`, con el comodín escapado y el rollback protegido | **741 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con las correcciones de la auditoría final (preflight, rollbacks registrados) | **766 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con la revisión del preflight (módulos permitidos, proceso de migraciones, playground, Node sin `registerHooks`) | **784 superadas**, 0 fallos, 0 omitidas, en una ejecución | No se ejecutó |
| El mismo árbol con el límite del apagado corregido | **797 superadas**, 0 fallos, 0 omitidas, en una ejecución | No se ejecutó |
| El mismo árbol con la revisión final de la auditoría (pruebas sin esperas fijas, apagado por pasos) | **798 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| El mismo árbol con el bloqueo de las pruebas de integración, los mínimos de Node medidos y `captcha.test.js` sin dependencia de orden | **810 superadas**, 0 fallos, 0 omitidas, en cada una de tres ejecuciones | No se ejecutó |
| `5eae954` con la lista cerrada de ramas de Node en las guardas de integración, sin commit | **811 superadas**, 0 fallos, 0 omitidas, en una ejecución | No se ejecutó |
| `e4ec28f` (web y playground al día con el lenguaje 0.7) con `List` en los tipos de `language_info`, sin commit | **818 superadas**, 0 fallos, 0 omitidas, en una ejecución, el 21 de octubre de 2026 | No se ejecutó |
| `6d61ea9` (registros nominales, la 0.8.0) con la web y el servidor al día con el lenguaje 0.8, sin commit | **821 superadas**, 0 fallos, 0 omitidas, en una ejecución, el 21 de octubre de 2026 | No se ejecutó |

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

Las 68 pruebas nuevas de la fila de 643, todas sin red y sin base de datos real:

- `playground-config.test.js` (11): en producción, el playground activado sin la orden de contenedor
  impide arrancar (sin orden y con una orden de proceso); con la orden de contenedor, desactivado o
  fuera de producción, arranca. Una de ellas lanza `src/index.js` en un proceso aparte, sin
  `servidor/.env`, con el puerto 0 y la base de datos en un puerto cerrado: termina con error antes
  de escuchar y antes de borrar sesiones.
- `passwords.test.js` (7): scrypt real; formato guardado, sal distinta en cada hash, contraseñas
  incorrectas, 10 y 200 caracteres, texto no ASCII, otros parámetros, formatos inválidos y parámetros
  imposibles (un error, no una contraseña incorrecta).
- `oauth.test.js` (32): Google y GitHub simulados. `state` ausente, distinto, repetido o de otra
  longitud; cancelación; proveedor sin configurar; errores HTTP, respuestas que no son JSON o sin los
  campos esperados, tiempo agotado y red caída; emails sin verificar; cuenta con contraseña que no se
  enlaza; fallos de la base de datos dentro y fuera de la transacción; y que en ningún fallo se
  confirma (`commit`) una cuenta ni se abre una sesión, ni el registro recibe el secreto, el token,
  el código o el email. Que una cuenta deshecha con `rollback` no quede guardada de verdad solo se
  puede comprobar con un MySQL real.
- `health.test.js` (6), `lifecycle.test.js` (8) y `safe-log.test.js` (4): `/api/health`, el apagado
  ordenado con servidores HTTP reales en puertos libres, y la descripción de errores en el registro.
  Las señales en sí (`SIGTERM`, `SIGINT`) no se prueban: en Windows, matar un proceso no ejecuta sus
  manejadores. Siguen pendientes en Linux.

Las 15 pruebas de la fila de 658 corrigen lo que encontró la revisión de esa fase. Cada una se
escribió antes que la corrección y falló sin ella:

- `lifecycle.test.js` (4): una conexión keep-alive (con `http.Agent` y con `fetch`) ya no retiene el
  apagado: la respuesta lleva `Connection: close` y sale con 0 en menos de 1,5 s, donde antes agotaba
  un límite de 3 s; el pool se cierra solo después de la tanda de borrado en curso; si el borrado no
  termina a tiempo o falla, el pool se cierra igualmente y sale con 1, sin el mensaje del error.
- `session-cleanup.test.js` (5): `stop()` espera a la tanda en curso, no envía otra aunque quedaran
  sesiones y no programa más pasadas; termina enseguida si no hay ninguna en curso; nunca se rechaza;
  y un error sin código se registra por su tipo, nunca por su mensaje.
- `health.test.js` (3) y `safe-log.test.js` (3 más; la de `describePath` se sustituye por cuatro de
  `describeRoute`): la ruta se registra por su plantilla, también la anidada
  (`/api/auth/:provider/callback`) y escrita con otras mayúsculas; sin ruta que coincida,
  `(no route)`; nunca el camino pedido, la cadena de consulta, un email o un identificador.

En la fila de 659, la prueba que leía `src/index.js` con expresiones regulares se sustituye por dos
que arrancan el servidor real en un proceso aparte (puerto libre, sin `servidor/.env`, base de datos
en un puerto cerrado, playground desactivado) y le envían `SIGTERM` o `SIGINT` a través de
`test/fixtures/signal-bridge.js`, que emite el evento en `process`: ejecuta los mismos manejadores que
una señal, pero no es una señal del sistema. Con `SIGTERM` llega mientras hay un registro en curso:
la respuesta lleva `Connection: close` y el proceso sale con 0. Las dos detectan tres fallos
introducidos a propósito en una copia de `src/index.js`: sin manejador de `SIGTERM`, el apagado
creado tarde y el seguimiento de respuestas empezado después de la primera petición. La señal del
sistema operativo y systemd siguen sin probar.

En la fila de 797, el apagado ya no puede terminar antes de su límite. `within()`
(`servidor/src/lifecycle.js`), que limita cada espera del apagado, ponía su temporizador con
`unref()`: si lo único pendiente no tenía ningún recurso detrás (por ejemplo, un cierre del pool que
no termina nunca), al proceso no le quedaba nada que lo mantuviera vivo y salía con 0 en 1–2 ms, sin
registrar el límite ni llegar a `exit()`. Ahora el temporizador no lleva `unref()`: mantiene vivo el
proceso hasta que la espera termina o vence, y `clearTimeout` lo sigue limpiando en cuanto termina.
Con el flujo actual, el apagado puede tardar hasta unas dos veces el límite (`timeoutMs`, 10 s): las
peticiones en curso y el borrado de sesiones se esperan a la vez, y el pool después. Las 13 pruebas
nuevas de `lifecycle.test.js`:

- 6 con temporizadores simulados: ningún temporizador del límite usa `unref()`; todos se limpian tras
  el cierre, el error y el vencimiento; un cierre tardío no añade nada al registro; y cada orden entre
  el límite y el cierre del pool tiene un resultado fijo (en el mismo turno, en cualquier orden, cuenta
  como vencimiento; si el pool cierra antes de que llegue el límite, como cierre).
- 7 en un proceso propio (`test/fixtures/shutdown-child.js`, con `process.exit` de verdad, un pool
  simulado y un servidor HTTP en un puerto libre de 127.0.0.1): un pool que no cierra, sin nada más
  vivo, espera el límite, lo registra y sale con 1 (antes, con 0 en 1–2 ms); uno que cierra enseguida
  sale con 0 sin esperar; uno más lento que el límite y uno que rechaza salen con 1 y una sola línea;
  sin `process.exit`, el proceso termina en cuanto acaba el apagado, sin ningún temporizador
  pendiente; y, con el mismo plazo que el límite, gana el temporizador que se puso antes (el del
  límite o, si se puso antes de empezar el apagado, el del pool).

Las dos pruebas que ya esperaban un límite vencido (un pool o un borrado de sesiones que no terminan)
lo esperan ahora sin nada más que mantenga vivo el proceso. Antes de la corrección, en Node 20.6.1 y
22.23.3 se cancelaban 19 pruebas de `lifecycle.test.js` y `session-cleanup.test.js`: siete esperaban
un temporizador con `unref()` sin nada más vivo, y las demás caían en cadena tras ellas (el ejecutor de
pruebas de Node 24 no las cancela). Las cinco de `session-cleanup.test.js` esperan ahora con el bucle
de eventos vivo, como en el servidor real; las dos de `lifecycle.test.js` ya no lo necesitan.

`npm test` con esta fila, en Windows 11, una ejecución por versión, el 18 de octubre de 2026 (Node
20.6.1 y 22.23.3 son las distribuciones portátiles oficiales, con su SHA-256 comprobado; 24.21.0 es el
del sistema):

| Node | Pruebas | Superadas | Omitidas | Fallos | Canceladas |
|------|---------|-----------|----------|--------|------------|
| 20.6.1 | 797 | 783 | 14 (las de `preflight.js`, sin `registerHooks`) | 0 | 0 |
| 22.23.3 | 797 | 797 | 0 | 0 | 0 |
| 24.21.0 | 797 | 797 | 0 | 0 | 0 |

Sigue sin demostrarse: el caso con un MySQL real (que el cierre del pool quede pendiente sin ningún
socket abierto), las señales reales del sistema operativo (las pruebas usan
`test/fixtures/signal-bridge.js`) y el `TimeoutStopSec` de systemd, que tiene que superar esas dos
veces el límite.

En la fila de 798, la revisión final de la auditoría:

- `servidor/src/lifecycle.js`: marcar el servidor como en apagado (`onDraining`, que pone
  `/api/health` en 503) y parar el borrado de sesiones (`stopCleanup`) se intentan por separado. Antes
  estaban en el mismo bloque: si fallaba el primero, el segundo no se llegaba a llamar. La prueba nueva
  es la 798.
- `lifecycle.test.js` ya no espera tiempos fijos. Las pruebas que necesitaban una petición en curso
  esperaban 100 ms y daban por hecho que había llegado; ahora esperan a que el servidor la reciba, y la
  respuesta lenta llega cuando la prueba lo decide. La del `SIGTERM` al servidor real enviaba la señal
  mientras scrypt calculaba el resumen (unos 100 ms); ahora envía el cuerpo en dos partes, y la segunda
  solo cuando `test/fixtures/signal-bridge.js` confirma por IPC que ha emitido la señal. Además usa un
  cliente keep-alive: con `agent: false` el propio cliente pedía `Connection: close`, y comprobar esa
  cabecera en la respuesta no demostraba nada.
- `whileAlive()` (`session-cleanup.test.js`) tiene un límite de 5 s. Antes, si una pasada no terminaba
  nunca, la prueba esperaba para siempre: `node:test` no pone límite por defecto.
- `auth-routes.test.js`: la prueba de que un registro fallido no deja la cuenta a medias repetía el
  registro con una base simulada nueva, así que no comprobaba nada; ahora lo repite con la misma.
- La prueba de `stop()` con una tanda en curso anota sus líneas en vez de escribirlas en la salida de
  error.

Cinco fallos introducidos a propósito en copias del árbol (sin `servidor/.env`) los detectan estas
pruebas: los dos pasos del apagado otra vez juntos, sin el manejador de `SIGTERM`, sin
`Connection: close`, el registro confirmando (`COMMIT`) en vez de deshacer, y un plazo de pasada que
no vence nunca (las cinco pruebas con `whileAlive()` fallan a los 5 s, en vez de quedarse esperando).
Sin `Connection: close`, la prueba del `SIGTERM` real solo lo detecta desde que usa el cliente
keep-alive.

`npm test` con esta fila, en Windows 11, el 18 de octubre de 2026 (las mismas distribuciones de Node
que en la fila de 797, con su SHA-256 comprobado de nuevo):

| Node | Ejecuciones | Pruebas | Superadas | Omitidas | Fallos | Canceladas |
|------|-------------|---------|-----------|----------|--------|------------|
| 20.6.1 | 1 | 798 | 784 | 14 (las de `preflight.js`, sin `registerHooks`) | 0 | 0 |
| 22.23.3 | 1 | 798 | 798 | 0 | 0 | 0 |
| 24.21.0 | 3 | 798 | 798 | 0 | 0 | 0 |

Después de cada ejecución no quedó ningún proceso de Node abierto. Con Node 20.6.1, el ejecutor de
pruebas avisa una vez `MaxListenersExceededWarning` en `integration-guard.test.js`: según la traza, lo
produce su propia forma de aplicar el `timeout` de cada prueba (`stopTest`), no el código del servidor.

Con las pruebas de cada archivo en orden aleatorio (`node --test --test-randomize`, Node 24.21.0), en
seis ejecuciones: en cuatro pasan las 798; en dos fallan las mismas dos pruebas de `captcha.test.js`
(confirmadas en `cda0ee9` y `a160829`), porque comparten el límite estricto de una misma IP: la segunda
da por hecho que la primera ya lo agotó. Con el orden normal, `node:test` ejecuta las pruebas de un
archivo en el orden en que están escritas, y `npm test` no fallaba. Se corrigen en la fila de 810.

En la fila de 810:

- **`captcha.test.js` sin dependencia de orden.** Las dos pruebas que gastan el límite estricto usan
  ahora cada una su propia ruta, con el cupo entero (`protectedRoute`), y gastan el cupo ellas mismas:
  una puntuación baja y una caída de Google pasan dos veces y después las dos se frenan. Con la versión
  anterior, las semillas 2774676119 y 4 reproducen el fallo (48 superadas, 2 fallos); con la nueva, esas
  dos semillas y 100 más (1000–1099) pasan las 50 pruebas del archivo.
- **Las pruebas de integración tienen un bloqueo de ejecución** (ver más abajo). 11 pruebas nuevas en
  `integration-guard.test.js`, con conexiones simuladas.
- **El mínimo de Node de las pruebas de integración estaba mal.** `module.registerHooks` existe desde
  Node 22.15, pero en las versiones de abajo, al importar un módulo CommonJS desde ESM, el gancho
  recibió en las mediciones una segunda resolución con la ruta absoluta y sin `parentURL`: el gancho de
  `preflight.js` no puede saber quién lo pide y bloquea `mysql2` también en el orden legítimo. Es una
  observación en Windows: la documentación de Node no describe ese comportamiento ni su cambio, así que
  su causa exacta no está confirmada. Fallaba de forma segura (no deja pasar nada), pero las pruebas de
  integración no podían ejecutarse, y `npm test` fallaba en esas versiones (3 fallos en Node 22.15.0)
  en lugar de omitir esas pruebas. Medido con
  el caso «legit» de `test/fixtures/preflight-probe.js` y las distribuciones oficiales para Windows, con
  su SHA-256 comprobado: lo bloquean 22.15.0, 22.18.0, 22.19.0, 22.20.0, 22.21.0, 22.22.0, 22.22.1,
  22.22.2, 24.0.0, 24.11.1, 24.13.0 y 24.13.1; lo cargan 22.22.3, 22.23.0, 22.23.3, 24.14.0, 24.14.1,
  24.15.0, 24.16.0, 24.21.0, 25.9.0 y 26.12.0. `checkHookSupport` (`guard.js`) exige ahora esas
  versiones y explica por qué; en las demás, `npm test` omite las 14 pruebas que lanzan procesos con
  `preflight.js`, cada una con su motivo. Una prueba nueva fija la tabla de versiones.

`npm test` con esta fila, en Windows 11, el 18 de octubre de 2026, una ejecución por versión salvo
24.21.0 (tres). Las cifras salen de los registros de cada ejecución:

| Node | Pruebas | Superadas | Fallos | Omitidas | Canceladas | Código de salida |
|------|---------|-----------|--------|----------|------------|------------------|
| 20.6.1 | 810 | 796 | 0 | 14 (sin `registerHooks`) | 0 | 0 |
| 22.15.0 | 810 | 796 | 0 | 14 (gancho que no ve quién carga cada módulo) | 0 | 0 |
| 22.22.3 | 810 | 810 | 0 | 0 | 0 | 0 |
| 22.23.3 | 810 | 810 | 0 | 0 | 0 | 0 |
| 24.14.0 | 810 | 810 | 0 | 0 | 0 | 0 |
| 24.21.0 (×3) | 810 | 810 | 0 | 0 | 0 | 0 |

Con orden aleatorio, Node 24.21.0, semillas 2774676119, 1, 2, 3, 4 y 5: las 810 superadas en cada una
de las seis, código de salida 0. Después de cada ejecución no quedó ningún proceso de Node abierto.

**Fallos intermitentes, sin corregir.** En una ejecución anterior de esta misma ronda, con el mismo
código de servidor, fallaron por tiempo agotado pruebas que arrancan el intérprete real de Python o
procesos con un límite de tiempo: 1 en Node 20.6.1 (`playground-api.test.js`) y 4 en Node 22.23.3
(`playground-api`, `playground-containers`, `playground-frontend` y `web-guide`). Son pruebas
confirmadas antes de esta auditoría. No se reprodujeron: esos cuatro archivos pasaron 3 veces seguidas
con cada una de las dos versiones (326 de 326), y en la tabla de arriba. Lo más probable es que fuera
carga momentánea del equipo mientras `node --test` ejecuta varios archivos a la vez, pero no está
demostrado.

En la fila de 811 (`5eae954` con los cambios sin commit), las guardas de las pruebas de integración
admiten solo las ramas de `HOOK_MINIMUMS` (Node 22 desde 22.22.3 y Node 24 desde 24.14.0) y rechazan
cualquier otra rama y las versiones que no son exactamente X.Y.Z. Antes admitían cualquier versión de
las ramas 25 y posteriores, y versiones incompletas como `v24`. El mensaje de rechazo dice el motivo
(versión ilegible, rama sin mínimo medido o versión por debajo del mínimo) y ya no presenta como un
hecho la causa del bloqueo de mysql2. La prueba de esas versiones se reescribe con cada motivo y con el
límite de cada rama, y una prueba nueva comprueba que todo lo que admite `engines` en
`servidor/package.json` está dentro de esa lista. `npm test`, en Windows 11 con Node 24.21.0, una
ejecución, el 18 de octubre de 2026: 813 superadas, 0 fallos, 0 omitidas, código de salida 0, en 26,3 s.
La ejecución anterior, con 811 superadas, fue la de la fila a la que se refiere este párrafo. No se ha
ejecutado con Node 22.23.2 ni con 24.18.1, ni en Linux ni en macOS.

En la fila de 818, las listas de palabras del playground, la guía y la documentación de la web se
ponen al día con el lenguaje 0.7 (listas y `for`): antes de `e4ec28f`, tres pruebas comparaban esas
listas con el intérprete real y fallaban. `language_info()` incluye además `List` en `types`, y una
prueba del coloreado comprueba que `List` se marca como tipo. Código de salida 0, 29 s. No se ha ejecutado
con Node 22.23.2 ni con 24.18.1, ni en Linux ni en macOS.

En la fila de 821, la web y el servidor se ponen al día con el lenguaje 0.8 (registros): el catálogo
de ejemplos del playground ofrece `records.nex`, el coloreado del editor reconoce los tipos que
declara el programa (un registro se marca como tipo, no como función), la hoja de ruta de la
documentación separa lo que ya está de lo que sigue, y la guía describe los registros con un
ejemplo que las pruebas ejecutan con el intérprete real. Código de salida 0, 32 s. No se ha ejecutado
con Node 22.23.2 ni con 24.18.1, ni en Linux ni en macOS.

#### Pruebas de integración con MySQL: ejecutadas una vez

`servidor/test/integration/` contiene pruebas contra una base de datos real (migraciones y esquema,
cuentas y sesiones, borrado de sesiones y cierre del pool con consultas en curso y bloqueos, OAuth
con persistencia y concurrencia, y errores de SQL). Necesitan antes la base `nexora_test`, el esquema
de la marca `nexora_test_guard` y dos cuentas, que se crean con
`servidor/test/integration/setup-admin.sql`. Ese script **sí se ha ejecutado**: el 18 de octubre de
2026 creó la base, el esquema de la marca y las dos cuentas con sus permisos. La cuenta de migraciones
solo tiene `CREATE`, `ALTER`, `INSERT` y `REFERENCES` sobre las tres tablas de la aplicación, **sin
`DROP`** y ningún permiso sobre la base entera: no puede borrar tablas, crear otras ni borrar la base.
La de la aplicación tiene `SELECT`, `INSERT` y `DELETE` sobre `` `nexora\_test`.* ``, con el `_`
escapado: sin escapar, en un permiso sobre una base entera `_` es un comodín y daría acceso también a
`nexoraXtest`. Las dos solo pueden leer la marca. Solo se lanzan con `npm run test:integration`,
nunca con `npm test`, y cargan `servidor/.env.integration` (ignorado por git), nunca `servidor/.env`.

**Resultado medido.** El 18 de octubre de 2026 se ejecutó `npm run test:integration` **una única vez**,
en la rama `feature/server-hardening` (HEAD `74f2a03`, con `test/integration/context.js`, `run.js`,
`guard.js` y `test/integration-guard.test.js` modificados y sin commitear), dentro de un contenedor
auxiliar aislado que comparte el espacio de red de un contenedor `nexora-mysql-test` con MySQL 8.4.11,
publicado solo en `127.0.0.1:3307` del anfitrión: **30 superadas, 0 fallos, 0 omitidas, código de
salida 0**, en 20,36 s. Por suite: migraciones 6/6, cuentas 8/8, sesiones 3/3, cierre del pool con
consultas en curso 2/2, OAuth 6/6 y errores de SQL 5/5.

Las migraciones se ejecutaron y terminaron correctamente. Pasaron las tres comprobaciones que las
cubren: crear el esquema esperado desde una base sin tablas, repetirlas sin cambiar ninguna tabla ni
perder filas, y no reparar un esquema desviado a mano; esta última deshizo su propio `ALTER`. La
ejecución terminó sola y emitió su resumen.

Fue **una sola ejecución**: no se ha repetido, así que el dato no dice nada de que el resultado sea
determinista, ni de que lo sea en otro sistema operativo o con otra versión de Node. Aquí el proceso
era Node 24.21.0 dentro de un contenedor de Linux sobre MySQL 8.4.11, no en el anfitrión de Windows
como la medición de `npm test` de arriba. El límite de tiempo al liberar el bloqueo de ejecución
(10 s en `guard.js`) no llegó a activarse: la ejecución fue rápida y limpia.

**La prueba de esquema nuevo** solo se ejecuta si ninguna de las tres tablas existe, es decir, con la
base recién creada. Si existen, se omite y lo dice; si solo existen algunas, falla, porque la base
quedó a medio migrar. Para repetirla, una persona con permisos de administración ejecuta antes, a
mano y en el servidor de pruebas, `servidor/test/integration/prepare-fresh-schema-admin.sql`, que borra
solo las tres tablas de la aplicación (ni la base, ni la marca, ni las cuentas). El script **no
garantiza por sí solo** estar en el servidor de pruebas: muestra la marca, y comprobarla es tarea de
quien lo ejecuta. Antes de nada hay que revisar el destino (servidor, puerto y cuenta del cliente);
después, usar el cliente de MySQL o MariaDB **sin `--force`**, para que se detenga en el primer error
(si la marca no existe, su consulta falla y los `DROP` no se ejecutan); y mirar el resultado de la
consulta de la marca: tiene que ser exactamente una fila, `nexora-integration-tests-only`. Con
cualquier otra cosa, hay que detenerse. Lo más seguro es ejecutar primero solo esa consulta.

Como la ejecución del 18 de octubre de 2026 creó las tres tablas, esa preparación ya no hace falta
para volver a lanzar la suite en ese mismo servidor de pruebas: mientras las tablas existan, la
prueba de esquema nuevo **se omite y lo dice**. Para volver a ejercitarla hay que ejecutar antes
`prepare-fresh-schema-admin.sql`, como describe el párrafo anterior.

La prueba de esquema desviado deshace su cambio con `ALTER`, sin borrar nada, también si fallan las
migraciones o una comprobación (`undoAfter` en `guard.js`). Si lo que falla es deshacerlo, no tapa el
error original: lo anota aparte y pide `prepare-fresh-schema-admin.sql`.

Antes de cargar ninguna prueba, `servidor/test/integration/preflight.js` (con `--import` en el script, y
además la primera importación de `run.js`) rechaza un entorno inseguro: sin `npm run test:integration`,
con cualquier variable `DB_*`, con el playground activable (`PLAYGROUND_ENABLED` solo puede faltar o
valer exactamente `false`, y no se admite ninguna otra variable `PLAYGROUND_*`) o con una configuración
de pruebas que no sea la autorizada. Además instala un gancho de resolución de módulos de Node: de
`servidor/src/` solo se pueden cargar los módulos de la lista `APP_MODULES` de `guard.js` (los que
importan las pruebas y todo lo que estos importan; `npm test` comprueba que la lista es exactamente
eso), y solo cuando una conexión de la aplicación se ha verificado y `useAppDatabase()` ha preparado el
entorno. `src/index.js` (escucharía en `PORT`, 3000 si no hay otro, y arrancaría el borrado de
sesiones) y `src/migrate.js` (conecta y migra al cargarse) no se cargan nunca en ese proceso. `mysql2`
solo lo puede cargar `guard.js` (con el proceso ya marcado) o esos módulos. Esto vale para cualquier
forma de cargarlos: importación estática, `import()` con texto, variable o plantilla, `require` y
`createRequire`, y otras formas de escribir la misma ruta (`SRC`, `%73rc`). `playground/worker.js`, que
está en la lista porque lo importa `app.js`, crea al cargarse su carpeta de trabajo en el directorio
temporal, como en `npm test`.

**Las pruebas de integración solo admiten Node 22.22.3 o posterior en la rama 22, o 24.14.0 o
posterior en la rama 24** (`module.registerHooks`, y que su gancho vea quién carga cada módulo; ver las
filas de 810 y 811). Son mínimos medidos en Windows, con las distribuciones oficiales: en las versiones
anteriores que se probaron, el gancho bloqueaba mysql2 también en el orden legítimo. La documentación
de Node no describe ese cambio, así que su causa exacta no está confirmada. La lista es cerrada
(`HOOK_MINIMUMS` en `servidor/test/integration/guard.js`): cualquier otra rama (23, 25, 26, 27 o
posterior) se rechaza hasta medirla y añadirla, aunque alguna versión suelta no bloqueara mysql2 en la
medición (25.9.0 y 26.12.0). También se rechazan las versiones que no son exactamente X.Y.Z, como las
que llevan sufijo (`-pre`, `-rc`) o ceros a la izquierda.

La compatibilidad declarada en `servidor/package.json` (`engines`) es más estricta:
`^22.23.2 || ^24.18.1`, las últimas versiones de seguridad de cada rama en octubre de 2026. El código
del servidor no necesita esas versiones (`npm test` pasaba con Node 20.6.1), pero Node 20 no tiene
soporte desde el 30 de abril de 2026 y las versiones anteriores de las ramas 22 y 24 tienen fallos de
seguridad publicados. Dentro de ese rango se han probado en local 22.23.3 y 24.21.0 (Windows 11); los
mínimos exactos, 22.23.2 y 24.18.1, no. La integración continua prueba esos mínimos fijos, la última
versión de las ramas 22 y 24 y, en Linux y sin bloquear, Node 26, que queda fuera de `engines` hasta
validarlo; no se ha ejecutado nunca. Los mínimos de `engines` y los de las guardas son cosas
distintas: `engines` dice dónde se admite el servidor, y las guardas, dónde se pueden ejecutar las
pruebas de integración. Una prueba de `integration-guard.test.js` comprueba que todo lo que admite
`engines` está dentro de lo que admiten las guardas. En cualquier Node que las guardas no admiten
(también en la ejecución experimental de Node 26 de la integración continua):
- `preflight.js` se niega a ejecutar las pruebas de integración y explica por qué;
- `npm test` puede ejecutar todo lo demás; de `integration-guard.test.js` se omiten las 14 pruebas que
  lanzan procesos con `preflight.js`, cada una con su motivo, y el resumen las cuenta como omitidas
  (`skipped 14`), no como superadas.

Con Node 20.6.1 y 22.15.0 reales, en Windows 11, `npm test` omite exactamente esas 14, cada una con su
motivo (ver las filas de 797, 798 y 810). Que `preflight.js` se niegue con `npm run test:integration` no se ha ejecutado en Node
20.6: solo se ha simulado en Node 24, quitando `registerHooks` antes de cargar `preflight.js` (`node
--import ./test/fixtures/without-register-hooks.js --test test/integration-guard.test.js`). La
integración continua tampoco valida nunca las pruebas de
integración: solo ejecuta `npm test`, sin base de datos; que ese paso salga bien no dice nada de ellas.
La alternativa que existe desde Node 20.6, `module.register`, ejecuta sus ganchos de forma asíncrona en
otro hilo y en Node 20 no ve `require`; habría que completarla con una función interna de Node, así que
no se usa.

Las migraciones se ejecutan en un proceso aparte, a través de `servidor/test/integration/migrate-child.js`.
Su entorno es exactamente el de `migratorProcessEnv` (la cuenta de migraciones, `127.0.0.1`,
`nexora_test`, `NODE_ENV=test`, `PATH` y `SystemRoot`; en Windows, además, las variables del sistema que
Node añade a todo proceso hijo, como `TEMP` o `USERPROFILE`): cualquier otra, como `NODE_OPTIONS`, una
`TEST_*` o la cuenta de la aplicación, lo detiene antes de conectar. Con su propia conexión verifica la
cuenta de migraciones (identidad, permisos exactos y marca, solo lecturas) antes de cargar
`src/migrate.js` y otra vez después de migrar; si la primera falla, no migra.

**Dos ejecuciones no cambian `nexora_test` a la vez.** Antes de abrir cualquier otra conexión, la
ejecución toma un bloqueo con nombre, `GET_LOCK('nexora_test.integration_run', 0)`, con una conexión
propia verificada como la de la aplicación, y la conserva hasta el final (`holdRunLock` en `guard.js`).
No espera: si otra ejecución lo tiene, se detiene sin abrir nada más y sin cambiar nada. Antes de
vaciar las tablas y antes de lanzar las migraciones, comprueba en el servidor que el bloqueo sigue
siendo suyo (`IS_USED_LOCK(…) = CONNECTION_ID()`); si se perdió (la conexión se cortó o venció
`wait_timeout`), se detiene. Al terminar, `run.js` lo libera (`RELEASE_LOCK`); si el proceso acaba de
otra forma, también si se cae, lo libera el servidor al cerrarse la conexión, y su socket no mantiene
vivo el proceso. No necesita ningún permiso. **No es una barrera de seguridad**: es un bloqueo de todo
el servidor MySQL o MariaDB que solo ordena estas pruebas entre sí; no aísla nada de producción, y en
un clúster con varios servidores (Galera, réplicas) cada servidor tiene sus propios bloqueos. Probado
solo con conexiones simuladas: que MySQL o MariaDB lo liberen al cortarse la conexión, y el
comportamiento con dos ejecuciones reales, sin comprobar.

**Nada de esto es una barrera absoluta**: protege de errores, no de código escrito para saltárselo.
Quedan estos límites:
- el proceso de migraciones no tiene el gancho (ejecuta `src/migrate.js` a propósito);
- **`src/migrate.js` abre una conexión diferente de la que verifica el proceso de migraciones.** Usa
  la misma configuración (las variables `DB_*` ya comprobadas) y se ejecuta entre las dos
  verificaciones, pero lo que hace esa conexión no se verifica por sí mismo: lo que se verifica es la
  cuenta y su configuración;
- un `Worker`, un proceso hijo propio, `--preserve-symlinks` o un socket abierto a mano no pasan por el
  gancho;
- si `run.js` se lanzara sin `--import`, el entorno se comprueba igualmente antes de evaluar ninguna
  prueba (`preflight.js` es su primera importación), pero el gancho llegaría después de enlazar sus
  importaciones estáticas: una importación estática de `src/` se evaluaría. Sin variables `DB_*`,
  `src/config.js` se detendría al cargarse. Las comprobaciones de texto de `npm test` lo avisan antes,
  pero no lo garantizan.

Lo que sí se ejecuta con `npm test` son las 127 pruebas de `integration-guard.test.js`: las guardas
que esas pruebas tienen que superar antes de hacer nada. Rechazan variables `DB_*` en el entorno,
`NODE_ENV` distinto de `test`, otro host, otra base, otro usuario, una contraseña de plantilla, otra
identidad efectiva (`CURRENT_USER()`), cualquier permiso de más o de menos (también globales, sobre
otra base, la base sin el `_` escapado o con nombres parecidos como `nexoraXtest`, `DROP` o
cualquier permiso sobre la base entera para la cuenta de migraciones, escritura en la marca, roles,
`PROXY` o `GRANT OPTION`, en el formato de MySQL 8 y en el de MariaDB) y la falta de la marca; la única
operación destructiva (vaciar las tres tablas) solo acepta conexiones verificadas; ninguna función
abre una conexión si el proceso no lo lanzó `run.js` con `npm run test:integration` y una lista de
archivos idéntica a la de la carpeta; ningún archivo de la carpeta llega a `src/` ni a `mysql2` por
importaciones estáticas, ni directa ni indirectamente; y `src/` solo se importa con `import()`, dentro
de funciones y después de llamar a una guarda. Las pruebas de `preflight.js` lanzan procesos aparte
con `--import` (con conexiones falsas y el puerto 1, nunca un servidor de bases de datos): un entorno
inseguro se detiene antes de cargar nada; once formas de cargar `src/` o `mysql2` antes de tiempo
(importación estática, `import()` con texto, variable o plantilla, `await` a nivel superior, `require`,
`createRequire`, `%73rc`, `SRC` en Windows, con el proceso solo marcado y `mysql2` desde una prueba) se
paran; y el orden legítimo (conexión verificada, `useAppDatabase()`, `src/db.js` y `mysql2` a través de
él) sigue funcionando. `src/index.js` y `src/migrate.js` se rechazan antes y después de ese momento, con
`import()` y con `require`, y la prueba de que no se evaluaron es que no hay ningún manejador de
`SIGTERM` (`index.js` lo registra al cargarse) ni rastro de que escuchara o migrara; esas pruebas dan
`PORT=0` y `LISTEN_HOST=127.0.0.1`, para que un fallo nunca tocara el puerto 3000. `PLAYGROUND_ENABLED`
se acepta sin definir o con `false`, y se rechaza con `true` o cualquier otro valor, igual que
cualquier otra `PLAYGROUND_*`. Del proceso de migraciones se prueba, con conexiones falsas, la
verificación antes y después (y que sin la primera no migra, que un cambio de permisos durante la
migración se detecta después y que la conexión se cierra siempre); y, con procesos reales que se
detienen antes de conectar, que el entorno exacto se acepta y uno distinto se rechaza. Esa prueba con
un proceso real encontró que en Windows Node añade variables del sistema a todo proceso hijo: sin
admitirlas, el proceso de migraciones se habría negado a arrancar en Windows. Las comprobaciones de texto (`require`, `createRequire`, `process.env[…]`,
variables `DB_*`, `import()` sin un texto fijo, `await` a nivel superior también tras `export`) se
aplican a todos los archivos de la carpeta, no solo a las pruebas; son heurísticas sobre el formato
habitual del código, un aviso temprano, no un análisis sintáctico. Los fallos introducidos a propósito
en copias de `guard.js`, `preflight.js`, `run.js`, `package.json`, `setup-admin.sql` y los archivos de
integración los detectan. Que MySQL o MariaDB se comporten así de verdad (el comodín, los permisos de
tabla, el formato de `SHOW GRANTS`) sigue sin comprobar: no se ha conectado a ningún servidor.

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
| `test_text_operations.py` | 184 | Las funciones de un tipo (`Text.length`, `Int.parse`…) y el orden entre textos: cada caso de la decisión, sus requisitos y sugerencias, textos enormes, redondeo y límites de `Float`, la sintaxis del punto y sus errores, que los programas de la 0.5.1 no cambian, y `inspect`, `symbols`, `context` y las capacidades ([decisión 0011](decisions/0011-operaciones-sobre-textos.md)) |
| `test_loops.py` | 96 | `var`, asignaciones, bucles con su medida y sus invariantes: análisis, cada diagnóstico con su vuelta y sus valores, que ningún bucle se queda colgado (tampoco en `nex test`), y lo que muestran `inspect`, `symbols` y `context` ([decisión 0010](decisions/0010-var-y-while.md)) |
| `test_interpreter.py` | 47 | Salida de los programas, aritmética entera y decimal, desbordamiento, división por cero |
| `test_out_of_memory.py` | 20 | Un programa que se queda sin memoria mientras corre: el `E3007`. El `MemoryError` se provoca a propósito, así que ninguna prueba agota la memoria real ([decisión 0009](decisions/0009-memoria-agotada.md)) |
| `test_diagnostics.py` | 16 | Formato de texto, formato JSON, y que el registro de códigos coincide con la especificación |
| `test_inspect.py` | 9 | El esquema JSON de `nex inspect`: nodos, campos, tipos y posiciones |
| `test_cli.py` | 74 | Comandos, opciones, códigos de salida y formatos; también con el comando real en un proceso aparte, desde otros directorios |
| `test_examples.py` | 80 | Cada programa de `examples/`: salida, diagnósticos y código de salida, comparados con los registrados |
| `test_nex_test.py` | 46 | La evaluación de ejemplos: el motor, `nexora.api.test_source` y el comando `nex test`, con los casos de la matriz de la decisión ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| `test_docs.py` | 178 | Cada programa de la documentación y su salida; enlaces; versión; que la referencia de la CLI y la lista de códigos están completas |
| `test_security.py` | 76 | Que el intérprete no evalúa código Python, qué puede hacer un programa, qué módulos puede importar cada archivo, que las herramientas de análisis no ejecutan |
| `test_records_syntax.py` | 25 | La gramática de los registros: declaración, construcción, acceso, cadenas y la asignación a un campo ([decisión 0014](decisions/0014-registros-nominales-inmutables.md)) |
| `test_records_types.py` | 27 | Los tipos de los registros, su identidad nominal, las referencias adelantadas y los ciclos |
| `test_records_values.py` | 24 | Qué hace un registro al ejecutarse: construcción, lectura, igualdad por valor e inmutabilidad |
| `test_records_diagnostics.py` | 18 | Los tres códigos de los registros: título, categoría, mensaje, posición y orden |
| `test_records_tools.py` | 11 | Los nodos nuevos del árbol y el campo `records` del contexto |
| `test_input_arguments.py` | 11 | Los argumentos con los que se ejecutó un programa: vacíos, múltiples, con espacios y con Unicode ([decisión 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)) |
| `test_input_stdin.py` | 14 | La entrada estándar: varias líneas, línea vacía y el final de la entrada (`E3009`) |
| `test_permissions_files.py` | 23 | Los archivos y los permisos: las tres reglas del modelo, el confineamiento de las rutas y los errores del sistema de archivos |
| `test_permissions_static.py` | 12 | Lo que el análisis estático detecta de las declaraciones que faltan (`E2026`) |
| `test_permissions_environments.py` | 8 | Que el worker del playground y el servidor MCP rechazan siempre el acceso a archivos |
| `test_robustness.py` | 86 | Entradas truncadas, mutadas, aleatorias, binarias, enormes o muy anidadas; regresiones de defectos reales |
| `test_api.py` | 42 | Comprobar y ejecutar código en memoria (`nexora.api`), con sus límites de salida y de texto |
| `test_worker.py` | 23 | El proceso de un solo uso del playground: peticiones válidas e inválidas, límites, entorno |
| `test_tooling.py` | 85 | Los JSON Schema y que la salida real los cumple; símbolos, referencias y contexto; el análisis parcial con errores de sintaxis, incluido un programa cortado en cada carácter; que el análisis no ejecuta ni abre archivos; que la CLI y la API devuelven lo mismo |
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
- **El servidor contra servicios reales**: MySQL (las sesiones, las cuentas y OAuth se prueban con
  una base de datos simulada), Google y GitHub, reCAPTCHA, nginx, HTTPS, el apagado con `systemctl
  stop` y las copias de seguridad de MySQL.
- **La web del proyecto** (`web/`): el playground y la guía tienen pruebas en `servidor/test/`
  (lógica del editor, API, enlaces); el aspecto visual y el resto de páginas, no.
- **La instalación del paquete en un entorno limpio** no se ha repetido desde que se añadieron las
  herramientas de análisis. El paquete se genera sin errores e incluye los esquemas y el comando
  `nex-mcp`, pero la comprobación completa de [Empaquetado](#empaquetado) es anterior.
