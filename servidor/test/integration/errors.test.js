// Errores reales de MySQL o MariaDB: lo que dicen las restricciones del esquema, el modo estricto y
// los bloqueos, y que el registro de la aplicación solo recibe su código (cuenta «app»).

import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';
import express from 'express';
import { connectVerified, resetAppTables } from './guard.js';
import { appContext, listen } from './context.js';

const EMAIL = 'ana@example.test';

describe('SQL errors against nexora_test', () => {
  let pool;
  before(async () => { ({ pool } = await appContext()); });
  beforeEach(() => resetAppTables(pool));

  test('the server runs in strict mode: a value that does not fit is an error, not silently cut', async () => {
    const [[row]] = await pool.query('SELECT @@SESSION.sql_mode AS mode');
    assert.match(row.mode, /STRICT_(TRANS|ALL)_TABLES/, `sql_mode is "${row.mode}": the schema relies on strict mode`);
    await assert.rejects(
      pool.query('INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['x'.repeat(81), EMAIL]),
      (error) => error.code === 'ER_DATA_TOO_LONG',
    );
  });

  test('a duplicated email, OAuth identity or session token is ER_DUP_ENTRY', async () => {
    await pool.query('INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['Ana', EMAIL]);
    const [[user]] = await pool.query('SELECT id FROM `nexora_test`.`users` WHERE email = ?', [EMAIL]);
    await pool.query("INSERT INTO `nexora_test`.`oauth_accounts` (provider, provider_user_id, user_id) VALUES ('google', 'g-1', ?)", [user.id]);
    await pool.query("INSERT INTO `nexora_test`.`sessions` (token_hash, user_id, expires_at) VALUES (UNHEX(SHA2('t', 256)), ?, NOW() + INTERVAL 1 DAY)", [user.id]);
    for (const [sql, params] of [
      ['INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['Otra', EMAIL]],
      ["INSERT INTO `nexora_test`.`oauth_accounts` (provider, provider_user_id, user_id) VALUES ('google', 'g-1', ?)", [user.id]],
      ["INSERT INTO `nexora_test`.`sessions` (token_hash, user_id, expires_at) VALUES (UNHEX(SHA2('t', 256)), ?, NOW() + INTERVAL 1 DAY)", [user.id]],
    ]) {
      await assert.rejects(pool.query(sql, params), (error) => error.code === 'ER_DUP_ENTRY' && error.errno === 1062, sql);
    }
  });

  test('a session or a link for a user that does not exist is refused by the foreign key', async () => {
    for (const sql of [
      "INSERT INTO `nexora_test`.`sessions` (token_hash, user_id, expires_at) VALUES (UNHEX(SHA2('t', 256)), 999999, NOW())",
      "INSERT INTO `nexora_test`.`oauth_accounts` (provider, provider_user_id, user_id) VALUES ('google', 'g-9', 999999)",
    ]) {
      await assert.rejects(pool.query(sql), (error) => error.code === 'ER_NO_REFERENCED_ROW_2', sql);
    }
  });

  test('waiting for a row locked by another transaction ends in ER_LOCK_WAIT_TIMEOUT', async () => {
    await pool.query('INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['Ana', EMAIL]);
    const holder = await connectVerified('app');
    const waiter = await connectVerified('app');
    try {
      await holder.query('START TRANSACTION');
      await holder.query('SELECT id FROM `nexora_test`.`users` WHERE email = ? FOR UPDATE', [EMAIL]);
      await waiter.query('SET SESSION innodb_lock_wait_timeout = 1');
      await assert.rejects(waiter.query('DELETE FROM `nexora_test`.`users` WHERE email = ?', [EMAIL]), (error) => error.code === 'ER_LOCK_WAIT_TIMEOUT');
    } finally {
      await holder.query('ROLLBACK');
      await holder.end();
      await waiter.end();
    }
  });

  test('a database error in a route reaches the log only as its code and the route template', async () => {
    const { createApp } = await import('../../src/app.js');
    const logs = [];
    const authRouter = express.Router();
    authRouter.post('/dup/:id', async (req, res) => {
      await pool.query('INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['Ana', EMAIL]);
      await pool.query('INSERT INTO `nexora_test`.`users` (name, email) VALUES (?, ?)', ['Ana', EMAIL]);
      res.end();
    });
    const s = await listen(createApp({ authRouter, playgroundRouter: express.Router(), log: (line) => logs.push(line) }));
    try {
      const response = await fetch(`${s.base}/api/auth/dup/${encodeURIComponent(EMAIL)}?x=secret`, { method: 'POST' });
      assert.equal(response.status, 500);
      assert.deepEqual(await response.json(), { error: 'Internal server error.' });
      assert.deepEqual(logs, ['error: POST /api/auth/dup/:id: Error ER_DUP_ENTRY']);
    } finally {
      await s.close();
    }
  });
});
