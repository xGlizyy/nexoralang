// Apagado ordenado (src/lifecycle.js). Nunca hay una base de datos real ni se usa el puerto 3000: todos
// los servidores HTTP escuchan en 127.0.0.1, en un puerto libre que elige el sistema.
//   - En este proceso: createShutdown con servidores HTTP reales y un pool y un borrado de sesiones
//     simulados; y, con setTimeout y clearTimeout simulados, el límite de cada espera.
//   - En un proceso aparte: src/index.js de verdad (sin servidor/.env, con PORT=0 y
//     LISTEN_HOST=127.0.0.1, la base de datos en un puerto cerrado y el playground desactivado), al
//     que test/fixtures/signal-bridge.js, cargado con --import, le hace llegar SIGTERM o SIGINT como un
//     evento de process; y test/fixtures/shutdown-child.js, un apagado con process.exit de verdad y un
//     pool simulado.
// Las señales del sistema operativo no se prueban: en Windows, matar un proceso no ejecuta sus
// manejadores, y el puente solo emite el evento.

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import http from 'node:http';
import { describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createShutdown } from '../src/lifecycle.js';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Un servidor real con una ruta /slow que tarda `slow` ms (o no termina nunca, con Infinity) o, si
 * `slow` es una promesa, que responde cuando se cumple. `arrived(n)` se cumple cuando el servidor ya ha
 * recibido n peticiones: así una prueba sabe que están en curso sin esperar un tiempo fijo.
 */
