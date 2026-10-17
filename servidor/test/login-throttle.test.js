// Freno del inicio de sesión por cuenta (src/login-throttle.js), con un reloj simulado: ninguna
// prueba depende de pausas ni de temporizadores reales.

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, test } from 'node:test';
import {
  ACCOUNT_FREE, ACCOUNT_MAX_DELAY_MS, FORGET_AFTER_MS, OVERFLOW_WINDOW_MS, PAIR_FREE, PAIR_MAX_DELAY_MS, accountDigest, createLoginThrottle,
} from '../src/login-throttle.js';

function clock() {
  let time = 1_000_000;
  return { now: () => time, advance: (ms) => { time += ms; } };
}

/** Un intento entero: reserva y, si se pudo intentar, lo resuelve con `outcome`. */
function attempt(throttle, email, client, outcome = 'failed') {
  const { wait, attempt: started } = throttle.begin(email, client);
  if (wait > 0) return wait;
  started[outcome]();
  return 0;
}
const fail = (throttle, email, client, times) => { for (let i = 0; i < times; i += 1) attempt(throttle, email, client); };
const ADA = 'ada@example.com';

describe('sequential attempts (behaviour unchanged)', () => {
  test('the first failures cost nothing; after PAIR_FREE the waits double', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    fail(throttle, ADA, '198.51.100.1', PAIR_FREE - 1);
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0);
    attempt(throttle, ADA, '198.51.100.1');
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 1000);
    c.advance(1000);
    attempt(throttle, ADA, '198.51.100.1');
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 2000);
    c.advance(2000);
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0, 'once waited, the next attempt is allowed');
  });

  test('an attempt made during the wait is refused and does not lengthen it', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    fail(throttle, ADA, '198.51.100.1', PAIR_FREE);
    assert.equal(attempt(throttle, ADA, '198.51.100.1'), 1000);
    assert.equal(attempt(throttle, ADA, '198.51.100.1'), 1000, 'still one second, not more');
  });

  test('the wait of one client never exceeds PAIR_MAX_DELAY_MS', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    for (let i = 0; i < ACCOUNT_FREE - 1; i += 1) {
      c.advance(PAIR_MAX_DELAY_MS);
      attempt(throttle, ADA, '198.51.100.1');
    }
    assert.equal(throttle.wait(ADA, '198.51.100.1'), PAIR_MAX_DELAY_MS);
  });

  test('one client failing does not make another client wait for the same account', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    fail(throttle, ADA, '203.0.113.66', PAIR_FREE);
    assert.ok(throttle.wait(ADA, '203.0.113.66') > 0);
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0, 'the owner, elsewhere, is not affected');
  });

  test('an attack spread over many clients slows the account down, but never for more than a minute', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    for (let i = 0; i < ACCOUNT_FREE + 30; i += 1) {
      c.advance(ACCOUNT_MAX_DELAY_MS);
      attempt(throttle, ADA, `198.51.100.${i % 250}`);
    }
    const wait = throttle.wait(ADA, '192.0.2.10');
    assert.ok(wait > 0 && wait <= ACCOUNT_MAX_DELAY_MS, `capped at one minute (${wait} ms)`);
    c.advance(ACCOUNT_MAX_DELAY_MS);
    assert.equal(throttle.wait(ADA, '192.0.2.10'), 0, 'the owner can try again after at most a minute');
  });

  test('a success clears the failures, so the next attempt is not delayed', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    fail(throttle, ADA, '198.51.100.1', PAIR_FREE);
    c.advance(1000);
    assert.equal(attempt(throttle, ADA, '198.51.100.1', 'succeeded'), 0);
    // Regression: the reservation of the successful attempt must not leave a wait behind.
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0);
    assert.equal(throttle.size, 0, 'nothing left to remember');
  });

  test('failures are forgotten some time after the last one', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    fail(throttle, ADA, '198.51.100.1', PAIR_FREE);
    c.advance(FORGET_AFTER_MS + 1);
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0);
    attempt(throttle, ADA, '198.51.100.1');
    assert.equal(throttle.wait(ADA, '198.51.100.1'), 0, 'counting starts again from one');
  });

  test('an email with an account and one without are treated alike', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    fail(throttle, 'exists@example.com', '198.51.100.1', PAIR_FREE);
    fail(throttle, 'nobody@example.com', '198.51.100.1', PAIR_FREE);
    assert.equal(throttle.wait('exists@example.com', '198.51.100.1'), throttle.wait('nobody@example.com', '198.51.100.1'));
  });
});

