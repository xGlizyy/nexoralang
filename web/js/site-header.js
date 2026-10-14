// Site header shared by every page: folding into a menu when it does not fit, the menu itself,
// the shrinking bar, the link highlight, the Documentation outline and the GitHub links.

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

// Below 1180px the links always fold into the menu. Above it they fold only when they do not fit
// beside the actions in the full-size bar, because labels can be longer than the English ones: a
// page translated by the browser, or a long name once someone has signed in.
function setupCollapse() {
  const root = document.documentElement;
  const header = document.querySelector('.site-header');
  const row = header?.querySelector('.site-header__row');
  const brand = header?.querySelector('.brand');
  const links = header?.querySelector('.site-nav__links');
  const actions = header?.querySelector('.site-nav__actions');
  const nav = document.getElementById('site-nav');
  const toggle = header?.querySelector('.nav-toggle');
  if (!row || !brand || !links || !actions) return;

  const narrow = matchMedia('(max-width: 1180px)');
  const MIN_GAP = 40;

  // The actions sit at the end of a wider grid cell: what matters is where their content starts.
  function contentLeft(element) {
    const lefts = [...element.children].map((child) => child.getBoundingClientRect())
      .filter((box) => box.width > 0).map((box) => box.left);
    return lefts.length ? Math.min(...lefts) : element.getBoundingClientRect().right;
  }

  // Lays the bar out at full size for a moment (no paint happens in between) and checks the room.
  function fullBarFits() {
    const scrolled = header.classList.contains('is-scrolled');
    root.classList.remove('nav-collapsed');
    header.classList.remove('is-scrolled');
    const brandBox = brand.getBoundingClientRect();
    const linksBox = links.getBoundingClientRect();
    const fits = row.scrollWidth <= row.clientWidth + 1
      && linksBox.left - brandBox.right >= MIN_GAP
      && contentLeft(actions) - linksBox.right >= MIN_GAP;
    header.classList.toggle('is-scrolled', scrolled);
    return fits;
  }

  function update() {
    root.classList.add('nav-measuring');
    const collapse = narrow.matches || !fullBarFits();
    root.classList.toggle('nav-collapsed', collapse);
    void row.offsetWidth;   // settle the final layout while transitions are still off
    root.classList.remove('nav-measuring');
    if (!collapse && nav?.classList.contains('is-open')) {
      nav.classList.remove('is-open');
      toggle?.setAttribute('aria-expanded', 'false');
      toggle?.setAttribute('aria-label', 'Open menu');
    }
  }

  let pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; update(); });
  }

  update();
  narrow.addEventListener('change', update);
  addEventListener('resize', schedule);
  document.fonts?.ready.then(schedule);
  // Text that changes after load: a translation, or the session area filled in by auth.js.
  new MutationObserver(schedule).observe(header, { subtree: true, childList: true, characterData: true });
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
  setupCollapse();
  setupNav();
  setupHeader();
  setupNavHighlight();
  setupNavMenu();
  renderGuideOutline();
  setupGithubLinks();
}
