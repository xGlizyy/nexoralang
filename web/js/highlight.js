// Syntax highlighting for NEXORA snippets. Returns escaped HTML.

const KEYWORDS = [
  'ai', 'and', 'assert', 'break', 'const', 'continue', 'else', 'ensures',
  'enum', 'example', 'false', 'fn', 'for', 'if', 'import', 'in',
  'let', 'match', 'not', 'or', 'pub', 'requires', 'return', 'test',
  'tool', 'true', 'try', 'type', 'uses', 'var', 'where', 'while',
];

// Group order: comment, string, number, keyword, type, call.
const TOKEN = new RegExp(
  [
    '(\\/\\/[^\\n]*)',
    '("(?:\\\\.|[^"\\\\])*")',
    '\\b(\\d[\\d_]*(?:\\.\\d+)?)\\b',
    `\\b(${KEYWORDS.join('|')})\\b`,
    '\\b([A-Z][A-Za-z0-9]*)\\b',
    '\\b([a-z_][a-z0-9_]*)(?=\\()',
  ].join('|'),
  'g',
);

const TOKEN_CLASSES = ['com', 'str', 'num', 'kw', 'type', 'fn'];

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** @param {string} source */
export function highlight(source) {
  let html = '';
  let last = 0;
  for (const match of source.matchAll(TOKEN)) {
    const group = match.slice(1).findIndex((part) => part !== undefined);
    html += escapeHtml(source.slice(last, match.index));
    html += `<span class="tok-${TOKEN_CLASSES[group]}">${escapeHtml(match[0])}</span>`;
    last = match.index + match[0].length;
  }
  return html + escapeHtml(source.slice(last));
}
