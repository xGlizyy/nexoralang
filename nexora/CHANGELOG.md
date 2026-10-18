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

Cambios posteriores al tag `v0.6.0`, todavía sin versión. Afectan al servidor web (`servidor/`) y
a la web (`web/`), no al intérprete: el lenguaje y el paquete `nexora-lang` no cambian.

### Añadido

- **Antispam en el registro y el inicio de sesión** (`servidor/src/captcha.js`): Google reCAPTCHA v3,
  un campo trampa y un límite estricto por cliente (5 registros o 15 inicios de sesión por hora) para
  toda petición sin un token que Google confirme. reCAPTCHA solo se carga en el navegador si la
  persona lo acepta en el panel de cookies; sin él se puede entrar igual, con ese límite. La clave
  secreta va en `RECAPTCHA_SECRET_KEY` y la del sitio en `web/js/consent-config.js`; al arrancar, el
  servidor avisa si solo está una de las dos.
- **Freno del inicio de sesión por cuenta** (`servidor/src/login-throttle.js`): tras 5 fallos desde
  un cliente, ese cliente espera cada vez más, hasta 15 minutos; tras 20 fallos contra una cuenta
  desde cualquier cliente, cada intento espera, como mucho un minuto. Responde igual para un email
  con cuenta y uno sin ella, y reserva cada intento antes de consultar la base de datos.
- **Límites por cliente con IPv6** (`servidor/src/rate-limits.js`): todos los límites cuentan una
  dirección IPv6 por su bloque /56, y además cada red /48 con cuatro veces el cupo. Las cabeceras
  `RateLimit-*` describen la cuenta que antes se agota, y cada rechazo lleva `Retry-After`.
- **Borrado de las sesiones caducadas** al arrancar y cada hora, por tandas, sin que dos pasadas se
  solapen (`servidor/src/session-cleanup.js`).
