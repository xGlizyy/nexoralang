// Antispam de los formularios de cuenta (src/captcha.js). Google se simula: ninguna prueba sale a la red.

import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import express from 'express';
import { POLICY, antispam, captchaKeyWarnings, loadCaptchaConfig, readSiteKey, readSiteKeyFile, strictLimiter, throttledLog, verifyCaptcha } from '../src/captcha.js';
import { clientRateLimit } from '../src/rate-limits.js';

const NOW = Date.parse('2026-10-16T12:00:00Z');
const TOKEN = 'A'.repeat(40);
const config = { secret: 'test-secret', minScore: 0.5, hostnames: ['nexora.test'] };

/** Respuesta de siteverify como la da Google, con los cambios de cada prueba. */
function google(overrides = {}, { status = 200 } = {}) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, body: String(options.body) });
    return new Response(JSON.stringify({
      success: true,
      score: 0.9,
      action: 'signup',
      hostname: 'nexora.test',
      challenge_ts: new Date(NOW - 10_000).toISOString(),
      ...overrides,
    }), { status });
  };
  return { fetch, calls };
}

const check = (token, fake, action = 'signup', cfg = config) => verifyCaptcha(token, action, cfg, { fetch: fake.fetch, now: () => NOW });

describe('reCAPTCHA v3 verification', () => {
  test('a valid token for the expected action, host and a good score is verified', async () => {
    const fake = google();
    assert.deepEqual(await check(TOKEN, fake), { outcome: 'verified', score: 0.9 });
    assert.equal(fake.calls[0].url, 'https://www.google.com/recaptcha/api/siteverify');
    const sent = new URLSearchParams(fake.calls[0].body);
    assert.equal(sent.get('secret'), 'test-secret');
    assert.equal(sent.get('response'), TOKEN);
    assert.equal(sent.has('remoteip'), false, 'the IP is not sent to Google');
  });

  test('without a secret key reCAPTCHA is disabled and Google is never called', async () => {
    const fake = google();
    assert.equal((await check(TOKEN, fake, 'signup', { ...config, secret: null })).outcome, 'disabled');
    assert.equal(fake.calls.length, 0);
  });

  test('a missing token is reported as missing, without calling Google', async () => {
    const fake = google();
    for (const token of [undefined, null, '']) assert.equal((await check(token, fake)).outcome, 'missing');
    assert.equal(fake.calls.length, 0);
  });

  test('a malformed token is reported as malformed, without calling Google', async () => {
    const fake = google();
    for (const token of ['short', 42, 'x'.repeat(5000), `${'A'.repeat(30)} <script>`]) {
      assert.equal((await check(token, fake)).outcome, 'malformed', String(token).slice(0, 20));
    }
    assert.equal(fake.calls.length, 0);
  });

  test('a token Google does not recognise is rejected', async () => {
    const result = await check(TOKEN, google({ success: false, 'error-codes': ['invalid-input-response'] }));
    assert.deepEqual(result, { outcome: 'rejected', reason: 'invalid-input-response' });
    assert.deepEqual(await check(TOKEN, google({ success: false })), { outcome: 'rejected', reason: 'not successful' });
  });

  test('an expired or reused token is expired', async () => {
    assert.equal((await check(TOKEN, google({ success: false, 'error-codes': ['timeout-or-duplicate'] }))).outcome, 'expired');
  });

  test('a token issued more than two minutes ago is expired even if Google accepts it', async () => {
    const result = await check(TOKEN, google({ challenge_ts: new Date(NOW - 121_000).toISOString() }));
    assert.deepEqual(result, { outcome: 'expired', reason: 'challenge_ts' });
  });

  test('a token of another action is a wrong action', async () => {
    assert.deepEqual(await check(TOKEN, google({ action: 'login' })), { outcome: 'wrong_action', reason: 'login' });
  });

  test('a token of another site is a wrong host when the hosts are configured', async () => {
    assert.deepEqual(await check(TOKEN, google({ hostname: 'Evil.Example' })), { outcome: 'wrong_hostname', reason: 'evil.example' });
    assert.equal((await check(TOKEN, google({ hostname: 'NEXORA.test' }))).outcome, 'verified', 'host names compare without case');
    assert.equal((await check(TOKEN, google({ hostname: 'evil.example' }), 'signup', { ...config, hostnames: [] })).outcome, 'verified');
  });

  test('a score below the minimum is low, not invalid', async () => {
    assert.deepEqual(await check(TOKEN, google({ score: 0.3 })), { outcome: 'low_score', score: 0.3 });
    assert.equal((await check(TOKEN, google({ score: 0.5 }))).outcome, 'verified', 'the minimum itself passes');
  });

  test('Google unreachable or answering nonsense is unavailable, never the sender\'s fault', async () => {
    const down = { fetch: async () => { throw new TypeError('fetch failed'); } };
    assert.equal((await check(TOKEN, down)).outcome, 'unavailable');
    assert.equal((await check(TOKEN, google({}, { status: 502 }))).outcome, 'unavailable');
    const nonsense = { fetch: async () => new Response('null', { status: 200 }) };
    assert.equal((await check(TOKEN, nonsense)).outcome, 'unavailable');
  });

  test('a secret key Google rejects is a configuration error, not the sender\'s fault', async () => {
    for (const code of ['invalid-input-secret', 'missing-input-secret']) {
      assert.deepEqual(await check(TOKEN, google({ success: false, 'error-codes': [code] })), { outcome: 'misconfigured', reason: code });
    }
  });
});

