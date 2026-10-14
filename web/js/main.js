import { playgroundRuntime, roadmap, statusLabels } from './config.js';
import { mountCodeWindows } from './code-window.js';
import { mountPlayground } from './playground.js';
import { setupDocsPages } from './docs-pages.js';
import { setupSiteHeader } from './site-header.js';

document.documentElement.classList.add('js');

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

// Section titles on the landing page: as each one scrolls in, its eyebrow decodes from random
// characters and the heading's words rise out of a blur one after another.
function setupHeadingEffects() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const eyebrows = [...document.querySelectorAll('#main > .section .eyebrow')]
    .filter((eyebrow) => eyebrow.nextElementSibling?.tagName === 'H2');
  if (eyebrows.length === 0) return;

  const glyphs = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ<>/_#*+=';

  function decode(eyebrow) {
    const text = eyebrow.textContent;
    const frames = 22;
    let frame = 0;
    const timer = setInterval(() => {
      frame += 1;
      eyebrow.textContent = [...text].map((char, i) => {
        if (char === ' ' || frame >= frames * (0.35 + 0.65 * (i / text.length))) return char;
        return glyphs[Math.floor(Math.random() * glyphs.length)];
      }).join('');
      if (frame >= frames) {
        clearInterval(timer);
        eyebrow.textContent = text;
      }
    }, 38);
  }

  function splitWords(heading) {
    const words = heading.textContent.trim().split(/\s+/);
    heading.setAttribute('aria-label', words.join(' '));
    heading.replaceChildren(...words.flatMap((word, i) => {
      const span = document.createElement('span');
      span.className = 'fx-word';
      span.setAttribute('aria-hidden', 'true');
      span.style.setProperty('--i', String(i));
      span.textContent = word;
      return i === 0 ? [span] : [' ', span];
    }));
  }

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      entry.target.classList.add('is-shown');
      decode(entry.target.querySelector('.eyebrow'));
    }
  }, { rootMargin: '0px 0px -15% 0px' });

  for (const eyebrow of eyebrows) {
    const head = eyebrow.parentElement;
    splitWords(eyebrow.nextElementSibling);
    head.classList.add('fx-head');
    observer.observe(head);
  }
}

setupSiteHeader();
mountCodeWindows();
setupHeadingEffects();
mountPlayground(playgroundRuntime);
renderRoadmap();
setupDocsPages();
setupReveal();

for (const year of document.querySelectorAll('[data-year]')) {
  year.textContent = String(new Date().getFullYear());
}
