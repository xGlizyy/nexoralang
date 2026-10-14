# NEXORA

**Un lenguaje de programación nuevo, con sintaxis y reglas propias, que explora cómo estructurar
los programas para que sean más fáciles de analizar por personas y por herramientas automáticas.**

Este directorio contiene el núcleo del lenguaje: su intérprete de referencia, la herramienta de
línea de comandos `nex`, la especificación, los ejemplos y las pruebas.

<!-- nex:run -->
```nex
type Grade = Float where value >= 0.0 and value <= 100.0, "A grade goes from 0 to 100"

fn average(total: Int, count: Int) -> Grade {
    requires count > 0, "An average needs at least one mark"
    return Grade(to_float(total) / to_float(count))
}

fn main() -> Void {
    let mean = average(270, 4)
    if mean >= 50.0 {
        print("Passed with " + to_text(mean))
    } else {
        print("Failed")
    }
}
```

```text
Passed with 67.5
```

## Visión y motivación

La mayoría de los lenguajes se diseñaron para que una persona diera instrucciones a una máquina.
Hoy el código también lo generan, lo leen y lo revisan sistemas de inteligencia artificial.
NEXORA parte de una pregunta: **¿cómo debería ser un lenguaje pensado para ese trabajo compartido?**

En esta versión, la pregunta se concreta en decisiones de diseño comprobables:

- **Nada implícito.** No hay conversiones automáticas entre tipos; todo cambio de tipo se escribe.
- **Un nombre, un significado.** Dentro de una función un nombre no se redefine ni se oculta.
- **Lo que puede comprobarse antes de ejecutar, se comprueba antes.** Todos los errores de tipos se
  detectan sin ejecutar el programa.
- **Las reglas forman parte del código.** Es la característica que distingue a NEXORA: una función
  declara qué espera y qué promete (contratos), un tipo declara qué valores admite (tipos
  refinados), y cada regla puede llevar su explicación. Cuando una regla se incumple, el diagnóstico
  dice cuál, dónde, con qué valores y por qué existe
  ([decisión 0006](docs/decisions/0006-requisitos-verificables.md)).
- **Las herramientas reciben datos, no texto.** El programa y sus errores pueden obtenerse en JSON,
  con un esquema versionado.

Estas decisiones son una **hipótesis de trabajo**. No existe ninguna evaluación que demuestre que
facilitan el trabajo de una herramienta de IA, y este proyecto no afirma que NEXORA sea más rápido,
más seguro, más productivo ni mejor que ningún otro lenguaje.

NEXORA no incluye ni llama a ningún modelo de IA. Sus reglas son código determinista que funciona
sin conexión. Lo que hay y lo que no, con precisión: [Herramientas automáticas e IA](docs/ai-tooling.md).

## Estado

**Versión 0.3.1. Proyecto en fase temprana**, anterior a la 1.0: el lenguaje puede cambiar de forma
incompatible y no es apto para uso en producción.

| Estado | Qué incluye |
|--------|-------------|
| **Implementado y probado** | Tipos estáticos `Int`, `Float`, `Bool`, `Text` y `Void`, con inferencia y anotaciones · **tipos refinados** (`type Percent = Int where ...`): las constantes se comprueban sin ejecutar y el resto con `Percent(x)` al ejecutar · **contratos** (`requires`, `ensures`), estables desde la 0.3, comprobados al ejecutar · explicación de cada regla en los diagnósticos · variables inmutables y ámbitos · aritmética, comparaciones y lógica · conversiones explícitas · funciones con parámetros y `return` · `if` / `else` · recursividad · análisis estático de nombres, tipos y rutas de retorno · comandos `run`, `check`, `inspect`, `context` y `symbols` · diagnósticos con código y categoría, en texto y en JSON · formatos JSON versionados con JSON Schema |
| **Experimental** | API de Python `nexora.tooling` · servidor MCP opcional (probado con el cliente del SDK y, a mano, en Claude Code; en ningún otro asistente) · [playground](docs/playground.md) web, solo en local |
| **Previsto** (no existe) | Bucles, variables reasignables, listas y otros tipos compuestos, operaciones sobre textos, entrada de datos, módulos, servidor de lenguaje (LSP) |
| **En investigación** (no existe) | Verificación estática de contratos, características de IA dentro del lenguaje, y la evaluación de la hipótesis del proyecto |

