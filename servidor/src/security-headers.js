// Cabeceras de seguridad de todas las respuestas: páginas, API y errores.
//
// Las páginas no tienen scripts, estilos ni manejadores en línea (servidor/test/web-guide.test.js lo
// comprueba), y el JavaScript solo cambia estilos con la API del DOM (style.setProperty), que la CSP
// permite. Por eso la política base no necesita 'unsafe-inline' ni 'unsafe-eval': solo se carga lo
// que viene de este sitio.

import path from 'node:path';

// La política que ya tenían el playground y la guía, ahora la de todas las páginas.
const PAGE_DIRECTIVES = {
  'default-src': ["'self'"],
  'script-src': ["'self'"],
  'style-src': ["'self'"],
  // Las tipografías se sirven desde el propio sitio (web/fonts/): ningún tercero recibe la visita.
  'font-src': ["'self'"],
  'img-src': ["'self'", 'data:'],
  'connect-src': ["'self'"],
  'object-src': ["'none'"],
  'base-uri': ["'self'"],
  'form-action': ["'self'"],
  'frame-ancestors': ["'none'"],
};

// Lo mínimo que Google indica para reCAPTCHA: su script (www.google.com/recaptcha/ y
// www.gstatic.com/recaptcha/) y el iframe invisible con que trabaja reCAPTCHA v3. Solo en las páginas
// con un formulario protegido, y solo si el servidor tiene RECAPTCHA_SECRET_KEY. **Sin comprobar
// todavía con claves reales de Google.**
const RECAPTCHA_SCRIPTS = ['https://www.google.com/recaptcha/', 'https://www.gstatic.com/recaptcha/'];
const RECAPTCHA_FRAMES = ['https://www.google.com/recaptcha/', 'https://recaptcha.google.com/recaptcha/'];

// Las respuestas de la API son JSON o redirecciones: no tienen por qué cargar nada.
export const API_POLICY = "default-src 'none'; frame-ancestors 'none'";

// Las páginas con política propia se reconocen por el ARCHIVO que se sirve, no por la URL pedida
// (pageFileHeaders, más abajo): /login, /login.html, /logi%6E.html o, en Windows, /LOGIN llevan al
// mismo archivo, y por tanto a la misma política. Comparar la URL en bruto dejaba fuera las variantes.
const AUTH_FILES = new Set(['login.html', 'signup.html']);
// Páginas que no envían el Referer a ningún sitio: muestran código escrito por otras personas.
const NO_REFERRER_FILES = new Set(['playground.html', 'guide.html']);

function serialize(directives) {
  return Object.entries(directives).map(([name, sources]) => `${name} ${sources.join(' ')}`).join('; ');
}

/** La CSP de una página; con `recaptcha`, la de las páginas con formulario protegido. */
export function pagePolicy({ recaptcha = false } = {}) {
  if (!recaptcha) return serialize(PAGE_DIRECTIVES);
  return serialize({
    ...PAGE_DIRECTIVES,
    'script-src': [...PAGE_DIRECTIVES['script-src'], ...RECAPTCHA_SCRIPTS],
    'frame-src': RECAPTCHA_FRAMES,
  });
}

// Un año. Sin includeSubDomains ni preload: afectarían a otros subdominios del titular, y esa es una
// decisión de despliegue que no se deduce del repositorio.
export const HSTS = 'max-age=31536000';

/**
 * Middleware de cabeceras de TODAS las respuestas (páginas, API, errores, rutas inexistentes), con
 * la política genérica. `production` viene de la configuración del servidor. HSTS solo se envía en
 * producción y en una petición que llegó por HTTPS (req.secure: con nginx delante, gracias a
 * X-Forwarded-Proto y a TRUST_PROXY); nunca en desarrollo por HTTP.
 */
export function securityHeaders({ production = false } = {}) {
  const page = pagePolicy();
  return (req, res, next) => {
    res.set('X-Content-Type-Options', 'nosniff');
    // frame-ancestors 'none' en la CSP, y X-Frame-Options para los navegadores que no la entienden.
    res.set('X-Frame-Options', 'DENY');
    res.set('Referrer-Policy', 'strict-origin-when-cross-origin');
    // Otra ventana abierta desde este sitio, o que lo abra, no puede manipularlo (window.opener).
    res.set('Cross-Origin-Opener-Policy', 'same-origin');
    // Funciones del navegador que el sitio no usa.
    res.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()');
    res.set('Content-Security-Policy', req.path === '/api' || req.path.startsWith('/api/') ? API_POLICY : page);
    if (production && req.secure) res.set('Strict-Transport-Security', HSTS);
    next();
  };
}

/**
 * setHeaders de express.static para web/: ajusta la política según el archivo que de verdad se va
 * a servir. `send` lo llama con la ruta ya decodificada (una sola vez) y resuelta dentro de web/, y
 * antes de decidir una respuesta 304, así que también esa la lleva. Compara solo el nombre del
 * archivo, sin mayúsculas: en Windows /LOGIN sirve login.html; en Linux esa URL no existe (404).
 * Solo puede cambiar la política de la genérica a la de una página concreta, nunca relajarla para
 * otra cosa: la de login y registro añade únicamente reCAPTCHA, y solo con `recaptcha`.
 */
export function pageFileHeaders({ recaptcha = false } = {}) {
  const auth = pagePolicy({ recaptcha });
  return (res, file) => {
    const name = path.basename(file).toLowerCase();
    if (AUTH_FILES.has(name)) res.set('Content-Security-Policy', auth);
    if (NO_REFERRER_FILES.has(name)) res.set('Referrer-Policy', 'no-referrer');
  };
}
