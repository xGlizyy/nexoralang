// Un DOM mínimo para ejecutar web/js/consent.js y web/js/auth.js en Node, sin navegador ni
// dependencias. Solo tiene lo que esos scripts usan: elementos, atributos, selectores sencillos
// (etiqueta, #id, .clase, [atributo], [atributo="valor"], compuestos y con descendiente), eventos,
// <dialog>, document.cookie, localStorage, dataset, el valor de los <input> y FormData. No pretende ser
// un navegador: lo que no está aquí, esos scripts no lo usan.

import { readFileSync } from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = document;
    this.attributes = [];
    this.childNodes = [];
    this.parentNode = null;
    this.listeners = {};
    this._text = '';
  }

  getAttribute(name) { return this.attributes.find((a) => a.name === name)?.value ?? null; }
  hasAttribute(name) { return this.attributes.some((a) => a.name === name); }
  setAttribute(name, value) {
    const attribute = this.attributes.find((a) => a.name === name);
    if (attribute) attribute.value = String(value);
    else this.attributes.push({ name, value: String(value) });
  }
  removeAttribute(name) { this.attributes = this.attributes.filter((a) => a.name !== name); }

  get id() { return this.getAttribute('id') ?? ''; }
  // Reflected like in a browser: setting the property sets the attribute.
  get src() { return this.getAttribute('src') ?? ''; }
  set src(value) { this.setAttribute('src', value); }
  get hidden() { return this.hasAttribute('hidden'); }
  set hidden(value) { if (value) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); }
  get open() { return this.hasAttribute('open'); }
  get children() { return this.childNodes.filter((node) => node instanceof Element); }
  get firstChild() { return this.childNodes[0] ?? null; }

  get textContent() { return this._text + this.childNodes.map((node) => node.textContent).join(''); }
  set textContent(value) { this.childNodes = []; this._text = String(value); }
  get text() { return this.textContent; }
  set text(value) { this.textContent = value; }

  appendChild(node) { return this.insertBefore(node, null); }
  insertBefore(node, reference) {
    node.parentNode?.removeChild(node);
    const index = reference ? this.childNodes.indexOf(reference) : -1;
    if (index === -1) this.childNodes.push(node); else this.childNodes.splice(index, 0, node);
    node.parentNode = this;
    this.ownerDocument.inserted(node);
    return node;
  }
  removeChild(node) {
    this.childNodes = this.childNodes.filter((child) => child !== node);
    node.parentNode = null;
    return node;
  }
  replaceChild(node, old) {
    this.insertBefore(node, old);
    return this.removeChild(old);
  }
  remove() { this.parentNode?.removeChild(this); }
  contains(node) {
    for (let current = node; current; current = current.parentNode) if (current === this) return true;
    return false;
  }

  matches(selector) { return matchesSelector(this, selector); }
  closest(selector) {
    for (let current = this; current instanceof Element; current = current.parentNode) {
      if (current.matches(selector)) return current;
    }
    return null;
  }
  querySelectorAll(selector) {
    const found = [];
    const walk = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }

  addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); }
  dispatchEvent(event) {
    for (const listener of this.listeners[event.type] ?? []) listener.call(this, event);
    return true;
  }
  focus() { this.ownerDocument.activeElement = this; }

  // <dialog>
  showModal() { this.setAttribute('open', ''); }
  close() {
    if (!this.open) return;
    this.removeAttribute('open');
    this.dispatchEvent({ type: 'close', target: this });
  }

  // <input type="checkbox">
  get checked() { return this.hasAttribute('data-checked'); }
  set checked(value) { if (value) this.setAttribute('data-checked', ''); else this.removeAttribute('data-checked'); }

  // <input> (for auth.js): its value, from the value attribute.
  get value() { return this.getAttribute('value') ?? ''; }
  set value(value) { this.setAttribute('value', value); }

  // The data-* attributes, as the camelCase properties of element.dataset (read only here).
  get dataset() {
    const data = {};
    for (const { name, value } of this.attributes) {
      if (name.startsWith('data-')) data[name.slice(5).replace(/-([a-z])/g, (match, letter) => letter.toUpperCase())] = value;
    }
    return data;
  }
}

// new FormData(form), as auth.js uses it: the [name, value] pairs of the named inputs inside the form.
class FormData {
  constructor(form) {
    this.pairs = form.querySelectorAll('input')
      .filter((input) => input.getAttribute('name') && !input.hasAttribute('disabled'))
      .map((input) => [input.getAttribute('name'), input.value]);
  }

