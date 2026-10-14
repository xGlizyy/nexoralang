# 0008 — Ejemplos en las funciones (`example`) y el comando `nex test`

- **Estado:** aceptada
- **Versión:** 0.4.0 (prevista)

## Contexto

La [decisión 0006](0006-requisitos-verificables.md) hace de los requisitos verificables la
característica principal de NEXORA. La 0.3 cubre dos clases de requisito: lo que un valor admite
(tipos refinados) y la relación entre la entrada y la salida de una función (contratos). Falta la
tercera: **qué resultado concreto debe dar una función con unas entradas concretas**.

Los contratos, además, solo se comprueban en las llamadas que se ejecutan: una función que ningún
`main` llama no se comprueba nunca. Y hoy, para saber si una edición rompió algo, hay que escribir
un `main` que ejerza el código y leer lo que imprime.

Este es el paso 3 de la línea principal de la [hoja de ruta](../roadmap.md#línea-principal-requisitos-verificables).

Términos que usa esta decisión:

- **Ejemplo:** una cláusula `example` de una función.
- **Función del ejemplo:** la función en cuyo cuerpo está escrita la cláusula.
- **Llamada propia:** un nodo de llamada, dentro de la expresión del ejemplo, a la función del
  ejemplo (sección 1.4).
- **Evaluar un ejemplo:** calcular su expresión ejecutando las funciones a las que llama. Solo lo
  hace `nex test`.

## Decisión

### 1. La cláusula `example`

```text
fn apply_discount(price: Cents, percent: Percent) -> Cents {
    requires percent < 100, "A full discount would make it free"
    ensures result <= price, "A discount never raises the price"

    example apply_discount(10000, 20) == 8000, "Twenty percent off"
    example apply_discount(999, 0) == 999

    return Cents(price * (100 - percent) / 100)
}
```

#### 1.1 Posición

`example` es una cláusula del principio del cuerpo, como `requires` y `ensures`: va antes de la
primera sentencia, y las tres pueden mezclarse en cualquier orden. Puede haber cualquier número de
ejemplos en una función. Una cláusula `example` después de una sentencia es el error existente
`E1106` (*Misplaced contract clause*), cuyo mensaje ya nombra la palabra concreta:
`'example' must come at the start of a function body, before any other statement`.

#### 1.2 Forma y gramática

```ebnf
contract = ( "requires" | "ensures" | "example" ) expression [ explanation ] end ;
```

La explicación sigue exactamente las reglas de la 0.3.1 para `requires`, `ensures` y `where`: un
único texto literal, no vacío, de una sola línea. Lo contrario es `E1101`.

`example` pasa de palabra reservada a palabra clave.

#### 1.3 Tipo y nombres visibles

- La expresión es de tipo `Bool`. Si no lo es, el análisis estático da `E2011` con el mensaje
  `The condition of 'example' must be Bool, found Int`, el mismo formato que `requires` y `ensures`.
- Un ejemplo no ocurre dentro de una llamada: **no ve los parámetros de su función ni `result`**.
  Usar cualquiera de ellos es `E2005` (*Unknown variable*), con la sugerencia
  `An example has no parameters: write its inputs as values, for example: double(2)`.
- Puede usar literales, operadores, las funciones integradas, **cualquier función del programa** y
  comprobaciones de tipos refinados (`Percent(x)`).
- Los argumentos constantes se comprueban contra los tipos refinados sin ejecutar, como cualquier
  constante (`E2017`), y cuentan para el límite de trabajo del análisis (`E2019`).
- Consecuencia: una función `Void` no puede tener ejemplos válidos, porque una llamada a ella no
  produce ningún valor que pueda formar parte de una expresión `Bool` (`E2011`).

#### 1.4 La llamada propia

Una **llamada propia** es un nodo `Call` que está en el árbol de sintaxis de la expresión del ejemplo
(en cualquier posición: como operando, como argumento de otra llamada, dentro de paréntesis) y cuyo
nombre es el de la función del ejemplo.

- NEXORA no tiene sobrecarga: dos funciones no pueden llamarse igual (`E2002`), y el nombre de una
  función no puede ser el de un tipo (`E2006`). Por eso el nombre identifica la función sin ninguna
  regla adicional de resolución.
- Basta **una**. Puede haber varias, y pueden estar anidadas.
- Una llamada que ocurre al ejecutar otra función **no cuenta**: se mira el texto del ejemplo, no su
  ejecución, porque el análisis no ejecuta nada (sección 2).
- Una llamada propia con errores (número de argumentos, tipos) cuenta como llamada propia: su error
  es el suyo (`E2009`, `E2011`), no `E2020`.

| Expresión en un ejemplo de `f` | ¿Tiene llamada propia? |
|--------------------------------|------------------------|
| `f(2) == 4` | Sí |
| `f(f(2)) == 16` | Sí, dos |
| `f(1) + f(2) == 6` | Sí, dos |
| `to_float(f(2)) > 3.5` | Sí |
| `g(f(2)) == 1` | Sí: `f(2)` está en el árbol del ejemplo |
| `g(2) == 4`, aunque `g` llame a `f` | No |
| `2 + 2 == 4` | No |

Sin ninguna llamada propia: **`E2020`** (*Example without its function*, categoría `semantic`).
Señala la expresión completa del ejemplo; mensaje `This example of 'f' never calls 'f'`; sugerencia
`Write the call with its inputs, for example: example f(2) == 4`. Si la expresión, además, no es
`Bool`, se informan los dos errores: son dos problemas distintos.

### 2. Analizar no es ejecutar

| Herramienta | Qué hace con los ejemplos |
|-------------|---------------------------|
| `nex check`, `nex inspect`, `nex context`, `nex symbols` y el servidor MCP | Aplican las reglas de la sección 1. **No evalúan ningún ejemplo ni llaman a ninguna función** |
| `nex run` | Nada. Ejecuta `main` como siempre |
| `nex test` y `nexora.api.test_source` | Los evalúan |

La 0.3.1 dejó escrito que el análisis no ejecuta el programa; lo único que evalúa son las
condiciones de los tipos refinados sobre constantes, que no llaman a funciones del programa. Esta
decisión no cambia esa frontera.

**Grafo de llamadas.** Las llamadas que hay en un ejemplo **no son aristas** del grafo de llamadas de
su función. Un ejemplo de `f` que llama a `f` no hace a `f` recursiva, y un ejemplo de `f` que llama
a `g` no hace que `f` "llame" a `g`. En `nex context`, `calls`, `called_by` y `recursive` no cambian.
Sí son **referencias** a la función llamada en `nex symbols`: el nombre se usa ahí.

### 3. Evaluación de los ejemplos

#### 3.1 Estados

| Estado | Definición | Diagnóstico |
|--------|------------|-------------|
| `passed` | La evaluación termina sin error de ejecución ni regla incumplida, y la expresión vale `true` | Ninguno |
| `failed` | La evaluación termina sin error de ejecución ni regla incumplida, y la expresión vale `false` | `E4004` |
| `error` | La evaluación se detiene por un error de ejecución (`E3001`–`E3006`) o por una regla incumplida (`E4001`–`E4003`) | El original, con su código, más una nota |

Son excluyentes, y un `error` **nunca** se convierte en `failed`.

**`E4004`** (*Example failed*, categoría nueva **`test`**): señala la expresión del ejemplo, con el
mensaje `This example of 'f' is false`. Las notas son, en este orden: una por cada llamada propia que
devolvió un valor (`f(2) returned 5`), en el orden en que se invocaron (sección 6.3), y, si existe,
la explicación (`Reason: ...`).

**Nota de un `error`:** al diagnóstico original se le añade, como última nota,
`While evaluating example 2 of 'f', at line 14.` El resto del diagnóstico (código, posición,
mensaje, cadena de llamadas) no cambia.

#### 3.2 Qué se comprueba

Exactamente lo mismo que en `nex run`, a cualquier profundidad: los `requires` y `ensures` de toda
función que se llame durante el ejemplo (la del ejemplo y las demás, aunque `--function` no las
seleccione), las comprobaciones `Tipo(x)`, la división por cero, los desbordamientos, el límite de
1000 llamadas anidadas. Una violación de `requires` en una llamada anidada (el ejemplo de `f` llama a
`g`, y `g` incumple el `requires` de `h`) es un `error` con el `E4001` que señala la llamada a `h` y
la cadena de llamadas de siempre.

#### 3.3 Aislamiento real

Cada ejemplo se evalúa con **un intérprete nuevo**, en el orden del archivo (funciones en el orden
en que se declaran; dentro de cada una, ejemplos en el orden en que se escriben). Lo que eso
garantiza, con la arquitectura actual:

- **Pila y variables propias.** El intérprete guarda la cadena de llamadas en curso y no la vacía
  tras un error; uno nuevo por ejemplo evita que un fallo la contamine. Las variables viven en
  entornos que se crean en cada llamada.
- **Nada más que compartir.** Un programa NEXORA no tiene variables globales, no puede leer ni
  escribir archivos, red ni entrada, y su único efecto es `print`, que se recoge por separado para
  cada ejemplo. Por eso un ejemplo no puede influir en otro.

Lo que **no** garantiza: todos los ejemplos se evalúan en el mismo proceso, uno tras otro. No hay
límite de tiempo ni de memoria por ejemplo, ni ningún aislamiento del sistema operativo. Un cálculo
muy largo retrasa los siguientes; una recursividad sin fin se detiene en el límite de llamadas
(`E3004`) y queda en `error`.

#### 3.4 Continuar o detenerse

Tras un `failed` o un `error` se evalúa el ejemplo siguiente. Lo que ocurre al evaluar un ejemplo se
clasifica así. **La regla general es que el código `70` corresponde a un fallo de NEXORA, con una
única excepción heredada, `MemoryError`**, descrita en la tabla y en la sección "Cuestiones
pendientes":

| Lo que ocurre | Origen | Resultado |
|---------------|--------|-----------|
| Un diagnóstico de ejecución o de regla (`NexoraRuntimeError`: `E3001`–`E3006`, `E4001`–`E4003`) | El programa | Ejemplo en `error`; se sigue con el siguiente |
| El programa agota la pila de Python antes del límite de 1000 llamadas (recursividad dentro de expresiones muy anidadas) | El programa | Se convierte en `E3004`, exactamente como hace hoy `Interpreter.run` con `RecursionError`. Ejemplo en `error`; se sigue |
| `MemoryError` | El programa | **Excepción a la regla general.** `nex test` hereda el comportamiento actual de `nex run`, que no captura `MemoryError` y lo deja llegar al manejador de errores internos: se detiene, sin informe, con `70`. No es un fallo de NEXORA, pero en la 0.4.0 se informa igual que uno. Ver "Cuestiones pendientes" |
| Ctrl+C (`KeyboardInterrupt`) | Quien usa el comando | Se detiene, sin informe, con `130`, como los demás comandos |
| Cualquier otra excepción de Python | **NEXORA** (un defecto) | Se detiene, sin informe, con `70` y el mismo mensaje de error interno que los demás comandos |

El informe solo se escribe cuando han terminado **todos** los ejemplos. Por eso, cuando `nex test` se
detiene, no queda ningún informe parcial que pueda tomarse por completo, ni en texto ni en JSON.

### 4. El comando `nex test`

```text
nex test <archivo> [--format text|json] [--function FUNCION]
```

1. **Análisis estático.** El mismo de `nex check`, con una única diferencia: no exige `main`
   (`E2001`). Si hay `main`, sus reglas se comprueban igual (`E2004`, `E2013`), pero **no se
   ejecuta**.
2. **Con errores estáticos no se evalúa nada:** estado `not_run`, código `1`.
3. **Sin errores**, se evalúan los ejemplos seleccionados: todos, o los de la función de
   `--function`.
4. **`--function NOMBRE`** selecciona los ejemplos **declarados en** esa función. Las funciones a las
   que esos ejemplos llaman se ejecutan y se comprueban como siempre (sección 3.2).
   - Los errores estáticos se informan primero: con errores no se sabe con seguridad qué funciones
     existen.
   - Si la función no existe, es un error de uso: `error: <archivo> has no function named 'NOMBRE'`
     en la salida de error (con `Did you mean 'X'?` si hay un nombre parecido), código `2`, sin
     evaluar nada y sin documento, ni siquiera con `--format json`, igual que cualquier otro error
     de uso.
   - Si la función existe y no tiene ejemplos: estado `no_examples`.
   - Diferencia deliberada con `nex symbols --function`, que con un nombre inexistente devuelve una
     lista vacía: `nex symbols` **describe**, y "no hay símbolos con ese nombre" es una respuesta
     correcta; `nex test` **verifica**, y "no se probó nada porque el nombre estaba mal" no puede
     parecer un resultado.
5. **Salida:** nada se escribe en la salida estándar hasta que han terminado todos los ejemplos
   (sección 3.4). En texto, el resumen va a la salida estándar y los diagnósticos a la de error,
   como en `nex run`. En JSON, un único documento en la salida estándar.
6. No hay más filtros, ni ejecución en paralelo, ni botón "Test" en el playground en la 0.4.0.

#### 4.1 Estado global

| Estado | Definición | Código de salida |
|--------|------------|------------------|
| `passed` | Se evaluó **al menos un** ejemplo y **todos** terminaron en `passed` | `0` |
| `failed` | Se evaluó al menos un ejemplo y **alguno** terminó en `failed` o `error` | `6` |
| `no_examples` | El análisis no tiene errores, pero no había ningún ejemplo seleccionado | `6` |
| `not_run` | No se evaluó nada porque el análisis estático encontró errores, o porque el archivo no pudo leerse | `1`, o `4` si el archivo no pudo leerse |

`no_examples` **no es un éxito**: un `0` significa "probado y correcto", y ahí no se ha probado
nada.

#### 4.2 Códigos de salida

Comprobados contra `nexora/src/nexora/cli.py` (0, 1, 2, 3, 4, 5, 70 y 130 existen; 6 está libre).
Se conservan todos y se añade uno:

| Código | En `nex test` |
|--------|---------------|
| `0` | Estado `passed` |
| `1` | Estado `not_run` por errores estáticos |
| `2` | Uso incorrecto, incluida una función inexistente en `--function` |
| `4` | Estado `not_run` porque el archivo no pudo leerse, con el `E0001`/`E0002` en `diagnostics` (la misma convención que `nex inspect`, `nex context` y `nex symbols`) |
| **`6`** | **Nuevo.** Estado `failed` o `no_examples`: la prueba no se superó |
| `70` | Error interno de NEXORA, o el programa agotó la memoria (`MemoryError`, excepción heredada de `nex run`; sección 3.4); sin informe |
| `130` | Interrumpido con Ctrl+C; sin informe |

`nex test` **no devuelve `3` ni `5`**: un error de ejecución o una regla incumplida durante un ejemplo
es un ejemplo en `error`, con su diagnóstico original, y el código global es `6`. `nex run` sigue
devolviendo `3` y `5` como hasta ahora.

### 5. Formato de texto

```text
prices.nex: 5 examples in 3 functions
  apply_discount   2 passed
  as_percent       1 passed, 1 failed
  total            1 error

test error[E4004]: Example failed
  --> prices.nex:14:13
   |
14 |     example as_percent(1, 3) == 34, "Thirds round up"
   |             ^^^^^^^^^^^^^^^^^^^^^^ This example of 'as_percent' is false
   = note: as_percent(1, 3) returned 33
   = note: Reason: Thirds round up

runtime error[E3001]: Division by zero
  ...
   = note: While evaluating example 1 of 'total', at line 22.

error: prices.nex: 2 of 5 examples did not pass (1 failed, 1 error)
```

- Sin ejemplos: `prices.nex: no examples to run`, y en la salida de error
  `error: prices.nex: nothing was tested`.
- Con `--function`: el resumen dice `examples of 'as_percent'`.
- Los valores de las llamadas propias se muestran en las notas de `E4004`. Lo que imprimió un
  ejemplo se muestra solo si no pasó.
- Lo que no cambia es **qué** se informa; la redacción exacta se fija al implementar y queda cubierta
  por las pruebas.

### 6. Formato JSON: `nexora.test/1`

#### 6.1 Documento

Sigue las convenciones de [Protocolo JSON](../json-protocol.md): la cabecera común, objetos que
pueden ganar campos sin cambiar de versión, campos que siempre aparecen (un valor ausente es `null`,
nunca se omite el campo), salida determinista y un JSON Schema generado desde el código
(`docs/schemas/nexora-test.schema.json`).

| Campo | Tipo | Significado |
|-------|------|-------------|
| `schema` | `"nexora.test/1"` | |
| `nexora_version` | texto | |
| `file` | texto | Como en los demás formatos |
| `ok` | booleano | Como en los demás formatos: **el análisis estático no encontró errores**. No dice nada de los ejemplos |
| `diagnostics` | lista | Los diagnósticos **estáticos** (o el de archivo ilegible). Vacía si `ok` |
| `status` | texto | Estado global (sección 4.1): `passed`, `failed`, `no_examples` o `not_run` |
| `filter` | objeto | `{"function": texto o null}`, como el `filter` de `nexora.symbols/1` |
| `summary` | objeto o `null` | `{"total", "passed", "failed", "error"}`, contando los ejemplos seleccionados. `null` si `not_run` |
| `examples` | lista o `null` | Un resultado por ejemplo seleccionado, en el orden de evaluación. `[]` si `no_examples`; `null` si `not_run` |

**`ok` frente a `status`:** `ok: true` significa que el programa supera el análisis estático;
`status: "passed"` significa que, además, se evaluó al menos un ejemplo y todos pasaron. Un documento
con `ok: true` puede tener `status` `failed` o `no_examples`. `status: "passed"` implica `ok: true`.

#### 6.2 Resultado de un ejemplo

| Campo | Tipo | Significado |
|-------|------|-------------|
| `function` | texto | La función del ejemplo |
| `index` | entero ≥ 1 | Su posición entre los ejemplos de esa función, en el orden del texto. Con `function`, identifica el ejemplo de forma estable mientras no se reordenen los ejemplos de esa función |
| `span` | posición | La expresión del ejemplo (sin la palabra `example` ni la explicación) |
| `expression` | texto | La expresión tal como está escrita |
| `message` | texto o `null` | La explicación |
| `status` | texto | `passed`, `failed` o `error` |
| `values` | lista | Las llamadas propias que se invocaron, en el orden en que se invocaron (sección 6.3) |
| `not_evaluated` | lista | Las llamadas propias que no llegaron a invocarse, en el orden del texto (sección 6.3) |
| `diagnostic` | objeto o `null` | `null` si `passed`; el `E4004` si `failed`; el diagnóstico original, con la nota del ejemplo, si `error`. Mismo formato que en `nexora.diagnostics/1` |
| `output` | texto | Lo que se imprimió durante el ejemplo; `""` si nada |

#### 6.3 Llamadas propias: `values` y `not_evaluated`

Cada llamada propia de la expresión (sección 1.4) aparece **exactamente una vez**, en una de las dos
listas. Una expresión no tiene bucles, así que cada nodo de llamada se invoca como mucho una vez.
Las llamadas a la función que ocurren dentro del cuerpo de otras funciones, o dentro de la propia
función al recursar, no son llamadas propias y no aparecen.

**Invocar** una llamada es entrar en la función, después de haber evaluado todos sus argumentos y
antes de comprobar sus `requires`. Es el momento que fija el orden.

**`values`: las llamadas que se invocaron, en el orden real de invocación.** El intérprete evalúa los
argumentos de una llamada antes de invocarla, y los operandos de izquierda a derecha. Por eso:

| Expresión | Orden en `values` |
|-----------|-------------------|
| `f(f(2)) == 16` | `f(2)`, después `f(f(2))`: la interior se invoca y termina antes de que la exterior empiece |
| `f(1) + f(2) == 6` | `f(1)`, después `f(2)` |
| `g(f(2)) == 1` | `f(2)` (la llamada a `g` no es una llamada propia) |

| Campo | Tipo | Significado |
|-------|------|-------------|
| `call` | texto | La llamada tal como está escrita |
| `span` | posición | Su posición |
| `type` | texto | Su tipo según el análisis estático: el tipo de retorno de la función |
| `status` | texto | `returned`: devolvió un valor. `stopped`: se invocó, pero no devolvió nada porque la evaluación se detuvo dentro de ella (su `requires`, su cuerpo, una función a la que llamó o su `ensures`) |
| `value` | texto o `null` | Si `returned`, el valor escrito como en el código (`"33"`, `"2.5"`, `"true"`, `"\"text\""`). Si `stopped`, `null` |

Como una evaluación se detiene en el primer error, **como mucho una** entrada de `values` es
`stopped`, y es la última de la lista. El ejemplo, en ese caso, está en `error`.

**`not_evaluated`: las llamadas que no llegaron a invocarse**, es decir, que no llegaron a ejecutarse
en absoluto, **en el orden del texto** (por la columna en la que empiezan). Una llamada que sí se
invocó nunca está aquí, aunque no devolviera nada: esa está en `values` como `stopped`.

| Campo | Tipo | Significado |
|-------|------|-------------|
| `call` | texto | La llamada tal como está escrita |
| `span` | posición | Su posición |
| `type` | texto | Su tipo según el análisis estático |
| `reason` | texto | `short_circuit`: está en un operando que un `and` o un `or` no necesitó evaluar. `stopped_before`: la evaluación se detuvo por un error antes de llegar a invocarla (en otra llamada, en uno de sus argumentos o en un operando anterior) |

El motivo se determina de forma mecánica: al evaluar, cada operando que `and` u `or` se saltan marca
como `short_circuit` las llamadas propias que contiene; al terminar, las llamadas que no se invocaron
ni se marcaron son `stopped_before`, lo que solo puede ocurrir en un ejemplo en `error`.

**Tres casos distintos, sin ambigüedad:**

| Situación | Dónde aparece |
|-----------|---------------|
| Se invocó y devolvió un valor | `values`, `status: "returned"`, `value` con el valor |
| Se invocó y no devolvió nada | `values`, `status: "stopped"`, `value: null` |
| No se invocó | `not_evaluated`, con `reason` |

NEXORA no tiene ningún valor nulo: sus valores son `Int`, `Float`, `Bool` y `Text`, y una llamada a una
función `Void` no puede formar parte de un ejemplo (sección 1.3). Por eso un valor del lenguaje nunca
se escribe como `null`, y `value: null` solo aparece en una llamada `stopped`. Las dos listas pueden
estar vacías por separado, pero no a la vez: todo ejemplo tiene al menos una llamada propia.

#### 6.4 Documentos de ejemplo

Cinco documentos completos y válidos según el esquema. Cada uno corresponde a una versión del archivo
`double.nex`; los números de línea forman parte del ejemplo.

**1. Todos aprobados** — código `0`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(double(1)) == 4
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "passed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 2, "failed": 0, "error": 0},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 35},
      "expression": "double(double(1)) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(1)", "span": {"line": 4, "column": 20, "end_line": 4, "end_column": 29},
         "type": "Int", "status": "returned", "value": "2"},
        {"call": "double(double(1))", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 30},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    }
  ]
}
```

**2. Un ejemplo `failed`** — código `6`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(3) == 7, "Three doubled is seven"
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "failed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 1, "failed": 1, "error": 0},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 27},
      "expression": "double(3) == 7",
      "message": "Three doubled is seven",
      "status": "failed",
      "values": [
        {"call": "double(3)", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 22},
         "type": "Int", "status": "returned", "value": "6"}
      ],
      "not_evaluated": [],
      "diagnostic": {
        "severity": "error", "category": "test", "code": "E4004", "message": "Example failed",
        "label": "This example of 'double' is false", "hint": null,
        "notes": ["double(3) returned 6", "Reason: Three doubled is seven"],
        "file": "double.nex", "line": 4, "column": 13, "end_line": 4, "end_column": 27
      },
      "output": ""
    }
  ]
}
```

