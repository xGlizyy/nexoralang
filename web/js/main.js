import { playgroundRuntime, roadmap, site, statusLabels } from './config.js';
import { mountCodeWindows } from './code-window.js';
import { mountPlayground } from './playground.js';

document.documentElement.classList.add('js');

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

// Documentation: each section is shown on its own, as a page of its own (docs.html#status, …).
// Without JavaScript the whole document stays visible as one long page.
function setupDocsPages() {
  const article = document.querySelector('.docs__article');
  if (!article) return;
  const sections = [...article.querySelectorAll(':scope > section[id]')];
  if (sections.length === 0) return;

  // Everything outside the sections (page title, lead, notice) belongs to the first page.
  const intro = [...article.children].filter((element) => !sections.includes(element));
  const tocLinks = [...document.querySelectorAll('.docs__toc a')];
  const baseTitle = document.title;
  const titleOf = (section) => section.querySelector('h2').textContent;

  const pager = document.createElement('nav');
  pager.className = 'docs__pager';
  pager.setAttribute('aria-label', 'Documentation pages');
  article.append(pager);
  article.classList.add('docs__article--paged');

  function pagerLink(section, label, className) {
    const link = document.createElement('a');
    link.href = `#${section.id}`;
    link.className = className;
    const small = document.createElement('small');
    small.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = titleOf(section);
    link.append(small, strong);
    return link;
  }

  function show(index) {
    sections.forEach((section, i) => { section.hidden = i !== index; });
    for (const element of intro) element.hidden = index !== 0;

    for (const link of tocLinks) {
      if (link.hash === `#${sections[index].id}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    document.title = index === 0 ? baseTitle : `${titleOf(sections[index])} — NEXORA`;

    const links = [];
    if (index > 0) links.push(pagerLink(sections[index - 1], '← Previous', 'docs__pager-prev'));
    if (index < sections.length - 1) links.push(pagerLink(sections[index + 1], 'Next →', 'docs__pager-next'));
    pager.replaceChildren(...links);

    scrollTo({ top: 0, behavior: 'instant' });
  }

  // A hash that is not a section (the skip link, for instance) leaves the current page alone.
  addEventListener('hashchange', () => {
    const index = sections.findIndex((section) => `#${section.id}` === location.hash);
    if (index !== -1) show(index);
  });

  show(Math.max(0, sections.findIndex((section) => `#${section.id}` === location.hash)));
  // On arrival the browser scrolls to the section named in the URL; a page starts from its top instead.
  if (location.hash) addEventListener('load', () => scrollTo({ top: 0, behavior: 'instant' }), { once: true });
}

function setupGithubLinks() {
  if (!site.githubUrl) return;
  for (const link of document.querySelectorAll('[data-github]')) {
    link.href = site.githubUrl;
    link.hidden = false;
  }
  for (const fallback of document.querySelectorAll('[data-no-github]')) fallback.hidden = true;
}

function renderRoadmap() {
  for (const list of document.querySelectorAll('[data-roadmap]')) {
    list.replaceChildren(...roadmap.map((phase, index) => {
      const item = document.createElement('li');
      item.className = `phase phase--${phase.status}`;
      item.dataset.reveal = '';

      const number = document.createElement('span');
      number.className = 'phase__number';
      number.textContent = `Phase ${index + 1}`;

      const title = document.createElement('h3');
      title.textContent = phase.title;

      const description = document.createElement('p');
      description.textContent = phase.description;

      const status = document.createElement('span');
      status.className = `chip chip--${phase.status}`;
      status.textContent = statusLabels[phase.status];

      item.append(number, title, description, status);
      return item;
    }));
  }
}

// Only elements that start below the fold are animated, so nothing visible ever flickers.
function setupReveal() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.remove('reveal-pending');
      observer.unobserve(entry.target);
    }
  }, { rootMargin: '0px 0px -12% 0px' });

  for (const element of document.querySelectorAll('[data-reveal]')) {
    if (element.getBoundingClientRect().top < innerHeight) continue;
    // Siblings that share a row come in one after another instead of all at once.
    const siblings = [...element.parentElement.children].filter((child) => child.hasAttribute('data-reveal'));
    element.style.setProperty('--reveal-delay', `${Math.min(siblings.indexOf(element), 4) * 0.11}s`);
    element.classList.add('reveal-pending');
    observer.observe(element);
  }
}

mountCodeWindows();
mountPlayground(playgroundRuntime);
setupNav();
setupHeader();
setupNavHighlight();
setupNavMenu();
setupGithubLinks();
renderRoadmap();
setupDocsPages();
setupReveal();

for (const year of document.querySelectorAll('[data-year]')) {
  year.textContent = String(new Date().getFullYear());
}
