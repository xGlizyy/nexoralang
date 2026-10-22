// La extensión para Visual Studio Code en la portada: el logotipo hecho de puntos y el comando que
// la instala.
//
// Lo que se comprueba es lo que puede romperse sin que nadie se dé cuenta: que la página y el módulo
// estén unidos, que el comando diga la extensión de verdad (con su nombre y su versión), y que el
// roadmap no siga anunciando como futuro lo que ya existe.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';
import { repo } from './helpers.js';

const web = path.join(repo, 'web');
const read = (name) => readFileSync(path.join(web, name), 'utf8');

const index = read('index.html');
const config = read('js/config.js');
const module_ = read('js/vscode-dots.js');
const main = read('js/main.js');
const styles = read('styles.css');
const legal = read('aviso-legal.html');
const manifest = JSON.parse(readFileSync(path.join(repo, 'vscode-nexora', 'package.json'), 'utf8'));

// Cómo se dicen los números en el roadmap, para que el sitio no diga una cosa y el repositorio otra.
const NUMBER_WORDS = {
  13: 'Thirteen', 14: 'Fourteen', 15: 'Fifteen', 16: 'Sixteen', 17: 'Seventeen',
  18: 'Eighteen', 19: 'Nineteen', 20: 'Twenty',
};

describe('the extension in the landing', () => {
  test('the logo is in the hero, right next to the install window', () => {
    const hero = index.slice(index.indexOf('<section class="hero">'), index.indexOf('<section class="statement">'));
    assert.match(hero, /class="hero__vscode" data-vscode-dots/);
    assert.match(hero, /class="vscode-dots" type="button"/);
    assert.match(hero, /<svg class="vscode-dots__svg" viewBox="0 0 96 96"/);
  });

  test('the section that was below is gone', () => {
    assert.doesNotMatch(index, /<section class="section" id="editor">/);
    assert.doesNotMatch(styles, /\.editor-layout/);
  });

  test('the module is called by the landing', () => {
    assert.match(main, /import \{ mountVscodeDots \} from '\.\/vscode-dots\.js';/);
    assert.match(main, /mountVscodeDots\(\);/);
  });

  test('the module draws the dots with the silhouette of Visual Studio Code', () => {
    // The path is the one of the icon of Visual Studio Code itself (microsoft/vscode, MIT).
    assert.match(module_, /M65\.566 89\.4264/);
    // And the inner triangle is a hole: the rule `evenodd` is the one its own icon uses.
    assert.match(module_, /context\.fill\(new Path2D\(LOGO\.path\), 'evenodd'\)/);
  });

  test('the logo copies the command when it is clicked', () => {
    assert.match(module_, /data-command/);
    assert.match(module_, /copyText/);
    assert.match(module_, /container\.addEventListener\('click'/);
    // And it says so, with a small note.
    assert.match(index, /data-vscode-hint/);
    assert.match(module_, /is-shown/);
  });

  test('the styles say what the page asks for', () => {
    for (const selector of ['.hero__vscode', '.vscode-dots', '.vscode-dots__dot', '.vscode-dots__hint']) {
      assert.ok(styles.includes(selector), selector);
    }
    // The command is not shown in a box: the logo copies it.
    assert.doesNotMatch(styles, /\.vscode-command/);
    assert.doesNotMatch(index, /vscode-command/);
  });

  test('the logo has no frame around it, and no label of its own', () => {
    // The logo is the logo: nothing is drawn around it.
    const bloque = styles.slice(styles.indexOf('.vscode-dots {'), styles.indexOf('.vscode-dots__svg'));
    assert.doesNotMatch(bloque, /border:\s*1px/);
    assert.doesNotMatch(bloque, /background:\s*rgba/);
    // And the page does not put a title next to it.
    assert.doesNotMatch(index, /hero__editor-title/);
  });
});

describe('the command that installs the extension', () => {
  test('it names the extension and its version, as the manifest has them', () => {
    const command = `code --install-extension vscode-nexora/${manifest.name}-${manifest.version}.vsix`;
    assert.ok(index.includes(command), command);
  });

  test('the logo carries that command', () => {
    const contenedor = index.slice(index.indexOf('class="hero__vscode"'), index.indexOf('class="hero__vscode"') + 300);
    const command = `code --install-extension vscode-nexora/${manifest.name}-${manifest.version}.vsix`;
    assert.match(contenedor, new RegExp(`data-command="${command}"`));
  });
});

describe('the roadmap tells the truth', () => {
  const tooling = config.slice(config.indexOf("title: 'Tooling and documentation'"));
  const phase = tooling.slice(0, tooling.indexOf('},'));

  test('the extension and the formatter are already available, not promised', () => {
    const available = phase.slice(phase.indexOf('available:'), phase.indexOf('next:'));
    const next = phase.slice(phase.indexOf('next:'));
    assert.match(available, /Visual Studio Code extension with a language server/);
    assert.match(available, /A formatter for the language/);
    // What may still come is other editors, using the same server; what may not is promising
    // again the extension or the formatter, which already exist.
    assert.doesNotMatch(next, /A formatter/i);
    assert.doesNotMatch(next, /Visual Studio Code/);
  });

  test('the number of design records is the number there are', () => {
    const decisions = readFileSync(path.join(repo, 'nexora', 'docs', 'decisions', 'README.md'), 'utf8');
    const rows = (decisions.match(/^\| \[00\d\d\]/gm) ?? []).length;
    assert.ok(NUMBER_WORDS[rows], `the site does not know how to say ${rows}`);
    assert.ok(config.includes(`${NUMBER_WORDS[rows]} accepted design records`), `${rows} design records`);
  });
});

describe('the legal notice', () => {
  test('it says that the Visual Studio Code logo belongs to Microsoft', () => {
    assert.match(legal, /Visual Studio Code/);
    assert.match(legal, /marca registrada de Microsoft Corporation/);
  });
});
