// Guardas de las pruebas de integración con MySQL o MariaDB (servidor/test/integration).
//
// Nada de esta carpeta se ejecuta con `npm test`: solo con `npm run test:integration`, que carga
// servidor/.env.integration (ignorado por git) y NUNCA servidor/.env. Antes de cualquier consulta que
// lea o escriba filas, cada conexión tiene que demostrar que es exactamente la autorizada:
//
//   1. Configuración: NODE_ENV=test; ninguna variable DB_* en el entorno (si las hay, se cargó
//      servidor/.env o el entorno del servidor real); TEST_DB_HOST=127.0.0.1; TEST_DB_NAME=nexora_test;
//      el usuario exacto de cada papel; una contraseña que no sea la plantilla.
//   2. Identidad efectiva, ya conectada: DATABASE() es nexora_test y CURRENT_USER() es la cuenta
//      esperada en 127.0.0.1. CURRENT_USER() es la cuenta con la que el servidor autenticó, no el
//      nombre que se pidió: un usuario anónimo o un comodín de host no pasan.
//   3. Permisos: SHOW GRANTS FOR CURRENT_USER() tiene exactamente los de setup-admin.sql para ese
//      papel, ni uno más ni uno menos, y en ningún otro sitio. Sin roles, PROXY, GRANT OPTION ni
//      permisos globales (salvo USAGE, que es «ninguno»).
//   4. La marca nexora_test_guard.marker, con su única fila, en un esquema propio donde las dos
//      cuentas solo pueden leer.
//   0. Antes que todo: que el proceso lo haya lanzado run.js con `npm run test:integration` y una lista
//      de archivos idéntica a la carpeta (markRunner). Sin eso, ninguna función de aquí conecta. Y,
//      antes de abrir cualquier otra conexión, el bloqueo de la ejecución (holdRunLock): dos
//      ejecuciones no pueden cambiar nexora_test a la vez.
//  -1. Antes incluso de cargar las pruebas, preflight.js (con --import) rechaza un entorno inseguro e
//      instala un gancho de resolución de módulos: servidor/src/ y mysql2 no se pueden cargar, de
//      ninguna forma (import estático o dinámico, con variable o plantilla, createRequire), hasta que
//      una conexión de la aplicación se haya verificado y useAppDatabase() haya preparado el entorno.
//      Ver checkModuleLoad.
//
// Si algo no coincide, se lanza IntegrationGuardError y la prueba no hace nada más. Los mensajes nunca
// copian la contraseña ni las líneas de SHOW GRANTS (en MariaDB incluyen el resumen de la contraseña).
// La única operación destructiva (resetAppTables, que vacía las tres tablas de la aplicación de
// nexora_test) solo acepta conexiones verificadas aquí como «app», con nombres escritos en este
// archivo, nunca leídos del entorno. Ninguna cuenta de pruebas puede borrar tablas: preparar un
// esquema nuevo es un paso administrativo aparte (prepare-fresh-schema-admin.sql).

import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const TEST_DATABASE = 'nexora_test';
export const TEST_HOST = '127.0.0.1';
// La marca vive en su propio esquema, donde las dos cuentas solo pueden leer: ninguna prueba puede
// cambiarla ni borrarla, y su permiso no se mezcla con los de la aplicación.
export const GUARD_SCHEMA = 'nexora_test_guard';
export const GUARD_TABLE = 'marker';
export const GUARD_VALUE = 'nexora-integration-tests-only';
// Las tablas de la aplicación, de hijas a madres: el orden en que se pueden vaciar o borrar.
export const APP_TABLES = Object.freeze(['oauth_accounts', 'sessions', 'users']);

const GUARD_SCOPE = `${GUARD_SCHEMA}.${GUARD_TABLE}`;
// Sin DROP: la cuenta de migraciones crea y modifica las tres tablas, pero no puede borrarlas.
const MIGRATOR_TABLE = Object.freeze(['ALTER', 'CREATE', 'INSERT', 'REFERENCES']);
// En un GRANT sobre una base entera, «_» es un comodín («cualquier carácter»): `nexora_test`.* daría
// también acceso a nexoraXtest. setup-admin.sql lo escribe escapado, y SHOW GRANTS lo muestra así; la
// forma sin escapar se rechaza. En los permisos de tabla el nombre de la base es literal.
const APP_DATABASE_SCOPE = 'nexora\\_test.*';

