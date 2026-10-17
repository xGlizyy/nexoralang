// Rutas /api/playground: comprobar y ejecutar código NEXORA con el intérprete real.
//
// Esta capa solo hace transporte: valida la petición, aplica los límites del servicio y
// entrega el código al worker. Las reglas del lenguaje y los diagnósticos vienen del núcleo.
// El esquema de peticiones y respuestas está documentado en nexora/docs/playground.md.

import express from 'express';
import { clientRateLimit } from '../rate-limits.js';
import { loadExamples } from './examples.js';
import { BusyError, Limiter } from './limiter.js';
import { RESULT_SCHEMA, WorkerError, runWorker } from './worker.js';

const FILENAME = /^[A-Za-z0-9_-]{1,64}\.nex$/;
const DEFAULT_FILENAME = 'playground.nex';

/** Error de la petición o del servicio (no del programa). Se convierte en una respuesta JSON. */
class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function errorBody(code, message) {
  return { schema: RESULT_SCHEMA, status: 'error', error: { code, message } };
}

/** Valida el cuerpo de la petición y devuelve { code, filename }. */
export function parseRequest(body, maxCodeBytes) {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    throw new ApiError(400, 'invalid_request', 'The request body must be a JSON object.');
  }
  if (body.code === undefined) {
    throw new ApiError(400, 'missing_code', 'The request must include the "code" field.');
  }
  if (typeof body.code !== 'string') {
    throw new ApiError(400, 'invalid_code_type', 'The "code" field must be a string.');
  }
  if (Buffer.byteLength(body.code, 'utf8') > maxCodeBytes) {
    throw new ApiError(413, 'code_too_large', `The program is larger than the limit of ${maxCodeBytes} bytes.`);
  }
  const filename = body.filename === undefined ? DEFAULT_FILENAME : body.filename;
  // Es un nombre virtual: solo aparece en los diagnósticos. Aun así se restringe a un nombre
  // simple, para que nunca pueda parecerse a una ruta.
  if (typeof filename !== 'string' || !FILENAME.test(filename)) {
    throw new ApiError(400, 'invalid_filename', 'The "filename" field must be a simple name ending in .nex.');
  }
  return { code: body.code, filename };
}

/**
 * @param {ReturnType<import('./config.js').loadPlaygroundConfig>} config
 * @param {{ log?: (message: string) => void }} [options]
 */
