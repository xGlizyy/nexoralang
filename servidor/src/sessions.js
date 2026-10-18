// Sesiones en base de datos. El navegador solo recibe un token aleatorio en una cookie HttpOnly.

import { createHash, randomBytes } from 'node:crypto';
import { config } from './config.js';
import { pool } from './db.js';

const SESSION_COOKIE = 'nexora_session';
const SESSION_DAYS = 30;

function hashToken(token) {
  return createHash('sha256').update(token).digest();
}

function cookieOptions() {
  return { httpOnly: true, sameSite: 'lax', secure: config.production, path: '/' };
}

export function readCookie(req, cookie) {
  for (const part of (req.headers.cookie ?? '').split(';')) {
    const [name, value] = part.trim().split('=');
    if (name === cookie && value) return value;
  }
  return null;
}

function readToken(req) {
  return readCookie(req, SESSION_COOKIE);
}

/**
 * Guarda una sesión nueva con `db` (el pool, o la conexión de una transacción) y devuelve su token.
 * No toca la respuesta: la cookie se pone con setSessionCookie cuando la sesión ya es definitiva.
 */
export async function createSession(db, userId) {
  const token = randomBytes(32).toString('base64url');
  await db.execute(
    'INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ? DAY))',
    [hashToken(token), userId, SESSION_DAYS],
  );
  return token;
}

export function setSessionCookie(res, token) {
  res.cookie(SESSION_COOKIE, token, { ...cookieOptions(), maxAge: SESSION_DAYS * 24 * 60 * 60 * 1000 });
}

export async function startSession(res, userId) {
  setSessionCookie(res, await createSession(pool, userId));
}

export async function currentUser(req) {
  const token = readToken(req);
  if (!token) return null;
  const [rows] = await pool.execute(
    `SELECT u.id, u.name, u.email
       FROM sessions s JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = ? AND s.expires_at > NOW()`,
    [hashToken(token)],
  );
  return rows[0] ?? null;
}

export async function endSession(req, res) {
  const token = readToken(req);
  if (token) await pool.execute('DELETE FROM sessions WHERE token_hash = ?', [hashToken(token)]);
  res.clearCookie(SESSION_COOKIE, cookieOptions());
}
