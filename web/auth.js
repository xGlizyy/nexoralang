// Account forms and the session state shown in the header.

async function api(path, body) {
  const response = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error ?? 'The operation could not be completed.');
  return data;
}

// The server sends a failed Google or GitHub sign-in back to /login?error=<code>.
const OAUTH_ERRORS = {
  oauth_unavailable: 'That sign-in method is not available yet.',
  oauth_cancelled: 'The sign-in was cancelled.',
  oauth_failed: 'Could not sign in with that provider. Try again.',
  email_unverified: 'That account has no verified email address.',
  account_exists: 'An account with that email already exists. Log in with your password.',
};

const form = document.querySelector('[data-auth-form]');

if (form) {
  const error = form.querySelector('[role="alert"]');
  const submit = form.querySelector('[type="submit"]');

  const oauthError = OAUTH_ERRORS[new URLSearchParams(location.search).get('error')];
  if (oauthError) {
    error.textContent = oauthError;
    error.hidden = false;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    try {
      await api(form.dataset.endpoint, Object.fromEntries(new FormData(form)));
      location.href = 'index.html';
    } catch (failure) {
      error.textContent = failure instanceof TypeError
        ? 'Could not connect to the server.'
        : failure.message;
      error.hidden = false;
      submit.disabled = false;
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
