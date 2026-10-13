// Lógica del playground en el navegador (web/js/playground), probada sin navegador.
// El controlador recibe sus dependencias desde fuera, así que aquí se le da el cliente real
// contra un servidor real, o un cliente falso para los casos de fallo.
// El dibujado de la página (view.js) se comprueba a mano en el navegador: ver nexora/docs/playground.md.

import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';
import { createClient } from '../../web/js/playground/client.js';
import { CONNECTION_MESSAGE, FALLBACK_EXAMPLE, createController, describe as describeOutcome } from '../../web/js/playground/controller.js';
import { FALLBACK_LANGUAGE, highlight } from '../../web/js/playground/syntax.js';
import { offsetOf } from '../../web/js/playground/view.js';
import { HELLO, inMain, SLOW, startServer } from './helpers.js';

/** Un controlador con todo lo que lo rodea sustituido por dobles observables. */
function harness(client, { saved = null, clipboard } = {}) {
  const renders = [];
  const stored = new Map(saved ? [['nexora.playground.v1', JSON.stringify(saved)]] : []);
  const copied = [];
  const timers = [];
  const controller = createController({
    client,
    render: (state) => renders.push(structuredClone({ ...state, origin: state.origin.id })),
    storage: { getItem: (key) => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) },
    clipboard: clipboard === undefined ? { writeText: async (text) => { copied.push(text); } } : clipboard,
    setTimer: (callback) => { timers.push(callback); return timers.length; },
    clearTimer: () => {},
  });
  return { controller, state: controller.state, renders, stored, copied, timers };
}

describe('against the real server', () => {
  let server;
  let client;
  before(async () => {
    server = await startServer({ timeoutMs: 1500 });
    client = createClient({ base: server.base });
  });
  after(() => server.close());

  test('initial load shows a real example and the version of the language', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    assert.equal(state.ready, true);
    assert.equal(state.origin.id, 'hello');
    assert.equal(state.filename, 'hello.nex');
    assert.match(state.code, /fn main\(\) -> Void/);
    assert.ok(state.examples.length >= 6);
    assert.match(state.info.version, /^\d+\.\d+\.\d+$/);
    assert.equal(state.outcome, null);
    assert.equal(state.status.text, 'Nothing has been run yet.');
  });

  test('run shows the real output of the program that is in the editor', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.edit(inMain('print(21 * 2)\nprint("edited by the visitor")'));
    await controller.run();
    assert.equal(state.outcome.kind, 'result');
    assert.equal(state.outcome.result.output, '42\nedited by the visitor\n');
    assert.deepEqual([state.status.tone, state.tab, state.outcomeIsCurrent], ['ok', 'output', true]);
    assert.match(state.status.text, /^Finished in \d+ ms\.$/);
  });

  test('check reports that the program was not run', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.edit(inMain('print("SIDE EFFECT")\nprint(1 / 0)'));
    await controller.check();
    assert.equal(state.outcome.result.output, '');
    assert.match(state.status.text, /^Check passed: no errors found in \d+ ms\. The program was not run\.$/);
  });

  test('errors of the program open the diagnostics with their location', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.edit(inMain('let age: Int = "twenty"\nprint(missing)'));
    await controller.check();
    assert.deepEqual([state.status.tone, state.status.text, state.tab], ['error', '2 errors found.', 'diagnostics']);
    assert.deepEqual(state.outcome.result.diagnostics.map((d) => [d.category, d.line, d.column]), [['type', 2, 20], ['semantic', 3, 11]]);

    await controller.run();
    assert.equal(state.status.text, '2 errors found. The program was not run.');
  });

  test('a runtime error keeps the partial output and explains itself', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.edit(inMain('print("before")\nprint(1 / 0)'));
    await controller.run();
    assert.equal(state.outcome.result.output, 'before\n');
    assert.deepEqual([state.status.tone, state.tab], ['error', 'diagnostics']);
    assert.equal(state.status.text, 'The program stopped because of a runtime error.');
  });

  test('a timeout is presented as a limit, not as an error of the code or of the connection', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.edit(SLOW);
    await controller.run();
    assert.equal(state.outcome.result.status, 'timeout');
    assert.deepEqual([state.status.tone, state.status.text], ['limit', 'The program ran for more than 1500 ms and was stopped.']);
    assert.equal(state.code, SLOW);
  });

  test('loading states: the button cannot be pressed twice', async () => {
    const { controller, state, renders } = harness(client);
    await controller.init();
    const first = controller.run();
    assert.equal(state.busy, 'run');
    assert.equal(state.status.text, 'Running…');
    await controller.run();          // ignored while busy
    await controller.check();        // ignored while busy
    await first;
    assert.equal(state.busy, null);
    assert.equal(renders.filter((snapshot) => snapshot.busy !== null).length, 1);
    assert.equal(state.outcome.result.action, 'run');
  });

  test('editing after a run marks the results as out of date', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    await controller.run();
    assert.equal(state.outcomeIsCurrent, true);
    controller.edit(`${state.code}\n// changed`);
    assert.equal(state.outcomeIsCurrent, false);
  });

  test('every example offered by the server loads into the editor', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    for (const example of state.examples) {
      controller.loadExample(example.id);
      assert.deepEqual([state.code, state.filename, state.origin.id], [example.code, example.filename, example.id]);
    }
  });

  test('the fallback example and word lists match the real language', async () => {
    const outcome = await client.run(FALLBACK_EXAMPLE.code, FALLBACK_EXAMPLE.filename);
    assert.deepEqual([outcome.result.status, outcome.result.output], ['success', 'Hello from NEXORA\n']);
    const { data } = await client.info();
    for (const list of ['keywords', 'types', 'builtins', 'reserved_words']) {
      assert.deepEqual([...FALLBACK_LANGUAGE[list]].sort(), [...data.language[list]].sort(), list);
    }
  });

  test('a service refusal is not presented as an error of the program', async () => {
    const tooLarge = await client.run(`// ${'a'.repeat(70_000)}`, 'big.nex');
    assert.deepEqual([tooLarge.kind, tooLarge.code], ['service', 'code_too_large']);
    assert.equal(describeOutcome(tooLarge).tone, 'service');
  });
});

