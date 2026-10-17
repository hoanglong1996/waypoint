/* Map step (specs/014): pure rules and wording. No DOM access, so it can be unit-tested with `node --test`.
   Hard rules from the design: there is never a total number of items (no "6 of 10", no percentage bar),
   median and 95th percentile need enough finished items, and every state has words (never colour alone). */
import { fmt, fmtDuration, formatMetricValue } from './model.js';

export const PAGE_SIZE = 50;
export const MIN_PERCENTILE_ITEMS = 5;
export const STATUSES = ['all', 'failed', 'running', 'done'];
export const STATUS_LABEL = { all: 'All', failed: 'Failed', running: 'Running', done: 'Done' };
const SORTS = ['started', 'duration', 'key'];
export const SORT_LABEL = { started: 'Order started', duration: 'Duration', key: 'Key' };
const DEFAULT_DIR = { started: 'asc', duration: 'desc', key: 'asc' };

/** A duration in milliseconds as the design shows it: `420 ms`, `3.9 s`, `41 s`, `1m 05s`. */
export function fmtMs(ms) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return Math.round(ms) + ' ms';
  if (ms < 10000) return (ms / 1000).toFixed(1) + ' s';
  if (ms < 60000) return Math.round(ms / 1000) + ' s';
  return fmtDuration(Math.round(ms / 1000));
}

/* ---------- map step node and summary ---------- */

/** Word for items that are "running" while the run is stalled or died (design: they take the run's state). */
export const runningWord = (state) => (state === 'stalled' ? 'stalled' : state === 'died' ? 'died' : 'running');

/**
 * The progress of a map step as parts: `{text}` for 0 started / 0 items, else `{parts: [{n, word, bad}]}`
 * ("6 done · 4 running · 0 failed"). Only items that have started are counted.
 */
export function mapProgressParts(map) {
  const { started, running, done, failed } = map.counts;
  if (started === 0) return { text: map.state === 'done' ? '0 items' : '0 started' };
  return {
    parts: [
      { n: fmt(done), word: 'done', bad: false },
      { n: fmt(running), word: runningWord(map.state), bad: false },
      { n: fmt(failed), word: 'failed', bad: failed > 0 },
    ],
  };
}

export function mapProgress(map) {
  const p = mapProgressParts(map);
  return p.text || p.parts.map((x) => x.n + ' ' + x.word).join(' · ');
}

/** `1 failed item`, `3 failed items`, or '' when none failed. */
export function mapPillText(map) {
  const n = map.counts.failed;
  return n > 0 ? fmt(n) + ' failed item' + (n === 1 ? '' : 's') : '';
}

export const mapLostText = (map) => (map.lostItems > 0 ? 'items lost data' : '');

/** Which border the node gets: `fail` (red), `stall` (amber) or '' (neutral). */
export function mapNodeTone(map) {
  if (map.state === 'stalled') return 'stall';
  if (map.state === 'failed' || map.state === 'died' || map.counts.failed > 0) return 'fail';
  return '';
}

const STATE_WORD = { running: 'running', done: 'done', failed: 'failed', stalled: 'stalled', died: 'died' };

/** Text for assistive technology on the node. */
export function mapAria(name, map, open) {
  const p = mapProgressParts(map);
  const prog = p.text || p.parts.map((x) => x.n + ' ' + x.word).join(', ');
  return name + ', map step, ' + (STATE_WORD[map.state] || map.state) + ': ' + prog +
    (map.lostItems > 0 ? ', items lost data' : '') + '. ' + (open ? 'Hide' : 'Show') + ' items';
}

/** Notices about partial detail: texts, or null when nothing is partial. `withRecord` comes from the items page. */
export function mapPartialNotice(map, withRecord) {
  const out = { partial: null, partialHow: '', orphan: null, orphanHow: '' };
  if (map.detail.partial) {
    const have = withRecord != null ? withRecord : map.detail.kept;
    out.partial = 'Showing items with a record: ' + fmt(have) + ' of ' + fmt(map.counts.started) + '. Totals cover every item.';
    out.partialHow = 'Kept: the first 1,000 items, up to 1,000 further failed items and the 50 slowest. Search and filters only see these.';
  }
  const n = map.detail.failedWithoutRecord;
  if (n > 0) {
    out.orphan = fmt(n) + ' further failed item' + (n === 1 ? ' has' : 's have') + ' no record of ' + (n === 1 ? 'its' : 'their') + ' own.';
    out.orphanHow = 'They are counted in “' + fmt(map.counts.failed) + ' failed” and in the item flow above, but cannot be listed or opened.';
  }
  return out;
}

