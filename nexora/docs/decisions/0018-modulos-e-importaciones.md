# 0018 — Módulos e importaciones

- **Estado:** aceptada
- **Versión:** 0.11.0 (estado del repositorio; no se ha publicado en ningún paquete)
- **Fecha:** 2026-10-22
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (solo se ejecuta lo comprobado), la [0005](0005-diagnosticos-y-esquemas-json.md) (los diagnósticos
  tienen código estable) y la [0014](0014-registros-nominales-inmutables.md) (los registros son
  nominales). **No modifica ninguna.**
- **Relacionada con el borrador de diseño:** implementa su §8 («Módulos») y su regla R14 (no hay
  importaciones circulares) **en el alcance que el lenguaje tiene hoy**. El borrador es de la v0.1 y
  escribe otra sintaxis; aquí se decide la que encaja con el lenguaje actual.
- **Implementación:** la 0.11.0. El cargador de módulos está en `modules.py`; el resto del trabajo
  está en `tokens.py`, `ast_nodes.py`, `parser.py`, `checker.py`, `pipeline.py`, `interpreter.py`,
  `cli.py` y `lsp.py`. La evidencia está en `tests/test_modules.py` y en los ejemplos de
  `examples/modules/`.

## Contexto

Un programa de NEXORA es **un único archivo**. Todo lo que el lenguaje tiene hoy cabe en un
fichero, y por eso el lenguaje no tiene módulos: no los necesitaba.

