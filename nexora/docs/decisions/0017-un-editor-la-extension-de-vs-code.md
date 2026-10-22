# 0017 — Un editor: la extensión de VS Code

- **Estado:** aceptada
- **Versión:** 0.10.0 (estado del repositorio; la extensión se distribuye aparte, en su propio `.vsix`)
- **Fecha:** 2026-10-22
- **Rama de trabajo:** `feature/server-hardening`
- **Relacionada con:** la [decisión 0005](0005-diagnosticos-y-esquemas-json.md) (los diagnósticos
  tienen código y categoría estables) y la [0013](0013-listas-y-for.md) (el modelo de tipos que
  sostiene la comprobación). **No modifica ninguna.**
- **Implementación:** el servidor de lenguaje y el formateador están en el núcleo
  (`nexora/src/nexora/lsp.py` y `nexora/src/nexora/formatter.py`), y la extensión, en TypeScript, en
  `vscode-nexora/`. La evidencia está en `tests/test_lsp.py`, `tests/test_formatter.py` y
  `tests/test_vscode_extension.py`.

## Contexto

NEXORA se usa hoy desde la línea de órdenes (`nex check`, `nex run`, `nex test`) y desde el
navegador (el playground). Falta la herramienta de la que todo programador sale: el editor.

Escribir un editor para NEXORA sin el analizador sería escribir un analizador dos veces. El
lenguaje ya tiene todo lo que un editor necesita: un léxico, un analizador sintáctico, un
comprobador de nombres y tipos con sus diagnósticos, y una tabla de símbolos con las
referencias de cada nombre. La [decisión 0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md)
ya obliga a que todo lo que se ejecuta pase por el comprobador; un editor que no lo usara
daría diagnósticos distintos de los de la línea de órdenes, y dos verdades sobre el mismo
programa.

## Decisión

### 1. El servidor de lenguaje es un proceso de Python del propio paquete

`python -m nexora.lsp` habla LSP por la entrada y la salida estándar. Es el mismo patrón que
el [servidor MCP](../mcp.md) del proyecto, y usa la biblioteca estándar: no necesita instalar
nada para funcionar.

El servidor **no reimplementa el lenguaje**. Todo lo que responde sale de
`pipeline.analyze`, el mismo camino que usa `nex check`, así que el código de un diagnóstico
(E2011, E3004…), su categoría, su posición y su sugerencia son los mismos.

### 2. La extensión es TypeScript y solo habla con el servidor

`vscode-nexora/` es una extensión de VS Code de lo habitual: el cliente del protocolo, el
lenguaje, la gramática y los comandos. No contiene una línea de análisis del lenguaje.

### 3. La gramática se escribe sobre el léxico real

La gramática TextMate nombra las palabras clave, los tipos, las funciones integradas y las
palabras reservadas **que el lenguaje tiene hoy**, y una prueba comprueba que la gramática y el
léxico no se separan. Un archivo `.nex` se reconoce sin que nadie lo declare.

### 4. El formateador vive en el lenguaje, no en la extensión

`nexora/src/nexora/formatter.py` reescribe un programa con la forma canónica. Trabaja sobre
los **tokens del léxico**, nunca sobre el texto: solo cambian la sangría y el espaciado, así
que el programa significa lo mismo. No une líneas ni las parte (el lenguaje se escribe por
líneas), no reescribe el interior de un texto y no toca los comentarios.

Un formateador en la extensión habría sido un formateador en TypeScript, con un segundo
léxico que mantener.

### 5. Lo que el editor ofrece

| | |
|---|---|
| Diagnósticos | Los de `nex check`, en el panel *Problems* |
| Autocompletado | Palabras clave, funciones integradas, los nombres en alcance y las palabras reservadas |
| Hover | El tipo de un valor y la firma de una función |
| Ir a definición, referencias, renombrado | Sobre funciones, parámetros y variables |
| Símbolos del documento | Las funciones y las variables, con su tipo |
| Ayuda de firma | Los parámetros de la función que se está llamando |
| Formateador | Documento entero o selección; opcionalmente al guardar |

## Hechos verificados en el repositorio

| Hecho | Dónde |
|-------|-------|
| El comprobador sabe el tipo de cada expresión y cada símbolo con sus referencias | `checker.py` (`CheckedProgram`) |
| Los diagnósticos tienen código, categoría, posición y sugerencia | `diagnostics.py` |
| El MCP ya es un proceso externo del propio paquete | `mcp_server.py` |
| La gramática y el manifiesto se comprueban contra el léxico | `tests/test_vscode_extension.py` |

