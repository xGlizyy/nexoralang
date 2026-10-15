// API del playground, de extremo a extremo: peticiones HTTP reales contra el intérprete real.

import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { examplesDir, fakeWorker, HELLO, inMain, SLOW, startServer, testConfig } from './helpers.js';

const RESULT_FIELDS = ['schema', 'action', 'status', 'output', 'diagnostics', 'message', 'duration_ms', 'version'];
const DIAGNOSTIC_FIELDS = [
  'severity', 'category', 'code', 'message', 'label', 'hint', 'notes', 'file', 'line', 'column', 'end_line', 'end_column',
];
const python = testConfig().workerCommand[0];

function assertResult(response, action, status) {
  assert.equal(response.status, 200, response.text);
  assert.match(response.headers.get('content-type'), /^application\/json/);
  assert.deepEqual(Object.keys(response.json).sort(), [...RESULT_FIELDS].sort());
  assert.equal(response.json.schema, 'nexora.result/1');
  assert.equal(response.json.action, action);
  assert.equal(response.json.status, status);
  assert.equal(typeof response.json.output, 'string');
  assert.ok(Number.isInteger(response.json.duration_ms) && response.json.duration_ms >= 0);
  for (const diagnostic of response.json.diagnostics) {
    assert.deepEqual(Object.keys(diagnostic), DIAGNOSTIC_FIELDS);
  }
}

