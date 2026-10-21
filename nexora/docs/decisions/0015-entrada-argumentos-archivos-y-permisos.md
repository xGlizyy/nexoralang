# 0015 — Entrada, argumentos, archivos y permisos

- **Estado:** aceptada
- **Versión:** 0.9.0 (estado del repositorio; no se ha publicado en ningún paquete)
- **Fecha:** 2026-10-21
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (solo se ejecuta lo comprobado), la [0005](0005-diagnosticos-y-esquemas-json.md) (códigos de
  diagnóstico estables), la [0009](0009-memoria-agotada.md) (errores de ejecución), la
  [0011](0011-operaciones-sobre-textos.md) (funciones de un tipo) y la
  [0014](0014-registros-nominales-inmutables.md) (registros nominales). **No modifica ninguna.**
- **Sustituye a:** ninguna. **No modifica ni sustituye la
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)**: su parte de entrada (D11)
  y su sistema de efectos (`uses`) siguen siendo propuesta; esta decisión describe otra forma de
  hacer lo mismo, y solo decide lo que se implementa.
- **Implementación:** la 0.9.0. El código está en `capabilities.py` (el modelo de permisos, sin
  sistema operativo), `host.py` (lo que un programa puede hacer además de calcular), `parser.py`,
  `checker.py`, `interpreter.py`, `cli.py`, `api.py` y `worker.py`; la evidencia está en las
  pruebas de la sección «Pruebas de regresión previstas».

## Contexto

Hasta la 0.8.0, NEXORA es un lenguaje de cálculo: un programa lee literales, llama a funciones
propias e integradas y escribe con `print`. No lee nada de fuera. Es una decisión deliberada, no
un descuido: la [decisión 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) hace
que el intérprete solo ejecute programas comprobados, y el borrador de diseño
(`docs/fase-1-diseno.md` de la raíz del repositorio) deja la entrada y los efectos para más
adelante.

Esa limitación impide escribir aplicaciones de consola de verdad: un programa no puede recibir los
argumentos con los que se invoca, ni leer de una tubería, ni abrir un archivo de datos.

El problema no es solo añadir una función de lectura. Es hacerlo **sin convertir el intérprete en
algo que pueda tocar el sistema que lo ejecuta**. Un lenguaje que lee archivos por el motivo que sea
es un problema de seguridad para quien lo ejecuta: el playground de la web ejecuta código de
visitantes, y el servidor MCP analiza código que viene de un asistente.

De ahí la forma que se decide aquí: **el programa declara lo que necesita, quien lo ejecuta
concede lo que permite, y el entorno decide qué se puede conceder**. Ninguna de las tres cosas
basta sola, y el intérprete comprueba las tres en cada acceso, no solo al empezar.

## Decisión

### 1. Qué puede hacer un programa

Se añaden cuatro funciones integradas:

| Función | Qué hace | Permiso |
|---------|----------|---------|
| `args() -> List[Text]` | Los argumentos con los que se ejecutó el programa | Ninguno: siempre permitido |
| `input() -> Text` | Lee **una línea** de la entrada estándar, sin el final de línea | Ninguno: siempre permitido |
| `read_file(ruta: Text) -> Text` | Lee un archivo de texto completo | `uses read` **y** autorización del ejecutor |
| `write_file(ruta: Text, texto: Text) -> Void` | Escribe un archivo de texto (lo crea si no existe) | `uses write` **y** autorización del ejecutor |

`print` sigue siendo la salida estándar y no cambia.

Los argumentos y la entrada estándar **no necesitan declaración**: son la forma normal de invocar
un programa de consola, y no dan acceso a nada que el ejecutor no haya dado ya. Los archivos sí, porque
tocar el disco es lo que se restringe.

### 2. Cómo declara el programa lo que necesita

Una declaración nueva, al nivel superior del archivo, junto a las funciones y los tipos:

```nexora
uses read "datos/entradas.txt"
uses write "datos/salida.txt"
```

`uses` declara una **capacidad**: «mi programa necesita leer esto». Declarar no concede nada: es la
mitad del modelo, no el permiso.

