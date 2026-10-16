// Ciclo de vida de los contenedores del worker, con un Docker falso (fixtures/fake-docker.js):
// ninguna de estas pruebas usa Docker.
//
// Matar el cliente `docker run` no detiene el contenedor. El servidor da a cada contenedor un
// nombre, lo elimina por ese nombre cuando no terminó bien, y no libera su hueco hasta confirmar
// que ya no existe.

import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, describe, test } from 'node:test';
import { isContainerTool, loadPlaygroundConfig } from '../src/playground/config.js';
import { runWorker } from '../src/playground/worker.js';
import { HELLO, repo, startServer } from './helpers.js';

const fakeDocker = fileURLToPath(new URL('./fixtures/fake-docker.js', import.meta.url));
const NAME = /^nexora-pg-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const states = [];
after(() => { for (const state of states) rmSync(state, { recursive: true, force: true }); });

/** Un Docker falso con su propio estado. `run` y `stop` deciden cómo se comporta. */
function docker({ run = 'ok', stop = 'ok' } = {}) {
  const state = mkdtempSync(path.join(tmpdir(), 'nexora-fake-docker-'));
  states.push(state);
  const set = (file, value) => writeFileSync(path.join(state, file), value);
  set('run', run);
  set('stop', stop);
  const calls = () => {
    const file = path.join(state, 'calls.jsonl');
    return existsSync(file) ? readFileSync(file, 'utf8').trim().split('\n').map((line) => JSON.parse(line)) : [];
  };
  return {
    command: [process.execPath, fakeDocker, state, 'run', '--rm', '-i', '--init', '--name', '{container}', 'from-state'],
    calls,
    count: (command) => calls().filter((call) => call.command === command).length,
    alive: () => readdirSync(path.join(state, 'containers')),
    setRun: (value) => set('run', value),
    setStop: (value) => set('stop', value),
  };
}

// Tiempo máximo de las pruebas que agotan el tiempo a propósito: corto, pero con margen para que
// el Docker falso (un proceso de Node) arranque y anote su llamada aunque el equipo esté cargado.
const TIMEOUT_MS = 1000;
// El de las demás: una respuesta normal nunca debe confundirse con un tiempo agotado.
const NORMAL_TIMEOUT_MS = 10_000;

/** Un solo hueco y sin cola: la segunda petición a la vez recibe `busy`. */
const oneSlot = (fake, extra = {}) => startServer({
  workerCommand: fake.command,
  maxConcurrent: 1,
  maxQueue: 0,
  timeoutMs: NORMAL_TIMEOUT_MS,
  containerStop: { attemptTimeoutMs: 2000, retryDelaysMs: [20, 20] },
  ...extra,
});

