// Gestor de consentimiento de cookies (web/js/consent.js), ejecutado en un DOM mínimo
// (fixtures/mini-dom.js). Comprueba lo que se comprobó a mano en Chrome: qué se carga antes y
// después de decidir, Consent Mode, la retirada, la persistencia y los textos. El aspecto del banner
// y del panel se sigue comprobando a mano en el navegador.

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { describe, test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { loadConsent } from './fixtures/mini-dom.js';

const NONE = { policyVersion: 'test-1', maxAgeDays: 365, google: { analyticsId: null, tagManagerId: null, adsId: null }, recaptchaSiteKey: null };
const SITE_KEY = `6L${'a'.repeat(38)}`;
const ALL = { ...NONE, google: { analyticsId: 'G-TEST1234', tagManagerId: null, adsId: 'AW-123456789' }, recaptchaSiteKey: SITE_KEY };
const GTAG = 'https://www.googletagmanager.com/gtag/js';
const RECAPTCHA = 'https://www.google.com/recaptcha/api.js';

/** Una página con el pie de «Configurar cookies» y, si se pide, un formulario protegido. */
function page(config, options = {}) {
  return loadConsent({
    config,
    build: (document, el) => {
      if (options.form !== false) document.body.appendChild(el('form', { 'data-captcha-action': 'signup' }));
      document.body.appendChild(el('button', { type: 'button', 'data-consent-open': '', hidden: '' }, 'Configurar cookies'));
      for (const script of options.blocked ?? []) document.body.appendChild(el('script', script));
    },
    ...options,
  });
}

const choice = (choices, extra = {}) => ({ version: 'test-1', date: new Date().toISOString(), choices, ...extra });
const external = (consent) => consent.scripts().map((src) => src.replace(/\?.*$/, ''));
const banner = (consent) => consent.document.querySelector('.consent-banner');
const button = (root, action) => root.querySelector(`[data-consent-action="${action}"]`);

describe('before any choice', () => {
  test('every optional Consent Mode signal starts denied, before anything else', () => {
    const consent = page(NONE);
    const [first] = consent.consentCalls();
    assert.deepEqual(first[0], 'default');
    for (const signal of ['analytics_storage', 'ad_storage', 'ad_user_data', 'ad_personalization', 'functionality_storage', 'personalization_storage']) {
      assert.equal(first[1][signal], 'denied', signal);
    }
  });

  test('with no optional service configured the banner still asks to accept the notice', () => {
    const consent = page(NONE);
    consent.finishLoading();
    assert.ok(banner(consent));
    assert.deepEqual(consent.scripts(), []);
    assert.equal(consent.window.NexoraConsent.get(), null);
    assert.equal(consent.document.querySelector('[data-consent-open]').hidden, false, 'the link to the preferences is shown');
    assert.deepEqual(banner(consent).querySelectorAll('button').map((b) => b.textContent), ['Configurar', 'Aceptar']);
    assert.doesNotMatch(banner(consent).textContent, /también usaremos/);
  });

  test('accepting the notice with no optional service stores the choice and loads nothing', () => {
    const consent = page(NONE);
    consent.finishLoading();
    consent.click(button(banner(consent), 'accept'));
    assert.equal(banner(consent), null);
    assert.deepEqual(consent.scripts(), []);
    assert.deepEqual(JSON.parse(consent.store.get('nexora.consent')).choices, { analytics: false, advertising: false, antispam: false });
    const [, update] = consent.consentCalls().at(-1);
    assert.deepEqual(update, { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });
  });

  test('without a stored choice, the banner asks again on the next page', () => {
    const first = page(NONE);
    first.finishLoading();
    assert.ok(banner(first));
    assert.equal(first.store.get('nexora.consent'), undefined, 'nothing was stored');
    const second = page(NONE, { stored: first.store.get('nexora.consent') });
    second.finishLoading();
    assert.ok(banner(second));
  });

  test('with no optional service the preferences only say so, and offer to close', () => {
    const consent = page(NONE);
    consent.finishLoading();
    consent.click(consent.document.querySelector('[data-consent-open]'));
    const panel = consent.document.querySelector('dialog');
    assert.ok(panel.open);
    assert.equal(panel.querySelectorAll('.consent-switch').length, 0);
    assert.deepEqual(panel.querySelectorAll('.consent-panel__actions button').map((b) => b.textContent), ['Cerrar']);
  });

  test('with optional services, a banner asks first and nothing optional is loaded until then', () => {
    const consent = page(ALL);
    consent.finishLoading();
    assert.ok(banner(consent));
    assert.deepEqual(consent.scripts(), []);
    const actions = banner(consent).querySelectorAll('button');
    assert.deepEqual(actions.map((b) => b.textContent), ['Rechazar todas', 'Configurar', 'Aceptar todas']);
    assert.deepEqual(new Set(actions.map((b) => b.getAttribute('class'))).size, 1, 'the three choices look the same');
  });

  test('an ID with the wrong format is ignored and never loaded, but the notice still appears', () => {
    const consent = page({ ...NONE, google: { analyticsId: 'UA-1234-1', tagManagerId: 'GTM-<x>', adsId: null }, recaptchaSiteKey: 'abc' }, { form: true });
    consent.finishLoading();
    assert.ok(banner(consent), 'the notice still asks to acknowledge the necessary cookies');
    assert.equal(consent.warnings.length, 3);
    consent.window.NexoraConsent.acceptAll();
    assert.deepEqual(consent.scripts(), []);
    assert.equal(banner(consent), null);
  });
});

describe('the words of the banner and the panel', () => {
  test('cookies and reCAPTCHA are named for what they are, with correct Spanish', () => {
    const consent = page(ALL);
    consent.finishLoading();
    assert.match(banner(consent).textContent,
      /también usaremos cookies analíticas y publicitarias, y la protección antispam de Google reCAPTCHA\. Puedes aceptarlo todo, rechazarlo todo o elegir;/);
  });

  test('one kind of cookie, or reCAPTCHA alone, reads naturally too', () => {
    const analytics = page({ ...NONE, google: { ...NONE.google, analyticsId: 'G-TEST1234' } }, { form: false });
    analytics.finishLoading();
    assert.match(banner(analytics).textContent, /también usaremos cookies analíticas\. /);
    const recaptcha = page({ ...NONE, recaptchaSiteKey: SITE_KEY });
    recaptcha.finishLoading();
    assert.match(banner(recaptcha).textContent, /también usaremos la protección antispam de Google reCAPTCHA\. /);
    assert.doesNotMatch(banner(recaptcha).textContent, /cookies antispam/);
  });

  test('reCAPTCHA is only offered on pages with a protected form', () => {
    const consent = page({ ...NONE, recaptchaSiteKey: SITE_KEY }, { form: false });
    consent.finishLoading();
    assert.ok(banner(consent), 'the notice still appears');
    assert.doesNotMatch(banner(consent).textContent, /reCAPTCHA/);
    consent.window.NexoraConsent.open();
    assert.equal(consent.document.querySelectorAll('.consent-switch').length, 0);
  });

  test('without policyUrl, neither the banner nor the panel links anywhere', () => {
    const consent = page(ALL);
    consent.finishLoading();
    assert.deepEqual(banner(consent).querySelectorAll('a'), [], 'no link to a page that may not exist');
    assert.match(banner(consent).querySelector('p').textContent, /al pie de la página\.$/);
    consent.window.NexoraConsent.open();
    const intro = consent.document.querySelector('.consent-panel__intro');
    assert.deepEqual(intro.querySelectorAll('a'), []);
    assert.doesNotMatch(intro.textContent, /Más información/);
  });

  test('with policyUrl, the banner and the panel link exactly to it', () => {
    for (const policyUrl of ['cookies.html', 'https://nexora.test/cookies']) {
      const consent = page({ ...ALL, policyUrl });
      consent.finishLoading();
      consent.window.NexoraConsent.open();
      for (const root of [banner(consent).querySelector('p'), consent.document.querySelector('.consent-panel__intro')]) {
        const links = root.querySelectorAll('a');
        assert.equal(links.length, 1, policyUrl);
        assert.equal(links[0].getAttribute('href'), policyUrl);
        assert.match(root.textContent, /Más información en la política de cookies\.$/);
      }
    }
  });

  test('a policyUrl that is not a path or an http(s) URL is ignored, with a warning', () => {
    const consent = page({ ...ALL, policyUrl: 'javascript:alert(1)' });
    consent.finishLoading();
    assert.deepEqual(banner(consent).querySelectorAll('a'), []);
    assert.ok(consent.warnings.some((line) => /policyUrl ignored/.test(line)));
  });

  test('the panel states the last choice in words', () => {
    const consent = page(ALL);
    consent.finishLoading();
    consent.window.NexoraConsent.rejectAll();
    consent.window.NexoraConsent.open();
    assert.match(consent.document.querySelector('.consent-panel__status').textContent, /: solo lo necesario\. Versión de la política: test-1\./);
  });
});

describe('deciding', () => {
  test('rejecting stores the choice, closes the banner and loads nothing', () => {
    const consent = page(ALL);
    consent.finishLoading();
    consent.click(button(banner(consent), 'reject'));
    assert.equal(banner(consent), null);
    assert.deepEqual(consent.scripts(), []);
    const stored = JSON.parse(consent.store.get('nexora.consent'));
    assert.equal(stored.version, 'test-1');
    assert.deepEqual(stored.choices, { analytics: false, advertising: false, antispam: false });
  });

  test('accepting loads the Google tags and reCAPTCHA, and grants the matching signals', () => {
    const consent = page(ALL);
    consent.finishLoading();
    consent.click(button(banner(consent), 'accept'));
    assert.deepEqual(external(consent), [GTAG, RECAPTCHA]);
    const [, update] = consent.consentCalls().at(-1);
    assert.deepEqual(update, { analytics_storage: 'granted', ad_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted' });
    const configured = consent.window.dataLayer.filter((entry) => entry[0] === 'config').map((entry) => entry[1]);
    assert.deepEqual([...configured], ['G-TEST1234', 'AW-123456789']);
  });

  test('choosing in the panel loads only what was chosen', () => {
    const consent = page(ALL);
    consent.finishLoading();
    consent.click(button(banner(consent), 'configure'));
    const panel = consent.document.querySelector('dialog');
    assert.ok(panel.open);
    for (const input of panel.querySelectorAll('.consent-switch')) assert.equal(input.checked, false, 'everything optional starts off');
    panel.querySelector('#consent-antispam').checked = true;
    consent.click(button(panel, 'save'));
    assert.equal(panel.open, false);
    assert.deepEqual(external(consent), [RECAPTCHA]);
    assert.equal(consent.consentCalls().at(-1)[1].analytics_storage, 'denied');
  });

  test('a script held back in the page runs only once its category is accepted', () => {
    const blocked = [{ type: 'text/plain', 'data-consent': 'analytics', src: 'https://stats.example/s.js' }];
    const consent = page(NONE, { blocked });
    consent.finishLoading();
    assert.deepEqual(consent.scripts().filter((src) => src.includes('stats')), []);
    consent.window.NexoraConsent.acceptAll();
    const activated = consent.scriptElements().filter((el) => el.getAttribute('src') === 'https://stats.example/s.js');
    assert.equal(activated.length, 1);
    assert.equal(activated[0].getAttribute('type'), null, 'it is now a real script');
  });

  test('withdrawing a category deletes its cookies, keeps the others, and reloads the page', () => {
    const consent = page(ALL);
    consent.finishLoading();
    consent.window.NexoraConsent.acceptAll();
    consent.document.cookie = '_ga=GA1.1.test; path=/';
    consent.document.cookie = '_ga_TEST=GS1; path=/; domain=nexora.test';
    consent.document.cookie = '_gcl_au=1.1.test; path=/';
    consent.document.cookie = 'unrelated=1; path=/';
    consent.window.NexoraConsent.open();
    const panel = consent.document.querySelector('dialog');
    panel.querySelector('#consent-analytics').checked = false;
    consent.click(button(panel, 'save'));
    assert.deepEqual([...consent.document.jar.keys()].sort(), ['_gcl_au', 'unrelated']);
    assert.equal(consent.reloads, 1, 'scripts already running are stopped by reloading');
    assert.equal(JSON.parse(consent.store.get('nexora.consent')).choices.analytics, false);
  });

  test('closing the panel gives the focus back to what opened it', () => {
    const consent = page(ALL);
    consent.finishLoading();
    const opener = consent.document.querySelector('[data-consent-open]');
    consent.click(opener);
    consent.click(button(consent.document.querySelector('dialog'), 'close'));
    assert.equal(consent.document.activeElement, opener);
  });
});

describe('a stored choice', () => {
  test('is applied while the page is still loading, before any other script', () => {
    const consent = page(ALL, { stored: choice({ analytics: true, advertising: false, antispam: true }) });
    assert.equal(consent.document.readyState, 'loading');
    assert.deepEqual(external(consent), [GTAG], 'Google tags start at once');
    consent.finishLoading();
    assert.deepEqual(external(consent), [GTAG, RECAPTCHA], 'reCAPTCHA waits for its form');
    assert.equal(banner(consent), null);
  });

  for (const [name, stored] of [
    ['older than its validity', choice({ analytics: true }, { date: new Date(Date.now() - 366 * 864e5).toISOString() })],
    ['made for another version of the policy', choice({ analytics: true }, { version: 'test-0' })],
    ['dated in the future', choice({ analytics: true }, { date: new Date(Date.now() + 864e5).toISOString() })],
    ['unreadable', '{broken'],
    ['without choices', { version: 'test-1', date: new Date().toISOString() }],
  ]) {
    test(`${name} is ignored: nothing loads and the banner asks again`, () => {
      const consent = page(ALL, { stored });
      consent.finishLoading();
      assert.deepEqual(consent.scripts(), []);
      assert.ok(banner(consent));
    });
  }

  test('without browser storage, the choice still works for the page', () => {
    const consent = page(ALL, { storage: 'blocked' });
    consent.finishLoading();
    consent.window.NexoraConsent.acceptAll();
    assert.deepEqual(external(consent), [GTAG, RECAPTCHA]);
    assert.equal(consent.window.NexoraConsent.get().choices.analytics, true);
  });
});

describe('reCAPTCHA tokens for the forms', () => {
  function accepted(grecaptcha) {
    const consent = page({ ...NONE, recaptchaSiteKey: SITE_KEY }, { stored: choice({ antispam: true }), grecaptcha });
    consent.finishLoading();
    return consent;
  }

  test('without consent there is no token, at once', async () => {
    const consent = page({ ...NONE, recaptchaSiteKey: SITE_KEY }, { stored: choice({ antispam: false }) });
    consent.finishLoading();
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
  });

  test('a loaded reCAPTCHA gives a token for the action', async () => {
    const calls = [];
    const consent = accepted({ ready: (callback) => callback(), execute: async (key, options) => { calls.push([key, options.action]); return 'token-123'; } });
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), 'token-123');
    assert.deepEqual(calls, [[SITE_KEY, 'signup']]);
  });

  test('a blocked reCAPTCHA script means no token at once, not a long wait', async () => {
    const consent = accepted(undefined);
    consent.scriptElements()[0].dispatchEvent({ type: 'error' });
    const started = Date.now();
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
    assert.ok(Date.now() - started < 500, `took ${Date.now() - started} ms`);
  });

  test('a reCAPTCHA that never answers is given up after 3 seconds', async () => {
    const consent = accepted({ ready: (callback) => callback(), execute: () => new Promise(() => {}) });
    const started = Date.now();
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
    const waited = Date.now() - started;
    assert.ok(waited >= 2900 && waited < 4500, `waited ${waited} ms`);
  });

  test('a reCAPTCHA that becomes ready after the 3 seconds is not asked for a token any more', async () => {
    // Regression: the late ready() callback still called execute(), wasting a token nobody would use.
    let readyCallback = null;
    let executed = 0;
    const consent = accepted({ ready: (callback) => { readyCallback = callback; }, execute: async () => { executed += 1; return 'late'; } });
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
    readyCallback();
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(executed, 0);
  });

  test('a token that arrives late, or a late failure, is ignored without an unhandled rejection', async () => {
    const unhandled = [];
    const onUnhandled = (reason) => unhandled.push(reason);
    process.on('unhandledRejection', onUnhandled);
    try {
      let reject;
      const consent = accepted({ ready: (callback) => callback(), execute: () => new Promise((resolve, no) => { reject = no; }) });
      assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
      reject(new Error('late failure'));
      await new Promise((resolve) => setTimeout(resolve, 20));
      assert.deepEqual(unhandled, []);
    } finally {
      process.off('unhandledRejection', onUnhandled);
    }
  });

  test('the status tells a form whether reCAPTCHA is off, loading, ready or failed, and announces changes', () => {
    const off = page({ ...NONE, recaptchaSiteKey: SITE_KEY }, { stored: choice({ antispam: false }) });
    off.finishLoading();
    assert.equal(off.window.NexoraConsent.recaptchaStatus(), 'off');

    const consent = accepted(undefined);
    assert.equal(consent.window.NexoraConsent.recaptchaStatus(), 'loading');
    consent.scriptElements()[0].dispatchEvent({ type: 'error' });
    assert.equal(consent.window.NexoraConsent.recaptchaStatus(), 'failed');
    const announced = consent.events.filter((event) => event.type === 'nexora:recaptcha').map((event) => event.detail.state);
    assert.deepEqual(announced, ['loading', 'failed']);

    const loaded = accepted(undefined);
    loaded.scriptElements()[0].dispatchEvent({ type: 'load' });
    assert.equal(loaded.window.NexoraConsent.recaptchaStatus(), 'ready');
  });

  test('a reCAPTCHA that fails gives no token', async () => {
    const consent = accepted({ ready: (callback) => callback(), execute: () => Promise.reject(new Error('reCAPTCHA error')) });
    assert.equal(await consent.window.NexoraConsent.recaptchaToken('signup'), undefined);
  });
});

test('both forms have an empty status region where a failed reCAPTCHA is announced', () => {
  for (const file of ['login.html', 'signup.html']) {
    const html = readFileSync(new URL(`../../web/${file}`, import.meta.url), 'utf8');
    assert.match(html, /<p class="auth__captcha" data-captcha-failed role="status" aria-live="polite"><\/p>/, file);
  }
  const script = readFileSync(new URL('../../web/js/auth.js', import.meta.url), 'utf8');
  assert.match(script, /recaptchaStatus\?\.\(\) === 'failed'/, 'the form reads the status');
  assert.doesNotMatch(script, /CAPTCHA_FAILED = [^;]*(secret|token|error code|siteverify)/i, 'the message reveals nothing internal');
});

test('the policy version the banner asks about is the one the cookie policy shows', () => {
  const read = (file) => readFileSync(new URL(`../../web/${file}`, import.meta.url), 'utf8');
  const configured = read('js/consent-config.js').match(/policyVersion: '([^']+)'/)[1];
  assert.match(read('cookies.html'), new RegExp(`versión ${configured.replace(/\./g, '\\.')}\\b`));
});