export function createPlaygroundRouter(config, { log = console.error } = {}) {
  const router = express.Router();
  const limiter = new Limiter(config.maxConcurrent, config.maxQueue);
  const examples = loadExamples(config.examplesDir);
  // La respuesta del worker contiene la salida (hasta maxOutputBytes) y los diagnósticos.
  const maxResponseBytes = config.maxOutputBytes * 6 + 512 * 1024;
  let info = null;

  const limits = {
    output_bytes: config.maxOutputBytes,
    text_chars: config.maxTextChars,
    memory_bytes: config.memoryBytes,
    cpu_seconds: Math.ceil(config.timeoutMs / 1000) + 1,
    wall_seconds: Math.ceil(config.timeoutMs / 1000) + 2,
  };
  const publicLimits = {
    code_bytes: config.maxCodeBytes,
    timeout_ms: config.timeoutMs,
    output_bytes: config.maxOutputBytes,
    text_chars: config.maxTextChars,
  };

  // El hueco se libera cuando el worker ha terminado de verdad, no cuando responde: un contenedor
  // puede seguir vivo después de que su cliente `docker run` haya muerto (ver worker.js).
  const worker = async (request, timeoutMs = config.timeoutMs) => {
    const release = await limiter.acquire();
    let answer;
    try {
      answer = runWorker(config.workerCommand, request, {
        timeoutMs, maxResponseBytes, onFinished: release, containerStop: config.containerStop, log,
      });
    } catch (error) {
      // Una excepción síncrona significa que no se lanzó ningún worker: el hueco queda libre.
      release();
      throw error;
    }
    return answer;
  };

  // Solo se aceptan peticiones del propio sitio (o de los orígenes configurados). Un navegador
  // envía la cabecera Origin en las peticiones entre sitios; si no coincide, se rechaza.
  router.use((req, res, next) => {
    const origin = req.headers.origin;
    if (!origin) return next();
    let sameOrigin = false;
    try {
      sameOrigin = new URL(origin).host === req.headers.host;
    } catch {
      sameOrigin = false;
    }
    if (sameOrigin) return next();
    if (config.allowedOrigins.includes(origin)) {
      res.set('Access-Control-Allow-Origin', origin);
      res.set('Vary', 'Origin');
      if (req.method === 'OPTIONS') {
        res.set('Access-Control-Allow-Methods', 'GET, POST');
        res.set('Access-Control-Allow-Headers', 'Content-Type');
        return res.status(204).end();
      }
      return next();
    }
    next(new ApiError(403, 'origin_not_allowed', 'This origin is not allowed to use the playground.'));
  });

  router.use((req, res, next) => {
    res.set('Cache-Control', 'no-store');
    res.set('X-Content-Type-Options', 'nosniff');
    next();
  });

  // Si el playground está activado. La página lo pregunta antes que nada: desactivado, no pide
  // /info ni /examples y lo dice en vez de ofrecer Run y Check. No arranca el worker.
  router.get('/status', (req, res) => {
    res.json({ schema: RESULT_SCHEMA, status: 'success', enabled: config.enabled });
  });

  router.use((req, res, next) => {
    if (!config.enabled) {
      return next(new ApiError(503, 'playground_disabled', 'The playground is disabled on this server.'));
    }
    next();
  });

  router.get('/info', async (req, res) => {
    // Lo que el editor necesita saber del lenguaje, preguntado al propio núcleo (una vez).
    if (!info) {
      try {
        const answer = await worker({ action: 'info' }, Math.max(config.timeoutMs, 10_000));
        info = {
          version: answer.version,
          language: {
            keywords: answer.keywords,
            reserved_words: answer.reserved_words,
            types: answer.types,
            builtins: answer.builtins,
          },
        };
      } catch (error) {
        log(`playground: runtime not available (${error.kind ?? error.name})`);
      }
    }
    res.json({
      schema: RESULT_SCHEMA,
      status: 'success',
      available: info !== null,
      version: info?.version ?? null,
      language: info?.language ?? null,
      limits: publicLimits,
    });
  });

  router.get('/examples', (req, res) => {
    res.json({ schema: RESULT_SCHEMA, status: 'success', examples });
  });

  // Por cliente y por red IPv6 /48 (rate-limits.js).
  const requests = clientRateLimit({
    windowMs: config.rateLimit.windowMs,
    limit: config.rateLimit.limit,
    handler: (req, res) => {
      res.status(429).json(errorBody('rate_limited', 'Too many requests. Wait a moment and try again.'));
    },
  });

  // El JSON escapa algunos caracteres, así que el cuerpo puede ocupar más que el programa.
  const json = express.json({ limit: config.maxCodeBytes * 6 + 1024, type: 'application/json' });

  for (const action of ['check', 'run']) {
    router.post(`/${action}`, requests, json, async (req, res) => {
      if (!req.is('application/json')) {
        throw new ApiError(415, 'unsupported_media_type', 'Send the request as application/json.');
      }
      const { code, filename } = parseRequest(req.body, config.maxCodeBytes);
      const started = performance.now();
      let result;
      try {
        result = await worker({ action, code, filename, limits });
      } catch (error) {
        if (error instanceof WorkerError && error.kind === 'timeout') {
          // Agotar el tiempo es un resultado del programa, no un fallo del servicio.
          result = {
            schema: RESULT_SCHEMA,
            action,
            status: 'timeout',
            output: '',
            diagnostics: [],
            message: `The program ran for more than ${config.timeoutMs} ms and was stopped.`,
            version: info?.version ?? null,
          };
        } else {
          throw error;
        }
      }
      // Duración vista desde el servidor: incluye arrancar el worker.
      result.duration_ms = Math.round(performance.now() - started);
      res.json(result);
    });
  }

  router.use((req, res) => {
    res.status(404).json(errorBody('not_found', 'Route not found.'));
  });

  // Todos los errores de estas rutas salen con el mismo esquema, sin detalles internos.
  router.use((error, req, res, next) => { // eslint-disable-line no-unused-vars
    if (error instanceof ApiError) {
      return res.status(error.status).json(errorBody(error.code, error.message));
    }
    if (error.type === 'entity.too.large') {
      return res.status(413).json(errorBody('code_too_large', `The program is larger than the limit of ${config.maxCodeBytes} bytes.`));
    }
    if (error.type === 'entity.parse.failed' || error.type === 'charset.unsupported' || error.type === 'encoding.unsupported') {
      return res.status(400).json(errorBody('invalid_json', 'The request body is not valid JSON.'));
    }
    if (error instanceof BusyError) {
      res.set('Retry-After', '2');
      return res.status(503).json(errorBody('busy', 'The playground is busy. Try again in a few seconds.'));
    }
    if (error instanceof WorkerError) {
      // Se registra el tipo de fallo, nunca el código enviado.
      log(`playground: worker ${error.kind}`);
      return res.status(503).json(errorBody('runtime_unavailable', 'The NEXORA runtime is not available right now.'));
    }
    log(`playground: internal error (${error.name})`);
    res.status(500).json(errorBody('internal_error', 'The playground failed to process the request.'));
  });

  return router;
}
