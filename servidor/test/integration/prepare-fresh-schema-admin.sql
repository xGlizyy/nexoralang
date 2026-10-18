-- Preparar una prueba de ESQUEMA NUEVO en nexora_test (servidor/test/integration/migrations.test.js).
--
-- PROPUESTA PARA REVISIÓN: este archivo no lo ejecuta ninguna prueba ni ningún script. Ninguna cuenta
-- de pruebas tiene DROP: la prueba de esquema nuevo solo se ejecuta si las tres tablas de la
-- aplicación no existen (la primera vez, con la base recién creada) y, si existen, se omite y lo dice.
-- Para repetirla, una persona con permisos de administración ejecuta esto a mano, en el servidor de
-- PRUEBAS, nunca en producción. Borra los datos de prueba de esas tres tablas y nada más: ni la base
-- nexora_test, ni el esquema nexora_test_guard, ni las cuentas, ni sus permisos (los permisos de
-- tabla no se pierden al borrar la tabla).
--
-- Cómo ejecutarlo:
--   1. Revisa el destino ANTES de nada: el servidor (host y puerto) al que conecta tu cliente y la
--      cuenta con la que lo haces. Tiene que ser el servidor de pruebas.
--   2. Usa el cliente de línea de órdenes de MySQL o MariaDB SIN --force (ni opciones equivalentes de
--      otras herramientas, como «continuar ante errores»): así se detiene en el primer error. Si
--      nexora_test_guard.marker no existe, la consulta de abajo falla y los DROP no llegan a ejecutarse.
--   3. La consulta de la marca es una comprobación MANUAL: este archivo no la evalúa ni se detiene solo
--      si devuelve otra cosa. Mira su resultado: tiene que ser exactamente UNA fila con el valor
--      'nexora-integration-tests-only'. Si ves cualquier otra cosa (ninguna fila, varias, otro valor o
--      un error), detente y no ejecutes nada más. Lo más seguro es ejecutar primero solo esta consulta,
--      revisar la respuesta y, después, el resto del archivo.
SELECT purpose FROM nexora_test_guard.marker;

-- De hijas a madres, por las claves ajenas.
DROP TABLE IF EXISTS nexora_test.oauth_accounts;
DROP TABLE IF EXISTS nexora_test.sessions;
DROP TABLE IF EXISTS nexora_test.users;

-- Comprobación: no debe devolver ninguna fila.
SELECT TABLE_NAME FROM information_schema.TABLES
 WHERE TABLE_SCHEMA = 'nexora_test' AND TABLE_NAME IN ('users', 'sessions', 'oauth_accounts');
