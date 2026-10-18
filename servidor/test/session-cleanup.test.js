// Borrado de las sesiones caducadas (src/session-cleanup.js). La base de datos se simula: estas
// pruebas comprueban qué se le pide, no un MySQL real.

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import { PURGE_BATCH, PURGE_SQL, QUERY_TIMEOUT_MS, purgeExpiredSessions, startSessionCleanup } from '../src/session-cleanup.js';

/**
 * Espera a `work` con el bucle de eventos vivo, como lo mantienen en el servidor real el servidor HTTP
 * y la conexión del pool. El plazo de cada pasada y su intervalo usan temporizadores con unref(), que no
 * lo mantienen por sí solos: si la consulta simulada no responde, no queda nada pendiente y el ejecutor
 * de pruebas de Node 20 y 22 cancela la prueba antes de que salte el plazo. No cambia lo que se
 * comprueba: el plazo, el intervalo y lo que se anota siguen siendo los de session-cleanup.js. El caso
 * en que no queda ningún otro recurso activo es otro, y estas pruebas no lo cubren.
 * El temporizador que mantiene vivo el bucle es también un límite: si `work` no termina en `limitMs`,
 * la prueba falla en vez de quedarse esperando para siempre (node:test no tiene límite por defecto).
 */
async function whileAlive(work, limitMs = 5_000) {
  let alive;
  const limit = new Promise((resolve, reject) => {
    alive = setTimeout(() => reject(new Error(`still pending after ${limitMs} ms`)), limitMs);
  });
  try {
    return await Promise.race([work(), limit]);
  } finally {
    clearTimeout(alive);
  }
}

/**
 * Un pool que borra `pending` filas caducadas, de PURGE_BATCH en PURGE_BATCH, y anota cada consulta.
 * `fail`: cada consulta falla; `hang`: ninguna responde nunca.
 */
function fakePool(pending, { fail, hang } = {}) {
  const queries = [];
  return {
    queries,
    async query(options) {
      queries.push(options);
      if (hang) return new Promise(() => {});
      if (fail) throw Object.assign(new Error('connect ECONNREFUSED'), { code: 'ECONNREFUSED' });
      const deleted = Math.min(pending, PURGE_BATCH);
      pending -= deleted;
      return [{ affectedRows: deleted }];
    },
  };
}

test('only sessions that the server would no longer accept are deleted, and nothing else', () => {
  assert.equal(PURGE_SQL, `DELETE FROM sessions WHERE expires_at <= NOW() LIMIT ${PURGE_BATCH}`);
  // The exact opposite of the condition under which a session is still accepted, on the same clock.
  const sessions = readFileSync(new URL('../src/sessions.js', import.meta.url), 'utf8');
  assert.match(sessions, /WHERE s\.token_hash = \? AND s\.expires_at > NOW\(\)/);
  assert.match(sessions, /DATE_ADD\(NOW\(\), INTERVAL \? DAY\)/, 'expiry is computed with the same NOW()');
});

test('the condition is served by the index on expires_at', () => {
  const migrations = new URL('../migraciones/', import.meta.url);
  const sql = readdirSync(migrations).map((name) => readFileSync(new URL(name, migrations), 'utf8')).join('\n');
  assert.match(sql, /KEY idx_sessions_expires \(expires_at\)/);
});

test('every query carries the mysql2 timeout', async () => {
  const pool = fakePool(5);
  await purgeExpiredSessions(pool);
  assert.deepEqual(pool.queries, [{ sql: PURGE_SQL, timeout: QUERY_TIMEOUT_MS }]);
});

test('expired sessions are deleted in batches until none is left', async () => {
  const pool = fakePool(PURGE_BATCH * 2 + 5);
  assert.equal(await purgeExpiredSessions(pool), PURGE_BATCH * 2 + 5);
  assert.equal(pool.queries.length, 3);
});

test('with nothing to delete, one query is enough', async () => {
  const pool = fakePool(0);
  assert.equal(await purgeExpiredSessions(pool), 0);
  assert.equal(pool.queries.length, 1);
});

test('one pass stops after a bounded number of batches; the rest waits for the next pass', async () => {
  const pool = fakePool(Number.MAX_SAFE_INTEGER);
  assert.equal(await purgeExpiredSessions(pool), PURGE_BATCH * 100);
});

