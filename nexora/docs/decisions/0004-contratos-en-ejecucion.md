# 0004 — Contratos al principio del cuerpo, comprobados en ejecución

- **Estado:** aceptada. Fue experimental en la 0.2; la [decisión 0007](0007-contratos-estables-y-tipos-refinados.md)
  la declara estable en la 0.3.0 sin cambiar su sintaxis
- **Versión:** 0.2.0

## Decisión

1. Una función puede declarar condiciones previas (`requires`) y posteriores (`ensures`).
2. **Las cláusulas se escriben al principio del cuerpo**, antes de cualquier sentencia. El borrador
   de diseño las colocaba entre la firma y la llave de apertura.
3. Una condición es una expresión `Bool` normal. En `requires` solo son visibles los parámetros; en
   `ensures`, los parámetros y `result`.
4. `result` es un nombre contextual: solo significa "el valor devuelto" dentro de `ensures`. Un
   parámetro no puede llamarse `result`.
5. **`nex check` comprueba los tipos de las condiciones. Su verdad se comprueba al ejecutar**, en
   cada llamada: `requires` antes del cuerpo, `ensures` después de calcular el valor de retorno.
6. Una condición falsa detiene el programa con un diagnóstico de categoría `contract`:
   - `E4001` señala **la llamada** (quien llama incumple).
   - `E4002` señala **la cláusula** (la función incumple).
7. El proceso termina con el código de salida `5`, distinto del de un error de ejecución (`3`).

## Motivos

- Se sigue la sintaxis propuesta para esta fase. Dentro del cuerpo, las cláusulas no necesitan
  reglas especiales de continuación de línea, y `E1106` puede detectar una cláusula mal colocada.
- Atribuir la culpa (llamada o función) es lo que distingue un contrato de un `if` que imprime un
  error: el diagnóstico dice quién tiene que corregir su código.
- Los valores de los argumentos y de `result` se incluyen en el diagnóstico porque son exactamente
  lo que hace falta para entender por qué la condición fue falsa.
- Comprobar en ejecución es lo que puede hacerse correctamente hoy. Una verificación estática
  parcial que a veces dijera "cumple" sin poder demostrarlo sería peor que no tenerla.

## Lo que no garantiza

- No demuestra que un contrato se cumpla siempre. Solo comprueba las llamadas que se ejecutan.
- `nex check` nunca dice que un contrato se cumple; solo que está bien formado. Hay una prueba
  (`test_check_does_not_claim_a_contract_holds`) con una condición imposible de cumplir que supera
  `nex check` y falla al ejecutarse.
- No comprueba que una condición no tenga efectos: puede llamar a una función que use `print`.
- Los contratos no pueden desactivarse.

## Alternativas descartadas

- **Cláusulas entre la firma y el cuerpo** (borrador). Queda como posible cambio futuro.
- **Verificación estática.** Fuera del alcance: requeriría un demostrador o análisis de rangos.
- **Tratar la violación como un error de ejecución corriente.** Perdería la distinción entre
  "el programa hizo una operación imposible" y "el programa incumplió lo que él mismo declara".

## Posibles cambios incompatibles

Al ser experimental, pueden cambiar la posición de las cláusulas, el nombre `result` y los nodos
correspondientes del esquema de `nex inspect` (lo que cambiaría la versión del esquema).

> Resuelto en la [decisión 0007](0007-contratos-estables-y-tipos-refinados.md): la posición de las
> cláusulas y el nombre `result` se mantienen y pasan a ser estables.
