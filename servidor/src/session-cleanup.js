// Borrado periódico de las sesiones caducadas.
//
// Una sesión caducada ya no sirve: currentUser() (sessions.js) solo acepta las que cumplen
// `expires_at > NOW()`. Este borrado usa la condición exacta contraria, `expires_at <= NOW()`, con el
// mismo reloj (el NOW() de MySQL, el mismo con que se calculó expires_at al crearla), así que nunca
// toca una sesión que todavía se aceptaría. No borra usuarios ni ningún otro dato. La condición usa
// el índice idx_sessions_expires (migraciones/).
//
// Borra por tandas para no bloquear la tabla mucho tiempo si se han acumulado muchas.
//
// Replicación: `DELETE … LIMIT` sin orden definido es una sentencia «insegura» para la replicación
// basada en sentencias (binlog_format=STATEMENT): las réplicas podrían borrar otras filas. Con
// binlog_format=ROW (el valor por defecto de MySQL 8) o MIXED no hay problema. Añadir ORDER BY no
// basta por sí solo para todas las configuraciones; si el servidor de destino usa STATEMENT, la
// alternativa es seleccionar primero las claves de la tanda y borrarlas por su clave primaria. Es una
// decisión pendiente: depende del MySQL de producción, que no se conoce desde el repositorio.

export const PURGE_BATCH = 1000;
// Tope de tandas en una pasada: lo que quede se borra en la siguiente.
const MAX_BATCHES = 100;
export const PURGE_INTERVAL_MS = 60 * 60 * 1000;
// Tiempo máximo de cada consulta, con la opción `timeout` de mysql2: pasado ese tiempo la promesa
// falla (PROTOCOL_SEQUENCE_TIMEOUT). Hay que distinguir tres cosas (mysql2 3.24.6, comprobado en su
// código):
//   - el tiempo de la aplicación: la promesa falla y la pasada termina; esto sí lo garantiza;
//   - la cancelación de la consulta: NO ocurre. El tope es del cliente, no del protocolo de MySQL, y
//     la sentencia sigue ejecutándose en el servidor hasta que termine;
//   - la liberación de la conexión: tampoco es inmediata. El pool la devuelve cuando la sentencia
//     acaba de verdad (evento 'end' en lib/base/pool.js), no al vencer el tope. Los tipos de mysql2
//     dicen que la conexión «se destruye», pero el código de esta versión no lo hace.
// Consecuencia: un DELETE que se quedara bloqueado en MySQL retendría una de las conexiones del pool
// hasta que el servidor lo resolviera (innodb_lock_wait_timeout, 50 s por defecto, corta las esperas
// por bloqueo). Corregirlo (KILL QUERY o destruir la conexión) está pendiente de probar con un MySQL
// de pruebas: ver «Tareas pendientes y riesgos» en nexora/docs/playground.md.
export const QUERY_TIMEOUT_MS = 30 * 1000;
// Tiempo máximo de una pasada entera. Si se supera, la pasada se anota como vencida y no envía ninguna
// tanda más, pero la que ya estaba en curso no se cancela y puede seguir en marcha (y en MySQL, aunque
// mysql2 la dé por terminada). Cuando por fin termina, se anota cuántas sesiones borró o con qué error
// acabó. Mientras no termine, las pasadas siguientes no empiezan, solo se anotan como omitidas. Así el borrado nunca tiene más de una pasada en curso ni acumula consultas bloqueadas
// que ocupen conexiones del pool, que es el mismo que usan el registro y el inicio de sesión. El
// precio: si una consulta no terminara nunca, el borrado quedaría detenido (y el registro lo diría
// cada hora) hasta reiniciar el servidor. Con mysql2 eso no ocurre, porque cada consulta falla como
// mucho a los QUERY_TIMEOUT_MS; cancelar de verdad una sentencia sigue pendiente (ver arriba).
export const PASS_TIMEOUT_MS = 5 * 60 * 1000;

export const PURGE_SQL = `DELETE FROM sessions WHERE expires_at <= NOW() LIMIT ${PURGE_BATCH}`;

/**
 * Borra las sesiones caducadas. Devuelve cuántas borró. Con `signal` abortada no envía ninguna tanda
 * más; la que ya esté en curso no se cancela (ni aquí ni en MySQL) y su resultado sí se cuenta.
 */
export async function purgeExpiredSessions(pool, { timeout = QUERY_TIMEOUT_MS, signal } = {}) {
  let total = 0;
  for (let batch = 0; batch < MAX_BATCHES; batch += 1) {
    if (signal?.aborted) break;
    const [result] = await pool.query({ sql: PURGE_SQL, timeout });
    total += result.affectedRows;
    if (result.affectedRows < PURGE_BATCH) break;
  }
  return total;
}

/**
 * Borra las sesiones caducadas al arrancar y después cada hora. Un fallo (por ejemplo, la base de
 * datos no disponible) se anota y se reintenta en la siguiente pasada; nunca detiene el servidor.
 * Devuelve una función que detiene el borrado periódico.
 */
export function startSessionCleanup(pool, {
  interval = PURGE_INTERVAL_MS,
  queryTimeout = QUERY_TIMEOUT_MS,
  passTimeout = PASS_TIMEOUT_MS,
  log = console.error,
} = {}) {
  // Las consultas de la pasada en curso, hasta que terminen de verdad (no hasta que venza el tope).
  let inFlight = null;
  const run = async () => {
    if (inFlight) {
      log('sessions: the previous pass is still running; skipping this one');
      return;
    }
    // Al vencer el plazo, la pasada deja de enviar tandas nuevas; la que esté en curso sigue.
    const stop = new AbortController();
    let timedOut = false;
    const purge = purgeExpiredSessions(pool, { timeout: queryTimeout, signal: stop.signal });
    inFlight = purge;
    purge.then(
      (deleted) => {
        inFlight = null;
        if (timedOut) log(`sessions: the timed-out pass has ended; it deleted ${deleted} expired sessions`);
      },
      (error) => {
        inFlight = null;
        if (timedOut) log(`sessions: the timed-out pass has ended with an error (${error.code ?? error.message})`);
      },
    );
    let timer;
    try {
      const deadline = new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(Object.assign(new Error('pass timeout'), { code: 'PASS_TIMEOUT' })), passTimeout);
        timer.unref();
      });
      await Promise.race([purge, deadline]);
    } catch (error) {
      if (error.code === 'PASS_TIMEOUT') {
        timedOut = true;
        stop.abort();
        log('sessions: the pass timed out; it sends no more batches, but the batch in flight may still be running in MySQL; the next pass will retry');
      } else {
        log(`sessions: could not delete expired sessions (${error.code ?? error.message}); retrying in the next pass`);
      }
    } finally {
      clearTimeout(timer);
    }
  };
  const done = run();
  const timer = setInterval(run, interval);
  timer.unref(); // no mantiene vivo el proceso por sí solo
  return { done, stop: () => clearInterval(timer) };
}
