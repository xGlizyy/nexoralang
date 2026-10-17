// La aplicación de NEXORA: la web estática, la API de cuentas y la API del playground. index.js la
// arranca; las pruebas la construyen igual, sin escuchar en ningún puerto.

import express from 'express';
import { fileURLToPath } from 'node:url';
import { auth } from './auth.js';
import { loadCaptchaConfig } from './captcha.js';
import { config } from './config.js';
import { loadPlaygroundConfig } from './playground/config.js';
import { createPlaygroundRouter } from './playground/router.js';
import { pageFileHeaders, securityHeaders } from './security-headers.js';

const root = (relative) => fileURLToPath(new URL(`../../${relative}`, import.meta.url));

export function createApp({
  authRouter = auth,
  playgroundRouter = createPlaygroundRouter(loadPlaygroundConfig()),
  production = config.production,
  trustProxy = config.trustProxy,
  recaptcha = Boolean(loadCaptchaConfig().secret),
  log = console.error,
} = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', trustProxy);

  // Antes que cualquier ruta: las cabeceras llegan también a la API y a las respuestas de error.
  app.use(securityHeaders({ production }));

  app.use('/api/auth', authRouter);
  app.use('/api/playground', playgroundRouter);
  app.use('/api', (req, res) => res.status(404).json({ error: 'Route not found.' }));

  // Las páginas con política propia se reconocen por el archivo servido (security-headers.js).
  app.use(express.static(root('web'), { extensions: ['html'], setHeaders: pageFileHeaders({ recaptcha }) }));
  app.use('/docs', express.static(root('docs')));
  app.use('/ejemplos', express.static(root('ejemplos')));

  app.use((error, req, res, next) => {
    if (error.type === 'entity.parse.failed' || error.type === 'entity.too.large') {
      return res.status(400).json({ error: 'Invalid request.' });
    }
    log(error);
    res.status(500).json({ error: 'Internal server error.' });
  });

  return app;
}
