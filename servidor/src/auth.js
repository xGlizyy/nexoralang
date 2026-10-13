// Rutas /api/auth: registro, inicio y cierre de sesión, y usuario actual. Google y GitHub están en oauth.js.

import express from 'express';
import rateLimit from 'express-rate-limit';
import { pool } from './db.js';
import { oauth } from './oauth.js';
import { hashPassword, verifyPassword } from './passwords.js';
import { currentUser, endSession, startSession } from './sessions.js';

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 10;
const MAX_PASSWORD = 200;

// Se verifica contra este hash cuando el email no existe, para que la respuesta tarde lo mismo.
const DUMMY_HASH = await hashPassword('nexora');

const attempts = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many attempts. Try again in a few minutes.' },
});

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function publicUser({ id, name, email }) {
  return { id, name, email };
}

export const auth = express.Router();

auth.use(express.json({ limit: '10kb' }));
auth.use(oauth);

auth.post('/signup', attempts, async (req, res) => {
  const name = text(req.body?.name);
  const email = text(req.body?.email).toLowerCase();
  const password = typeof req.body?.password === 'string' ? req.body.password : '';

  if (name.length < 1 || name.length > 80) {
    return res.status(400).json({ error: 'Enter a name of up to 80 characters.' });
  }
  if (email.length > 254 || !EMAIL.test(email)) {
    return res.status(400).json({ error: 'Enter a valid email address.' });
  }
  if (password.length < MIN_PASSWORD || password.length > MAX_PASSWORD) {
    return res.status(400).json({ error: `The password must be at least ${MIN_PASSWORD} characters long.` });
  }

  let userId;
  try {
    const [result] = await pool.execute(
      'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
      [name, email, await hashPassword(password)],
    );
    userId = result.insertId;
  } catch (error) {
    if (error.code === 'ER_DUP_ENTRY') {
      return res.status(409).json({ error: 'An account with that email already exists.' });
    }
    throw error;
  }

  await startSession(res, userId);
  res.status(201).json({ user: publicUser({ id: userId, name, email }) });
});

auth.post('/login', attempts, async (req, res) => {
  const email = text(req.body?.email).toLowerCase();
  const password = typeof req.body?.password === 'string' ? req.body.password : '';

  if (!email || !password || password.length > MAX_PASSWORD) {
    return res.status(400).json({ error: 'Enter your email and password.' });
  }

  const [rows] = await pool.execute(
    'SELECT id, name, email, password_hash FROM users WHERE email = ?',
    [email],
  );
  const user = rows[0];
  // Las cuentas creadas con Google o GitHub no tienen contraseña y nunca entran por aquí.
  const valid = await verifyPassword(password, user?.password_hash ?? DUMMY_HASH);
  if (!user?.password_hash || !valid) {
    return res.status(401).json({ error: 'Incorrect email or password.' });
  }

  await startSession(res, user.id);
  res.json({ user: publicUser(user) });
});

auth.post('/logout', async (req, res) => {
  await endSession(req, res);
  res.status(204).end();
});

auth.get('/me', async (req, res) => {
  const user = await currentUser(req);
  res.json({ user: user ? publicUser(user) : null });
});
