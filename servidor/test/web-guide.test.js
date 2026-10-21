// Los programas de la guía del lenguaje (web/guide.html) y los enlaces del playground.
// Cada ejemplo de la guía se ejecuta con el intérprete real y se compara con la salida que muestra la página.

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { repo, startServer } from './helpers.js';

const web = path.join(repo, 'web');
const read = (name) => readFileSync(path.join(web, name), 'utf8');
const decode = (html) => html.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');

const guide = read('guide.html');
const EXAMPLE = /<pre class="code" data-example="([\w-]+)"([^>]*)><code>([\s\S]*?)<\/code><\/pre>\s*<div class="guide-output[^"]*"><pre[^>]*>([\s\S]*?)<\/pre>/g;
const examples = [...guide.matchAll(EXAMPLE)].map(([, kind, attributes, code, shown]) => ({
  kind, attributes, code: decode(code), shown: decode(shown),
}));

describe('language guide', () => {
  let server;
  before(async () => { server = await startServer(); });
  after(() => server.close());

  test('the guide has examples, and no code block escapes the check', () => {
    assert.ok(examples.length >= 7);
    assert.equal(examples.length, (guide.match(/<pre class="code"/g) ?? []).length);
  });

  for (const [index, example] of examples.entries()) {
    test(`example ${index + 1} (${example.kind}) behaves as the page says`, async () => {
      if (example.kind === 'run') {
        const { json } = await server.run(example.code);
        assert.equal(json.status, 'success', JSON.stringify(json.diagnostics));
        assert.equal(json.output, `${example.shown}\n`);
      } else {
        assert.equal(example.kind, 'check-fails');
        const { json } = await server.check(example.code);
        assert.equal(json.status, 'invalid');
        const [diagnostic] = json.diagnostics;
        assert.equal(diagnostic.code, example.attributes.match(/data-code="(E\d{4})"/)[1]);
        assert.equal(String(diagnostic.line), example.attributes.match(/data-line="(\d+)"/)[1]);
        // Lo que la página muestra del diagnóstico es lo que el intérprete dice.
        assert.ok(example.shown.includes(`${diagnostic.category} error[${diagnostic.code}]: ${diagnostic.message}`));
        assert.ok(example.shown.includes(`line ${diagnostic.line}, column ${diagnostic.column}: ${diagnostic.label}`));
      }
    });
  }

  test('the guide names the version it describes', async () => {
    const { json } = await server.call('/info');
    assert.ok(guide.includes(`version ${json.version.split('.').slice(0, 2).join('.')}`));
  });
});

