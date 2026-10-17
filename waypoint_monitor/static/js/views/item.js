/* The item page (specs/014, design 3.3): one item of a map step with its inner steps in order, counts, durations, errors,
   metrics and events. It has its own address (#/p/<pipeline>/runs/<env>/<run>/steps/<map>/items/<key>) so it can be shared.
   Data: GET …/maps/<map>/items/<key> and GET …/events?item=<key>; a running item refreshes with the page and keeps its
   scroll position and focus. All text is escaped; nothing here puts pipeline text in markup. */
import { loadEvents, loadItem } from '../api.js';
import {
  currentStepOf, fmtMs, innerMetricDecl, itemStepsView, metricCheckText, panelRoute, slowRatio,
} from '../map-model.js';
import {
  innerStepHTML, itemEventsHTML, itemMetricsHTML, itemStatePill, lostFlag, mapIcon, mapIconSmall, slowFlag,
} from '../map-ui.js';
import { esc, fmt, formatMetricValue, hhmmss } from '../model.js';
import { buildRoute } from '../router.js';
import { errorBlockHTML } from './step.js';
import { markReturn, savedPanelState } from './map.js';

let current = null; // the mounted page: {el, ctx, detail, events, state}
let keyWired = false;

const put = (node, html) => {
  if (node && node._html !== html) {
    node._html = html;
    node.innerHTML = html;
  }
};

/** A page that is one block of markup (loading, no record, no map), not the shell of the full item page. */
const solo = (doc, html) => {
  doc._shell = null;
  put(doc, html);
};

const backHash = (ctx) => buildRoute(panelRoute(ctx.run, ctx.route.map, savedPanelState(ctx.run, ctx.route.map)));

function crumbHTML(ctx) {
  const { run, route } = ctx;
  const step = run.steps.find((s) => s.name === route.map);
  const def = run.defs[run.steps.indexOf(step)];
  const label = (def && def.label) || route.map;
  return '<nav class="mp-crumb" aria-label="Breadcrumb">' +
    '<a href="' + esc(buildRoute({ name: 'pipeline', id: route.id, page: 'history', env: route.env })) + '">' + esc(ctx.label) + '</a><span aria-hidden="true">›</span>' +
    '<a href="' + esc(buildRoute({ name: 'run', id: route.id, env: route.env, runId: route.runId })) + '">' + esc(ctx.runLabel) + '</a><span aria-hidden="true">›</span>' +
    '<a class="mp-crumb__map" href="' + esc(backHash(ctx)) + '">' + mapIconSmall('loop') + esc(label) + '</a><span aria-hidden="true">›</span>' +
    '<span class="mono mp-crumb__key" aria-current="page">' + esc(route.key) + '</span></nav>';
}

function mapOf(ctx) {
  const i = ctx.run.steps.findIndex((s) => s.name === ctx.route.map && s.map);
  return i < 0 ? null : { step: ctx.run.steps[i], def: ctx.run.defs[i] };
}

function headerHTML(ctx, detail) {
  const { run, route } = ctx;
  const m = mapOf(ctx);
  const label = (m.def && m.def.label) || route.map;
  const median = m.step.map.duration.enough ? m.step.map.duration.medianMs : null;
  const live = detail && detail.state === 'running';
  const ms = detail ? (live ? detail.elapsedMs : detail.durationMs) : null;
  const slow = detail && detail.slow ? slowFlag(slowRatio(ms, median)).replace('mp-pill--sm', 'mp-pill--lg') : '';
  const failedStep = detail ? detail.steps.find((s) => s.state === 'failed') : null;
  const meta = [];
  if (detail) {
    if (detail.startedAt) meta.push('<span>' + mapIconSmall('calendar') + 'started <b>' + esc(hhmmss(detail.startedAt)) + '</b></span>');
    if (live && ms != null) {
      meta.push('<span>' + mapIconSmall('slow') + 'running for <b class="num" data-elapsed="' + ms / 1000 + '" data-fetched="' + detail.fetchedAt + '">' + esc(fmtMs(ms)) + '</b>' +
        (median ? ' (median ≈' + esc(fmtMs(median)) + ')' : '') + '</span>');
    } else if (ms != null) {
      meta.push('<span>' + mapIconSmall('slow') + 'duration <b>' + esc(fmtMs(ms)) + '</b>' + (median ? ' (median ≈' + esc(fmtMs(median)) + ')' : '') + '</span>');
    }
    if (failedStep) {
      meta.push('<span>failed at <b class="mono mp-bad">' + esc(failedStep.name) + '</b>' + (failedStep.error ? ' · ' + esc(failedStep.error.type) : '') + '</span>');
    } else if (live) {
      const at = currentStepOf(detail);
      if (at) meta.push('<span>now at <b class="mono">' + esc(at) + '</b></span>');
    }
    meta.push('<span>order started <b>#' + esc(fmt(detail.index)) + '</b></span>');
  }
  const link = location.origin + location.pathname + buildRoute(route);
  return '<div class="mp-ihead__top"><a class="mp-btn mp-btn--lg" href="' + esc(backHash(ctx)) + '" data-mp-back aria-label="Back to ' + esc(label) + ' items (Escape)">' +
    mapIcon('back') + 'Back to items</a>' +
    '<div class="mp-ihead__link"><span class="mono mp-faint mp-wrap">' + esc(buildRoute(route)) + '</span>' +
    '<button type="button" class="mp-btn" data-mp-copylink="' + esc(link) + '">' + mapIconSmall('link') + 'Copy link</button></div></div>' +
    '<div class="mp-ihead__title"><div class="mp-eyebrow mp-eyebrow--map mp-full">Item of map step ' + esc(label) + '</div>' +
    '<h1 class="mono" id="item-title" tabindex="-1">' + esc(route.key) + '</h1>' +
    (detail ? itemStatePill(detail.state, 'lg') + slow : '') + '</div>' +
    (meta.length ? '<div class="mp-meta">' + meta.join('') + '</div>' : '') +
    (live && run.status === 'running'
      ? '<div class="mp-live" role="status" aria-live="polite"><span class="mp-ldot" aria-hidden="true"></span><span><b>Live</b> · refreshes every 5 s</span><span class="mp-faint">Your scroll position is kept on refresh.</span></div>'
      : '');
}

