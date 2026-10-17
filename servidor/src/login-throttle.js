// Freno de los intentos de inicio de sesión por cuenta, además de los límites por cliente.
//
// Los límites por cliente (rate-limits.js) no frenan un ataque repartido entre muchas direcciones
// contra una misma cuenta. Este freno cuenta los fallos de cada cuenta, con esperas que crecen:
//
//   - Por cuenta y cliente: tras PAIR_FREE fallos, cada intento siguiente desde ese cliente espera
//     1 s, 2 s, 4 s… hasta PAIR_MAX_DELAY_MS. Afecta solo al cliente que falla.
//   - Por cuenta, desde cualquier cliente: tras ACCOUNT_FREE fallos, cada intento espera 1 s, 2 s…
//     hasta ACCOUNT_MAX_DELAY_MS, un minuto.
//
// Por qué la cuenta global tiene un tope tan corto: cualquiera puede fallar a propósito con el email
// de otra persona. Con un bloqueo largo, un atacante podría dejarla sin acceso indefinidamente. Así,
// lo más que consigue es que la persona espere como mucho un minuto entre intentos.
//
// Peticiones simultáneas. Comprobar la base de datos es asíncrono: si el freno solo contara el fallo
// al terminar, una ráfaga de peticiones simultáneas pasaría entera antes de que se anotara ninguno.
// Por eso cada intento se RESERVA antes de consultar nada (begin(): comprobar y reservar en un solo
// paso síncrono, que en JavaScript nadie puede interrumpir) y cuenta como pendiente. Las esperas se
// calculan con fallos + pendientes. Al terminar, la reserva se resuelve:
//   failed()     la contraseña no era válida: pasa a ser un fallo
//   succeeded()  era válida: se retira, y no cuenta como fallo
//   cancelled()  hubo un error interno (la base de datos, por ejemplo): se retira sin contar nada
// Un acierto borra los fallos anteriores solo si no hay otros intentos en vuelo ni una espera activa
// en ese momento: nunca retira una espera que otra petición haya provocado entretanto.
//
// Los intentos rechazados por la espera no cuentan como fallos (no la alargan). Los fallos se
// olvidan FORGET_AFTER_MS después del último. El freno trata igual un email que existe y uno que no:
// no revela qué cuentas hay. Los emails no se guardan: solo un resumen SHA-256.
//
// Memoria. Vive en la memoria del proceso: se pierde al reiniciar y no se comparte entre varias
// instancias. Guarda como mucho MAX_ENTRIES registros:
//   - un registro olvidado o sin fallos ni intentos en vuelo no protege nada y se borra;
//   - al llegar al máximo, se desaloja el registro inactivo más antiguo (sin espera activa ni
//     intentos en vuelo). Un registro ACTIVO nunca se desaloja: llenar la tabla no borra una espera;
//   - si todos los registros que se revisan están activos, el intento se admite sin registro propio
//     dentro de un cupo global de reserva (OVERFLOW_ATTEMPTS por OVERFLOW_WINDOW_MS); agotado ese
//     cupo, se pide esperar. Solo ocurre con la tabla llena de esperas activas, es decir, durante un
//     ataque muy grande: entonces el freno se vuelve más estricto en vez de olvidar.

import { createHash } from 'node:crypto';

export const PAIR_FREE = 5;
export const PAIR_MAX_DELAY_MS = 15 * 60 * 1000;
export const ACCOUNT_FREE = 20;
export const ACCOUNT_MAX_DELAY_MS = 60 * 1000;
export const FORGET_AFTER_MS = 60 * 60 * 1000;
export const MAX_ENTRIES = 50_000;
// Cupo de reserva con la tabla llena de registros activos, y cuántos registros se revisan, de los
// más antiguos a los más recientes, buscando uno inactivo que desalojar.
export const OVERFLOW_ATTEMPTS = 100;
export const OVERFLOW_WINDOW_MS = 60 * 1000;
const EVICTION_SCAN = 1000;

const LIMITS = {
  pair: { free: PAIR_FREE, max: PAIR_MAX_DELAY_MS },
  account: { free: ACCOUNT_FREE, max: ACCOUNT_MAX_DELAY_MS },
};