La declaración es una ruta, escrita como un literal de texto. Las rutas relativas se resuelven
respecto al **directorio de trabajo** del proceso, que es donde se espera que se ejecute el
programa y donde quien lo ejecuta ve sus archivos.

### 3. El modelo de permisos: la intersección

La capacidad efectiva de una operación es la **intersección** de tres cosas:

1. **Lo que declara el programa**: un `uses read "ruta"` (o `uses write`) que cubra la ruta.
2. **Lo que concede quien ejecuta**: `--allow-read=RUTA` (o `--allow-write=RUTA`) en la orden de
   `nex run`, repetible.
3. **Lo que permite el entorno**: si el entorno de ejecución admite archivos.

Las tres tienen que estar. Consecuencias, que son el punto de la decisión:

- **Declarar no concede.** Un programa con `uses read "secreto.txt"` que se ejecuta sin
  `--allow-read` recibe un error de permiso, no el archivo.
- **Conceder no habilita.** `--allow-read=secreto.txt` no permite leerlo si el programa no lo
  declara.
- **El entorno manda.** En un entorno que no admite archivos, ninguna combinación los habilita.

Quien concede lo hace de forma **explícita, automatizable y reproducible**: la orden exacta es el
permiso. No hay permisos interactivos, ni «¿quieres permitir este archivo?», ni un aviso que
dependa de una respuesta: el mismo programa, con la misma orden, se comporta igual siempre.

La lectura y la escritura se conceden **por separado**: `--allow-read` no habilita la escritura, ni
al revés.

### 4. Cómo se confinan las rutas

El confineamiento se hace sobre la ruta **resuelta**, nunca sobre el texto escrito:

- La ruta del programa y la ruta concedida se resuelven con `os.path.realpath`, que sigue los
  enlaces simbólicos y las uniones de directorio de Windows. Una ruta que no existe todavía (al
  escribir) se resuelve sobre su parte existente.
- La comparación se hace entre rutas resueltas y **por segmentos**, de modo que `datos/secreto` no
  cuela dentro de un ámbito `datos` solo porque el texto empiece igual.
- Un `..` que sale del ámbito se resuelve fuera de él, y por lo tanto no está cubierto.
- Un enlace simbólico dentro del ámbito que apunta fuera se resuelve fuera de él, y por lo tanto
  tampoco está cubierto.

**No se comprueba un prefijo de texto.** Un prefijo de texto no es un confineamiento: `datos2` no
está dentro de `datos`, y un enlace simbólico puede apuntar a cualquier parte. La comprobación
textual solo se usa en el análisis estático, como ayuda, nunca como frontera de seguridad.

### 5. Qué hace el análisis estático y qué hace el intérprete

`nex check` puede avisar de lo que se ve en el texto:

- Una llamada a `read_file` o `write_file` **sin** una declaración `uses` que la cubra es el error
  `E2026`. Cuando la ruta de la llamada es un literal y ninguna declaración la cubre, también se
  avisa; si la ruta no es un literal (depende de una variable), el análisis no puede saberlo y no
  avisa.

Eso es una **ayuda**, no la seguridad. La frontera real la aplica el intérprete, en cada acceso:

- Si el entorno no admite archivos, `read_file` y `write_file` fallan con `E3008`, aunque el
  programa declare la capacidad y quien lo ejecuta haya concedido el permiso.
- Si falta la declaración o falta la autorización, lo mismo: `E3008`.

Un programa con `E2026` no llega a ejecutarse, porque el análisis estático es obligatorio
(decisión 0002). Un programa sin `E2026` que intente algo no permitido se detiene en ejecución, con
`E3008`. Los dos caminos cierran.

### 6. Los entornos restringidos

| Entorno | Archivos | Argumentos | Entrada estándar |
|----------|----------|------------|------------------|
| `nex run` | Solo con `--allow-read` / `--allow-write` y con la declaración del programa | Los que se pasan tras `--` | La del proceso |
| `nex test` | Igual que `nex run` (las ejemplos se ejecutan) | Los que se pasan tras `--` | La del proceso |
| El worker del playground | **Nunca** | Los que el visitante envíe, si el protocolo los admite | La que el visitante envíe |
| El servidor MCP | **Nunca** (solo analiza, no ejecuta) | — | — |