- **Cabeceras de seguridad en todas las respuestas** (`servidor/src/security-headers.js`): la
  política de contenido (CSP) sin código en línea que tenían el playground y la guía pasa a todas las
  páginas, más `X-Frame-Options`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`,
  `Referrer-Policy` y, en producción y solo por HTTPS, HSTS. La API tiene una política que no carga
  nada.
- `LISTEN_HOST`: la dirección en la que escucha el servidor. Con nginx en el mismo equipo,
  `LISTEN_HOST=127.0.0.1` y `TRUST_PROXY=loopback`; al arrancar, el servidor avisa si no casan.
- Web: las tipografías se sirven desde el propio sitio (JetBrains Mono, con su licencia OFL) en vez
  de Google Fonts, y todo el sitio usa JetBrains Mono; un gestor de consentimiento de cookies con
  Google Consent Mode v2; las páginas legales, todavía en borrador (ver Limitaciones); y una
  documentación web ampliada: qué es NEXORA, cómo se prueba y los cambios recientes.
- `GET /api/playground/status` dice si el playground está activado (`{"enabled": true}` o `false`).
  Responde también con el playground desactivado y no arranca el worker. La página lo pregunta
  primero: desactivado, no pide `/info` ni `/examples`.
- Las páginas legales llevan `<meta name="robots" content="noindex, nofollow">` mientras sean un
  borrador, y una prueba lo exige. Solo pide a los buscadores que no las indexen: no impide abrirlas
  a quien tenga el enlace.
- `GET /api/health`: dice si el proceso está en marcha y responde peticiones
  (`{"status":"ok","checks":{"http":"ok"}}`), y nada más: no comprueba MySQL, Google, GitHub,
  reCAPTCHA ni el playground, ni revela la versión o la configuración. Durante el apagado responde 503.
- **Apagado ordenado** (`servidor/src/lifecycle.js`): con `SIGTERM` o `SIGINT`, el servidor deja de
  aceptar conexiones y responde con `Connection: close`, para que una conexión persistente no lo
  retenga; espera hasta 10 s a las peticiones en curso y a la tanda de borrado de sesiones que esté
  en MySQL (no envía ninguna más); cierra el pool de MySQL (otros 10 s como mucho) y sale con 0, o
  con 1 si tuvo que cortar algo. Si durante el apagado llega la otra
  señal, no se repite; si llega otra vez la misma, Node termina el proceso en el acto, sin esperar.
  El límite de cada espera mantiene vivo el proceso hasta que vence: si lo único pendiente no tiene
  ningún recurso detrás (un cierre del pool que no termina), el proceso ya no sale con 0 antes de
  tiempo sin registrarlo, sino que espera el límite, lo registra y sale con 1. Probado con pruebas
  automatizadas en Windows (Node 20.6.1, 22.23.3 y 24.21.0), sin señales reales: con systemd, sin
  probar.

### Cambios incompatibles

- **El servidor requiere Node.js 22.23.2 o posterior en la rama 22, o 24.18.1 o posterior en la rama
  24** (`engines` en `servidor/package.json`: `^22.23.2 || ^24.18.1`; antes, 20.6 o posterior). Node 20
  no tiene soporte desde el 30 de abril de 2026, y las mínimas son las últimas versiones de seguridad
  de cada rama en octubre de 2026. Las ramas 23, 25 y 26 quedan fuera. npm solo avisa (`EBADENGINE`)
  con otra versión, no impide instalar. Dentro del rango se han probado en local, en Windows, 22.23.3
  y 24.21.0; los mínimos exactos no. La integración continua del servidor pasa a probar 22.23.2,
  24.18.1, la última de las ramas 22 y 24 y, sin bloquear, Node 26; todavía no se ha ejecutado.
- **Con `NODE_ENV=production`, `PLAYGROUND_ENABLED=true` exige la orden de contenedor** en
  `PLAYGROUND_WORKER_COMMAND`. Sin ella (o con una orden de proceso), el servidor no arranca: el modo
  de proceso ejecuta el código de los visitantes con los permisos del servidor. Fuera de producción,
  el modo de proceso sigue disponible para probar en un equipo propio. Configurar la orden de
  contenedor no demuestra que el aislamiento funcione: sigue sin comprobarse con Docker real.

- **`NODE_ENV` solo admite `development`, `test` o `production`, en minúsculas.** Antes cualquier
  valor distinto de `production` (`Production`, `prod`, vacío) dejaba el servidor en desarrollo, sin
  cookies solo por HTTPS. Ahora esos valores impiden arrancar. Sin definir sigue funcionando como
  desarrollo, y el servidor lo avisa al arrancar.
- **`TRUST_PROXY` solo admite `0`, `loopback` o un entero de 1 a 10 sin ceros a la izquierda.**
  Antes se leía con `Number()`: `true` o `nginx` daban `NaN` sin ningún aviso. Ahora cualquier otro
  valor impide arrancar. Con nginx en el mismo equipo, se recomienda `loopback` en vez de `1`.
- `LISTEN_HOST` solo admite una dirección IP o quedar vacía; un nombre, también `localhost`, impide
  arrancar.
- Con `NODE_ENV=production` y `RECAPTCHA_SECRET_KEY`, falta `RECAPTCHA_HOSTNAMES` impide arrancar.
  `RECAPTCHA_MIN_SCORE` fuera de 0 a 1, o un `RECAPTCHA_HOSTNAMES` que no sea una lista de dominios,
  también.
- **En producción sin `RECAPTCHA_SECRET_KEY`, todos los registros e inicios de sesión pasan por el
  límite estricto** (5 registros o 15 inicios de sesión por cliente y hora). En desarrollo no cambia
  nada.
- La API de cuentas tiene respuestas nuevas: `429` con `code: "login_throttled"` y `Retry-After`
  durante el freno del inicio de sesión; `400` con `captcha_invalid` o `captcha_expired`; y `429`
  con `captcha_required` en el límite estricto. Un campo `website` con contenido se rechaza con `400`.

- **El playground está desactivado salvo que se active de forma explícita.** Antes se activaba
  siempre que `PLAYGROUND_ENABLED` no fuera exactamente `false`: sin definir, vacía o con una errata
  (`False`, `0`), quedaba abierto. Ahora solo `PLAYGROUND_ENABLED=true` lo activa; sin definir,
  vacía o `false`, la API responde 503 (`playground_disabled`) y no arranca ningún worker. Una
  instalación local que quiera usar el playground tiene que añadir `PLAYGROUND_ENABLED=true` a su
  `servidor/.env`.
- Cualquier otro valor de `PLAYGROUND_ENABLED` (`True`, `1`, `yes`…) impide arrancar el servidor,
  con un mensaje que pide `"true"` o `"false"`.
- **La única orden de contenedor que admite `PLAYGROUND_WORKER_COMMAND` es la documentada.** Tiene
  que empezar por `"docker","run"`, llevar exactamente una vez cada opción de aislamiento y de
  límites de `servidor/.env.example` con su valor exacto, entre ellas `"--init"`,
  `"--pull","never"` y `"--name","{container}"`, y terminar en la imagen. Cualquier otra orden de
  contenedor impide arrancar el servidor, aunque el playground esté desactivado, con un mensaje que
  nombra lo que falla. Eso incluye una opción que falte, se repita, tenga otro valor o no esté en la
  lista, como los alias `-m`, `-u`, `--net` o `--interactive`; la forma `--opción=valor`; algo
  después de la imagen; una ruta al ejecutable, `docker.exe`, `sudo`, Podman,
  `docker container run` u opciones globales de Docker. Lo que va después de la imagen no lo aplica
  Docker, sino que lo recibe el programa del contenedor. Con la comprobación anterior, un
  `"--name","{container}"` escrito detrás de la imagen se aceptaba (comprobado con el validador
  anterior) y, según el código, el servidor podía dar por eliminado un contenedor que seguía vivo;
  no se ha observado con Docker real. Para actualizar una configuración existente, copia la orden
  de `servidor/.env.example`. Cambiar un límite exige cambiar el servidor
  (`servidor/src/playground/config.js`), no solo `servidor/.env`.
- **Solo se ejecuta la imagen local `nexora-worker`, y Docker no la descarga nunca.** La imagen
  tiene que ser `nexora-worker` o `nexora-worker:<etiqueta>`: no se admite otro nombre, una ruta, un
  registro ni un digest. `"--pull","never"` hace que, si la imagen no está en el equipo, la
  ejecución falle en vez de descargarla. Hay que construir la imagen en el servidor antes de
  activar el playground y en cada actualización (ver la
  [guía del playground](docs/playground.md#3-imagen-del-worker)). `--pull` necesita Docker 20.10 o
  posterior.
- Las órdenes del modo de proceso siguen sin comprobarse, salvo las que contienen `{container}` o
  un ejecutable llamado `docker` o `podman`: esas se tratan como órdenes de contenedor y se
  rechazan si no son la documentada.

### Corregido

- **Un contenedor que agota el tiempo ya no sigue ejecutándose con su hueco liberado.** Antes, el
  servidor mataba el cliente `docker run`, que no detiene el contenedor, y liberaba el hueco en ese
  momento. Según el código, eso permitía que hubiera más contenedores vivos que
  `PLAYGROUND_MAX_CONCURRENT`; no se ha observado con Docker real, porque el modo contenedor
  todavía no se ha probado. Ahora cada
  contenedor tiene un nombre generado por el servidor; si no termina bien, se elimina por ese
  nombre y el hueco solo se libera cuando se confirma que ya no existe. Los intentos de eliminarlo
  están limitados; si ninguno confirma, el hueco queda ocupado.
- **El botón Run del playground vuelve a verse en móvil.** A 390 px quedaba cortado y a 320 y 360 px
  no se veía; solo quedaba el atajo Ctrl+Enter. Por debajo de 440 px los cuatro botones van ahora en
  dos filas.
- **Con el playground desactivado, la página ya no parece lista para ejecutar.** Antes mostraba
  «Real interpreter» con un punto verde y Run y Check activos, y cada carga recibía dos respuestas
  503. Ahora dice «Disabled», Run y Check están desactivados (también sus atajos), la ayuda y el pie
  no dicen que el código se ejecuta, y no envía ninguna petición de ejecución. Mientras espera la
  respuesta del servidor dice «Connecting…». Si el servidor no confirma si está activado (no
  responde o responde algo que la página no entiende), dice «Status unknown» y tampoco deja ejecutar:
  Run y Check solo se activan cuando el servidor lo confirma. «Real interpreter» en verde solo
  aparece si además el intérprete respondió; si no, «Unavailable». Activado, se comporta como antes.
- El formulario de registro cabe entero, botón incluido, en una pantalla de 1366×768. El inicio de
  sesión ya cabía y no cambia.
- **El registro es atómico.** Antes se creaba la cuenta y después, aparte, su primera sesión: si la
  sesión no se podía guardar, la cuenta quedaba creada, la persona recibía un error y, al volver a
  intentarlo, un 409. Ahora la cuenta y la sesión se guardan en una sola transacción, la cookie solo
  se envía después de confirmarla, y el resumen de la contraseña se calcula antes de abrirla, para no
  ocupar una conexión del pool durante scrypt. Si además falla el `ROLLBACK`, cuenta el error
  original (un email duplicado sigue respondiendo 409) y esa conexión no vuelve al pool, porque podría
  haber quedado con la transacción abierta: se destruye. El fallo del `ROLLBACK` queda en el registro
  con su tipo y su código (`auth: sign-up rollback failed (Error ER_ERROR_DURING_ROLLBACK)`), sin el
  mensaje ni ningún dato de la petición. Probado con una base de datos simulada; contra MySQL real, la
  prueba está preparada y sin ejecutar.
- El inicio de sesión con Google o GitHub sigue la misma regla en su transacción: si falla el
  `ROLLBACK`, cuenta el error original (por ejemplo, `account_exists` sigue siendo `account_exists`), la
  conexión se destruye en vez de volver al pool (una sola vez, nunca devuelta y destruida) y queda una
  línea `oauth: <proveedor>: rollback failed (…)` sin datos. Antes, un `ROLLBACK` fallido sustituía al
  error original y la conexión volvía al pool. Probado con una base de datos simulada.
- **El registro del servidor ya no copia los errores enteros.** Un error interno de la aplicación o
  del inicio de sesión con Google o GitHub escribía el objeto completo, que en un error de MySQL
  incluye la consulta y el mensaje del servidor (con el email, por ejemplo). Ahora solo se escribe el
  tipo y un código conocido (`Error ER_DUP_ENTRY`, `ProviderError token_http_500`), nunca el mensaje,
  la pila, la consulta, el token, el código de autorización ni el secreto. La ruta se escribe por su
  plantilla (`/api/auth/:provider/callback`), nunca por el camino pedido ni su cadena de consulta; sin
  una ruta que coincida, `(no route)`. El borrado de sesiones caducadas sigue la misma regla: antes
  escribía el mensaje del error cuando no tenía código.
- Google: una cuenta solo se crea o se enlaza si `email_verified` es exactamente `true`; antes
  bastaba cualquier valor que JavaScript tome por verdadero. Un perfil sin identificador, o una lista
  de emails de GitHub que no es una lista, son ahora un fallo del proveedor con su propio código.
- Un resumen de contraseña guardado con campos de más (`…$extra`) ya no se acepta como válido: el
  formato tiene que ser exactamente el de `hashPassword`.

### Documentación

- `servidor/.env.example` deja el playground en `false`, y la [guía del playground](docs/playground.md)
  lo mantiene desactivado en un servidor público hasta completar la
  [comprobación del aislamiento](docs/playground.md#comprobar-el-aislamiento). Las comprobaciones
  que necesitan el playground activo se hacen en un entorno controlado, sin exposición pública.
- Linux comprobado ([Pruebas](docs/testing.md#linux)): en Ubuntu 24.04 sobre WSL 2 pasan las
  pruebas automáticas de `nexora/` con Python 3.11, 3.12 y 3.13 (también las cuatro de POSIX, que
  nunca se habían ejecutado) y las de `npm/` y `servidor/`, y los paquetes de pip y npm se instalan
  y funcionan. No hizo falta cambiar código. Docker y el aislamiento del playground siguen sin
  comprobar.
- Despliegue ([guía del playground](docs/playground.md#despliegue-en-un-servidor-propio)): nginx con
  redirección de HTTP a HTTPS, `limit_req`, `server_tokens off` y la sintaxis `http2 on` de las
  versiones actuales; `TimeoutStopSec` en systemd; la ruta de salud; y copias de seguridad y
  restauración de MySQL. **Nada de ello se ha probado** con nginx, systemd ni MySQL reales: la guía
  lo dice en cada apartado.

### Limitaciones

- El aislamiento en contenedor sigue **sin comprobar**: este cambio evita activar el playground por
  error, pero no lo hace más seguro una vez activado.
- Nada de esto se ha probado con Docker real. Las pruebas de la orden solo analizan la lista de
  argumentos, sin ejecutar ningún Docker; las del ciclo de vida (eliminación de contenedores, hueco
  ocupado, imagen ausente) usan un Docker falso. Si el servidor se cae, nadie elimina los
  contenedores que tuviera en marcha.
- Qué es una orden de contenedor se decide solo por los nombres documentados. Un script
  envoltorio, otra herramienta (`nerdctl`…) o un ejecutable de Docker con otro nombre quedan fuera
  de la detección: no son una forma admitida de ejecutar contenedores, y el servidor no validaría
  su orden ni eliminaría sus contenedores.
- Validar la orden no garantiza la configuración efectiva del demonio Docker ni de sus runtimes.
- La etiqueta local (`nexora-worker` o `nexora-worker:<etiqueta>`) es mutable: quien tenga acceso
  al demonio Docker puede volver a etiquetar otra imagen con ese nombre, y el servidor la
  ejecutaría sin notarlo. Que se ejecute la imagen de Nexora depende del control de acceso al
  equipo y al demonio Docker.
- Docker en modo *rootless* no está admitido: la orden no permite `-H` ni `--context`, y el
  servidor solo pasa `PATH` y `SystemRoot` a las órdenes que lanza.
- El antispam, el freno del inicio de sesión, el borrado de sesiones y las cabeceras se han probado
  con la base de datos, Google reCAPTCHA y el navegador simulados: no contra un MySQL real, con claves
  reales de reCAPTCHA, en un navegador ni detrás de nginx. Las pruebas automatizadas del servidor,
  con esos mismos servicios simulados, dan 810 superadas y 0 fallos con Node 24.21.0 (en cada una de
  tres ejecuciones), 24.14.0, 22.23.3 y 22.22.3, y 796 superadas, 14 omitidas (las que necesitan Node
  22.22.3 o posterior en la rama 22, o 24.14.0 o posterior) y 0 fallos con Node 20.6.1 y 22.15.0 (una
  ejecución con cada una de esas versiones), en Windows 11; en Ubuntu 24.04 en WSL 2 se ejecutaron antes de las últimas correcciones de la web
  (567 superadas, 0 fallos, en cada una de tres ejecuciones) ([Pruebas](docs/testing.md)).
- Los contadores de los límites y del freno del inicio de sesión están en memoria: se pierden al
  reiniciar y no se comparten entre varias instancias del servidor.
- En el inicio de sesión con Google o GitHub, la sesión se crea fuera de la transacción de la cuenta y
  su enlace: si falla, la cuenta queda enlazada sin sesión hasta el siguiente intento. Durante el
  apagado, un segundo `SIGTERM` o `SIGINT` termina el proceso sin completar la limpieza, y el 503 de
  `/api/health` solo llega por conexiones ya abiertas. Las pruebas automatizadas, en Windows y con la
  base de datos simulada, cubren el fallo de la sesión de OAuth y el reintento, el 503 durante el
  apagado y el rechazo de las conexiones nuevas. No cubren la segunda señal del mismo tipo ni dos
  primeros inicios simultáneos con la misma identidad, que siguen sin probar. Quedan pendientes las
  pruebas contra un MySQL real, con señales reales del sistema operativo, con systemd y detrás de
  nginx ([Tareas pendientes y riesgos](docs/playground.md#tareas-pendientes-y-riesgos)).
- Las páginas legales son un borrador sin los datos del titular ni revisión jurídica: no deben
  publicarse así. Riesgos y decisiones pendientes (Analytics y su CSP, el `409` que revela si un email
  tiene cuenta, la cancelación de consultas de MySQL):
  [Tareas pendientes y riesgos](docs/playground.md#tareas-pendientes-y-riesgos).

## 0.6.0 — Operaciones sobre textos que declaran sus requisitos

Un programa puede medir un texto, cortarlo, buscar en él, ordenarlo y leer los números escritos en
él. Las funciones nuevas pertenecen a un tipo y se llaman con su nombre (`Text.length`,
`Int.parse`…), y las que pueden no tener respuesta declaran cuándo la tienen con un `requires`
escrito en NEXORA, igual que una función del programa. Implementa la
[decisión 0011](docs/decisions/0011-operaciones-sobre-textos.md). Ningún programa válido en la 0.5.1
deja de serlo ni cambia de resultado, y no se reserva ningún nombre. Para un programa válido solo
cambian los documentos de las herramientas, que ganan campos y entradas sin cambiar de versión:
`"qualifier": null` en los nodos `Call` de `nex inspect`, y las funciones nuevas en `nex symbols`.

### Añadido

- **Funciones de un tipo**, llamadas como `Tipo.función(…)`:
  - `Text.length`, `Text.slice`, `Text.contains`, `Text.starts_with` y `Text.ends_with`. Trabajan
    con caracteres (puntos de código Unicode), sin normalizar y distinguiendo mayúsculas.
  - `Int.can_parse`, `Int.parse`, `Float.can_parse` y `Float.parse`. Leen una única forma de
    número, la misma en cualquier máquina: `Int.parse` un entero dentro del rango de `Int`
    (`"-42"`), y `Float.parse` un número con parte decimal o exponente (`"2.5"`, `"2.5e3"`, pero no
    `"42"`). No admiten espacios, `+` delante, separadores ni otras bases.
- **Las funciones del lenguaje tienen `requires`.** `Text.slice`, `Int.parse` y `Float.parse`
  declaran sus condiciones en NEXORA, con su explicación, y una llamada que las incumple se detiene
  con el mismo `E4001` que una función del programa (código de salida `5`). En `Int.parse` y
  `Float.parse`, el diagnóstico añade una sugerencia según lo que falló: comprobar antes el texto con
  `Int.can_parse` o `Float.can_parse`, o el rango de `Int` si el número no cabe. Un programa puede
  usar las mismas funciones en sus propios `requires` (`requires Int.can_parse(written)`) y en sus
  tipos refinados (`type Code = Text where Text.length(value) == 3`).
- **Orden entre textos:** `<`, `<=`, `>` y `>=` entre dos `Text` (también de tipos refinados con
  base `Text`). Se comparan carácter a carácter por punto de código, y un texto va antes que
  cualquier otro que empiece por él (`"ab" < "abc"`, `"" < "a"`). No depende del idioma ni de la
  configuración del sistema (`"Z" < "a"`), y compara caracteres, no números (`"10" < "9"`).
- Diagnósticos para la nueva sintaxis, sin códigos nuevos: `E1101` cuando la forma está mal
  (`Text.length` sin paréntesis, espacios alrededor del `.`, más de un punto) y `E2008` cuando el
  nombre no existe, con sugerencias como `Did you mean 'Text.length'?` para `length(t)`.
- `nex inspect`: campo `qualifier` en cada nodo `Call` (`null` en las llamadas sin cualificar),
  sin cambiar la versión del esquema (`nexora.inspect/2`). `nex symbols` y las capacidades
  (`language.builtins`): nombres cualificados y campo `contracts` con los requisitos de cada función
  integrada. `nex context`: nombres cualificados en `builtins_called` y valor `text_operations` en
  `features`.
- Ejemplos `texts.nex` y `failing/parse_number.nex`.

### Cambiado

Solo en programas que ya eran inválidos:

- Un `.` fuera de un número, un texto o un comentario pasa a ser un token. Donde antes había `E1001`
  (`x.y`), ahora hay `E1101` o `E2008`.
- `E2011` mantiene su código, su título y su categoría, pero su sugerencia, cuando se compara un
  `Text` con un número, propone convertir uno de los lados con `to_text(...)` o `Int.parse(...)`.
  Ordenar dos `Text` ya no es un error.

### Corregido

- **El paquete de código fuente no podía ejecutar su propia batería de pruebas.** `MANIFEST.in` no
  incluía los esquemas JSON de `tests/golden/schemas/`, y las pruebas que los leen fallaban en una
  copia generada con `python -m build`. El paquete instalable (`.whl`) no estaba afectado.

### Documentación

- Especificación 0.6: sección 8.1 (funciones de un tipo y orden entre textos).
- Guías: requisitos de las funciones del lenguaje en
  [contratos](docs/contracts.md#las-funciones-del-lenguaje-también-tienen-requires), y límites
  actualizados en [limitaciones](docs/limitations.md).
- El ejemplo de bucles de la guía web y de la especificación suma hasta 10 000 en lugar de 100 000:
  así se ejecuta con holgura dentro del límite de tiempo del playground.

### Limitaciones

- Un carácter es un punto de código, no lo que una persona ve como una letra: una `e` con el acento
  combinado tiene longitud 2, y dos textos que se ven iguales pueden ser distintos para `==`.
- El orden entre textos no es alfabético en ningún idioma.
- Los requisitos de las funciones integradas se comprueban al ejecutar; `nex check` no avisa aunque
  los argumentos sean constantes.
- `Float.parse` redondea al `Float` más cercano: el valor que devuelve puede no ser exactamente el
  número escrito (`"0.1"`).
- No hay `trim`, mayúsculas, `split`, `replace`, interpolación ni búsqueda de posiciones.

## 0.5.1 — Revisión de la memoria agotada

Resultado de auditar la [decisión 0009](docs/decisions/0009-memoria-agotada.md) después de
implementarla. Su garantía se cumple: `E3007` se sigue construyendo sin retener los valores del
programa que falló, y cada ejemplo de `nex test` se evalúa aislado. La auditoría encontró dos
defectos alrededor de ella, corregidos aquí. Ningún programa cambia de resultado ni de código de
salida.

### Corregido

- **`E3007` y el `E3004` por falta de pila no decían en qué bucle ocurrieron.** La
  [decisión 0010](docs/decisions/0010-var-y-while.md) (sección 7) da a todo error de ejecución
  dentro de un bucle una nota por bucle (`In turn 3 of the loop at line 6.`). Estos dos se
  construyen cuando el error ya ha salido de los bucles, y llegaban sin ellas. Ahora llevan las
  mismas notas que cualquier otro error en el mismo punto, del bucle más interior al exterior y con
  el mismo máximo de seis.
- **`nex test` en texto podía dejar un resumen sin terminar.** El informe se escribía a medida que
  se preparaba: si fallaba después del resumen (un error interno, la memoria agotada), ese resumen
  quedaba en la salida estándar igual que en un informe completo, con el código `70`. Ahora el
  informe se prepara entero y se escribe al final, como el documento JSON: si algo falla, la salida
  estándar queda vacía. Los informes normales no cambian.

### Limitaciones

- La prueba que agota memoria real (la del worker, con `RLIMIT_AS`) solo puede ejecutarse en Linux
  y macOS, y no se ha ejecutado todavía: en Windows se omite y la integración continua no ha
  funcionado nunca. Las demás pruebas de `E3007` provocan el `MemoryError` a propósito.

## 0.5.0 — `var` y bucles que dicen por qué terminan

La repetición deja de depender de la recursividad y del límite de 1000 llamadas. Y lo hace a la
manera de NEXORA: cada bucle declara por qué termina (`decreases`) y qué mantiene (`invariant`), y
el intérprete lo comprueba en cada vuelta. Así ningún bucle se queda repitiendo para siempre: o
termina, o se detiene y dice en qué vuelta y con qué valores. Implementa la
[decisión 0010](docs/decisions/0010-var-y-while.md).

### Añadido

- **Variables reasignables:** `var count = 0` y `count = count + 1`. El tipo de una `var` no cambia
  nunca. `let` sigue siendo inmutable, y los parámetros también, para que `ensures` y los
  diagnósticos vean siempre los valores con los que se llamó a la función. Una `var` de tipo
  refinado conserva su garantía: se le asigna una constante válida o un valor comprobado con
  `Tipo(x)`.
- **Bucles `while`** con dos cláusulas al principio del cuerpo, con la forma de los contratos y su
  explicación opcional tras una coma:
  - `decreases` (exactamente una): la medida, un `Int` que no baja de 0 y disminuye en cada vuelta.
  - `invariant` (cero o más): condiciones que se cumplen antes de cada evaluación de la condición.
- Códigos nuevos: `E2021` (bucle sin medida, o con más de una), `E4005` (invariante incumplido) y
  `E4006` (la medida no disminuye o es negativa), estos dos de categoría `contract`, con código de
  salida `5`. Sus diagnósticos dicen la vuelta y los valores de todas las variables visibles.
- Un error dentro de un bucle (`E3xxx`, `E4xxx`) gana una nota por cada bucle que lo contiene:
  `In turn 3 of the loop at line 6.`
- `nex test` ya no puede quedarse esperando por un bucle: el ejemplo queda en `error` con `E4006`.
- `nex inspect`: nodos `Var`, `While` y `LoopClause` (sigue siendo `nexora.inspect/2`). `nex symbols`:
  campos `mutable` y `assignments`. `nex context`: campo `mutable` en las variables, campo `loops` al
  final de cada función con la condición, los invariantes y la medida de cada bucle, valores
  `mutable_variables`, `loops` y `loop_invariants` en `features`, y una nota cuando hay bucles.
- `E1103` sugiere cómo escribir con `while` lo que se intentaba con `for`, `break` o `continue`.
- Ejemplos `loops.nex` y `failing/loop_measure.nex`.

### Cambiado

- `E2007` mantiene su código y su título, pero su etiqueta y su sugerencia dicen ahora si el nombre
  es una variable `let` o un parámetro, y proponen `var`.
- La sugerencia de `E2014` recuerda que un bucle puede no ejecutarse nunca.

### Cambios incompatibles

- **`invariant` y `decreases` pasan a ser palabras clave.** Un programa que los use como nombre de
  variable, parámetro o función deja de ser válido (`E1101`); se renombran.
- `var` y `while` dejan de ser palabras reservadas. Ningún programa válido podía usarlas.

### Documentación

- Especificación 0.5: sección 5.3 (`var` y la asignación) y sección 9.5 (bucles).
- Guías: bucles en [contratos](docs/contracts.md#bucles-invariant-y-decreases) y en
  [primeros pasos](docs/getting-started.md).

### Limitaciones

- No hay `for`, `break` ni `continue`, ni asignaciones compuestas (`+=`).
- La medida es un `Int`; no hay medidas compuestas.
- Una medida garantiza que un bucle termina, no que termine pronto: una medida inicial enorme
  permite muchísimas vueltas. Una recursividad lenta (`fib(40)`) sigue sin límite de tiempo.

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
