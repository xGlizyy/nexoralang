# 0014 — Registros nominales inmutables

- **Estado:** aceptada
- **Versión:** 0.8.0 (estado del repositorio; no se ha publicado en ningún paquete). La decisión se
  aceptó con la 0.7.0 y se implementó en la 0.8.0.
- **Fecha:** 2026-10-21
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) (tipos
  estáticos), la [0003](0003-funciones-retorno-e-if.md) (un único espacio de nombres), la
  [0005](0005-diagnosticos-y-esquemas-json.md) (diagnósticos y esquemas JSON), la
  [0007](0007-contratos-estables-y-tipos-refinados.md) (tipos refinados), la
  [0011](0011-operaciones-sobre-textos.md) (funciones de un tipo), la
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) (propuesta de la que sale
  D02) y la [0013](0013-listas-y-for.md) (listas, `for` y el modelo de tipos). **No modifica
  ninguna.**
- **Sustituye a:** ninguna. **No modifica ni sustituye la
  [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) ni la
  [0013](0013-listas-y-for.md)**: la 0012 sigue siendo una propuesta para el resto de su
  contenido y la 0013 sigue aceptando solo D01, D08 y D09.
- **Implementación:** la etapa I6 (registros nominales inmutables), en la 0.8.0. El código está en
  `types.py`, `type_adapter.py`, `ast_nodes.py`, `parser.py`, `checker.py`, `interpreter.py`,
  `values.py`, `tooling.py`, `schemas.py` y `diagnostics.py`; la evidencia está en las pruebas de la
  sección «Pruebas de regresión».

## Contexto

La [decisión 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) propone, entre
otras cosas, los registros de usuario, y su decisión **D02** recomienda que sean **nominales**:
dos registros con los mismos campos no son intercambiables si son declaraciones distintas. La
[0013](0013-listas-y-for.md) aceptó solo la parte de la 0012 que estaba implementada (D01, D08 y
D09) y dejó los registros, los enums, los patrones, `Option`/`Result`, `type_repr` y los genéricos
de usuario como propuesta. Hoy el lenguaje tiene tipos refinados (`type Percent = Int where ...`),
listas `List[T]` y `for`, pero ninguna estructura de datos propia: la especificación lo dice
(`docs/language-spec.md`, «No hay registros, mapas, enumeraciones, `Option`, `Result`…») y las
guías de límites también (`docs/limitations.md`).

El repositorio exige que código, especificación, ejemplos, esquemas y pruebas digan lo mismo, y que
una decisión no se reescriba: si algo se revisa, se añade otra que la sustituye y se indica en
ambas. Este ADR sigue ese patrón: no toca la 0012 ni la 0013; explica qué parte de D02 se decide
ahora y con qué alcance.

El problema técnico que hay que resolver no es la sintaxis, sino la **identidad**. El
comprobador razona hoy con cadenas de tipos (`"Int"`, `"List[Int]"`, `"Percent"`), y el modelo
estructurado de `types.py` distingue la identidad de un tipo refinado por su **nombre**. Para un
registro eso no basta: un registro se declara en un archivo, y su identidad debe ser la de su
**declaración**, no la de su nombre ni la de sus campos. Sin esa distinción, dos registros con el
mismo nombre en programas distintos (o dos campos con el mismo nombre y tipos distintos) se
confundirían, y el intérprete —que compara valores en ejecución— no podría saber si dos valores
son del mismo tipo.

## Decisión

Se decide **una forma de declarar y usar registros nominales inmutables**, sin más. La decisión
acepta la parte de **D02** de la 0012 que está descrita aquí, y nada más de la 0012.

### 1. Qué es un registro

Un registro es un **tipo nominal declarado por el usuario**, con campos **inmutables** y
**obligatorios**, que se construye con campos **con nombre**.

```nexora
type Point = { x: Int, y: Int }

fn main() -> Void {
    let p = Point(x: 1, y: 2)
    print(p.x)
}
```

Propiedades:

- **Nominal.** La identidad es la de su declaración. `Point` y `Line` son tipos distintos aunque
  tengan los mismos campos, y aunque se llame igual en programas distintos.
