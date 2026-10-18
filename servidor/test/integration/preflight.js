// Lo primero que se ejecuta en `npm run test:integration`, antes de cargar ninguna prueba: el script lo
// carga con `--import` (que node --test pasa también al proceso de cada archivo), y run.js lo importa
// además en primer lugar, por si alguien lanza run.js de otra forma.
//
//   1. Comprueba que este Node tiene un module.registerHooks que sirve (Node 22.22.3 o posterior en la
//      rama 22, o 24.14.0 o posterior; ver hookSupportProblem en guard.js). Si no, se detiene:
//      las pruebas de integración no se ejecutan en esos Node, aunque el servidor y npm test sí.
//   2. Rechaza un entorno inseguro (checkPreflight en guard.js): sin `npm run test:integration`, con
//      alguna variable DB_*, con el playground activable o con una configuración de pruebas que no sea
//      la autorizada, se detiene aquí, sin haber cargado nada de servidor/src/ ni mysql2.
//   3. Instala un gancho de resolución de módulos que aplica checkModuleLoad a TODO lo que se cargue
//      después: import estático, import() con literal, variable o plantilla, y require (también con
//      createRequire). De servidor/src/ solo se pueden cargar los módulos de APP_MODULES, y solo cuando
//      las guardas lo permiten; mysql2, solo a través de guard.js o de esos módulos.
//
// Límites: protege de errores, no de código escrito para saltárselo. No ve lo que haga un proceso hijo
// (src/migrate.js se lanza aparte, a través de migrate-child.js, que verifica su propia conexión), y si
// run.js se ejecuta sin --import, el gancho llega después de enlazar las importaciones estáticas de
// run.js (que integration-guard.test.js comprueba que no alcanzan src/ ni mysql2).

// Por defecto, y no con nombre: en un Node sin registerHooks, `import { registerHooks }` fallaría al
// enlazar con un error confuso; así se llega a checkHookSupport, que lo explica.
import nodeModule from 'node:module';
import { checkHookSupport, checkModuleLoad, checkPreflight } from './guard.js';

const INSTALLED = Symbol.for('nexora.integration.preflight');

checkHookSupport(nodeModule.registerHooks);
checkPreflight(process.env);

if (globalThis[INSTALLED] !== true) {
  nodeModule.registerHooks({
    resolve(specifier, context, nextResolve) {
      const result = nextResolve(specifier, context);
      checkModuleLoad(result.url, context.parentURL);
      return result;
    },
  });
  globalThis[INSTALLED] = true;
}
