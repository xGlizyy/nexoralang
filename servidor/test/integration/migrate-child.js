// El proceso de migraciones de migrations.test.js: se lanza aparte, con el entorno de
// migratorProcessEnv y sin servidor/.env. Antes de cargar src/migrate.js comprueba que su entorno es
// exactamente ese (solo la cuenta de migraciones) y verifica esa cuenta con su propia conexión
// (identidad, permisos exactos y marca, solo lecturas); después de migrar, la vuelve a verificar. Ver
// runVerifiedMigration en guard.js. Si algo no coincide, sale con 1 sin escribir mensajes del servidor.
//
// Límite: src/migrate.js abre su PROPIA conexión, distinta de la que se verifica aquí. Usa la misma
// configuración (las variables DB_* de este proceso, ya comprobadas) y se ejecuta entre las dos
// verificaciones, pero lo que hace esa conexión no se verifica por sí mismo.

import { runVerifiedMigration } from './guard.js';

runVerifiedMigration({ migrate: () => import('../../src/migrate.js') }).catch((error) => {
  console.error(error.name === 'IntegrationGuardError' ? error.message : `migrate-child: failed (${error.name}${typeof error.code === 'string' ? ` ${error.code}` : ''})`);
  process.exitCode = 1;
});
