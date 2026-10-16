import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ago, analyse, compact, deltaPct, dur, elapsedLabel, fmt, groupKeys, groupSlot, hasCounts, headline, isDone, isLoss, metric, niceMax, retryIn,
  runSignature, series, stepState, updatedLabel,
} from '../js/model.js';

const step = (name, inputs, output) => ({ name, inputs: inputs.map(([n, value]) => ({ name: n, value })), output, finishedAt: new Date() });
const missing = (name) => ({ name, missing: true });

function run({ calls = 1284, saved = 1284, accounts = 10, clickview = 3410, missingSave = false } = {}) {
  return {
    steps: [
      step('read_callrail_account', [], accounts),
      step('read_callrail_call', [['accounts', accounts]], calls),
      step('read_gads_clickview', [['instances', 14]], clickview),
      step('record_call_statistics', [['call_statistics', saved]], null),
      missingSave ? missing('save_call_statistics') : step('save_call_statistics', [['call_statistics', saved]], null),
    ],
    status: 'complete', firstMissingStep: null, missingCount: 0, lossSteps: [], stale: false, ageSeconds: 3600, durationSeconds: 72,
  };
}

test('metric: output, first input when output is null, null when missing', () => {
  assert.equal(metric(step('a', [], 10)), 10);
  assert.equal(metric(step('save', [['call_statistics', 77]], null)), 77);
  assert.equal(metric(step('save', [], null)), null);
  assert.equal(metric(missing('x')), null);
  assert.equal(metric(null), null);
  assert.equal(metric(step('z', [['i', 5]], 0)), 0);
});

test('isLoss: output 0 with some input > 0 only', () => {
  assert.equal(isLoss(step('a', [['i', 5]], 0)), true);
  assert.equal(isLoss(step('a', [['i', 0]], 0)), false);
  assert.equal(isLoss(step('a', [], 0)), false);
  assert.equal(isLoss(step('a', [['i', 5]], null)), false);
  assert.equal(isLoss(step('a', [['i', 5]], 3)), false);
  assert.equal(isLoss(missing('a')), false);
});

const values = (h) => h.map((k) => k.value);
const names = (h) => h.map((k) => k.step);

test('headline: first reported step, largest metric, last metric; no step names built in', () => {
  const h = headline(run());
  assert.deepEqual(names(h), ['read_callrail_account', 'read_gads_clickview', 'save_call_statistics']);
  assert.deepEqual(values(h), [10, 3410, 1284]);
  assert.deepEqual(h.map((k) => k.key), ['first', 'peak', 'last']);
  assert.deepEqual(values(headline(run({ missingSave: true }))), [10, 3410, 1284]);
  assert.deepEqual(values(headline({ steps: [] })), [null, null, null]);
});

test('headline uses the run\'s own labels when it has them', () => {
  const r = run();
  r.defs = r.steps.map((s) => ({ name: s.name, label: s.name.toUpperCase() }));
  assert.equal(headline(r)[0].label, 'READ_CALLRAIL_ACCOUNT');
  assert.equal(headline(run())[0].label, 'read_callrail_account');
});

test('hasCounts: done and unplanned steps report counts, others do not', () => {
  assert.equal(hasCounts({ state: 'done' }), true);
  assert.equal(hasCounts({ state: 'unplanned' }), true);
  assert.equal(hasCounts({ state: 'running' }), false);
  assert.equal(hasCounts({ state: 'waiting' }), false);
  assert.equal(hasCounts({ missing: true }), false);
  assert.equal(isDone({ state: 'unplanned' }), false);
  assert.equal(metric({ state: 'unplanned', inputs: [], output: 7 }), 7);
});

test('groups: declared order first, then groups only steps use; colour slot cycles through 8', () => {
  const r = { flow: { groups: [{ key: 'b' }, { key: 'a' }] }, defs: [{ group: 'c' }, { group: 'a' }, {}] };
  assert.deepEqual(groupKeys(r), ['b', 'a', 'c']);
  assert.equal(groupSlot(r, 'a'), 1);
  assert.equal(groupSlot(r, null), 3);
  assert.equal(groupSlot({ flow: { groups: Array.from({ length: 10 }, (_, i) => ({ key: 'g' + i })) }, defs: [] }, 'g9'), 1);
  assert.deepEqual(groupKeys({ flow: null, defs: [{ group: null }] }), []);
});

test('deltaPct rules', () => {
  assert.deepEqual(deltaPct(null, 5), { kind: 'none', pct: null });
  assert.deepEqual(deltaPct(5, null), { kind: 'none', pct: null });
  assert.deepEqual(deltaPct(0, 0), { kind: 'flat', pct: 0 });
  assert.deepEqual(deltaPct(5, 0), { kind: 'new', pct: null });
  assert.deepEqual(deltaPct(110, 100), { kind: 'up', pct: 10 });
  assert.equal(deltaPct(50, 100).kind, 'down');
  assert.equal(deltaPct(50, 100).pct, -50);
  assert.deepEqual(deltaPct(0, 5), { kind: 'down', pct: -100 });
  assert.equal(deltaPct(100.01, 100).kind, 'flat');
});

test('series: newest n runs, oldest first, gaps are null not zero', () => {
  const runs = [run({ calls: 3 }), run({ calls: 2 }), { steps: [missing('read_callrail_call')] }, run({ calls: 1 })];
  assert.deepEqual(series(runs, 'read_callrail_call', 3), [null, 2, 3]);
  assert.deepEqual(series(runs, 'read_callrail_call', 10), [1, null, 2, 3]);
  assert.deepEqual(series([run({ saved: 9 })], 'save_call_statistics', 14), [9]);
});

