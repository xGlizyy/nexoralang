// Cookie consent: Google Consent Mode v2 defaults, the stored choice, the banner, the preferences
// panel and the loading of optional scripts.
//
// A classic script loaded in <head>, right after js/consent-config.js and before any other script,
// so the consent defaults exist before any tag can run. Optional tags are never loaded before
// consent (Consent Mode "basic" implementation): until the visitor accepts a category, nothing of
// that category is requested. The texts are in Spanish, like the legal pages they link to.
(function () {
  'use strict';

  var config = window.NEXORA_CONSENT_CONFIG || {};
  var POLICY_VERSION = String(config.policyVersion || '1');
  var MAX_AGE_DAYS = Number(config.maxAgeDays) > 0 ? Number(config.maxAgeDays) : 365;
  var STORAGE_KEY = 'nexora.consent';
  // The page with the cookie policy, linked from the banner and the panel. Without one (null), they
  // link nowhere instead of to a page that does not exist. Only a path on this site or an http(s) URL.
  var POLICY_URL = typeof config.policyUrl === 'string' && config.policyUrl.trim() !== ''
    && (!/^[a-z][a-z0-9+.-]*:/i.test(config.policyUrl.trim()) || /^https?:/i.test(config.policyUrl.trim()))
    ? config.policyUrl.trim()
    : null;
  if (config.policyUrl && !POLICY_URL) console.warn('[consent] policyUrl ignored: not a path or an http(s) URL');
  var CATEGORIES = ['analytics', 'advertising', 'antispam'];
  var NONE = { analytics: false, advertising: false, antispam: false };
  var ALL = { analytics: true, advertising: true, antispam: true };

  // ---------------------------------------------------------------------------------------------
  // Google IDs: only well-formed ones are used, so a typo never loads an unexpected script.

  var ID_FORMATS = {
    analyticsId: /^G-[A-Z0-9]{4,20}$/,
    tagManagerId: /^GTM-[A-Z0-9]{4,12}$/,
    adsId: /^AW-[0-9]{6,15}$/,
  };
  var google = {};
  Object.keys(ID_FORMATS).forEach(function (key) {
    var value = config.google && config.google[key];
    if (value === null || value === undefined || value === '') return;
    if (typeof value === 'string' && ID_FORMATS[key].test(value)) google[key] = value;
    else console.warn('[consent] google.' + key + ' ignored: not a valid ID');
  });

  // ---------------------------------------------------------------------------------------------
  // Consent Mode v2 defaults, before any tag. Everything optional starts denied.

  window.dataLayer = window.dataLayer || [];
  if (typeof window.gtag !== 'function') {
    // Google's snippet: it must push the `arguments` object itself.
    window.gtag = function () { window.dataLayer.push(arguments); };
  }
  var gtag = window.gtag;
  gtag('consent', 'default', {
    analytics_storage: 'denied',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
    functionality_storage: 'denied',
    personalization_storage: 'denied',
    security_storage: 'granted',
    wait_for_update: 500,
  });
  gtag('set', 'ads_data_redaction', true);
  gtag('set', 'url_passthrough', false);

  function consentModeState(choices) {
    var analytics = choices.analytics ? 'granted' : 'denied';
    var advertising = choices.advertising ? 'granted' : 'denied';
    return {
      analytics_storage: analytics,
      ad_storage: advertising,
      ad_user_data: advertising,
      ad_personalization: advertising,
    };
  }

  // ---------------------------------------------------------------------------------------------
  // The stored choice: { version, date, choices: { analytics, advertising } }, in localStorage.
  // Without storage (private mode, blocked) the choice lasts for this page only.

  var memory = null;

  function normalize(choices) {
    var result = {};
    CATEGORIES.forEach(function (category) { result[category] = choices[category] === true; });
    return result;
  }

  function readStored() {
    var raw = null;
    try { raw = window.localStorage.getItem(STORAGE_KEY); } catch (error) { raw = null; }
    var record = memory;
    if (raw) {
      try { record = JSON.parse(raw); } catch (error) { record = null; }
    }
    if (!record || typeof record !== 'object' || !record.choices || typeof record.date !== 'string') return null;
    if (record.version !== POLICY_VERSION) return null;
    var date = Date.parse(record.date);
    if (!isFinite(date) || Date.now() - date > MAX_AGE_DAYS * 24 * 60 * 60 * 1000 || date > Date.now() + 60000) return null;
    return {
      version: record.version,
      date: record.date,
      choices: normalize(record.choices),
    };
  }

  function store(choices) {
    var record = {
      version: POLICY_VERSION,
      date: new Date().toISOString(),
      choices: normalize(choices),
    };
    memory = record;
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record)); } catch (error) { /* page only */ }
    return record;
  }

  // ---------------------------------------------------------------------------------------------
  // Optional scripts. Google tags are added here; any other optional script is written in the page
  // as <script type="text/plain" data-consent="analytics|advertising" src="…"> and stays inert
  // until its category is accepted.

  var loaded = { gtag: false, gtm: false, configured: {}, other: false, recaptcha: false };

  // Google reCAPTCHA v3, only on pages with a protected form (data-captcha-action): Sign up, Log in.
  var RECAPTCHA_SITE_KEY = typeof config.recaptchaSiteKey === 'string' && /^6L[\w-]{38}$/.test(config.recaptchaSiteKey)
    ? config.recaptchaSiteKey
    : null;
  if (config.recaptchaSiteKey && !RECAPTCHA_SITE_KEY) console.warn('[consent] recaptchaSiteKey ignored: not a valid site key');

  function pageUsesRecaptcha() {
    return !!RECAPTCHA_SITE_KEY && document.readyState !== 'loading' && !!document.querySelector('[data-captcha-action]');
  }

  // 'idle' until it is requested, then 'loading', and 'loaded' or 'failed' (blocked, offline…).
  var recaptchaState = 'idle';

  // Every change is announced with a 'nexora:recaptcha' event, so a form can tell the visitor.
  function setRecaptchaState(state) {
    recaptchaState = state;
    try {
      window.dispatchEvent(new CustomEvent('nexora:recaptcha', { detail: { state: state } }));
    } catch (error) { /* very old browser */ }
  }

  function loadRecaptcha(choices) {
    if (!choices.antispam || loaded.recaptcha || !pageUsesRecaptcha()) return;
    loaded.recaptcha = true;
    setRecaptchaState('loading');
    addScript('https://www.google.com/recaptcha/api.js?render=' + encodeURIComponent(RECAPTCHA_SITE_KEY), function (ok) {
      setRecaptchaState(ok ? 'loaded' : 'failed');
    });
  }

  /**
   * What a protected form can expect: 'off' (no site key on this page, or no consent), 'loading',
   * 'ready' or 'failed' (accepted, but the script could not be loaded).
   */
  function recaptchaStatus() {
    if (!current || !current.choices.antispam || !pageUsesRecaptcha()) return 'off';
    if (recaptchaState === 'loaded') return 'ready';
    return recaptchaState === 'idle' ? 'loading' : recaptchaState;
  }

  // The longest a form waits for a reCAPTCHA token. Without a token the form is still sent and the
  // server applies its stricter limit, so waiting longer would only make people wait.
  var RECAPTCHA_WAIT_MS = 3000;

  /**
   * A reCAPTCHA token for `action`, or undefined when there is none to give: no site key, no
   * consent, the script failed to load, or no answer within RECAPTCHA_WAIT_MS in total.
   */
  function recaptchaToken(action) {
    if (!current || !current.choices.antispam || !pageUsesRecaptcha() || recaptchaState === 'failed' || recaptchaState === 'idle') {
      return Promise.resolve(undefined);
    }
    return new Promise(function (resolve) {
      var finished = false;
      function finish(token) {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        resolve(typeof token === 'string' && token ? token : undefined);
      }
      var timer = setTimeout(function () { finish(undefined); }, RECAPTCHA_WAIT_MS);
      (function poll() {
        if (finished) return;
        if (recaptchaState === 'failed') return finish(undefined);
        var grecaptcha = window.grecaptcha;
        if (!grecaptcha || typeof grecaptcha.ready !== 'function') return void setTimeout(poll, 50);
        grecaptcha.ready(function () {
          // Ready too late: the form has already gone without a token, so no token is requested
          // (it would be wasted, and nothing would handle its result).
          if (finished) return;
          try {
            Promise.resolve(grecaptcha.execute(RECAPTCHA_SITE_KEY, { action: action }))
              .then(finish, function () { finish(undefined); });
          } catch (error) {
            finish(undefined);
          }
        });
      })();
    });
  }

  function addScript(src, done) {
    var script = document.createElement('script');
    script.async = true;
    script.src = src;
    if (done) {
      script.addEventListener('load', function () { done(true); });
      script.addEventListener('error', function () { done(false); });
    }
    document.head.appendChild(script);
  }

  function loadGoogle(choices) {
    var wantsGtag = (choices.analytics && google.analyticsId) || (choices.advertising && google.adsId);
    if (wantsGtag && !loaded.gtag) {
      loaded.gtag = true;
      gtag('js', new Date());
      addScript('https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(choices.analytics && google.analyticsId ? google.analyticsId : google.adsId));
    }
    if (choices.analytics && google.analyticsId && !loaded.configured[google.analyticsId]) {
      loaded.configured[google.analyticsId] = true;
      gtag('config', google.analyticsId);
    }
    if (choices.advertising && google.adsId && !loaded.configured[google.adsId]) {
      loaded.configured[google.adsId] = true;
      gtag('config', google.adsId);
    }
    if ((choices.analytics || choices.advertising) && google.tagManagerId && !loaded.gtm) {
      loaded.gtm = true;
      window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
      addScript('https://www.googletagmanager.com/gtm.js?id=' + encodeURIComponent(google.tagManagerId));
    }
  }

  function activateBlockedScripts(choices) {
    var blocked = document.querySelectorAll('script[type="text/plain"][data-consent]');
    Array.prototype.forEach.call(blocked, function (original) {
      if (!choices[original.getAttribute('data-consent')]) return;
      var script = document.createElement('script');
      Array.prototype.forEach.call(original.attributes, function (attribute) {
        if (attribute.name !== 'type' && attribute.name !== 'data-consent') script.setAttribute(attribute.name, attribute.value);
      });
      script.text = original.text;
      original.parentNode.replaceChild(script, original);
      loaded.other = true;
    });
  }

  function googleUses(category) {
    if (!COOKIE_PATTERNS[category]) return false;
    if (google.tagManagerId) return true;
    return category === 'analytics' ? !!google.analyticsId : !!google.adsId;
  }

  function anyLoaded() {
    return loaded.gtag || loaded.gtm || loaded.other || loaded.recaptcha;
  }

  // Cookies of a category that was refused or withdrawn. They are deleted on this host and on every
  // parent domain, which is where Google sets them. Third-party cookies (on Google's own domains)
  // cannot be deleted from here; the cookie policy explains how to remove them.
  var COOKIE_PATTERNS = {
    analytics: [/^_ga$/, /^_ga_/, /^_gid$/, /^_gat/],
    advertising: [/^_gcl_/, /^_gac_/],
  };

  function deleteCookies(category) {
    if (!COOKIE_PATTERNS[category]) return;
    var names = document.cookie.split(';').map(function (part) { return part.split('=')[0].trim(); });
    var parts = location.hostname.split('.');
    var domains = [''];
    for (var index = 0; index < parts.length - 1; index += 1) domains.push(parts.slice(index).join('.'));
    names.forEach(function (name) {
      if (!COOKIE_PATTERNS[category].some(function (pattern) { return pattern.test(name); })) return;
      domains.forEach(function (domain) {
        document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + (domain ? '; domain=' + domain : '');
      });
    });
  }

  // ---------------------------------------------------------------------------------------------
  // Applying a choice.

  var current = null;

  function apply(record, previous) {
    current = record;
    var choices = record ? record.choices : NONE;
    gtag('consent', 'update', consentModeState(choices));
    window.dataLayer.push({ event: 'nexora_consent_update', nexora_consent: { analytics: choices.analytics, advertising: choices.advertising } });

    var withdrawn = CATEGORIES.filter(function (category) {
      return previous && previous.choices[category] && !choices[category];
    });
    // Only the categories this site uses: a cookie with the same name on a parent domain may belong
    // to another site of that domain.
    CATEGORIES.forEach(function (category) {
      if (!choices[category] && (googleUses(category) || loaded.other)) deleteCookies(category);
    });

    // A script that already runs cannot be stopped: when something was loaded and consent is
    // withdrawn, the page reloads so it starts again without it.
    if (withdrawn.length > 0 && anyLoaded()) {
      location.reload();
      return;
    }
    loadGoogle(choices);
    loadRecaptcha(choices);
    if (document.readyState !== 'loading') activateBlockedScripts(choices);

    try {
      window.dispatchEvent(new CustomEvent('nexora:consent', { detail: record }));
    } catch (error) { /* very old browser */ }
  }

  function decide(choices) {
    var previous = current;
    apply(store(choices), previous);
    hideBanner();
    renderStatus();
  }

  // A stored choice is applied at once, before the page goes on loading.
  var stored = readStored();
  if (stored) apply(stored, null);

  // ---------------------------------------------------------------------------------------------
  // What the site uses. This is also what the cookie policy (cookies.html) lists.

  var NECESSARY = [
    ['nexora_session', 'NEXORA (propia)', 'Mantiene la sesión iniciada en tu cuenta. HttpOnly; solo existe si inicias sesión.', '30 días'],
    ['nexora_oauth_state', 'NEXORA (propia)', 'Protege el inicio de sesión con Google o GitHub frente a peticiones falsificadas.', '10 minutos'],
    ['nexora.consent', 'NEXORA (localStorage)', 'Guarda tu elección sobre cookies, su fecha y la versión de la política. Solo existe si has elegido, y solo en tu navegador.', 'Vale ' + MAX_AGE_DAYS + ' días; después se vuelve a preguntar'],
    ['nexora.playground.v1', 'NEXORA (sessionStorage)', 'Conserva el código que escribes en el playground mientras la pestaña está abierta.', 'Hasta cerrar la pestaña'],
  ];

  function optionalCatalogue() {
    var analytics = [];
    var advertising = [];
    if (google.analyticsId || google.tagManagerId) {
      analytics.push(['_ga', 'Google Analytics (Google Ireland Ltd.)', 'Distingue visitantes de forma seudónima para medir el uso del sitio.', '2 años']);
      analytics.push(['_ga_<id>', 'Google Analytics (Google Ireland Ltd.)', 'Mantiene el estado de la sesión de medición.', '2 años']);
    }
    if (google.adsId || google.tagManagerId) {
      advertising.push(['_gcl_au', 'Google Ads (Google Ireland Ltd.)', 'Atribuye conversiones a los anuncios.', '90 días']);
      advertising.push(['Cookies en dominios de Google', 'Google (terceros)', 'Publicidad y medición de anuncios, según la política de Google.', 'Según Google']);
    }
    Array.prototype.forEach.call(document.querySelectorAll('script[type="text/plain"][data-consent]'), function (script) {
      var list = script.getAttribute('data-consent') === 'analytics' ? analytics : script.getAttribute('data-consent') === 'advertising' ? advertising : null;
      if (list && script.getAttribute('data-consent-name')) {
        list.push([script.getAttribute('data-consent-name'), script.getAttribute('data-consent-provider') || '', script.getAttribute('data-consent-purpose') || '', script.getAttribute('data-consent-duration') || '']);
      } else if (list && list.length === 0) {
        list.push(['Script configurado en la página', '', 'Ver la política de cookies.', '']);
      }
    });
    var antispam = pageUsesRecaptcha()
      ? [
        ['_GRECAPTCHA', 'Google reCAPTCHA (Google, terceros)', 'Análisis de riesgo para distinguir personas de bots.', '6 meses'],
        ['rc::a, rc::b, rc::c, rc::d', 'Google reCAPTCHA (almacenamiento en google.com)', 'Detección de bots.', 'Persistente o de sesión'],
      ]
      : [];
    return { analytics: analytics, advertising: advertising, antispam: antispam };
  }

  // ---------------------------------------------------------------------------------------------
  // Interface. Built with DOM methods: no text from outside this file is parsed as HTML.

  function element(tag, attributes, children) {
    var node = document.createElement(tag);
    Object.keys(attributes || {}).forEach(function (name) {
      if (name === 'text') node.textContent = attributes[name];
      else node.setAttribute(name, attributes[name]);
    });
    (children || []).forEach(function (child) { if (child) node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child); });
    return node;
  }

  // " Más información en la política de cookies." with its link, or nothing without a policyUrl.
  function policyMention() {
    if (!POLICY_URL) return [];
    return [' Más información en la ', element('a', { href: POLICY_URL, text: 'política de cookies' }), '.'];
  }

  var banner = null;
  var panel = null;
  var statusLine = null;
  var switches = {};
  var opener = null;

  function inUse() {
    var catalogue = optionalCatalogue();
    return CATEGORIES.filter(function (category) { return catalogue[category].length > 0; });
  }

  // "a", "a y b", "a, b y c".
  function listText(items) {
    return items.length < 2 ? items.join('') : items.slice(0, -1).join(', ') + ' y ' + items[items.length - 1];
  }

  // What the optional categories are, in words: the cookies by their kind, and reCAPTCHA as the
  // service it is (it is a Google service with its own storage, not one more kind of our cookies).
  function describeUse(categories) {
    var names = { analytics: 'analíticas', advertising: 'publicitarias' };
    var cookies = categories.filter(function (category) { return names[category]; })
      .map(function (category) { return names[category]; });
    var parts = [];
    if (cookies.length) parts.push('cookies ' + listText(cookies));
    if (categories.indexOf('antispam') !== -1) parts.push('la protección antispam de Google reCAPTCHA');
    // "cookies analíticas y publicitarias, y la protección…": the comma keeps the two "y" apart.
    return parts.length === 2 && cookies.length > 1 ? parts[0] + ', y ' + parts[1] : listText(parts);
  }

  function buildBanner(categories) {
    var title = element('h2', { class: 'consent-banner__title', id: 'consent-banner-title', text: 'Cookies en NEXORA' });
    var text = element('p', {}, [
      'Usamos cookies necesarias para que la web funcione. Con tu permiso, también usaremos '
        + describeUse(categories) + '. Puedes aceptarlo todo, rechazarlo todo o elegir; no se activará nada opcional hasta que decidas. '
        + 'Podrás cambiar tu elección cuando quieras desde «Configurar cookies», al pie de la página.',
    ].concat(policyMention()));
    var actions = element('div', { class: 'consent-banner__actions' }, [
      element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'reject', text: 'Rechazar todas' }),
      element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'configure', text: 'Configurar' }),
      element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'accept', text: 'Aceptar todas' }),
    ]);
    banner = element('section', { class: 'consent-banner', lang: 'es', 'aria-labelledby': 'consent-banner-title' }, [
      element('div', { class: 'consent-banner__body' }, [title, text]),
      actions,
    ]);
    document.body.insertBefore(banner, document.body.firstChild);
  }

  function hideBanner() {
    if (banner) {
      banner.remove();
      banner = null;
    }
  }

  function cookieTable(rows) {
    var list = element('ul', { class: 'consent-cookies' });
    rows.forEach(function (row) {
      list.appendChild(element('li', {}, [
        element('code', { text: row[0] }),
        element('span', { text: [row[1], row[2], row[3]].filter(Boolean).join(' · ') }),
      ]));
    });
    return element('details', { class: 'consent-cat__details' }, [
      element('summary', { text: 'Ver cookies y almacenamiento (' + rows.length + ')' }),
      list,
    ]);
  }

  function category(id, name, description, rows, optional) {
    var head = element('div', { class: 'consent-cat__head' });
    if (optional) {
      var input = element('input', { type: 'checkbox', role: 'switch', class: 'consent-switch', id: 'consent-' + id, 'aria-describedby': 'consent-' + id + '-desc' });
      switches[id] = input;
      head.appendChild(element('label', { for: 'consent-' + id, class: 'consent-cat__name', text: name }));
      head.appendChild(input);
    } else {
      head.appendChild(element('span', { class: 'consent-cat__name', text: name }));
      head.appendChild(element('span', { class: 'consent-cat__always', text: 'Siempre activas' }));
    }
    return element('div', { class: 'consent-cat' }, [
      head,
      element('p', { id: 'consent-' + id + '-desc', class: 'consent-cat__desc', text: description }),
      rows.length ? cookieTable(rows) : null,
    ]);
  }

  function buildPanel() {
    var catalogue = optionalCatalogue();
    var categories = inUse();
    switches = {};

    var close = element('button', { class: 'consent-panel__close', type: 'button', 'aria-label': 'Cerrar', 'data-consent-action': 'close', text: '×' });
    var intro = categories.length
      ? 'Elige qué cookies y servicios opcionales aceptas. Las cookies necesarias no se pueden desactivar porque sin ellas la web no funciona. Lo opcional está desactivado hasta que lo actives.'
      : 'Ahora mismo NEXORA solo usa cookies y almacenamiento necesarios para que la web funcione. No usa cookies analíticas, publicitarias ni de personalización, así que no hay nada que aceptar o rechazar.';

    var body = [
      element('div', { class: 'consent-panel__head' }, [
        element('h2', { id: 'consent-panel-title', text: 'Preferencias de cookies' }),
        close,
      ]),
      element('p', { class: 'consent-panel__intro' }, [intro].concat(policyMention())),
      category('necessary', 'Necesarias', 'Imprescindibles para el funcionamiento y la seguridad: la sesión de tu cuenta, la protección del inicio de sesión y recordar tu elección sobre cookies.', NECESSARY, false),
    ];
    if (catalogue.analytics.length) {
      body.push(category('analytics', 'Analíticas', 'Nos permiten medir de forma agregada cómo se usa la web para mejorarla.', catalogue.analytics, true));
    }
    if (catalogue.antispam.length) {
      body.push(category('antispam', 'Antispam (Google reCAPTCHA)', 'Antes de enviar el registro o el inicio de sesión, Google reCAPTCHA analiza tu navegador y tu interacción con la página para detectar bots. Google recibe tu dirección IP y datos de tu dispositivo. Si no lo activas, puedes registrarte e iniciar sesión igualmente, con un límite de intentos más estricto.', catalogue.antispam, true));
    }
    if (catalogue.advertising.length) {
      body.push(category('advertising', 'Publicidad y personalización', 'Permiten medir campañas publicitarias y mostrar anuncios personalizados.', catalogue.advertising, true));
    }
    statusLine = element('p', { class: 'consent-panel__status', 'aria-live': 'polite' });
    body.push(statusLine);

    var actions = categories.length
      ? [
        element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'reject', text: 'Rechazar todas' }),
        element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'save', text: 'Guardar preferencias' }),
        element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'accept', text: 'Aceptar todas' }),
      ]
      : [element('button', { class: 'btn btn--sm', type: 'button', 'data-consent-action': 'close', text: 'Cerrar' })];
    body.push(element('div', { class: 'consent-panel__actions' }, actions));

    panel = element('dialog', { class: 'consent-panel', lang: 'es', 'aria-labelledby': 'consent-panel-title' }, body);
    panel.addEventListener('close', function () {
      if (opener && document.contains(opener)) opener.focus();
      opener = null;
    });
    document.body.appendChild(panel);
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleString('es-ES', { dateStyle: 'long', timeStyle: 'short' });
    } catch (error) {
      return iso;
    }
  }

  function renderStatus() {
    if (!statusLine) return;
    if (!inUse().length) {
      statusLine.textContent = 'Versión de la política: ' + POLICY_VERSION + '.';
    } else if (current) {
      var accepted = CATEGORIES.filter(function (category) { return current.choices[category]; });
      statusLine.textContent = 'Tu elección del ' + formatDate(current.date) + ': '
        + (accepted.length ? 'aceptas ' + describeUse(accepted) : 'solo lo necesario')
        + '. Versión de la política: ' + current.version + '.';
    } else {
      statusLine.textContent = 'Todavía no has elegido. Versión de la política: ' + POLICY_VERSION + '.';
    }
  }

  function openPanel(trigger) {
    if (!panel) buildPanel();
    var choices = current ? current.choices : NONE;
    Object.keys(switches).forEach(function (id) { switches[id].checked = choices[id] === true; });
    renderStatus();
    opener = trigger || document.activeElement;
    if (typeof panel.showModal === 'function') {
      if (!panel.open) panel.showModal();
    } else {
      panel.setAttribute('open', '');
    }
    var first = panel.querySelector('.consent-switch') || panel.querySelector('.consent-panel__actions button');
    if (first) first.focus();
  }

  function closePanel() {
    if (!panel) return;
    if (typeof panel.close === 'function' && panel.open) panel.close();
    else panel.removeAttribute('open');
  }

  function onAction(action) {
    if (action === 'accept') decide(ALL);
    else if (action === 'reject') decide(NONE);
    else if (action === 'save') {
      var chosen = {};
      CATEGORIES.forEach(function (id) { chosen[id] = !!(switches[id] && switches[id].checked); });
      decide(chosen);
    }
    if (action === 'configure') openPanel(document.activeElement);
    else closePanel();
  }

  function start() {
    // Links to the preferences: hidden without JavaScript, because they need this script.
    Array.prototype.forEach.call(document.querySelectorAll('[data-consent-open]'), function (button) {
      button.hidden = false;
    });
    document.addEventListener('click', function (event) {
      var target = event.target instanceof Element ? event.target : null;
      var trigger = target && target.closest('[data-consent-open]');
      if (trigger) {
        event.preventDefault();
        openPanel(trigger);
        return;
      }
      var action = target && target.closest('[data-consent-action]');
      if (action && (banner && banner.contains(action) || panel && panel.contains(action))) {
        onAction(action.getAttribute('data-consent-action'));
      }
    });

    if (current) {
      activateBlockedScripts(current.choices);
      loadRecaptcha(current.choices);
    }
    var categories = inUse();
    if (categories.length && !current) buildBanner(categories);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();

  window.NexoraConsent = {
    /** The current choice, or null while the visitor has not decided. */
    get: function () { return current ? JSON.parse(JSON.stringify(current)) : null; },
    open: function () { openPanel(null); },
    acceptAll: function () { decide(ALL); },
    rejectAll: function () { decide(NONE); },
    policyVersion: POLICY_VERSION,
    /** The reCAPTCHA site key when this page uses reCAPTCHA, or null. */
    recaptchaSiteKey: function () { return pageUsesRecaptcha() ? RECAPTCHA_SITE_KEY : null; },
    /** A promise of a reCAPTCHA token for `action`, or of undefined; it never waits more than 3 s. */
    recaptchaToken: recaptchaToken,
    /** 'off', 'loading', 'ready' or 'failed'; changes are announced with a 'nexora:recaptcha' event. */
    recaptchaStatus: recaptchaStatus,
  };
})();