describe('editing, copying and resetting', () => {
  const example = (id, code) => ({ id, title: `Title ${id}`, description: `About ${id}.`, filename: `${id}.nex`, code });
  const client = {
    examples: async () => ({ kind: 'data', data: { examples: [example('one', HELLO), example('two', 'fn main() -> Void {}\n')] } }),
    info: async () => ({ kind: 'data', data: { available: true, version: '9.9.9', language: FALLBACK_LANGUAGE, limits: {} } }),
    run: async () => ({ kind: 'connection' }),
    check: async () => ({ kind: 'connection' }),
  };

  test('the code is kept in the browser and comes back after a reload', async () => {
    const first = harness(client);
    await first.controller.init();
    first.controller.loadExample('two');
    first.controller.edit('fn main() -> Void {\n    print("mine")\n}\n');

    const reloaded = harness(client, { saved: JSON.parse(first.stored.get('nexora.playground.v1')) });
    await reloaded.controller.init();
    assert.equal(reloaded.state.code, 'fn main() -> Void {\n    print("mine")\n}\n');
    assert.equal(reloaded.state.origin.id, 'two');
  });

  test('copy puts exactly the editor content on the clipboard', async () => {
    const { controller, state, copied } = harness(client);
    await controller.init();
    controller.edit('fn main() -> Void {\n\tprint("tabs,  spaces and ñ")\n}\n');
    await controller.copy();
    assert.deepEqual(copied, ['fn main() -> Void {\n\tprint("tabs,  spaces and ñ")\n}\n']);
    assert.deepEqual(state.notice, { text: 'Code copied to the clipboard.', undo: false });
  });

  test('copy says so when the browser refuses', async () => {
    for (const clipboard of [null, { writeText: async () => { throw new Error('denied'); } }]) {
      const { controller, state } = harness(client, { clipboard });
      await controller.init();
      await controller.copy();
      assert.match(state.notice.text, /^Could not copy/);
    }
  });

  test('reset restores the example and can be undone', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.reset();
    assert.equal(state.notice.text, 'The editor already shows the original example.');

    controller.edit('// my work\n');
    controller.reset();
    assert.equal(state.code, HELLO);
    assert.deepEqual(state.notice, { text: 'Reset to “Title one”. Your previous code was replaced.', undo: true });

    controller.undo();
    assert.equal(state.code, '// my work\n');
    assert.equal(state.notice.text, 'Your code is back.');
  });

  test('loading an example never loses edited code silently', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.loadExample('two');
    assert.equal(state.notice.undo, false, 'nothing to undo: the editor had no changes');

    controller.edit('// my work\n');
    controller.loadExample('one');
    assert.equal(state.code, HELLO);
    assert.equal(state.notice.undo, true);
    controller.undo();
    assert.deepEqual([state.code, state.origin.id, state.filename], ['// my work\n', 'two', 'two.nex']);
  });

  test('the undo offer expires and can be dismissed', async () => {
    const { controller, state, timers } = harness(client);
    await controller.init();
    controller.edit('// my work\n');
    controller.reset();
    timers.at(-1)();                       // the notice times out
    assert.equal(state.notice, null);
    controller.undo();                     // too late: nothing happens
    assert.equal(state.code, HELLO);

    controller.edit('// again\n');
    controller.reset();
    controller.dismissNotice();
    controller.undo();
    assert.equal(state.code, HELLO);
  });

  test('tabs can be switched by hand', async () => {
    const { controller, state } = harness(client);
    await controller.init();
    controller.selectTab('diagnostics');
    assert.equal(state.tab, 'diagnostics');
    controller.selectTab('nonsense');
    assert.equal(state.tab, 'diagnostics');
  });
});