**3. Un ejemplo `error` por violación de contrato** — código `6`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example double(2) == 4
4      example double(-1) == -2
5      return n * 2
6  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "failed",
  "filter": {"function": null},
  "summary": {"total": 2, "passed": 1, "failed": 0, "error": 1},
  "examples": [
    {
      "function": "double",
      "index": 1,
      "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 27},
      "expression": "double(2) == 4",
      "message": null,
      "status": "passed",
      "values": [
        {"call": "double(2)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
         "type": "Int", "status": "returned", "value": "4"}
      ],
      "not_evaluated": [],
      "diagnostic": null,
      "output": ""
    },
    {
      "function": "double",
      "index": 2,
      "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 29},
      "expression": "double(-1) == -2",
      "message": null,
      "status": "error",
      "values": [
        {"call": "double(-1)", "span": {"line": 4, "column": 13, "end_line": 4, "end_column": 23},
         "type": "Int", "status": "stopped", "value": null}
      ],
      "not_evaluated": [],
      "diagnostic": {
        "severity": "error", "category": "contract", "code": "E4001", "message": "Precondition violated",
        "label": "This call breaks a 'requires' condition of 'double'", "hint": null,
        "notes": [
          "The condition at line 2 is false: requires n >= 0",
          "Reason: Only natural numbers",
          "It was called with: n = -1",
          "While evaluating example 2 of 'double', at line 4."
        ],
        "file": "double.nex", "line": 4, "column": 13, "end_line": 4, "end_column": 23
      },
      "output": ""
    }
  ]
}
```

La llamada `double(-1)` figura como `stopped`: empezó, pero su `requires` la detuvo antes de
devolver nada.

**4. Ningún ejemplo seleccionado** — código `6`.

```text
1  fn double(n: Int) -> Int {
2      return n * 2
3  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": true,
  "diagnostics": [],
  "status": "no_examples",
  "filter": {"function": null},
  "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0},
  "examples": []
}
```

**5. Análisis estático fallido** — código `1`.

```text
1  fn double(n: Int) -> Int {
2      requires n >= 0, "Only natural numbers"
3      example 2 + 2 == 4
4      return n * 2
5  }
```

```json
{
  "schema": "nexora.test/1",
  "nexora_version": "0.4.0",
  "file": "double.nex",
  "ok": false,
  "diagnostics": [
    {
      "severity": "error", "category": "semantic", "code": "E2020", "message": "Example without its function",
      "label": "This example of 'double' never calls 'double'",
      "hint": "Write the call with its inputs, for example: example double(2) == 4",
      "notes": [],
      "file": "double.nex", "line": 3, "column": 13, "end_line": 3, "end_column": 23
    }
  ],
  "status": "not_run",
  "filter": {"function": null},
  "summary": null,
  "examples": null
}
```

En el documento 1, `double(1)` figura antes que `double(double(1))`: se invocó primero (sección 6.3).
Ninguno de los cinco tiene `main`: `nex test` no lo exige (sección 4).

**Fragmentos: llamadas no invocadas.** No son documentos completos, sino el resultado de un ejemplo
dentro de `examples`, para ver los dos motivos de `not_evaluated`. En una versión de `double.nex` con
el ejemplo `double(1) == 3 and double(2) == 4` en la línea 3 (`failed`, porque `double(1)` vale `2`):

```json
{
  "function": "double",
  "index": 1,
  "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 46},
  "expression": "double(1) == 3 and double(2) == 4",
  "message": null,
  "status": "failed",
  "values": [
    {"call": "double(1)", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 22},
     "type": "Int", "status": "returned", "value": "2"}
  ],
  "not_evaluated": [
    {"call": "double(2)", "span": {"line": 3, "column": 32, "end_line": 3, "end_column": 41},
     "type": "Int", "reason": "short_circuit"}
  ],
  "diagnostic": {
    "severity": "error", "category": "test", "code": "E4004", "message": "Example failed",
    "label": "This example of 'double' is false", "hint": null,
    "notes": ["double(1) returned 2"],
    "file": "double.nex", "line": 3, "column": 13, "end_line": 3, "end_column": 46
  },
  "output": ""
}
```

Y con el ejemplo `double(double(-1)) == 4` en la línea 3 (`error`: la llamada interior incumple el
`requires`, y la exterior no llega a invocarse):

```json
{
  "function": "double",
  "index": 1,
  "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 36},
  "expression": "double(double(-1)) == 4",
  "message": null,
  "status": "error",
  "values": [
    {"call": "double(-1)", "span": {"line": 3, "column": 20, "end_line": 3, "end_column": 30},
     "type": "Int", "status": "stopped", "value": null}
  ],
  "not_evaluated": [
    {"call": "double(double(-1))", "span": {"line": 3, "column": 13, "end_line": 3, "end_column": 31},
     "type": "Int", "reason": "stopped_before"}
  ],
  "diagnostic": {
    "severity": "error", "category": "contract", "code": "E4001", "message": "Precondition violated",
    "label": "This call breaks a 'requires' condition of 'double'", "hint": null,
    "notes": [
      "The condition at line 2 is false: requires n >= 0",
      "Reason: Only natural numbers",
      "It was called with: n = -1",
      "While evaluating example 1 of 'double', at line 3."
    ],
    "file": "double.nex", "line": 3, "column": 20, "end_line": 3, "end_column": 30
  },
  "output": ""
}
```

### 7. API de Python

`nexora.tooling` promete en su documentación que **nada se ejecuta** ("Nothing is executed"), y el
servidor MCP se apoya en esa promesa. La evaluación va en **`nexora.api`**, el módulo que ya ejecuta
código en memoria con `run_source`, y sigue sus convenciones (código como texto, `filename` solo como
nombre, ningún archivo abierto, resultado como diccionario listo para `json.dumps`):

```text
nexora.api.test_source(source, filename="playground.nex", *, function=None) -> dict
```

- Devuelve **el mismo documento `nexora.test/1`** que `nex test --format json`.
- `function` hace lo mismo que `--function`. Si la función no existe (y el análisis no tiene
  errores), lanza `nexora.tooling.ToolingError("unknown_function", ...)`, el mismo patrón que
  `get_language_spec` usa para una sección inexistente (`"unknown_section"`).
- Un error interno no se convierte en documento: la excepción llega a quien llama, que decide.
- No acepta límites (`limits`) en la 0.4.0. `run_source` los tiene para el playground, que no tendrá
  botón "Test" en esta versión; se añadirán con él, con la misma clase `Limits`.
- `nexora.tooling` y el servidor MCP **no** ganan ninguna función de prueba.

### 8. Herramientas de análisis

- **`nex inspect`:** nodo nuevo `Example` con los campos `condition` (expresión) y `message` (texto o
  `null`), y campo nuevo `examples` (lista de `Example`) en `Function`, **al final**, después de `body`.
  El formato **sigue siendo `nexora.inspect/2`**, por el contrato escrito, no por comodidad:
  - [Esquema de `nex inspect`](../inspect-schema.md), "Estabilidad y evolución": *el número de
    versión no cambia cuando se añade un campo a un nodo o un tipo de nodo nuevo*, y *las
    herramientas deben ignorar los campos y los tipos de nodo que no conozcan*.
    [Protocolo JSON](../json-protocol.md) dice lo mismo, y los esquemas no prohíben campos
    adicionales.
  - El mismo documento exige que *el orden de los campos sea estable dentro de una versión*. Añadir
    `examples` **al final** de `Function` deja todos los campos existentes en el mismo orden.
  - Ningún campo existente cambia de tipo ni de significado: `Contract.clause` sigue siendo
    `requires` o `ensures`, y `type` en las expresiones sigue teniendo los valores de la 0.3. Lo
    nuevo solo aparece dentro del campo nuevo.
  - Contraste: la 0.3.0 sí pasó a `/2` porque cambió el significado de un campo existente (`type`
    dejó de ser una lista cerrada de cinco tipos). Aquí no ocurre nada parecido.
  - Consecuencia comprobable: un consumidor escrito para la 0.3.1 que siga la regla de ignorar lo que
    no conoce lee igual que antes cualquier programa, tenga ejemplos o no (caso 38 de la matriz).
- **`nex context`:** campo nuevo `examples` en cada función, al final (`condition`, `message`,
  `line`), y valor nuevo `examples` en `features`. El formato sigue siendo `nexora.context/1`.
- **`nex symbols`:** las llamadas de un ejemplo son referencias a las funciones llamadas.
- **Diagnósticos:** `E2020` (`semantic`), `E4004` (`test`) y la categoría nueva `test`. Añadir un
  código o una categoría no cambia la versión de `nexora.diagnostics/1` (Protocolo JSON). La API usa
  la categoría `contract` para elegir el estado `contract_violation` en `run_source`; `E4004` solo
  aparece en `nexora.test/1` y, con su propia categoría, no puede confundirse con un contrato.

## Motivos

- **Por qué en la función y no en un archivo de pruebas aparte.** El requisito queda junto al código
  que lo cumple: quien edita la función, persona o agente, lo tiene delante. Es la idea de los
  contratos.
- **Por qué una llamada en el árbol, y no "que la ejecución pase por la función".** Lo segundo solo
  se sabe ejecutando, y el análisis no ejecuta. Lo primero se comprueba mirando el árbol.
- **Por qué no se exige exactamente una llamada ni que esté en la raíz.** `f(f(2)) == 16` y
  `f(1) + f(2) == 6` son ejemplos naturales; exigir más no protege nada.
- **Por qué no ven los parámetros.** Un ejemplo es un caso cerrado. Si dependiera de los valores de
  una llamada, sería un `ensures`.
- **Por qué `failed` y `error` no se mezclan.** "La función devuelve otra cosa" y "la función no llegó
  a devolver nada" se corrigen de forma distinta.
- **Por qué la categoría `test`.** Un ejemplo falso no detuvo nada: el resultado no es el esperado.
  Con `contract`, quien filtra por categoría lo confundiría con un contrato incumplido.
- **Por qué `no_examples` termina con `6`.** Un `0` significa "probado y correcto".
- **Por qué el informe solo al final.** Es la única forma de que un error interno no deje medio
  informe que parezca completo.

## Lo que no garantiza

- Los ejemplos comprueban **los casos escritos**, no todos. Para reglas generales están los contratos
  y los tipos refinados.
- No hay límite de tiempo ni de memoria por ejemplo (sección 3.3).
- No hay pruebas fuera de las funciones (bloques `test` del borrador), ni comparación aproximada para
  `Float`: `==` es exacto.

## Alternativas descartadas

- **Bloques `test "nombre" { ... }`** (borrador de diseño). Necesitan sentencias y `assert`, y separan
  el caso de la función. Pueden añadirse después sin cambiar `example`.
- **Evaluar los ejemplos en `nex check`, o en `nex run` antes de `main`.** Romperían la frontera entre
  analizar y ejecutar.
- **Reutilizar el nodo `Contract` con `clause: "example"`.** Cambiaría el significado de un campo que
  las herramientas ya leen; un nodo nuevo es un añadido.
- **`test_source` en `nexora.tooling`.** Rompería la promesa de ese módulo (sección 7).

## Compatibilidad

- `example` pasa de palabra reservada a palabra clave. Ningún programa válido podía usarla como
  nombre.
- `nex run`, `nex check` y las herramientas de análisis no cambian con los programas sin ejemplos.
- Formatos: `nexora.test/1` es nuevo. `nexora.inspect/2` y `nexora.context/1` ganan campos al final de
  sus objetos. `nexora.diagnostics/1` gana una categoría y dos códigos. Ninguno cambia de versión.
- Códigos de salida: se añade `6`; ninguno existente cambia de significado.

## Condiciones para implementarlo

Lo que la implementación necesita y hoy no existe. No cambia ninguna decisión anterior:

1. **El análisis sin `main`.** `pipeline.analyze` y el comprobador necesitan una forma de omitir
   `E2001` que solo use `nex test`.
2. **Ejemplos fuera del grafo de llamadas.** Al comprobar un ejemplo, el comprobador debe registrar
   las referencias (para `nex symbols`) pero no las llamadas (`CheckedProgram.calls`).
3. **Evaluar una expresión sin llamada.** El intérprete solo sabe ejecutar `main`. Necesita evaluar
   una expresión con un entorno vacío, con el mismo ajuste del límite de recursividad de Python y
   la misma conversión de `RecursionError` en `E3004` que hace `Interpreter.run` (sección 3.4).
4. **Observar las llamadas propias.** Para `values` y `not_evaluated`, el intérprete tiene que poder
   anotar, para los nodos de llamada propia de la expresión, el momento de su invocación y su valor,
   y marcar como `short_circuit` las de un operando que `and` u `or` se saltan, sin cambiar cómo se
   evalúa nada.
5. **La salida por ejemplo.** Un recolector de `print` por ejemplo.

## Matriz de pruebas de diseño

Se escribirán antes que la implementación y deben fallar hasta que exista. "Unidad" son pruebas del
comprobador y del intérprete; "CLI" usa `nex test`; "API" usa `test_source`; "Docs" son ejemplos de
la documentación comprobados por `tests/test_docs.py`.

| # | Caso | Entrada (resumida) | Resultado esperado | Nivel |
|---|------|--------------------|--------------------|-------|
| 1 | Ejemplo válido | `example double(2) == 4` | `passed`; `values` con `"4"`; `status: passed`; código `0` | Unidad, CLI, Docs |
| 2 | Expresión falsa | `example double(2) == 5` | `failed`, `E4004` en la expresión, notas `double(2) returned 4`; código `6` | Unidad, CLI, Docs |
| 3 | Sin llamada propia | en `double`: `example 2 + 2 == 4` | `nex check`: `E2020` en la expresión completa. `nex test`: `not_run`, código `1` | Unidad, CLI |
| 4 | Llamada solo desde otra función | en `double`: `example quad(1) == 4`, y `quad` llama a `double` | `E2020` | Unidad |
| 5 | Varias llamadas propias | `double(double(1)) == 4`, `double(1) + double(2) == 6` | `passed`; `values` en orden de invocación: `double(1)` antes que `double(double(1))`; `double(1)` antes que `double(2)` | Unidad, API |
| 6 | Expresión no `Bool` | `example double(2)` | `E2011` `The condition of 'example' must be Bool, found Int`; no `E2020` | Unidad |
| 7 | No `Bool` y sin llamada propia | `example 2 + 2` | `E2011` y `E2020` | Unidad |
| 8 | Usa un parámetro o `result` | `example double(n) == 4`, `example result == 4` | `E2005` con la sugerencia propia | Unidad |
| 9 | Explicación | `example double(2) == 4, "Two doubled"` | `message` en `nex inspect`, `nex context` y el documento; `Reason:` en `E4004` si falla | Unidad, API |
| 10 | Explicación mal formada | vacía, solo espacios, con `\n`, o no textual | `E1101` | Unidad |
| 11 | Cláusula fuera de sitio | `example` después de una sentencia | `E1106` con `'example' must come at the start...` | Unidad |
| 12 | `requires` incumplido | `requires n >= 0` y `example double(-1) == -2` | `error`, `E4001` en la llamada, nota del ejemplo al final, `values` con `double(-1)` `stopped` y `value: null`; código `6` | Unidad, CLI, API |
| 13 | `ensures` incumplido | `ensures result > n` y `example double(0) == 0` | `error`, `E4002` en la cláusula, nota del ejemplo | Unidad, CLI |
| 14 | Contrato incumplido en llamada anidada | ejemplo de `f` → `g` → `h`, y `g` incumple el `requires` de `h` | `error`, `E4001` en la llamada a `h`, cadena de llamadas y nota del ejemplo de `f` | Unidad |
| 15 | Error de ejecución | ejemplo que llega a una división por cero en otra función | `error`, `E3001` en esa función, nota del ejemplo | Unidad, CLI |
| 16 | Tipo refinado incumplido | `example f(Percent(150 - 1)) == 1` | `error`, `E4003`, nota del ejemplo | Unidad |
| 17 | Constante fuera del tipo refinado | `example f(150) == 1` con parámetro `Percent` | `E2017` sin ejecutar; `not_run` | Unidad |
| 18 | Resultados distintos | tres ejemplos: `failed`, `passed`, `error` | los tres evaluados, en orden; `summary` `3/1/1/1`; `status: failed`; código `6` | Unidad, CLI, API |
| 19 | Aislamiento | un ejemplo provoca `E3004` por recursividad sin fin (se detiene en el límite de 1000 llamadas de NEXORA, que es determinista) y el siguiente es válido | el primero `error`, el segundo `passed`, con su pila limpia y su `output` propio | Unidad |
| 20 | Cortocircuito | `example double(1) == 3 and double(2) == 4` | `failed`; `double(1)` en `values`; `double(2)` en `not_evaluated` con `reason: short_circuit` | Unidad, API |
| 21 | Salida de `print` | la función imprime durante el ejemplo | `output` la contiene; en texto solo se muestra si no pasa | CLI, API |
| 22 | Filtro válido | `--function triple` con ejemplos en `double` y `triple`; `triple` llama a `double` | solo los de `triple`; el `requires` de `double` se sigue comprobando | CLI, API |
| 23 | Filtro inexistente | `--function nope` | mensaje de uso con sugerencia, código `2`, sin documento; en la API, `ToolingError("unknown_function")` | CLI, API |
| 24 | Función sin ejemplos | `--function helper`, que no tiene | `no_examples`, `examples: []`, código `6` | CLI |
| 25 | Archivo sin ejemplos | ninguna función los tiene | `no_examples`, texto `no examples to run`, código `6` | CLI, Docs |
| 26 | Errores estáticos | cualquier error del análisis | `not_run`, `summary` y `examples` `null`, código `1`; con `--function` inexistente, también `1` | CLI, API |
| 27 | Archivo ilegible | ruta inexistente | `not_run`, `E0001`, código `4` | CLI |
| 28 | Sin `main` | solo funciones con ejemplos | `nex test` los evalúa; `nex check` sigue informando `E2001` | CLI |
| 29 | `main` presente | un `main` que imprime | no se ejecuta: no aparece su salida | CLI |
| 30 | Esquema JSON | todos los documentos anteriores | cumplen `nexora-test.schema.json`; `ok`, `status`, `summary` y `examples` coherentes entre sí | API, CLI |
| 31 | Error interno | una excepción de Python simulada en el intérprete durante el segundo ejemplo | código `70`, mensaje de error interno, nada en la salida estándar (ni texto ni JSON) | CLI |
| 32 | Grafo de llamadas | ejemplo de `f` que llama a `f` y a `g` | `nex context`: `f` no es `recursive`, `calls` de `f` no incluye `g`; `nex symbols`: las dos son referencias | Unidad |
| 33 | El análisis no ejecuta | ejemplo que haría `E3001`, o que imprime | `nex check`, `nex inspect` y `nex context` terminan sin evaluarlo ni imprimir nada | CLI |
| 34 | `nex inspect` y `nex context` | función con dos ejemplos | `Example` con `condition` y `message`, `examples` al final de `Function`; `examples` en `context` y en `features` | Unidad |
| 35 | Llamada no invocada tras un error | `example double(double(-1)) == 4` | `error`; `double(-1)` en `values` como `stopped`; `double(double(-1))` en `not_evaluated` con `reason: stopped_before` | Unidad, API |
| 36 | `RecursionError` durante un ejemplo | dos ejemplos; durante el primero, la prueba hace que el intérprete lance `RecursionError` (sustituyendo una función interna, como ya hace `test_refined_types.py` con `broken_rule`) | el primero en `error` con `E3004`; el segundo evaluado y `passed`; código global `6`, **no** `70`. No depende del límite de recursividad de Python, de la profundidad real de la pila ni del tiempo | Unidad, CLI |
| 37 | Ctrl+C | interrupción durante un ejemplo | código `130`, sin informe | CLI |
| 38 | Compatibilidad de `nexora.inspect/2` | un programa con ejemplos | el documento valida contra el esquema de `nexora.inspect/2` de la 0.3.1 (sin los campos nuevos), y todos los campos anteriores conservan su orden | Unidad |

## Decisiones cerradas en la revisión

1. **`nex check` sigue exigiendo `main` (`E2001`).** Un archivo solo con funciones y ejemplos pasa
   `nex test` y no pasa `nex check`. Es coherente con lo que `nex check` promete: que el programa
   puede ejecutarse con `nex run`, y sin `main` no puede. `nex test` no exige `main` porque no
   ejecuta el programa, solo sus ejemplos. Una forma de comprobar "bibliotecas" sin `main` (por
   ejemplo, `nex check --library`) queda para una decisión futura, si hace falta.
2. **`no_examples` termina con `6`**, el mismo código que `failed`: los dos significan "la prueba no se
   superó". No se encontró nada en el contrato actual que obligue a otro código. Quien necesite
   distinguirlos lee `status` en el documento JSON.

## Cuestiones pendientes

1. **`MemoryError` y el código `70`.** `MemoryError` lo provoca el programa, no NEXORA, pero hoy
   `nex run` lo trata como error interno (`70`): no lo captura y llega al manejador general de
   `cli.py`. La API, en cambio, lo convierte en el estado `memory_limit` (`api.py`, `worker.py`).
   - En la 0.4.0, `nex test` **hereda** el comportamiento de `nex run` (sección 3.4). Es la única
     excepción a la regla de que el `70` corresponde a un fallo de NEXORA, y está escrita como tal.
   - Lo coherente es decidirlo para todos los comandos a la vez, por ejemplo con un diagnóstico de
     ejecución propio para el agotamiento de memoria. Esa decisión afecta también a `nex run` y queda
     **fuera del alcance de la 0.4.0**, para una decisión futura.
