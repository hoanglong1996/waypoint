/* Map step (specs/014): markup builders for the graph node, the map panel and the item view.
   Markup, class names and spacing follow docs/design/map-step-design (classes carry an `mp-` / `mn-` prefix so they
   cannot clash with the rest of the dashboard). Every string that comes from a pipeline (keys, step names, error text,
   event text) goes through `esc`; nothing here uses innerHTML on raw data. Status is always an icon plus words. */
import { elapsedLabel, esc, fmt } from './model.js';
import {
  fmtMs, itemFlowStrip, itemRowView, mapAria, mapLostText, mapNodeTone, mapPillText, mapProgressParts, runningWord,
} from './map-model.js';

const svg = (inner, cls = 'mic') => '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true">' + inner + '</svg>';
const small = (inner) => svg(inner, 'mic mic--s');

/* icons: [paths] so they can be drawn at both sizes */
const PATHS = {
  loop: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
  spinner: '<path d="M21 12a9 9 0 1 1-9-9"/>',
  done: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  failed: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  warn: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17v.01"/>',
  power: '<path d="M12 3v8"/><path d="M6.3 7.5a8 8 0 1 0 11.4 0"/>',
  lost: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  slow: '<circle cx="12" cy="14" r="7"/><path d="M12 14v-3M10 3h4M12 3v4"/>',
  notrun: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
  wait: '<path d="M6 3h12M6 21h12M7 3v3l5 6-5 6v3M17 3v3l-5 6 5 6v3"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevDown: '<path d="m6 9 6 6 6-6"/>',
  chevRight: '<path d="m9 6 6 6-6 6"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  arrow: '<path d="M4 12h15M14 7l5 5-5 5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4L3 5z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
};
const icon = (name) => svg(PATHS[name]);
const icon12 = (name) => small(PATHS[name]);
export { icon as mapIcon, icon12 as mapIconSmall };

/* ---------- pills ---------- */
const pill = (tone, name, text, size = 'sm', extra = '') =>
  '<span class="mp-pill mp-pill--' + tone + ' mp-pill--' + size + (extra ? ' ' + extra : '') + '">' + (name ? icon12(name) : '') + esc(text) + '</span>';

const MAP_STATE = {
  running: ['run', 'spinner', 'Running'],
  done: ['ok', 'done', 'Done'],
  failed: ['bad', 'failed', 'Failed'],
  stalled: ['warn', 'warn', 'Stalled'],
  died: ['bad', 'power', 'Died'],
};

/** The state of a map step or an item as a pill: icon and word. */
export function mapStatePill(state, size = 'sm') {
  const [tone, name, text] = MAP_STATE[state] || ['neutral', null, state];
  return pill(tone, name, text, size);
}

export const itemStatePill = mapStatePill;

const INNER = {
  done: ['ok', 'done', 'Done'],
  running: ['run', 'spinner', 'Running'],
  failed: ['bad', 'failed', 'Failed'],
  notrun: ['ghost', 'notrun', 'Not run'],
  waiting: ['ghost', 'wait', 'Waiting'],
};
export function innerStatePill(kind) {
  const [tone, name, text] = INNER[kind] || INNER.waiting;
  return pill(tone, name, text, 'md');
}

export const slowFlag = (text) => pill('warn', 'slow', text);
export const lostFlag = (text = 'data lost') => pill('bad', 'lost', text, 'sm', 'mp-pill--dash');

/* ---------- the node ---------- */

/**
 * The map step as one node of the graph (design 3.1): state pill, MAP tag, name, the item flow, the progress line,
 * pills for failed items and lost data, and the "Show items" footer. `open` is whether its panel is shown.
 */
