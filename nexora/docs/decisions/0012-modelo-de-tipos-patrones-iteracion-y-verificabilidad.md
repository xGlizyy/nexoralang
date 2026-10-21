# 0012 — Modelo de tipos, patrones, iteración y evidencia verificable

- **Estado:** propuesta para revisión. **No aceptada todavía.**
- **Fecha:** 2026-10-19.
- **Rama de trabajo:** `feature/server-hardening`.
- **Relacionada con:** [0001](0001-tipos-estaticos-sin-conversiones-implicitas.md), [0002](0002-el-interprete-solo-ejecuta-programas-comprobados.md), [0004](0004-contratos-en-ejecucion.md), [0005](0005-diagnosticos-y-esquemas-json.md), [0006](0006-requisitos-verificables.md), [0007](0007-contratos-estables-y-tipos-refinados.md), [0008](0008-ejemplos-y-nex-test.md), [0010](0010-var-y-while.md) y [0011](0011-operaciones-sobre-textos.md).
- **Sustituye a:** ninguna.
- **Implementación:** ninguna. Este documento no modifica el lenguaje, la hoja de ruta ni las limitaciones oficiales.

## Convenciones de evidencia

Este ADR se apoya en lectura de código y documentación. **No se ha ejecutado ningún programa, prueba, build, instalación, migración ni consulta.** Las marcas siguientes separan lo observado de lo propuesto:

- **[V]** observado en el código o en la documentación del repositorio.
- **[D]** afirmación de la documentación, coherente con el código leído, pero no comprobada por ejecución.
- **[I]** inferencia técnica.
- **[P]** propuesta sujeta a aprobación.
- **[?]** cuestión pendiente de evidencia o de decisión.

---

## A. Contexto, objetivos y principios

### A.1. Propósito diferencial

La [decisión 0006](0006-requisitos-verificables.md) fija la propuesta de NEXORA: los requisitos, restricciones y condiciones de validación de una función forman parte verificable del programa, no solo de una instrucción, un ticket o un comentario. La [decisión 0007](0007-contratos-estables-y-tipos-refinados.md) estabilizó los contratos, las explicaciones y los tipos refinados; la [0008](0008-ejemplos-y-nex-test.md) añadió ejemplos ejecutables y `nex test`; la [0010](0010-var-y-while.md) añadió bucles con `invariant` y `decreases`; la [0011](0011-operaciones-sobre-textos.md) añadió funciones de tipo con contratos.

NEXORA no debe presentarse como un lenguaje que demuestra programas correctos. Su propuesta defendible es más concreta:

> Los requisitos verificables son datos explícitos del programa y del análisis; las herramientas deterministas indican qué pueden comprobar, qué han comprobado y qué no; y una edición que elimina o relaja un requisito se señala como un cambio visible.

### A.2. Cómo ayuda a una IA

Una IA que trabaja sobre código necesita responder preguntas que hoy no puede responder solo leyendo el texto:

1. ¿Qué requisitos tiene esta función antes de tocarla?
2. ¿Qué tipos, contratos, restricciones y dependencias son relevantes?
3. ¿Qué requisitos pueden verse afectados por el cambio?
4. ¿La modificación propuesta respeta las restricciones conocidas?
5. ¿Qué comprobaciones se han ejecutado y con qué resultado?
6. ¿Qué queda sin comprobar o es incierto?
7. ¿Puede demostrar que no ha roto un requisito, o solo afirmarlo?

NEXORA puede ayudar con las preguntas 1, 2, 3, 5 y 6 mediante datos estructurados y herramientas deterministas. La pregunta 4 es responsabilidad del agente que escribe el cambio. Las preguntas 6 y 7 exigen un contrato de evidencia explícito: **no basta con “no hay diagnósticos”**. La pregunta 7 no autoriza a decir “verificado” si solo se comprobó en algunas ejecuciones.

### A.3. Capacidades actuales, propuestas e hipótesis

| Categoría | Qué incluye | Estado |
|---|---|---|
| **Capacidad actual** | Tipos estáticos `Int`, `Float`, `Bool`, `Text`, `Void`; contratos `requires`/`ensures` comprobados al ejecutar; tipos refinados sobre builtins; `example`; `while` con `invariant`/`decreases`; `nex check`, `inspect`, `context`, `symbols`, `test`; JSON; MCP de solo lectura; playground con worker | Implementado y documentado **[V]/[D]** |
| **Propuesta de este ADR** | Álgebra de tipos; listas; registros; enums; `match`; exhaustividad; `Option`/`Result`; entrada explícita; módulos; evidencia e impacto de requisitos | Diseño, no implementado **[P]** |
| **Hipótesis de investigación** | Que los requisitos en el código y las herramientas de NEXORA hacen que una IA detecte más incumplimientos, debilite menos requisitos y necesite menos correcciones | **No medida** **[?]** |

La distinción importa: una capacidad propuesta no debe describirse como existente; una hipótesis no debe presentarse como resultado.

### A.4. Principios que deben mantenerse

1. **Semántica explícita.** Cada construcción tiene una regla escrita y comprobable; no se introducen conversiones, mutaciones o efectos ocultos.
2. **Diagnósticos útiles y estables.** Código estable, posición exacta, etiqueta concreta, notas y sugerencia solo cuando existe una regla que la fundamente.
3. **Verificabilidad honesta.** Se distingue lo comprobado estáticamente, lo comprobado en ejecución, lo inferido y lo no comprobado. Nunca se afirma más de lo que se ha comprobado.
4. **Seguridad por capas.** Las garantías del lenguaje no son las garantías del entorno. El playground no es una sandbox por sí mismo.
5. **Coherencia lenguaje-herramientas-documentación.** Una funcionalidad no está terminada si el lexer, el parser, el checker, el intérprete, los diagnósticos, la CLI, JSON/MCP, la documentación, los ejemplos, los tests y el playground no la reflejan.
6. **Compatibilidad incremental.** Los programas existentes deben seguir funcionando; los esquemas JSON crecen de forma aditiva salvo que se decida lo contrario.
7. **Una sola forma de escribir cada cosa.** Sin azúcar redundante ni casos especiales innecesarios; `Option`/`Result` no deben ser excepciones del compilador.

### A.5. Fuera de alcance

Este ADR no decide typeclasses, efectos algebraicos, concurrencia, macros, `ai fn`, `tool fn`, compilación a JavaScript/WebAssembly, registro de paquetes, optimización ni una fecha para 1.0. Tampoco implementa ninguna decisión.

---

## B. Modelo de tipos

### B.1. Estado actual **[V]**

- Los tipos son cadenas: `INT = "Int"`, `FLOAT`, `BOOL`, `TEXT`, `VOID`; `VALUE_TYPES = (INT, FLOAT, BOOL, TEXT)` en `nexora/src/nexora/values.py`.
- `TypeRef` solo guarda `name: str` en `ast_nodes.py`; no tiene argumentos de tipo.
- `TypeDecl` solo representa tipos refinados: `name`, `base: TypeRef`, `condition: Expr`, `message`.
- `Signature` usa `params: tuple[tuple[str, str | None], ...]` y `return_type: str | None` en `checker.py`.
- `BUILTINS` es un diccionario de `Signature` con cadenas.
- `Symbol.type` es `str | None`; `CheckedProgram.types` es `dict[int, str]`.
- `RefinedType` guarda `base: str`, `root: str` y `chain`.
- `binary_result(operator, left: str, right: str)` decide la aritmética comparando cadenas.
- `parser._type` exige un único `IDENT`; el lexer no tiene tokens `[` ni `]`.
- No hay `types.py`: la lógica de tipos vive en `checker.py`.

**Consecuencia observada [I]:** `List[T]`, `Option[T]`, `Result[T,E]`, los registros y los enums no se pueden representar sin cambiar las interfaces anteriores. La propia `architecture.md` reconoce que los tipos compuestos exigirán una representación propia y que es el cambio más profundo del comprobador.

### B.2. Propuesta **[P]**

#### B.2.1. D01 — Representación interna del modelo de tipos **[P]**

> **Estado: propuesta pendiente de aprobación.** No aceptada. Esta subsección concreta D01 y no reabre D02 (nominal frente a estructural), D03 (alcance de genéricos e inferencia) ni D04 (refinamientos): fija únicamente cómo se representan, identifican, comparan, presentan y migran los tipos. Los nombres `Type`, `TypeExpr`, `type_repr`, `types.py`, etc. son nombres provisionales de diseño; **no existen hoy en el código** y no deben presentarse como implementados.

**D01.1. Representación interna frente a presentación textual**

La fuente de verdad debe ser una estructura de datos, no una cadena. La cadena se conserva como una de las formas de presentación, nunca como la representación sobre la que se decide la semántica.

Responsabilidades del modelo de tipos:

- construir un tipo a partir del `TypeRef` del AST y de las declaraciones del programa;
- comprobar aridad y nombres de constructores;
- comparar tipos por identidad y equivalencia;
- sustituir variables de tipo por argumentos;
- unificar cuando la inferencia lo necesite;
- calcular el tipo raíz de un refinamiento;
- recorrer el tipo para diagnósticos, herramientas y serialización;
- producir una representación textual canónica y una representación estructurada.

Responsabilidades de la presentación textual:

- mostrar tipos legibles para personas (`List[Option[Int]]`, `Result[Text, Error]`);
- mantener el campo `type` actual de JSON mientras sea necesario para compatibilidad;
- no usarse para decidir igualdad, asignabilidad, aridad ni diagnóstico.

Ejemplos conceptuales:

