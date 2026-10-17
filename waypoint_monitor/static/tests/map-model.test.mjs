import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  mapEvent, mapItemDetail, mapItemsPage, mapMapSummary, mapRun,
} from '../js/api.js';
import {
  buildPanelQuery, chipsFor, countText, currentStepOf, durationLine, effectiveStatus, fmtMs, ioText, itemFlowStrip,
  itemRowView, itemStepsView, itemsApiParams, itemsQuery, mapAria, mapLostText, mapNodeTone, mapPartialNotice,
  mapPillText, mapProgress, mapProgressParts, mergePages, mergeRefresh, metricCheckText, metricFlag, moreText,
  parsePanelQuery, slowestLabel, slowDisabled,
} from '../js/map-model.js';
import { buildRoute, parseRoute, withoutPanel } from '../js/router.js';

/* ---------- fixtures shaped like contracts/api.md ---------- */
const rawMap = (over = {}) => ({
  state: 'failed',
  counts: { started: 10, running: 0, done: 9, failed: 1 },
  in_total: 482,
  out_total: 383,
  lost_items: 1,
  concurrency_limit: 5,
  over: 'list_accounts',
  loop_seconds: 41,
  duration: { count: 10, median_ms: 3900, p95_ms: 9100, approx: true, enough: true },
  slowest: [{ key: 'acct-7', ms: 9120 }],
  failed_items: [{ key: 'acct-7', step: 'transform', error_type: 'ValueError' }],
  inner: [
    { name: 'fetch', running: 0, done: 10, failed: 0, in: 10, out: 480 },
    { name: 'transform', running: 0, done: 8, failed: 1, in: 480, out: 383 },
    { name: 'load', running: 0, done: 8, failed: 0, in: 383, out: 383 },
  ],
  detail: { partial: false, kept: 10, failed_without_record: 0 },
  unreadable: 0,
  ...over,
});
const map = (over) => mapMapSummary(rawMap(over));

const rawRun = () => ({
  run_id: '20261017T020301Z', pipeline: 'google_ads', env: 'prod', started_at: '2026-10-17T02:03:01Z', ended_at: '2026-10-17T02:05:00Z',
  duration_seconds: 119, age_seconds: 5, stale: false, status: 'incomplete', first_missing_step: null, missing_count: 0, loss_steps: [],
  unreadable: 0, died: null, failed: null, flow_status: 'ok', flow_problems: [],
  flow: {
    label: 'Google Ads', groups: [],
    steps: [
      { name: 'extract', inputs: [], returns_nothing: false },
      {
        name: 'accounts', inputs: [{ name: 'accounts', from: 'extract' }], returns_nothing: false,
        map: { over: 'extract', max_concurrency: 5, steps: [{ name: 'fetch', inputs: [] }, { name: 'transform', inputs: [{ name: 'rows', from: 'fetch' }], metrics: [{ name: 'rejected', unit: 'rows', warn_above: 100 }] }] },
      },
    ],
  },
  steps: [
    { name: 'extract', state: 'done', inputs: [], output: 10, finished_at: '2026-10-17T02:03:30Z' },
    { name: 'accounts', state: 'failed', started_at: '2026-10-17T02:03:31Z', failed_at: '2026-10-17T02:04:12Z', error: { type: 'ItemsFailed', message: '1 of 10 items failed', traceback: '' }, map: rawMap() },
  ],
});

/* ---------- api mapping ---------- */
test('a map step carries its summary; an ordinary step is unchanged', () => {
  const run = mapRun(rawRun());
  assert.equal(run.steps[0].map, undefined);
  assert.equal('map' in run.steps[0], false);
  const m = run.steps[1].map;
  assert.deepEqual(m.counts, { started: 10, running: 0, done: 9, failed: 1 });
  assert.equal(m.state, 'failed');
  assert.equal(m.concurrencyLimit, 5);
  assert.equal(m.over, 'list_accounts');
  assert.equal(m.duration.medianMs, 3900);
  assert.deepEqual(m.slowest, [{ key: 'acct-7', ms: 9120 }]);
  assert.deepEqual(m.failedItems, [{ key: 'acct-7', step: 'transform', errorType: 'ValueError' }]);
  assert.equal(m.inner[1].failed, 1);
  assert.equal(m.detail.partial, false);
});

