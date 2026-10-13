# Instalación

NEXORA se instala desde el código fuente. No está publicado en PyPI ni en ningún otro repositorio
de paquetes.

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
| Linux | **No comprobado.** Las instrucciones siguen el procedimiento estándar de Python. El flujo de integración continua preparado en `.github/workflows/` ejecutaría las pruebas en Linux, pero todavía no se ha ejecutado nunca |
| macOS | **No comprobado** |
| Python 3.11 y 3.13 | **No comprobado.** El código no usa nada posterior a Python 3.11 |

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
NEXORA 0.2.0
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

Esto crea dos archivos en `dist/`: `nexora-0.2.0-py3-none-any.whl` y `nexora-0.2.0.tar.gz`. El
primero puede instalarse en cualquier entorno con Python 3.11 o superior:

```bash
python -m pip install dist/nexora-0.2.0-py3-none-any.whl
```

El *wheel* contiene solo el intérprete y el comando `nex`. Los ejemplos, la documentación y las
pruebas están en el archivo `.tar.gz` y en el repositorio.

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
python -m pip uninstall nexora
```

O, simplemente, borra la carpeta `.venv`: todo lo instalado está dentro de ella.