## Decisiones que se toman aquí, y por qué

| Decisión | Por qué |
|----------|---------|
| El servidor en Python, la extensión en TypeScript | Reutilizar el analizador es lo que hace que los diagnósticos sean los mismos; la extensión es lo que VS Code espera |
| Sin dependencias de Python | El servidor se escribe con la biblioteca estándar: un servidor que no hay que instalar es un servidor que siempre funciona |
| El formateador en el núcleo | Un solo formateador, reutilizable desde la línea de órdenes, y que por construcción no rompe la sintaxis |
| La gramática comprobada contra el léxico | Si el lenguaje añade una palabra clave, la prueba falla hasta que la gramática la nombra |
| El servidor decide el formato | La extensión solo decide si se usa: el formato canónico es una decisión del lenguaje |

## Lo que no garantiza

- El analizador no resuelve todavía los miembros de un registro por tipo, así que la navegación y
  el renombrado no llegan a los campos de un registro.
- No hayCompletion con tipos variables: el tipo de error de un `Ok` lo dice el contexto, y el
  formateador no inventa nada.
- El formateador no reformatea un texto, no mueve comentarios y no reescribe la estructura de
  un programa: solo la sangría y el espaciado.
- La extensión no trae el paquete `nexora` instalado: hace falta un Python con el paquete
  (o el ajuste `nexora.python.path`).

## Fuera del alcance

- Otros editores (Neovim, Emacs, JetBrains): el servidor habla LSP, así que lo que falta es el
  cliente, no el servidor.
- Un lenguaje de servidor para el servidor MCP: es otro protocolo y otra integración.
- Formatear los comentarios, o reescribir el interior de un texto.

## Alternativas descartadas

| Alternativa | Por qué no |
|-------------|-----------|
| Escribir el analizador en TypeScript | Sería un segundo analizador, con otros diagnósticos; el proyecto ya tiene el suyo |
| El servidor en Node, con el analizador invocado como proceso aparte | Cada respuesta costaría un proceso y un análisis; el servidor en Python tiene el analizador en la misma memoria |
| Un formateador en la extensión | Duplicaría el formateador y sería el único que no conoce la gramática del lenguaje |
| Resaltado escrito a mano sin comprobarlo | La gramática se separaría del lenguaje en la primera palabra clave nueva |

## Compatibilidad

- El lenguaje no cambia: el formateador solo reescribe la forma, y las pruebas comprueban que
  los tokens de un programa formateado son los mismos que antes de formatearlo.
- Los diagnósticos del editor son los de la línea de órdenes, con los mismos códigos.
- La extensión no modifica el paquete que se publica: vive en `vscode-nexora/` y se distribuye
  como un `.vsix` aparte.

## Cambios necesarios

- `nexora/src/nexora/lsp.py`: el servidor de lenguaje.
- `nexora/src/nexora/formatter.py`: el formateador.
- `nexora/pyproject.toml`: la orden `nexora-lsp`.
- `vscode-nexora/`: la extensión, con su icono (la misma marca del sitio) y lo que el marketplace
  pide: licencia, bandeja, descripción, categorías y palabras clave.
- `nexora/tests/test_lsp.py`, `test_formatter.py`, `test_vscode_extension.py`: las pruebas.

## Pruebas de regresión previstas

| Archivo | Qué fija |
|---------|----------|
| `tests/test_lsp.py` | Que los diagnósticos del servidor son los de `nex check`, y que el autocompletado, el hover, la definición, las referencias, el renombrado, los símbolos, la firma y el formateo responden lo que deben |
| `tests/test_formatter.py` | Que el formateador no cambia lo que significa un programa (los mismos tokens), que es idempotente y que aguanta todos los ejemplos del repositorio |
| `tests/test_vscode_extension.py` | Que el manifiesto y la gramática siguen al léxico |

## Relación con las decisiones anteriores y el índice

Se añade al índice de decisiones como aceptada. No modifica ninguna: usa el analizador que las
decisiones anteriores definieron.

## Cuestiones que siguen abiertas

- ¿Debería el servidor resolver los campos de un registro por tipo, para que la navegación
  llegue a ellos? Depende del analizador, no del editor.
- ¿Un formateador que reorganice los bloques, como el que tienen algunos lenguajes? El lenguaje
  se escribe por líneas y con un bloque por construcción; reorganizarlo sería decidir sobre el
  lenguaje, no sobre la herramienta.