export function mapNodeHTML({ def, step, index, style, open, panelId, label }) {
  const map = step.map;
  const tone = mapNodeTone(map);
  const prog = mapProgressParts(map);
  const progHTML = prog.text
    ? '<b>' + esc(prog.text.split(' ')[0]) + '</b> ' + esc(prog.text.split(' ').slice(1).join(' '))
    : prog.parts.map((x) => (x.bad ? '<span class="mn-f"><b>' + esc(x.n) + '</b> ' + esc(x.word) + '</span>' : '<b>' + esc(x.n) + '</b> ' + esc(x.word))).join(' · ');
  const failed = mapPillText(map);
  const lost = mapLostText(map);
  const flow = (def.map && def.map.steps.length ? def.map.steps.map((s) => s.name) : map.inner.map((s) => s.name)).join(' → ');
  const pills = (failed ? pill('bad', 'failed', failed) : '') + (lost ? pill('bad', 'lost', lost, 'sm', 'mp-pill--dash') : '');
  return '<button type="button" class="gnode gnode--map mn' + (tone ? ' mn--' + tone : '') + '" data-i="' + index + '" data-map-step="' + esc(step.name) + '" style="' + style + '"' +
    ' aria-expanded="' + (open ? 'true' : 'false') + '" aria-controls="' + esc(panelId) + '" aria-label="' + esc(mapAria(label, map, open)) + '">' +
    '<span class="mn-top">' + mapStatePill(map.state) + '<span class="mn-tag">' + icon12('loop') + 'Map</span></span>' +
    '<span class="mn-name">' + esc(label) + '</span>' +
    (flow ? '<span class="mn-flow">' + esc(flow) + '</span>' : '') +
    '<span class="mn-prog">' + progHTML + '</span>' +
    (pills ? '<span class="mn-pills">' + pills + '</span>' : '') +
    '<span class="mn-foot"><span class="mn-foot__txt">' + (open ? 'Hide items' : 'Show items') + '</span>' + icon12('chevDown') + '</span>' +
    '</button>';
}

/* ---------- the panel ---------- */

const mono = (t) => '<span class="mono">' + esc(t) + '</span>';

/** Header, summary line, item flow strip, notices and the list's own container. */
export function panelShellHTML({ id, label, name }) {
  return '<div class="mp-panel__head"><div>' +
    '<div class="mp-eyebrow mp-eyebrow--map">' + icon12('loop') + 'Map step</div>' +
    '<h2 class="mp-panel__title" id="' + esc(id) + '-title" tabindex="-1">' + esc(label) + (label !== name ? ' <span class="mono mp-panel__id">' + esc(name) + '</span>' : '') + '</h2>' +
    '</div><button type="button" class="mp-xbtn" data-mp-close aria-label="Close items panel (Escape)">' + icon('x') + '</button></div>' +
    '<div class="mp-sum" data-mp="sum"></div>' +
    '<div class="mp-stripw" data-mp="strip"></div>' +
    '<div data-mp="notices"></div>' +
    '<div data-mp="hint"></div>' +
    '<div class="mp-tools" data-mp="tools"></div>' +
    '<p class="mp-count" role="status" aria-live="polite" data-mp="count"></p>' +
    '<span class="mp-sr" role="status" aria-live="polite" data-mp="announce"></span>' +
    '<div data-mp="list"></div>' +
    '<div class="mp-more" data-mp="more"></div>';
}

/** The summary line: state, loop time, median, p95, slowest (a link to that item), rows, the concurrency limit. */
export function summaryHTML({ map, line, slowest, io, slowestHref }) {
  const parts = [];
  parts.push('<span>' + mapStatePill(map.state, 'md') + '</span>');
  if (map.counts.started === 0) parts.push('<span><b>' + (map.state === 'done' ? '0</b> items' : '0</b> started') + '</span>');
  else {
    const prog = mapProgressParts(map);
    parts.push('<span>' + prog.parts.map((x) => '<b' + (x.bad ? ' class="mp-bad"' : '') + '>' + esc(x.n) + '</b> ' + esc(x.word)).join(' · ') + '</span>');
  }
  if (line.loop) parts.push('<span>loop <b>' + esc(line.loop) + '</b></span>');
  if (line.median) parts.push('<span>median <b>' + esc(line.median) + '</b></span>');
  if (line.p95) parts.push('<span>p95 <b>' + esc(line.p95) + '</b></span>');
  if (line.note) parts.push('<span class="mp-faint">' + esc(line.note) + '</span>');
  if (slowest) parts.push('<span>slowest <a class="mp-link" href="' + esc(slowestHref) + '" data-mp-slowest>' + mono(slowest.key) + ' ' + esc(slowest.text) + '</a></span>');
  if (io) parts.push('<span>rows in <b>' + esc(io.inText) + '</b> → out <b>' + esc(io.outText) + '</b></span>');
  if (map.concurrencyLimit != null) parts.push('<span><span class="mp-tag">concurrency limit ' + esc(fmt(map.concurrencyLimit)) + '</span></span>');
  return parts.join('');
}

