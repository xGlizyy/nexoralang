// Configuración del playground. No depende de la base de datos: el playground no guarda nada.

import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** En la orden de un contenedor, el servidor sustituye este marcador por un nombre único. */
export const CONTAINER_PLACEHOLDER = '{container}';
const CONTAINER_TOOLS = new Set(['docker', 'podman']);

/**
 * Eliminar un contenedor que no terminó bien: tiempo máximo de cada orden y esperas entre
 * intentos. Son retryDelaysMs.length + 1 intentos (seis), separados por 31 s de esperas en total;
 * cada intento ejecuta dos órdenes (rm y ps) y cada una se mata a los attemptTimeoutMs. Si ningún
 * intento confirma que el contenedor ya no existe, su hueco sigue ocupado hasta reiniciar el servidor.
 */
export const CONTAINER_STOP = Object.freeze({
  attemptTimeoutMs: 10_000,
  retryDelaysMs: Object.freeze([1000, 2000, 4000, 8000, 16_000]),
});

const root = (relative) => fileURLToPath(new URL(`../../../${relative}`, import.meta.url));

function integer(name, fallback, minimum = 1) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < minimum) {
    throw new Error(`${name} debe ser un entero mayor o igual que ${minimum} (revisa servidor/.env)`);
  }
  return value;
}

function list(name) {
  return (process.env[name] ?? '').split(',').map((item) => item.trim()).filter(Boolean);
}

// El playground ejecuta código de cualquier visitante, así que solo se activa si se pide de forma
// explícita: sin definir, vacío o "false", queda desactivado. Cualquier otro valor ("True", "1"...)
// impide arrancar, para que una errata no lo deje activado ni desactivado sin que nadie lo note.
function enabledFlag() {
  const raw = process.env.PLAYGROUND_ENABLED;
  if (raw === undefined || raw === '' || raw === 'false') return false;
  if (raw === 'true') return true;
  throw new Error('PLAYGROUND_ENABLED debe ser exactamente "true" o "false" (revisa servidor/.env)');
}

// Python del entorno virtual del núcleo. En producción conviene indicarlo con NEXORA_PYTHON.
function defaultPython() {
  return process.platform === 'win32'
    ? root('nexora/.venv/Scripts/python.exe')
    : root('nexora/.venv/bin/python');
}

// Orden que arranca el worker. Por defecto, un proceso de Python en modo aislado (-I: ignora
// variables PYTHON*, el directorio actual y los paquetes del usuario). Para ejecutar el worker
// dentro de un contenedor se sustituye entera con PLAYGROUND_WORKER_COMMAND (una lista JSON).
function workerCommand() {
  const custom = process.env.PLAYGROUND_WORKER_COMMAND;
  if (!custom) return [process.env.NEXORA_PYTHON || defaultPython(), '-I', '-m', 'nexora.worker'];
  let command;
  try {
    command = JSON.parse(custom);
  } catch {
    command = null;
  }
  if (!Array.isArray(command) || command.length === 0 || !command.every((part) => typeof part === 'string')) {
    throw new Error('PLAYGROUND_WORKER_COMMAND debe ser una lista JSON de textos, por ejemplo ["docker","run","--rm","-i","nexora-worker"]');
  }
  checkContainerCommand(command);
  return command;
}

// path.win32 separa por "\" y por "/": el resultado es el mismo en cualquier sistema operativo,
// también para una ruta de Windows leída en Linux o macOS.
export const isContainerTool = (part) => CONTAINER_TOOLS.has(path.win32.basename(part).replace(/\.exe$/i, '').toLowerCase());

// Matar la orden `docker run` no detiene el contenedor: el servidor tiene que poder nombrarlo para
// eliminarlo. Por eso una orden de contenedor sin `--name {container}` impide arrancar. `--init`
// evita que Python sea el proceso 1 del contenedor, que ignora las señales sin manejador (SIGALRM).
function checkContainerCommand(command) {
  const run = command.indexOf('run');
  const marks = command.filter((part) => part === CONTAINER_PLACEHOLDER).length;
  if (marks === 0) {
    if (run > 0 && command.slice(0, run).some(isContainerTool)) {
      throw new Error(`PLAYGROUND_WORKER_COMMAND ejecuta un contenedor sin "--name","${CONTAINER_PLACEHOLDER}": el servidor no podría detenerlo (revisa servidor/.env)`);
    }
    return;
  }
  const at = command.indexOf(CONTAINER_PLACEHOLDER);
  if (marks > 1 || run < 1 || at < run || command[at - 1] !== '--name') {
    throw new Error(`PLAYGROUND_WORKER_COMMAND debe contener "--name","${CONTAINER_PLACEHOLDER}" una sola vez, después de "run" (revisa servidor/.env)`);
  }
  if (!command.slice(run + 1).includes('--init')) {
    throw new Error('PLAYGROUND_WORKER_COMMAND debe incluir "--init" después de "run" (revisa servidor/.env)');
  }
}

/** Lee la configuración del entorno. Se llama una vez al arrancar; las pruebas pasan la suya. */
export function loadPlaygroundConfig() {
  const timeoutMs = integer('PLAYGROUND_TIMEOUT_MS', 2000, 100);
  return {
    enabled: enabledFlag(),
    workerCommand: workerCommand(),
    examplesDir: process.env.NEXORA_EXAMPLES_DIR || root('nexora/examples'),

    // Límites de una petición.
    maxCodeBytes: integer('PLAYGROUND_MAX_CODE_BYTES', 64 * 1024),
    timeoutMs,
    maxOutputBytes: integer('PLAYGROUND_MAX_OUTPUT_BYTES', 64 * 1024),
    maxTextChars: integer('PLAYGROUND_MAX_TEXT_CHARS', 256 * 1024),
    // Solo los aplica el sistema operativo en Linux y macOS (ver nexora/docs/playground.md).
    memoryBytes: integer('PLAYGROUND_MEMORY_MB', 512) * 1024 * 1024,

    // Límites del servicio.
    maxConcurrent: integer('PLAYGROUND_MAX_CONCURRENT', 4),
    maxQueue: integer('PLAYGROUND_MAX_QUEUE', 8, 0),
    rateLimit: {
      windowMs: integer('PLAYGROUND_RATE_WINDOW_MS', 60_000, 1000),
      limit: integer('PLAYGROUND_RATE_LIMIT', 30),
    },

    // Orígenes que pueden llamar a la API además del propio. Vacío: solo el mismo origen.
    allowedOrigins: list('PLAYGROUND_ALLOWED_ORIGINS'),

    containerStop: CONTAINER_STOP,
  };
}
