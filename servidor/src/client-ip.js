// Quién es «el mismo cliente» para los límites de peticiones, y cuántos proxies hay delante.
//
// express-rate-limit 7 cuenta cada dirección por separado. Con IPv4 es lo correcto, pero un
// proveedor de IPv6 suele dar a cada cliente un bloque entero (/64, /56 o mayor), y cambiar de
// dirección dentro de él es trivial: contada una a una, cada petición estrenaría su propio cupo.
// Por eso las direcciones IPv6 se agrupan por su prefijo /56, el mismo valor por defecto que usa
// express-rate-limit desde la versión 8.

import { isIPv4, isIPv6 } from 'node:net';

export const IPV6_PREFIX = 56;

/** Los 128 bits de una dirección IPv6 válida, como BigInt. Admite "::" y un IPv4 final. */
function ipv6Bits(address) {
  let text = address;
  const tail = text.match(/(\d+\.\d+\.\d+\.\d+)$/);
  if (tail) {
    const [a, b, c, d] = tail[1].split('.').map(Number);
    text = `${text.slice(0, -tail[1].length)}${((a << 8) | b).toString(16)}:${((c << 8) | d).toString(16)}`;
  }
  const [head, rest] = text.split('::');
  const left = head ? head.split(':') : [];
  const right = rest === undefined ? [] : (rest ? rest.split(':') : []);
  const groups = rest === undefined ? left : [...left, ...Array(8 - left.length - right.length).fill('0'), ...right];
  return groups.reduce((bits, group) => (bits << 16n) | BigInt(`0x${group}`), 0n);
}

// Quien controla un bloque /48 (habitual en algunos proveedores) tiene 256 bloques /56. El límite
// por cliente (rate-limits.js) añade por eso un segundo cupo, más amplio, por bloque /48.
export const IPV6_NETWORK_PREFIX = 48;

/**
 * La clave de un cliente para los límites: la dirección IPv4 tal cual; de una IPv6, su prefijo /56
 * con los ocho grupos escritos (por ejemplo "2001:db8:aa:bb00:0:0:0:0/56"). Un IPv4 escrito como
 * IPv6 (::ffff:1.2.3.4) cuenta como el IPv4. Todo lo que no es una dirección (solo posible con un
 * TRUST_PROXY mal puesto, que deja pasar X-Forwarded-For inventadas) comparte una única clave:
 * inventarse textos distintos no da cupos nuevos.
 */
export function clientKey(ip, prefix = IPV6_PREFIX) {
  if (typeof ip !== 'string' || ip === '') return 'invalid-address';
  const address = ip.replace(/%[\w.-]*$/, ''); // sin el identificador de zona (fe80::1%eth0)
  if (isIPv4(address)) return address;
  if (!isIPv6(address)) return 'invalid-address';
  const bits = ipv6Bits(address);
  if (bits >> 32n === 0xffffn) {
    return [24n, 16n, 8n, 0n].map((shift) => String((bits >> shift) & 0xffn)).join('.');
  }
  const network = (bits >> BigInt(128 - prefix)) << BigInt(128 - prefix);
  const groups = [];
  for (let shift = 112n; shift >= 0n; shift -= 16n) groups.push(((network >> shift) & 0xffffn).toString(16));
  return `${groups.join(':')}/${prefix}`;
}

/** keyGenerator para express-rate-limit: req.ip ya es la dirección real si TRUST_PROXY es correcto. */
export const rateLimitKey = (req) => clientKey(req.ip);

/** keyGenerator del cupo amplio: el bloque /48 de una IPv6; un IPv4, como en rateLimitKey. */
export const networkRateLimitKey = (req) => clientKey(req.ip, IPV6_NETWORK_PREFIX);

/**
 * TRUST_PROXY: qué proxies propios hay delante del servidor.
 *   0          sin proxy (valor por defecto)
 *   loopback   un proxy en el mismo equipo, como nginx en el despliegue de la guía. Solo se cree
 *              X-Forwarded-For si la conexión viene de 127.0.0.1/8 o ::1: una conexión directa desde
 *              otro equipo no puede inventarse su dirección. Pero CUALQUIER proceso del propio equipo
 *              que pueda conectar con el servidor sí puede: loopback confía en todos ellos, no solo en
 *              nginx. No protege por sí solo frente a un proceso local malicioso (ver LISTEN_HOST, listen.js)
 *   1 a 10     número de proxies, estén donde estén. Con un valor mayor que el real, cualquiera puede
 *              inventarse su dirección con X-Forwarded-For y saltarse los límites. Sin ceros a la
 *              izquierda
 * Con un valor menor que el real, todas las peticiones parecen venir del proxy y comparten un único
 * cupo. Cualquier otro valor detiene el servidor en vez de interpretarse.
 */
export function parseTrustProxy(value) {
  if (value === undefined || value.trim() === '') return 0;
  const text = value.trim();
  if (text === 'loopback') return 'loopback';
  // Sin ceros a la izquierda ("01"): un valor así es ambiguo y probablemente una errata.
  if (!/^(0|[1-9]\d?)$/.test(text) || Number(text) > 10) {
    throw new Error(`TRUST_PROXY debe ser 0 (sin proxy), loopback (nginx en el mismo equipo) o el número de proxies delante del servidor, no "${value}" (revisa servidor/.env)`);
  }
  return Number(text);
}
