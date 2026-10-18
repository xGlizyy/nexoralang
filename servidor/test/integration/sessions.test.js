// Sesiones caducadas, su borrado por tandas y el cierre del pool de mysql2 con consultas en curso y
// bloqueos reales de InnoDB, contra nexora_test (cuenta «app»).

import assert from 'node:assert/strict';
import http from 'node:http';
import { after, before, beforeEach, describe, test } from 'node:test';
import { connectVerified, openVerifiedPool, resetAppTables } from './guard.js';
import { appContext, count } from './context.js';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Un usuario y `expired` sesiones caducadas más `valid` vigentes, insertadas de una vez. */
async function seed(pool, { expired = 0, valid = 0 } = {}) {
  await pool.query("INSERT INTO `nexora_test`.`users` (name, email) VALUES ('Ana', 'ana@example.test')");
  const [[user]] = await pool.query("SELECT id FROM `nexora_test`.`users` WHERE email = 'ana@example.test'");
  const rows = [];
  for (let i = 0; i < expired + valid; i++) rows.push([`s-${i}`, user.id, i < expired ? -60 : 3600]);
  for (let at = 0; at < rows.length; at += 500) {
    const chunk = rows.slice(at, at + 500);
    await pool.query(
      `INSERT INTO \`nexora_test\`.\`sessions\` (token_hash, user_id, expires_at) VALUES ${chunk.map(() => '(UNHEX(SHA2(?, 256)), ?, NOW() + INTERVAL ? SECOND)').join(', ')}`,
      chunk.flat(),
    );
  }
  return user.id;
}

describe('sessions against nexora_test', () => {
  let pool;
  let cleanup;
  before(async () => {
    ({ pool } = await appContext());
    cleanup = await import('../../src/session-cleanup.js');
  });
  beforeEach(() => resetAppTables(pool));

  test('the purge deletes only expired sessions, in batches, until none is left', async () => {
    await seed(pool, { expired: 2500, valid: 3 });
    assert.equal(await cleanup.purgeExpiredSessions(pool), 2500);
    assert.equal(await count(pool, 'sessions'), 3);
    assert.equal(await cleanup.purgeExpiredSessions(pool), 0);
  });

  test('deleting a user deletes its sessions and its OAuth links (ON DELETE CASCADE)', async () => {
    const id = await seed(pool, { valid: 2 });
    await pool.query("INSERT INTO `nexora_test`.`oauth_accounts` (provider, provider_user_id, user_id) VALUES ('google', 'g-1', ?)", [id]);
    await pool.query('DELETE FROM `nexora_test`.`users` WHERE id = ?', [id]);
    assert.equal(await count(pool, 'sessions'), 0);
    assert.equal(await count(pool, 'oauth_accounts'), 0);
  });

  test('the periodic cleanup with the real pool: it purges, and stop() ends it', async () => {
    await seed(pool, { expired: 10, valid: 1 });
    const logs = [];
    const job = cleanup.startSessionCleanup(pool, { interval: 60_000, log: (line) => logs.push(line) });
    await job.done;
    await job.stop();
    assert.equal(await count(pool, 'sessions'), 1);
    assert.deepEqual(logs, []);
  });
});

describe('closing a mysql2 pool with work in progress (the claims of lifecycle.js)', () => {
  let shared;
  before(async () => { ({ pool: shared } = await appContext()); });
  beforeEach(() => resetAppTables(shared));

  test('pool.end() lets a query in progress finish, and then refuses new ones', async () => {
    const pool = await openVerifiedPool('app');
    const started = Date.now();
    const slow = pool.query('SELECT SLEEP(1) AS slept');
    await sleep(100);
    const ended = pool.end();
    const [[row]] = await slow;
    assert.equal(Number(row.slept), 0, 'SLEEP returns 0 when it was not interrupted');
    await ended;
    assert.ok(Date.now() - started >= 900);
    await assert.rejects(pool.query('SELECT 1'), /Pool is closed/);
  });

  test('a cleanup DELETE blocked by a lock: the shutdown waits its limit, closes the pool anyway and exits 1', async () => {
    const { createShutdown } = await import('../../src/lifecycle.js');
    const { startSessionCleanup } = await import('../../src/session-cleanup.js');
    await seed(shared, { expired: 5 });
    // Otra conexión bloquea las sesiones caducadas: el DELETE del borrado tiene que esperar.
    const locker = await connectVerified('app');
    await locker.query('START TRANSACTION');
    await locker.query('SELECT token_hash FROM `nexora_test`.`sessions` WHERE expires_at <= NOW() FOR UPDATE');
    const pool = await openVerifiedPool('app');
    const job = startSessionCleanup(pool, { interval: 60_000, log: () => {} });
    await sleep(200); // el DELETE ya está esperando al bloqueo
    const server = http.createServer();
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const logs = [];
    let exitCode;
    const started = Date.now();
    await createShutdown({ server, closePool: () => pool.end(), stopCleanup: job.stop, timeoutMs: 1000, log: (line) => logs.push(line), exit: (code) => { exitCode = code; } })('SIGTERM');
    assert.equal(exitCode, 1);
    assert.ok(Date.now() - started < 4000);
    assert.ok(logs.includes('shutdown: the session cleanup did not end within 1000 ms; closing the database pool anyway'), logs.join('\n'));
    assert.ok(logs.includes('shutdown: the database pool did not close within 1000 ms'), logs.join('\n'));
    // Al soltar el bloqueo, el DELETE en curso termina (no se cortó) y el pool acaba de cerrarse.
    await locker.query('ROLLBACK');
    await locker.end();
    await job.stop();
    assert.equal(await count(shared, 'sessions'), 0, 'the batch that was waiting did run');
  });
});