- `List[Option[Int]]` se representa como un constructor de lista cuyo argumento es un constructor opcional cuyo argumento es `Int`. La cadena se genera al mostrar; la comparación no recorre ni analiza la cadena.
- `Result[Text, Error]` se representa como un constructor de resultado con dos argumentos posicionales. La aridad se comprueba con la declaración del constructor, no contando comas.
- Dos tipos escritos con espacios distintos (`List[ Int ]` y `List[Int]`) deben ser el mismo tipo si el parser los acepta; la representación textual no participa en esa decisión.

La verificación de tipos deja de depender de `left != right` o de comparaciones equivalentes sobre cadenas. Esa dependencia existe hoy en el código y es la razón principal de D01.

**D01.2. Tipos mínimos**

| Categoría | Ejemplos | Representación propuesta | Límite inicial |
|---|---|---|---|
| Primitivos | `Int`, `Float`, `Bool`, `Text`, `Void` | Constructor sin argumentos | `Void` solo como resultado de función |
| Refinados | `Percent`, `Positive`, `NonEmpty` | Envoltorio nominal con nombre, base y referencia a su condición | No se expanden por defecto; conservan su identidad |
| Declarados | registros y enums de usuario (propuestos en D02/D05) | Tipo nominal con identidad de declaración y argumentos de tipo | Inicialmente sin genéricos de usuario o con aridad sencilla |
| Variables de tipo | `T`, `E` en una declaración genérica | Variable con un identificador y un nombre ligado a su declaración | Solo dentro de la declaración que las introduce |
| Constructores genéricos | `List[T]`, `Option[T]`, `Result[T, E]` | Constructor con aridad fija y argumentos posicionales | `List` aridad 1; `Option` aridad 1; `Result` aridad 2 |
| Tipo de función | firma de una función | Estructura reservada para la firma, sin valores función | No es un tipo de primera clase en esta fase |

Reglas mínimas:

- No hay `Any`, ni conversiones numéricas implícitas, ni subtipado por anchura.
- `Void` no es un tipo de valor: no puede ser parámetro ni argumento de un constructor de datos.
- Un refinado es un tipo distinto de su base, aunque sea asignable a ella en el sentido de ensanchamiento (`widening`).
- Un tipo declarado es distinto de otro con la misma forma: la identidad no depende de los campos.
- Los constructores integrados y los declarados comparten la misma forma de representación; no hay un caso especial para `List` más allá de su aridad y de sus operaciones asociadas.

**D01.3. Tipos compuestos**

- Un tipo compuesto es un constructor con una tupla de argumentos, posiblemente anidados.
- `List[Option[Int]]` se representa como `Apply(List, (Apply(Option, (Int,)),))` en notación conceptual.
- `Result[Text, Error]` se representa como `Apply(Result, (Text, Error))`.
- `Option[Result[Int, Error]]`, listas de listas y combinaciones equivalentes se representan por anidamiento directo, sin aplanar ni codificar en una cadena.
- La aridad se valida contra la declaración del constructor. Un constructor de aridad 1 usado con dos argumentos es un error de tipo, no un error de análisis de cadena.
- La presentación canónica usa corchetes y comas: `List[Option[Int]]`, `Result[Text, Error]`. La presentación no necesita ser única en el espacio en blanco (el parser normaliza), pero sí estable para una misma estructura.
- Los futuros registros y enums usan la misma representación, con sus propios constructores de tipo.

**D01.4. Identidad y equivalencia**

La igualdad de tipos se define estructuralmente sobre la representación interna, con una excepción nominal para los tipos declarados:

1. **Primitivos:** iguales si y solo si son el mismo primitivo.
2. **Constructores:** iguales si el constructor es el mismo y sus argumentos son iguales en orden. `List[Int]` y `List[Text]` no son iguales.
3. **Tipos declarados:** iguales si son la misma declaración, no si tienen los mismos campos. `Persona` y `Empleado` con campos idénticos no son el mismo tipo.
4. **Refinados:** iguales si son el mismo nombre declarado, incluso si comparten base y condición. `Percent` y `Cantidad` no son intercambiables.
5. **Variables de tipo:** iguales si están ligadas a la misma variable; una variable sin ligar no es igual a un tipo concreto.
6. **Funciones:** iguales por parámetros y resultado cuando ese tipo se incorpore; aplazado hasta que haya valores función.

Reglas de compatibilidad iniciales:

- **Invariancia en argumentos genéricos:** `List[Int]` no es asignable a `List[Text]`, y `Option[Int]` no es asignable a `Option[Text]`. La covarianza se aplaza.
- **Ensanchamiento de refinados:** un valor de `Percent` es aceptable donde se espera `Int`; lo contrario exige construir el refinado (`Percent(x)`) y comprobar la condición en ejecución.
- **Sin subtipado estructural:** dos registros con la misma forma no son compatibles si son declaraciones distintas.
- **Identidad de declaración:** en un archivo, el nombre de la declaración; cuando existan módulos, una identidad que incluya el módulo o un identificador estable. La forma exacta queda abierta y depende de D13.
- No se comparan tipos por su representación textual, por su orden de declaración ni por la posición en el archivo.

**D01.5. Genéricos e inferencia**

D01 solo fija cómo se representan las variables de tipo y cómo se instancian. El alcance funcional se decide en D03; D01 no lo aprueba.

Recomendación inicial:

- Genéricos **paramétricos de primer orden**, con declaración explícita de variables (`fn f[T](x: T) -> T`, `type Caja[T] = ...`).
- Sin typeclasses.
- Sin generalización automática.
- Sin tipos de rango superior, sin familias de tipos y sin recursión polimórfica sin anotación.
- Inferencia local para `let`/`var` a partir del inicializador, como hoy.
- Unificación de primer orden en llamadas para inferir argumentos de tipo de builtins y funciones genéricas.
- `let xs = []` exige anotación (`let xs: List[Int] = []`): el modelo no inventa el tipo del elemento.
- Si un argumento de tipo queda ambiguo, se pide una anotación en lugar de elegir por defecto.
- En el cuerpo de una función genérica, una variable de tipo solo se puede pasar, devolver o almacenar en una estructura que la acepte. No se permite aritmética, acceso a campos, ordenación ni ninguna operación que requiera una restricción. La comparación por igualdad se permite solo para tipos de valor, no para funciones.

Justificación de no empezar por Hindley-Milner ni por typeclasses:

- El caso de uso inmediato —listas, `Option`, `Result` y funciones genéricas simples— se cubre con unificación de primer orden y anotaciones explícitas.
- Hindley-Milner añade generalización, ambigüedad y mensajes difíciles sin resolver ningún caso de uso aprobado.
- Las typeclasses exigen un mecanismo de resolución y restricciones que hoy no hacen falta; pueden añadirse después sin invalidar la representación interna.
- La prioridad de NEXORA es la verificabilidad de requisitos, no la expresividad máxima del sistema de tipos.

Aplazado de forma explícita: typeclasses, tipos de rango superior, generalización automática, covarianza/contravarianza inferida, row types, tipos dependientes y verificación formal de genéricos.

**D01.6. Refinamientos y contratos**

D01 representa los refinamientos; su semántica completa se decide en D04 y en las decisiones 0004/0007, que no se reabren.

- Un refinado se representa como un tipo nominal cuyo nombre, base y condición son datos del modelo. La base puede ser un primitivo, otro refinado o, en el futuro, un tipo compuesto.
- La cadena de refinamientos se conserva para explicar de qué tipo raíz se parte y qué condiciones debe cumplir un valor.
- Las constantes se comprueban estáticamente como hoy; los valores calculados entran con la construcción explícita del refinado y se comprueban al ejecutar (`E4003`). D01 no cambia esa garantía.
- Los contratos `requires`/`ensures` siguen siendo comprobaciones en ejecución. D01 no insinúa que un predicado refinado quede demostrado automáticamente ni que el checker sea un demostrador.
- Un refinado es asignable a su base (ensanchamiento). La dirección contraria requiere construir el refinado; no hay coerción implícita de `Int` a `Percent`.
- Cuando los refinados se apliquen a listas o registros, el modelo debe poder representar la base compuesta sin convertir el predicado en una cadena.
- La exhaustividad y los diagnósticos sobre refinados siguen siendo conservadores: si el modelo no puede probar una propiedad, pide un caso general o deja la comprobación para ejecución.

**D01.7. Diagnósticos**

Los diagnósticos de tipos deben construirse a partir de los valores del modelo, no analizando cadenas.

- Un diagnóstico de incompatibilidad guarda al menos: tipo esperado, tipo encontrado, posición de la expresión y, cuando exista, posición de la declaración o del parámetro relevante.
- La explicación señala el primer punto de divergencia: por ejemplo, “se esperaba `List[Option[Int]]` y se encontró `List[Int]`; el argumento de la lista no coincide”.
- Los códigos son estables y específicos: tipo desconocido, aridad incorrecta, argumento incompatible, tipo ambiguo, campo duplicado/desconocido/faltante, patrón inválido, etc. La asignación exacta de códigos se hace al implementar, no en este ADR.
- Los mensajes no dependen del formato textual ni del orden de las declaraciones. La misma estructura produce el mismo mensaje salvo posición.
- Se pueden añadir notas y posiciones relacionadas (“el tipo se declaró aquí”, “el parámetro se declara aquí”) cuando aporten.
- Los diagnósticos deben poder serializarse con el tipo estructurado (o una forma estable de él) para que una herramienta no tenga que volver a interpretar la cadena.

**D01.8. Interfaces públicas y versionado**

