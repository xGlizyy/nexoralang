// Inicio de sesión con Google y GitHub con proveedores SIMULADOS (ninguna petición sale de este
// equipo) y persistencia REAL en nexora_test (cuenta «app»): transacciones, rollback, conexiones del
// pool y dos primeros accesos a la vez con el mismo email.

import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';
import express from 'express';
import { resetAppTables } from './guard.js';
import { appContext, count, listen } from './context.js';

const EMAIL = 'ana@example.test';
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const SETTINGS = {
  oauth: { google: { clientId: 'test-google', clientSecret: 'test-secret' }, github: { clientId: 'test-github', clientSecret: 'test-secret' } },
  publicUrl: 'http://127.0.0.1:1',
  production: false,
};

/** Respuestas de los proveedores para una identidad: Google con `sub`, GitHub con `id`. */
function answersFor({ sub = 'g-1', githubId = 7, email = EMAIL } = {}) {
  return {
    'https://oauth2.googleapis.com/token': () => json({ access_token: 'test-token' }),
    'https://openidconnect.googleapis.com/v1/userinfo': () => json({ sub, name: 'Ana', email, email_verified: true }),
    'https://github.com/login/oauth/access_token': () => json({ access_token: 'test-token' }),
    'https://api.github.com/user': () => json({ id: githubId, login: 'ana' }),
    'https://api.github.com/user/emails': () => json([{ email, primary: true, verified: true }]),
  };
}

