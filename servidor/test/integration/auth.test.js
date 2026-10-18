// Registro, inicio y cierre de sesión con la aplicación real y nexora_test (cuenta «app»).

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { after, before, beforeEach, describe, test } from 'node:test';
import express from 'express';
import { resetAppTables } from './guard.js';
import { appContext, count, listen } from './context.js';

const PASSWORD = 'integration-only-pass';
const sha256 = (text) => createHash('sha256').update(text).digest();

describe('accounts against nexora_test', () => {
  let pool;
  let s;
  let logs;
  let createApp;
  let createAuthRouter;
  let loadCaptchaConfig;
  let sessions;

  before(async () => {
    ({ pool } = await appContext());
    ({ createApp } = await import('../../src/app.js'));
    ({ createAuthRouter } = await import('../../src/auth.js'));
    ({ loadCaptchaConfig } = await import('../../src/captcha.js'));
    sessions = await import('../../src/sessions.js');
    logs = [];
    // Sin límite de intentos que estorbe, sin reCAPTCHA y sin proveedores OAuth (oauth.test.js).
    const authRouter = createAuthRouter({ db: pool, captcha: loadCaptchaConfig({}), attemptsLimit: 100_000, providers: null });
    s = await listen(createApp({ authRouter, playgroundRouter: express.Router(), log: (line) => logs.push(line) }));
  });
  after(() => s?.close());
  beforeEach(async () => {
    await resetAppTables(pool);
    logs.length = 0;
  });

  const post = (path, body, cookie) => fetch(`${s.base}/api/auth${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) }, body: JSON.stringify(body ?? {}),
  });
  const me = async (cookie) => (await fetch(`${s.base}/api/auth/me`, { headers: cookie ? { Cookie: cookie } : {} })).json();
  const sessionCookie = (response) => response.headers.get('set-cookie')?.match(/nexora_session=([^;]+)/)?.[1];

  test('sign-up stores the account and a session as hashes, never the password or the token', async () => {
    const response = await post('/signup', { name: 'Ana', email: 'Ana@Example.TEST', password: PASSWORD });
    assert.equal(response.status, 201);
    const token = sessionCookie(response);
    assert.match(token, /^[\w-]{43}$/);
    assert.match(response.headers.get('set-cookie'), /HttpOnly/);
    const [[user]] = await pool.query("SELECT id, name, email, password_hash FROM `nexora_test`.`users` WHERE email = 'ana@example.test'");
    assert.equal(user.name, 'Ana');
    assert.match(user.password_hash, /^scrypt\$32768\$8\$1\$[\w+/=]+\$[\w+/=]+$/);
    assert.ok(!user.password_hash.includes(PASSWORD));
    const [[session]] = await pool.query(
      'SELECT token_hash, TIMESTAMPDIFF(HOUR, NOW(), expires_at) AS hours FROM `nexora_test`.`sessions` WHERE user_id = ?', [user.id],
    );
    assert.deepEqual(session.token_hash, sha256(token));
    assert.ok(session.hours >= 30 * 24 - 1 && session.hours <= 30 * 24, String(session.hours));
    assert.deepEqual((await me(`nexora_session=${token}`)).user, { id: user.id, name: 'Ana', email: 'ana@example.test' });
  });

  test('the same email, written in other letters, is refused with 409 and no second row', async () => {
    assert.equal((await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD })).status, 201);
    assert.equal((await post('/signup', { name: 'Otra', email: 'ANA@example.test', password: PASSWORD })).status, 409);
    assert.equal(await count(pool, 'users'), 1);
    assert.equal(await count(pool, 'sessions'), 1);
  });

  test('a wrong password creates no session; the right one creates a new one', async () => {
    await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD });
    assert.equal((await post('/login', { email: 'ana@example.test', password: 'wrong-password-1' })).status, 401);
    assert.equal(await count(pool, 'sessions'), 1);
    const response = await post('/login', { email: 'ana@example.test', password: PASSWORD });
    assert.equal(response.status, 200);
    assert.equal(await count(pool, 'sessions'), 2);
    assert.ok(sessionCookie(response));
  });

  test('an account without a password (from Google or GitHub) never logs in with a password', async () => {
    await pool.query("INSERT INTO `nexora_test`.`users` (name, email, password_hash) VALUES ('Ana', 'ana@example.test', NULL)");
    assert.equal((await post('/login', { email: 'ana@example.test', password: PASSWORD })).status, 401);
    assert.equal(await count(pool, 'sessions'), 0);
  });

  test('log-out deletes exactly that session; the others stay', async () => {
    const first = sessionCookie(await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD }));
    const second = sessionCookie(await post('/login', { email: 'ana@example.test', password: PASSWORD }));
    assert.equal((await post('/logout', {}, `nexora_session=${first}`)).status, 204);
    assert.equal((await me(`nexora_session=${first}`)).user, null);
    assert.equal((await me(`nexora_session=${second}`)).user.email, 'ana@example.test');
    const [rows] = await pool.query('SELECT token_hash FROM `nexora_test`.`sessions`');
    assert.deepEqual(rows.map((row) => row.token_hash), [sha256(second)]);
  });

  test('an expired session is not accepted, even if its row is still there', async () => {
    await pool.query("INSERT INTO `nexora_test`.`users` (name, email) VALUES ('Ana', 'ana@example.test')");
    const [[user]] = await pool.query("SELECT id FROM `nexora_test`.`users` WHERE email = 'ana@example.test'");
    await pool.query('INSERT INTO `nexora_test`.`sessions` (token_hash, user_id, expires_at) VALUES (?, ?, NOW() - INTERVAL 1 MINUTE)', [sha256('old-token'), user.id]);
    assert.equal((await me('nexora_session=old-token')).user, null);
    assert.equal(await sessions.currentUser({ headers: { cookie: 'nexora_session=old-token' } }), null);
  });

  test('sign-up is atomic: if the session cannot be stored, no account is left behind (a real rollback)', async () => {
    // La sesión falla después de que el INSERT del usuario ya se ejecutó en la transacción.
    const failing = { ...sessions, createSession: async () => { throw Object.assign(new Error('simulated'), { code: 'ER_LOCK_WAIT_TIMEOUT' }); } };
    const router = createAuthRouter({ db: pool, sessions: failing, captcha: loadCaptchaConfig({}), attemptsLimit: 100_000, providers: null });
    const other = await listen(createApp({ authRouter: router, playgroundRouter: express.Router(), log: () => {} }));
    try {
      const response = await fetch(`${other.base}/api/auth/signup`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Ana', email: 'ana@example.test', password: PASSWORD }),
      });
      assert.equal(response.status, 500);
      assert.equal(response.headers.get('set-cookie'), null);
      assert.equal(await count(pool, 'users', 'ana@example.test'), 0);
      assert.equal(await count(pool, 'sessions'), 0);
      // Y la misma persona puede registrarse después: no quedó nada a medias.
      assert.equal((await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD })).status, 201);
    } finally {
      await other.close();
    }
  });

  test('nothing of the account reaches the log', async () => {
    await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD });
    await post('/signup', { name: 'Ana', email: 'ana@example.test', password: PASSWORD });
    await post('/login', { email: 'ana@example.test', password: 'wrong-password-1' });
    const text = logs.join('\n');
    for (const value of ['ana@example.test', PASSWORD, 'wrong-password-1', 'Duplicate', 'INSERT']) assert.ok(!text.includes(value), value);
  });
});