describe('when the server cannot be reached or misbehaves', () => {
  const failingFetch = async () => { throw new TypeError('fetch failed'); };
  const respond = (status, body) => async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

  test('connection errors keep the code and say what happened', async () => {
    const { controller, state } = harness(createClient({ fetch: failingFetch }));
    await controller.init();
    assert.equal(state.ready, true);
    assert.equal(state.code, FALLBACK_EXAMPLE.code, 'a valid program is shown even without the server');
    assert.equal(state.status.text, CONNECTION_MESSAGE);

    controller.edit('// my work\n');
    await controller.run();
    assert.deepEqual(state.outcome, { kind: 'connection' });
    assert.deepEqual(state.status, { tone: 'service', text: CONNECTION_MESSAGE });
    assert.equal(state.code, '// my work\n');
    assert.equal(state.busy, null);
  });

  test('a proxy error page is a connection problem', async () => {
    const client = createClient({ fetch: respond(502, '<html><body>Bad Gateway</body></html>') });
    assert.deepEqual(await client.run(HELLO, 'a.nex'), { kind: 'connection' });
  });

  test('errors of the service carry their own message', async () => {
    const body = { schema: 'nexora.result/1', status: 'error', error: { code: 'busy', message: 'The playground is busy. Try again in a few seconds.' } };
    const outcome = await createClient({ fetch: respond(503, body) }).run(HELLO, 'a.nex');
    assert.deepEqual(outcome, { kind: 'service', code: 'busy', message: body.error.message });
    assert.deepEqual(describeOutcome(outcome), { tone: 'service', text: body.error.message });
  });

  test('an answer that is not a result is never shown as a successful run', async () => {
    for (const body of ['{"status": "success"}', '{"hello": 1}', '[]', 'null', '{"status":"success","output":5,"diagnostics":[]}',
      '{"status":"made-up","output":"","diagnostics":[]}']) {
      const outcome = await createClient({ fetch: respond(200, body) }).run(HELLO, 'a.nex');
      assert.deepEqual([outcome.kind, outcome.code], ['service', 'unexpected_response'], body);
    }
  });

  test('a server that reports the runtime as unavailable is announced on load', async () => {
    const client = {
      examples: async () => ({ kind: 'data', data: { examples: [] } }),
      info: async () => ({ kind: 'data', data: { available: false, version: null, language: null, limits: {} } }),
    };
    const { controller, state } = harness(client);
    await controller.init();
    assert.equal(state.status.text, 'The NEXORA runtime is not available on this server right now.');
    assert.equal(state.code, FALLBACK_EXAMPLE.code);
  });
});

describe('highlighting and positions', () => {
  const classes = (source) => [...highlight(source).matchAll(/<span class="tok-(\w+)">([^<]*)<\/span>/g)].map((m) => [m[1], m[2]]);

  test('the words of the real grammar are recognised', () => {
    assert.deepEqual(classes('fn add(a: Int) -> Int { return a + 1 }'), [
      ['kw', 'fn'], ['fn', 'add'], ['type', 'Int'], ['op', '-&gt;'], ['type', 'Int'], ['kw', 'return'], ['op', '+'], ['num', '1'],
    ]);
    assert.deepEqual(classes('print(to_text(2.5)) // done'), [['builtin', 'print'], ['builtin', 'to_text'], ['num', '2.5'], ['com', '// done']]);
    assert.deepEqual(classes('requires n >= 0 and not ok'), [['kw', 'requires'], ['op', '&gt;='], ['num', '0'], ['kw', 'and'], ['kw', 'not']]);
    assert.deepEqual(classes('while x'), [['reserved', 'while']]);
  });

  test('text is never coloured as code, and unfinished text does not break', () => {
    assert.deepEqual(classes('"fn let // not a comment"'), [['str', '"fn let // not a comment"']]);
    assert.deepEqual(classes('let a = "open'), [['kw', 'let'], ['op', '='], ['str', '"open']]);
  });

  test('highlighting only adds markup: the text is unchanged and escaped', () => {
    const source = 'fn main() -> Void {\n    print("<script>alert(1)</script> & <b>")\n}\n';
    const html = highlight(source);
    assert.doesNotMatch(html, /<script|<b>/);
    const text = html.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    assert.equal(text, source);
  });

  test('line and column become an offset in the text', () => {
    const text = 'fn main() -> Void {\n    print(x)\n}\n';
    assert.equal(text.slice(offsetOf(text, 2, 11), offsetOf(text, 2, 12)), 'x');
    assert.equal(offsetOf(text, 1, 1), 0);
    assert.equal(offsetOf(text, 2, 999), text.indexOf('\n', 20), 'a column past the end stops at the end of the line');
    assert.equal(offsetOf(text, 99, 1), text.length);
  });
});
