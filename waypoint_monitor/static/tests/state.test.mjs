import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mapRun } from '../js/api.js';
import {
  edgesOf, neighbours, nodeStates, partition, readingOrder,
} from '../js/graph-model.js';
import { analyse, hasCounts, headline, isDone, metric, stepState } from '../js/model.js';

const done = (name, inputs = [], output = 3) => ({ name, state: 'done', inputs, output, finished_at: '2026-10-16T02:00:08Z' });
const flow = {
  label: 'Demo',
  steps: [
    { name: 'a', inputs: [] },
    { name: 'b', inputs: [{ name: 'x', from: 'a' }] },
    { name: 'c', inputs: [{ name: 'x', from: 'b' }] },
  ],
};
const apiRun = (steps, over = {}) => ({
  run_id: '20261016T020000Z', pipeline: 'demo', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:00:20Z',
  duration_seconds: 20, age_seconds: 60, stale: false, status: 'complete', running_step: null, first_missing_step: null,
  missing_count: 0, loss_steps: [], unreadable: 0, flow_status: 'ok', flow_problems: [], flow, steps, ...over,
});
const withUnplanned = () => mapRun(apiRun([
  done('a'), done('b', [{ name: 'x', value: 3 }]), done('c', [{ name: 'x', value: 3 }]),
  { name: 'extra', state: 'unplanned', inputs: [{ name: 'z', value: 9 }], output: 9, finished_at: '2026-10-16T02:00:12Z' },
]));

test('an unplanned step keeps its counts but is not a done step', () => {
  const run = withUnplanned();
  const extra = run.steps[3];
  assert.equal(stepState(extra), 'unplanned');
  assert.equal(isDone(extra), false);
  assert.equal(hasCounts(extra), true);
  assert.equal(metric(extra), 9);
  assert.equal(extra.output, 9);
});

test('an unplanned step is not an edge endpoint and sits in "Other steps"', () => {
  const run = withUnplanned();
  const edges = edgesOf(run.defs);
  assert.equal(edges.length, 2);
  assert.ok(edges.every((e) => e.from !== 3 && e.to !== 3));
  assert.deepEqual(partition(run.defs).other, [3]);
  assert.deepEqual(neighbours(edges, 3), { up: new Set(), down: new Set() });
});

test('an unplanned step is listed after the planned ones in reading order, never in the graph', () => {
  const run = withUnplanned();
  const order = readingOrder(run.defs, edgesOf(run.defs));
  assert.deepEqual(order, [0, 1, 2]);
  assert.ok(!order.includes(3));
});

test('an unplanned step does not stop the run or count as missing', () => {
  const run = withUnplanned();
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st.slice(0, 3), ['ok', 'ok', 'ok']);
  assert.ok(!st.includes('stopped') && !st.includes('unreached'));
  assert.equal(analyse(run).missingCount, 0);
  assert.equal(analyse(run).complete, true);
});

test('headline ignores unplanned steps', () => {
  const run = withUnplanned();
  assert.ok(!headline(run).some((k) => k.step === 'extra'));
});

test('three planned, one reported: the other two are not reached, the first missing one is where it stopped', () => {
  const run = mapRun(apiRun(
    [done('a'), { name: 'b', state: 'missing', missing: true }, { name: 'c', state: 'missing', missing: true }],
    { status: 'incomplete', first_missing_step: 'b', missing_count: 2 },
  ));
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st, ['ok', 'stopped', 'unreached']);
});

test('a run that has just started: every planned step waiting, nothing running, no spinner node', () => {
  const run = mapRun(apiRun(
    ['a', 'b', 'c'].map((name) => ({ name, state: 'waiting' })),
    { status: 'running', running_step: null },
  ));
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st, ['waiting', 'waiting', 'waiting']);
  assert.equal(analyse(run).running, true);
  assert.equal(analyse(run).runningStep, null);
});

