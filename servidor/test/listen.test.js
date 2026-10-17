// Dirección de escucha (src/listen.js) y la estrategia común de límites (src/rate-limits.js).

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import express from 'express';
import { listenWarnings, parseListenHost } from '../src/listen.js';
import { NETWORK_FACTOR, clientRateLimit } from '../src/rate-limits.js';

describe('LISTEN_HOST', () => {
  test('unset or empty keeps the old behaviour: every interface', () => {
    assert.equal(parseListenHost(undefined), null);
    assert.equal(parseListenHost(''), null);
    assert.equal(parseListenHost('  '), null);
  });

  test('takes an IP address', () => {
    for (const value of ['127.0.0.1', '::1', '0.0.0.0', '10.0.0.5']) assert.equal(parseListenHost(value), value);
  });

  test('anything else stops the server instead of being guessed, localhost included', () => {
    // localhost may resolve to ::1 only (it does on Windows 11 with Node 24), and then a proxy that
    // connects to 127.0.0.1 never reaches the server.
    for (const value of ['localhost', 'my-laptop', 'nexora.dev', '127.0.0.1:3000', 'http://127.0.0.1']) {
      assert.throws(() => parseListenHost(value), /LISTEN_HOST/, value);
    }
  });

  test('warns when a proxy is trusted but the port may be reachable from elsewhere', () => {
    assert.equal(listenWarnings({ host: null, trustProxy: 0 }).length, 0, 'development: nothing to say');
    assert.equal(listenWarnings({ host: '127.0.0.1', trustProxy: 'loopback' }).length, 0, 'the recommended setup');
    for (const host of ['::1', '127.0.0.2']) assert.equal(listenWarnings({ host, trustProxy: 'loopback' }).length, 0, `${host} is this machine too`);
    assert.match(listenWarnings({ host: null, trustProxy: 'loopback' })[0], /LISTEN_HOST=127\.0\.0\.1/);
    assert.match(listenWarnings({ host: '0.0.0.0', trustProxy: 'loopback' })[0], /listens on 0\.0\.0\.0/);
    assert.match(listenWarnings({ host: null, trustProxy: 1 })[0], /anyone can choose the address/);
  });
});

describe('one rate-limit strategy for every limit', () => {
  async function limited(limit) {
    const app = express();
    app.set('trust proxy', 1);
    app.get('/', clientRateLimit({ windowMs: 60_000, limit, message: { error: 'limited' } }), (req, res) => res.json({ ok: true }));
    const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
    const get = async (address) => (await fetch(`http://127.0.0.1:${server.address().port}/`, { headers: { 'X-Forwarded-For': address } })).status;
    return { get, close: () => new Promise((resolve) => server.close(resolve)) };
  }

  test('IPv4: each address has its own limit', async () => {
    const r = await limited(1);
    try {
      assert.deepEqual([await r.get('198.51.100.1'), await r.get('198.51.100.1'), await r.get('198.51.100.2')], [200, 429, 200]);
    } finally { await r.close(); }
  });

  test('an IPv4 address written as IPv6 shares the limit of that IPv4 address', async () => {
    const r = await limited(1);
    try {
      assert.deepEqual([await r.get('198.51.100.1'), await r.get('::ffff:198.51.100.1'), await r.get('::ffff:c633:6401')], [200, 429, 429]);
    } finally { await r.close(); }
  });

  test('one client hammering past its own limit does not use up the share of its /48 neighbours', async () => {
    // Regression: the /48 count ran first, so refused requests of one client still spent the network's share.
    const r = await limited(1);
    try {
      assert.equal(await r.get('2001:db8:cc:100::1'), 200);
      for (let i = 0; i < 20; i += 1) assert.equal(await r.get('2001:db8:cc:100::1'), 429);
      for (let block = 2; block <= NETWORK_FACTOR; block += 1) {
        assert.equal(await r.get(`2001:db8:cc:${(block << 8).toString(16)}::1`), 200, `neighbour ${block} still gets in`);
      }
    } finally { await r.close(); }
  });

  test('IPv6: a /56 is one client; its /48 has NETWORK_FACTOR times the limit; another /48 is apart', async () => {
    const r = await limited(1);
    try {
      assert.equal(await r.get('2001:db8:aa:1::1'), 200);
      assert.equal(await r.get('2001:db8:aa:1::2'), 429, 'same /56');
      for (let block = 2; block <= NETWORK_FACTOR; block += 1) {
        assert.equal(await r.get(`2001:db8:aa:${(block << 8).toString(16)}::1`), 200, `another /56 of the /48 (${block})`);
      }
      assert.equal(await r.get('2001:db8:aa:ff00::1'), 429, 'the /48 used up its share');
      assert.equal(await r.get('2001:db8:bb::1'), 200, 'another /48');
    } finally { await r.close(); }
  });

  test('invalid addresses share one limit', async () => {
    const r = await limited(1);
    try {
      assert.deepEqual([await r.get('not-an-ip'), await r.get('also-not'), await r.get('1.2.3.4:80')], [200, 429, 429]);
    } finally { await r.close(); }
  });
});
