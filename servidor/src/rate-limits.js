// Límites de peticiones por cliente, con la misma estrategia en cada límite que la use.
//
// Cada límite cuenta dos cosas a la vez:
//   - por cliente: una dirección IPv4, o un bloque IPv6 /56 (client-ip.js);
//   - por red IPv6 /48, con un cupo NETWORK_FACTOR veces mayor.
// Quien controla un /48 tiene 256 bloques /56; sin la segunda cuenta, repartirse entre ellos
// multiplicaría su cupo por 256. Con ella, como mucho por NETWORK_FACTOR.
//
// El equilibrio: una red /48 compartida (una universidad, una empresa) reparte entre todas sus
// personas ese cupo de red, igual que ya ocurre con una sola IPv4 detrás de un NAT, que tiene el
// cupo de un único cliente. Por eso el factor es pequeño pero mayor que 1. Con IPv4 la cuenta de red
// es la misma dirección con un tope mayor, así que nunca actúa antes que la del cliente.
//
// Cabeceras. Una petición puede pasar por varias cuentas: las dos de cada límite y, si una ruta
// encadena varios límites, las de cada uno. Las cabeceras
// RateLimit-* (borrador 6 del IETF, las que ya enviaba express-rate-limit) describen siempre la cuenta
// que antes se agota: la de menos peticiones restantes y, a igualdad, la que tarda más en renovarse.
// Si cada cuenta escribiera las suyas, ganaría la última, que puede ser la más holgada (la de red
// tiene un cupo cuatro veces mayor). Una petición rechazada lleva además Retry-After, con lo que
// falta para que se renueve la cuenta que la rechazó.
//
// Los contadores viven en la memoria del proceso (el almacén por defecto de express-rate-limit): se
// pierden al reiniciar y no se comparten entre varias instancias del servidor.

import rateLimit from 'express-rate-limit';
import { networkRateLimitKey, rateLimitKey } from './client-ip.js';

export const NETWORK_FACTOR = 4;

// Dónde guarda cada cuenta su estado en la petición, y qué cabeceras se han enviado ya.
const CLIENT_INFO = Symbol('client rate limit');
const NETWORK_INFO = Symbol('network rate limit');
const SHOWN = Symbol('rate limit headers');

/** Segundos hasta que una cuenta se renueva; sin hora de renovación, la ventana entera. */
function secondsToReset(info, windowMs, now) {
  const ms = info.resetTime instanceof Date ? info.resetTime.getTime() - now : windowMs;
  return Math.max(0, Math.ceil(ms / 1000));
}

/**
 * Escribe las cabeceras de `info` si esta cuenta es la que antes se agota de las vistas hasta ahora
 * en la petición. Devuelve los segundos que faltan para que se renueve.
 */
export function showRateLimit(req, res, info, windowMs, now = Date.now()) {
  const reset = secondsToReset(info, windowMs, now);
  const shown = req[SHOWN];
  if (shown && (info.remaining > shown.remaining || (info.remaining === shown.remaining && reset <= shown.reset))) {
    return reset;
  }
  req[SHOWN] = { remaining: info.remaining, reset };
  res.set('RateLimit-Policy', `${info.limit};w=${Math.ceil(windowMs / 1000)}`);
  res.set('RateLimit-Limit', String(info.limit));
  res.set('RateLimit-Remaining', String(info.remaining));
  res.set('RateLimit-Reset', String(reset));
  return reset;
}

// La respuesta por defecto de express-rate-limit (estado y mensaje), para los límites sin `handler`.
const defaultHandler = (req, res, next, options) => res.status(options.statusCode).send(options.message);

/**
 * Un límite de `limit` peticiones por cliente y `limit × NETWORK_FACTOR` por red /48 en `windowMs`.
 * Admite las demás opciones de express-rate-limit (message, handler…), que se aplican a las dos cuentas.
 * Las cabeceras las escribe showRateLimit, no express-rate-limit.
 */
export function clientRateLimit({ limit, windowMs, handler = defaultHandler, networkFactor = NETWORK_FACTOR, ...options }) {
  const account = (property, max, keyGenerator) => rateLimit({
    ...options,
    windowMs,
    limit: max,
    keyGenerator,
    standardHeaders: false,
    legacyHeaders: false,
    requestPropertyName: property,
    handler: (req, res, next, settings) => {
      res.set('Retry-After', String(showRateLimit(req, res, req[property], windowMs)));
      return handler(req, res, next, settings);
    },
  });
  const perClient = account(CLIENT_INFO, limit, rateLimitKey);
  const perNetwork = account(NETWORK_INFO, limit * networkFactor, networkRateLimitKey);
  // Primero el cliente: una petición que ya rechaza su propio límite no gasta el cupo de la red. Si no,
  // un solo cliente insistente agotaría el /48 entero y bloquearía a sus vecinos; así necesita al
  // menos NETWORK_FACTOR clientes distintos para llenarlo.
  return (req, res, next) => perClient(req, res, (error) => {
    if (error) return next(error);
    showRateLimit(req, res, req[CLIENT_INFO], windowMs);
    return perNetwork(req, res, (networkError) => {
      if (networkError) return next(networkError);
      showRateLimit(req, res, req[NETWORK_INFO], windowMs);
      return next();
    });
  });
}
