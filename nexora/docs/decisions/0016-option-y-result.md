# 0016 — Option y Result

- **Estado:** aceptada
- **Versión:** 0.10.0 (estado del repositorio; no se ha publicado en ningún paquete)
- **Fecha:** 2026-10-22
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0006](0006-requisitos-verificables.md) (los requisitos se
  comprueban), la [0011](0011-operaciones-sobre-textos.md) (las funciones que pertenecen a un tipo) y
  la [0014](0014-registros-nominales-inmutables.md) (los registros nominales). **No modifica
  ninguna.**
- **Relacionada con la [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md):**
  acepta su parte de `Option` y `Result` (C.2.4) **en el alcance que el lenguaje tiene hoy**, que
  es el de la 0013: no hay enums del usuario ni `match`, así que estos dos tipos se implementan como
  tipos integrados con funciones de inspección. La 0012 sigue siendo propuesta en lo demás.
- **Implementación:** la 0.10.0. El código está en `values.py` (la representación en ejecución),
  `types.py` (los constructores `Option` y `Result` del modelo), `type_adapter.py` y `parser.py`
  (el texto de los tipos), `checker.py` (las firmas y la inferencia), `prelude.py` (las funciones
  puras) e `interpreter.py` (los constructores y las lecturas que pueden fallar); la evidencia está
  en las pruebas de la sección «Pruebas de regresión previstas».

## Contexto

Un programa necesita decir dos cosas que ningún valor puede decir por sí solo: que **no hay**
valor, y que **algo falló**. Hasta la 0.9.0 NEXORA no tiene ninguna forma de decirlo: no hay
excepciones, no hay `null`, y la única manera de avisar de un fallo es detener el programa.

Eso obliga a dos cosas malas. Una función que puede no encontrar nada tiene que devolver un valor
cualquiera y avisar por otro lado (un texto vacío, un `-1`), y quien la llama no puede distinguir
«no estaba» de «estaba y valía cero». Y una función que puede fallar tiene que detener el
programa, aunque el fallo sea recoverable: un archivo que no está hoy puede estar mañana, y un
número que no se puede leer no tiene por qué impedir que el programa siga.

El borrador de diseño (`docs/fase-1-diseno.md` de la raíz del repositorio) y la
[decisión 0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) proponen los dos
tipos: `Option[T]`, con `Some` y `None`, y `Result[T, E]`, con `Ok` y `Err`. La 0012 los quiere
como **enums ordinarios** de la prelud, con `match` y exhaustividad, y dice que tratarlos como
casos especiales del lenguaje sería «inconsistente y difícil de extender».

## Decisión

Se implementan `Option[T]` y `Result[T, E]` como **tipos integrados** del lenguaje, con las
funciones que ya usa el lenguaje para lo que pertenece a un tipo (`Text.length`, `List.get`), y **sin
excepciones**.

### 1. Los dos tipos, y sus dos variantes

`Option[T]` tiene `Some(valor)` y `None`. `Result[T, E]` tiene `Ok(valor)` y `Err(error)`. El
nombre de la variante es parte del valor: `None` nunca es `Some(x)` y `Ok(x)` nunca es `Err(x)`,
aunque los dos载荷 sean iguales.

### 2. Se reconocen y se leen con funciones

`Option.is_some`, `Option.is_none`, `Result.is_ok` y `Result.is_err` dicen qué variante es un
valor. `Option.unwrap_or` y `Result.unwrap_or` devuelven el valor o un defecto del mismo tipo.
`Option.unwrap`, `Result.unwrap` y `Result.error` leen el valor sin defecto, y **fallan con un
diagnóstico** (`E3011`, `E3012`, `E3013`) cuando la variante no lo lleva: no hay una lectura que
devuelva un valor inventado, ni una que haga fallar el programa sin decir por qué.

### 3. El tipo lo dice el contexto

`T` y `E` los dice el contexto que espera el valor: la anotación de una variable, el tipo de un
parámetro, el tipo de resultado de una función o el otro lado de una comparación. `None`, `Ok` y
`Err` escritos sin ese contexto no tienen tipo completo, y el análisis lo dice (`E2011`).

### 4. `None` es un nombre, no una palabra reservada

