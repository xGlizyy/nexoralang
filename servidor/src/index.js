// Servidor de NEXORA: sirve la web estática, la API de cuentas y la API del playground.

import express from 'express';
import { fileURLToPath } from 'node:url';
import { auth } from './auth.js';
import { config } from './config.js';
import { listenWarnings } from './listen.js';
import { loadPlaygroundConfig } from './playground/config.js';
import { createPlaygroundRouter } from './playground/router.js';

const root = (relative) => fileURLToPath(new URL(`../../${relative}`, import.meta.url));

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', config.trustProxy);

app.use('/api/auth', auth);
app.use('/api/playground', createPlaygroundRouter(loadPlaygroundConfig()));
app.use('/api', (req, res) => res.status(404).json({ error: 'Route not found.' }));

// La página del playground muestra texto producido por programas ajenos. Además de escribirlo
// siempre como texto, se le prohíbe al navegador cargar o ejecutar nada que no venga de este sitio.
const playgroundPolicy = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

app.use((req, res, next) => {
  res.set('X-Content-Type-Options', 'nosniff');
  if (/^\/(playground|guide)(\.html)?$/.test(req.path)) {
    res.set('Content-Security-Policy', playgroundPolicy);
    res.set('Referrer-Policy', 'no-referrer');
  }
  next();
});

app.use(express.static(root('web'), { extensions: ['html'] }));
app.use('/docs', express.static(root('docs')));
app.use('/ejemplos', express.static(root('ejemplos')));

app.use((error, req, res, next) => {
  if (error.type === 'entity.parse.failed' || error.type === 'entity.too.large') {
    return res.status(400).json({ error: 'Invalid request.' });
  }
  console.error(error);
  res.status(500).json({ error: 'Internal server error.' });
});

for (const warning of listenWarnings(config)) console.error(`warning: ${warning}`);

// Sin LISTEN_HOST, en todas las interfaces, como siempre; con LISTEN_HOST, solo en esa dirección.
const server = config.host ? app.listen(config.port, config.host) : app.listen(config.port);
server.on('listening', () => {
  const { address, port } = server.address();
  console.log(`NEXORA en http://localhost:${port} (${config.environment}, escuchando en ${address === '::' || address === '0.0.0.0' ? 'todas las interfaces' : address})`);
});