/* ---------- died runs (spec 009) ---------- */
const diedStep = { name: 'b', state: 'died', started_at: '2026-10-16T02:00:08Z', last_seen_at: '2026-10-16T02:00:50Z' };
const diedRun = () => mapRun(apiRun(
  [done('a'), diedStep, { name: 'c', state: 'missing', missing: true }],
  {
    status: 'incomplete', first_missing_step: 'b', missing_count: 2,
    died: { judged_at: '2026-10-16T02:02:20Z', last_seen_at: '2026-10-16T02:00:50Z', recorded: true },
  },
));

test('a died step has no counts and keeps when it started and when it was last seen', () => {
  const step = diedRun().steps[1];
  assert.equal(stepState(step), 'died');
  assert.equal(isDone(step), false);
  assert.equal(hasCounts(step), false);
  assert.deepEqual([step.inputs, step.output, step.finishedAt], [[], null, null]);
  assert.equal(step.startedAt.toISOString(), '2026-10-16T02:00:08.000Z');
  assert.equal(step.lastSeenAt.toISOString(), '2026-10-16T02:00:50.000Z');
});

test('the run carries when it was judged dead, when it was last seen and whether it is stored', () => {
  const run = diedRun();
  assert.equal(run.died.judgedAt.toISOString(), '2026-10-16T02:02:20.000Z');
  assert.equal(run.died.lastSeenAt.toISOString(), '2026-10-16T02:00:50.000Z');
  assert.equal(run.died.recorded, true);
  assert.equal(mapRun(apiRun([done('a'), done('b'), done('c')])).died, null);
  assert.equal(mapRun(apiRun([done('a'), done('b'), done('c')], { died: null })).died, null);
});

test('a died run stops at the died step; later steps are not reached; it is not running or complete', () => {
  const run = diedRun();
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st, ['ok', 'died', 'unreached']);
  const a = analyse(run);
  assert.deepEqual([a.died, a.running, a.complete], [true, false, false]);
  assert.equal(analyse(mapRun(apiRun([done('a'), done('b'), done('c')]))).died, false);
});

test('a died step is not part of the headline numbers', () => {
  assert.ok(!headline(diedRun()).some((k) => k.step === 'b'));
});

/* ---------- History: failed runs (specs/011-step-failure-errors) ---------- */
test('filterRuns keeps every run for "all" and only the failed ones for "failed"', async () => {
  const { filterRuns } = await import('../js/model.js');
  const runs = [{ id: 'c', failed: null }, { id: 'b', failed: { step: 'x' } }, { id: 'a', failed: null }, { id: 'z', failed: { step: 'y' } }];
  assert.deepEqual(filterRuns(runs, 'all').map((r) => r.id), ['c', 'b', 'a', 'z']);
  assert.deepEqual(filterRuns(runs, 'failed').map((r) => r.id), ['b', 'z']);
  assert.deepEqual(filterRuns(runs, 'anything else').map((r) => r.id), ['c', 'b', 'a', 'z']);
  assert.deepEqual(filterRuns([], 'failed'), []);
});

test('a Failed run shows the Failed pill, never Died or Incomplete', async () => {
  const { statusPill } = await import('../js/ui.js');
  const html = statusPill({ failed: { step: 'b' }, died: false, running: false, complete: false }, 'sm');
  assert.match(html, /Failed/);
  assert.doesNotMatch(html, /Died|Incomplete/);
  assert.match(statusPill({ died: true }), /Died/);
  assert.match(statusPill({ failed: null, complete: false }), /Incomplete/);
});

test('a failed step has no metric, so the trend and deltas treat it as a gap', async () => {
  const { series } = await import('../js/model.js');
  const failed = { name: 'b', state: 'failed', inputs: [], output: null, error: { type: 'E', message: null, traceback: '' } };
  const ok = { name: 'b', state: 'done', inputs: [], output: 5 };
  assert.deepEqual(series([{ steps: [failed] }, { steps: [ok] }], 'b', 2), [5, null]);
});
