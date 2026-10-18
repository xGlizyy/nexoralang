-- Base de datos y cuentas SOLO para las pruebas de integración de NEXORA (servidor/test/integration).
--
-- PROPUESTA PARA REVISIÓN: este archivo no lo ejecuta ninguna prueba ni ningún script. Lo ejecuta, a
-- mano, una persona con permisos de administración, en el servidor de PRUEBAS. Nunca en producción.
--
-- Antes de ejecutarlo:
--   1. Sustituye <CONTRASEÑA_MIGRACIONES_SOLO_PRUEBAS> y <CONTRASEÑA_APLICACION_SOLO_PRUEBAS> por dos
--      contraseñas aleatorias nuevas, distintas entre sí y que no se usen en ningún otro sitio.
--   2. Comprueba que nexora_test y nexora_test_guard no existen: CREATE DATABASE falla a propósito.
--
-- Dos esquemas:
--   nexora_test         las tablas de la aplicación (las crean las migraciones).
--   nexora_test_guard   solo la marca que las pruebas exigen antes de hacer nada. Ninguna cuenta de
--                       pruebas puede escribir en él.
--
-- Dos cuentas, solo desde 127.0.0.1:
--   nexora_test_migrator  ejecuta las migraciones: crea y modifica las tres tablas de la aplicación.
--                         Sus permisos son de TABLA, sobre esas tres, y sin DROP: no puede borrarlas,
--                         crear otras tablas ni borrar la base. Para repetir la prueba de esquema
--                         nuevo, un administrador vacía antes nexora_test con
--                         prepare-fresh-schema-admin.sql.
--   nexora_test_app       lo que hace la aplicación: leer, insertar y borrar filas. Sin DDL ni DROP.
-- Ninguna tiene permisos globales, GRANT OPTION, FILE, PROCESS, SUPER ni acceso a otras bases.

CREATE DATABASE nexora_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE nexora_test_guard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE nexora_test_guard.marker (
  purpose VARCHAR(64) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO nexora_test_guard.marker (purpose) VALUES ('nexora-integration-tests-only');

CREATE USER 'nexora_test_migrator'@'127.0.0.1'
  IDENTIFIED BY '<CONTRASEÑA_MIGRACIONES_SOLO_PRUEBAS>'
  WITH MAX_USER_CONNECTIONS 5;

CREATE USER 'nexora_test_app'@'127.0.0.1'
  IDENTIFIED BY '<CONTRASEÑA_APLICACION_SOLO_PRUEBAS>'
  WITH MAX_USER_CONNECTIONS 30;

-- Migraciones, tabla a tabla. Las tablas todavía no existen: MySQL documenta que se pueden conceder
-- permisos sobre una tabla que no existe si incluyen CREATE (aquí lo incluyen). En MariaDB está
-- PENDIENTE DE VERIFICAR; si se negara, el administrador tendría que crear antes las tres tablas
-- (ejecutando las migraciones con su propia cuenta) y conceder después estos permisos.
--   CREATE      CREATE TABLE IF NOT EXISTS (001_usuarios.sql, 002_oauth.sql)
--   ALTER       ALTER TABLE users MODIFY ... (002_oauth.sql)
--   INSERT      también lo exige ALTER TABLE, según la documentación de MySQL y de MariaDB (puede copiar
--               las filas). Las pruebas no insertan filas con esta cuenta.
--   REFERENCES  claves ajenas de sessions y oauth_accounts a users (MySQL 8 lo exige sobre la tabla madre)
-- Sin DROP. En un permiso de tabla el nombre de la base es literal: aquí «_» no es un comodín.
GRANT CREATE, ALTER, INSERT, REFERENCES ON nexora_test.users          TO 'nexora_test_migrator'@'127.0.0.1';
GRANT CREATE, ALTER, INSERT, REFERENCES ON nexora_test.sessions       TO 'nexora_test_migrator'@'127.0.0.1';
GRANT CREATE, ALTER, INSERT, REFERENCES ON nexora_test.oauth_accounts TO 'nexora_test_migrator'@'127.0.0.1';
GRANT SELECT ON nexora_test_guard.marker TO 'nexora_test_migrator'@'127.0.0.1';

-- Aplicación: las consultas reales (src/auth.js, src/sessions.js, src/oauth.js, src/session-cleanup.js)
-- solo usan SELECT, INSERT y DELETE. DELETE es además el permiso que MySQL 8 exige, junto con SELECT,
-- para SELECT ... FOR UPDATE (oauth.js). Sin UPDATE: el código no lo usa. Sobre la base entera porque
-- las tablas las crean después las migraciones; la marca está en otro esquema y aquí solo se lee.
-- En un permiso sobre una base entera, «_» es un comodín («cualquier carácter»): sin escapar,
-- nexora_test.* daría también acceso a nexoraXtest o nexora-test. Por eso va escapado, \_, y entre
-- comillas invertidas. Las pruebas exigen esta forma exacta en SHOW GRANTS.
GRANT SELECT, INSERT, DELETE ON `nexora\_test`.* TO 'nexora_test_app'@'127.0.0.1';
GRANT SELECT ON nexora_test_guard.marker TO 'nexora_test_app'@'127.0.0.1';

-- Comprobaciones, de solo lectura. SHOW GRANTS puede incluir el resumen de la contraseña en MariaDB:
-- no copies su salida en informes ni en el chat.
SHOW GRANTS FOR 'nexora_test_migrator'@'127.0.0.1';
SHOW GRANTS FOR 'nexora_test_app'@'127.0.0.1';
-- No debe devolver ninguna fila: un usuario anónimo podría ganar a estas cuentas al identificar la conexión.
SELECT user, host FROM mysql.user WHERE user = '';

-- Para deshacerlo todo (también solo a mano, cuando se decida):
--   DROP USER 'nexora_test_migrator'@'127.0.0.1', 'nexora_test_app'@'127.0.0.1';
--   DROP DATABASE nexora_test;
--   DROP DATABASE nexora_test_guard;
