// Rutas de cuentas (src/auth.js) con una base de datos, unas sesiones y unas contraseñas simuladas:
// comprueban el contrato de la API, los límites y el freno del login, no un MySQL real.

// auth.js carga la configuración real, que exige variables de base de datos. Apuntan a un puerto donde
// no hay nada: estas pruebas usan una base de datos simulada y nunca deben llegar a una real.
process.env.DB_USER = 'test';
process.env.DB_NAME = 'test';
process.env.DB_HOST = '127.0.0.1';
process.env.DB_PORT = '1';

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import express from 'express';

const { createAuthRouter } = await import('../src/auth.js');
const { loadCaptchaConfig } = await import('../src/captcha.js');
const { ACCOUNT_FREE, PAIR_FREE, createLoginThrottle } = await import('../src/login-throttle.js');

function fakeDb() {
  const users = new Map();
  const queries = [];
  let nextId = 1;
  return {
    queries,
    async execute(sql, params) {
      queries.push(sql);
      if (sql.startsWith('INSERT INTO users')) {
        const [name, email, passwordHash] = params;
        if ([...users.values()].some((user) => user.email === email)) throw Object.assign(new Error('duplicate'), { code: 'ER_DUP_ENTRY' });
        const id = nextId++;
        users.set(id, { id, name, email, password_hash: passwordHash });
        return [{ insertId: id }];
      }
      if (sql.startsWith('SELECT id, name, email, password_hash FROM users WHERE email = ?')) {
        return [[...users.values()].filter((user) => user.email === params[0])];
      }
      throw new Error(`unexpected SQL: ${sql}`);
    },
  };
}

async function start({ attemptsLimit = 1000, now } = {}) {
  let time = 1_000_000;
  const clock = now ?? (() => time);
  const db = fakeDb();
  const app = express();
  app.set('trust proxy', 1);
  app.use('/api/auth', createAuthRouter({
    db,
    sessions: {
      startSession: async (res, id) => { res.cookie('nexora_session', `session-${id}`, { httpOnly: true }); },
      endSession: async (req, res) => { res.clearCookie('nexora_session'); },
      currentUser: async () => null,
    },
    passwords: { hashPassword: async (password) => `hash:${password}`, verifyPassword: async (password, hash) => hash === `hash:${password}` },
    captcha: loadCaptchaConfig({}),
    throttle: createLoginThrottle({ now: clock }),
    attemptsLimit,
    providers: null,
  }));
  app.use((error, req, res, next) => {
    if (error.type === 'entity.parse.failed') return res.status(400).json({ error: 'Invalid request.' });
    res.status(500).json({ error: 'Internal server error.' });
  });
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const post = async (route, body, from = '198.51.100.1') => {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/auth${route}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Forwarded-For': from }, body: JSON.stringify(body),
    });
    return { status: response.status, json: await response.json().catch(() => ({})), retryAfter: response.headers.get('retry-after') };
  };
  return { post, db, advance: (ms) => { time += ms; }, close: () => new Promise((resolve) => server.close(resolve)) };
}

const ADA = { name: 'Ada', email: 'ada@example.com', password: 'correct horse battery' };
const login = (password, email = ADA.email) => ({ email, password });

describe('sign-up', () => {
  test('creates the account and starts a session (contract unchanged)', async () => {
    const s = await start();
    try {
      const { status, json } = await s.post('/signup', ADA);
      assert.equal(status, 201);
      assert.deepEqual(json, { user: { id: 1, name: 'Ada', email: 'ada@example.com' } });
    } finally { await s.close(); }
  });

  test('an email that already has an account still answers 409: hiding it needs email confirmation (pending decision)', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      assert.deepEqual(await s.post('/signup', { ...ADA, name: 'Other' }), {
        status: 409, json: { error: 'An account with that email already exists.' }, retryAfter: null,
      });
    } finally { await s.close(); }
  });

  test('invalid input is refused before touching the database', async () => {
    const s = await start();
    try {
      assert.equal((await s.post('/signup', { ...ADA, email: 'not-an-email' })).status, 400);
      assert.equal((await s.post('/signup', { ...ADA, password: 'short' })).status, 400);
      assert.equal((await s.post('/signup', { ...ADA, website: 'http://spam.example' })).status, 400, 'honeypot');
      assert.deepEqual(s.db.queries, []);
    } finally { await s.close(); }
  });
});

