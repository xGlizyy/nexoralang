# Documentación de NEXORA

NEXORA es un lenguaje de programación nuevo, en una fase temprana de desarrollo. Esta
documentación describe lo que la versión actual hace de verdad: cada programa de ejemplo y cada
salida que aparece en estas páginas se ejecuta en las pruebas automatizadas y se compara con el
resultado real del intérprete.

## Por dónde empezar

| Si quieres… | Lee |
|-------------|-----|
| Instalar NEXORA | [Instalación](installation.md) |
| Escribir y ejecutar tu primer programa | [Primeros pasos](getting-started.md) |
| Ver programas completos | [`examples/`](../examples/README.md) |
| Saber qué **no** hace todavía | [Limitaciones](limitations.md) |

## Guías del lenguaje

| Guía | Contenido |
|------|-----------|
| [Tipos](types.md) | Los tipos, listas `List[T]`, inferencia, anotaciones, operadores, conversiones, tipos refinados (`where`) y registros |
| [Funciones](functions.md) | Parámetros, `return`, rutas de retorno, `if` / `else`, recursividad |
| [Contratos](contracts.md) | `requires` y `ensures`, con la explicación de cada regla |

## Referencia

| Documento | Contenido |
|-----------|-----------|
| [Especificación del lenguaje](language-spec.md) | La referencia formal: léxico, gramática EBNF, tipos, ámbitos, semántica y errores |
| [Referencia de la CLI](cli-reference.md) | Comandos, opciones, formatos de salida y códigos de salida de `nex` |
| [Diagnósticos](diagnostics.md) | Cómo leer un error, categorías y todos los códigos |
| [Herramientas automáticas e IA](ai-tooling.md) | Qué ofrece NEXORA a una herramienta o a un agente, la API de Python y qué no existe |
| [Contexto estructurado](ai-context.md) | `nex context` y `nex symbols`: resumen y símbolos de un programa, sin ejecutarlo |
| [Protocolo JSON](json-protocol.md) | Todos los formatos JSON, sus versiones, sus reglas y sus JSON Schema |
| [Servidor MCP](mcp.md) | Servidor opcional para asistentes de IA compatibles: instalación, herramientas y seguridad |
| [LSP](lsp.md) | Integración con editores: **planificada, no implementada** |
| [Esquema de `nex inspect`](inspect-schema.md) | Todos los nodos y campos del árbol de sintaxis en JSON |
| [Playground](playground.md) | Ejecutar NEXORA desde el navegador: arquitectura, API, límites, aislamiento y despliegue |

## Proyecto

| Documento | Contenido |
|-----------|-----------|
| [Arquitectura](architecture.md) | Las etapas del intérprete, los módulos y dónde añadir funcionalidades |
| [Pruebas](testing.md) | Qué se prueba, cómo ejecutarlo y cobertura |
| [Decisiones técnicas](decisions/README.md) | Por qué el lenguaje es como es, y los cambios incompatibles |
| [Hoja de ruta](roadmap.md) | Qué está hecho y verificado, y qué está pendiente |
| [Limitaciones](limitations.md) | Lo que no existe y los riesgos conocidos |
| [Cambios](../CHANGELOG.md) | Qué ha cambiado en cada versión |
| [Cómo contribuir](../CONTRIBUTING.md) | Entorno de desarrollo y comprobaciones antes de proponer un cambio |
| [Seguridad](../SECURITY.md) | Alcance real de las protecciones y cómo avisar de un problema |

## Estado de cada parte

| Estado | Significado en esta documentación |
|--------|-----------------------------------|
| Sin marca | Implementado y cubierto por pruebas |
| **Experimental** | Implementado y probado, pero puede cambiar de forma incompatible (la API de Python, el servidor MCP y el playground; ninguna parte del lenguaje) |
| **Previsto** | No existe. Solo aparece en [Limitaciones](limitations.md) y en la [hoja de ruta](roadmap.md) |

La documentación está en español. Las palabras del lenguaje y los mensajes de error están en inglés.