- **Inmutable.** No hay ninguna forma de cambiar un campo. Un registro se construye una vez y ya
  no cambia.
- **De campos obligatorios.** No hay valores por defecto, ni campos opcionales: una construcción
  debe dar **todos** los campos, **una sola vez** cada uno.
- **Sin métodos.** Un registro solo tiene campos. No hay funciones asociadas a un tipo de
  usuario: `Text.length` y `List.length` siguen siendo las únicas funciones cualificadas, y
  pertenecen a tipos integrados.
- **De valor.** Un registro se puede comparar con `==` y `!=`, imprimir, pasar a una función,
  devolver de una función, guardar en una variable y meter en una lista.

### 2. Sintaxis

**Declaración.** `type Nombre = { campo: Tipo, ... }`.

- El `{` va **en la misma línea que el `=`**. Si hay un salto de línea entre `=` y `{`, es un
  error de sintaxis (`E1101`).
- **Dentro** de las llaves se permiten saltos de línea, entre campos:

  ```nexora
  type Point = {
      x: Int,
      y: Int
  }
  ```

- **No hay registros vacíos**: `type Point = {}` es un error de sintaxis (`E1101`). Un registro
  tiene al menos un campo.
- **No hay coma final**, ni en la declaración ni en la construcción, igual que en las listas y en
  las llamadas (`[1, 2,]` y `f(1, 2,)` ya son errores de sintaxis).
- El **nombre** del registro sigue las reglas de los nombres de tipo: empieza por mayúscula, no es
  el de un tipo integrado (`Int`, `Float`, `Bool`, `Text`, `Void`), no está ya declarado y no se
  usa para una función, un parámetro o una variable. Los incumplimientos son `E2016` (nombre) y
  `E2006` (nombre en uso), los mismos códigos y con el mismo significado que ya tienen.
- Un **campo** se escribe `nombre: Tipo`. Dos campos del mismo registro no pueden llamarse igual
  (`E2016`). El nombre de un campo es un nombre cualquiera del lenguaje: no hay una regla de
  mayúsculas para los campos, porque los valores del lenguaje no la tienen.
- El **tipo** de un campo es cualquier tipo del lenguaje: un tipo integrado, `List[T]`, un tipo
  refinado o **otro registro**. Un tipo que no existe es `E2012`; `Void` como tipo de un campo es
  `E2012`.

**Construcción.** `Nombre(campo: valor, ...)`.

- Los campos se pueden dar **en cualquier orden**; el orden del texto no importa.
- Cada campo se da **una sola vez**. Un campo repetido es `E2023`.
- Todos los campos son obligatorios. Un campo que falta es `E2023`, **uno por cada campo que
  falte**.
- Un campo que el registro no tiene es `E2023`.
- Los valores se escriben **con el nombre del campo**: `Point(1, 2)` es un error de sintaxis
  (`E1101`). No hay construcción posicional.
- La forma es `Nombre(...)`, la misma que una llamada, y el analizador distingue una de otra por el
  nombre: un nombre de registro solo puede ser una construcción.

**Lectura de un campo.** `valor.campo`, y cadenas de acceso `a.b.c` **sin un límite fijo de
longitud**, siempre que cada paso intermedio sea un registro válido.

- La **raíz** de la cadena es siempre un **nombre**: una variable, un parámetro o `result` dentro
  de un `ensures`. No hay acceso a un campo sobre una llamada, una construcción, un grupo ni una
  lista: `f().x` y `(p).x` son errores de sintaxis (`E1101`).
- No se introduce un sistema de posfijos general: `p.x` es la única forma de leer un campo, y
  solo cuando la raíz es un nombre.
- `Point.x` **no** es un acceso a un campo: `Point` es un tipo, no un valor. La forma sigue siendo
  la llamada cualificada de siempre, con su diagnóstico de siempre.

**Asignación a un campo.** `valor.campo = expresión`.

- Los registros son inmutables: asignar a un campo existente es `E2025`.
- La forma solo existe para poder decir que no se puede: el analizador no ejecuta la asignación.

### 3. Identidad nominal y modelo de tipos

La identidad de un registro es **opaca** y **por declaración**: no depende del nombre ni de los
campos.