En el worker, el protocolo **no tiene** campos de permiso: aunque una petición intente concederlos,
se ignoran, y el programa recibe `E3008` al tocar un archivo. El playground es público: no hay
ninguna forma de que un visitante lo convierta en un entorno con acceso a archivos.

### 7. La entrada estándar y su final

`input()` lee una línea y devuelve su texto sin el final de línea. Una línea vacía devuelve el
texto vacío. Cuando ya no queda nada que leer, `input()` es un error de ejecución `E3009`: el
programa se detiene y lo dice. Leer «hasta el final» sin parar no es expresable todavía; cuando
existan `Option` o una función que devuelva todas las líneas, se añadirá.

### 8. Los argumentos

`nex run programa.nex -- uno dos` da al programa los argumentos `uno` y `dos`. Sin `--`, no hay
argumentos. `args()` devuelve una `List[Text]`, con el orden en que se pasaron.

### 9. La opción sin ruta, que no se incluye

Conceder acceso general («a cualquier ruta») **no se incluye** en esta decisión. Si algún día se
incluyera, tendría que ser una opción explícita, con una advertencia visible en cada ejecución,
y seguiría siendo imposible en el playground y en el MCP. No se implementa por accidente: no hay
ninguna forma de concederlo.

## Hechos verificados en el repositorio

| Hecho | Dónde |
|-------|-------|
| El intérprete solo ejecuta programas comprobados; `run` recibe un `CheckedProgram` | `src/nexora/interpreter.py`, `src/nexora/pipeline.py` |
| Las etapas del lenguaje no tocan el sistema operativo: solo la CLI, el `__main__` y el worker pueden importar `os`, `pathlib` o `subprocess` | `tests/test_security.py:61-78` |
| El servidor MCP solo analiza: ninguna de sus siete herramientas ejecuta un programa | `src/nexora/mcp_server.py:11`, `:72` |
| El worker del playground es un proceso aparte que recibe un JSON y devuelve otro; su protocolo no tiene campos de permiso | `src/nexora/worker.py:9-17` |
| La salida del programa la escribe la función que el intérprete recibe (`run(checked, write)`), no el intérprete | `src/nexora/interpreter.py:112-118`, `src/nexora/cli.py:253` |
| `print` y las conversiones se resuelven en el intérprete, y las funciones de un tipo en `prelude.py` | `src/nexora/interpreter.py:590-632`, `src/nexora/prelude.py:145` |
| Los códigos de diagnóstico tienen su número y su categoría en un registro único, y las pruebas comparan el registro con la especificación y con `docs/diagnostics.md` | `src/nexora/diagnostics.py:74`, `tests/test_diagnostics.py:103`, `tests/test_docs.py:294` |
| Los últimos códigos en uso son `E2022` (semántico) y `E3007` (ejecución) | `src/nexora/diagnostics.py:74-127` |
| La gramática es la de `docs/language-spec.md`, sección 3, y el analizador léxico ya reconoce `//` como comentario | `docs/language-spec.md:126-195`, `src/nexora/lexer.py` |
| El playground ejecuta cada programa en un proceso aparte, con límites de tiempo y de salida | `servidor/src/playground/worker.js`, `servidor/src/playground/router.js` |
| La 0012 propone un registro `Input` y `main(input)`, y aplaza el sistema de efectos `uses` | `docs/decisions/0012-…md:605-624`, `:642`, `:988` |

## Decisiones que se toman aquí, y por qué

