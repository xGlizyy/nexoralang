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

/**
 * Una base de datos simulada con transacciones: lo que se inserta con una conexión de getConnection()
 * solo se ve en `users` y `sessions` después de commit(); rollback() lo descarta. `fail` hace fallar
 * las sentencias que empiecen así (y 'COMMIT' o 'ROLLBACK' esas órdenes), como fallaría MySQL; cada
 * fallo lleva su propio código, para saber cuál llega al manejador de errores. Vaciar `failures` hace
 * que la misma base vuelva a funcionar.
 */
function fakeDb({ fail = [] } = {}) {
  const users = new Map();
  const sessions = [];
  const queries = [];
  const transactions = [];
  let nextId = 1;
  const failures = [fail].flat().filter(Boolean);
  const CODES = { COMMIT: 'ER_ERROR_DURING_COMMIT', ROLLBACK: 'ER_ERROR_DURING_ROLLBACK' };
  // Como los de mysql2, los errores llevan en el mensaje los datos de la última sentencia (nombre,
  // email, hash): lo que nunca debe llegar al registro.
  let lastParams = [];
  const failIf = (what) => {
    const match = failures.find((prefix) => what.startsWith(prefix));
    if (match) {
      throw Object.assign(new Error(`simulated failure after ${JSON.stringify(lastParams)}`), { code: CODES[match] ?? 'ER_LOCK_WAIT_TIMEOUT' });
    }
  };
  function run(sql, params, staged) {
    queries.push(sql);
    lastParams = params ?? [];
    failIf(sql);
    if (sql.startsWith('INSERT INTO users')) {
      const [name, email, passwordHash] = params;
      const all = [...users.values(), ...(staged?.users ?? [])];
      if (all.some((user) => user.email === email)) throw Object.assign(new Error('duplicate'), { code: 'ER_DUP_ENTRY' });
      const user = { id: nextId++, name, email, password_hash: passwordHash };
      if (staged) staged.users.push(user);
      else users.set(user.id, user);
      return [{ insertId: user.id }];
    }
    if (sql.startsWith('INSERT INTO sessions')) {
      const session = { tokenHash: params[0], userId: params[1] };
      if (staged) staged.sessions.push(session);
      else sessions.push(session);
      return [{ affectedRows: 1 }];
    }
    if (sql.startsWith('SELECT id, name, email, password_hash FROM users WHERE email = ?')) {
      return [[...users.values()].filter((user) => user.email === params[0])];
    }
    throw new Error(`unexpected SQL: ${sql}`);
  }
  return {
    users,
    sessions,
    queries,
    transactions,
    failures,
    async execute(sql, params) {
      return run(sql, params, null);
    },
    async getConnection() {
      const staged = { users: [], sessions: [] };
      const record = { began: false, committed: false, rolledBack: false, released: false };
      transactions.push(record);
      return {
        async beginTransaction() { record.began = true; },
        async execute(sql, params) { return run(sql, params, staged); },
        async commit() {
          failIf('COMMIT');
          for (const user of staged.users) users.set(user.id, user);
          sessions.push(...staged.sessions);
          record.committed = true;
        },
        async rollback() {
          failIf('ROLLBACK');
          record.rolledBack = true;
        },
        release() { record.released = true; },
        destroy() { record.destroyed = true; },
      };
    },
  };
}

/** Sesiones simuladas que guardan con la base de datos que se les dé, como src/sessions.js. */
const fakeSessions = {
  createSession: async (db, id) => {
    await db.execute('INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)', [`hash-${id}`, id, 30]);
    return `session-${id}`;
  },
  setSessionCookie: (res, token) => { res.cookie('nexora_session', token, { httpOnly: true }); },
  startSession: async (res, id) => { res.cookie('nexora_session', `session-${id}`, { httpOnly: true }); },
  endSession: async (req, res) => { res.clearCookie('nexora_session'); },
  currentUser: async () => null,
};

