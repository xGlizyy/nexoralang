# NEXORA Playground

El playground permite escribir, comprobar y ejecutar código NEXORA desde el navegador. El código
se envía al servidor, que lo entrega al **mismo intérprete que usa la orden `nex`**, y la página
muestra lo que el intérprete responde. No hay ninguna ejecución simulada ni una segunda
implementación del lenguaje en JavaScript.

Esta página describe la arquitectura, la API, los límites, el aislamiento real que existe, cómo
ejecutarlo en local y cómo desplegarlo en un servidor propio.

## Estado

| Parte | Estado |
|-------|--------|
| Interfaz del núcleo (`nexora.api`) y proceso worker | Implementado y probado |
| API del servidor (`/api/playground`) | Implementada y probada |
| Página (`web/playground.html`) | Implementada. Lógica probada de forma automática; el dibujado, comprobado a mano en Chrome |
| Límites de tiempo, tamaño, salida, concurrencia y peticiones | Implementados y probados |
| Límites de memoria y CPU del sistema operativo | Implementados para Linux y macOS. Probados en Linux (Ubuntu 24.04 sobre WSL 2) con `tests/test_worker.py`, que lanza el worker como proceso, sin contenedor; en macOS, no. En Windows no existen |
| Aislamiento en contenedor (Docker) | Configuración preparada. **No probada**: no había Docker en el equipo de desarrollo |
| Despliegue en un servidor público | **No realizado** |

