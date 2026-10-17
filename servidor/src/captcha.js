// Protección antispam de los formularios de cuenta: Google reCAPTCHA v3, verificado aquí, y medidas
// que no dependen de Google (un campo trampa y un límite estricto por cliente).
//
// reCAPTCHA solo se carga en el navegador si la persona lo acepta en el panel de cookies. Una
// petición solo evita el límite estricto con un token que Google confirma: válido, de esta acción,
// de un dominio admitido, reciente y con puntuación suficiente. Cualquier otra respuesta pasa, como
// mínimo, por ese límite. Así ni un bot gana nada enviando un token falso (es lo mismo que no
// enviarlo) ni un error de configuración deja a todo el mundo sin poder registrarse: solo le aplica
// el límite estricto, y queda en el registro del servidor.
//
// Solo se rechaza (400) lo que una página auténtica no envía nunca o puede arreglar sola: un token de
// otra acción (sacado de otro formulario) y un token caducado o ya usado, que la página sustituye por
// uno nuevo y reenvía una vez. Ese reenvío gasta un intento más del límite general de la ruta, y es a
// propósito: si los rechazos no contaran, cualquiera podría reenviar sin fin un token ya usado, y el
// servidor preguntaría a Google cada vez.

import { readFileSync } from 'node:fs';
import { isProduction } from './environment.js';
import { clientRateLimit } from './rate-limits.js';

const VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify';
// Google invalida el token a los dos minutos; esta comprobación no depende de ello.
const TOKEN_MAX_AGE_MS = 2 * 60 * 1000;
// Formato esperado de un token. Uno distinto no se envía a Google, pero tampoco se rechaza: si Google
// cambiara el formato, las personas que aceptaron reCAPTCHA seguirían pudiendo entrar, con el límite.
const TOKEN = /^[\w.-]{20,4096}$/;
// El mismo motivo se escribe en el registro como mucho una vez en este intervalo, con un recuento.
const LOG_INTERVAL_MS = 10 * 60 * 1000;

// Un nombre de dominio, sin esquema, puerto ni ruta (nexora.dev, www.nexora.dev, localhost).
const HOSTNAME = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/;

/**
 * Configuración desde el entorno. Sin RECAPTCHA_SECRET_KEY, reCAPTCHA queda desactivado.
 * En producción (NODE_ENV=production):
 *   - con clave secreta, RECAPTCHA_HOSTNAMES es obligatorio: sin él se aceptarían tokens generados en
 *     cualquier dominio con la misma clave del sitio. Si falta, el servidor no arranca;
 *   - sin clave secreta, todos los registros e inicios de sesión pasan por el límite estricto (ver
 *     POLICY.disabled_in_production): una configuración ausente nunca deja el formulario sin freno.
 */
export function loadCaptchaConfig(env = process.env) {
  const production = isProduction(env.NODE_ENV);
  const secret = env.RECAPTCHA_SECRET_KEY?.trim() || null;
  const rawScore = env.RECAPTCHA_MIN_SCORE?.trim();
  const minScore = rawScore ? Number(rawScore) : 0.5;
  if (!Number.isFinite(minScore) || minScore < 0 || minScore > 1) {
    throw new Error('RECAPTCHA_MIN_SCORE debe ser un número entre 0 y 1 (revisa servidor/.env)');
  }
  const hostnames = (env.RECAPTCHA_HOSTNAMES ?? '')
    .split(',')
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
  const invalid = hostnames.filter((name) => !HOSTNAME.test(name));
  if (invalid.length > 0) {
    throw new Error(`RECAPTCHA_HOSTNAMES solo admite nombres de dominio separados por comas, sin https:// ni puerto; no vale: ${invalid.join(', ')} (revisa servidor/.env)`);
  }
  if (production && secret && hostnames.length === 0) {
    throw new Error('En producción, con RECAPTCHA_SECRET_KEY hace falta RECAPTCHA_HOSTNAMES con los dominios del sitio (revisa servidor/.env)');
  }
  return { secret, minScore, hostnames, production };
}

// La clave del sitio, tal como la comprueba web/js/consent.js; con otro formato, el navegador la ignora.
const SITE_KEY = /^6L[\w-]{38}$/;

/**
 * La clave pública del sitio escrita en web/js/consent-config.js (`recaptchaSiteKey`), leída como texto:
 * el archivo es para el navegador y no se ejecuta aquí. Devuelve la clave, '' si es null, o undefined
 * si no se encuentra la línea (el archivo cambió de forma).
 */
export function readSiteKey(source) {
  const match = source.match(/^\s*recaptchaSiteKey:\s*(?:null|'([^']*)'|"([^"]*)")\s*,?\s*$/m);
  if (!match) return undefined;
  return match[1] ?? match[2] ?? '';
}

