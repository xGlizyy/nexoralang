// NODE_ENV (src/environment.js): un solo criterio en todo el servidor, y un valor desconocido detiene
// el arranque antes de escuchar conexiones.

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, test } from 'node:test';
import { loadCaptchaConfig } from '../src/captcha.js';
import { ENVIRONMENTS, isProduction, parseNodeEnv } from '../src/environment.js';

describe('NODE_ENV', () => {
  test('each documented value is accepted as it is', () => {
    assert.deepEqual(ENVIRONMENTS, ['development', 'test', 'production']);
    for (const value of ENVIRONMENTS) assert.equal(parseNodeEnv(value), value);
    assert.equal(isProduction('production'), true);
    assert.equal(isProduction('development'), false);
    assert.equal(isProduction('test'), false);
  });

  test('unset keeps the documented default, development', () => {
    assert.equal(parseNodeEnv(undefined), 'development');
    assert.equal(isProduction(undefined), false);
  });

  test('any other spelling is a configuration error, never a silent development', () => {
    // Regression: "Production" used to be taken as development, without HTTPS-only cookies or HSTS.
    for (const value of ['Production', 'PRODUCTION', 'prod', 'producción', ' production', 'production ', '', 'dev', 'staging', 'true']) {
      assert.throws(() => parseNodeEnv(value), /NODE_ENV debe ser development, test o production/, JSON.stringify(value));
      assert.throws(() => isProduction(value), /NODE_ENV/, JSON.stringify(value));
    }
  });

  test('the reCAPTCHA configuration follows the same rule', () => {
    assert.equal(loadCaptchaConfig({ NODE_ENV: 'production' }).production, true);
    assert.equal(loadCaptchaConfig({ NODE_ENV: 'test' }).production, false);
    assert.throws(() => loadCaptchaConfig({ NODE_ENV: 'Production', RECAPTCHA_SECRET_KEY: 'x' }), /NODE_ENV/);
  });
});

/**
 * Arranca src/index.js de verdad, sin servidor/.env, con la base de datos en un puerto donde no hay
 * nada y escuchando solo en 127.0.0.1 en un puerto libre. Devuelve el código de salida y lo escrito,
 * o se detiene en cuanto el servidor dice que escucha.
 */
function startServer(nodeEnv) {
  const env = { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, DB_USER: 'test', DB_NAME: 'test', DB_HOST: '127.0.0.1', DB_PORT: '1', PORT: '0', LISTEN_HOST: '127.0.0.1' };
  if (nodeEnv !== undefined) env.NODE_ENV = nodeEnv;
  const child = spawn(process.execPath, [fileURLToPath(new URL('../src/index.js', import.meta.url))], { env });
  let output = '';
  return new Promise((resolve) => {
    const collect = (chunk) => {
      output += chunk;
      if (output.includes('NEXORA en')) child.kill();
    };
    child.stdout.on('data', collect);
    child.stderr.on('data', collect);
    child.on('exit', (code) => resolve({ code, output, listened: output.includes('NEXORA en') }));
  });
}

describe('starting the real server', () => {
  for (const value of ['Production', 'prod', '']) {
    test(`NODE_ENV=${JSON.stringify(value)} stops it before it listens`, async () => {
      const { code, output, listened } = await startServer(value);
      assert.notEqual(code, 0);
      assert.equal(listened, false, 'it never listened');
      assert.match(output, /NODE_ENV debe ser development, test o production/);
    });
  }

  test('NODE_ENV=test starts, and says which environment it runs in', async () => {
    const { listened, output } = await startServer('test');
    assert.equal(listened, true, output);
    assert.match(output, /NEXORA en http:\/\/localhost:\d+ \(test, escuchando en 127\.0\.0\.1\)/);
  });

  test('without NODE_ENV it starts as development and says so', async () => {
    const { listened, output } = await startServer(undefined);
    assert.equal(listened, true, output);
    assert.match(output, /NODE_ENV is not set: running as development/);
    assert.match(output, /\(development, escuchando en 127\.0\.0\.1\)/);
  });
});
