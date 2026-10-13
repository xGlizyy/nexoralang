// Utilidades de las pruebas del playground: arrancan la API real en un puerto libre.

import express from 'express';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { loadPlaygroundConfig } from '../src/playground/config.js';
import { createPlaygroundRouter } from '../src/playground/router.js';

export const repo = fileURLToPath(new URL('../../', import.meta.url));
export const examplesDir = path.join(repo, 'nexora', 'examples');
export const fakeWorker = (mode) => [
  process.execPath, fileURLToPath(new URL('./fixtures/fake-worker.js', import.meta.url)), mode,
];

/** Configuración real (el intérprete de nexora/.venv), con los cambios que pida cada prueba. */
export function testConfig(overrides = {}) {
  return {
    ...loadPlaygroundConfig(),
    // Por defecto, sin límite de peticiones que estorbe a las pruebas.
    rateLimit: { windowMs: 60_000, limit: 100_000 },
    ...overrides,
  };
}

/**
 * Arranca un servidor con las rutas del playground. Devuelve funciones para llamarlo
 * y `logs`, con todo lo que el servidor habría escrito en su registro.
 */
export async function startServer(overrides = {}) {
  const logs = [];
  const app = express();
  app.use('/api/playground', createPlaygroundRouter(testConfig(overrides), { log: (line) => logs.push(line) }));
  const server = await new Promise((resolve) => {
    const listening = app.listen(0, '127.0.0.1', () => resolve(listening));
  });
  const base = `http://127.0.0.1:${server.address().port}/api/playground`;

  const call = async (route, body, { headers = {}, raw } = {}) => {
    const response = await fetch(`${base}${route}`, {
      method: body === undefined && raw === undefined ? 'GET' : 'POST',
      headers: body === undefined && raw === undefined ? headers : { 'Content-Type': 'application/json', ...headers },
      body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
    const text = await response.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* se comprueba en la prueba */ }
    return { status: response.status, headers: response.headers, text, json };
  };

  return {
    base,
    logs,
    call,
    run: (code, extra = {}) => call('/run', { code, ...extra }),
    check: (code, extra = {}) => call('/check', { code, ...extra }),
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

export const HELLO = 'fn main() -> Void {\n    print("Hello from NEXORA")\n}\n';

/** Un programa que tarda varios segundos: muchas llamadas, poca profundidad. */
export const SLOW = [
  'fn fib(n: Int) -> Int {',
  '    if n < 2 {',
  '        return n',
  '    }',
  '    return fib(n - 1) + fib(n - 2)',
  '}',
  'fn main() -> Void {',
  '    print("started")',
  '    print(fib(40))',
  '}',
].join('\n');

export const inMain = (body) => `fn main() -> Void {\n${body.split('\n').map((line) => `    ${line}`).join('\n')}\n}\n`;