/**
 * La clave del sitio leída del archivo `file` (web/js/consent-config.js): la de readSiteKey, o null si
 * el archivo no existe (un sitio sin gestor de consentimiento, que nunca carga reCAPTCHA). Cualquier
 * otro error de lectura devuelve undefined. Nunca lanza: el servidor arranca aunque falte la web.
 */
export function readSiteKeyFile(file, { read = readFileSync } = {}) {
  try {
    return readSiteKey(read(file, 'utf8'));
  } catch (error) {
    return error.code === 'ENOENT' ? null : undefined;
  }
}

/**
 * Avisos para el registro al arrancar sobre las dos claves, que se configuran en sitios distintos: la
 * secreta en servidor/.env y la del sitio en web/js/consent-config.js. No cambian nada.
 */
export function captchaKeyWarnings({ secret, siteKey }) {
  const warnings = [];
  if (siteKey === null) {
    if (secret) {
      warnings.push('RECAPTCHA_SECRET_KEY is set but web/js/consent-config.js does not exist: browsers never load reCAPTCHA, so every sign-up and log-in falls under the strict limit');
    }
    return warnings;
  }
  if (siteKey === undefined) {
    warnings.push('could not find recaptchaSiteKey in web/js/consent-config.js; the reCAPTCHA keys were not cross-checked');
    return warnings;
  }
  if (siteKey && !SITE_KEY.test(siteKey)) {
    warnings.push('recaptchaSiteKey in web/js/consent-config.js is not a valid site key: browsers ignore it and never load reCAPTCHA');
  }
  if (secret && !siteKey) {
    warnings.push('RECAPTCHA_SECRET_KEY is set but web/js/consent-config.js has no recaptchaSiteKey: browsers never load reCAPTCHA, so every sign-up and log-in falls under the strict limit');
  }
  if (!secret && siteKey) {
    warnings.push('web/js/consent-config.js has a recaptchaSiteKey but RECAPTCHA_SECRET_KEY is not set: the security policy of the pages blocks reCAPTCHA, and visitors who turn it on are told it could not be loaded');
  }
  return warnings;
}

/**
 * Verifica un token de reCAPTCHA v3 con Google. Devuelve { outcome, reason? , score? } con uno de:
 *   disabled        reCAPTCHA no está configurado en el servidor
 *   missing         la petición no trae token
 *   malformed       el token no tiene el formato esperado (no se pregunta a Google)
 *   rejected        Google no reconoce el token: falso, o la clave del sitio no es pareja de la secreta
 *   wrong_action    token válido de otra acción (por ejemplo, de login usado en el registro)
 *   wrong_hostname  token válido de un dominio que no está en RECAPTCHA_HOSTNAMES
 *   expired         token caducado o ya usado
 *   low_score       token válido con puntuación por debajo de RECAPTCHA_MIN_SCORE
 *   misconfigured   Google rechaza la clave secreta (fallo de configuración nuestro)
 *   unavailable     Google no respondió o respondió algo que no se entiende
 *   verified        token válido, acción y dominio esperados, reciente, puntuación suficiente
 */
export async function verifyCaptcha(token, expectedAction, config, { fetch = globalThis.fetch, now = Date.now } = {}) {
  if (!config.secret) return { outcome: 'disabled' };
  if (token === undefined || token === null || token === '') return { outcome: 'missing' };
  if (typeof token !== 'string' || !TOKEN.test(token)) return { outcome: 'malformed' };

  let data;
  try {
    // No se envía la IP (remoteip es opcional): Google ya la ve desde el navegador.
    const response = await fetch(VERIFY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ secret: config.secret, response: token }),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return { outcome: 'unavailable', reason: `HTTP ${response.status}` };
    data = await response.json();
  } catch (error) {
    return { outcome: 'unavailable', reason: error.name };
  }
  if (!data || typeof data !== 'object') return { outcome: 'unavailable', reason: 'unexpected response' };

  const codes = Array.isArray(data['error-codes']) ? data['error-codes'].map(String) : [];
  if (data.success !== true) {
    if (codes.some((code) => code.includes('secret'))) return { outcome: 'misconfigured', reason: codes.join(',') };
    if (codes.includes('timeout-or-duplicate')) return { outcome: 'expired', reason: 'timeout-or-duplicate' };
    return { outcome: 'rejected', reason: codes.join(',') || 'not successful' };
  }
  if (data.action !== expectedAction) return { outcome: 'wrong_action', reason: String(data.action) };
  const hostname = String(data.hostname).toLowerCase();
  if (config.hostnames.length > 0 && !config.hostnames.includes(hostname)) {
    return { outcome: 'wrong_hostname', reason: hostname };
  }
  const issued = Date.parse(data.challenge_ts);
  if (!Number.isFinite(issued) || now() - issued > TOKEN_MAX_AGE_MS) return { outcome: 'expired', reason: 'challenge_ts' };
  if (typeof data.score !== 'number' || data.score < config.minScore) return { outcome: 'low_score', score: data.score };
  return { outcome: 'verified', score: data.score };
}

