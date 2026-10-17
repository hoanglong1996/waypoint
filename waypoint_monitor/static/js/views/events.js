/* The Events tab of a run: a time-ordered timeline of what the run did (specs/012-duration-and-run-events).
   Derived entries come from the monitor, the others from the pipeline; all text is escaped, never HTML. */
import { loadEvents } from '../api.js';
import {
  EVENT_LEVELS, esc, eventNotes, eventWord, filterSummary, fmt, hhmmss, stepChoices,
} from '../model.js';
import { buildRoute } from '../router.js';
import { I } from '../ui.js';

const PAGE = 200;
const ICON = { info: I.info, warning: I.alert, error: I.xCircle };

const fullTime = (d) => d.toISOString().replace('T', ' ').replace('Z', ' UTC');

function fieldChips(fields) {
  if (!fields) return '';
  return '<span class="event__fields">' + Object.keys(fields).map((k) =>
    '<span class="chip event__field"><span class="event__fname">' + esc(k) + '</span> <b>' +
    (typeof fields[k] === 'number' ? esc(fmt(fields[k])) : esc(fields[k])) + '</b></span>').join('') + '</span>';
}

/** One entry of the timeline. `route` is the run's route; the step chip filters the timeline to that step. */
export function eventRowHTML(e, route) {
  const word = eventWord(e.level);
  const stepLink = e.step
    ? '<a class="chip event__step" href="' + esc(buildRoute({ ...route, tab: 'events', step: e.step })) + '" title="Show only this step">' + esc(e.step) + '</a>'
    : '';
  const msg = e.message == null
    ? '<span class="event__msg faint">message not stored</span>'
    : '<span class="event__msg">' + esc(e.message) + '</span>';
  return (
    '<li class="event event--' + e.level + (e.source === 'monitor' ? ' event--derived' : '') + '" data-id="' + esc(e.id) + '">' +
    '<time class="event__time num" datetime="' + esc(e.ts.toISOString()) + '" title="' + esc(fullTime(e.ts)) + '">' + hhmmss(e.ts) + '</time>' +
    '<span class="event__level event__level--' + e.level + '">' + ICON[e.level] + '<span>' + word + '</span></span>' +
    '<span class="event__body">' + msg + fieldChips(e.fields) + '</span>' +
    '<span class="event__meta">' + stepLink + (e.source === 'monitor' ? '<span class="tag-monitor" title="Worked out by the monitor from the run’s records">monitor</span>' : '') + '</span></li>'
  );
}

function toolbarHTML(run, route, steps, summary) {
  const levels = route.levels || [];
  const checked = (k) => !levels.length || levels.includes(k);
  const boxes = EVENT_LEVELS.map((l) =>
    '<label class="segmented__opt event-filter"><input type="checkbox" name="ev-level" value="' + l.key + '"' + (checked(l.key) ? ' checked' : '') + '><span>' + ICON[l.key] + l.word + '</span></label>').join('');
  const opts = '<option value="">All steps</option>' + steps.map((n) =>
    '<option value="' + esc(n) + '"' + (route.step === n ? ' selected' : '') + '>' + esc(n) + '</option>').join('');
  return '<div class="events__bar"><fieldset class="segmented segmented--levels"><legend class="sr-only">Levels</legend>' + boxes + '</fieldset>' +
    '<label class="events__step"><span class="sr-only">Step</span><select id="ev-step" class="select" aria-label="Step">' + opts + '</select></label>' +
    '<span class="events__count" id="ev-count" role="status">' + esc(summary) + '</span></div>';
}

let current = null; // the mounted timeline: {el, run, route, entries, ...}

/** Draw the page for `run`; the list loads after the frame is on screen. */
export function mountEvents(el, { run, route }) {
  const sameRun = current && current.run.id === run.id && current.run.env === run.env;
  const sameFilters = sameRun && JSON.stringify([current.route.levels, current.route.step]) === JSON.stringify([route.levels, route.step]);
  current = {
    el, run, route,
    entries: sameFilters ? current.entries : [],
    info: sameFilters ? current.info : null,
    hasMore: sameFilters ? current.hasMore : false,
    status: sameFilters && current.info ? 'ok' : 'loading',
    announce: '',
  };
  paint();
  wire();
  if (!sameFilters || !current.info) fetchPages(PAGE);
}

/** Refetch what is already loaded (a running run keeps adding events); filters and scroll stay. */
export function refreshEvents() {
  if (!current || !current.el.isConnected) return;
  fetchPages(Math.max(PAGE, current.entries.length));
}

async function fetchPages(upTo) {
  const view = current;
  if (!view) return;
  const { run, route } = view;
  try {
    let entries = [];
    let info = null;
    let more = true;
    while (more && entries.length < upTo) {
      const page = await loadEvents(run.pipeline, run.env, run.id, { levels: route.levels || [], step: route.step, offset: entries.length, limit: Math.min(500, Math.max(PAGE, upTo - entries.length)) });
      if (current !== view) return; // another run or filter was chosen meanwhile
      entries = entries.concat(page.events);
      info = page;
      more = page.hasMore && page.events.length > 0;
    }
    const grew = view.entries.length ? Math.max(0, entries.length - view.entries.length) : 0;
    view.entries = entries;
    view.info = info;
    view.hasMore = more && info ? info.hasMore : false;
    view.status = 'ok';
    view.announce = grew ? grew + ' new event' + (grew === 1 ? '' : 's') : '';
  } catch (err) {
    if (current !== view) return;
    view.status = 'error';
  }
  paint();
}

