# Hoja de ruta

Qué está hecho, qué se está haciendo y qué queda. No hay fechas: cada cosa empieza cuando la
anterior es sólida.

## Criterios

| Estado | Significa que… |
|--------|----------------|
| **Completado y verificado** | Funciona, tiene pruebas automatizadas que pasan y su documentación describe su comportamiento real |
| **En desarrollo** | Existe en parte; lo que falta se indica |
| **Planificado** | No existe. Hay una idea clara de qué construir |
| **En investigación** | No existe y no está decidido cómo debería ser, o si debería existir |

Que un archivo exista no cuenta. Una característica solo está "completada" si se puede ejecutar y
hay una prueba que falla si deja de funcionar.

## Completado y verificado

| Elemento | Cómo se verifica |
|----------|------------------|
| Analizador léxico y sintáctico, con recuperación de errores | `tests/test_lexer.py`, `tests/test_parser.py` |
| Tipos `Int`, `Float`, `Bool`, `Text`, `Void`; inferencia y anotaciones | `tests/test_types.py` |
| **Listas** `List[T]` inmutables, con literales, igualdad y `List.length`, `List.get`, `List.append`, `List.concat` y `List.contains` | `tests/test_type_lists_syntax.py`, `tests/test_type_lists_values.py`, `tests/test_type_lists_functions.py` |
| Aritmética, comparaciones y operadores lógicos | `tests/test_types.py`, `tests/test_interpreter.py` |
| Conversiones explícitas (`to_float`, `to_int`, `to_text`) | `tests/test_types.py` |
| Variables inmutables (`let`) y reasignables (`var`), bloques y ámbitos | `tests/test_checker.py`, `tests/test_loops.py` |
| **Bucles** `while` con su medida (`decreases`) e invariantes (`invariant`), comprobados en cada vuelta | `tests/test_loops.py` |
| **`for` sobre listas**, con iterador inmutable, invariantes y ámbitos por vuelta | `tests/test_for.py` |
| **Operaciones sobre textos**: `Text.length`, `Text.slice`, búsqueda, orden entre textos y lectura de números (`Int.parse`, `Float.parse`), con sus requisitos comprobados en cada llamada | `tests/test_text_operations.py` |
| Funciones con parámetros, `return`, rutas de retorno, recursividad | `tests/test_functions.py` |
| `if` / `else if` / `else` | `tests/test_functions.py` |
| **Contratos** (`requires`, `ensures`), estables desde la 0.3.0 | `tests/test_contracts.py` |
| **Explicación de cada regla**, mostrada en el diagnóstico cuando se incumple | `tests/test_contracts.py`, `tests/test_refined_types.py` |
| **Tipos refinados** (`type ... where ...`): constantes comprobadas sin ejecutar, `Tipo(x)` al ejecutar, cadenas de tipos | `tests/test_refined_types.py` |
| **Ejemplos en las funciones** (`example`), evaluados con `nex test` | `tests/test_example_clauses.py`, `tests/test_nex_test.py` |
| Memoria agotada al ejecutar como error del programa (`E3007`) | `tests/test_out_of_memory.py` |
| Ningún bucle se queda repitiendo para siempre: se detiene con `E4006`, también en `nex test` | `tests/test_loops.py` |
| Análisis estático separado de la ejecución | `tests/test_checker.py`, `tests/test_security.py` |
| Intérprete | `tests/test_interpreter.py` |
| Diagnósticos con código, categoría y posición, en texto y JSON | `tests/test_diagnostics.py`, `tests/test_cli.py` |
| Comandos `nex run`, `nex check`, `nex inspect` | `tests/test_cli.py` |
| Representación JSON del programa (`nexora.inspect/2`) | `tests/test_inspect.py` |
| Símbolos y referencias (`nex symbols`) y resumen del programa (`nex context`) | `tests/test_tooling.py` |
| Formatos JSON versionados, con JSON Schema generados desde el código | `tests/test_tooling.py` valida con ellos la salida real |
| Árbol, símbolos y resumen parciales cuando el programa tiene errores de sintaxis | `tests/test_tooling.py`, incluido el programa cortado en cada carácter |
| Tareas de referencia para las herramientas de análisis | `tests/test_tooling_tasks.py` |
| Ejemplos ejecutables con salida registrada | `tests/test_examples.py` |
| Documentación sincronizada con la implementación | `tests/test_docs.py` |
| Resistencia ante entradas incorrectas, enormes o truncadas | `tests/test_robustness.py` |
| Empaquetado instalable en local | Comprobado a mano en Windows; ver [pruebas](testing.md#empaquetado) |

## En desarrollo

| Elemento | Qué hay | Qué falta |
|----------|---------|-----------|
| **API de Python** (`nexora.tooling`) | Implementada y probada (`tests/test_tooling.py`) | Declararla estable. Hoy es experimental y puede cambiar |
| **Servidor MCP** (opcional) | Siete herramientas de análisis, probadas con el cliente del SDK oficial (`tests/test_mcp.py`). Comprobado a mano una vez en Claude Code. No ejecuta código | Probarlo en otros asistentes. Incluir la especificación en el paquete instalable |
| **Playground** (web) | Editor, API y ejecución en un proceso aparte con límites; probado en local ([Playground](playground.md)) | Desplegarlo. Verificar el aislamiento con contenedor y los límites POSIX, que no se han podido probar en Windows |
| **Integración continua** | Flujo de GitHub Actions en marcha: se ejecuta en cada cambio a `main`, en Linux, Windows y macOS | Ampliar la matriz a más versiones de Node |
| **Valores opcionales y resultados** | `Option[T]` y `Result[T, E]`, con `Some`, `None`, `Ok` y `Err`, y las funciones que reconocen la variante y leen el valor. Sin `match` ni `?` | `match`, `if let` y el operador `?`, cuando haya enums del usuario |
| **Valores opcionales y resultados** | `Option[T]` y `Result[T, E]`, con `Some`, `None`, `Ok` y `Err`, y las funciones que reconocen la variante y leen el valor. Sin `match` ni `?` | `match`, `if let` y el operador `?`, cuando haya enums del usuario |
| **Valores opcionales y resultados** | `Option[T]` y `Result[T, E]`, con `Some`, `None`, `Ok` y `Err`, y las funciones que reconocen la variante y leen el valor. Sin `match` ni `?` | `match`, `if let` y el operador `?`, cuando haya enums del usuario |
| **Verificación en otras plataformas** | Comprobado en Windows 11 con Python 3.12; ejecutado en Linux, Windows y macOS con Python 3.11, 3.12 y 3.13 por la integración continua | Comprobarlo en macOS y en Linux con un equipo, no solo en los ejecutores |
| **Preparación para colaboradores** | Licencia MIT, guía de contribución, política de seguridad, código de conducta, repositorio público con su rastreador de incidencias | Definir un canal de contacto privado |

## Línea principal: requisitos verificables

La característica que distingue a NEXORA es que los requisitos de una función forman parte
verificable del programa ([decisión 0006](decisions/0006-requisitos-verificables.md)). Es la
prioridad del proyecto. Su trabajo va en este orden, y cada paso empieza cuando el anterior es
sólido:

| # | Paso | Estado |
|---|------|--------|
| 1 | **Estabilizar los contratos** (`requires`, `ensures`): fijar su posición en el código y el nombre `result`, y dejar de marcarlos como experimentales | **Completado en la 0.3.0** ([decisión 0007](decisions/0007-contratos-estables-y-tipos-refinados.md)) |
| 2 | **Una explicación en lenguaje natural unida a cada condición**, que aparece en el diagnóstico cuando la condición se incumple | **Completado en la 0.3.0**, en contratos y en tipos refinados |
| 3 | **Casos concretos en la función (`example`)** y un comando que los ejecute sin escribir `main` | **Completado en la 0.4.0** ([decisión 0008](decisions/0008-ejemplos-y-nex-test.md)) |
| 4 | **Avisar cuando una edición elimina o debilita un requisito** | En investigación: no está decidido cómo detectar que una condición es más débil que otra |
| 5 | **Tipos refinados** (`type Percent = Int where ...`) | **Completado en la 0.3.0** sobre los tipos integrados. Falta refinar registros: no está implementado |
| 5b | **Requisitos de los bucles**: la medida (`decreases`) y los invariantes (`invariant`), con su explicación, comprobados en cada vuelta | **Completado en la 0.5.0** ([decisión 0010](decisions/0010-var-y-while.md)) |
| 6 | **Evaluar si los requisitos en el código ayudan a un agente de IA** a no romperlos | Planificado; ver la última fila de [En investigación](#en-investigación) |

Hasta que el paso 6 dé resultados, la característica es una hipótesis y no se presenta como una
ventaja demostrada.

## Planificado

El resto del lenguaje, en el orden en que tendría sentido abordarlo. Avanza junto a la línea
principal; cuando un punto de esta lista es necesario para un paso de la línea principal, va
primero:

1. ~~**Operaciones sobre textos**~~: hechas en la 0.6.0 ([decisión 0011](decisions/0011-operaciones-sobre-textos.md)).
2. ~~**Un primer tipo compuesto: listas**~~: hechas en la 0.7.0, con `for` sobre listas ([decisión 0013](decisions/0013-listas-y-for.md)). El modelo de tipos y las listas están descritos en la [especificación](language-spec.md), secciones 4.5, 8.2 y 9.6.
3. ~~**Registros**~~: hechos en la 0.8.0, con identidad nominal y campos inmutables ([decisión 0014](decisions/0014-registros-nominales-inmutables.md)); están descritos en la [especificación](language-spec.md), sección 4.6. Quedan los **valores opcionales** (`Option`, `Result`), para representar la ausencia de un
   valor y los errores sin excepciones.
4. ~~**Entrada de datos**~~: hecha en la 0.9.0, con los argumentos del programa, la entrada estándar y los archivos con permisos explícitos ([decisión 0015](decisions/0015-entrada-argumentos-archivos-y-permisos.md)). Quedan la red y los procesos externos.
5. ~~**Módulos e importaciones**~~: hechas en la 0.11.0 ([decisión 0018](decisions/0018-modulos-e-importaciones.md)).
6. **Avisos** (variables sin usar, `var` que nunca cambia) y convenciones de nombres.
7. **Análisis más tolerante**: conservar las funciones cuya declaración tiene un error, y dar
   estructura también con errores léxicos. El árbol parcial con errores de sintaxis ya existe.
8. **Servidor de lenguaje (LSP)**, empezando por los diagnósticos. La evaluación y los requisitos
   que quedan están en [LSP](lsp.md). Hoy no existe.
9. **Formateador.**

## En investigación

Ideas del diseño original cuyo valor o cuya forma no están decididos:

| Idea | Pregunta abierta |
|------|------------------|
| Verificación estática de contratos | ¿Qué parte puede demostrarse sin un demostrador completo, y sin dar falsas garantías? |
| Requisitos debilitados entre dos versiones de una función | ¿Cómo saber, sin un demostrador, que una condición nueva es más débil que la anterior? ¿Basta con avisar cuando una condición desaparece o cambia? |
| Efectos declarados (`uses`) | ¿Compensa la carga de anotarlos? |
| Funciones resueltas por un modelo de IA (`ai fn`, `tool fn`) | ¿Puede un lenguaje determinista incorporar una operación que no lo es, y cómo se prueba? |
| Ediciones estructuradas en los diagnósticos | ¿Qué formato permitiría aplicar una corrección automáticamente con seguridad? |
| **La hipótesis central del proyecto** | Cuando una IA modifica una función, ¿se detectan más incumplimientos si los requisitos están escritos en el código que si solo están en la instrucción? **No se ha evaluado.** El experimento está descrito en la [decisión 0006](decisions/0006-requisitos-verificables.md#cómo-se-sabrá-si-funciona); las [tareas de referencia](ai-tooling.md#tareas-de-referencia) son su punto de partida |
| Ejecución de programas a través de MCP | ¿Con qué aislamiento y bajo qué activación explícita? Hoy el servidor solo analiza |
| Compilación a JavaScript o WebAssembly | El borrador original lo proponía; hoy solo existe un intérprete, y el playground ejecuta en el servidor |

## Historial de fases

| Fase | Objetivo | Resultado |
|------|----------|-----------|
| 1 | Núcleo: lexer, parser, intérprete, CLI, diagnósticos | Completada (versión 0.1.0) |
| 2 | Sistema de tipos, funciones, contratos, salidas JSON | Completada (versión 0.2.0); los contratos quedan como experimentales |
| 3 | Documentación, pruebas y calidad | Completada en lo que puede comprobarse en local; integración continua y otras plataformas, pendientes de ejecutar |
| 4 | Playground: editor web que ejecuta con el intérprete real | Implementada y probada en local; sin desplegar, y con el aislamiento por contenedor sin verificar |
| 5 | Herramientas para agentes: protocolo JSON, `nex context`, `nex symbols`, API de Python, servidor MCP | Implementada y probada en local; el LSP queda planificado y ningún modelo de IA se ha evaluado |
| 6 | Requisitos verificables: contratos estables, explicación de las reglas y tipos refinados | Completada (versión 0.3.0). Los ejemplos (paso 3) llegaron en la 0.4.0; quedan los pasos 4 y 6 de la [línea principal](#línea-principal-requisitos-verificables) |
| 7 | Repetición sin recursividad: `var` y bucles que declaran por qué terminan y qué mantienen | Completada (versión 0.5.0) |

La web del proyecto (`web/`, en la raíz del repositorio) muestra una versión resumida de esta hoja
de ruta. Este documento es la referencia.