- `types.py` añade una variante **`Nominal`**: nombre, campos e **identidad**. Dos `Nominal` son el
  mismo tipo si y solo si tienen **la misma identidad**. `types.equal` compara por identidad, no
  por nombre ni por campos.
- La identidad es un **token opaco** (`RecordIdentity`), que el comprobador crea una vez por
  declaración y que viajan en el `CheckedProgram` hasta el intérprete. El intérprete **no**
  reconstruye la identidad a partir del nombre: usa la que le da el comprobador.
- `types.py` gana las ramas que le faltan a `Nominal` en `equal`, `display`, `to_data`, `widen`,
  `root` y `substitute`, y `type_adapter.py` gana un `register_record` y la forma de resolver un
  nombre de registro. Sin esas ramas, un registro no se compararía, no se presentaría y no
  encajaría en el modelo.
- `Nominal` **no** aparece en ningún documento JSON: el campo `type` de las expresiones sigue
  siendo el **nombre canónico** del tipo (`"Point"`), como ya hace con los tipos refinados.

**Igualdad de valores.** La decide el valor, no el nombre:

- Dos valores del **mismo** tipo nominal se comparan **por valor**: campo a campo, en el orden de
  la declaración. `Point(x: 1, y: 2) == Point(x: 1, y: 2)` es `true`.
- Dos valores de **tipos nominales distintos** no se comparan: es un error estático `E2011`, nunca
  un `false` en ejecución.
- Un valor de registro y un valor de otro tipo tampoco: `E2011`.

**Impresión.** Se reutilizan `format_value` y `show_value`, y con ellas se conserva la diferencia
que ya existe entre **imprimir** y **describir**:

| Forma | Texto | Dónde |
|-------|-------|-------|
| `format_value` | `Point(x: 1, y: 2)` | lo que escribe `print`, lo que devuelve `to_text` |
| `show_value` | `Point(x: "a", y: 2)` | diagnósticos, `nex test`, `nexora.test/1` |

Es decir: en la forma de impresión los textos **no** van entrecomillados, igual que en una lista;
en la forma de diagnóstico **sí**, para que se pueda leer como código fuente.

### 4. Comprobación

El comprobador hace tres cosas que no hacía antes.

**Resolución de los campos.** Los tipos de los campos se resuelven **después** de leer todas las
declaraciones, de modo que un registro puede usar otro **declarado más abajo** (referencia
adelantada). Una declaración de registro **no** puede refinarse con otra (`type Meters = Point
where ...` es `E2016`, igual que hoy un tipo refinado no puede tener una lista como base).

**Detección de ciclos.** Un registro no puede contenerse a sí mismo, ni directa ni
indirectamente, ni a través de una lista:

```nexora
type D = { d: D }              // E2016: ciclo directo
type A = { b: B }              // E2016: ciclo indirecto A -> B -> A
type B = { a: A }              // E2016: ciclo indirecto A -> B -> A
type C = { items: List[C] }    // E2016: el ciclo sigue existiendo a través de la lista
```

Un ciclo produce **un solo** `E2016`, en la declaración donde el ciclo empieza, con una nota que
escribe la cadena (`A -> B -> A`). `List` no rompe el ciclo: `List[C]` contiene valores de `C`, y
`C` contiene una `List[C]`.

**Construcción, lectura y asignación.** El comprobador resuelve el nombre del registro, comprueba
que la construcción da exactamente sus campos, comprueba el tipo de cada valor (`E2011` por campo
que no encaje), comprueba que la raíz de una lectura es un registro (`E2024`) y que el campo
existe (`E2024`), y comprueba que a un campo no se le asigna (`E2025`).

El tipo de un registro es un **tipo de valor**: puede ser el tipo de una variable, de un
parámetro, del retorno de una función o de un campo de otro registro. Un registro **no** puede
ser la base de un tipo refinado en esta versión.

### 5. Diagnósticos

Se usan **tres códigos nuevos**. Los tres están libres hoy (el último código `semantic` en uso es
`E2022`), y los tres se registran en `diagnostics.py` con el título y la categoría de esta tabla,
que es la misma que tendrá `docs/language-spec.md` y `docs/diagnostics.md`:

