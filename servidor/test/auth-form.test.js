// Formularios de cuenta (web/js/auth.js), ejecutados en un DOM mínimo (fixtures/mini-dom.js) con el
// servidor y js/consent.js simulados: comprueban lo que hace el script al enviar, no un navegador ni
// Google. reCAPTCHA aparece solo a través de window.NexoraConsent; ningún token se verifica aquí.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, test } from 'node:test';
import { loadAuth } from './fixtures/mini-dom.js';

/** El formulario de inicio de sesión, con los mismos ganchos que web/login.html. */
function loginForm(document, el) {
  const form = el('form', { class: 'auth__card', 'data-auth-form': '', 'data-endpoint': '/api/auth/login', 'data-captcha-action': 'login', novalidate: '' });
  form.appendChild(el('input', { id: 'email', name: 'email', type: 'email', value: 'ada@example.com' }));
  form.appendChild(el('input', { id: 'password', name: 'password', type: 'password', value: 'correct horse battery' }));
  const trap = form.appendChild(el('div', { class: 'auth__hp', 'aria-hidden': 'true' }));
  trap.appendChild(el('input', { id: 'website', name: 'website', type: 'text', tabindex: '-1' }));
  const note = form.appendChild(el('p', { class: 'auth__captcha', 'data-captcha-note': '', hidden: '' }));
  note.appendChild(el('button', { type: 'button', 'data-consent-open': '', hidden: '' }, 'Turn on'));
  form.appendChild(el('p', { class: 'auth__captcha', 'data-captcha-failed': '', role: 'status', 'aria-live': 'polite' }));
  form.appendChild(el('p', { class: 'auth__error', role: 'alert', hidden: '' }));
  form.appendChild(el('button', { class: 'btn btn--primary', type: 'submit' }, 'Log in'));
  document.body.appendChild(form);
}

/** Un window.NexoraConsent simulado: los tokens que dará, en orden, y el estado de reCAPTCHA. */
function consent({ tokens = [], status = 'ready', siteKey = 'site-key', accepted = true } = {}) {
  const given = [];
  return {
    given,
    recaptchaToken: async (action) => { given.push(action); return tokens.shift(); },
    recaptchaStatus: () => status,
    recaptchaSiteKey: () => siteKey,
    get: () => (accepted === null ? null : { choices: { antispam: accepted } }),
  };
}

const ok = (request, { json }) => json(200, { user: { id: 1, name: 'Ada', email: 'ada@example.com' } });
const refuse = (status, code, error) => (request, { json }) => json(status, { error, code });

function page(options = {}) {
  return loadAuth({ build: loginForm, ...options });
}
const alert = (p) => p.form.querySelector('[role="alert"]');
const submitButton = (p) => p.form.querySelector('[type="submit"]');
const failedRegion = (p) => p.form.querySelector('[data-captcha-failed]');

describe('sending the form', () => {
  test('without js/consent.js there is no token: the form is sent without one, and the server decides', async () => {
    const p = page({ respond: ok });
    await p.submit();
    assert.equal(p.requests.length, 1);
    const [request] = p.requests;
    assert.equal(request.path, '/api/auth/login');
    assert.equal(request.method, 'POST');
    assert.equal(request.credentials, 'same-origin', 'only this site, with its cookies');
    assert.ok(!('captchaToken' in request.body), 'no captchaToken field at all');
    assert.deepEqual(p.navigations, ['index.html']);
  });

  test('with reCAPTCHA turned on, the token of the form action is sent', async () => {
    const recaptcha = consent({ tokens: ['token-1'] });
    const p = page({ respond: ok, consent: recaptcha });
    await p.submit();
    assert.deepEqual(recaptcha.given, ['login']);
    assert.equal(p.requests[0].body.captchaToken, 'token-1');
  });

  test('reCAPTCHA turned off: no token, and nothing says it failed', async () => {
    const p = page({ respond: ok, consent: consent({ tokens: [undefined], status: 'off', accepted: false }) });
    await p.submit();
    assert.ok(!('captchaToken' in p.requests[0].body));
    assert.equal(failedRegion(p).textContent, '');
  });

  test('the honeypot field travels empty, with what the person typed', async () => {
    const p = page({ respond: ok });
    await p.submit();
    assert.deepEqual(p.requests[0].body, { email: 'ada@example.com', password: 'correct horse battery', website: '' });
  });
});

