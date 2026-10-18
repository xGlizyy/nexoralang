// Para integration-guard.test.js: simula un Node sin module.registerHooks (Node 20.6–22.14) antes de
// cargar preflight.js con otro --import. Es una simulación en el Node actual, no una prueba en Node 20.
import nodeModule from 'node:module';

nodeModule.registerHooks = undefined;