function stepsHTML(ctx, detail) {
  const m = mapOf(ctx);
  const view = itemStepsView(detail).map((s, i) => ({ ...s, liveSeconds: null, fetchedAt: detail.fetchedAt, raw: detail.steps[i] }));
  view.forEach((s) => {
    if (s.kind === 'running' && s.raw.startedAt) s.liveSeconds = Math.max(0, (Date.now() - s.raw.startedAt.getTime()) / 1000);
  });
  const names = (m.def && m.def.map ? m.def.map.steps.map((x) => x.name) : view.map((s) => s.name)).join(' → ');
  const rows = view.map((s, i) => {
    const err = s.error ? errorBlockHTML({ env: ctx.run.env, id: ctx.run.id }, { name: ctx.route.key + '|' + s.name, error: s.error }, false) : '';
    return innerStepHTML(s, i === view.length - 1, err);
  }).join('');
  const own = detail.error
    ? '<div class="mp-own-error">' + errorBlockHTML({ env: ctx.run.env, id: ctx.run.id }, { name: ctx.route.key + '|item', error: detail.error }, false) + '</div>'
    : '';
  const compact = detail.compact
    ? '<p class="mp-note">This item has a short record: its stack trace, metrics and detailed counts are not kept for items beyond the first 1,000.</p>'
    : '';
  return '<div class="mp-sec-h"><h2 id="mp-st-h">Inner steps</h2><span class="mp-faint">' + esc(names) + '</span></div>' +
    own + (view.length ? '<ol class="mp-isteps">' + rows + '</ol>' : '<p class="mp-note">No inner step has reported for this item yet.</p>') + compact;
}

function metricsHTML(ctx, detail) {
  const m = mapOf(ctx);
  const withMetrics = detail.steps.filter((s) => s.metrics.length);
  const prefix = withMetrics.length > 1;
  const rows = [];
  withMetrics.forEach((s) => s.metrics.forEach((x) => {
    const decl = innerMetricDecl(m.def, s.name, x.name);
    rows.push({
      step: prefix ? s.name : null,
      label: x.label || x.name,
      value: formatMetricValue(x.value, x.unit || (decl && decl.unit)),
      check: metricCheckText(x, decl),
    });
  }));
  return itemMetricsHTML(rows);
}

function noRecordHTML(ctx) {
  const m = mapOf(ctx);
  const label = (m.def && m.def.label) || ctx.route.map;
  const kept = m.step.map.detail.kept;
  return '<section class="mp-card mp-norecord" aria-labelledby="item-title">' +
    '<a class="mp-btn mp-btn--lg" href="' + esc(backHash(ctx)) + '" data-mp-back>' + mapIcon('back') + 'Back to items</a>' +
    '<div class="mp-eyebrow mp-eyebrow--map">Item of map step ' + esc(label) + '</div>' +
    '<h1 class="mono" id="item-title" tabindex="-1">' + esc(ctx.route.key) + '</h1>' +
    '<div class="mp-notice" role="status">' + mapIcon('info') + '<span>This item has no record of its own (item detail is partial). It is still counted in the map step totals.</span></div>' +
    '<a class="mp-link" href="' + esc(backHash(ctx)) + '">Go to the item list (' + esc(fmt(kept)) + ' items with a record)</a></section>';
}

function noMapHTML(ctx) {
  return '<section class="mp-card mp-norecord"><a class="mp-btn mp-btn--lg" href="' + esc(buildRoute({ name: 'run', id: ctx.route.id, env: ctx.route.env, runId: ctx.route.runId })) + '">' +
    mapIcon('back') + 'Back to the run</a><h1 id="item-title" tabindex="-1">Map step not found</h1>' +
    '<div class="mp-notice" role="status">' + mapIcon('info') + '<span>This run has no map step named <span class="mono">' + esc(ctx.route.map) + '</span>.</span></div></section>';
}