Compatibilidad con lo existente:

- El campo `type` de los documentos JSON actuales sigue siendo la representación textual canónica. No se elimina ni cambia de significado.
- `Signature.describe()` y otras formas legibles pueden seguir existiendo para humanos.
- Se propone añadir un campo estructurado, por ejemplo `type_repr`, junto al campo `type` cuando una herramienta necesite distinguir estructura y no solo texto.
- `type_repr` debe ser aditivo: un consumidor antiguo puede ignorarlo. No se convierte en obligatorio ni sustituye a `type` en la misma versión.
- Un cambio de versión de esquema es necesario si se elimina o renombra un campo, si cambia su significado, si `type_repr` pasa a ser obligatorio o si su forma deja de ser compatible hacia atrás. Añadir un campo opcional no lo exige según la regla de compatibilidad vigente.
- La forma exacta de `type_repr` (vocabulario de `kind`, representación de nombres cualificados, etc.) se coordina con D16 y con el versionado de esquemas. Hasta entonces, D01 solo fija que debe ser estructurado, estable y aditivo.
- No se modifican ahora los esquemas, los documentos ni las herramientas; este ADR solo propone la dirección.

**D01.9. Migración**

Componentes actuales afectados:

- `values.py`: constantes de tipos y `VALUE_TYPES`; el modelo nuevo debe sustituir su uso como tabla de tipos.
- `ast_nodes.py`: `TypeRef` (hoy solo `name`) y `TypeDecl` (hoy solo refinado).
- `parser.py`: `_type` acepta un único identificador; la sintaxis de tipos compuestos requiere cambios posteriores.
- `checker.py`: `Signature`, `Symbol.type`, `CheckedProgram.types`, `RefinedType`, `binary_result` y las comprobaciones de asignabilidad.
- `interpreter.py`: comprobación de valores, contratos y refinados en ejecución.
- `diagnostics.py`: mensajes y posiciones que hoy asumen cadenas.
- `tooling.py` y `schemas.py`: campos `type`, entradas de tipos, validación y documentos.
- `cli.py`, `mcp_server.py` y el playground, que consumen esas formas.
- Documentación, ejemplos y pruebas que citan cadenas de tipo.

Estrategia para reducir el riesgo de una reescritura masiva:

1. Introducir el modelo estructurado en un único módulo de tipos, sin cambiar todavía la sintaxis del lenguaje.
2. Mantener la representación textual como capa de presentación y como valor inicial de compatibilidad.
3. Migrar primero las operaciones puras del modelo: construcción, identidad, equivalencia, raíz y presentación.
4. Adaptar después el checker y el intérprete, sustituyendo comparaciones de cadenas por las operaciones del modelo.
5. Añadir los tipos compuestos y la sintaxis `[...]` cuando el modelo ya esté probado internamente.
6. Extender las herramientas y los esquemas al final, con `type_repr` aditivo.

Pruebas futuras necesarias (no ejecutadas en este encargo):

- igualdad y diferencia de primitivos, refinados, declarados y compuestos;
- anidamiento (`List[Option[Int]]`) y aridad incorrecta;
- presentación canónica y estabilidad del formato;
- ensanchamiento de refinados y rechazo de la dirección contraria sin construcción explícita;
- diagnóstico con tipo esperado/encontrado y posición;
- compatibilidad de `type` y validación de `type_repr` contra los esquemas;
- regresión de todos los programas y ejemplos existentes;
- rendimiento de las operaciones del modelo en programas representativos.

**D01.10. Alternativas y costes**

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| Mantener cadenas y analizarlas cuando haga falta | Cambio aparente mínimo | Igualdad, aridad, unificación y diagnóstico ad hoc; deuda creciente | Rechazada como base |
| Álgebra estructurada mínima (`Type`/`TypeExpr`) | Correcta, extensible, buena para herramientas | Requiere migrar checker y tooling | **Recomendada** |
| Modelo estructural por defecto | Flexible | Identidad débil y refactors peligrosos | Aplazada a D02 |
| Hindley-Milner completo | Menos anotaciones | Complejidad y mensajes difíciles | Aplazada; no es requisito inicial |
| Typeclasses desde el inicio | Genéricos más expresivos | Resolución y complejidad prematuras | Aplazadas |
| Verificación formal de refinados | Más garantías | Fuera del alcance y del modelo actual | No forma parte de D01 |

Coste y complejidad que añade el modelo recomendado:

- un módulo de tipos y un cambio profundo en `checker.py`;
- migración de firmas, símbolos, tipos de expresiones y refinados;
- adaptación de diagnósticos, tooling y esquemas;
- riesgo de que la primera versión sea demasiado limitada en genéricos, aceptable si el modelo permite crecer.

Riesgos abiertos:

- rendimiento de la comparación y de la sustitución en programas grandes;
- ergonomía de la inferencia y calidad de los mensajes;
- identidad de tipos declarados cuando existan módulos;
- forma y versionado de `type_repr`;
- igualdad de tipos de función cuando se incorporen;
- posible necesidad de alias de tipo y su relación con la identidad.

**D01.11. Cuestiones abiertas de D01**

1. **Identidad de tipos declarados entre archivos.** Recomendación: nombre cualificado por módulo; la forma exacta depende de D13. Abierta.
2. **`Void` como tipo.** Recomendación: solo como resultado de función; no como valor. Abierta a confirmación.
3. **Alias de tipo.** Recomendación: un alias se resuelve a su tipo canónico y no crea identidad nueva. Abierta; no bloquea D01.
4. **`Function` en el modelo.** Recomendación: representar la firma internamente desde el principio, pero no exponerla como tipo de valor hasta que existan funciones como valores. Abierta.
5. **`type_repr`.** Recomendación: campo aditivo, opcional y versionado; nombre y forma se coordinan con D16. Abierta.
6. **Igualdad sobre variables de tipo.** Recomendación: permitir `==`/`!=` solo para tipos de valor y no para funciones. Abierta a confirmación.
7. **Alcance de los refinados compuestos.** Recomendación: representarlos desde D01; limitar sus predicados en D04. Abierta.

Ninguna de estas cuestiones impide aprobar la dirección principal de D01; se resuelven al implementar cada fase o en las decisiones D02–D04 y D13/D16.

#### B.2.2. Tipos compuestos y constructores genéricos

- `List[T]`: constructor integrado, aridad 1.
- `Option[T]`: constructor de la prelude, aridad 1.
- `Result[T,E]`: constructor de la prelude, aridad 2.
- Los registros y enums definidos por el usuario tienen aridad igual al número de parámetros de tipo declarados; inicialmente pueden ser no genéricos.
- Invariancia por defecto en los argumentos: `List[Int]` no es asignable a `List[Text]`. La covarianza se aplaza hasta que exista una regla explícita y, preferiblemente, inmutabilidad garantizada.
- Sin `Any`, sin subtipado por anchura y sin conversiones implícitas.

#### B.2.3. Variables de tipo y límites iniciales de la genericidad

- Declaración explícita: `fn f[T](x: T) -> T`, `type Caja[T] = { valor: T }`.
- Sin typeclasses en la primera versión.
- En el cuerpo de una función genérica, una variable de tipo `T` solo puede:
  - pasarse a otra función que espere `T`;
  - devolverse;
  - almacenarse en una estructura que acepte `T`;
  - compararse con `==`/`!=` solo si se decide que la igualdad estructural es total para todos los tipos de valor. Recomendación: permitirla para tipos de valor, no para funciones.
- No se permite aritmética sobre `T`, acceso a campos de `T`, ordenación de `T` ni ninguna operación que exija una restricción. Es una limitación deliberada y documentable.
- Sin tipos de rango superior, sin generalización Hindley-Milner y sin recursión polimórfica sin anotación.

#### B.2.4. Tipos nominales frente a estructurales

Para registros y enums, la recomendación es **nominal**:

- La identidad del tipo es su declaración (módulo + nombre), no la forma de sus campos.
- Dos registros con los mismos campos no son intercambiables.
- Ventajas: contratos estables, mensajes claros, evolución controlada, mejor base para agentes y para detección de impacto.
- Inconvenientes: no hay subtipado por anchura; una conversión entre formas equivalentes debe ser explícita.
- Los tipos estructurales/row types pueden añadirse después como construcción explícita, no como defecto.

#### B.2.5. Inferencia y límites

- Inferencia local para `let`/`var` a partir del inicializador, como hoy.
- Unificación de primer orden en llamadas para inferir argumentos de tipo.
- Sin generalización automática, sin tipos de rango superior, sin inferencia a través de módulos.
- `let xs = []` exige anotación (`let xs: List[Int] = []`); no se inventa el tipo del elemento.
- Si un argumento de tipo queda ambiguo, error dedicado con sugerencia de anotación.
- Los builtins genéricos se declaran con variables de tipo y se instancian en la llamada.
- La inferencia no debe impedir diagnósticos claros: si no puede explicar por qué eligió un tipo, debe pedir una anotación.

#### B.2.6. Tipos refinados y garantías verificables

- Un tipo refinado puede refinar cualquier tipo de valor, no solo builtins: `type NonEmpty = List[Int] where List.length(value) > 0`.
- La condición debe ser `Bool`, pura y total. Inicialmente:
  - puede usar operadores y funciones builtin puras;
  - puede acceder a campos de registros y a constructores de enums si la operación es total;
  - **no** puede llamar a funciones del programa, salvo que en el futuro exista un análisis de pureza/terminación.
