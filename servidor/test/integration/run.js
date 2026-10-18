// Punto de entrada de `npm run test:integration`. Los archivos comparten nexora_test, así que se
// cargan aquí, en este orden, en un solo proceso, y node:test los ejecuta uno detrás de otro.
// migrations.test.js va primero: deja las tablas de la aplicación creadas para los demás.
//
// Antes de nada hacen falta la base y las cuentas de setup-admin.sql, y servidor/.env.integration
// (ignorado por git) con NODE_ENV=test, TEST_DB_HOST=127.0.0.1, TEST_DB_PORT, TEST_DB_NAME=nexora_test,
// TEST_DB_MIGRATOR_USER, TEST_DB_MIGRATOR_PASSWORD, TEST_DB_APP_USER y TEST_DB_APP_PASSWORD. Sin ese
// archivo, node no arranca. Las guardas (guard.js) detienen todo ante cualquier discrepancia.
//
// Las importaciones de abajo solo registran pruebas: ninguna conecta al cargarse. Las conexiones se
// abren en los `before` de cada archivo, cuando este archivo ya ha terminado de ejecutarse. Por eso
// markRunner, al final, llega a tiempo; y si sus comprobaciones fallan, el proceso no queda marcado y
// ninguna prueba consigue conectar.
//
// preflight.js va el primero: normalmente ya lo ha cargado `--import` (y no se repite); si no, se
// evalúa antes que cualquier archivo de pruebas y detiene un entorno inseguro.

import './preflight.js';
import { readdirSync } from 'node:fs';
import { after } from 'node:test';
import { markRunner, releaseRunLock } from './guard.js';
import './migrations.test.js';
import './auth.test.js';
import './sessions.test.js';
import './oauth.test.js';
import './errors.test.js';

// Al terminar todas las pruebas, se libera el bloqueo de la ejecución (guard.js). Si el proceso acaba
// antes, por cualquier motivo, lo libera el servidor al cerrarse la conexión.
after(() => releaseRunLock());

const FILES = ['migrations.test.js', 'auth.test.js', 'sessions.test.js', 'oauth.test.js', 'errors.test.js'];
const present = readdirSync(new URL('./', import.meta.url)).filter((name) => name.endsWith('.test.js'));
markRunner({ files: FILES, present });
