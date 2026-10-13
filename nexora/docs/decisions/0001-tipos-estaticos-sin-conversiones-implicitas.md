# 0001 — Tipos estáticos, sin conversiones implícitas; `String` pasa a llamarse `Text`

- **Estado:** aceptada
- **Versión:** 0.2.0

## Contexto

La versión 0.1 ya deducía el tipo de cada expresión, pero no permitía escribir tipos, no tenía
comparaciones ni lógica, y no ofrecía ninguna forma de pasar de un tipo a otro: `1 + 1.5` era un
error sin solución dentro del lenguaje.

## Decisión

1. **Todo tipo se conoce sin ejecutar.** El tipo de una expresión depende solo de literales,
   anotaciones y firmas. Ningún error de tipos puede aparecer durante la ejecución.
2. **Dos tipos son compatibles solo si son el mismo.** No hay subtipos ni promoción numérica:
   `Int` y `Float` no se mezclan en operaciones, comparaciones, argumentos ni retornos.
3. **Las conversiones son llamadas explícitas**: `to_float`, `to_int` y `to_text`. No hay ninguna
   otra.
4. **La división entre `Int` devuelve `Int`**, redondeando hacia cero. Se mantiene el
   comportamiento de 0.1.
5. **Las condiciones son `Bool`.** Un número o un texto no valen como condición.
6. **Anotaciones opcionales** en `let` (`let age: Int = 25`); sin anotación, el tipo se infiere.
7. **El tipo de texto se llama `Text`** en lugar de `String`.
8. Los operadores lógicos son palabras (`and`, `or`, `not`), como en el borrador de diseño.

## Motivos

- Una conversión implícita puede ocultar un error: `1 + 1.5` puede ser una mezcla de unidades
  accidental. Si la conversión hay que escribirla, el código dice lo que hace y una herramienta
  que lo lea no tiene que conocer reglas de promoción.
- Con una única regla de compatibilidad ("el mismo tipo") los mensajes de error pueden ser exactos
  y proponer la conversión correcta cuando existe.
- La división entera que devuelve entero evita que el tipo del resultado dependa de los valores.
  La alternativa (devolver siempre `Float`) habría convertido `10 / 2` en `5.0` y habría hecho
  imposible la aritmética entera exacta sin otro operador.
- `Text` es el nombre pedido para esta fase; describe el valor para quien no viene de otro lenguaje.

## Alternativas descartadas

- **Promoción `Int` → `Float`.** Cómoda, pero es precisamente la conversión silenciosa que se
  quiere evitar, y pierde precisión con enteros de más de 53 bits.
- **Un operador de división entera aparte (`//`).** Añade sintaxis para algo que el tipo de los
  operandos ya expresa.
- **`!`, `&&`, `||`.** El borrador ya había elegido palabras; se mantiene una sola forma.
- **Comparar textos con `<`.** Requiere definir un orden (¿por código Unicode?, ¿por idioma?). Se
  aplaza hasta decidirlo.

## Cambios incompatibles y cómo actualizar

| Cambio | Efecto | Qué hacer |
|--------|--------|-----------|
| `String` → `Text` | Los mensajes de error dicen `Text`. Ningún programa de 0.1 escribía `String`, porque no había anotaciones, así que no hay código que cambiar | Nada. Escribir `String` en 0.2 produce `E2012` con la pista "The text type is called Text" |
| `and`, `or`, `not`, `if`, `else`, `return`, `requires`, `ensures` ahora tienen significado | Ya eran palabras reservadas en 0.1, así que ningún programa válido las usaba como nombres | Nada |
| `to_text`, `to_float`, `to_int` son funciones integradas | Un programa de 0.1 que declarase una variable con uno de esos nombres ahora da `E2006` | Renombrar la variable |

Los cuatro ejemplos de la versión 0.1 se ejecutan sin cambios y dan el mismo resultado.