/** The item flow with aggregate counts across every item. */
export function stripHTML(map, declared) {
  const boxes = itemFlowStrip(map, declared);
  const word = runningWord(map.state);
  const cnt = (kind, n, label) => {
    const ic = kind === 'done' ? 'check' : kind === 'failed' ? 'failed' : kind === 'notrun' ? 'notrun' : kind === 'running' ? (map.state === 'running' ? 'spinner' : map.state === 'died' ? 'power' : 'warn') : 'wait';
    return '<span class="mp-cnt mp-cnt--' + kind + '">' + icon12(ic) + '<b>' + esc(fmt(n)) + '</b> ' + esc(label) + '</span>';
  };
  const html = boxes.map((b, i) => {
    const counts = b.empty
      ? '<span class="mp-cnt mp-cnt--nr">' + esc(b.text) + '</span>'
      : b.parts.map((p) => cnt(p.kind, p.n, p.kind === 'running' ? word : p.word)).join('');
    return (i ? '<span class="mp-sarr" aria-hidden="true">' + icon('arrow') + '</span>' : '') +
      '<div class="mp-sbox' + (b.hot ? ' mp-sbox--hot' : b.busy ? ' mp-sbox--busy' : '') + '"><div class="mp-sbox__h"><span class="mp-sbox__n">' + esc(b.name) + '</span>' +
      (b.hot ? pill('bad', null, 'failures here') : '<span class="mp-tag">' + b.order + '</span>') + '</div><div class="mp-cnts">' + counts + '</div></div>';
  }).join('');
  return '<div class="mp-eyebrow">Item flow · counts across every item</div><div class="mp-strip">' + html + '</div>';
}

/** Notices about partial detail (design: neutral for the record limit, red for failures without a record). */
export function noticesHTML(n) {
  const note = (cls, ic, text, how) => '<div class="mp-notice' + cls + '" role="note">' + icon(ic) + '<div>' + text + (how ? '<small>' + esc(how) + '</small>' : '') + '</div></div>';
  let html = '';
  if (n.partial) {
    html += note('', 'info', esc(n.partial).replace(/(\d[\d,]*)/g, '<b>$1</b>'), n.partialHow);
  }
  if (n.orphan) html += note(' mp-notice--bad', 'warn', esc(n.orphan).replace(/^([\d,]+)/, '<b>$1</b>'), n.orphanHow);
  return html;
}

/** "Failed is pre-selected because this map step failed. Show all N items" */
export function preselectHTML(allCount) {
  return '<div class="mp-notice">' + icon('filter') + '<span class="mp-grow">Failed is pre-selected because this map step failed.</span>' +
    '<button type="button" class="mp-link mp-linkbtn" data-mp-showall>Show all' + (allCount != null ? ' ' + esc(fmt(allCount)) + ' items' : ' items') + '</button></div>';
}

