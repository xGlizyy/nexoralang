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

/** Ejecuta `body` con estas variables (undefined: sin definir) y deja process.env como estaba. */
async function withEnv(values, body) {
  const before = Object.fromEntries(Object.keys(values).map((name) => [name, [Object.hasOwn(process.env, name), process.env[name]]]));
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  try {
    return await body();
  } finally {
    for (const [name, [had, value]] of Object.entries(before)) {
      if (had) process.env[name] = value;
      else delete process.env[name];
    }
  }
}

const CONTAINER = JSON.stringify(['docker', 'run', '--rm', '-i', '--init', '--pull', 'never', '--name', '{container}', '--network', 'none',
  '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '32', '--memory', '256m', '--memory-swap', '256m',
  '--cpus', '0.5', '--user', '65534:65534', '--tmpfs', '/tmp:rw,size=1m,noexec', 'nexora-worker']);
const PROCESS = JSON.stringify(['/srv/nexora/nexora/.venv/bin/python', '-I', '-m', 'nexora.worker']);
const ISOLATION = /PLAYGROUND_ENABLED=true en producción exige PLAYGROUND_WORKER_COMMAND con la orden de contenedor/;

describe('in production, the enabled playground needs the container command', () => {
  // Cada caso: [NODE_ENV, PLAYGROUND_ENABLED, PLAYGROUND_WORKER_COMMAND, resultado].
  const cases = [
    ['production', 'true', undefined, 'refused'],
    ['production', 'true', PROCESS, 'refused'],
    ['production', 'true', CONTAINER, 'container'],
    ['production', undefined, undefined, 'disabled'],
    ['production', 'false', undefined, 'disabled'],
    ['production', 'false', PROCESS, 'disabled'],
    ['development', 'true', undefined, 'process'],
    ['test', 'true', PROCESS, 'process'],
    [undefined, 'true', undefined, 'process'],
  ];
  for (const [environment, enabled, command, expected] of cases) {
    test(`NODE_ENV=${environment}, PLAYGROUND_ENABLED=${enabled}, ${command === undefined ? 'no worker command' : command === CONTAINER ? 'container command' : 'process command'}: ${expected}`, async () => {
      await withEnv({ NODE_ENV: environment, PLAYGROUND_ENABLED: enabled, PLAYGROUND_WORKER_COMMAND: command, NEXORA_PYTHON: undefined }, () => {
        if (expected === 'refused') {
          assert.throws(() => loadPlaygroundConfig(), ISOLATION);
          return;
        }
        const config = loadPlaygroundConfig();
        assert.equal(config.enabled, expected !== 'disabled');
        if (expected === 'container') assert.equal(config.workerCommand[0], 'docker');
        if (expected === 'process') assert.ok(config.workerCommand.includes('nexora.worker'));
      });
    });
  }

  test('an invalid container command is still refused with its own message, also in production', async () => {
    const wrong = JSON.stringify(JSON.parse(CONTAINER).filter((part) => part !== '--read-only'));
    await withEnv({ NODE_ENV: 'production', PLAYGROUND_ENABLED: 'true', PLAYGROUND_WORKER_COMMAND: wrong }, () => {
      assert.throws(() => loadPlaygroundConfig(), /no incluye antes de la imagen: "--read-only"/);
    });
  });

  test('the real server stops before listening, and before touching the database', async () => {
    // Un proceso aparte con src/index.js, sin servidor/.env: puerto 0, base de datos en un puerto
    // cerrado. Si el arranque no se detuviera, la prueba fallaría por el mensaje de escucha.
    const { spawn } = await import('node:child_process');
    const { fileURLToPath } = await import('node:url');
    const cwd = fileURLToPath(new URL('..', import.meta.url));
    const env = {
      PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, NODE_ENV: 'production', PLAYGROUND_ENABLED: 'true',
      PORT: '0', LISTEN_HOST: '127.0.0.1', DB_HOST: '127.0.0.1', DB_PORT: '1', DB_USER: 'test', DB_NAME: 'test',
    };
    const child = spawn(process.execPath, ['src/index.js'], { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => child.kill('SIGKILL'), 15_000);
    const code = await new Promise((resolve) => child.on('close', resolve));
    clearTimeout(timer);
    assert.notEqual(code, 0);
    assert.match(stderr, ISOLATION);
    assert.doesNotMatch(stdout, /NEXORA en http/);
    assert.doesNotMatch(stderr, /sessions:/, 'the session cleanup never started');
  });
});