| Código | Título | Categoría | Qué significa |
|--------|--------|-----------|---------------|
| `E2023` | Invalid record construction | `type` | Una construcción bien formada pero con los campos equivocados: falta uno, sobra uno o se repite uno |
| `E2024` | Invalid field access | `type` | Se lee un campo y el valor no es un registro, o el registro no tiene ese campo, o un paso intermedio de la cadena no es un registro |
| `E2025` | Cannot reassign a field | `semantic` | Se asigna a un campo que existe de un registro, que es inmutable |

Los códigos que ya existen **no cambian de significado**:

| Código | Categoría | Uso en los registros |
|--------|-----------|------------------------|
| `E1101` | `syntax` | `type Point = {}`, `Point(1, 2)`, `{` en otra línea que el `=`, coma final, acceso a un campo sobre una llamada o un grupo |
| `E2005` | `semantic` | La raíz de un acceso o de una asignación no está declarada |
| `E2006` | `semantic` | El nombre de un registro se usa para una función, un parámetro o una variable |
| `E2011` | `type` | El tipo de un valor de campo no es el del campo; un registro donde se espera otro tipo; dos registros distintos comparados |
| `E2012` | `type` | El tipo de un campo no es un tipo, o es `Void` |
| `E2016` | `semantic` | Nombre de registro inválido (minúscula, integrado, repetido), campo repetido, o ciclo de registros |

`E2016` mantiene su título («Invalid type declaration») y su categoría (`semantic`); lo que hace
este ADR es **ampliar su descripción documentada** a los casos de los registros, que es la misma
significación aplicada al constructo nuevo. `E1101` mantiene su título («Unexpected token»): el
mensaje dice qué se esperaba, como siempre.

**Un diagnóstico por problema, en orden estable.** Un problema que se puede determinar por sí solo
se informa una vez. Las reglas concretas:

- En una construcción, los campos que el registro **no tiene** se informan **en el orden en que
  se escriben**; los **repetidos**, en el orden en que se escriben; los que **faltan**, en el
  **orden de la declaración**.
- El **tipo** de cada valor de campo se comprueba por separado: un valor con el tipo equivocado
  es un `E2011` propio, y no se mezcla con los errores de forma de la construcción.
- En una **asignación** a un campo que existe se informa **solo** `E2025`: **no** se añade un
  `E2011` por el tipo del valor asignado. El valor se sigue comprobando por dentro (si usa un
  nombre que no existe, sale su `E2005`), pero no se compara con el tipo del campo.
- Si la raíz **no existe**, el diagnóstico es `E2005` y no hay nada más. Si la raíz existe pero
  **no es un registro**, o el campo **no existe**, el diagnóstico es `E2024`: el error de acceso
  **tiene prioridad** sobre el de inmutabilidad, porque sin el campo no hay nada que asignar.

### 6. Herramientas y esquemas

`Program.types` y `context.types` **siguen siendo solo de tipos refinados**. No se mezclan: el
nombre `types` ya significa eso en el repositorio, y `tooling._type_entries()` asume que cada
entrada tiene `base` y `condition`. Los registros van en campos **nuevos y separados**:

| Documento | Campo nuevo | Contenido | Versión |
|-----------|-------------|-----------|---------|
| `nexora.inspect/2` | `Program.records` | Los nodos `RecordDecl` del árbol | **Sin cambio** (`/2`) |
| `nexora.context/1` | `records` | Un objeto por registro: `name`, `fields` (nombre y tipo de cada campo), `valid`, `line`, `reason` | **Sin cambio** (`/1`) |

`valid` dice si la declaración es utilizable: es `true` cuando el nombre, los campos y los tipos
son correctos y el registro no está en un ciclo; es `false` cuando la declaración tiene un error,
y `reason` dice cuál. `records` es `null` cuando el texto no tiene estructura, igual que `types`.

La lista `features` de `nexora.context/1` gana el valor `records` cuando el programa declara
registros. `nexora.symbols/1` **no cambia**: los símbolos son funciones, parámetros y variables, y
un nombre de registro no es un valor.

