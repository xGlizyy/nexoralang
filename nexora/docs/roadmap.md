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
| Aritmética, comparaciones y operadores lógicos | `tests/test_types.py`, `tests/test_interpreter.py` |
| Conversiones explícitas (`to_float`, `to_int`, `to_text`) | `tests/test_types.py` |
| Variables inmutables, bloques y ámbitos | `tests/test_checker.py` |
| Funciones con parámetros, `return`, rutas de retorno, recursividad | `tests/test_functions.py` |
| `if` / `else if` / `else` | `tests/test_functions.py` |
| Análisis estático separado de la ejecución | `tests/test_checker.py`, `tests/test_security.py` |
| Intérprete | `tests/test_interpreter.py` |
| Diagnósticos con código, categoría y posición, en texto y JSON | `tests/test_diagnostics.py`, `tests/test_cli.py` |
| Comandos `nex run`, `nex check`, `nex inspect` | `tests/test_cli.py` |
| Representación JSON del programa (`nexora.inspect/1`) | `tests/test_inspect.py` |
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
| **Contratos** (`requires`, `ensures`) | Implementados, comprobados al ejecutar, con pruebas (`tests/test_contracts.py`) | Estabilizar la sintaxis. Siguen marcados como experimentales |
| **API de Python** (`nexora.tooling`) | Implementada y probada (`tests/test_tooling.py`) | Declararla estable. Hoy es experimental y puede cambiar |
| **Servidor MCP** (opcional) | Siete herramientas de análisis, probadas con el cliente del SDK oficial (`tests/test_mcp.py`). Comprobado a mano una vez en Claude Code. No ejecuta código | Probarlo en otros asistentes. Incluir la especificación en el paquete instalable |
| **Playground** (web) | Editor, API y ejecución en un proceso aparte con límites; probado en local ([Playground](playground.md)) | Desplegarlo. Verificar el aislamiento con contenedor y los límites POSIX, que no se han podido probar en Windows |
| **Integración continua** | Flujo de GitHub Actions escrito | No se ha ejecutado nunca: el proyecto no tiene repositorio remoto |
| **Verificación en otras plataformas** | Probado en Windows 11 con Python 3.12 | Linux, macOS, Python 3.11 y 3.13 |
| **Preparación para colaboradores** | Licencia MIT, guía de contribución, política de seguridad, código de conducta | Publicar el repositorio y definir un canal de contacto |

## Planificado

En el orden en que tendría sentido abordarlo:

1. **Variables reasignables (`var`) y bucles (`while`).** Van juntos: uno no sirve sin el otro.
   Eliminan la dependencia de la recursividad.
2. **Operaciones sobre textos**: longitud, comparación de orden, conversión de texto a número.
3. **Un primer tipo compuesto: listas.** Exige cambiar la forma en que el comprobador representa
   los tipos.
4. **Registros y valores opcionales** (`Option`, `Result`), para representar la ausencia de un
   valor y los errores sin excepciones.
5. **Entrada de datos**: argumentos del programa y lectura de la entrada estándar.
6. **Módulos e importaciones.**
7. **Avisos** (variables sin usar) y convenciones de nombres.
8. **Análisis más tolerante**: conservar las funciones cuya declaración tiene un error, y dar
   estructura también con errores léxicos. El árbol parcial con errores de sintaxis ya existe.
9. **Servidor de lenguaje (LSP)**, empezando por los diagnósticos. La evaluación y los requisitos
   que quedan están en [LSP](lsp.md). Hoy no existe.
10. **Formateador.**

## En investigación

Ideas del diseño original cuyo valor o cuya forma no están decididos:

| Idea | Pregunta abierta |
|------|------------------|
| Verificación estática de contratos | ¿Qué parte puede demostrarse sin un demostrador completo, y sin dar falsas garantías? |
| Ejemplos ejecutables en la firma (`example`) | ¿Aportan algo que no den ya las pruebas? |
| Efectos declarados (`uses`) | ¿Compensa la carga de anotarlos? |
| Funciones resueltas por un modelo de IA (`ai fn`, `tool fn`) | ¿Puede un lenguaje determinista incorporar una operación que no lo es, y cómo se prueba? |
| Ediciones estructuradas en los diagnósticos | ¿Qué formato permitiría aplicar una corrección automáticamente con seguridad? |
| **La hipótesis central del proyecto** | ¿Facilitan estas decisiones de diseño el trabajo de las herramientas de IA? **No se ha evaluado.** Requiere un experimento reproducible que compare resultados con y sin ellas; [qué haría falta](ai-tooling.md#tareas-de-referencia) |
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

La web del proyecto (`web/`, en la raíz del repositorio) muestra una versión resumida de esta hoja
de ruta. Este documento es la referencia.