- Las constantes se comprueban estáticamente; los valores calculados entran con `T(x)`, comprobado al ejecutar (`E4003`).
- Se amplía la comprobación de constantes a literales compuestos, con el mismo presupuesto de trabajo (`MAX_REFINEMENT_STEPS`, `E2019`).
- Los contratos pueden usar valores refinados como su tipo base (widening). `ensures` puede devolver un tipo refinado; la función debe devolver una constante válida o `T(x)`.
- No se promete que una condición refinada sea decidible en general. El checker evalúa lo que puede y reporta el límite.
- La exhaustividad sobre tipos refinados es conservadora: se exige comodín salvo prueba; no se inventa una demostración.

#### B.2.7. Diagnósticos y representación

- Códigos estables y específicos: tipo desconocido, aridad incorrecta, argumento incompatible, tipo ambiguo, campo duplicado/desconocido/faltante, patrón inválido, etc.
- `display` canónico: `List[Int]`, `Result[Int, Text]`, `{nombre: Text, edad: Int}`, `Option[Int]`.
- JSON: mantener `type` como cadena y añadir `type_repr` estructurado; no eliminar campos existentes.
- Diagnósticos con posición, etiqueta concreta, notas y sugerencia solo si está fundamentada.
- Para herramientas, añadir `related` cuando aporte (“declarado aquí”, “tipo esperado aquí”).

### B.3. Alternativas

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| Codificar tipos compuestos como cadenas (`"List[Int]"`) | Cambio aparente mínimo | Igualdad, sustitución, unificación y errores ad hoc; deuda alta | Rechazada como base arquitectónica |
| Álgebra de tipos con constructores y variables | Correcta, extensible, buena para herramientas | Reescritura profunda | **Recomendada** |
| Tipado estructural por defecto | Flexible | Identidad débil, contratos frágiles, refactors peligrosos | Rechazada como defecto; posible extensión |
| `Option`/`Result` como casos especiales | Menos trabajo inicial | Inconsistencia y difícil extensión | Rechazada |
| Typeclasses desde el inicio | Genéricos más expresivos | Retrasa el núcleo y añade complejidad | Aplazada |
| Inferencia Hindley-Milner completa | Menos anotaciones | Complejidad, mensajes difíciles, límites poco claros | Aplazada |

### B.4. Consecuencias

**Positivas:** tipos compuestos expresables; `Option`/`Result` consistentes; mejores diagnósticos; herramientas con tipos estructurados; base para evidencia e impacto.

**Negativas:** reescritura de checker, parser, AST, intérprete, tooling y esquemas; más complejidad en inferencia y errores; coste de migración alto; riesgo de que la primera versión de genéricos sea demasiado limitada.

### B.5. Evidencia pendiente **[?]**

- No hay prototipo del álgebra de tipos ni medición del coste de migración.
- No se ha validado la ergonomía de la inferencia ni de los mensajes de error.
- No se ha medido el impacto en rendimiento del intérprete.
- No se ha probado la compatibilidad de `type_repr` con consumidores existentes.
- No se ha decidido si la igualdad estructural debe ser total para todos los tipos de valor.

---

## C. Enumeraciones, patrones y exhaustividad

### C.1. Estado actual **[V]**

- No hay enums, uniones etiquetadas, `match` ni patrones.
- `enum`, `match`, `for`, `import`, `pub`, `in`, `break` y `continue` están reservadas; `for`/`enum`/`match` producen `E1103` si se usan.
- `record` **no** está reservada; introducirla como palabra clave rompería nombres existentes.
- `Option`/`Result` no existen; `limitations.md` lo declara y `language-spec.md` los sitúa entre las funcionalidades previstas.
- Los tipos refinados actuales solo refinan builtins; no hay variantes.

### C.2. Propuesta **[P]**

#### C.2.1. Enums y uniones etiquetadas

Usar la declaración de tipo existente, sin introducir `record` como palabra clave global:

```text
type Option[T] = enum {
    None,
    Some(valor: T),
}

type Result[T, E] = enum {
    Ok(valor: T),
    Err(error: E),
}
```

- `enum` se usa como palabra contextual dentro de `type`; ya está reservada.
- Constructores con nombre, posibles nulos (`None`) y campos.
- Constructores namespaced por el tipo; resolución sin cualificar si no hay ambigüedad, o cualificada (`Option.Some(x)`) si la hay.
- Sin métodos ni `self` inicialmente; las operaciones son funciones.
- Igualdad estructural; orden no definido.
- `to_text`/`print` con representación canónica documentada.

#### C.2.2. Pattern matching

`match` como expresión, y por tanto también en posición de sentencia:

```text
let valor = match resultado {
    Ok(v) => v,
    Err(e) => 0,
}
```

- Brazos con expresión o bloque; `return` permitido dentro de un bloque.
- Patrones iniciales:
  - literal;
  - comodín `_`;
  - variable;
  - constructor (`Some(x)`, `None`, `Ok(v)`, `Err(e)`);
  - registro (`Persona { nombre: n, edad: e }`);
  - lista (`[]`, `[x, ...resto]`, `[a, b]`).
- Se aplazan: guardas (`if` en el patrón), or-patterns (`p | q`), patrones de rango, patrones de mapas.
- `_` debe tratarse como patrón, no como variable ligada; si hoy se permite como identificador, hay que decidir si se reserva o se restringe contextualmente.

#### C.2.3. Exhaustividad y casos no cubiertos

- `match` como expresión exige exhaustividad.
- Algoritmo de utilidad (estilo Maranget) sobre constructores:
  - `Bool`: `true`/`false`;
  - enums: todos los constructores;
  - registros: todos los campos;
  - listas: `[]` y `cons`;
  - `Int`/`Text`: exigen comodín;
  - refinados: exigen comodín salvo prueba;
  - anidados: se desciende.
- Diagnóstico con **testigo**: “falta `None`”, “falta `Err(_)`”, “falta `[]`”.
- Patrón inalcanzable o redundante: decidir entre error y warning. Recomendación inicial: error, porque hoy no existe infraestructura de warnings; revisar cuando exista.
- Si el checker acepta un `match`, el intérprete no debe encontrar un caso sin gestionar; si lo encuentra, es un error interno.

#### C.2.4. `Option` y `Result`

Deben construirse sobre enums y `match`, no como excepciones del lenguaje:

- `Option[T]` y `Result[T,E]` son enums ordinarios de la prelude.
- No hay `unwrap` implícito ni excepciones.
- `?` para propagación de errores se aplaza; primero se usa `match`.
- Las funciones parciales (`List.get`, `List.head`) declaran `requires` y siguen el modelo actual de contratos; cuando `Option` exista, se añaden variantes totales (`List.get_option`), sin cambiar la semántica de las parciales.
- Los contratos pueden usar `Option`/`Result` como tipos; `ensures` puede devolver `Ok(...)`/`Err(...)`.

### C.3. Alternativas

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| Enums + `match` + exhaustividad | General, consistente, base para `Option`/`Result` | Más trabajo inicial | **Recomendada** |
| `Option`/`Result` especiales | Menos trabajo inicial | Inconsistencia, difícil de extender | Rechazada |
| `match` como sentencia solamente | Más cerca del `if` actual | Peor ergonomía para `Option`/`Result` | Aplazada; se prefiere expresión |
| Exhaustividad opcional | Menos errores al principio | Deja casos sin gestionar | Rechazada para `match` expresión |
| Guardas/or-patterns desde el inicio | Más expresivo | Complica exhaustividad y alcanzabilidad | Aplazadas |

### C.4. Consecuencias

**Positivas:** `Option`/`Result` sin casos especiales; código más seguro; diagnósticos de casos faltantes; base para evidencia de cobertura de variantes.

**Negativas:** complejidad del algoritmo de exhaustividad; necesidad de nuevos nodos AST, tokens y diagnósticos; riesgo de mensajes difíciles; `match` expresión exige decidir la relación con `if` sentencia.

### C.5. Evidencia pendiente **[?]**

- No hay implementación ni prueba del algoritmo de exhaustividad.
- No se ha validado la ergonomía de `match` expresión frente a `match` sentencia.
- No se ha decidido el tratamiento de `_` si hoy puede ser identificador.
- No se ha medido el coste de los patrones anidados.
- No se ha probado la calidad de los testigos de no exhaustividad.

---

## D. Colecciones e iteración

### D.1. Estado actual **[V]**

- No hay listas, mapas, tuplas ni registros.
- No hay `for`; se usa `while` con contador.
- Todo `while` exige `decreases` (`E2021`) y puede tener `invariant`; la medida y los invariantes se comprueban en ejecución (`E4005`, `E4006`).
- No hay `break` ni `continue`.
- No hay límite de tiempo ni de memoria en `nex`; el playground tiene timeout y límites.
- No se demuestra estáticamente la terminación de funciones recursivas; se limita la profundidad a 1000 llamadas (`E3004`).

### D.2. Propuesta **[P]**

#### D.2.1. Listas

- `List[T]` nominal, inmutable y finita.
- Literales: `[1, 2, 3]`, `[]`; `[]` exige anotación si no se puede inferir.
- Operaciones esenciales: `List.length`, `List.get`, `List.append`, `List.concat`, `List.contains`.
- `List.get(xs, i)` es parcial y declara `requires 0 <= i and i < List.length(xs)`; el contrato se comprueba en ejecución. Cuando exista `Option`, se añade una variante total.
- Sin mutación de elementos; `var` puede reasignar la variable a otra lista, no modificar la lista original.
- Igualdad estructural; `to_text`/`print` con representación canónica.

#### D.2.2. `for` sobre listas

