// Borrado de las sesiones caducadas (src/session-cleanup.js). La base de datos se simula: estas
// pruebas comprueban qué se le pide, no un MySQL real.

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';
import { PURGE_BATCH, PURGE_SQL, QUERY_TIMEOUT_MS, purgeExpiredSessions, startSessionCleanup } from '../src/session-cleanup.js';

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
  assert.deepEqual(logs, ['sessions: could not delete expired sessions (ECONNREFUSED); retrying in the next pass']);
});

test('a query that never answers: the pass gives up, and later passes are skipped and logged instead of piling up', async () => {
  // A query past its deadline may still hold a connection of the shared pool: starting another pass
  // on top of it could, pass after pass, take every connection that log-in needs.
  const logs = [];
  const pool = fakePool(0, { hang: true });
  const cleanup = startSessionCleanup(pool, { interval: 40, passTimeout: 20, log: (line) => logs.push(line) });
  await cleanup.done;
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
  await cleanup.done;
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
  await cleanup.done;
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
  await cleanup.done;
  fail(Object.assign(new Error('timeout'), { code: 'PROTOCOL_SEQUENCE_TIMEOUT' }));
  await new Promise((resolve) => setTimeout(resolve, 10));
  cleanup.stop();
  assert.equal(logs[1], 'sessions: the timed-out pass has ended with an error (PROTOCOL_SEQUENCE_TIMEOUT)');
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