describe('what the server does with each result', () => {
  test('only a verified token (or reCAPTCHA turned off) skips the strict limit', () => {
    const passing = Object.keys(POLICY).filter((outcome) => POLICY[outcome].action === 'pass');
    assert.deepEqual(passing.sort(), ['disabled', 'verified']);
  });

  test('anything a real page can send, or a configuration mistake can cause, falls under the strict limit instead of being refused', () => {
    for (const outcome of ['missing', 'low_score', 'malformed', 'rejected', 'wrong_hostname', 'misconfigured', 'unavailable']) {
      assert.equal(POLICY[outcome].action, 'strict', outcome);
    }
  });

  test('only what the page can fix by itself, or never sends, is refused, with a code it understands', () => {
    assert.deepEqual(POLICY.expired, { action: 'refuse', status: 400, code: 'captcha_expired', error: 'The anti-spam check expired. Try again.' });
    assert.equal(POLICY.wrong_action.action, 'refuse');
    assert.equal(POLICY.wrong_action.code, 'captcha_invalid');
  });

  test('the visitor\'s own choices are not written to the log; configuration and Google problems are', () => {
    for (const outcome of ['verified', 'disabled', 'missing', 'low_score', 'expired', 'wrong_action']) assert.ok(!POLICY[outcome].log, outcome);
    for (const outcome of ['malformed', 'rejected', 'wrong_hostname', 'misconfigured', 'unavailable']) assert.ok(POLICY[outcome].log, outcome);
  });
});

describe('throttled log', () => {
  test('the same reason is written once per interval, then with how many were left out', () => {
    let time = 0;
    const lines = [];
    const report = throttledLog((line) => lines.push(line), { interval: 1000, now: () => time });
    report('a', 'first');
    report('a', 'again');
    report('a', 'again');
    report('b', 'other reason');
    time = 1000;
    report('a', 'later');
    assert.deepEqual(lines, ['first', 'other reason', 'later (2 more since the last report)']);
  });
});

describe('reCAPTCHA configuration', () => {
  test('defaults: disabled, minimum score 0.5, no host check, not production', () => {
    assert.deepEqual(loadCaptchaConfig({}), { secret: null, minScore: 0.5, hostnames: [], production: false });
  });

  test('reads the secret, the score and the hosts', () => {
    assert.deepEqual(
      loadCaptchaConfig({ RECAPTCHA_SECRET_KEY: ' s3cret ', RECAPTCHA_MIN_SCORE: '0.7', RECAPTCHA_HOSTNAMES: 'Nexora.dev, www.nexora.dev' }),
      { secret: 's3cret', minScore: 0.7, hostnames: ['nexora.dev', 'www.nexora.dev'], production: false },
    );
  });

  test('a minimum score outside 0..1 stops the server', () => {
    for (const value of ['2', '-0.1', 'high']) {
      assert.throws(() => loadCaptchaConfig({ RECAPTCHA_MIN_SCORE: value }), /RECAPTCHA_MIN_SCORE/);
    }
  });

  test('in production, a secret key without RECAPTCHA_HOSTNAMES stops the server', () => {
    assert.throws(
      () => loadCaptchaConfig({ NODE_ENV: 'production', RECAPTCHA_SECRET_KEY: 's3cret' }),
      /RECAPTCHA_HOSTNAMES/,
    );
    assert.equal(loadCaptchaConfig({ NODE_ENV: 'production', RECAPTCHA_SECRET_KEY: 's3cret', RECAPTCHA_HOSTNAMES: 'nexora.dev' }).production, true);
  });

  test('development without a secret key still starts, as before', () => {
    assert.deepEqual(loadCaptchaConfig({ NODE_ENV: 'development' }), { secret: null, minScore: 0.5, hostnames: [], production: false });
    assert.equal(loadCaptchaConfig({ NODE_ENV: 'production' }).secret, null, 'production without reCAPTCHA starts too, with the strict limit');
  });

  test('RECAPTCHA_HOSTNAMES only takes host names', () => {
    for (const value of ['https://nexora.dev', 'nexora.dev:443', 'nexora.dev/login', '*.nexora.dev', 'nexora dev', '-nexora.dev']) {
      assert.throws(() => loadCaptchaConfig({ RECAPTCHA_HOSTNAMES: value }), /RECAPTCHA_HOSTNAMES/, value);
    }
    assert.deepEqual(loadCaptchaConfig({ RECAPTCHA_HOSTNAMES: 'localhost, nexora.dev ,' }).hostnames, ['localhost', 'nexora.dev']);
  });
});