/**
 * One box per inner step across every item. `declared` is the item flow of the flow description (inner steps in
 * order); without it the order of the summary is used. A step that the failed items never reached is `not run`
 * for them: failures at an earlier step are exactly those items.
 */
export function itemFlowStrip(map, declared) {
  const names = declared && declared.length ? declared.map((d) => d.name) : map.inner.map((x) => x.name);
  const by = new Map(map.inner.map((x) => [x.name, x]));
  const word = runningWord(map.state);
  let failedBefore = 0;
  return names.map((name, i) => {
    const x = by.get(name) || { running: 0, done: 0, failed: 0 };
    const notRun = failedBefore;
    failedBefore += x.failed;
    const parts = [];
    if (x.done) parts.push({ kind: 'done', n: x.done, word: 'done' });
    if (x.running) parts.push({ kind: 'running', n: x.running, word });
    if (x.failed) parts.push({ kind: 'failed', n: x.failed, word: 'failed' });
    if (notRun) parts.push({ kind: 'notrun', n: notRun, word: 'not run' });
    const empty = parts.length === 0;
    const text = empty ? (map.state === 'done' ? '0 items' : 'no items yet') : parts.map((q) => fmt(q.n) + ' ' + q.word).join(' · ');
    return { name, order: i + 1, parts, empty, text, hot: x.failed > 0, busy: x.running > 0 && x.failed === 0 };
  });
}

/** The loop, median and 95th percentile of a map step as texts; the percentiles only with enough finished items. */
export function durationLine(map, minItems = MIN_PERCENTILE_ITEMS) {
  const d = map.duration;
  const enough = d.enough && d.medianMs != null;
  return {
    loop: map.loopSeconds == null ? null : fmtMs(map.loopSeconds * 1000) + (map.state === 'running' ? ' so far' : ''),
    median: enough ? '≈' + fmtMs(d.medianMs) : null,
    p95: enough && d.p95Ms != null ? '≈' + fmtMs(d.p95Ms) : null,
    note: enough ? null : 'percentiles need ' + minItems + ' finished items',
  };
}

/** The slowest item as `{key, text}`, or null. */
export function slowestLabel(map) {
  const s = map.slowest && map.slowest[0];
  return s ? { key: s.key, text: '(' + fmtMs(s.ms) + ')' } : null;
}

export function ioText(map) {
  if (map.inTotal == null && map.outTotal == null) return null;
  return { inText: map.inTotal == null ? '—' : fmt(map.inTotal), outText: map.outTotal == null ? '—' : fmt(map.outTotal) };
}

/* ---------- panel state, in the address and on the API ---------- */

/** The panel state from the route's query values ({items, slow, sort, q}); `touched` says the address chose a status. */
export function parsePanelQuery(route) {
  const r = route || {};
  const status = STATUSES.includes(r.items) ? r.items : null;
  const [s, d] = String(r.sort || '').split('-');
  const sort = SORTS.includes(s) ? s : 'started';
  const dir = d === 'asc' || d === 'desc' ? d : DEFAULT_DIR[sort];
  return { status, touched: status != null, slow: r.slow === '1', sort, dir, q: typeof r.q === 'string' ? r.q : '' };
}

/** The status shown: the address's, else Failed for a failed map step, else All. */
export const effectiveStatus = (state, map) => state.status || (map.state === 'failed' && map.counts.failed > 0 ? 'failed' : 'all');

/** Route query values for the panel state (defaults are left out). */
export function buildPanelQuery(state) {
  const q = {};
  if (state.touched && state.status) q.items = state.status;
  if (state.slow) q.slow = '1';
  if (state.sort !== 'started' || state.dir !== 'asc') q.sort = state.sort + '-' + state.dir;
  if (state.q) q.q = state.q;
  return q;
}

/** Parameters for `loadItems`. The design sorts failed rows first in the All view of a failed map step. */
export function itemsApiParams(state, map, { limit = PAGE_SIZE, after = null } = {}) {
  const status = effectiveStatus(state, map);
  return {
    state: status === 'all' ? null : status,
    slow: state.slow,
    q: state.q.trim(),
    sort: state.sort === 'started' ? 'index' : state.sort,
    order: state.dir,
    failedFirst: status === 'all' && map.state === 'failed',
    limit,
    after,
  };
}

