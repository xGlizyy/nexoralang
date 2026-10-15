# 0010 — Variables reasignables (`var`) y bucles con requisitos (`while`, `invariant`, `decreases`)

- **Estado:** aceptada
- **Versión:** 0.5.0
- **Relacionada con:** la [decisión 0003](0003-funciones-retorno-e-if.md) (rutas de retorno), la
  [0004](0004-contratos-en-ejecucion.md) (los parámetros en `ensures`), la
  [0006](0006-requisitos-verificables.md) (la línea principal), la
  [0007](0007-contratos-estables-y-tipos-refinados.md) (la garantía de los tipos refinados y la
  forma de las cláusulas) y la [0008](0008-ejemplos-y-nex-test.md) (`nex test`). **No modifica
  ninguna**: las conserva, y esta decisión explica cómo.

## Contexto

Hoy toda variable es inmutable (`language-spec.md`, 5.1) y no hay bucles: la única forma de repetir
algo es la recursividad, limitada a 1000 llamadas anidadas (`E3004`, sección 7.5). Es el primer
punto de "Planificado" en la [hoja de ruta](../roadmap.md): "Van juntos: uno no sirve sin el otro.
Eliminan la dependencia de la recursividad."

| Necesidad | Hoy | Problema |
|-----------|-----|----------|
| Sumar los números de 1 a 5000 | Una función recursiva | `E3004`: más de 1000 llamadas anidadas |
| Repetir hasta que se cumpla una condición | Recursividad con el estado en los parámetros | El límite lo pone la implementación, no el problema |
| Acumular un resultado | Una variable nueva en cada paso o una función auxiliar | Código que nadie escribiría en otro lenguaje |

El borrador de diseño (`docs/fase-1-diseno.md`) proponía `var`, `while` y la regla R3: "Todo es
inmutable por defecto; solo `var` permite reasignar". Ambas palabras están reservadas desde la 0.1.

### El problema que introducen los bucles

En los lenguajes habituales un bucle es el sitio donde más fácil es equivocarse sin que nada lo
señale: no termina, termina una vuelta antes o después, o rompe en una vuelta intermedia una regla
que el código daba por supuesta. En NEXORA, además:

- **Hasta hoy toda repetición sin fin acababa en `E3004`.** Con un `while` corriente, `while true { }`
  no terminaría nunca sin agotar ni la pila ni la memoria. `nex run` y `nex test` se quedarían
  esperando, y un agente que ejecuta `nex test` sin supervisión no recibiría nunca el informe.
- **Un programa NEXORA no puede leer entradas** (sección 8 de la especificación). No existe ningún
  programa correcto que necesite un bucle sin fin: no hay un servidor ni un menú que esperar. Un
  bucle que no termina es siempre un defecto.
- **La línea principal del proyecto** ([0006](0006-requisitos-verificables.md)) es que los requisitos
  forman parte verificable del programa. Una función los declara con `requires` y `ensures`; un bucle,
  que es la parte del código donde más se necesitan, no tendría ninguno.

## Decisión

### 1. `var`: una variable que puede cambiar de valor

```text
var count = 0
var total: Int = 0
```

- Misma forma que `let`: `var` NOMBRE [`:` TIPO] `=` EXPRESIÓN. Se inicializa siempre al declararla.
- **Su tipo es fijo.** Se infiere del valor inicial o se anota, con las mismas reglas que `let`
  (`E2011`, `E2012`). Cambia el valor, nunca el tipo.
- Mismas reglas de ámbito que `let` (`language-spec.md`, 5.2): existe desde la sentencia siguiente
  hasta el final de su bloque; sin ocultación (`E2006`); un único espacio de nombres (`E2006`).
- `let` sigue siendo inmutable. **Lo inmutable es lo que se escribe por defecto**; `var` señala en la
  declaración que el valor puede cambiar más abajo.

### 2. La asignación

```text
count = count + 1
```

- Es una **sentencia**, no una expresión. `a = b = 1` e `if x = 1 { }` son `E1101`.
- Solo existe `=`. **No hay `+=`, `-=` ni `++`**: una sola forma de escribir cada cosa.
- Se evalúa el valor y después se guarda.

| Destino | Resultado |
|---------|-----------|
| Una variable `var` visible en ese punto (también desde un bloque interior) | Correcto |
| Una variable `let` | `E2007`, con una nota que señala la declaración y la sugerencia de usar `var` |
| Un parámetro | `E2007` (sección 3) |
| Un nombre que no es una variable visible | Como hoy: `E2005` |