En cuanto un proyecto crece, un archivo se queda corto, y el estilo de resolverlo importando
trozos de código de otra parte tiene un coste que no es solo de longitud: el analizador no puede
saber qué nombres existen, así que no puede comprobar nada. Un programa que importa el código de
otro sitio no está comprobado, y la [decisión 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
no permite ejecutar lo que no está comprobado.

El borrador de diseño (`docs/fase-1-diseno.md` de la raíz del repositorio) lo anticipa en su §8:

```nexora
import http
import app/models.{User, Order}
```

- Un archivo es un módulo; su nombre es el del archivo.
- Todo es privado salvo lo marcado con `pub`.
- Cada tipo es también un espacio de nombres.
- No se permiten importaciones circulares.
- El punto de entrada es `fn main()` en el archivo que se ejecuta.

La [especificación](../language-spec.md) lo recoge como limitación conocida (§13: «Un programa es un
único archivo: no hay módulos ni importaciones») y como funcionalidad prevista (§14).

## Decisión

Se implementan los módulos como **un archivo es un módulo**, con las importaciones al principio
del archivo, un espacio de nombres por módulo y la privacidad con `pub`.

### 1. La sintaxis

```
import "app/models.nex"
```

Una importación es una **declaración de nivel superior** y va **antes que cualquier otra
declaración** del archivo, como en el borrador (`program = { import } { item }`).

La ruta es un **literal de texto**, con la extensión del fichero, y se resuelve **respecto al
fichero que importa**, no respecto al directorio de trabajo:

- Es un literal de texto, y no una palabra, porque el lenguaje ya trata las rutas así: las
  capacidades se declaran `uses read "datos.txt"`, con un literal de texto y con la ruta escrita.
- La extensión se escribe porque el lenguaje no adivina: `List` no es `List[T]`, y un fichero no es
  un fichero sin nombre.
- La ruta es relativa al fichero que importa, y no al directorio de trabajo, porque un programa
  tiene que depender de donde está, no de donde se ejecuta.

Lo que **no** hay en esta versión: los alias (`import "x.nex" as y`) y la importación selectiva
(`import "x.nex".{A, B}`) del borrador. Se explican más abajo.

### 2. El espacio de nombres

Una importación ata un **espacio de nombres** al nombre del fichero importado, sin su extensión:

```
import "app/models.nex"
...
let p = models.Point(x: 1, y: 2)
```

Los nombres de un módulo se usan **cualificados**: `models.add(1, 2)`, `models.Point(...)`,
`models.Percent`. Un módulo nunca suelta sus nombres en el ámbito de quien lo importa.

El nombre del espacio de nombres es el del fichero sin la extensión. Si dos módulos importados
tuvieran el mismo nombre, es un error (`E2030`): renombrar el fichero lo resuelve, y el lenguaje
no decide todavía cómo se llama un módulo que no coincide con su fichero.

### 3. La privacidad

Todo lo que un módulo declara es **privado** salvo que lo marque con `pub`:

```
pub fn add(a: Int, b: Int) -> Int {
    return a + b
}

fn helper(x: Int) -> Int {
    return x * 2
}
```

`models.add` se puede llamar desde fuera; `models.helper` no, y llamarlo es un error (`E2028`).

`pub` vale para las funciones y para los tipos, incluidos los registros: `pub type Point = { x:
Int, y: Int }` hace que el registro y su constructor sean públicos.

El archivo que se ejecuta es la excepción: sus nombres son los del programa, y todos son
visibles, porque son su punto de entrada.

### 4. Las importaciones circulares

No se permiten, y son un error (`E2029`), con los módulos implicados en el mensaje. Es la
regla R14 del borrador.

Un módulo A importa a B y B importa a A: no hay un orden en que se puedan definir los dos, y
permitirlo daría dos lecturas distintas del mismo programa según por dónde se empiece.

### 5. Los tipos cruzan los módulos

Un registro de otro módulo es un registro como cualquier otro, y **nominal**: el registro
`Point` del módulo `models` no es el mismo tipo que un `Point` de otro módulo, y un valor de uno no
se acepta donde se espera el otro.

En el análisis, los nombres de un módulo van cualificados (`models.Point`), de modo que dos
módulos pueden declarar registros con el mismo nombre sin que el analizador los confunda. El
nombre que ve quien escribe el código es el que escribe: `models.Point`.

### 6. Lo que se carga, y cuándo

Los módulos se cargan cuando se **analiza** el programa, no cuando se ejecuta: son parte del
programa, y el programa tiene que estar comprobado antes de ejecutarse (decisión 0002).

El cargador (`modules.py`) resuelve las rutas, lee los ficheros, analiza cada módulo una sola vez
(cada fichero se lee una vez, aunque lo importen varios) y detecta los ciclos.

Un módulo que no se puede leer es un diagnóstico, con el mismo código que usa el comando de
línea cuando el programa principal no se puede leer (`E0001`).

### 7. El alcance de esta versión

Lo que **funciona**:

- `import "ruta/fichero.nex"` al principio del archivo.
- Un espacio de nombres por módulo, con los nombres cualificados.
- `pub` y la privacidad.
- Los registros y las funciones de otros módulos, con su identidad nominal.
- Las importaciones circulares, detectadas y explicadas.

Lo que **no** funciona todavía, y por qué:

- **Los alias y la importación selectiva.** El borrador los tiene; aquí no, porque los dos hacen
  falta por la misma razón: evitar que dos módulos con el mismo nombre se estorben. Con el
  espacio de nombres y el nombre del fichero, un clash es un error claro, no un conflicto
  silencioso. Cuando haga falta, un alias es una palabra clave más y una regla más.
- **El playground.** El playground recibe el programa como texto y lo ejecuta en un contenedor; no
  tiene los ficheros de al lado, así que un programa con importaciones no se puede ejecutar ahí.
  La limitación está escrita en la documentación del playground.
- **Los ejemplos (`example`) de los módulos importados.** Se comprueban, porque el módulo se
  analiza entero, pero `nex test` solo ejecuta los del archivo que se le pasó.
- **`nex inspect`** describe solo el árbol del archivo que se le pasó (con sus `imports`); el
  árbol de los módulos importados no aparece. **`nex symbols` y `nex context`** sí incluyen los
  nombres y las funciones de los módulos importados, cada uno con un campo nuevo `file`, al final
  del objeto (decisión 0008, §8): el archivo que lo declara, con la ruta relativa al programa y `/`
  como separador, nunca la ruta absoluta del equipo. Los esquemas lo recogen: `nexora.inspect/2`
  (`imports`, `public`, `qualifier`), y el campo `file` en `nexora.context/1` y `nexora.symbols/1`.

## Hechos verificados en el repositorio

| Hecho | Dónde |
|-------|-------|
| `import` y `pub` ya estaban reservados para esto | `tokens.py` (`RESERVED_WORDS`) |
| El borrador de diseño ya propone los módulos y su sintaxis | `docs/fase-1-diseno.md` (§8, R14) |
| La especificación ya lo marca como limitación y como previsto | `docs/language-spec.md` (§13, §14) |
| El analizador ya resuelve las llamadas cualificadas de un tipo | `checker.py` (`_qualified_call`), `parser.py` (`_qualified_call`) |
| El intérprete ya resuelve las funciones por nombre | `interpreter.py` (`_call`) |
| Las rutas ya se declaran con literales de texto | `parser.py` (`_uses_declaration`), el ejemplo `uses read "datos.txt"` |
| El comando de línea ya lee el programa de un fichero | `cli.py` (`_load`) |

## Decisiones que se toman aquí, y por qué

| Decisión | Por qué |
|----------|---------|
| La ruta es un literal de texto, con la extensión | Como `uses read "datos.txt"`: el lenguaje escribe las rutas, no las adivina |
| La ruta es relativa al fichero que importa | Un programa depende de donde está, no de donde se ejecuta |
| Un espacio de nombres por módulo | Los nombres de otro módulo no se sueltan en el ámbito de quien importa: no hay clashes silenciosos |
| El espacio de nombres es el nombre del fichero | Es lo que dice el borrador, y no hace falta una palabra clave más |
| `pub` y nada más | Todo privado por defecto es lo más seguro; el borrador dice lo mismo |
| Las importaciones circulares son un error | R14 del borrador: no hay un orden de definición posible |
| Los módulos se cargan al analizar | Son parte del programa: lo que no se comprueba no se ejecuta (decisión 0002) |
| El nombre interno de los tipos es cualificado | Los registros son nominales: dos `Point` de módulos distintos son tipos distintos |
| Sin alias ni importación selectiva | Hacen falta por lo mismo, y se pueden añadir después sin romper nada |
| El playground no los admite | Recibe el programa como texto; no tiene los ficheros de al lado |

## Lo que no garantiza

- No hay alias, ni importación selectiva, ni `import *`: los nombres de un módulo se usan
  cualificados y solo.
- No hay paquetes, ni registros de módulos, ni rutas de búsqueda: la única forma de importar es
  una ruta relativa a un fichero.
- No hay un `main` por módulo: el punto de entrada es el del archivo que se ejecuta, y un módulo
  importado no lo necesita.
- El árbol de los módulos importados no se ve en `nex inspect`; sus nombres y funciones sí se ven en
  `nex symbols` y `nex context`, con el archivo que los declara.
- El playground no ejecuta programas con importaciones.
- Dos módulos importados con el mismo nombre de fichero son un error; no hay forma de renombrarlos
  al importarlos.

## Fuera del alcance

- Los alias y la importación selectiva: se deciden cuando haya dos módulos con el mismo nombre.
- El `pub` en los refinamientos de tipo y en los contratos.
- Un gestor de paquetes o de dependencias: el lenguaje no tiene ni el `cargo` ni el `npm`; las
  importaciones son rutas a ficheros.
- Los módulos anidados (un módulo dentro de otro) y las bibliotecas estándar como módulos.
- El `match` y los enums del usuario: siguen siendo la parte grande de la
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md), que sigue siendo propuesta.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|-----------|
| `import models` (una palabra, como en el borrador) | El lenguaje escribe las rutas con literales de texto; una palabra dejaría la extensión y el directorio a la interpretación |
| `import models.nex` sin comillas | Una ruta sin comillas es indistinguible de un nombre; el lenguaje no tiene esa ambigüedad en ningún sitio |
| Traer los nombres al ámbito de quien importa (`from x import y`) | Los nombres de dos módulos se estorbarían; el espacio de nombres hace que el clash se vea |
| Un único espacio de nombres plano para todo el programa | Un `Point` de un módulo y otro de otro serían el mismo nombre, y los registros son nominales |
| Un `main` por módulo y el que se ejecuta elegido por nombre | No hay forma de saber qué módulo es el de entrada sin otra regla; el archivo que se ejecuta lo dice |
| Cargar los módulos al ejecutar | Lo que no se comprueba no se ejecuta (decisión 0002): el módulo es parte del programa |
| Ignorar los ciclos y dejarlos para la ejecución | Dos lecturas del mismo programa según por dónde se empiece; el error tiene que salir antes |
| Dejar los módulos para después de los enums y el `match` | Los módulos no necesitan `match`: son un espacio de nombres y una resolución de nombres, y la comprobación de tipos ya sabe hacerlo |

