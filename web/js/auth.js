// Account forms and the session state shown in the header.

async function api(path, body) {
  const response = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error ?? 'The operation could not be completed.');
    error.code = data.code;
    throw error;
  }
  return data;
}

// Google reCAPTCHA v3 (js/consent.js loads it only after consent, and gives up on a token after 3 s:
// a blocked or failed script answers at once). Without a token the form is still sent, and the
// server applies stricter attempt limits instead of refusing the request.
async function captchaToken(action) {
  return window.NexoraConsent?.recaptchaToken ? window.NexoraConsent.recaptchaToken(action) : undefined;
}

// The server sends a failed Google or GitHub sign-in back to /login?error=<code>.
const OAUTH_ERRORS = {
  oauth_unavailable: 'That sign-in method is not available yet.',
  oauth_cancelled: 'The sign-in was cancelled.',
  oauth_failed: 'Could not sign in with that provider. Try again.',
  email_unverified: 'That account has no verified email address.',
  account_exists: 'An account with that email already exists. Log in with your password.',
};

// The back button returns to the page of this site the visitor came from; coming from elsewhere
// (or with no history), its link leads to the home page.
const back = document.querySelector('[data-back]');

if (back) {
  back.addEventListener('click', (event) => {
    let fromThisSite = false;
    try {
      fromThisSite = new URL(document.referrer).origin === location.origin;
    } catch {
      fromThisSite = false;
    }
    if (fromThisSite && history.length > 1) {
      event.preventDefault();
      history.back();
    }
  });
}

const form = document.querySelector('[data-auth-form]');

if (form) {
  const error = form.querySelector('[role="alert"]');
  const submit = form.querySelector('[type="submit"]');

  const oauthError = OAUTH_ERRORS[new URLSearchParams(location.search).get('error')];
  if (oauthError) {
    error.textContent = oauthError;
    error.hidden = false;
  }

  // When the page uses reCAPTCHA but the visitor has not turned it on, say what that means.
  const captchaNote = form.querySelector('[data-captcha-note]');
  const showCaptchaNote = () => {
    if (!captchaNote) return;
    captchaNote.hidden = !window.NexoraConsent?.recaptchaSiteKey() || window.NexoraConsent.get()?.choices.antispam === true;
  };
  showCaptchaNote();
  window.addEventListener('nexora:consent', showCaptchaNote);

  // When it was turned on but could not be used (blocked, offline, too slow), say so too. The status
  // region is always in the page, empty, so screen readers announce the text when it appears.
  const captchaFailed = form.querySelector('[data-captcha-failed]');
  const CAPTCHA_FAILED = 'reCAPTCHA could not be loaded, so stricter attempt limits apply. '
    + 'If this keeps happening, check your connection or content blocker and reload the page.';
  const showCaptchaFailed = (failed) => {
    if (captchaFailed) captchaFailed.textContent = failed ? CAPTCHA_FAILED : '';
  };
  window.addEventListener('nexora:recaptcha', () => showCaptchaFailed(window.NexoraConsent?.recaptchaStatus?.() === 'failed'));
  showCaptchaFailed(window.NexoraConsent?.recaptchaStatus?.() === 'failed');

  // The form keeps what was typed on any error: nothing here clears or reloads it.
  async function send() {
    const action = form.dataset.captchaAction;
    const body = Object.fromEntries(new FormData(form));
    if (action) {
      body.captchaToken = await captchaToken(action);
      // Turned on, but no token in time: the server applies its stricter limit; tell the visitor why.
      const status = window.NexoraConsent?.recaptchaStatus?.();
      showCaptchaFailed(body.captchaToken === undefined && (status === 'failed' || status === 'loading' || status === 'ready'));
    }
    try {
      return await api(form.dataset.endpoint, body);
    } catch (failure) {
      // A token is valid for two minutes and only once: a stale one is replaced and sent again, once.
      // The server counts that second request against the general attempt limit too, on purpose.
      // Any other anti-spam failure is not fixed by a new token, so it is shown as it is.
      if (action && failure.code === 'captcha_expired') {
        body.captchaToken = await captchaToken(action);
        return api(form.dataset.endpoint, body);
      }
      throw failure;
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    // Busy while the request (and a possible wait for a reCAPTCHA token, or one retry) is in flight.
    form.setAttribute('aria-busy', 'true');
    try {
      await send();
      location.href = 'index.html';
    } catch (failure) {
      error.textContent = failure instanceof TypeError
        ? 'Could not connect to the server.'
        : failure.message;
      error.hidden = false;
      submit.disabled = false;
    } finally {
      form.setAttribute('aria-busy', 'false');
    }
  });
}

const sessionSlot = document.querySelector('[data-session]');

if (sessionSlot) {
  // Without the server (a page opened as a file) the header keeps its default link.
  api('/api/auth/me').then(({ user }) => {
    if (!user) return;

    const name = document.createElement('span');
    name.className = 'nav-user';
    name.textContent = user.name;

    const logout = document.createElement('button');
    logout.className = 'pill';
    logout.type = 'button';
    logout.textContent = 'Log out';
    logout.addEventListener('click', async () => {
      await api('/api/auth/logout', {});
      location.reload();
    });

    sessionSlot.replaceChildren(name, logout);
  }).catch(() => {});
}
