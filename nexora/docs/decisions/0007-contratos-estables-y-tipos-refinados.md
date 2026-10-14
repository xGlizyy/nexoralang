# 0007 — Contratos estables, explicación de las reglas y tipos refinados

- **Estado:** aceptada
- **Versión:** 0.3.0
- **Sustituye a:** la parte provisional de [0004](0004-contratos-en-ejecucion.md) (posición de las
  cláusulas y nombre `result`), que pasa de experimental a estable.

## Contexto

La [decisión 0006](0006-requisitos-verificables.md) hace de los requisitos verificables la
característica principal de NEXORA y fija un orden de trabajo. Esta decisión cubre sus pasos 1, 2 y
5: estabilizar los contratos, unir una explicación a cada regla y añadir tipos refinados.

Hasta la 0.2 los contratos eran experimentales: su posición en el código y el nombre `result`
podían cambiar. Una característica que se presenta como principal no puede estar en esa situación.
Además, una regla sin explicación obliga a quien la incumple a deducir por qué existe, y los
contratos solo describen funciones: no había forma de decir que un valor, esté donde esté, cumple
una regla.

## Decisión

### 1. Los contratos son estables

1. **Las cláusulas van al principio del cuerpo**, como en la 0.2. No se mueven a la firma.
2. **El valor devuelto se llama `result`** dentro de `ensures`. Es un nombre contextual, no una
   palabra clave: fuera de `ensures` es un nombre corriente. Un parámetro no puede llamarse
   `result` (`E2013`).
3. Lo demás queda como en [0004](0004-contratos-en-ejecucion.md): `requires` solo ve los
   parámetros, `ensures` ve además `result`, y la verdad de las condiciones se comprueba al
   ejecutar (`E4001` señala la llamada; `E4002`, la cláusula).

### 2. Cada regla puede llevar su explicación

```text
requires amount <= balance, "An account cannot go below zero"
type Percent = Int where value >= 0 and value <= 100, "A percentage goes from 0 to 100"
```

- Detrás de la condición, tras una coma, un único texto literal no vacío.
- No cambia lo que se comprueba. Aparece en el diagnóstico como `Reason: ...` cuando la regla se
  incumple, y las herramientas la reciben como dato (`message` en `nex inspect` y en
  `nex context`).
- Es opcional: obligarla llenaría el código de textos que repiten la condición.

### 3. Tipos refinados

```text
type Percent = Int where value >= 0 and value <= 100
```

1. **Un tipo refinado es una base y una condición sobre `value`.** La base es un tipo integrado u
   otro tipo refinado.
2. **La garantía: todo valor de un tipo refinado cumple su condición.** Para que se mantenga sin
   comprobar nada en cada uso, un valor solo puede entrar en el tipo por dos puertas:
   - **Una constante**, que `nex check` comprueba sin ejecutar (`E2017`).
   - **La comprobación explícita `Percent(x)`**, que se hace al ejecutar y detiene el programa si
     el valor no cumple la condición (`E4003`, categoría `contract`, código de salida 5).
3. **Ensanchar es libre; estrechar se escribe.** Un `Percent` se usa donde se espera un `Int`. Un
   `Int` que no es una constante no se acepta donde se espera un `Percent` (`E2011`); el mensaje
   indica que se compruebe con `Percent(...)`.
4. **Las operaciones devuelven la base.** `p + 1` es un `Int`: el resultado puede salirse del rango.
5. **La condición solo habla del valor.** Puede usar `value`, literales, operadores y las
   conversiones integradas. No puede llamar a funciones del programa ni comprobar otros tipos
   refinados (`E2018`).
6. **Se pueden encadenar.** `type Pass = Percent where value >= 50` exige las dos condiciones, y se
   comprueban desde la base.
7. Los nombres de tipo empiezan por mayúscula (`E2016`) y no pueden usarse para nada más (`E2006`).

## Motivos

- **Por qué `result` y no otra forma.** Se consideraron tres alternativas:

  | Alternativa | Por qué no |
  |-------------|------------|
  | Nombrar el resultado en la firma (`-> total: Int`) | Añade una segunda forma de escribir el tipo de retorno, y el nombre solo sirve en `ensures` |
  | Una palabra clave nueva (`return` como valor, `out`) | `return` ya significa "salir"; dar dos significados a una palabra va contra la regla de una sola forma |
  | Mantener `result` | Es lo que ya funcionaba, se lee sin explicación y no rompe ningún programa |

  Se mantiene `result`, y se declara estable.

- **Por qué las cláusulas siguen en el cuerpo.** Moverlas a la firma (como en el borrador) obligaría
  a reglas de continuación de línea entre la firma y la llave, y rompería todos los programas con
  contratos para ganar solo una diferencia visual.
- **Por qué una coma y un texto para la explicación.** Es la forma más corta que no necesita una
  palabra nueva, y se parece a las aserciones con mensaje de otros lenguajes. Un texto literal, y no
  una expresión, para que una herramienta pueda leerlo sin ejecutar nada.
- **Por qué dos puertas de entrada y no una comprobación en cada asignación.** Si un `Int` se
  aceptara donde se espera un `Percent` y se comprobara en silencio al pasarlo, cualquier línea
  podría detener el programa sin que el código lo dijera. Con `Percent(x)` cada punto donde una
  regla puede detener el programa está escrito y puede buscarse. Es la misma idea que las
  conversiones explícitas de [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md).
- **Por qué las constantes se aceptan sin `Percent(...)`.** Su valor se conoce sin ejecutar, así que
  la comprobación la hace `nex check` y el error aparece antes de ejecutar. Escribir `Percent(20)`
  no añadiría información.
- **Por qué la condición no puede llamar a funciones.** Una función podría recibir un valor del
  propio tipo y crear una comprobación circular, o depender de algo más que el valor. Mantenerla
  como una expresión sobre `value` la hace evaluable por `nex check` para las constantes y la hace
  legible como dato. Las reglas que dependen de otros valores se escriben con `requires`.
- **Por qué `Percent(x)` detiene el programa en vez de devolver un error.** No existe `Result` en
  el lenguaje. Cuando exista, podrá añadirse una forma que devuelva el error como valor sin cambiar
  esta.

## Lo que no garantiza

- `nex check` no razona sobre valores calculados: un `Percent(n + 2)` puede pasar la comprobación
  y fallar al ejecutarse (`E4003`). Solo las constantes se comprueban sin ejecutar.
- No demuestra que una función con `-> Percent` nunca falle; garantiza que, si devuelve, lo que
  devuelve cumple la condición.
- Los contratos siguen comprobándose solo en las llamadas que se ejecutan.

## Alternativas descartadas

- **Alias sin condición (`type UserId = Int`).** No aportan ninguna regla comprobable y serían una
  segunda forma de nombrar el mismo tipo. Se rechazan con un mensaje que lo explica (`E1101`).
- **Comprobación implícita al asignar.** Descartada por lo explicado en los motivos.
- **Tipos refinados de solo lectura sin herencia (sin cadenas).** Encadenar permite reutilizar una
  regla (`Pass` sobre `Percent`) sin copiarla; el coste de implementarlo es pequeño.

## Cambios incompatibles

- `type` y `where` pasan de palabras reservadas a palabras clave. Ningún programa válido de la 0.2
  podía usarlas como nombres, así que ninguno deja de funcionar.
- `nex inspect` cambia a `nexora.inspect/2`: el campo `type` de una expresión puede ser el nombre
  de un tipo refinado, `Program` tiene el campo `types` y `Contract` tiene `message`.
- Ningún programa válido de la 0.2 cambia de comportamiento.
