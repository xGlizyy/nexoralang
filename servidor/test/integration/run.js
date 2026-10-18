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
import { closeAppContext } from './context.js';
import { markRunner, releaseRunLock } from './guard.js';
import './migrations.test.js';
import './auth.test.js';
import './sessions.test.js';
import './oauth.test.js';
import './errors.test.js';

// Al terminar todas las pruebas, en un solo hook: primero se cierra el pool real de src/db.js, que
// comparten cuatro archivos y que mantiene vivos los sockets del proceso, y después se libera el
// bloqueo de la ejecución (guard.js). El bloqueo se intenta liberar en el finally aunque el pool
// falle, y en un único hook el orden no depende de cómo se ejecuten varios hooks raíz. Si fallan los
// dos cierres, se lanzan los dos errores juntos: un finally que solo lanza el último taparía el
// primero, que es justo el que explica por qué el proceso no podía terminar. Si el proceso acaba
// antes, por cualquier motivo, lo libera el servidor al cerrarse la conexión del bloqueo.
after(async () => {
  let poolFailure = null;
  try {
    await closeAppContext();
  } catch (error) {
    poolFailure = error;
  } finally {
    let lockFailure = null;
    try {
      await releaseRunLock();
    } catch (error) {
      lockFailure = error;
    }
    const failures = [poolFailure, lockFailure].filter(Boolean);
    if (failures.length === 1) throw failures[0];
    if (failures.length > 1) throw new AggregateError(failures, 'the integration run could not close the shared pool and the run lock cleanly');
  }
});

const FILES = ['migrations.test.js', 'auth.test.js', 'sessions.test.js', 'oauth.test.js', 'errors.test.js'];
const present = readdirSync(new URL('./', import.meta.url)).filter((name) => name.endsWith('.test.js'));
markRunner({ files: FILES, present });