test('the flow declares the item flow of a map step and its limit', () => {
  const run = mapRun(rawRun());
  assert.equal('map' in run.flow.steps[0], false);
  const d = run.flow.steps[1].map;
  assert.equal(d.maxConcurrency, 5);
  assert.equal(d.over, 'extract');
  assert.deepEqual(d.steps.map((s) => s.name), ['fetch', 'transform']);
  assert.equal(d.steps[1].metrics[0].warnAbove, 100);
  assert.equal(run.defs[1].map, d);
});

test('damaged counts become zero and a missing summary field never throws', () => {
  const m = mapMapSummary({ counts: { started: -3, running: 'x', done: 2 } });
  assert.deepEqual(m.counts, { started: 0, running: 0, done: 2, failed: 0 });
  assert.equal(m.state, 'running');
  assert.deepEqual(m.inner, []);
  assert.equal(m.duration.enough, false);
  assert.equal(m.loopSeconds, null);
});

test('items page and item detail map as the API sends them', () => {
  const page = mapItemsPage({
    total: 10, with_record: 10, counts: { failed: 1, running: 0, done: 9 }, partial: false, failed_without_record: 0,
    matched: 1, has_more: false, next: null, unreadable: 0,
    items: [{
      key: 'acct-7', index: 7, state: 'failed', slow: true, started_at: '2026-10-17T02:04:21Z', duration_ms: 9120,
      failed_step: 'transform', error_type: 'ValueError', in: 51, out: null, loss: false, compact: false,
    }],
  });
  assert.equal(page.items[0].failedStep, 'transform');
  assert.equal(page.items[0].outCount, null);
  assert.equal(page.withRecord, 10);
  const detail = mapItemDetail({
    key: 'acct-7', index: 7, state: 'failed', slow: true, compact: false, started_at: '2026-10-17T02:04:21Z', duration_ms: 9120,
    steps: [
      { name: 'fetch', state: 'done', inputs: [{ name: 'account', value: 1 }], output: 51, duration_ms: 600, loss: false },
      { name: 'transform', state: 'failed', inputs: [{ name: 'rows', value: 51 }], output: null, duration_ms: 8500, error: { type: 'ValueError', message: 'bad date', traceback: 'Traceback…' }, metrics: [{ name: 'rejected', label: null, unit: 'rows', value: 150, over: true }] },
      { name: 'load', state: 'not_run' },
    ],
    error: null,
  });
  assert.equal(detail.steps[1].error.type, 'ValueError');
  assert.equal(detail.steps[1].metrics[0].over, true);
  assert.equal(detail.steps[2].state, 'not_run');
});

test('an event keeps its item key as text', () => {
  assert.equal(mapEvent({ id: 1, ts: '2026-10-17T02:04:21Z', level: 'warning', item: 'acct-7', message: 'm' }).item, 'acct-7');
  assert.equal('item' in mapEvent({ id: 1, ts: '2026-10-17T02:04:21Z', level: 'info' }), false);
});

/* ---------- node and summary wording ---------- */
test('progress counts only items that started and never shows a total', () => {
  const running = map({ state: 'running', counts: { started: 10, running: 4, done: 6, failed: 0 }, lost_items: 0 });
  assert.equal(mapProgress(running), '6 done · 4 running · 0 failed');
  for (const m of [running, map(), map({ state: 'stalled' })]) assert.ok(!/\bof\b/.test(mapProgress(m)), mapProgress(m));
  assert.equal(mapProgress(map({ state: 'running', counts: { started: 0, running: 0, done: 0, failed: 0 } })), '0 started');
  assert.equal(mapProgress(map({ state: 'done', counts: { started: 0, running: 0, done: 0, failed: 0 } })), '0 items');
  assert.equal(mapProgress(map({ state: 'stalled', counts: { started: 10, running: 4, done: 6, failed: 0 } })), '6 done · 4 stalled · 0 failed');
  assert.equal(mapProgress(map({ state: 'died', counts: { started: 10, running: 4, done: 5, failed: 1 } })), '5 done · 4 died · 1 failed');
});