/**
 * Los dos papeles de setup-admin.sql y los permisos exactos de cada uno, por objeto. El de migraciones
 * solo tiene permisos sobre las tres tablas, ninguno sobre la base entera: no puede crear otras
 * tablas, borrarlas, borrar la base ni tocar la marca.
 */
export const ROLES = Object.freeze({
  migrator: Object.freeze({
    prefix: 'TEST_DB_MIGRATOR',
    user: 'nexora_test_migrator',
    scopes: Object.freeze({
      ...Object.fromEntries(APP_TABLES.map((table) => [`${TEST_DATABASE}.${table}`, MIGRATOR_TABLE])),
      [GUARD_SCOPE]: Object.freeze(['SELECT']),
    }),
  }),
  app: Object.freeze({
    prefix: 'TEST_DB_APP',
    user: 'nexora_test_app',
    scopes: Object.freeze({
      [APP_DATABASE_SCOPE]: Object.freeze(['DELETE', 'INSERT', 'SELECT']),
      [GUARD_SCOPE]: Object.freeze(['SELECT']),
    }),
  }),
});

// El ejecutor (run.js) marca el proceso solo si lo lanzó `npm run test:integration` y su lista de
// archivos coincide con la carpeta. Sin la marca, nada de este archivo abre una conexión real.
const RUNNER = Symbol.for('nexora.integration.runner');

const SERVER_VARIABLES = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'];

export class IntegrationGuardError extends Error {
  constructor(message) {
    super(`integration guard: ${message}`);
    this.name = 'IntegrationGuardError';
  }
}

const fail = (message) => { throw new IntegrationGuardError(message); };

// Lo que useAppDatabase() ha escrito en process.env: lo único DB_* que se admite después.
let ownServerVariables = null;
// Si alguna conexión ha pasado ya todas las comprobaciones como «app» (verifyQueryable).
let appVerified = false;
// Si servidor/src/ se puede cargar ya: lo decide useAppDatabase(), y lo aplica checkModuleLoad.
let appModulesReady = false;

function roleOf(role) {
  return Object.hasOwn(ROLES, role) ? ROLES[role] : fail(`unknown role ${JSON.stringify(role)}`);
}

/**
 * La configuración de conexión de un papel, desde `env`. Lanza ante cualquier discrepancia.
 * No mira nunca servidor/.env: si hay variables DB_* que no puso useAppDatabase(), se detiene.
 */
export function readIntegrationConfig(env, role) {
  const { prefix, user } = roleOf(role);
  const present = SERVER_VARIABLES.filter((name) => Object.hasOwn(env, name));
  const own = ownServerVariables && present.every((name) => env[name] === ownServerVariables[name])
    && present.length === Object.keys(ownServerVariables).length;
  if (present.length > 0 && !own) {
    fail(`${present.join(', ')} are set: the integration tests never use servidor/.env or the server's environment; run them with npm run test:integration`);
  }
  if (env.NODE_ENV !== 'test') fail('NODE_ENV must be "test"');
  if (env.TEST_DB_HOST !== TEST_HOST) fail(`TEST_DB_HOST must be ${TEST_HOST}`);
  const port = env.TEST_DB_PORT;
  if (typeof port !== 'string' || !/^[1-9]\d{0,4}$/.test(port) || Number(port) > 65535) fail('TEST_DB_PORT must be a port number');
  if (env.TEST_DB_NAME !== TEST_DATABASE) fail(`TEST_DB_NAME must be ${TEST_DATABASE}`);
  if (env[`${prefix}_USER`] !== user) fail(`${prefix}_USER must be ${user}`);
  const password = env[`${prefix}_PASSWORD`];
  if (typeof password !== 'string' || password === '' || /[<>]/.test(password)) {
    fail(`${prefix}_PASSWORD must be set to the password chosen in setup-admin.sql, not its placeholder`);
  }
  return { host: TEST_HOST, port: Number(port), user, password, database: TEST_DATABASE };
}

/** La identidad de una conexión ya abierta: { database, currentUser } de SELECT DATABASE(), CURRENT_USER(). */
export function checkIdentity({ database, currentUser }, role) {
  const { user } = roleOf(role);
  if (database !== TEST_DATABASE) fail(`the connection uses database ${JSON.stringify(database)}, not ${TEST_DATABASE}`);
  if (currentUser !== `${user}@${TEST_HOST}`) fail(`the server authenticated the connection as another account, not ${user}@${TEST_HOST}`);
}