describe('errors', () => {
  test('an error of the server is shown in the alert, and the button works again', async () => {
    const p = page({ respond: refuse(401, undefined, 'Incorrect email or password.') });
    await p.submit();
    assert.equal(alert(p).hidden, false);
    assert.equal(alert(p).textContent, 'Incorrect email or password.');
    assert.equal(submitButton(p).disabled, false);
    assert.deepEqual(p.navigations, [], 'it stays on the page');
  });

  test('an error without a message gets the generic one', async () => {
    const p = page({ respond: (request, { json }) => json(500, {}) });
    await p.submit();
    assert.equal(alert(p).textContent, 'The operation could not be completed.');
  });

  test('without a connection, the visitor is told so', async () => {
    const p = page({ respond: (request, { networkError }) => { throw networkError(); } });
    await p.submit();
    assert.equal(alert(p).textContent, 'Could not connect to the server.');
    assert.equal(submitButton(p).disabled, false);
  });

  test('an expired token is replaced and the form is sent again, exactly once', async () => {
    const recaptcha = consent({ tokens: ['stale', 'fresh'] });
    let calls = 0;
    const p = page({
      consent: recaptcha,
      respond: (request, helpers) => (++calls === 1 ? refuse(400, 'captcha_expired', 'The anti-spam check expired. Try again.')(request, helpers) : ok(request, helpers)),
    });
    await p.submit();
    assert.deepEqual(p.requests.map((request) => request.body.captchaToken), ['stale', 'fresh']);
    assert.deepEqual(p.navigations, ['index.html']);
  });

  test('a second expired token is shown, not retried again: no loop', async () => {
    const p = page({ consent: consent({ tokens: ['a', 'b', 'c'] }), respond: refuse(400, 'captcha_expired', 'The anti-spam check expired. Try again.') });
    await p.submit();
    assert.equal(p.requests.length, 2);
    assert.equal(alert(p).textContent, 'The anti-spam check expired. Try again.');
    assert.equal(submitButton(p).disabled, false);
  });

  for (const [status, code, message] of [
    [400, 'captcha_invalid', 'The anti-spam check failed. Reload the page and try again.'],
    [429, 'captcha_required', 'Too many attempts without the anti-spam check. Try again later, or turn on Google reCAPTCHA in Cookie settings.'],
    [429, 'login_throttled', 'Too many failed attempts. Try again in 4 seconds.'],
  ]) {
    test(`${code} is shown as it is, without a retry`, async () => {
      const recaptcha = consent({ tokens: ['one', 'two'] });
      const p = page({ consent: recaptcha, respond: refuse(status, code, message) });
      await p.submit();
      assert.equal(p.requests.length, 1);
      assert.deepEqual(recaptcha.given, ['login'], 'no second token asked for');
      assert.equal(alert(p).textContent, message);
      assert.equal(submitButton(p).disabled, false);
    });
  }

  test('a Google or GitHub sign-in that failed is explained from ?error=', () => {
    const p = page({ search: '?error=oauth_cancelled' });
    assert.equal(alert(p).hidden, false);
    assert.equal(alert(p).textContent, 'The sign-in was cancelled.');
    const unknown = page({ search: '?error=something_else' });
    assert.equal(alert(unknown).hidden, true, 'an unknown code shows nothing');
  });
});