El valor tiene que ser compatible con el tipo de la variable, con la regla de siempre
(`language-spec.md`, 4.2).

### 3. Los parámetros siguen siendo inmutables

Un parámetro no puede reasignarse (`E2007`). Es lo que mantiene la regla de los contratos "en
`ensures` [los parámetros] tienen el mismo valor que al entrar" (9.1) y que la nota "It was called
with: …" de los diagnósticos diga la verdad. Quien necesite cambiarlo escribe `var n = start`.

### 4. Los tipos refinados conservan su garantía

Una asignación a una variable de tipo refinado llega por uno de los dos caminos que ya existen
(`language-spec.md`, 4.4):

```text
var p: Percent = 20
p = 30                 // constante: se comprueba sin ejecutar (E2017 si no cumple)
p = Percent(p + 10)    // comprobación explícita: al ejecutar (E4003 si no cumple)
p = p + 10             // E2011: un Int no es un Percent; la sugerencia propone Percent(...)
```

Las constantes de las asignaciones cuentan en el mismo presupuesto de análisis (`E2019`).

### 5. `while`, con sus requisitos al principio del cuerpo

```text
fn sum_to(n: Int) -> Int {
    requires n >= 0, "Only natural numbers"
    ensures result == n * (n + 1) / 2
    var total = 0
    var i = 0
    while i < n {
        invariant total == i * (i + 1) / 2, "total is the sum of the numbers already added"
        decreases n - i, "Each turn moves i one step closer to n"
        i = i + 1
        total = total + i
    }
    return total
}
```

Un bucle es `while` CONDICIÓN `{` CLÁUSULAS SENTENCIAS `}`. Las cláusulas van al principio del cuerpo,
una por línea, con la forma de los contratos de una función: expresión y, tras una coma, la
explicación opcional.

| Cláusula | Cuántas | Qué declara | Tipo |
|----------|---------|-------------|------|
| `decreases` | **Exactamente una** | La **medida**: una cantidad que no baja de 0 y que disminuye en cada vuelta. Es la razón por la que el bucle termina | `Int` |
| `invariant` | Cero o más | Una condición que se cumple **antes de cada evaluación de la condición** del bucle: al llegar, después de cada vuelta y, por tanto, al salir | `Bool` |

Reglas:

- **Todo bucle declara su medida.** Un `while` sin `decreases` es `E2021`; con dos o más, `E2021`.
- Las cláusulas ven todo lo que es visible en el punto del bucle (parámetros, `let`, `var`) y nada
  declarado dentro del cuerpo. Pueden llamar a funciones, como los contratos.
- `invariant` y `decreases` fuera del principio del cuerpo de un `while` son `E1106`, igual que
  `requires`, `ensures` y `example` fuera del principio de una función. Y al revés: `requires`,
  `ensures` y `example` dentro de un `while` son `E1106`.
- La condición del bucle es `Bool` (`E2011`).
- **Cada vuelta abre un ámbito nuevo**: lo declarado dentro del cuerpo existe solo en esa vuelta.
- Un `return` dentro del cuerpo termina la función, como en cualquier bloque; la vuelta en curso
  no se completa y no se comprueba nada más del bucle.
- **Las vueltas no son llamadas.** No cuentan para el límite de 1000 llamadas ni consumen la pila de
  Python: el intérprete ejecuta el bucle de forma iterativa.
- No hay `break`, `continue` ni `for` (siguen reservadas; ver "Fuera del alcance").

### 6. Qué se comprueba en cada vuelta

El intérprete ejecuta un `while` así:

1. Comprueba los `invariant`, en orden. Si uno es falso: **`E4005` Loop invariant violated**.
2. Evalúa la condición. Si es `false`, el bucle termina.
3. Evalúa la medida. Si es negativa, o si no es **estrictamente menor** que la medida de la vuelta
   anterior de esta misma ejecución del bucle: **`E4006` Loop measure did not decrease**.
4. Ejecuta el cuerpo, en un ámbito nuevo, y vuelve al paso 1.

Consecuencias:

- **Un bucle siempre termina, o se detiene con un diagnóstico que dice por qué no lo hacía.** La
  medida es un entero que no baja de 0 y baja en cada vuelta; no puede hacerlo indefinidamente. Es un
  argumento matemático, no un límite de tiempo: el mismo programa da siempre el mismo resultado.
- El invariante se comprueba también al salir: el código que sigue al bucle puede contar con él.
- La medida se compara con la de la vuelta anterior de **esa ejecución** del bucle. Un bucle interior
  vuelve a empezar su comparación cada vez que se entra en él.