  [Symbol.iterator]() { return this.pairs[Symbol.iterator](); }
}

class Text {
  constructor(text) { this.textContent = text; this.parentNode = null; }
}

// Selectores: una lista de partes compuestas separadas por espacios (descendiente).
function parseCompound(text) {
  const parts = { tag: null, conditions: [] };
  const pattern = /^([a-z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/gi;
  let match;
  let consumed = 0;
  while ((match = pattern.exec(text)) && match.index === consumed) {
    consumed += match[0].length;
    if (match[1]) parts.tag = match[1].toUpperCase();
    else if (match[2]) parts.conditions.push((el) => el.id === match[2]);
    else if (match[3]) { const name = match[3]; parts.conditions.push((el) => (el.getAttribute('class') ?? '').split(/\s+/).includes(name)); }
    else { const [, , , , name, value] = match; parts.conditions.push((el) => (value === undefined ? el.hasAttribute(name) : el.getAttribute(name) === value)); }
    pattern.lastIndex = consumed;
    if (consumed === text.length) break;
  }
  if (consumed !== text.length) throw new Error(`mini-dom: unsupported selector "${text}"`);
  return (el) => (!parts.tag || el.tagName === parts.tag) && parts.conditions.every((condition) => condition(el));
}

function matchesSelector(element, selector) {
  const steps = selector.trim().split(/\s+/).map(parseCompound);
  if (!steps.at(-1)(element)) return false;
  let current = element.parentNode;
  for (let index = steps.length - 2; index >= 0; index -= 1) {
    while (current instanceof Element && !steps[index](current)) current = current.parentNode;
    if (!(current instanceof Element)) return false;
    current = current.parentNode;
  }
  return true;
}

class Document {
  constructor({ hostname }) {
    this.readyState = 'loading';
    this.listeners = {};
    this.activeElement = null;
    this.added = []; // every element ever inserted, in order (to see which scripts were added)
    this.jar = new Map();
    this.hostname = hostname;
    this.documentElement = new Element('html', this);
    this.head = this.documentElement.appendChild(new Element('head', this));
    this.body = this.documentElement.appendChild(new Element('body', this));
  }

  inserted(node) { if (node instanceof Element) this.added.push(node); }
  createElement(tag) { return new Element(tag, this); }
  createTextNode(text) { return new Text(text); }
  querySelector(selector) { return this.documentElement.querySelector(selector); }
  querySelectorAll(selector) { return this.documentElement.querySelectorAll(selector); }
  contains(node) { return this.documentElement.contains(node); }
  addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); }
  dispatch(type, event = {}) { for (const listener of this.listeners[type] ?? []) listener({ type, ...event }); }

  get cookie() { return [...this.jar].map(([name, value]) => `${name}=${value}`).join('; '); }
  set cookie(text) {
    const [pair, ...attributes] = text.split(';').map((part) => part.trim());
    const [name, value] = pair.split('=');
    const expires = attributes.find((part) => /^expires=/i.test(part));
    const domain = attributes.find((part) => /^domain=/i.test(part))?.slice(7);
    // A cookie can only be set for this host or a parent domain of it.
    if (domain && !(`.${this.hostname}`.endsWith(`.${domain.replace(/^\./, '')}`))) return;
    if (expires && Date.parse(expires.slice(8)) < Date.now()) this.jar.delete(name);
    else this.jar.set(name, value);
  }
}

/**
 * Carga consent-config (el objeto `config`) y web/js/consent.js en un contexto aislado, con el
 * documento todavía cargando. `finishLoading()` simula el fin del análisis de la página.
 */
