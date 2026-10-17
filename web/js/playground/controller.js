// State and behaviour of the playground, independent of the page.
//
// The controller receives what it needs from outside (the API client, a place to keep the
// code, the clipboard, and a `render` function), so it can be exercised without a browser.
// Everything shown on screen is derived from the state object passed to `render`.

/** Used only when the examples cannot be loaded from the server. It is a real, valid program. */
export const FALLBACK_EXAMPLE = Object.freeze({
  id: 'hello',
  title: 'Hello world',
  description: 'The first NEXORA program.',
  filename: 'hello.nex',
  code: '// The first NEXORA program.\nfn main() -> Void {\n    let message = "Hello from NEXORA"\n    print(message)\n}\n',
});

export const CONNECTION_MESSAGE = 'Unable to reach the NEXORA runtime. Your code is still available in the editor.';
export const DISABLED_MESSAGE = 'The playground is disabled on this server.';
const STORAGE_KEY = 'nexora.playground.v1';
const NOTICE_MS = 8000;

function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}

/** What the status line says about an outcome. `tone` selects its colour. */
export function describe(outcome) {
  if (outcome.kind === 'connection') return { tone: 'service', text: CONNECTION_MESSAGE };
  if (outcome.kind === 'service') return { tone: 'service', text: outcome.message };

  const { action, status, diagnostics, message, duration_ms: duration } = outcome.result;
  const time = Number.isInteger(duration) ? ` in ${duration} ms` : '';
  if (status === 'success') {
    return action === 'check'
      ? { tone: 'ok', text: `Check passed: no errors found${time}. The program was not run.` }
      : { tone: 'ok', text: `Finished${time}.` };
  }
  if (status === 'invalid') {
    const tail = action === 'run' ? ' The program was not run.' : '';
    return { tone: 'error', text: `${plural(diagnostics.length, 'error')} found.${tail}` };
  }
  if (status === 'runtime_error') return { tone: 'error', text: 'The program stopped because of a runtime error.' };
  if (status === 'contract_violation') return { tone: 'error', text: 'The program stopped because a contract was broken.' };
  // timeout, output_limit, memory_limit: the runtime explains which limit was reached.
  return { tone: 'limit', text: message ?? 'The program was stopped because it reached a limit.' };
}

/**
 * @param {object} dependencies
 * @param {ReturnType<import('./client.js').createClient>} dependencies.client
 * @param {(state: object) => void} dependencies.render
 * @param {{ getItem(key: string): string | null, setItem(key: string, value: string): void } | null} [dependencies.storage]
 * @param {{ writeText(text: string): Promise<void> } | null} [dependencies.clipboard]
 * @param {(callback: () => void, ms: number) => unknown} [dependencies.setTimer]
 * @param {(timer: unknown) => void} [dependencies.clearTimer]
 */
