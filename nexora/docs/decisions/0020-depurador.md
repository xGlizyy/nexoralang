# 0020 — Depuración paso a paso

- **Estado:** aceptada; integración automática verificada, revisión visual del navegador pendiente.
- **Fecha:** 2026-10-27.
- **Rama de trabajo:** `feat/debugger-prototype`.
- **Afecta:** intérprete, worker y Playground.
- **No añade:** sintaxis al lenguaje ni evaluación de expresiones arbitrarias.

## Decisión

El intérprete expone eventos opcionales antes de ejecutar cada sentencia. El Playground usa un
worker persistente durante la sesión y ofrece `Step`, `Continue` y `Stop`, breakpoints por línea,
pila de llamadas, variables del marco actual y salida acumulada. Entrar en llamadas es el
comportamiento de `Step`.

Los valores del inspector se convierten a texto con límites de tamaño. El worker no acepta órdenes
para evaluar expresiones. El programa depurado usa `NoHost`, no puede leer la entrada del worker ni
acceder a archivos u otras capacidades.

Las sesiones usan JSON Lines entre el servidor y el worker. Comparten el límite de concurrencia con
las ejecuciones normales, tienen un máximo de 10.000 sentencias inspeccionadas, 256 breakpoints,
10 segundos por orden, 60 segundos de inactividad y cinco minutos de duración total. El servidor
las detiene al apagarse. El Playground público sigue requiriendo que el aislamiento con Docker se
haya validado antes de activarlo.

## Alcance inicial

El depurador está integrado en el Playground. No se añade todavía un comando local `nex debug`,
paso por expresión, paso por encima, breakpoints condicionales ni edición de variables.

## Criterios de aceptación

- `Step` avanza exactamente una sentencia y vuelve a pausar antes de la siguiente, incluso dentro
  de llamadas y bucles.
- `Continue` se detiene en un breakpoint o al terminar el programa.
- La ubicación, la pila y las variables provienen de los marcos vivos del intérprete.
- Cerrar, detener, completar o dejar expirar una sesión termina el worker y libera su espacio de
  concurrencia; al apagar el servidor se cierran las sesiones activas.
- No se puede iniciar una sesión si el Playground está desactivado, y no se amplían las capacidades
  disponibles al programa.
- Los flujos del worker y la interfaz se verifican antes de habilitar el depurador en producción.