async function realServer(slow) {
  let seen = 0;
  const server = http.createServer((req, res) => {
    seen += 1;
    if (req.url === '/slow') {
      if (slow instanceof Promise) slow.then(() => res.end('done'));
      else if (slow !== Infinity) setTimeout(() => res.end('done'), slow);
      return;
    }
    res.end('fast');
  });
  const arrived = (n) => new Promise((resolve) => {
    const check = () => {
      if (seen < n) return;
      server.off('request', check);
      resolve();
    };
    server.on('request', check);
    check();
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address(); // después de cerrar, address() ya no lo dice
  return { server, arrived, url: (path) => `http://127.0.0.1:${port}${path}` };
}

/** Lo que pasa durante un apagado, en orden. */
function recorder() {
  const events = [];
  const logs = [];
  let exitCode;
  return {
    events,
    logs,
    get exitCode() { return exitCode; },
    options: {
      onDraining: () => events.push('draining'),
      stopCleanup: () => events.push('cleanup stopped'),
      closePool: async () => { events.push('pool closed'); },
      log: (line) => logs.push(line),
      exit: (code) => { events.push(`exit ${code}`); exitCode = code; },
    },
  };
}

/** Una petición que no rechaza: el resultado o el código del error. */
const request = (url) => fetch(url).then((response) => response.text(), (error) => error.cause?.code ?? error.name);

describe('shutdown', () => {
  test('in order: health draining, cleanup stopped, server closed, pool closed, exit 0', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    await createShutdown({ server, ...r.options })('SIGTERM');
    assert.deepEqual(r.events, ['draining', 'cleanup stopped', 'pool closed', 'exit 0']);
    assert.equal(server.listening, false);
    assert.match(r.logs[0], /^shutdown: SIGTERM: no new connections/);
    assert.equal(r.logs.at(-1), 'shutdown: done');
  });

  test('a request in progress finishes; a new connection is refused', async () => {
    // La respuesta lenta llega cuando la prueba lo decide, no tras un tiempo fijo.
    let release;
    const { server, url, arrived } = await realServer(new Promise((resolve) => { release = resolve; }));
    const r = recorder();
    const slow = request(url('/slow'));
    await arrived(1); // la petición ya está en curso
    const done = createShutdown({ server, ...r.options })('SIGTERM');
    assert.equal(await request(url('/fast')), 'ECONNREFUSED');
    assert.equal(r.exitCode, undefined, 'it does not exit while the request is in progress');
    release();
    assert.equal(await slow, 'done');
    await done;
    assert.equal(r.exitCode, 0);
  });

  test('a request that never ends is cut at the time limit, and the exit code says so', async () => {
    const { server, url, arrived } = await realServer(Infinity);
    const r = recorder();
    const hanging = request(url('/slow'));
    await arrived(1);
    const started = Date.now();
    await createShutdown({ server, ...r.options, timeoutMs: 300 })('SIGTERM');
    assert.ok(Date.now() - started < 2000);
    assert.equal(r.exitCode, 1);
    assert.ok(r.logs.some((line) => /requests still in progress after 300 ms; closing their connections/.test(line)), r.logs.join('\n'));
    assert.notEqual(await hanging, 'done');
    assert.ok(r.events.includes('pool closed'), 'the pool is closed even then');
  });

  test('a second signal does not shut down twice', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    let closes = 0;
    const close = server.close.bind(server);
    server.close = (callback) => { closes += 1; return close(callback); };
    const shutdown = createShutdown({ server, ...r.options });
    const first = shutdown('SIGTERM');
    const second = shutdown('SIGINT');
    assert.equal(first, second);
    await first;
    assert.equal(closes, 1);
    assert.deepEqual(r.events.filter((event) => event.startsWith('exit')), ['exit 0']);
  });

  test('a pool that fails to close: exit 1, with a log line without the error message', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const closePool = async () => { throw Object.assign(new Error('Access denied for user test@ana.example (using password: YES)'), { code: 'ER_ACCESS_DENIED_ERROR' }); };
    await createShutdown({ server, ...r.options, closePool })('SIGTERM');
    assert.equal(r.exitCode, 1);
    assert.ok(r.logs.includes('shutdown: could not close the database pool (Error ER_ACCESS_DENIED_ERROR)'), r.logs.join('\n'));
    assert.ok(!r.logs.join('\n').includes('ana.example'));
  });

  test('a pool that never closes does not keep the process waiting', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const started = Date.now();
    // Sin nada más vivo: el propio límite tiene que mantener vivo el proceso hasta que salte.
    await createShutdown({ server, ...r.options, closePool: () => new Promise(() => {}), timeoutMs: 200 })('SIGTERM');
    assert.ok(Date.now() - started < 2000);
    assert.equal(r.exitCode, 1);
    assert.ok(r.logs.includes('shutdown: the database pool did not close within 200 ms'));
  });

  test('a server that was not running, or background tasks that fail: it still finishes', async () => {
    const server = http.createServer();
    const r = recorder();
    const stopCleanup = () => { throw new Error('boom'); };
    await createShutdown({ server, ...r.options, stopCleanup })('SIGINT');
    assert.equal(r.exitCode, 1);
    assert.ok(r.logs.some((line) => /could not stop the background tasks \(Error\)/.test(line)));
    assert.ok(r.logs.some((line) => /did not close cleanly \(Error ERR_SERVER_NOT_RUNNING\)/.test(line)));
    assert.ok(r.events.includes('pool closed'));
  });

  test('if marking the server as draining fails, the session cleanup is still stopped: exit 1', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const onDraining = () => { throw new Error('draining failed for ana@example.com'); };
    await createShutdown({ server, ...r.options, onDraining })('SIGTERM');
    assert.deepEqual(r.events, ['cleanup stopped', 'pool closed', 'exit 1']);
    assert.ok(r.logs.includes('shutdown: could not mark the server as draining (Error)'), r.logs.join('\n'));
    assert.ok(!r.logs.join('\n').includes('ana@example.com'));
    assert.equal(server.listening, false);
  });
});

/**
 * Arranca src/index.js en un proceso aparte, con el puente de señales (fixtures/signal-bridge.js), sin
 * servidor/.env, en 127.0.0.1 y un puerto libre, con la base de datos en un puerto cerrado y el
 * playground desactivado. Devuelve el proceso, la dirección y lo que escribe.
 */
