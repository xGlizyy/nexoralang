// Inicio de sesión con Google y GitHub (src/oauth.js) con proveedores, base de datos y sesiones
// simulados: ninguna petición sale a Google ni a GitHub, y no se usa ninguna credencial real.

// oauth.js carga la configuración real, que exige variables de base de datos. Apuntan a un puerto donde
// no hay nada: estas pruebas usan una base de datos simulada y nunca deben llegar a una real.
process.env.DB_USER = 'test';
process.env.DB_NAME = 'test';
process.env.DB_HOST = '127.0.0.1';
process.env.DB_PORT = '1';

import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import express from 'express';

const { createOAuthRouter } = await import('../src/oauth.js');

const SECRET = 'test-client-secret-value';
const ACCESS_TOKEN = 'test-access-token-value';
const AUTH_CODE = 'test-authorization-code';
const EMAIL = 'ana@example.com';
const SETTINGS = {
  oauth: {
    google: { clientId: 'test-google-client', clientSecret: SECRET },
    github: { clientId: 'test-github-client', clientSecret: SECRET },
  },
  publicUrl: 'http://127.0.0.1:1',
  production: false,
};

const json = (body, status = 200) => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** Un proveedor simulado: cada URL responde lo que diga `answers` (una respuesta o una función). */
function fakeProvider(answers) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method ?? 'GET', headers: options.headers ?? {}, body: options.body ? String(options.body) : '' });
    const answer = answers[url];
    if (answer === undefined) throw new TypeError('fetch failed');
    return typeof answer === 'function' ? answer() : answer;
  };
  return { fetch, calls };
}

const GOOGLE_OK = {
  'https://oauth2.googleapis.com/token': () => json({ access_token: ACCESS_TOKEN }),
  'https://openidconnect.googleapis.com/v1/userinfo': () => json({ sub: 'google-123', name: 'Ana', email: EMAIL, email_verified: true }),
};
const GITHUB_OK = {
  'https://github.com/login/oauth/access_token': () => json({ access_token: ACCESS_TOKEN }),
  'https://api.github.com/user': () => json({ id: 777, login: 'ana', name: null }),
  'https://api.github.com/user/emails': () => json([{ email: 'old@example.com', primary: false, verified: true }, { email: EMAIL, primary: true, verified: true }]),
};

/** Una base de datos simulada que anota cada consulta y lo que pasa con la transacción. */
function fakeDb({ linked = null, existing = null, failOn = null, rollbackFails = false } = {}) {
  // ends: cuántas veces se devolvió (release) o cerró (destroy) la conexión; tiene que ser una.
  const state = { queries: [], began: false, committed: false, rolledBack: false, released: false, destroyed: false, ends: 0 };
  const execute = async (sql, params) => {
    state.queries.push({ sql, params });
    if (failOn && sql.startsWith(failOn)) {
      // Como un error de mysql2: con la consulta y el mensaje del servidor, que llevan datos personales.
      throw Object.assign(new Error(`Duplicate entry '${EMAIL}' for key 'uq_users_email'`), {
        code: 'ER_DUP_ENTRY', errno: 1062, sql: `${sql} -- ${EMAIL}`, sqlMessage: `Duplicate entry '${EMAIL}'`,
      });
    }
    if (sql.startsWith('SELECT user_id FROM oauth_accounts')) return [linked ? [{ user_id: linked }] : []];
    if (sql.startsWith('SELECT id, password_hash FROM users')) return [existing ? [existing] : []];
    if (sql.startsWith('INSERT INTO users')) return [{ insertId: 42 }];
    if (sql.startsWith('INSERT INTO oauth_accounts')) return [{ affectedRows: 1 }];
    throw new Error(`unexpected query: ${sql}`);
  };
  return {
    state,
    execute,
    inserts: () => state.queries.filter(({ sql }) => sql.startsWith('INSERT')).map(({ sql }) => sql.split(' (')[0]),
    getConnection: async () => ({
      execute,
      beginTransaction: async () => { state.began = true; },
      commit: async () => { state.committed = true; },
      rollback: async () => {
        if (rollbackFails) {
          throw Object.assign(new Error(`Rollback failed for '${EMAIL}'`), { code: 'ER_ERROR_DURING_ROLLBACK', errno: 1180, sqlMessage: `'${EMAIL}'` });
        }
        state.rolledBack = true;
      },
      release: () => { state.released = true; state.ends += 1; },
      destroy: () => { state.destroyed = true; state.ends += 1; },
    }),
  };
}