async function start({ attemptsLimit = 1000, now, fail } = {}) {
  let time = 1_000_000;
  const clock = now ?? (() => time);
  const db = fakeDb({ fail });
  const logs = [];
  const app = express();
  app.set('trust proxy', 1);
  app.use('/api/auth', createAuthRouter({
    db,
    sessions: fakeSessions,
    passwords: { hashPassword: async (password) => `hash:${password}`, verifyPassword: async (password, hash) => hash === `hash:${password}` },
    captcha: loadCaptchaConfig({}),
    throttle: createLoginThrottle({ now: clock }),
    attemptsLimit,
    providers: null,
    log: (line) => logs.push(line),
  }));
  // Los errores que llegan al manejador final: para comprobar cuál es (el original, no el del rollback).
  const errors = [];
  app.use((error, req, res, next) => {
    if (error.type === 'entity.parse.failed') return res.status(400).json({ error: 'Invalid request.' });
    errors.push(error.code);
    res.status(500).json({ error: 'Internal server error.' });
  });
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const post = async (route, body, from = '198.51.100.1') => {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/auth${route}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Forwarded-For': from }, body: JSON.stringify(body),
    });
    return { status: response.status, json: await response.json().catch(() => ({})), retryAfter: response.headers.get('retry-after'), setCookie: response.headers.get('set-cookie') };
  };
  return { post, db, errors, logs, advance: (ms) => { time += ms; }, close: () => new Promise((resolve) => server.close(resolve)) };
}

const ADA = { name: 'Ada', email: 'ada@example.com', password: 'correct horse battery' };
const login = (password, email = ADA.email) => ({ email, password });

/** El registro de un rollback fallido: una línea con tipo y código, sin nada de la petición. */
const ROLLBACK_LOG = 'auth: sign-up rollback failed (Error ER_ERROR_DURING_ROLLBACK)';
function assertLogsClean(logs) {
  const text = logs.join('\n');
  for (const secret of [ADA.email, ADA.password, ADA.name, 'hash:', 'session-', 'nexora_session', 'simulated failure']) {
    assert.ok(!text.includes(secret), `the log contains ${secret}: ${text}`);
  }
}

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
        status: 409, json: { error: 'An account with that email already exists.' }, retryAfter: null, setCookie: null,
      });
      assert.equal(s.db.users.size, 1);
      assert.equal(s.db.sessions.length, 1);
      const refused = s.db.transactions.at(-1);
      assert.deepEqual([refused.committed, refused.rolledBack, refused.released], [false, true, true]);
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