```text
for x in xs {
    ...
}
```

- `xs` se evalúa una vez y debe ser `List[T]`.
- `x` es inmutable y de tipo `T`.
- El cuerpo es un bloque con su propio ámbito.
- No exige `decreases`: la lista es finita por construcción.
- Puede tener `invariant` (misma semántica que en `while`), pero no `decreases`.
- No hay `break` ni `continue` en la primera versión.
- No se añade `for` sobre rangos ni sobre `Text`; eso exigiría `Range` o una conversión explícita y sería un caso especial.

#### D.2.3. Terminación y garantías

| Garantía | Tipo | Qué se puede afirmar |
|---|---|---|
| `for` sobre `List[T]` inmutable y finita | Estructural | Termina si la lista es finita; no promete rapidez |
| `while` con `decreases` | En ejecución | La medida se comprueba; no se demuestra estáticamente |
| Recursividad | Límite de ejecución | Se detiene con `E3004`; no hay prueba de terminación |
| Programa que termina pero tarda | Documentada | Puede consumir tiempo/memoria; el playground tiene timeout; `nex` no |
| División por cero, overflow | En ejecución | No se detectan estáticamente |

**Importante:** “termina” no significa “termina pronto”. Un `for` sobre una lista enorme puede tardar. El playground lo corta; `nex` no tiene límite de tiempo. No se debe prometer más.

#### D.2.4. `break` y `continue`

Recomendación: **no introducirlos inicialmente**.

Motivos:

- `continue` es relativamente simple, pero añade una ruta de control que los invariantes deben tolerar.
- `break` invalida el razonamiento “el bucle terminó porque la condición es falsa”; cualquier postcondición que dependa de la condición de salida deja de ser válida.
- Para que `break` fuera verificable haría falta una condición de salida explícita o un valor de bucle, que es otra construcción.
- No hay demanda demostrada; se puede escribir con `while`, condición o `return`.

Si se añaden después, deben tener semántica documentada, interacción con `invariant` y pruebas de que no rompen la terminación.

### D.3. Alternativas

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| Listas inmutables | Sin aliasing; contratos y terminación simples | Coste de copia; puede ser lento | **Recomendada** |
| Listas mutables | Rendimiento intuitivo | Aliasing, contratos, terminación, igualdad complejos | Aplazada |
| `for` sobre rangos | Cómodo | Otro caso especial; sin tipo `Range` | Aplazada |
| Iteradores/lazy | Potente | Terminación y efectos difíciles | Aplazada |
| `break`/`continue` desde el inicio | Familiar | Rompe razonamiento de invariantes | Aplazada |

### D.4. Consecuencias

**Positivas:** iteración clara y terminante; listas como base de `Input`, stdlib y datos; `for` sin medida obligatoria; menos casos especiales.

**Negativas:** inmutabilidad puede costar; sin `break` algunos algoritmos son más verbosos; `List.get` parcial exige contratos; la stdlib necesitará más funciones.

### D.5. Evidencia pendiente **[?]**

- No se ha medido el coste de listas inmutables en el intérprete.
- No se ha validado si `for` sin `break`/`continue` es suficiente para las tareas objetivo.
- No se ha decidido la representación interna (tupla, lista persistente, etc.).
- No se ha probado la ergonomía de `List.get` parcial frente a `Option`.
- No se ha medido el impacto de `for` en el playground.

---

## E. Entrada, efectos y testabilidad

### E.1. Estado actual **[V]**

- Un programa NEXORA solo puede calcular y escribir con `print`; no hay entrada de teclado, argumentos, archivos ni red.
- `main` no puede tener parámetros (`E2013`) y debe devolver `Void` (`E2004`).
- El playground ejecuta el worker con entorno vacío; no hay estado global del servidor.
- `nex test` evalúa `example` sin ejecutar `main`.
- El intérprete no usa `eval` ni `exec`; las pruebas de seguridad lo comprueban.

### E.2. Propuesta **[P]**

#### E.2.1. Entrada explícita

Introducir un tipo de prelude `Input`:

```text
type Input = {
    args: List[Text],
    stdin: Text,
}
```

El programa puede declarar:

- `fn main() -> Void` (compatibilidad), o
- `fn main(input: Input) -> Void`.

El runtime construye `Input` con argumentos y entrada estándar. No hay `read_line()` global, ni variables de entorno, ni archivos, ni red.

- `nex run archivo.nex -- arg1 arg2` y la entrada estándar alimentan `Input`.
- `nex test` construye un `Input` vacío por defecto; las funciones que necesitan entrada se prueban pasándoles un `Input` construido explícitamente en un `example` cuando los registros existan.
- El playground añade un campo `input` a la petición y lo pasa al worker; sigue sin acceso a archivos/red.
- `Text.lines(text) -> List[Text]` o una operación equivalente en la stdlib procesa `stdin`; no se hace un caso especial de `Input`.

#### E.2.2. Errores de entrada

- La entrada ausente o inválida se representa con `Option`/`Result` cuando existan; antes, con contratos y valores válidos.
- No se lanzan excepciones del lenguaje.
- `Int.parse`/`Float.parse` ya tienen `requires` y `E4001`; se mantiene ese modelo.
- Los errores de entrada deben ser datos, no efectos ocultos.

#### E.2.3. Efectos explícitos sin sistema formal

En la primera versión no se introduce un sistema de efectos algebraicos. Se mantienen explícitos:

- `print`: salida.
- `Input`: entrada inyectada como parámetro.
- Errores de ejecución: `E3001`–`E4006`, documentados.
- Sin archivos, red, procesos, variables de entorno ni reloj.

Un sistema de efectos (`uses`) puede explorarse después; no es necesario para la propuesta diferencial y añadiría carga de anotación.

### E.3. Alternativas

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| `Input` explícito | Testable, reproducible, seguro | Cambia `main` o exige dos formas | **Recomendada** |
| `read_line()` global | Cómodo | Estado oculto, no testable, inseguro | Rechazada |
| Mónada `IO` | Efectos explícitos | Demasiado pesado para el lenguaje actual | Aplazada |
| Sistema de efectos `uses` | Documenta efectos | Carga de anotación y análisis | Aplazada |
| Variables de entorno | Cómodo para configuración | Secretos y no determinismo | Rechazada para el lenguaje |

### E.4. Consecuencias

**Positivas:** pruebas reproducibles; playground con entrada controlada; sin estado global; base para `nex test` de funciones con entrada.

**Negativas:** dos formas de `main`; necesidad de `Input` y registros; la entrada interactiva/streaming no está cubierta; la stdlib necesita operaciones de texto.

### E.5. Evidencia pendiente **[?]**

- La API exacta de `Input` no está aprobada.
- No se ha decidido `stdin: Text` frente a `stdin: List[Text]`.
- No se ha validado la compatibilidad de `main()` y `main(input)`.
- No se ha diseñado la interfaz de entrada del playground.
- No se ha medido el coste de inyectar entrada en `nex test`.

---

## F. Módulos y visibilidad

### F.1. Estado actual **[V]**

- Un programa es un único archivo.
- `nex context` y `nex symbols` describen un solo archivo.
- No hay imports, exports, visibilidad, namespaces ni proyecto.
- El checker resuelve nombres en un único espacio global + ámbitos locales.
- `nex inspect`, `context`, `symbols` y MCP no tienen concepto de módulo.

### F.2. Problemas que hay que resolver antes de implementar

1. **Imports y exports:** qué se importa, con qué nombre y cómo se resuelve.
2. **Visibilidad:** `pub`/privado; qué se exporta por defecto.
3. **Dependencias y ciclos:** grafo, orden topológico, rechazo de ciclos.
4. **Resolución de nombres:** cualificada, `from`-import, alias, conflictos.
5. **Organización de proyectos:** raíz, manifest, rutas, stdlib.
6. **Cachés e invalidación:** contenido, dependencias, cambios de interfaz.
7. **Herramientas:** `inspect` por archivo, `context`/`symbols` por proyecto, IDs estables, grafo.
8. **Seguridad:** imports de stdlib vs código de usuario; no acceso a archivos arbitrarios.

### F.3. Propuesta **[P]**

- **Archivo = módulo.** Nombre por defecto: el del archivo; declaración opcional `module a.b.c`.
- **Imports:** `import a.b.c`, `from a.b.c import f, Tipo`, alias `import a.b.c as c`.
- **Visibilidad:** `pub` en funciones y tipos; privado por defecto. Sin `pub` en variables locales.
- **Sin imports comodín** en la primera versión; sin re-exportaciones; sin ciclos.
- **Resolución:** nombres cualificados por defecto; `from` introduce nombres; conflictos = error.
- **Proyecto:** raíz detectable por `nexora.toml` (o `nex.project`) con nombre/versión; sin registro de paquetes en 1.0. Los módulos de la stdlib se resuelven desde la instalación.
- **Orden:** grafo acíclico, orden topológico; sin inicialización de módulo con efectos (solo declaraciones).
- **Caché:** no se implementa en la primera fase; se diseña con hash de contenido + huella de interfaz + grafo de dependencias. Invalidación conservadora: si cambia una interfaz pública, se reanalizan los dependientes.
- **Herramientas:** `nex inspect` sigue siendo por archivo; `nex context`/`symbols` aceptan archivo o proyecto; se añaden `module`, `imports`, `exports`, `dependencies`, `dependents`, `cycles`.

### F.4. Impacto en herramientas

