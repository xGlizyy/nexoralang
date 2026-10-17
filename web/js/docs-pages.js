// Documentation and language guide: each section is shown on its own, as a page of its own
// (docs.html#status, guide.html#types, …).
// Without JavaScript the whole document stays visible as one long page.
export function setupDocsPages() {
  const article = document.querySelector('.docs__article');
  if (!article) return;
  const sections = [...article.querySelectorAll(':scope > section[id]')];
  if (sections.length === 0) return;

  // Everything outside the sections (page title, lead, notice) belongs to the first page.
  const intro = [...article.children].filter((element) => !sections.includes(element));
  const baseTitle = document.title;
  // The heading's own text, without any badge inside it ("Contracts", not "ContractsExperimental").
  const titleOf = (section) => section.querySelector('h2').firstChild.textContent.trim();

  const pager = document.createElement('nav');
  pager.className = 'docs__pager';
  pager.setAttribute('aria-label', 'Documentation pages');
  article.append(pager);
  article.classList.add('docs__article--paged');
  // With JavaScript the stylesheet hides the index beside the article and centres the article on
  // its own: the Documentation outline in the header and the pager move between the sections.
  article.parentElement?.classList.add('docs--paged');

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

    // Every link that points at one of these sections — the index beside the article and the
    // Documentation outline in the header — marks the section being read. The outline is built
    // after the page loads, so the links are looked up again on every change.
    const ids = sections.map((section) => `#${section.id}`);
    for (const link of document.querySelectorAll('a[href]')) {
      if (!ids.includes(link.hash)) continue;
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
