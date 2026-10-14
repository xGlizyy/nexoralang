// Site header shared by every page: mobile menu, shrinking bar, link highlight, the Documentation
// outline and the GitHub links.

import { site } from './config.js';

function setupNav() {
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('site-nav');
  if (!toggle || !nav) return;

  function setOpen(open) {
    nav.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  }

  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  nav.addEventListener('click', (event) => {
    if (event.target.closest('a')) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      setOpen(false);
      toggle.focus();
    }
  });
}

// The header bar shrinks once the page is scrolled. Two thresholds keep it from flickering at the edge.
// The brand mark also turns with the scroll position, so it only moves while the page does.
function setupHeader() {
  const header = document.querySelector('.site-header');
  if (!header) return;
  const spins = !matchMedia('(prefers-reduced-motion: reduce)').matches;

  function update() {
    if (scrollY > 56) header.classList.add('is-scrolled');
    else if (scrollY < 16) header.classList.remove('is-scrolled');
    if (spins) header.style.setProperty('--brand-spin', `${Math.round(scrollY * 0.4)}deg`);
  }

  addEventListener('scroll', update, { passive: true });
  update();
}

// A highlight slides under the nav link being hovered or focused.
function setupNavHighlight() {
  const list = document.querySelector('.site-nav__links');
  if (!list) return;
  let current = null;

  function place(link) {
    list.style.setProperty('--hl-x', `${link.offsetLeft - 12}px`);
    list.style.setProperty('--hl-w', `${link.offsetWidth + 24}px`);
  }

  function show(link) {
    if (current) {
      place(link);
    } else {
      // First link: appear in place instead of sliding in from wherever it was last.
      list.classList.add('is-jumping');
      place(link);
      void list.offsetWidth;
      list.classList.remove('is-jumping');
    }
    current?.classList.remove('is-highlighted');
    current = link;
    link.classList.add('is-highlighted');
    list.classList.add('has-highlight');
  }

  function hide() {
    current?.classList.remove('is-highlighted');
    current = null;
    list.classList.remove('has-highlight');
  }

  for (const link of list.querySelectorAll('.nav-link')) {
    link.addEventListener('pointerenter', () => show(link));
    link.addEventListener('focus', () => show(link));
    link.addEventListener('blur', hide);
  }
  list.addEventListener('pointerleave', hide);

  // The links move when the header shrinks or grows: keep the highlight on the hovered one.
  list.addEventListener('transitionend', (event) => {
    if (current && !event.pseudoElement) place(current);
  });
}

// Clicking "Documentation" opens its outline instead of leaving the page. Where the outline is not
// shown (the collapsed mobile menu) the link keeps working as a normal link.
function setupNavMenu() {
  const item = document.querySelector('.nav-item--menu');
  if (!item) return;
  const link = item.querySelector('.nav-link');
  const menu = item.querySelector('.nav-menu');

  function setOpen(open) {
    item.classList.toggle('is-open', open);
    link.setAttribute('aria-expanded', String(open));
  }

  link.setAttribute('aria-haspopup', 'true');
  link.setAttribute('aria-expanded', 'false');

  link.addEventListener('click', (event) => {
    if (getComputedStyle(menu).display === 'none') return;
    event.preventDefault();
    setOpen(true);
  });
  // Choosing a section closes the outline, even while the pointer is still over it
  // (on the documentation page the choice only swaps the section, the page does not reload).
  menu.addEventListener('click', (event) => {
    if (!event.target.closest('a')) return;
    setOpen(false);
    item.classList.add('is-dismissed');
    document.activeElement?.blur();
  });
  item.addEventListener('pointerleave', () => item.classList.remove('is-dismissed'));
  document.addEventListener('click', (event) => {
    if (!item.contains(event.target)) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !item.classList.contains('is-open')) return;
    setOpen(false);
    link.blur();
  });
}

// The "Language guide" branch of the Documentation menu is read from the guide's own outline,
// so a section added to guide.html shows up in the menu without touching every page.
async function renderGuideOutline() {
  const list = document.querySelector('[data-guide-outline]');
  if (!list) return;
  let links;
  try {
    const response = await fetch('guide.html');
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    links = [...page.querySelectorAll('.docs__toc a[href^="#"]')];
  } catch {
    return;
  }
  list.replaceChildren(...links.map((source, index) => {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = `guide.html${source.getAttribute('href')}`;
    const number = document.createElement('span');
    number.textContent = String(index + 1).padStart(2, '0');
    const title = document.createElement('strong');
    title.textContent = source.textContent.trim();
    link.append(number, title);
    item.append(link);
    return item;
  }));
}

function setupGithubLinks() {
  if (!site.githubUrl) return;
  for (const link of document.querySelectorAll('[data-github]')) {
    link.href = site.githubUrl;
    link.hidden = false;
  }
  for (const fallback of document.querySelectorAll('[data-no-github]')) fallback.hidden = true;
}

export function setupSiteHeader() {
  setupNav();
  setupHeader();
  setupNavHighlight();
  setupNavMenu();
  renderGuideOutline();
  setupGithubLinks();
}