async function startRealServer(signal) {
  const { spawn } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url');
  const cwd = fileURLToPath(new URL('..', import.meta.url));
  const env = {
    PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, NODE_ENV: 'development', PORT: '0', LISTEN_HOST: '127.0.0.1',
    DB_HOST: '127.0.0.1', DB_PORT: '1', DB_USER: 'test', DB_NAME: 'test', PLAYGROUND_ENABLED: 'false',
  };
  const child = spawn(process.execPath, ['--import', './test/fixtures/signal-bridge.js', 'src/index.js'], {
    cwd, env, stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  });
  const out = { stdout: '', stderr: '' };
  child.stdout.on('data', (chunk) => { out.stdout += chunk; });
  child.stderr.on('data', (chunk) => { out.stderr += chunk; });
  const exited = new Promise((resolve) => child.on('exit', (code) => resolve(code)));
  const killer = setTimeout(() => child.kill('SIGKILL'), 20_000);
  exited.then(() => clearTimeout(killer));
  for (let i = 0; i < 200 && !/NEXORA en http:\/\/localhost:\d+/.test(out.stdout); i++) await sleep(50);
  const port = out.stdout.match(/NEXORA en http:\/\/localhost:(\d+)/)?.[1];
  assert.ok(port, `the server did not start: ${out.stderr}`);
  return { child, out, exited, base: `http://127.0.0.1:${port}`, signal: () => child.send(signal) };
}

describe('src/index.js, the real server in a process of its own', () => {
  test('SIGTERM with a request in progress: it ends, says Connection: close, and the process exits 0', async () => {
    const server = await startRealServer('SIGTERM');
    // Nada más arrancar: la primera petición ya la sigue el apagado. El cuerpo se envía en dos partes:
    // la segunda, solo cuando el apagado ya ha empezado. Así la petición está en curso al llegar la
    // señal, sin depender de lo que tarde nada. Después, el registro falla al conectar con la base de
    // datos, que no existe: un 500.
    const message = (key) => new Promise((resolve) => {
      const check = (value) => {
        if (value?.[key] === undefined) return;
        server.child.off('message', check);
        resolve(value);
      };
      server.child.on('message', check);
    });
    const body = JSON.stringify({ name: 'Ana', email: 'ana@example.com', password: 'a-test-password-only' });
    const arrived = message('request');
    // Un cliente que pide keep-alive: si la respuesta dice «close», lo ha decidido el apagado.
    const agent = new http.Agent({ keepAlive: true });
    let req;
    const signup = new Promise((resolve, reject) => {
      req = http.request(`${server.base}/api/auth/signup`, {
        method: 'POST', agent, headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      }, (res) => {
        res.resume();
        res.on('end', () => resolve(res));
      });
      req.on('error', reject);
    });
    req.write(body.slice(0, 10));
    await arrived;
    const signalled = message('signalled');
    const started = Date.now();
    server.signal();
    assert.deepEqual(await signalled, { signalled: 'SIGTERM' });
    req.end(body.slice(10));
    const response = await signup;
    const code = await server.exited;
    agent.destroy();
    assert.equal(response.statusCode, 500);
    assert.equal(response.headers.connection, 'close');
    assert.equal(code, 0, server.out.stderr);
    assert.ok(Date.now() - started < 5000);
    assert.match(server.out.stderr, /shutdown: SIGTERM: no new connections/);
    assert.match(server.out.stderr, /shutdown: done\n/);
    assert.match(server.out.stderr, /error: POST \/api\/auth\/signup: Error ECONNREFUSED/);
    assert.ok(!server.out.stderr.includes('ana@example.com') && !server.out.stderr.includes('a-test-password-only'));
  });

  test('SIGINT with nothing in progress: /api/health was ok, and the process exits 0 at once', async () => {
    const server = await startRealServer('SIGINT');
    const health = await fetch(`${server.base}/api/health`, { headers: { Connection: 'close' } });
    assert.deepEqual(await health.json(), { status: 'ok', checks: { http: 'ok' } });
    const started = Date.now();
    server.signal();
    assert.equal(await server.exited, 0, server.out.stderr);
    assert.ok(Date.now() - started < 3000);
    assert.match(server.out.stderr, /shutdown: SIGINT: no new connections/);
  });
});

