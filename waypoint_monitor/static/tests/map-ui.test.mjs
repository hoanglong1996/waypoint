import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mapItemDetail, mapItemsPage, mapMapSummary } from '../js/api.js';
import {
  emptyHTML, innerStepHTML, itemEventsHTML, itemMetricsHTML, listHTML, mapNodeHTML, moreHTML, noticesHTML, panelShellHTML,
  preselectHTML, stripHTML, summaryHTML, toolsHTML,
} from '../js/map-ui.js';
import {
  chipsFor, durationLine, itemStepsView, mapPartialNotice, parsePanelQuery, slowestLabel,
} from '../js/map-model.js';

const EVIL = '<img src=x onerror=alert(1)>"\'&';
const raw = (over = {}) => ({
  state: 'failed',
  counts: { started: 10, running: 0, done: 9, failed: 1 },
  in_total: 482, out_total: 383, lost_items: 1, concurrency_limit: 5, loop_seconds: 41,
  duration: { count: 10, median_ms: 3900, p95_ms: 9100, approx: true, enough: true },
  slowest: [{ key: 'acct-7', ms: 9120 }],
  failed_items: [],
  inner: [{ name: 'fetch', running: 0, done: 10, failed: 0 }, { name: 'transform', running: 0, done: 8, failed: 1 }],
  detail: { partial: false, kept: 10, failed_without_record: 0 },
  ...over,
});
const map = (over) => mapMapSummary(raw(over));
const noTags = (html) => !/<img|<script|onerror=/i.test(html.replace(/&lt;img[^]*?&gt;/g, ''));

