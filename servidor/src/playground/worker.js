// Lanza el worker de NEXORA (un proceso aparte por petición) y recoge su respuesta.
// El código del visitante nunca se ejecuta dentro del proceso del servidor.

import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { CONTAINER_PLACEHOLDER, CONTAINER_STOP } from './config.js';

export const RESULT_SCHEMA = 'nexora.result/1';

/** Estados que puede devolver el worker para "check" y "run". */
export const RESULT_STATUSES = new Set([
  'success', 'invalid', 'runtime_error', 'contract_violation', 'output_limit', 'memory_limit',
]);

/**
 * El worker no pudo dar una respuesta válida.
 * kind: 'unavailable' (no arrancó) | 'timeout' | 'failed' (terminó mal o respondió algo que no se entiende).
 */
export class WorkerError extends Error {
  constructor(kind, detail) {
    super(`worker ${kind}: ${detail}`);
    this.kind = kind;
  }
}

// El worker arranca en un directorio vacío: no tiene nada del proyecto a mano.
const workDir = path.join(tmpdir(), 'nexora-playground-worker');
mkdirSync(workDir, { recursive: true });

// Entorno mínimo: el worker no recibe ninguna variable del servidor (ni secretos, ni la
// configuración de la base de datos). Windows necesita SystemRoot para arrancar un proceso.
function workerEnvironment() {
  const environment = {};
  for (const name of ['SystemRoot', 'PATH']) {
    if (process.env[name]) environment[name] = process.env[name];
  }
  return environment;
}

function isResult(value, action) {
  if (typeof value !== 'object' || value === null || value.schema !== RESULT_SCHEMA) return false;
  if (action === 'info') return value.status === 'success' && typeof value.version === 'string';
  return RESULT_STATUSES.has(value.status)
    && value.action === action
    && typeof value.output === 'string'
    && Array.isArray(value.diagnostics)
    && (value.message === null || typeof value.message === 'string');
}

// Nombres que genera el servidor. Nunca se elimina un contenedor con otro nombre.
const CONTAINER_NAME = /^nexora-pg-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * Si la orden arranca un contenedor (lleva CONTAINER_PLACEHOLDER), le da un nombre nuevo.
 * `cli` es lo que va antes de "run" (["docker"]): con ello se elimina el contenedor después.
 */
function containerFor(command) {
  const run = command.indexOf('run');
  if (run < 1 || !command.includes(CONTAINER_PLACEHOLDER)) return null;
  return { name: `nexora-pg-${randomUUID()}`, cli: command.slice(0, run) };
}

/**
 * Envía una petición al worker y devuelve su respuesta.
 *
 * Responder y terminar son dos momentos distintos. `onFinished` se llama una sola vez, cuando el
 * worker ha terminado de verdad: en el modo de proceso, cuando el proceso ha salido; en el modo
 * contenedor, cuando el contenedor terminó bien o se ha confirmado que ya no existe. Matar el
 * cliente `docker run` no detiene el contenedor, así que si no se puede confirmar que ya no
 * existe, `onFinished` no se llama nunca y el hueco del worker sigue ocupado.
 *
 * @param {string[]} command  Orden que arranca el worker.
 * @param {object} request    Lo que se escribe, como JSON, en su entrada estándar.
 * @param {{ timeoutMs: number, maxResponseBytes: number, onFinished?: () => void,
 *           containerStop?: { attemptTimeoutMs: number, retryDelaysMs: number[] },
 *           log?: (message: string) => void }} options
 */
