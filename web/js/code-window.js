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
  // Only NEXORA is highlighted; anything else (shell commands) is shown as plain text.
  const html = code.dataset.lang === 'nex' ? highlight(source) : code.innerHTML.replace(/\n+$/, '');
  code.innerHTML = html
    .split('\n')
    .map((line) => `<span class="line">${line}</span>`)
    .join('');
}

/**
 * Copies text to the clipboard. Returns whether it could be copied.
 * @param {string} text
 * @returns {Promise<boolean>}
 */
export async function copyText(text) {
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
  const list = root.querySelector('[role="tablist"]');
  // Tab lists marked --slide have one short underline that glides to the selected tab.
  const slides = list.classList.contains('window__tabs--slide');

  function placeIndicator(tab) {
    list.style.setProperty('--ind-x', `${tab.offsetLeft + tab.offsetWidth * 0.25}px`);
    list.style.setProperty('--ind-w', `${tab.offsetWidth * 0.5}px`);
  }

  function select(tab) {
    for (const other of tabs) {
      const active = other === tab;
      other.setAttribute('aria-selected', String(active));
      other.tabIndex = active ? 0 : -1;
      document.getElementById(other.getAttribute('aria-controls')).hidden = !active;
    }
    if (slides) placeIndicator(tab);
  }

  if (slides) {
    // Widths change once the web fonts load: re-place without animating. The tabs are observed
    // too, because a tab can change width while the list keeps its own.
    const observer = new ResizeObserver(() => {
      list.classList.add('is-jumping');
      placeIndicator(tabs.find((tab) => tab.getAttribute('aria-selected') === 'true'));
      void list.offsetWidth;
      list.classList.remove('is-jumping');
    });
    observer.observe(list);
    for (const tab of tabs) observer.observe(tab);
  }

  for (const tab of tabs) {
    tab.addEventListener('click', () => select(tab));
  }

  list.addEventListener('keydown', (event) => {
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