describe('concurrent attempts (D1)', () => {
  test('a burst from one client: only PAIR_FREE attempts get through before any of them finishes', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    const results = Array.from({ length: 12 }, () => throttle.begin(ADA, '198.51.100.9'));
    const started = results.filter((r) => r.attempt);
    assert.equal(started.length, PAIR_FREE);
    assert.ok(results.filter((r) => r.wait).every((r) => r.wait > 0));
    for (const r of started) r.attempt.failed();
    assert.ok(throttle.wait(ADA, '198.51.100.9') > 0);
  });

  test('a burst against one account from many clients: only ACCOUNT_FREE get through', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    const results = Array.from({ length: 60 }, (_, i) => throttle.begin(ADA, `203.0.113.${i + 1}`));
    assert.equal(results.filter((r) => r.attempt).length, ACCOUNT_FREE);
  });

  test('a correct password in flight with failures is not blocked by its own reservation', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    const wrong = Array.from({ length: PAIR_FREE - 1 }, () => throttle.begin(ADA, '198.51.100.9'));
    const right = throttle.begin(ADA, '198.51.100.9');
    assert.ok(right.attempt, 'there was room for it');
    right.attempt.succeeded();
    for (const r of wrong) r.attempt.failed();
    // The success did not wipe failures that happened while it was in flight…
    assert.equal(throttle.wait(ADA, '198.51.100.9'), 0, '4 real failures: still below the threshold');
    attempt(throttle, ADA, '198.51.100.9');
    assert.ok(throttle.wait(ADA, '198.51.100.9') > 0, '…so one more failure reaches it');
  });

  test('a success does not remove a wait that concurrent failures caused meanwhile', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    const owner = throttle.begin(ADA, '198.51.100.1');
    const attackers = Array.from({ length: ACCOUNT_FREE - 1 }, (_, i) => throttle.begin(ADA, `203.0.113.${i + 1}`));
    for (const r of attackers) r.attempt.failed();
    owner.attempt.succeeded();
    assert.equal(throttle.wait(ADA, '192.0.2.1'), 0, '19 failures, below ACCOUNT_FREE');
    attempt(throttle, ADA, '203.0.113.99');
    assert.ok(throttle.wait(ADA, '192.0.2.1') > 0, 'the attackers\' failures still count');
  });

  test('an internal error does not count as a wrong password', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    for (let i = 0; i < 50; i += 1) throttle.begin(ADA, '198.51.100.9').attempt.cancelled();
    assert.equal(throttle.wait(ADA, '198.51.100.9'), 0);
    assert.equal(throttle.size, 0);
  });

  test('settling an attempt twice has no further effect', () => {
    const throttle = createLoginThrottle({ now: clock().now });
    const { attempt: a } = throttle.begin(ADA, '198.51.100.9');
    a.failed();
    a.failed();
    a.succeeded();
    fail(throttle, ADA, '198.51.100.9', PAIR_FREE - 2);
    assert.equal(throttle.wait(ADA, '198.51.100.9'), 0, 'counted once: 4 failures in all');
  });
});