Detalle: [hoja de ruta](docs/roadmap.md) y [limitaciones](docs/limitations.md).

## Requisitos

- Python 3.11 o superior.
- Nada más para usar el lenguaje: el intérprete solo usa la biblioteca estándar de Python.
- Conexión a internet solo durante la instalación.

## Instalación

Desde este directorio (`nexora/`):

```bash
python -m venv .venv
```

Activa el entorno virtual:

| Sistema | Comando |
|---------|---------|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Linux y macOS | `source .venv/bin/activate` |

Instala y comprueba:

```bash
python -m pip install -e .
nex --version
```

```text
NEXORA 0.3.1
```

El comando `nex` queda instalado dentro del entorno virtual, no en todo el sistema: solo está
disponible con el entorno activado. `python -m nexora` hace lo mismo que `nex`.

Comprobado en Windows 11 con Python 3.12. Linux y macOS no se han probado todavía. Guía completa,
alternativas y solución de problemas: [Instalación](docs/installation.md).

## Primer programa

Guarda esto en un archivo `program.nex`:

<!-- nex:run -->
```nex
fn square(n: Int) -> Int {
    return n * n
}

fn main() -> Void {
    let side = 12
    print("Side: " + to_text(side))
    print("Area: " + to_text(square(side)))
}
```

Ejecútalo:

```bash
nex run program.nex
```

```text
Side: 12
Area: 144
```

Si el programa tiene un error, NEXORA lo explica **antes de ejecutar nada**:

<!-- nex:check-fails -->
```nex
fn square(n: Int) -> Int {
    return n * n
}

fn main() -> Void {
    print(square(2.5))
}
```

```text
type error[E2011]: Type mismatch
 --> program.nex:6:18
  |
6 |     print(square(2.5))
  |                  ^^^ Expected Int, found Float
  = note: This is the argument for 'n' in: fn square(n: Int) -> Int
  = hint: Convert the Float explicitly with to_int(...), which drops the fractional part.

error: program.nex: check failed with 1 error
```

Siguiente paso: [Primeros pasos](docs/getting-started.md), una guía que recorre variables, tipos,
funciones y cómo leer un error.

## Comandos

| Comando | Qué hace |
|---------|----------|
| `nex run archivo.nex` | Analiza el programa y, si no tiene errores, lo ejecuta |
| `nex check archivo.nex` | Comprueba sintaxis, nombres y tipos **sin ejecutar** el programa |
| `nex inspect archivo.nex` | Escribe la estructura del programa en JSON, **sin ejecutarlo** |
| `nex context archivo.nex` | Resume el programa: firmas, contratos, llamadas, características. **Sin ejecutarlo** |
| `nex symbols archivo.nex` | Lista funciones, parámetros y variables, y dónde se usa cada uno. **Sin ejecutarlo** |
| `nex --version` | Muestra la versión |
| `nex --help` | Muestra la ayuda |

`nex check`, `nex run`, `nex context` y `nex symbols` aceptan `--format json` para entregar el
resultado como datos.

| Código de salida | Significado |
|------------------|-------------|
| `0` | Correcto |
| `1` | El programa tiene errores (detectados sin ejecutar) |
| `2` | Uso incorrecto del comando |
| `3` | El programa falló durante la ejecución |
| `4` | El archivo no pudo leerse |
| `5` | El programa incumplió un contrato |
| `70` | Error interno de NEXORA |
| `130` | Interrumpido con Ctrl+C |

Referencia completa: [CLI](docs/cli-reference.md).

## Estructura para personas y para herramientas

