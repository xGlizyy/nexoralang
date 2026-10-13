# Cómo contribuir a NEXORA

Gracias por tu interés. Esta guía explica cómo preparar el entorno, qué comprobaciones tiene que
pasar un cambio y cómo mantener sincronizados el código, la especificación y los ejemplos.

## Antes de empezar

- **El proyecto se distribuye con la licencia MIT** ([`LICENSE`](LICENSE)). Al proponer un cambio
  aceptas que tu contribución se publique con esa misma licencia.
- **No hay todavía un repositorio público ni un canal de contacto oficial.** Cuando existan, se
  indicarán aquí. Los pasos de esta guía que mencionan *pull requests* describen el flujo previsto.
- El proyecto está en una fase temprana: la sintaxis puede cambiar. Antes de dedicar tiempo a una
  funcionalidad nueva, consulta la [hoja de ruta](docs/roadmap.md) y las
  [decisiones técnicas](docs/decisions/README.md).

## Preparar el entorno

Necesitas Python 3.11 o superior. Desde el directorio `nexora/`:

```bash
python -m venv .venv
```

Activa el entorno (`.venv\Scripts\Activate.ps1` en Windows, `source .venv/bin/activate` en Linux y
macOS) e instala el proyecto con las herramientas de desarrollo:

```bash
python -m pip install -e ".[dev]"
```

Esto instala `pytest`, `pytest-cov` y `ruff`. Son las únicas dependencias de desarrollo; el
intérprete no tiene ninguna dependencia en ejecución, y debe seguir así.

Más detalle y solución de problemas: [Instalación](docs/installation.md).

## Comprobaciones que tienen que pasar

Antes de proponer un cambio, las tres tienen que terminar sin errores:

```bash
python -m ruff check src tests
python -m pytest
python -m pytest --cov
```

| Comando | Qué comprueba |
|---------|---------------|
| `python -m ruff check src tests` | Errores y descuidos en el código Python |
| `python -m pytest` | Todas las pruebas: lenguaje, CLI, ejemplos, documentación, seguridad y robustez |
| `python -m pytest --cov` | Lo mismo, y falla si la cobertura baja del umbral configurado en `pyproject.toml` |

Las mismas comprobaciones están definidas en el flujo de integración continua
(`.github/workflows/nexora-ci.yml`, en la raíz del repositorio).

Qué cubre cada archivo de pruebas: [Pruebas](docs/testing.md).

## Mantener todo sincronizado

En NEXORA el código, la especificación, los ejemplos y la documentación tienen que decir lo mismo.
No se confía en la disciplina: **las pruebas fallan si se desincronizan**.

| Si cambias… | Tienes que actualizar… | Lo vigila |
|-------------|------------------------|-----------|
| El comportamiento del lenguaje | `docs/language-spec.md` y la guía correspondiente | `tests/test_docs.py` ejecuta todos los programas de la documentación y compara su salida |
| La salida de un ejemplo | Los archivos de `tests/golden/examples/` | `tests/test_examples.py` |
| Un código de error | `_REGISTRY` en `diagnostics.py`, y las tablas de `docs/language-spec.md` y `docs/diagnostics.md` | `tests/test_diagnostics.py`, `tests/test_docs.py` |
| Un nodo del árbol de sintaxis | `docs/inspect-schema.md` y la lista de `tests/test_inspect.py` | `tests/test_inspect.py` |
| Un comando, una opción o un código de salida | `docs/cli-reference.md` | `tests/test_docs.py` |
| Una palabra clave o una función integrada | Un ejemplo válido de `examples/` que la use | `tests/test_examples.py` |
| La versión | Solo `src/nexora/version.py` | `tests/test_docs.py`, `tests/test_cli.py` |
| Un enlace o un título de la documentación | Los enlaces que apuntan a él | `tests/test_docs.py` |

### Programas en la documentación

Un bloque de código NEXORA en un archivo Markdown se comprueba si lleva delante un comentario
marcador. Por ejemplo:

````markdown
<!-- nex:run -->
```nex
fn main() -> Void {
    print("Hello")
}
```

```text
Hello
```
````

Los marcadores disponibles (`nex:run`, `nex:fails`, `nex:check-fails`, `nex:check-json`,
`nex:inspect`, `nex:valid`, `nex:body`, `nex:body-fails`) están descritos al principio de
`tests/test_docs.py`. Un bloque que contenga `fn main` y no tenga marcador hace fallar las pruebas.

### Actualizar salidas registradas

Si un cambio modifica **a propósito** la salida de un ejemplo o de un programa de la documentación,
regenera los archivos y **revisa las diferencias una a una** antes de aceptarlas:

```bash
# Linux y macOS
NEXORA_UPDATE_GOLDEN=1 python -m pytest tests/test_examples.py
NEXORA_UPDATE_DOCS=1 python -m pytest tests/test_docs.py
```

```powershell
# Windows (PowerShell)
$env:NEXORA_UPDATE_GOLDEN = "1"; python -m pytest tests/test_examples.py; $env:NEXORA_UPDATE_GOLDEN = $null
$env:NEXORA_UPDATE_DOCS = "1"; python -m pytest tests/test_docs.py; $env:NEXORA_UPDATE_DOCS = $null
```

Después ejecuta `python -m pytest` sin esas variables. Regenerar no es una forma de "arreglar" una
prueba que falla: si la salida cambió sin que lo pretendieras, has encontrado un error.

