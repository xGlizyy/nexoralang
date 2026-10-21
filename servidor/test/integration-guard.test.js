// Las guardas de las pruebas de integración (test/integration/guard.js), sin base de datos: se les dan
// configuraciones, identidades, permisos y filas, y tienen que rechazar todo lo que no sea exactamente
// lo autorizado en test/integration/setup-admin.sql. Se ejecutan con `npm test`; nunca conectan.

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { afterEach, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import nodeModule from 'node:module';
import {
  APP_MODULES, APP_TABLES, GUARD_SQL, GUARD_VALUE, IntegrationGuardError, RESET_SQL, checkGrants, checkGuardRows,
  HOOK_MINIMUMS, checkHookSupport, checkIdentity, checkLockResult, checkModuleLoad, checkPreflight, connectVerified, existingAppTables,
  holdRunLock, markRunner, migratorProcessEnv, openVerifiedPool, readIntegrationConfig, readMigrationChildConfig,
  releaseRunLock, resetAppTables, resetOwnVariablesForTests, resetRunnerForTests, runVerifiedMigration, RUN_LOCK,
  undoAfter, useAppDatabase, verifyQueryable, assertRunLock, hookSupportProblem,
} from './integration/guard.js';
import { operatingSystemVariables } from './platform.js';

// El gancho de preflight.js necesita module.registerHooks y una de las ramas medidas de HOOK_MINIMUMS:
// Node 22.22.3 o posterior en la rama 22, o 24.14.0 o posterior en la rama 24; ninguna otra rama
// (hookSupportProblem en guard.js). En otro Node, las pruebas que lanzan procesos con preflight.js se
// omiten y dicen por qué; la que simula la ausencia de registerHooks, no.
const HOOK_PROBLEM = hookSupportProblem(nodeModule.registerHooks);
const HOOKS = HOOK_PROBLEM === null ? {} : { skip: HOOK_PROBLEM };

const PASSWORD = 'only-a-test-value-x';
const ENV = Object.freeze({
  NODE_ENV: 'test', TEST_DB_HOST: '127.0.0.1', TEST_DB_PORT: '3306', TEST_DB_NAME: 'nexora_test',
  TEST_DB_MIGRATOR_USER: 'nexora_test_migrator', TEST_DB_MIGRATOR_PASSWORD: PASSWORD,
  TEST_DB_APP_USER: 'nexora_test_app', TEST_DB_APP_PASSWORD: PASSWORD,
});
const env = (changes = {}) => {
  const result = { ...ENV, ...changes };
  for (const [name, value] of Object.entries(changes)) if (value === undefined) delete result[name];
  return result;
};
const refused = (fn, pattern) => assert.throws(fn, (error) => error instanceof IntegrationGuardError && pattern.test(error.message) && !error.message.includes(PASSWORD));

// Las líneas de SHOW GRANTS que dejaría setup-admin.sql, en el formato de MySQL 8 y en el de MariaDB.
// En el permiso sobre la base entera, el «_» va escapado (`nexora\_test`.*): sin escapar es un comodín.
// En los permisos de tabla el nombre de la base es literal y va sin escapar.
const APP = '`nexora_test_app`@`127.0.0.1`';
const MIG = '`nexora_test_migrator`@`127.0.0.1`';
const ESCAPED = '`nexora\\_test`';
const MYSQL = {
  app: [
    `GRANT USAGE ON *.* TO ${APP}`,
    `GRANT SELECT, INSERT, DELETE ON ${ESCAPED}.* TO ${APP}`,
    `GRANT SELECT ON \`nexora_test_guard\`.\`marker\` TO ${APP}`,
  ],
  migrator: [
    `GRANT USAGE ON *.* TO ${MIG}`,
    `GRANT INSERT, CREATE, REFERENCES, ALTER ON \`nexora_test\`.\`oauth_accounts\` TO ${MIG}`,
    `GRANT INSERT, CREATE, REFERENCES, ALTER ON \`nexora_test\`.\`sessions\` TO ${MIG}`,
    `GRANT INSERT, CREATE, REFERENCES, ALTER ON \`nexora_test\`.\`users\` TO ${MIG}`,
    `GRANT SELECT ON \`nexora_test_guard\`.\`marker\` TO ${MIG}`,
  ],
};
const HASH = '*0123456789ABCDEF0123456789ABCDEF01234567';
const MARIADB = {
  app: [`GRANT USAGE ON *.* TO ${APP} IDENTIFIED BY PASSWORD '${HASH}' WITH MAX_USER_CONNECTIONS 30`, MYSQL.app[1], MYSQL.app[2]],
};

/**
 * Una conexión simulada que responde lo que le digan y anota todo lo que se le pide. Sus permisos
 * (`grants`) se pueden cambiar después, como si alguien los cambiara en el servidor. `lock` dice qué
 * responden GET_LOCK (`got`) e IS_USED_LOCK(…) = CONNECTION_ID() (`mine`), o con qué error fallan.
 */
function fakeConnection({ identity = { db: 'nexora_test', who: 'nexora_test_app@127.0.0.1' }, grants = MYSQL.app, guard = [{ purpose: GUARD_VALUE }], lock = {} } = {}) {
  const asked = [];
  const params = [];
  const { got = 1, mine = 1, lockError = null, checkError = null, releaseError = null, endError = null } = lock;
  return {
    asked,
    params,
    grants,
    lock: { got, mine },
    ended: false,
    closed: false,
    async query(sql, values) {
      asked.push(sql);
      params.push(values);
      if (sql.startsWith('SELECT GET_LOCK')) {
        if (lockError) throw lockError;
        return [[{ got: this.lock.got }]];
      }
      if (sql.startsWith('SELECT IS_USED_LOCK')) {
        if (checkError) throw checkError;
        return [[{ mine: this.lock.mine }]];
      }
      if (sql.startsWith('SELECT RELEASE_LOCK')) {
        if (releaseError) throw releaseError;
        return [[{ released: 1 }]];
      }
      if (sql.startsWith('SELECT DATABASE()')) return [[identity]];
      if (sql.startsWith('SHOW GRANTS')) return [this.grants.map((line) => ({ 'Grants for x': line }))];
      if (sql === GUARD_SQL) {
        if (guard instanceof Error) throw guard;
        return [guard];
      }
      return [[]];
    },
    async end() {
      if (endError) throw endError;
      this.ended = true;
    },
    // La conexión real expone close() (mysql2 lo delega en la base): no espera a la cola de comandos,
    // marca la conexión cerrada y cierra el socket. Es lo que releaseRunLock() usa en su finally.
    async close() { this.closed = true; },
  };
}

afterEach(() => {
  resetOwnVariablesForTests();
  resetRunnerForTests();
});

const SRC = new URL('../src/', import.meta.url).href;
const REPO = new URL('../../', import.meta.url).href;

/**
 * Los especificadores de las importaciones y reexportaciones ESTÁTICAS de un archivo (no import()),
 * también sin espacios (import{a}from'x', import'x') y con export * from.
 */
function staticSpecifiers(source) {
  const found = [];
  for (const match of source.matchAll(/^\s*(?:import|export)\b[^;]*?\bfrom\s*['"]([^'"]+)['"]/gm)) found.push(match[1]);
  for (const match of source.matchAll(/^\s*import\s*['"]([^'"]+)['"]/gm)) found.push(match[1]);
  return found;
}

/**
 * Recorre el grafo de importaciones estáticas desde `roots` y devuelve las cadenas que llegan a src/
 * del servidor o a mysql2. Sigue los archivos locales del repositorio; los paquetes (express, node:)
 * no se recorren.
 */
function staticImportViolations(roots) {
  const violations = [];
  const seen = new Set();
  const visit = (url, chain) => {
    if (seen.has(url.href)) return;
    seen.add(url.href);
    for (const specifier of staticSpecifiers(readFileSync(url, 'utf8'))) {
      const path = [...chain, specifier];
      if (/^mysql2(\/|$)/.test(specifier)) {
        violations.push(path.join(' -> '));
        continue;
      }
      if (!specifier.startsWith('.')) continue;
      const target = new URL(specifier, url);
      if (target.href.startsWith(SRC)) {
        violations.push(path.join(' -> '));
        continue;
      }
      if (target.href.startsWith(REPO) && target.pathname.endsWith('.js')) visit(target, path);
    }
  };
  for (const root of roots) visit(root, [root.pathname.split('/').slice(-2).join('/')]);
  return violations;
}

/** El código sin comentarios de bloque ni de línea completa, que pueden nombrar algo para explicarlo. */
const withoutComments = (source) => source.replace(/\/\*[\s\S]*?\*\//g, '').split('\n').filter((line) => !/^\s*\/\//.test(line)).join('\n');

/**
 * Lo que las comprobaciones de texto encuentran en un archivo de test/integration/ (`file` es su
 * nombre): un aviso temprano, en `npm test`, de lo que el gancho de preflight.js pararía al ejecutar.
 * Son heurísticas sobre código con el formato habitual, no un análisis sintáctico.
 */
function sourceProblems(file, source) {
  const code = withoutComments(source);
  const problems = [];
  if (/\bcreateRequire\b|\brequire\s*\(/.test(code)) problems.push('require or createRequire');
  if (/process\.env\s*\[/.test(code)) problems.push('process.env[...]');
  // DB_ sin nada delante (TEST_DB_* sí se admite), también partido: 'DB_' + 'HOST'.
  if (file.endsWith('.test.js') && /(?<!\w)DB_/.test(code)) problems.push('a DB_* variable');
  // Una línea sin sangría con await antes de cualquier async: await a nivel superior.
  if (/^(?![\s}])(?:(?!\basync\b)[^\n])*\bawait\b/m.test(code)) problems.push('top-level await');
  const calls = ['appContext(', 'connectVerified(', 'openVerifiedPool(', 'useAppDatabase(', 'runVerifiedMigration('].map((call) => code.indexOf(call)).filter((at) => at >= 0);
  const firstGuard = Math.min(...calls);
  for (const match of code.matchAll(/\bimport\s*\(([^)]*)\)/g)) {
    const literal = match[1].trim().match(/^(['"])([^'"`$\\]+)\1$/);
    if (!literal) {
      problems.push(`import() of something that is not a plain string: ${match[1].trim()}`);
      continue;
    }
    const target = literal[2];
    if (/^mysql2(\/|$)/.test(target) && file !== 'guard.js') problems.push(`import('${target}') outside guard.js`);
    if (/(^|\/)src\//.test(target) && !(match.index > firstGuard)) problems.push(`import('${target}') before any guard is called`);
  }
  return problems;
}

describe('the configuration', () => {
  test('the authorized configuration of each role is accepted', () => {
    assert.deepEqual(readIntegrationConfig(env(), 'app'), { host: '127.0.0.1', port: 3306, user: 'nexora_test_app', password: PASSWORD, database: 'nexora_test' });
    assert.equal(readIntegrationConfig(env(), 'migrator').user, 'nexora_test_migrator');
  });

  test('variables of servidor/.env (DB_*) stop everything, even one of them', () => {
    for (const name of ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']) {
      refused(() => readIntegrationConfig(env({ [name]: 'x' }), 'app'), /never use servidor\/\.env/);
    }
  });

  test('NODE_ENV other than test, also production or unset, is refused', () => {
    for (const value of ['production', 'development', '', undefined, 'TEST']) refused(() => readIntegrationConfig(env({ NODE_ENV: value }), 'app'), /NODE_ENV/);
  });

  test('another host, also localhost or a name, is refused', () => {
    for (const host of ['localhost', '::1', '127.0.0.2', 'db.example.com', '0.0.0.0', '', undefined, ' 127.0.0.1']) {
      refused(() => readIntegrationConfig(env({ TEST_DB_HOST: host }), 'app'), /TEST_DB_HOST/);
    }
  });

  test('another database name, however close, is refused', () => {
    for (const name of ['nexora', 'NEXORA_TEST', 'nexora_test2', 'nexora_test ', 'nexora_test_guard', 'nexora_test`;DROP', 'test', undefined]) {
      refused(() => readIntegrationConfig(env({ TEST_DB_NAME: name }), 'app'), /TEST_DB_NAME/);
    }
  });

  test('a user of another role, or any other user, is refused', () => {
    refused(() => readIntegrationConfig(env({ TEST_DB_APP_USER: 'nexora_test_migrator' }), 'app'), /TEST_DB_APP_USER/);
    refused(() => readIntegrationConfig(env({ TEST_DB_MIGRATOR_USER: 'root' }), 'migrator'), /TEST_DB_MIGRATOR_USER/);
    refused(() => readIntegrationConfig(env({ TEST_DB_APP_USER: undefined }), 'app'), /TEST_DB_APP_USER/);
  });

  test('a missing password, or the placeholder of setup-admin.sql, is refused without showing it', () => {
    for (const password of [undefined, '', '<CONTRASEÑA_APLICACION_SOLO_PRUEBAS>']) {
      refused(() => readIntegrationConfig(env({ TEST_DB_APP_PASSWORD: password }), 'app'), /TEST_DB_APP_PASSWORD/);
    }
  });

  test('a port that is not a port is refused', () => {
    for (const port of ['0', '65536', '3306x', '', undefined, '-1']) refused(() => readIntegrationConfig(env({ TEST_DB_PORT: port }), 'app'), /TEST_DB_PORT/);
  });

  test('an unknown role is refused', () => {
    for (const role of ['root', 'toString', '__proto__', undefined]) refused(() => readIntegrationConfig(env(), role), /unknown role/);
  });

  test('useAppDatabase() needs an application connection verified first', async () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    const local = env();
    refused(() => useAppDatabase(local), /needs a connection verified as app first/);
    await verifyQueryable(fakeConnection({ identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator }), 'migrator');
    // Una conexión de migraciones verificada no cuenta.
    refused(() => useAppDatabase(local), /needs a connection verified as app first/);
    assert.equal(local.DB_NAME, undefined, 'nothing was written');
  });

  test('after useAppDatabase(), only the DB_* it set itself are accepted', async () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    await verifyQueryable(fakeConnection(), 'app');
    const local = env();
    useAppDatabase(local);
    assert.equal(local.DB_NAME, 'nexora_test');
    assert.equal(local.DB_USER, 'nexora_test_app');
    assert.equal(readIntegrationConfig(local, 'app').user, 'nexora_test_app');
    refused(() => readIntegrationConfig({ ...local, DB_NAME: 'nexora' }, 'app'), /never use servidor\/\.env/);
    const { DB_PASSWORD, ...missing } = local; // eslint-disable-line no-unused-vars
    refused(() => readIntegrationConfig(missing, 'app'), /never use servidor\/\.env/);
  });

  test('the migration process gets only the migrator account and no DB_* from the parent', () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    const child = migratorProcessEnv(env({ PATH: '/bin' }));
    assert.deepEqual(Object.keys(child).sort(), ['DB_HOST', 'DB_NAME', 'DB_PASSWORD', 'DB_PORT', 'DB_USER', 'NODE_ENV', 'PATH', 'SystemRoot'].sort());
    assert.equal(child.DB_USER, 'nexora_test_migrator');
    assert.equal(child.DB_NAME, 'nexora_test');
  });
});

describe('the runner', () => {
  const FILES = ['auth.test.js', 'migrations.test.js'];

  test('outside run.js nothing opens a connection or prepares one', async () => {
    let created = 0;
    const mysql = { createConnection: async () => { created += 1; }, createPool: () => { created += 1; } };
    await assert.rejects(connectVerified('app', { env: env(), mysql }), /not started by test\/integration\/run\.js/);
    await assert.rejects(openVerifiedPool('app', { env: env(), mysql }), /not started by test\/integration\/run\.js/);
    assert.throws(() => useAppDatabase(env()), /not started by/);
    assert.throws(() => migratorProcessEnv(env()), /not started by/);
    assert.equal(created, 0);
  });

  test('only npm run test:integration marks the process', () => {
    for (const event of [undefined, 'test', 'start', 'migrate', 'test:integration ']) {
      assert.throws(() => markRunner({ event, files: FILES, present: FILES }), /only run through npm run test:integration/);
    }
    assert.throws(() => useAppDatabase(env()), /not started by/, 'a refused runner leaves the process unmarked');
  });

  test('a file in the folder that run.js does not list, or a listed file that is missing, stops everything', () => {
    for (const [files, present] of [
      [FILES, [...FILES, 'extra.test.js']],
      [[...FILES, 'gone.test.js'], FILES],
      [[], []],
      [['auth.test.js'], ['migrations.test.js']],
    ]) {
      assert.throws(() => markRunner({ event: 'test:integration', files, present }), /every file must be listed, and only those/);
      assert.throws(() => useAppDatabase(env()), /not started by/);
    }
  });

  test('the real run.js lists exactly the test files of the folder, and imports exactly those', () => {
    const run = readFileSync(new URL('./integration/run.js', import.meta.url), 'utf8');
    const listed = JSON.parse(run.match(/const FILES = (\[[^\]]*\]);/)[1].replace(/'/g, '"'));
    const imported = [...run.matchAll(/^import '\.\/([\w-]+\.test\.js)';$/gm)].map(([, file]) => file);
    const present = readdirSync(new URL('./integration/', import.meta.url)).filter((name) => name.endsWith('.test.js'));
    assert.deepEqual([...listed].sort(), [...present].sort());
    assert.deepEqual(imported, listed);
    assert.match(run, /markRunner\(\{ files: FILES, present \}\);\s*$/);
  });
});

describe('the identity of the connection', () => {
  test('the expected database and account pass', () => {
    checkIdentity({ database: 'nexora_test', currentUser: 'nexora_test_app@127.0.0.1' }, 'app');
    checkIdentity({ database: 'nexora_test', currentUser: 'nexora_test_migrator@127.0.0.1' }, 'migrator');
  });

  test('another database, no database, or another effective account is refused', () => {
    for (const [database, currentUser] of [
      ['nexora', 'nexora_test_app@127.0.0.1'], [null, 'nexora_test_app@127.0.0.1'], ['nexora_test_guard', 'nexora_test_app@127.0.0.1'],
      ['nexora_test', 'nexora_test_app@%'], ['nexora_test', '@localhost'], ['nexora_test', 'root@localhost'],
      ['nexora_test', 'nexora_test_migrator@127.0.0.1'], ['nexora_test', 'nexora_test_app@localhost'],
    ]) {
      refused(() => checkIdentity({ database, currentUser }, 'app'), /database|another account/);
    }
  });
});

describe('the privileges of the account', () => {
  test('exactly the privileges of setup-admin.sql pass, in the MySQL 8 and the MariaDB formats', () => {
    checkGrants(MYSQL.app, 'app');
    checkGrants(MYSQL.migrator, 'migrator');
    checkGrants(MARIADB.app, 'app');
  });

  test('the MariaDB password hash never reaches an error message', () => {
    const lines = [...MARIADB.app, `GRANT SELECT ON \`nexora\`.* TO ${APP}`];
    assert.throws(() => checkGrants(lines, 'app'), (error) => !error.message.includes(HASH) && /outside the authorized objects: nexora\.\*/.test(error.message));
  });

  const appDatabase = (scope, privileges = 'SELECT, INSERT, DELETE') => [MYSQL.app[0], `GRANT ${privileges} ON ${scope}.* TO ${APP}`, MYSQL.app[2]];
  const appCases = {
    'a global privilege': [...MYSQL.app, `GRANT PROCESS ON *.* TO ${APP}`],
    'a dynamic global privilege': [...MYSQL.app, `GRANT SYSTEM_VARIABLES_ADMIN ON *.* TO ${APP}`],
    'FILE': [`GRANT FILE ON *.* TO ${APP}`, MYSQL.app[1], MYSQL.app[2]],
    'GRANT OPTION': [MYSQL.app[0], `GRANT SELECT, INSERT, DELETE ON ${ESCAPED}.* TO ${APP} WITH GRANT OPTION`, MYSQL.app[2]],
    'ALL PRIVILEGES on the test database': appDatabase(ESCAPED, 'ALL PRIVILEGES'),
    // El comodín: sin escapar, «_» deja entrar también en nexoraXtest, nexora-test…
    'the database name with an unescaped «_» (a wildcard)': appDatabase('`nexora_test`'),
    'the unescaped name without quotes': appDatabase('nexora_test'),
    'a similar name: nexoraXtest': appDatabase('`nexoraXtest`'),
    'a similar name: nexora-test': appDatabase('`nexora-test`'),
    'a «%» pattern': appDatabase('`nexora%test`'),
    'an escaped name with a «%» pattern': appDatabase('`nexora\\_test%`'),
    'a double escape': appDatabase('`nexora\\\\_test`'),
    'the escaped name in other letters': appDatabase('`NEXORA\\_TEST`'),
    'another database': [...MYSQL.app, `GRANT SELECT ON \`nexora\`.* TO ${APP}`],
    'a table of another database': [...MYSQL.app, `GRANT SELECT ON \`mysql\`.\`user\` TO ${APP}`],
    'a role': [...MYSQL.app, `GRANT \`dba\`@\`%\` TO ${APP}`],
    'a proxy grant': [...MYSQL.app, "GRANT PROXY ON ''@'' TO 'nexora_test_app'@'127.0.0.1'"],
    'one privilege more (DROP for the application)': appDatabase(ESCAPED, 'SELECT, INSERT, DELETE, DROP'),
    'UPDATE, which the application never uses': appDatabase(ESCAPED, 'SELECT, INSERT, UPDATE, DELETE'),
    'one privilege less': appDatabase(ESCAPED, 'SELECT, INSERT'),
    'no privileges on the test database': [MYSQL.app[0], MYSQL.app[2]],
    'writing in the guard marker': [MYSQL.app[0], MYSQL.app[1], `GRANT SELECT, INSERT, DELETE ON \`nexora_test_guard\`.\`marker\` TO ${APP}`],
    'privileges on the whole guard schema': [...MYSQL.app, `GRANT SELECT ON \`nexora_test_guard\`.* TO ${APP}`],
    'no access to the guard marker': MYSQL.app.slice(0, 2),
    'column privileges': [...MYSQL.app, `GRANT SELECT (email) ON \`nexora_test\`.\`users\` TO ${APP}`],
    'a grant to another account': [MYSQL.app[0], `GRANT SELECT, INSERT, DELETE ON ${ESCAPED}.* TO \`nexora_test_app\`@\`%\``, MYSQL.app[2]],
    'text that is not a grant': [...MYSQL.app, 'nothing here'],
  };

  test('the unescaped «_» is refused with a message that names the scope', () => {
    assert.throws(() => checkGrants(appDatabase('`nexora_test`'), 'app'), /outside the authorized objects: nexora_test\.\*/);
  });
  for (const [name, lines] of Object.entries(appCases)) {
    test(`refused for the application: ${name}`, () => assert.throws(() => checkGrants(lines, 'app'), IntegrationGuardError));
  }

  const usersTable = (privileges, scope = '`nexora_test`.`users`') => [...MYSQL.migrator.slice(0, 3), `GRANT ${privileges} ON ${scope} TO ${MIG}`, MYSQL.migrator[4]];
  const migratorCases = {
    'DROP on an application table (option B: no account of the tests drops tables)': usersTable('INSERT, CREATE, DROP, REFERENCES, ALTER'),
    'DROP on every application table': MYSQL.migrator.map((line) => line.replace('INSERT, CREATE, REFERENCES, ALTER', 'INSERT, CREATE, DROP, REFERENCES, ALTER')),
    'any privilege on the whole database (DROP DATABASE would be possible)': [...MYSQL.migrator, `GRANT DROP ON ${ESCAPED}.* TO ${MIG}`],
    'CREATE on the whole database (other tables)': [...MYSQL.migrator, `GRANT CREATE ON ${ESCAPED}.* TO ${MIG}`],
    'reading the rows of an application table': usersTable('SELECT, INSERT, CREATE, REFERENCES, ALTER'),
    'deleting the rows of an application table': usersTable('DELETE, INSERT, CREATE, REFERENCES, ALTER'),
    'one privilege less (ALTER, which 002_oauth.sql needs)': usersTable('INSERT, CREATE, REFERENCES'),
    'the table of a similar database: nexoraXtest.users': usersTable('INSERT, CREATE, REFERENCES, ALTER', '`nexoraXtest`.`users`'),
    'the table with an escaped database name': usersTable('INSERT, CREATE, REFERENCES, ALTER', `${ESCAPED}.\`users\``),
    'a table that is not one of the three': [...MYSQL.migrator, `GRANT CREATE ON \`nexora_test\`.\`other\` TO ${MIG}`],
    'missing the privileges of one of the three tables': [MYSQL.migrator[0], MYSQL.migrator[1], MYSQL.migrator[2], MYSQL.migrator[4]],
    'writing in the guard marker': [...MYSQL.migrator.slice(0, 4), `GRANT SELECT, DROP ON \`nexora_test_guard\`.\`marker\` TO ${MIG}`],
    'no access to the guard marker': MYSQL.migrator.slice(0, 4),
  };
  for (const [name, lines] of Object.entries(migratorCases)) {
    test(`refused for the migrator: ${name}`, () => assert.throws(() => checkGrants(lines, 'migrator'), IntegrationGuardError));
  }
});

describe('the guard marker and the destructive operations', () => {
  test('the marker must hold exactly its row, and is read from its own schema', () => {
    checkGuardRows([{ purpose: GUARD_VALUE }]);
    for (const rows of [[], [{ purpose: 'x' }], [{ purpose: GUARD_VALUE }, { purpose: GUARD_VALUE }], null]) {
      assert.throws(() => checkGuardRows(rows), IntegrationGuardError);
    }
    assert.equal(GUARD_SQL, 'SELECT purpose FROM `nexora_test_guard`.`marker`');
  });

  test('the only destructive statements empty the three application tables of nexora_test; none drops anything', () => {
    assert.deepEqual(APP_TABLES, ['oauth_accounts', 'sessions', 'users']);
    assert.deepEqual(RESET_SQL, APP_TABLES.map((table) => `DELETE FROM \`nexora_test\`.\`${table}\``));
    for (const sql of RESET_SQL) assert.doesNotMatch(sql, /guard|marker|DATABASE|WHERE|DROP/i);
    const guard = readFileSync(new URL('./integration/guard.js', import.meta.url), 'utf8');
    assert.doesNotMatch(guard.split('\n').filter((line) => !/^\s*(\/\/|\*)/.test(line)).join('\n'), /DROP |TRUNCATE/, 'guard.js has no DROP or TRUNCATE');
  });

  test('nothing destructive runs on a connection that was not verified, or was verified for the other role', async () => {
    const plain = fakeConnection();
    await assert.rejects(resetAppTables(plain), /not verified as app/);
    await assert.rejects(existingAppTables(plain), /not verified as migrator/);
    const app = await verifyQueryable(fakeConnection(), 'app');
    await assert.rejects(existingAppTables(app), /not verified as migrator/);
    const migrator = await verifyQueryable(fakeConnection({ identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator }), 'migrator');
    await assert.rejects(resetAppTables(migrator), /not verified as app/);
    assert.deepEqual(plain.asked, []);
  });

  test('the fresh-schema check only reads information_schema, for the three tables of nexora_test', async () => {
    const migrator = await verifyQueryable(fakeConnection({ identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator }), 'migrator');
    assert.deepEqual(await existingAppTables(migrator), []);
    const sql = migrator.asked.at(-1);
    assert.match(sql, /^SELECT TABLE_NAME AS t FROM information_schema\.TABLES WHERE TABLE_SCHEMA = 'nexora_test' AND TABLE_NAME IN \('oauth_accounts', 'sessions', 'users'\)/);
  });

  test('a verified application connection, with the run lock held, only empties the three tables', async () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    await holdRunLock({ env: env(), mysql: { createConnection: async () => fakeConnection() } });
    const app = await verifyQueryable(fakeConnection(), 'app');
    await resetAppTables(app);
    assert.deepEqual(app.asked.slice(3), RESET_SQL);
  });

  test('a connection that fails a check is never marked as verified', async () => {
    for (const options of [
      { identity: { db: 'nexora', who: 'nexora_test_app@127.0.0.1' } },
      { grants: [...MYSQL.app, `GRANT SUPER ON *.* TO ${APP}`] },
      { guard: [] },
      { guard: Object.assign(new Error(`Table 'nexora_test_guard.marker' doesn't exist for ${PASSWORD}`), { code: 'ER_NO_SUCH_TABLE' }) },
    ]) {
      const connection = fakeConnection(options);
      await assert.rejects(verifyQueryable(connection, 'app'), (error) => error instanceof IntegrationGuardError && !error.message.includes(PASSWORD));
      await assert.rejects(resetAppTables(connection), /not verified/);
    }
  });

  test('connectVerified checks the configuration before connecting, and closes a connection that fails', async () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    let created = 0;
    const mysql = { createConnection: async () => { created += 1; return fakeConnection({ guard: [] }); } };
    await assert.rejects(connectVerified('app', { env: env({ DB_PASSWORD: 'x' }), mysql }), /never use servidor\/\.env/);
    assert.equal(created, 0, 'no connection is attempted with a wrong configuration');
    let opened;
    const failing = { createConnection: async (config) => { opened = fakeConnection({ guard: [] }); opened.config = config; return opened; } };
    await assert.rejects(connectVerified('app', { env: env(), mysql: failing }), /guard row/);
    assert.equal(opened.ended, true);
    assert.equal(opened.config.multipleStatements, false);
  });
});

describe('how the integration tests are run', () => {
  const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));

  test('npm test never runs them, and test:integration never loads servidor/.env', () => {
    assert.doesNotMatch(pkg.scripts.test, /integration\//);
    assert.match(pkg.scripts['test:integration'], /^node --env-file=\.env\.integration --import \.\/test\/integration\/preflight\.js --test test\/integration\/run\.js$/);
    assert.doesNotMatch(pkg.scripts['test:integration'], /--env-file=\.env(\s|$)/);
  });

  test('run.js imports preflight.js before anything else', () => {
    const run = withoutComments(readFileSync(new URL('./integration/run.js', import.meta.url), 'utf8'));
    assert.equal(run.match(/^import\s[^\n]*$/m)?.[0], "import './preflight.js';");
    const preflight = withoutComments(readFileSync(new URL('./integration/preflight.js', import.meta.url), 'utf8'));
    assert.deepEqual(staticSpecifiers(preflight), ['node:module', './guard.js'], 'preflight.js loads nothing else');
  });

  test('servidor/.env.integration is ignored by git and .env.example is not', () => {
    const ignore = readFileSync(new URL('../../.gitignore', import.meta.url), 'utf8').split(/\r?\n/);
    assert.ok(ignore.includes('.env') && ignore.includes('.env.*') && ignore.includes('!.env.example'));
  });

  test('every integration test file goes through the guards, and none can mark the runner or skip them', () => {
    const folder = new URL('./integration/', import.meta.url);
    const files = readdirSync(folder).filter((name) => name.endsWith('.test.js'));
    assert.ok(files.length >= 5, files.join(', '));
    // Solo el código: los comentarios pueden nombrar mysql2 o DROP para explicar algo.
    const code = (text) => text.split('\n').filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line)).join('\n');
    for (const file of files) {
      const source = code(readFileSync(new URL(file, folder), 'utf8'));
      assert.match(source, /from '\.\/guard\.js'/, file);
      assert.doesNotMatch(source, /createConnection|createPool|['"]mysql2|src\/db\.js|process\.env\.DB_|DROP |TRUNCATE|markRunner|Symbol\.for|globalThis/i, `${file} must go through guard.js`);
    }
    // context.js es el único que importa src/db.js, y solo después de verificar.
    const context = readFileSync(new URL('context.js', folder), 'utf8');
    assert.ok(context.indexOf("await connectVerified('app')") < context.indexOf("import('../../src/db.js')"));
    assert.ok(context.indexOf('useAppDatabase()') < context.indexOf("import('../../src/db.js')"));
    assert.match(context, /await verifyQueryable\(pool, 'app'\);/);
  });

  test('no integration file reaches src/ or mysql2 through static imports, directly or through other modules', () => {
    // Una importación estática se carga antes que cualquier código: si llegara a src/, cargaría la
    // configuración y el pool antes de las guardas. Se recorre el grafo de importaciones estáticas desde
    // cada archivo de la carpeta; las dinámicas (import()) no cuentan aquí, ver la prueba siguiente.
    const folder = new URL('./integration/', import.meta.url);
    const roots = readdirSync(folder).filter((name) => name.endsWith('.js')).map((name) => new URL(name, folder));
    const violations = staticImportViolations(roots);
    assert.deepEqual(violations, []);
  });

  test('every file of the folder, helpers included: src/ only after a guard, no require, no top-level await', () => {
    const folder = new URL('./integration/', import.meta.url);
    const files = readdirSync(folder).filter((name) => name.endsWith('.js'));
    assert.ok(files.includes('preflight.js') && files.includes('context.js') && files.includes('run.js'), files.join(', '));
    for (const file of files) {
      assert.deepEqual(sourceProblems(file, readFileSync(new URL(file, folder), 'utf8')), [], file);
    }
  });

  test('the text checks catch the forms the audit found, and accept the legitimate ones', () => {
    for (const [source, problem, file = 'x.test.js'] of [
      ["export const pool = await import('../../src/db.js');", /top-level await/],
      ["export const pool = await import('../../src/db.js');", /before any guard/],
      ["for await (const x of y) {}", /top-level await/],
      ["const name = 'db.js';\ntest('x', async () => { await connectVerified('app'); await import('../../src/' + name); });", /not a plain string/],
      ["test('x', async () => { await appContext(); await import(`../../src/${name}.js`); });", /not a plain string/],
      ["const require = createRequire(import.meta.url);", /require or createRequire/],
      ["test('x', () => require('../../src/db.js'));", /require or createRequire/],
      ["const host = process.env['DB_HOST'];", /process\.env\[/],
      ["const host = process.env[`${prefix}_HOST`];", /process\.env\[/],
      ["const name = 'DB_' + 'HOST';", /a DB_\* variable/],
      ["export async function helper() { return import('../../src/app.js'); }", /before any guard/, 'helper.js'],
      ["test('x', async () => { await import('mysql2/promise'); });", /outside guard\.js/],
    ]) {
      const problems = sourceProblems(file, source);
      assert.ok(problems.some((text) => problem.test(text)), `${source}\n  -> ${problems.join('; ') || 'nothing found'}`);
    }
    for (const [file, source] of [
      ['x.test.js', "before(async () => {\n  ({ pool } = await appContext());\n  ({ createApp } = await import('../../src/app.js'));\n});"],
      ['x.test.js', "test('x', async () => {\n  await connectVerified('app');\n  const { createShutdown } = await import('../../src/lifecycle.js');\n});"],
      ['x.test.js', "// await import('../../src/db.js') en un comentario\n/* createRequire, process.env['DB_HOST'] */\nconst a = 1;"],
      ['x.test.js', "const env = { TEST_DB_HOST: '127.0.0.1' };"],
      ['guard.js', "export async function connectVerified() {\n  const driver = mysql ?? await import('mysql2/promise');\n}"],
    ]) {
      assert.deepEqual(sourceProblems(file, source), [], source);
    }
    // Las importaciones estáticas, también sin espacios y como reexportación.
    assert.deepEqual(staticSpecifiers("import{pool}from'../../src/db.js';\nimport'../../src/a.js';\nexport * from '../../src/b.js';"),
      ['../../src/db.js', '../../src/b.js', '../../src/a.js']);
  });

  test('setup-admin.sql grants exactly what the guards expect, and nothing on the whole database to the migrator', () => {
    const sql = readFileSync(new URL('./integration/setup-admin.sql', import.meta.url), 'utf8');
    const grants = [...sql.matchAll(/^GRANT (.+?) ON (\S+)\s+TO '([\w]+)'@'127\.0\.0\.1';$/gm)]
      .map(([, privileges, scope, user]) => `${user} ${scope} ${privileges.split(',').map((p) => p.trim()).sort().join(',')}`).sort();
    assert.deepEqual(grants, [
      'nexora_test_app `nexora\\_test`.* DELETE,INSERT,SELECT',
      'nexora_test_app nexora_test_guard.marker SELECT',
      'nexora_test_migrator nexora_test.oauth_accounts ALTER,CREATE,INSERT,REFERENCES',
      'nexora_test_migrator nexora_test.sessions ALTER,CREATE,INSERT,REFERENCES',
      'nexora_test_migrator nexora_test.users ALTER,CREATE,INSERT,REFERENCES',
      'nexora_test_migrator nexora_test_guard.marker SELECT',
    ]);
    // Las sentencias, sin los comentarios (que explican, por ejemplo, que no hay GRANT OPTION).
    const statements = sql.split('\n').filter((line) => !line.trimStart().startsWith('--')).join('\n');
    assert.doesNotMatch(statements, /^GRANT[^\n]*\*\.\*/m);
    assert.doesNotMatch(statements, /GRANT OPTION|SUPER|FILE|PROCESS|ALL PRIVILEGES/);
    assert.doesNotMatch(statements, /^GRANT[^\n]*\bDROP\b/m, 'no account of the tests can drop anything');
    assert.doesNotMatch(statements, /^GRANT[^\n]* ON `?nexora\\?_test`?\.\* TO 'nexora_test_migrator'/m);
    // Ningún «_» sin escapar en un permiso sobre una base entera.
    for (const [, scope] of statements.matchAll(/^GRANT [^\n]* ON (\S+)\.\* TO/gm)) assert.doesNotMatch(scope.replace(/\\_/g, ''), /_/, scope);
    // Sin credenciales: solo las dos plantillas, que las guardas rechazan como contraseña.
    assert.deepEqual([...statements.matchAll(/IDENTIFIED BY '([^']*)'/g)].map(([, password]) => password),
      ['<CONTRASEÑA_MIGRACIONES_SOLO_PRUEBAS>', '<CONTRASEÑA_APLICACION_SOLO_PRUEBAS>']);
  });

  test('prepare-fresh-schema-admin.sql only drops the three application tables, after checking the marker', () => {
    const sql = readFileSync(new URL('./integration/prepare-fresh-schema-admin.sql', import.meta.url), 'utf8');
    const statements = sql.split('\n').filter((line) => line.trim() && !line.trimStart().startsWith('--')).join('\n');
    assert.deepEqual([...statements.matchAll(/^DROP [^;]+;/gm)].map(([statement]) => statement), [
      'DROP TABLE IF EXISTS nexora_test.oauth_accounts;',
      'DROP TABLE IF EXISTS nexora_test.sessions;',
      'DROP TABLE IF EXISTS nexora_test.users;',
    ]);
    assert.ok(statements.indexOf('SELECT purpose FROM nexora_test_guard.marker;') < statements.indexOf('DROP '));
    assert.doesNotMatch(statements, /GRANT|REVOKE|CREATE USER|DROP USER|DROP DATABASE|IDENTIFIED/i);
    // Nada en el repositorio lo ejecuta: ni las pruebas ni los scripts lo nombran fuera de comentarios.
    for (const file of readdirSync(new URL('./integration/', import.meta.url)).filter((name) => name.endsWith('.js'))) {
      const code = readFileSync(new URL(`./integration/${file}`, import.meta.url), 'utf8').split('\n').filter((line) => !/^\s*(\/\/|\*)/.test(line)).join('\n');
      assert.doesNotMatch(code, /\.sql['"]/, `${file} must not load an SQL file`);
    }
  });
});

describe('the module gate of preflight.js (checkModuleLoad)', () => {
  const SRC = new URL('../src/', import.meta.url);
  const at = (relative) => new URL(relative, SRC).href;
  const FIXTURE = new URL('./fixtures/preflight-probe.js', import.meta.url).href;
  const GUARD = new URL('./integration/guard.js', import.meta.url).href;
  const MYSQL2 = new URL('../node_modules/mysql2/promise.js', import.meta.url).href;
  const MYSQL2_INSIDE = new URL('../node_modules/mysql2/lib/base/pool.js', import.meta.url).href;
  const gated = (url, parent) => assert.throws(() => checkModuleLoad(url, parent), (error) => error instanceof IntegrationGuardError && /cannot be loaded here/.test(error.message));

  async function ready() {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    await verifyQueryable(fakeConnection(), 'app');
    useAppDatabase(env());
  }

  test('servidor/src/ stays closed until useAppDatabase(), also with the runner marked and a migrator verified', async () => {
    gated(at('db.js'), FIXTURE);
    gated(at('playground/config.js'), FIXTURE);
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    await verifyQueryable(fakeConnection({ identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator }), 'migrator');
    gated(at('db.js'), FIXTURE);
    // Una conexión «app» verificada no basta: lo abre useAppDatabase().
    await verifyQueryable(fakeConnection(), 'app');
    gated(at('db.js'), FIXTURE);
    useAppDatabase(env());
    checkModuleLoad(at('db.js'), FIXTURE);
    checkModuleLoad(at('app.js'), undefined);
  });

  test('other spellings of the same files are closed too: upper case and percent-encoding', () => {
    gated(at('db.js').replace('/src/', '/%73rc/'), FIXTURE);
    gated(at('db.js').replace('/src/', '/SRC/'), FIXTURE);
    gated(at('db.js').replace('/servidor/', '/SERVIDOR/'), FIXTURE);
  });

  test('mysql2: only from guard.js with the runner marked, from servidor/src/ once open, or from inside mysql2', async () => {
    gated(MYSQL2, FIXTURE);
    gated(MYSQL2, GUARD);
    checkModuleLoad(MYSQL2_INSIDE, MYSQL2);
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    checkModuleLoad(MYSQL2, GUARD);
    gated(MYSQL2, FIXTURE);
    gated(MYSQL2, at('db.js'));
    await ready();
    checkModuleLoad(MYSQL2, at('db.js'));
    // Un archivo de pruebas nunca carga mysql2 por su cuenta.
    gated(MYSQL2, FIXTURE);
  });

  test('everything else loads freely', () => {
    for (const url of ['node:fs', 'node:test', new URL('../node_modules/express/index.js', import.meta.url).href, GUARD, FIXTURE, 'data:text/javascript,export default 1']) {
      checkModuleLoad(url, FIXTURE);
    }
  });

  test('only the modules of APP_MODULES: index.js, migrate.js or any other module of src/ never, not even once open', async () => {
    const outside = (url) => assert.throws(() => checkModuleLoad(url, FIXTURE), (error) => error instanceof IntegrationGuardError && /is not one of the modules the integration tests may load/.test(error.message));
    for (const name of ['index.js', 'migrate.js', 'unknown.js', 'playground/other.js']) outside(at(name));
    outside(at('index.js').replace('/src/', '/SRC/'));
    outside(at('migrate.js').replace('/src/', '/%73rc/'));
    await ready();
    for (const name of APP_MODULES) checkModuleLoad(at(name), FIXTURE);
    for (const name of ['index.js', 'migrate.js', 'unknown.js']) outside(at(name));
    outside(at('INDEX.JS'));
  });

  test('APP_MODULES is exactly what the integration files import from src/, and everything those import', () => {
    // Las raíces: los import() de src/ de los archivos de la carpeta (migrate-child.js aparte: su
    // src/migrate.js se carga en otro proceso, sin gancho). Después, sus importaciones estáticas.
    const folder = new URL('./integration/', import.meta.url);
    const roots = new Set();
    for (const file of readdirSync(folder).filter((name) => name.endsWith('.js') && name !== 'migrate-child.js')) {
      for (const match of withoutComments(readFileSync(new URL(file, folder), 'utf8')).matchAll(/import\(\s*'(\.\.\/\.\.\/src\/[^']+)'\s*\)/g)) {
        roots.add(new URL(match[1], folder).href);
      }
    }
    const reached = new Set();
    const visit = (href) => {
      if (reached.has(href)) return;
      reached.add(href);
      for (const specifier of staticSpecifiers(readFileSync(new URL(href), 'utf8'))) {
        if (specifier.startsWith('.')) visit(new URL(specifier, href).href);
      }
    };
    for (const root of roots) visit(root);
    const SRC_HREF = new URL('../src/', import.meta.url).href;
    const names = [...reached].filter((href) => href.startsWith(SRC_HREF)).map((href) => href.slice(SRC_HREF.length)).sort();
    assert.deepEqual([...APP_MODULES].sort(), names);
    assert.ok(!APP_MODULES.includes('index.js') && !APP_MODULES.includes('migrate.js'));
  });

  test('checkPreflight: npm run test:integration, no DB_* at all, and the authorized configuration of both roles', () => {
    const ok = env({ npm_lifecycle_event: 'test:integration' });
    checkPreflight(ok);
    refused(() => checkPreflight(env()), /only run through npm run test:integration/);
    for (const name of ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']) refused(() => checkPreflight({ ...ok, [name]: 'x' }), /DB_/);
    refused(() => checkPreflight({ ...ok, NODE_ENV: 'production' }), /NODE_ENV/);
    refused(() => checkPreflight({ ...ok, TEST_DB_MIGRATOR_PASSWORD: '<CONTRASEÑA_MIGRACIONES_SOLO_PRUEBAS>' }), /TEST_DB_MIGRATOR_PASSWORD/);
    refused(() => checkPreflight({ ...ok, TEST_DB_HOST: 'db.example.com' }), /TEST_DB_HOST/);
  });

  test('checkPreflight: the playground stays disabled; PLAYGROUND_ENABLED only unset or "false", no other PLAYGROUND_*', () => {
    const ok = env({ npm_lifecycle_event: 'test:integration' });
    checkPreflight(ok);
    checkPreflight({ ...ok, PLAYGROUND_ENABLED: 'false' });
    for (const value of ['true', 'TRUE', 'True', '1', 'yes', ' true', '', 'false ']) {
      refused(() => checkPreflight({ ...ok, PLAYGROUND_ENABLED: value }), /PLAYGROUND_ENABLED must be unset or "false"/);
    }
    for (const name of ['PLAYGROUND_WORKER_COMMAND', 'PLAYGROUND_TIMEOUT_MS', 'PLAYGROUND_ALLOWED_ORIGINS', 'PLAYGROUND_SOMETHING_NEW']) {
      refused(() => checkPreflight({ ...ok, [name]: 'x' }), new RegExp(`${name} is set: the integration tests never configure the playground`));
      refused(() => checkPreflight({ ...ok, PLAYGROUND_ENABLED: 'false', [name]: 'x' }), new RegExp(name));
    }
  });

  test('checkHookSupport: without module.registerHooks (Node 20.6–22.14) the integration tests refuse to run', () => {
    for (const value of [undefined, null, {}, 'registerHooks']) {
      refused(() => checkHookSupport(value, 'v20.6.0'), /need module\.registerHooks \(Node 22\.22\.3 or later in the 22 line, or 24\.14\.0 or later in the 24 line\), and this is Node v20\.6\.0/);
    }
  });

  test('checkHookSupport: only the lines of HOOK_MINIMUMS, each from its measured minimum; any other line is refused', () => {
    // Medido con las distribuciones oficiales para Windows (caso «legit» de preflight-probe.js): por
    // debajo de estos mínimos, el gancho bloqueó mysql2 también en el orden legítimo. La causa no está
    // confirmada.
    assert.deepEqual(HOOK_MINIMUMS, { 22: [22, 22, 3], 24: [24, 14, 0] });
    for (const version of ['v22.22.3', 'v22.23.0', 'v22.23.2', 'v22.23.3', 'v24.14.0', 'v24.18.1', 'v24.21.0', '24.21.0']) {
      checkHookSupport(() => {}, version);
    }
    const need = 'need Node 22\\.22\\.3 or later in the 22 line, or 24\\.14\\.0 or later in the 24 line, and this is Node \\S*: ';
    const below = new RegExp(`${need}it is below the minimum measured for its line\\. .*the cause is not confirmed`);
    for (const version of ['v22.15.0', 'v22.18.0', 'v22.22.2', 'v24.0.0', 'v24.13.1']) {
      refused(() => checkHookSupport(() => {}, version), below);
    }
    // El límite de cada rama, sacado de la tabla: su mínimo se admite y la versión anterior no.
    for (const [major, minor, patch] of Object.values(HOOK_MINIMUMS)) {
      checkHookSupport(() => {}, `v${major}.${minor}.${patch}`);
      const previous = patch > 0 ? `v${major}.${minor}.${patch - 1}` : `v${major}.${minor - 1}.999`;
      refused(() => checkHookSupport(() => {}, previous), below);
    }
    // 25.9.0 y 26.12.0 no bloquearon mysql2 en la medición, pero sus ramas no tienen mínimo medido.
    for (const version of ['v21.7.0', 'v23.11.0', 'v25.0.0', 'v25.9.0', 'v26.0.0', 'v26.12.0', 'v27.0.0', 'v30.1.2']) {
      refused(() => checkHookSupport(() => {}, version), new RegExp(`${need}no minimum has been measured for its line\\.`));
    }
    for (const version of ['nonsense', '', 'v24', 'v24.14', 'v24.14.0-pre', 'v24.14.0.1', 'v24.x.0', 'v024.14.0', 'v24.014.0']) {
      refused(() => checkHookSupport(() => {}, version), new RegExp(`${need}its version could not be read\\.`));
    }
  });

  test('checkHookSupport: every Node allowed by engines in servidor/package.json can run the integration tests', () => {
    const { engines } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
    const clauses = engines.node.split('||').map((part) => part.trim());
    assert.ok(clauses.length > 0, 'engines.node is empty');
    for (const clause of clauses) {
      // Solo rangos ^X.Y.Z con X >= 1: de X.Y.Z hasta antes de (X+1).0.0. Otra forma obliga a revisar esta prueba.
      const match = clause.match(/^\^([1-9]\d*)\.(\d+)\.(\d+)$/);
      assert.ok(match, `engines clause not understood by this test: ${clause}`);
      const [major, minor, patch] = match.slice(1).map(Number);
      // Todo el rango, no solo unos ejemplos: su rama tiene un mínimo medido y el rango no empieza por debajo.
      // Como hookSupportProblem admite cada versión de la rama desde su mínimo, eso cubre el rango entero.
      assert.ok(Object.hasOwn(HOOK_MINIMUMS, major), `engines allows the ${major} line, which has no measured minimum`);
      const [, minimumMinor, minimumPatch] = HOOK_MINIMUMS[major];
      assert.ok(minor > minimumMinor || (minor === minimumMinor && patch >= minimumPatch), `${clause} starts below the measured minimum`);
      // Y la función lo confirma en el principio del rango y en una versión alta de la rama.
      for (const version of [`v${major}.${minor}.${patch}`, `v${major}.999.999`]) {
        assert.equal(hookSupportProblem(() => {}, version), null, version);
      }
    }
  });
});

// Lo que comparten las pruebas que lanzan procesos: la carpeta servidor/, preflight.js y un entorno de
// pruebas completo, con contraseñas falsas, la base en el puerto 1 (donde no hay nada) y el servidor, si
// algo lo arrancara por error, en un puerto libre de 127.0.0.1, nunca el 3000.
const SERVIDOR = fileURLToPath(new URL('..', import.meta.url));
const PREFLIGHT = new URL('./integration/preflight.js', import.meta.url).href;
const PROBE_ENV = Object.freeze({
  PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, NODE_ENV: 'test', npm_lifecycle_event: 'test:integration',
  PORT: '0', LISTEN_HOST: '127.0.0.1',
  TEST_DB_HOST: '127.0.0.1', TEST_DB_PORT: '1', TEST_DB_NAME: 'nexora_test',
  TEST_DB_MIGRATOR_USER: 'nexora_test_migrator', TEST_DB_MIGRATOR_PASSWORD: PASSWORD,
  TEST_DB_APP_USER: 'nexora_test_app', TEST_DB_APP_PASSWORD: PASSWORD,
});

/** Lanza node con estos argumentos en servidor/ y este entorno; comprueba que la contraseña no sale. */
function launch(args, environment) {
  const result = spawnSync(process.execPath, args, { cwd: SERVIDOR, env: environment, encoding: 'utf8', timeout: 20_000 });
  assert.ok(!`${result.stdout}${result.stderr}`.includes(PASSWORD), 'the password never reaches the output');
  return result;
}

describe('preflight.js on a Node without module.registerHooks (simulated in this Node, not a Node 20 run)', () => {
  test('it stops before loading anything, with a message that says why', () => {
    const without = new URL('./fixtures/without-register-hooks.js', import.meta.url).href;
    const result = launch(['--import', without, '--import', PREFLIGHT, 'test/fixtures/preflight-probe.js', 'literal'], PROBE_ENV);
    assert.notEqual(result.status, 0);
    assert.doesNotMatch(result.stdout, /PROBE STARTED/);
    assert.match(result.stderr, /need module\.registerHooks \(Node 22\.22\.3 or later in the 22 line, or 24\.14\.0 or later in the 24 line\)/);
  });
});

// La omisión va en cada prueba, no en el describe: así el resumen cuenta las omitidas («skipped»), con
// su motivo, en vez de no contarlas.
describe('preflight.js in a real process (it never connects: port 1, fake connections)', () => {
  /** Lanza un archivo de test/fixtures con --import preflight.js; devuelve lo que escribió. */
  function probe(fixture, args = [], changes = {}) {
    const environment = { ...PROBE_ENV, ...changes };
    for (const [name, value] of Object.entries(changes)) if (value === undefined) delete environment[name];
    return launch(['--import', PREFLIGHT, `test/fixtures/${fixture}`, ...args], environment);
  }

  for (const [name, changes, pattern] of [
    ['a DB_* variable', { DB_HOST: '127.0.0.1' }, /DB_HOST are set/],
    ['DB_PASSWORD alone', { DB_PASSWORD: 'x' }, /DB_PASSWORD are set/],
    ['not npm run test:integration', { npm_lifecycle_event: undefined }, /only run through npm run test:integration/],
    ['NODE_ENV production', { NODE_ENV: 'production' }, /NODE_ENV must be "test"/],
    ['the placeholder password', { TEST_DB_APP_PASSWORD: '<CONTRASEÑA_APLICACION_SOLO_PRUEBAS>' }, /TEST_DB_APP_PASSWORD/],
    ['another host', { TEST_DB_HOST: 'localhost' }, /TEST_DB_HOST/],
    ['PLAYGROUND_ENABLED=true', { PLAYGROUND_ENABLED: 'true' }, /PLAYGROUND_ENABLED must be unset or "false"/],
    ['a playground worker command', { PLAYGROUND_WORKER_COMMAND: 'docker run x' }, /PLAYGROUND_WORKER_COMMAND is set/],
  ]) {
    test(`an unsafe environment stops before any test file is loaded: ${name}`, HOOKS, () => {
      const result = probe('preflight-probe.js', ['literal'], changes);
      assert.notEqual(result.status, 0);
      assert.doesNotMatch(result.stdout, /PROBE STARTED/);
      assert.match(result.stderr, pattern);
    });
  }

  test('a static import of servidor/src/ stops the process before the file runs', HOOKS, () => {
    const result = probe('preflight-static-src.js');
    assert.notEqual(result.status, 0);
    assert.doesNotMatch(result.stdout, /PROBE STARTED/);
    assert.match(result.stderr, /servidor\/src\/ cannot be loaded here/);
  });

  // En este orden: los últimos marcan el proceso y preparan la base, como haría run.js. «uppercase»
  // solo tiene sentido en Windows, donde SRC y src son la misma carpeta.
  const BLOCKED = [
    ['literal', 'servidor/src/'], ['variable', 'servidor/src/'], ['template', 'servidor/src/'], ['top-level-export', 'servidor/src/'],
    ['require-src', 'servidor/src/'], ['require-mysql2', 'mysql2'], ['mysql2', 'mysql2'], ['encoded', 'servidor/src/'],
    ...(process.platform === 'win32' ? [['uppercase', 'servidor/src/']] : []),
    ['runner-only', 'servidor/src/'], ['mysql2-after-ready', 'mysql2'],
  ];
  test(`every way of loading servidor/src/ or mysql2 too early is stopped (${BLOCKED.map(([kind]) => kind).join(', ')})`, HOOKS, () => {
    const result = probe('preflight-probe.js', BLOCKED.map(([kind]) => kind));
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split(/\r?\n/), ['PROBE STARTED', ...BLOCKED.map(([kind, what]) => `${kind}: BLOCKED ${what}`)]);
  });

  test('useAppDatabase() without a verified application connection is refused, and src/ stays closed', HOOKS, () => {
    const result = probe('preflight-probe.js', ['unverified', 'literal']);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split(/\r?\n/), ['PROBE STARTED', 'unverified: REFUSED', 'literal: BLOCKED servidor/src/']);
  });

  test('the legitimate order still works: verified connection, useAppDatabase(), then src/db.js and mysql2 through it', HOOKS, () => {
    const result = probe('preflight-probe.js', ['legit']);
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split(/\r?\n/), ['PROBE STARTED', 'legit: LOADED']);
  });

  test('PLAYGROUND_ENABLED=false is accepted', HOOKS, () => {
    const result = probe('preflight-probe.js', ['legit'], { PLAYGROUND_ENABLED: 'false' });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split(/\r?\n/), ['PROBE STARTED', 'legit: LOADED']);
  });

  test('src/index.js and src/migrate.js are never evaluated, with import() or require, before or after src/ opens', HOOKS, () => {
    // Antes de marcar el proceso y de verificar nada; después, ya con src/ abierto.
    const EACH = ['index', 'require-index', 'migrate', 'require-migrate'];
    const result = probe('preflight-probe.js', [...EACH, 'legit', ...EACH, 'not-evaluated']);
    assert.equal(result.status, 0, result.stderr);
    const blocked = EACH.map((kind) => `${kind}: BLOCKED-MODULE ${kind.replace('require-', '')}.js`);
    assert.deepEqual(result.stdout.trim().split(/\r?\n/), [
      'PROBE STARTED',
      ...blocked,
      'legit: LOADED',
      ...blocked,
      // index.js registra su manejador de SIGTERM al evaluarse y escucha: ni lo uno ni lo otro.
      'evidence: SIGTERM listeners 0', 'not-evaluated: LOADED',
    ]);
    assert.doesNotMatch(`${result.stdout}${result.stderr}`, /NEXORA en|Aplicada/);
  });
});

describe('the migration process (migrate-child.js): its own environment and account, checked before and after', () => {
  const childEnv = () => {
    markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
    return migratorProcessEnv(env({ PATH: '/bin', SystemRoot: 'C:\\Windows' }));
  };
  const MIGRATOR = { identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator };

  test('the environment of migratorProcessEnv is accepted, and gives the migrator account', () => {
    assert.deepEqual(readMigrationChildConfig(childEnv()), { host: '127.0.0.1', port: 3306, user: 'nexora_test_migrator', password: PASSWORD, database: 'nexora_test' });
  });

  test('any other variable, another account or another target is refused', () => {
    const base = childEnv();
    for (const extra of ['NODE_OPTIONS', 'TEST_DB_APP_PASSWORD', 'TEST_DB_MIGRATOR_PASSWORD', 'DB_SOCKET', 'npm_lifecycle_event', 'PLAYGROUND_ENABLED']) {
      refused(() => readMigrationChildConfig({ ...base, [extra]: 'x' }), new RegExp(`unexpected variables: ${extra}`));
    }
    refused(() => readMigrationChildConfig({ ...base, DB_USER: 'nexora_test_app' }), /TEST_DB_MIGRATOR_USER must be nexora_test_migrator/);
    refused(() => readMigrationChildConfig({ ...base, DB_USER: 'root' }), /TEST_DB_MIGRATOR_USER/);
    refused(() => readMigrationChildConfig({ ...base, DB_HOST: 'localhost' }), /TEST_DB_HOST/);
    refused(() => readMigrationChildConfig({ ...base, DB_NAME: 'nexora' }), /TEST_DB_NAME/);
    refused(() => readMigrationChildConfig({ ...base, DB_PASSWORD: '<CONTRASEÑA_MIGRACIONES_SOLO_PRUEBAS>' }), /PASSWORD/);
    refused(() => readMigrationChildConfig({ ...base, NODE_ENV: 'production' }), /NODE_ENV/);
    const { DB_PASSWORD, ...missing } = base; // eslint-disable-line no-unused-vars
    refused(() => readMigrationChildConfig(missing), /PASSWORD/);
  });

  test('the system variables that libuv adds to every child on Windows are accepted there, and only there', () => {
    const windows = { ...childEnv(), HOMEDRIVE: 'C:', HOMEPATH: '\\Users\\x', LOGONSERVER: '\\\\X', SYSTEMDRIVE: 'C:', TEMP: 'C:\\t', USERDOMAIN: 'X', USERNAME: 'x', USERPROFILE: 'C:\\Users\\x', WINDIR: 'C:\\Windows' };
    assert.equal(readMigrationChildConfig(windows, 'win32').user, 'nexora_test_migrator');
    refused(() => readMigrationChildConfig(windows, 'linux'), /unexpected variables: HOMEDRIVE, HOMEPATH, LOGONSERVER/);
    refused(() => readMigrationChildConfig({ ...windows, NODE_OPTIONS: '--import x' }, 'win32'), /unexpected variables: NODE_OPTIONS/);
  });

  test('the variable that macOS adds to every child is accepted there, and only there', () => {
    const macos = { ...childEnv(), __CF_USER_TEXT_ENCODING: 'UTF-8' };
    assert.equal(readMigrationChildConfig(macos, 'darwin').user, 'nexora_test_migrator');
    refused(() => readMigrationChildConfig(macos, 'linux'), /unexpected variables: __CF_USER_TEXT_ENCODING/);
    refused(() => readMigrationChildConfig(macos, 'win32'), /unexpected variables: __CF_USER_TEXT_ENCODING/);
    refused(() => readMigrationChildConfig({ ...macos, NODE_OPTIONS: '--import x' }, 'darwin'), /unexpected variables: NODE_OPTIONS/);
  });

  test('the variables the operating system adds to a child are the ones of that system, and no others', () => {
    assert.deepEqual(operatingSystemVariables('win32'), [
      'HOMEDRIVE', 'HOMEPATH', 'LOGONSERVER', 'SYSTEMDRIVE', 'TEMP', 'USERDOMAIN', 'USERNAME', 'USERPROFILE', 'WINDIR',
    ]);
    assert.deepEqual(operatingSystemVariables('darwin'), ['__CF_USER_TEXT_ENCODING']);
    assert.deepEqual(operatingSystemVariables('linux'), []);
  });

  test('the account is verified before migrating and again after, on its own connection, which is always closed', async () => {
    const steps = [];
    const connection = fakeConnection(MIGRATOR);
    await runVerifiedMigration({
      env: childEnv(), mysql: { createConnection: async (config) => { steps.push(`connect ${config.user} multipleStatements=${config.multipleStatements}`); return connection; } },
      migrate: async () => steps.push('migrate'), log: (line) => steps.push(line),
    });
    assert.deepEqual(steps, [
      'connect nexora_test_migrator multipleStatements=false',
      'migrate-child: migrator verified before migrating', 'migrate', 'migrate-child: migrator verified after migrating',
    ]);
    assert.equal(connection.ended, true);
    assert.deepEqual(connection.asked.filter((sql) => !/^(SELECT DATABASE\(\)|SHOW GRANTS|SELECT purpose)/.test(sql)), [], 'only the read-only checks');
  });

  test('a wrong account or wrong privileges stop it before migrating', async () => {
    for (const options of [{}, { ...MIGRATOR, grants: [...MYSQL.migrator, `GRANT DROP ON \`nexora_test\`.\`users\` TO ${MIG}`] }, { ...MIGRATOR, guard: [] }]) {
      let migrated = false;
      const connection = fakeConnection(options);
      await assert.rejects(runVerifiedMigration({ env: childEnv(), mysql: { createConnection: async () => connection }, migrate: async () => { migrated = true; }, log: () => {} }), IntegrationGuardError);
      assert.equal(migrated, false);
      assert.equal(connection.ended, true);
    }
  });

  test('privileges that change during the migration are caught after it; a failed migration skips the second check', async () => {
    const connection = fakeConnection(MIGRATOR);
    const logs = [];
    await assert.rejects(runVerifiedMigration({
      env: childEnv(), mysql: { createConnection: async () => connection },
      migrate: async () => { connection.grants = [...MYSQL.migrator, `GRANT SELECT ON \`nexora_test\`.\`users\` TO ${MIG}`]; },
      log: (line) => logs.push(line),
    }), /on nexora_test\.users the account has/);
    assert.deepEqual(logs, ['migrate-child: migrator verified before migrating']);
    assert.equal(connection.ended, true);
    const failing = fakeConnection(MIGRATOR);
    const original = Object.assign(new Error('migration failed'), { code: 'ER_PARSE_ERROR' });
    const failingLogs = [];
    await assert.rejects(runVerifiedMigration({ env: childEnv(), mysql: { createConnection: async () => failing }, migrate: async () => { throw original; }, log: (line) => failingLogs.push(line) }), (error) => error === original);
    assert.deepEqual(failingLogs, ['migrate-child: migrator verified before migrating']);
    assert.equal(failing.ended, true);
  });

  test('a real child process gets exactly that environment: the operating system adds nothing that would be refused', () => {
    const guard = new URL('./integration/guard.js', import.meta.url).href;
    const result = launch(['--input-type=module', '-e', `import { readMigrationChildConfig } from '${guard}'; readMigrationChildConfig(process.env); console.log('ACCEPTED');`], { ...childEnv(), PATH: process.env.PATH, SystemRoot: process.env.SystemRoot });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout.trim(), 'ACCEPTED');
  });

  test('migrate-child.js refuses an unexpected environment before connecting or loading src/migrate.js', () => {
    const base = { ...childEnv(), PATH: process.env.PATH, SystemRoot: process.env.SystemRoot, DB_PORT: '1' };
    for (const [changes, pattern] of [
      [{ TEST_DB_APP_PASSWORD: 'x' }, /unexpected variables: TEST_DB_APP_PASSWORD/],
      [{ DB_USER: 'nexora_test_app' }, /TEST_DB_MIGRATOR_USER must be nexora_test_migrator/],
      [{ DB_HOST: 'localhost' }, /TEST_DB_HOST/],
    ]) {
      const result = launch(['test/integration/migrate-child.js'], { ...base, ...changes });
      assert.equal(result.status, 1, result.stderr);
      assert.match(result.stderr, pattern);
      assert.doesNotMatch(result.stdout, /Aplicada|verified/);
    }
  });

  test('migrations.test.js runs migrations only through migrate-child.js, which loads only src/migrate.js, after the checks', () => {
    const tests = withoutComments(readFileSync(new URL('./integration/migrations.test.js', import.meta.url), 'utf8'));
    assert.match(tests, /spawn\(process\.execPath, \['test\/integration\/migrate-child\.js'\], \{ cwd: servidor, env: migratorProcessEnv\(\)/);
    assert.doesNotMatch(tests, /src\/migrate\.js/);
    const child = withoutComments(readFileSync(new URL('./integration/migrate-child.js', import.meta.url), 'utf8'));
    assert.deepEqual([...child.matchAll(/import\(\s*'([^']+)'\s*\)/g)].map((match) => match[1]), ['../../src/migrate.js']);
    assert.ok(child.indexOf('runVerifiedMigration(') < child.indexOf("import('../../src/migrate.js')"));
  });
});

describe('undoAfter: a test undoes its own change, and a failed undo never hides the original error', () => {
  test('the body passes: the undo runs once and the value comes back', async () => {
    const calls = [];
    assert.equal(await undoAfter(async () => { calls.push('body'); return 7; }, async () => { calls.push('undo'); }, () => calls.push('report')), 7);
    assert.deepEqual(calls, ['body', 'undo']);
  });

  test('the body fails: the undo still runs, and the error is the body one', async () => {
    const calls = [];
    const original = new Error('assertion');
    await assert.rejects(undoAfter(async () => { throw original; }, async () => { calls.push('undo'); }, () => calls.push('report')), (error) => error === original);
    assert.deepEqual(calls, ['undo']);
  });

  test('the body and the undo fail: the body error, and the undo failure is reported apart', async () => {
    const original = new Error('migrate failed');
    const undoError = Object.assign(new Error('undo failed'), { code: 'ER_LOCK_WAIT_TIMEOUT' });
    const reported = [];
    await assert.rejects(undoAfter(async () => { throw original; }, async () => { throw undoError; }, (error) => reported.push(error)), (error) => error === original);
    assert.deepEqual(reported, [undoError]);
  });

  test('the body passes and the undo fails: that failure is the error', async () => {
    const undoError = new Error('undo failed');
    const reported = [];
    await assert.rejects(undoAfter(async () => 1, async () => { throw undoError; }, (error) => reported.push(error)), (error) => error === undoError);
    assert.deepEqual(reported, []);
  });

  test('the drift test of migrations.test.js undoes exactly its own change, through undoAfter', () => {
    const source = withoutComments(readFileSync(new URL('./integration/migrations.test.js', import.meta.url), 'utf8'));
    assert.match(source, /^const DRIFT_SQL = 'ALTER TABLE `nexora_test`\.`users` MODIFY name VARCHAR\(40\) NOT NULL';$/m);
    assert.match(source, /^const UNDO_DRIFT_SQL = 'ALTER TABLE `nexora_test`\.`users` MODIFY name VARCHAR\(80\) NOT NULL';$/m);
    assert.ok(source.includes("'users.name varchar(80) NOT NULL',"), 'the undo restores the column that EXPECTED describes');
    const body = source.slice(source.indexOf("test('a drifted schema"), source.indexOf("test('the migration account cannot"));
    const drift = body.indexOf('await migrator.query(DRIFT_SQL);');
    const guarded = body.indexOf('await undoAfter(');
    const migrate = body.indexOf('await migrate()');
    const undo = body.indexOf('() => migrator.query(UNDO_DRIFT_SQL)');
    assert.ok(drift >= 0 && drift < guarded && guarded < migrate && migrate < undo, 'the change, then undoAfter around migrate() and the checks, with the undo as its second argument');
    // Ningún otro ALTER, DROP ni DELETE en esa prueba: solo las dos constantes.
    assert.equal(body.match(/ALTER TABLE|DROP |DELETE /g), null);
  });
});

// El bloqueo de la ejecución (holdRunLock, assertRunLock y releaseRunLock en guard.js), con conexiones
// simuladas: que GET_LOCK y RELEASE_LOCK se comporten así en un MySQL o MariaDB real está sin comprobar.
describe('the run lock: two runs never change nexora_test at the same time', () => {
  const mark = () => markRunner({ event: 'test:integration', files: ['a.test.js'], present: ['a.test.js'] });
  const rejectsGuard = (promise, pattern) => assert.rejects(promise, (error) => error instanceof IntegrationGuardError && pattern.test(error.message) && !error.message.includes(PASSWORD));
  const MIGRATOR = { identity: { db: 'nexora_test', who: 'nexora_test_migrator@127.0.0.1' }, grants: MYSQL.migrator };

  /** Un mysql2 simulado que anota cada conexión que abre; `lock` es lo que responde cada una al bloqueo. */
  function driver(lock = {}) {
    const opened = [];
    const open = () => {
      const connection = fakeConnection({ lock });
      opened.push(connection);
      return connection;
    };
    return { opened, mysql: { createConnection: async () => open(), createPool: () => open() } };
  }

  test('GET_LOCK: 1 is the lock; 0 means another run has it; anything else is an error', () => {
    checkLockResult(1);
    checkLockResult('1');
    refused(() => checkLockResult(0), /another integration run holds the lock nexora_test\.integration_run/);
    for (const value of [null, undefined, 2, -1, '', 'yes', true]) refused(() => checkLockResult(value), /could not be taken/);
    assert.equal(RUN_LOCK, 'nexora_test.integration_run');
  });

  test('it is taken once, without waiting, on a verified connection of its own, before any other connection', async () => {
    mark();
    const { opened, mysql } = driver();
    const first = await connectVerified('app', { env: env(), mysql });
    await connectVerified('migrator', { env: env(), mysql: { createConnection: async () => fakeConnection(MIGRATOR) } });
    await openVerifiedPool('app', { env: env(), mysql });
    const [lock] = opened;
    assert.equal(opened.length, 3, 'the lock connection, then the two of the tests');
    assert.equal(opened[1], first);
    assert.deepEqual(lock.asked, ['SELECT DATABASE() AS db, CURRENT_USER() AS who', 'SHOW GRANTS FOR CURRENT_USER()', GUARD_SQL, 'SELECT GET_LOCK(?, ?) AS got']);
    assert.deepEqual(lock.params.at(-1), [RUN_LOCK, 0], 'a fixed name, and no wait');
    assert.equal(lock.ended, false, 'the lock connection stays open for the whole run');
  });

  test('another run holds it: refused before any other connection, the lock connection closed, and it can be tried again', async () => {
    mark();
    const busy = driver({ got: 0 });
    await rejectsGuard(connectVerified('app', { env: env(), mysql: busy.mysql }), /another integration run holds the lock/);
    await rejectsGuard(openVerifiedPool('app', { env: env(), mysql: busy.mysql }), /another integration run holds the lock/);
    assert.equal(busy.opened.length, 2, 'only the lock connections were opened');
    assert.ok(busy.opened.every((connection) => connection.ended));
    await rejectsGuard(assertRunLock(), /does not hold the integration run lock/);
    // Cuando la otra ejecución termina, un nuevo intento lo consigue.
    const free = driver();
    await connectVerified('app', { env: env(), mysql: free.mysql });
    assert.equal(free.opened.length, 2);
  });

  test('a lock connection that fails its checks never asks for the lock; an error of GET_LOCK leaves no data in the message', async () => {
    mark();
    let opened;
    const unverified = { createConnection: async () => { opened = fakeConnection({ guard: [] }); return opened; } };
    await rejectsGuard(connectVerified('app', { env: env(), mysql: unverified }), /guard row/);
    assert.ok(!opened.asked.some((sql) => /GET_LOCK/.test(sql)));
    assert.equal(opened.ended, true);
    const lockError = Object.assign(new Error(`Access denied for ${PASSWORD}`), { code: 'ER_SPECIFIC_ACCESS_DENIED_ERROR' });
    const failing = driver({ lockError });
    await rejectsGuard(connectVerified('app', { env: env(), mysql: failing.mysql }), /could not be taken \(ER_SPECIFIC_ACCESS_DENIED_ERROR\)/);
    assert.equal(failing.opened.length, 1);
    assert.equal(failing.opened[0].ended, true);
  });

  test('without the runner mark, or with a wrong configuration, nothing is opened', async () => {
    const { opened, mysql } = driver();
    await rejectsGuard(holdRunLock({ env: env(), mysql }), /not started by test\/integration\/run\.js/);
    mark();
    await rejectsGuard(holdRunLock({ env: env({ DB_HOST: '10.0.0.1' }), mysql }), /never use servidor\/\.env/);
    assert.equal(opened.length, 0);
  });

  test('emptying the tables asks the server first whether the lock still belongs to this run', async () => {
    mark();
    const { opened, mysql } = driver();
    await holdRunLock({ env: env(), mysql });
    const [lock] = opened;
    const app = await verifyQueryable(fakeConnection(), 'app');
    await resetAppTables(app);
    assert.equal(lock.asked.at(-1), 'SELECT IS_USED_LOCK(?) = CONNECTION_ID() AS mine');
    assert.deepEqual(lock.params.at(-1), [RUN_LOCK]);
    // El bloqueo se perdió (la conexión se cortó, venció wait_timeout, lo tiene otra): nada se vacía.
    for (const mine of [0, null]) {
      lock.lock.mine = mine;
      const other = await verifyQueryable(fakeConnection(), 'app');
      await rejectsGuard(resetAppTables(other), /no longer holds the integration run lock/);
      assert.ok(!other.asked.some((sql) => sql.startsWith('DELETE')), 'nothing was deleted');
    }
  });

  test('a lock check that fails stops everything, without the message of the error', async () => {
    mark();
    const { mysql } = driver({ checkError: Object.assign(new Error(`Lost connection for ${PASSWORD}`), { code: 'PROTOCOL_CONNECTION_LOST' }) });
    await holdRunLock({ env: env(), mysql });
    const app = await verifyQueryable(fakeConnection(), 'app');
    await rejectsGuard(resetAppTables(app), /could not be checked \(PROTOCOL_CONNECTION_LOST\)/);
    assert.ok(!app.asked.some((sql) => sql.startsWith('DELETE')));
  });

  test('without the lock, nothing is emptied', async () => {
    const app = await verifyQueryable(fakeConnection(), 'app');
    await rejectsGuard(resetAppTables(app), /does not hold the integration run lock/);
    assert.ok(!app.asked.some((sql) => sql.startsWith('DELETE')));
  });

  test('releaseRunLock() releases it by name and closes its connection; after that, nothing connects', async () => {
    mark();
    const { opened, mysql } = driver();
    await holdRunLock({ env: env(), mysql });
    await releaseRunLock();
    const [lock] = opened;
    assert.equal(lock.asked.at(-1), 'SELECT RELEASE_LOCK(?)');
    assert.deepEqual(lock.params.at(-1), [RUN_LOCK]);
    assert.equal(lock.ended, true);
    assert.equal(lock.closed, true, 'the socket is closed for good, not only asked to end');
    await rejectsGuard(connectVerified('app', { env: env(), mysql }), /already released/);
    await rejectsGuard(assertRunLock(), /does not hold the integration run lock/);
    assert.equal(opened.length, 1);
    await releaseRunLock(); // otra vez: no hace nada
  });

  test('a release that fails is not hidden, and the connection is closed anyway', async () => {
    mark();
    const releaseError = Object.assign(new Error('release failed'), { code: 'PROTOCOL_CONNECTION_LOST' });
    const { opened, mysql } = driver({ releaseError });
    await connectVerified('app', { env: env(), mysql });
    await assert.rejects(releaseRunLock(), (error) => error === releaseError, 'the error of RELEASE_LOCK reaches the caller');
    const [lock] = opened;
    assert.equal(lock.ended, true, 'the close was asked for even though the release failed');
    assert.equal(lock.closed, true, 'and the socket is closed for good: that is what drops the lock server-side');
  });

  test('a release and a close that both fail travel together, and the socket is closed anyway', async () => {
    mark();
    const releaseError = Object.assign(new Error('release failed'), { code: 'PROTOCOL_CONNECTION_LOST' });
    const endError = Object.assign(new Error('close failed'), { code: 'PROTOCOL_CONNECTION_LOST' });
    const { opened, mysql } = driver({ releaseError, endError });
    await connectVerified('app', { env: env(), mysql });
    await assert.rejects(releaseRunLock(), (error) => {
      assert.ok(error instanceof AggregateError, 'the two failures travel together');
      assert.deepEqual(error.errors, [releaseError, endError]);
      return true;
    });
    assert.equal(opened[0].closed, true, 'forcing the socket closed does not hide the original failures');
  });

  test('the socket of the lock does not keep the process alive, except while a check waits for its answer', async () => {
    mark();
    const calls = [];
    const stream = { ref: () => calls.push('ref'), unref: () => calls.push('unref') };
    const connection = Object.assign(fakeConnection(), { connection: { stream } });
    await holdRunLock({ env: env(), mysql: { createConnection: async () => connection } });
    assert.deepEqual(calls, ['unref']);
    await assertRunLock();
    assert.deepEqual(calls, ['unref', 'ref', 'unref']);
  });

  test('run.js closes the shared pool and releases the lock after all the tests, hiding neither failure; migrations are only spawned with the lock held', () => {
    const run = withoutComments(readFileSync(new URL('./integration/run.js', import.meta.url), 'utf8'));
    // Un solo hook raíz de cierre, y con esta forma exacta: cerrar el contexto compartido y, en el
    // finally, liberar el bloqueo, en ese orden. No basta con que aparezcan las dos llamadas.
    const hooks = [...run.matchAll(/^after\(/gm)];
    assert.equal(hooks.length, 1, 'run.js registers exactly one root after hook');
    const hook = run.slice(hooks[0].index, run.indexOf('\nconst FILES')).replace(/\s+/g, ' ').trim();
    assert.match(hook, /^after\(async \(\) => \{[\s\S]*await closeAppContext\(\);[\s\S]*\} finally \{[\s\S]*await releaseRunLock\(\);[\s\S]*\} \}\);$/);
    assert.ok(hook.indexOf('closeAppContext()') < hook.indexOf('releaseRunLock()'), 'the shared pool is closed before the lock is released');
    // Los dos fallos se lanzan juntos: con un finally que solo lanza el último, el error del pool
    // desaparecería del diagnóstico, que es el que explica por qué el proceso no terminaba.
    assert.match(hook, /const failures = \[poolFailure, lockFailure\]\.filter\(Boolean\);[\s\S]*throw new AggregateError\(failures,/);
    // Y en guard.js: RELEASE_LOCK y connection.end() salen a la vez, ninguno se silencia, y el cierre no
    // depende de la respuesta de la consulta. Si los dos fallan, se lanzan los dos.
    const guard = withoutComments(readFileSync(new URL('./integration/guard.js', import.meta.url), 'utf8'));
    const release = guard.slice(guard.indexOf('export async function releaseRunLock()'), guard.indexOf('export async function connectVerified(')).replace(/\s+/g, ' ').trim();
    assert.doesNotMatch(release, /\.catch\(\(\) => \{\}\)/, 'releaseRunLock() must not swallow the release or the close');
    assert.match(release, /const releasing = connection\.query\('SELECT RELEASE_LOCK\(\?\)', \[RUN_LOCK\]\)\.then\(\(\) => null, \(error\) => error\);/);
    assert.match(release, /const closing = connection\.end\(\)\.then\(\(\) => null, \(error\) => error\);/);
    assert.ok(release.indexOf('connection.end()') < release.indexOf('await Promise.all('), 'the close is asked for before waiting on the query');
    assert.match(release, /if \(outcome\) failures\.push\(outcome\);/);
    assert.match(release, /if \(failures\.length > 1\) throw new AggregateError\(failures,/);
    // Con el límite, la liberación no se da por confirmada; y en el finally, la conexión se cierra sin
    // esperar a la cola de comandos y el socket queda sin referenciar.
    assert.match(release, /bounded\([\s\S]*could not be confirmed released within/);
    assert.match(release, /\} finally \{[\s\S]*connection\.close\(\);[\s\S]*socketOf\(connection\)\?\.unref\?\.\(\);[\s\S]*\}/);
    const migrations = readFileSync(new URL('./integration/migrations.test.js', import.meta.url), 'utf8');
    const body = migrations.slice(migrations.indexOf('async function migrate()'));
    assert.ok(body.indexOf('await assertRunLock();') >= 0 && body.indexOf('await assertRunLock();') < body.indexOf('spawn('));
  });
});