describe('memory bound (D4)', () => {
  test('filling the table never removes an active wait', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now, maxEntries: 20, overflowAttempts: 1000 });
    fail(throttle, 'victim@example.com', '203.0.113.1', PAIR_FREE);
    const before = throttle.wait('victim@example.com', '203.0.113.1');
    assert.ok(before > 0);
    // Regression: unrelated failures used to push the victim's entries out of the table.
    for (let i = 0; i < 200; i += 1) attempt(throttle, `filler${i}@example.com`, '198.51.100.200');
    assert.equal(throttle.wait('victim@example.com', '203.0.113.1'), before);
    assert.ok(throttle.size <= 20, `bounded (${throttle.size})`);
  });

  test('an attempt that needs two new entries never evicts the first one to make room for the second', () => {
    // Regression: the first entry, just created and not yet reserved, could be taken as inactive.
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now, maxEntries: 2, overflowAttempts: 0 });
    fail(throttle, 'victim@example.com', '203.0.113.1', PAIR_FREE); // its pair entry is active, its account entry is not
    const r = throttle.begin('new@example.com', '198.51.100.1');
    assert.ok(r.wait > 0, 'no room for both entries and no overflow share: it waits');
    assert.equal(throttle.size, 1, 'the half-made entry was rolled back, the inactive one evicted');
    assert.ok(throttle.wait('victim@example.com', '203.0.113.1') > 0, 'the active wait is still there');
  });

  test('with every entry active, a bounded overflow share applies, then a wait; the table never grows', () => {
    const throttle = createLoginThrottle({ now: clock().now, maxEntries: 10, overflowAttempts: 3 });
    // Five attempts in flight: ten entries, all of them active (pending).
    const inFlight = Array.from({ length: 5 }, (_, i) => throttle.begin(`busy${i}@example.com`, `203.0.113.${i}`));
    assert.equal(throttle.size, 10);
    const overflow = Array.from({ length: 5 }, (_, i) => throttle.begin(`new${i}@example.com`, '198.51.100.7'));
    assert.equal(overflow.filter((r) => r.attempt).length, 3, 'the overflow share');
    assert.ok(overflow.filter((r) => !r.attempt).every((r) => r.wait > 0 && r.wait <= OVERFLOW_WINDOW_MS), 'then a bounded wait');
    assert.equal(throttle.size, 10, 'no growth beyond the maximum');
    for (const r of [...inFlight, ...overflow]) r.attempt?.failed();
    assert.equal(throttle.size, 10, 'the in-flight attempts were still counted when they failed');
  });

  test('capacity comes back when the waits expire', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now, maxEntries: 2, overflowAttempts: 0 });
    fail(throttle, 'victim@example.com', '203.0.113.1', PAIR_FREE);
    assert.ok(throttle.begin('late@example.com', '198.51.100.7').wait > 0, 'no room and no overflow share');
    c.advance(1000); // the 1 s wait is over: that entry is inactive now
    const r = throttle.begin('late@example.com', '198.51.100.7');
    assert.ok(r.attempt, 'room again');
    r.attempt.failed();
    assert.ok(throttle.size <= 2);
  });

  test('the overflow share renews every window', () => {
    const throttle = createLoginThrottle({ now: clock().now, maxEntries: 2, overflowAttempts: 1 });
    const busy = throttle.begin('busy@example.com', '203.0.113.1'); // two active (pending) entries
    assert.ok(throttle.begin('a@example.com', '198.51.100.1').attempt, 'the one overflow attempt');
    assert.ok(throttle.begin('b@example.com', '198.51.100.1').wait > 0);
    busy.attempt.cancelled();
    assert.ok(throttle.begin('b@example.com', '198.51.100.1').attempt, 'once the busy entries are released, there is room');
  });

  test('without room, the overflow share comes back after OVERFLOW_WINDOW_MS', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now, maxEntries: 2, overflowAttempts: 1 });
    throttle.begin('busy@example.com', '203.0.113.1'); // stays in flight
    assert.ok(throttle.begin('a@example.com', '198.51.100.1').attempt);
    const refused = throttle.begin('b@example.com', '198.51.100.1');
    assert.equal(refused.wait, OVERFLOW_WINDOW_MS);
    c.advance(OVERFLOW_WINDOW_MS);
    assert.ok(throttle.begin('b@example.com', '198.51.100.1').attempt);
  });
});

describe('how an email is kept (HMAC with a key of each throttle)', () => {
  test('the stored digest is neither the email nor its plain SHA-256, which a list of emails would undo', () => {
    const throttle = createLoginThrottle();
    const digest = throttle.digest(ADA);
    assert.ok(!digest.includes(ADA) && !digest.includes('ada'));
    assert.notEqual(digest, createHash('sha256').update(ADA).digest('base64url'));
    assert.match(digest, /^[\w-]{43}$/, 'a 256-bit digest in base64url');
  });

  test('each throttle draws its own random key: the same email gives different digests', () => {
    assert.notEqual(createLoginThrottle().digest(ADA), createLoginThrottle().digest(ADA));
  });

  test('within one throttle the digest is stable, so the limits still apply to the account', () => {
    const c = clock();
    const throttle = createLoginThrottle({ now: c.now });
    assert.equal(throttle.digest(ADA), throttle.digest(ADA));
    fail(throttle, ADA, '198.51.100.1', PAIR_FREE);
    assert.ok(throttle.wait(ADA, '198.51.100.1') > 0, 'the account is recognised again');
  });

  test('with an injected key the digest is the documented HMAC-SHA-256, in base64url', () => {
    const key = Buffer.alloc(32, 7);
    assert.equal(createLoginThrottle({ key }).digest(ADA), accountDigest(ADA, key));
    assert.equal(accountDigest(ADA, key), createHmacReference(ADA, key));
  });
});

/** HMAC-SHA-256 written out with createHash, as RFC 2104 defines it, to check accountDigest independently. */
function createHmacReference(message, key) {
  const block = Buffer.alloc(64);
  key.copy(block);
  const pad = (byte) => Buffer.from(block.map((b) => b ^ byte));
  const inner = createHash('sha256').update(pad(0x36)).update(message).digest();
  return createHash('sha256').update(pad(0x5c)).update(inner).digest('base64url');
}
