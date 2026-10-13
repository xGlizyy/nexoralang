# Decisiones técnicas

Registro de las decisiones de diseño de NEXORA: qué se decidió, por qué, qué se descartó y qué
cambia para quien ya tiene programas escritos. Cada decisión tiene un número y no se reescribe: si
una decisión se revisa, se añade otra que la sustituye y se indica en ambas.

| Nº | Decisión | Estado | Incompatible con 0.1 |
|----|----------|--------|----------------------|
| [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) | Tipos estáticos, sin conversiones implícitas; `String` pasa a llamarse `Text` | Aceptada | Sí |
| [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) | El intérprete solo ejecuta programas comprobados | Aceptada | No |
| [0003](0003-funciones-retorno-e-if.md) | Funciones con `return` explícito, un único espacio de nombres e `if` como sentencia | Aceptada | No |
| [0004](0004-contratos-en-ejecucion.md) | Contratos al principio del cuerpo, comprobados en ejecución | Experimental | No |
| [0005](0005-diagnosticos-y-esquemas-json.md) | Categorías de diagnóstico, esquemas JSON versionados y código de salida 5 | Aceptada | Sí |

## Posibles cambios incompatibles en el futuro

Decisiones que probablemente haya que revisar y que afectarían a programas existentes:

- **Contratos (0004).** Su posición en el código y el nombre `result` son provisionales.
- **Variables sin usar y convenciones de nombres.** El borrador de diseño las trata como errores.
  Si se activan, programas hoy válidos dejarán de serlo.
- **`+` entre textos (0001).** Existe porque no hay interpolación. Cuando la haya, podría retirarse.
- **`if` como expresión (0003).** Si `if` pasa a producir un valor, la regla de "expresión usada
  como sentencia" (`E2010`) tendrá que revisarse.
- **Límite de 1000 llamadas anidadas.** Es una consecuencia de la implementación actual, no una
  regla deseada del lenguaje.
