// Proceso de prueba de integration-guard.test.js. Se lanza con --import test/integration/preflight.js
// y una lista de casos; cada caso intenta cargar servidor/src/ o mysql2 de una forma y escribe
// «caso: BLOCKED …», «caso: BLOCKED-MODULE …», «caso: LOADED», «caso: REFUSED» u «caso: OTHER código».
// Nunca conecta: la única conexión «verificada» es un objeto falso, y TEST_DB_PORT es 1. Las pruebas le
// dan PORT=0 y LISTEN_HOST=127.0.0.1: si index.js llegara a cargarse por un fallo, no tocaría el 3000.

import { createRequire } from 'node:module';
import { connectVerified, markRunner, useAppDatabase, verifyQueryable } from '../integration/guard.js';

console.log('PROBE STARTED');

const APP = '`nexora_test_app`@`127.0.0.1`';
const GRANTS = [
  `GRANT USAGE ON *.* TO ${APP}`,
  `GRANT SELECT, INSERT, DELETE ON \`nexora\\_test\`.* TO ${APP}`,
  `GRANT SELECT ON \`nexora_test_guard\`.\`marker\` TO ${APP}`,
];

/** Una conexión falsa que responde lo que esperan las guardas para el papel «app». */
function fakeConnection() {
  return {
    async query(sql) {
      if (sql.startsWith('SELECT DATABASE()')) return [[{ db: 'nexora_test', who: 'nexora_test_app@127.0.0.1' }]];
      if (sql.startsWith('SHOW GRANTS')) return [GRANTS.map((line) => ({ grant: line }))];
      if (sql.startsWith('SELECT GET_LOCK')) return [[{ got: 1 }]];
      return [[{ purpose: 'nexora-integration-tests-only' }]];
    },
    async end() {},
  };
}

const mark = () => markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
const require = createRequire(import.meta.url);
const name = 'db';

const CASES = {
  literal: () => import('../../src/config.js'),
  variable: () => import(['..', '..', 'src', `${name}.js`].join('/')),
  template: () => import(`../../src/${name}.js`),
  'top-level-export': () => import('./preflight-top-level.js'),
  'require-src': () => require('../../src/safe-log.js'),
  'require-mysql2': () => require('mysql2'),
  mysql2: () => import('mysql2/promise'),
  encoded: () => import('../../%73rc/config.js'),
  uppercase: () => import('../../SRC/config.js'),
  'runner-only': () => { mark(); return import('../../src/config.js'); },
  'mysql2-after-ready': async () => {
    mark();
    await verifyQueryable(fakeConnection(), 'app');
    useAppDatabase();
    return import('mysql2/promise');
  },
  unverified: () => { mark(); useAppDatabase(); },
  // Fuera de APP_MODULES: ni antes ni después de useAppDatabase().
  index: () => import('../../src/index.js'),
  migrate: () => import('../../src/migrate.js'),
  'require-index': () => require('../../src/index.js'),
  'require-migrate': () => require('../../src/migrate.js'),
  // La prueba de que index.js no se evaluó: habría registrado su manejador de SIGTERM (y escuchado).
  'not-evaluated': () => {
    console.log(`evidence: SIGTERM listeners ${process.listenerCount('SIGTERM')}`);
  },
  legit: async () => {
    mark();
    const connection = await connectVerified('app', { mysql: { createConnection: async () => fakeConnection() } });
    await connection.end();
    useAppDatabase();
    const { pool } = await import('../../src/db.js');
    await import(`../../src/${'safe-log'}.js`);
    await pool.end();
  },
};

for (const kind of process.argv.slice(2)) {
  try {
    await CASES[kind]();
    console.log(`${kind}: LOADED`);
  } catch (error) {
    const blocked = /^integration guard: (servidor\/src\/|mysql2) cannot be loaded here/.exec(error.message);
    const outside = /^integration guard: servidor\/src\/(\S+) is not one of the modules/.exec(error.message);
    if (blocked) console.log(`${kind}: BLOCKED ${blocked[1]}`);
    else if (outside) console.log(`${kind}: BLOCKED-MODULE ${outside[1]}`);
    else if (error.name === 'IntegrationGuardError') console.log(`${kind}: REFUSED`);
    else console.log(`${kind}: OTHER ${error.code ?? error.name}`);
  }
}
