// Language guide: colours the code examples with the same highlighter as the playground.

import { highlight } from './playground/syntax.js';

for (const code of document.querySelectorAll('[data-example] > code')) {
  code.innerHTML = highlight(code.textContent)
    .split('\n')
    .map((line) => `<span class="line">${line}</span>`)
    .join('');
}
