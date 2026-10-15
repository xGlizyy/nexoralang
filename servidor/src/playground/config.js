// Configuración del playground. No depende de la base de datos: el playground no guarda nada.

import { fileURLToPath } from 'node:url';

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
  return command;
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
  };
}
