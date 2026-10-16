// Docker falso para las pruebas del ciclo de vida de los contenedores. No usa Docker.
//
//   node fake-docker.js <directorio de estado> run … --name <nombre> … <modo | from-state>
//   node fake-docker.js <directorio de estado> rm -f <nombre>
//   node fake-docker.js <directorio de estado> ps -aq --filter name=^<nombre>$
//
// Un contenedor "existe" mientras hay un archivo con su nombre en <estado>/containers. Así se
// imita lo que hace Docker de verdad: matar el cliente `run` no elimina el contenedor.
// Cada llamada se anota en <estado>/calls.jsonl. El archivo <estado>/stop decide cómo responden
// rm y ps: "ok" (o ausente), "never" (nunca se elimina), "fail:N" (los N primeros listados
// todavía lo muestran), "hang" (rm no termina nunca).

import { appendFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const [state, command, ...args] = process.argv.slice(2);
const containers = path.join(state, 'containers');
mkdirSync(containers, { recursive: true });

const record = (entry) => appendFileSync(path.join(state, 'calls.jsonl'), `${JSON.stringify(entry)}\n`);
const read = (name, fallback) => (existsSync(path.join(state, name)) ? readFileSync(path.join(state, name), 'utf8').trim() : fallback);
const stopMode = read('stop', 'ok');

if (command === 'run') {
  const name = args[args.indexOf('--name') + 1];
  // El modo es el último argumento (donde iría la imagen), o "from-state": el archivo <estado>/run.
  const mode = args.at(-1) === 'from-state' ? read('run', 'ok') : args.at(-1);
  record({ command, name, args });
  if (mode === 'refused') {
    // Docker rechaza la orden antes de crear el contenedor (imagen inexistente, sin permiso...).
    process.exit(125);
  }
  writeFileSync(path.join(containers, name), 'running');
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => { input += chunk; });
  process.stdin.on('end', () => {
    const request = JSON.parse(input);
    if (mode === 'ok') {
      process.stdout.write(JSON.stringify({
        schema: 'nexora.result/1', action: request.action, status: 'success', output: 'ok\n', diagnostics: [], message: null,
      }));
      rmSync(path.join(containers, name)); // --rm: el contenedor terminó y se borra
    } else if (mode === 'hang') {
      setInterval(() => {}, 1000);
    } else if (mode === 'flood') {
      const block = 'x'.repeat(1024 * 1024);
      const write = () => { while (process.stdout.write(block)); process.stdout.once('drain', write); };
      write();
    } else if (mode === 'garbage') {
      process.stdout.write('this is not JSON');
      process.exitCode = 1;
    }
  });
} else if (command === 'rm') {
  const name = args.at(-1);
  record({ command, name, args });
  if (stopMode === 'hang') {
    setInterval(() => {}, 1000);
  } else if (stopMode !== 'never') {
    rmSync(path.join(containers, name), { force: true });
  }
} else if (command === 'ps') {
  const name = args.at(-1).replace(/^name=\^/, '').replace(/\$$/, '');
  record({ command, name, args });
  let listed = existsSync(path.join(containers, name)) || stopMode === 'never';
  const failing = /^fail:(\d+)$/.exec(stopMode);
  if (failing) {
    const seen = Number(read('ps-count', '0')) + 1;
    writeFileSync(path.join(state, 'ps-count'), String(seen));
    listed = seen <= Number(failing[1]);
  }
  if (listed) process.stdout.write('0123456789ab\n');
} else {
  process.exit(2);
}
