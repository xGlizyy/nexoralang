# Instalación

NEXORA se instala desde el código fuente. **Todavía no está publicado** en PyPI ni en npm: los
paquetes para ambos están preparados y probados en local, pero no subidos
([paquetes para pip y npm](#paquetes-para-pip-y-npm)).

## Requisitos

- **Python 3.11 o superior.** Compruébalo con `python --version` (en algunos sistemas, `python3 --version`).
- `pip` y el módulo `venv`, que vienen con Python. En Debian y Ubuntu puede hacer falta instalarlos
  aparte: `sudo apt install python3-venv python3-pip`.
- Conexión a internet **solo durante la instalación**, para que `pip` descargue la herramienta de
  empaquetado (`setuptools`) y, si vas a ejecutar las pruebas, `pytest`, `pytest-cov` y `ruff`.

El intérprete no tiene dependencias: solo usa la biblioteca estándar de Python. Una vez instalado,
NEXORA funciona sin conexión.

## Qué se ha comprobado

| Entorno | Estado |
|---------|--------|
| Windows 11, Python 3.12 | **Comprobado**: instalación en modo desarrollo en un entorno limpio, instalación desde el paquete generado, y batería de pruebas completa |
| Windows 11, Node.js 24, paquete de npm | **Comprobado**: generado con `npm pack`, instalado desde el archivo y usado. No publicado |
| Linux (Ubuntu 24.04 en WSL 2), Python 3.12 | **Comprobado** el 17 de octubre de 2026: batería de pruebas completa, sin ninguna omitida, con un usuario que no es root; paquete generado e instalado desde el archivo en un entorno limpio, y `nex run` usado. Otras distribuciones y Linux sin WSL, no comprobados |
| Linux, Node.js 24, paquete de npm | **Comprobado**: generado con `npm pack`, instalado desde el archivo y usado con `npx nex`. No publicado |
| macOS | **Ejecutado** en `macos-latest` por la [integración continua](testing.md#integración-continua): batería de pruebas con Python 3.11, 3.12 y 3.13, el paquete de npm y el servidor. En un Mac local, no comprobado |
| Python 3.11 y 3.13 | **Ejecutados** en Linux, Windows y macOS por la integración continua, y **comprobados** a mano en Linux (3.11.17 y 3.13.16): batería de pruebas completa, sin instalar el paquete generado |

## Instalación paso a paso

Todos los comandos se ejecutan desde el directorio `nexora/` del repositorio (el que contiene
`pyproject.toml`).

### 1. Crea un entorno virtual

```bash
python -m venv .venv
```

Un entorno virtual es una carpeta (`.venv`) con una copia aislada de Python. NEXORA se instala
dentro de ella y no toca el resto del sistema.

### 2. Activa el entorno

| Sistema | Comando |
|---------|---------|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Linux y macOS (bash, zsh) | `source .venv/bin/activate` |

Hay que activarlo en cada terminal nueva. Con el entorno activado, el nombre `(.venv)` suele
aparecer al principio de la línea de comandos.

### 3. Instala NEXORA

Para usar el lenguaje:

```bash
python -m pip install -e .
```

Para trabajar en el proyecto (añade las herramientas de pruebas y de análisis):

```bash
python -m pip install -e ".[dev]"
```

La opción `-e` instala en modo desarrollo: el comando `nex` usa directamente los archivos de
`src/`, de modo que cualquier cambio en el código tiene efecto sin reinstalar.

### 4. Comprueba la instalación

```bash
nex --version
nex run examples/hello.nex
```

Resultado esperado:

```text
NEXORA 0.9.0
Hello from NEXORA
```

## Dónde queda el comando `nex`

El comando `nex` se instala **dentro del entorno virtual**, no en todo el sistema. Solo está
disponible en las terminales donde el entorno está activado.

Sin activar el entorno hay dos alternativas:

| Alternativa | Windows | Linux y macOS |
|-------------|---------|---------------|
| Llamar al comando por su ruta | `.venv\Scripts\nex.exe run programa.nex` | `.venv/bin/nex run programa.nex` |
| Usar el módulo de Python del entorno | `.venv\Scripts\python.exe -m nexora run programa.nex` | `.venv/bin/python -m nexora run programa.nex` |

`python -m nexora` hace exactamente lo mismo que `nex`.

## Instalar desde un paquete generado

El proyecto puede empaquetarse en un archivo instalable (*wheel*). No se publica en ningún sitio:
se genera y se instala en local.

```bash
python -m pip install build
python -m build
```

Esto crea dos archivos en `dist/`: `nexora_lang-0.9.0-py3-none-any.whl` y `nexora_lang-0.9.0.tar.gz`. El
primero puede instalarse en cualquier entorno con Python 3.11 o superior:

```bash
python -m pip install dist/nexora_lang-0.9.0-py3-none-any.whl
```

El *wheel* contiene solo el intérprete y el comando `nex`. Los ejemplos, la documentación y las
pruebas están en el archivo `.tar.gz` y en el repositorio.

## Paquetes para pip y npm

El comando `nex` puede distribuirse por dos vías. El paquete se llama **`nexora-lang`** en las dos,
porque el nombre `nexora` ya pertenece a otros proyectos en PyPI y en npm. El comando sigue siendo
`nex`.

**Ninguno de los dos está publicado.** Las órdenes `pip install nexora-lang` y
`npm install -g nexora-lang` no funcionarán hasta que alguien con cuenta en esos registros los suba.
Lo que sí se ha comprobado, en Windows 11, es que los dos paquetes se generan, se instalan desde el
archivo local y dejan un comando `nex` que funciona.

| | pip | npm |
|-|-----|-----|
| Paquete | `nexora-lang` (directorio `nexora/`) | `nexora-lang` (directorio `npm/`, en la raíz del repositorio) |
| Qué contiene | El intérprete y los comandos `nex` y `nex-mcp` | Una copia del intérprete y un lanzador en JavaScript |
| Qué necesita | Python 3.11 o superior | Node.js 18 o superior **y Python 3.11 o superior** |
| Una vez publicado | `pipx install nexora-lang` | `npm install -g nexora-lang` |

El paquete de npm **no elimina la dependencia de Python**: el intérprete está escrito en Python. El
lanzador busca un Python 3.11+ en la máquina (`py -3` en Windows, `python3`, `python` y, en Windows,
las carpetas del instalador oficial), ejecuta con él el intérprete incluido en el paquete, y pasa
tal cual los argumentos, la salida y el código de salida. Si no encuentra ninguno lo explica y
termina con el código `127`. La variable `NEXORA_PYTHON` permite elegir uno. No incluye el servidor
MCP.

### Generar e instalar el paquete de npm en local

Desde el directorio `npm/`:

```bash
npm test                 # copia el intérprete al paquete y ejecuta las pruebas del lanzador
npm pack                 # genera nexora-lang-0.9.0.tgz
npm install -g ./nexora-lang-0.9.0.tgz
nex --version
```

### Publicar

Requiere una cuenta en cada registro y es irreversible en la práctica (una versión publicada no
puede reutilizarse). Antes, la batería de pruebas tiene que pasar.

```bash
# PyPI, desde nexora/
python -m pip install build twine
python -m build
python -m twine upload dist/*

# npm, desde npm/
npm login
npm publish
```

Las credenciales se introducen al ejecutar esas órdenes; no se guardan en el repositorio.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---------|------------------|
| `nex` no se reconoce como comando | El entorno virtual no está activado en esa terminal. Actívalo (paso 2) o usa la ruta completa |
| En Windows, `python` abre la Microsoft Store o dice que no se encontró Python | Python no está instalado, o solo existe el acceso directo de la Store. Instálalo desde [python.org](https://www.python.org/downloads/) y abre una terminal nueva |
| En Linux o macOS, `python` no existe | Usa `python3` para crear el entorno (`python3 -m venv .venv`). Una vez activado, `python` ya funciona |
| PowerShell se niega a ejecutar `Activate.ps1` ("la ejecución de scripts está deshabilitada") | Ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, o usa `nex` por su ruta sin activar el entorno |
| `pip` dice `requires a different Python` | La versión de Python es anterior a la 3.11. Crea el entorno con una versión más reciente |
| `error: externally-managed-environment` | Estás instalando fuera de un entorno virtual. Crea y activa uno (pasos 1 y 2) |
| `The virtual environment was not created successfully because ensurepip is not available` | Falta el paquete `python3-venv` (Debian, Ubuntu) |
| `pip` no puede descargar `setuptools` | La instalación necesita internet la primera vez. Después ya no |
| Los acentos o el símbolo `✓` se ven mal al redirigir la salida en Windows | La salida de `nex` es siempre UTF-8. Configura la terminal para UTF-8: `[Console]::OutputEncoding = [Text.Encoding]::UTF8` en PowerShell |
| `nex --version` muestra una versión antigua | Hay otra instalación de NEXORA en ese entorno. Reinstala con `python -m pip install -e .` |

## Desinstalar

```bash
python -m pip uninstall nexora-lang
```

O, simplemente, borra la carpeta `.venv`: todo lo instalado está dentro de ella.
