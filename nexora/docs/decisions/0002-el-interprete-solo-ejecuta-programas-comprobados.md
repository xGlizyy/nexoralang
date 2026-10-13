# 0002 — El intérprete solo ejecuta programas comprobados

- **Estado:** aceptada
- **Versión:** 0.2.0

## Contexto

En 0.1 el intérprete repetía las comprobaciones de nombres y tipos que ya hacía el comprobador
estático, "por si acaso" se le pasaba un programa sin comprobar. Con funciones, retornos y
contratos, mantener dos copias de las mismas reglas habría duplicado la lógica y abierto la puerta
a que las dos copias dejaran de coincidir.

## Decisión

- Las reglas de nombres, ámbitos y tipos viven en un único módulo: `checker.py`.
- El comprobador devuelve un `CheckedProgram`, y **eso es lo único que el intérprete acepta**.
- El intérprete solo comprueba lo que no puede saberse antes de ejecutar: división por cero,
  desbordamiento, conversiones fuera de rango, profundidad de llamadas y contratos.
- Si el intérprete encuentra algo que el comprobador debería haber rechazado, es un defecto de
  NEXORA y se comunica como error interno (código de salida 70), no como error del programa.

Las cuatro etapas quedan así:

| Etapa | Módulo | Depende de |
|-------|--------|------------|
| Análisis léxico | `lexer.py` | — |
| Análisis sintáctico | `parser.py` | tokens |
| Análisis estático | `checker.py` | AST |
| Ejecución | `interpreter.py` | `CheckedProgram` |

`pipeline.analyze` encadena las tres primeras y es lo que usan todos los comandos (`run`, `check`,
`inspect`), de modo que los tres ven exactamente el mismo programa.

## Motivos

- Una sola definición de cada regla: lo que `nex check` acepta es exactamente lo que `nex run`
  ejecuta.
- La lista de errores posibles en ejecución es corta y cerrada (sección 10.3 de la especificación),
  y puede documentarse como garantía.

## Consecuencias

- El módulo se sigue llamando `checker.py`; no se renombró a `type_checker.py` porque también
  comprueba nombres, ámbitos y rutas de retorno.
- Desaparecen las pruebas de 0.1 que ejecutaban el intérprete sin pasar por el comprobador. Su
  cobertura la dan ahora las pruebas del comprobador.
- Sin cambios visibles para quien usa el lenguaje.
