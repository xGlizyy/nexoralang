// Lanza el worker de NEXORA (un proceso aparte por petición) y recoge su respuesta.
// El código del visitante nunca se ejecuta dentro del proceso del servidor.

import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

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

/**
 * Envía una petición al worker y devuelve su respuesta.
 * @param {string[]} command  Orden que arranca el worker.
 * @param {object} request    Lo que se escribe, como JSON, en su entrada estándar.
 * @param {{ timeoutMs: number, maxResponseBytes: number }} options
 */
export function runWorker(command, request, { timeoutMs, maxResponseBytes }) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(command[0], command.slice(1), {
        cwd: workDir,
        env: workerEnvironment(),
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      });
    } catch (error) {
      reject(new WorkerError('unavailable', error.code ?? error.name));
      return;
    }

    const chunks = [];
    let size = 0;
    let settled = false;
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

    const timer = setTimeout(() => stop('timeout', `${timeoutMs} ms`), timeoutMs);

    child.on('error', (error) => {
      // El ejecutable no existe o no se puede lanzar.
      finish(() => reject(new WorkerError('unavailable', error.code ?? error.name)));
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
        resolve(response);
      });
    });

    child.stdin.end(JSON.stringify(request));
  });
}
