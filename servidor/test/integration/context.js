// Lo que comparten las pruebas de integración que usan la aplicación: el pool real de src/db.js,
// conectado a nexora_test con el papel «app», y la forma de servir rutas en un puerto libre.
//
// El orden importa: primero se verifica una conexión aparte (guard.js), después se ponen las variables
// DB_* (useAppDatabase) y solo entonces se importa src/, que lee la configuración al cargarse. El pool
// de src/db.js se verifica también, con las mismas comprobaciones, antes de usarlo.

import { connectVerified, useAppDatabase, verifyQueryable } from './guard.js';

let ready = null;

/** { pool } de src/db.js, verificado. Se prepara una sola vez por proceso. */
export function appContext() {
  ready ??= (async () => {
    const check = await connectVerified('app');
    await check.end();
    useAppDatabase();
    const { pool } = await import('../../src/db.js');
    await verifyQueryable(pool, 'app');
    return { pool };
  })();
  return ready;
}

/**
 * Cierra el pool real de src/db.js, como mucho una vez por proceso. Lo llama run.js al terminar las
 * pruebas: sin cerrarlo, sus sockets quedan referenciados, el bucle de eventos no se vacía y el
 * proceso no termina nunca. Si el contexto nunca llegó a iniciarse, o falló al iniciarse, no hay pool
 * que cerrar y no hace nada. Un cierre que sí falla propaga su error: silenciarlo haría parecer limpia
 * una ejecución que no lo está.
 */
export async function closeAppContext() {
  if (ready === null) return;
  const pending = ready;
  ready = null; // a partir de aquí, aunque se llame otra vez, no hay nada que cerrar
  const context = await pending.catch(() => null);
  if (context === null) return;
  await context.pool.end();
}

/** Sirve una aplicación de Express en 127.0.0.1 y un puerto libre (nunca el 3000). */
export async function listen(app) {
  const server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  return { server, base, close: () => new Promise((resolve) => server.close(resolve)) };
}

/** Cuántas filas tiene una de las tablas de la aplicación, opcionalmente con un email. */
export async function count(pool, table, email) {
  if (!['users', 'sessions', 'oauth_accounts'].includes(table)) throw new Error(`not an application table: ${table}`);
  const where = email === undefined ? '' : table === 'users' ? ' WHERE email = ?' : ' WHERE user_id IN (SELECT id FROM `nexora_test`.`users` WHERE email = ?)';
  const [[row]] = await pool.query(`SELECT COUNT(*) AS n FROM \`nexora_test\`.\`${table}\`${where}`, email === undefined ? [] : [email]);
  return Number(row.n);
}