Los nodos nuevos del árbol son `RecordDecl`, `FieldDecl`, `RecordConstruction`, `FieldInitializer`,
`FieldAccess` y `FieldAssign`. El esquema del árbol se **deriva de las clases** (`schemas.py`), de
modo que los nodos nuevos aparecen en el esquema sin trabajo extra; `Program.records` es un campo
más de `Program`, y `Program` conserva el orden de sus campos (los campos nuevos van al final, como
se hizo con `Function.examples`).

**Compatibilidad de los esquemas, comprobada y no afirmada.** Lo que dice la política del
repositorio (`docs/json-protocol.md`) es direccional: *un documento nuevo debe ser aceptado por un
consumidor viejo*, que ignora los campos que no conoce. Eso **se cumple**: ningún esquema del
repositorio fija `additionalProperties` (lo comprueba `tests/test_tooling.py:96`), así que un
documento con `records` valida contra el esquema viejo. Lo que **no** dice esa política es que un
documento **guardado** con la 0.7.0 valide contra el esquema nuevo: con `Program.records` y
`context.records` como campos obligatorios, **no valida**. Es el mismo caso que ya ocurrió cuando
en la 0.3.0 se añadió `Program.types` al árbol sin cambiar el número de `nexora.inspect/2`, y es
lo que se hará constar en el historial de `docs/json-protocol.md`. No se promete ninguna
compatibilidad que no se haya comprobado.

Las versiones de los formatos **no cambian**: `nexora.inspect/2`, `nexora.context/1`,
`nexora.symbols/1`, `nexora.diagnostics/1`, `nexora.test/1` y `nexora.result/1` siguen igual. Se
añaden campos y tipos de nodo, que es un cambio aditivo. `nexora.capabilities/1` tampoco cambia:
sus `types` son los nombres de los tipos **integrados**, y un registro es del usuario.

### 7. Lo que este ADR no acepta de la 0012

Quedan fuera, y siguen siendo propuesta en la 0012:

- los **enums**, el `match`, los patrones y la **exhaustividad** (D05, D06, D07);
- `Option`, `Result` y su sintaxis;
- los **genéricos de usuario** y las funciones genéricas (D03);
- los **refinamientos** sobre registros o sobre cualquier tipo compuesto (D04);
- la **entrada** de datos, los **módulos** y la evidencia verificable (E, F, H, I);
- `type_repr`, la serialización de valores en JSON y cualquier cambio de los esquemas por un tipo
  estructurado;
- los **registros recursivos**, los **tipos de registro refinados**, los **métodos**, la
  **mutación** de campos, los **registros estructurales** y los **parámetros de tipo** de un
  registro.

## Hechos verificados en el repositorio

Estos puntos se comprobaron en el código, no se deducen:

| Hecho | Dónde |
|-------|-------|
| `E2023`, `E2024` y `E2025` no se usan; `E2022` es el último código `semantic` | `src/nexora/diagnostics.py:74-127` |
| El registro de códigos, sus títulos y sus categorías son la **única** fuente; la especificación y `docs/diagnostics.md` se comparan con él | `tests/test_diagnostics.py:103-106`, `tests/test_docs.py:294-299` |
| Todo código registrado tiene que **usarse** en el código fuente | `tests/test_diagnostics.py:128-133` |
| Los prefijos por categoría: `semantic` y `type` usan ambos `E2` | `tests/test_diagnostics.py:120-125` |
| `Program.types` y `context.types` son de tipos refinados, y `_type_entries()` usa `base` y `condition` | `src/nexora/tooling.py:371-385` |
| `ast.Program` se construye posicionalmente en un sitio más (`interpreter.py:685`), así que el campo nuevo necesita un valor por defecto | `src/nexora/ast_nodes.py:252-255` |
| `unparse` termina en `node.callee`, `_evaluate` termina en `_call` y `_skipped` no conoce los nodos nuevos: los tres necesitan ramas | `src/nexora/interpreter.py:477-496, 638-656, 659-676` |
| `types.equal`, `display`, `to_data`, `widen`, `root` y `substitute` no tienen rama para un tipo nominal de usuario | `src/nexora/types.py:196-219, 224-234, 255-280, 346-382` |
| `type_adapter` resuelve nombres con `_resolve_name` y solo conoce primitivos y refinados | `src/nexora/type_adapter.py:46-51, 162-167` |
| El parser manda **todo** `IDENT . IDENT` a la llamada cualificada, y el diagnóstico «Expected '(' to call…» es el que hay que conservar | `src/nexora/parser.py:630-636, 672-692` |
| La recuperación del parser sincroniza con el siguiente `fn` o `type` que empieza línea: una declaración de registro rota no rompe la recuperación | `src/nexora/parser.py:209-214` |
| El lexer emite un token `NEWLINE` por salto de línea y **no** cambia con las llaves: una declaración multilínea se resuelve en el parser, sin tocar el lexer | `src/nexora/lexer.py:154-171` |
| `type` dentro de una función ya es `E1101` | `src/nexora/parser.py:463-468` |
| `result` solo existe en un `ensures` de una función que devuelve un valor | `src/nexora/checker.py:789-798` |
| Los esquemas no fijan `additionalProperties` | `tests/test_tooling.py:96` |
| La política de compatibilidad y su historial | `docs/json-protocol.md:176-205` |
| Los diagnósticos de llamada cualificada que hay que preservar | `tests/test_text_operations.py:402, 412` |