test('progress parts mark failures so the node can colour them with words beside', () => {
  const p = mapProgressParts(map());
  assert.deepEqual(p.parts.map((x) => x.bad), [false, false, true]);
  assert.equal(mapProgressParts(map({ state: 'running', counts: { started: 0, running: 0, done: 0, failed: 0 } })).text, '0 started');
});

test('failed item pill, lost data pill and the node tone', () => {
  assert.equal(mapPillText(map({ counts: { started: 10, running: 0, done: 8, failed: 2 } })), '2 failed items');
  assert.equal(mapPillText(map()), '1 failed item');
  assert.equal(mapPillText(map({ counts: { started: 10, running: 0, done: 10, failed: 0 } })), '');
  assert.equal(mapLostText(map()), 'items lost data');
  assert.equal(mapLostText(map({ lost_items: 0 })), '');
  assert.equal(mapNodeTone(map()), 'fail');
  assert.equal(mapNodeTone(map({ state: 'running', counts: { started: 10, running: 4, done: 5, failed: 1 } })), 'fail');
  assert.equal(mapNodeTone(map({ state: 'stalled', counts: { started: 10, running: 4, done: 6, failed: 0 } })), 'stall');
  assert.equal(mapNodeTone(map({ state: 'done', counts: { started: 10, running: 0, done: 10, failed: 0 } })), '');
});

test('aria text names the state, the counts and the action', () => {
  assert.equal(mapAria('Accounts', map(), false), 'Accounts, map step, failed: 9 done, 0 running, 1 failed, items lost data. Show items');
  assert.ok(mapAria('Accounts', map(), true).endsWith('Hide items'));
});

test('partial detail notices use the thousands separator and the real numbers', () => {
  const big = map({
    counts: { started: 10000, running: 0, done: 9812, failed: 188 },
    detail: { partial: true, kept: 1050, failed_without_record: 37 },
  });
  const n = mapPartialNotice(big, 1050);
  assert.equal(n.partial, 'Showing items with a record: 1,050 of 10,000. Totals cover every item.');
  assert.equal(n.orphan, '37 further failed items have no record of their own.');
  assert.match(n.orphanHow, /188 failed/);
  assert.deepEqual(mapPartialNotice(map()), { partial: null, partialHow: '', orphan: null, orphanHow: '' });
  assert.equal(mapPartialNotice(map({ detail: { partial: false, kept: 10, failed_without_record: 1 } })).orphan, '1 further failed item has no record of its own.');
  // without the page's count the summary's own count of kept records is used
  assert.match(mapPartialNotice(big).partial, /1,050 of 10,000/);
});

test('item flow strip counts every item and marks where failures are', () => {
  const strip = itemFlowStrip(map(), [{ name: 'fetch' }, { name: 'transform' }, { name: 'load' }]);
  assert.deepEqual(strip.map((s) => s.text), ['10 done', '8 done · 1 failed', '8 done · 1 not run']);
  assert.deepEqual(strip.map((s) => s.hot), [false, true, false]);
  assert.deepEqual(strip.map((s) => s.order), [1, 2, 3]);
});