test('series for a step that returns nothing uses its input', () => {
  assert.deepEqual(series([run({ saved: 8 }), run({ saved: 7 })], 'record_call_statistics', 14), [7, 8]);
});

test('analyse reads the API flags', () => {
  const a = analyse({ ...run(), status: 'incomplete', firstMissingStep: 'save_call_statistics', missingCount: 2, lossSteps: ['x'], stale: true, ageSeconds: 7200, endedAt: 'E' });
  assert.equal(a.complete, false);
  assert.equal(a.firstMissing, 'save_call_statistics');
  assert.equal(a.missingCount, 2);
  assert.deepEqual(a.loss, ['x']);
  assert.equal(a.stale, true);
  assert.equal(a.ageH, 2);
  assert.equal(a.durationS, 72);
});

test('formatting helpers', () => {
  assert.equal(fmt(1284), '1,284');
  assert.equal(fmt(null), 'n/a');
  assert.equal(ago(0.5), '30m ago');
  assert.equal(ago(3.25), '3h 15m ago');
  assert.equal(ago(50), '2d 2h ago');
  assert.equal(dur(72), '1m 12s');
  assert.equal(dur(9), '9s');
  assert.equal(compact(1500), '1.5k');
  assert.equal(compact(3000), '3k');
  assert.equal(compact(42), '42');
  assert.equal(niceMax(1284), 2000);
  assert.equal(niceMax(3410), 5000);
});

test('updatedLabel and retryIn', () => {
  assert.equal(updatedLabel(0), 'just now');
  assert.equal(updatedLabel(12), '12s ago');
  assert.equal(updatedLabel(125), '2m ago');
  assert.equal(updatedLabel(7300), '2h ago');
  assert.equal(retryIn(10_000, 4_000), 6);
  assert.equal(retryIn(10_000, 10_001), 0);
  assert.equal(retryIn(10_000, 9_999), 1);
});

/* ---------- live states (spec 004) ---------- */
const live = (name, state, extra = {}) => ({ name, state, inputs: [], output: null, finishedAt: null, ...extra });

test('stepState: each value and the legacy fallback', () => {
  assert.equal(stepState(live('a', 'running')), 'running');
  assert.equal(stepState(live('a', 'waiting')), 'waiting');
  assert.equal(stepState(live('a', 'stalled')), 'stalled');
  assert.equal(stepState(live('a', 'died')), 'died');
  assert.equal(stepState({ name: 'a', state: 'missing', missing: true }), 'missing');
  assert.equal(stepState(missing('a')), 'missing'); // no state key: older server
  assert.equal(stepState(step('a', [], 1)), 'done');
  assert.equal(isDone(live('a', 'running')), false);
  assert.equal(isDone(null), false);
});

test('isLoss and metric ignore steps that have not finished', () => {
  for (const state of ['running', 'waiting', 'stalled', 'died']) {
    const s = { ...live('a', state), inputs: [{ name: 'i', value: 5 }], output: 0 };
    assert.equal(isLoss(s), false);
    assert.equal(metric(s), null);
  }
});

test('analyse flags a running run; headline ignores a running step', () => {
  const r = run();
  r.status = 'running';
  r.runningStep = 'read_callrail_call';
  r.steps[1] = live('read_callrail_call', 'running');
  const a = analyse(r);
  assert.equal(a.running, true);
  assert.equal(a.runningStep, 'read_callrail_call');
  assert.equal(a.complete, false);
  assert.equal(values(headline(r))[0], 10);
  assert.ok(!names(headline(r)).includes('read_callrail_call'));
  assert.equal(analyse(run()).running, false);
});

test('elapsedLabel: seconds, minutes, hours, never negative', () => {
  assert.equal(elapsedLabel(42), '42 s');
  assert.equal(elapsedLabel(0), '0 s');
  assert.equal(elapsedLabel(185), '3m 05s');
  assert.equal(elapsedLabel(3720), '1h 02m');
  assert.equal(elapsedLabel(-5), '0 s');
});

test('runSignature ignores elapsed time and same-minute age, sees real changes', () => {
  const mk = (over = {}) => ({
    ...run(), ageSeconds: 100, status: 'complete',
    steps: [live('a', 'running', { elapsedSeconds: 5, fetchedAt: 1 })], ...over,
  });
  const base = runSignature([mk()]);
  assert.equal(runSignature([mk({ ageSeconds: 110, steps: [live('a', 'running', { elapsedSeconds: 15, fetchedAt: 9 })] })]), base);
  assert.notEqual(runSignature([mk({ ageSeconds: 160 })]), base); // crossed a minute (not running)
  assert.notEqual(runSignature([mk({ steps: [live('a', 'stalled', { elapsedSeconds: 5 })] })]), base);
  assert.notEqual(runSignature([mk({ status: 'running' })]), base);
  assert.notEqual(runSignature([mk({ steps: [live('a', 'died', { lastSeenAt: new Date(1) })] })]), base);
  assert.notEqual(runSignature([mk({ died: { recorded: true } })]), base);
  assert.notEqual(runSignature([mk(), mk()]), base);
});

test('runSignature: a running run ignores age entirely', () => {
  const mk = (age) => ({ ...run(), status: 'running', ageSeconds: age, steps: [live('a', 'running')] });
  assert.equal(runSignature([mk(10)]), runSignature([mk(500)]));
});

test('a run that has just started: running with no running step, every step waiting', () => {
  const r = { ...run(), status: 'running', runningStep: null, steps: ['a', 'b'].map((n) => live(n, 'waiting')) };
  const a = analyse(r);
  assert.equal(a.running, true);
  assert.equal(a.runningStep, null);
  assert.deepEqual(values(headline(r)), [null, null, null]);
  assert.ok(runSignature([r]).length > 0);
});