## Decisiones que se toman aquí, y por qué

| Decisión | Motivo |
|----------|--------|
| Identidad **opaca por declaración**, no por nombre | Es lo que hace que dos registros con el mismo nombre y los mismos campos sean tipos distintos. Es D02, y es lo que el intérprete necesita para comparar valores |
| `Program.records` y `context.records` **separados** de `types` | `types` ya significa «tipos refinados» en el código y en la documentación; mezclarlo cambiaría el significado de un campo existente y rompería `_type_entries()` |
| **Sin versión nueva** de los formatos JSON | Añadir campos y tipos de nodo es un cambio aditivo, que es lo que dice la política del repositorio |
| Cadenas de acceso **sin límite fijo** | El límite de dos niveles era arbitrario: lo que importa es que cada paso intermedio sea un registro, y eso lo comprueba el analizador |
| La raíz del acceso tiene que ser **un nombre** | `f().x` y `(p).x` no tienen una lectura clara, y el parser actual ya los rechaza con `E1101`; mantenerlo evita tocar diagnósticos que no hacen falta |
| `E2023` y `E2024` son de categoría `type`; `E2025` es `semantic` | Un error de forma de una construcción o de un acceso es un problema de tipos; la inmutabilidad es una regla del programa, como la reasignación de una variable (`E2007`, `semantic`) |
| `E2025` **no** añade un `E2011` por el valor | Si el campo no se puede asignar, el tipo del valor es irrelevante: dos errores para un solo problema |
| El error de acceso **tiene prioridad** sobre el de inmutabilidad | Si el campo no existe, no hay nada inmutable que mutar: un solo diagnóstico, y el que explica el problema de verdad |
| Sin coma final | Es lo que ya hacen las listas y las llamadas del lenguaje; una excepción sería una diferencia que no aporta nada |
| `List[Point]` **sí** se permite | Es el mismo tipo `List[T]` de siempre, con un tipo de elemento nuevo; el modelo y el analizador ya lo hacen sin trabajo extra |
| Un tipo **refinado no puede refinarse** con un registro | Los refinamientos sobre tipos compuestos (D04) no están implementados; se dice explícitamente en vez de dejar que el analizador adivine |

## Lo que no garantiza

- Que el acceso a un campo sea rápido: no se ha medido el coste de la representación.
- Que los registros se puedan comparar entre sí con `<` o `>`: no hay orden; solo `==` y `!=`.
- Que un registro pueda refinarse, tener métodos o admitir recursión: nada de eso está implementado.
- Que la identidad de un registro sobreviva a un cambio de nombre o de campos: es la identidad de
  **esa declaración**, y por eso un cambio en la declaración es un cambio de tipo.
- Que los programas aceptados estén libres de errores de ejecución: siguen existiendo la división
  por cero, el desbordamiento, los contratos incumplidos y `List.get` fuera de rango.