const unquote = (text) => text.replace(/[`'"]/g, '');

/**
 * Comprueba las líneas de SHOW GRANTS FOR CURRENT_USER(). Admite el formato de MySQL 8 y el de
 * MariaDB (que añade IDENTIFIED BY PASSWORD '…' y los límites de recursos a la línea de USAGE).
 */
export function checkGrants(lines, role) {
  const { user, scopes: expectedScopes } = roleOf(role);
  const grantee = `${user}@${TEST_HOST}`;
  const scopes = new Map();
  for (const raw of lines) {
    if (typeof raw !== 'string') fail('SHOW GRANTS returned something that is not text');
    // Lo que va detrás del destinatario: contraseña (MariaDB), límites de recursos u opciones.
    const match = raw.match(/^GRANT (.+?) ON (\S+) TO (\S+)(.*)$/);
    if (!match) fail('a grant that is not a privilege on an object (a role or a proxy grant)');
    const [, privilegeText, scopeText, granteeText, tail] = match;
    if (unquote(granteeText) !== grantee) fail('a grant to another account');
    if (/GRANT OPTION/i.test(tail)) fail('a grant WITH GRANT OPTION');
    if (/^PROXY$/i.test(privilegeText.trim())) fail('a PROXY grant');
    const scope = unquote(scopeText);
    if (/\(/.test(privilegeText)) fail(`column privileges on ${scope}`);
    const privileges = privilegeText.split(',').map((name) => name.trim().toUpperCase());
    if (privileges.includes('ALL PRIVILEGES') || privileges.includes('ALL')) fail(`ALL PRIVILEGES on ${scope}`);
    scopes.set(scope, new Set([...(scopes.get(scope) ?? []), ...privileges]));
  }
  const expected = new Map(Object.entries(expectedScopes));
  for (const [scope, privileges] of scopes) {
    if (scope === '*.*') {
      const global = [...privileges].filter((name) => name !== 'USAGE');
      if (global.length > 0) fail(`global privileges: ${global.sort().join(', ')}`);
      continue;
    }
    if (!expected.has(scope)) fail(`privileges outside the authorized objects: ${scope}`);
    const want = [...expected.get(scope)].sort().join(', ');
    const have = [...privileges].sort().join(', ');
    if (have !== want) fail(`on ${scope} the account has ${have}; it must have exactly ${want}`);
  }
  for (const scope of expected.keys()) {
    if (!scopes.has(scope)) fail(`no privileges on ${scope}: it is not the account of setup-admin.sql`);
  }
}

/** Las filas de SELECT purpose FROM nexora_test_guard.marker. */
export function checkGuardRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 1 || rows[0]?.purpose !== GUARD_VALUE) {
    fail(`${GUARD_SCOPE} does not hold its single guard row`);
  }
}

/** La consulta de la marca, con nombres fijos. */
export const GUARD_SQL = `SELECT purpose FROM \`${GUARD_SCHEMA}\`.\`${GUARD_TABLE}\``;

/**
 * La llama run.js: comprueba que lo lanzó `npm run test:integration` (que carga .env.integration y no
 * servidor/.env) y que su lista de archivos es exactamente la de la carpeta; solo entonces marca el
 * proceso. Un archivo ejecutado suelto, o uno que no esté en la lista, nunca llega a conectar.
 */
export function markRunner({ event = process.env.npm_lifecycle_event, files, present }) {
  if (event !== 'test:integration') fail('the integration tests only run through npm run test:integration');
  const listed = [...files].sort();
  const found = [...present].sort();
  if (listed.length === 0 || listed.join('\n') !== found.join('\n')) {
    fail(`run.js lists ${listed.join(', ') || 'nothing'}, but the folder has ${found.join(', ') || 'nothing'}: every file must be listed, and only those`);
  }
  globalThis[RUNNER] = true;
}

function assertRunner() {
  if (globalThis[RUNNER] !== true) fail('not started by test/integration/run.js through npm run test:integration: no connection is opened');
}

/** Solo para las pruebas de estas guardas: olvida la marca del ejecutor y el bloqueo. */
export function resetRunnerForTests() {
  delete globalThis[RUNNER];
  runLock = null;
}

const verified = new WeakMap();

/**
 * Comprueba identidad, permisos y guarda de algo con query() (una conexión o un pool de mysql2).
 * Si todo coincide, lo anota como verificado para ese papel.
 */
export async function verifyQueryable(queryable, role) {
  roleOf(role);
  try {
    const [[identity]] = await queryable.query('SELECT DATABASE() AS db, CURRENT_USER() AS who');
    checkIdentity({ database: identity.db, currentUser: identity.who }, role);
    const [grants] = await queryable.query('SHOW GRANTS FOR CURRENT_USER()');
    checkGrants(grants.map((row) => Object.values(row)[0]), role);
    const [guard] = await queryable.query(GUARD_SQL);
    checkGuardRows(guard);
  } catch (error) {
    if (error instanceof IntegrationGuardError) throw error;
    // Un error del servidor (sin permiso, tabla inexistente…): solo su código, nunca su mensaje.
    fail(`the checks could not run (${error.code ?? error.name})`);
  }
  verified.set(queryable, role);
  if (role === 'app') appVerified = true;
  return queryable;
}

// El bloqueo de la ejecución. Dos ejecuciones a la vez sobre nexora_test se pisarían (resetAppTables de
// una vaciaría las tablas de la otra, y las migraciones de una cambiarían el esquema de la otra). Antes
// de abrir cualquier otra conexión, la ejecución toma un bloqueo con nombre (GET_LOCK) con una conexión
// propia, verificada como «app», que conserva hasta el final:
//   - GET_LOCK no espera (0 s): si otra ejecución lo tiene, esta se detiene sin conectar nada más.
//   - Lo libera releaseRunLock() (run.js, al terminar) o, si el proceso acaba de cualquier forma
//     (también si se cae), el propio servidor, al cerrarse la conexión. Su socket no mantiene vivo el
//     proceso (unref): no impide que termine.
//   - Antes de vaciar tablas o de migrar, assertRunLock() comprueba en el servidor que el bloqueo sigue
//     siendo de esta conexión: si se perdió (conexión cortada, wait_timeout), se detiene.
// GET_LOCK es de TODO el servidor MySQL o MariaDB, no de una base: ordena las ejecuciones de estas
// pruebas entre sí. No aísla nada ni protege una base de producción: eso lo hacen las demás guardas.
// No necesita ningún permiso.
export const RUN_LOCK = 'nexora_test.integration_run';
const RUN_LOCK_WAIT_SECONDS = 0;
// null: sin tomar; una promesa: tomándose o tomado ({ connection }); 'released': ya liberado.
let runLock = null;

const socketOf = (connection) => connection?.connection?.stream;

/** Ejecuta `work` con el socket del bloqueo referenciado: mientras espera, el proceso sigue vivo. */
async function referenced(connection, work) {
  const socket = socketOf(connection);
  socket?.ref?.();
  try {
    return await work();
  } finally {
    socket?.unref?.();
  }
}

/** Lo que devolvió GET_LOCK: 1 si se obtuvo; 0 si lo tiene otra ejecución; NULL, un error. */
export function checkLockResult(got) {
  if (got === 1 || got === '1') return;
  if (got === 0 || got === '0') fail(`another integration run holds the lock ${RUN_LOCK}: wait for it to end; nothing was changed`);
  fail(`the lock ${RUN_LOCK} could not be taken: nothing was changed`);
}

/**
 * Toma el bloqueo de la ejecución, una vez por proceso (las llamadas siguientes esperan al mismo). Si
 * falla, no queda tomado y se puede volver a intentar; después de releaseRunLock(), ya no.
 */
export function holdRunLock({ env = process.env, mysql } = {}) {
  try {
    assertRunner();
  } catch (error) {
    return Promise.reject(error);
  }
  if (runLock === 'released') return Promise.reject(new IntegrationGuardError('the integration run lock was already released: no connection is opened'));
  if (runLock !== null) return runLock;
  const taking = (async () => {
    const config = readIntegrationConfig(env, 'app');
    const driver = mysql ?? await import('mysql2/promise');
    const connection = await driver.createConnection({ ...config, charset: 'utf8mb4', multipleStatements: false });
    try {
      await verifyQueryable(connection, 'app');
      let row;
      try {
        [[row]] = await connection.query('SELECT GET_LOCK(?, ?) AS got', [RUN_LOCK, RUN_LOCK_WAIT_SECONDS]);
      } catch (error) {
        fail(`the lock ${RUN_LOCK} could not be taken (${error.code ?? error.name})`);
      }
      checkLockResult(row?.got);
    } catch (error) {
      await connection.end().catch(() => {});
      throw error;
    }
    socketOf(connection)?.unref?.();
    return { connection };
  })().catch((error) => {
    if (runLock === taking) runLock = null;
    throw error;
  });
  runLock = taking;
  return taking;
}

/** Comprueba en el servidor que el bloqueo sigue siendo de esta ejecución. Lanza si no. */
export async function assertRunLock() {
  if (runLock === null || runLock === 'released') fail('this process does not hold the integration run lock: nothing is changed');
  const { connection } = await runLock;
  let row;
  try {
    [[row]] = await referenced(connection, () => connection.query('SELECT IS_USED_LOCK(?) = CONNECTION_ID() AS mine', [RUN_LOCK]));
  } catch (error) {
    fail(`the integration run lock could not be checked (${error.code ?? error.name}): nothing is changed`);
  }
  if (!(row?.mine === 1 || row?.mine === '1')) fail('this process no longer holds the integration run lock: nothing is changed');
}

/** Libera el bloqueo y cierra su conexión (run.js, al terminar). Después no se abre ninguna conexión. */
export async function releaseRunLock() {
  const current = runLock;
  runLock = 'released';
  if (current === null || current === 'released') return;
  let connection;
  try {
    ({ connection } = await current);
  } catch {
    return; // no llegó a tomarse
  }
  await referenced(connection, async () => {
    await connection.query('SELECT RELEASE_LOCK(?)', [RUN_LOCK]).catch(() => {});
    await connection.end().catch(() => {});
  });
}

/** Abre una conexión verificada de un papel. mysql2 se pasa desde fuera para poder probar sin él. */
export async function connectVerified(role, { env = process.env, mysql } = {}) {
  assertRunner();
  await holdRunLock({ env, mysql });
  const config = readIntegrationConfig(env, role);
  const driver = mysql ?? await import('mysql2/promise');
  const connection = await driver.createConnection({ ...config, charset: 'utf8mb4', multipleStatements: false });
  try {
    return await verifyQueryable(connection, role);
  } catch (error) {
    await connection.end().catch(() => {});
    throw error;
  }
}

/**
 * Un pool propio y verificado de un papel, para las pruebas que lo cierran (pool.end()) sin tocar el
 * de src/db.js. Mismas comprobaciones que connectVerified; si fallan, se cierra.
 */
export async function openVerifiedPool(role, { env = process.env, mysql, connectionLimit = 4 } = {}) {
  assertRunner();
  await holdRunLock({ env, mysql });
  const config = readIntegrationConfig(env, role);
  const driver = mysql ?? await import('mysql2/promise');
  const pool = driver.createPool({ ...config, charset: 'utf8mb4', multipleStatements: false, connectionLimit });
  try {
    return await verifyQueryable(pool, role);
  } catch (error) {
    await pool.end().catch(() => {});
    throw error;
  }
}

function assertVerified(queryable, role) {
  if (verified.get(queryable) !== role) fail(`refused: the connection was not verified as ${role}`);
}

// Las únicas sentencias destructivas de las pruebas: nombres fijos, nada leído del entorno.
export const RESET_SQL = Object.freeze(APP_TABLES.map((table) => `DELETE FROM \`${TEST_DATABASE}\`.\`${table}\``));

/** Vacía las tablas de la aplicación. Solo con una conexión verificada como «app» y el bloqueo tomado. */
export async function resetAppTables(queryable) {
  assertVerified(queryable, 'app');
  await assertRunLock();
  for (const sql of RESET_SQL) await queryable.query(sql);
}

/**
 * Cuáles de las tres tablas de la aplicación existen ya, para la prueba de esquema nuevo. Solo lee
 * information_schema, con una conexión verificada como «migrator».
 */
export async function existingAppTables(queryable) {
  assertVerified(queryable, 'migrator');
  const [rows] = await queryable.query(
    `SELECT TABLE_NAME AS t FROM information_schema.TABLES WHERE TABLE_SCHEMA = '${TEST_DATABASE}' AND TABLE_NAME IN (${APP_TABLES.map((table) => `'${table}'`).join(', ')}) ORDER BY TABLE_NAME`,
  );
  return rows.map((row) => row.t);
}

/**
 * Prepara process.env para que src/config.js (y por tanto el pool de src/db.js) use la base de pruebas
 * con el papel «app». Exige que una conexión de ese papel ya se haya verificado, y se llama antes de
 * importar nada de src/: es lo que permite cargarlo (checkModuleLoad). Devuelve las variables puestas,
 * que readIntegrationConfig admite a partir de entonces.
 */
export function useAppDatabase(env = process.env) {
  assertRunner();
  if (!appVerified) fail('useAppDatabase() needs a connection verified as app first (connectVerified)');
  const config = readIntegrationConfig(env, 'app');
  ownServerVariables = { DB_HOST: config.host, DB_PORT: String(config.port), DB_USER: config.user, DB_PASSWORD: config.password, DB_NAME: config.database };
  Object.assign(env, ownServerVariables);
  appModulesReady = true;
  return Object.keys(ownServerVariables);
}

/**
 * Lo primero que comprueba preflight.js, antes de cargar ninguna prueba: que lo lanzó
 * `npm run test:integration`, que no hay ninguna variable DB_* (servidor/.env o el entorno del servidor
 * real), que el playground no se puede activar y que la configuración de los dos papeles es la
 * autorizada.
 */
export function checkPreflight(env) {
  if (env.npm_lifecycle_event !== 'test:integration') fail('the integration tests only run through npm run test:integration');
  const present = SERVER_VARIABLES.filter((name) => Object.hasOwn(env, name));
  if (present.length > 0) fail(`${present.join(', ')} are set: the integration tests never use servidor/.env or the server's environment`);
  // El playground ejecuta código y lanza procesos: en estas pruebas está siempre desactivado. Solo se
  // admite PLAYGROUND_ENABLED sin definir o exactamente "false"; cualquier otra PLAYGROUND_* (la orden
  // del worker, los límites…) sugiere que se ha copiado la configuración del servidor, y se rechaza.
  const playground = Object.keys(env).filter((name) => name.startsWith('PLAYGROUND_')).sort();
  for (const name of playground) {
    if (name === 'PLAYGROUND_ENABLED' && env[name] === 'false') continue;
    fail(name === 'PLAYGROUND_ENABLED'
      ? 'PLAYGROUND_ENABLED must be unset or "false": the playground stays disabled in the integration tests'
      : `${name} is set: the integration tests never configure the playground`);
  }
  for (const role of Object.keys(ROLES)) readIntegrationConfig(env, role);
}

// Las versiones en las que el gancho de preflight.js funciona como esperan las guardas. module.registerHooks
// existe desde Node 22.15 y 23.5. Observación empírica, con causa sin confirmar: en algunas versiones, al
// importar un módulo CommonJS desde ESM, el gancho recibió una segunda resolución con la ruta absoluta y
// sin parentURL; así no puede saber quién lo pide y bloquea mysql2 también en el orden legítimo. La
// documentación de Node no describe ese comportamiento ni su cambio. Medido solo en Windows, con las
// distribuciones oficiales y solo en estas versiones: lo bloquearon 22.15.0, 22.18.0, 22.19.0, 22.20.0,
// 22.21.0, 22.22.0, 22.22.1, 22.22.2, 24.0.0, 24.11.1, 24.13.0 y 24.13.1; no lo bloquearon 22.22.3,
// 22.23.0, 22.23.3, 24.14.0, 24.14.1, 24.15.0, 24.16.0, 24.21.0, 25.9.0 y 26.12.0. Los mínimos de abajo
// salen de esa medición. La rama 23 no se admite (sin soporte).
export const HOOK_MINIMUMS = Object.freeze({ 22: Object.freeze([22, 22, 3]), 24: Object.freeze([24, 14, 0]) });
const HOOK_REQUIREMENT = 'Node 22.22.3 or later in the 22 line, or 24.14.0 or later';

/** Por qué este Node no puede ejecutar las pruebas de integración, o null si puede. */
export function hookSupportProblem(registerHooks, version = process.version) {
  if (typeof registerHooks !== 'function') {
    return `the integration tests need module.registerHooks (${HOOK_REQUIREMENT}), and this is Node ${version}: they do not run on it`;
  }
  const [major, minor, patch] = String(version).replace(/^v/, '').split('.').map(Number);
  const minimum = HOOK_MINIMUMS[major];
  const below = minimum && (minor < minimum[1] || (minor === minimum[1] && patch < minimum[2]));
  if (!(major >= 22) || major === 23 || below || [minor, patch].some(Number.isNaN)) {
    return `the integration tests need ${HOOK_REQUIREMENT}: in Node ${version}, module.registerHooks does not see who loads a CommonJS module imported from ESM, and the guards would block mysql2`;
  }
  return null;
}

/**
 * Que este Node pueda ejecutar el gancho de preflight.js (hookSupportProblem). Si no, las pruebas de
 * integración no se ejecutan: no hay otra forma síncrona, en el mismo hilo, de vigilar import() y require
 * a la vez. npm test y el servidor no lo necesitan (ver testing.md).
 */
export function checkHookSupport(registerHooks, version = process.version) {
  const problem = hookSupportProblem(registerHooks, version);
  if (problem) fail(problem);
}

/**
 * Los únicos módulos de servidor/src/ que pueden cargar las pruebas de integración (rutas relativas a
 * src/): los que importan, y todo lo que estos importan a su vez. integration-guard.test.js comprueba
 * que la lista es exactamente eso. Quedan fuera index.js (escucha en PORT, 3000 si no hay otro, y
 * arranca el borrado de sesiones) y migrate.js (conecta y migra al cargarse): las migraciones solo se
 * ejecutan en un proceso aparte, con migrate-child.js. playground/worker.js crea al cargarse su carpeta
 * de trabajo en el directorio temporal, como en npm test; el playground sigue desactivado.
 */
export const APP_MODULES = Object.freeze([
  'app.js', 'auth.js', 'captcha.js', 'client-ip.js', 'config.js', 'db.js', 'environment.js', 'lifecycle.js', 'listen.js',
  'login-throttle.js', 'oauth.js', 'passwords.js', 'playground/config.js', 'playground/examples.js', 'playground/limiter.js',
  'playground/router.js', 'playground/worker.js', 'rate-limits.js', 'safe-log.js', 'security-headers.js', 'session-cleanup.js',
  'sessions.js',
]);

const SRC_DIR = fileURLToPath(new URL('../../src/', import.meta.url)).toLowerCase();
const GUARD_FILE = fileURLToPath(import.meta.url).toLowerCase();

/**
 * Qué es un módulo, por su URL ya resuelta: 'src' (servidor/src/), 'mysql2', 'guard' (este archivo) o
 * null. Se compara la ruta del disco, ya decodificada y en minúsculas: «SRC» o «%73rc» en Windows
 * cargarían el mismo archivo.
 */
function moduleKind(url) {
  if (typeof url !== 'string' || !url.startsWith('file:')) return null;
  const file = path.resolve(fileURLToPath(url)).toLowerCase();
  if (file.startsWith(SRC_DIR)) return 'src';
  if (/[\\/]node_modules[\\/]mysql2([\\/]|$)/.test(file)) return 'mysql2';
  if (file === GUARD_FILE) return 'guard';
  return null;
}

/** La ruta de un módulo de servidor/src/, relativa a src/, en minúsculas y con «/». */
const srcModule = (url) => path.relative(SRC_DIR, path.resolve(fileURLToPath(url)).toLowerCase()).split(path.sep).join('/');

/**
 * La regla del gancho de preflight.js, para cada módulo que se va a cargar (`url`) desde `parentURL`:
 *   - servidor/src/, solo los de APP_MODULES, y solo después de useAppDatabase() (una conexión «app»
 *     verificada antes); index.js, migrate.js o cualquier otro, nunca;
 *   - mysql2, solo desde este archivo con el proceso ya marcado por run.js, desde servidor/src/ en ese
 *     mismo momento, o desde dentro de mysql2;
 *   - todo lo demás, libre.
 * Lanza IntegrationGuardError si no se cumple, y el módulo no se carga (ni se evalúa).
 */
export function checkModuleLoad(url, parentURL) {
  const kind = moduleKind(url);
  if (kind !== 'src' && kind !== 'mysql2') return;
  if (kind === 'src') {
    const name = srcModule(url);
    if (!APP_MODULES.includes(name)) fail(`servidor/src/${name} is not one of the modules the integration tests may load (APP_MODULES)`);
    if (appModulesReady) return;
  }
  if (kind === 'mysql2') {
    const parent = moduleKind(parentURL);
    if (parent === 'mysql2') return;
    if (parent === 'src' && appModulesReady) return;
    if (parent === 'guard' && globalThis[RUNNER] === true) return;
  }
  fail(`${kind === 'src' ? 'servidor/src/' : 'mysql2'} cannot be loaded here: only after the guards have verified an application connection (see preflight.js)`);
}

/**
 * El entorno de un proceso hijo que ejecuta src/migrate.js (a través de migrate-child.js) con el papel
 * «migrator», y nada más.
 */
export function migratorProcessEnv(env = process.env) {
  assertRunner();
  const config = readIntegrationConfig(env, 'migrator');
  return {
    PATH: env.PATH, SystemRoot: env.SystemRoot, NODE_ENV: 'test',
    DB_HOST: config.host, DB_PORT: String(config.port), DB_USER: config.user, DB_PASSWORD: config.password, DB_NAME: config.database,
  };
}

// Las únicas variables que puede tener el proceso de migraciones: las de migratorProcessEnv.
const MIGRATION_CHILD_VARIABLES = Object.freeze(['DB_HOST', 'DB_NAME', 'DB_PASSWORD', 'DB_PORT', 'DB_USER', 'NODE_ENV', 'PATH', 'SystemRoot']);
// En Windows, libuv (bajo Node) añade a todo proceso hijo estas variables del sistema, copiadas del
// padre, aunque no se le pasen: son del sistema operativo, no de configuración, y no llevan
// credenciales de la base de datos. Solo se admiten en Windows.
const WINDOWS_CHILD_VARIABLES = Object.freeze(['HOMEDRIVE', 'HOMEPATH', 'LOGONSERVER', 'SYSTEMDRIVE', 'TEMP', 'USERDOMAIN', 'USERNAME', 'USERPROFILE', 'WINDIR']);

/**
 * Dentro del proceso de migraciones (migrate-child.js): su entorno tiene que ser exactamente el de
 * migratorProcessEnv (más, en Windows, las variables del sistema que añade libuv), con la cuenta de
 * migraciones y nada más (ni NODE_OPTIONS, ni variables TEST_*, ni la cuenta de la aplicación).
 * Devuelve la configuración de conexión.
 */
export function readMigrationChildConfig(env, platform = process.platform) {
  const allowed = [...MIGRATION_CHILD_VARIABLES, ...(platform === 'win32' ? WINDOWS_CHILD_VARIABLES : [])].map((name) => name.toLowerCase());
  const extra = Object.keys(env).filter((name) => !allowed.includes(name.toLowerCase())).sort();
  if (extra.length > 0) fail(`the migration process has unexpected variables: ${extra.join(', ')}`);
  const { prefix, user } = ROLES.migrator;
  const config = readIntegrationConfig({
    NODE_ENV: env.NODE_ENV, TEST_DB_HOST: env.DB_HOST, TEST_DB_PORT: env.DB_PORT, TEST_DB_NAME: env.DB_NAME,
    [`${prefix}_USER`]: env.DB_USER, [`${prefix}_PASSWORD`]: env.DB_PASSWORD,
  }, 'migrator');
  if (config.user !== user) fail('the migration process must use the migrator account');
  return config;
}

/**
 * Lo que hace migrate-child.js: con su propia conexión, verifica la cuenta de migraciones (identidad,
 * permisos exactos y marca, solo lecturas) ANTES de migrar; ejecuta `migrate` (src/migrate.js, con la
 * misma configuración); y la vuelve a verificar DESPUÉS, con la misma conexión. Si la primera
 * comprobación falla, `migrate` no se llama. La conexión se cierra siempre. src/migrate.js abre otra
 * conexión, distinta de esta: lo que se verifica es la cuenta y su configuración, no esa conexión.
 */
export async function runVerifiedMigration({ env = process.env, mysql, migrate, log = console.log }) {
  const config = readMigrationChildConfig(env);
  const driver = mysql ?? await import('mysql2/promise');
  const connection = await driver.createConnection({ ...config, charset: 'utf8mb4', multipleStatements: false });
  try {
    await verifyQueryable(connection, 'migrator');
    log('migrate-child: migrator verified before migrating');
    await migrate();
    await verifyQueryable(connection, 'migrator');
    log('migrate-child: migrator verified after migrating');
  } finally {
    await connection.end().catch(() => {});
  }
}

/**
 * Ejecuta `body` y después, pase lo que pase, `undo`, que deshace un cambio que hizo la propia prueba.
 * Si `body` falló, ese es el error que se lanza: un fallo de `undo` no lo tapa, solo se comunica a
 * `onUndoFailure`. Si `body` fue bien, el fallo de `undo` es el error.
 */
export async function undoAfter(body, undo, onUndoFailure) {
  let passed = false;
  try {
    const value = await body();
    passed = true;
    return value;
  } finally {
    try {
      await undo();
    } catch (error) {
      if (passed) throw error;
      onUndoFailure(error);
    }
  }
}

/** Solo para las pruebas de estas guardas: olvida lo que puso useAppDatabase(). */
export function resetOwnVariablesForTests() {
  ownServerVariables = null;
  appVerified = false;
  appModulesReady = false;
}
