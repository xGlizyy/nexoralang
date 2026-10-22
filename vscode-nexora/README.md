# NEXORA para Visual Studio Code

![El icono de la extensión](images/icon.png)

Extensión del lenguaje de programación NEXORA: resaltado, diagnósticos, navegación y
formateador.

No reimplementa el lenguaje. Todas las respuestas salen del mismo analizador que usa la
línea de órdenes (`nex check`), así que lo que el editor dice de un programa es exactamente
lo que dice `nex check`, con los mismos códigos y los mismos textos.

## Qué da

| | |
|---|---|
| Resaltado | Gramática TextMate escrita sobre el léxico real: palabras clave, tipos, funciones integradas, operadores, textos, números y comentarios |
| Diagnósticos | Errores léxicos, sintácticos y semánticos, en el panel *Problems*, con el código (`E2011`), la posición y la sugerencia |
| Autocompletado | Palabras clave, funciones integradas, los nombres que están en alcance y las palabras reservadas |
| Hover | El tipo de un valor y la firma de una función |
| Ir a definición, referencias y renombrado | Sobre funciones, parámetros y variables |
| Símbolos del documento | Las funciones y las variables, con su tipo |
| Ayuda de firma | Los parámetros de la función que se está llamando |
| Formateador | Documento entero o selección, con la forma canónica del lenguaje |

## Qué necesita

- **Python 3.11 o superior** con el paquete `nexora` instalado: el servidor de lenguaje es un
  proceso de Python.

  ```bash
  cd nexora
  python -m pip install -e .
  ```

- **Node.js 18 o superior** solo para compilar la extensión (el `.vsix` ya viene compilado).

## Instalar

1. Compilar y empaquetar:

   ```bash
   cd vscode-nexora
   npm install
   npm run compile
   npm run package        # deja nexora-0.10.0.vsix
   ```

2. Instalarlo:

   ```bash
   code --install-extension nexora-0.10.0.vsix
   ```

   O desde el editor: *Extensions* → *⋯* → *Install from VSIX…*.

## Configurar

| Ajuste | Qué hace | Por defecto |
|---|---|---|
| `nexora.python.path` | El Python que arranca el servidor. Vacío = el `python` del PATH. | `""` |
| `nexora.trace.server` | Cuánto escribe el servidor en el panel de salida: `off`, `messages`, `verbose`. | `off` |
| `nexora.format.enable` | Formatear los documentos con el formateador del lenguaje. | `true` |
| `nexora.format.onSave` | Formatear cada vez que se guarda. | `false` |

Si el Python del PATH no tiene el paquete instalado, la extensión busca el entorno del propio
repositorio (`nexora/.venv`), que es lo habitual cuando se desarrolla dentro del proyecto.

## Publicar en el marketplace de Visual Studio Code

La extensión está preparada para el marketplace: lleva el icono (128×128), la licencia, la
bandeja, la descripción, las categorías, las palabras clave y el aviso para reportar un
problema.

```bash
cd vscode-nexora
npm run compile
npm run package          # comprueba que el paquete está bien
npm run publish:marketplace -- --pat <EL_TOKEN>
```

Hacen falta dos cosas que solo puede hacer quien publica:

1. **Ser dueño del publicador** `nexoralang` en el marketplace (o cambiar `"publisher"` en
   `package.json` por el que ya tengas). Con el publicador `nexoralang` y el nombre `nexora`, la
   extensión es `nexoralang.nexora` en el marketplace.
2. **Un token de acceso** del marketplace: en <https://marketplace.visualstudio.com/manage/publishers>
   se crea, con el alcance *Manage extensions*. Se pasa con `--pat` para que no quede en el
   historial del shell; `vsce publish` lo pide de forma interactiva si no se le da.

La primera publicación tiene que hacer la cuenta de publisher, que pide verificarla a
través de una cuenta de Microsoft. Nada de esto lo puede hacer el repositorio: es una
decisión de quien publica.

Antes de publicar, una comprobación rápida de que el paquete sirve:

```bash
code --install-extension nexora-0.10.0.vsix
```

## Comandos

- **NEXORA: Check the current file** — ejecuta `nex check` sobre el fichero abierto y escribe el
  resultado en un panel de salida.
- **NEXORA: Restart the language server** — lo reinicia.

## Desarrollar

```bash
cd vscode-nexora
npm install
npm run compile      # compila TypeScript a out/
npm run watch        # recompila al guardar
```

Para depurar el servidor de lenguaje:

```bash
cd nexora
python -m nexora.lsp
```

habla el protocolo por la entrada y la salida estándar, así que se puede probar sin el editor.

## Las pruebas

El servidor, el formateador y la extensión se prueban desde la suite del propio lenguaje:

```bash
cd nexora
python -m pytest tests/test_lsp.py tests/test_formatter.py tests/test_vscode_extension.py
```

Ahí se comprueba que los diagnósticos del servidor son los de `nex check`, que el formateador
no cambia lo que significa un programa y que el manifiesto y la gramática de la extensión
siguen al léxico.

## Limitaciones

- El analizador no resuelve todavía los miembros de un registro por tipo (`x.field` se comprueba
  contra el tipo que tiene `x`, no contra el de cada registro posible), así que la navegación y
  el renombrado no llegan a los campos de un registro.
- No hay tipo variable en el lenguaje: `Option[T]` y `Result[T, E]` son los únicos tipos con
  argumentos, y el tipo de error de un `Ok` lo dice el contexto.
- No hay `match`: las variantes se reconocen con funciones.
- El formateador no reescribe el interior de un texto, ni toca los comentarios, ni une ni parte
  líneas: solo la sangría y el espaciado.