test('the node is a disclosure button with state, tag, flow, progress, pills and footer', () => {
  const step = { name: 'accounts', map: map() };
  const html = mapNodeHTML({
    def: { name: 'accounts', map: { steps: [{ name: 'fetch' }, { name: 'transform' }] } }, step, index: 1, style: 'left:0px', open: false, panelId: 'map-panel-accounts', label: 'Accounts',
  });
  assert.match(html, /^<button type="button" class="gnode gnode--map mn mn--fail"/);
  assert.match(html, /aria-expanded="false" aria-controls="map-panel-accounts"/);
  assert.match(html, /Failed<\/span>/); // a word beside the icon
  assert.match(html, /Map<\/span>/);
  assert.match(html, /fetch → transform/);
  assert.match(html, /<b>9<\/b> done · <b>0<\/b> running · <span class="mn-f"><b>1<\/b> failed<\/span>/);
  assert.match(html, /1 failed item/);
  assert.match(html, /items lost data/);
  assert.match(html, /Show items/);
  assert.ok(!/ of /.test(html.replace(/aria-label="[^"]*"/, '')), 'no total is ever shown');
  assert.match(mapNodeHTML({ def: { name: 'a' }, step, index: 0, style: '', open: true, panelId: 'p', label: 'A' }), /aria-expanded="true"[^>]*aria-label="[^"]*Hide items"/);
});

test('0 started and 0 items are plain words on the node', () => {
  const none = map({ state: 'running', counts: { started: 0, running: 0, done: 0, failed: 0 }, lost_items: 0, inner: [] });
  const html = mapNodeHTML({ def: { name: 'a' }, step: { name: 'a', map: none }, index: 0, style: '', open: false, panelId: 'p', label: 'A' });
  assert.match(html, /<b>0<\/b> started/);
  assert.ok(!/mn-pills/.test(html));
});

test('everything that comes from a pipeline is escaped on the node, the rows and the item page', () => {
  const m = map({ inner: [{ name: EVIL, running: 0, done: 1, failed: 0 }] });
  const node = mapNodeHTML({ def: { name: EVIL, map: { steps: [{ name: EVIL }] } }, step: { name: EVIL, map: m }, index: 0, style: '', open: false, panelId: 'p', label: EVIL });
  assert.ok(noTags(node), node);
  assert.ok(noTags(stripHTML(m, [{ name: EVIL }])));
  assert.ok(noTags(summaryHTML({ map: m, line: durationLine(m), slowest: { key: EVIL, text: '(1 s)' }, io: null, slowestHref: '#x' })));
  const page = mapItemsPage({
    items: [{ key: 'k', state: 'failed', failed_step: EVIL, error_type: EVIL, duration_ms: 5, in: 1, out: null, loss: true, slow: true }],
  });
  assert.ok(noTags(listHTML(page.items, m, () => '#/p/x?"><img src=x>')), 'the address is escaped too');
  const detail = mapItemDetail({
    key: 'k', state: 'failed',
    steps: [{ name: EVIL, state: 'failed', inputs: [{ name: EVIL, value: 1 }], error: { type: EVIL, message: EVIL, traceback: EVIL } }],
  });
  const step = itemStepsView(detail)[0];
  assert.ok(noTags(innerStepHTML(step, true, '')));
  assert.ok(noTags(itemMetricsHTML([{ step: EVIL, label: EVIL, value: EVIL, check: EVIL }])));
  assert.ok(noTags(itemEventsHTML([{ ts: new Date(0), level: 'error', step: EVIL, message: EVIL, fields: { [EVIL]: EVIL } }], EVIL)));
  assert.ok(noTags(panelShellHTML({ id: 'p', label: EVIL, name: EVIL })));
  assert.ok(noTags(emptyHTML('nomatch', EVIL)));
  assert.ok(noTags(noticesHTML({ partial: EVIL, partialHow: EVIL, orphan: EVIL, orphanHow: EVIL })));
});

test('the summary line shows loop, median, p95, the slowest as a link, rows and the limit', () => {
  const m = map();
  const html = summaryHTML({ map: m, line: durationLine(m), slowest: slowestLabel(m), io: { inText: '482', outText: '383' }, slowestHref: '#/p/g/runs/prod/20261017T020301Z/steps/accounts/items/acct-7' });
  assert.match(html, /loop <b>41 s<\/b>/);
  assert.match(html, /median <b>≈3\.9 s<\/b>/);
  assert.match(html, /p95 <b>≈9\.1 s<\/b>/);
  assert.match(html, /<a class="mp-link" href="#\/p\/g\/runs\/prod\/20261017T020301Z\/steps\/accounts\/items\/acct-7"/);
  assert.match(html, /rows in <b>482<\/b> → out <b>383<\/b>/);
  assert.match(html, /concurrency limit 5/);
  const few = map({ duration: { count: 3, enough: false } });
  assert.match(summaryHTML({ map: few, line: durationLine(few), slowest: null, io: null, slowestHref: '#' }), /percentiles need 5 finished items/);
});

test('item flow strip: boxes in order, failures marked in words', () => {
  const html = stripHTML(map(), [{ name: 'fetch' }, { name: 'transform' }]);
  assert.match(html, /Item flow · counts across every item/);
  assert.match(html, /failures here/);
  assert.match(html, /<b>10<\/b> done/);
  assert.match(html, /<b>1<\/b> failed/);
});

test('notices for partial detail use the exact wording', () => {
  const big = map({ counts: { started: 10000, running: 0, done: 9812, failed: 188 }, detail: { partial: true, kept: 1050, failed_without_record: 37 } });
  const html = noticesHTML(mapPartialNotice(big, 1050));
  assert.match(html, /Showing items with a record: <b>1,050<\/b> of <b>10,000<\/b>\. Totals cover every item\./);
  assert.match(html, /<b>37<\/b> further failed items have no record of their own\./);
  assert.match(html, /mp-notice--bad/);
  assert.equal(noticesHTML(mapPartialNotice(map())), '');
});

test('tools: chips are buttons with aria-pressed, Slow is a toggle, sort is a labelled select with a direction button', () => {
  const state = parsePanelQuery({});
  const page = mapItemsPage({ with_record: 10, counts: { failed: 1, running: 0, done: 9 }, items: [], matched: 1 });
  const html = toolsHTML({ id: 'mp', chips: chipsFor(page, state, map()), state, slowDisabled: false, slowOn: false });
  assert.equal((html.match(/data-mp-chip=/g) || []).length, 4);
  assert.match(html, /data-mp-chip="failed" aria-pressed="true"/);
  assert.match(html, /data-mp-chip="running" aria-pressed="false" disabled/);
  assert.match(html, /<label class="mp-sr" for="mp-q">Search items by key<\/label>/);
  assert.match(html, /<label for="mp-sort">Sort<\/label>/);
  assert.match(html, /aria-label="Sort direction: ascending\. Switch to descending"/);
  assert.match(toolsHTML({ id: 'mp', chips: chipsFor(page, state, map()), state, slowDisabled: true, slowOn: false }), /disabled title="Needs 5 finished items"/);
});

test('a row is one link with the key, the state in words, where, duration, in to out and flags', () => {
  const m = map();
  const page = mapItemsPage({
    items: [
      { key: 'acct-7', index: 7, state: 'failed', slow: true, duration_ms: 9120, failed_step: 'transform', error_type: 'ValueError', in: 51, out: null, loss: false },
      { key: 'acct-3', index: 3, state: 'done', duration_ms: 4100, in: 48, out: 0, loss: true },
      { key: 'acct-6', index: 6, state: 'running', elapsed_ms: 12000, in: 49, out: null, slow: true },
    ],
  });
  const html = listHTML(page.items, m, (k) => '#/item/' + k);
  assert.equal((html.match(/<a class="mp-row"/g) || []).length, 3);
  assert.match(html, /href="#\/item\/acct-7" data-key="acct-7"/);
  assert.match(html, /Failed<\/span>/);
  assert.match(html, /transform · ValueError/);
  assert.match(html, /slow ×2\.3 median/);
  assert.match(html, /48 → 0/);
  assert.match(html, /data lost/);
  assert.match(html, /running <span class="num" data-elapsed="12"/);
});

test('empty states and the show more button', () => {
  assert.match(emptyHTML('none'), /No items started\./);
  assert.match(emptyHTML('empty-loop'), /finished with 0 items/);
  assert.match(emptyHTML('nomatch', 'Failed'), /No items match\.[^]*data-mp-clear[^]*Clear search and filters/);
  assert.match(moreHTML('101 more failed items with a record', 151), /Show more · next 50/);
  assert.match(moreHTML('', 10), /Show more · next 10/);
  assert.match(preselectHTML(10), /Failed is pre-selected because this map step failed\.[^]*Show all 10 items/);
});

test('inner steps: bubbles and pills with words, not-run is dimmed, running has a live clock', () => {
  const detail = mapItemDetail({
    key: 'a', state: 'failed',
    steps: [
      { name: 'fetch', state: 'done', inputs: [{ name: 'in', value: 1 }], output: 2, duration_ms: 500 },
      { name: 'transform', state: 'failed', inputs: [], output: null, error: { type: 'E', message: 'm', traceback: '' } },
      { name: 'load', state: 'not_run' },
    ],
  });
  const steps = itemStepsView(detail);
  assert.match(innerStepHTML(steps[0], false, ''), /Done<\/span>/);
  assert.match(innerStepHTML(steps[1], false, '<div class="step__error"></div>'), /Failed<\/span>[^]*step__error/);
  const notRun = innerStepHTML(steps[2], true, '');
  assert.match(notRun, /mp-dim/);
  assert.match(notRun, /Not run<\/span>/);
  assert.match(notRun, /Skipped because transform failed\./);
  const live = innerStepHTML({ ...steps[0], kind: 'running', label: 'Running', liveSeconds: 11.5, fetchedAt: 5 }, false, '');
  assert.match(live, /data-elapsed="11.5" data-fetched="5"/);
});

test('events are oldest first lines of plain text', () => {
  const html = itemEventsHTML([
    { ts: new Date(Date.UTC(2026, 9, 17, 14, 49, 12, 31)), level: 'info', step: null, message: 'item started', fields: null },
    { ts: new Date(Date.UTC(2026, 9, 17, 14, 49, 15, 902)), level: 'warning', step: 'transform', message: 'retrying', fields: { attempt: 2 } },
  ], '2 events · oldest first');
  assert.match(html, /mp-ev--warn/);
  assert.match(html, /warning · <span class="mono">transform<\/span> · retrying/);
  assert.match(html, /attempt=2/);
  assert.match(itemEventsHTML([], 'x'), /No events were recorded for this item\./);
});
