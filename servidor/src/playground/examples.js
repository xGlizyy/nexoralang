// Ejemplos del playground. Son los programas de nexora/examples, los mismos que ejecutan las
// pruebas del lenguaje: aquí no se copia ni se inventa ningún programa.

import { readFileSync } from 'node:fs';
import path from 'node:path';

// Qué ejemplos se ofrecen, en qué orden y con qué título. `expect` es lo que ocurre al ejecutarlo.
const CATALOGUE = [
  { id: 'hello', file: 'hello.nex', title: 'Hello world', expect: 'success' },
  { id: 'variables', file: 'variables.nex', title: 'Variables and scopes', expect: 'success' },
  { id: 'arithmetic', file: 'arithmetic.nex', title: 'Arithmetic', expect: 'success' },
  { id: 'types', file: 'types.nex', title: 'Types and conversions', expect: 'success' },
  { id: 'functions', file: 'functions.nex', title: 'Functions and recursion', expect: 'success' },
  { id: 'contracts', file: 'contracts.nex', title: 'Contracts', expect: 'success' },
  { id: 'refined-types', file: 'refined_types.nex', title: 'Refined types', expect: 'success' },
  { id: 'loops', file: 'loops.nex', title: 'Loops that say why they end', expect: 'success' },
  { id: 'texts', file: 'texts.nex', title: 'Texts', expect: 'success' },
  { id: 'lists', file: 'lists.nex', title: 'Lists and for', expect: 'success' },
  { id: 'type-errors', file: 'invalid/type_errors.nex', title: 'Type errors, on purpose', expect: 'invalid' },
  { id: 'runtime-error', file: 'failing/runtime_error.nex', title: 'A runtime error, on purpose', expect: 'runtime_error' },
  { id: 'contract-violation', file: 'failing/contract_violation.nex', title: 'A broken contract, on purpose', expect: 'contract_violation' },
  { id: 'refinement-violation', file: 'failing/refinement_violation.nex', title: 'A broken refined type, on purpose', expect: 'contract_violation' },
];

// La descripción es la primera frase del comentario con el que empieza el propio archivo. Llega
// hasta el primer punto: un título con dos puntos ("Lists: ...") se queda con lo que lo explica.
function descriptionOf(code) {
  const lines = [];
  for (const line of code.split(/\r?\n/)) {
    if (!line.startsWith('//')) break;
    lines.push(line.replace(/^\/\/\s?/, ''));
  }
  const text = lines.join(' ').trim();
  const firstSentence = text.match(/^.*?\.(?=\s|$)/);
  return firstSentence ? firstSentence[0] : text;
}

/** Lee los ejemplos del disco. Lanza si falta alguno: el servidor no debe ofrecer una lista rota. */
export function loadExamples(directory) {
  return CATALOGUE.map(({ id, file, title, expect }) => {
    const code = readFileSync(path.join(directory, file), 'utf8').replace(/\r\n/g, '\n');
    return { id, title, description: descriptionOf(code), filename: path.basename(file), expect, code };
  });
}
