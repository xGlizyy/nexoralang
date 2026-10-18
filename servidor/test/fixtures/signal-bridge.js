// Solo para pruebas: se carga con `node --import` delante de src/index.js en un proceso hijo.
//
// En Windows, matar un proceso no ejecuta sus manejadores de SIGTERM o SIGINT. Este puente recibe el
// nombre de la señal por el canal IPC y emite ese evento en `process`: se ejecutan los mismos
// manejadores que registra index.js (process.once('SIGTERM', …)), sin señal real del sistema.
// Además avisa por IPC cada vez que el servidor recibe una petición, para que la prueba pueda enviar
// la señal con esa petición todavía en curso, y cuando ya ha emitido la señal (los manejadores
// síncronos, como el comienzo del apagado, ya se han ejecutado). No cambia nada del servidor.

import http from 'node:http';

process.on('message', (message) => {
  if (message !== 'SIGTERM' && message !== 'SIGINT') return;
  process.emit(message, message);
  process.send?.({ signalled: message });
});

const emit = http.Server.prototype.emit;
http.Server.prototype.emit = function emitAndReport(event, ...args) {
  if (event === 'request') process.send?.({ request: args[0].method });
  return emit.call(this, event, ...args);
};