describe('log-in', () => {
  test('a wrong password and an unknown email look exactly the same', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      const wrong = await s.post('/login', login('wrong password!'));
      const unknown = await s.post('/login', login('wrong password!', 'nobody@example.com'));
      assert.deepEqual(wrong, unknown);
      assert.deepEqual(wrong, { status: 401, json: { error: 'Incorrect email or password.' }, retryAfter: null });
    } finally { await s.close(); }
  });

  test('after PAIR_FREE failures from one client, that client waits, without a database query', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      for (let i = 0; i < PAIR_FREE; i += 1) assert.equal((await s.post('/login', login('wrong password!'))).status, 401);
      const queries = s.db.queries.length;
      const throttled = await s.post('/login', login(ADA.password));
      assert.equal(throttled.status, 429, 'even the right password waits');
      assert.equal(throttled.json.code, 'login_throttled');
      assert.equal(throttled.retryAfter, '1');
      assert.equal(s.db.queries.length, queries, 'the database was not asked');
      s.advance(1000);
      assert.equal((await s.post('/login', login(ADA.password))).status, 200, 'after waiting, the right password works');
      assert.equal((await s.post('/login', login('wrong password!'))).status, 401, 'and the count started again');
    } finally { await s.close(); }
  });

  test('another client is not made to wait by someone else failing on the same account', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      for (let i = 0; i < PAIR_FREE + 3; i += 1) await s.post('/login', login('wrong password!'), '203.0.113.66');
      assert.equal((await s.post('/login', login(ADA.password), '198.51.100.7')).status, 200);
    } finally { await s.close(); }
  });

  test('an attack spread over many clients makes the account wait at most a minute', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      for (let i = 0; i < ACCOUNT_FREE; i += 1) await s.post('/login', login('wrong password!'), `203.0.113.${i + 1}`);
      const throttled = await s.post('/login', login(ADA.password), '198.51.100.7');
      assert.equal(throttled.status, 429);
      assert.ok(Number(throttled.retryAfter) <= 60, `Retry-After ${throttled.retryAfter}`);
      s.advance(60_000);
      assert.equal((await s.post('/login', login(ADA.password), '198.51.100.7')).status, 200);
    } finally { await s.close(); }
  });

  test('the throttle behaves the same for an email without an account: it reveals nothing', async () => {
    const s = await start();
    try {
      await s.post('/signup', ADA);
      const run = async (email, from) => {
        const statuses = [];
        for (let i = 0; i <= PAIR_FREE; i += 1) {
          const { status, retryAfter } = await s.post('/login', login('wrong password!', email), from);
          statuses.push(`${status}/${retryAfter}`);
        }
        return statuses;
      };
      assert.deepEqual(await run(ADA.email, '198.51.100.1'), await run('nobody@example.com', '198.51.100.2'));
    } finally { await s.close(); }
  });
});

/**
 * Un servidor cuya base de datos retiene cada consulta hasta que la prueba abre la compuerta: así
 * las peticiones están de verdad en vuelo a la vez, sin pausas ni temporizadores. `failWith` hace que
 * las consultas fallen (un error interno, no una contraseña incorrecta).
 */
