/* The steps list (List view of a run): a map step shows its progress and a button that opens the same panel as the graph
   does, inside the step's own item. */
import { mountMapPanel, panelId, syncAddress } from './map.js';
import { parseRoute } from '../router.js';

/** Make the "Show items" buttons of a drawn list work; a panel named in the address starts open. */
export function wireMapSlots(el, run, route) {
  el.querySelectorAll('[data-map-toggle]').forEach((btn) => {
    const name = btn.getAttribute('data-map-toggle');
    const slot = el.querySelector('[data-map-slot="' + name + '"]');
    const step = run.steps.find((s) => s.name === name);
    const def = run.defs[run.steps.indexOf(step)];
    if (!slot || !step || !step.map) return;
    const label = btn.querySelector('.step__map-txt');
    const open = (focus) => {
      slot.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      if (label) label.textContent = 'Hide items';
      mountMapPanel(slot, {
        run, step, def, route, live: run.status === 'running', focus,
        onClose: () => close(true),
      });
    };
    const close = (focusBack) => {
      slot.hidden = true;
      slot.innerHTML = '';
      if (slot._mpTimer) clearInterval(slot._mpTimer);
      btn.setAttribute('aria-expanded', 'false');
      if (label) label.textContent = 'Show items';
      if (parseRoute(location.hash).map) syncAddress(run, null);
      if (focusBack) btn.focus();
    };
    btn.setAttribute('aria-controls', panelId(name));
    btn.addEventListener('click', () => (slot.hidden ? open(true) : close(false)));
    if (route && route.map === name) open(false);
  });
}
