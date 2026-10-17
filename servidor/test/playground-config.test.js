// Activación del playground: desactivado si no se pide de forma explícita con PLAYGROUND_ENABLED=true.
// Estas pruebas usan la configuración real (loadPlaygroundConfig), no la de las demás pruebas, que lo
// activan siempre. Cada una deja process.env como lo encontró.

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import express from 'express';
import { loadPlaygroundConfig } from '../src/playground/config.js';
import { createPlaygroundRouter } from '../src/playground/router.js';
import { HELLO } from './helpers.js';

/** Ejecuta `body` con PLAYGROUND_ENABLED en `value` (undefined: sin definir) y restaura el valor anterior. */
async function withEnabled(value, body) {
  const had = Object.hasOwn(process.env, 'PLAYGROUND_ENABLED');
  const previous = process.env.PLAYGROUND_ENABLED;
  if (value === undefined) delete process.env.PLAYGROUND_ENABLED;
  else process.env.PLAYGROUND_ENABLED = value;
  try {
    return await body();
  } finally {
    if (had) process.env.PLAYGROUND_ENABLED = previous;
    else delete process.env.PLAYGROUND_ENABLED;
  }
}

/** Sirve el playground con la configuración real, en 127.0.0.1 y un puerto libre. */
async function serve(config) {
  const logs = [];
  const app = express();
  app.use('/api/playground', createPlaygroundRouter(config, { log: (line) => logs.push(line) }));
  const server = await new Promise((resolve) => {
    const listening = app.listen(0, '127.0.0.1', () => resolve(listening));
  });
  const base = `http://127.0.0.1:${server.address().port}/api/playground`;
  const call = async (route, body) => {
    const response = await fetch(`${base}${route}`, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    return { status: response.status, json: await response.json() };
  };
  return { logs, call, close: () => new Promise((resolve) => server.close(resolve)) };
}

describe('PLAYGROUND_ENABLED', () => {
  test('undefined: the playground is disabled', async () => {
    await withEnabled(undefined, () => assert.equal(loadPlaygroundConfig().enabled, false));
  });

  test('empty: the playground is disabled', async () => {
    await withEnabled('', () => assert.equal(loadPlaygroundConfig().enabled, false));
  });

  test('"false": the playground is disabled', async () => {
    await withEnabled('false', () => assert.equal(loadPlaygroundConfig().enabled, false));
  });

  test('"true": the playground is enabled', async () => {
    await withEnabled('true', () => assert.equal(loadPlaygroundConfig().enabled, true));
  });

  for (const value of ['True', 'TRUE', 'False', '1', '0', 'yes', 'no', 'on', ' true', 'true ', '"true"']) {
    test(`${JSON.stringify(value)} stops the server from starting`, async () => {
      await withEnabled(value, () => assert.throws(
        () => loadPlaygroundConfig(),
        { message: 'PLAYGROUND_ENABLED debe ser exactamente "true" o "false" (revisa servidor/.env)' },
      ));
    });
  }

  test('every test leaves process.env as it found it', async () => {
    const before = process.env.PLAYGROUND_ENABLED;
    await withEnabled('true', () => {});
    await withEnabled(undefined, () => {});
    await assert.rejects(withEnabled('true', () => { throw new Error('boom'); }), /boom/);
    assert.equal(process.env.PLAYGROUND_ENABLED, before);
  });
});

describe('the API with the real configuration', () => {
  test('without PLAYGROUND_ENABLED, /status says so, every other route answers 503 and no worker starts', async () => {
    await withEnabled(undefined, async () => {
      const server = await serve(loadPlaygroundConfig());
      try {
        assert.equal((await server.call('/status')).json.enabled, false);
        for (const [route, body] of [['/info'], ['/examples'], ['/check', { code: HELLO }], ['/run', { code: HELLO }]]) {
          const response = await server.call(route, body);
          assert.equal(response.status, 503, route);
          assert.equal(response.json.status, 'error', route);
          assert.equal(response.json.error.code, 'playground_disabled', route);
        }
        assert.deepEqual(server.logs, []);
      } finally {
        await server.close();
      }
    });
  });

  test('with PLAYGROUND_ENABLED=true, it runs programs with the real interpreter', async () => {
    await withEnabled('true', async () => {
      const server = await serve(loadPlaygroundConfig());
      try {
        assert.equal((await server.call('/status')).json.enabled, true);
        const info = await server.call('/info');
        assert.equal(info.status, 200);
        assert.equal(info.json.available, true);
        const run = await server.call('/run', { code: HELLO });
        assert.equal(run.status, 200);
        assert.equal(run.json.status, 'success');
        assert.equal(run.json.output, 'Hello from NEXORA\n');
      } finally {
        await server.close();
      }
    });
  });
});
