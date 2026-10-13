// Inicio de sesión con Google y GitHub (OAuth 2.0, flujo de código de autorización).

import { randomBytes, timingSafeEqual } from 'node:crypto';
import express from 'express';
import rateLimit from 'express-rate-limit';
import { config } from './config.js';
import { pool } from './db.js';
import { readCookie, startSession } from './sessions.js';

const STATE_COOKIE = 'nexora_oauth_state';
const STATE_MINUTES = 10;

/** Fallo que se muestra al usuario: `code` viaja a /login?error=code y web/auth.js lo traduce. */
class OAuthError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

async function fetchJson(url, options) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(10_000) });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return response.json();
}

function bearer(token) {
  return { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json', 'User-Agent': 'nexora' } };
}

// profile() devuelve el email solo si el proveedor lo ha verificado; si no, null.
const PROVIDERS = {
  google: {
    authorizeUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
    tokenUrl: 'https://oauth2.googleapis.com/token',
    scope: 'openid email profile',
    async profile(token) {
      const info = await fetchJson('https://openidconnect.googleapis.com/v1/userinfo', bearer(token));
      return { id: info.sub, name: info.name, email: info.email_verified ? info.email : null };
    },
  },
  github: {
    authorizeUrl: 'https://github.com/login/oauth/authorize',
    tokenUrl: 'https://github.com/login/oauth/access_token',
    scope: 'read:user user:email',
    async profile(token) {
      const [user, emails] = await Promise.all([
        fetchJson('https://api.github.com/user', bearer(token)),
        fetchJson('https://api.github.com/user/emails', bearer(token)),
      ]);
      const primary = emails.find((entry) => entry.primary && entry.verified);
      return { id: String(user.id), name: user.name || user.login, email: primary?.email ?? null };
    },
  },
};

async function exchangeCode(provider, credentials, redirectUri, code) {
  const data = await fetchJson(provider.tokenUrl, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      client_id: credentials.clientId,
      client_secret: credentials.clientSecret,
      redirect_uri: redirectUri,
    }),
  });
  // GitHub responde 200 también cuando el código no es válido.
  if (typeof data.access_token !== 'string') throw new Error(`${provider.tokenUrl} no devolvió un token`);
  return data.access_token;
}

/** Usuario ya enlazado a esa identidad, o uno nuevo (o enlazado por email) si es la primera vez. */
async function userIdFor(providerName, profile) {
  const [linked] = await pool.execute(
    'SELECT user_id FROM oauth_accounts WHERE provider = ? AND provider_user_id = ?',
    [providerName, profile.id],
  );
  if (linked[0]) return linked[0].user_id;

  if (!profile.email) throw new OAuthError('email_unverified');
  const email = profile.email.toLowerCase();
  const name = (profile.name || email.split('@')[0]).trim().slice(0, 80);

  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const [existing] = await connection.execute(
      'SELECT id, password_hash FROM users WHERE email = ? FOR UPDATE',
      [email],
    );
    // El registro con contraseña no verifica el email, así que esa cuenta podría no ser de esta
    // persona: no se enlaza sola. Sin contraseña, la cuenta nació de otro proveedor que sí lo verificó.
    if (existing[0]?.password_hash) throw new OAuthError('account_exists');

    let userId = existing[0]?.id;
    if (!userId) {
      const [created] = await connection.execute('INSERT INTO users (name, email) VALUES (?, ?)', [name, email]);
      userId = created.insertId;
    }
    await connection.execute(
      'INSERT INTO oauth_accounts (provider, provider_user_id, user_id) VALUES (?, ?, ?)',
      [providerName, profile.id, userId],
    );
    await connection.commit();
    return userId;
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

function stateCookieOptions() {
  return { httpOnly: true, sameSite: 'lax', secure: config.production, path: '/api/auth' };
}

function sameState(received, expected) {
  const a = Buffer.from(received);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

function fail(res, code) {
  res.redirect(`/login?error=${code}`);
}

const attempts = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 40,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => fail(res, 'oauth_failed'),
});

export const oauth = express.Router();

for (const [name, provider] of Object.entries(PROVIDERS)) {
  const credentials = config.oauth[name];
  const redirectUri = `${config.publicUrl}/api/auth/${name}/callback`;

  oauth.get(`/${name}`, attempts, (req, res) => {
    if (!credentials) return fail(res, 'oauth_unavailable');

    const state = randomBytes(24).toString('base64url');
    res.cookie(STATE_COOKIE, state, { ...stateCookieOptions(), maxAge: STATE_MINUTES * 60 * 1000 });
    res.redirect(`${provider.authorizeUrl}?${new URLSearchParams({
      client_id: credentials.clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      scope: provider.scope,
      state,
    })}`);
  });

  oauth.get(`/${name}/callback`, attempts, async (req, res) => {
    const expected = readCookie(req, STATE_COOKIE);
    res.clearCookie(STATE_COOKIE, stateCookieOptions());
    if (!credentials) return fail(res, 'oauth_unavailable');

    const { code, state } = req.query;
    if (typeof state !== 'string' || !expected || !sameState(state, expected)) return fail(res, 'oauth_failed');
    // Sin código: la persona canceló en la pantalla del proveedor.
    if (typeof code !== 'string') return fail(res, 'oauth_cancelled');

    try {
      const token = await exchangeCode(provider, credentials, redirectUri, code);
      const userId = await userIdFor(name, await provider.profile(token));
      await startSession(res, userId);
      res.redirect('/');
    } catch (error) {
      if (!(error instanceof OAuthError)) console.error(error);
      fail(res, error instanceof OAuthError ? error.code : 'oauth_failed');
    }
  });
}
