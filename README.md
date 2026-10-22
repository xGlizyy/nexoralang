# NEXORA

Lenguaje de programación orientado a la web y diseñado para el desarrollo con inteligencia artificial.

Estado: existe un intérprete (versión 0.10.0) que ejecuta un subconjunto del lenguaje: tipos estáticos, variables inmutables (`let`) y reasignables (`var`), funciones con parámetros y retorno, `if`/`else`, recursividad, bucles `while` que declaran por qué terminan (`decreases`) y qué mantienen (`invariant`), listas inmutables `List[T]` con `List.length`, `List.get`, `List.append`, `List.concat` y `List.contains`, `for` sobre listas, registros inmutables (`type Point = { x: Int, y: Int }`) con identidad nominal, los argumentos del programa (`args()`), la entrada estándar (`input()`) y los archivos con permisos explícitos (`uses read "ruta"` y `--allow-read=ruta`), operaciones sobre textos (`Text.length`, `Text.slice`, `Int.parse`) que declaran sus requisitos, contratos (`requires`, `ensures`) y tipos refinados (`type Percent = Int where ...`), cada regla con su explicación, y ejemplos en las funciones (`example`) que evalúa `nex test`. El resto del diseño aún no está implementado.

Lo que distingue a NEXORA: los requisitos de un programa se escriben en el propio código y se comprueban de forma determinista ([decisión 0006](nexora/docs/decisions/0006-requisitos-verificables.md)).

- [nexora/](nexora/): núcleo del lenguaje. Intérprete, comando `nex`, documentación ([nexora/docs/index.md](nexora/docs/index.md)), ejemplos ejecutables y pruebas. Empieza por [nexora/README.md](nexora/README.md).
- [.github/workflows/nexora-ci.yml](.github/workflows/nexora-ci.yml): integración continua del núcleo para GitHub Actions. Se ejecuta en cada cambio a `main`, en Linux, Windows y macOS.
- [docs/fase-1-diseno.md](docs/fase-1-diseno.md): borrador del diseño completo (sintaxis, tipos, funciones y reglas). Describe hacia dónde va el lenguaje, no lo que funciona hoy.
- [ejemplos/tienda.nx](ejemplos/tienda.nx) y [ejemplos/soporte_ia.nx](ejemplos/soporte_ia.nx): ejemplos del borrador de diseño. Usan sintaxis que el intérprete todavía no admite, así que no se pueden ejecutar.
- [npm/](npm/): paquete de npm (`nexora-lang`) que instala el comando `nex`. Necesita Python 3.11 o superior en la máquina. Preparado y probado en local, sin publicar.
- [web/](web/): página web del lenguaje, con el playground (`/playground`) y una guía (`/guide`).
- [servidor/](servidor/): servidor Node.js que sirve la web, las cuentas de usuario (MySQL) y la API del playground, que ejecuta cada programa con el intérprete real en un proceso aparte. Solo se ha probado en local: [nexora/docs/playground.md](nexora/docs/playground.md).

Herramientas para editores y agentes de IA (análisis en JSON, `nex context`, `nex symbols`, API de Python y servidor MCP opcional): [nexora/docs/ai-tooling.md](nexora/docs/ai-tooling.md). NEXORA no llama a ningún modelo de IA.

Licencia: [MIT](LICENSE).

## Arrancar el servidor

Requiere Node.js 22.23.2 o posterior en la rama 22, o 24.18.1 o posterior en la rama 24, y una base
de datos MySQL o MariaDB. Usa la última versión de tu rama.

```
cd servidor
npm install
cp .env.example .env     # rellena los datos de la base de datos
npm run migrate          # crea las tablas users, sessions y oauth_accounts
npm start
```

Con la configuración copiada de `.env.example`, el playground queda desactivado (`PLAYGROUND_ENABLED=false`) y su API responde 503. Para probarlo en tu equipo, establece `PLAYGROUND_ENABLED=true` en `servidor/.env` y reinicia el servidor.

Úsalo solo para pruebas locales controladas. Como el servidor escucha en todas las interfaces de red, mantén el playground desactivado en servidores accesibles desde Internet hasta completar la [comprobación del aislamiento](nexora/docs/playground.md#comprobar-el-aislamiento).

## Inicio de sesión con Google y GitHub

Es opcional: sin credenciales, los botones llevan a un aviso y el registro con email sigue funcionando.

1. Crea una aplicación OAuth en cada proveedor (los enlaces están en `servidor/.env.example`).
2. Registra como URL de retorno `{PUBLIC_URL}/api/auth/google/callback` y `{PUBLIC_URL}/api/auth/github/callback`.
3. Copia el ID y el secreto de cada una en `servidor/.env` y reinicia el servidor.