/** The same parameters as one string; equal strings mean the same list. */
export function itemsQuery(state, map) {
  const p = itemsApiParams(state, map);
  return [p.state || 'all', p.slow ? 'slow' : '', p.q, p.sort, p.order, p.failedFirst ? 'ff' : ''].join('|');
}

/** Chips: id, label, count (items with a record) and whether it is pressed. */
export function chipsFor(page, state, map) {
  const status = effectiveStatus(state, map);
  const counts = page
    ? { all: page.withRecord, failed: page.counts.failed, running: page.counts.running, done: page.counts.done }
    : { all: 0, failed: 0, running: 0, done: 0 };
  // while the run is stalled or died, the items that were running say so (the filter is still the stored state)
  const label = (id) => (id === 'running' && (map.state === 'stalled' || map.state === 'died') ? runningWord(map.state)[0].toUpperCase() + runningWord(map.state).slice(1) : STATUS_LABEL[id]);
  return STATUSES.map((id) => ({
    id, label: label(id), n: counts[id], pressed: status === id, disabled: counts[id] === 0 && status !== id,
  }));
}

export const slowDisabled = (map) => !(map.duration && map.duration.enough);

/** The polite result line: "1 failed item · slow only · key contains "acct" · sorted by duration ↓ · failed first". */
export function countText(page, state, map) {
  if (!page) return '';
  if (page.matched === 0) return 'No items match.';
  const status = effectiveStatus(state, map);
  const what = (status === 'all' ? '' : STATUS_LABEL[status].toLowerCase() + ' ') + 'item' + (page.matched === 1 ? '' : 's');
  const q = state.q.trim();
  return fmt(page.matched) + ' ' + what + (state.slow ? ' · slow only' : '') + (q ? ' · key contains "' + q + '"' : '') +
    ' · sorted by ' + SORT_LABEL[state.sort].toLowerCase() + (state.dir === 'asc' ? ' ↑' : ' ↓') +
    (status === 'all' && map.state === 'failed' ? ' · failed first' : '');
}

/** How many more records match than are shown, e.g. "101 more failed items with a record". */
export function moreText(page, shown, state, map) {
  const left = Math.max(0, page.matched - shown);
  if (left === 0) return '';
  const status = effectiveStatus(state, map);
  return fmt(left) + ' more ' + (status === 'all' ? '' : STATUS_LABEL[status].toLowerCase() + ' ') + 'item' + (left === 1 ? '' : 's') + ' with a record';
}

/** Pages loaded one after another: every item once, in order (an item already shown is not shown again). */
export function mergePages(pages) {
  const seen = new Set();
  const out = [];
  pages.forEach((p) => p.forEach((it) => {
    if (!seen.has(it.key)) {
      seen.add(it.key);
      out.push(it);
    }
  }));
  return out;
}

/**
 * Refresh of a list on screen: items keep their place and take their new data; items that are no longer in the answer
 * leave; new items go to the end. Rows never jump under the pointer or the focus.
 */
export function mergeRefresh(prev, fresh) {
  const by = new Map(fresh.map((it) => [it.key, it]));
  const kept = prev.filter((it) => by.has(it.key)).map((it) => by.get(it.key));
  const have = new Set(kept.map((it) => it.key));
  return kept.concat(fresh.filter((it) => !have.has(it.key)));
}

/* ---------- one row of the list ---------- */

const ITEM_STATE_LABEL = { running: 'Running', done: 'Done', failed: 'Failed', stalled: 'Stalled', died: 'Died' };

export const itemStateLabel = (state) => ITEM_STATE_LABEL[state] || state;

/** "×2.3 median" when the median is known, else "slow". */
export function slowRatio(ms, medianMs) {
  if (ms == null || !medianMs) return 'slow';
  return 'slow ×' + (ms / medianMs).toFixed(1) + ' median';
}