describe('shutdown with keep-alive connections and the session cleanup', () => {
  test('a keep-alive connection does not hold the shutdown: the answer says Connection: close', async () => {
    // El caso medido: después de close(), una respuesta en curso decía keep-alive y la conexión
    // seguía abierta hasta keepAliveTimeout (5 s). Con un límite de 3 s, el apagado acababa en 1.
    const { server, url, arrived } = await realServer(400);
    const r = recorder();
    const shutdown = createShutdown({ server, ...r.options, timeoutMs: 3000 });
    const agent = new http.Agent({ keepAlive: true });
    const viaAgent = new Promise((resolve, reject) => {
      http.get(url('/slow'), { agent }, (res) => {
        res.resume();
        res.on('end', () => resolve(res.headers.connection));
      }).on('error', reject);
    });
    const viaFetch = fetch(url('/slow')).then(async (response) => { await response.text(); return response.headers.get('connection'); });
    await arrived(2); // las dos peticiones ya están en curso
    const started = Date.now();
    await shutdown('SIGTERM');
    const elapsed = Date.now() - started;
    const headers = [await viaAgent, await viaFetch];
    agent.destroy();
    assert.deepEqual(headers, ['close', 'close']);
    assert.equal(r.exitCode, 0, r.logs.join('\n'));
    assert.ok(elapsed < 1500, `the shutdown took ${elapsed} ms`);
  });

  test('the pool is closed only after the session cleanup in flight has ended', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const stopCleanup = () => {
      r.events.push('cleanup stopping');
      return sleep(200).then(() => r.events.push('cleanup ended'));
    };
    await createShutdown({ server, ...r.options, stopCleanup })('SIGTERM');
    assert.deepEqual(r.events, ['draining', 'cleanup stopping', 'cleanup ended', 'pool closed', 'exit 0']);
  });

  test('a session cleanup that does not end in time: the pool closes anyway, exit 1, and the log says so', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const started = Date.now();
    // Sin nada más vivo: el propio límite tiene que mantener vivo el proceso hasta que salte.
    await createShutdown({ server, ...r.options, stopCleanup: () => new Promise(() => {}), timeoutMs: 200 })('SIGTERM');
    assert.ok(Date.now() - started < 2000);
    assert.equal(r.exitCode, 1);
    assert.ok(r.events.includes('pool closed'));
    assert.ok(r.logs.includes('shutdown: the session cleanup did not end within 200 ms; closing the database pool anyway'), r.logs.join('\n'));
  });

  test('a session cleanup that fails while stopping: logged without its message, exit 1', async () => {
    const { server } = await realServer(0);
    const r = recorder();
    const stopCleanup = () => Promise.reject(new Error('Access denied for user ana@example.com'));
    await createShutdown({ server, ...r.options, stopCleanup })('SIGTERM');
    assert.equal(r.exitCode, 1);
    assert.ok(r.logs.includes('shutdown: the session cleanup ended with an error (Error)'), r.logs.join('\n'));
    assert.ok(!r.logs.join('\n').includes('ana@example.com'));
  });
});