describe('consent-config.js as the server reads it', () => {
  const config = readFileSync(new URL('../../web/js/consent-config.js', import.meta.url), 'utf8');

  // What the browser gets from the file: it is run as the page runs it, with only `window`.
  const browserConfig = (source) => {
    const window = {};
    runInNewContext(source, { window });
    return window.NEXORA_CONSENT_CONFIG;
  };
  // The line of the file with a site key instead of its current value, written as the comment asks.
  const withSiteKey = (key) => config.replace(/^(\s*recaptchaSiteKey:\s*).*$/m, `$1'${key}',`);

  test('the server finds its recaptchaSiteKey line, and reads what the browser gets (src/captcha.js, readSiteKey)', async () => {
    const { readSiteKey } = await import('../src/captcha.js');
    const value = readSiteKey(config);
    assert.notEqual(value, undefined, 'the server must find the recaptchaSiteKey line');
    // Without a key (null) the server reads '', and with one, the key itself, in the format
    // js/consent.js accepts: a malformed key would be ignored by the browser.
    assert.equal(value, browserConfig(config).recaptchaSiteKey ?? '');
    if (value !== '') assert.match(value, /^6L[\w-]{38}$/, 'recaptchaSiteKey is not a valid site key');
  });

  test('with a site key in the file, the server and the browser read the same key', async () => {
    const { captchaKeyWarnings, readSiteKey } = await import('../src/captcha.js');
    // A key of the right shape made up for the test: it is not a key of any Google account.
    const source = withSiteKey(SITE_KEY);
    assert.notEqual(source, config, 'the recaptchaSiteKey line was replaced');
    assert.equal(browserConfig(source).recaptchaSiteKey, SITE_KEY);
    assert.equal(readSiteKey(source), SITE_KEY);
    assert.deepEqual(captchaKeyWarnings({ secret: 'test-secret', siteKey: readSiteKey(source) }), []);
  });

  test('its policyUrl is null or names a page of this site that exists: never a broken link', () => {
    const value = config.match(/^\s*policyUrl: (null|'([^']*)'),\s*$/m);
    assert.ok(value, 'consent-config.js sets policyUrl');
    if (value[1] === 'null') return;
    assert.doesNotMatch(value[2], /^[a-z][a-z0-9+.-]*:|^\/\//i, 'a page of this site');
    assert.ok(existsSync(new URL(`../../web/${value[2]}`, import.meta.url)), `web/${value[2]} exists`);
  });

  test('no Google tag is configured, so the page policy does not need to allow one', () => {
    // If Analytics, Tag Manager or Ads are ever configured here, their scripts and connections must
    // be added to the policy first (servidor/src/security-headers.js), or the browser blocks them.
    for (const id of ['analyticsId', 'tagManagerId', 'adsId']) {
      assert.match(config, new RegExp(`${id}: null,`), `${id} is set: update the Content-Security-Policy`);
    }
  });
});