## Compatibilidad

- Los programas que ya existen siguen comprobando lo mismo: no había importaciones, así que no
  hay ningún programa cuyo resultado cambie.
- `import` y `pub` pasan a ser palabras clave del lenguaje. Antes eran palabras reservadas, que
  ya no se podían usar como nombres: un programa que usara `import` como nombre no compilaba
  antes, y sigue sin compilar, con el mismo código (`E1103`).
- Los nombres de los módulos son cualificados en el análisis: un tipo que antes se llamaba
  `Point` y se escribía `Point` se sigue escribiendo igual, y ahora se puede llamar `models.Point`
  si viene de un módulo.
- La especificación pasa a la versión 0.11 y la implementación de referencia a la 0.11.0. La
  0.10.0 ya publicada en npm y en PyPI no se toca.

## Cambios necesarios

- `tokens.py`: `import` y `pub` pasan de palabras reservadas a palabras clave.
- `ast_nodes.py`: `ImportDecl`; `Program.imports`; el campo `public` de las funciones, los
  registros y los tipos refinados.
- `parser.py`: las declaraciones de importación, el `pub`, y los tipos cualificados
  (`models.Point`).
- `checker.py`: el prefijo de los nombres de un módulo, la privacidad, las llamadas cualificadas
  a un módulo y los tipos cualificados.
