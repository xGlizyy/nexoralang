// Language guide: colours the code examples with the same highlighter as the playground
// and shows one section at a time.

import { highlight } from './playground/syntax.js';
import { setupDocsPages } from './docs-pages.js';
import { setupSiteHeader } from './site-header.js';

document.documentElement.classList.add('js');
setupSiteHeader();

for (const code of document.querySelectorAll('[data-example] > code')) {
  code.innerHTML = highlight(code.textContent)
    .split('\n')
    .map((line) => `<span class="line">${line}</span>`)
    .join('');
}

// Each section is a page of its own; the outline is in the Documentation menu of the header.
setupDocsPages();
