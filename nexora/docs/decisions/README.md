# Decisiones técnicas

Registro de las decisiones de diseño de NEXORA: qué se decidió, por qué, qué se descartó y qué
cambia para quien ya tiene programas escritos. Cada decisión tiene un número y no se reescribe: si
una decisión se revisa, se añade otra que la sustituye y se indica en ambas.

| Nº | Decisión | Estado | Incompatible con 0.1 |
|----|----------|--------|----------------------|
| [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md) | Tipos estáticos, sin conversiones implícitas; `String` pasa a llamarse `Text` | Aceptada | Sí |
| [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md) | El intérprete solo ejecuta programas comprobados | Aceptada | No |
| [0003](0003-funciones-retorno-e-if.md) | Funciones con `return` explícito, un único espacio de nombres e `if` como sentencia | Aceptada | No |
| [0004](0004-contratos-en-ejecucion.md) | Contratos al principio del cuerpo, comprobados en ejecución | Aceptada (estable desde 0007) | No |
| [0005](0005-diagnosticos-y-esquemas-json.md) | Categorías de diagnóstico, esquemas JSON versionados y código de salida 5 | Aceptada | Sí |
| [0006](0006-requisitos-verificables.md) | Característica diferencial: los requisitos son parte verificable del programa | Aceptada | No |
| [0007](0007-contratos-estables-y-tipos-refinados.md) | Contratos estables, explicación de las reglas y tipos refinados | Aceptada | No |
| [0008](0008-ejemplos-y-nex-test.md) | Ejemplos en las funciones (`example`) y el comando `nex test` | Aceptada | No |
| [0009](0009-memoria-agotada.md) | Un programa que agota la memoria al ejecutarse: diagnóstico `E3007` | Aceptada | Sí |
| [0010](0010-var-y-while.md) | Variables reasignables (`var`) y bucles con requisitos (`while`, `invariant`, `decreases`) | Aceptada | Sí |
| [0011](0011-operaciones-sobre-textos.md) | Operaciones sobre textos: funciones asociadas a un tipo (`Text.length`, `Int.parse`) que declaran sus requisitos | Aceptada | No |
| [0012](0012-modelo-de-tipos-patrones-iteracion-y-verificabilidad.md) | Modelo de tipos, registros, patrones, enumeraciones, `Option`/`Result`, listas, `for`, entrada, módulos y evidencia verificable | Propuesta (no aceptada; la 0013 acepta solo D01, D08 y D09 en el alcance implementado) | No |
| [0013](0013-listas-y-for.md) | Listas `List[T]`, `for` sobre listas y el modelo de tipos que los sostiene: acepta D01, D08 y D09 en el alcance implementado | Aceptada | No |
| [0014](0014-registros-nominales-inmutables.md) | Registros nominales inmutables: declaración `type X = { ... }`, construcción con campos nombrados, acceso a campos e identidad nominal por declaración | Aceptada | No |
| [0015](0015-entrada-argumentos-archivos-y-permisos.md) | Entrada, argumentos, archivos y permisos: `args()`, `input()`, `read_file()`, `write_file()`, declaraciones `uses` y permisos concedidos por quien ejecuta | Aceptada | No |
| [0016](0016-option-y-result.md) | `Option[T]` y `Result[T, E]`: `Some`, `None`, `Ok` y `Err`, con funciones que reconocen la variante y leen el valor, sin excepciones | Aceptada | No |
| [0017](0017-un-editor-la-extension-de-vs-code.md) | Un editor: la extensión de VS Code, con su servidor de lenguaje y su formateador, sobre el analizador del propio lenguaje | Aceptada | No |

## Posibles cambios incompatibles en el futuro

Decisiones que probablemente haya que revisar y que afectarían a programas existentes:

- **Variables sin usar y convenciones de nombres.** El borrador de diseño las trata como errores.
  Si se activan, programas hoy válidos dejarán de serlo.
- **`+` entre textos (0001).** Existe porque no hay interpolación. Cuando la haya, podría retirarse.
- **`if` como expresión (0003).** Si `if` pasa a producir un valor, la regla de "expresión usada
  como sentencia" (`E2010`) tendrá que revisarse.
- **Límite de 1000 llamadas anidadas.** Es una consecuencia de la implementación actual, no una
  regla deseada del lenguaje.