async function until(condition, what, timeoutMs = 5000) {
  const started = Date.now();
  while (!condition()) {
    if (Date.now() - started > timeoutMs) assert.fail(`timed out waiting until ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

const isBusy = (response) => response.status === 503 && response.json?.error?.code === 'busy';

/** Repite la petición mientras el hueco esté ocupado (el Docker falso anota antes de terminar). */
async function runWhenFree(server, timeoutMs = 3000) {
  const started = Date.now();
  for (;;) {
    const response = await server.run(HELLO);
    if (!isBusy(response) || Date.now() - started > timeoutMs) return response;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

describe('containers that do not end well are removed by name', () => {
  test('after a timeout, the same container is removed, and only then is its slot freed', async () => {
    const fake = docker({ run: 'hang' });
    const server = await oneSlot(fake, { timeoutMs: TIMEOUT_MS });
    try {
      const response = await server.run(HELLO);
      assert.equal(response.status, 200);
      assert.equal(response.json.status, 'timeout');

      await until(() => fake.count('run') === 1, 'the run call is recorded');
      await until(() => fake.count('ps') === 1, 'the removal is confirmed');
      const [run, rm, ps] = fake.calls();
      assert.equal(run.command, 'run');
      assert.match(run.name, NAME);
      assert.ok(run.args.includes('--init'));
      assert.ok(!run.args.includes('{container}'), 'the placeholder is replaced');
      assert.deepEqual([rm.command, rm.name, ps.command, ps.name], ['rm', run.name, 'ps', run.name]);
      assert.deepEqual(rm.args, ['-f', run.name]);
      assert.deepEqual(fake.alive(), []);

      fake.setRun('ok');
      const next = await runWhenFree(server);
      assert.equal(next.json?.status, 'success', next.text);
    } finally {
      await server.close();
    }
  });

  test('the slot stays taken while the removal is not confirmed, and is freed when it is', async () => {
    // Los dos primeros listados todavía muestran el contenedor; el tercero, no.
    const fake = docker({ run: 'hang', stop: 'fail:2' });
    const server = await oneSlot(fake, {
      timeoutMs: TIMEOUT_MS, containerStop: { attemptTimeoutMs: 2000, retryDelaysMs: [300, 300] },
    });
    try {
      assert.equal((await server.run(HELLO)).json.status, 'timeout');
      assert.ok(isBusy(await server.run(HELLO)), 'the slot is still taken during the removal');

      await until(() => fake.count('ps') === 3, 'the third listing');
      fake.setRun('ok');
      const next = await runWhenFree(server);
      assert.equal(next.json?.status, 'success', next.text);
      assert.equal(fake.count('rm'), 3);
      assert.deepEqual(server.logs, []);
    } finally {
      await server.close();
    }
  });

  test('when the removal is never confirmed, the attempts stop and the slot stays taken', async () => {
    const fake = docker({ run: 'hang', stop: 'never' });
    const server = await oneSlot(fake, { timeoutMs: TIMEOUT_MS });
    try {
      assert.equal((await server.run(HELLO)).json.status, 'timeout');
      await until(() => server.logs.length === 1, 'the server gives up');
      assert.match(server.logs[0], /container not confirmed stopped after 3 attempts; its slot stays taken/);

      // Un número fijo de intentos (retryDelaysMs.length + 1), y ninguno más después.
      await new Promise((resolve) => setTimeout(resolve, 300));
      assert.equal(fake.count('rm'), 3);
      assert.equal(fake.count('ps'), 3);
      assert.ok(isBusy(await server.run(HELLO)), 'the slot is never freed');
      assert.equal(fake.count('run'), 1, 'no new container is started');
    } finally {
      await server.close();
    }
  });

  test('a removal command that never ends is killed and counts as a failed attempt', async () => {
    const fake = docker({ run: 'hang', stop: 'hang' });
    // attemptTimeoutMs corto a propósito: lo que se prueba es que la orden se mata a ese tiempo.
    const server = await oneSlot(fake, {
      timeoutMs: TIMEOUT_MS, containerStop: { attemptTimeoutMs: 200, retryDelaysMs: [20] },
    });
    try {
      const started = Date.now();
      assert.equal((await server.run(HELLO)).json.status, 'timeout');
      await until(() => server.logs.length === 1, 'the server gives up');
      assert.match(server.logs[0], /after 2 attempts/);
      assert.ok(Date.now() - started < TIMEOUT_MS + 4000);
      assert.equal(fake.count('rm'), 2);
      assert.ok(isBusy(await server.run(HELLO)));
    } finally {
      await server.close();
    }
  });

  test('an answer that is too large: the container is removed', async () => {
    const fake = docker({ run: 'flood' });
    const server = await oneSlot(fake);
    try {
      const response = await server.run(HELLO);
      assert.equal(response.status, 503);
      assert.equal(response.json.error.code, 'runtime_unavailable');
      await until(() => fake.count('run') === 1, 'the run call is recorded');
      await until(() => fake.count('ps') === 1, 'the removal is confirmed');
      assert.equal(fake.calls().find((call) => call.command === 'rm').name, fake.calls()[0].name);
      assert.deepEqual(fake.alive(), []);
    } finally {
      await server.close();
    }
  });

  test('a client that fails is cleaned up too: it cannot say whether the container ended', async () => {
    const fake = docker({ run: 'garbage' });
    const server = await oneSlot(fake);
    try {
      assert.equal((await server.run(HELLO)).json.error.code, 'runtime_unavailable');
      await until(() => fake.count('ps') === 1, 'the removal is confirmed');
      assert.deepEqual(fake.alive(), []);
    } finally {
      await server.close();
    }
  });

  test('a run that Docker refuses: removing what does not exist is confirmed at once', async () => {
    const fake = docker({ run: 'refused' });
    const server = await oneSlot(fake);
    try {
      assert.equal((await server.run(HELLO)).json.error.code, 'runtime_unavailable');
      await until(() => fake.count('ps') === 1, 'the removal is confirmed');
      assert.equal(fake.count('rm'), 1);
      fake.setRun('ok');
      assert.equal((await runWhenFree(server)).json?.status, 'success');
    } finally {
      await server.close();
    }
  });
});

describe('when nothing needs removing', () => {
  test('a container that ends well is not removed, and its slot is freed at once', async () => {
    const fake = docker({ run: 'ok' });
    const server = await oneSlot(fake);
    try {
      assert.equal((await server.run(HELLO)).json.status, 'success');
      assert.equal((await server.run(HELLO)).json.status, 'success');
      assert.deepEqual(fake.calls().map((call) => call.command), ['run', 'run']);
    } finally {
      await server.close();
    }
  });

  test('if the container tool cannot be started, no removal is attempted and the slot is freed', async () => {
    // Una herramienta que no existe tampoco podría confirmar una eliminación: si se intentara, el
    // hueco no se liberaría nunca. Que se libere demuestra que no se intentó.
    const missing = path.join(tmpdir(), 'nexora-no-such-docker', 'docker');
    const command = [missing, 'run', '--init', '--name', '{container}', 'nexora-worker'];
    let finished = 0;
    await assert.rejects(
      runWorker(command, { action: 'run', code: HELLO }, {
        timeoutMs: 2000,
        maxResponseBytes: 1024,
        onFinished: () => { finished += 1; },
        containerStop: { attemptTimeoutMs: 2000, retryDelaysMs: [60_000] },
      }),
      (error) => error.kind === 'unavailable',
    );
    await until(() => finished === 1, 'the slot is freed', 1000);
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(finished, 1, 'freed exactly once');

    const server = await startServer({ workerCommand: command, maxConcurrent: 1, maxQueue: 0 });
    try {
      for (let request = 0; request < 3; request += 1) {
        const response = await server.run(HELLO);
        assert.equal(response.json.error.code, 'runtime_unavailable', 'never busy: the slot was freed');
      }
    } finally {
      await server.close();
    }
  });

  test('if starting the worker throws at once, the slot is freed and the error is reported', async () => {
    // Una orden que no es una lista hace que runWorker lance una excepción antes de crear ningún
    // proceso. Con un solo hueco y sin cola, si no se liberara, la segunda petición sería `busy`.
    const server = await startServer({ workerCommand: 42, maxConcurrent: 1, maxQueue: 0 });
    try {
      for (let request = 0; request < 3; request += 1) {
        const response = await server.run(HELLO);
        assert.equal(response.status, 500, response.text);
        assert.equal(response.json.error.code, 'internal_error');
      }
      assert.deepEqual(server.logs, Array(3).fill('playground: internal error (TypeError)'));
    } finally {
      await server.close();
    }
  });

  test('each container gets a new name, made by the server and not by the request', async () => {
    const fake = docker({ run: 'ok' });
    const server = await oneSlot(fake);
    try {
      await server.run('fn main() -> Void {\n    print("{container}")\n}\n', { name: 'evil', container: 'evil' });
      await server.run(HELLO);
      const names = fake.calls().map((call) => call.name);
      assert.equal(names.length, 2);
      for (const name of names) assert.match(name, NAME);
      assert.notEqual(names[0], names[1]);
    } finally {
      await server.close();
    }
  });
});

/** Ejecuta `body` con PLAYGROUND_WORKER_COMMAND en `value` y restaura el valor anterior. */
function withCommand(value, body) {
  const had = Object.hasOwn(process.env, 'PLAYGROUND_WORKER_COMMAND');
  const previous = process.env.PLAYGROUND_WORKER_COMMAND;
  process.env.PLAYGROUND_WORKER_COMMAND = typeof value === 'string' ? value : JSON.stringify(value);
  try {
    return body();
  } finally {
    if (had) process.env.PLAYGROUND_WORKER_COMMAND = previous;
    else delete process.env.PLAYGROUND_WORKER_COMMAND;
  }
}

const load = (command) => withCommand(command, () => loadPlaygroundConfig().workerCommand);
const VALID = ['docker', 'run', '--rm', '-i', '--init', '--name', '{container}', 'nexora-worker'];

describe('a container command must let the server stop the container', () => {
  test('a valid command is accepted as it is', () => {
    assert.deepEqual(load(VALID), VALID);
  });

  for (const [why, command] of [
    ['without a name', ['docker', 'run', '--rm', '-i', '--init', 'nexora-worker']],
    ['with a path to docker', ['/usr/bin/docker', 'run', '--rm', '-i', '--init', 'nexora-worker']],
    ['on Windows', ['C:\\Program Files\\Docker\\docker.exe', 'run', '-i', 'nexora-worker']],
    ['through sudo', ['sudo', '-n', 'docker', 'run', '-i', 'nexora-worker']],
    ['with podman', ['podman', 'run', '-i', 'nexora-worker']],
  ]) {
    test(`a container command ${why} prevents the server from starting`, () => {
      assert.throws(() => load(command), /sin "--name","\{container\}"/);
    });
  }

  for (const [why, command] of [
    ['twice', ['docker', 'run', '--init', '--name', '{container}', '--name', '{container}', 'img']],
    ['without --name before it', ['docker', 'run', '--init', '{container}', 'img']],
    ['before run', ['docker', '--name', '{container}', 'run', '--init', 'img']],
  ]) {
    test(`the placeholder ${why} prevents the server from starting`, () => {
      assert.throws(() => load(command), /una sola vez, después de "run"/);
    });
  }

  test('a path to docker or podman is recognised with the same rules on Linux, macOS and Windows', () => {
    const windows = String.raw`C:\Program Files\Docker\docker.exe`;
    // El caso tiene sentido fuera de Windows: con las reglas de rutas de POSIX, esta ruta no
    // termina en "docker.exe", así que una detección basada en path.basename fallaría allí.
    assert.notEqual(path.posix.basename(windows), 'docker.exe');
    for (const tool of [windows, 'C:/Tools/podman.EXE', String.raw`\\server\share\docker`, '/usr/bin/docker', 'docker', 'podman']) {
      assert.equal(isContainerTool(tool), true, tool);
    }
    for (const other of ['python', String.raw`C:\Tools\dockerize.exe`, '/opt/docker/bin/python', 'sudo', 'run']) {
      assert.equal(isContainerTool(other), false, other);
    }
  });

  test('a container command without --init prevents the server from starting', () => {
    assert.throws(() => load(['docker', 'run', '-i', '--name', '{container}', 'img']), /"--init"/);
  });

  test('a command that runs no container is not affected', () => {
    const command = ['/srv/nexora/.venv/bin/python', '-I', '-m', 'nexora.worker'];
    assert.deepEqual(load(command), command);
  });

  test('the documented container commands are accepted', () => {
    const documents = [
      [path.join(repo, 'servidor', '.env.example'), /^#?PLAYGROUND_WORKER_COMMAND=(.+)$/m],
      [path.join(repo, 'nexora', 'docs', 'playground.md'), /^PLAYGROUND_WORKER_COMMAND=(.+)$/m],
    ];
    for (const [file, pattern] of documents) {
      const [, command] = pattern.exec(readFileSync(file, 'utf8')) ?? [];
      assert.ok(command, `${file} documents PLAYGROUND_WORKER_COMMAND`);
      const parsed = withCommand(command, () => loadPlaygroundConfig().workerCommand);
      assert.ok(parsed.includes('--init') && parsed.includes('{container}'), file);
    }
  });
});
