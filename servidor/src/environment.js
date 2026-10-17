// NODE_ENV: el único sitio donde se interpreta. config.js y captcha.js lo leen de aquí, así que
// nunca pueden discrepar sobre si el servidor está en producción.
//
// En producción se activan protecciones (cookies solo por HTTPS, HSTS, RECAPTCHA_HOSTNAMES
// obligatorio, límite estricto sin reCAPTCHA). Por eso un valor mal escrito ("Production", "prod",
// "producción") no puede tratarse en silencio como desarrollo: detiene el servidor antes de que
// escuche conexiones.

export const ENVIRONMENTS = ['development', 'test', 'production'];

/**
 * El entorno, a partir de NODE_ENV:
 *   sin definir      'development', como siempre (el servidor lo dice al arrancar, ver index.js)
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
