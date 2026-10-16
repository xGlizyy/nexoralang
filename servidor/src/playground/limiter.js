// Limita cuántos workers hay a la vez. Lo que no cabe espera en una cola corta; si la cola
// también está llena, se rechaza enseguida en vez de acumular trabajo sin límite.

export class BusyError extends Error {
  constructor() {
    super('The playground is busy.');
  }
}

export class Limiter {
  #running = 0;
  #waiting = [];

  constructor(maxConcurrent, maxQueue) {
    this.maxConcurrent = maxConcurrent;
    this.maxQueue = maxQueue;
  }

  get running() { return this.#running; }
  get waiting() { return this.#waiting.length; }

  /**
   * Espera un hueco y devuelve la función que lo libera. Lanza BusyError si no cabe ni en la cola.
   * El hueco se libera cuando el worker ha terminado de verdad, que puede ser después de responder.
   * Llamar a la función más de una vez no tiene efecto.
   */
  async acquire() {
    if (this.#running >= this.maxConcurrent) {
      if (this.#waiting.length >= this.maxQueue) throw new BusyError();
      await new Promise((resolve) => this.#waiting.push(resolve));
    } else {
      this.#running += 1;
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      // El hueco pasa directamente al siguiente en espera, sin quedar libre entre medias.
      const next = this.#waiting.shift();
      if (next) next();
      else this.#running -= 1;
    };
  }
}