## Añadir una funcionalidad al lenguaje

Sigue este orden. Cada paso deja algo comprobable.

1. **Decide y documenta.** Si es una decisión de diseño o un cambio incompatible, añade un
   documento a `docs/decisions/` (siguiente número libre) con el motivo, las alternativas
   descartadas y el efecto sobre programas existentes.
2. **Escribe la especificación.** Añade la sintaxis a la gramática EBNF de `docs/language-spec.md`
   y describe su significado: tipos, errores posibles, y qué se comprueba antes y durante la
   ejecución.
3. **Implementa por etapas**, en este orden: `tokens.py` y `lexer.py`, `ast_nodes.py`, `parser.py`,
   `checker.py`, `interpreter.py`. La tabla "Dónde añadir cosas" de
   [Arquitectura](docs/architecture.md#dónde-añadir-cosas) indica qué tocar en cada caso.
4. **Respeta la separación de etapas.** Las reglas de nombres y tipos van **solo** en `checker.py`.
   El intérprete no las repite; solo comprueba lo que depende de los valores.
5. **Escribe las pruebas** junto con cada etapa: casos válidos, casos inválidos y casos límite.
6. **Añade un ejemplo** en `examples/` y regístralo en `tests/test_examples.py` y en
   `examples/README.md`.
7. **Actualiza las guías** (`docs/`), el `CHANGELOG.md` y, si procede, `docs/limitations.md` y
   `docs/roadmap.md`.

Una funcionalidad no está terminada hasta que funciona, tiene pruebas y su documentación describe
su comportamiento real. No documentes como existente algo que solo está previsto.

## Modificar la especificación

- `docs/language-spec.md` describe **lo que el intérprete hace hoy**. Lo previsto va en su sección
  14 y en `docs/roadmap.md`.
- Un cambio de la especificación sin cambio de código solo es válido si corrige un texto que no
  describía bien el comportamiento real.
- La gramática EBNF tiene que corresponder al parser. Si añades una regla a la gramática, añade una
  prueba del parser que la ejerza.
- Mantén las tres marcas de estado: implementado, **experimental** y **previsto**.

## Añadir un diagnóstico

1. Elige el siguiente código libre de su rango: `E10xx` léxico, `E11xx` sintáctico, `E2xxx`
   semántico o de tipos, `E3xxx` de ejecución, `E4xxx` de contrato.
2. **Nunca reutilices un código**, tampoco uno retirado (`E1104`, `E2003`).
3. Añádelo a `_REGISTRY` en `src/nexora/diagnostics.py`, con su título y su categoría.
4. Documéntalo en las tablas de `docs/language-spec.md` (sección 11.3) y de `docs/diagnostics.md`.
5. Escribe una prueba que lo provoque y compruebe código, posición y mensaje.

Criterios para el mensaje:

- El título (`CODES`) es fijo y corto. La explicación concreta va en `label`.
- Di qué se esperaba y qué se encontró.
- Señala el fragmento más pequeño que identifica el problema.
- Añade una sugerencia (`hint`) **solo si hay una regla que la respalde**. Una sugerencia que puede
  ser incorrecta es peor que ninguna.
- Un error del usuario nunca debe mostrarse como una traza de Python, y un defecto del intérprete
  nunca debe mostrarse como un error del usuario.

## Estilo del código

- Python 3.11, sin dependencias externas en `src/`.
- Lo que `ruff` acepta con la configuración de `pyproject.toml`. No hay formateador obligatorio.
- Nombres y comentarios del código en inglés, como los mensajes del lenguaje. La documentación, en
  español.
- Los comentarios explican el porqué, no lo que el código ya dice.
- Módulos pequeños con una responsabilidad. Solo `cli.py` toca el sistema operativo.
- No uses `eval`, `exec` ni nada que ejecute código a partir de texto: hay una prueba que lo impide.

## Pruebas

- Cada prueba comprueba un comportamiento: un resultado, un diagnóstico o un código de salida.
  No escribas pruebas que solo recorran código.
- Si corriges un defecto, añade antes una prueba que lo reproduzca (las de regresión están en
  `tests/test_robustness.py`).
- Prueba también lo que tiene que **fallar**, y que falla con el diagnóstico correcto.
- El comportamiento de la CLI se prueba a través del comando real, en un proceso aparte, además de
  mediante llamadas directas.

## Proponer el cambio

Cuando exista el repositorio público:

1. Crea una rama a partir de la principal.
2. Haz cambios pequeños y relacionados entre sí.
3. Comprueba que las tres comprobaciones pasan en local.
4. Describe en la propuesta qué cambia, por qué, y cómo lo has probado.
5. Añade una entrada en `CHANGELOG.md`, en la sección "Sin publicar".

## Avisar de un error

Incluye la versión (`nex --version`), el sistema operativo, el programa `.nex` más pequeño que
reproduzca el problema, lo que esperabas y lo que ocurrió. Si el mensaje empieza por
`internal error:`, vuelve a ejecutar con la variable de entorno `NEXORA_DEBUG=1` y adjunta la traza.

Los problemas de seguridad se comunican como indica [`SECURITY.md`](SECURITY.md), no en un aviso
público.

## Conducta

La participación en el proyecto se rige por el [código de conducta](CODE_OF_CONDUCT.md).