describe('links between the pages of the site', () => {
  const pages = [
    'index.html', 'docs.html', 'playground.html', 'guide.html', 'login.html', 'signup.html',
    'aviso-legal.html', 'privacidad.html', 'cookies.html', 'terminos.html',
  ];

  for (const page of pages) {
    test(`${page}: every local link points to a page and an anchor that exist`, () => {
      const html = read(page);
      for (const [, target] of html.matchAll(/href="([^"#:]*)(?:#[^"]*)?"/g)) {
        if (target === '' || target.startsWith('/api/') || target.startsWith('..')) continue;
        assert.ok(existsSync(path.join(web, target)), `${page} links to missing ${target}`);
      }
      for (const [, target, anchor] of html.matchAll(/href="([^"#:]*)#([^"]+)"/g)) {
        const destination = target === '' ? html : read(target);
        assert.ok(destination.includes(`id="${anchor}"`), `${page} links to missing #${anchor} in ${target || page}`);
      }
    });
  }

  test('the playground links to every topic of the guide it promises', () => {
    const playground = read('playground.html');
    for (const topic of ['introduction', 'syntax', 'types', 'operators', 'functions', 'lists', 'diagnostics', 'limitations']) {
      assert.ok(playground.includes(`guide.html#${topic}`), topic);
    }
  });

  // The outline in the header is what turns the documentation into one page per section, so it has
  // to name exactly the sections of docs.html, in the same order, on every page that carries it.
  const OUTLINE = /<li><a href="docs\.html#([\w-]+)"><span>(\d+)<\/span><strong>([^<]+)<\/strong>/g;

  test('the documentation has one section per entry of its own index', () => {
    const sections = [...read('docs.html').matchAll(/<section id="([\w-]+)">/g)].map(([, id]) => id);
    assert.ok(sections.length >= 2);
    const toc = read('docs.html').match(/<nav class="docs__toc"[\s\S]*?<\/nav>/)[0];
    const index = [...toc.matchAll(/<li><a href="#([\w-]+)">/g)].map(([, id]) => id);
    assert.deepEqual(index, sections);
  });

  for (const page of ['index.html', 'docs.html']) {
    test(`${page}: the Documentation outline lists every section, in order`, () => {
      // The outline may shorten a title ("FAQ"), so what has to match is which sections it names,
      // in which order, and the number each one is given.
      const ids = [...read('docs.html').matchAll(/<section id="([\w-]+)">/g)].map(([, id]) => id);
      const outline = [...read(page).matchAll(OUTLINE)].map(([, id, number]) => [id, number]);
      assert.deepEqual(outline, ids.map((id, index) => [id, String(index + 1).padStart(2, '0')]));
    });
  }

  test('the home page and the documentation lead to the playground', () => {
    assert.ok(read('index.html').includes('href="playground.html"'));
    assert.ok(read('docs.html').includes('href="playground.html"'));
  });

  test('every page links to the legal pages and can reopen the cookie preferences', () => {
    for (const page of pages) {
      const html = read(page);
      for (const legal of ['aviso-legal.html', 'privacidad.html', 'cookies.html', 'terminos.html']) {
        assert.ok(html.includes(`href="${legal}"`), `${page} does not link to ${legal}`);
      }
      assert.ok(html.includes('data-consent-open'), `${page} has no way to reopen the cookie preferences`);
      // The consent manager runs first, before any other script of the page.
      const scripts = [...html.matchAll(/<script[^>]*\bsrc="([^"]+)"/g)].map(([, src]) => src);
      assert.deepEqual(scripts.slice(0, 2), ['js/consent-config.js', 'js/consent.js'], page);
    }
  });

  // Data the owner still has to provide ([NIF O CIF], [DOMINIO]…) may only appear in the legal pages,
  // which say at the top that they are a draft; never in a page that presents itself as finished.
  test('only the legal drafts show data still to be provided, and they say they are drafts', () => {
    const PENDING = /class="placeholder"|\[[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,}\]/;
    const drafts = ['aviso-legal.html', 'privacidad.html', 'cookies.html', 'terminos.html'];
    for (const page of pages) {
      const html = read(page);
      if (!drafts.includes(page)) {
        assert.doesNotMatch(html, PENDING, `${page} shows data still to be provided`);
      } else if (PENDING.test(html)) {
        assert.ok(html.includes('Borrador pendiente de completar y de revisión jurídica'), `${page} does not say it is a draft`);
      }
    }
  });

  // While a legal page is a draft, it asks search engines not to index it or follow its links. That
  // is a request, not access control: anyone with the address can still open it.
  test('the legal drafts ask search engines not to index them', () => {
    const NOINDEX = /<meta name="robots" content="noindex, nofollow">/;
    for (const page of ['aviso-legal.html', 'privacidad.html', 'cookies.html', 'terminos.html']) {
      const html = read(page);
      if (html.includes('Borrador pendiente de completar y de revisión jurídica')) {
        assert.match(html, NOINDEX, `${page} is a draft and can be indexed`);
      }
    }
  });

  test('the playground page loads no script or style from outside the site, and has none inline', () => {
    for (const page of ['playground.html', 'guide.html']) {
      const html = read(page);
      assert.doesNotMatch(html, /<script(?![^>]*\bsrc="js\/)[^>]*>/, `${page} has an inline or external script`);
      assert.doesNotMatch(html, /\sstyle="/, `${page} has an inline style`);
      assert.doesNotMatch(html, /\son\w+="/, `${page} has an inline event handler`);
    }
  });

  // The fonts are served from the site itself, so loading a page sends nothing to a third party.
  test('no page loads a stylesheet or a font from another site, and every font file exists', () => {
    for (const page of pages) {
      const html = read(page);
      for (const [tag] of html.matchAll(/<link\b[^>]*>/g)) {
        assert.doesNotMatch(tag, /href="(https?:)?\/\//, `${page} links to another site: ${tag}`);
      }
    }
    const css = read('styles.css');
    assert.doesNotMatch(css, /@import/);
    const fonts = [...css.matchAll(/@font-face\s*\{[^}]*?src:\s*url\("([^"]+)"\)/g)].map(([, url]) => url);
    assert.ok(fonts.length > 0, 'styles.css declares its fonts');
    for (const url of fonts) {
      assert.ok(!/^(https?:)?\/\//.test(url), `font from another site: ${url}`);
      assert.ok(existsSync(path.join(web, url)), `missing font file ${url}`);
    }
    assert.ok(existsSync(path.join(web, 'fonts', 'jetbrains-mono', 'OFL.txt')), 'the font licence travels with the font');
  });
});