describe('reCAPTCHA turned off', () => {
  async function route(production) {
    const app = express();
    app.use(express.json());
    const logs = [];
    const cfg = { ...loadCaptchaConfig({}), production };
    app.post('/signup', antispam('signup', cfg, { strict: strictLimiter(1), log: (line) => logs.push(line) }), (req, res) => res.status(201).json({ ok: true }));
    const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
    const post = async () => (await fetch(`http://127.0.0.1:${server.address().port}/signup`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })).status;
    return { post, logs, close: () => new Promise((resolve) => server.close(resolve)) };
  }

  test('in development, without a secret key, the form has no extra limit', async () => {
    const r = await route(false);
    try {
      assert.deepEqual([await r.post(), await r.post(), await r.post()], [201, 201, 201]);
      assert.deepEqual(r.logs, []);
    } finally {
      await r.close();
    }
  });

  test('in production, without a secret key, every request falls under the strict limit and it is logged once', async () => {
    const r = await route(true);
    try {
      assert.deepEqual([await r.post(), await r.post(), await r.post()], [201, 429, 429]);
      assert.equal(r.logs.length, 1);
      assert.match(r.logs[0], /^captcha: signup: disabled_in_production: RECAPTCHA_SECRET_KEY is not set in production/);
    } finally {
      await r.close();
    }
  });
});

