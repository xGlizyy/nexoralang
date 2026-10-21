# 0013 — Listas, `for` sobre listas y el modelo de tipos que los sostiene

- **Estado:** aceptada
- **Versión:** 0.7.0 (estado del repositorio; no se ha publicado en ningún paquete)
- **Fecha:** 2026-10-21
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (sin
  conversiones implícitas), la [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
  (solo se ejecuta lo comprobado), la [0003](0003-funciones-retorno-e-if.md) (un único espacio de
  nombres), la [0004](0004-contratos-en-ejecucion.md) (`requires` en ejecución), la
  [0005](0005-diagnosticos-y-esquemas-json.md) (diagnósticos y esquemas JSON), la
  [0007](0007-contratos-estables-y-tipos-refinados.md) (tipos refinados), la
  [0010](0010-var-y-while.md) (`var`, `while` e invariantes) y la
  [0011](0011-operaciones-sobre-textos.md) (funciones de un tipo). **No modifica ninguna.**
- **Sustituye a:** ninguna. **No modifica ni sustituye la
  [decisión 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md)**: la 0012 sigue
  siendo una propuesta para el resto de su contenido. Este documento acepta únicamente las partes
  D01, D08 y D09 que ya están implementadas y probadas, en el alcance que se detalla abajo.
- **Implementación:** las etapas I1–I5 del incremento de listas y `for`. El código está en
  `types.py`, `type_adapter.py`, `checker.py`, `parser.py`, `interpreter.py`, `prelude.py` y las
  herramientas; la evidencia está en las pruebas de la sección «Pruebas de regresión».

## Contexto

La [decisión 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) es una propuesta
amplia: modelo de tipos, registros, enumeraciones, patrones, `Option`/`Result`, listas, `for`,
entrada de datos, módulos y evidencia verificable. En el momento de escribirla no había
implementación de ninguna de esas partes y así lo declara su cabecera. Desde entonces se
implementaron, por etapas y con pruebas, tres partes concretas:

1. un modelo de tipos estructurado, construido al lado del comprobador existente (D01);
2. listas inmutables `List[T]`, con literales, igualdad y cinco funciones (D08);
3. `for x in xs { ... }` sobre una `List[T]` (D09).

El código y la documentación no podían seguir en desacuerdo: la especificación no describía las
listas ni las funciones de `List`, la hoja de ruta las presentaba como pendientes y la 0012 seguía
diciendo que no había implementación. A la vez, aceptar la 0012 entera sería falso: registros,
enumeraciones, `Option`/`Result`, `type_repr`, genéricos de usuario y el resto de la propuesta no
existen.

La regla del repositorio es que una decisión no se reescribe: si se revisa, se añade otra. Por eso
este ADR no edita la 0012. La 0012 conserva su estado de propuesta y su texto histórico; la 0013
acepta solo el subconjunto implementado y deja el resto donde está.

## Decisión

Se aceptan **D01, D08 y D09 en el alcance implementado que se describe a continuación**. Nada de lo
que no aparezca aquí se considera aceptado por este ADR.

### 1. D01 — Modelo de tipos, en el alcance implementado

Se acepta que la semántica de los tipos se decida sobre una representación estructurada, no sobre
la comparación de cadenas, y que la cadena canónica siga siendo la forma de presentación pública.

**Representación.** `types.py` define un tipo base `Type` y cinco variantes inmutables:

| Variante | Qué representa | Alcance actual |
|----------|----------------|----------------|
| `Primitive` | `Int`, `Float`, `Bool`, `Text`, `Void` | Los cinco nombres integrados |
| `Constructor` | Nombre, aridad e identidad estable de un constructor | `List` (aridad 1); `Option` y `Result` solo como formas internas reservadas |
| `Application` | Un constructor aplicado a argumentos posicionales | `List[T]`, anidado tanto como permita el parser |
| `Refined` | Un tipo refinado nominal, con nombre, base y referencia a su declaración | Los tipos refinados que ya aceptaba la 0007 |
| `TypeVariable` | Una variable de primer orden, identificada por un entero | Solo para las firmas internas de las funciones de `List`; el lenguaje no permite escribirla |

Las operaciones del modelo son `equal` (identidad), `assignable` (compatibilidad), `widen` y
`root` (ensanchamiento y tipo raíz), `substitute` y `unify` (sustitución y unificación de primer
orden), `display` (texto canónico) y `to_data` (forma interna para pruebas y seguimiento). `to_data`
**no** es un contrato público: no aparece en ningún documento JSON ni tiene esquema. El campo `type`
de los documentos JSON sigue siendo el texto canónico.

`type_adapter.py` es el puente entre los nombres que usa el comprobador y el modelo. Resuelve
primitivos, tipos refinados y la forma canónica `List[T]`; rechaza `None`, los objetos ajenos y toda
forma que no sea canónica. `Option`, `Result`, los registros y cualquier otro constructor quedan
fuera: el adaptador no los resuelve.

**Identidad y compatibilidad.** Dos tipos son el mismo si son el mismo primitivo, la misma
aplicación con los mismos argumentos en orden, el mismo nombre de tipo refinado o la misma variable
de tipo. Un tipo refinado se acepta donde se espera su base, o cualquier base de su cadena; la
dirección contraria exige construir el refinado explícitamente y comprobar su condición al
ejecutar. Los argumentos de un constructor son **invariantes**: `List[Int]` no es `List[Text]` y
`List[Percent]` no es `List[Int]`, aunque `Percent` ensanche a `Int`.

**Unificación.** Las firmas de las funciones de `List` usan una variable de tipo interna. Cada
llamada la liga con los tipos de sus argumentos mediante unificación de primer orden. No hay
genéricos de usuario, generalización automática, typeclasses ni tipos de rango superior.

**Refinamientos.** La semántica de la 0007 no cambia: las constantes se comprueban sin ejecutar y
los valores calculados entran con `Tipo(x)` al ejecutar. En esta versión un tipo refinado solo puede
construirse sobre `Int`, `Float`, `Bool`, `Text` u otro refinado; refinar una lista es `E2016`.
Esto deja pendiente la parte de D01/D04 que permitiría refinar tipos compuestos.

**Diagnósticos.** Las reglas ya migradas al modelo construyen sus diagnósticos a partir de los
valores del modelo. Las reglas que aún no se han migrado conservan su representación de cadena y
sus mensajes. No se introduce `type_repr` ni se cambia la versión de ningún esquema: la parte de
D01.8 que proponía ese campo sigue sin aceptarse.

**Lo que no se acepta de D01.** No se aceptan los tipos declarados por el usuario con constructores
propios (registros y enumeraciones), las funciones como valores, los genéricos de usuario, los alias
de tipo ni `type_repr`. Tampoco se acepta la sustitución completa del comprobador por el modelo: el
comprobador sigue usando sus cadenas para las reglas no migradas, y el adaptador acompaña a esas
cadenas. Es una migración parcial y deliberada, no una reescritura total.

### 2. D08 — Listas, en el alcance implementado

**Tipo y valores.** `List[T]` es una secuencia **inmutable y finita** de valores de tipo `T`. `T`
puede ser `Int`, `Float`, `Bool`, `Text`, un tipo refinado u otra `List[...]`; `Void` no puede ser
elemento (`List[Void]` es `E1101`). El tipo es invariante en `T`.

**Sintaxis.** `List[T]` se escribe en cualquier posición donde se escribe un tipo: anotación de
`let`/`var`, parámetro, retorno, tipo de un tipo refinado (aunque refinarlo sea `E2016`) y
`nex inspect`. El parser limita el anidamiento de tipos a 64 niveles (`E1105`). `List` sin
argumento no es un tipo (`E2012`); `Option[...]`, `Result[...]`, `Foo[...]`, `Int[...]`,
`List[...]` con más de un argumento y `List[Void]` son errores de sintaxis (`E1101`).

**Literales e inferencia.** `[a, b, c]` y `[]` son expresiones. Sin un tipo esperado, el primer
elemento fija el tipo de los demás; todos deben ser aceptables como ese tipo. Con un tipo esperado
`List[T]`, todos los elementos se comprueban contra `T`. Por eso `[Percent(10), 20]` sin anotación
falla (el primer elemento fija `Percent`), mientras que `let xs: List[Int] = [Percent(10), 20]`
acepta el ensanchamiento de cada elemento a `Int`.

Una lista vacía **necesita un tipo esperado**: una anotación, un parámetro, un retorno, una
asignación, el lado izquierdo de una igualdad o una función que fije el tipo del argumento. `let xs = []`
y `print([])` son `E2011`; `a == []` funciona, pero `[] == a` no infiere el tipo del lado derecho. El
tipo esperado también se propaga a listas anidadas: `let xs: List[List[Int]] = [[]]` es válido.

**Igualdad.** `==` y `!=` comparan listas del **mismo tipo** de forma estructural: mismos elementos,
en el mismo orden, comparados recursivamente. El resultado es `Bool`. No hay orden (`<`, `<=`, `>`,
`>=`) entre listas. Dos listas de tipos de elemento distintos no se comparan (`E2011`).

**Representación e impresión.** En ejecución una lista es una tupla inmutable de Python. `print` y
`to_text` escriben la forma canónica con corchetes, sin comillas alrededor de los textos:
`[1, 2, 3]`, `[[1], [2, 3]]`, `[a, b]`, `[]`. `show_value`, que usan los diagnósticos, sí entrecomilla
los textos. No hay sintaxis de índice (`xs[i]`) ni mutación de elementos.

**Funciones.** Se aceptan exactamente estas cinco, con la variable de tipo `T` ligada en cada
llamada:

| Función | Firma | Comportamiento |
|---------|-------|----------------|
| `List.length` | `List.length(xs: List[T]) -> Int` | Número de elementos; total |
| `List.get` | `List.get(xs: List[T], i: Int) -> T` | Elemento en la posición `i`, empezando en 0; parcial |
| `List.append` | `List.append(xs: List[T], x: T) -> List[T]` | Lista nueva con `x` al final; no cambia `xs` |
| `List.concat` | `List.concat(xs: List[T], ys: List[T]) -> List[T]` | Lista nueva con los elementos de `xs` y después los de `ys`; no cambia ninguna |
| `List.contains` | `List.contains(xs: List[T], x: T) -> Bool` | Si algún elemento es estructuralmente igual a `x` |

`List.get` declara `requires 0 <= i and i < List.length(xs)` con la explicación «An index must be
inside the list». Un índice negativo, igual a la longitud o mayor detiene el programa con `E4001`;
no hay índices negativos desde el final ni recortes silenciosos. La comprobación es en ejecución,
también cuando el índice es una constante: `nex check` no demuestra el contrato. Una lista vacía
literal en un argumento de `List.*` necesita un tipo esperado, porque las firmas paramétricas no
fijan el elemento antes de leer los argumentos; por ejemplo, `List.append([], 1)` y
`List.concat([1], [])` son `E2011`.

**Lo que no se acepta de D08.** No hay `List.set`, `map`, `filter`, `fold`, ordenación, `slice` ni
ninguna otra función; no hay `Option` para una variante total de `List.get`; no hay listas
mutables, perezosas ni infinitas; no hay indexación sintáctica; no se pueden refinar listas.

### 3. D09 — `for` sobre listas, en el alcance implementado

**Sintaxis.** `for x in xs { cláusulas sentencias }`. Es una sentencia, no una expresión. `x` es el
iterador; `xs` es el iterable; las cláusulas son cero o más `invariant` y, sintácticamente,
`decreases` (que en un `for` es siempre `E2022`).

**Evaluación.** El iterable se evalúa **una sola vez**, antes de la primera comprobación de
invariantes y antes de cualquier vuelta. Debe tener tipo `List[T]`; un `Int`, `Float`, `Bool` o
`Text` es `E2011`. Una lista vacía literal como iterable (`for x in []`) no tiene tipo esperado y es
`E2011`; para recorrer una lista vacía hay que usar una variable anotada, por ejemplo
`let xs: List[Int] = []`.

**Iterador y ámbitos.** El iterador es inmutable y tiene el tipo del elemento `T`. Se declara en el
propio `for`, no antes, y no puede ocultar un nombre visible (`E2006`). Asignarle un valor es
`E2007`. No es visible después del bucle. Cada vuelta ejecuta el cuerpo en un entorno nuevo: las
variables declaradas en el cuerpo no conservan su valor entre vueltas; las asignaciones a una `var`
del ámbito exterior sí se conservan. Las cláusulas ven los nombres visibles donde está el `for`,
nunca el iterador.

**Invariantes.** Un `for` puede declarar cero o más `invariant`. Cada uno debe ser `Bool` (`E2011`).
Se comprueban antes de cada vuelta y una vez después de la última, con la misma semántica que en un
`while`. En una lista vacía se comprueba una vez, antes de la primera vuelta que no llega a
ejecutarse; no hay una comprobación adicional separada. Un invariante falso detiene el programa con
`E4005` y las notas indican la vuelta y los valores.

**Medida, salida y terminación.** No hay `decreases`: la lista es finita por construcción, y un
`decreases` es `E2022`. No hay `break` ni `continue`; siguen siendo palabras reservadas (`E1103`).
Un `return` dentro del cuerpo termina la función. Los bucles se pueden anidar. Las vueltas no son
llamadas: el bucle no añade una llamada y no consume el límite de 1000, aunque las llamadas dentro del
cuerpo sí cuentan. La terminación es estructural (la
lista es finita), pero no se promete rapidez: una lista enorme tarda lo que tarda, y `nex run` no
tiene límite de tiempo.

**Rutas de retorno.** El análisis de rutas no considera que un `for` siempre devuelve, aunque todas
sus vueltas contengan un `return`. Una función que devuelve un valor necesita un `return` después
del bucle si el `for` es la última sentencia. Es el comportamiento actual y se documenta como tal;
si se quiere cambiar, será otra decisión.

**Lo que no se acepta de D09.** No hay `for` sobre rangos, `Text`, mapas ni iteradores perezosos;
no hay `break`/`continue`; no hay variables de tipo de usuario ni funciones de orden superior que
reciban el cuerpo del bucle.

### 4. Lo que este ADR no acepta de la 0012

Para que no haya dudas, quedan **fuera** de esta aceptación, y siguen siendo propuesta en la 0012:

- los registros, las enumeraciones y los patrones (D02, D05, D06, D07);
- `Option`, `Result` y su sintaxis, sus valores y sus funciones;
- `type_repr` y cualquier cambio de los esquemas JSON por un tipo estructurado;
- los genéricos de usuario, las funciones genéricas y las funciones como valores (D03);
- los refinamientos sobre listas, registros o cualquier tipo compuesto (D04 en la parte no
  implementada);
- la entrada de datos, los módulos, la evidencia verificable y la puerta de seguridad (E, F, H, I);
- los criterios de 1.0 y la secuencia de decisiones que dependen de todo lo anterior (K, L).

La 0012 sigue siendo el lugar donde se discuten esas partes. La 0013 no las aprueba por omisión.

## Motivos

- **Coherencia.** El repositorio exige que código, especificación, ejemplos, esquemas y pruebas digan
  lo mismo. Aceptar solo lo implementado y documentarlo es la única forma de cumplirlo sin fingir
  que la propuesta entera está hecha.
- **Trazabilidad.** Cada parte aceptada tiene pruebas que fallan si deja de funcionar. La 0013 puede
  citarlas; la 0012, en cambio, describe cosas que no existen.
- **Conservación de la historia.** Reescribir la 0012 borraría el registro de que fue una propuesta y
  de que su alcance era mucho mayor. La 0013 deja ese registro intacto y explica la relación.
- **Incrementalidad.** El modelo estructurado se introdujo al lado del comprobador, con un adaptador,
  en vez de reescribirlo entero. Esa decisión reduce el riesgo y permite que las reglas no migradas
  sigan funcionando con sus cadenas.

## Lo que no garantiza

- Que una lista sea barata: la inmutabilidad implica copias en `append` y `concat`; no se ha medido
  el coste.
- Que `List.get` sea total: sigue siendo parcial y exige un índice válido.
- Que los invariantes de un `for` sean los adecuados: se comprueban al ejecutar las vueltas que
  ocurren, no se demuestran.
- Que un `for` termine pronto: solo se garantiza que la lista es finita.
- Que el modelo de tipos cubra todos los tipos futuros: solo cubre los que existen hoy.
- Que los programas aceptados estén libres de errores de ejecución: siguen existiendo división por
  cero, desbordamiento, contratos incumplidos y `List.get` fuera de rango.

## Fuera del alcance

Quedan fuera de esta decisión, además de lo enumerado en el apartado 4: las funciones de orden
superior sobre listas, la igualdad ordenada, la covarianza, los alias de tipo, la impresión
personalizada, la serialización estructurada de tipos y cualquier optimización del intérprete.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|------------|
| Aceptar la 0012 entera | Aceptaría registros, enums, `Option`/`Result`, `type_repr` y genéricos que no existen; convertiría una propuesta en una promesa falsa |
| Dejar la 0012 como única referencia y no crear la 0013 | El código quedaría sin una decisión aceptada que lo respalde; la documentación seguiría diciendo que no hay implementación |
| Reescribir la 0012 para marcar lo implementado | Viola la regla de que las decisiones no se reescriben y borra el contexto histórico |
| Listas mutables | Introducen aliasing y complican la igualdad, los contratos y la terminación; se aplazan |
| `List.get` total devolviendo un valor por defecto | Inventa un valor y oculta el error; la variante total llegará con `Option`, que aún no existe |
| `for` sobre rangos o `Text` en la primera versión | Añade casos especiales y tipos que no existen; se aplaza |
| `break`/`continue` desde el principio | Rompen el razonamiento sobre los invariantes y la terminación; se aplazan |

## Compatibilidad

**Programas.** Ningún programa válido en la 0.6.0 deja de serlo ni cambia de resultado. `for` e `in`
ya eran palabras reservadas y ahora son palabras clave; `[` y `]` eran caracteres inesperados y
ahora son símbolos. Los usos que cambian de diagnóstico ya eran inválidos. `List`, `length`, `get`,
`append`, `concat` y `contains` no se reservan como nombres: las funciones nuevas se llaman
cualificadas (`List.length`), como las de `Text` en la 0011. Un programa puede seguir declarando un
tipo refinado llamado `List`; `List[Int]` siempre significa la lista integrada.

**Herramientas.** Los cambios son aditivos y no cambian la versión de los esquemas:

- `nex inspect`: `arguments` en `TypeRef` (`[]` para un nombre sin corchetes), nodo `ListLiteral` y
  nodo `For`; el campo `type` de una expresión puede ser `List[...]`.
- `nex context`: `loops` incluye `for`, con `kind: "for"`, `condition` igual a `x in xs` y
  `measure: null`.
- `nex symbols`: el iterador aparece como variable inmutable, con su tipo y su ámbito.
- `nex inspect` y `nex context` siguen sin ejecutar el programa.

**Versión.** El estado del repositorio pasa a `0.7.0`. No se declara publicado: no hay tag ni paquete
publicado. El `CHANGELOG.md` lo presenta como estado del repositorio y mantiene separados los cambios
de `servidor/` y `web/`, que no forman parte de esta decisión.

## Cambios necesarios

- Especificación 0.7: sección 4.5 (listas), 8.2 (funciones de `List`), 9.6 (`for`), tablas de tipos,
  compatibilidad, conversiones, diagnósticos y limitaciones.
- Guías: `types.md` (listas y funciones), `limitations.md` (límites reales) y `index.md`.
- Hoja de ruta: listas y `for` dejan de estar pendientes.
- Arquitectura: el modelo de tipos ya no es «tipos son textos».
- Herramientas: documentar los campos aditivos en `inspect-schema.md`, `ai-context.md` y
  `ai-tooling.md`.
- `CHANGELOG.md` y `version.py` a `0.7.0`.

## Pruebas de regresión

La implementación se apoya en estas pruebas, que se ejecutan en la batería completa:

| Archivo | Qué fija |
|---------|----------|
| `tests/test_type_lists_syntax.py` | Tokens `[`/`]`, gramática de `List[T]`, anidamiento, errores de sintaxis, `TypeRef.arguments` y el límite de 64 niveles |
| `tests/test_type_lists_values.py` | Literales, inferencia, listas vacías, homogeneidad, invariancia, ensanchamiento de refinados, igualdad, impresión, inmutabilidad y `main` sin listas |
| `tests/test_type_lists_functions.py` | Aridad y tipos de las cinco funciones, contrato de `List.get`, resultados, inmutabilidad de `append`/`concat` y búsqueda estructural |
| `tests/test_for.py` | Sintaxis, orden, evaluación única, lista vacía, tipo del iterador, ámbitos, inmutabilidad, `return`, anidamiento, invariantes, `E2022`, palabras reservadas y herramientas |
| `tests/test_parser.py`, `tests/test_inspect.py`, `tests/test_tooling.py` | Nodos, esquemas y documentos de las herramientas |
| `tests/test_examples.py`, `tests/test_docs.py` | `examples/lists.nex`, sus salidas registradas y los programas de la documentación |

El ejemplo ejecutable es [`examples/lists.nex`](../../examples/lists.nex), con su salida en
`tests/golden/examples/lists.run.stdout`. La batería completa y `ruff check .` se ejecutaron al
cerrar este incremento; el resultado real se registra en el informe del cambio, no en este ADR.

## Relación con la 0012 y el índice

- La 0012 **no se reescribe**. Su cabecera («no aceptada», «implementación: ninguna») describe el
  momento en que se escribió; la 0013 explica qué partes se han implementado y aceptado desde
  entonces.
- La 0013 no sustituye a la 0012 ni la deroga: la complementa para el subconjunto implementado.
- El índice [`README.md`](README.md) registra la 0012 como propuesta y la 0013 como aceptada.
