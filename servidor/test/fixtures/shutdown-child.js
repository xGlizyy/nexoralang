// Solo para pruebas (lifecycle.test.js): un apagado real de createShutdown en un proceso propio, con un
// servidor HTTP en 127.0.0.1 y un puerto libre, y un pool simulado (nunca una base de datos).
//
//   node test/fixtures/shutdown-child.js <pool> <límite en ms> [real|soft]
//
// <pool>: never          la promesa de closePool no termina nunca, y no hay ningún otro recurso detrás
//         fast           cierra enseguida
//         slow           cierra al doble del límite (con un temporizador normal, como un socket que tarda)
//         reject         rechaza con un error de código EPOOL
//         same-deadline  cierra con el mismo retraso que el límite, con su temporizador puesto DESPUÉS
//                        (dentro de closePool, que se llama cuando el del límite ya existe): el límite
//                        vence primero, siempre
//         set-first      cierra con el mismo retraso que el límite, con su temporizador puesto ANTES de
//                        empezar el apagado: el pool cierra primero, siempre
// En los dos últimos, el orden no es azar: Node dispara los temporizadores del mismo retraso en el orden
// en que se pusieron, y entre uno y otro ejecuta las microtareas pendientes.
// real (por defecto): exit es process.exit, como en index.js. soft: exit solo fija process.exitCode, y
// el proceso termina cuando no le queda nada pendiente: así se ve si queda algún temporizador vivo.
//
// Cada línea lleva los milisegundos desde que empieza el apagado. Se escribe con writeSync para que
// nada se pierda al llamar a process.exit.

import { writeSync } from 'node:fs';
import http from 'node:http';
import { createShutdown } from '../../src/lifecycle.js';

const [pool, limit, mode = 'real'] = process.argv.slice(2);
const timeoutMs = Number(limit);
let started = 0;
const say = (line) => writeSync(1, `${Date.now() - started} ${line}\n`);

const POOLS = {
  never: () => new Promise(() => {}),
  fast: async () => {},
  slow: () => new Promise((resolve) => setTimeout(resolve, timeoutMs * 2)),
  reject: async () => { throw Object.assign(new Error('pool failed for ana@example.com'), { code: 'EPOOL' }); },
  'same-deadline': () => new Promise((resolve) => setTimeout(resolve, timeoutMs)),
  'set-first': () => setFirst,
};
if (!POOLS[pool] || !(timeoutMs > 0) || !['real', 'soft'].includes(mode)) throw new Error('usage: <never|fast|slow|reject|same-deadline|set-first> <ms> [real|soft]');

process.on('exit', (code) => say(`process exit ${code}`));

const server = http.createServer((req, res) => res.end('ok'));
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

const exit = mode === 'real'
  ? (code) => { say(`exit(${code})`); process.exit(code); }
  : (code) => { say(`exit(${code})`); process.exitCode = code; };
// set-first: el temporizador del pool se pone aquí, justo antes de empezar el apagado.
const setFirst = pool === 'set-first' ? new Promise((resolve) => setTimeout(resolve, timeoutMs)) : null;
const shutdown = createShutdown({ server, closePool: POOLS[pool], timeoutMs, log: say, exit });
started = Date.now();
shutdown('SIGTERM');
