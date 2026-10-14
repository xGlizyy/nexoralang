# 0006 — Característica diferencial: los requisitos son parte verificable del programa

- **Estado:** aceptada
- **Versión:** ninguna todavía. Esta decisión fija una dirección; no cambia el lenguaje por sí sola.

## Contexto

El borrador de diseño reúne muchas ideas (contratos, efectos, `ai fn`, diagnósticos en JSON,
sintaxis regular) y la hoja de ruta formula la hipótesis central en términos generales: si estas
decisiones "facilitan el trabajo de las herramientas de IA". Así planteada, no se puede comprobar
ni sirve para elegir qué construir primero. Hace falta un problema concreto.

### El problema elegido

Cuando una función se escribe o se modifica con ayuda de una IA, **los requisitos viven en lenguaje
natural**: en la instrucción que recibe el modelo, en una conversación, en un ticket o en un
comentario. De ahí salen cuatro fallos concretos:

| Fallo | Ejemplo |
|-------|---------|
| **Nadie los comprueba** | Se pide "el descuento nunca puede subir el precio" y nada avisa si el código generado lo incumple |
| **Se pierden entre ediciones** | La siguiente persona o el siguiente modelo que toca la función no ve la conversación original y puede romper el requisito sin saberlo |
| **Son ambiguos** | "El porcentaje es válido" admite varias lecturas; una condición escrita solo admite una |
| **Encarecen la revisión** | Quien revisa tiene que reconstruir la intención antes de poder juzgar si el código la cumple |

Lo que una instrucción en lenguaje natural no puede dar es una respuesta mecánica a la pregunta:
**"¿este código sigue cumpliendo lo que se pidió?"**

## Decisión

La característica que distingue a NEXORA es esta:

> **Los requisitos, las restricciones y las condiciones de validación de una función se escriben
> en el propio programa, junto a la función, y una herramienta determinista comprueba si se
> cumplen.** Una instrucción en lenguaje natural puede explicarlos, pero no es el único sitio
> donde existen.

Todo el trabajo sobre el lenguaje se ordena según esa característica. En concreto:

1. **Un requisito que se puede comprobar se escribe como condición en el código**, no solo en la
   instrucción ni en un comentario. Hay cuatro clases:

   | Clase | Pregunta que responde | Mecanismo |
   |-------|-----------------------|-----------|
   | Precondición | ¿Qué necesita la función para funcionar? | `requires` |
   | Postcondición | ¿Qué promete la función al terminar? | `ensures` |
   | Restricción sobre datos | ¿Qué valores son válidos para un tipo? | Tipos refinados (`where`), planificados |
   | Caso concreto | ¿Qué debe dar con estas entradas? | `example`, planificado |

2. **La explicación en lenguaje natural acompaña a la condición; no la sustituye.** Un requisito
   puede llevar una frase que diga por qué existe, y esa frase aparece en el diagnóstico cuando se
   incumple. Una frase sin condición no cuenta como requisito.
3. **La comprobación es determinista.** Ningún modelo de IA decide si un requisito se cumple: el
   mismo programa con las mismas entradas da siempre el mismo resultado.
4. **Cada incumplimiento dice qué requisito falló, quién lo incumplió y con qué valores**: la
   llamada (precondición) o la función (postcondición). En texto para personas y en JSON para
   herramientas.
5. **Los requisitos son visibles antes de editar.** `nex context` y `nex inspect` los entregan como
   datos, de modo que un agente los recibe como restricciones del trabajo y no tiene que deducirlos.
6. **Quitar o debilitar un requisito es un cambio visible.** Si una edición borra o relaja una
   condición para que el programa "pase", la herramienta debe señalarlo, igual que señala un error.
7. **NEXORA nunca dice que un requisito "se cumple" si solo lo ha comprobado en algunas
   ejecuciones.** Comprobar en ejecución detecta incumplimientos; no demuestra que no existan.

## Un ejemplo con lo que existe hoy

La instrucción en lenguaje natural sería: *"Aplica un descuento a un precio en céntimos. El
porcentaje va de 0 a 100, y el resultado nunca puede ser negativo ni mayor que el precio."* En
NEXORA esos requisitos se escriben en la función:

<!-- nex:run -->
```nex
fn apply_discount(price_cents: Int, percent: Int) -> Int {
    requires price_cents >= 0
    requires percent >= 0 and percent <= 100
    ensures result >= 0 and result <= price_cents
    return price_cents * (100 - percent) / 100
}

fn main() -> Void {
    print(apply_discount(10000, 20))
    print(apply_discount(999, 0))
}
```

```text
8000
999
```

Si una edición posterior, hecha por una persona o por un modelo, cambia el signo y convierte el
descuento en un recargo, el requisito sigue ahí aunque la instrucción original ya no esté en
ninguna parte. El programa se detiene y dice qué promesa se rompió y con qué valores:

<!-- nex:fails exit=5 -->
```nex
fn apply_discount(price_cents: Int, percent: Int) -> Int {
    requires price_cents >= 0
    requires percent >= 0 and percent <= 100
    ensures result >= 0 and result <= price_cents
    return price_cents * (100 + percent) / 100
}

fn main() -> Void {
    print(apply_discount(10000, 20))
    print(apply_discount(999, 0))
}
```

```text
contract error[E4002]: Postcondition violated
 --> program.nex:4:5
  |
4 |     ensures result >= 0 and result <= price_cents
  |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 'apply_discount' breaks its own 'ensures' condition
  = note: 'apply_discount' finished, but its condition is false: ensures result >= 0 and result <= price_cents
  = note: It returned: result = 12000
  = note: It was called with: price_cents = 10000, percent = 20
  = note: In 'apply_discount', called at line 9, column 11.

error: program.nex: the program stopped because a contract was broken
```