/** Search, status chips, the Slow toggle, the sort select and its direction button. */
export function toolsHTML({ id, chips, state, slowDisabled, slowOn }) {
  const chipHTML = chips.map((c) =>
    '<button type="button" class="mp-chip" data-mp-chip="' + c.id + '" aria-pressed="' + c.pressed + '"' + (c.disabled ? ' disabled' : '') + '>' +
    icon12('check').replace('class="mic mic--s"', 'class="mic mic--s mp-on"') + esc(c.label) + ' <span class="mp-n">' + esc(fmt(c.n)) + '</span></button>').join('');
  const dirLabel = state.dir === 'asc' ? '↑ Asc' : '↓ Desc';
  const dirAria = state.dir === 'asc' ? 'Sort direction: ascending. Switch to descending' : 'Sort direction: descending. Switch to ascending';
  const opt = (v, t) => '<option value="' + v + '"' + (state.sort === v ? ' selected' : '') + '>' + t + '</option>';
  return '<div class="mp-search">' + icon('search') + '<label class="mp-sr" for="' + esc(id) + '-q">Search items by key</label>' +
    '<input id="' + esc(id) + '-q" type="search" placeholder="Search key…" autocomplete="off" spellcheck="false" value="' + esc(state.q) + '" data-mp-q></div>' +
    '<div class="mp-chips" role="group" aria-label="Filter items by status">' + chipHTML + '<span class="mp-vsep" aria-hidden="true"></span>' +
    '<button type="button" class="mp-chip mp-chip--tg" data-mp-slow aria-pressed="' + slowOn + '"' + (slowDisabled ? ' disabled title="Needs 5 finished items"' : '') + '>' +
    icon12('check').replace('class="mic mic--s"', 'class="mic mic--s mp-on"') + icon12('slow') + 'Slow' + (slowDisabled ? ' <span class="mp-n">needs 5 finished items</span>' : '') + '</button></div>' +
    '<div class="mp-sort"><label for="' + esc(id) + '-sort">Sort</label><select id="' + esc(id) + '-sort" class="mp-sel" data-mp-sort>' +
    opt('started', 'Order started') + opt('duration', 'Duration') + opt('key', 'Key') + '</select>' +
    '<button type="button" class="mp-btn" data-mp-dir aria-label="' + esc(dirAria) + '">' + dirLabel + '</button></div>';
}

/** One row of the items list (a single link to the item). */
export function rowHTML(item, map, href) {
  const v = itemRowView(item, map);
  const dur = v.live
    ? 'running <span class="num" data-elapsed="' + (v.seconds == null ? 0 : v.seconds) + '" data-fetched="' + item.fetchedAt + '">' + esc(elapsedLabel(v.seconds || 0)) + '</span>'
    : esc(v.durText);
  const flags = (v.slow ? slowFlag(v.slow) : '') + (v.lost ? lostFlag() : '');
  return '<li><a class="mp-row" href="' + esc(href) + '" data-key="' + esc(item.key) + '">' +
    '<span class="mp-key mono">' + esc(v.key) + '</span>' +
    '<span class="mp-c-st">' + itemStatePill(v.state) + '</span>' +
    '<span class="mp-brk"></span>' +
    '<span class="mp-c-dur">' + icon12('slow').replace('class="mic mic--s"', 'class="mic mic--s mp-mi"') + dur + '</span>' +
    '<span class="mp-c-where' + (v.whereBad ? ' mp-bad' : '') + '">' + esc(v.where) + '</span>' +
    '<span class="mp-c-io mono' + (v.ioLost ? ' mp-lost' : '') + '">' + esc(v.io) + '</span>' +
    '<span class="mp-c-flags">' + flags + '</span>' +
    icon12('chevRight').replace('class="mic mic--s"', 'class="mic mic--s mp-c-go"') + '</a></li>';
}

export function listHTML(items, map, hrefFor) {
  return '<div class="mp-rhead" aria-hidden="true"><span>Item key</span><span>Status</span><span>Duration</span><span>Where · error</span><span>In → out</span><span>Flags</span><span></span></div>' +
    '<ul class="mp-items" aria-label="Items">' + items.map((it) => rowHTML(it, map, hrefFor(it.key))).join('') + '</ul>';
}

/** Empty states of the list. `kind`: none (no item started), empty-loop (done with 0 items), nomatch. */
export function emptyHTML(kind, detail = '') {
  if (kind === 'nomatch') {
    return '<div class="mp-empty">' + icon('search') + '<strong>No items match.</strong>' + (detail ? '<span>' + esc(detail) + '</span>' : '') +
      '<button type="button" class="mp-btn" data-mp-clear>Clear search and filters</button></div>';
  }
  return '<div class="mp-empty" role="status">' + icon('loop') + '<strong>No items started.</strong><span>' +
    (kind === 'empty-loop' ? 'The map step finished with 0 items.' : 'Items appear here as soon as the first one begins.') + '</span></div>';
}

export function moreHTML(text, remaining) {
  return '<button type="button" class="mp-btn" data-mp-more>Show more' + (remaining ? ' · next ' + Math.min(50, remaining) : '') + '</button>' +
    (text ? '<span class="mp-more__left">' + esc(text) + '</span>' : '');
}

/* ---------- the item view ---------- */

