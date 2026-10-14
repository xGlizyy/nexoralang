# Servidor MCP

NEXORA incluye un servidor **opcional** de [Model Context Protocol](https://modelcontextprotocol.io)
(MCP). Permite que un asistente de IA compatible use el análisis de NEXORA como herramientas:
comprobar código, obtener su estructura, sus símbolos y un resumen, y consultar la especificación.

El asistente decide qué código escribir. **Si ese código es válido lo decide NEXORA**, de forma
determinista, con el mismo comprobador que usa `nex check`.

## Estado

| | |
|-|-|
| Implementado | Sí: `src/nexora/mcp_server.py` |
| Probado | Sí, con el protocolo real: `tests/test_mcp.py` arranca el servidor como proceso y habla con él mediante el cliente del SDK oficial |
| SDK | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), versión 2 (probado con la 2.3.0) |
| Transporte | Entrada y salida estándar (*stdio*): el asistente arranca el servidor como proceso local |
| Probado con un asistente real | **Solo con Claude Code**, en una sesión manual ([detalle](#comprobación-en-claude-code)). No es una prueba automatizada. En ningún otro asistente |
| ¿Ejecuta código? | **No.** Ninguna herramienta ejecuta el programa que recibe |

El SDK cambió de interfaz entre sus versiones 1 y 2. Este servidor está escrito para la **2**
(`mcp.server.MCPServer`) y no funciona con la 1.

## Instalación

El SDK no es una dependencia de NEXORA. Se instala aparte, en el mismo entorno:

```bash
python -m pip install -e ".[mcp]"
```

Instala el paquete `mcp` (versión 2) y sus dependencias. NEXORA sigue funcionando igual sin él: solo
el archivo `mcp_server.py` lo importa.

Comprobación:

```bash
nex-mcp
```

El servidor queda esperando mensajes por la entrada estándar; no escribe nada. Ciérralo con Ctrl+C.
`python -m nexora.mcp_server` es equivalente. Si el SDK no está instalado, el comando lo dice y
termina.

## Herramientas

Todas reciben el **código como texto**. Ninguna recibe una ruta, abre un archivo indicado por quien
llama, ni ejecuta nada.

| Herramienta | Argumentos | Devuelve |
|-------------|------------|----------|
| `nexora_check` | `source`, `filename`* | Documento `nexora.diagnostics/1`: `ok` y los diagnósticos |
| `nexora_get_diagnostics` | `source`, `filename`* | Solo `ok`, `count` y la lista de diagnósticos |
| `nexora_inspect` | `source`, `filename`* | Documento `nexora.inspect/2`: el árbol de sintaxis con tipos |
| `nexora_get_context` | `source`, `filename`* | Documento `nexora.context/1`: [resumen técnico](ai-context.md) |
| `nexora_get_symbols` | `source`, `filename`*, `name`*, `function`* | Documento `nexora.symbols/1`: símbolos y referencias |
| `nexora_get_language_spec` | `section`* | Documento `nexora.spec/1`: el índice de la especificación o el texto de una sección |
| `nexora_get_capabilities` | — | Documento `nexora.capabilities/1`: palabras clave, tipos, funciones integradas, códigos de error y límites |

\* opcional.

- `source`: el código NEXORA. Como máximo 256 KiB.
- `filename`: una etiqueta para los resultados (por defecto `source.nex`). Tiene que ser un nombre
  simple terminado en `.nex`; una ruta se rechaza.
- `section`: un identificador tomado de la lista que devuelve la propia herramienta, por ejemplo
  `7-funciones`. No es una ruta: se busca en la lista de títulos de la especificación.

Los formatos están en [Protocolo JSON](json-protocol.md). Cada herramienta devuelve el documento
como contenido estructurado y, además, como texto JSON.

Todas las herramientas se declaran de solo lectura (`readOnlyHint`), no destructivas e idempotentes,
y sin acceso al exterior (`openWorldHint: false`).

### Un programa con errores no es un error de la herramienta

Si el código tiene errores, `nexora_check` **tiene éxito** y devuelve `ok: false` con los
diagnósticos. Una llamada solo falla (`isError`) cuando los argumentos no son válidos:

| Situación | Resultado |
|-----------|-----------|
| Falta `source` o no es un texto | Error: el mensaje de validación del SDK |
| `filename` es una ruta | Error: "'filename' is only a label for the results: a simple name ending in .nex, not a path." |
| `source` supera 256 KiB | Error: "'source' is larger than the limit of 262144 bytes." |
| `name` o `function` no son identificadores | Error: "… must be a NEXORA identifier." |
| `section` parece una ruta o un nombre de archivo | Error: "'section' must be a section id from the list this tool returns." |
| `section` no existe | Error: "The specification has no section with the id '…'." |

Los errores no incluyen trazas ni rutas internas, y una llamada rechazada no interrumpe la sesión.

## Configuración

Cada asistente se configura a su manera. **No existe una configuración universal**: consulta la
documentación del tuyo. En todos los casos hay que indicar la orden que arranca el servidor, y esa
orden tiene que ser la del entorno virtual donde está instalado NEXORA, con su ruta completa.

| Sistema | Orden |
|---------|-------|
| Windows | `C:\ruta\a\nexora\.venv\Scripts\nex-mcp.exe` |
| Linux y macOS | `/ruta/a/nexora/.venv/bin/nex-mcp` |

### Ejemplo: Claude Code

Con su línea de comandos:

```bash
claude mcp add nexora -- /ruta/a/nexora/.venv/bin/nex-mcp
```

O con un archivo `.mcp.json` en la raíz del proyecto:

```json
{
  "mcpServers": {
    "nexora": {
      "command": "/ruta/a/nexora/.venv/bin/nex-mcp",
      "args": []
    }
  }
}
```

### Ejemplo: Claude Desktop

En su archivo `claude_desktop_config.json`, el mismo bloque `mcpServers` del ejemplo anterior.

El bloque `mcpServers` se ha comprobado con Claude Code (ver más abajo). **En Claude Desktop no se
ha probado**: el ejemplo sigue el formato que documenta ese cliente. Si tu versión usa otro formato,
manda su documentación.

### Comprobación en Claude Code

Hecha a mano el 14 de octubre de 2026, en Windows 11, con Claude Code 2.1.296 en modo no
interactivo, el bloque `mcpServers` anterior (con la ruta de `nex-mcp.exe`) y solo tres herramientas
permitidas:

```bash
claude -p "…" --mcp-config mcp.json --strict-mcp-config \
  --allowedTools "mcp__nexora__nexora_get_capabilities,mcp__nexora__nexora_check,mcp__nexora__nexora_get_context"
```

Lo que se observó en el registro de la sesión:

| Paso | Resultado |
|------|-----------|
| Conexión | El servidor apareció como `connected` y el asistente descubrió las siete herramientas |
| `nexora_get_capabilities` | Devolvió el documento `nexora.capabilities/1` |
| `nexora_check` con un programa que pasa un `Text` donde se espera un `Int` | `ok: false`, diagnóstico `E2011` |
| `nexora_check` con el programa corregido por el asistente | `ok: true` |
| `nexora_get_context` | Devolvió el documento `nexora.context/1` |

Qué demuestra: que el servidor negocia el protocolo con un cliente real distinto del SDK y que el
[ciclo previsto](#el-ciclo-previsto) puede recorrerse. Qué **no** demuestra: es una sola sesión,
con un programa de siete líneas; `nexora_inspect`, `nexora_get_symbols`, `nexora_get_diagnostics` y
`nexora_get_language_spec` no se llamaron desde el asistente; y no dice nada sobre la calidad del
código que escribe un modelo. No forma parte de la batería de pruebas, porque exigiría llamar a un
modelo.

### Probarlo sin un asistente

Con el cliente del propio SDK, en Python:

```python
import asyncio, sys
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(command=sys.executable, args=["-m", "nexora.mcp_server"])
    async with Client(server) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])
        result = await client.call_tool("nexora_check", {"source": "fn main() -> Void {\n    print(x)\n}"})
        print(result.structured_content["diagnostics"][0]["code"])   # E2005

asyncio.run(main())
```

Es lo que hacen las pruebas de `tests/test_mcp.py`.

## El ciclo previsto

El servidor está pensado para este ciclo de trabajo de un agente:

1. `nexora_get_capabilities` o `nexora_get_language_spec`: las reglas del lenguaje, de la fuente oficial.
2. `nexora_get_context`: la estructura del programa que va a modificar.
3. El agente escribe o cambia el código. Esa decisión es suya.
4. `nexora_check`: el análisis estático.
5. Lee los diagnósticos: código, categoría, posición exacta y, si la hay, sugerencia.
6. Corrige y vuelve al paso 4, hasta que `ok` sea `true` o hasta el límite de intentos que se fije.

NEXORA no aplica cambios, no reescribe el código y no decide cuándo parar: aporta hechos
comprobables en cada vuelta.

## Seguridad

Lo que hace el servidor, y lo que comprueban sus pruebas:

- **No ejecuta el código que recibe.** No existe ninguna herramienta de ejecución. Una prueba envía
  a cada herramienta un programa que imprime, divide por cero y entra en recursividad infinita, y
  todas responden de inmediato que es válido, sin efectos.
- **No abre archivos indicados por quien llama.** El código llega como texto. `filename` se valida
  como nombre simple. La única lectura de disco es la especificación del propio proyecto, en una
  ruta fija que no depende de ningún argumento.
- **No ejecuta órdenes** ni accede a la red.
- **Valida los argumentos** y limita el tamaño del código.
- **No expone variables de entorno, secretos ni rutas internas** en sus respuestas.
- **Lo que hay dentro de un programa son datos.** Un comentario o un texto que diga "ignora tus
  instrucciones" se analiza como cualquier otro; no cambia el comportamiento del servidor. Una
  prueba lo comprueba.

Lo que **no** cubre:

- **El servidor no es una sandbox** y no hace falta que lo sea, porque no ejecuta los programas que
  analiza. Lo único que evalúa son las condiciones de los tipos refinados sobre constantes: expresiones
  sin llamadas a funciones del programa y con el trabajo acotado (`E2019`). Pero se ejecuta con los
  permisos del usuario que lo arranca.
- **Los permisos que el asistente pida al usuario no son una medida de seguridad de NEXORA.** Que un
  asistente pregunte antes de llamar a una herramienta es cosa del asistente.
- **Los resultados vuelven al modelo.** El árbol y los diagnósticos contienen fragmentos del código
  analizado (nombres, textos). Si ese código contiene instrucciones dirigidas a un modelo, el
  servidor las devuelve como datos, pero es el asistente quien debe tratarlas como tales.
- El análisis de un programa muy grande consume tiempo y memoria; el único límite es el tamaño del
  código (256 KiB).

### Por qué no hay una herramienta para ejecutar

Ejecutar código suministrado por un modelo es un riesgo distinto del de analizarlo: un programa
puede no terminar o consumir memoria sin límite. Hacerlo bien exige el aislamiento descrito en
[Playground](playground.md#seguridad-y-aislamiento) (proceso aparte, límites, contenedor), y
ofrecerlo por MCP sería una decisión de diseño aparte. En esta versión **no existe**, y no se
activa con ninguna opción.

## Limitaciones

- En un asistente real solo se ha comprobado una vez, a mano, con Claude Code. No se ha probado en
  Claude Desktop ni en ningún otro cliente.
- Solo transporte *stdio*. No hay servidor HTTP.
- Solo herramientas: no expone recursos ni *prompts* de MCP.
- La especificación solo está disponible si NEXORA se instaló desde el código fuente (modo
  desarrollo). Instalado desde un paquete *wheel*, `nexora_get_language_spec` responde
  `available: false`, porque el *wheel* no incluye la documentación.
- La especificación está en español.
- Depende de la versión 2 del SDK, que es reciente; una versión 3 podría requerir cambios.
