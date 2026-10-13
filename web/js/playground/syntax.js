// Syntax highlighting for the playground editor. Returns escaped HTML.
//
// This is colouring, not parsing: it knows the words of the language, not its grammar, and it
// never decides whether a program is valid. That is the job of the real interpreter on the server.
// The word lists are replaced at start-up by the ones the language core reports (/api/playground/info);
// the lists below are the fallback for when the server cannot be reached.

export const FALLBACK_LANGUAGE = Object.freeze({
  keywords: ['and', 'else', 'ensures', 'false', 'fn', 'if', 'let', 'not', 'or', 'requires', 'return', 'true'],
  types: ['Void', 'Int', 'Float', 'Bool', 'Text'],
  builtins: ['print', 'to_float', 'to_int', 'to_text'],
  reserved_words: [
    'ai', 'assert', 'break', 'const', 'continue', 'enum', 'example', 'for', 'import', 'in', 'match', 'pub',
    'test', 'tool', 'try', 'type', 'uses', 'var', 'where', 'while',
  ],
});

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Group order: comment, text, number, word, operator.
const TOKEN = /(\/\/[^\n]*)|("(?:\\.|[^"\\\n])*"?)|(\b\d[\d_]*(?:\.\d[\d_]*)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(->|==|!=|<=|>=|[-+*/<>=])/g;

/**
 * @param {string} source
 * @param {{ keywords: string[], types: string[], builtins: string[], reserved_words: string[] }} [language]
 */
export function highlight(source, language = FALLBACK_LANGUAGE) {
  const keywords = new Set(language.keywords);
  const types = new Set(language.types);
  const builtins = new Set(language.builtins);
  const reserved = new Set(language.reserved_words);

  let html = '';
  let last = 0;
  for (const match of source.matchAll(TOKEN)) {
    const [text, comment, string, number, word, operator] = match;
    let kind = null;
    if (comment !== undefined) kind = 'com';
    else if (string !== undefined) kind = 'str';
    else if (number !== undefined) kind = 'num';
    else if (operator !== undefined) kind = 'op';
    else if (keywords.has(word)) kind = 'kw';
    else if (types.has(word)) kind = 'type';
    else if (builtins.has(word)) kind = 'builtin';
    else if (reserved.has(word)) kind = 'reserved';
    else if (source[match.index + text.length] === '(') kind = 'fn';

    html += escapeHtml(source.slice(last, match.index));
    html += kind ? `<span class="tok-${kind}">${escapeHtml(text)}</span>` : escapeHtml(text);
    last = match.index + text.length;
  }
  return html + escapeHtml(source.slice(last));
}
