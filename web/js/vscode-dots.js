// The Visual Studio Code logo, drawn as a grid of dots.
//
// The silhouette is the one Visual Studio Code itself uses: the path comes from its own icon
// (`microsoft/vscode`, MIT licence). It is rasterised once in a canvas to find out which points
// of the grid fall inside the shape, and only those become dots; the shape is never redrawn.
//
// When the pointer moves over the logo, the dots near it grow and brighten. And when the logo is
// clicked, the command that installs the extension is copied to the clipboard.
//
// The Visual Studio Code logo is a trademark of Microsoft. It is used here only to point at the
// editor the extension is for, and it is not modified.

import { copyText } from './code-window.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

// The silhouette of the logo, and the box it lives in.
const LOGO = {
  size: 96,
  path: 'M65.566 89.4264C66.889 89.9418 68.3976 89.9087 69.7329 89.2662L87.0271 80.9446C88.8444 80.0701 90 78.231 90 76.2132V19.7872C90 17.7695 88.8444 15.9303 87.0271 15.0559L69.7329 6.73395C67.9804 5.89069 65.9295 6.09724 64.3914 7.21543C64.1716 7.37517 63.9624 7.55352 63.7659 7.75007L30.6583 37.9548L16.2372 27.0081C14.8948 25.9891 13.0171 26.0726 11.7702 27.2067L7.14495 31.4141C5.61986 32.8014 5.61811 35.2007 7.14117 36.5902L19.6476 48.0001L7.14117 59.4099C5.61811 60.7995 5.61986 63.1988 7.14495 64.5861L11.7702 68.7934C13.0171 69.9276 14.8948 70.0111 16.2372 68.9921L30.6583 58.0453L63.7659 88.2501C64.2897 88.7741 64.9046 89.1688 65.566 89.4264ZM69.0128 28.9311L43.8917 48.0001L69.0128 67.069V28.9311Z',
};

// The side of each square of the grid, in the units of the logo.
const CELL = 3;
// How far the light of the pointer reaches, in the same units.
const REACH = 14;
// How finely the shape is rasterised, so the edge of the logo is exact.
const RESOLUTION = 4;

/**
 * The points of the grid that fall inside the silhouette.
 * @returns {{x: number, y: number}[]}
 */
function pointsInsideShape() {
  if (typeof Path2D === 'undefined') return [];
  const pixels = LOGO.size * RESOLUTION;
  const canvas = document.createElement('canvas');
  canvas.width = pixels;
  canvas.height = pixels;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return [];
  context.fillStyle = '#fff';
  // The path is drawn in the units of the logo, so the canvas is scaled first: each unit of the
  // logo is `RESOLUTION` pixels, and the edge of the shape falls where it should.
  context.scale(RESOLUTION, RESOLUTION);
  // The inner triangle of the logo is a hole: the rule `evenodd` is the one its own icon uses.
  context.fill(new Path2D(LOGO.path), 'evenodd');
  const { data } = context.getImageData(0, 0, pixels, pixels);
  const points = [];
  for (let y = CELL / 2; y < LOGO.size; y += CELL) {
    for (let x = CELL / 2; x < LOGO.size; x += CELL) {
      const pixel = Math.floor(y * RESOLUTION) * pixels + Math.floor(x * RESOLUTION);
      if (data[pixel * 4 + 3] > 128) points.push({ x, y });
    }
  }
  return points;
}

/**
 * The dots of the grid, as SVG circles.
 * @param {SVGElement} svg
 * @param {{x: number, y: number}[]} points
 * @returns {SVGElement[]}
 */
function buildDots(svg, points) {
  const field = document.createElementNS(SVG_NS, 'g');
  field.setAttribute('class', 'vscode-dots__field');
  const dots = points.map((point, index) => {
    const dot = document.createElementNS(SVG_NS, 'circle');
    dot.setAttribute('class', 'vscode-dots__dot');
    dot.setAttribute('cx', point.x.toFixed(2));
    dot.setAttribute('cy', point.y.toFixed(2));
    dot.setAttribute('r', '0.9');
    // The order of the dots, so they can come in one after another.
    dot.style.setProperty('--i', String(index));
    field.append(dot);
    return dot;
  });
  svg.append(field);
  return dots;
}

/**
 * The dots near the pointer grow and brighten; the ones that leave the light go back to normal.
 * @param {HTMLElement} container
 * @param {SVGElement} svg
 * @param {{x: number, y: number}[]} points
 * @param {SVGElement[]} dots
 */

