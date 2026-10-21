// Configuration of the consent manager (js/consent.js). The site has no build step, so this file is
// the configuration: it is loaded before consent.js on every page.
//
// Google IDs are public (they appear in the page anyway), so they are not secrets. Leave a service as
// null to keep it off: nothing is loaded for it. The banner still asks the visitor to acknowledge the
// necessary cookies; the optional categories only appear when a service is configured.
window.NEXORA_CONSENT_CONFIG = {
  // Change it whenever the cookie policy changes in a way that matters (a new service, a new purpose):
  // every visitor is then asked again. Keep it equal to the version shown in cookies.html.
  policyVersion: '2026-10-17.1',

  // How long a choice is kept before asking again, in days.
  maxAgeDays: 365,

  // The page with the cookie policy, linked from the banner and the preferences panel. null: no link
  // is shown, for a site that does not have that page (yet). Set it in the same change that adds it.
  policyUrl: 'cookies.html',

  // Setting an ID is NOT enough to turn a Google service on. The site's Content-Security-Policy
  // (servidor/src/security-headers.js) only allows scripts and connections of this site, so the browser
  // would block the service even after consent, and servidor/test/consent.test.js fails while an ID
  // is set. Using one of these services is a pending product and privacy decision, together with
  // the exact domains its policy needs (nexora/docs/playground.md, «Tareas pendientes y riesgos»).
  google: {
    // Google Analytics 4, for example 'G-XXXXXXXXXX'. Loaded only after consent to analytics cookies.
    analyticsId: null,
    // Google Tag Manager, for example 'GTM-XXXXXXX'. Loaded only after consent to at least one
    // optional category; each tag inside it must respect Consent Mode.
    tagManagerId: null,
    // Google Ads, for example 'AW-123456789'. Loaded only after consent to advertising cookies.
    adsId: null,
  },

  // Google reCAPTCHA v3: the PUBLIC site key (the secret key goes only in servidor/.env as
  // RECAPTCHA_SECRET_KEY). Used on Sign up and Log in, and loaded only after consent to the
  // "Antispam" category; without consent, the server applies stricter attempt limits instead.
  recaptchaSiteKey: null,
};
