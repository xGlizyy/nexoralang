// Worker falso para las pruebas: se comporta según su primer argumento.
// Sirve para comprobar cómo reacciona el servidor cuando el worker real falla o miente.

const mode = process.argv[2];
const answer = (output) => ({
  schema: 'nexora.result/1', action: 'run', status: 'success', output, diagnostics: [], message: null,
});

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  if (mode === 'garbage') {
    process.stdout.write('this is not JSON');
  } else if (mode === 'crash') {
    process.stderr.write('Traceback (most recent call last): secret/internal/path.py\n');
    process.exit(3);
  } else if (mode === 'wrong-shape') {
    process.stdout.write(JSON.stringify({ schema: 'nexora.result/1', status: 'success' }));
  } else if (mode === 'wrong-status') {
    process.stdout.write(JSON.stringify({ ...answer(''), status: 'everything-is-fine' }));
  } else if (mode === 'internal-error') {
    process.stdout.write(JSON.stringify({ schema: 'nexora.result/1', status: 'internal_error' }));
    process.exit(1);
  } else if (mode === 'hang') {
    setInterval(() => {}, 1000);
  } else if (mode === 'flood') {
    const block = 'x'.repeat(1024 * 1024);
    const write = () => { while (process.stdout.write(block)); process.stdout.once('drain', write); };
    write();
  } else if (mode === 'environment') {
    // Devuelve lo que el worker puede ver de su entorno, para comprobar que es lo mínimo.
    process.stdout.write(JSON.stringify(answer(JSON.stringify({
      variables: Object.keys(process.env).sort(),
      directory: process.cwd(),
      request: Object.keys(JSON.parse(input)).sort(),
    }))));
  }
});