export function runWorker(command, request, {
  timeoutMs, maxResponseBytes, onFinished = () => {}, containerStop = CONTAINER_STOP, log = () => {},
}) {
  const container = containerFor(command);
  const argv = container ? command.map((part) => (part === CONTAINER_PLACEHOLDER ? container.name : part)) : command;

  let finished = false;
  const finishOnce = () => {
    if (finished) return;
    finished = true;
    onFinished();
  };

  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(argv[0], argv.slice(1), {
        cwd: workDir,
        env: workerEnvironment(),
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      });
    } catch (error) {
      // No llegó a existir ningún proceso, ni por tanto ningún contenedor.
      finishOnce();
      reject(new WorkerError('unavailable', error.code ?? error.name));
      return;
    }

    const chunks = [];
    let size = 0;
    let settled = false;
    let spawned = false;
    let succeeded = false;
    let cleaning = false;
    let reason = null;

    const finish = (action) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      action();
    };
    const stop = (kind, detail) => {
      // Se recuerda el motivo y se mata el proceso; la promesa se resuelve cuando termina.
      reason ??= new WorkerError(kind, detail);
      child.kill('SIGKILL');
    };
    // Se llama cuando el proceso ya no existe. Un contenedor que no terminó bien puede seguir vivo
    // aunque su cliente haya terminado: se elimina, y el hueco solo se libera si se confirma.
    const cleanUp = () => {
      if (cleaning) return;
      cleaning = true;
      if (!container || succeeded || !spawned) return finishOnce();
      stopContainer(container, containerStop, log).then((stopped) => {
        if (stopped) finishOnce();
      }, () => {}); // un fallo inesperado deja el hueco ocupado, nunca lo libera
    };

    const timer = setTimeout(() => stop('timeout', `${timeoutMs} ms`), timeoutMs);

    child.on('spawn', () => { spawned = true; });

    child.on('error', (error) => {
      // El ejecutable no existe o no se puede lanzar (no hubo proceso), o falló una señal.
      finish(() => reject(reason ?? new WorkerError('unavailable', error.code ?? error.name)));
      if (!spawned) cleanUp();
    });

    child.stdout.on('data', (chunk) => {
      size += chunk.length;
      if (size > maxResponseBytes) stop('failed', 'response too large');
      else chunks.push(chunk);
    });
    // Lo que el worker escribe en su salida de error se descarta: no se registra ni se reenvía.
    child.stderr.resume();
    child.stdin.on('error', () => {});

    child.on('close', (code) => {
      finish(() => {
        if (reason) return reject(reason);
        let response;
        try {
          response = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        } catch {
          return reject(new WorkerError('failed', `exit ${code}, unreadable response`));
        }
        if (code !== 0 || !isResult(response, request.action)) {
          return reject(new WorkerError('failed', `exit ${code}, unexpected response`));
        }
        succeeded = true;
        resolve(response);
      });
      cleanUp();
    });

    child.stdin.end(JSON.stringify(request));
  });
}

/**
 * Elimina el contenedor y confirma que ya no existe. Hace como mucho retryDelaysMs.length + 1
 * intentos, uno detrás de otro, y cada orden se mata si tarda más de attemptTimeoutMs.
 * Devuelve true solo si un listado confirma que el contenedor ya no existe.
 */
async function stopContainer({ name, cli }, { attemptTimeoutMs, retryDelaysMs }, log) {
  if (!CONTAINER_NAME.test(name)) {
    log('playground: refused to stop a container with an unexpected name; its slot stays taken');
    return false;
  }
  const attempts = retryDelaysMs.length + 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (attempt > 0) await delay(retryDelaysMs[attempt - 1]);
    // Se ignora el resultado de "rm": puede fallar porque el contenedor ya no existe. Lo que
    // decide es el listado: sin error y vacío.
    await runTool(cli, ['rm', '-f', name], attemptTimeoutMs);
    const listed = await runTool(cli, ['ps', '-aq', '--filter', `name=^${name}$`], attemptTimeoutMs);
    if (listed.code === 0 && listed.stdout.trim() === '') return true;
  }
  log(`playground: container not confirmed stopped after ${attempts} attempts; its slot stays taken`);
  return false;
}

/** Ejecuta una orden de la herramienta de contenedores. code es null si no arrancó o se mató. */
function runTool(cli, args, timeoutMs) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(cli[0], [...cli.slice(1), ...args], {
        cwd: workDir,
        env: workerEnvironment(),
        stdio: ['ignore', 'pipe', 'ignore'],
        windowsHide: true,
      });
    } catch {
      resolve({ code: null, stdout: '' });
      return;
    }
    let stdout = '';
    let killed = false;
    let spawned = false;
    const timer = setTimeout(() => {
      killed = true;
      child.kill('SIGKILL');
    }, timeoutMs);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      if (stdout.length < 4096) stdout += chunk;
    });
    child.on('spawn', () => { spawned = true; });
    child.on('error', () => {
      if (spawned) return; // falló una señal: se espera a 'close'
      clearTimeout(timer);
      resolve({ code: null, stdout: '' });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code: killed ? null : code, stdout });
    });
  });
}