// El límite de cada espera (within, en src/lifecycle.js), con temporizadores simulados: sin reloj real,
// el orden de lo que pasa lo decide la prueba. Comprueban la lógica de createShutdown en este proceso;
// cómo termina un proceso de verdad lo comprueban las pruebas de proceso hijo de más abajo.
describe('the limit of each wait, with simulated timers', () => {
  // Un límite que nada más usa: así se distinguen sus temporizadores de cualquier otro.
  const LIMIT = 4321;

  /** Sustituye setTimeout y clearTimeout globales mientras dura `work`; anota cada temporizador del límite. */
  async function withFakeTimers(work) {
    const realSet = globalThis.setTimeout;
    const realClear = globalThis.clearTimeout;
    const timers = [];
    globalThis.setTimeout = (callback, ms, ...args) => {
      if (ms !== LIMIT) return realSet(callback, ms, ...args);
      const timer = {
        cleared: false, fired: false, unrefCalls: 0,
        fire() { assert.ok(!this.cleared, 'a cleared timer never fires'); this.fired = true; callback(); },
        unref() { this.unrefCalls += 1; return this; },
        ref() { return this; },
        hasRef() { return this.unrefCalls === 0; },
      };
      timers.push(timer);
      return timer;
    };
    globalThis.clearTimeout = (timer) => {
      if (timers.includes(timer)) timer.cleared = true;
      else realClear(timer);
    };
    try {
      return await work(timers);
    } finally {
      globalThis.setTimeout = realSet;
      globalThis.clearTimeout = realClear;
    }
  }

  /** Espera, sin reloj, a que se cumpla `check` (dejando correr la cola de tareas). */
  async function until(check) {
    for (let i = 0; i < 1000 && !check(); i++) await new Promise((resolve) => setImmediate(resolve));
    assert.ok(check(), 'the expected state was never reached');
  }

  /** Una promesa que la prueba resuelve o rechaza cuando quiere. */
  function deferred() {
    let resolve;
    const promise = new Promise((ok) => { resolve = ok; });
    return { promise, resolve };
  }

  /** Arranca un apagado con este pool; devuelve el registro, los temporizadores y la promesa del apagado. */
  async function start(timers, closePool) {
    const { server } = await realServer(0);
    const r = recorder();
    const done = createShutdown({ server, ...r.options, closePool, timeoutMs: LIMIT })('SIGTERM');
    // Las dos primeras esperas (servidor y borrado de sesiones) y, después, la del pool.
    await until(() => timers.length === 3);
    return { r, done };
  }

  const exits = (r) => r.events.filter((event) => event.startsWith('exit'));
  const poolLines = (r) => r.logs.filter((line) => /database pool/.test(line));

  test('no limit timer is unref()ed: each one keeps the process alive while its wait is pending', async () => {
    await withFakeTimers(async (timers) => {
      const { r, done } = await start(timers, async () => {});
      await done;
      assert.equal(timers.length, 3);
      assert.deepEqual(timers.map((timer) => timer.unrefCalls), [0, 0, 0]);
      assert.deepEqual(exits(r), ['exit 0']);
    });
  });

  test('the pool closes in time: every limit timer is cleared, exit 0, no limit line', async () => {
    await withFakeTimers(async (timers) => {
      const { r, done } = await start(timers, async () => {});
      await done;
      assert.deepEqual(timers.map((timer) => [timer.cleared, timer.fired]), [[true, false], [true, false], [true, false]]);
      assert.deepEqual(exits(r), ['exit 0']);
      assert.deepEqual(poolLines(r), []);
      assert.equal(r.logs.at(-1), 'shutdown: done');
    });
  });

  test('the pool rejects: its limit timer is cleared, one line without the message, exit 1', async () => {
    await withFakeTimers(async (timers) => {
      const failing = async () => { throw Object.assign(new Error('pool failed for ana@example.com'), { code: 'EPOOL' }); };
      const { r, done } = await start(timers, failing);
      await done;
      assert.deepEqual(timers.map((timer) => timer.cleared), [true, true, true]);
      assert.deepEqual(poolLines(r), ['shutdown: could not close the database pool (Error EPOOL)']);
      assert.ok(!r.logs.join('\n').includes('ana@example.com'));
      assert.deepEqual(exits(r), ['exit 1']);
      assert.equal(r.logs.at(-1), 'shutdown: done, with errors');
    });
  });

  test('the pool never closes: when its limit fires, one line and exit 1; a late close adds nothing', async () => {
    await withFakeTimers(async (timers) => {
      const late = deferred();
      const { r, done } = await start(timers, () => late.promise);
      timers[2].fire();
      await done;
      assert.deepEqual(poolLines(r), [`shutdown: the database pool did not close within ${LIMIT} ms`]);
      assert.deepEqual(exits(r), ['exit 1']);
      const logged = [...r.logs];
      late.resolve();
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(r.logs, logged, 'the late close is not logged');
      assert.deepEqual(exits(r), ['exit 1'], 'exit is called once');
    });
  });

  test('the limit and the pool close together: each order has one exact result', async () => {
    // El límite resuelve su promesa en el acto, dentro de su temporizador; el cierre del pool llega a la
    // espera a través de microtareas (la promesa de closePool, adoptada por within). Por eso:
    //   - el límite y después el pool, en el mismo turno: vence el límite;
    //   - el pool y después el límite, en el mismo turno: también vence el límite, porque el cierre aún
    //     no ha pasado por sus microtareas cuando salta el temporizador;
    //   - el pool, y la cola de tareas corre antes de que llegue el límite: cierra el pool, y el
    //     temporizador del límite queda limpio y ya no salta.
    const LIMIT_LINE = `shutdown: the database pool did not close within ${LIMIT} ms`;
    const ORDERS = [
      ['limit, then pool, same turn', (close, timer) => { timer.fire(); close.resolve(); }, { exit: 'exit 1', lines: [LIMIT_LINE], fired: true }],
      ['pool, then limit, same turn', (close, timer) => { close.resolve(); timer.fire(); }, { exit: 'exit 1', lines: [LIMIT_LINE], fired: true }],
      ['pool, queue drained, then the limit is due', async (close) => { close.resolve(); await new Promise((resolve) => setImmediate(resolve)); }, { exit: 'exit 0', lines: [], fired: false }],
    ];
    for (const [order, drive, expected] of ORDERS) {
      await withFakeTimers(async (timers) => {
        const close = deferred();
        const { r, done } = await start(timers, () => close.promise);
        await drive(close, timers[2]);
        await done;
        assert.deepEqual(exits(r), [expected.exit], order);
        assert.deepEqual(poolLines(r), expected.lines, order);
        assert.equal(timers[2].fired, expected.fired, order);
        assert.equal(timers[2].cleared, true, order);
        assert.equal(r.logs.filter((line) => line.startsWith('shutdown: done')).length, 1, order);
      });
    }
  });

  test('the pool closes before its limit fires (with the queue drained in between): exit 0, and the timer can no longer fire', async () => {
    await withFakeTimers(async (timers) => {
      const close = deferred();
      const { r, done } = await start(timers, () => close.promise);
      close.resolve();
      await done;
      assert.equal(timers[2].cleared, true);
      assert.throws(() => timers[2].fire(), /a cleared timer never fires/);
      assert.deepEqual(exits(r), ['exit 0']);
      assert.deepEqual(poolLines(r), []);
    });
  });
});

