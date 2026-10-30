# 0022 — Depurador local por CLI

- **Estado:** aceptada e implementada.
- **Afecta:** CLI e intérprete.
- **Modifica:** el alcance inicial de la decisión 0020; no cambia la semántica del lenguaje.

## Decisión

La CLI ofrece `nex debug <file>` para ejecutar localmente un programa bajo el depurador por
sentencias del intérprete. `step` avanza una sentencia, `continue` reanuda hasta un breakpoint
o el final, y `break [FILE:]LINE` y `delete [FILE:]LINE` gestionan breakpoints. En cada pausa
se muestran la ubicación, la pila de llamadas, las variables visibles y su valor acotado.
`quit` detiene el programa.

Los comandos de depuración se leen del terminal controlador. El programa conserva su entrada
estándar para `input()`. Su acceso a archivos, red y procesos sigue las mismas declaraciones,
concesiones explícitas y límites que `nex run`; depurar no concede capacidades adicionales.
No se evalúan expresiones arbitrarias ni se modifican variables desde el depurador.

La sesión inspecciona como máximo 10.000 sentencias y admite hasta 256 breakpoints. Los límites
de fuente, entrada, salida, texto y memoria de la CLI también están disponibles. `--timeout`
cuenta el tiempo de ejecución y excluye el tiempo que el programa permanece pausado en el
prompt. Un programa que supera `--max-steps` se detiene de forma controlada.

El comando local es la interfaz de depuración de referencia en 1.0. No se implementa DAP ni
una integración de depuración para el servidor de lenguaje en este alcance. El Playground
conserva sus controles de depuración y su aislamiento de worker, definidos en la decisión 0020.

## Ejemplo de referencia

El archivo [`docs/examples/local-debugger.nex`](../examples/local-debugger.nex) se puede depurar
con:

```console
nex debug docs/examples/local-debugger.nex --breakpoint 3
```

En la primera pausa, escribe `continue` para llegar al breakpoint de la función `add_tip`.
El inspector muestra el parámetro `subtotal` y la pila de llamadas; `step` ejecuta la sentencia
seleccionada y vuelve a pausar antes de la siguiente.