export function createLoginThrottle({ now = Date.now, maxEntries = MAX_ENTRIES, overflowAttempts = OVERFLOW_ATTEMPTS } = {}) {
  // key -> { kind: 'pair' | 'account', failures, pending, lastFailure, lastReserve, seq }
  // `seq` cuenta los fallos anotados: un acierto sabe así si hubo alguno desde que empezó.
  const entries = new Map();
  let overflow = { start: 0, used: 0 };

  const accountKey = (email) => `a:${createHash('sha256').update(email).digest('base64url')}`;
  const pairKey = (email, client) => `p:${accountKey(email)}|${client}`;

  function remaining(entry) {
    if (!entry) return 0;
    const { free, max } = LIMITS[entry.kind];
    const count = entry.failures + entry.pending;
    if (count < free) return 0;
    // Con intentos en vuelo, la espera cuenta desde la última reserva; sin ellos, desde el último fallo.
    const since = entry.pending > 0 ? Math.max(entry.lastFailure, entry.lastReserve) : entry.lastFailure;
    return Math.max(0, since + Math.min(max, 1000 * 2 ** (count - free)) - now());
  }

  const active = (entry) => entry.pending > 0 || remaining(entry) > 0;
  const lastActivity = (entry) => Math.max(entry.lastFailure, entry.lastReserve);

  function read(key) {
    const entry = entries.get(key);
    if (entry && entry.pending === 0 && now() - lastActivity(entry) > FORGET_AFTER_MS) {
      entries.delete(key);
      return null;
    }
    return entry ?? null;
  }

  // Al final del Map: su orden es el de uso más reciente, y se desaloja desde el principio.
  function touch(key, entry) {
    entries.delete(key);
    entries.set(key, entry);
  }

  function evictOne() {
    let scanned = 0;
    for (const [key, entry] of entries) {
      if (!active(entry)) {
        entries.delete(key);
        return true;
      }
      scanned += 1;
      if (scanned >= EVICTION_SCAN) break;
    }
    return false;
  }

  /** Un registro para `key`, creándolo si hace falta y hay sitio; null si la tabla está llena de activos. */
  function obtain(key, kind) {
    const existing = read(key);
    if (existing) return existing;
    while (entries.size >= maxEntries) if (!evictOne()) return null;
    const entry = { kind, failures: 0, pending: 0, lastFailure: now(), lastReserve: now(), seq: 0 };
    entries.set(key, entry);
    return entry;
  }

  function takeOverflow() {
    const time = now();
    if (time - overflow.start >= OVERFLOW_WINDOW_MS) overflow = { start: time, used: 0 };
    if (overflow.used >= overflowAttempts) return overflow.start + OVERFLOW_WINDOW_MS - time;
    overflow.used += 1;
    return 0;
  }

  function release(key, entry) {
    if (entry.pending === 0 && entry.failures === 0) entries.delete(key);
  }

  return {
    /**
     * Comprueba y, si se puede intentar, reserva el intento en el mismo paso. Devuelve { wait } con
     * los milisegundos que hay que esperar, o { attempt } con failed(), succeeded() y cancelled().
     */
    begin(email, client) {
      const keys = [[pairKey(email, client), 'pair'], [accountKey(email), 'account']];
      const wait = Math.max(...keys.map(([key]) => remaining(read(key))));
      if (wait > 0) return { wait };

      // Cada registro se reserva en cuanto se obtiene: así, buscando sitio para el segundo, nunca se
      // desaloja el primero, que ya es de este intento.
      const tracked = [];
      for (const [key, kind] of keys) {
        const entry = obtain(key, kind);
        if (!entry) continue;
        entry.pending += 1;
        tracked.push([key, entry]);
      }
      if (tracked.length < keys.length) {
        const overflowWait = takeOverflow();
        if (overflowWait > 0) {
          for (const [key, entry] of tracked) {
            entry.pending -= 1;
            release(key, entry);
          }
          return { wait: overflowWait };
        }
      }
      const started = new Map();
      for (const [key, entry] of tracked) {
        entry.lastReserve = now();
        started.set(entry, entry.seq);
        touch(key, entry);
      }

      let settled = false;
      const settle = (apply) => {
        if (settled) return;
        settled = true;
        for (const [key, entry] of tracked) {
          entry.pending -= 1;
          apply(entry);
          release(key, entry);
        }
      };
      return {
        attempt: {
          failed: () => settle((entry) => {
            entry.failures += 1;
            entry.lastFailure = now();
            entry.seq += 1;
          }),
          // Un acierto borra los fallos anteriores, pero no si otro intento sigue en vuelo o falló
          // después de empezar este: esa espera la necesita otra petición.
          succeeded: () => settle((entry) => {
            if (entry.pending === 0 && entry.seq === started.get(entry)) entry.failures = 0;
          }),
          cancelled: () => settle(() => {}),
        },
      };
    },

    /** Milisegundos que este cliente debe esperar antes de intentarlo con este email (0: puede). */
    wait(email, client) {
      return Math.max(remaining(read(pairKey(email, client))), remaining(read(accountKey(email))));
    },

    get size() { return entries.size; },
  };
}
