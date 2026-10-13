// Playground. Without a runtime it stays a read-only preview; with one it becomes an editor that runs code.

import { sourceOf } from './code-window.js';

/**
 * @param {import('./config.js').PlaygroundRuntime | null} runtime
 */
export function mountPlayground(runtime) {
  const root = document.querySelector('[data-playground]');
  if (!root || !runtime) return;

  const editor = root.querySelector('[data-playground-editor]');
  const output = root.querySelector('[data-playground-output]');

  const input = document.createElement('textarea');
  input.className = 'playground__input';
  input.spellcheck = false;
  input.setAttribute('aria-label', 'NEXORA source code');
  input.value = sourceOf(editor.querySelector('code'));
  editor.replaceChildren(input);

  const run = document.createElement('button');
  run.type = 'button';
  run.className = 'copy';
  run.textContent = 'Run';
  run.addEventListener('click', async () => {
    run.disabled = true;
    try {
      output.textContent = await runtime.run(input.value);
    } catch (error) {
      output.textContent = String(error?.message ?? error);
    } finally {
      run.disabled = false;
    }
  });

  root.querySelector('[data-playground-flag]').replaceWith(run);
  output.classList.add('playground__message--result');
  output.textContent = '';
}