| Herramienta | Hoy | Con módulos |
|---|---|---|
| `nex inspect` | AST de un archivo | AST de un archivo + `module`, `imports`; sigue siendo local |
| `nex context` | Resumen de un archivo | Resumen de proyecto o archivo; grafo de llamadas entre módulos; API pública |
| `nex symbols` | Símbolos de un archivo | Símbolos de proyecto; IDs con módulo; visibilidad; filtros |
| MCP | 7 herramientas de un archivo | Añadir `project_context`; el resto conserva compatibilidad |
| JSON | Esquemas por archivo | Campos aditivos; nuevo esquema de proyecto si hace falta |

### F.5. Secuencia segura de implementación

1. **Ahora:** decidir semántica de módulos, visibilidad, ciclos, resolución y forma del manifest.
2. **Después de tipos/patrones:** añadir `module`/`import`/`from`/`pub` al lexer/parser/AST.
3. **Checker:** tabla de módulos, resolución, visibilidad, ciclos.
4. **Cargador de proyecto:** raíz, manifest, orden topológico, stdlib.
5. **Herramientas:** contexto/símbolos de proyecto, IDs, grafo.
6. **Caché:** solo cuando el análisis de proyecto sea estable y medible.

### F.6. Alternativas

| Alternativa | Ventajas | Inconvenientes | Consecuencia |
|---|---|---|---|
| Archivo = módulo, imports explícitos | Claro, tooling-friendly | Más sintaxis | **Recomendada** |
| Módulos implícitos por ruta | Menos sintaxis | Colisiones y ambigüedad | Rechazada |
| Espacio global plano | Simple | No escala | Rechazada para 1.0 |
| Ciclos permitidos | Flexible | Orden de inicialización y análisis complejos | Rechazada inicialmente |
| Registro de paquetes | Ecosistema | Fuera de alcance | Aplazado |
| Imports comodín | Cómodo | Conflictos y difícil análisis | Aplazados |

### F.7. Consecuencias

**Positivas:** stdlib posible; proyectos reales; grafo para IA; API pública explícita.

**Negativas:** cambio profundo en checker, tooling, esquemas y CLI; necesidad de manifest y caché; riesgo de complejidad de resolución.

### F.8. Evidencia pendiente **[?]**

- No hay diseño validado de manifest ni de resolución de nombres.
- No se ha medido el coste de análisis de proyectos.
- No se ha probado la invalidación de caché.
- No se ha decidido si `nex inspect` debe aceptar proyectos o solo archivos.
- No se ha evaluado el impacto en el playground (que ejecuta un archivo).

---

## G. Arquitectura vertical de las funcionalidades

### G.1. Capas que deben mantenerse coherentes

Para cada capacidad nueva, el cambio debe atravesar estas capas:

| Capa | Artefactos | Qué debe cumplir |
|---|---|---|
| Léxico | `tokens.py`, `lexer.py` | Tokens, palabras reservadas, posiciones |
| Sintaxis | `ast_nodes.py`, `parser.py` | Nodos inmutables con `Span`, recuperación de errores |
| Tipos | `checker.py` | Reglas, firmas, símbolos, rutas de retorno, diagnósticos |
| Ejecución | `interpreter.py` | Semántica, valores, errores de ejecución, contratos |
| Diagnósticos | `diagnostics.py` | Código estable, categoría, etiqueta, notas, sugerencia |
| CLI | `cli.py` | Comando, formatos, códigos de salida |
| JSON/MCP | `schemas.py`, `tooling.py`, `mcp_server.py` | Esquema, documento, paridad, solo lectura |
| Documentación | `language-spec.md`, docs temáticas, ADR | Semántica y límites |
| Ejemplos | `examples/`, docs | Ejecutables y con salida esperada |
| Tests | `tests/` | Positivos, negativos, límites, regresión |
| Playground | `worker.py`, `servidor/src/playground/` | Misma semántica, límites, seguridad |

### G.2. Definición de “terminado”

Una funcionalidad está terminada cuando:

1. Tiene semántica escrita en la especificación y en un ADR o documento de diseño.
2. El lexer/parser la reconocen y producen nodos con posición.
3. El checker la tipa y diagnostica sus errores.
4. El intérprete la ejecuta con la semántica documentada.
5. Tiene códigos de diagnóstico estables y mensajes con posición.
6. `nex check`, `inspect`, `context` y `symbols` la representan correctamente.
7. Los esquemas JSON se actualizan de forma aditiva y validan la salida real.
8. La CLI, la API y MCP devuelven el mismo documento cuando comparten capacidad.
9. Hay ejemplos ejecutables y documentación sincronizada.
10. Hay pruebas positivas, negativas, de límites y de regresión.
11. El playground la ejecuta con los mismos límites y sin debilitar la seguridad.
12. Los programas existentes siguen funcionando o hay una migración documentada.

### G.3. Cómo evitar que las herramientas queden por detrás

- **Esquema primero:** diseñar el nodo/forma JSON antes de implementar el parser, para que el checker y las herramientas no inventen formas incompatibles.
- **Prueba de paridad:** cada funcionalidad debe tener una prueba que compare CLI/API/MCP y la salida del intérprete.
- **`capabilities.features`:** declarar qué está soportado y qué no, para que un agente no alucine.
- **Documentación ejecutable:** los ejemplos de la especificación se ejecutan en pruebas; si no, se detecta el desfase.
- **Prohibición de campos vacíos:** si una herramienta no puede representar una funcionalidad, la funcionalidad no está terminada.
- **Revisión de esquema:** cualquier campo nuevo se añade al final; cualquier eliminación exige subir la versión del esquema.

### G.4. Matriz por fase

| Fase | Léxico/parser | Tipos | Intérprete | Diagnósticos | CLI/JSON/MCP | Docs/ejemplos | Tests | Playground |
|---|---|---|---|---|---|---|---|---|
| Tipos base | — | `Type` | — | códigos de tipo | `type_repr` | spec | unitarios | — |
| Listas + `for` | `[` `]`, `for` | `List[T]`, `for` | listas inmutables | índices, tipos | inspect/context/symbols | ejemplos | límites | sí |
| Registros | `type X = { ... }` | nominal, campos | valores inmutables | campos | símbolos/campos | ejemplos | negativos | sí |
| Enums + `match` | `enum`, `=>`, patrones | variantes, exhaustividad | match | testigos | inspect/context | ejemplos | exhaustividad | sí |
| `Option`/`Result` | — | prelude | constructores | — | requirements | ejemplos | contracts | sí |
| Entrada | `Input` | registro | `main(input)` | entrada inválida | API/worker | ejemplos | reproducibilidad | input |
| Módulos | `module`, `import`, `pub` | tabla de módulos | carga | ciclos/visibilidad | project_context | proyecto | grafo | límites |

---

## H. Desarrollo asistido por IA y evidencia

### H.1. Estado actual **[V]/[D]**

- La CLI, la API Python y MCP comparten `tooling.py`; MCP es de solo lectura.
- `nex context` entrega firmas, contratos, variables, llamadas, llamadores, ejemplos y bucles.
- `nex symbols` entrega símbolos, referencias, tipos y builtins con contratos.
- `nex inspect` entrega el AST con tipos como cadenas.
- `tests/tooling_tasks.py` define nueve tareas de referencia; `tests/test_tooling_tasks.py` las comprueba contra las herramientas reales.
- No hay documento de requisitos con IDs, ni análisis de impacto, ni evidencia `checked`/`not_checked`, ni IDs estables de símbolos, ni grafo de proyecto, ni tipos estructurados.
- La API Python es experimental; los esquemas son versionados y aditivos.

### H.2. Propuesta incremental **[P]**

| Paso | Qué añadir | Depende de | Valor para el agente |
|---|---|---|---|
| 1 | `type_repr` estructurado + IDs estables en `inspect`/`symbols`/`context` | Modelo de tipos | Referencias estables y tipos legibles por máquina |
| 2 | `nexora.requirements/1`: inventario de contratos, refinamientos y ejemplos con ID, condición, explicación, span, procedencia, estado de comprobación y dependencias | Tipos + contratos | Comprender requisitos antes de editar |
| 3 | `evidence`: `checked`, `not_checked`, `assumptions`, `source_hash`, `tool_version` | Paso 1-2 | Honestidad sobre lo comprobado |
| 4 | `nexora.impact/1`: diff semántico, requisitos afectados, nivel de certeza, comprobaciones y límites | Requisitos + grafo de llamadas | Identificar impacto de un cambio |
| 5 | `nexora.project_context/1`: módulos, imports, exports, dependencias, ciclos, API pública | Módulos | Análisis de proyectos reales |
| 6 | `capabilities.features`: matriz de soportado/no soportado | Todo | Evitar alucinaciones |

No se propone duplicar `nexora_check` (ya existe), `nexora_types` (basta extender `inspect`/`symbols`) ni `nexora_run` en MCP (la ejecución debe ser explícita y aislada).

### H.3. Identificar requisitos afectados

El análisis de impacto debe combinar:

- **Cambios de firma:** parámetros, retorno, tipos, visibilidad.
- **Cambios de contrato:** `requires`/`ensures` añadidos, eliminados o modificados.
- **Cambios de refinamiento:** condición, base, cadena.
- **Cambios de cuerpo:** llamadas, variables, ramas, bucles.
- **Grafo de llamadas:** llamadores directos y transitivos.
- **Propagación de requisitos:** un `ensures` de una función puede ser un `requires` implícito de sus llamadores; el análisis debe decirlo, no inventarlo.
- **Nivel de certeza:** `definitely_removed`, `definitely_added`, `changed_unproved`, `possibly_weakened`, `possibly_strengthened`, `unchanged`.
- **Regla de honestidad:** no usar `proved_weakened` salvo que un fragmento decidible lo demuestre.