async function gated({ failWith } = {}) {
  let open;
  const gate = new Promise((resolve) => { open = resolve; });
  let waiting = 0;
  let queries = 0;
  const users = [{ id: 1, name: 'Ada', email: ADA.email, password_hash: `hash:${ADA.password}` }];
  const db = {
    async execute(sql, params) {
      queries += 1;
      waiting += 1;
      await gate;
      if (failWith) throw failWith;
      return [users.filter((user) => user.email === params[0])];
    },
  };
  // The throttle, counting how many requests have already gone through begin().
  let begun = 0;
  const throttle = createLoginThrottle({ now: () => 1_000_000 });
  const counted = { ...throttle, begin: (...args) => { begun += 1; return throttle.begin(...args); } };
  const app = express();
  app.set('trust proxy', 1);
  app.use('/api/auth', createAuthRouter({
    db,
    sessions: { startSession: async () => {}, endSession: async () => {}, currentUser: async () => null },
    passwords: { hashPassword: async (p) => `hash:${p}`, verifyPassword: async (p, h) => h === `hash:${p}` },
    captcha: loadCaptchaConfig({}),
    throttle: counted,
    attemptsLimit: 1000,
    providers: null,
  }));
  app.use((error, req, res, next) => res.status(500).json({ error: 'Internal server error.' }));
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const send = (password, from, email = ADA.email) => fetch(`http://127.0.0.1:${server.address().port}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Forwarded-For': from }, body: JSON.stringify({ email, password }),
  }).then((response) => response.status);
  return {
    send,
    open: () => open(),
    get waiting() { return waiting; },
    get queries() { return queries; },
    get begun() { return begun; },
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

/**
 * Lanza las peticiones y abre la compuerta solo cuando TODAS han pasado por el freno y las que entran
 * están en la base de datos: entonces el resultado no depende del orden en que el sistema operativo
 * entregue las conexiones. (Abrir antes hacía que el resultado dependiera de ese orden: en Linux, las
 * últimas llegaban al freno cuando las primeras ya habían terminado.)
 */
async function burst(s, requests, expectedInFlight) {
  const pending = requests.map(([password, from, email]) => s.send(password, from, email));
  while (s.begun < requests.length || s.waiting < expectedInFlight) await new Promise((resolve) => setImmediate(resolve));
  assert.equal(s.waiting, expectedInFlight, 'exactly the expected attempts reached the database');
  s.open();
  const statuses = await Promise.all(pending);
  return statuses.reduce((acc, status) => ({ ...acc, [status]: (acc[status] ?? 0) + 1 }), {});
}

describe('concurrent log-ins (D1)', () => {
  test('many wrong passwords at once from one client: only PAIR_FREE reach the database', async () => {
    const s = await gated();
    try {
      const tally = await burst(s, Array.from({ length: 12 }, () => ['wrong password!', '198.51.100.9']), PAIR_FREE);
      // Regression: all 12 used to get through (401) before any failure was counted.
      assert.deepEqual(tally, { 401: PAIR_FREE, 429: 12 - PAIR_FREE });
      assert.equal(s.queries, PAIR_FREE);
    } finally { await s.close(); }
  });

  test('many wrong passwords at once against one account from different clients: only ACCOUNT_FREE get through', async () => {
    const s = await gated();
    try {
      const tally = await burst(s, Array.from({ length: 60 }, (_, i) => ['wrong password!', `203.0.113.${i + 1}`]), ACCOUNT_FREE);
      assert.deepEqual(tally, { 401: ACCOUNT_FREE, 429: 60 - ACCOUNT_FREE });
    } finally { await s.close(); }
  });

  test('the right password in flight together with wrong ones logs in', async () => {
    const s = await gated();
    try {
      const requests = [
        ...Array.from({ length: PAIR_FREE - 1 }, () => ['wrong password!', '198.51.100.9']),
        [ADA.password, '198.51.100.9'],
      ];
      assert.deepEqual(await burst(s, requests, PAIR_FREE), { 200: 1, 401: PAIR_FREE - 1 });
    } finally { await s.close(); }
  });

  test('database errors are not counted as wrong passwords', async () => {
    const s = await gated({ failWith: Object.assign(new Error('connection lost'), { code: 'PROTOCOL_CONNECTION_LOST' }) });
    try {
      const tally = await burst(s, Array.from({ length: PAIR_FREE + 3 }, () => ['wrong password!', '198.51.100.9']), PAIR_FREE);
      assert.deepEqual(tally, { 500: PAIR_FREE, 429: 3 }, 'while in flight they are reserved…');
      const next = await Promise.all(Array.from({ length: PAIR_FREE }, () => s.send('wrong password!', '198.51.100.9')));
      assert.deepEqual(next, Array(PAIR_FREE).fill(500), '…but once they ended in an error, none of them counted');
    } finally { await s.close(); }
  });

  test('an email with an account and one without behave alike under a burst', async () => {
    const results = [];
    for (const email of [ADA.email, 'nobody@example.com']) {
      const s = await gated();
      try {
        results.push(await burst(s, Array.from({ length: 9 }, () => ['wrong password!', '198.51.100.9', email]), PAIR_FREE));
      } finally { await s.close(); }
    }
    assert.deepEqual(results[0], results[1]);
  });
});

describe('the per-client limit of the account routes', () => {
  test('counts an IPv4 address and its IPv6-mapped form as one client, and spreads over /48 as documented', async () => {
    const s = await start({ attemptsLimit: 2 });
    try {
      const body = login('wrong password!');
      assert.equal((await s.post('/login', body, '198.51.100.9')).status, 401);
      assert.equal((await s.post('/login', body, '::ffff:198.51.100.9')).status, 401);
      assert.equal((await s.post('/login', body, '198.51.100.9')).status, 429, 'the same client');
      assert.equal((await s.post('/login', body, '198.51.100.10')).status, 401, 'another client');
    } finally { await s.close(); }
  });
});
