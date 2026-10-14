// El script `npm test` nombra cada archivo de prueba: `node --test` solo acepta patrones desde
// Node 21, y engines admite Node 20.6. Esta prueba comprueba que la lista está completa y al día.

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const { scripts } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));

test('npm test runs every test file of the server, and only files that exist', () => {
  const listed = scripts.test.split(/\s+/).filter((word) => word.startsWith('test/'));
  const present = readdirSync(new URL('./', import.meta.url))
    .filter((name) => name.endsWith('.test.js'))
    .map((name) => `test/${name}`);
  assert.deepEqual(present.filter((file) => !listed.includes(file)), [], 'test files that `npm test` does not run');
  assert.deepEqual(listed.filter((file) => !present.includes(file)), [], 'files in `npm test` that do not exist');
});
