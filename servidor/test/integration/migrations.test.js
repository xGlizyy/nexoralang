// Migraciones (src/migrate.js y servidor/migraciones) contra nexora_test, con la cuenta de migraciones
// para el esquema y la de la aplicación para las filas. Ver guard.js: nada se ejecuta sin verificar.

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { after, before, describe, test } from 'node:test';
import {
  GUARD_SQL, GUARD_VALUE, assertRunLock, checkGuardRows, connectVerified, existingAppTables, migratorProcessEnv, resetAppTables,
  undoAfter,
} from './guard.js';

const servidor = fileURLToPath(new URL('../../', import.meta.url));

/**
 * Ejecuta src/migrate.js en un proceso aparte, con la cuenta de migraciones y sin servidor/.env, a
 * través de migrate-child.js: verifica la cuenta antes y después de migrar. Solo con el bloqueo de la
 * ejecución todavía tomado (guard.js): el proceso hijo no lo tiene, lo tiene este.
 */
async function migrate() {
  await assertRunLock();
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ['test/integration/migrate-child.js'], { cwd: servidor, env: migratorProcessEnv(), stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

// El esquema que dejan 001_usuarios.sql y 002_oauth.sql. Los tipos se normalizan para que valga igual
// en MySQL 8 (bigint unsigned, CURRENT_TIMESTAMP) y en MariaDB (bigint(20) unsigned, current_timestamp()).
const EXPECTED = {
  tables: {
    oauth_accounts: { engine: 'InnoDB', collation: 'utf8mb4_unicode_ci' },
    sessions: { engine: 'InnoDB', collation: 'utf8mb4_unicode_ci' },
    users: { engine: 'InnoDB', collation: 'utf8mb4_unicode_ci' },
  },
  columns: [
    'oauth_accounts.provider varchar(20) NOT NULL',
    'oauth_accounts.provider_user_id varchar(64) NOT NULL',
    'oauth_accounts.user_id bigint unsigned NOT NULL',
    'oauth_accounts.created_at timestamp NOT NULL default current_timestamp',
    'sessions.token_hash binary(32) NOT NULL',
    'sessions.user_id bigint unsigned NOT NULL',
    'sessions.created_at timestamp NOT NULL default current_timestamp',
    'sessions.expires_at datetime NOT NULL',
    'users.id bigint unsigned NOT NULL',
    'users.name varchar(80) NOT NULL',
    'users.email varchar(254) NOT NULL',
    'users.password_hash varchar(255) NULL',
    'users.created_at timestamp NOT NULL default current_timestamp',
  ],
  indexes: [
    'oauth_accounts.PRIMARY unique (provider, provider_user_id)',
    'oauth_accounts.idx_oauth_accounts_user (user_id)',
    'sessions.PRIMARY unique (token_hash)',
    'sessions.idx_sessions_expires (expires_at)',
    'sessions.idx_sessions_user (user_id)',
    'users.PRIMARY unique (id)',
    'users.uq_users_email unique (email)',
  ],
  foreignKeys: [
    'oauth_accounts.fk_oauth_accounts_user (user_id) -> users (id) ON DELETE CASCADE',
    'sessions.fk_sessions_user (user_id) -> users (id) ON DELETE CASCADE',
  ],
};

const normalType = (type) => type.toLowerCase().replace(/\b(bigint|int)\(\d+\)/, '$1');
const normalDefault = (value) => (value === null || value === 'NULL' ? null : String(value).toLowerCase().replace(/\(\)$/, ''));

/**
 * El esquema real de las tablas de la aplicación, en la misma forma que EXPECTED. `foreignConnection`
 * lee las claves ajenas: en MariaDB, REFERENTIAL_CONSTRAINTS no devuelve filas a la cuenta de
 * migraciones, con permisos solo de tabla (medido en 10.11.19); la de la aplicación sí las ve.
 */
async function schema(connection, foreignConnection = connection) {
  const [tables] = await connection.query(
    "SELECT TABLE_NAME AS t, ENGINE AS engine, TABLE_COLLATION AS collation FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'nexora_test' AND TABLE_NAME IN ('users', 'sessions', 'oauth_accounts') ORDER BY TABLE_NAME",
  );
  const [columns] = await connection.query(
    "SELECT TABLE_NAME AS t, COLUMN_NAME AS c, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_DEFAULT AS def FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'nexora_test' AND TABLE_NAME IN ('users', 'sessions', 'oauth_accounts') ORDER BY TABLE_NAME, ORDINAL_POSITION",
  );
  const [indexes] = await connection.query(
    "SELECT TABLE_NAME AS t, INDEX_NAME AS i, NON_UNIQUE AS nonUnique, COLUMN_NAME AS c FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = 'nexora_test' AND TABLE_NAME IN ('users', 'sessions', 'oauth_accounts') ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
  );
  const [foreign] = await foreignConnection.query(
    "SELECT k.TABLE_NAME AS t, k.CONSTRAINT_NAME AS name, k.COLUMN_NAME AS c, k.REFERENCED_TABLE_NAME AS rt, k.REFERENCED_COLUMN_NAME AS rc, r.DELETE_RULE AS onDelete FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA = 'nexora_test' AND k.REFERENCED_TABLE_NAME IS NOT NULL ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME",
  );
  const grouped = new Map();
  for (const row of indexes) {
    const key = `${row.t}.${row.i}`;
    const entry = grouped.get(key) ?? { unique: Number(row.nonUnique) === 0, columns: [] };
    entry.columns.push(row.c);
    grouped.set(key, entry);
  }
  // La vista REFERENTIAL_CONSTRAINTS (la única con DELETE_RULE) no devolvió filas a la cuenta de
  // migraciones en MariaDB 10.11.19 (solo tiene permisos de tabla): sin esta comprobación, el fallo se
  // leería como dos claves ajenas «missing», sin decir por qué.
  if (foreign.length === 0) {
    throw new Error('nexora_test: the foreign-key query returned no rows: check whether the account reading the schema can see information_schema.REFERENTIAL_CONSTRAINTS');
  }
  const foreignKeys = foreign.map((row) => {
    if (typeof row.onDelete !== 'string' || row.onDelete === '') {
      throw new Error(`nexora_test: ${row.t}.${row.name} came back without a DELETE_RULE: the connection that read REFERENTIAL_CONSTRAINTS cannot see it`);
    }
    return `${row.t}.${row.name} (${row.c}) -> ${row.rt} (${row.rc}) ON DELETE ${row.onDelete}`;
  });
  return {
    tables: Object.fromEntries(tables.map((row) => [row.t, { engine: row.engine, collation: row.collation }])),
    columns: columns.map((row) => `${row.t}.${row.c} ${normalType(row.type)} ${row.nullable === 'YES' ? 'NULL' : 'NOT NULL'}${normalDefault(row.def) ? ` default ${normalDefault(row.def)}` : ''}`),
    indexes: [...grouped].map(([key, { unique, columns: cols }]) => `${key}${unique ? ' unique' : ''} (${cols.join(', ')})`).sort(),
    foreignKeys,
  };
}

// El cambio a mano de la prueba de esquema desviado y lo que lo deshace: la misma columna, nada más.
const DRIFT_SQL = 'ALTER TABLE `nexora_test`.`users` MODIFY name VARCHAR(40) NOT NULL';
const UNDO_DRIFT_SQL = 'ALTER TABLE `nexora_test`.`users` MODIFY name VARCHAR(80) NOT NULL';

/** Las diferencias entre el esquema real y el esperado: vacío si coinciden. */
function drift(actual, expected = EXPECTED) {
  const differences = [];
  for (const part of ['columns', 'indexes', 'foreignKeys']) {
    for (const item of expected[part]) if (!actual[part].includes(item)) differences.push(`missing ${item}`);
    for (const item of actual[part]) if (!expected[part].includes(item)) differences.push(`unexpected ${item}`);
  }
  for (const [table, info] of Object.entries(expected.tables)) {
    if (JSON.stringify(actual.tables[table]) !== JSON.stringify(info)) differences.push(`table ${table}: ${JSON.stringify(actual.tables[table])}`);
  }
  return differences;
}

describe('migrations on nexora_test', () => {
  let migrator;
  let app;
  before(async () => {
    migrator = await connectVerified('migrator');
    app = await connectVerified('app');
  });
  after(async () => {
    await migrator?.end();
    await app?.end();
  });

  test('on a database without the application tables, they create exactly the expected schema', async (t) => {
    // Ninguna cuenta de pruebas puede borrar tablas: esta prueba solo es posible con nexora_test vacía
    // (recién creada, o vaciada por un administrador con prepare-fresh-schema-admin.sql).
    const existing = await existingAppTables(migrator);
    if (existing.length === 3) {
      t.skip('OMITTED: the application tables already exist in nexora_test, so this is not a fresh schema. To run it, an administrator first runs test/integration/prepare-fresh-schema-admin.sql (see testing.md).');
      return;
    }
    assert.deepEqual(existing, [], `only some application tables exist (${existing.join(', ')}): nexora_test is half migrated; ask an administrator to run prepare-fresh-schema-admin.sql`);
    const result = await migrate();
    assert.equal(result.code, 0, result.stderr);
    assert.match(result.stdout, /migrate-child: migrator verified before migrating\nAplicada: 001_usuarios\.sql\nAplicada: 002_oauth\.sql\nmigrate-child: migrator verified after migrating/);
    assert.deepEqual(drift(await schema(migrator, app)), []);
    // La marca sigue ahí, intacta.
    const [guard] = await migrator.query(GUARD_SQL);
    checkGuardRows(guard);
  });

  test('running them again changes no table and keeps every row', async () => {
    await resetAppTables(app);
    await app.query("INSERT INTO `nexora_test`.`users` (name, email, password_hash) VALUES ('Ana', 'ana@example.test', NULL)");
    const [[user]] = await app.query("SELECT id FROM `nexora_test`.`users` WHERE email = 'ana@example.test'");
    await app.query("INSERT INTO `nexora_test`.`sessions` (token_hash, user_id, expires_at) VALUES (UNHEX(SHA2('t', 256)), ?, NOW() + INTERVAL 1 DAY)", [user.id]);
    await app.query("INSERT INTO `nexora_test`.`oauth_accounts` (provider, provider_user_id, user_id) VALUES ('github', '1', ?)", [user.id]);
    const before = await schema(migrator, app);
    // Si se omitió la prueba de esquema nuevo, esta es la que comprueba el esquema que ya había.
    assert.deepEqual(drift(before), []);
    for (let i = 0; i < 2; i++) {
      const result = await migrate();
      assert.equal(result.code, 0, result.stderr);
    }
    assert.deepEqual(await schema(migrator, app), before);
    for (const table of ['users', 'sessions', 'oauth_accounts']) {
      const [[row]] = await app.query(`SELECT COUNT(*) AS n FROM \`nexora_test\`.\`${table}\``);
      assert.equal(Number(row.n), 1, table);
    }
    await resetAppTables(app);
  });

  test('a drifted schema is NOT repaired by the migrations; only the schema check notices it', async (t) => {
    // CREATE TABLE IF NOT EXISTS no mira lo que ya existe: una columna cambiada a mano sigue cambiada.
    await migrator.query(DRIFT_SQL);
    // Desde aquí, users.name se deja como estaba pase lo que pase (aunque fallen migrate() o una
    // aserción), con ALTER y sin borrar nada: solo se deshace el cambio de esta prueba. Si deshacerlo
    // falla, no tapa el error original (ver undoAfter en guard.js).
    await undoAfter(
      async () => {
        const result = await migrate();
        assert.equal(result.code, 0, result.stderr);
        assert.deepEqual(drift(await schema(migrator, app)), ['missing users.name varchar(80) NOT NULL', 'unexpected users.name varchar(40) NOT NULL']);
      },
      () => migrator.query(UNDO_DRIFT_SQL),
      (error) => t.diagnostic(`users.name could not be restored (${error.code ?? error.name}): an administrator must run prepare-fresh-schema-admin.sql`),
    );
    assert.deepEqual(drift(await schema(migrator, app)), []);
  });

  test('the migration account cannot read or delete rows, create other tables or reach other databases', async () => {
    for (const sql of [
      'SELECT * FROM `nexora_test`.`users`',
      'DELETE FROM `nexora_test`.`sessions`',
      'CREATE TABLE `nexora_test`.`x` (id INT)',
      'SELECT 1 FROM `mysql`.`user`',
    ]) {
      await assert.rejects(migrator.query(sql), (error) => /ACCESS_DENIED/.test(error.code), sql);
    }
  });

  test('neither account can write in the guard marker', async () => {
    // Se intenta insertar el MISMO valor que ya tiene: con un permiso de más, el servidor respondería
    // ER_DUP_ENTRY y la marca seguiría igual. Lo esperado es que ni lo intente: acceso denegado.
    for (const connection of [migrator, app]) {
      await assert.rejects(
        connection.query('INSERT INTO `nexora_test_guard`.`marker` (purpose) VALUES (?)', [GUARD_VALUE]),
        (error) => /ACCESS_DENIED/.test(error.code),
      );
    }
    const [guard] = await app.query(GUARD_SQL);
    checkGuardRows(guard);
  });

  test('the application account cannot change the schema or reach another database', async () => {
    for (const sql of [
      'CREATE TABLE `nexora_test`.`x` (id INT)',
      'ALTER TABLE `nexora_test`.`users` ADD COLUMN x INT',
      'UPDATE `nexora_test`.`users` SET name = name',
      'SELECT 1 FROM `mysql`.`user`',
      'CREATE DATABASE nexora_test_other',
    ]) {
      await assert.rejects(app.query(sql), (error) => /ACCESS_DENIED/.test(error.code), sql);
    }
  });
});
