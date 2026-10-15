# Limitaciones

Lo que NEXORA **no** hace en la versión 0.5.1, y los riesgos que conviene conocer antes de usarlo.
Nada de lo que aparece aquí como "no existe" funciona hoy, aunque se mencione en el borrador de
diseño o en la hoja de ruta.

## Estado general

NEXORA es un proyecto en una fase temprana (anterior a la versión 1.0):

- El lenguaje puede cambiar de forma incompatible entre versiones.
- **No es apto para uso en producción.**
- No ha sido utilizado por nadie fuera de su desarrollo, ni auditado por terceros.
- No se ha medido su rendimiento ni se ha comparado con ningún otro lenguaje.

## Lo que el lenguaje no tiene

| Falta | Consecuencia |
|-------|--------------|
| `for`, `break` y `continue` | Se escribe un `while` con un contador; para salir antes, la condición o `return` |
| Asignaciones compuestas (`+=`, `++`) | Se escribe `x = x + 1` |
| Reasignar un parámetro | Se copia antes en una `var` |
| Un bucle sin medida (`decreases`) | Todo bucle declara por qué termina; si no puede escribirse una medida, se pone un máximo de vueltas explícito (`decreases limit - turns`) |
| `if` como expresión | `if` no puede usarse para dar valor a una variable |
| Tipos compuestos: listas, mapas, registros, enumeraciones, opcionales | Solo existen `Int`, `Float`, `Bool` y `Text` |
| Tipos definidos por el usuario y genéricos | |
| `trim`, mayúsculas, `split`, `replace`, búsqueda de posiciones | Existen `Text.length`, `Text.slice`, `Text.contains`, `Text.starts_with`, `Text.ends_with` y el orden entre textos ([especificación](language-spec.md), 8.1) |
| Grafemas y normalización Unicode | Un carácter es un punto de código: una `e` con el acento combinado cuenta 2, y dos textos que se ven iguales pueden ser distintos para `==` |
| Orden alfabético según el idioma | El orden entre textos es el de los puntos de código: `"Z" < "a"` |
| Interpolación de textos | Se usa `+` y `to_text` |
| Leer números con espacios, `+`, separadores o en otras bases | `Int.parse` y `Float.parse` solo leen una forma (`"-42"`, `"2.5e3"`) |
| Operador de resto (`%`) y potencias | |
| Funciones matemáticas (raíz, redondeo, valor absoluto…) | Hay que escribirlas |
| Entrada de datos: teclado, argumentos, archivos, red | Un programa solo puede escribir con `print` |
| Módulos e importaciones | Un programa es un único archivo |
| Funciones como valores, funciones anónimas, sobrecarga, valores por defecto | |
| Avisos (*warnings*) | Todo diagnóstico es un error. Una variable sin usar no produce ningún aviso |
| Comentarios de bloque, textos de varias líneas | |
| Literales hexadecimales o con exponente (`1e-3`) | |

Con estas limitaciones NEXORA sirve para programas pequeños de cálculo y para estudiar el propio
lenguaje. No sirve todavía para escribir aplicaciones.

## Límites de la implementación

| Límite | Valor | Qué ocurre al superarlo |
|--------|-------|-------------------------|
| Llamadas anidadas | 1000 (contando `main`) | Error de ejecución `E3004` |
| Llamadas anidadas con expresiones muy profundas | Menos de 1000 | El mismo error `E3004`; el mensaje indica cuántas había |
| Anidamiento de paréntesis, bloques, `else if` u operadores unarios | 64 niveles | Error `E1105` |
| Profundidad de una expresión (por ejemplo, términos de una suma) | 256 | Error `E1105` |
| Trabajo de `nex check` comprobando constantes contra tipos refinados | 100 000 nodos de condición evaluados | Error `E2019`; el programa no se ejecuta |
| Errores comunicados por etapa y archivo | 100 | El análisis se detiene; el resumen lo indica |
| Rango de `Int` | 64 bits con signo | Error de ejecución `E3002` |
| Entero literal más pequeño | `-9223372036854775807` | `-9223372036854775808` solo puede obtenerse calculándolo: `-9223372036854775807 - 1` |

No hay límite de tiempo ni de memoria: un programa puede tardar o consumir memoria sin que el
intérprete lo detenga. Ningún programa se queda repitiendo algo para siempre: una recursividad sin
fin se detiene con `E3004` y un bucle sin fin, con `E4006` (su medida deja de disminuir). Pero un
programa que termina puede tardar mucho: una recursividad que se ramifica (`fib(40)`) o un bucle
con una medida inicial enorme. Se puede interrumpir con Ctrl+C. Tampoco `nex test` tiene límites
de tiempo por ejemplo. Si Python se queda sin memoria mientras el programa se ejecuta, el programa
termina con el error `E3007`; pero en Linux el sistema puede matar el proceso antes, sin ningún
mensaje ([decisión 0009](decisions/0009-memoria-agotada.md)).