describe('sign-up is atomic: the account and its first session, or neither', () => {
  test('success: both rows in one committed transaction, and the cookie only then', async () => {
    const s = await start();
    try {
      const { status, setCookie } = await s.post('/signup', ADA);
      assert.equal(status, 201);
      assert.match(setCookie, /^nexora_session=session-1;/);
      assert.equal(s.db.users.size, 1);
      assert.deepEqual(s.db.sessions, [{ tokenHash: 'hash-1', userId: 1 }]);
      assert.deepEqual(s.db.transactions, [{ began: true, committed: true, rolledBack: false, released: true }]);
    } finally { await s.close(); }
  });

  for (const [where, fail] of [['storing the session', 'INSERT INTO sessions'], ['the commit', 'COMMIT']]) {
    test(`a failure in ${where} leaves no account, no session and no cookie`, async () => {
      const s = await start({ fail });
      try {
        const { status, setCookie } = await s.post('/signup', ADA);
        assert.equal(status, 500);
        assert.equal(setCookie, null);
        assert.equal(s.db.users.size, 0, 'no account was left behind');
        assert.equal(s.db.sessions.length, 0);
        assert.deepEqual(s.db.transactions, [{ began: true, committed: false, rolledBack: true, released: true }]);
        assert.deepEqual(s.errors, [fail === 'COMMIT' ? 'ER_ERROR_DURING_COMMIT' : 'ER_LOCK_WAIT_TIMEOUT'], 'the original error');
        assert.deepEqual(s.logs, [], 'a rollback that works leaves no log line of its own');
      } finally { await s.close(); }
    });
  }

  // Si también falla el rollback: el error que cuenta es el original, la respuesta no lleva cookie y la
  // conexión no vuelve al pool (podría haber quedado con la transacción abierta): se destruye.
  for (const [where, first, expected] of [
    ['storing the session', 'INSERT INTO sessions', 'ER_LOCK_WAIT_TIMEOUT'],
    ['the commit', 'COMMIT', 'ER_ERROR_DURING_COMMIT'],
  ]) {
    test(`a failure in ${where} and then in the rollback: the original error, no cookie, the connection destroyed`, async () => {
      const s = await start({ fail: [first, 'ROLLBACK'] });
      try {
        const { status, setCookie } = await s.post('/signup', ADA);
        assert.equal(status, 500);
        assert.equal(setCookie, null);
        assert.deepEqual(s.errors, [expected], 'the error of the rollback does not replace the original one');
        assert.deepEqual(s.logs, [ROLLBACK_LOG], 'the failed rollback is recorded, once, beside the original error');
        assertLogsClean(s.logs);
        assert.equal(s.db.users.size, 0);
        assert.deepEqual(s.db.transactions, [{ began: true, committed: false, rolledBack: false, released: false, destroyed: true }]);
      } finally { await s.close(); }
    });
  }

  test('a duplicated email whose rollback fails still answers 409, and the connection is destroyed', async () => {
    const s = await start({ fail: 'ROLLBACK' });
    try {
      assert.equal((await s.post('/signup', ADA)).status, 201);
      const { status, json, setCookie } = await s.post('/signup', { ...ADA, name: 'Other' });
      assert.equal(status, 409);
      assert.deepEqual(json, { error: 'An account with that email already exists.' });
      assert.equal(setCookie, null);
      assert.deepEqual(s.errors, []);
      assert.deepEqual(s.logs, [ROLLBACK_LOG], 'recorded, and the answer is still the 409');
      assertLogsClean(s.logs);
      assert.deepEqual(s.db.transactions.at(-1), { began: true, committed: false, rolledBack: false, released: false, destroyed: true });
    } finally { await s.close(); }
  });

  test('after a failed sign-up, the same email can sign up again (nothing was half created)', async () => {
    // La misma base de datos: si el primer intento hubiera dejado la cuenta, el segundo daría 409.
    const s = await start({ fail: 'INSERT INTO sessions' });
    try {
      assert.equal((await s.post('/signup', ADA)).status, 500);
      assert.equal(s.db.users.size, 0);
      s.db.failures.length = 0; // la base de datos vuelve a funcionar
      assert.equal((await s.post('/signup', ADA)).status, 201);
      assert.equal(s.db.users.size, 1);
      assert.equal(s.db.sessions.length, 1);
    } finally { await s.close(); }
  });

  test('the password hash is computed before the transaction: no connection is held during scrypt', async () => {
    const order = [];
    const db = fakeDb();
    const getConnection = db.getConnection.bind(db);
    db.getConnection = async () => { order.push('connection'); return getConnection(); };
    const app = express();
    app.use('/api/auth', createAuthRouter({
      db,
      sessions: fakeSessions,
      passwords: { hashPassword: async (password) => { order.push('hash'); return `hash:${password}`; }, verifyPassword: async () => false },
      captcha: loadCaptchaConfig({}),
      attemptsLimit: 1000,
      providers: null,
    }));
    const server = await new Promise((resolve) => { const sv = app.listen(0, '127.0.0.1', () => resolve(sv)); });
    try {
      const response = await fetch(`http://127.0.0.1:${server.address().port}/api/auth/signup`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ADA),
      });
      assert.equal(response.status, 201);
      assert.deepEqual(order, ['hash', 'connection']);
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
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
      assert.deepEqual(wrong, { status: 401, json: { error: 'Incorrect email or password.' }, retryAfter: null, setCookie: null });
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
