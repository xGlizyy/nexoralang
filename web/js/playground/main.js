// Entry point of the playground page.

import { site } from '../config.js';
import { createClient } from './client.js';
import { createController } from './controller.js';
import { mountView } from './view.js';

function sessionStore() {
  try {
    // The code stays in this browser tab. Nothing is saved on the server.
    sessionStorage.setItem('nexora.playground.probe', '1');
    sessionStorage.removeItem('nexora.playground.probe');
    return sessionStorage;
  } catch {
    return null;
  }
}

const root = document.querySelector('[data-playground-app]');
let render = () => {};

const controller = createController({
  client: createClient(),
  render: (state) => render(state),
  storage: sessionStore(),
  clipboard: navigator.clipboard ?? null,
});

render = mountView(root, controller, { githubUrl: site.githubUrl });
controller.init();