test('item flow strip before any item and for an empty loop, and a step the summary lacks', () => {
  const none = map({ state: 'running', counts: { started: 0, running: 0, done: 0, failed: 0 }, inner: [] });
  assert.deepEqual(itemFlowStrip(none, [{ name: 'fetch' }]).map((s) => s.text), ['no items yet']);
  const empty = map({ state: 'done', counts: { started: 0, running: 0, done: 0, failed: 0 }, inner: [] });
  assert.deepEqual(itemFlowStrip(empty, [{ name: 'fetch' }]).map((s) => s.text), ['0 items']);
  assert.deepEqual(itemFlowStrip(map({ inner: [] }), null).map((s) => s.name), []);
  const stalled = map({ state: 'stalled', counts: { started: 10, running: 4, done: 6, failed: 0 }, inner: [{ name: 'fetch', running: 4, done: 6, failed: 0 }] });
  assert.equal(itemFlowStrip(stalled, null)[0].text, '6 done · 4 stalled');
});

test('duration line: median and p95 only with enough finished items, approximate, slowest as a link', () => {
  const d = durationLine(map());
  assert.deepEqual(d, { loop: '41 s', median: '≈3.9 s', p95: '≈9.1 s', note: null });
  const few = durationLine(map({ duration: { count: 3, median_ms: null, p95_ms: null, approx: true, enough: false }, state: 'running' }));
  assert.equal(few.median, null);
  assert.equal(few.p95, null);
  assert.equal(few.note, 'percentiles need 5 finished items');
  assert.equal(few.loop, '41 s so far');
  assert.deepEqual(slowestLabel(map()), { key: 'acct-7', text: '(9.1 s)' });
  assert.equal(slowestLabel(map({ slowest: [] })), null);
  assert.equal(slowDisabled(map()), false);
  assert.equal(slowDisabled(map({ duration: { count: 2, enough: false } })), true);
});

test('milliseconds read like the design: ms, one decimal under 10 s, whole seconds, minutes', () => {
  assert.equal(fmtMs(420), '420 ms');
  assert.equal(fmtMs(3900), '3.9 s');
  assert.equal(fmtMs(9120), '9.1 s');
  assert.equal(fmtMs(41000), '41 s');
  assert.equal(fmtMs(65000), '1m 05s');
  assert.equal(fmtMs(null), '—');
  assert.equal(fmtMs(-1), '—');
});

test('rows in and out are texts, or null without counts', () => {
  assert.deepEqual(ioText(map()), { inText: '482', outText: '383' });
  assert.equal(ioText(map({ in_total: null, out_total: null })), null);
});

/* ---------- panel state ---------- */
test('panel state round-trips through the address and leaves defaults out', () => {
  const state = parsePanelQuery({ items: 'failed', slow: '1', sort: 'duration-desc', q: 'acct' });
  assert.deepEqual(state, { status: 'failed', touched: true, slow: true, sort: 'duration', dir: 'desc', q: 'acct' });
  assert.deepEqual(buildPanelQuery(state), { items: 'failed', slow: '1', sort: 'duration-desc', q: 'acct' });
  const plain = parsePanelQuery({});
  assert.deepEqual(plain, { status: null, touched: false, slow: false, sort: 'started', dir: 'asc', q: '' });
  assert.deepEqual(buildPanelQuery(plain), {});
  assert.equal(parsePanelQuery({ items: 'nonsense' }).status, null);
  assert.equal(parsePanelQuery({ sort: 'wat' }).sort, 'started');
  assert.equal(parsePanelQuery({ sort: 'duration' }).dir, 'desc');
  assert.equal(parsePanelQuery({ sort: 'key-desc' }).dir, 'desc');
});

test('a failed map step opens on Failed until the viewer chooses something else', () => {
  const failed = map();
  assert.equal(effectiveStatus(parsePanelQuery({}), failed), 'failed');
  assert.equal(effectiveStatus(parsePanelQuery({ items: 'all' }), failed), 'all');
  const ok = map({ state: 'done', counts: { started: 10, running: 0, done: 10, failed: 0 } });
  assert.equal(effectiveStatus(parsePanelQuery({}), ok), 'all');
  const running = map({ state: 'running', counts: { started: 10, running: 4, done: 5, failed: 1 } });
  assert.equal(effectiveStatus(parsePanelQuery({}), running), 'all');
});

