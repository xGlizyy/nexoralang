// Cómo se describen los errores en el registro (src/safe-log.js): el tipo y un código conocido, nunca
// el mensaje, la pila ni los datos que lleven dentro.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describeError, describeRoute } from '../src/safe-log.js';

const EMAIL = 'ana@example.com';

test('the type and a known code, nothing else', () => {
  const mysql = Object.assign(new Error(`Duplicate entry '${EMAIL}' for key 'uq_users_email'`), {
    code: 'ER_DUP_ENTRY', errno: 1062, sql: `INSERT INTO users VALUES ('${EMAIL}', 'scrypt$...')`, sqlMessage: EMAIL,
  });
  assert.equal(describeError(mysql), 'Error ER_DUP_ENTRY');
  assert.equal(describeError(Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:3306'), { code: 'ECONNREFUSED' })), 'Error ECONNREFUSED');
  assert.equal(describeError(new TypeError(`Cannot read properties of undefined (reading '${EMAIL}')`)), 'TypeError');
  assert.equal(describeError(Object.assign(new Error('aborted'), { name: 'TimeoutError', code: 23 })), 'TimeoutError 23');
});

test('a code or a name that could carry data is left out', () => {
  for (const code of [`user=${EMAIL}`, 'Bearer abc.def', 'x'.repeat(65), '', 'a b', 1.5, { toString: () => EMAIL }]) {
    const text = describeError(Object.assign(new Error('m'), { code }));
    assert.equal(text, 'Error', String(code));
  }
  const named = Object.assign(new Error('m'), { name: `Error for ${EMAIL}` });
  assert.equal(describeError(named), 'Error');
});

test('values that are not errors are not written at all', () => {
  for (const value of [EMAIL, { password: 'secret' }, null, undefined, 42]) {
    assert.equal(describeError(value), 'non-error value');
  }
});

// Peticiones como las ve Express en un manejador de errores del montaje: baseUrl es la parte de la URL
// que coincidió con el montaje; route, la ruta que coincidió, si hubo alguna.
const request = (baseUrl, path, extra = {}) => ({ baseUrl, route: path === undefined ? undefined : { path }, path: `/x/${EMAIL}`, originalUrl: `/x/${EMAIL}?token=SECRET`, ...extra });

test('a route is logged by its template: the mount and the path written in the code', () => {
  assert.equal(describeRoute(request('/api/auth', '/login')), '/api/auth/login');
  assert.equal(describeRoute(request('/api/auth', '/:provider/callback')), '/api/auth/:provider/callback');
  assert.equal(describeRoute(request('', '/api/health')), '/api/health');
  // Express compara sin distinguir mayúsculas, y baseUrl copia las de la URL pedida.
  assert.equal(describeRoute(request('/API/Auth', '/login')), '/api/auth/login');
});

test('without a matching route, a fixed value: never the path, the URL or the query string', () => {
  for (const req of [request('/api/auth', undefined), request('', undefined), { baseUrl: '', path: `/${EMAIL}`, originalUrl: `/${EMAIL}` }, {}]) {
    assert.equal(describeRoute(req), '(no route)');
  }
});

test('a route that is not written as text (a pattern or a list) is not described', () => {
  assert.equal(describeRoute(request('/api', /^\/u\/(.+)$/)), '(no route)');
  assert.equal(describeRoute(request('/api', ['/a', '/b'])), '(no route)');
});

test('the template is short and has only plain characters', () => {
  assert.equal(describeRoute(request('/api', '/a b\n{c}')), '/api/a_b__c_');
  assert.equal(describeRoute(request('/api', `/${'p'.repeat(200)}`)).length, 80);
});
