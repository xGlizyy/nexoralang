// Servidor de NEXORA: arranca la aplicación (app.js) y las tareas periódicas.

import { createApp } from './app.js';
import { captchaKeyWarnings, loadCaptchaConfig, readSiteKeyFile } from './captcha.js';
import { config } from './config.js';
import { pool } from './db.js';
import { listenWarnings } from './listen.js';
import { startSessionCleanup } from './session-cleanup.js';

const app = createApp();

// Las sesiones caducadas se borran al arrancar y cada hora (session-cleanup.js).
startSessionCleanup(pool);

for (const warning of listenWarnings(config)) console.error(`warning: ${warning}`);
// Las dos claves de reCAPTCHA se configuran en sitios distintos: se avisa si no van a la par. Si falta
// el archivo de la web, el servidor arranca igual (readSiteKeyFile nunca lanza).
const siteKey = readSiteKeyFile(new URL('../../web/js/consent-config.js', import.meta.url));
for (const warning of captchaKeyWarnings({ secret: loadCaptchaConfig().secret, siteKey })) console.error(`warning: ${warning}`);
// Sin NODE_ENV el servidor funciona como desarrollo (sin cookies solo-HTTPS ni HSTS): se dice siempre.
if (process.env.NODE_ENV === undefined) console.error('warning: NODE_ENV is not set: running as development');

// Sin LISTEN_HOST, en todas las interfaces, como siempre; con LISTEN_HOST, solo en esa dirección.
const server = config.host ? app.listen(config.port, config.host) : app.listen(config.port);
server.on('listening', () => {
  const { address, port } = server.address();
  console.log(`NEXORA en http://localhost:${port} (${config.environment}, escuchando en ${address === '::' || address === '0.0.0.0' ? 'todas las interfaces' : address})`);
});