Hacia donde apunta esta decisión, con una sintaxis **solo ilustrativa y no decidida**: cada
condición con su explicación, un tipo que lleva su propia restricción y un caso concreto que se
comprueba sin escribir `main`.

```text
type Percent = Int where value >= 0 and value <= 100

fn apply_discount(price_cents: Int, percent: Percent) -> Int {
    requires price_cents >= 0           "Un precio no puede ser negativo"
    ensures result <= price_cents       "Un descuento nunca sube el precio"
    example apply_discount(10000, 20) == 8000
    return price_cents * (100 - percent) / 100
}
```

## Qué existe y qué falta

| Pieza | Estado |
|-------|--------|
| `requires` y `ensures`, comprobados en cada llamada ([0004](0004-contratos-en-ejecucion.md)) | Implementado; **experimental** |
| Atribución del incumplimiento (`E4001` a la llamada, `E4002` a la función) con los valores | Implementado |
| Contratos visibles para herramientas en `nex context` y `nex inspect` | Implementado |
| Diagnósticos de contrato en JSON (`nexora.diagnostics/1`) | Implementado |
| Explicación en lenguaje natural unida a cada condición | No existe |
| Casos concretos en la función (`example`) y un comando que los ejecute | No existe; planificado |
| Tipos refinados (`where`) | No existe; necesita antes registros o tipos definidos por el usuario |
| Aviso cuando una edición elimina o debilita un requisito | No existe; no está decidido cómo detectar "debilitar" |
| Evaluación de si esto ayuda de verdad a una IA | **No se ha hecho** |

> **Actualización (0.3.0).** La [decisión 0007](0007-contratos-estables-y-tipos-refinados.md)
> implementa tres piezas de esta tabla: los contratos dejan de ser experimentales, cada condición
> puede llevar su explicación y existen los tipos refinados sobre los tipos integrados. El estado
> al día está en la [hoja de ruta](../roadmap.md#línea-principal-requisitos-verificables).

## Cómo se sabrá si funciona

La característica es una hipótesis hasta que se mida. El experimento mínimo:

- Un conjunto de tareas en las que un agente modifica funciones que tienen requisitos.
- Dos variantes de cada tarea: los requisitos **solo en la instrucción**, o **también en el
  código** como condiciones.
- Medidas:
  - Ediciones que incumplen un requisito y se detectan antes de entregarlas.
  - Ediciones que incumplen un requisito y no se detectan.
  - Avisos falsos: requisitos señalados como incumplidos sin estarlo.
  - Requisitos eliminados o relajados por el agente para que el programa pase.

Las [tareas de referencia](../ai-tooling.md#tareas-de-referencia) son el punto de partida. Hasta
tener resultados, ninguna página del proyecto debe afirmar que NEXORA mejora el trabajo con IA.

## Lo que no pretende

- **No es verificación formal.** No demuestra que un requisito se cumpla para todas las entradas;
  detecta incumplimientos en las llamadas que se ejecutan.
- **No sustituye a las pruebas.** Un requisito dice qué debe ser cierto; una prueba elige con qué
  entradas comprobarlo. Hacen falta los dos.
- **No hace que la IA escriba código correcto.** Hace que el código incorrecto se note, y que se
  note pronto y con una explicación.
- **No cubre todos los requisitos.** El rendimiento, la experiencia de uso o el estilo no se
  expresan como condiciones sobre valores.
- **No es una idea nueva por separado.** Los contratos existen en otros lenguajes desde hace
  décadas. Lo que NEXORA propone es hacer de ellos el centro del trabajo con IA: obligatorios en
  la unidad que se edita, entregados como datos a las herramientas, con la culpa atribuida y sin
  que un modelo decida nada.

## Alternativas descartadas como característica diferencial

| Alternativa | Por qué no es la característica principal |
|-------------|-------------------------------------------|
| **Funciones resueltas por un modelo (`ai fn`, `tool fn`)** | No son deterministas, ya existen como bibliotecas en otros lenguajes y no resuelven el problema de comprobar el código. Siguen en investigación |
| **Efectos declarados (`uses`)** | Útiles para saber qué toca una función, pero secundarios: no dicen si el resultado es correcto |
| **Diagnósticos y salidas en JSON** | Ya existen y son necesarios, pero son el medio por el que se comunican los requisitos, no el fin |
| **Una sintaxis "más fácil para la IA"** | No se puede afirmar sin un experimento, y no aporta nada que una herramienta pueda comprobar |

## Consecuencias

El orden de trabajo de la hoja de ruta que tiene que ver con esta característica pasa a ser el
siguiente (en la [hoja de ruta](../roadmap.md#línea-principal-requisitos-verificables), con el
estado de cada paso):

1. Estabilizar los contratos y sacarlos de experimental (posición en el código y nombre `result`).
2. Unir una explicación en lenguaje natural a cada condición y mostrarla en el diagnóstico.
3. Casos concretos en la función (`example`) y un comando que los ejecute sin `main`.
4. Detectar cuándo una edición elimina o debilita un requisito.
5. Tipos refinados, cuando existan los tipos definidos por el usuario.
6. El experimento de evaluación, antes de presentar la característica como una ventaja demostrada.

La web y la documentación general deben presentar NEXORA a partir de este problema, sin afirmar
resultados que todavía no se han medido.
