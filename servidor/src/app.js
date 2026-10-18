// La aplicación de NEXORA: la web estática, la API de cuentas y la API del playground. index.js la
// arranca; las pruebas la construyen igual, sin escuchar en ningún puerto.

import express from 'express';
import { fileURLToPath } from 'node:url';
import { auth } from './auth.js';
import { loadCaptchaConfig } from './captcha.js';
import { config } from './config.js';
import { loadPlaygroundConfig } from './playground/config.js';
import { createPlaygroundRouter } from './playground/router.js';
import { describeError, describeRoute } from './safe-log.js';
import { pageFileHeaders, securityHeaders } from './security-headers.js';

const root = (relative) => fileURLToPath(new URL(`../../${relative}`, import.meta.url));

// La plantilla de la ruta que lanzó un error. Se anota en un manejador de errores del propio montaje,
// donde Express aún conserva su baseUrl («/api/auth»); en el manejador final ya está vacío.
const ROUTE = Symbol('route');
const noteRoute = (error, req, res, next) => {
  req[ROUTE] ??= describeRoute(req);
  next(error);
};

export function createApp({
  authRouter = auth,
  playgroundRouter = createPlaygroundRouter(loadPlaygroundConfig()),
  production = config.production,
  trustProxy = config.trustProxy,
  recaptcha = Boolean(loadCaptchaConfig().secret),
  lifecycle = { draining: false },
  log = console.error,
} = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', trustProxy);

  // Antes que cualquier ruta: las cabeceras llegan también a la API y a las respuestas de error.
  app.use(securityHeaders({ production }));

  // Salud del PROCESO: que está en marcha y responde peticiones HTTP. No consulta MySQL, Google,
  // GitHub, reCAPTCHA ni el playground, y no dice nada de ellos. Durante el apagado (lifecycle.js)
  // responde 503, para que un balanceador o un monitor dejen de enviar peticiones.
  app.get('/api/health', (req, res) => {
    res.set('Cache-Control', 'no-store');
    if (lifecycle.draining) return res.status(503).json({ status: 'shutting_down' });
    res.json({ status: 'ok', checks: { http: 'ok' } });
  });

  app.use('/api/auth', authRouter, noteRoute);
  app.use('/api/playground', playgroundRouter, noteRoute);
  app.use('/api', (req, res) => res.status(404).json({ error: 'Route not found.' }));

  // Las páginas con política propia se reconocen por el archivo servido (security-headers.js).
  app.use(express.static(root('web'), { extensions: ['html'], setHeaders: pageFileHeaders({ recaptcha }) }));
  app.use('/docs', express.static(root('docs')));
  app.use('/ejemplos', express.static(root('ejemplos')));

  app.use((error, req, res, next) => {
    if (error.type === 'entity.parse.failed' || error.type === 'entity.too.large') {
      return res.status(400).json({ error: 'Invalid request.' });
    }
    // Al registro, la plantilla de la ruta, el tipo y un código conocido (safe-log.js): nunca el
    // camino pedido, la consulta, el mensaje ni la pila, que pueden llevar emails u otros datos.
    log(`error: ${req.method} ${req[ROUTE] ?? describeRoute(req)}: ${describeError(error)}`);
    res.status(500).json({ error: 'Internal server error.' });
  });

  return app;
}
