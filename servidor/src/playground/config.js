// Configuración del playground. No depende de la base de datos: el playground no guarda nada.

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isProduction } from '../environment.js';

/** En la orden de un contenedor, el servidor sustituye este marcador por un nombre único. */
export const CONTAINER_PLACEHOLDER = '{container}';
// Se reconocen para rechazar una orden de contenedor que no sea la admitida, no porque se admitan.
const CONTAINER_TOOLS = new Set(['docker', 'podman']);

/**
 * La única orden de contenedor admitida: "docker", "run", estas opciones exactamente una vez cada
 * una y en cualquier orden, y la imagen (CONTAINER_IMAGE) como último elemento. Los valores son
 * fijos: cambiar un límite, el aislamiento o la imagen es una decisión explícita, que se toma aquí
 * y no en servidor/.env.
 */
export const CONTAINER_FLAGS = Object.freeze(['--rm', '-i', '--init', '--read-only']);
export const CONTAINER_OPTIONS = Object.freeze([
  ['--name', CONTAINER_PLACEHOLDER],
  ['--network', 'none'],
  ['--cap-drop', 'ALL'],
  ['--security-opt', 'no-new-privileges'],
  ['--pids-limit', '32'],
  ['--memory', '256m'],
  ['--memory-swap', '256m'],
  ['--cpus', '0.5'],
  ['--user', '65534:65534'],
  ['--tmpfs', '/tmp:rw,size=1m,noexec'],
  // Solo la imagen local: si no existe, Docker falla (código 125) en vez de descargar otra.
  ['--pull', 'never'],
].map((pair) => Object.freeze(pair)));
// La única imagen admitida es la local de Nexora, con o sin etiqueta (la gramática de etiquetas de
// Docker). Sin ruta, sin registro y sin digest: ningún nombre que pueda resolverse fuera del equipo.
export const CONTAINER_IMAGE = 'nexora-worker';
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const IMAGE = new RegExp(`^${escapeRegExp(CONTAINER_IMAGE)}(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?$`);

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
    throw new Error('PLAYGROUND_WORKER_COMMAND debe ser una lista JSON de textos, por ejemplo ["/srv/nexora/nexora/.venv/bin/python","-I","-m","nexora.worker"]; la orden de contenedor admitida está en servidor/.env.example');
  }
  checkContainerCommand(command);
  return command;
}

// path.win32 separa por "\" y por "/": el resultado es el mismo en cualquier sistema operativo,
// también para una ruta de Windows leída en Linux o macOS.
export const isContainerTool = (part) => CONTAINER_TOOLS.has(path.win32.basename(part).replace(/\.exe$/i, '').toLowerCase());

const invalid = (detail) => new Error(`PLAYGROUND_WORKER_COMMAND ${detail}. La orden de contenedor admitida está en servidor/.env.example y en nexora/docs/playground.md (revisa servidor/.env)`);

// Una orden que lleva el marcador o nombra docker o podman en cualquier posición es una orden de
// contenedor, y tiene que ser exactamente la admitida (CONTAINER_FLAGS y CONTAINER_OPTIONS). Las
// demás son el modo de proceso y no se comprueban. Matar `docker run` no detiene el contenedor:
// `--name {container}` permite eliminarlo, y `--init` evita que Python sea el proceso 1, que ignora
// las señales sin manejador (SIGALRM). Las opciones van antes de la imagen, porque lo que va detrás
// llega al programa del contenedor y no a Docker.
function checkContainerCommand(command) {
  if (!command.some((part) => part.includes(CONTAINER_PLACEHOLDER) || isContainerTool(part))) return;
  if (command[0] !== 'docker' || command[1] !== 'run') {
    throw invalid('ejecuta un contenedor, pero no empieza por "docker","run": no se admiten rutas al ejecutable, sudo, podman, "container run" ni opciones globales de Docker');
  }
  const values = new Map(CONTAINER_OPTIONS);
  const seen = new Set();
  let at = 2;
  while (at < command.length && command[at].startsWith('-')) {
    const option = command[at];
    if (!CONTAINER_FLAGS.includes(option) && !values.has(option)) {
      throw invalid(`contiene la opción "${option}", que no está admitida (tampoco la forma --opción=valor)`);
    }
    if (seen.has(option)) throw invalid(`repite la opción "${option}"`);
    seen.add(option);
    if (!values.has(option)) {
      at += 1;
      continue;
    }
    const expected = values.get(option);
    if (at + 1 >= command.length) throw invalid(`termina en "${option}" sin su valor "${expected}"`);
    if (command[at + 1] !== expected) {
      throw invalid(`da a "${option}" el valor "${command[at + 1]}"; el único admitido es "${expected}"`);
    }
    at += 2;
  }
  if (at >= command.length) throw invalid('no termina en el nombre de la imagen');
  if (at < command.length - 1) {
    throw invalid(`tiene elementos después de la imagen "${command[at]}": Docker no los aplicaría, se los pasaría al programa del contenedor`);
  }
  const missing = [
    ...CONTAINER_FLAGS.filter((flag) => !seen.has(flag)).map((flag) => `"${flag}"`),
    ...CONTAINER_OPTIONS.filter(([option]) => !seen.has(option)).map(([option, value]) => `"${option}","${value}"`),
  ];
  if (missing.length > 0) throw invalid(`no incluye antes de la imagen: ${missing.join(', ')}`);
  if (!IMAGE.test(command[at])) {
    throw invalid(`termina en "${command[at]}", que no es un nombre de imagen admitido: solo "${CONTAINER_IMAGE}" o "${CONTAINER_IMAGE}:<etiqueta>", la imagen local`);
  }
}

// En producción, el playground activado solo arranca con la orden de contenedor admitida. El modo de
// proceso ejecuta el código de los visitantes con los permisos del servidor, sin aislamiento: sirve
// para probar en un equipo propio, nunca para un servidor público. Que la orden de contenedor esté
// configurada no demuestra que el aislamiento funcione: eso se comprueba aparte, con Docker real
// (nexora/docs/playground.md, «Comprobar el aislamiento»).
function checkProductionIsolation(enabled, command) {
  if (!enabled || !isProduction(process.env.NODE_ENV)) return;
  if (command.includes(CONTAINER_PLACEHOLDER)) return; // ya validada por checkContainerCommand
  throw new Error('PLAYGROUND_ENABLED=true en producción exige PLAYGROUND_WORKER_COMMAND con la orden de contenedor admitida: sin ella, el código de los visitantes se ejecutaría en este equipo sin aislamiento. Desactiva el playground o configura la orden de servidor/.env.example (revisa servidor/.env)');
}

/** Lee la configuración del entorno. Se llama una vez al arrancar; las pruebas pasan la suya. */
export function loadPlaygroundConfig() {
  const timeoutMs = integer('PLAYGROUND_TIMEOUT_MS', 2000, 100);
  const enabled = enabledFlag();
  const command = workerCommand();
  checkProductionIsolation(enabled, command);
  return {
    enabled,
    workerCommand: command,
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
