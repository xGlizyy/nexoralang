// En qué dirección escucha el servidor (LISTEN_HOST) y avisos sobre su combinación con TRUST_PROXY.
//
// Sin LISTEN_HOST, el servidor escucha en todas las interfaces, como siempre: así funcionan el desarrollo
// local y las instalaciones existentes. Detrás de nginx en el mismo equipo conviene LISTEN_HOST=127.0.0.1:
// entonces solo se puede llegar al servidor desde el propio equipo, sea cual sea el cortafuegos.

import { isIP, isIPv4 } from 'node:net';

/**
 * LISTEN_HOST: vacío (todas las interfaces) o una dirección IP escrita tal cual. No admite nombres, ni
 * siquiera "localhost": según el sistema, Node lo resuelve a ::1 o a 127.0.0.1 y escucha solo en esa
 * dirección (en Windows 11 con Node 24, ::1), y un nginx que apunte a la otra no llegaría al servidor.
 */
export function parseListenHost(value) {
  if (value === undefined || value.trim() === '') return null;
  const host = value.trim();
  if (isIP(host)) return host;
  throw new Error(`LISTEN_HOST debe ser una dirección IP (por ejemplo 127.0.0.1; no localhost) o estar vacía, no "${value}" (revisa servidor/.env)`);
}

// Las direcciones del propio equipo: 127.0.0.0/8 y ::1.
const isLoopback = (host) => host === '::1' || (isIPv4(host) && host.startsWith('127.'));

/** Avisos para el registro al arrancar; no cambian nada. */
export function listenWarnings({ host, trustProxy }) {
  const warnings = [];
  if (trustProxy === 'loopback' && !isLoopback(host ?? '')) {
    warnings.push(
      `TRUST_PROXY=loopback but the server listens on ${host ?? 'every interface'}, not only on this machine: `
      + 'anything that can reach this port bypasses nginx. Set LISTEN_HOST=127.0.0.1 if nginx runs on this machine.',
    );
  }
  if (typeof trustProxy === 'number' && trustProxy > 0 && host === null) {
    warnings.push(
      `TRUST_PROXY=${trustProxy} trusts X-Forwarded-For from any connection, and the server listens on every interface: `
      + 'if this port is reachable from outside, anyone can choose the address the limits see. '
      + 'Prefer TRUST_PROXY=loopback and LISTEN_HOST=127.0.0.1 with nginx on this machine.',
    );
  }
  return warnings;
}