/** Everything a list row shows, as plain strings and flags. */
export function itemRowView(item, map) {
  const live = item.state === 'running';
  const failed = item.state === 'failed';
  const where = failed
    ? [item.failedStep, item.errorType].filter(Boolean).join(' · ')
    : item.loss && item.lossStep ? item.lossStep + ' · in → out 0'
      : (live || item.state === 'stalled' || item.state === 'died') && item.currentStep ? (item.state === 'running' ? 'at ' : 'was at ') + item.currentStep : '';
  const ms = live ? item.elapsedMs : item.durationMs;
  return {
    key: item.key,
    state: item.state,
    stateLabel: itemStateLabel(item.state),
    where,
    whereBad: failed || (item.loss && !!where),
    live,
    seconds: live && item.elapsedMs != null ? item.elapsedMs / 1000 : null,
    durText: ms == null ? '—' : fmtMs(ms),
    io: (item.inCount == null ? '—' : fmt(item.inCount)) + ' → ' + (item.outCount == null ? '—' : fmt(item.outCount)),
    ioLost: item.loss,
    slow: item.slow ? slowRatio(live ? item.elapsedMs : item.durationMs, map && map.duration ? map.duration.medianMs : null) : null,
    lost: item.loss,
  };
}

/* ---------- the item view ---------- */

const STEP_KIND = { done: 'done', running: 'running', failed: 'failed', not_run: 'notrun', waiting: 'waiting' };
export const STEP_LABEL = { done: 'Done', running: 'Running', failed: 'Failed', notrun: 'Not run', waiting: 'Waiting' };

/** Inner steps of an item as the view draws them. */
export function itemStepsView(detail) {
  const steps = detail.steps;
  return steps.map((s, i) => {
    const kind = STEP_KIND[s.state] || 'waiting';
    const prior = steps.slice(0, i).find((x) => x.state === 'failed');
    const live = kind === 'running';
    const ins = s.inputs.filter((x) => x.value != null);
    return {
      name: s.name,
      kind,
      label: STEP_LABEL[kind],
      dim: kind === 'notrun' || kind === 'waiting',
      inText: ins.length ? ins.map((x) => (s.inputs.length > 1 ? x.name + ' ' : '') + fmt(x.value)).join(' · ') : null,
      outText: s.output != null ? fmt(s.output) : kind === 'failed' ? '— (none reported)' : live ? '… not yet' : null,
      tookText: s.durationMs != null ? fmtMs(s.durationMs) : null,
      lost: s.loss || (kind === 'done' && s.output === 0 && s.inputs.some((x) => x.value > 0)),
      unplanned: s.unplanned,
      error: s.error,
      note: kind === 'notrun' ? 'Skipped because ' + (prior ? prior.name : 'an earlier step') + ' failed.'
        : kind === 'waiting' ? 'Starts after ' + (i > 0 ? steps[i - 1].name : 'the item starts') + ' finishes.' : null,
      metrics: s.metrics,
    };
  });
}

/** The inner step an item is at now, or null. */
export function currentStepOf(detail) {
  const s = detail.steps.find((x) => x.state === 'running');
  return s ? s.name : null;
}

/** Which way a declared limit was crossed, for a metric the API marked `over`. */
export function metricFlag(m, decl) {
  if (!m.over) return null;
  if (decl && decl.warnAbove != null && m.value != null && m.value > decl.warnAbove) return 'above';
  if (decl && decl.warnBelow != null && m.value != null && m.value < decl.warnBelow) return 'below';
  return 'over';
}

/** "over 2" / "under 5,000 ms" / "over limit". */
export function metricCheckText(m, decl) {
  const flag = metricFlag(m, decl);
  if (!flag) return '';
  if (flag === 'above') return 'over ' + formatMetricValue(decl.warnAbove, m.unit || (decl && decl.unit));
  if (flag === 'below') return 'under ' + formatMetricValue(decl.warnBelow, m.unit || (decl && decl.unit));
  return 'over limit';
}

/** The address of one item. */
export function itemRoute(run, map, key) {
  return { name: 'item', id: run.pipeline, env: run.env, runId: run.id, map, key };
}

/** The address of the run page with the map panel open (and its list state). */
export function panelRoute(run, map, state) {
  return { name: 'run', id: run.pipeline, env: run.env, runId: run.id, map, ...buildPanelQuery(state) };
}

/** The map step's flow declaration (item flow, concurrency limit) of a step def, or null. */
export const declOf = (def) => (def && def.map ? def.map : null);

/** The item flow of a map step, in order. */
export const innerDefs = (def) => (def && def.map ? def.map.steps : []);

/** The metric declaration of an inner step (for thresholds). */
export function innerMetricDecl(def, step, name) {
  const inner = innerDefs(def).find((d) => d.name === step);
  return inner ? (inner.metrics || []).find((m) => m.name === name) || null : null;
}

/** A map step with data in this run (the node and panel are drawn only for these). */
export const hasMapData = (step) => !!step && !!step.map;