- Como en los contratos, si evaluar una cláusula produce un error de ejecución (`E3xxx`), el error
  que se comunica es ese.

### 7. Los diagnósticos de un bucle dicen en qué vuelta y con qué valores

`E4005` y `E4006` son de categoría `contract` (código de salida `5`, como `E4001`–`E4003`):

```text
contract error[E4006]: Loop measure did not decrease
 --> program.nex:6:19
  |
6 |         decreases n - i, "Each turn moves i one step closer to n"
  |                   ^^^^^ The measure was 3 and is still 3
  = note: In turn 4 of the loop at line 5
  = note: The values: n = 10, i = 7, total = 28
  = note: Reason: Each turn moves i one step closer to n
```

| Campo | `E4005` Loop invariant violated | `E4006` Loop measure did not decrease |
|-------|--------------------------------|---------------------------------------|
| Posición | La cláusula `invariant` | La cláusula `decreases` |
| Etiqueta | `This condition is false` y, si es al salir, `This condition is false when the loop ends` | `The measure was A and is now B` · `The measure was A and is still A` · `The measure is B; it must be 0 or more` |
| Notas | `The condition at line N is false: invariant …` · `In turn K of the loop at line L` (`Before the first turn…`, `After the last turn…`) · `The values: …` · `Reason: …` | `In turn K of the loop at line L` · `The values: …` · `Reason: …` |

**`The values:`** muestra las variables y los parámetros visibles en el punto del bucle, en el
orden en que se declararon, con el formato de `print`. Es lo que una persona o un agente necesita para
saber qué vuelta falló y por qué, sin añadir `print` para depurar. Los textos largos se recortan con
la misma regla que las notas de los contratos.

**Errores de ejecución dentro de un bucle.** Un `E3xxx` producido dentro del cuerpo o de sus cláusulas
gana la nota `In turn K of the loop at line L`, una por cada bucle que lo contiene, del más interior
al más exterior. Ningún otro campo cambia.

### 8. Rutas de retorno y código inalcanzable

La regla de la [decisión 0003](0003-funciones-retorno-e-if.md) no evalúa condiciones, y se mantiene:

| Sentencia | Siempre devuelve si… |
|-----------|----------------------|
| `while` | **Nunca** (la condición puede ser falsa desde el principio) |
| Asignación | Nunca |

- Una función con valor cuyo único `return` está dentro de un `while` es `E2014`.
- El código después de un bucle nunca es inalcanzable (`E2015` no se aplica): todo bucle termina.
- `E2015` sí se aplica dentro del cuerpo, después de un `return`.

### 9. Diagnósticos nuevos y cambiados

| Código | Título | Categoría | Cuándo |
|--------|--------|-----------|--------|
| `E2021` | Missing loop measure | `semantic` | Un `while` sin `decreases`, o con más de uno. Sugerencia para el caso que falta: `Add 'decreases <expression>' with an Int that gets smaller on every turn and never goes below 0, for example 'decreases n - i'.` |
| `E4005` | Loop invariant violated | `contract` | Sección 6, paso 1 |
| `E4006` | Loop measure did not decrease | `contract` | Sección 6, paso 3 |

`E1106` (Misplaced contract clause) cubre también `invariant` y `decreases` mal colocadas; su título
no cambia. `E2007` conserva código y título; cambian su etiqueta y su sugerencia:

| Caso | Etiqueta | Sugerencia |
|------|----------|------------|
| Variable `let` | `'x' was declared with 'let' and cannot be given a new value` | `Declare it with 'var' if its value has to change.` |
| Parámetro | `'n' is a parameter and cannot be given a new value` | `Copy it into a variable: 'var name = n'.` |

### 10. Lo que no cambia

- **Contratos de función:** `requires` y `ensures` siguen viendo solo los parámetros y `result`.
- **Ejemplos:** no ven variables; su evaluación no cambia.
- **Funciones:** no ven las variables de quien las llama. Sin funciones anónimas ni variables
  globales, una `var` solo cambia desde su propia función: no hay estado compartido.
- **Valores:** siguen siendo inmutables. `var` cambia a qué valor se refiere un nombre.

### 11. Herramientas