| Decisión | Motivo |
|----------|--------|
| Los argumentos y la entrada estándar no se declaran | No dan acceso a nada que el ejecutor no haya dado ya; declararlos sería ruido |
| Los archivos se declaran con `uses` | Es lo que el programa dice que necesita: legible, revisable y comprobable por el análisis estático |
| La capacidad efectiva es una intersección de tres | Ninguna de las tres basta sola; una sola decisión (del programa, del ejecutor o del entorno) nunca habilita por sí sola |
| Las rutas se confinan sobre la ruta resuelta | Un prefijo de texto no es un confineamiento: `..` y los enlaces simbólicos lo esquivan |
| La comprobación real la hace el intérprete, no el análisis | El análisis estático puede engañarse; el intérprete es la frontera |
| `--allow-read` y `--allow-write` son independientes | Leer y escribir no es lo mismo, y una aplicación que solo lee no necesita permiso de escritura |
| La opción sin ruta no se incluye | Acceso general a un disco desde un lenguaje no es una capacidad que se conceda por comodidad |
| El playground y el MCP no admiten archivos, sin excepción | El playground ejecuta código de visitantes; el MCP analiza código de un asistente |
| `input()` falla al llegar al final | Devolver un texto vacío no distinguiría el final de una línea vacía, y un programa que lee en un bucle no terminaría nunca |
| `uses` es una declaración, no una expresión | Es una propiedad del programa, no un valor: no puede pasar por un parámetro ni construirse en ejecución |

## Lo que no garantiza

- Que el análisis estático detecte todos los usos indebidos: solo lo que se ve en el texto. La
  seguridad no depende de él.
- Que el confineamiento de rutas valga para un sistema de archivos que cambie mientras el programa
  corre (un `..` resuelto en un momento y otro en otro).
- Que leer un archivo granted sea seguro por sí mismo: el contenido es del archivo, y el programa
  puede interpretarlo como quiera.
- Que `input()` pueda leer «hasta el final» sin parar.
- Que exista aislamiento frente a la red, los procesos o las variables de entorno: no existen
  todavía.
- Que los programas con acceso a archivos sean seguros en un servidor público: por eso el
  playground no los admite.

## Fuera del alcance

- La red, los procesos externos y las variables de entorno.
- Los permisos interactivos por archivo y los avisos que dependen de una respuesta.
- Escribir en un directorio, crear directorios, renombrar o borrar: solo leer y escribir un
  archivo de texto.
- Los archivos que no son de texto (binarios).
- El acceso a la red, a los sockets o a las variables de entorno.
- `Option`, `Result` y las demás construcciones de la 0012.
- Los módulos y las importaciones.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|------------|
| Un registro `Input` con `main(input)`, como propone la 0012 | Cambia la forma de `main` y hace que cada programa que no lea nada declare un parámetro que no usa; además aplaza el problema de los permisos, que es el difícil |
| Declarar el permiso solo en el programa | El programa podría pedir lo que quiera; quien lo ejecuta no podría negar nada |
| Conceder solo desde el ejecutor | El ejecutor no puede saber qué va a leer el programa; conceder «de todo» por prudencia es lo contrario de explícito |
| Una comprobación de prefijo de texto | `datos2` cuela dentro de `datos`, y un enlace simbólico dentro del ámbito puede apuntar fuera. No es un confineamiento |
| Conceder el acceso a cualquier ruta con una opción | Es acceso general al disco con una palabra; el ejecutor deja de controlar lo que ocurre |
| Un aviso interactivo por archivo | Depende de una respuesta: no es automatizable ni reproducible, y en un servidor no hay nadie que responda |
| Dejar que el análisis estático sea la seguridad | Se puede engañar: rutas calculadas, literales construidos en ejecución, o una ruta que cambia entre el análisis y la ejecución |

## Compatibilidad

**Programas.** Ningún programa válido en la 0.8.0 deja de serlo ni cambia de resultado. `print`,
`to_text`, `to_float`, `to_int` y las funciones de `Text`, `Int`, `Float` y `List` siguen igual. Los
programas que no usan las funciones nuevas no se ven afectados: `args()` devuelve una lista vacía y `input()` lee de la entrada estándar, que es lo que
ya hacía el proceso.

**Herramientas.** Los cambios son aditivos y no cambian el número de ningún formato JSON: un nodo
`UsesDecl`, un campo más en `Program`, y el campo nuevo de `nexora.context/1`. Los esquemas se
regeneran; un documento nuevo valida contra el esquema viejo, que ignora los campos que no conoce.

**Códigos.** Se añaden cuatro: `E2026` (falta la declaración de una capacidad), `E3008` (permiso
denegado) y `E3009` (no queda entrada). Los anteriores no cambian de significado.