test('API parameters: natural names, failed first only in the All view of a failed map', () => {
  const failed = map();
  assert.deepEqual(itemsApiParams(parsePanelQuery({}), failed), {
    state: 'failed', slow: false, q: '', sort: 'index', order: 'asc', failedFirst: false, limit: 50, after: null,
  });
  const all = itemsApiParams(parsePanelQuery({ items: 'all', sort: 'key-asc', q: ' acct ' }), failed, { after: 'cur' });
  assert.equal(all.state, null);
  assert.equal(all.failedFirst, true);
  assert.equal(all.sort, 'key');
  assert.equal(all.q, 'acct');
  assert.equal(all.after, 'cur');
  const done = map({ state: 'done', counts: { started: 10, running: 0, done: 10, failed: 0 } });
  assert.equal(itemsApiParams(parsePanelQuery({}), done).failedFirst, false);
  // a change of any filter is a different list
  assert.notEqual(itemsQuery(parsePanelQuery({}), failed), itemsQuery(parsePanelQuery({ slow: '1' }), failed));
  assert.equal(itemsQuery(parsePanelQuery({ q: 'a' }), failed), itemsQuery(parsePanelQuery({ q: 'a' }), failed));
});

const page = (over = {}) => mapItemsPage({
  total: 10, with_record: 10, counts: { failed: 1, running: 0, done: 9 }, partial: false, failed_without_record: 0, matched: 1,
  has_more: false, next: null, items: [], ...over,
});

test('chips: counts are items with a record, a chip with none is disabled unless pressed', () => {
  const chips = chipsFor(page(), parsePanelQuery({}), map());
  assert.deepEqual(chips.map((c) => [c.id, c.n, c.pressed, c.disabled]), [
    ['all', 10, false, false], ['failed', 1, true, false], ['running', 0, false, true], ['done', 9, false, false],
  ]);
  const chosen = chipsFor(page(), parsePanelQuery({ items: 'running' }), map());
  assert.equal(chosen.find((c) => c.id === 'running').disabled, false);
  assert.equal(chipsFor(null, parsePanelQuery({}), map()).length, 4);
  const stalled = chipsFor(page(), parsePanelQuery({}), map({ state: 'stalled' }));
  assert.equal(stalled.find((c) => c.id === 'running').label, 'Stalled');
  assert.equal(chipsFor(page(), parsePanelQuery({}), map({ state: 'died' })).find((c) => c.id === 'running').label, 'Died');
});

test('result line matches the design wording', () => {
  const failed = map();
  assert.equal(countText(page(), parsePanelQuery({}), failed), '1 failed item · sorted by order started ↑');
  assert.equal(
    countText(page({ matched: 2 }), parsePanelQuery({ items: 'all', slow: '1', q: 'acct', sort: 'duration-desc' }), failed),
    '2 items · slow only · key contains "acct" · sorted by duration ↓ · failed first',
  );
  assert.equal(countText(page({ matched: 0 }), parsePanelQuery({}), failed), 'No items match.');
  assert.equal(countText(null, parsePanelQuery({}), failed), '');
  assert.equal(moreText(page({ matched: 152 }), 51, parsePanelQuery({}), failed), '101 more failed items with a record');
  assert.equal(moreText(page({ matched: 51 }), 51, parsePanelQuery({}), failed), '');
});

test('pages join without repeating an item, and a refresh keeps rows in place', () => {
  const a = { key: 'a', n: 1 };
  const b = { key: 'b', n: 1 };
  const c = { key: 'c', n: 1 };
  assert.deepEqual(mergePages([[a, b], [b, c]]).map((x) => x.key), ['a', 'b', 'c']);
  const prev = [a, b];
  const fresh = [{ key: 'b', n: 2 }, { key: 'a', n: 2 }, { key: 'd', n: 2 }];
  const merged = mergeRefresh(prev, fresh);
  assert.deepEqual(merged.map((x) => x.key), ['a', 'b', 'd']); // old order, new data, new items at the end
  assert.deepEqual(merged.map((x) => x.n), [2, 2, 2]);
  assert.deepEqual(mergeRefresh([a, b], [{ key: 'b', n: 3 }]).map((x) => x.key), ['b']); // left the filter
});

