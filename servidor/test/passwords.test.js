// Contraseñas con scrypt (src/passwords.js), con la implementación real: sin dobles.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import { hashPassword, verifyPassword } from '../src/passwords.js';

const PASSWORD = 'correct horse battery staple';

describe('hashPassword', () => {
  test('stores scrypt, its parameters, a salt and the hash, never the password', async () => {
    const stored = await hashPassword(PASSWORD);
    const [scheme, N, r, p, salt, hash, ...rest] = stored.split('$');
    assert.deepEqual([scheme, N, r, p, rest], ['scrypt', '32768', '8', '1', []]);
    assert.equal(Buffer.from(salt, 'base64').length, 16);
    assert.equal(Buffer.from(hash, 'base64').length, 32);
    assert.ok(!stored.includes(PASSWORD));
    // Cabe en la columna users.password_hash (VARCHAR(255)).
    assert.ok(stored.length <= 255, String(stored.length));
  });

  test('the same password gets a different salt, and so a different hash, every time', async () => {
    const [a, b] = await Promise.all([hashPassword(PASSWORD), hashPassword(PASSWORD)]);
    assert.notEqual(a, b);
    assert.notEqual(a.split('$')[4], b.split('$')[4]);
    assert.equal(await verifyPassword(PASSWORD, a), true);
    assert.equal(await verifyPassword(PASSWORD, b), true);
  });
});

describe('verifyPassword', () => {
  test('accepts the right password and refuses any other', async () => {
    const stored = await hashPassword(PASSWORD);
    assert.equal(await verifyPassword(PASSWORD, stored), true);
    for (const wrong of ['', 'correct horse battery stapl', `${PASSWORD} `, PASSWORD.toUpperCase(), 'x'.repeat(200)]) {
      assert.equal(await verifyPassword(wrong, stored), false, JSON.stringify(wrong));
    }
  });

  test('the limits of the account form: 10 and 200 characters, and text beyond ASCII', async () => {
    for (const password of ['a'.repeat(10), 'b'.repeat(200), 'contraseña ñandú 🔐 éèê']) {
      const stored = await hashPassword(password);
      assert.equal(await verifyPassword(password, stored), true, password);
      assert.equal(await verifyPassword(password.slice(0, -1), stored), false, password);
    }
  });

  test('a hash made with other scrypt parameters is checked with its own parameters', async () => {
    // Si un día cambian los parámetros, las contraseñas guardadas con los anteriores siguen valiendo.
    const { scrypt } = await import('node:crypto');
    const salt = Buffer.alloc(16, 7);
    const hash = await new Promise((resolve, reject) => scrypt(PASSWORD, salt, 32, { N: 16384, r: 8, p: 1 }, (error, key) => (error ? reject(error) : resolve(key))));
    const stored = ['scrypt', 16384, 8, 1, salt.toString('base64'), hash.toString('base64')].join('$');
    assert.equal(await verifyPassword(PASSWORD, stored), true);
    assert.equal(await verifyPassword('another one', stored), false);
  });

  test('a stored value that is not in the format of hashPassword is never a match', async () => {
    const stored = await hashPassword(PASSWORD);
    const fields = stored.split('$');
    const malformed = {
      empty: '',
      'plain text': 'not-a-hash',
      'another scheme': ['bcrypt', ...fields.slice(1)].join('$'),
      'a bcrypt hash': '$2b$10$abcdefghijklmnopqrstuuJ3bCJxUuWl9cH5r8eXr3dO2ZbW3fQe',
      'without the hash': fields.slice(0, 5).join('$'),
      'with an empty hash': [...fields.slice(0, 5), ''].join('$'),
      'with an extra field': `${stored}$extra`,
      'with an empty salt': [...fields.slice(0, 4), '', fields[5]].join('$'),
      'the hash of another password': [...fields.slice(0, 5), Buffer.alloc(32).toString('base64')].join('$'),
    };
    for (const [name, value] of Object.entries(malformed)) {
      assert.equal(await verifyPassword(PASSWORD, value), false, name);
    }
  });

  test('impossible scrypt parameters (a damaged hash) are an error, not a wrong password', async () => {
    const fields = (await hashPassword(PASSWORD)).split('$');
    const withN = (N) => ['scrypt', N, ...fields.slice(2)].join('$');
    // N no es potencia de dos; N enorme pasaría del tope de memoria (MAX_MEMORY) en vez de usarla.
    for (const N of ['1000', String(2 ** 30), 'abc']) {
      await assert.rejects(verifyPassword(PASSWORD, withN(N)), N);
    }
  });
});
