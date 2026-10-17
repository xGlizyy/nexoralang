// Rutas /api/auth: registro, inicio y cierre de sesión, y usuario actual. Google y GitHub están en oauth.js.

import express from 'express';
import { antispam, loadCaptchaConfig } from './captcha.js';
import { rateLimitKey } from './client-ip.js';
import { pool } from './db.js';
import { createLoginThrottle } from './login-throttle.js';
import { oauth } from './oauth.js';
import { hashPassword, verifyPassword } from './passwords.js';
import { clientRateLimit } from './rate-limits.js';
import { currentUser, endSession, startSession } from './sessions.js';

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 10;
const MAX_PASSWORD = 200;

// Se verifica contra este hash cuando el email no existe, para que la respuesta tarde lo mismo.
const DUMMY_HASH = await hashPassword('nexora');

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function publicUser({ id, name, email }) {
  return { id, name, email };
}

/**
 * Las rutas de cuentas. Las dependencias (base de datos, sesiones, contraseñas, antispam, freno
 * del login) se pueden sustituir en las pruebas; `auth`, más abajo, usa las reales.
 */
export function createAuthRouter({
  db = pool,
  sessions = { currentUser, endSession, startSession },
  passwords = { hashPassword, verifyPassword },
  captcha = loadCaptchaConfig(),
  throttle = createLoginThrottle(),
  attemptsLimit = 20,
  providers = oauth,
} = {}) {
  const attempts = clientRateLimit({
    windowMs: 15 * 60 * 1000,
    limit: attemptsLimit,
    message: { error: 'Too many attempts. Try again in a few minutes.' },
  });

  const router = express.Router();
  router.use(express.json({ limit: '10kb' }));
  if (providers) router.use(providers);

  router.post('/signup', attempts, antispam('signup', captcha), async (req, res) => {
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
      const [result] = await db.execute(
        'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
        [name, email, await passwords.hashPassword(password)],
      );
      userId = result.insertId;
    } catch (error) {
      // Revela que el email ya tiene cuenta. Evitarlo exige confirmar el email por correo, que el
      // sitio no envía: es una decisión pendiente (ver «Tareas pendientes y riesgos» en
      // nexora/docs/playground.md).
      if (error.code === 'ER_DUP_ENTRY') {
        return res.status(409).json({ error: 'An account with that email already exists.' });
      }
      throw error;
    }

    await sessions.startSession(res, userId);
    res.status(201).json({ user: publicUser({ id: userId, name, email }) });
  });

  router.post('/login', attempts, antispam('login', captcha), async (req, res) => {
    const email = text(req.body?.email).toLowerCase();
    const password = typeof req.body?.password === 'string' ? req.body.password : '';

    if (!email || !password || password.length > MAX_PASSWORD) {
      return res.status(400).json({ error: 'Enter your email and password.' });
    }

    // Freno por cuenta (login-throttle.js): igual para un email con cuenta y uno sin ella, y antes de
    // consultar la base de datos. begin() comprueba y reserva el intento en un solo paso, así que una
    // ráfaga de peticiones simultáneas no puede pasar entera antes de que se anote ningún fallo.
    const client = rateLimitKey(req);
    const { wait, attempt } = throttle.begin(email, client);
    if (wait > 0) {
      const seconds = Math.ceil(wait / 1000);
      res.set('Retry-After', String(seconds));
      return res.status(429).json({ error: `Too many failed attempts. Try again in ${seconds} seconds.`, code: 'login_throttled' });
    }

    let user;
    let valid;
    try {
      const [rows] = await db.execute(
        'SELECT id, name, email, password_hash FROM users WHERE email = ?',
        [email],
      );
      user = rows[0];
      // Las cuentas creadas con Google o GitHub no tienen contraseña y nunca entran por aquí.
      valid = await passwords.verifyPassword(password, user?.password_hash ?? DUMMY_HASH);
    } catch (error) {
      // Un fallo interno no demuestra que la contraseña sea incorrecta: el intento no cuenta.
      attempt.cancelled();
      throw error;
    }
    if (!user?.password_hash || !valid) {
      attempt.failed();
      return res.status(401).json({ error: 'Incorrect email or password.' });
    }

    attempt.succeeded();
    await sessions.startSession(res, user.id);
    res.json({ user: publicUser(user) });
  });

  router.post('/logout', async (req, res) => {
    await sessions.endSession(req, res);
    res.status(204).end();
  });

  router.get('/me', async (req, res) => {
    const user = await sessions.currentUser(req);
    res.json({ user: user ? publicUser(user) : null });
  });

  return router;
}

export const auth = createAuthRouter();