/* ---------- rows ---------- */
const row = (over) => mapItemsPage({ items: [{ key: 'acct-7', index: 7, state: 'failed', slow: false, duration_ms: 9120, in: 51, out: null, loss: false, ...over }] }).items[0];

test('a failed row says where and which error; a done row with lost data shows in and out', () => {
  const v = itemRowView(row({ failed_step: 'transform', error_type: 'ValueError', slow: true }), map());
  assert.equal(v.where, 'transform · ValueError');
  assert.equal(v.whereBad, true);
  assert.equal(v.io, '51 → —');
  assert.equal(v.durText, '9.1 s');
  assert.equal(v.slow, 'slow ×2.3 median');
  const lost = itemRowView(row({ key: 'acct-3', state: 'done', in: 48, out: 0, loss: true, duration_ms: 4100, loss_step: 'transform' }), map());
  assert.equal(lost.io, '48 → 0');
  assert.equal(lost.ioLost, true);
  assert.equal(lost.where, 'transform · in → out 0');
  assert.equal(lost.lost, true);
});

test('a running row counts up from its elapsed time and a stalled or died one takes the run state', () => {
  const live = itemRowView(row({ state: 'running', duration_ms: null, elapsed_ms: 12000, current_step: 'transform', slow: true }), map({ state: 'running' }));
  assert.equal(live.live, true);
  assert.equal(live.seconds, 12);
  assert.equal(live.where, 'at transform');
  assert.equal(live.slow, 'slow ×3.1 median');
  const stalled = itemRowView(row({ state: 'stalled', duration_ms: null, current_step: 'load' }), map({ state: 'stalled' }));
  assert.equal(stalled.stateLabel, 'Stalled');
  assert.equal(stalled.where, 'was at load');
  assert.equal(itemRowView(row({ state: 'died', duration_ms: null }), map()).stateLabel, 'Died');
});

test('slow without a known median is just slow', () => {
  const v = itemRowView(row({ slow: true }), map({ duration: { count: 2, enough: false } }));
  assert.equal(v.slow, 'slow');
});

/* ---------- item view ---------- */
const detail = () => mapItemDetail({
  key: 'acct-7', index: 7, state: 'failed', slow: true, started_at: '2026-10-17T02:04:21Z', duration_ms: 9120,
  steps: [
    { name: 'fetch', state: 'done', inputs: [{ name: 'account', value: 1 }], output: 51, duration_ms: 600 },
    { name: 'transform', state: 'failed', inputs: [{ name: 'rows', value: 51 }], output: null, duration_ms: 8500, error: { type: 'ValueError', message: 'bad date', traceback: 'tb' } },
    { name: 'load', state: 'not_run' },
  ],
});

test('inner steps are in order: done, failed, then not run with the reason', () => {
  const v = itemStepsView(detail());
  assert.deepEqual(v.map((s) => s.kind), ['done', 'failed', 'notrun']);
  assert.deepEqual(v.map((s) => s.label), ['Done', 'Failed', 'Not run']);
  assert.equal(v[1].outText, '— (none reported)');
  assert.equal(v[1].error.type, 'ValueError');
  assert.equal(v[2].note, 'Skipped because transform failed.');
  assert.equal(v[2].dim, true);
  assert.equal(v[0].tookText, '600 ms');
  assert.equal(v[0].inText, '1');
});

test('a running item shows its running step with a live clock and the next step waiting', () => {
  const d = mapItemDetail({
    key: 'acct-6', state: 'running', elapsed_ms: 11500,
    steps: [
      { name: 'fetch', state: 'done', inputs: [{ name: 'account', value: 1 }], output: 49, duration_ms: 500 },
      { name: 'transform', state: 'running', inputs: [{ name: 'rows', value: 49 }], output: null },
      { name: 'load', state: 'waiting' },
    ],
  });
  const v = itemStepsView(d);
  assert.deepEqual(v.map((s) => s.kind), ['done', 'running', 'waiting']);
  assert.equal(v[1].outText, '… not yet');
  assert.equal(v[2].note, 'Starts after transform finishes.');
  assert.equal(currentStepOf(d), 'transform');
  assert.equal(currentStepOf(detail()), null);
});