describe('reCAPTCHA status on the form', () => {
  const FAILED = /^reCAPTCHA could not be loaded, so stricter attempt limits apply\./;

  test('a script that could not be loaded is announced in the status region at once', () => {
    const p = page({ consent: consent({ status: 'failed' }) });
    assert.match(failedRegion(p).textContent, FAILED);
    assert.equal(failedRegion(p).getAttribute('role'), 'status');
  });

  test('turned on but no token in time: the form is still sent, and the visitor is told why', async () => {
    const p = page({ respond: ok, consent: consent({ tokens: [undefined], status: 'ready' }) });
    await p.submit();
    assert.equal(p.requests.length, 1);
    assert.match(failedRegion(p).textContent, FAILED);
  });

  test('a later failure is announced when js/consent.js reports it', () => {
    const recaptcha = consent({ status: 'loading' });
    const p = page({ consent: recaptcha });
    assert.equal(failedRegion(p).textContent, '');
    recaptcha.recaptchaStatus = () => 'failed';
    p.announce('nexora:recaptcha');
    assert.match(failedRegion(p).textContent, FAILED);
  });

  test('the note that reCAPTCHA is off shows only with a site key and without consent', () => {
    const note = (p) => p.form.querySelector('[data-captcha-note]');
    assert.equal(note(page({ consent: consent({ accepted: false }) })).hidden, false);
    assert.equal(note(page({ consent: consent({ accepted: true }) })).hidden, true);
    assert.equal(note(page({ consent: consent({ siteKey: null, accepted: false }) })).hidden, true, 'no site key: nothing to turn on');
  });
});

describe('busy state', () => {
  test('aria-busy is true while the request is in flight, and false again after success', async () => {
    let during;
    const p = page({ respond: (request, helpers) => { during = p.form.getAttribute('aria-busy'); return ok(request, helpers); } });
    await p.submit();
    assert.equal(during, 'true');
    assert.equal(p.form.getAttribute('aria-busy'), 'false');
  });

  test('aria-busy is false again after an error, a lost connection and a retry', async () => {
    for (const respond of [
      refuse(401, undefined, 'Incorrect email or password.'),
      (request, { networkError }) => { throw networkError(); },
      refuse(400, 'captcha_expired', 'The anti-spam check expired. Try again.'),
    ]) {
      const p = page({ respond, consent: consent({ tokens: ['a', 'b'] }) });
      await p.submit();
      assert.equal(p.form.getAttribute('aria-busy'), 'false');
      assert.equal(submitButton(p).disabled, false);
    }
  });

  test('aria-busy is false again even if asking for a token throws', async () => {
    const broken = { ...consent(), recaptchaToken: async () => { throw new Error('reCAPTCHA exploded'); } };
    const p = page({ respond: ok, consent: broken });
    await p.submit();
    assert.equal(p.requests.length, 0);
    assert.equal(p.form.getAttribute('aria-busy'), 'false');
    assert.equal(alert(p).textContent, 'reCAPTCHA exploded');
    assert.equal(submitButton(p).disabled, false);
  });
});

test('web/login.html and web/signup.html carry the hooks these tests rely on', () => {
  for (const [file, endpoint, action] of [['login.html', '/api/auth/login', 'login'], ['signup.html', '/api/auth/signup', 'signup']]) {
    const html = readFileSync(new URL(`../../web/${file}`, import.meta.url), 'utf8');
    assert.match(html, new RegExp(`<form [^>]*data-auth-form data-endpoint="${endpoint}" data-captcha-action="${action}"`), file);
    assert.match(html, /<p class="auth__error" role="alert" hidden><\/p>/, file);
    assert.match(html, /<button class="btn btn--primary" type="submit">/, file);
    assert.match(html, /<div class="auth__hp" aria-hidden="true">\s*<label for="website">[^<]+<\/label>\s*<input id="website" name="website" type="text" tabindex="-1" autocomplete="off" data-1p-ignore data-lpignore="true">/, file);
    assert.match(html, /<p class="auth__captcha" data-captcha-failed role="status" aria-live="polite"><\/p>/, file);
    assert.match(html, /<script src="js\/auth\.js" defer><\/script>/, file);
    for (const provider of ['google', 'github']) assert.ok(html.includes(`href="/api/auth/${provider}"`), `${file}: ${provider} sign-in`);
  }
});