## Rendimiento

El intérprete recorre el árbol de sintaxis directamente, sin compilar. Es una implementación de
referencia, pensada para ser correcta y fácil de entender, no rápida. **No se ha medido** su
velocidad, y no se hace ninguna afirmación sobre ella.

## Contratos y tipos refinados

Estables desde la 0.3.0. Sus límites, en detalle, en [contratos](contracts.md#limitaciones) y en
[tipos refinados](types.md#tipos-refinados):

- Los contratos se comprueban al ejecutar, en las llamadas que se ejecutan. No se demuestran.
- `nex check` no afirma que un contrato se cumpla.
- De los tipos refinados, `nex check` solo comprueba las constantes. Un valor calculado se comprueba
  con `Percent(x)` al ejecutar, y `nex check` no afirma que vaya a cumplir la condición.
- La condición de un tipo refinado no puede llamar a funciones del programa.
- No hay alias de tipos sin condición, ni forma de comprobar un valor sin detener el programa si
  falla (no existe `Result`).
- No pueden desactivarse.

## Herramientas

- La única interfaz estable es la línea de comandos. La API de Python (`nexora.tooling`) es
  **experimental**; el resto de módulos de `src/nexora/` son internos y pueden cambiar sin aviso.
- No hay formateador, depurador ni integración con editores. El servidor de lenguaje (LSP) está
  **planificado, no implementado**: [LSP](lsp.md).
- Con errores de sintaxis, `nex inspect`, `nex context` y `nex symbols` devuelven una estructura
  **parcial**: faltan las sentencias con errores y, entera, cualquier función cuya declaración tenga
  uno; y solo se comunican los errores de sintaxis. Con errores léxicos (un texto sin cerrar, un
  carácter no válido) no devuelven estructura. Nunca incluyen los comentarios.
- `nex context` y `nex symbols` describen un único archivo, porque el lenguaje no tiene módulos.
- Las sugerencias de los diagnósticos son texto para personas, no ediciones aplicables
  automáticamente.
- El servidor MCP se prueba de forma automática con el cliente del SDK oficial. En un asistente
  real solo se ha comprobado **una vez, a mano, en Claude Code**; en ningún otro. Solo analiza: no ejecuta programas. Depende de la versión 2 del SDK de Python de MCP. Sus
  límites, en [Servidor MCP](mcp.md#limitaciones).
- La especificación solo está disponible para las herramientas (`get_language_spec`) si NEXORA se
  instaló desde el código fuente; el paquete *wheel* no incluye la documentación.
- NEXORA no llama a ningún modelo de IA, y **ningún modelo se ha evaluado** con estas herramientas.
  Lo que hay son datos estructurados y deterministas:
  [Herramientas automáticas e IA](ai-tooling.md).

## Seguridad

Un programa NEXORA solo puede calcular y escribir texto: el lenguaje no tiene ninguna construcción
para leer archivos, usar la red o ejecutar otros programas, y las pruebas comprueban que el
intérprete no usa `eval` ni `exec`. Aun así:

- **NEXORA no es un entorno aislado (*sandbox*).** Se ejecuta dentro de un proceso de Python normal,
  con los permisos de quien lo lanza.
- **No hay límites de tiempo ni de memoria** al usar `nex`. Un programa malintencionado puede hacer
  que el proceso consuma recursos.
- El [playground](playground.md) sí ejecuta cada programa en un proceso aparte con límites de
  tiempo, de salida y de tamaño, pero **eso tampoco es una sandbox**: el aislamiento con contenedor
  está configurado y **no se ha probado**, y los límites de memoria y CPU del sistema operativo solo
  existen en Linux y macOS, donde no se han ejecutado. No está desplegado en ningún servidor.
- El servidor MCP no ejecuta programas, pero se ejecuta con los permisos de quien lo arranca.
- No ha sido auditado.

No ejecutes programas NEXORA que no sean de confianza en un entorno donde un consumo excesivo de
recursos sea un problema. El alcance exacto está en [`SECURITY.md`](../SECURITY.md).

## Plataformas

Solo se ha comprobado en Windows 11 con Python 3.12. Linux, macOS y otras versiones de Python no se
han probado todavía; ver [Instalación](installation.md#qué-se-ha-comprobado).

## Proyecto

- Se distribuye con la licencia MIT: sin garantía de ningún tipo.
- No hay repositorio público, ni canal de contacto, ni proceso de publicación de versiones.
- La integración continua está preparada pero no se ha ejecutado nunca.
- Los ejemplos de `ejemplos/*.nx` y el documento `docs/fase-1-diseno.md`, en la raíz del
  repositorio, describen un diseño anterior y más amplio. Usan una sintaxis que el intérprete **no**
  admite. La referencia válida es la [especificación](language-spec.md).
