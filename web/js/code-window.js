// Editor-style code windows: highlighting, line numbers, file tabs and copy to clipboard.

import { highlight } from './highlight.js';

/** @type {WeakMap<Element, string>} */
const sources = new WeakMap();

/** Original source of a rendered code block. */
export function sourceOf(code) {
  return sources.get(code) ?? code.textContent;
}

function renderCode(code) {
  const source = code.textContent.replace(/\n+$/, '');
  sources.set(code, source);
  code.innerHTML = highlight(source)
    .split('\n')
    .map((line) => `<span class="line">${line}</span>`)
    .join('');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // navigator.clipboard is unavailable on plain http; fall back to a hidden textarea.
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    return copied;
  }
}

function setupTabs(root) {
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  if (tabs.length === 0) return;

  function select(tab) {
    for (const other of tabs) {
      const active = other === tab;
      other.setAttribute('aria-selected', String(active));
      other.tabIndex = active ? 0 : -1;
      document.getElementById(other.getAttribute('aria-controls')).hidden = !active;
    }
  }

  for (const tab of tabs) {
    tab.addEventListener('click', () => select(tab));
  }

  root.querySelector('[role="tablist"]').addEventListener('keydown', (event) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    const next = tabs[(tabs.indexOf(document.activeElement) + step + tabs.length) % tabs.length];
    next.focus();
    select(next);
  });
}

function setupCopy(root) {
  const button = root.querySelector('[data-copy]');
  if (!button) return;
  const label = button.querySelector('[data-copy-label]');

  button.addEventListener('click', async () => {
    const visible = [...root.querySelectorAll('code[data-lang]')].find((code) => !code.closest('[hidden]'));
    const copied = await copyText(sourceOf(visible));
    label.textContent = copied ? 'Copied' : 'Copy failed';
    setTimeout(() => { label.textContent = 'Copy'; }, 1800);
  });
}

export function mountCodeWindows() {
  for (const code of document.querySelectorAll('code[data-lang]')) renderCode(code);
  for (const root of document.querySelectorAll('[data-code-window]')) {
    setupTabs(root);
    setupCopy(root);
  }
}