test('it runs at start-up and a database error is logged, never thrown', async () => {
  const logs = [];
  const cleanup = startSessionCleanup(fakePool(0, { fail: true }), { log: (line) => logs.push(line) });
  await cleanup.done;
  cleanup.stop();
  assert.deepEqual(logs, ['sessions: could not delete expired sessions (Error ECONNREFUSED); retrying in the next pass']);
});

test('a query that never answers: the pass gives up, and later passes are skipped and logged instead of piling up', async () => {
  // A query past its deadline may still hold a connection of the shared pool: starting another pass
  // on top of it could, pass after pass, take every connection that log-in needs.
  const logs = [];
  const pool = fakePool(0, { hang: true });
  const cleanup = startSessionCleanup(pool, { interval: 40, passTimeout: 20, log: (line) => logs.push(line) });
  await whileAlive(() => cleanup.done);
  assert.deepEqual(logs, ['sessions: the pass timed out; it sends no more batches, but the batch in flight may still be running in MySQL; the next pass will retry']);
  await new Promise((resolve) => setTimeout(resolve, 150));
  cleanup.stop();
  assert.equal(pool.queries.length, 1, 'only the hung query was ever sent');
  assert.ok(logs.length >= 3, `skipped passes are logged (${logs.length} lines)`);
  assert.ok(logs.slice(1).every((line) => line === 'sessions: the previous pass is still running; skipping this one'));
});

test('once the late query finally ends, the next pass runs again', async () => {
  const logs = [];
  const queries = [];
  let release;
  const pool = {
    async query(options) {
      queries.push(options);
      if (queries.length === 1) await new Promise((resolve) => { release = resolve; });
      return [{ affectedRows: 0 }];
    },
  };
  const cleanup = startSessionCleanup(pool, { interval: 30, passTimeout: 10, log: (line) => logs.push(line) });
  await whileAlive(() => cleanup.done);
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.equal(queries.length, 1, 'nothing new while the first query runs');
  release();
  await new Promise((resolve) => setTimeout(resolve, 80));
  cleanup.stop();
  assert.ok(queries.length >= 2, `passes resumed (${queries.length} queries)`);
  assert.equal(logs[0], 'sessions: the pass timed out; it sends no more batches, but the batch in flight may still be running in MySQL; the next pass will retry');
  assert.ok(logs.includes('sessions: the timed-out pass has ended; it deleted 0 expired sessions'), logs.join(' | '));
});

test('with its signal aborted, a purge sends no batch at all', async () => {
  const pool = fakePool(PURGE_BATCH * 3);
  const stop = new AbortController();
  stop.abort();
  assert.equal(await purgeExpiredSessions(pool, { signal: stop.signal }), 0);
  assert.equal(pool.queries.length, 0);
});

test('past its deadline a pass sends no new batch; the batch in flight is not cancelled, and what it did is logged', async () => {
  // The first batch comes back full, which would normally ask for another one. It ends after the
  // deadline, so no other batch may be sent; its rows still count, and the log says so.
  const logs = [];
  const queries = [];
  let release;
  const pool = {
    async query(options) {
      queries.push(options);
      if (queries.length === 1) await new Promise((resolve) => { release = resolve; });
      return [{ affectedRows: PURGE_BATCH }];
    },
  };
  const cleanup = startSessionCleanup(pool, { interval: 60_000, passTimeout: 10, log: (line) => logs.push(line) });
  await whileAlive(() => cleanup.done);
  release();
  await new Promise((resolve) => setTimeout(resolve, 30));
  cleanup.stop();
  assert.equal(queries.length, 1, 'no batch after the deadline');
  assert.deepEqual(logs, [
    'sessions: the pass timed out; it sends no more batches, but the batch in flight may still be running in MySQL; the next pass will retry',
    `sessions: the timed-out pass has ended; it deleted ${PURGE_BATCH} expired sessions`,
  ]);
});

test('a timed-out pass that later fails says so', async () => {
  const logs = [];
  let fail;
  const pool = { query: () => new Promise((resolve, reject) => { fail = reject; }) };
  const cleanup = startSessionCleanup(pool, { interval: 60_000, passTimeout: 10, log: (line) => logs.push(line) });
  await whileAlive(() => cleanup.done);
  fail(Object.assign(new Error('timeout'), { code: 'PROTOCOL_SEQUENCE_TIMEOUT' }));
  await new Promise((resolve) => setTimeout(resolve, 10));
  cleanup.stop();
  assert.equal(logs[1], 'sessions: the timed-out pass has ended with an error (Error PROTOCOL_SEQUENCE_TIMEOUT)');
});

