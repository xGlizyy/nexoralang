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
import { CONTAINER_FLAGS, CONTAINER_IMAGE, CONTAINER_OPTIONS, isContainerTool, loadPlaygroundConfig } from '../src/playground/config.js';
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

/** Ejecuta `body` con la variable de entorno `name` en `value` y restaura el valor anterior. */
function withVariable(name, value, body) {
  const had = Object.hasOwn(process.env, name);
  const previous = process.env[name];
  process.env[name] = value;
  try {
    return body();
  } finally {
    if (had) process.env[name] = previous;
    else delete process.env[name];
  }
}

/** Ejecuta `body` con PLAYGROUND_WORKER_COMMAND en `value` y restaura el valor anterior. */
const withCommand = (value, body) => withVariable('PLAYGROUND_WORKER_COMMAND', typeof value === 'string' ? value : JSON.stringify(value), body);

const load = (command) => withCommand(command, () => loadPlaygroundConfig().workerCommand);

// La orden de contenedor documentada, por grupos: cada opción con su valor, si lo lleva.
const GROUPS = [
  ['--rm'], ['-i'], ['--init'], ['--pull', 'never'], ['--name', '{container}'], ['--network', 'none'], ['--read-only'],
  ['--cap-drop', 'ALL'], ['--security-opt', 'no-new-privileges'], ['--pids-limit', '32'],
  ['--memory', '256m'], ['--memory-swap', '256m'], ['--cpus', '0.5'], ['--user', '65534:65534'],
  ['--tmpfs', '/tmp:rw,size=1m,noexec'],
];
const OPTIONS = GROUPS.flat();
const VALID = ['docker', 'run', ...OPTIONS, 'nexora-worker'];

/** Una orden de contenedor con estas opciones y, detrás, `tail` (por defecto, solo la imagen). */
const command = (options, tail = ['nexora-worker']) => ['docker', 'run', ...options, ...tail];
/** Las opciones documentadas sin `option` ni su valor. */
const dropping = (...options) => GROUPS.filter(([name]) => !options.includes(name)).flat();
/** `options` con `parts` en lugar del valor de `option`. */
const replacingValueOf = (option, parts, options) => options.flatMap((part, at) => (options[at - 1] === option ? parts : [part]));
/** Las opciones documentadas con otro valor para `option`. */
const setting = (option, value) => GROUPS.map((group) => (group[0] === option ? [option, value] : group)).flat();

/** La orden impide arrancar el servidor, con un mensaje que contiene `expected`. */
function rejects(rejected, expected) {
  assert.throws(() => load(rejected), (error) => {
    assert.ok(error.message.includes(expected), `"${error.message}" should contain "${expected}"`);
    return true;
  });
}