/** Sirve las rutas con estas dependencias; devuelve cómo recorrer el flujo y lo que quedó anotado. */
async function serve({ answers = GOOGLE_OK, db = fakeDb(), settings = SETTINGS, beginFails = false } = {}) {
  const provider = fakeProvider(answers);
  const sessions = [];
  const logs = [];
  const app = express();
  app.use('/api/auth', createOAuthRouter({
    settings,
    db,
    fetch: provider.fetch,
    begin: async (res, userId) => {
      if (beginFails) throw Object.assign(new Error('connect ECONNREFUSED'), { code: 'ECONNREFUSED' });
      sessions.push(userId);
      res.cookie('nexora_session', `session-${userId}`, { httpOnly: true });
    },
    log: (line) => logs.push(line),
  }));
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}/api/auth`;

  const get = (path, cookie) => fetch(`${base}${path}`, { redirect: 'manual', headers: cookie ? { Cookie: cookie } : {} });
  /** Empieza en /{name}: devuelve la redirección al proveedor, el state y la cookie que lo guarda. */
  async function start(name = 'google') {
    const response = await get(`/${name}`);
    const location = new URL(response.headers.get('location'));
    const cookie = response.headers.get('set-cookie') ?? '';
    return { response, location, state: location.searchParams.get('state'), cookie, stateCookie: cookie.split(';')[0] };
  }
  /** El flujo completo hasta /callback; `query` sustituye a lo que mandaría el proveedor. */
  async function login(name = 'google', { query, cookie } = {}) {
    const started = await start(name);
    const search = query ?? `code=${AUTH_CODE}&state=${started.state}`;
    const response = await get(`/${name}/callback?${search}`, cookie === undefined ? started.stateCookie : cookie);
    return { response, location: response.headers.get('location'), setCookie: response.headers.get('set-cookie') ?? '' };
  }
  return { server, db, provider, sessions, logs, start, login, get, close: () => new Promise((resolve) => server.close(resolve)) };
}

/** Nada de lo secreto o personal aparece en el registro. */
function assertLogsClean(logs) {
  const text = logs.join('\n');
  for (const secret of [SECRET, ACCESS_TOKEN, AUTH_CODE, EMAIL, 'Duplicate entry', 'SELECT', 'INSERT']) {
    assert.ok(!text.includes(secret), `the log contains ${secret}: ${text}`);
  }
}

describe('starting the sign-in', () => {
  let s;
  before(async () => { s = await serve(); });
  after(() => s.close());

  test('redirects to the provider with a fresh state, kept in an HttpOnly cookie for /api/auth', async () => {
    const first = await s.start('google');
    const second = await s.start('google');
    assert.equal(first.response.status, 302);
    assert.equal(first.location.origin + first.location.pathname, 'https://accounts.google.com/o/oauth2/v2/auth');
    assert.equal(first.location.searchParams.get('redirect_uri'), 'http://127.0.0.1:1/api/auth/google/callback');
    assert.equal(first.location.searchParams.get('client_id'), 'test-google-client');
    assert.ok(!first.location.href.includes(SECRET), 'the client secret never goes to the browser');
    assert.match(first.state, /^[\w-]{32}$/);
    assert.notEqual(first.state, second.state);
    assert.match(first.cookie, /^nexora_oauth_state=[\w-]{32};/);
    assert.match(first.cookie, /HttpOnly/);
    assert.match(first.cookie, /Path=\/api\/auth/);
    assert.match(first.cookie, /SameSite=Lax/);
    assert.equal(s.provider.calls.length, 0, 'nothing is asked to the provider before it answers');
  });

  test('GitHub too', async () => {
    const started = await s.start('github');
    assert.equal(started.location.origin + started.location.pathname, 'https://github.com/login/oauth/authorize');
  });
});

describe('a check that fails stops the sign-in: no provider call, no account, no session', () => {
  let s;
  before(async () => { s = await serve(); });
  after(() => s.close());

  const cases = {
    'no state cookie': { cookie: '' },
    'a state that is not the one in the cookie': { query: `code=${AUTH_CODE}&state=${'x'.repeat(32)}` },
    'a state of another length': { query: `code=${AUTH_CODE}&state=short` },
    'no state in the answer': { query: `code=${AUTH_CODE}` },
    'two states in the answer': { query: `code=${AUTH_CODE}&state=a&state=b` },
  };
  for (const [name, options] of Object.entries(cases)) {
    test(name, async () => {
      const before = s.provider.calls.length;
      const { location, setCookie } = await s.login('google', options);
      assert.equal(location, '/login?error=oauth_failed');
      assert.equal(s.provider.calls.length, before);
      assert.deepEqual(s.sessions, []);
      assert.deepEqual(s.db.state.queries, []);
      // La cookie del state se borra en cualquier caso: sirve para un solo intento.
      assert.match(setCookie, /nexora_oauth_state=;/);
    });
  }

  test('cancelled on the provider (no code): oauth_cancelled, and nothing is asked', async () => {
    const started = await s.start('google');
    const response = await s.get(`/google/callback?state=${started.state}&error=access_denied`, started.stateCookie);
    assert.equal(response.headers.get('location'), '/login?error=oauth_cancelled');
    assert.deepEqual(s.sessions, []);
    assert.deepEqual(s.db.state.queries, []);
  });

  test('a state cookie is good for one attempt only', async () => {
    const started = await s.start('google');
    await s.get(`/google/callback?state=${started.state}`, started.stateCookie); // cancelado: la cookie se borra
    const replay = await s.get(`/google/callback?code=${AUTH_CODE}&state=${started.state}`);
    assert.equal(replay.headers.get('location'), '/login?error=oauth_failed');
  });
});

describe('a provider that is not configured', () => {
  test('is unavailable at the start and at the callback', async () => {
    const s = await serve({ settings: { ...SETTINGS, oauth: { google: null, github: null } } });
    try {
      for (const path of ['/google', '/github', `/google/callback?code=${AUTH_CODE}&state=x`]) {
        const response = await s.get(path);
        assert.equal(response.headers.get('location'), '/login?error=oauth_unavailable', path);
      }
      assert.equal(s.provider.calls.length, 0);
      assert.deepEqual(s.sessions, []);
    } finally {
      await s.close();
    }
  });
});

describe('a successful sign-in', () => {
  test('Google, first time: creates the account and the link in one transaction, and starts the session', async () => {
    const s = await serve();
    try {
      const { location } = await s.login('google');
      assert.equal(location, '/');
      assert.deepEqual(s.sessions, [42]);
      assert.deepEqual(s.db.inserts(), ['INSERT INTO users', 'INSERT INTO oauth_accounts']);
      assert.deepEqual([s.db.state.began, s.db.state.committed, s.db.state.rolledBack, s.db.state.released], [true, true, false, true]);
      // El código se cambia por un token solo en el endpoint del proveedor, y el token solo viaja a él.
      const [token, profile] = s.provider.calls;
      assert.equal(token.url, 'https://oauth2.googleapis.com/token');
      assert.equal(token.method, 'POST');
      assert.match(token.body, new RegExp(`code=${AUTH_CODE}`));
      assert.match(token.body, /redirect_uri=http%3A%2F%2F127\.0\.0\.1%3A1%2Fapi%2Fauth%2Fgoogle%2Fcallback/);
      assert.equal(profile.headers.Authorization, `Bearer ${ACCESS_TOKEN}`);
      // El email se guarda en minúsculas y el nombre del proveedor, recortado.
      const user = s.db.state.queries.find(({ sql }) => sql.startsWith('INSERT INTO users'));
      assert.deepEqual(user.params, ['Ana', EMAIL]);
    } finally {
      await s.close();
    }
  });

  test('GitHub, an identity already linked: the session of that user, with no transaction', async () => {
    const s = await serve({ answers: GITHUB_OK, db: fakeDb({ linked: 7 }) });
    try {
      const { location } = await s.login('github');
      assert.equal(location, '/');
      assert.deepEqual(s.sessions, [7]);
      assert.deepEqual(s.db.inserts(), []);
      assert.equal(s.db.state.began, false);
      assert.deepEqual(s.db.state.queries[0].params, ['github', '777']);
    } finally {
      await s.close();
    }
  });

  test('an account without a password (from the other provider) is linked, not duplicated', async () => {
    const s = await serve({ answers: GITHUB_OK, db: fakeDb({ existing: { id: 9, password_hash: null } }) });
    try {
      const { location } = await s.login('github');
      assert.equal(location, '/');
      assert.deepEqual(s.sessions, [9]);
      assert.deepEqual(s.db.inserts(), ['INSERT INTO oauth_accounts']);
    } finally {
      await s.close();
    }
  });
});

describe('the account is never created or linked without a verified email', () => {
  const unverified = {
    'Google says email_verified: false': { ...GOOGLE_OK, 'https://openidconnect.googleapis.com/v1/userinfo': () => json({ sub: 'g-1', name: 'Ana', email: EMAIL, email_verified: false }) },
    'Google says email_verified: "true" (a text, not a boolean)': { ...GOOGLE_OK, 'https://openidconnect.googleapis.com/v1/userinfo': () => json({ sub: 'g-1', email: EMAIL, email_verified: 'true' }) },
    'Google sends no email': { ...GOOGLE_OK, 'https://openidconnect.googleapis.com/v1/userinfo': () => json({ sub: 'g-1', email_verified: true }) },
    'GitHub has no verified primary email': { ...GITHUB_OK, 'https://api.github.com/user/emails': () => json([{ email: EMAIL, primary: true, verified: false }, { email: 'b@example.com', primary: false, verified: true }]) },
    'GitHub has no email at all': { ...GITHUB_OK, 'https://api.github.com/user/emails': () => json([]) },
  };
  for (const [name, answers] of Object.entries(unverified)) {
    test(name, async () => {
      const s = await serve({ answers });
      try {
        const provider = name.startsWith('GitHub') ? 'github' : 'google';
        const { location } = await s.login(provider);
        assert.equal(location, '/login?error=email_unverified');
        assert.deepEqual(s.sessions, []);
        assert.deepEqual(s.db.inserts(), []);
        assert.equal(s.db.state.began, false);
      } finally {
        await s.close();
      }
    });
  }

  test('an account with a password is never linked by email: account_exists, rolled back', async () => {
    const s = await serve({ db: fakeDb({ existing: { id: 5, password_hash: 'scrypt$...' } }) });
    try {
      const { location } = await s.login('google');
      assert.equal(location, '/login?error=account_exists');
      assert.deepEqual(s.sessions, []);
      assert.deepEqual(s.db.inserts(), []);
      assert.deepEqual([s.db.state.committed, s.db.state.rolledBack, s.db.state.released], [false, true, true]);
    } finally {
      await s.close();
    }
  });

  test('account_exists whose rollback fails: still account_exists, the connection destroyed, one line without data', async () => {
    const s = await serve({ db: fakeDb({ existing: { id: 5, password_hash: 'scrypt$...' }, rollbackFails: true }) });
    try {
      const { location, setCookie } = await s.login('google');
      assert.equal(location, '/login?error=account_exists');
      assert.deepEqual(s.sessions, []);
      assert.doesNotMatch(setCookie, /nexora_session=/);
      assert.deepEqual([s.db.state.released, s.db.state.destroyed, s.db.state.ends], [false, true, 1]);
      assert.deepEqual(s.logs, ['oauth: google: rollback failed (Error ER_ERROR_DURING_ROLLBACK)']);
      assertLogsClean(s.logs);
    } finally {
      await s.close();
    }
  });
});

describe('a failing provider or database: oauth_failed, nothing created, and a log line without data', () => {
  const token = 'https://oauth2.googleapis.com/token';
  const userinfo = 'https://openidconnect.googleapis.com/v1/userinfo';
  const cases = {
    'the token endpoint answers 500': [{ ...GOOGLE_OK, [token]: () => json({ error: 'server_error' }, 500) }, /ProviderError token_http_500/],
    'the token endpoint answers 200 without a token (as GitHub does)': [{ ...GOOGLE_OK, [token]: () => json({ error: 'bad_verification_code' }) }, /ProviderError token_missing/],
    'the token endpoint answers something that is not JSON': [{ ...GOOGLE_OK, [token]: () => json('<html>oops</html>') }, /ProviderError token_bad_json/],
    'the provider cannot be reached': [{ ...GOOGLE_OK, [token]: undefined }, /TypeError/],
    'the provider takes too long': [{ ...GOOGLE_OK, [token]: () => { throw Object.assign(new Error('The operation was aborted due to timeout'), { name: 'TimeoutError', code: 23 }); } }, /TimeoutError 23/],
    'the profile answers 401': [{ ...GOOGLE_OK, [userinfo]: () => json({ error: 'invalid_token' }, 401) }, /ProviderError profile_http_401/],
    'the profile is not JSON': [{ ...GOOGLE_OK, [userinfo]: () => json('nope') }, /ProviderError profile_bad_json/],
    'the profile has no id': [{ ...GOOGLE_OK, [userinfo]: () => json({ email: EMAIL, email_verified: true }) }, /ProviderError profile_unexpected/],
    'the profile is not an object': [{ ...GOOGLE_OK, [userinfo]: () => json('null') }, /ProviderError profile_unexpected/],
  };
  for (const [name, [answers, logged]] of Object.entries(cases)) {
    test(name, async () => {
      const s = await serve({ answers });
      try {
        const { location } = await s.login('google');
        assert.equal(location, '/login?error=oauth_failed');
        assert.deepEqual(s.sessions, []);
        assert.deepEqual(s.db.inserts(), []);
        assert.equal(s.logs.length, 1);
        assert.match(s.logs[0], /^oauth: google: sign-in failed \(/);
        assert.match(s.logs[0], logged);
        assertLogsClean(s.logs);
      } finally {
        await s.close();
      }
    });
  }

  test('GitHub profile with a malformed list of emails', async () => {
    const s = await serve({ answers: { ...GITHUB_OK, 'https://api.github.com/user/emails': () => json({ message: 'Bad credentials' }) } });
    try {
      assert.equal((await s.login('github')).location, '/login?error=oauth_failed');
      assert.deepEqual(s.sessions, []);
      assert.match(s.logs[0], /ProviderError profile_unexpected/);
    } finally {
      await s.close();
    }
  });

  test('the database fails inside the transaction: rolled back, released, no session', async () => {
    const s = await serve({ db: fakeDb({ failOn: 'INSERT INTO oauth_accounts' }) });
    try {
      assert.equal((await s.login('google')).location, '/login?error=oauth_failed');
      assert.deepEqual(s.sessions, []);
      assert.deepEqual([s.db.state.committed, s.db.state.rolledBack, s.db.state.released], [false, true, true]);
      assert.deepEqual([s.db.state.destroyed, s.db.state.ends], [false, 1], 'released once, not destroyed');
      assert.deepEqual(s.logs, ['oauth: google: sign-in failed (Error ER_DUP_ENTRY)']);
      assertLogsClean(s.logs);
    } finally {
      await s.close();
    }
  });

  test('the database fails inside the transaction and then the rollback fails: the original error, the connection destroyed', async () => {
    const s = await serve({ db: fakeDb({ failOn: 'INSERT INTO oauth_accounts', rollbackFails: true }) });
    try {
      const { location, setCookie } = await s.login('google');
      assert.equal(location, '/login?error=oauth_failed');
      assert.deepEqual(s.sessions, []);
      assert.doesNotMatch(setCookie, /nexora_session=/);
      // No vuelve al pool (podría tener la transacción abierta), y se cierra una sola vez.
      assert.deepEqual([s.db.state.committed, s.db.state.released, s.db.state.destroyed, s.db.state.ends], [false, false, true, 1]);
      // El fallo del rollback queda anotado aparte; el que llega al usuario y al registro es el original.
      assert.deepEqual(s.logs, [
        'oauth: google: rollback failed (Error ER_ERROR_DURING_ROLLBACK)',
        'oauth: google: sign-in failed (Error ER_DUP_ENTRY)',
      ]);
      assertLogsClean(s.logs);
    } finally {
      await s.close();
    }
  });

  test('the database fails before the transaction', async () => {
    const s = await serve({ db: fakeDb({ failOn: 'SELECT user_id' }) });
    try {
      assert.equal((await s.login('google')).location, '/login?error=oauth_failed');
      assert.deepEqual(s.sessions, []);
      assert.equal(s.db.state.began, false);
      assertLogsClean(s.logs);
    } finally {
      await s.close();
    }
  });

  test('the session cannot be started: no session cookie and oauth_failed', async () => {
    const s = await serve({ beginFails: true });
    try {
      const { location, setCookie } = await s.login('google');
      assert.equal(location, '/login?error=oauth_failed');
      assert.doesNotMatch(setCookie, /nexora_session=/);
      assert.deepEqual(s.logs, ['oauth: google: sign-in failed (Error ECONNREFUSED)']);
    } finally {
      await s.close();
    }
  });
});
