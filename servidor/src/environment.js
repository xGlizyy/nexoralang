// NODE_ENV: el único sitio donde se interpreta. config.js lo lee de aquí, así que el servidor no
// puede tener dos criterios sobre si está en producción.
//
// En producción se activan protecciones (cookies solo por HTTPS). Por eso un valor mal escrito
// ("Production", "prod", "producción") no puede tratarse en silencio como desarrollo: detiene el
// servidor antes de que escuche conexiones.

export const ENVIRONMENTS = ['development', 'test', 'production'];

/**
 * El entorno, a partir de NODE_ENV:
 *   sin definir      'development', como siempre
 *   development, test, production   ese valor, escrito exactamente así
 *   cualquier otro (también vacío o con otras mayúsculas)   error de configuración
 */
export function parseNodeEnv(value) {
  if (value === undefined) return 'development';
  if (ENVIRONMENTS.includes(value)) return value;
  throw new Error(`NODE_ENV debe ser development, test o production (en minúsculas), no ${JSON.stringify(value)} (revisa servidor/.env)`);
}

/** ¿Producción? Con el mismo criterio en todo el servidor. */
export const isProduction = (value) => parseNodeEnv(value) === 'production';