test('it repeats on its interval, never overlaps, and can be stopped', async () => {
  let active = 0;
  let overlap = false;
  const queries = [];
  const pool = {
    async query(options) {
      queries.push(options);
      active += 1;
      if (active > 1) overlap = true;
      await new Promise((resolve) => setTimeout(resolve, 30)); // slower than the interval
      active -= 1;
      return [{ affectedRows: 0 }];
    },
  };
  const cleanup = startSessionCleanup(pool, { interval: 10 });
  await new Promise((resolve) => setTimeout(resolve, 120));
  cleanup.stop();
  assert.equal(overlap, false, 'two passes never run at once');
  const runs = queries.length;
  assert.ok(runs >= 2, `ran ${runs} times`);
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.equal(queries.length, runs, 'no pass after stop()');
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('stop() waits for the batch in flight, sends no more batches and starts no more passes', async () => {
  // El apagado (lifecycle.js) espera a stop() antes de cerrar el pool: la tanda en curso termina, y
  // no se envía ninguna más aunque quedaran sesiones por borrar.
  let release;
  const queries = [];
  const pool = {
    async query(options) {
      queries.push(options);
      if (queries.length === 1) {
        await new Promise((resolve) => { release = resolve; });
        return [{ affectedRows: PURGE_BATCH }]; // una tanda llena: sin stop(), pediría otra
      }
      return [{ affectedRows: 0 }];
    },
  };
  // El intervalo vence mientras la tanda sigue en curso: esas pasadas se saltan y se anotan aquí.
  const logs = [];
  const cleanup = startSessionCleanup(pool, { interval: 20, log: (line) => logs.push(line) });
  await sleep(10);
  let stopped = false;
  const stopping = Promise.resolve(cleanup.stop()).then(() => { stopped = true; });
  await sleep(60);
  assert.equal(stopped, false, 'stop() waits while the batch is in flight');
  release();
  await stopping;
  assert.equal(queries.length, 1, 'no batch after stop()');
  await sleep(60);
  assert.equal(queries.length, 1, 'no pass after stop()');
  const skipped = 'sessions: the previous pass is still running; skipping this one';
  assert.ok(logs.every((line) => line === skipped), logs.join('\n'));
});

test('stop() with no pass in flight ends at once, and can be called again', async () => {
  const cleanup = startSessionCleanup(fakePool(0), { interval: 60_000 });
  await cleanup.done;
  const first = cleanup.stop();
  assert.ok(first instanceof Promise);
  await first;
  await cleanup.stop();
});

test('stop() while the batch in flight fails: it ends, never rejects, and logs no message', async () => {
  const logs = [];
  const pool = {
    async query() {
      await sleep(30);
      throw new Error('Access denied for user ana@example.com to database nexora');
    },
  };
  const cleanup = startSessionCleanup(pool, { interval: 60_000, log: (line) => logs.push(line) });
  await cleanup.stop();
  await cleanup.done;
  assert.deepEqual(logs, ['sessions: could not delete expired sessions (Error); retrying in the next pass']);
});

test('a database error without a code is logged by its type only, never by its message', async () => {
  const logs = [];
  const pool = { async query() { throw new TypeError("Cannot read properties of undefined (reading 'ana@example.com')"); } };
  const cleanup = startSessionCleanup(pool, { log: (line) => logs.push(line) });
  await cleanup.done;
  cleanup.stop();
  assert.deepEqual(logs, ['sessions: could not delete expired sessions (TypeError); retrying in the next pass']);
});

test('a timed-out pass that later fails without a code: its message is not logged either', async () => {
  const logs = [];
  let fail;
  const pool = { query: () => new Promise((resolve, reject) => { fail = reject; }) };
  const cleanup = startSessionCleanup(pool, { interval: 60_000, passTimeout: 10, log: (line) => logs.push(line) });
  await whileAlive(() => cleanup.done);
  fail(new Error('Lock wait timeout exceeded; try restarting transaction for ana@example.com'));
  await sleep(10);
  cleanup.stop();
  assert.equal(logs[1], 'sessions: the timed-out pass has ended with an error (Error)');
});