| Formato | Cambio | Versión |
|---------|--------|---------|
| `nexora.inspect/2` | Nodos nuevos `Var` (campos de `Let`), `While` (`condition`, `invariants`, `measure`, `body`) y `LoopClause` (`kind`: `"invariant"` o `"decreases"`, `condition`, `message`). `Assign` no cambia de campos; su descripción deja de decir que siempre va con `E2007` | Sigue en `/2`: solo se añaden tipos de nodo, como `Example` en la 0.4.0 |
| `nexora.symbols/1` | Campo `mutable` en cada símbolo (`true` solo en las `var`) y campo `assignments` con la posición de cada asignación (que también están en `references`) | Sin cambio: campos añadidos |
| `nexora.context/1` | Valores `mutable_variables`, `loops` y `loop_invariants` en `features`; con bucles, la nota: `Every loop declares a measure ('decreases') that is checked on every turn: a loop ends, or stops with E4006. Invariants are checked before every evaluation of the loop condition (E4005).` | Sin cambio: valores añadidos |
| `nexora.diagnostics/1`, `nexora.result/1`, `nexora.test/1` | Solo códigos nuevos | Sin cambio |

Un nodo `Var` en lugar de un campo `mutable` en `Let`: una herramienta escrita para la 0.4 nota un
tipo de nodo desconocido, pero ignora en silencio un campo nuevo y trataría la variable como
inmutable.

## Motivos

- **Elimina un límite de la implementación del lenguaje.** El límite de 1000 llamadas deja de decidir
  qué programas se pueden escribir.
- **Ningún bucle se queda colgado.** Se resuelve de forma determinista, sin límites de tiempo que
  dependan de la máquina, y por eso `nex test` y `nex run` siempre terminan con un resultado cuando
  el programa usa bucles. Para un agente que ejecuta `nex test` sin supervisión es la diferencia
  entre recibir un informe y no recibir nada.
- **El bucle explica por qué es correcto.** La medida y el invariante son los dos argumentos que se
  usan para razonar sobre un bucle; aquí se escriben en el código, con su explicación, y se
  comprueban. Es la [decisión 0006](0006-requisitos-verificables.md) aplicada al sitio donde más se
  necesita.
- **Los diagnósticos dicen la vuelta y los valores.** Un fallo en la vuelta 4 de 10 se entiende sin
  depurar.
- **Coherente con lo que existe.** Las cláusulas tienen la forma, la posición y el tipo de
  explicación de `requires`/`ensures`; los errores son `contract` con salida `5`.
- **Lo inmutable sigue siendo lo normal**, y ninguna regla existente se debilita (parámetros, tipos
  refinados, ámbitos).

## Lo que no garantiza

- **Que un programa termine pronto.** Una medida inicial de `1_000_000_000` permite mil millones de
  vueltas. La garantía es que el bucle termina o se detiene con `E4006`, no que lo haga en un tiempo
  razonable. Tampoco cubre la recursividad: una función recursiva puede seguir tardando mucho
  (`fib(40)`), como hoy.
- **Que la medida o el invariante sean los adecuados.** Se comprueba lo que está escrito, en las
  vueltas que se ejecutan. Un invariante trivial (`invariant true`) se cumple siempre.
- **Verificación estática.** Nada de esto se demuestra sin ejecutar; `nex check` comprueba que las
  cláusulas estén bien formadas.
- **Que una `var` cambie alguna vez.** No existen los avisos.

## Fuera del alcance

- `break` y `continue`. Con una medida obligatoria, salir antes no rompe nada, pero cada salida es
  otro punto en el que el invariante tiene que valer; se decidirá cuando haga falta.
- `for` y los rangos, que esperan a las listas.
- Asignaciones compuestas (`+=`) y de incremento.
- Medidas que no sean un `Int` (pares, textos).
- Un límite de tiempo en `nex test` para la recursividad lenta.
- `if` como expresión.

## Alternativas descartadas

- **Un `while` sin medida, como en otros lenguajes.** Era el primer borrador de esta decisión. Deja
  sin respuesta los programas que no terminan, en un lenguaje en el que nunca son correctos, y obliga
  a `nex test` a depender de un límite de tiempo.
- **Un límite fijo de vueltas.** Rompe programas correctos que necesitan muchas, y el número no
  explica nada.
- **Un límite de tiempo.** Depende de la máquina: el mismo programa daría resultados distintos.
- **Deducir la medida sin escribirla.** Funciona en los casos sencillos y falla sin explicación en
  los demás; una regla que a veces se aplica sola es más difícil de entender que una que siempre se
  escribe. Escrita, además, es un requisito más que un agente no puede borrar sin que se note.
- **Medida opcional.** Volvería a permitir bucles sin fin, y su ausencia no se notaría.
- **Hacer reasignable cualquier variable.** Rompe R3 y la regla de que cada nombre significa una
  sola cosa (5.2).
