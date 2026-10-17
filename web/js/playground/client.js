// Client of the playground API. It never decides anything about the language: it sends the
// code to the server and classifies what comes back into one of three outcomes.
//
//   { kind: 'result', result }             the runtime answered (the program may still have errors)
//   { kind: 'service', code, message }     the service refused or failed (limit, busy, unavailable)
//   { kind: 'connection' }                 the server could not be reached at all

const RESULT_STATUSES = new Set([
  'success', 'invalid', 'runtime_error', 'contract_violation', 'timeout', 'output_limit', 'memory_limit',
]);

function isResult(body) {
  return typeof body === 'object' && body !== null
    && RESULT_STATUSES.has(body.status)
    && typeof body.output === 'string'
    && Array.isArray(body.diagnostics);
}

const UNEXPECTED = {
  kind: 'service',
  code: 'unexpected_response',
  message: 'The server sent an answer the playground does not understand.',
};

/**
 * @param {{ fetch?: typeof fetch, base?: string }} [options]
 */
export function createClient({ fetch: fetchImpl = globalThis.fetch.bind(globalThis), base = '/api/playground' } = {}) {
  async function request(route, body) {
    let response;
    try {
      response = await fetchImpl(`${base}${route}`, body === undefined ? {} : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch {
      return { kind: 'connection' };
    }
    let payload;
    try {
      payload = await response.json();
    } catch {
      // A proxy error page, for instance: the playground API always answers with JSON.
      return response.ok ? UNEXPECTED : { kind: 'connection' };
    }
    if (payload?.status === 'error' && typeof payload.error?.message === 'string') {
      return { kind: 'service', code: String(payload.error.code), message: payload.error.message };
    }
    return { kind: 'payload', ok: response.ok, payload };
  }

  async function execute(action, code, filename) {
    const answer = await request(`/${action}`, { code, filename });
    if (answer.kind !== 'payload') return answer;
    return answer.ok && isResult(answer.payload) ? { kind: 'result', result: answer.payload } : UNEXPECTED;
  }

  async function read(route, isValid) {
    const answer = await request(route);
    if (answer.kind !== 'payload') return answer;
    return answer.ok && isValid(answer.payload) ? { kind: 'data', data: answer.payload } : UNEXPECTED;
  }

  return {
    run: (code, filename) => execute('run', code, filename),
    check: (code, filename) => execute('check', code, filename),
    status: () => read('/status', (body) => typeof body.enabled === 'boolean'),
    info: () => read('/info', (body) => typeof body.available === 'boolean' && typeof body.limits === 'object'),
    examples: () => read('/examples', (body) => Array.isArray(body.examples)
      && body.examples.every((example) => typeof example.code === 'string' && typeof example.id === 'string')),
  };
}