### H.4. Explicar relaciones y separar evidencia

Un documento de impacto debería incluir:

```json
{
  "schema": "nexora.impact/1",
  "base": {"source_hash": "…"},
  "current": {"source_hash": "…"},
  "changes": [
    {"kind": "contract_removed", "requirement_id": "…:requires:0", "assessment": "definitely_removed"},
    {"kind": "contract_changed", "requirement_id": "…:ensures:0", "assessment": "possibly_weakened",
     "reason": "the condition text changed; implication is not proved"}
  ],
  "affected": {"definitely": ["…"], "possibly": ["…"], "unknown": ["…"]},
  "checks": [
    {"name": "types", "status": "passed"},
    {"name": "exhaustiveness", "status": "passed"},
    {"name": "contracts", "status": "not_checked", "reason": "requires execution"}
  ],
  "limitations": ["weakening is conservative; only a decidable fragment is proved"]
}
```

La separación es obligatoria:

- **Verificado:** lo que una herramienta determinista ha comprobado.
- **Inferido:** lo que se deduce del grafo o del diff, con su nivel de certeza.
- **No resuelto:** lo que depende de ejecución, de decisiones humanas o de propiedades indecidibles.

### H.5. Diagnósticos, cobertura y regresiones

- Diagnósticos con código estable, posición y `related`.
- Cobertura de requisitos, no solo cobertura de código: qué contratos se han ejercitado en `nex test`/`nex run`.
- Regresiones: comparación de diagnóstico/resultados entre versiones.
- `nex test` puede informar qué ejemplos cubren qué requisitos; no debe afirmar cobertura total.
- Un agente debe poder ver “0 diagnósticos” y “contratos no comprobados” al mismo tiempo.

### H.6. Cambios compatibles sin afirmar corrección

Las herramientas pueden:

- dar restricciones y requisitos;
- proponer un diff estructurado;
- señalar conflictos;
- ejecutar comprobaciones autorizadas;
- devolver evidencia y límites.

Las herramientas **no** deben:

- aplicar cambios sin autorización;
- decir “correcto” o “verificado” sin evidencia;
- ocultar que un contrato solo se comprobó en ejecución;
- ejecutar código no confiable en MCP.

### H.7. Plan de evaluación empírica

Partir de las nueve tareas de `tests/tooling_tasks.py` y ampliar a familias:

| Familia | Tarea | Qué mide |
|---|---|---|
| A. Modificación con requisitos | Cambiar una fórmula preservando `ensures` | Preservación |
| B. Invariantes | Cambiar un bucle preservando `invariant`/`decreases` | Razonamiento |
| C. Regresión deliberada | Introducir un fallo que viola un contrato | Detección |
| D. Comprensión | ¿Quién llama y qué promete? | Uso de herramientas |
| E. Tentación de debilitar | “Haz que pase”; la vía fácil es borrar un contrato | Honestidad |
| F. Multiarchivo | Cambiar una función usada en varios módulos | Impacto |

**Condiciones:** lenguaje de referencia con tests; NEXORA sin herramientas; NEXORA con herramientas estáticas; NEXORA con herramientas + ejecución; referencia con contratos/tests equivalentes.

**Métricas:** requisitos violados detectados/no detectados; falsos positivos; contratos eliminados/debilitados; éxito de la tarea; tiempo/tokens/llamadas; calidad del diagnóstico; honestidad.

**Controles:** modelos fijados por versión, temperatura/budget fijos, repeticiones, orden aleatorizado, evaluador ciego, pruebas ocultas, publicación de todos los resultados, pre-registro de umbrales.

**Criterios de publicación:** no afirmar superioridad sin datos; publicar resultados negativos; separar hipótesis, observaciones y conclusiones; indicar límites (muestra, modelo, tarea, novedad de NEXORA).

**No se ha ejecutado nada de esto.** No hay resultados.

---

## I. Seguridad y aislamiento

### I.1. Garantías del lenguaje vs. garantías del entorno

| Nivel | Garantía | Límite |
|---|---|---|
| Lenguaje | No hay archivos, red, procesos, variables de entorno, `eval` ni `exec`; solo cálculo y `print` | Un defecto del intérprete podría romperlo |
| `nex` CLI | Ejecuta con los permisos del usuario | Sin límite de tiempo/memoria; no es sandbox |
| Worker del playground | Proceso separado por petición; entorno vacío; `-I`; límites de salida/texto; timeout externo | No es sandbox; en Windows no hay límites POSIX |
| Contenedor | Configuración `--network none`, `--read-only`, `--cap-drop ALL`, `--user 65534`, etc. | **No probado**; depende de Docker/kernel |
| Servicio | Origen, rate limit, tamaño, CSP, salida como texto | No elimina riesgos de agotamiento o defectos |

### I.2. Riesgos del playground

- **Agotamiento de recursos:** tiempo, memoria, CPU, salida; el timeout externo ayuda, pero no es aislamiento.
- **Defecto del intérprete:** código malicioso podría explotar un fallo; el lenguaje no es una sandbox.
- **Contenedor:** escapar del contenedor o del kernel; Docker mal configurado; imagen mutable por etiqueta; daemon Docker con privilegios.
- **Usuario del servidor:** pertenecer al grupo `docker` equivale a privilegios de administrador; un compromiso del servidor web controla el equipo.
- **Caché/limpieza:** contenedores huérfanos tras una caída; el servidor no los busca al arrancar.
- **Inyección de salida:** la salida se trata como texto y se escribe con `textContent`; hay que mantenerlo.
- **CSRF/origen:** la comprobación de `Origin` es necesaria; CORS limitado.
- **Abuso:** rate limit por cliente, pero IPv6/red distribuida; no hay CAPTCHA en playground.
- **Secretos:** el worker debe seguir con entorno vacío; nunca pasar `.env` ni credenciales.

### I.3. Pruebas necesarias antes de exposición pública

No ejecutadas en este encargo:

1. Límites POSIX de memoria, CPU, archivos, procesos y wall-clock en Linux/macOS.
2. Worker en contenedor: sin red, solo lectura, usuario no privilegiado, `--init`, límites de memoria/CPU/PIDs.
3. Timeout y limpieza de contenedores; `docker rm -f` y confirmación con `docker ps`.
4. Caída del servidor y contenedores huérfanos.
5. Imagen ausente y `--pull never`.
6. Concurrencia y cola; 503 `busy`.
7. Origen/CORS/CSP; salida con HTML/JS.
8. Fuzzing del parser/checker/intérprete y entradas truncadas.
9. Memoria agotada en análisis y ejecución.
10. Aislamiento real con Docker/kernel versionados; no basta con validar la orden.

### I.4. Puerta de despliegue

El playground debe permanecer desactivado por defecto (`PLAYGROUND_ENABLED=false`) y no debe exponerse públicamente hasta completar la lista anterior. En producción, el servidor ya exige la orden de contenedor admitida si el playground está activo; aun así, **configurar la orden no demuestra el aislamiento**. **[V]/[D]**

---

## J. Decisiones, alternativas y cuestiones abiertas

> Ninguna decisión nueva de esta tabla está aprobada. “Decidida previamente” se refiere a ADR ya aceptados que este documento no reabre.

