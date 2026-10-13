// Contraseñas con scrypt (incluido en Node). Formato guardado: scrypt$N$r$p$sal$hash

import { randomBytes, scrypt, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';

const scryptAsync = promisify(scrypt);

const PARAMS = { N: 32768, r: 8, p: 1 };
const KEY_LENGTH = 32;
const MAX_MEMORY = 64 * 1024 * 1024;

function derive(password, salt, { N, r, p }, length) {
  return scryptAsync(password, salt, length, { N, r, p, maxmem: MAX_MEMORY });
}

export async function hashPassword(password) {
  const salt = randomBytes(16);
  const hash = await derive(password, salt, PARAMS, KEY_LENGTH);
  const { N, r, p } = PARAMS;
  return ['scrypt', N, r, p, salt.toString('base64'), hash.toString('base64')].join('$');
}

export async function verifyPassword(password, stored) {
  const [scheme, N, r, p, salt, hash] = stored.split('$');
  if (scheme !== 'scrypt' || !hash) return false;
  const expected = Buffer.from(hash, 'base64');
  const actual = await derive(
    password,
    Buffer.from(salt, 'base64'),
    { N: Number(N), r: Number(r), p: Number(p) },
    expected.length,
  );
  return timingSafeEqual(actual, expected);
}