function trackPointer(container, svg, points, dots) {
  const REACH = 22;       // Radius of influence of the pointer.
  const MAX_PUSH = 6;     // Maximum separation of the dots.
  const SPRING = 0.16;    // Spring force returning to origin.
  const DAMPING = 0.72;   // Damping of the movement.

  const particles = points.map((point) => ({
    x: point.x,
    y: point.y,
    vx: 0,
    vy: 0
  }));

  let pointer = null;
  let frame = 0;
  let reduced = false;

  function animate() {
    let moving = false;

    const box = svg.getBoundingClientRect();

    if (!box.width || !box.height) return;

    for (let i = 0; i < particles.length; i++) {
      const particle = particles[i];
      const origin = points[i];

      // The spring always pulls the particle back to its origin.
      let ax = (origin.x - particle.x) * SPRING;
      let ay = (origin.y - particle.y) * SPRING;

      let near = 0;

      if (pointer) {
        const scaleX = LOGO.size / box.width;
        const scaleY = LOGO.size / box.height;

        const dx = particle.x - pointer.x;
        const dy = particle.y - pointer.y;
        const distance = Math.hypot(dx, dy);

        if (distance < REACH) {
          near = (1 - distance / REACH) ** 2;

          // If the pointer coincides exactly with a dot,
          // use a safe direction to avoid division by zero.
          const safeDistance = Math.max(distance, 0.001);
          const force = near * MAX_PUSH * 0.18;

          ax += (dx / safeDistance) * force;
          ay += (dy / safeDistance) * force;
        }
      }

      particle.vx = (particle.vx + ax) * DAMPING;
      particle.vy = (particle.vy + ay) * DAMPING;

      particle.x += particle.vx;
      particle.y += particle.vy;

      // Stop the animation when motion becomes imperceptible.
      if (
        Math.abs(particle.x - origin.x) > 0.015 ||
        Math.abs(particle.y - origin.y) > 0.015 ||
        Math.abs(particle.vx) > 0.015 ||
        Math.abs(particle.vy) > 0.015
      ) {
        moving = true;
      } else {
        particle.x = origin.x;
        particle.y = origin.y;
        particle.vx = 0;
        particle.vy = 0;
      }

      dots[i].setAttribute("cx", particle.x.toFixed(3));
      dots[i].setAttribute("cy", particle.y.toFixed(3));
      dots[i].style.setProperty("--near", near.toFixed(3));
    }

    // Request another frame only while there is interaction
    // or the dots are still returning to their positions.
    if (pointer || moving) {
      frame = requestAnimationFrame(animate);
    }
  }

  function startAnimation() {
    if (!frame) {
      frame = requestAnimationFrame(animate);
    }
  }

  function stopAnimation() {
    if (frame) {
      cancelAnimationFrame(frame);
      frame = 0;
    }
  }

  function setReduced(value) {
    if (value === reduced) return;
    reduced = value;
    if (reduced) {
      // Reset all particles to their origins immediately.
      for (let i = 0; i < particles.length; i++) {
        particles[i].x = points[i].x;
        particles[i].y = points[i].y;
        particles[i].vx = 0;
        particles[i].vy = 0;
        dots[i].setAttribute("cx", points[i].x.toFixed(3));
        dots[i].setAttribute("cy", points[i].y.toFixed(3));
        dots[i].style.removeProperty("--near");
      }
      stopAnimation();
      pointer = null;
    }
  }

  // Listen for prefers-reduced-motion changes at runtime.
  const mediaQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const handleChange = (event) => setReduced(event.matches);
  mediaQuery.addEventListener('change', handleChange);

  // Initial state.
  setReduced(mediaQuery.matches);

  container.addEventListener("pointermove", (event) => {
    if (reduced) return;

    const box = svg.getBoundingClientRect();

    if (!box.width || !box.height) return;

    pointer = {
      x: (event.clientX - box.left) * (LOGO.size / box.width),
      y: (event.clientY - box.top) * (LOGO.size / box.height)
    };

    startAnimation();
  });

  container.addEventListener("pointerleave", () => {
    pointer = null;
    startAnimation();
  });

  // Clean up on unmount (if the container is removed).
  const observer = new MutationObserver(() => {
    if (!document.body.contains(container)) {
      mediaQuery.removeEventListener('change', handleChange);
      stopAnimation();
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * The dots come in when the logo scrolls into view.
 * @param {HTMLElement} container
 */
function revealWhenSeen(container) {
  if (!('IntersectionObserver' in window)) {
    container.classList.remove('vscode-dots--pending');
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.remove('vscode-dots--pending');
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }, { rootMargin: '0px 0px -12% 0px' });
  observer.observe(container);
}

/**
 * The logo copies the command that installs the extension, and says what it copied.
 * @param {HTMLElement} container
 */
async function copyCommand(container) {
  const command = container.getAttribute('data-command');
  if (!command) return;
  const copied = await copyText(command);
  const hint = container.querySelector('[data-vscode-hint]');
  if (!hint) return;
  hint.textContent = copied ? 'VS Code installer copied' : 'Copy failed';
  hint.classList.add('is-shown');
  clearTimeout(container.hintTimer);
  container.hintTimer = setTimeout(() => hint.classList.remove('is-shown'), 2200);
}

/**
 * Draws the logo of Visual Studio Code in dots, wherever the page asks for it.
 */
export function mountVscodeDots() {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  for (const container of document.querySelectorAll('[data-vscode-dots]')) {
    const svg = container.querySelector('svg');
    if (!svg) continue;
    const points = pointsInsideShape();
    if (points.length === 0) continue;
    const dots = buildDots(svg, points);
    if (!reduced) {
      trackPointer(container, svg, points, dots);
      container.classList.add('vscode-dots--pending');
      revealWhenSeen(container);
    } else {
      container.classList.add('is-visible');
    }
    container.addEventListener('click', () => copyCommand(container));
  }
}
