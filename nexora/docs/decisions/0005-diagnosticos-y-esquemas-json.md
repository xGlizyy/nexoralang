# 0005 — Categorías de diagnóstico, esquemas JSON versionados y código de salida 5

- **Estado:** aceptada
- **Versión:** 0.2.0

## Decisión

1. **Cada código de error pertenece a una categoría**: `file`, `lexical`, `syntax`, `semantic`,
   `type`, `runtime` o `contract`. La categoría indica qué etapa encontró el problema.
2. **La cabecera de un diagnóstico de texto incluye la categoría**:
   `type error[E2011]: Type mismatch` en lugar de `error[E2011]: Type mismatch`.
3. **Los códigos no se reutilizan.** Un código que deja de emitirse se retira y queda documentado.
4. **Los documentos JSON llevan un campo `schema`** con nombre y versión: `nexora.diagnostics/1`
   y `nexora.inspect/1`. La versión cambia solo si un campo se elimina, se renombra o cambia de
   significado.
5. **Comando nuevo `nex inspect`**, que escribe el árbol de sintaxis con tipos y posiciones.
6. **`nex run --format json`** escribe los errores como JSON en la salida de error.
7. **Código de salida `5`** para un contrato incumplido.
8. **Las sugerencias (`hint`) solo aparecen cuando una regla las fundamenta**: existe una
   conversión entre los dos tipos, hay un nombre declarado parecido al escrito, o el mensaje
   describe la forma correcta de la construcción.

## Motivos

- Una herramienta puede decidir qué hacer con un error por su categoría sin interpretar el texto ni
  memorizar rangos de códigos.
- Un esquema con versión permite que el formato evolucione sin romper a quien lo consume, y que
  quien lo consume sepa cuándo debe revisarse.
- El árbol que muestra `nex inspect` es el mismo que usan el comprobador y el intérprete: no hay
  una segunda representación que pueda desviarse.
- Las reglas del lenguaje siguen siendo código determinista. Estas salidas son datos para
  herramientas externas; ninguna herramienta, ni ningún modelo, interviene en decidir si un
  programa es válido.

## Cambios incompatibles y cómo actualizar

| Cambio | A quién afecta | Qué hacer |
|--------|----------------|-----------|
| La cabecera de texto empieza por la categoría | Scripts que busquen líneas que **empiecen** por `error[` | Buscar `error[` en cualquier posición o, mejor, usar `--format json` |
| El JSON de `nex check` añade `schema` y, en cada diagnóstico, `category` | Nadie que lea el JSON por nombre de campo; solo quien compare el documento completo | Ignorar los campos desconocidos |
| Un contrato incumplido termina con código `5` | Nadie: los contratos no existían en 0.1 | — |
| `E1104` y `E2003` ya no se emiten | Quien filtrase por esos códigos | Las situaciones que señalaban ahora son código válido |
| `E2004` ya no cubre los tipos de retorno desconocidos | Quien filtrase por `E2004` | Un tipo que no existe es ahora `E2012`; `E2004` queda para "`main` debe devolver `Void`" |

## Alternativas descartadas

- **Renumerar los códigos por categoría** (por ejemplo, mover todos los de tipos a un rango
  propio). Habría roto la estabilidad de los códigos de 0.1; la categoría va en un campo aparte.
- **Un formato de texto para `nex inspect`.** No hay un uso claro todavía; se añade solo JSON.