`None` se resuelve como constante integrada cuando el programa no declara un nombre así. Un
programa que ya usara `None` como nombre sigue funcionando: su nombre gana.

### 5. No hay `?`

El operador de propagación **no se implementa ahora**. Se decide aquí por qué, y qué haría falta
para añadirlo:

- La propagación necesita que el tipo de resultado de la función que la usa y el tipo de error de
  la expresión coincidan exactamente. El lenguaje no tiene variables de tipo en las declaraciones,
  así que esa coincidencia se comprueba pero no se deduce: propagar un `Err` de tipo `Text` desde
  una función que devuelve `Result[Int, Error]` sería un error de tipos, y no una conversión.
- Propagar un `Option` dentro de una función que devuelve `Option[T]` necesita el mismo tipo de
  elemento, con la mismaLimitación.
- El valor propagado tiene que **conservar** el error: propagar es `return Err(error)`, y eso es
  exactamente lo que hace el `Err` que ya se escribe. La propagación solo ahorra escribir la
  comprobación y el `return`, a cambio de una forma sintáctica nueva y de reglas de comprobación
  nuevas.

Lo que hoy hace falta se puede escribir sin una forma nueva:

```nex
fn parse(text: Text) -> Result[Int, Text] {
    if Int.can_parse(text) {
        return Ok(Int.parse(text))
    }
    return Err("not a whole number")
}
```

Cuando el lenguaje tenga enums del usuario y `match` (la 0012 completa), la propagación tendrá un
sitio natural y se decidirá con ellos.

## Hechos verificados en el repositorio

| Hecho | Dónde |
|-------|-------|
| Los tipos `Option` y `Result` ya estaban en el modelo, sin sintaxis | `types.py` (`OPTION`, `RESULT`, `option_of`, `result_of`) |
| Las firmas con variables de tipo ya existían, con `unify` por llamada | `checker.py` (`ParametricSignature`, `_parametric_call`) |
| El tipo esperado ya llegaba a las expresiones, como en la lista vacía | `checker.py` (`_expression`, `_list_literal`) |
| Las funciones de un tipo se llaman con el nombre del tipo | `checker.py` (`BUILTINS`), `prelude.py` (`IMPLEMENTATIONS`) |
| Los valores se imprimen con `format_value` y se comparan por valor | `values.py` |

## Decisiones que se toman aquí, y por qué

| Decisión | Por qué |
|----------|---------|
| Dos tipos integrados y no enums del usuario | El lenguaje no tiene enums ni `match`. Añadirlos es otra decisión, más grande; mientras tanto, estos dos dan lo que se necesita |
| Las variantes se nombran sin cualificar (`Some`, `Ok`, `Err`) | Como en el resto del lenguaje, un nombre de función es un nombre; el cualificado se reserva para lo que pertenece a un tipo (`Text.length`) |
| La inspección con funciones y no con `match` | `match` no existe: no hay dos construcciones que compitan por lo mismo |
| `None` como constante y no como palabra reservada | No rompe los programas que ya usan ese nombre |
| Las lecturas que fallan lo dicen con un diagnóstico | El proyecto no tiene excepciones: un fallo tiene que ser un diagnóstico, con su código y su posición |
| Sin propagación por ahora | Ver la decisión 5 |

## Lo que no garantiza

- No hay `match`, ni `if let`, ni `?`: la inspección se hace con funciones.
- El tipo de un `None`, de un `Ok` o de un `Err` **escrito directamente en una comparación** no se
  deduce: `Ok(1) == Ok(1)` necesita que el tipo de error esté escrito en una variable antes.
- El tipo de un argumento de una función con variables de tipo no se deduce de los otros
  argumentos: el lenguaje no infiere un tipo a través de los argumentos de una llamada.
- `Option` y `Result` no son enums del usuario: no se pueden añadir variantes, y `match` sobre ellos
  no es exhaustivo por construction.

## Fuera del alcance

- Los enums del usuario y el `match` con exhaustividad: son la parte grande de la 0012 y siguen
  siendo propuesta.
- La propagación `?`: se decide más adelante, con el `match`.
- Los genéricos de usuario: `Option[T]` y `Result[T, E]` son los dos únicos tipos con argumentos
  que el lenguaje admite.
