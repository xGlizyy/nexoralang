# Ejemplos

Programas de referencia de NEXORA. Cada uno tiene un objetivo concreto, descrito en el comentario
de su primera línea.

Todos se ejecutan en las pruebas automatizadas (`tests/test_examples.py`), que comparan su salida,
sus diagnósticos y su código de salida, carácter a carácter, con los archivos de
`tests/golden/examples/`. Si un cambio en el lenguaje altera el comportamiento de un ejemplo, las
pruebas fallan.

Ejecuta cualquiera desde el directorio `nexora/`:

```bash
nex run examples/hello.nex
```

## Válidos

Superan `nex check` y `nex run` termina con código `0`.

| Archivo | Qué muestra |
|---------|-------------|
| [`hello.nex`](hello.nex) | El primer programa |
| [`variables.nex`](variables.nex) | Variables, textos, bloques y ámbitos |
| [`arithmetic.nex`](arithmetic.nex) | Precedencia, división entera y decimal, límites de `Int` |
| [`types.nex`](types.nex) | Inferencia, anotaciones, comparaciones, lógica y conversiones |
| [`functions.nex`](functions.nex) | Funciones, `if` / `else`, recursividad |
| [`contracts.nex`](contracts.nex) | Contratos `requires` y `ensures` que se cumplen, con su explicación |
| [`refined_types.nex`](refined_types.nex) | Tipos refinados con `where`: constantes comprobadas sin ejecutar y comprobación explícita con `Percent(x)` |

## Inválidos (`invalid/`)

Incorrectos a propósito. El error se detecta **sin ejecutar**: `nex check` y `nex run` terminan con
código `1` y el programa no llega a iniciarse.

| Archivo | Categoría de los errores |
|---------|--------------------------|
| [`invalid/syntax_error.nex`](invalid/syntax_error.nex) | `syntax`: el texto no sigue la gramática |
| [`invalid/name_errors.nex`](invalid/name_errors.nex) | `semantic`: nombres, valores sin usar, rutas de retorno |
| [`invalid/type_errors.nex`](invalid/type_errors.nex) | `type`: tipos incompatibles |
| [`invalid/refinement_errors.nex`](invalid/refinement_errors.nex) | `semantic` y `type`: tipos refinados mal declarados y valores que no cumplen su condición |

## Fallan al ejecutarse (`failing/`)

Superan `nex check`, porque el fallo depende de valores que solo se conocen al ejecutar.

| Archivo | Qué ocurre | `nex run` termina con |
|---------|------------|-----------------------|
| [`failing/runtime_error.nex`](failing/runtime_error.nex) | División por cero | `3` |
| [`failing/contract_violation.nex`](failing/contract_violation.nex) | Una condición `requires` es falsa | `5` |
| [`failing/refinement_violation.nex`](failing/refinement_violation.nex) | Un valor calculado no cumple la condición de un tipo refinado | `5` |
