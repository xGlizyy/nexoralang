// Cabeceras de seguridad de la aplicación real (src/app.js y src/security-headers.js), página a
// página. Comprueban lo que el servidor envía, no cómo lo trata un navegador concreto ni el servidor
// de producción (HTTPS real, nginx real): eso sigue pendiente de probar en el despliegue.

// app.js carga la configuración real, que exige variables de base de datos. Apuntan a un puerto donde
// no hay nada: ninguna prueba debe consultar la base de datos, y si una lo hiciera, fallaría.
process.env.DB_USER = 'test';
process.env.DB_NAME = 'test';
process.env.DB_HOST = '127.0.0.1';
process.env.DB_PORT = '1';

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import http from 'node:http';
import { after, before, describe, test } from 'node:test';

const { createApp } = await import('../src/app.js');
const { API_POLICY, HSTS, pagePolicy } = await import('../src/security-headers.js');

const web = (file) => readFileSync(new URL(`../../web/${file}`, import.meta.url), 'utf8');
// Every page of the site, whatever it has: the same headers have to reach a page added later.
const PAGES = readdirSync(new URL('../../web/', import.meta.url)).filter((name) => name.endsWith('.html')).sort();
const AUTH_PATHS = ['/login', '/login.html', '/signup', '/signup.html'];
// The policy the playground and the guide had before it was extended to every page.
const PREVIOUS_PLAYGROUND_POLICY = "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";

async function serve(options) {
  const logs = [];
  const app = createApp({ ...options, log: (line) => logs.push(line) });
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const get = (path, init) => fetch(`${base}${path}`, init);
  return { base, get, logs, close: () => new Promise((resolve) => server.close(resolve)) };
}

function assertCommon(response, path) {
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff', path);
  assert.equal(response.headers.get('x-frame-options'), 'DENY', path);
  assert.equal(response.headers.get('cross-origin-opener-policy'), 'same-origin', path);
  assert.match(response.headers.get('permissions-policy') ?? '', /camera=\(\)/, path);
}

test('the pages checked include every page the site has always had', () => {
  for (const page of ['index.html', 'docs.html', 'guide.html', 'playground.html', 'login.html', 'signup.html']) {
    assert.ok(PAGES.includes(page), page);
  }
});

describe('in development, without reCAPTCHA', () => {
  let server;
  before(async () => { server = await serve({ production: false, trustProxy: 0, recaptcha: false }); });
  after(() => server.close());

  for (const page of PAGES) {
    test(`${page}: every security header, and the strict page policy`, async () => {
      const response = await server.get(`/${page}`);
      assert.equal(response.status, 200);
      assertCommon(response, page);
      assert.equal(response.headers.get('content-security-policy'), pagePolicy());
      assert.equal(response.headers.get('strict-transport-security'), null, 'no HSTS over plain HTTP in development');
    });
  }

  test('the playground and the guide keep exactly the policy they had, and send no Referer', async () => {
    assert.equal(pagePolicy(), PREVIOUS_PLAYGROUND_POLICY);
    for (const path of ['/playground', '/playground.html', '/guide', '/guide.html']) {
      const response = await server.get(path);
      assert.equal(response.headers.get('content-security-policy'), PREVIOUS_PLAYGROUND_POLICY, path);
      assert.equal(response.headers.get('referrer-policy'), 'no-referrer', path);
    }
  });

  test('the other pages send only the origin to other sites', async () => {
    for (const path of ['/', '/docs.html', '/login', '/signup']) {
      assert.equal((await server.get(path)).headers.get('referrer-policy'), 'strict-origin-when-cross-origin', path);
    }
  });

  test('without reCAPTCHA, the sign-up and log-in pages allow nothing from Google', async () => {
    for (const path of AUTH_PATHS) {
      const response = await server.get(path);
      assert.equal(response.headers.get('content-security-policy'), pagePolicy(), path);
      assert.doesNotMatch(response.headers.get('content-security-policy'), /google/, path);
    }
  });

  test('API responses, including errors, get the headers and a policy that loads nothing', async () => {
    const responses = {
      info: await server.get('/api/playground/info'),
      missing: await server.get('/api/no-such-route'),
      badJson: await server.get('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{bad' }),
      honeypot: await server.get('/api/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"website":"x"}' }),
    };
    assert.equal(responses.missing.status, 404);
    assert.equal(responses.badJson.status, 400, 'handled by the error handler');
    assert.equal(responses.honeypot.status, 400);
    for (const [name, response] of Object.entries(responses)) {
      assertCommon(response, name);
      assert.equal(response.headers.get('content-security-policy'), API_POLICY, name);
    }
  });

  test('a page that does not exist still gets the anti-framing headers', async () => {
    const response = await server.get('/no-such-page.html');
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('x-frame-options'), 'DENY');
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  });

  test('the fonts are served by the site, as fonts', async () => {
    const response = await server.get('/fonts/jetbrains-mono/jetbrains-mono-latin.woff2');
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'font/woff2');
  });
});