| ID | Tema | Recomendación propuesta | Alternativas | Motivo | Coste/riesgo | Evidencia pendiente | Dependencias | Estado |
|---|---|---|---|---|---|---|---|---|
| D01 | Representación interna de tipos | Modelo estructurado `Type` + `TypeExpr`; cadenas solo para presentación; identidad estructural/nominal; `type_repr` aditivo | Seguir con cadenas; HM/typeclasses desde el inicio | Corrección, tipos anidados, diagnósticos y tooling | Alto (migración de checker/tooling) | Prototipo de igualdad/display, migración, rendimiento y estabilidad de `type_repr` | — | **Propuesta pendiente de aprobación** |
| D02 | Registros nominales vs. estructurales | Nominales por defecto; estructural explícito después | Estructural por defecto | Contratos estables, mensajes claros | Medio | Ergonomía, migración | D01 | Propuesta |
| D03 | Genéricos e inferencia | Paramétricos de primer orden; sin typeclasses; inferencia local + unificación | HM; typeclasses; sin genéricos | Equilibrio potencia/coste | Alto | Usabilidad, mensajes | D01 | Propuesta |
| D04 | Refinamientos sobre compuestos | Predicados puros/totales; constantes estáticas + `T(x)` | Contratos completos; verificación formal | Mantener garantía actual y honestidad | Medio | Lenguaje de predicados, rendimiento | D01 | Propuesta |
| D05 | Enums/uniones etiquetadas | `type X[T] = enum { ... }`; constructores namespaced | `enum` global; clases selladas; especiales | Generalidad y consistencia | Medio | Ergonomía, colisiones | D01 | Propuesta |
| D06 | Pattern matching | `match` expresión con patrones y bloques | `match` sentencia; visitor | Base para Option/Result | Alto | Ergonomía, AST, parser | D05 | Propuesta |
| D07 | Exhaustividad | Obligatoria; testigo; inalcanzable error inicial | Opcional; warning | Evitar casos sin gestionar | Medio | Calidad de testigos, falso positivo | D06 | Propuesta |
| D08 | Listas | Inmutables, finitas, `List[T]` | Mutables; persistentes; lazy | Sin aliasing; terminación simple | Medio | Rendimiento, memoria | D01 | Propuesta |
| D09 | `for` y terminación | `for` sobre `List[T]`; `invariant` opcional; sin `decreases` | Rangos; iteradores; `for` con medida | Terminación estructural clara | Medio | Suficiencia, rendimiento | D08 | Propuesta |
| D10 | `break`/`continue` | No introducir inicialmente | Introducir ambos; solo `continue` | Evitar romper invariantes/salida | Bajo/medio | Demanda real, semántica de salida | D09 | Propuesta |
| D11 | Entrada | `Input` explícito; `main()` o `main(input)` | `read_line` global; IO monad | Testabilidad y seguridad | Bajo/medio | API, stdin, playground | D08, D02 | Propuesta |
| D12 | Errores | `Option`/`Result` como enums; `?` después | Excepciones; solo contratos | Consistencia y composición | Medio | Ergonomía, `?` | D05-D07 | Propuesta |
| D13 | Módulos | Archivo=módulo; `import`/`from`; `pub`; sin ciclos | Implícitos; plano; ciclos | Proyectos reales y stdlib | Alto | Resolución, tooling, caché | D01-D12 | Propuesta |
| D14 | Proyecto y caché | Manifest mínimo; caché por contenido + interfaz + grafo | Sin proyecto; caché por mtime | Análisis de proyectos | Medio | Invalidación, rendimiento | D13 | Propuesta |
| D15 | Requisitos e impacto | `requirements` + `impact` + `evidence`; solo lectura | Extender solo `context` | Propuesta diferencial | Medio | Precisión/recall, ergonomía | D01, D06, D13 | Propuesta |
| D16 | IDs y esquemas | IDs por ruta de declaración; JSON aditivo; `type_repr` | IDs por línea; sin IDs | Estabilidad para agentes | Medio | Compatibilidad, migración | D15 | Propuesta |
| D17 | Seguridad/playground | Desactivado por defecto; puerta de aislamiento; límites | Exposición pública ya; solo proceso | Ejecuta código de terceros | Alto | Pruebas de aislamiento | — | Propuesta |
| D18 | Alcance de 1.0 | Núcleo + módulos + stdlib + herramientas + seguridad; LSP/REPL opcionales | Todo; fecha fija | Coherencia y calidad | Alto | Criterios K | Todas | Propuesta |
| D19 | Contratos en ejecución | Mantener 0004/0007: se comprueban al ejecutar, no se demuestran | Verificación formal | Ya decidido | — | — | — | Decidida previamente |
| D20 | Intérprete solo programas comprobados | Mantener 0002 | Ejecución sin checker | Ya decidido | — | — | — | Decidida previamente |
| D21 | Requisitos como característica diferencial | Mantener 0006; la hipótesis sigue sin medir | Otra característica | Ya decidido | — | Evaluación H.7 | — | Decidida previamente (dirección), hipótesis pendiente |

### J.1. Cuestiones abiertas que requieren aprobación

1. ¿Se aprueba el álgebra de tipos D01 como base, aunque la implementación sea por fases?
2. ¿Registros nominales D02 o se quiere explorar antes el tipado estructural?
3. ¿Genéricos de usuario en 1.0 o solo builtins genéricos?
4. ¿`match` expresión o sentencia? ¿`if` expresión también?
5. ¿Exhaustividad obligatoria en `match` expresión y error en inalcanzables?
6. ¿Listas inmutables D08 o se necesita mutabilidad para el caso de uso previsto?
7. ¿`for` con `invariant` desde el inicio? ¿`break`/`continue` fuera de 1.0?
8. ¿`Input` con `stdin: Text` o `stdin: List[Text]`? ¿Dos formas de `main`?
9. ¿Módulos con `nexora.toml`? ¿Ciclos prohibidos? ¿Imports comodín?
10. ¿Qué parte de la detección de requisitos debilitados se considera suficiente para 1.0?
11. ¿Se introduce un sistema de warnings para patrones inalcanzables/variables sin usar?
12. ¿Qué nivel de LSP/formatter/REPL se exige para 1.0 y cuál puede ser 1.x?
13. ¿Qué presupuesto y modelos se usan en la evaluación empírica?
14. ¿Quién aprueba la puerta de seguridad del playground?

---

## K. Criterios para NEXORA 1.0

### K.1. Imprescindibles

| Área | Criterio verificable |
|---|---|
| Semántica | Toda construcción documentada tiene especificación, ejemplos y pruebas; no hay construcciones “a medias” |
| Tipos | Builtins + listas + registros + enums + `Option`/`Result` + genéricos acordados; errores estables; `type_repr` |
| Contratos/refinamientos | `requires`/`ensures` estables; refinamientos sobre compuestos; ejemplos; `nex test`; límites documentados |
| Módulos | Archivo=módulo; imports/exports/visibilidad; ciclos rechazados; proyecto analizable |
| Diagnósticos | Códigos estables; posiciones; notas; sugerencias fundamentadas; sin duplicados; docs sincronizadas |
| Herramientas | CLI/API/MCP de análisis con paridad; `requirements`/`impact`/`evidence`; MCP sin ejecución |
| Formatter/tooling | Formatter canónico e idempotente; `nex fmt --check`; LSP puede ser 1.x si se declara |
| Documentación | Spec + guías + ejemplos ejecutables; pruebas de documentación |
| Pruebas | Unitarias, integración, límites, regresión, seguridad, fuzzing básico |
| Seguridad | Modelo de amenazas; playground desactivado por defecto; puerta de aislamiento; sin P0 conocido |
| Compatibilidad | Programas existentes siguen funcionando; guía de migración; esquemas aditivos |
| Rendimiento | Línea base medida; sin afirmaciones no respaldadas |

### K.2. Mejoras opcionales

- LSP completo (el mínimo puede ser diagnóstico por CLI/JSON).
- REPL.
- Formatter con más opciones de estilo.
- Typeclasses.
- Sistema de efectos `uses`.
- `ai fn`/`tool fn`.
- Concurrencia.
- Compilación a JS/WASM.
- Registro de paquetes.
- Optimización del intérprete.
- Mapas, tuplas, rangos, interpolación.

### K.3. Regla de honestidad de 1.0

1.0 no significa “sin errores” ni “verificación formal”. Significa que el núcleo es coherente, está documentado, tiene pruebas, distingue lo comprobado de lo no comprobado y no promete más de lo que puede. **No se fija una fecha.**

---

## L. Secuencia de decisiones

### L.1. Orden recomendado

| Paso | Decisiones | Por qué | Puede ir en paralelo con |
|---|---|---|---|
| 1 | Principios A + D01 (álgebra de tipos) | Bloquea tipos compuestos, patrones, listas y tooling | Revisión de principios, seguridad |
| 2 | D02 (nominal), D03 (genéricos), D04 (refinamientos) | Definen la forma de los datos y las garantías | D05-D07 (diseño de enums/patrones) |
| 3 | D05 (enums), D06 (`match`), D07 (exhaustividad) | Bloquea `Option`/`Result` y parte de la stdlib | D08-D09 (diseño de listas/`for`) |
| 4 | D08 (listas), D09 (`for`), D10 (`break`/`continue`) | Base de iteración y datos | D11-D12 (diseño de entrada/errores) |
| 5 | D11 (entrada), D12 (`Option`/`Result`) | Programas reales y testabilidad | D13-D14 (diseño de módulos) |
| 6 | D13 (módulos), D14 (proyecto/caché) | Stdlib y análisis de proyectos | D15-D16 (diseño de requisitos/IDs) |
| 7 | D15 (requisitos/impacto), D16 (IDs/esquemas) | Propuesta diferencial y herramientas | D17 (seguridad) |
| 8 | D17 (seguridad/playground) | Puerta de exposición pública | Todas |
| 9 | D18 (alcance 1.0) | Cierra el conjunto | Todas |

### L.2. Qué bloquea a qué

- **D01** bloquea D02-D09, D12-D16.
- **D05-D07** bloquean D12 (`Option`/`Result`).
- **D08-D09** bloquean D11 (entrada con listas) y parte de la stdlib.
- **D13-D14** bloquean `project_context`, stdlib y el análisis de proyectos.
- **D15-D16** dependen de D01, D05-D07 y, para proyectos, D13.
- **D17** es independiente, pero es puerta para exponer el playground.
- **D18** depende de todas.

### L.3. Qué puede explorarse en paralelo sin comprometer el diseño

- **Diagnósticos y formatter:** se pueden diseñar con la sintaxis actual y adaptarse después; no deben cerrar decisiones de tipos.
- **Evaluación empírica H.7:** se puede preparar el arnés y las tareas con las capacidades actuales; no necesita esperar a módulos.
- **Seguridad del playground I.3:** se puede planificar y ejecutar en un entorno controlado; no cambia el lenguaje.
- **Documentación y ejemplos:** se pueden preparar borradores; no se publican hasta aprobar.
- **Diseño de stdlib:** se puede esbozar sobre el papel; la implementación depende de módulos y tipos.

### L.4. Condiciones para pasar a implementación

1. El responsable aprueba explícitamente D01 y los principios A.
2. Se resuelven o se aplazan de forma explícita las cuestiones J.1.
3. Se actualizan, en un cambio autorizado separado, `roadmap.md`, `limitations.md`, `language-spec.md` y el índice de decisiones.
4. Se crea un plan de implementación por fases con criterios de aceptación (G.2).
5. Se confirma que no se ha prometido una fecha ni una capacidad no decidida.

**Este ADR no modifica la hoja de ruta oficial.** La actualización del roadmap y del índice de decisiones queda pendiente de aprobación.