describe('the documented container command is the only one accepted', () => {
  test('the documented command is accepted as it is', () => {
    assert.deepEqual(load(VALID), VALID);
  });

  test('the server and these tests agree on the documented options', () => {
    assert.deepEqual(
      new Set(GROUPS.map((group) => group.join(' '))),
      new Set([...CONTAINER_FLAGS, ...CONTAINER_OPTIONS.map((pair) => pair.join(' '))]),
    );
    assert.equal(CONTAINER_IMAGE, 'nexora-worker');
  });

  test('the options can go in any order before the image', () => {
    const reversed = command([...GROUPS].reverse().flat());
    assert.deepEqual(load(reversed), reversed);
  });

  test('the local Nexora image can have a tag', () => {
    for (const image of ['nexora-worker:0.6.0', 'nexora-worker:latest', 'nexora-worker:0.6.0-rc.1', 'nexora-worker:Build_7']) {
      assert.deepEqual(load(command(OPTIONS, [image])), command(OPTIONS, [image]), image);
    }
  });

  test('the commands documented in .env.example, playground.md and the Dockerfile are the accepted one', () => {
    const documents = [
      [path.join(repo, 'servidor', '.env.example'), /^#?PLAYGROUND_WORKER_COMMAND=(.+)$/m, JSON.parse],
      [path.join(repo, 'nexora', 'docs', 'playground.md'), /^PLAYGROUND_WORKER_COMMAND=(.+)$/m, JSON.parse],
      // En el Dockerfile, la orden está en un comentario y partida en varias líneas.
      [path.join(repo, 'servidor', 'playground', 'Dockerfile'), /^# {5}(docker run [^\n]*(?:\n# {7}[^\n]*)*)/m,
        (text) => text.replace(/\n# +/g, ' ').trim().split(/\s+/)],
    ];
    for (const [file, pattern, parse] of documents) {
      const [, text] = pattern.exec(readFileSync(file, 'utf8')) ?? [];
      assert.ok(text, `${file} documents the container command`);
      const documented = parse(text);
      assert.deepEqual(documented, VALID, file);
      assert.deepEqual(load(documented), VALID, file);
    }
  });
});

describe('only the local Nexora image runs, and it is never pulled', () => {
  const notAdmitted = 'que no es un nombre de imagen admitido: solo "nexora-worker" o "nexora-worker:<etiqueta>"';
  for (const image of [
    'alpine', 'python:3.12-slim', 'nexora-worker2', 'my-nexora-worker', 'nexora_worker', 'NEXORA-WORKER',
    'nexora/worker', 'library/nexora-worker', 'docker.io/library/nexora-worker', 'ghcr.io/nexora/nexora-worker',
    'localhost:5000/nexora-worker', `nexora-worker@sha256:${'0'.repeat(64)}`, `nexora-worker:0.6.0@sha256:${'0'.repeat(64)}`,
    'nexora-worker:', 'nexora-worker:-rc', 'nexora-worker:.hidden', 'nexora-worker:a/b', `nexora-worker:${'x'.repeat(129)}`,
  ]) {
    test(`the image ${image.length > 60 ? `${image.slice(0, 40)}…` : image} prevents the server from starting`, () => {
      rejects(command(OPTIONS, [image]), `termina en "${image}", ${notAdmitted}`);
    });
  }

  test('the image the server accepts is CONTAINER_IMAGE, the one the documents use', () => {
    assert.equal(VALID.at(-1), CONTAINER_IMAGE);
    for (const image of [CONTAINER_IMAGE, `${CONTAINER_IMAGE}:0.6.0`]) {
      assert.deepEqual(load(command(OPTIONS, [image])), command(OPTIONS, [image]), image);
    }
    for (const image of [`${CONTAINER_IMAGE}x`, `x${CONTAINER_IMAGE}`, CONTAINER_IMAGE.replace('-', '.')]) {
      rejects(command(OPTIONS, [image]), `termina en "${image}", ${notAdmitted}`);
    }
  });

  test('a tag of 128 characters, the most Docker allows, is accepted', () => {
    const image = `nexora-worker:${'x'.repeat(128)}`;
    assert.deepEqual(load(command(OPTIONS, [image])), command(OPTIONS, [image]));
  });

  for (const value of ['missing', 'always', 'Never', '']) {
    test(`--pull ${value || '""'} instead of never prevents the server from starting`, () => {
      rejects(command(setting('--pull', value)), `da a "--pull" el valor "${value}"`);
    });
  }

  test('--pull=never, the form in the Docker manual, is not accepted: the contract uses two elements', () => {
    rejects(command([...dropping('--pull'), '--pull=never']), 'la opción "--pull=never", que no está admitida');
  });
});

describe('a command that runs no container is the process mode', () => {
  test('a command that runs no container is not affected', () => {
    const python = ['/srv/nexora/.venv/bin/python', '-I', '-m', 'nexora.worker'];
    assert.deepEqual(load(python), python);
  });

  test('without PLAYGROUND_WORKER_COMMAND, the worker is the Python of the virtual environment', () => {
    assert.deepEqual(load('').slice(1), ['-I', '-m', 'nexora.worker']);
  });

  test('an invalid container command prevents loading the configuration even with the playground disabled', () => {
    for (const enabled of ['false', '']) {
      withVariable('PLAYGROUND_ENABLED', enabled, () => {
        rejects(command(dropping('--init')), 'no incluye antes de la imagen: "--init"');
        const config = withCommand(VALID, () => loadPlaygroundConfig());
        assert.equal(config.enabled, false);
        assert.deepEqual(config.workerCommand, VALID);
      });
    }
  });

  test('a process command with the placeholder is treated as a container command, and rejected', () => {
    rejects(['python', '-I', '-m', 'nexora.worker', '{container}'], 'no empieza por "docker","run"');
    rejects(['python', '-I', '-m', 'nexora.worker', '--name={container}'], 'no empieza por "docker","run"');
  });
});

describe('only "docker" "run" is accepted as the container tool', () => {
  for (const [why, rejected] of [
    ['a path to docker', ['/usr/bin/docker', 'run', ...OPTIONS, 'nexora-worker']],
    ['a Windows path to docker.exe', [String.raw`C:\Program Files\Docker\docker.exe`, 'run', ...OPTIONS, 'nexora-worker']],
    ['docker.exe', ['docker.exe', 'run', ...OPTIONS, 'nexora-worker']],
    ['Docker in capitals', ['Docker', 'run', ...OPTIONS, 'nexora-worker']],
    ['sudo', ['sudo', '-n', 'docker', 'run', ...OPTIONS, 'nexora-worker']],
    ['env', ['/usr/bin/env', 'docker', 'run', ...OPTIONS, 'nexora-worker']],
    ['podman', ['podman', 'run', ...OPTIONS, 'nexora-worker']],
    ['docker container run', ['docker', 'container', 'run', ...OPTIONS, 'nexora-worker']],
    ['a global option of docker', ['docker', '--context', 'default', 'run', ...OPTIONS, 'nexora-worker']],
    ['another subcommand', ['docker', 'create', ...OPTIONS, 'nexora-worker']],
    ['the placeholder before run', ['docker', '--name', '{container}', 'run', ...dropping('--name'), 'nexora-worker']],
  ]) {
    test(`${why} prevents the server from starting`, () => {
      rejects(rejected, 'no empieza por "docker","run"');
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
});

describe('the cases A to G: options that Docker would not apply as written', () => {
  const afterImage = afterImageOf('nexora-worker');
  for (const [why, rejected, expected] of [
    ['A: --name {container} after the image', command(dropping('--name'), ['nexora-worker', '--name', '{container}']), afterImage],
    ['A: the placeholder alone after the image', command(dropping('--name'), ['nexora-worker', '{container}']), afterImage],
    ['B: --init after the image', command(dropping('--init'), ['nexora-worker', '--init']), afterImage],
    ['C: --init and --name {container} after the image', command(dropping('--init', '--name'), ['nexora-worker', '--init', '--name', '{container}']), afterImage],
    ['D: a second --name with a fixed name', command([...OPTIONS, '--name', 'fijo']), 'repite la opción "--name"'],
    ['D: a second --name with the placeholder', command([...OPTIONS, '--name', '{container}']), 'repite la opción "--name"'],
    ['D: a second name as --name=fijo', command([...OPTIONS, '--name=fijo']), 'la opción "--name=fijo", que no está admitida'],
    ['E: --init=false after --init', command([...OPTIONS, '--init=false']), 'la opción "--init=false", que no está admitida'],
    ['E: --init=true instead of --init', command([...dropping('--init'), '--init=true']), 'la opción "--init=true", que no está admitida'],
    ['E: --init twice', command([...OPTIONS, '--init']), 'repite la opción "--init"'],
    ['F: --init as the value of --user', command(replacingValueOf('--user', ['--init'], dropping('--init'))), 'da a "--user" el valor "--init"'],
    ['F: --init as the value of an unknown --hostname', command([...dropping('--init'), '--hostname', '--init']), 'la opción "--hostname", que no está admitida'],
    ['G: --name as the value of --network', command(replacingValueOf('--network', ['--name', '{container}'], dropping('--name'))), 'da a "--network" el valor "--name"'],
  ]) {
    test(`${why} prevents the server from starting`, () => {
      rejects(rejected, expected);
    });
  }
});

describe('every documented option is required, once, with its documented value', () => {
  for (const group of GROUPS) {
    const [option] = group;

    test(`without ${option}, the server does not start`, () => {
      rejects(command(dropping(option)), `no incluye antes de la imagen: ${group.map((part) => `"${part}"`).join(',')}`);
    });

    test(`${option} twice prevents the server from starting`, () => {
      rejects(command([...OPTIONS, ...group]), `repite la opción "${option}"`);
    });

    if (group.length === 2) {
      test(`${option} without its value at the end prevents the server from starting`, () => {
        rejects(command([...dropping(option), option], []), `termina en "${option}" sin su valor "${group[1]}"`);
      });

      test(`${option} cannot take the image as its value`, () => {
        rejects(command([...dropping(option), option]), `da a "${option}" el valor "nexora-worker"`);
      });

      test(`${option}=value prevents the server from starting`, () => {
        rejects(command([...dropping(option), `${option}=${group[1]}`]), `la opción "${option}=${group[1]}", que no está admitida`);
      });
    }
  }

  test('all the missing options are named at once', () => {
    rejects(['docker', 'run', '-i', '--name', '{container}', 'img'], 'no incluye antes de la imagen: "--rm", "--init", "--read-only", "--network","none"');
  });

  for (const [option, value] of [
    ['--name', 'nexora-pg-fijo'], ['--name', 'nexora-worker'],
    ['--network', 'host'], ['--network', 'bridge'], ['--network', 'None'],
    ['--cap-drop', 'NET_RAW'], ['--cap-drop', 'all'],
    ['--security-opt', 'no-new-privileges:true'], ['--security-opt', 'seccomp=unconfined'],
    ['--pids-limit', '64'], ['--pids-limit', '-1'],
    ['--memory', '512m'], ['--memory', '256M'], ['--memory', '268435456'],
    ['--memory-swap', '-1'], ['--memory-swap', '512m'],
    ['--cpus', '1'], ['--cpus', '0.50'],
    ['--user', '0:0'], ['--user', 'root'], ['--user', '65534'],
    ['--tmpfs', '/tmp:rw,size=10m,noexec'], ['--tmpfs', '/tmp:rw,size=1m,exec'], ['--tmpfs', '/tmp'],
  ]) {
    test(`${option} ${value} instead of the documented value prevents the server from starting`, () => {
      rejects(command(setting(option, value)), `da a "${option}" el valor "${value}"`);
    });
  }
});

describe('nothing but the documented options, and the image last', () => {
  for (const unknown of ['--privileged', '-it', '-t', '-d', '--', '--network-alias', '--cap-add', '-v']) {
    test(`the unknown option ${unknown} prevents the server from starting`, () => {
      rejects(command([...OPTIONS, unknown]), `la opción "${unknown}", que no está admitida`);
    });
  }

  test('-it instead of -i prevents the server from starting', () => {
    rejects(command([...dropping('-i'), '-it']), 'la opción "-it", que no está admitida');
  });

  // Docker acepta estos alias de opciones documentadas. Si se admitieran, un alias repetido podría
  // cambiar un valor ya comprobado: se rechazan solos, en lugar de la opción o junto a ella.
  for (const [alias, option, value, other] of [
    ['-m', '--memory', '256m', '1g'],
    ['-u', '--user', '65534:65534', '0:0'],
    ['--net', '--network', 'none', 'host'],
    ['--interactive', '-i', null, null],
  ]) {
    const unknown = `la opción "${alias}", que no está admitida`;
    const as = (v) => (v === null ? [alias] : [alias, v]);

    test(`the alias ${alias} alone prevents the server from starting`, () => {
      rejects(command(as(value), ['nexora-worker']), unknown);
    });

    test(`the alias ${alias} instead of ${option} prevents the server from starting`, () => {
      rejects(command([...dropping(option), ...as(value)]), unknown);
    });

    test(`the alias ${alias} next to ${option} prevents the server from starting`, () => {
      rejects(command([...OPTIONS, ...as(value)]), unknown);
      if (other !== null) rejects(command([...OPTIONS, ...as(other)]), unknown);
    });
  }

  for (const [why, tail, expected] of [
    ['without an image', [], 'no termina en el nombre de la imagen'],
    ['with arguments for the program after the image', ['nexora-worker', '-c', 'print(1)'], afterImageOf('nexora-worker')],
    ['with two images', ['nexora-worker', 'python'], afterImageOf('nexora-worker')],
    ['with the placeholder as the image', ['{container}'], 'termina en "{container}", que no es un nombre de imagen admitido'],
    ['with an image in capitals', ['Nexora-Worker'], 'termina en "Nexora-Worker", que no es un nombre de imagen admitido'],
    ['with a registry and a port', ['localhost:5000/nexora-worker'], 'que no es un nombre de imagen admitido'],
    ['with a digest', [`nexora-worker@sha256:${'0'.repeat(64)}`], 'que no es un nombre de imagen admitido'],
  ]) {
    test(`a command ${why} prevents the server from starting`, () => {
      rejects(command(OPTIONS, tail), expected);
    });
  }
});

describe('the container commands rejected before this contract are still rejected', () => {
  for (const [why, rejected, expected] of [
    ['without a name', ['docker', 'run', '--rm', '-i', '--init', 'nexora-worker'], '"--name","{container}"'],
    ['with a path to docker', ['/usr/bin/docker', 'run', '--rm', '-i', '--init', 'nexora-worker'], 'no empieza por "docker","run"'],
    ['on Windows', [String.raw`C:\Program Files\Docker\docker.exe`, 'run', '-i', 'nexora-worker'], 'no empieza por "docker","run"'],
    ['through sudo', ['sudo', '-n', 'docker', 'run', '-i', 'nexora-worker'], 'no empieza por "docker","run"'],
    ['with podman', ['podman', 'run', '-i', 'nexora-worker'], 'no empieza por "docker","run"'],
    ['with the placeholder twice', ['docker', 'run', '--init', '--name', '{container}', '--name', '{container}', 'img'], 'repite la opción "--name"'],
    ['with the placeholder without --name before it', ['docker', 'run', '--init', '{container}', 'img'], 'tiene elementos después de la imagen "{container}"'],
    ['with the placeholder before run', ['docker', '--name', '{container}', 'run', '--init', 'img'], 'no empieza por "docker","run"'],
    ['without --init', ['docker', 'run', '-i', '--name', '{container}', 'img'], '"--init"'],
  ]) {
    test(`a container command ${why} prevents the server from starting`, () => {
      rejects(rejected, expected);
    });
  }
});

function afterImageOf(image) {
  return `tiene elementos después de la imagen "${image}"`;
}
