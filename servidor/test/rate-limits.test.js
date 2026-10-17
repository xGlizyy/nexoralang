// Cabeceras RateLimit-* y Retry-After de los límites por cliente (src/rate-limits.js). Cómo se cuenta a
// cada cliente lo comprueban listen.test.js y client-ip.test.js.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import express from 'express';
import { NETWORK_FACTOR, clientRateLimit } from '../src/rate-limits.js';

/** Un servidor con `limits` (opciones de clientRateLimit) en cadena delante de la misma ruta. */
async function chain(...limits) {
  const app = express();
  app.set('trust proxy', 1);
  app.get('/', ...limits.map((options) => clientRateLimit({ message: { error: 'limited' }, ...options })), (req, res) => res.json({ ok: true }));
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const get = async (address = '198.51.100.1') => {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/`, { headers: { 'X-Forwarded-For': address } });
    const header = (name) => response.headers.get(name);
    return {
      status: response.status,
      limit: header('ratelimit-limit'),
      remaining: header('ratelimit-remaining'),
      reset: Number(header('ratelimit-reset')),
      policy: header('ratelimit-policy'),
      retryAfter: header('retry-after'),
    };
  };
  return { get, close: () => new Promise((resolve) => server.close(resolve)) };
}

describe('RateLimit headers', () => {
  test('describe the client\'s own count, not the wider count of its network', async () => {
    const r = await chain({ windowMs: 60_000, limit: 3 });
    try {
      const first = await r.get();
      assert.equal(first.status, 200);
      assert.equal(first.limit, '3', `the /48 count (${3 * NETWORK_FACTOR}) must not overwrite it`);
      assert.equal(first.remaining, '2');
      assert.equal(first.policy, '3;w=60');
      assert.ok(first.reset > 0 && first.reset <= 60);
      assert.equal(first.retryAfter, null, 'only a refusal says when to come back');
    } finally { await r.close(); }
  });

  test('with two limits in a row, describe the one that runs out first, whichever runs last', async () => {
    for (const order of [[{ windowMs: 60_000, limit: 10 }, { windowMs: 60_000, limit: 2 }], [{ windowMs: 60_000, limit: 2 }, { windowMs: 60_000, limit: 10 }]]) {
      const r = await chain(...order);
      try {
        const first = await r.get();
        assert.equal(first.limit, '2');
        assert.equal(first.remaining, '1');
      } finally { await r.close(); }
    }
  });

  test('when two counts have as many requests left, describe the one that takes longer to renew', async () => {
    const r = await chain({ windowMs: 60_000, limit: 2 }, { windowMs: 60 * 60_000, limit: 2 });
    try {
      const first = await r.get();
      assert.equal(first.remaining, '1');
      assert.equal(first.policy, '2;w=3600');
      assert.ok(first.reset > 60, `RateLimit-Reset ${first.reset}`);
    } finally { await r.close(); }
  });

  test('a refusal by the client\'s count says when that count renews', async () => {
    const r = await chain({ windowMs: 60_000, limit: 1 });
    try {
      await r.get();
      const refused = await r.get();
      assert.equal(refused.status, 429);
      assert.equal(refused.remaining, '0');
      assert.equal(refused.limit, '1');
      assert.ok(Number(refused.retryAfter) > 0 && Number(refused.retryAfter) <= 60, `Retry-After ${refused.retryAfter}`);
      assert.equal(Number(refused.retryAfter), refused.reset);
    } finally { await r.close(); }
  });

  test('a refusal by the network count describes the network count', async () => {
    // Each /56 makes one request of the two it may: only the /48 runs out, and that is what is shown.
    const r = await chain({ windowMs: 60_000, limit: 2 });
    try {
      for (let block = 1; block <= 2 * NETWORK_FACTOR; block += 1) {
        assert.equal((await r.get(`2001:db8:aa:${(block << 8).toString(16)}::1`)).status, 200);
      }
      const refused = await r.get('2001:db8:aa:ff00::1');
      assert.equal(refused.status, 429);
      assert.equal(refused.limit, String(2 * NETWORK_FACTOR));
      assert.equal(refused.remaining, '0');
      assert.ok(Number(refused.retryAfter) > 0 && Number(refused.retryAfter) <= 60);
    } finally { await r.close(); }
  });

  test('a custom handler still answers, with Retry-After already set', async () => {
    const app = express();
    app.get('/', clientRateLimit({ windowMs: 60_000, limit: 1, handler: (req, res) => res.status(429).json({ code: 'custom', retryAfter: res.get('Retry-After') }) }), (req, res) => res.json({ ok: true }));
    const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
    try {
      const url = `http://127.0.0.1:${server.address().port}/`;
      await fetch(url);
      const refused = await fetch(url);
      const body = await refused.json();
      assert.equal(refused.status, 429);
      assert.equal(body.code, 'custom');
      assert.ok(Number(body.retryAfter) > 0);
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });
});