- Que el modelo de tipos cubra los tipos futuros: cubre solo los que existen hoy.

## Fuera del alcance

Quedan fuera, además de lo enumerado en el apartado 7: las funciones de orden superior sobre
registros, la igualdad ordenada, los alias de tipo, la impresión personalizada, la serialización
estructurada de valores, la conversión implícita entre registros con la misma forma, la
serialización a JSON de valores en ejecución y cualquier optimización del intérprete.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|------------|
| Aceptar la 0012 entera | Aceptaría enums, `match`, `Option`/`Result`, `type_repr` y genéricos que no existen; convertiría una propuesta en una promesa falsa |
| Reescribir la 0012 para marcar lo implementado | Viola la regla de que las decisiones no se reescriben y borra el contexto histórico |
| Dejar la 0012 como única referencia y no crear esta | El código y la documentación quedarían sin una decisión que los respalde |
| Meter los registros en `Program.types` y `context.types` | Cambiaría el significado de un campo existente, obligaría a `nexora.inspect/3` y rompería `_type_entries()`, que asume `base` y `condition` |
| Identidad por nombre (`"Point" == "Point"`) | Dos declaraciones distintas con el mismo nombre se confundirían; el intérprete no podría saber si dos valores son del mismo tipo |
| Registros **estructurales** (dos registros con los mismos campos son el mismo tipo) | Contradice D02 y hace que añadir un campo a un registro rompa a los demás |
| Límite fijo de dos niveles en el acceso | Es arbitrario: lo que importa es que cada paso intermedio sea un registro, y eso lo decide el analizador |
| Acceso a un campo sobre una llamada o una construcción | No tiene una lectura clara y obligaría a un sistema de posfijos general, que se aplaza |
| `E2023` y `E2024` de categoría `semantic` | Son problemas de tipos, no de nombres: el tipo del valor o del campo es lo que está mal |
| Coma final permitida | Rompería la coherencia con las listas y las llamadas del lenguaje |
| Exigir un tipo de retorno `Void` o un `main` con registros | No hay ninguna razón; los registros son valores como los demás |

## Compatibilidad

**Programas.** Ningún programa válido en la 0.7.0 deja de serlo ni cambia de resultado. La gramática
solo crece: `type Nombre = { ... }` no era código válido antes (era `E1101`), y `a.b` sin
paréntesis después también era `E1101` («Expected '(' to call 'a.b'»), salvo cuando `a` era el
nombre de un tipo, que es el caso que se conserva **exactamente igual**. Un programa que hoy usa
`Text.length` (con o sin paréntesis) no cambia: la forma de llamada cualificada se decide por
tokens, no por el nombre. La única diferencia observable es que `p.x`, donde `p` es una variable
que no es un tipo, pasa de ser `E1101` a ser un acceso a un campo (o un `E2024`/`E2005` si la
variable no existe o no es un registro). Los usos que cambian de diagnóstico ya eran inválidos.

**Herramientas.** Los cambios son aditivos y no cambian la versión de los esquemas:

- `nex inspect`: nodos `RecordDecl`, `FieldDecl`, `RecordConstruction`, `FieldInitializer`,
  `FieldAccess` y `FieldAssign`; el campo `records` en `Program`; el campo `type` de una expresión
  puede ser el nombre de un registro.
- `nex context`: el campo `records`, con `name`, `fields`, `valid`, `line` y `reason`; el valor
  `records` en `features`.
- `nex symbols`: sin cambios.
- `nex inspect` y `nex context` siguen sin ejecutar el programa.

**Versión.** La implementación de esta etapa moverá el estado del repositorio a `0.8.0` y la
especificación a `0.8`, siguiendo lo que hizo la 0013 con la 0.7.0. No se declara publicado: no
hay tag ni paquete publicado. Aceptar esta decisión **no cambia ninguna versión**: la cambia la
implementación, que sigue pendiente de autorización.

## Cambios necesarios

- **Especificación** (`docs/language-spec.md`): gramática de la declaración y la construcción de
  registros, cadena de acceso, inmutabilidad, igualdad nominal, impresión, la tabla de tipos y la
  tabla de diagnósticos con los tres códigos nuevos, y el apartado de limitaciones.