describe('in production behind nginx, with reCAPTCHA', () => {
  let server;
  before(async () => { server = await serve({ production: true, trustProxy: 'loopback', recaptcha: true }); });
  after(() => server.close());

  test('sign-up and log-in allow exactly the reCAPTCHA script and frame, nothing else from Google', async () => {
    for (const path of AUTH_PATHS) {
      const policy = (await server.get(path)).headers.get('content-security-policy');
      assert.equal(policy, pagePolicy({ recaptcha: true }), path);
      assert.match(policy, /script-src 'self' https:\/\/www\.google\.com\/recaptcha\/ https:\/\/www\.gstatic\.com\/recaptcha\//);
      assert.match(policy, /frame-src https:\/\/www\.google\.com\/recaptcha\/ https:\/\/recaptcha\.google\.com\/recaptcha\//);
      assert.match(policy, /frame-ancestors 'none'/);
    }
  });

  test('every other page keeps the strict policy', async () => {
    for (const path of ['/', '/playground', '/guide', '/docs.html']) {
      assert.equal((await server.get(path)).headers.get('content-security-policy'), pagePolicy(), path);
    }
  });

  test('HSTS only on requests that arrived over HTTPS', async () => {
    const https = await server.get('/', { headers: { 'X-Forwarded-Proto': 'https' } });
    assert.equal(https.headers.get('strict-transport-security'), HSTS);
    const http = await server.get('/');
    assert.equal(http.headers.get('strict-transport-security'), null, 'plain HTTP: no HSTS');
  });
});

describe('the page policy follows the file actually served (D2)', () => {
  let server;
  before(async () => { server = await serve({ production: false, trustProxy: 0, recaptcha: true }); });
  after(() => server.close());

  const AUTH_POLICY = pagePolicy({ recaptcha: true });

  test('encoded spellings of the log-in and sign-up pages get their policy', async () => {
    // Regression: the policy was chosen from the raw URL, so /logi%6E.html got the generic one.
    for (const route of ['/login', '/login.html', '/logi%6E.html', '/%6Cogin', '/sign%75p.html', '/signup%2Ehtml']) {
      const response = await server.get(route);
      assert.equal(response.status, 200, route);
      assert.equal(response.headers.get('content-security-policy'), AUTH_POLICY, route);
    }
  });

  test('encoded spellings of the playground and the guide keep no-referrer and the strict policy', async () => {
    for (const route of ['/playground', '/playgroun%64', '/playground%2Ehtml', '/guide', '/guid%65.html']) {
      const response = await server.get(route);
      assert.equal(response.status, 200, route);
      assert.equal(response.headers.get('referrer-policy'), 'no-referrer', route);
      assert.equal(response.headers.get('content-security-policy'), pagePolicy(), route);
    }
  });

  test('HEAD and a 304 answer carry the page policy too', async () => {
    assert.equal((await server.get('/logi%6E.html', { method: 'HEAD' })).headers.get('content-security-policy'), AUTH_POLICY);
    const first = await server.get('/login');
    // node:http, not fetch: with a hand-set If-None-Match, fetch adds Cache-Control: no-cache, which
    // makes any server answer 200 instead of 304.
    const cached = await new Promise((resolve, reject) => {
      http.get(`${server.base}/login`, { headers: { 'If-None-Match': first.headers.get('etag') } }, (response) => {
        response.resume();
        resolve(response);
      }).on('error', reject);
    });
    assert.equal(cached.statusCode, 304);
    assert.equal(cached.headers['content-security-policy'], AUTH_POLICY);
  });

  test('upper case: served on a case-insensitive file system (Windows) with the same policy; absent on Linux', async () => {
    for (const route of ['/LOGIN', '/Login.html', '/PLAYGROUND']) {
      const response = await server.get(route);
      if (process.platform === 'win32') {
        assert.equal(response.status, 200, route);
        const expected = route.toLowerCase().includes('login') ? AUTH_POLICY : pagePolicy();
        assert.equal(response.headers.get('content-security-policy'), expected, route);
        if (route === '/PLAYGROUND') assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
      } else {
        assert.equal(response.status, 404, route);
      }
      assert.equal(response.headers.get('x-frame-options'), 'DENY', route);
    }
  });

  test('malformed or double encodings are not served, and keep the global headers', async () => {
    for (const route of ['/logi%E0.html', '/%', '/login%', '/logi%256E.html', '/%2']) {
      const response = await server.get(route);
      assert.notEqual(response.status, 200, route);
      assert.equal(response.headers.get('x-frame-options'), 'DENY', route);
      assert.equal(response.headers.get('x-content-type-options'), 'nosniff', route);
      assert.notEqual(response.headers.get('content-security-policy'), AUTH_POLICY, route);
    }
  });

  test('paths that try to leave web/ serve nothing from outside it', async () => {
    for (const route of ['/%2e%2e/servidor/.env.example', '/..%2fservidor%2f.env.example', '/fonts/..%2f..%2fservidor%2f.env.example',
      '/%2e%2e%5cservidor%5c.env.example', '/..%5c..%5cservidor%5c.env.example']) {
      const response = await server.get(route);
      const body = await response.text();
      assert.notEqual(response.status, 200, route);
      assert.doesNotMatch(body, /TRUST_PROXY|DB_USER/, route);
      assert.equal(response.headers.get('x-frame-options'), 'DENY', route);
    }
  });

  test('a page that does not exist gets the global headers, never the log-in policy', async () => {
    for (const route of ['/login.htm', '/login/', '/nope/login.html']) {
      const response = await server.get(route);
      assert.equal(response.status, 404, route);
      assert.equal(response.headers.get('x-frame-options'), 'DENY', route);
      assert.notEqual(response.headers.get('content-security-policy'), AUTH_POLICY, route);
    }
  });
});

test('in development, a request marked as HTTPS gets no HSTS either', async () => {
  const server = await serve({ production: false, trustProxy: 'loopback', recaptcha: false });
  try {
    const response = await server.get('/', { headers: { 'X-Forwarded-Proto': 'https' } });
    assert.equal(response.headers.get('strict-transport-security'), null);
  } finally {
    await server.close();
  }
});

describe('what the policies allow', () => {
  test('no inline code, no eval, no wildcards, nothing over plain http', () => {
    for (const policy of [pagePolicy(), pagePolicy({ recaptcha: true }), API_POLICY]) {
      assert.doesNotMatch(policy, /unsafe-inline|unsafe-eval|unsafe-hashes|\*|http:/, policy);
    }
  });

  test('no page needs inline code: no inline scripts, styles or event handlers', () => {
    for (const page of PAGES) {
      const html = web(page);
      assert.doesNotMatch(html, /<script(?![^>]*\bsrc=")[^>]*>/, `${page} has an inline script`);
      assert.doesNotMatch(html, /<style\b/, `${page} has a style element`);
      assert.doesNotMatch(html, /\sstyle="/, `${page} has an inline style`);
      assert.doesNotMatch(html, /\son\w+="/, `${page} has an inline event handler`);
    }
  });

  test('no page holds an optional script waiting for consent, so the policy does not need to allow one', () => {
    // consent.js can activate <script type="text/plain" data-consent="…" src="…"> after consent, but the
    // policy only allows scripts of this site: one from another site would be blocked even with consent.
    // Allowing a service is a pending decision (nexora/docs/playground.md, «Tareas pendientes y riesgos»).
    for (const page of PAGES) {
      assert.doesNotMatch(web(page), /<script\b[^>]*\bdata-consent=/, `${page} has an optional script: update the Content-Security-Policy`);
    }
  });
});