describe('anti-spam middleware on a form route', () => {
  let server;
  let base;
  let fake = google();
  const logs = [];

  before(async () => {
    const app = express();
    app.use(express.json());
    const verify = (token, action, cfg) => verifyCaptcha(token, action, cfg, { fetch: (...args) => fake.fetch(...args), now: () => NOW });
    // A strict limit of 2 so the tests can reach it.
    app.post('/signup', antispam('signup', config, { verify, strict: strictLimiter(2), log: (line) => logs.push(line) }), (req, res) => {
      res.status(201).json({ ok: true, name: req.body.name });
    });
    server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
    base = `http://127.0.0.1:${server.address().port}`;
  });
  after(() => new Promise((resolve) => server.close(resolve)));

  const post = async (body) => {
    const response = await fetch(`${base}/signup`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return { status: response.status, json: await response.json() };
  };

  test('a legitimate submission with a valid token goes through, as many times as needed', async () => {
    fake = google();
    for (let i = 0; i < 4; i += 1) {
      const { status, json } = await post({ name: 'Ada', captchaToken: TOKEN, website: '' });
      assert.equal(status, 201);
      assert.equal(json.name, 'Ada');
    }
  });

  test('a token of another form is refused', async () => {
    fake = google({ action: 'login' });
    assert.deepEqual(await post({ captchaToken: TOKEN }), {
      status: 400, json: { error: 'The anti-spam check failed. Reload the page and try again.', code: 'captcha_invalid' },
    });
  });

  test('an expired token is refused as expired', async () => {
    fake = google({ success: false, 'error-codes': ['timeout-or-duplicate'] });
    assert.equal((await post({ captchaToken: TOKEN })).json.code, 'captcha_expired');
  });

  test('the honeypot field filled in is refused before asking Google', async () => {
    fake = google();
    const before = fake.calls.length;
    const { status } = await post({ captchaToken: TOKEN, website: 'http://spam.example' });
    assert.equal(status, 400);
    assert.equal(fake.calls.length, before);
  });

  test('without a token (reCAPTCHA refused) the form still works, up to the strict limit', async () => {
    fake = google();
    assert.equal((await post({ name: 'Grace' })).status, 201);
    assert.equal((await post({ name: 'Grace' })).status, 201);
    const limited = await post({ name: 'Grace' });
    assert.equal(limited.status, 429);
    assert.equal(limited.json.code, 'captcha_required');
    // A verified submission is not affected by that limit.
    assert.equal((await post({ name: 'Grace', captchaToken: TOKEN })).status, 201);
  });

  test('a low score and an unavailable Google fall under the same strict limit, and the outage is logged', async () => {
    fake = google({ score: 0.1 });
    assert.equal((await post({ captchaToken: TOKEN })).status, 429, 'the strict limit of this IP is already used up');
    fake = { fetch: async () => { throw new TypeError('fetch failed'); }, calls: [] };
    assert.equal((await post({ captchaToken: TOKEN })).status, 429);
    assert.ok(logs.some((line) => line.startsWith('captcha: signup: unavailable (TypeError): Google could not be reached')));
  });
});

/** Una ruta protegida con su propio límite estricto, para empezar cada prueba con el cupo entero. */
async function protectedRoute({ fake, trustProxy = 0, limit = 2 }) {
  const logs = [];
  const app = express();
  app.set('trust proxy', trustProxy);
  app.use(express.json());
  const verify = (token, action, cfg) => verifyCaptcha(token, action, cfg, { fetch: fake.fetch, now: () => NOW });
  app.post('/signup', antispam('signup', config, { verify, strict: strictLimiter(limit), log: (line) => logs.push(line) }), (req, res) => {
    res.status(201).json({ ok: true });
  });
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const url = `http://127.0.0.1:${server.address().port}/signup`;
  const post = async (body, headers = {}) => {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    return { status: response.status, json: await response.json() };
  };
  return { post, logs, close: () => new Promise((resolve) => server.close(resolve)) };
}

describe('configuration mistakes and forged tokens', () => {
  const cases = [
    ['a site key that does not belong to the secret key', google({ success: false, 'error-codes': ['invalid-input-response'] }), 'rejected'],
    ['RECAPTCHA_HOSTNAMES without the real domain', google({ hostname: 'www.nexora.test' }), 'wrong_hostname'],
    ['a wrong secret key', google({ success: false, 'error-codes': ['invalid-input-secret'] }), 'misconfigured'],
  ];
  for (const [mistake, fake, outcome] of cases) {
    test(`${mistake}: people can still sign up, within the strict limit, and the server says why`, async () => {
      const route = await protectedRoute({ fake });
      try {
        assert.equal((await route.post({ captchaToken: TOKEN })).status, 201);
        assert.equal((await route.post({ captchaToken: TOKEN })).status, 201);
        const limited = await route.post({ captchaToken: TOKEN });
        assert.equal(limited.status, 429, 'never more than the strict limit');
        assert.equal(limited.json.code, 'captcha_required');
        // Three requests, one line: the log cannot be flooded.
        assert.equal(route.logs.length, 1);
        assert.match(route.logs[0], new RegExp(`^captcha: signup: ${outcome} `));
      } finally {
        await route.close();
      }
    });
  }

  test('a token of another form or an expired one never reaches the route, before or after the strict limit', async () => {
    for (const fake of [google({ action: 'login' }), google({ success: false, 'error-codes': ['timeout-or-duplicate'] })]) {
      const route = await protectedRoute({ fake, limit: 1 });
      try {
        assert.equal((await route.post({ captchaToken: TOKEN })).status, 400);
        assert.equal((await route.post({})).status, 201, 'refusals do not use up the strict limit of the visitor');
        assert.equal((await route.post({ captchaToken: TOKEN })).status, 400, 'still refused once the limit is used up');
        assert.equal((await route.post({})).status, 429);
      } finally {
        await route.close();
      }
    }
  });

  test('an expired token still costs one attempt of the general limit, so a used token cannot be replayed for free', async () => {
    // Free refusals would let anyone resend one used token forever, and the server would ask Google
    // every time. The page resends once with a new token: that costs one more attempt, no more.
    const fake = google({ success: false, 'error-codes': ['timeout-or-duplicate'] });
    const app = express();
    app.use(express.json());
    const verify = (token, action, cfg) => verifyCaptcha(token, action, cfg, { fetch: fake.fetch, now: () => NOW });
    app.post('/signup', clientRateLimit({ windowMs: 60_000, limit: 2, message: { code: 'too_many' } }), antispam('signup', config, { verify, log: () => {} }), (req, res) => res.status(201).json({ ok: true }));
    const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
    try {
      const post = async () => (await fetch(`http://127.0.0.1:${server.address().port}/signup`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ captchaToken: TOKEN }),
      })).status;
      assert.deepEqual([await post(), await post(), await post(), await post()], [400, 400, 429, 429]);
      assert.equal(fake.calls.length, 2, 'Google is not asked once the general limit is used up');
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  test('a forged token gets nothing that sending no token at all would not get', async () => {
    const route = await protectedRoute({ fake: google({ success: false, 'error-codes': ['invalid-input-response'] }) });
    try {
      assert.equal((await route.post({ captchaToken: TOKEN })).status, 201);
      assert.equal((await route.post({})).status, 201);
      assert.equal((await route.post({ captchaToken: 'not a token at all' })).status, 429, 'forged, missing and malformed share one limit');
    } finally {
      await route.close();
    }
  });
});

describe('who counts as the same client', () => {
  test('behind one proxy (TRUST_PROXY=1) each visitor has a limit of their own', async () => {
    const route = await protectedRoute({ fake: google(), trustProxy: 1, limit: 1 });
    try {
      assert.equal((await route.post({}, { 'X-Forwarded-For': '198.51.100.1' })).status, 201);
      assert.equal((await route.post({}, { 'X-Forwarded-For': '198.51.100.1' })).status, 429);
      assert.equal((await route.post({}, { 'X-Forwarded-For': '198.51.100.2' })).status, 201, 'another visitor is not affected');
    } finally {
      await route.close();
    }
  });

  test('without TRUST_PROXY a forged X-Forwarded-For does not buy a new limit', async () => {
    const route = await protectedRoute({ fake: google(), trustProxy: 0, limit: 1 });
    try {
      assert.equal((await route.post({}, { 'X-Forwarded-For': '198.51.100.1' })).status, 201);
      assert.equal((await route.post({}, { 'X-Forwarded-For': '198.51.100.2' })).status, 429);
    } finally {
      await route.close();
    }
  });

  test('spreading over the /56 blocks of one /48 does not multiply the limit', async () => {
    // Regression: each /56 used to have a limit of its own, so a /48 had 256 of them.
    const route = await protectedRoute({ fake: google(), trustProxy: 1, limit: 1 });
    try {
      for (let block = 0; block < 4; block += 1) {
        const address = `2001:db8:aa:${(block << 8).toString(16)}::1`;
        assert.equal((await route.post({}, { 'X-Forwarded-For': address })).status, 201, address);
      }
      assert.equal((await route.post({}, { 'X-Forwarded-For': '2001:db8:aa:ff00::1' })).status, 429, 'the /48 has used its 4 × 1');
      assert.equal((await route.post({}, { 'X-Forwarded-For': '2001:db8:bb:100::1' })).status, 201, 'another /48 is not affected');
    } finally {
      await route.close();
    }
  });

  test('made-up X-Forwarded-For values share one limit', async () => {
    const route = await protectedRoute({ fake: google(), trustProxy: 1, limit: 1 });
    try {
      assert.equal((await route.post({}, { 'X-Forwarded-For': 'garbage-1' })).status, 201);
      assert.equal((await route.post({}, { 'X-Forwarded-For': 'garbage-2' })).status, 429);
    } finally {
      await route.close();
    }
  });

  test('addresses of one IPv6 block share a limit; another block does not', async () => {
    const route = await protectedRoute({ fake: google(), trustProxy: 1, limit: 1 });
    try {
      assert.equal((await route.post({}, { 'X-Forwarded-For': '2001:db8:aa:bb01::1' })).status, 201);
      assert.equal((await route.post({}, { 'X-Forwarded-For': '2001:db8:aa:bbfe:1234::9' })).status, 429, 'same /56');
      assert.equal((await route.post({}, { 'X-Forwarded-For': '2001:db8:aa:cc00::1' })).status, 201, 'another /56');
    } finally {
      await route.close();
    }
  });
});

describe('the two reCAPTCHA keys', () => {
  const SITE_KEY = `6L${'a'.repeat(38)}`;

  // That the real web/js/consent-config.js is still readable this way is checked with it, in consent.test.js.
  test('the site key is read from the recaptchaSiteKey line of consent-config.js', () => {
    assert.equal(readSiteKey('  recaptchaSiteKey: null,'), '', 'null: no site key, but the line was found');
    assert.equal(readSiteKey(`  recaptchaSiteKey: '${SITE_KEY}',`), SITE_KEY);
    assert.equal(readSiteKey(`  recaptchaSiteKey: "${SITE_KEY}"`), SITE_KEY);
    assert.equal(readSiteKey('  // recaptchaSiteKey: null'), undefined, 'a comment is not the setting');
    assert.equal(readSiteKey('window.X = {};'), undefined);
  });

  test('both set or both empty: nothing to say', () => {
    assert.deepEqual(captchaKeyWarnings({ secret: null, siteKey: '' }), []);
    assert.deepEqual(captchaKeyWarnings({ secret: 'secret', siteKey: SITE_KEY }), []);
  });

  test('only one of them set: the server says what visitors will get', () => {
    assert.match(captchaKeyWarnings({ secret: 'secret', siteKey: '' })[0], /no recaptchaSiteKey: .*strict limit/);
    assert.match(captchaKeyWarnings({ secret: null, siteKey: SITE_KEY })[0], /RECAPTCHA_SECRET_KEY is not set: .*blocks reCAPTCHA/);
  });

  test('a site key the browser would ignore, or a file it cannot read, is reported too', () => {
    assert.match(captchaKeyWarnings({ secret: 'secret', siteKey: 'not-a-key' })[0], /not a valid site key/);
    assert.match(captchaKeyWarnings({ secret: 'secret', siteKey: undefined })[0], /could not find recaptchaSiteKey/);
  });

  test('without web/js/consent-config.js the server still starts: no site key, and a word only if a secret is set', () => {
    assert.equal(readSiteKeyFile(new URL('./no-such-consent-config.js', import.meta.url)), null);
    assert.deepEqual(captchaKeyWarnings({ secret: null, siteKey: null }), []);
    assert.match(captchaKeyWarnings({ secret: 'secret', siteKey: null })[0], /consent-config\.js does not exist: .*strict limit/);
  });

  test('a file that exists but cannot be read is not fatal either: the keys are just not cross-checked', () => {
    const denied = () => { throw Object.assign(new Error('denied'), { code: 'EACCES' }); };
    assert.deepEqual(readSiteKeyFile('consent-config.js', { read: denied }), { readError: 'EACCES' });
    assert.equal(readSiteKeyFile('consent-config.js', { read: () => `  recaptchaSiteKey: '${SITE_KEY}',` }), SITE_KEY);
  });

  test('an unreadable file is reported as unreadable, with or without a secret key', () => {
    for (const secret of [null, 'secret']) {
      const warnings = captchaKeyWarnings({ secret, siteKey: { readError: 'EACCES' } });
      assert.equal(warnings.length, 1, String(secret));
      assert.match(warnings[0], /^could not read web\/js\/consent-config\.js \(EACCES\); the reCAPTCHA keys were not cross-checked$/);
      assert.doesNotMatch(warnings[0], /could not find/);
    }
    const odd = () => { throw new TypeError('not a path'); };
    assert.deepEqual(readSiteKeyFile('consent-config.js', { read: odd }), { readError: 'TypeError' }, 'an error without a code is named');
  });

  test('"could not find recaptchaSiteKey" is kept for a file that was read but has no such line', () => {
    const siteKey = readSiteKeyFile('consent-config.js', { read: () => 'window.NEXORA_CONSENT_CONFIG = {};' });
    assert.equal(siteKey, undefined);
    for (const secret of [null, 'secret']) {
      assert.deepEqual(captchaKeyWarnings({ secret, siteKey }), ['could not find recaptchaSiteKey in web/js/consent-config.js; the reCAPTCHA keys were not cross-checked']);
    }
    // Neither a missing file nor an unreadable one gets that message.
    assert.ok(!captchaKeyWarnings({ secret: 'secret', siteKey: null }).some((line) => line.includes('could not find')));
    assert.ok(!captchaKeyWarnings({ secret: 'secret', siteKey: { readError: 'EISDIR' } }).some((line) => line.includes('could not find')));
  });
});