const when = (d) => (d ? d.toTimeString().slice(0, 8) : '—');
const msClock = (d) => (d ? d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0') : '—');

/** An inner step of an item: rail bubble, name, state, counts and (when failed) the error block drawn by the caller. */
export function innerStepHTML(s, isLast, errorHTML) {
  const bub = { done: ['ok', 'check'], failed: ['bad', 'x'], running: ['run', 'spinner'], notrun: ['nr', 'notrun'], waiting: ['wait', 'wait'] }[s.kind] || ['nr', 'wait'];
  const stats = [];
  if (s.inText != null) stats.push('<span>in <b>' + esc(s.inText) + '</b></span>');
  if (s.outText != null) stats.push('<span>out <b>' + esc(s.outText) + '</b></span>');
  if (s.tookText != null) stats.push('<span>took <b>' + esc(s.tookText) + '</b></span>');
  if (s.liveSeconds != null) stats.push('<span>running <span class="num mp-live" data-elapsed="' + s.liveSeconds + '" data-fetched="' + s.fetchedAt + '">' + esc(elapsedLabel(s.liveSeconds)) + '</span></span>');
  if (s.note) stats.push('<span>' + esc(s.note) + '</span>');
  return '<li class="mp-istep' + (s.dim ? ' mp-dim' : '') + '"><div class="mp-rail"><span class="mp-bub mp-bub--' + bub[0] + '">' + icon12(bub[1]) + '</span>' +
    (isLast ? '' : '<span class="mp-line' + (s.kind === 'failed' || s.kind === 'running' ? ' mp-line--dash' : '') + '"></span>') + '</div>' +
    '<div class="mp-sbody"><div class="mp-shead"><span class="mp-sname">' + esc(s.name) + '</span>' + innerStatePill(s.kind) +
    (s.lost ? lostFlag() : '') + (s.unplanned ? '<span class="mp-tag">not in flow</span>' : '') + '</div>' +
    (stats.length ? '<div class="mp-sstats">' + stats.join('') + '</div>' : '') + (errorHTML || '') + '</div></li>';
}

/** The metrics table of an item (declared limits come from the flow). */
export function itemMetricsHTML(rows) {
  if (!rows.length) return '';
  return '<section class="mp-card" aria-labelledby="mp-mt-h"><div class="mp-sec-h"><h2 id="mp-mt-h">Item metrics</h2><span class="mp-faint">this item only</span></div>' +
    '<table class="mp-table"><thead><tr><th>Metric</th><th class="mp-r">Value</th><th>Check</th></tr></thead><tbody>' +
    rows.map((r) => '<tr><td class="mp-k">' + esc(r.step ? r.step + ' · ' + r.label : r.label) + '</td><td class="mp-r' + (r.check ? ' mp-warnv' : '') + '">' + esc(r.value) + '</td><td>' +
      (r.check ? pill('warn', 'warn', r.check) : '') + '</td></tr>').join('') + '</tbody></table></section>';
}

/** The item's events, oldest first. Plain text only. */
export function itemEventsHTML(events, note) {
  const items = events.map((e) => {
    const tone = e.level === 'error' ? ' mp-ev--bad' : e.level === 'warning' ? ' mp-ev--warn' : '';
    const fields = e.fields ? ' ' + Object.keys(e.fields).map((k) => k + '=' + e.fields[k]).join(' ') : '';
    return '<li class="mp-ev' + tone + '"><time>' + esc(msClock(e.ts)) + '</time><span class="mp-evt">' +
      (e.level !== 'info' ? esc(e.level) + ' · ' : '') + (e.step ? mono(e.step) + ' · ' : '') + esc(e.message == null ? '(message not stored)' : e.message) +
      (fields ? '<span class="mp-faint">' + esc(fields) + '</span>' : '') + '</span></li>';
  }).join('');
  return '<section class="mp-card" aria-labelledby="mp-ev-h"><div class="mp-sec-h"><h2 id="mp-ev-h">Item events</h2><span class="mp-faint">' + esc(note) + '</span></div>' +
    (events.length ? '<ol class="mp-evs">' + items + '</ol>' : '<p class="mp-evs-empty">No events were recorded for this item.</p>') + '</section>';
}

export { when as clockOf, fmtMs };