## Cambios necesarios

- **Léxico y sintaxis**: la declaración `uses`, sus dos formas, y la gramática de `docs/language-spec.md`
  (sección 3).
- **Tipo**: el nodo `UsesDecl`, el campo `uses` en `Program`, y las cuatro funciones en el registro
  de las integradas.
- **Comprobación**: las declaraciones, el error `E2026` cuando una llamada no tiene declaración que
  la cubra, y la tabla de diagnósticos.
- **Intérprete**: `args`, `input`, `read_file` y `write_file`, con la comprobación de permisos en
  cada acceso.
- **Permisos**: el modelo de la intersección y el confineamiento de rutas, en un módulo aparte que
  no toca el sistema: el intérprete pide, el entorno concede.
- **CLI**: `--allow-read` y `--allow-write` en `nex run` y `nex test`, y los argumentos tras `--`.
- **Entornos restringidos**: el worker del playground sin acceso a archivos, y el MCP igual.
- **Herramientas**: `nexora.context/1` con las capacidades declaradas, y `nexora.inspect/2` con el
  nodo nuevo.
- **Documentación**: la especificación, `docs/diagnostics.md`, `types.md`, `limitations.md`,
  `docs/playground.md`, `docs/cli-reference.md` y la guía del sitio.
- **Ejemplos**: un programa que lee argumentos y un archivo autorizado, y uno que falla sin permiso.

## Pruebas de regresión previstas

| Archivo | Qué fija |
|---------|----------|
| `tests/test_input_arguments.py` | Argumentos vacíos y múltiples, con espacios y con Unicode; `args()` sin argumentos |
| `tests/test_input_stdin.py` | Varias líneas, línea vacía, final de la entrada (`E3009`), y que la entrada se lee una vez y en orden |
| `tests/test_permissions_files.py` | Declaraciones, permisos concedidos y denegados, lectura sin escritura y escritura sin lectura, rutas fuera del ámbito, `..`, rutas absolutas, enlaces simbólicos, y el error `E3008` en ejecución |
| `tests/test_permissions_static.py` | El error `E2026` del análisis estático y su ausencia cuando la declaración cubre la ruta |
| `tests/test_permissions_environments.py` | Que el worker y el MCP rechazan siempre el acceso a archivos, y que el playground no puede concederlo |
| `tests/test_security.py` | Que las etapas del lenguaje siguen sin tocar el sistema, y que el módulo de permisos es el único que lo hace |

## Relación con las decisiones anteriores y el índice

- La [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) no cambia: el programa sigue
  sin ejecutarse si tiene errores estáticos, y un programa sin declaración de capacidad no pasa el
  análisis.
- La [0005](0005-diagnosticos-y-esquemas-json.md) no cambia: los códigos nuevos siguen el mismo
  registro, con su categoría y su texto fijo.
- La [0014](0014-registros-nominales-inmutables.md) no cambia: los registros son valores, y un
  registro puede guardarse en un archivo como cualquier otro texto.
- La [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) **no se reescribe**: su
  parte de entrada (D11) y su sistema de efectos siguen siendo propuesta. Esta decisión describe
  otra forma de resolver lo mismo, y solo decide lo que se implementa. La 0012 sigue siendo la
  referencia para el resto de su contenido.
- El índice [`README.md`](README.md) registrará la 0015 cuando se acepte.

## Cuestiones que siguen abiertas

1. **Leer hasta el final.** `input()` falla al llegar al final; no hay forma de leer todas las
   líneas. Se resolverá con `Option` o con una función que devuelva la lista, cuando existan.
2. **La forma de la declaración.** `uses read "ruta"` es una lista de rutas. Cuando haya módulos,
   la ruta podría ser relativa al módulo, y eso hay que decidirlo entonces.
3. **El aviso visible de la opción sin ruta.** No se incluye ninguna; si algún día se incluye, la
   forma del aviso también está por decidir.
4. **Los directorios.** Hoy solo se leen y escriben archivos, no directorios. Ampliarlo cambia el
   modelo de confineamiento y sería otra decisión.