export function loadConsent({ config, build = () => {}, stored = null, storage = 'ok', hostname = 'nexora.test', grecaptcha } = {}) {
  const document = new Document({ hostname });
  build(document, (tag, attributes = {}, text) => {
    const element = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    if (text) element.textContent = text;
    return element;
  });
  const store = new Map(stored === null ? [] : [['nexora.consent', typeof stored === 'string' ? stored : JSON.stringify(stored)]]);
  const localStorage = storage === 'blocked'
    ? { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); } }
    : { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => store.set(key, String(value)) };
  const warnings = [];
  const events = [];
  let reloads = 0;
  const window = {
    NEXORA_CONSENT_CONFIG: config,
    document,
    localStorage,
    location: { hostname, reload: () => { reloads += 1; } },
    console: { warn: (line) => warnings.push(line), log() {}, error() {} },
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    Element,
    setTimeout: (...args) => setTimeout(...args),
    clearTimeout: (id) => clearTimeout(id),
    Promise,
    JSON,
    Date,
    isFinite,
    encodeURIComponent,
    grecaptcha,
    dispatchEvent: (event) => { events.push(event); return true; },
    addEventListener() {},
  };
  window.window = window;
  const context = vm.createContext(window);
  vm.runInContext(readFileSync(new URL('../../../web/js/consent.js', import.meta.url), 'utf8'), context, { filename: 'consent.js' });

  return {
    window,
    document,
    store,
    warnings,
    events,
    get reloads() { return reloads; },
    finishLoading() {
      document.readyState = 'interactive';
      document.dispatch('DOMContentLoaded');
    },
    click(element) { document.dispatch('click', { target: element, preventDefault() {} }); },
    /** Las URL de los scripts que el navegador ejecutaría: con src y sin type="text/plain". */
    scripts() { return this.scriptElements().map((el) => el.getAttribute('src')); },
    scriptElements() {
      return document.added.filter((el) => el.tagName === 'SCRIPT' && el.getAttribute('src') && el.getAttribute('type') !== 'text/plain');
    },
    consentCalls() {
      return window.dataLayer.filter((entry) => entry[0] === 'consent').map((entry) => [entry[1], { ...entry[2] }]);
    },
  };
}

/**
 * Carga web/js/auth.js en un contexto aislado, con el documento ya construido por `build` (igual que en
 * loadConsent). Nada sale a la red: cada petición llama a `respond({ path, method, body }, helpers)`,
 * que devuelve `helpers.json(estado, cuerpo)` o lanza `helpers.networkError()`, un TypeError del propio
 * contexto, como el de fetch en un navegador cuando no hay conexión. `consent` hace de
 * window.NexoraConsent (js/consent.js); sin él, la página se comporta como si ese script no estuviera.
 */
export function loadAuth({ build = () => {}, search = '', respond = () => { throw new Error('unexpected request'); }, consent } = {}) {
  const document = new Document({ hostname: 'nexora.test' });
  build(document, (tag, attributes = {}, text) => {
    const element = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    if (text) element.textContent = text;
    return element;
  });
  const requests = [];
  const navigations = [];
  const listeners = {};
  let context;
  const helpers = {
    json: (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body }),
    networkError: () => new (vm.runInContext('TypeError', context))('Failed to fetch'),
  };
  const window = {
    document,
    location: {
      search,
      origin: 'https://nexora.test',
      get href() { return 'https://nexora.test/'; },
      set href(url) { navigations.push(url); },
    },
    history: { length: 1, back() {} },
    console: { log() {}, warn() {}, error() {} },
    URL,
    URLSearchParams,
    FormData,
    NexoraConsent: consent,
    async fetch(path, init = {}) {
      const request = { path, method: init.method, body: init.body ? JSON.parse(init.body) : undefined, credentials: init.credentials };
      requests.push(request);
      return respond(request, helpers);
    },
    addEventListener: (type, listener) => { (listeners[type] ??= []).push(listener); },
    dispatchEvent: (event) => { for (const listener of listeners[event.type] ?? []) listener(event); return true; },
    setTimeout: (...args) => setTimeout(...args),
    clearTimeout: (id) => clearTimeout(id),
  };
  window.window = window;
  context = vm.createContext(window);
  vm.runInContext(readFileSync(new URL('../../../web/js/auth.js', import.meta.url), 'utf8'), context, { filename: 'auth.js' });

  const form = document.querySelector('[data-auth-form]');
  return {
    window,
    document,
    form,
    requests,
    navigations,
    /** Envía el formulario como el navegador y espera a que el manejador de auth.js termine. */
    async submit() {
      const event = { type: 'submit', target: form, preventDefault() {} };
      await Promise.all((form.listeners.submit ?? []).map((listener) => listener.call(form, event)));
    },
    /** Un evento de window, como los que anuncia js/consent.js ('nexora:consent', 'nexora:recaptcha'). */
    announce(type) { window.dispatchEvent({ type }); },
  };
}
