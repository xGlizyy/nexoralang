// The page of the playground: turns the controller's state into DOM and user input into calls.
//
// The editor is deliberately small: a <textarea> for editing, with a highlighted copy of the
// same text drawn underneath it and a gutter of line numbers. It gives normal selection, undo
// and keyboard behaviour for free. It has no autocompletion, bracket matching, multiple cursors
// or code folding.
//
// Everything that comes from a program or from the server is written with `textContent`,
// never as HTML. The only HTML built here is the highlighting of the visitor's own code,
// which escapes it first (see syntax.js).

import { FALLBACK_LANGUAGE, highlight } from './syntax.js';

const INDENT = '    ';

/** Offset of a 1-based line and column in `text`. */
export function offsetOf(text, line, column) {
  let offset = 0;
  for (let current = 1; current < line; current += 1) {
    const next = text.indexOf('\n', offset);
    if (next === -1) return text.length;
    offset = next + 1;
  }
  const end = text.indexOf('\n', offset);
  return Math.min(offset + column - 1, end === -1 ? text.length : end);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mountView(root, controller, { githubUrl = null } = {}) {
  const find = (selector) => document.querySelector(selector);
  const input = find('[data-input]');
  const highlighted = find('[data-highlight]');
  const gutter = find('[data-gutter]');
  const examples = find('[data-examples]');
  const output = find('[data-output]');
  const diagnosticsList = find('[data-diagnostics]');
  const tabs = [...document.querySelectorAll('[data-tab]')];

  let shownCode = null;
  let shownExamples = null;
  let shownOutcome = null;
  let shownLanguage = null;
  let escapePressed = false;

  // Editing

  function replaceSelection(text, start = input.selectionStart, end = input.selectionEnd) {
    input.setSelectionRange(start, end);
    // execCommand keeps the browser's undo history; setRangeText is the fallback.
    if (!document.execCommand('insertText', false, text)) {
      input.setRangeText(text, start, end, 'end');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function lineStart(position) {
    return input.value.lastIndexOf('\n', position - 1) + 1;
  }

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (event.shiftKey) controller.check();
      else controller.run();
      return;
    }
    if (event.key === 'Escape') {
      escapePressed = true;
      return;
    }
    if (event.key === 'Tab' && !escapePressed && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      const { selectionStart: start, selectionEnd: end } = input;
      if (event.shiftKey) {
        const begin = lineStart(start);
        const leading = input.value.slice(begin).match(/^ {1,4}/);
        if (leading) {
          replaceSelection('', begin, begin + leading[0].length);
          input.setSelectionRange(Math.max(begin, start - leading[0].length), Math.max(begin, end - leading[0].length));
        }
      } else {
        replaceSelection(INDENT);
      }
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.altKey) {
      // Keep the indentation of the current line, one level deeper after an opening brace.
      event.preventDefault();
      const start = input.selectionStart;
      const line = input.value.slice(lineStart(start), start);
      const indent = line.match(/^ */)[0] + (line.trimEnd().endsWith('{') ? INDENT : '');
      replaceSelection(`\n${indent}`);
    }
    escapePressed = false;
  });

  input.addEventListener('input', () => controller.edit(input.value));

  const syncScroll = () => {
    highlighted.scrollTop = input.scrollTop;
    highlighted.scrollLeft = input.scrollLeft;
    gutter.scrollTop = input.scrollTop;
  };
  input.addEventListener('scroll', syncScroll);

  // Controls

  find('[data-run]').addEventListener('click', () => controller.run());
  find('[data-check]').addEventListener('click', () => controller.check());
  find('[data-copy]').addEventListener('click', () => controller.copy());
  find('[data-reset]').addEventListener('click', () => controller.reset());
  find('[data-undo]').addEventListener('click', () => controller.undo());
  find('[data-dismiss]').addEventListener('click', () => controller.dismissNotice());
  examples.addEventListener('change', () => controller.loadExample(examples.value));

  for (const tab of tabs) {
    tab.addEventListener('click', () => controller.selectTab(tab.dataset.tab));
  }
  find('.pg-tabs').addEventListener('keydown', (event) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    const next = tabs[(tabs.indexOf(document.activeElement) + step + tabs.length) % tabs.length];
    next.focus();
    controller.selectTab(next.dataset.tab);
  });

  if (githubUrl) {
    const link = find('[data-github]');
    link.href = githubUrl;
    link.hidden = false;
  }

  // Rendering

  function renderEditor(state, errorLines) {
    const language = state.info?.language ?? FALLBACK_LANGUAGE;
    if (state.code !== shownCode || language !== shownLanguage) {
      if (input.value !== state.code) input.value = state.code;
      // A final line break needs a character after it, or the last line would not take up space.
      highlighted.innerHTML = `${highlight(state.code, language)}\n`;
      shownCode = state.code;
      shownLanguage = language;
    }
    const lines = state.code.split('\n').length;
    if (gutter.childElementCount !== lines) {
      gutter.replaceChildren(...Array.from({ length: lines }, (_, index) => element('span', 'pg-line', String(index + 1))));
    }
    for (const [index, line] of [...gutter.children].entries()) {
      line.classList.toggle('pg-line--error', errorLines.has(index + 1));
    }
    syncScroll();
  }

  function renderExamples(state) {
    if (state.examples !== shownExamples) {
      examples.replaceChildren(...state.examples.map((example) => {
        const option = element('option', null, example.title);
        option.value = example.id;
        return option;
      }));
      shownExamples = state.examples;
    }
    examples.value = state.origin.id;
    find('[data-description]').textContent = state.origin.description ?? '';
    find('[data-filename]').textContent = state.filename;
  }

  function diagnosticItem(diagnostic) {
    const item = element('li', `pg-diagnostic pg-diagnostic--${diagnostic.category}`);
    const button = element('button', 'pg-diagnostic__go');
    button.type = 'button';

    const head = element('span', 'pg-diagnostic__head');
    head.append(
      element('span', 'pg-diagnostic__category', `${diagnostic.category} error`),
      element('span', 'pg-diagnostic__code', diagnostic.code),
      element('span', 'pg-diagnostic__title', diagnostic.message),
    );
    if (diagnostic.line !== null) {
      head.append(element('span', 'pg-diagnostic__where', `line ${diagnostic.line}, column ${diagnostic.column}`));
    }
    button.append(head, element('span', 'pg-diagnostic__label', diagnostic.label));
    for (const note of diagnostic.notes) button.append(element('span', 'pg-diagnostic__note', `note: ${note}`));
    if (diagnostic.hint) button.append(element('span', 'pg-diagnostic__hint', `hint: ${diagnostic.hint}`));

    if (diagnostic.line === null) {
      button.disabled = true;
    } else {
      button.title = 'Show this position in the editor';
      button.addEventListener('click', () => {
        const start = offsetOf(input.value, diagnostic.line, diagnostic.column);
        const end = offsetOf(input.value, diagnostic.end_line, diagnostic.end_column);
        input.focus();
        input.setSelectionRange(start, Math.max(start, end));
      });
    }
    item.append(button);
    return item;
  }

  function renderResults(state) {
    const result = state.outcome?.kind === 'result' ? state.outcome.result : null;
    const diagnostics = result?.diagnostics ?? [];

    if (state.outcome !== shownOutcome) {
      const ran = result !== null && result.action === 'run' && result.status !== 'invalid';
      const empty = find('[data-output-empty]');
      output.hidden = !(ran && result.output !== '');
      // Program output is text. textContent never interprets it as markup.
      output.textContent = ran ? result.output : '';
      empty.hidden = !output.hidden;
      if (state.outcome === null) {
        empty.textContent = 'Nothing has been run yet. Press Run to execute the program.';
      } else if (result === null) {
        empty.textContent = 'There is no output: the request did not reach the interpreter.';
      } else if (result.action === 'check') {
        empty.textContent = 'Check does not run the program, so there is no output. Press Run to execute it.';
      } else if (result.status === 'invalid') {
        empty.textContent = 'The program has errors and was not run. See Diagnostics.';
      } else {
        empty.textContent = 'The program did not print anything.';
      }

      diagnosticsList.replaceChildren(...diagnostics.map(diagnosticItem));
      const none = find('[data-diagnostics-empty]');
      none.hidden = diagnostics.length > 0;
      none.textContent = result === null
        ? 'No diagnostics yet. Press Check to analyse the program without running it.'
        : 'No diagnostics: the interpreter found no problems.';
      shownOutcome = state.outcome;
    }

    const count = find('[data-count]');
    count.hidden = diagnostics.length === 0;
    count.textContent = String(diagnostics.length);
    find('[data-stale]').hidden = diagnostics.length === 0 || state.outcomeIsCurrent;

    for (const tab of tabs) {
      const selected = tab.dataset.tab === state.tab;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      find(`[data-panel="${tab.dataset.tab}"]`).hidden = !selected;
    }
  }

  function renderChrome(state) {
    const busy = state.busy !== null;
    const run = find('[data-run]');
    const check = find('[data-check]');
    run.disabled = busy || !state.ready;
    check.disabled = busy || !state.ready;
    find('[data-reset]').disabled = busy;
    examples.disabled = busy;
    run.classList.toggle('is-loading', state.busy === 'run');
    check.classList.toggle('is-loading', state.busy === 'check');
    find('[data-run-label]').textContent = state.busy === 'run' ? 'Running' : 'Run';
    find('[data-check-label]').textContent = state.busy === 'check' ? 'Checking' : 'Check';
    find('[data-spinner]').hidden = !busy;
    root.setAttribute('aria-busy', String(busy));

    const status = find('[data-status]');
    status.textContent = state.status.text;
    status.dataset.tone = state.status.tone;

    const notice = find('[data-notice]');
    notice.hidden = state.notice === null;
    find('[data-notice-text]').textContent = state.notice?.text ?? '';
    find('[data-undo]').hidden = !state.notice?.undo;

    const version = find('[data-version]');
    version.hidden = !state.info?.version;
    version.textContent = state.info?.version ? `v${state.info.version}` : '';

    const limits = state.info?.limits;
    find('[data-limits]').textContent = limits
      ? `, for at most ${limits.timeout_ms / 1000} seconds and ${Math.round(limits.output_bytes / 1024)} KiB of output`
      : '';
  }

  return function render(state) {
    const current = state.outcomeIsCurrent && state.outcome?.kind === 'result' ? state.outcome.result.diagnostics : [];
    const errorLines = new Set(current.map((diagnostic) => diagnostic.line).filter((line) => line !== null));
    renderEditor(state, errorLines);
    renderExamples(state);
    renderResults(state);
    renderChrome(state);
  };
}