- **Permitir reasignar parámetros.** Cambiaría su significado en `ensures` y en los diagnósticos.
- **La asignación como expresión.** Permite `if x = 1`, un error clásico.
- **Palabras contextuales en lugar de palabras clave.** `invariant` y `decreases` podrían seguir
  siendo nombres fuera de un bucle, pero `invariant(x)` al principio de un bucle sería ambiguo entre
  una cláusula y una llamada. Palabras clave, como `requires` y `ensures`.

## Compatibilidad

- **Cambio incompatible:** `invariant` y `decreases` pasan a ser palabras clave. Un programa que los
  use como nombre de variable, parámetro o función deja de ser válido (`E1101`); se renombran.
- `var` y `while` pasan de palabras reservadas a palabras clave: antes usarlas era `E1103`.
- **`E2007`:** mismo código y título; etiqueta y sugerencia nuevas.
- **Formatos JSON:** solo añadidos (sección 11). Ninguna versión cambia.
- **Playground:** el resaltado de sintaxis gana `var`, `while`, `invariant` y `decreases`.

## Cambios necesarios

| Archivo | Cambio |
|---------|--------|
| `nexora/src/nexora/tokens.py` | `var`, `while`, `invariant`, `decreases` como palabras clave |
| `nexora/src/nexora/ast_nodes.py` | `Var`, `While`, `LoopClause` |
| `nexora/src/nexora/parser.py` | `var`; `while` con sus cláusulas; `E1106` para cláusulas mal colocadas |
| `nexora/src/nexora/checker.py` | Mutabilidad de los símbolos; asignación; `while` y sus cláusulas; `E2021`; rutas de retorno |
| `nexora/src/nexora/interpreter.py` | `Environment.assign`; `while` iterativo con las comprobaciones de la sección 6; notas de vuelta y valores |
| `nexora/src/nexora/diagnostics.py` | `E2021`, `E4005`, `E4006` |
| `nexora/src/nexora/tooling.py`, `schemas.py` | Sección 11 |
| `nexora/docs/*` | Especificación, diagnósticos, esquema de `inspect`, herramientas, limitaciones, hoja de ruta |
| `nexora/examples/loops.nex` | Ejemplo nuevo |
| `web/js/playground/syntax.js` | Palabras clave |

## Pruebas de regresión

**Sintaxis**

1. `var`, asignación y `while` con cláusulas se analizan con los nodos nuevos.
2. `var` y `while` ya no dan `E1103`; `break`, `continue` y `for` sí.
3. `invariant` o `decreases` fuera del principio de un `while`, y `requires`/`ensures`/`example` dentro
   de uno, dan `E1106`.
4. `a = b = 1` e `if x = 1 { }` dan `E1101`; `let invariant = 1` da `E1101`.

**Comprobación**

5. Asignar a una `var` del mismo bloque y de uno exterior es correcto.
6. Asignar a una `let` o a un parámetro da `E2007` con la etiqueta y la sugerencia de la sección 9.
7. Asignaciones de otro tipo (`E2011`) y a tipos refinados (sección 4), incluido el presupuesto `E2019`.
8. `while` sin `decreases` o con dos da `E2021`; medida no `Int`, invariante o condición no `Bool`,
   `E2011`.
9. Las cláusulas no ven lo declarado dentro del cuerpo (`E2005`).
10. Rutas de retorno (sección 8).

**Ejecución**

11. Un bucle de 100 000 vueltas termina con el resultado correcto y sin `E3004`.
12. Lo declarado dentro del cuerpo no sobrevive a la vuelta.
13. Medida que no baja, que sube y que llega a ser negativa: `E4006` con cada etiqueta, la vuelta y
    los valores.
14. Invariante falso al llegar, en una vuelta intermedia y al salir: `E4005` con cada nota.
15. Un bucle interior vuelve a empezar la comparación de la medida en cada entrada.
16. Un `E3001` dentro de dos bucles anidados lleva las dos notas de vuelta, de dentro afuera.
17. `return` dentro de un bucle termina la función y se comprueban sus `ensures`.
18. `while true { decreases 1 }` se detiene con `E4006` en la segunda vuelta; `nex test` con un
    ejemplo así termina con el ejemplo en `error` y sigue con los demás.

**Herramientas y documentación**

19. `nex inspect`, `nex symbols` y `nex context` (sección 11), validados con sus esquemas.
20. Las pruebas de documentación ejecutan los ejemplos nuevos.