function assertError(response, httpStatus, code) {
  assert.equal(response.status, httpStatus, response.text);
  assert.deepEqual(Object.keys(response.json), ['schema', 'status', 'error']);
  assert.equal(response.json.status, 'error');
  assert.equal(response.json.error.code, code);
  assert.equal(typeof response.json.error.message, 'string');
  // Nada interno en una respuesta pública.
  assert.doesNotMatch(response.text, /Traceback|\.py|\.js:|node_modules|[A-Z]:\\|\/home\/|\/usr\//);
}

describe('programs', () => {
  let server;
  before(async () => { server = await startServer(); });
  after(() => server.close());

  test('run executes a valid program with the real interpreter', async () => {
    const response = await server.run(HELLO);
    assertResult(response, 'run', 'success');
    assert.equal(response.json.output, 'Hello from NEXORA\n');
    assert.deepEqual(response.json.diagnostics, []);
    assert.match(response.json.version, /^\d+\.\d+\.\d+$/);
  });

  test('the output is computed, not canned', async () => {
    const response = await server.run(inMain('let a = 1234\nlet b = 5678\nprint(a * b + 1)\nprint(to_text(a) + "-" + to_text(b))'));
    assert.equal(response.json.output, '7006653\n1234-5678\n');
  });

  test('check validates without running', async () => {
    const response = await server.check(inMain('print("SIDE EFFECT")\nprint(1 / 0)'));
    assertResult(response, 'check', 'success');
    assert.equal(response.json.output, '');
    assert.deepEqual(response.json.diagnostics, []);
  });

  test('syntax error', async () => {
    const response = await server.run(inMain('print("must not appear")\nlet = 1'));
    assertResult(response, 'run', 'invalid');
    assert.equal(response.json.output, '');
    const [diagnostic] = response.json.diagnostics;
    assert.deepEqual(
      [diagnostic.category, diagnostic.code, diagnostic.line, diagnostic.column, diagnostic.file],
      ['syntax', 'E1101', 3, 9, 'playground.nex'],
    );
  });

  test('type error, with the location of the value', async () => {
    const response = await server.check(inMain('let age: Int = "twenty"'));
    assertResult(response, 'check', 'invalid');
    const [diagnostic] = response.json.diagnostics;
    assert.deepEqual(
      [diagnostic.category, diagnostic.code, diagnostic.label, diagnostic.line, diagnostic.column, diagnostic.end_column],
      ['type', 'E2011', 'Expected Int, found Text', 2, 20, 28],
    );
  });

  test('runtime error keeps the output printed before it', async () => {
    const response = await server.run(inMain('print("before")\nprint(10 / (5 - 5))\nprint("after")'));
    assertResult(response, 'run', 'runtime_error');
    assert.equal(response.json.output, 'before\n');
    assert.deepEqual([response.json.diagnostics[0].code, response.json.diagnostics[0].line], ['E3001', 3]);
  });

  test('contract violation', async () => {
    const program = `fn half(n: Int) -> Int {\n    requires n > 0\n    return n / 2\n}\n${inMain('print(half(0))')}`;
    const response = await server.run(program);
    assertResult(response, 'run', 'contract_violation');
    assert.equal(response.json.diagnostics[0].code, 'E4001');
  });

  test('the virtual file name is used in diagnostics', async () => {
    const response = await server.check(inMain('print(x)'), { filename: 'hello.nex' });
    assert.equal(response.json.diagnostics[0].file, 'hello.nex');
  });

  test('program output is returned as data, never as markup', async () => {
    const payload = '<script>alert(1)</script><img src=x onerror=alert(2)>';
    const response = await server.run(inMain(`print("${payload}")`));
    assert.equal(response.json.output, `${payload}\n`);
    assert.match(response.headers.get('content-type'), /^application\/json/);
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(response.headers.get('cache-control'), 'no-store');
  });

  test('non-ASCII text survives the round trip', async () => {
    const response = await server.run(inMain('print("año ✓ 日本")'));
    assert.equal(response.json.output, 'año ✓ 日本\n');
  });

  test('one failing program does not affect the next one', async () => {
    assert.equal((await server.run(inMain('print(1 / 0)'))).json.status, 'runtime_error');
    assert.equal((await server.run('not a program at all {{{')).json.status, 'invalid');
    assert.equal((await server.run(HELLO)).json.output, 'Hello from NEXORA\n');
  });
});

describe('request validation', () => {
  let server;
  before(async () => { server = await startServer({ maxCodeBytes: 1000 }); });
  after(() => server.close());

  test('malformed JSON', async () => {
    assertError(await server.call('/run', undefined, { raw: '{"code": ' }), 400, 'invalid_json');
    assertError(await server.call('/check', undefined, { raw: 'fn main() -> Void {}' }), 400, 'invalid_json');
  });

  test('body that is not an object', async () => {
    assertError(await server.call('/run', undefined, { raw: '["code"]' }), 400, 'invalid_request');
    // Un cuerpo vacío equivale a un objeto sin campos.
    assertError(await server.call('/run', undefined, { raw: '' }), 400, 'missing_code');
  });

  test('missing code', async () => {
    assertError(await server.call('/run', {}), 400, 'missing_code');
    assertError(await server.call('/check', { filename: 'a.nex' }), 400, 'missing_code');
  });

  test('code of the wrong type', async () => {
    for (const code of [42, null, true, ['fn'], { text: 'fn' }]) {
      assertError(await server.call('/run', { code }), 400, 'invalid_code_type');
    }
  });

  test('code larger than the limit', async () => {
    assertError(await server.run(`// ${'a'.repeat(1000)}\n${HELLO}`), 413, 'code_too_large');
    // También cuando el cuerpo entero supera lo que el servidor está dispuesto a leer.
    assertError(await server.run('a'.repeat(50_000)), 413, 'code_too_large');
  });

  test('the limit counts bytes, not characters', async () => {
    assert.equal((await server.run(`// ${'a'.repeat(900)}\n${HELLO}`)).status, 200);
    assertError(await server.run(`// ${'ñ'.repeat(600)}\n${HELLO}`), 413, 'code_too_large');
  });

  test('invalid virtual file name', async () => {
    const names = ['../../etc/passwd', 'C:\\Windows\\win.ini', '/etc/shadow.nex', 'a/b.nex', 'program.py', '', '.nex',
      'a b.nex', `${'a'.repeat(65)}.nex`, 'x.nex\u0000', 42, null];
    for (const filename of names) {
      assertError(await server.call('/run', { code: HELLO, filename }), 400, 'invalid_filename');
    }
  });

  test('wrong content type', async () => {
    const response = await server.call('/run', undefined, { raw: JSON.stringify({ code: HELLO }), headers: { 'Content-Type': 'text/plain' } });
    assertError(response, 415, 'unsupported_media_type');
  });

  test('unknown route and wrong method', async () => {
    assertError(await server.call('/execute', { code: HELLO }), 404, 'not_found');
    assertError(await server.call('/run'), 404, 'not_found');
  });
});

describe('limits', () => {
  test('a program that runs too long is stopped and reported as a timeout', async () => {
    const server = await startServer({ timeoutMs: 800 });
    try {
      const started = Date.now();
      const response = await server.run(SLOW);
      assertResult(response, 'run', 'timeout');
      assert.equal(response.json.message, 'The program ran for more than 800 ms and was stopped.');
      assert.ok(Date.now() - started < 4000, 'the request must end close to the time limit');
      // El servidor sigue atendiendo con normalidad.
      assert.equal((await server.run(HELLO)).json.output, 'Hello from NEXORA\n');
    } finally {
      await server.close();
    }
  });

  test('a slow program does not block other visitors', async () => {
    const server = await startServer({ timeoutMs: 3000, maxConcurrent: 2 });
    try {
      const slow = server.run(SLOW);
      const started = Date.now();
      const fast = await server.run(HELLO);
      assert.equal(fast.json.status, 'success');
      assert.ok(Date.now() - started < 2500, 'the fast request must not wait for the slow one');
      assert.equal((await slow).json.status, 'timeout');
    } finally {
      await server.close();
    }
  });

  test('output is limited', async () => {
    const server = await startServer({ maxOutputBytes: 200 });
    try {
      const spam = 'fn spam(n: Int) -> Void {\n    if n == 0 {\n        return\n    }\n    print("0123456789")\n    spam(n - 1)\n}\n';
      const response = await server.run(`${spam}${inMain('spam(900)')}`);
      assertResult(response, 'run', 'output_limit');
      assert.ok(Buffer.byteLength(response.json.output) <= 200);
      assert.match(response.json.message, /more than 200 bytes/);
    } finally {
      await server.close();
    }
  });

  test('text length is limited', async () => {
    const server = await startServer({ maxTextChars: 1000 });
    try {
      const grow = 'fn grow(text: Text, times: Int) -> Text {\n    if times == 0 {\n        return text\n    }\n    return grow(text + text, times - 1)\n}\n';
      const response = await server.run(`${grow}${inMain('let big = grow("ab", 40)\nprint("unreachable")')}`);
      assertResult(response, 'run', 'runtime_error');
      assert.equal(response.json.diagnostics[0].code, 'E3006');
      assert.equal(response.json.output, '');
    } finally {
      await server.close();
    }
  });

  test('when every worker is taken and the queue is full, the request is refused at once', async () => {
    const server = await startServer({ timeoutMs: 2000, maxConcurrent: 1, maxQueue: 0 });
    try {
      const slow = server.run(SLOW);
      await new Promise((resolve) => setTimeout(resolve, 200));
      const started = Date.now();
      const refused = await server.run(HELLO);
      assertError(refused, 503, 'busy');
      assert.equal(refused.headers.get('retry-after'), '2');
      assert.ok(Date.now() - started < 500);
      await slow;
      assert.equal((await server.run(HELLO)).status, 200);
    } finally {
      await server.close();
    }
  });

  test('requests wait their turn in the queue', async () => {
    const server = await startServer({ maxConcurrent: 1, maxQueue: 5 });
    try {
      const responses = await Promise.all([1, 2, 3, 4].map((n) => server.run(inMain(`print(${n})`))));
      assert.deepEqual(responses.map((response) => response.json.output), ['1\n', '2\n', '3\n', '4\n']);
    } finally {
      await server.close();
    }
  });

  test('requests per client are limited', async () => {
    const server = await startServer({ rateLimit: { windowMs: 60_000, limit: 3 } });
    try {
      for (let index = 0; index < 3; index += 1) assert.equal((await server.check(HELLO)).status, 200);
      assertError(await server.check(HELLO), 429, 'rate_limited');
      assertError(await server.run(HELLO), 429, 'rate_limited');
      // Las rutas de solo lectura no consumen ese cupo.
      assert.equal((await server.call('/examples')).status, 200);
    } finally {
      await server.close();
    }
  });
});

describe('when the runtime fails', () => {
  const secretCode = 'fn main() -> Void {\n    print("SECRET-SOURCE-CODE-12345")\n}\n';

  for (const [name, command] of [
    ['the worker cannot be started', ['this-executable-does-not-exist-nexora']],
    ['the worker writes something that is not JSON', fakeWorker('garbage')],
    ['the worker crashes', fakeWorker('crash')],
    ['the worker answers with the wrong shape', fakeWorker('wrong-shape')],
    ['the worker invents a status', fakeWorker('wrong-status')],
    ['the worker reports an internal error', fakeWorker('internal-error')],
    ['the worker floods its output', fakeWorker('flood')],
  ]) {
    test(name, async () => {
      const server = await startServer({ workerCommand: command });
      try {
        const response = await server.run(secretCode);
        assertError(response, 503, 'runtime_unavailable');
        // Ni la respuesta ni el registro del servidor contienen el código enviado.
        assert.doesNotMatch(response.text, /SECRET-SOURCE-CODE/);
        assert.equal(server.logs.length, 1);
        assert.doesNotMatch(server.logs.join('\n'), /SECRET-SOURCE-CODE|Traceback|secret\/internal/);
      } finally {
        await server.close();
      }
    });
  }

  test('a worker that never answers is killed at the time limit', async () => {
    const server = await startServer({ workerCommand: fakeWorker('hang'), timeoutMs: 500 });
    try {
      const started = Date.now();
      const response = await server.run(HELLO);
      assert.equal(response.json.status, 'timeout');
      assert.ok(Date.now() - started < 3000);
    } finally {
      await server.close();
    }
  });

  test('info reports that the runtime is not available', async () => {
    const server = await startServer({ workerCommand: ['this-executable-does-not-exist-nexora'] });
    try {
      const response = await server.call('/info');
      assert.equal(response.status, 200);
      assert.deepEqual([response.json.available, response.json.version, response.json.language], [false, null, null]);
    } finally {
      await server.close();
    }
  });

  test('a disabled playground refuses every request', async () => {
    const server = await startServer({ enabled: false });
    try {
      assertError(await server.run(HELLO), 503, 'playground_disabled');
      assertError(await server.call('/info'), 503, 'playground_disabled');
    } finally {
      await server.close();
    }
  });
});

describe('isolation of the worker', () => {
  test('the worker receives none of the server environment, and starts in an empty directory', async () => {
    process.env.NEXORA_TEST_SECRET = 'do-not-leak';
    process.env.DB_PASSWORD = 'do-not-leak-either';
    const server = await startServer({ workerCommand: fakeWorker('environment') });
    try {
      const seen = JSON.parse((await server.run(HELLO)).json.output);
      // El servidor solo pasa SystemRoot y PATH. En Windows, el sistema añade por su cuenta unas
      // pocas variables básicas del usuario a todo proceso nuevo; ninguna es del servidor.
      const passed = new Set(['SYSTEMROOT', 'PATH']);
      const addedByWindows = new Set([
        'HOMEDRIVE', 'HOMEPATH', 'LOGONSERVER', 'SYSTEMDRIVE', 'TEMP', 'USERDOMAIN', 'USERNAME', 'USERPROFILE', 'WINDIR',
      ]);
      const unexpected = seen.variables.filter((name) => {
        const upper = name.toUpperCase();
        return !passed.has(upper) && !(process.platform === 'win32' && addedByWindows.has(upper));
      });
      assert.deepEqual(unexpected, []);
      for (const name of Object.keys(process.env)) {
        if (/^(DB_|GOOGLE_|GITHUB_|NEXORA_|PLAYGROUND_|PUBLIC_URL|NODE_)/.test(name)) {
          assert.ok(!seen.variables.includes(name), `${name} reached the worker`);
        }
      }
      assert.doesNotMatch(JSON.stringify(seen), /do-not-leak/);
      assert.match(seen.directory, /nexora-playground-worker$/);
      assert.deepEqual(readdirSync(seen.directory), []);
      assert.deepEqual(seen.request, ['action', 'code', 'filename', 'limits']);
    } finally {
      delete process.env.NEXORA_TEST_SECRET;
      delete process.env.DB_PASSWORD;
      await server.close();
    }
  });

  test('user code runs in another process, not in the server', async () => {
    const server = await startServer({ timeoutMs: 1000 });
    try {
      // Si el programa se ejecutara dentro del servidor, este no podría responder mientras tanto.
      const slow = server.run(SLOW);
      const info = await server.call('/examples');
      assert.equal(info.status, 200);
      assert.equal((await slow).json.status, 'timeout');
    } finally {
      await server.close();
    }
  });
});

describe('origins', () => {
  test('requests from another site are refused', async () => {
    const server = await startServer();
    try {
      const response = await server.call('/run', { code: HELLO }, { headers: { Origin: 'https://evil.example' } });
      assertError(response, 403, 'origin_not_allowed');
      assert.equal(response.headers.get('access-control-allow-origin'), null);
    } finally {
      await server.close();
    }
  });

  test('requests from the same site and from configured origins are accepted', async () => {
    const server = await startServer({ allowedOrigins: ['https://nexora.example'] });
    try {
      const same = await server.call('/run', { code: HELLO }, { headers: { Origin: new URL(server.base).origin } });
      assert.equal(same.status, 200);
      const allowed = await server.call('/run', { code: HELLO }, { headers: { Origin: 'https://nexora.example' } });
      assert.equal(allowed.status, 200);
      assert.equal(allowed.headers.get('access-control-allow-origin'), 'https://nexora.example');
      assertError(await server.call('/run', { code: HELLO }, { headers: { Origin: 'https://other.example' } }), 403, 'origin_not_allowed');
    } finally {
      await server.close();
    }
  });
});

describe('info and examples', () => {
  let server;
  before(async () => { server = await startServer(); });
  after(() => server.close());

  test('info comes from the language core', async () => {
    const response = await server.call('/info');
    assert.equal(response.status, 200);
    const cliVersion = execFileSync(python, ['-m', 'nexora', '--version'], { encoding: 'utf8' }).trim();
    assert.equal(`NEXORA ${response.json.version}`, cliVersion);
    assert.equal(response.json.available, true);
    for (const keyword of ['fn', 'let', 'return', 'if', 'else', 'requires', 'ensures']) {
      assert.ok(response.json.language.keywords.includes(keyword), keyword);
    }
    assert.deepEqual(response.json.language.builtins, [
      'Float.can_parse', 'Float.parse', 'Int.can_parse', 'Int.parse', 'Text.contains', 'Text.ends_with',
      'Text.length', 'Text.slice', 'Text.starts_with', 'print', 'to_float', 'to_int', 'to_text',
    ]);
    assert.deepEqual(response.json.limits, { code_bytes: 65536, timeout_ms: 2000, output_bytes: 65536, text_chars: 262144 });
  });

  test('every example is a real file and behaves as announced', async () => {
    const { json } = await server.call('/examples');
    assert.ok(json.examples.length >= 6);
    assert.equal(new Set(json.examples.map((example) => example.id)).size, json.examples.length);
    for (const example of json.examples) {
      assert.ok(example.title.length > 3 && example.description.length > 10, example.id);
      assert.match(example.filename, /^[a-z_]+\.nex$/);
      const response = await server.run(example.code, { filename: example.filename });
      assert.equal(response.json.status, example.expect, example.id);
      if (example.expect === 'success') assert.ok(response.json.output.length > 0, example.id);
    }
  });

  test('the first example is a small program that runs', async () => {
    const { json } = await server.call('/examples');
    assert.equal(json.examples[0].id, 'hello');
    assert.equal((await server.run(json.examples[0].code)).json.output, 'Hello from NEXORA\n');
  });
});

describe('the playground and the command line share one core', () => {
  let server;
  before(async () => { server = await startServer(); });
  after(() => server.close());

  const files = [];
  const collect = (directory) => {
    for (const name of readdirSync(directory)) {
      const full = path.join(directory, name);
      if (statSync(full).isDirectory()) collect(full);
      else if (name.endsWith('.nex')) files.push(full);
    }
  };
  collect(examplesDir);
  const statusOfExit = { 0: 'success', 1: 'invalid', 3: 'runtime_error', 5: 'contract_violation' };
  const withoutFile = (diagnostics) => diagnostics.map(({ file, ...rest }) => rest);

  for (const file of files) {
    test(`same result as nex for ${path.relative(examplesDir, file).replaceAll('\\', '/')}`, async () => {
      const code = readFileSync(file, 'utf8');

      const cliRun = spawnSync(python, ['-m', 'nexora', 'run', file, '--format', 'json'], { encoding: 'utf8' });
      const apiRun = (await server.run(code)).json;
      assert.equal(apiRun.status, statusOfExit[cliRun.status]);
      assert.equal(apiRun.output, cliRun.stdout.replaceAll('\r\n', '\n'));
      const cliDiagnostics = cliRun.stderr.trim() ? JSON.parse(cliRun.stderr).diagnostics : [];
      assert.deepEqual(withoutFile(apiRun.diagnostics), withoutFile(cliDiagnostics));

      const cliCheck = spawnSync(python, ['-m', 'nexora', 'check', file, '--format', 'json'], { encoding: 'utf8' });
      const apiCheck = (await server.check(code)).json;
      assert.equal(apiCheck.status, cliCheck.status === 0 ? 'success' : 'invalid');
      assert.deepEqual(withoutFile(apiCheck.diagnostics), withoutFile(JSON.parse(cliCheck.stdout).diagnostics));
    });
  }
});