describe('OAuth against nexora_test', () => {
  let pool;
  let createOAuthRouter;
  let startSession;
  before(async () => {
    ({ pool } = await appContext());
    ({ createOAuthRouter } = await import('../../src/oauth.js'));
    ({ startSession } = await import('../../src/sessions.js'));
  });
  beforeEach(() => resetAppTables(pool));

  /** Sirve las rutas con este pool (o un envoltorio) y estos proveedores; devuelve cómo recorrer el flujo. */
  async function serve({ db = pool, answers = answersFor() } = {}) {
    const logs = [];
    const app = express();
    app.use('/api/auth', createOAuthRouter({
      settings: SETTINGS, db, begin: startSession, log: (line) => logs.push(line),
      fetch: async (url) => { const answer = answers[url]; if (!answer) throw new TypeError('fetch failed'); return answer(); },
    }));
    const s = await listen(app);
    async function login(provider) {
      const started = await fetch(`${s.base}/api/auth/${provider}`, { redirect: 'manual' });
      const state = new URL(started.headers.get('location')).searchParams.get('state');
      const cookie = started.headers.get('set-cookie').split(';')[0];
      const done = await fetch(`${s.base}/api/auth/${provider}/callback?code=c&state=${state}`, { redirect: 'manual', headers: { Cookie: cookie } });
      return done.headers.get('location');
    }
    return { ...s, logs, login };
  }

  test('first sign-in: one user, one link and one session, all committed', async () => {
    const s = await serve();
    try {
      assert.equal(await s.login('google'), '/');
      assert.equal(await count(pool, 'users', EMAIL), 1);
      assert.equal(await count(pool, 'oauth_accounts', EMAIL), 1);
      assert.equal(await count(pool, 'sessions', EMAIL), 1);
      const [[user]] = await pool.query('SELECT password_hash FROM `nexora_test`.`users` WHERE email = ?', [EMAIL]);
      assert.equal(user.password_hash, null);
      // La segunda vez, la identidad ya está enlazada: ninguna fila nueva salvo la sesión.
      assert.equal(await s.login('google'), '/');
      assert.equal(await count(pool, 'users'), 1);
      assert.equal(await count(pool, 'oauth_accounts'), 1);
      assert.equal(await count(pool, 'sessions'), 2);
    } finally {
      await s.close();
    }
  });

  test('a user created by Google is linked by GitHub with the same verified email, not duplicated', async () => {
    const s = await serve();
    try {
      await s.login('google');
      assert.equal(await s.login('github'), '/');
      assert.equal(await count(pool, 'users'), 1);
      assert.equal(await count(pool, 'oauth_accounts', EMAIL), 2);
    } finally {
      await s.close();
    }
  });

  test('an account with a password is never linked: account_exists, and no link row', async () => {
    await pool.query("INSERT INTO `nexora_test`.`users` (name, email, password_hash) VALUES ('Ana', ?, 'scrypt$32768$8$1$x$y')", [EMAIL]);
    const s = await serve();
    try {
      assert.equal(await s.login('google'), '/login?error=account_exists');
      assert.equal(await count(pool, 'oauth_accounts'), 0);
      assert.equal(await count(pool, 'sessions'), 0);
    } finally {
      await s.close();
    }
  });

  /** El pool real, salvo que el INSERT del enlace falla dentro de la transacción. */
  const failingLink = () => ({
    execute: (...args) => pool.execute(...args),
    async getConnection() {
      const connection = await pool.getConnection();
      return new Proxy(connection, {
        get(target, name) {
          if (name === 'execute') {
            return async (sql, params) => {
              if (sql.startsWith('INSERT INTO oauth_accounts')) throw Object.assign(new Error('simulated'), { code: 'ER_LOCK_DEADLOCK' });
              return target.execute(sql, params);
            };
          }
          const value = target[name];
          return typeof value === 'function' ? value.bind(target) : value;
        },
      });
    },
  });

  test('a failure inside the transaction leaves NO user in the database (a real rollback)', async () => {
    const s = await serve({ db: failingLink() });
    try {
      assert.equal(await s.login('google'), '/login?error=oauth_failed');
      assert.equal(await count(pool, 'users', EMAIL), 0, 'the INSERT INTO users was rolled back');
      assert.equal(await count(pool, 'sessions'), 0);
      assert.deepEqual(s.logs, ['oauth: google: sign-in failed (Error ER_LOCK_DEADLOCK)']);
    } finally {
      await s.close();
    }
  });

  test('failures return their connections: more failures than the pool has connections, and it still answers', async () => {
    const s = await serve({ db: failingLink() });
    try {
      for (let i = 0; i < 15; i++) assert.equal(await s.login('google'), '/login?error=oauth_failed'); // el pool tiene 10
      const started = Date.now();
      const [[row]] = await pool.query('SELECT 1 AS one');
      assert.equal(row.one, 1);
      assert.ok(Date.now() - started < 2000, 'no connection was left taken');
    } finally {
      await s.close();
    }
  });

  test('two first sign-ins at once with the same email: never two users with that email', async () => {
    // Google y GitHub a la vez, la primera vez, con el mismo email verificado. SELECT … FOR UPDATE sobre
    // una fila que no existe deja un bloqueo de hueco en InnoDB: las dos pueden llegar al INSERT y una
    // fallar (bloqueo mutuo o clave duplicada). Lo que no puede pasar es un usuario duplicado o un enlace
    // huérfano. Se repite para dar varias oportunidades a la carrera.
    for (let round = 0; round < 5; round++) {
      await resetAppTables(pool);
      const s = await serve();
      try {
        const outcomes = await Promise.all([s.login('google'), s.login('github')]);
        for (const outcome of outcomes) assert.ok(['/', '/login?error=oauth_failed'].includes(outcome), outcome);
        assert.ok(outcomes.includes('/'), `round ${round}: at least one of them signs in`);
        assert.equal(await count(pool, 'users', EMAIL), 1, `round ${round}`);
        const [orphans] = await pool.query('SELECT COUNT(*) AS n FROM `nexora_test`.`oauth_accounts` a LEFT JOIN `nexora_test`.`users` u ON u.id = a.user_id WHERE u.id IS NULL');
        assert.equal(Number(orphans[0].n), 0);
        for (const line of s.logs) assert.match(line, /^oauth: (google|github): sign-in failed \(Error (ER_LOCK_DEADLOCK|ER_DUP_ENTRY)\)$/);
      } finally {
        await s.close();
      }
    }
  });
});