**Conclusión práctica:** el playground está listo para usarse en local y en un entorno de confianza.
Antes de abrirlo en Internet hay que construir la imagen del worker, activar el modo contenedor y
completar la lista de [comprobación del aislamiento](#comprobar-el-aislamiento). Hasta entonces, en
un servidor público debe permanecer desactivado (`PLAYGROUND_ENABLED=false`).

## Arquitectura

```text
  Navegador                          Servidor web (Node, Express)               Worker (Python)
  ---------                          ----------------------------               ---------------
  web/playground.html
  web/js/playground/
    view.js        editor y paneles
    controller.js  estado            POST /api/playground/run
    client.js  ───────────────────►  servidor/src/playground/
                                       router.js   valida la petición,
                                                   límites, origen, cupo
                                       limiter.js  concurrencia y cola
                                       worker.js   lanza un proceso  ─────────►  python -I -m nexora.worker
                                                   por petición,                   nexora/worker.py
                                                   lo mata si tarda                  límites del sistema operativo
                                                                                   nexora/api.py
                                                                                     check_source / run_source
                                                                                   pipeline.analyze   (lexer, parser, checker)
                                                                                   interpreter.run
                   ◄───────────────────  respuesta JSON  ◄──────────────────────  resultado JSON
```

Puntos clave:

- **Un solo núcleo.** `nexora.api` llama a `pipeline.analyze` y a `interpreter.run`, las mismas
  funciones que usa `nex`. Una prueba ejecuta cada ejemplo por la línea de comandos y por la API y
  compara salida y diagnósticos.
- **El código del visitante nunca se ejecuta dentro del servidor web.** Cada petición arranca un
  proceso nuevo, que atiende esa petición y termina. Si tarda demasiado, el servidor lo mata.
- **El servidor solo hace transporte.** No conoce la gramática ni decide si un programa es válido.
- **El navegador solo presenta.** El resaltado de sintaxis es coloreado, no análisis; las listas de
  palabras clave se piden al propio núcleo.

### Editor

El editor es deliberadamente sencillo: un `<textarea>` sobre una copia resaltada del mismo texto,
con una columna de números de línea. No se usa CodeMirror ni ninguna otra biblioteca, porque la web
no tiene paso de compilación ni dependencias de JavaScript, y se quiso mantener así.

Lo que ofrece: edición, selección y deshacer normales del navegador, resaltado de la sintaxis real,
sangría automática, marca de las líneas con error y salto a la posición de un diagnóstico.

Lo que **no** ofrece: autocompletado, emparejado de llaves, varios cursores, plegado de código ni
búsqueda propia.

## API

Todas las rutas están bajo `/api/playground`. Las respuestas son siempre JSON.

| Ruta | Método | Función |
|------|--------|---------|
| `/check` | `POST` | Analiza el programa **sin ejecutarlo** |
| `/run` | `POST` | Analiza el programa y, si no tiene errores, lo ejecuta |
| `/status` | `GET` | Si el playground está activado (`{"enabled": true}` o `false`). Responde siempre, también desactivado, y no arranca el worker |
| `/info` | `GET` | Versión del lenguaje, palabras del lenguaje y límites del servicio |
| `/examples` | `GET` | Los programas de ejemplo |

La página pregunta primero `/status`. Con el playground desactivado no pide `/info` ni `/examples`:
muestra «Disabled» y deja Run y Check desactivados.

### Petición

`Content-Type: application/json`.

```json
{
  "code": "fn main() -> Void {\n    print(\"Hello from NEXORA\")\n}",
  "filename": "playground.nex"
}
```

| Campo | Obligatorio | Regla |
|-------|-------------|-------|
| `code` | Sí | Texto. Como máximo 64 KiB en UTF-8 |
| `filename` | No | Nombre **virtual**: solo aparece en los diagnósticos. Letras, dígitos, `_` y `-`, terminado en `.nex`, hasta 64 caracteres. Nunca se usa como ruta ni se abre ningún archivo |

### Respuesta de un programa (HTTP 200)

Esquema `nexora.result/1`. Se devuelve siempre que el intérprete haya podido dar una respuesta,
tenga o no errores el programa.

```json
{
  "schema": "nexora.result/1",
  "action": "run",
  "status": "success",
  "output": "Hello from NEXORA\n",
  "diagnostics": [],
  "message": null,
  "duration_ms": 104,
  "version": "0.8.0"
}
```

| Campo | Significado |
|-------|-------------|
| `schema` | Nombre y versión del formato |
| `action` | `"check"` o `"run"` |
| `status` | Ver la tabla siguiente |
| `output` | Lo que escribió el programa. Vacío en `check` y cuando el programa no llegó a iniciarse |
| `diagnostics` | Los diagnósticos del intérprete, con el formato `nexora.diagnostics/1` ([especificación, sección 11.4](language-spec.md#114-formato-json)): categoría, código, mensaje, archivo, línea, columna y sugerencia |
| `message` | Explicación cuando el estado no es un diagnóstico (un límite alcanzado). `null` en los demás casos |
| `duration_ms` | Tiempo medido por el servidor, incluido el arranque del worker |
| `version` | Versión de NEXORA que respondió |

| `status` | Significado | `output` |
|----------|-------------|----------|
| `success` | `check`: sin errores. `run`: el programa terminó | Salida completa |
| `invalid` | Errores léxicos, sintácticos, semánticos o de tipos. **El programa no se inició** | Vacío |
| `runtime_error` | El programa falló al ejecutarse | Lo escrito hasta el fallo |
| `contract_violation` | Una condición `requires` o `ensures` fue falsa | Lo escrito hasta el fallo |
| `timeout` | Superó el tiempo máximo y se detuvo | Vacío: el proceso se mató |
| `output_limit` | Escribió más de lo permitido y se detuvo | Los primeros bytes, hasta el límite |
| `memory_limit` | Necesitó más memoria de la permitida (solo donde el sistema operativo la limita). Si la memoria se agotó mientras el programa se ejecutaba, `diagnostics` contiene el `E3007` | Lo escrito hasta entonces |

Un programa con errores **no** es un error HTTP: la petición se atendió correctamente.

### Respuesta de error (HTTP 4xx y 5xx)

Cuando la petición no es válida o el servicio no puede atenderla:

```json
{
  "schema": "nexora.result/1",
  "status": "error",
  "error": { "code": "code_too_large", "message": "The program is larger than the limit of 65536 bytes." }
}
```

| HTTP | `error.code` | Cuándo |
|------|--------------|--------|
| 400 | `invalid_json` | El cuerpo no es JSON válido |
| 400 | `invalid_request` | El cuerpo no es un objeto JSON |
| 400 | `missing_code` | Falta el campo `code` |
| 400 | `invalid_code_type` | `code` no es un texto |
| 400 | `invalid_filename` | `filename` no es un nombre simple terminado en `.nex` |
| 403 | `origin_not_allowed` | La petición viene de otro sitio web |
| 404 | `not_found` | Ruta o método inexistente |
| 413 | `code_too_large` | El programa supera el tamaño máximo |
| 415 | `unsupported_media_type` | La petición no es `application/json` |
| 429 | `rate_limited` | Demasiadas peticiones desde el mismo cliente |
| 503 | `busy` | Todos los workers están ocupados y la cola está llena. Incluye `Retry-After` |
| 503 | `runtime_unavailable` | El worker no arrancó o no dio una respuesta válida |
| 503 | `playground_disabled` | El playground está desactivado en este servidor |
| 500 | `internal_error` | Fallo inesperado del servicio |

Las respuestas de error nunca contienen trazas, rutas del servidor ni el código enviado.

La página distingue tres situaciones y las presenta de forma distinta: **el programa** tiene un
problema (diagnósticos), **el servicio** rechaza o no puede atender la petición (el mensaje de
`error`), o **no hay conexión** con el servidor ("Unable to reach the NEXORA runtime. Your code is
still available in the editor.").

## Límites

Todos se configuran en `servidor/.env` (ver `servidor/.env.example`). Cambiarlos requiere reiniciar
el servidor.

| Límite | Valor inicial | Variable | Qué ocurre al superarlo |
|--------|---------------|----------|-------------------------|
| Tamaño del programa | 64 KiB | `PLAYGROUND_MAX_CODE_BYTES` | HTTP 413 |
| Tiempo de ejecución | 2 s | `PLAYGROUND_TIMEOUT_MS` | El proceso se mata; estado `timeout` |
| Salida | 64 KiB | `PLAYGROUND_MAX_OUTPUT_BYTES` | El programa se detiene; estado `output_limit` |
| Longitud de un texto | 262 144 caracteres | `PLAYGROUND_MAX_TEXT_CHARS` | Error de ejecución `E3006` |
| Memoria del worker | 512 MiB | `PLAYGROUND_MEMORY_MB` | Estado `memory_limit`. **Solo en Linux y macOS** |
| Programas a la vez | 4 | `PLAYGROUND_MAX_CONCURRENT` | Los siguientes esperan en la cola |
| Peticiones en espera | 8 | `PLAYGROUND_MAX_QUEUE` | HTTP 503 `busy` |
| Peticiones por cliente | 30 por minuto | `PLAYGROUND_RATE_LIMIT`, `PLAYGROUND_RATE_WINDOW_MS` | HTTP 429 |
| Llamadas anidadas | 1000 | (del lenguaje) | Error de ejecución `E3004` |

El tiempo se mide desde que arranca el worker, así que incluye el arranque de Python (del orden de
una décima de segundo) o del contenedor (más lento: mídelo en tu servidor y ajusta el límite).

## Seguridad y aislamiento

El playground acepta código de cualquier visitante. Esto es lo que lo protege, por capas, y lo que
cada capa **no** cubre.

### 1. El lenguaje

Un programa NEXORA solo puede calcular y escribir texto. No existe ninguna construcción para leer
archivos, usar la red, ejecutar otros programas ni acceder a variables de entorno, y el intérprete
no usa `eval` ni `exec`. Está comprobado por `tests/test_security.py`.

*No cubre:* un defecto del intérprete, ni el consumo de tiempo y memoria.

### 2. El proceso worker

- Proceso aparte por petición, con **entorno vacío**: no recibe ninguna variable del servidor
  (ni contraseñas de base de datos ni secretos de OAuth). En Windows el sistema añade por su cuenta
  unas pocas variables básicas del usuario; ninguna procede del servidor.
- Arranca en un directorio temporal vacío, con Python en modo aislado (`-I`).
- El servidor lo mata al superar el tiempo máximo y descarta una respuesta demasiado grande.
- El worker limita la salida y la longitud de los textos.
- En Linux y macOS pide al sistema operativo límites de memoria, de CPU, de creación de archivos y
  de creación de procesos, y un temporizador que termina el proceso aunque el servidor no lo haga.

*No cubre:* **esto no es una sandbox.** El worker se ejecuta con el mismo usuario y los mismos
permisos que el servidor web: si el intérprete tuviera un defecto explotable, ese proceso podría
leer lo que el usuario del servidor puede leer. En Windows, además, no hay límite de memoria.

### 3. El contenedor (necesario para un servicio público)

Con `PLAYGROUND_WORKER_COMMAND`, cada petición se ejecuta en un contenedor Docker de un solo uso:
sin red (`--network none`), con el sistema de archivos de solo lectura, sin capacidades, sin poder
ganar privilegios, como usuario sin privilegios, y con límites de memoria, CPU y número de procesos.
Solo se usa la imagen local `nexora-worker`, que Docker no descarga nunca (`--pull never`).

*No cubre:* un fallo del propio Docker o del núcleo del sistema. Y **no está probado todavía**.

### 4. El servicio

- Solo se aceptan peticiones del propio sitio (cabecera `Origin`); no se envían cabeceras CORS
  salvo para los orígenes de `PLAYGROUND_ALLOWED_ORIGINS`.
- Cupo de peticiones por cliente, tamaño máximo de petición, concurrencia y cola limitadas.
- La salida de un programa se trata siempre como texto: la API la devuelve dentro de un JSON y la
  página la escribe con `textContent`. Además, la página del playground se sirve con una política
  de seguridad de contenido que impide ejecutar scripts que no sean los del sitio.
- **No se guarda nada.** El código no se almacena ni se escribe en los registros del servidor; los
  registros solo anotan el tipo de fallo. El código se conserva en la pestaña del navegador
  (`sessionStorage`) mientras está abierta. No hay analítica.

### Resumen honesto

| Nivel de exposición | ¿Es adecuado el aislamiento actual? |
|---------------------|-------------------------------------|
| En tu equipo, para desarrollar | Sí |
| En una red interna o con usuarios de confianza | Sí, en Linux, con el modo de proceso |
| Público en Internet | **Solo con el modo contenedor, y después de comprobarlo.** El modo de proceso por sí solo no es suficiente |

## Ejecutarlo en local

Requisitos: Node.js 22.23.2 o posterior en la rama 22, o 24.18.1 o posterior en la rama 24; Python
3.11 o superior y, para las cuentas de usuario de la web, MySQL o MariaDB (el playground en sí no usa
la base de datos).

```bash
# 1. El intérprete
cd nexora
python -m venv .venv
.venv/bin/python -m pip install -e .          # Windows: .venv\Scripts\python.exe -m pip install -e .

# 2. El servidor
cd ../servidor
npm install
cp .env.example .env                          # rellena la base de datos y pon PLAYGROUND_ENABLED=true
npm run migrate
npm start
```

El playground solo se activa con `PLAYGROUND_ENABLED=true`. `.env.example` lo deja desactivado
(`PLAYGROUND_ENABLED=false`), y también queda desactivado si la variable no está definida o está
vacía: la API responde 503 (`playground_disabled`) en todas las rutas salvo `/status`. Cualquier
otro valor (`True`, `1`…) impide arrancar el servidor. **Una instalación local que ya tenga su `servidor/.env` y quiera usar el
playground tiene que añadir `PLAYGROUND_ENABLED=true` de forma explícita**: antes bastaba con no
definirla. Escríbela en tu `servidor/.env` y reinicia el servidor. Úsalo solo para pruebas locales
controladas: el servidor escucha en todas las interfaces del equipo, así que, si tu cortafuegos deja
entrar conexiones al puerto 3000, otros equipos de tu red también podrán usarlo.

Abre <http://localhost:3000/playground>.

El servidor busca el intérprete en `nexora/.venv`. Si está en otro lugar, indícalo con
`NEXORA_PYTHON`.

Comprobación rápida de la API, sin navegador:

```bash
curl -s http://localhost:3000/api/playground/info
curl -s -X POST http://localhost:3000/api/playground/run \
  -H "Content-Type: application/json" \
  --data '{"code": "fn main() -> Void {\n    print(6 * 7)\n}"}'
```

La segunda orden tiene que devolver `"status":"success"` y `"output":"42\n"`.

## Pruebas

```bash
cd nexora   && python -m pytest tests/test_api.py tests/test_worker.py
cd servidor && npm test
```

| Archivo | Qué comprueba |
|---------|---------------|
| `nexora/tests/test_api.py` | `check_source` y `run_source`; límites de salida y de texto; que la API y `nex` dan el mismo resultado en todos los ejemplos |
| `nexora/tests/test_worker.py` | El proceso worker: protocolo, peticiones malformadas, modo aislado. Los límites del sistema operativo solo se ejecutan en Linux y macOS |
| `servidor/test/playground-api.test.js` | La API por HTTP contra el intérprete real: validación, códigos HTTP, esquema, límites, tiempo agotado, concurrencia, fallos del worker, entorno del worker, orígenes, y paridad con la línea de comandos |
| `servidor/test/playground-containers.test.js` | El ciclo de vida de los contenedores con un Docker falso (`test/fixtures/fake-docker.js`), sin Docker: nombre único por petición, eliminación y confirmación tras tiempo agotado, respuesta excesiva o error, hueco ocupado hasta confirmar, intentos limitados, ningún intento si la herramienta no arranca, y el [formato de la orden de contenedor](#formato-de-la-orden-de-contenedor): la orden documentada en `.env.example`, esta guía y el `Dockerfile`, opciones ausentes, repetidas, con otro valor o desconocidas, y elementos después de la imagen |
| `servidor/test/playground-config.test.js` | La activación con la configuración real: desactivado sin `PLAYGROUND_ENABLED`, vacía o `false`; activado solo con `true`; error al arrancar con cualquier otro valor; `/status` y 503 en las demás rutas sin arrancar el worker, y un programa real con `true`; en producción, que el playground activado sin la orden de contenedor impide arrancar |
| `servidor/test/playground-frontend.test.js` | La lógica de la página (cliente, estado, resaltado) contra un servidor real y con fallos simulados |
| `servidor/test/web-guide.test.js` | Los ejemplos de la guía web y los enlaces entre páginas |

### Comprobado a mano en el navegador

La parte de la página que dibuja y recibe el teclado (`view.js`) no tiene pruebas automáticas: el
proyecto no incluye un navegador de pruebas. Se comprobó en Chrome, el 14 de octubre de 2026:

| Comprobación | Resultado |
|--------------|-----------|
| Carga inicial: ejemplo, versión, lista de ejemplos, sin errores en la consola | Correcto |
| Escribir con el teclado: sangría automática, resaltado, números de línea | Correcto |
| Run: botón desactivado e indicador mientras se ejecuta; salida real | Correcto |
| Check con errores: pestaña de diagnósticos, contador, línea marcada, salto a la posición | Correcto |
| Atajos Ctrl+Enter y Ctrl+Shift+Enter | Correcto |
| Salida con HTML (`<img onerror=…>`): se muestra como texto, no se interpreta | Correcto |
| Cargar ejemplo con cambios sin guardar: aviso y Deshacer | Correcto |
| Reset con y sin cambios | Correcto |
| Copy | Correcto |
| El código sobrevive a recargar la página | Correcto |
| Sin conexión con el servidor: mensaje propio, el código se conserva | Correcto |
| Ancho de móvil (390 px): paneles apilados, sin desbordamiento, todos los botones visibles | Correcto |
| La página no puede incrustarse en otro sitio (política `frame-ancestors`) | Correcto |

No se probó en Firefox ni en Safari, ni con lectores de pantalla.

## Despliegue en un servidor propio

Estas instrucciones **no se han ejecutado**: no se dispuso de acceso al servidor. Describen un
despliegue en un VPS con Linux, con software gratuito. Adapta rutas y nombres.

### 1. Dependencias

- Node.js 22.23.2 o posterior en la rama 22, o 24.18.1 o posterior en la rama 24 (`engines` en
  `servidor/package.json`). Instala la última versión de la rama.
- Python 3.11 o superior.
- MySQL o MariaDB (para las cuentas de la web).
- nginx como proxy inverso, con un certificado TLS (por ejemplo, de Let's Encrypt).
- Docker, para aislar la ejecución.

### 2. Instalar

```bash
sudo useradd --system --create-home --home-dir /srv/nexora nexora
sudo -u nexora git clone <tu-repositorio> /srv/nexora/app
cd /srv/nexora/app

# Intérprete (para el modo de proceso y para las comprobaciones)
python3 -m venv nexora/.venv
nexora/.venv/bin/python -m pip install ./nexora

# Servidor
cd servidor && npm ci --omit=dev
cp .env.example .env && chmod 600 .env        # rellena la base de datos, PUBLIC_URL, etc.
npm run migrate
```

Los secretos (contraseña de la base de datos, credenciales de OAuth) van solo en `servidor/.env`,
que no se sube al repositorio.

### 3. Imagen del worker

El playground solo ejecuta la imagen local `nexora-worker`. La orden lleva `--pull never`, así que
Docker nunca la descarga de un registro: la construye el operador en el propio servidor, a partir
del código que despliega.

```bash
cd /srv/nexora/app
docker build -f servidor/playground/Dockerfile -t nexora-worker .
docker image inspect nexora-worker --format '{{.Id}} {{.Created}}'   # existe, y cuál es
```

- Constrúyela antes de activar el playground y vuelve a construirla en cada actualización (paso 8):
  contiene su propia copia del intérprete. Cada petición crea un contenedor nuevo, así que la
  siguiente petición ya usa la imagen reconstruida.
- Para fijar una versión, constrúyela también con etiqueta (`-t nexora-worker:0.8.0`) y escribe esa
  etiqueta al final de la orden (`"nexora-worker:0.8.0"`). Para volver a una versión anterior que
  conserves, cambia la etiqueta de la orden y reinicia el servicio. La etiqueta es lo único de la
  orden que se puede cambiar.
- Si la imagen no está en el equipo (no se construyó, o se borró con `docker image rm` o
  `docker image prune -a`), cada ejecución falla sin ejecutar nada. Según el manual de Docker, con
  `--pull never` responde `No such image` y no crea el contenedor, y entonces la API devuelve 503
  `runtime_unavailable`. Ese camino está probado con un Docker falso que rechaza la orden con el
  código 125, no con Docker real.
- `--pull` existe desde Docker 20.10.0 (notas de esa versión). El manual de Docker lo escribe
  `--pull=never`; la orden de Nexora usa dos elementos (`"--pull","never"`), que según el código
  fuente del cliente de Docker es equivalente, porque `--pull` es una opción de texto sin valor por
  defecto implícito. Con una versión anterior a la 20.10, Docker debería rechazar la opción y no
  ejecutar nada. Ninguna de las dos cosas se ha comprobado con la versión instalada.
- No la subas a un registro para usarla aquí: el servidor no la descargaría.
- **La etiqueta es mutable.** `nexora-worker` y `nexora-worker:<etiqueta>` son nombres locales, no
  una huella de su contenido. Quien tenga acceso al demonio Docker de ese equipo puede volver a
  etiquetar otra imagen con ese nombre (`docker tag`, `docker build -t`), y el servidor la ejecutaría
  sin notar el cambio: no comprueba qué imagen hay detrás del nombre. Que se ejecute la imagen de
  Nexora depende, por tanto, de controlar quién accede al equipo y al demonio Docker.

En `servidor/.env`:

```bash
NODE_ENV=production
TRUST_PROXY=loopback
LISTEN_HOST=127.0.0.1
PUBLIC_URL=https://tu-dominio.example
PLAYGROUND_ENABLED=false
PLAYGROUND_WORKER_COMMAND=["docker","run","--rm","-i","--init","--pull","never","--name","{container}","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges","--pids-limit","32","--memory","256m","--memory-swap","256m","--cpus","0.5","--user","65534:65534","--tmpfs","/tmp:rw,size=1m,noexec","nexora-worker"]
PLAYGROUND_TIMEOUT_MS=4000
```

**El playground queda desactivado** hasta completar la
[comprobación del aislamiento](#comprobar-el-aislamiento). Solo el valor exacto `true` lo activa;
`false`, un valor vacío o no definir la variable lo dejan desactivado, y cualquier otro valor
(`True`, `1`…) impide arrancar el servidor. No la definas tampoco en el entorno del servicio
(`Environment=` en systemd o una variable exportada): ese valor tiene prioridad sobre
`servidor/.env`, y un `PLAYGROUND_ENABLED=true` olvidado ahí lo activaría.

Notas:

- El usuario que ejecuta el servidor tiene que poder usar Docker. **Pertenecer al grupo `docker`
  equivale a tener permisos de administrador en esa máquina.** Es el compromiso de este diseño: el
  código del visitante queda encerrado, a cambio de que el servidor web pueda lanzar contenedores.
- **Docker en modo *rootless* no está admitido por ahora.** Para encontrar su demonio, la orden
  `docker` necesitaría `DOCKER_HOST`, o las opciones `-H` o `--context`. Pero la orden admitida no
  permite opciones globales, y el servidor solo pasa `PATH` y `SystemRoot` a las órdenes que lanza,
  así que la orden `docker` usa el demonio por defecto del sistema. Admitirlo exigiría cambiar el
  contrato y el entorno del worker, y es una decisión pendiente.
- Arrancar un contenedor por petición es más lento que arrancar un proceso. Mide cuánto tarda en tu
  servidor y ajusta `PLAYGROUND_TIMEOUT_MS`; con el valor inicial de 2 s puede no bastar.
- Matar la orden `docker run` no detiene el contenedor. Por eso la orden lleva
  `"--name","{container}"`: el servidor pone en el marcador un nombre nuevo en cada petición
  (`nexora-pg-` y un UUID) y, si el contenedor no terminó bien (tiempo agotado, respuesta demasiado
  grande o ilegible, error del cliente), lo elimina con `docker rm -f` y comprueba con `docker ps`
  que ya no existe. El hueco del worker no se libera hasta esa confirmación. Lo intenta hasta seis
  veces, separadas por esperas de 1, 2, 4, 8 y 16 s (31 s de espera en total). Cada intento ejecuta
  dos órdenes, y cada orden se mata si tarda más de 10 s; si todas llegan a ese límite, se añaden
  hasta 120 s más, sin contar lo que tarde en terminar una orden ya matada. Si ningún intento
  confirma, el hueco queda ocupado hasta reiniciar el servidor y el registro anota
  `container not confirmed stopped`.
- **Si el servidor se cae** (un fallo, un `kill`, un corte de la máquina), no hay ninguna limpieza
  automática garantizada de los contenedores que tuviera en marcha: el servidor solo elimina los de
  las peticiones que está atendiendo, y al arrancar no busca los que quedaron. Según el código,
  además, esos contenedores no cuentan para `PLAYGROUND_MAX_CONCURRENT` después de reiniciar el
  servidor. Para ver los que puedan quedar:

  ```bash
  docker ps -a --filter name=nexora-pg- --format '{{.Names}}  {{.Status}}  {{.CreatedAt}}'
  ```

  Ese filtro también lista contenedores de peticiones en curso, si el servidor ya está en marcha.
  Antes de eliminar uno, compruébalo: que el nombre sea `nexora-pg-` seguido de un UUID, que sea de
  la imagen `nexora-worker` y que se creara antes de la caída (`docker inspect -f '{{.Config.Image}}
  {{.Created}} {{.State.Status}}' <nombre>`). Solo entonces elimínalo a mano con `docker rm -f
  <nombre>`. Ni esto ni la caída se han comprobado con Docker real.
- `--init` hace que el proceso 1 del contenedor sea el init de Docker y no Python, que como proceso
  1 ignoraría las señales sin manejador, como la del temporizador del worker. **Sin comprobar con
  Docker real todavía.**
- `TRUST_PROXY=loopback` es necesario detrás de nginx para que el cupo por cliente use la dirección
  real del visitante y no la del proxy. Con `loopback`, `X-Forwarded-For` solo se tiene en cuenta si
  la conexión llega desde el propio equipo: una conexión directa desde otro equipo no puede
  inventarse su dirección. **Pero confía en cualquier proceso del propio equipo** que pueda conectar
  con el servidor, no solo en nginx: no protege por sí solo frente a un proceso local malicioso.
  `TRUST_PROXY=1` también funciona detrás de nginx, pero confía en cualquier conexión, venga de donde
  venga. Los límites cuentan las direcciones IPv6 por bloque /56 y, además, por bloque /48.
- `LISTEN_HOST=127.0.0.1` hace que el servidor escuche solo en el propio equipo: aunque el
  cortafuegos dejara abierto el puerto 3000, no se podría llegar a él desde fuera. Sin ella escucha
  en todas las interfaces, como en desarrollo. Solo admite una dirección IP: `localhost` detiene el
  servidor al arrancar, porque Node puede resolverlo a `::1` (así ocurre en Windows 11 con Node 24) y
  entonces no atendería a un nginx que apunte a `127.0.0.1`. Al arrancar, el servidor escribe en qué dirección
  escucha y avisa si `TRUST_PROXY` y `LISTEN_HOST` no casan. **Sin comprobar en un VPS real.**
- Con `NODE_ENV=production`, el servidor envía HSTS solo en las peticiones que llegan por HTTPS
  (nginx las marca con `X-Forwarded-Proto`, y `TRUST_PROXY` hace que el servidor lo crea).

#### Formato de la orden de contenedor

`PLAYGROUND_WORKER_COMMAND` admite una sola orden de contenedor: la de arriba. El servidor la
comprueba al arrancar y, si no la cumple, no arranca y dice qué falla. Las reglas son:

1. Empieza por `"docker","run"`: `docker` sin ruta y `run` justo después.
2. Después van las opciones de la tabla, **cada una exactamente una vez y con ese valor exacto**,
   en cualquier orden. Una opción con valor va en dos elementos (`"--memory","256m"`).
3. El último elemento es la imagen local: `nexora-worker` o `nexora-worker:<etiqueta>`. La
   etiqueta sigue la gramática de Docker: letras, cifras, `_`, `.` y `-`, sin empezar por `.` ni
   por `-`, y hasta 128 caracteres. No se admite otro nombre, una ruta, un registro ni un digest.
   La etiqueta es lo único que se puede cambiar.

| Opción | Valor |
|--------|-------|
| `--rm` | — |
| `-i` | — |
| `--init` | — |
| `--read-only` | — |
| `--pull` | `never` |
| `--name` | `{container}` |
| `--network` | `none` |
| `--cap-drop` | `ALL` |
| `--security-opt` | `no-new-privileges` |
| `--pids-limit` | `32` |
| `--memory` | `256m` |
| `--memory-swap` | `256m` |
| `--cpus` | `0.5` |
| `--user` | `65534:65534` |
| `--tmpfs` | `/tmp:rw,size=1m,noexec` |

Las opciones van antes de la imagen porque el cliente de Docker deja de leer opciones al llegar a
ella y pasa lo que sigue al programa del contenedor (`SetInterspersed(false)` en su código fuente).
Según eso, un `"--name","{container}"` escrito después de la imagen dejaría al contenedor con un
nombre aleatorio, y el servidor no podría eliminarlo. No se ha observado con Docker real: está en
la [comprobación del aislamiento](#comprobar-el-aislamiento).

**No se admite:**
- otra opción de `docker run`, ni los alias de las de la tabla (`-m`, `-u`, `--net`,
  `--interactive`…);
- la forma `--opción=valor`, tampoco `--pull=never`, aunque sea la que muestra el manual de Docker;
- banderas combinadas (`-it`) ni `--`;
- nada después de la imagen, ni otra imagen;
- una ruta al ejecutable, `docker.exe`, `sudo`, Podman, `docker container run` ni opciones
  globales de Docker.

**Qué es una orden de contenedor se decide solo por nombres.** Si algún elemento contiene
`{container}`, o es un ejecutable llamado `docker` o `podman` (con ruta o `.exe`, en mayúsculas o
minúsculas), la orden se trata como de contenedor y tiene que ser exactamente la de arriba, aunque
el playground esté desactivado. Así, una orden de proceso que cumpla esa condición se rechaza. Las
demás órdenes son el modo de proceso y no se comprueban. Quedan fuera de esa detección un script
envoltorio, otra herramienta (`nerdctl`, `docker.cmd`…) o un ejecutable de Docker con otro nombre.
Ninguno es una forma admitida de ejecutar contenedores: el servidor no validaría su orden ni
eliminaría sus contenedores.

Los valores de la tabla y la imagen son fijos a propósito: cambiar un límite, el aislamiento o la
imagen es una decisión que se toma en el código (`CONTAINER_OPTIONS` y `CONTAINER_IMAGE` en
`servidor/src/playground/config.js`), con sus pruebas, y no una variación de `servidor/.env`.

Las pruebas de esta comprobación (`servidor/test/playground-containers.test.js`) solo analizan la
lista de argumentos y no ejecutan ningún Docker. Las del ciclo de vida del mismo archivo usan un
Docker falso. Ninguna usa Docker real.

Validar la orden tampoco garantiza por sí solo el aislamiento efectivo, que depende también de la
configuración del demonio Docker (`daemon.json`, el runtime por defecto, los espacios de nombres
de usuario) y de la versión instalada. El servidor no comprueba nada de eso.

### 4. Servicio (systemd)

`/etc/systemd/system/nexora.service`:

```ini
[Unit]
Description=NEXORA web
After=network.target mariadb.service docker.service

[Service]
User=nexora
WorkingDirectory=/srv/nexora/app/servidor
ExecStart=/usr/bin/node --env-file=.env src/index.js
Restart=on-failure
# El servidor se apaga solo al recibir SIGTERM: espera hasta 10 s a las peticiones en curso y otros
# 10 s al pool de MySQL (unos 20 s en el peor caso). Este margen debería dejarle terminar antes de que
# systemd lo mate con SIGKILL; no se ha probado con systemd.
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nexora
```

El servidor escucha en el puerto de `PORT` (3000). **No lo expongas directamente a Internet**:
ciérralo en el cortafuegos y deja que solo nginx llegue a él. El worker no escucha en ningún
puerto: solo se comunica con el servidor por su entrada y salida estándar.

Al recibir `SIGTERM` (`systemctl stop` o `restart`), el servidor deja de aceptar conexiones y
`/api/health` pasa a responder 503 a las peticiones que llegan por conexiones que ya estaban abiertas.
Una conexión nueva no recibe ese 503: tras `server.close()` el servidor ya no la acepta, y quien la
abre ve la conexión rechazada. Las pruebas automatizadas lo comprueban en Windows con un servidor local
(`ECONNREFUSED`); detrás de nginx lo normal sería un 502, pero no se ha probado con nginx ni con un
balanceador. Desde ese momento cada respuesta lleva `Connection: close`, para que una conexión
persistente no lo retenga. Espera, como mucho 10 s, a las peticiones en curso y a la tanda de borrado
de sesiones que esté en MySQL (no se envía ninguna más); después cierra el pool de MySQL, otros 10 s
como mucho. Si el borrado no termina a tiempo, el pool se cierra igualmente;
según el código de mysql2 3.24.6, cada conexión se cierra detrás de su consulta en curso, sin
cortarla (sin comprobar todavía contra un MySQL real). Sale con código 0 si todo
terminó a tiempo y con 1 si tuvo que cortar algo; el registro dice qué.

Cada señal se atiende una sola vez (`process.once`). Un segundo `SIGTERM`, o un segundo `SIGINT`,
durante el apagado ya no lo recibe el servidor: Node aplica su comportamiento por defecto y termina el
proceso en el acto, sin esperar a las peticiones en curso ni cerrar el pool de MySQL. Esto se deduce del
código y de la documentación de Node; no se ha probado. Un `SIGINT` después de un `SIGTERM` (o al
revés) no lo interrumpe: devuelve el mismo apagado en curso (las pruebas lo comprueban llamando dos
veces al apagado, sin señales del sistema). Al vencer `TimeoutStopSec`, systemd no envía otro
`SIGTERM`, sino `SIGKILL`, que tampoco permite limpiar nada.

**Probado solo con pruebas automatizadas en Windows**: la señal real, con systemd, sigue sin probar.

### 5. Proxy inverso (nginx)

**Sin probar**: esta configuración no se ha usado con un nginx real. Es un punto de partida que hay
que comprobar en un servidor de pruebas antes de publicar. Los valores de los límites son una
propuesta, no una medición.

```nginx
# En el bloque http (por ejemplo, /etc/nginx/conf.d/nexora-limits.conf): un cupo por cliente para
# la API, además de los límites del propio servidor.
limit_req_zone $binary_remote_addr zone=nexora_api:10m rate=10r/s;

server {
    listen 80;
    listen [::]:80;
    server_name tu-dominio.example;
    return 301 https://tu-dominio.example$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name tu-dominio.example;

    ssl_certificate     /etc/letsencrypt/live/tu-dominio.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.example/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;

    # El cuerpo más grande que acepta el servidor es el del playground (unos 385 KiB).
    client_max_body_size 512k;

    location /api/ {
        limit_req zone=nexora_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

- `http2 on;` es la forma de nginx 1.25.1 y posteriores. Con una versión anterior, quita esa línea y
  escribe `listen 443 ssl http2;` (y lo mismo para `[::]:443`).
- `proxy_set_header Host $host` es necesario: el servidor compara la cabecera `Origin` con `Host`
  para rechazar peticiones de otros sitios.
- `X-Forwarded-Proto` es lo que permite al servidor saber que la petición llegó por HTTPS (con
  `TRUST_PROXY=loopback`) y enviar HSTS. El servidor envía también la CSP y las demás cabeceras de
  seguridad: no hace falta repetirlas en nginx.
- `limit_req` frena a un mismo cliente antes de que llegue al servidor. Los límites del servidor
  siguen actuando detrás (y están en memoria: se pierden al reiniciar).
- Las páginas de error de nginx (502 si el servidor no responde, 413 si el cuerpo es demasiado
  grande, 429 del límite) no dicen nada del servidor. Las del servidor tampoco: un error interno
  responde `{"error":"Internal server error."}` y deja en el registro solo el tipo y un código.
- `/api/health` puede quedarse abierto (no revela nada) o limitarse a la red del monitor con
  `allow` y `deny` en un `location = /api/health` propio.

El certificado puede obtenerse con Let's Encrypt (por ejemplo, `certbot --nginx`), que además lo
renueva. Comprueba después la renovación con `certbot renew --dry-run`.

### 6. Registros

```bash
journalctl -u nexora -f
```

El servidor escribe una línea por cada fallo del playground, con el tipo de fallo
(`playground: worker failed`, `playground: worker unavailable`…). Nunca escribe el código enviado.

### 7. Verificar el despliegue

Primero, que el proceso responde:

```bash
curl -s https://tu-dominio.example/api/health
```

Tiene que responder `{"status":"ok","checks":{"http":"ok"}}`. Solo dice que el proceso está en marcha
y atiende peticiones: **no comprueba MySQL, Google, GitHub, reCAPTCHA ni el playground**. Durante un
apagado responde 503 con `{"status":"shutting_down"}`, pero solo por conexiones que ya estaban abiertas:
las nuevas se rechazan ([Servicio](#4-servicio-systemd)). Comprueba también que `http://` redirige a
`https://` (`curl -sI http://tu-dominio.example/` devuelve 301).

Mientras el playground esté desactivado, comprueba que de verdad lo está:

```bash
curl -s https://tu-dominio.example/api/playground/info
```

Tiene que responder con el estado HTTP 503 y el código `playground_disabled`.

Las comprobaciones siguientes, y las de la sección siguiente que usan la página o la API, necesitan
el playground activado. **Hazlas en un entorno controlado, sin exposición pública**: un servidor de
pruebas al que no se pueda llegar desde Internet, o este mismo servidor antes de abrir el sitio
(con el nombre de dominio sin publicar o el proxy cerrado al exterior). Usa en ese entorno su propia
dirección en lugar de `https://tu-dominio.example`.

```bash
curl -s https://tu-dominio.example/api/playground/info
```

Tiene que responder `"available": true` y la versión. Si responde `"available": false`, el worker no
arranca: revisa `PLAYGROUND_WORKER_COMMAND`, que la imagen exista y que el usuario pueda usar Docker.

```bash
curl -s -X POST https://tu-dominio.example/api/playground/run \
  -H "Content-Type: application/json" \
  --data '{"code": "fn main() -> Void {\n    print(6 * 7)\n}"}'
```

Tiene que devolver `"output":"42\n"`. Después abre `/playground` en el navegador y ejecuta el
ejemplo inicial.

### Comprobar el aislamiento

Antes de anunciar el playground, comprueba **en el servidor real** cada punto. Ninguno se ha
comprobado todavía. Las filas que usan la página o la API necesitan el playground activado: hazlas
en un entorno controlado, sin exposición pública (ver el paso 7). Solo cuando todas den el resultado
esperado, cambia `PLAYGROUND_ENABLED` a `true` en `servidor/.env` del servidor público y reinicia el
servicio.

| Comprobación | Cómo | Resultado esperado |
|--------------|------|--------------------|
| El worker funciona en el contenedor | La orden de `PLAYGROUND_WORKER_COMMAND`, escrita a mano como en el comentario de `servidor/playground/Dockerfile`, con un nombre propio en lugar de `{container}` (por ejemplo `--name nexora-prueba`: el marcador solo lo sustituye el servidor, y Docker no lo acepta como nombre), y con `{"action":"run","code":"fn main() -> Void {\n    print(1)\n}"}` por la entrada estándar | Un JSON con `"output":"1\n"` |
| Sin red | `docker run --rm --pull never --network none --entrypoint python nexora-worker -c "import socket; socket.create_connection(('1.1.1.1', 53), 2)"` | Falla |
| Sistema de archivos de solo lectura | Añade `--read-only --entrypoint python … -c "open('/x','w')"` | Falla |
| Usuario sin privilegios | `… --entrypoint id nexora-worker` | `uid=65534` |
| Límite de tiempo | Ejecuta desde la página un programa lento (por ejemplo `fib(40)`) | Estado `timeout`; con `docker ps` no queda ningún contenedor pasados unos segundos |
| Límite de memoria | Un programa que duplica un texto muchas veces | `E3006` o `memory_limit`; el servidor sigue respondiendo |
| Las pruebas del sistema operativo | `python -m pytest tests/test_worker.py` en el servidor | Las tres pruebas marcadas como POSIX pasan |
| Concurrencia | Varias peticiones lentas a la vez | Las que no caben reciben 503 `busy`; nunca hay más contenedores que `PLAYGROUND_MAX_CONCURRENT` |
| *Pendiente:* el nombre identifica un solo contenedor | Con una petición lenta en marcha, toma su nombre de `docker ps --filter name=nexora-pg-`. Ejecuta `docker ps -aq --filter name=^<nombre>$`, y lo mismo con el nombre sin su último carácter. Repite el primero cuando la petición haya terminado | El primero devuelve un identificador; el del nombre recortado, nada; el primero, repetido al final, nada |
| *Pendiente:* `--init` está activo | Con una petición lenta en marcha, `docker inspect -f '{{.HostConfig.Init}}' <nombre>` y `docker top <nombre>` | `HostConfig.Init` es `true`, y el primer proceso que muestra `docker top` es `docker-init`. `docker top` muestra los procesos desde fuera del contenedor: indica que `docker-init` es el primero, no lo demuestra como proceso 1 dentro del contenedor. La fila «Límite de tiempo» comprueba además que el temporizador interno del worker termina el programa |
| *Pendiente:* lo que va después de la imagen no es una opción de Docker | `docker run --rm --pull never --entrypoint python nexora-worker -c "import sys; print(sys.argv)" --name x` | Imprime `['-c', '--name', 'x']`, y `docker ps -a --filter name=^x$` no lista nada |
| *Pendiente:* un nombre ya en uso | `docker run -d --rm --pull never --name nexora-prueba --entrypoint sleep nexora-worker 30`, dos veces seguidas | La segunda falla por conflicto de nombre y no crea otro contenedor |
| *Pendiente:* sin la imagen no se descarga nada | `docker run --rm --pull never nexora-worker:no-existe` | Falla con `No such image`, sin descargar nada (`docker image ls` no cambia) |

### 8. Actualizar

```bash
cd /srv/nexora/app && sudo -u nexora git pull
nexora/.venv/bin/python -m pip install ./nexora
docker build -f servidor/playground/Dockerfile -t nexora-worker .
cd servidor && npm ci --omit=dev && npm run migrate
sudo systemctl restart nexora
curl -s https://tu-dominio.example/api/playground/info     # activado: la versión nueva; desactivado: 503
```

La imagen del worker hay que reconstruirla en cada actualización del lenguaje: contiene su propia
copia del intérprete. Si la orden usa una etiqueta (`nexora-worker:0.8.0`), construye la imagen con
la etiqueta nueva, cámbiala en `PLAYGROUND_WORKER_COMMAND` y reinicia el servicio; ver
[Imagen del worker](#3-imagen-del-worker).

### 9. Copias de seguridad de MySQL

**Sin probar**: ningún paso de esta sección se ha ejecutado todavía, ni la copia ni la restauración.
Hasta comprobar una restauración completa en un servidor de pruebas, no hay que dar por buena
ninguna copia.

La base de datos guarda cuentas (nombres, emails y resúmenes de contraseñas), sesiones y enlaces con
Google y GitHub: cada copia contiene datos personales. Guárdala cifrada, fuera del servidor, con
acceso restringido, y bórrala cuando pase el plazo que fije la política de privacidad.

Las credenciales van en un archivo de opciones, nunca en la línea de órdenes (se verían en `ps`):

```ini
# /home/nexora-backup/.my.cnf  (chmod 600, propiedad del usuario que hace la copia)
[client]
user=nexora_backup
password=...
```

El usuario de la copia solo necesita leer: `GRANT SELECT, SHOW VIEW, LOCK TABLES ON nexora.* TO
'nexora_backup'@'localhost';`. La copia, coherente sin bloquear las tablas (todas son InnoDB):

```bash
mysqldump --single-transaction --quick --default-character-set=utf8mb4 nexora \
  | gzip > nexora-$(date +%F).sql.gz
```

En MariaDB la orden se llama también `mariadb-dump`. Para restaurar, **primero en una base de datos
distinta** y comprueba que las tablas y el número de filas coinciden:

```bash
mysql -e 'CREATE DATABASE nexora_restore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
gunzip -c nexora-AAAA-MM-DD.sql.gz | mysql nexora_restore
mysql -e 'SELECT COUNT(*) FROM nexora_restore.users; SELECT COUNT(*) FROM nexora_restore.oauth_accounts'
```

Solo después, con el servicio parado (`systemctl stop nexora`), se restaura sobre la base de datos de
producción. Las sesiones de la copia que ya hayan caducado se borran solas al arrancar.

### Sin Docker

Si no puedes usar Docker, el modo de proceso (sin `PLAYGROUND_WORKER_COMMAND`) funciona en tu
equipo, y en Linux aplica los límites del sistema operativo. **No es una sandbox**: ejecuta el código
de los visitantes con los permisos del servidor. Por eso, con `NODE_ENV=production`, el servidor no
arranca con `PLAYGROUND_ENABLED=true` sin la orden de contenedor admitida: dice por qué y termina. Que
la orden de contenedor esté configurada tampoco demuestra que el aislamiento funcione: hay que
completar antes [Comprobar el aislamiento](#comprobar-el-aislamiento).

## Tareas pendientes y riesgos

- Construir y probar la imagen del worker, y completar la tabla de comprobación del aislamiento.
- Probar en un servidor de pruebas la configuración de nginx (redirección a HTTPS, `limit_req`,
  certificado), el apagado con `systemctl stop` y una copia de MySQL restaurada de principio a fin.
- En el modo contenedor, el usuario del servidor web tiene que poder usar Docker, y eso equivale a
  tener permisos de administrador en el equipo: quien comprometiera el servidor web controlaría el
  equipo. Antes de activar el playground en público hay que decidir cómo separarlos (por ejemplo,
  un servicio aparte, con su propio usuario, que sea el único que lanza contenedores).
- Comprobar los límites del sistema operativo dentro del contenedor. En Linux ya pasan con el worker
  lanzado como proceso, sin contenedor ([Pruebas](testing.md#linux)).
- Medir el tiempo de arranque de un contenedor por petición. Si es demasiado, la alternativa es un
  grupo de workers ya arrancados, que no se ha implementado.
- El cupo de peticiones y el freno del inicio de sesión se guardan en la memoria del servidor: se
  pierden al reiniciar y no se comparten entre varias instancias.
- El borrado de sesiones caducadas usa `DELETE … LIMIT`, que es inseguro con la replicación basada en
  sentencias (`binlog_format=STATEMENT`). Con `ROW` (el valor por defecto de MySQL 8) o `MIXED` no hay
  problema. Si el MySQL de producción usa `STATEMENT`, hay que cambiarlo por un borrado por clave
  primaria; está pendiente de conocer ese servidor.
- El tiempo máximo de cada consulta del borrado de sesiones es del cliente (mysql2): la promesa falla
  a los 30 s, pero la sentencia sigue en MySQL y la conexión no vuelve al pool hasta que termina. Una
  sentencia bloqueada retendría una conexión del pool, el mismo que usan el registro y el inicio de
  sesión. Para no acumularlas, una pasada no empieza mientras las consultas de la anterior no hayan
  terminado para mysql2: se omite y se anota en el registro. Una pasada que supera su tiempo máximo
  (5 minutos) deja de enviar tandas nuevas, pero no cancela la que tiene en curso; el registro lo dice,
  y anota cuántas sesiones borró en total esa pasada o con qué error acabó cuando por fin termina. Pero mysql2 da una consulta por terminada
  al vencer su tope aunque siga en MySQL, así que una sentencia que durase más que el intervalo (una
  hora) podría sumar otra conexión en la pasada siguiente. Pendiente de probar con un MySQL de pruebas
  una cancelación real (`KILL QUERY` desde otra conexión, o destruir la conexión al vencer el tiempo).
- El freno del inicio de sesión reserva cada intento antes de consultar la base de datos, así que las
  peticiones simultáneas no lo sortean. Su estado está en memoria: se pierde al reiniciar y no se
  comparte entre varias instancias del servidor.
- El playground no tiene CAPTCHA: sus peticiones solo tienen el cupo por cliente y por red IPv6 /48,
  que no frena un abuso repartido entre muchas direcciones. El registro y el inicio de sesión sí
  tienen un antispam (`servidor/src/captcha.js`): Google reCAPTCHA v3, que solo se carga si la persona
  lo acepta, un campo trampa y un límite estricto por cliente. **Sin probar con claves reales de
  Google**: las pruebas simulan sus respuestas.
- Inicio de sesión con Google o GitHub (`servidor/src/oauth.js`): la cuenta y su enlace con el
  proveedor se crean en una transacción, pero la sesión se crea después, fuera de ella. Si guardar la
  sesión falla, la cuenta queda creada y enlazada sin sesión, y la persona ve `oauth_failed`; según el
  código, el siguiente intento encuentra el enlace y crea la sesión. Las pruebas cubren esos dos
  caminos por separado, con una base de datos simulada, no contra MySQL. **Sin probar**: dos primeros
  inicios simultáneos con la misma identidad pueden chocar (por la clave primaria del enlace o por un
  bloqueo mutuo de MySQL), y uno de ellos recibiría `oauth_failed`. El registro con contraseña, en
  cambio, crea la cuenta y su primera sesión en una sola transacción.
- Apagado (`servidor/src/lifecycle.js`): un segundo `SIGTERM` o `SIGINT` termina el proceso en el acto,
  sin completar la limpieza (sin probar); y el 503 de `/api/health` solo llega por conexiones ya
  abiertas, porque las nuevas se rechazan una vez iniciado `server.close()`. Ver
  [Servicio](#4-servicio-systemd). Sin probar con señales reales del sistema operativo, systemd ni
  nginx.
- Decisión pendiente: el registro responde 409 a un email que ya tiene cuenta, y eso revela qué
  emails están registrados. Evitarlo exige confirmar el email por correo, que el sitio no envía.
- Decisión pendiente de producto y privacidad: el gestor de consentimiento (`web/js/consent.js`) sabe
  cargar Google Analytics, Tag Manager y Ads tras el consentimiento, pero ninguno está configurado y la
  política de seguridad de las páginas (CSP, `servidor/src/security-headers.js`) solo admite scripts y
  conexiones del propio sitio: el navegador los bloquearía aun con consentimiento. Las pruebas del
  servidor fallan mientras haya uno configurado. Si se decide usar alguno, la propuesta es que el
  servidor añada a la CSP solo los dominios del servicio configurado, tal como los documente Google en
  ese momento, y solo en scripts externos: los scripts escritos dentro de la página seguirían
  prohibidos. Antes habría que actualizar la política de cookies y la de privacidad.
- Las páginas legales (`web/aviso-legal.html`, `privacidad.html`, `cookies.html` y `terminos.html`)
  son un borrador: les faltan los datos del titular y otros datos, marcados entre corchetes (como
  `[NIF O CIF]` o `[DOMINIO]`), y no tienen revisión jurídica. No deben publicarse así. Esos
  marcadores solo pueden aparecer en las páginas legales, que avisan arriba de que son un borrador
  (`servidor/test/web-guide.test.js` lo comprueba). El aviso del formulario de registro
  (`web/signup.html`) no nombra al responsable del tratamiento: remite a la política de privacidad,
  donde está pendiente. La revisión jurídica debe confirmar si esa primera capa de información basta
  o si el formulario tiene que nombrarlo.
- La página no se ha probado en Firefox, en Safari ni con lectores de pantalla.
- No se puede compartir un programa mediante un enlace.