- `modules.py` (nuevo): el cargador, el grafo de importaciones y la detección de ciclos.
- `pipeline.py`: el análisis de un programa con sus módulos.
- `interpreter.py`: las funciones públicas de los módulos importados, con su nombre cualificado.
- `cli.py` y `lsp.py`: el cargador, con el directorio del fichero como base.
- `diagnostics.py`: `E2027` (módulo desconocido), `E2028` (nombre privado), `E2029` (importación
  circular) y `E2030` (dos módulos con el mismo nombre).

## Pruebas de regresión previstas

| Archivo | Qué fija |
|---------|----------|
| `tests/test_modules.py` | La sintaxis, el espacio de nombres, la privacidad, los ciclos, los registros cruzados, las rutas relativas y el error de lectura |
| `tests/test_modules_syntax.py` | Que una importación mal escrita es un error de sintaxis |
| `examples/modules/` | Un programa con módulos, y su salida registrada |
| `tests/test_diagnostics.py` | Que los cuatro códigos nuevos tienen texto, posición y sugerencia |

## Relación con las decisiones anteriores y el índice

Se añade al índice de decisiones como aceptada. No modifica ninguna: usa el analizador y el
intérprete que las decisiones anteriores definieron, y los módulos son la parte del borrador de
diseño que faltaba.

## Cuestiones que siguen abiertas

- ¿Los alias y la importación selectiva entran con el `match` y los enums, o antes? La regla R6
  del borrador dice que una importación sin usar es un error: ¿cuenta como sin usar una
  importación cuyo único uso es un tipo?
- ¿Un módulo puede declarar un `main`? Hoy se ignora, porque el punto de entrada es el del
  archivo que se ejecuta.
- ¿La ruta de una importación debería poder ser un identificador (`import math`) además de un
  literal? Sería más corto, y menos explícito.
- ¿Los tipos refinados y los contratos de un módulo público se comprueban igual que los privados?
  Hoy sí, porque el módulo se analiza entero.