export function createController({
  client, render, storage = null, clipboard = null,
  setTimer = setTimeout, clearTimer = clearTimeout,
}) {
  const state = {
    ready: false,
    // Whether the server confirmed that the playground is on: true, false, or null if it could not
    // be told (no answer, or one the page does not understand). Run and Check need true.
    enabled: null,
    disabled: false,          // enabled === false: the server says the playground is off
    code: '',
    filename: FALLBACK_EXAMPLE.filename,
    // The program the editor started from: what Reset goes back to.
    origin: FALLBACK_EXAMPLE,
    examples: [],
    info: null,               // { available, version, language, limits } once the server answers
    busy: null,               // null | 'run' | 'check'
    outcome: null,            // the last answer, or null if nothing has been run or checked yet
    outcomeIsCurrent: false,  // false once the code changes after the last answer
    status: { tone: 'idle', text: 'Nothing has been run yet.' },
    tab: 'output',
    notice: null,             // { text, undo: boolean } shown briefly after an action
  };
  let undoSnapshot = null;
  let noticeTimer = null;

  const update = () => render(state);
  const dirty = () => state.code !== state.origin.code;

  function save() {
    try {
      storage?.setItem(STORAGE_KEY, JSON.stringify({ code: state.code, origin: state.origin.id }));
    } catch {
      // Storage full or disabled: the playground works the same, it just forgets on reload.
    }
  }

  function restore() {
    try {
      const saved = JSON.parse(storage?.getItem(STORAGE_KEY) ?? 'null');
      return saved && typeof saved.code === 'string' ? saved : null;
    } catch {
      return null;
    }
  }

  function notify(text, undo = false) {
    clearTimer(noticeTimer);
    state.notice = { text, undo };
    if (!undo) undoSnapshot = null;
    noticeTimer = setTimer(() => {
      state.notice = null;
      undoSnapshot = null;
      update();
    }, NOTICE_MS);
  }

  /** Replaces the editor content with a program, keeping the old content for Undo if it had edits. */
  function replaceWith(example, label) {
    const hadEdits = dirty();
    const snapshot = { code: state.code, origin: state.origin, filename: state.filename };
    state.code = example.code;
    state.origin = example;
    state.filename = example.filename;
    state.outcomeIsCurrent = false;
    save();
    if (hadEdits) {
      notify(`${label} Your previous code was replaced.`, true);
      undoSnapshot = snapshot;
    } else {
      notify(label);
    }
    update();
  }

  async function execute(action) {
    if (state.busy || state.enabled !== true) return;
    state.busy = action;
    state.notice = null;
    state.status = { tone: 'busy', text: action === 'run' ? 'Running…' : 'Checking…' };
    update();

    // The code is read once: what is shown afterwards refers to exactly what was sent.
    const sent = state.code;
    const outcome = await client[action](sent, state.filename);

    state.busy = null;
    state.outcome = outcome;
    state.outcomeIsCurrent = state.code === sent;
    state.status = describe(outcome);
    if (outcome.kind === 'result') {
      state.tab = outcome.result.diagnostics.length > 0 ? 'diagnostics' : 'output';
    }
    update();
  }

  return {
    state,

    /** Loads the saved code or the first example, and asks the server about the language. */
    async init() {
      const saved = restore();
      if (saved) state.code = saved.code;
      update();

      // A server with the playground off says so first, and then nothing else is asked. If the
      // answer is anything else (an older server, no connection), the page asks as it always did.
      const status = await client.status();
      state.enabled = status.kind === 'data' ? status.data.enabled : null;
      const [examples, info] = state.enabled === false ? [null, null] : await Promise.all([client.examples(), client.info()]);
      // Without an answer from /status, /info decides: a server answers it only with the playground
      // on, and otherwise refuses it with playground_disabled. Nothing else confirms either way.
      if (state.enabled === null) {
        if (info.kind === 'data') state.enabled = true;
        else if (info.kind === 'service' && info.code === 'playground_disabled') state.enabled = false;
      }
      state.disabled = state.enabled === false;
      if (examples?.kind === 'data' && examples.data.examples.length > 0) {
        state.examples = examples.data.examples;
      } else {
        state.examples = [FALLBACK_EXAMPLE];
      }
      state.origin = state.examples.find((example) => example.id === saved?.origin) ?? state.examples[0];
      state.filename = state.origin.filename;
      if (!saved) state.code = state.origin.code;

      if (state.disabled) {
        state.status = { tone: 'service', text: DISABLED_MESSAGE };
      } else if (info.kind === 'data') {
        state.info = info.data;
        if (!info.data.available) {
          state.status = { tone: 'service', text: 'The NEXORA runtime is not available on this server right now.' };
        }
      } else if (info.kind === 'connection') {
        state.status = { tone: 'service', text: CONNECTION_MESSAGE };
      } else {
        state.status = { tone: 'service', text: info.message };
      }
      state.ready = true;
      update();
    },

    edit(code) {
      if (code === state.code) return;
      state.code = code;
      state.outcomeIsCurrent = false;
      save();
      update();
    },

    run: () => execute('run'),
    check: () => execute('check'),

    async copy() {
      try {
        if (!clipboard) throw new Error('no clipboard');
        await clipboard.writeText(state.code);
        notify('Code copied to the clipboard.');
      } catch {
        notify('Could not copy: the browser did not allow access to the clipboard.');
      }
      update();
    },

    reset() {
      if (!dirty()) {
        notify('The editor already shows the original example.');
        update();
        return;
      }
      replaceWith(state.origin, `Reset to “${state.origin.title}”.`);
    },

    loadExample(id) {
      const example = state.examples.find((candidate) => candidate.id === id);
      if (!example) return;
      replaceWith(example, `Loaded “${example.title}”.`);
    },

    undo() {
      if (!undoSnapshot) return;
      Object.assign(state, undoSnapshot);
      undoSnapshot = null;
      state.outcomeIsCurrent = false;
      save();
      notify('Your code is back.');
      update();
    },

    dismissNotice() {
      clearTimer(noticeTimer);
      state.notice = null;
      undoSnapshot = null;
      update();
    },

    selectTab(tab) {
      if (tab !== 'output' && tab !== 'diagnostics') return;
      state.tab = tab;
      update();
    },
  };
}