El mismo análisis produce dos lecturas. Una para personas: el diagnóstico de texto del apartado
anterior. Y otra para programas, con `nex check program.nex --format json`: el mismo error como
datos, con un código que no cambia (`E2011`), una categoría (`type`), la posición exacta de
principio a fin y, cuando existe una corrección fundamentada, una sugerencia.

`nex inspect` entrega además el árbol de sintaxis completo, con el tipo de cada expresión;
`nex symbols`, cada nombre declarado y sus usos; y `nex context`, un resumen breve del programa.
Ninguno de estos comandos ejecuta el programa, y en ninguno interviene un modelo de IA.

```bash
nex context examples/contracts.nex
nex symbols examples/functions.nex --name factorial
nex check examples/invalid/type_errors.nex --format json
```

Las mismas salidas están disponibles desde Python (`nexora.tooling`, experimental) y, de forma
opcional, como herramientas para un asistente compatible con MCP:

```bash
python -m pip install -e ".[mcp]"
nex-mcp
```

El servidor MCP solo analiza: no ejecuta programas ni abre archivos. Está probado con el cliente
del SDK oficial y, a mano, en una sesión de Claude Code; no en otros asistentes. No existe todavía un servidor de lenguaje (LSP).

| | |
|-|-|
| [Herramientas automáticas e IA](docs/ai-tooling.md) | Qué hay, qué no, la API de Python y el ciclo de un agente |
| [Contexto estructurado](docs/ai-context.md) | `nex context` y `nex symbols` |
| [Protocolo JSON](docs/json-protocol.md) | Formatos, versiones y JSON Schema |
| [Servidor MCP](docs/mcp.md) | Instalación, herramientas, configuración y seguridad |
| [LSP](docs/lsp.md) | Planificado, no implementado |

## Ejemplos

En [`examples/`](examples/README.md) hay once programas: seis válidos, tres con errores detectados
sin ejecutar y dos que fallan al ejecutarse. Todos se ejecutan en las pruebas, que comparan su
salida con la registrada.

```bash
nex run examples/functions.nex
nex check examples/invalid/type_errors.nex
nex run examples/failing/contract_violation.nex
```

## Pruebas

Con el entorno virtual activado y las herramientas de desarrollo instaladas
(`python -m pip install -e ".[dev]"`):

```bash
python -m pytest                 # todas las pruebas
python -m pytest --cov           # con medición de cobertura
python -m ruff check src tests   # análisis estático del código
```

Qué cubren y cómo interpretarlas: [Pruebas](docs/testing.md).

## Documentación

| | |
|-|-|
| [Índice](docs/index.md) | Todas las páginas |
| [Primeros pasos](docs/getting-started.md) | Tutorial |
| [Tipos](docs/types.md) · [Funciones](docs/functions.md) · [Contratos](docs/contracts.md) | Guías del lenguaje |
| [Especificación](docs/language-spec.md) | Referencia formal: gramática, tipos, semántica |
| [CLI](docs/cli-reference.md) · [Diagnósticos](docs/diagnostics.md) | Referencia de la herramienta y de los errores |
| [Arquitectura](docs/architecture.md) | Cómo está construido el intérprete |
| [Limitaciones](docs/limitations.md) · [Hoja de ruta](docs/roadmap.md) | Qué falta |
| [Cambios](CHANGELOG.md) · [Decisiones](docs/decisions/README.md) | Historial y motivos |

Todos los programas de ejemplo de la documentación se ejecutan en las pruebas, y la salida
mostrada se compara con la real.

## Contribuir

El proyecto está preparado para recibir colaboración. Todavía no tiene un repositorio público ni
un canal de contacto.

- [Cómo contribuir](CONTRIBUTING.md): entorno de desarrollo, cómo añadir una funcionalidad y qué
  comprobaciones deben pasar.
- [Seguridad](SECURITY.md): qué protege el proyecto, qué no, y cómo avisar de un problema.
- [Código de conducta](CODE_OF_CONDUCT.md).

## Licencia

[MIT](LICENSE).
