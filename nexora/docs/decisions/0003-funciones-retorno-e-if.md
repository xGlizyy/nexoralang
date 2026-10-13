# 0003 — Funciones con `return` explícito, un único espacio de nombres e `if` como sentencia

- **Estado:** aceptada
- **Versión:** 0.2.0

## Decisión

1. **Funciones con parámetros tipados y tipo de retorno obligatorio.** Sin sobrecarga, valores por
   defecto, genéricos ni funciones anónimas.
2. **El valor se devuelve siempre con `return`.** El borrador de diseño proponía que un bloque
   valiera lo que su última expresión; no se adopta en esta versión.
3. **Toda ruta devuelve.** El análisis estático rechaza una función que puede terminar sin
   `return` (`E2014`) y el código situado tras un `return` (`E2015`). El análisis es estructural:
   no evalúa condiciones.
4. **Un único espacio de nombres y sin ocultación.** Funciones, parámetros y variables comparten
   nombres; un nombre visible no se vuelve a declarar.
5. **Las funciones no son valores.** Solo pueden llamarse.
6. **Un valor devuelto no puede ignorarse** (`E2010`).
7. **`if` / `else if` / `else` como sentencia.** No estaba en la lista de esta fase, pero se añade.
8. **Recursividad permitida**, con un máximo de 1000 llamadas anidadas (`E3004`).

## Motivos

- `return` explícito hace visible dónde termina una función y permite comprobar las rutas de
  retorno con una regla sencilla. Con "la última expresión es el valor", la regla de `E2010`
  (valor sin usar) y la de retorno implícito entrarían en conflicto.
- Con un único espacio de nombres, cada nombre de una función significa una sola cosa. Esto
  simplifica la lectura para una persona y para una herramienta: no hay que resolver qué `x` es
  cuál.
- **Por qué `if`:** sin condicionales, una función recursiva no puede detenerse, la regla "toda
  ruta devuelve" no tiene rutas que comprobar y `ensures` nunca tendría más de un camino. Las
  comparaciones y los `Bool` tampoco servirían para nada más que imprimirse. Es la construcción
  mínima que hace útiles las demás.
- El límite de llamadas convierte una recursividad sin fin en un diagnóstico claro en lugar de un
  fallo del intérprete.

## Alternativas descartadas

- **Bucles (`while`).** Requieren variables reasignables (`var`), que no existen. Se aplazan juntos.
- **`if` como expresión.** Obliga a definir el tipo de un bloque; se aplaza.
- **Permitir ignorar valores devueltos.** Contradice la regla ya existente para expresiones sueltas.

## Límites conocidos

- El análisis de rutas no razona sobre valores: `if true { return 1 }` sin `else` se rechaza.
- El límite de 1000 llamadas depende de la implementación (el intérprete recorre el árbol de forma
  recursiva) y puede reducirse con expresiones muy anidadas.
- Como máximo 64 niveles de `else if` encadenados.

## Compatibilidad

Sin cambios incompatibles: en 0.1 solo podía declararse `main`, y todo programa de 0.1 sigue
siendo válido. Los códigos `E1104` y `E2003`, que avisaban de que estas construcciones no existían,
quedan retirados.
