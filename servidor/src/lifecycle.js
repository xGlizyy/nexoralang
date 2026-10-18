// Apagado ordenado del servidor, al recibir SIGTERM (systemd stop) o SIGINT (Ctrl+C).
//
// En orden: /api/health pasa a responder 503 (onDraining) y se pide al borrado de sesiones que pare
// (stopCleanup). Después, a la vez, el servidor deja de aceptar conexiones y espera a las peticiones
// en curso, y se espera a que termine la tanda de borrado que esté en MySQL. Cuando acaban las dos,
// se cierra el pool. Cada espera tiene un tope (timeoutMs): si una petición no termina, se cierran
// sus conexiones; si el borrado no termina, el pool se cierra igualmente (mysql2 pone su QUIT detrás
// de la consulta en curso, no la corta); si el pool no se cierra, se sale igualmente. El proceso
// termina con 0 si todo se cerró a tiempo y con 1 si no. Llamarlo otra vez no repite nada.
//
// Conexiones persistentes (keep-alive): close() solo cierra las que están inactivas en ese momento.
// Una conexión con una petición en curso quedaría abierta después de responder, hasta que el cliente
// la cerrara o venciera keepAliveTimeout (5 s), y el apagado la esperaría. Por eso, desde que empieza
// el apagado, cada respuesta lleva Connection: close; y si ya había enviado sus cabeceras, su conexión
// se cierra en cuanto queda inactiva.

import { describeError } from './safe-log.js';

export const SHUTDOWN_TIMEOUT_MS = 10_000;

/**
 * Resuelve con el resultado de `promise`, o con 'timeout' si tarda más de `ms`. El temporizador del
 * límite no lleva unref(): mientras la espera sigue pendiente, mantiene vivo el proceso. Si no, cuando lo
 * pendiente no tiene ningún recurso detrás (una promesa que no termina), el proceso saldría con 0 antes
 * del límite, sin registrarlo ni llegar a exit(). Se limpia en cuanto la espera termina.
 */
function within(promise, ms) {
  let timer;
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve('timeout'), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * Devuelve shutdown(signal), que apaga una sola vez y devuelve siempre la misma promesa. Hay que
 * crearlo al arrancar: desde ese momento sigue las respuestas en curso del servidor.
 * @param {{ server: import('node:http').Server, closePool?: () => Promise<void>,
 *           stopCleanup?: () => (void | Promise<void>), onDraining?: () => void, timeoutMs?: number,
 *           log?: (line: string) => void, exit?: (code: number) => void }} options
 */
export function createShutdown({
  server,
  closePool = async () => {},
  stopCleanup = () => {},
  onDraining = () => {},
  timeoutMs = SHUTDOWN_TIMEOUT_MS,
  log = console.error,
  exit = (code) => process.exit(code),
}) {
  let shutting = null;
  let draining = false;
  const active = new Set();

  // La conexión de esta respuesta no se reutiliza: se cierra al terminarla.
  function closeAfter(res) {
    if (!res.headersSent) {
      res.setHeader('Connection', 'close');
      return;
    }
    // Las cabeceras ya dijeron keep-alive: la conexión se cierra cuando queda inactiva.
    const closeIdle = () => setImmediate(() => server.closeIdleConnections?.());
    if (res.writableFinished) closeIdle();
    else res.once('finish', closeIdle);
  }

  server.on('request', (req, res) => {
    // Una petición que llega durante el apagado por una conexión que ya estaba abierta.
    if (draining) {
      closeAfter(res);
      return;
    }
    active.add(res);
    res.once('close', () => active.delete(res));
  });

  async function run(signal) {
    let code = 0;
    log(`shutdown: ${signal}: no new connections; waiting up to ${timeoutMs} ms for the requests in progress`);
    // Cada paso por separado: si falla uno, el otro se intenta igualmente.
    try {
      onDraining();
    } catch (error) {
      code = 1;
      log(`shutdown: could not mark the server as draining (${describeError(error)})`);
    }
    let cleanupEnded = Promise.resolve('ended');
    try {
      cleanupEnded = Promise.resolve(stopCleanup()).then(() => 'ended', (error) => error);
    } catch (error) {
      code = 1;
      log(`shutdown: could not stop the background tasks (${describeError(error)})`);
    }

    draining = true;
    for (const res of active) closeAfter(res);

    // close() deja de aceptar conexiones y cierra las que están sin uso; su callback llega cuando
    // se ha cerrado la última.
    const closed = new Promise((resolve) => {
      try {
        server.close((error) => resolve(error ?? 'closed'));
      } catch (error) {
        resolve(error);
      }
    });
    const [result, cleanup] = await Promise.all([within(closed, timeoutMs), within(cleanupEnded, timeoutMs)]);
    if (result === 'timeout') {
      code = 1;
      log(`shutdown: requests still in progress after ${timeoutMs} ms; closing their connections`);
      server.closeAllConnections?.();
    } else if (result !== 'closed') {
      code = 1;
      log(`shutdown: the server did not close cleanly (${describeError(result)})`);
    }
    if (cleanup === 'timeout') {
      code = 1;
      log(`shutdown: the session cleanup did not end within ${timeoutMs} ms; closing the database pool anyway`);
    } else if (cleanup !== 'ended') {
      code = 1;
      log(`shutdown: the session cleanup ended with an error (${describeError(cleanup)})`);
    }

    try {
      if (await within(Promise.resolve().then(closePool), timeoutMs) === 'timeout') {
        code = 1;
        log(`shutdown: the database pool did not close within ${timeoutMs} ms`);
      }
    } catch (error) {
      code = 1;
      log(`shutdown: could not close the database pool (${describeError(error)})`);
    }

    log(`shutdown: done${code === 0 ? '' : ', with errors'}`);
    exit(code);
  }

  return function shutdown(signal) {
    shutting ??= run(signal);
    return shutting;
  };
}
