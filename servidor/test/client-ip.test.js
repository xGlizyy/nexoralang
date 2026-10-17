// Clave de cliente de los límites de peticiones y TRUST_PROXY (src/client-ip.js).

import assert from 'node:assert/strict';
import { test } from 'node:test';
import express from 'express';
import { IPV6_NETWORK_PREFIX, IPV6_PREFIX, clientKey, parseTrustProxy } from '../src/client-ip.js';

test('an IPv4 address is its own key', () => {
  assert.equal(clientKey('203.0.113.7'), '203.0.113.7');
});

test('an IPv4 address written as IPv6 counts as that IPv4 address', () => {
  assert.equal(clientKey('::ffff:203.0.113.7'), '203.0.113.7');
  assert.equal(clientKey('::ffff:7f00:1'), '127.0.0.1');
});

test('IPv6 addresses are grouped by their /56 prefix, in any notation', () => {
  assert.equal(IPV6_PREFIX, 56);
  const key = '2001:db8:aa:bb00:0:0:0:0/56';
  for (const address of ['2001:db8:aa:bb12:1:2:3:4', '2001:db8:aa:bbff::9', '2001:0db8:00aa:bb00::', '2001:DB8:AA:BB01::1']) {
    assert.equal(clientKey(address), key, address);
  }
  assert.notEqual(clientKey('2001:db8:aa:bc00::1'), key, 'the next /56 is another client');
  assert.equal(clientKey('fe80::1%eth0'), 'fe80:0:0:0:0:0:0:0/56', 'the zone is ignored');
});

test('anything that is not an address shares one key, so made-up values do not buy new limits', () => {
  // Regression: these used to be returned as they were, one key each.
  for (const value of ['not-an-ip', 'not-an-ip-2', '1.2.3.4:5678', '[2001:db8::1]', '999.1.1.1', undefined, '']) {
    assert.equal(clientKey(value), 'invalid-address', String(value));
  }
});

test('the wider IPv6 network key is the /48 block; IPv4 keeps its own address', () => {
  assert.equal(IPV6_NETWORK_PREFIX, 48);
  assert.equal(clientKey('2001:db8:aa:bb12::1', IPV6_NETWORK_PREFIX), '2001:db8:aa:0:0:0:0:0/48');
  assert.equal(clientKey('2001:db8:aa:ff00::1', IPV6_NETWORK_PREFIX), '2001:db8:aa:0:0:0:0:0/48', 'every /56 of the /48');
  assert.equal(clientKey('203.0.113.7', IPV6_NETWORK_PREFIX), '203.0.113.7');
});

test('IPv4-mapped addresses cannot be used to dodge the IPv4 limit', () => {
  for (const address of ['::ffff:203.0.113.7', '::FFFF:203.0.113.7', '0:0:0:0:0:ffff:cb00:7107']) {
    assert.equal(clientKey(address), '203.0.113.7', address);
  }
});

test('TRUST_PROXY: unset or empty means no proxy; a small whole number is the number of proxies', () => {
  assert.equal(parseTrustProxy(undefined), 0);
  assert.equal(parseTrustProxy(''), 0);
  assert.equal(parseTrustProxy('0'), 0);
  assert.equal(parseTrustProxy(' 1 '), 1);
  assert.equal(parseTrustProxy('2'), 2);
});

test('TRUST_PROXY: any other value stops the server instead of being guessed', () => {
  // '01', '00': leading zeros are ambiguous, most likely a typo (regression: they used to be accepted).
  for (const value of ['true', 'yes', '-1', '1.5', '11', '01', '00', '007', 'Loopback', 'loopback,10.0.0.1', 'uniquelocal']) {
    assert.throws(() => parseTrustProxy(value), /TRUST_PROXY/, value);
  }
});

test('TRUST_PROXY=loopback believes X-Forwarded-For only from a proxy on this machine', () => {
  assert.equal(parseTrustProxy('loopback'), 'loopback');
  const app = express();
  app.set('trust proxy', parseTrustProxy('loopback'));
  const trusted = app.get('trust proxy fn');
  assert.equal(trusted('127.0.0.1', 0), true, 'nginx on this machine');
  assert.equal(trusted('::1', 0), true);
  // Regression: with TRUST_PROXY=1 a direct connection from the Internet is believed too, so an open
  // port lets anyone choose their address. With loopback it is not.
  assert.equal(trusted('203.0.113.9', 0), false, 'a direct connection from outside');
  app.set('trust proxy', 1);
  assert.equal(app.get('trust proxy fn')('203.0.113.9', 0), true, 'what TRUST_PROXY=1 does');
});
