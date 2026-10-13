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
| Límites de memoria y CPU del sistema operativo | Implementados para Linux y macOS. **No probados**: el desarrollo se hizo en Windows, donde no existen |
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
| `/info` | `GET` | Versión del lenguaje, palabras del lenguaje y límites del servicio |
| `/examples` | `GET` | Los programas de ejemplo |

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
  "version": "0.2.0"
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
| `memory_limit` | Necesitó más memoria de la permitida (solo donde el sistema operativo la limita) | Lo escrito hasta entonces |

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

Requisitos: Node.js 20.6 o superior, Python 3.11 o superior y, para las cuentas de usuario de la
web, MySQL o MariaDB (el playground en sí no usa la base de datos).

```bash
# 1. El intérprete
cd nexora
python -m venv .venv
.venv/bin/python -m pip install -e .          # Windows: .venv\Scripts\python.exe -m pip install -e .

# 2. El servidor
cd ../servidor
npm install
cp .env.example .env                          # y rellena los datos de la base de datos
npm run migrate
npm start
```

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

- Node.js 20.6 o superior.
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

```bash
cd /srv/nexora/app
docker build -f servidor/playground/Dockerfile -t nexora-worker .
```

En `servidor/.env`:

```bash
NODE_ENV=production
TRUST_PROXY=1
PUBLIC_URL=https://tu-dominio.example
PLAYGROUND_ENABLED=true
PLAYGROUND_WORKER_COMMAND=["docker","run","--rm","-i","--network","none","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges","--pids-limit","32","--memory","256m","--memory-swap","256m","--cpus","0.5","--user","65534:65534","--tmpfs","/tmp:rw,size=1m,noexec","nexora-worker"]
PLAYGROUND_TIMEOUT_MS=4000
```

Notas:

- El usuario que ejecuta el servidor tiene que poder usar Docker. **Pertenecer al grupo `docker`
  equivale a tener permisos de administrador en esa máquina.** Es el compromiso de este diseño: el
  código del visitante queda encerrado, a cambio de que el servidor web pueda lanzar contenedores.
  Una alternativa más estricta es Docker en modo *rootless*.
- Arrancar un contenedor por petición es más lento que arrancar un proceso. Mide cuánto tarda en tu
  servidor y ajusta `PLAYGROUND_TIMEOUT_MS`; con el valor inicial de 2 s puede no bastar.
- Si el servidor mata la orden `docker run` por tiempo, el contenedor termina por su cuenta poco
  después: el worker lleva un temporizador propio.
- `TRUST_PROXY=1` es necesario detrás de nginx para que el cupo por cliente use la dirección real
  del visitante y no la del proxy.

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

### 5. Proxy inverso (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name tu-dominio.example;
    # ssl_certificate y ssl_certificate_key: los de tu certificado

    client_max_body_size 512k;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

`proxy_set_header Host $host` es necesario: el servidor compara la cabecera `Origin` con `Host`
para rechazar peticiones de otros sitios.

### 6. Registros

```bash
journalctl -u nexora -f
```

El servidor escribe una línea por cada fallo del playground, con el tipo de fallo
(`playground: worker failed`, `playground: worker unavailable`…). Nunca escribe el código enviado.

### 7. Verificar el despliegue

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
comprobado todavía.

| Comprobación | Cómo | Resultado esperado |
|--------------|------|--------------------|
| El worker funciona en el contenedor | La orden de `PLAYGROUND_WORKER_COMMAND`, a mano, con `{"action":"run","code":"fn main() -> Void {\n    print(1)\n}"}` por la entrada estándar | Un JSON con `"output":"1\n"` |
| Sin red | `docker run --rm --network none --entrypoint python nexora-worker -c "import socket; socket.create_connection(('1.1.1.1', 53), 2)"` | Falla |
| Sistema de archivos de solo lectura | Añade `--read-only --entrypoint python … -c "open('/x','w')"` | Falla |
| Usuario sin privilegios | `… --entrypoint id nexora-worker` | `uid=65534` |
| Límite de tiempo | Ejecuta desde la página un programa lento (por ejemplo `fib(40)`) | Estado `timeout`; con `docker ps` no queda ningún contenedor pasados unos segundos |
| Límite de memoria | Un programa que duplica un texto muchas veces | `E3006` o `memory_limit`; el servidor sigue respondiendo |
| Las pruebas del sistema operativo | `python -m pytest tests/test_worker.py` en el servidor | Las tres pruebas marcadas como POSIX pasan |
| Concurrencia | Varias peticiones lentas a la vez | Las que no caben reciben 503 `busy`; nunca hay más contenedores que `PLAYGROUND_MAX_CONCURRENT` |

### 8. Actualizar

```bash
cd /srv/nexora/app && sudo -u nexora git pull
nexora/.venv/bin/python -m pip install ./nexora
docker build -f servidor/playground/Dockerfile -t nexora-worker .
cd servidor && npm ci --omit=dev && npm run migrate
sudo systemctl restart nexora
curl -s https://tu-dominio.example/api/playground/info     # la versión tiene que ser la nueva
```

La imagen del worker hay que reconstruirla en cada actualización del lenguaje: contiene su propia
copia del intérprete.

### Sin Docker

Si no puedes usar Docker, el modo de proceso (sin `PLAYGROUND_WORKER_COMMAND`) funciona, y en Linux
aplica los límites del sistema operativo. Reduce el riesgo ejecutando el servidor con un usuario
dedicado sin acceso a nada más. **No es una sandbox**, y no se recomienda para un servicio abierto a
cualquiera.

## Tareas pendientes y riesgos

- Construir y probar la imagen del worker, y completar la tabla de comprobación del aislamiento.
- Ejecutar en Linux las pruebas de los límites del sistema operativo.
- Medir el tiempo de arranque de un contenedor por petición. Si es demasiado, la alternativa es un
  grupo de workers ya arrancados, que no se ha implementado.
- El cupo de peticiones se guarda en la memoria del servidor: se pierde al reiniciar y no se
  comparte entre varias instancias.
- No hay CAPTCHA ni otra defensa contra un abuso distribuido desde muchas direcciones.
- La página no se ha probado en Firefox, en Safari ni con lectores de pantalla.
- No se puede compartir un programa mediante un enlace.
