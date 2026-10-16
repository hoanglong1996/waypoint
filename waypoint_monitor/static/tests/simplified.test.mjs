import assert from 'node:assert/strict';
import { test } from 'node:test';
import { defsFor, mapRun } from '../js/api.js';
import {
  edgesOf, layoutFor, partition, simpleLayout, stubsOf,
} from '../js/graph-model.js';
import { noticeFor, problemsHTML } from '../js/ui.js';

const rec = (name, extra = {}) => ({ name, state: 'done', inputs: [{ name: 'x', value: 3 }], output: 3, finished_at: '2026-10-16T02:00:08Z', ...extra });
const apiRun = (over = {}) => ({
  run_id: '20261016T020000Z', pipeline: 'demo', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:00:20Z',
  duration_seconds: 20, age_seconds: 60, stale: false, status: 'complete', running_step: null, first_missing_step: null,
  missing_count: 0, loss_steps: [], unreadable: 0, flow_status: 'missing', flow_problems: [], flow: null,
  steps: [rec('one'), rec('two')], ...over,
});

test('a run with no flow: one def per reported step, none placed, no edges', () => {
  const run = mapRun(apiRun());
  assert.equal(run.flow, null);
  assert.equal(run.flowStatus, 'missing');
  assert.deepEqual(run.defs.map((d) => d.name), ['one', 'two']);
  assert.ok(run.defs.every((d) => d.noFlow && !d.unplanned));
  assert.deepEqual(partition(run.defs).placed, []);
  assert.deepEqual(edgesOf(run.defs), []);
  assert.deepEqual(stubsOf(run.defs), []);
});

test('simple layout: one node per step, no arrows, wraps to the panel width', () => {
  const run = mapRun(apiRun({ steps: Array.from({ length: 7 }, (_, i) => rec('s' + i)) }));
  const L = simpleLayout(run.defs, 700, false);
  assert.equal(L.nodes.length, 7);
  assert.deepEqual(L.edges, []);
  assert.deepEqual(L.stubs, []);
  assert.deepEqual(L.bands, []);
  assert.ok(L.nodes.every((n) => n.x + n.w <= 700 + 1));
  assert.ok(L.nodes.some((n) => n.y > L.nodes[0].y), 'wrapped onto a second row');
  const wide = simpleLayout(run.defs, 4000, false);
  assert.ok(wide.nodes.every((n) => n.y === wide.nodes[0].y), 'one row when it fits');
  const seen = new Set(L.nodes.map((n) => n.x + ',' + n.y));
  assert.equal(seen.size, 7, 'no two nodes share a position');
  assert.equal(simpleLayout([], 600, true).nodes.length, 0);
});

test('the notice tells apart a missing and an unreadable flow description', () => {
  assert.match(noticeFor(mapRun(apiRun())), /No flow description for this run, showing steps in the order they reported/);
  assert.match(noticeFor(mapRun(apiRun({ flow_status: 'invalid' }))), /Flow description unreadable/);
  assert.match(noticeFor(mapRun(apiRun({ flow_status: 'unsupported' }))), /Unsupported record version/);
  assert.equal(noticeFor(mapRun(apiRun({ flow_status: 'ok', flow: { steps: [] } }))), '');
});

test('problems are listed with a count and stored text stays text', () => {
  const run = mapRun(apiRun({ flow_status: 'ok', flow: { steps: [{ name: 'one' }] }, flow_problems: ['input \'x\' of \'b\' names unknown step \'<img src=x onerror=alert(1)>\'', 'cycle'] }));
  const html = problemsHTML(run);
  assert.match(html, /Problems in this run’s description \(2\)/);
  assert.ok(!html.includes('<img'), 'markup in a stored string is escaped');
  assert.match(html, /&lt;img/);
  assert.equal(problemsHTML(mapRun(apiRun())), '');
});

test('labels and group names from a flow reach the page only through esc', () => {
  const run = mapRun(apiRun({
    flow_status: 'ok',
    flow: { label: '<b>L</b>', groups: [{ key: 'g', label: '<script>x</script>' }], steps: [{ name: 'one', label: '<i>One</i>', group: 'g', inputs: [] }] },
  }));
  assert.equal(run.defs[0].label, '<i>One</i>'); // the data keeps the raw text; views escape it
  assert.equal(run.flow.groups[0].label, '<script>x</script>');
});

test('a dangling input is kept on the def and shown as a stub, not an arrow', () => {
  const flow = { steps: [{ name: 'a', inputs: [] }, { name: 'b', inputs: [{ name: 'in', from: 'zzz', dangling: true }, { name: 'ok', from: 'a' }] }] };
  const run = mapRun(apiRun({ flow_status: 'ok', flow, steps: [rec('a'), rec('b')] }));
  assert.equal(run.defs[1].inputs[0].dangling, true);
  const edges = edgesOf(run.defs);
  assert.equal(edges.length, 1);
  const L = layoutFor('lr', run.defs, edges, 1200);
  assert.equal(L.edges.length, 1);
  assert.equal(L.stubs.length, 1);
});

test('defsFor: planned steps come from the flow, others are unplanned (flow present) or noFlow (flow absent)', () => {
  const flow = { steps: [{ name: 'a', label: 'A', inputs: [] }] };
  const defs = defsFor(flow, [{ name: 'a' }, { name: 'extra' }]);
  assert.equal(defs[0].label, 'A');
  assert.equal(defs[1].unplanned, true);
  assert.equal(defs[1].noFlow, false);
  assert.equal(defsFor(null, [{ name: 'x' }])[0].noFlow, true);
});