function paint() {
  const view = current;
  if (!view) return;
  const { el, run, route } = view;
  const info = view.info;
  const steps = stepChoices(run, view.entries);
  const summary = info ? filterSummary(info.matched, info.total) : 'Loading…';
  let body;
  if (view.status === 'error') {
    body = '<div class="events__state" role="alert">Could not load events. <button type="button" class="btn btn--sm" data-ev-retry>Retry</button></div>';
  } else if (view.status === 'loading' && !info) {
    body = '<ul class="events__list events__list--skel" aria-hidden="true">' + [1, 2, 3, 4, 5].map(() => '<li class="event"><span class="skel" style="width:100%;height:18px"></span></li>').join('') + '</ul><span class="sr-only" role="status">Loading events…</span>';
  } else if (!view.entries.length) {
    body = '<div class="events__state" role="status">No events match the filters.</div>';
  } else {
    body = '<ol class="events__list" aria-label="Events, oldest first">' + view.entries.map((e) => eventRowHTML(e, route)).join('') + '</ol>' +
      (view.hasMore ? '<div class="events__more"><button type="button" class="btn" data-ev-more>Load more</button></div>' : '');
  }
  const notes = info ? eventNotes(info).map((n) => '<p class="events__note">' + I.info + '<span>' + esc(n) + '</span></p>').join('') : '';
  el.innerHTML = '<section class="card events" aria-labelledby="events-title"><div class="section-head"><h2 class="section-title" id="events-title">Events</h2></div>' +
    toolbarHTML(run, route, steps, summary) + notes + body +
    '<div class="sr-only" aria-live="polite" id="ev-live">' + esc(view.announce) + '</div></section>';
  wire();
}

function applyFilters() {
  const view = current;
  if (!view) return;
  const boxes = [...view.el.querySelectorAll('input[name="ev-level"]')];
  const on = boxes.filter((b) => b.checked).map((b) => b.value);
  const levels = on.length === 0 || on.length === boxes.length ? [] : on;
  const step = view.el.querySelector('#ev-step').value || null;
  location.hash = buildRoute({ ...view.route, tab: 'events', levels, step });
}

function wire() {
  const view = current;
  if (!view) return;
  const { el } = view;
  el.querySelectorAll('input[name="ev-level"]').forEach((b) => b.addEventListener('change', applyFilters));
  const step = el.querySelector('#ev-step');
  if (step) step.addEventListener('change', applyFilters);
  const more = el.querySelector('[data-ev-more]');
  if (more) more.addEventListener('click', () => { more.disabled = true; fetchPages(view.entries.length + PAGE); });
  const retry = el.querySelector('[data-ev-retry]');
  if (retry) retry.addEventListener('click', () => { view.status = 'loading'; paint(); fetchPages(PAGE); });
}


/* ---------- a step's own events, inside its details (loaded when the disclosure is opened) ---------- */

/** The disclosure of one step; its list is fetched the first time it opens. */
export function stepEventsHTML(run, stepName) {
  return '<details class="step__events" data-ev-pipeline="' + esc(run.pipeline || '') + '" data-ev-env="' + esc(run.env) +
    '" data-ev-run="' + esc(run.id) + '" data-ev-step="' + esc(stepName) + '"><summary>Events of this step</summary>' +
    '<div class="step__events-body" aria-live="polite"></div></details>';
}

/** At most the 10 newest events of the step as rows, with a link to the timeline filtered to the step. */
export function stepEventsListHTML(events, matched, route, stepName) {
  const shown = events.slice(-10);
  const link = '<a class="step__events-all" href="' + esc(buildRoute({ ...route, tab: 'events', step: stepName })) + '">View all in timeline' +
    (matched > shown.length ? ' (' + matched + ' events)' : '') + '</a>';
  if (!shown.length) return '<p class="faint step__events-none">No events for this step.</p>' + link;
  return '<ol class="events__list events__list--step">' + shown.map((e) => eventRowHTML(e, route)).join('') + '</ol>' + link;
}

let stepEventsWired = false;
/** One delegated handler for every step disclosure on the page; safe to call again. */
export function wireStepEvents() {
  if (stepEventsWired || typeof document === 'undefined') return;
  stepEventsWired = true;
  document.addEventListener('toggle', async (ev) => {
    const d = ev.target;
    if (!(d instanceof Element) || !d.matches('details.step__events') || !d.open || d.dataset.loaded) return;
    d.dataset.loaded = '1';
    const body = d.querySelector('.step__events-body');
    const route = { name: 'run', id: d.dataset.evPipeline, env: d.dataset.evEnv, runId: d.dataset.evRun };
    body.innerHTML = '<p class="faint">Loading…</p>';
    try {
      const first = await loadEvents(route.id, route.env, route.runId, { step: d.dataset.evStep, limit: 1 });
      const offset = Math.max(0, first.matched - 10);
      const page = await loadEvents(route.id, route.env, route.runId, { step: d.dataset.evStep, offset, limit: 10 });
      body.innerHTML = stepEventsListHTML(page.events, first.matched, route, d.dataset.evStep);
    } catch (err) {
      delete d.dataset.loaded;
      body.innerHTML = '<p class="faint">Could not load events.</p>';
    }
  }, true);
}