// El apagado en un proceso propio (test/fixtures/shutdown-child.js), con process.exit de verdad y un pool
// simulado: lo que termina haciendo el proceso, no solo la lógica. Sin base de datos, en 127.0.0.1.
describe('shutdown in a process of its own: the limit and the exit code of a real process', () => {
  const LIMIT = 300;
  const servidor = fileURLToPath(new URL('..', import.meta.url));

  /** Ejecuta el proceso hijo; devuelve su código y sus líneas como { at, text } (ms desde el apagado). */
  function child(pool, mode = 'real') {
    const result = spawnSync(process.execPath, ['test/fixtures/shutdown-child.js', pool, String(LIMIT), mode], {
      cwd: servidor, env: { PATH: process.env.PATH, SystemRoot: process.env.SystemRoot }, encoding: 'utf8', timeout: 20_000,
    });
    const lines = result.stdout.split(/\r?\n/).filter(Boolean).map((line) => {
      const [, at, text] = /^(\d+) (.*)$/.exec(line);
      return { at: Number(at), text };
    });
    return { status: result.status, lines, texts: lines.map((line) => line.text), stderr: result.stderr };
  }
  const at = (run, text) => run.lines.find((line) => line.text === text)?.at;

  test('the pool never closes and nothing else is alive: it waits for the limit, logs it and exits 1', () => {
    const run = child('never');
    assert.equal(run.status, 1, run.texts.join('\n'));
    assert.ok(at(run, `shutdown: the database pool did not close within ${LIMIT} ms`) >= LIMIT - 10, run.texts.join('\n'));
    assert.deepEqual(run.texts.slice(-3), ['shutdown: done, with errors', 'exit(1)', 'process exit 1']);
  });

  test('the pool closes at once: exit 0 without waiting for the limit', () => {
    const run = child('fast');
    assert.equal(run.status, 0, run.texts.join('\n'));
    assert.ok(at(run, 'process exit 0') < LIMIT / 2, run.texts.join('\n'));
    assert.ok(!run.texts.some((text) => /did not close/.test(text)));
  });

  test('the pool is slower than the limit: one limit line, exit 1, and nothing after it', () => {
    const run = child('slow');
    assert.equal(run.status, 1, run.texts.join('\n'));
    assert.equal(run.texts.filter((text) => /did not close/.test(text)).length, 1);
    assert.deepEqual(run.texts.slice(-3), ['shutdown: done, with errors', 'exit(1)', 'process exit 1']);
    assert.ok(at(run, 'process exit 1') < LIMIT * 2, 'it does not wait for the slow pool');
  });

  test('the pool rejects: the error is logged without its message, exit 1, at once', () => {
    const run = child('reject');
    assert.equal(run.status, 1, run.texts.join('\n'));
    assert.ok(run.texts.includes('shutdown: could not close the database pool (Error EPOOL)'), run.texts.join('\n'));
    assert.ok(!`${run.texts.join('\n')}${run.stderr}`.includes('ana@example.com'));
    assert.ok(at(run, 'process exit 1') < LIMIT / 2);
  });

  test('no timer is left behind: without process.exit, the process ends as soon as the shutdown does', () => {
    // exit solo fija process.exitCode: el proceso termina cuando no le queda nada. Si un temporizador del
    // límite siguiera vivo, terminaría más tarde.
    const fast = child('fast', 'soft');
    assert.equal(fast.status, 0, fast.texts.join('\n'));
    assert.ok(at(fast, 'process exit 0') < LIMIT / 2, fast.texts.join('\n'));
    const rejected = child('reject', 'soft');
    assert.equal(rejected.status, 1, rejected.texts.join('\n'));
    assert.ok(at(rejected, 'process exit 1') < LIMIT / 2, rejected.texts.join('\n'));
    const never = child('never', 'soft');
    assert.equal(never.status, 1, never.texts.join('\n'));
    assert.ok(at(never, 'process exit 1') >= LIMIT - 10 && at(never, 'process exit 1') < LIMIT + 250, never.texts.join('\n'));
  });

  // El pool cierra con el mismo retraso que el límite. Quién gana no es azar: Node dispara los
  // temporizadores del mismo retraso en el orden en que se pusieron, y entre uno y otro ejecuta las
  // microtareas. Cada caso se repite unas veces como comprobación adicional; el resultado es siempre el mismo.
  test('the pool closes at the same deadline as the limit, its timer set after the limit\'s: the limit always wins', () => {
    for (let i = 0; i < 5; i++) {
      const run = child('same-deadline');
      assert.equal(run.status, 1, run.texts.join('\n'));
      assert.deepEqual(run.texts.filter((text) => /database pool/.test(text)), [`shutdown: the database pool did not close within ${LIMIT} ms`]);
      assert.deepEqual(run.texts.slice(-3), ['shutdown: done, with errors', 'exit(1)', 'process exit 1']);
    }
  });

  test('the pool closes at the same deadline as the limit, its timer set before the shutdown: the pool always wins', () => {
    for (let i = 0; i < 5; i++) {
      const run = child('set-first');
      assert.equal(run.status, 0, run.texts.join('\n'));
      assert.ok(!run.texts.some((text) => /database pool/.test(text)), run.texts.join('\n'));
      assert.deepEqual(run.texts.slice(-3), ['shutdown: done', 'exit(0)', 'process exit 0']);
      // Cerró justo al llegar al límite, no antes: es de verdad el caso del límite.
      assert.ok(at(run, 'process exit 0') >= LIMIT - 10, run.texts.join('\n'));
    }
  });
});
