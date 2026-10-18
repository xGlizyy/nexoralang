// /api/health y el registro de errores de la aplicación real (src/app.js), con rutas de cuentas y del
// playground sustituidas: ninguna prueba consulta la base de datos.

// app.js carga la configuración real, que exige variables de base de datos. Apuntan a un puerto donde
// no hay nada: si una prueba llegara a consultarla, fallaría.
process.env.DB_USER = 'test';
process.env.DB_NAME = 'test';
process.env.DB_HOST = '127.0.0.1';
process.env.DB_PORT = '1';

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import express from 'express';

const { createApp } = await import('../src/app.js');
const { API_POLICY } = await import('../src/security-headers.js');

const EMAIL = 'ana@example.com';

async function serve(options = {}) {
  const logs = [];
  const queries = [];
  // Unas rutas de cuentas que fallan como fallaría MySQL: con la consulta y el email en el error.
  const authRouter = express.Router();
  authRouter.post('/boom', (req, res, next) => {
    queries.push('INSERT');
    next(Object.assign(new Error(`Duplicate entry '${EMAIL}' for key 'uq_users_email'`), {
      code: 'ER_DUP_ENTRY', errno: 1062, sql: `INSERT INTO users (email) VALUES ('${EMAIL}')`, sqlMessage: `Duplicate entry '${EMAIL}'`,
    }));
  });
  authRouter.get('/odd', (req, res, next) => next(Object.assign(new Error('x'), { code: `password=${EMAIL}` })));
  // Un router dentro de otro, como oauth.js dentro de auth.js, con un parámetro en la ruta.
  const nested = express.Router();
  nested.get('/:provider/callback', (req, res, next) => next(Object.assign(new Error('provider said no'), { code: 'ECONNRESET' })));
  authRouter.use(nested);
  // Lo que no coincide con ninguna ruta: un middleware que falla para cualquier camino.
  authRouter.use((req, res, next) => next(new Error(`nothing at ${req.originalUrl}`)));
  const playgroundRouter = express.Router();
  playgroundRouter.use((req, res, next) => next(new TypeError('broken')));
  const app = createApp({ authRouter, playgroundRouter, log: (line) => logs.push(line), ...options });
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { base, logs, queries, close: () => new Promise((resolve) => server.close(resolve)) };
}

describe('/api/health', () => {
  test('says only that the process answers HTTP, and is never cached', async () => {
    const s = await serve();
    try {
      const response = await fetch(`${s.base}/api/health`);
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { status: 'ok', checks: { http: 'ok' } });
      assert.equal(response.headers.get('cache-control'), 'no-store');
      assert.equal(response.headers.get('content-security-policy'), API_POLICY);
      assert.match(response.headers.get('content-type'), /^application\/json/);
      assert.deepEqual(s.queries, []);
    } finally {
      await s.close();
    }
  });

  test('reveals no version, environment, address, configuration or database detail', async () => {
    const s = await serve();
    try {
      const response = await fetch(`${s.base}/api/health`);
      const text = await response.text();
      for (const word of ['version', 'node', 'mysql', 'database', 'db', 'env', 'host', 'port', 'uptime', 'memory', 'secret', 'key', 'test']) {
        assert.ok(!text.toLowerCase().includes(`"${word}`), `the answer mentions ${word}: ${text}`);
      }
      assert.equal(response.headers.get('x-powered-by'), null);
      assert.equal(response.headers.get('server'), null);
    } finally {
      await s.close();
    }
  });

  test('answers 503 while the server shuts down', async () => {
    const lifecycle = { draining: false };
    const s = await serve({ lifecycle });
    try {
      assert.equal((await fetch(`${s.base}/api/health`)).status, 200);
      lifecycle.draining = true;
      const response = await fetch(`${s.base}/api/health`);
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { status: 'shutting_down' });
    } finally {
      await s.close();
    }
  });

  test('only GET (and HEAD): other methods are not found', async () => {
    const s = await serve();
    try {
      assert.equal((await fetch(`${s.base}/api/health`, { method: 'HEAD' })).status, 200);
      assert.equal((await fetch(`${s.base}/api/health`, { method: 'POST' })).status, 404);
    } finally {
      await s.close();
    }
  });
});

describe('errors of the application', () => {
  test('the visitor gets a generic 500, and the log only the type and a known code', async () => {
    const s = await serve();
    try {
      const response = await fetch(`${s.base}/api/auth/boom`, { method: 'POST' });
      assert.equal(response.status, 500);
      assert.deepEqual(await response.json(), { error: 'Internal server error.' });
      assert.deepEqual(s.logs, ['error: POST /api/auth/boom: Error ER_DUP_ENTRY']);
    } finally {
      await s.close();
    }
  });

  test('a code that is not an identifier (it could carry data) is left out', async () => {
    const s = await serve();
    try {
      await fetch(`${s.base}/api/auth/odd`);
      assert.deepEqual(s.logs, ['error: GET /api/auth/odd: Error']);
      assert.ok(!s.logs.join('').includes(EMAIL));
    } finally {
      await s.close();
    }
  });

  test('a nested route is logged by its template: no provider, query string or code', async () => {
    const s = await serve();
    try {
      await fetch(`${s.base}/api/auth/google/callback?code=SECRET-CODE&state=STATE-VALUE`);
      assert.deepEqual(s.logs, ['error: GET /api/auth/:provider/callback: Error ECONNRESET']);
    } finally {
      await s.close();
    }
  });

  test('the same route written in other letters is logged the same way', async () => {
    const s = await serve();
    try {
      await fetch(`${s.base}/API/Auth/boom`, { method: 'POST' });
      assert.deepEqual(s.logs, ['error: POST /api/auth/boom: Error ER_DUP_ENTRY']);
    } finally {
      await s.close();
    }
  });

  test('a request that matches no route is logged with a fixed value, never its path', async () => {
    const s = await serve();
    try {
      await fetch(`${s.base}/api/auth/${encodeURIComponent(EMAIL)}/123456?token=SECRET`);
      await fetch(`${s.base}/api/playground/users/${EMAIL}`);
      assert.deepEqual(s.logs, ['error: GET (no route): Error', 'error: GET (no route): TypeError']);
      const text = s.logs.join('\n');
      for (const value of ['ana', 'example', '123456', 'SECRET', 'users', '%40']) assert.ok(!text.includes(value), value);
    } finally {
      await s.close();
    }
  });
});