/**
 * Qué hace el servidor con cada resultado:
 *   pass    sigue adelante (solo con los límites generales de la ruta)
 *   strict  sigue adelante si el cliente no ha agotado el límite estricto
 *   refuse  400 con un código que la página entiende
 * `log` indica si el resultado se anota en el registro: los que apuntan a un problema de
 * configuración o de Google, no los que son decisión del visitante (no aceptar reCAPTCHA).
 */
export const POLICY = Object.freeze({
  verified: { action: 'pass' },
  // Sin clave secreta: en desarrollo, sin freno extra; en producción, el límite estricto para todos.
  disabled: { action: 'pass' },
  disabled_in_production: { action: 'strict', log: true },
  missing: { action: 'strict' },
  low_score: { action: 'strict' },
  malformed: { action: 'strict', log: true },
  rejected: { action: 'strict', log: true },
  wrong_hostname: { action: 'strict', log: true },
  misconfigured: { action: 'strict', log: true },
  unavailable: { action: 'strict', log: true },
  wrong_action: { action: 'refuse', status: 400, code: 'captcha_invalid', error: 'The anti-spam check failed. Reload the page and try again.' },
  expired: { action: 'refuse', status: 400, code: 'captcha_expired', error: 'The anti-spam check expired. Try again.' },
});

// Qué puede significar cada resultado anotado, para quien lea el registro.
const LOG_HINTS = {
  disabled_in_production: 'RECAPTCHA_SECRET_KEY is not set in production',
  malformed: 'token with an unexpected format',
  rejected: 'Google did not recognise the token: a forged token, or a site key (web/js/consent-config.js) that does not belong to RECAPTCHA_SECRET_KEY',
  wrong_hostname: 'token from a host that is not in RECAPTCHA_HOSTNAMES',
  misconfigured: 'Google rejected RECAPTCHA_SECRET_KEY',
  unavailable: 'Google could not be reached',
};

/** Registro con freno: cada clave se escribe como mucho una vez por intervalo, con las omitidas. */
export function throttledLog(log, { interval = LOG_INTERVAL_MS, now = Date.now } = {}) {
  const last = new Map();
  return (key, line) => {
    const entry = last.get(key);
    const time = now();
    if (entry && time - entry.time < interval) {
      entry.skipped += 1;
      return;
    }
    const skipped = entry?.skipped ? ` (${entry.skipped} more since the last report)` : '';
    last.set(key, { time, skipped: 0 });
    log(`${line}${skipped}`);
  };
}

/**
 * Límite para las peticiones sin verificación de reCAPTCHA, por hora: `limit` por cliente (una IPv4
 * o un bloque IPv6 /56) y `limit × 4` por red IPv6 /48 (rate-limits.js).
 */
export function strictLimiter(limit) {
  return clientRateLimit({
    windowMs: 60 * 60 * 1000,
    limit,
    message: {
      error: 'Too many attempts without the anti-spam check. Try again later, or turn on Google reCAPTCHA in Cookie settings.',
      code: 'captcha_required',
    },
  });
}

/**
 * Middleware antispam de una acción ('signup', 'login'). Lee del cuerpo `captchaToken` y el campo
 * trampa `website`, que una persona nunca rellena porque no lo ve.
 */
export function antispam(action, config, {
  verify = verifyCaptcha,
  strict = strictLimiter(action === 'signup' ? 5 : 15),
  log = console.error,
} = {}) {
  const report = throttledLog(log);
  return async (req, res, next) => {
    try {
      if (typeof req.body?.website === 'string' && req.body.website !== '') {
        return res.status(400).json({ error: 'The request could not be processed.' });
      }
      const result = await verify(req.body?.captchaToken, action, config);
      if (result.outcome === 'disabled' && config.production) result.outcome = 'disabled_in_production';
      // Un resultado desconocido nunca deja pasar: se trata como un token sin verificar.
      const policy = POLICY[result.outcome] ?? { action: 'strict', log: true };
      if (policy.log) {
        const hint = LOG_HINTS[result.outcome] ?? 'unexpected verification result';
        report(`${action}:${result.outcome}`, `captcha: ${action}: ${result.outcome}${result.reason ? ` (${result.reason})` : ''}: ${hint}; the request falls under the strict limit`);
      }
      if (policy.action === 'pass') return next();
      if (policy.action === 'refuse') return res.status(policy.status).json({ error: policy.error, code: policy.code });
      return strict(req, res, next);
    } catch (error) {
      return next(error);
    }
  };
}
