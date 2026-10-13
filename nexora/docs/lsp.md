# Language Server Protocol (LSP)

**Estado: planificado. No está implementado.** NEXORA no incluye un servidor LSP, y ningún editor
tiene hoy integración con el lenguaje.

Esta página recoge la evaluación hecha y lo que haría falta, para que quien lo implemente no parta
de cero.

## Por qué no se ha implementado todavía

Se evaluó al final de la fase de herramientas y se decidió no entregar una versión a medias. Un
programa que devuelve diagnósticos sin respetar el protocolo no es un servidor LSP, y uno que lo
respeta necesita resolver bien tres cosas, de las que hoy solo una está resuelta en parte:

1. **Posiciones.** LSP mide las columnas, por defecto, en unidades UTF-16 y desde 0. NEXORA las
   mide en caracteres Unicode y desde 1. La conversión es sencilla para texto ASCII, pero tiene que
   ser exacta también con caracteres fuera del plano básico (emojis), y requiere negociar la
   codificación con el editor.
2. **Código a medio escribir.** Un editor envía el documento en cada pulsación, casi siempre con
   errores. **Resuelto en parte:** con errores de sintaxis NEXORA ya entrega un árbol y unos
   símbolos parciales. Quedan dos huecos: una función cuya declaración tiene un error desaparece
   entera, y con un error léxico (unas comillas sin cerrar, lo más habitual al escribir un texto)
   no hay estructura, así que *hover* e "ir a la definición" desaparecerían en ese momento.
3. **Ciclo de vida.** Versiones de documento, descarte de resultados obsoletos, cancelación y cierre
   ordenado. Es trabajo de protocolo que exige sus propias pruebas.

Se priorizó lo que ya aporta valor a herramientas y agentes: el [protocolo JSON](json-protocol.md),
el [contexto estructurado](ai-context.md) y el [servidor MCP](mcp.md).

## Lo que ya existe y se reutilizaría

Un servidor LSP no necesitaría ninguna lógica nueva del lenguaje:

| Función de LSP | Fuente en NEXORA | ¿Suficiente hoy? |
|----------------|------------------|------------------|
| Diagnósticos (`textDocument/publishDiagnostics`) | `tooling.check_source`: código, categoría, posición de inicio y fin, sugerencia | Sí |
| *Hover* con el tipo de una expresión | El tipo de cada nodo en `tooling.inspect_source` | Sí; parcial con errores de sintaxis, nada con errores léxicos |
| Firma de una función | `signature` en `tooling.get_symbols` | Sí |
| Ir a la definición | `declaration` y `references` en `tooling.get_symbols`, resueltas por el comprobador | Sí; parcial con errores de sintaxis, nada con errores léxicos |
| Buscar referencias | `references` | Sí, dentro del archivo |
| Símbolos del documento | `tooling.get_symbols` | Sí |
| Autocompletado | — | **No.** Completar solo palabras clave sería un autocompletado ficticio; hace falta saber qué nombres son visibles en un punto del código, y eso exige análisis con errores |

## Arquitectura prevista

```text
Editor  ⇄  servidor LSP (nuevo módulo, opcional)  ⇄  nexora.tooling  ⇄  lexer, parser, checker
```

- Un módulo aparte, `src/nexora/lsp_server.py`, con su dependencia declarada como opcional
  (`pip install "nexora[lsp]"`), igual que el servidor MCP. El núcleo no dependería de él.
- Una biblioteca que implemente el protocolo (por ejemplo `pygls`), para no escribir a mano el
  transporte JSON-RPC. Habría que comprobar su versión y su interfaz vigentes antes de empezar.
- Sincronización de documentos completa (el editor envía el texto entero en cada cambio): los
  programas son de un solo archivo y pequeños, y el análisis es rápido.
- Una función de conversión de posiciones, con pruebas propias, en un único lugar.
- Nada de ejecución: el servidor solo analizaría.

## Requisitos previos

En este orden:

1. **Completar la tolerancia a errores.** El árbol parcial con errores de sintaxis ya existe
   (`complete: false`). Falta conservar las funciones con la declaración incompleta y que el
   analizador léxico se recupere de un texto sin cerrar.
2. **Conversión de posiciones a UTF-16**, con pruebas.
3. El servidor, empezando solo por diagnósticos, con pruebas de protocolo: inicialización, apertura,
   cambios con versión, cierre de documento y cierre del servidor.
4. *Hover* y definición, una vez resuelto el punto 1.

## Mientras tanto

Un editor o un script puede obtener hoy los diagnósticos con posiciones exactas ejecutando
`nex check archivo.nex --format json` al guardar. No es LSP ni pretende serlo.