function paint() {
  const { el, ctx, detail, events, state } = current;
  const doc = el.querySelector('[data-item-doc]');
  if (!doc) return;
  const m = mapOf(ctx);
  if (!m) {
    solo(doc, noMapHTML(ctx));
    return;
  }
  if (state === 'norecord') {
    solo(doc, noRecordHTML(ctx));
    return;
  }
  if (!detail) {
    solo(doc, crumbHTML(ctx) + '<header class="mp-card mp-ihead">' + headerHTML(ctx, null) + '</header>' +
      '<div class="mp-card mp-pad" role="status">' + (state === 'error' ? 'This item could not be loaded. The page tries again by itself.' : 'Loading item…') + '</div>');
    return;
  }
  const shell = '<div data-i="crumb"></div><header class="mp-card mp-ihead" data-i="head"></header>' +
    '<div class="mp-grid"><section class="mp-card" aria-labelledby="mp-st-h" data-i="steps"></section>' +
    '<div class="mp-col"><div data-i="metrics"></div><div data-i="events"></div></div></div>';
  if (doc._shell !== 'full') {
    doc._shell = 'full';
    doc._html = null;
    doc.innerHTML = shell;
    doc.querySelectorAll('[data-i]').forEach((n) => { n._html = null; });
  }
  const part = (k) => doc.querySelector('[data-i="' + k + '"]');
  put(part('crumb'), crumbHTML(ctx));
  put(part('head'), headerHTML(ctx, detail));
  put(part('steps'), stepsHTML(ctx, detail));
  put(part('metrics'), metricsHTML(ctx, detail));
  const sorted = (events || []).slice().sort((a, b) => a.ts - b.ts);
  put(part('events'), itemEventsHTML(sorted, sorted.length + ' event' + (sorted.length === 1 ? '' : 's') + ' · oldest first'));
}

async function fetchAll() {
  const { ctx } = current;
  const { route } = ctx;
  const mine = current;
  try {
    const [detail, ev] = await Promise.all([
      loadItem(route.id, route.env, route.runId, route.map, route.key),
      loadEvents(route.id, route.env, route.runId, { item: route.key, limit: 200 }).catch(() => null),
    ]);
    if (current !== mine) return;
    if (detail == null) {
      current.state = 'norecord';
      current.detail = null;
    } else {
      current.state = 'ok';
      current.detail = detail;
      if (ev) current.events = ev.events;
    }
  } catch (err) {
    if (current !== mine) return;
    current.state = current.detail ? 'ok' : 'error';
  }
  paint();
  if (current.state === 'ok' && !current.focused) {
    current.focused = true;
    const h = current.el.querySelector('#item-title');
    if (h && !document.activeElement.closest('[data-item-doc]')) h.focus({ preventScroll: true });
  }
}

/** Draw the item page for `ctx`: {run, route, cfg, label (pipeline), runLabel}. Data loads after the frame is on screen. */
export function mountItem(el, ctx) {
  const same = current && current.el === el && current.ctx.route.key === ctx.route.key && current.ctx.route.map === ctx.route.map && current.ctx.run.id === ctx.run.id;
  const keep = same ? current : null;
  current = {
    el, ctx, detail: keep ? keep.detail : null, events: keep ? keep.events : [], state: keep ? keep.state : 'loading', focused: keep ? keep.focused : false,
  };
  if (!el.querySelector('[data-item-doc]') || !same) {
    el.innerHTML = '<div data-item-doc></div>';
  }
  wire(el);
  paint();
  fetchAll();
}

/** Reload the page that is on screen (called with every refresh of the run). Rows and scroll stay. */
export function refreshItem() {
  if (current && current.el.isConnected && !current.el.hidden) fetchAll();
}

function wire(el) {
  if (!el._itemWired) {
    el._itemWired = true;
    el.addEventListener('click', (ev) => {
      const back = ev.target instanceof Element ? ev.target.closest('[data-mp-back], .mp-crumb__map') : null;
      if (back && current) markReturn(current.ctx.run, current.ctx.route.map);
      const t = ev.target instanceof Element ? ev.target.closest('[data-mp-copylink]') : null;
      if (!t) return;
      const url = t.getAttribute('data-mp-copylink');
      const idle = t.innerHTML;
      const done = (text) => {
        t.textContent = text;
        setTimeout(() => { t.innerHTML = idle; }, 2000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(() => done('Copied'), () => done('Copy failed'));
      else done('Copy failed');
    });
  }
  if (!keyWired) {
    keyWired = true;
    document.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Escape' || !current || !current.el.isConnected || current.el.hidden) return;
      const t = ev.target instanceof Element ? ev.target : null;
      if (t && t.closest('input, select, textarea')) return;
      ev.preventDefault();
      markReturn(current.ctx.run, current.ctx.route.map);
      location.hash = backHash(current.ctx);
    });
  }
}