- **Diagnósticos** (`docs/diagnostics.md`): una fila por cada código nuevo, con el mismo título
  que el registro.
- **Guías**: `types.md` (registros), `limitations.md` (lo que sigue sin existir) e `index.md`.
- **Hoja de ruta** (`docs/roadmap.md`): los registros dejan de estar pendientes.
- **Arquitectura** (`docs/architecture.md`): el modelo de tipos ya no es solo «tipos refinados».
- **Protocolo JSON** (`docs/json-protocol.md`): los campos nuevos en el historial de cambios y la
  dirección real de la compatibilidad.
- **Esquema de inspección** (`docs/inspect-schema.md`): `Program.records` y las filas de los nodos
  nuevos.
- **Código**: `types.py`, `type_adapter.py`, `ast_nodes.py`, `parser.py`, `checker.py`,
  `interpreter.py`, `values.py`, `tooling.py`, `schemas.py`, `diagnostics.py`.
- **`CHANGELOG.md`**, `version.py` y `pyproject.toml` a `0.8.0`.
- **Índice de decisiones** (`docs/decisions/README.md`): la fila de esta 0014, como **aceptada** (ya
  está al aceptar este ADR).

## Pruebas de regresión previstas

La implementación se apoya en estas pruebas, que se ejecutan en la batería completa:

| Archivo | Qué fija |
|---------|----------|
| `tests/test_records_syntax.py` | Gramática de la declaración y la construcción, campos obligatorios y con nombre, multilínea, `{` en su línea, registro vacío, coma final, referencias adelantadas, recuperación del parser |
| `tests/test_records_types.py` | Identidad nominal, campos y sus tipos, ciclos (directo, indirecto y por `List`), `List[Point]`, refinamiento con un registro, tipos de valor y de referencia |
| `tests/test_records_values.py` | Construcción, lectura, cadenas de acceso, igualdad por valor, `E2011` entre tipos distintos, inmutabilidad y `E2025`, `result.x` en un `ensures` |
| `tests/test_records_diagnostics.py` | Los tres códigos nuevos: título, categoría, mensaje, posición y orden; la prioridad del error de acceso sobre el de inmutabilidad |
| `tests/test_records_tools.py` | `Program.records`, `context.records` con `valid`, `features`, los nodos nuevos en el esquema y los documentos contra su esquema |
| `tests/test_text_operations.py`, `tests/test_parser.py`, `tests/test_tooling.py`, `tests/test_docs.py` | Lo que no debe cambiar: los diagnósticos de llamada cualificada, el árbol, los documentos y la coherencia de la documentación |

El ejemplo ejecutable es `examples/records.nex`, con su salida registrada en
`tests/golden/examples/records.run.stdout`. La batería completa (`pytest -q`), `ruff check .`,
`npm test --prefix npm` y `git show --check` se ejecutan al cerrar el incremento; el resultado real
se registra en el informe del cambio, no en este ADR.

## Relación con la 0012 y el índice

- La 0012 **no se reescribe**. Su cabecera («no aceptada», «implementación: ninguna») describe el
  momento en que se escribió; este ADR explica qué parte de D02 se decide y con qué alcance.
- Este ADR no sustituye a la 0012 ni la deroga: la complementa para la parte de D02 que este
  documento decide.
- La 0013 sigue aceptando solo D01, D08 y D09. Este ADR no modifica ni sustituye la 0013.
- El índice [`README.md`](README.md) registra la 0014 como **aceptada**, con la implementación
  pendiente.

## Cuestiones que siguen abiertas

Estas no bloquean la decisión. La coma final (**no** se permite, por coherencia con las listas y
las llamadas) y la versión (`0.8.0` para el repositorio y `0.8` para la especificación, cuando se
implemente) quedan resueltas al aceptar este ADR. Solo queda abierta una cuestión de
implementación:

1. **La razón de un registro inválido en `context.records`.** El campo `reason` lleva el texto del
   diagnóstico que explica por qué la declaración no es utilizable. La forma exacta de ese texto es
   un detalle de implementación, siempre que sea la misma cadena que ve la persona en el error.
