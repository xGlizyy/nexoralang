# Seguridad

Este documento explica qué protege NEXORA hoy, qué **no** protege, y cómo avisar de un problema.

NEXORA es un proyecto en fase temprana que no ha sido auditado. **No afirmamos que sea seguro
ejecutar con él código que no sea de confianza.**

## Versiones con soporte

Solo la versión más reciente del código. No hay versiones publicadas ni mantenimiento de versiones
anteriores.

## Cómo avisar de una vulnerabilidad

**Todavía no existe un canal de contacto privado.** El repositorio es público, pero no hay una
dirección de correo para este fin, y *Private vulnerability reporting* no está activado (se
comprueba en `GET /repos/{propietario}/{repositorio}/private-vulnerability-reporting`).

> **Pendiente de configurar por quien mantiene el proyecto.** El repositorio ya está publicado; queda
> elegir el canal y sustituir este bloque por el elegido. Opciones sin coste:
>
> - En GitHub: activar *Private vulnerability reporting* (Settings → Code security, o
>   `PATCH /repos/{propietario}/{repositorio}/private-vulnerability-reporting` con `{"enabled": true}`)
>   e indicar aquí "Usa el botón *Report a vulnerability* de la pestaña *Security*".
> - Una dirección de correo dedicada.
>
> Indicar también un plazo de respuesta que realmente pueda cumplirse.

Hasta entonces, si tienes acceso directo a quien mantiene el proyecto, comunícaselo en privado.
**No describas una vulnerabilidad en un canal público** antes de que haya una corrección.

Un buen aviso incluye:

- La versión (`nex --version`), el sistema operativo y la versión de Python.
- El programa `.nex` o el comando más pequeño que reproduce el problema.
- Qué ocurre y qué impacto tiene.

No hay programa de recompensas.

## Qué está dentro del alcance

Se considera un problema de seguridad cualquier forma de conseguir, **mediante un archivo `.nex` o
mediante los argumentos de `nex`**, algo de lo siguiente:

- Ejecutar código Python o comandos del sistema.
- Leer o escribir archivos distintos del archivo `.nex` indicado.
- Acceder a la red, a variables de entorno o a otros procesos.
- Que `nex check` o `nex inspect` ejecuten el programa que analizan.
- Que un texto del programa se interprete como código en lugar de tratarse como dato.

También interesa, aunque con menor gravedad, cualquier entrada que provoque un error interno
(`internal error`, código de salida `70`) o un cierre inesperado del proceso.

## Qué protege el diseño

Estas propiedades se derivan de cómo está construido el lenguaje y **se comprueban con pruebas
automatizadas** (`tests/test_security.py`, `tests/test_robustness.py`):

| Propiedad | Cómo se consigue | Qué comprueba la prueba |
|-----------|------------------|-------------------------|
| Un programa solo puede calcular y escribir texto | El lenguaje no tiene ninguna construcción de entrada/salida salvo `print`. Las funciones integradas son `print`, `to_text`, `to_float` y `to_int` | Que la lista de funciones integradas es exactamente esa, y que nombres como `open`, `eval` o `exec` no existen |
| El intérprete no evalúa código Python | Recorre su propio árbol de sintaxis. No usa `eval`, `exec` ni `compile` | Se analiza el código fuente de cada módulo y se rechaza cualquier llamada a esas funciones |
| El análisis no ejecuta | `nex check` y `nex inspect` terminan antes de la etapa de ejecución | Un programa que imprime, divide por cero y entra en recursividad infinita se analiza sin que ocurra nada de eso |
| Los argumentos no son código | `nex` solo acepta rutas de archivo. No existe ninguna opción para pasar código | Argumentos con forma de código se tratan como nombres de archivo inexistentes |
| Las etapas del lenguaje no tocan el sistema | Solo `cli.py` lee el archivo y escribe en la terminal | Los demás módulos no importan `os`, `pathlib` ni `subprocess` |
| No se escriben archivos | La única operación de archivo es leer el programa | Ejecutar los tres comandos no crea ningún archivo |
| Sin dependencias externas | Solo se usa la biblioteca estándar de Python | La lista de dependencias está vacía, y los módulos solo importan de una lista cerrada |
| Las entradas incorrectas no hacen fallar al intérprete | Límites de anidamiento, de profundidad y de número de errores | Archivos truncados, mutados, aleatorios, binarios, enormes o con anidamiento extremo producen diagnósticos, no excepciones |

## Qué **no** está protegido

- **NEXORA no es un entorno aislado (*sandbox*).** El intérprete es un programa de Python normal,
  que se ejecuta con los permisos de quien lo lanza. Las propiedades anteriores dependen de que el
  intérprete no tenga defectos; no hay una segunda barrera (aislamiento de proceso, restricción de
  llamadas al sistema) si los tiene.
- **No hay límite de tiempo de ejecución.** Un programa puede tardar mucho.
- **No hay límite de memoria.** Un programa puede construir textos muy grandes por concatenación.
  El límite de 1000 llamadas anidadas acota la recursividad, no el consumo de memoria.
- **No hay límite de tamaño del archivo de entrada**, ni del tamaño de la salida.
- **Las pruebas con entradas aleatorias son limitadas.** Recorren unos miles de casos generados con
  una semilla fija. No son una búsqueda exhaustiva ni sustituyen a una auditoría.
- **No se ha hecho ninguna auditoría externa**, ni análisis de seguridad con herramientas
  especializadas.
- **La salida de un programa no se filtra.** Un programa puede escribir secuencias de control de
  terminal. Si muestras la salida de un programa no confiable en una terminal, tenlo en cuenta.

En consecuencia: ejecutar un programa NEXORA desconocido no debería poder leer tus archivos ni
ejecutar otros programas, pero **puede consumir CPU y memoria sin límite**. Si necesitas ejecutar
código no confiable, hazlo dentro de un aislamiento proporcionado por el sistema operativo
(un contenedor, una máquina virtual, límites de recursos del sistema).

## Cadena de suministro

- El intérprete no tiene dependencias en ejecución.
- Las dependencias de desarrollo (`pytest`, `pytest-cov`, `ruff`) y la de empaquetado
  (`setuptools`) se descargan de PyPI al instalar. No se fijan a versiones exactas ni se verifican
  por *hash*.
- No se publican paquetes de NEXORA en ningún repositorio. Cualquier paquete llamado `nexora` en
  PyPI u otro índice **no procede de este proyecto**.