- `Option` y `Result` en los contratos (`requires` y `ensures`) y en los refinamientos: no se ha
  comprobado que el análisis pueda darlos por buenos.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|-----------|
| Excepciones para el error | El lenguaje no las tiene, y la 0002 hace que solo se ejecute lo comprobado |
| Un valor centinela (un `-1`, un texto vacío) | No distingue la ausencia del valor, y no conserva el error |
| `null` | No existe en el lenguaje, y no distinguiría «no hay» de «hay un valor nulo» |
| Tratar `Option` y `Result` como registros | Un registro tiene campos y no tiene variantes; `Some` y `None` no serían el mismo tipo |
| `Option` y `Result` como casos especiales del analizador | La 0012 lo rechaza: sería inconsistente y difícil de extender |
| Añadir `?` ahora | Ver la decisión 5: el lenguaje no deduce el tipo de error que hay que propagar |

## Compatibilidad

- Los programas que ya existen siguen comprobando lo mismo: los tipos `Option` y `Result` no
  existían, así que no había ningún `Option` ni ningún `Result` que el nuevo código pueda cambiar.
- Los nombres `Option`, `Result`, `Some`, `Ok` y `Err` pasan a estar en el lenguaje. Un programa que
  declarara una función con uno de esos nombres usaría la integrada: es el mismo caso que `print` o
  `to_text`. `None` es el caso contrario: el nombre del programa gana.
- Los tipos con argumentos escribibles pasan de ser solo `List[T]` a ser también `Option[T]` y
  `Result[T, E]`. El texto canónico de un tipo con argumentos sigue siendo el que escribe
  `display`: `Result[Int, Text]`, con un espacio después de la coma.
- La especificación pasa a la versión 0.10 y la implementación de referencia a la 0.10.0. La 0.9.0
  ya publicada en npm no se toca.

## Cambios necesarios

- `types.py`: sin cambios de fondo; el modelo ya tenía los dos constructores. La documentación del
  módulo deja de decir que no están activados.
- `type_adapter.py`: admite `Option[T]` y `Result[T, E]` en el texto canónico.
- `parser.py`: `Option` y `Result` son nombres de tipo con argumentos, con su aridad.
- `checker.py`: las firmas de los constructores y de las funciones de inspección; el tipo esperado
  llega a la llamada; `None` es una constante; `_known_type` admite los dos tipos.
- `values.py`: la representación en ejecución (`VariantValue`) y su impresión.
- `prelude.py`: las funciones puras de inspección.
- `interpreter.py`: los constructores, la constante `None` y las tres lecturas que pueden fallar.
- `diagnostics.py`: `E3011`, `E3012` y `E3013`.

## Pruebas de regresión previstas

| Archivo | Qué fija |
|---------|----------|
| `tests/test_option_result.py` | Las cuatro variantes, sus payloads, la igualdad entre variantes, la inspección, las lecturas que fallan, los errores de tipo y la inferencia |
| `tests/test_type_lists.py` | Que `Option` y `Result` son tipos, y que el texto canónico es el que se espera |
| `tests/test_type_lists_syntax.py` | Que un tipo con argumentos mal escrito es un error de sintaxis |
| `tests/test_security.py` | Que las funciones integradas son exactamente las documentadas |
| `tests/test_text_operations.py` | Que toda función de un tipo tiene una implementación |
| `examples/option_result.nex` | Un programa completo que usa las dos variantes, y su salida registrada |

## Relación con las decisiones anteriores y el índice

Esta decisión implementa la parte de `Option` y `Result` de la
[0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) (C.2.4) **en el alcance que el
lenguaje tiene hoy**. No modifica la 0012, que sigue siendo propuesta en los enums, el `match`, la
exhaustividad, la entrada y los efectos. Se añade al índice de decisiones como aceptada.

## Cuestiones que siguen abiertas

- ¿Qué pasa con `Option` y `Result` cuando el lenguaje tenga enums del usuario y `match`? ¿Se
  mantienen como tipos integrados, o se convierten en enums de la prelud, como dice la 0012?
- ¿La propagación `?` tiene sentido con los enums y el `match`? ¿Qué reglas necesita?
- ¿Deben `Option` y `Result` poder aparecer en los contratos y en las condiciones de un tipo
  refinado?