test('data lost on an inner step is flagged from its counts even when the API did not say so', () => {
  const d = mapItemDetail({
    key: 'acct-3', state: 'done',
    steps: [{ name: 'transform', state: 'done', inputs: [{ name: 'rows', value: 48 }], output: 0 }],
  });
  assert.equal(itemStepsView(d)[0].lost, true);
});

test('a metric over its limit says which way, using the flow declaration', () => {
  const m = { name: 'rejected', unit: 'rows', value: 150, over: true };
  const decl = { name: 'rejected', unit: 'rows', warnAbove: 100, warnBelow: null };
  assert.equal(metricFlag(m, decl), 'above');
  assert.equal(metricCheckText(m, decl), 'over 100 rows');
  assert.equal(metricFlag({ ...m, value: 2 }, { warnAbove: null, warnBelow: 5 }), 'below');
  assert.equal(metricCheckText({ ...m, value: 2 }, { warnAbove: null, warnBelow: 5 }), 'under 5 rows');
  assert.equal(metricCheckText(m, null), 'over limit');
  assert.equal(metricFlag({ ...m, over: false }, decl), null);
  assert.equal(metricCheckText({ ...m, over: false }, decl), '');
});

/* ---------- addresses ---------- */
test('an item has its own address and round-trips', () => {
  const route = { name: 'item', id: 'google_ads', env: 'prod', runId: '20261017T020301Z', map: 'accounts', key: 'customer_00012345.part-0007' };
  const hash = buildRoute(route);
  assert.equal(hash, '#/p/google_ads/runs/prod/20261017T020301Z/steps/accounts/items/customer_00012345.part-0007');
  assert.deepEqual(parseRoute(hash), route);
});

test('an item address with a bad map name or key is not found', () => {
  assert.equal(parseRoute('#/p/g/runs/prod/20261017T020301Z/steps/Accounts/items/a').name, 'notfound');
  assert.equal(parseRoute('#/p/g/runs/prod/20261017T020301Z/steps/accounts/items/a%20b').name, 'notfound');
  assert.equal(parseRoute('#/p/g/runs/prod/20261017T020301Z/steps/accounts/items/' + 'x'.repeat(65)).name, 'notfound');
  assert.equal(parseRoute('#/p/g/runs/prod/nope/steps/accounts/items/a').name, 'notfound');
  assert.equal(parseRoute('#/p/g/runs/prod/20261017T020301Z/steps/accounts/nope/a').name, 'notfound');
});

test('the run address carries the panel state and a plain run address stays plain', () => {
  const hash = '#/p/g/runs/prod/20261017T020301Z?map=accounts&items=failed&slow=1&sort=duration-desc&q=acct';
  const route = parseRoute(hash);
  assert.deepEqual(route, {
    name: 'run', id: 'g', env: 'prod', runId: '20261017T020301Z', map: 'accounts', items: 'failed', slow: '1', sort: 'duration-desc', q: 'acct',
  });
  assert.equal(buildRoute(route), hash);
  assert.deepEqual(parseRoute('#/p/g/runs/prod/20261017T020301Z'), { name: 'run', id: 'g', env: 'prod', runId: '20261017T020301Z' });
  assert.equal(parseRoute('#/p/g/runs/prod/20261017T020301Z?map=Bad Name').map, undefined);
  assert.equal(withoutPanel(hash), '#/p/g/runs/prod/20261017T020301Z');
  assert.equal(withoutPanel('#/p/g/runs/prod/20261017T020301Z?tab=events&map=a'), '#/p/g/runs/prod/20261017T020301Z?tab=events');
});
