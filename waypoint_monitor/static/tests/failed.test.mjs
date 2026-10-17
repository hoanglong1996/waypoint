/* Step failures (specs/011-step-failure-errors): mapping, card rules, run page rules and graph states. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mapOverview, mapRun } from '../js/api.js';
import { edgesOf, nodeStates } from '../js/graph-model.js';
import {
  analyse, cardReason, cardStatus, cardWhen, groupCards, hasCounts, heroTitle, isDone, metric, stepState,
} from '../js/model.js';

const ERROR = { type: 'ValueError', message: 'boom', traceback: '  File "x.py", line 3, in run\nValueError: boom\n' };
const done = (name, inputs = [], output = 3) => ({ name, state: 'done', inputs, output, finished_at: '2026-10-16T02:00:08Z' });
const failedStep = (name, error = ERROR) => ({
  name, state: 'failed', started_at: '2026-10-16T02:00:10Z', failed_at: '2026-10-16T02:00:15Z', error,
});
const missing = (name) => ({ name, state: 'missing', missing: true });
const flow = {
  label: 'Demo',
  steps: [
    { name: 'a', inputs: [] },
    { name: 'b', inputs: [{ name: 'x', from: 'a' }] },
    { name: 'c', inputs: [{ name: 'x', from: 'b' }] },
  ],
};
const apiRun = (steps, over = {}) => ({
  run_id: '20261016T020000Z', pipeline: 'demo', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:00:15Z',
  duration_seconds: 15, age_seconds: 60, stale: false, status: 'incomplete', running_step: null, first_missing_step: 'b',
  missing_count: 2, loss_steps: [], unreadable: 0, died: null, failed: null, flow_status: 'ok', flow_problems: [], flow, steps, ...over,
});
const stopped = () => mapRun(apiRun(
  [done('a'), failedStep('b'), missing('c')],
  { failed: { step: 'b', index: 2, failed_at: '2026-10-16T02:00:15Z' } },
));

test('mapRun maps a failed step: times, error, no counts', () => {
  const s = stopped().steps[1];
  assert.equal(s.state, 'failed');
  assert.equal(s.startedAt.toISOString(), '2026-10-16T02:00:10.000Z');
  assert.equal(s.failedAt.toISOString(), '2026-10-16T02:00:15.000Z');
  assert.deepEqual(s.error, ERROR);
  assert.deepEqual(s.inputs, []);
  assert.equal(s.output, null);
  assert.equal(stepState(s), 'failed');
  assert.equal(isDone(s), false);
  assert.equal(hasCounts(s), false);
  assert.equal(metric(s), null);
});

test('a failed step without a stored message has message null, never undefined', () => {
  const run = mapRun(apiRun([done('a'), failedStep('b', { type: 'KeyError', traceback: 'KeyError\n' }), missing('c')]));
  assert.equal(run.steps[1].error.message, null);
  assert.equal(run.steps[1].error.type, 'KeyError');
});

test('mapRun maps the run failure, and null for runs without one', () => {
  const run = stopped();
  assert.deepEqual({ ...run.failed, failedAt: run.failed.failedAt.toISOString() }, {
    step: 'b', index: 2, failedAt: '2026-10-16T02:00:15.000Z',
  });
  assert.equal(mapRun(apiRun([done('a'), done('b'), done('c')], { status: 'complete' })).failed, null);
  const legacy = apiRun([done('a'), done('b'), done('c')], { status: 'complete' });
  delete legacy.failed;
  assert.equal(mapRun(legacy).failed, null);
});

test('analyse exposes the failure and the page title says a step failed', () => {
  const a = analyse(stopped());
  assert.equal(a.failed.step, 'b');
  assert.equal(heroTitle(a, true), 'A step failed');
  assert.equal(heroTitle(a, false), 'A step failed');
  assert.equal(analyse(mapRun(apiRun([done('a'), done('b'), done('c')], { status: 'complete' }))).failed, null);
});

test('a failed step is a stop point; later steps are not reached', () => {
  const run = stopped();
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st, ['ok', 'failed', 'unreached']);
});

test('a failed step that the pipeline stepped past is failed, and later steps keep their states', () => {
  const run = mapRun(apiRun([done('a'), failedStep('b'), done('c')], { status: 'incomplete', missing_count: 1 }));
  const { st } = nodeStates(run, edgesOf(run.defs));
  assert.deepEqual(st, ['ok', 'failed', 'ok']);
});

/* ---------- home cards ---------- */
const card = (over = {}, latest = {}) => ({
  name: 'p', label: 'P', environments: ['prod'], status: 'ok', needsAttention: false,
  generatedAt: new Date('2026-10-16T03:00:00Z'),
  latest: {
    runId: '20261016T020000Z', env: 'prod', status: 'complete', stale: false, startedAt: new Date('2026-10-16T02:00:00Z'),
    endedAt: new Date('2026-10-16T02:01:00Z'), ageSeconds: 3600, lossSteps: [], firstMissingStep: null,
    stalledStep: null, stalledSeconds: null, diedStep: null, lastSeenAt: null, unreadable: 0, headline: [],
    failedStep: null, failedAt: null, error: null, ...latest,
  },
  ...over,
});
const failedCard = (over = {}) => card(
  { status: 'failed', needsAttention: true, ...over },
  { status: 'incomplete', failedStep: 'b', failedAt: new Date('2026-10-16T02:03:41Z'), ageSeconds: 7200, error: { type: 'ValueError', message: 'boom' } },
);

test('card status Failed: words, tone, needs attention', () => {
  assert.deepEqual(cardStatus(failedCard()), { key: 'failed', text: 'Failed', tone: 'bad', attn: true });
});

test('card reason names the step and the error type, with the message when stored', () => {
  assert.deepEqual(cardReason(failedCard(), 26), { kind: 'failed', step: 'b', errorType: 'ValueError', message: 'boom' });
  const bare = failedCard();
  bare.latest.error = { type: 'KeyError' };
  assert.deepEqual(cardReason(bare, 26), { kind: 'failed', step: 'b', errorType: 'KeyError', message: null });
});

test('card time says how long ago it failed', () => {
  assert.deepEqual(cardWhen(failedCard(), 0), { kind: 'failed', hours: 2 });
  assert.equal(cardWhen(failedCard(), 3600).hours, 3);
});

test('failed cards lead the needs-attention group; the others stay by label', () => {
  const mk = (name, status, attn) => card({ name, label: name, status, needsAttention: attn });
  const cards = [mk('a_stale', 'stale', true), mk('c_failed', 'failed', true), mk('b_died', 'died', true), mk('b_failed', 'failed', true), mk('d_ok', 'ok', false)];
  const g = groupCards(cards);
  assert.deepEqual(g.attention.map((c) => c.name), ['b_failed', 'c_failed', 'a_stale', 'b_died']);
  assert.deepEqual(g.rest.map((c) => c.name), ['d_ok']);
});

test('mapOverview maps the failure fields of a card; legacy cards get nulls', () => {
  const latest = {
    run_id: '20261016T020000Z', env: 'prod', status: 'incomplete', stale: false, started_at: '2026-10-16T02:00:00Z',
    ended_at: '2026-10-16T02:03:41Z', age_seconds: 5, loss_steps: [], first_missing_step: 'b', stalled_step: null,
    stalled_seconds: null, unreadable: 0, headline: [], failed_step: 'b', failed_at: '2026-10-16T02:03:41Z',
    error: { type: 'ValueError', message: 'boom' },
  };
  const body = { generated_at: '2026-10-16T03:00:00Z', unreadable_total: 0, pipelines: [
    { name: 'p', label: 'P', environments: ['prod'], card_status: 'failed', needs_attention: true, latest },
    { name: 'q', label: 'Q', environments: ['prod'], card_status: 'ok', needs_attention: false, latest: { ...latest, failed_step: undefined, failed_at: undefined, error: undefined } },
  ] };
  const { cards } = mapOverview(body);
  assert.equal(cards[0].latest.failedStep, 'b');
  assert.equal(cards[0].latest.failedAt.toISOString(), '2026-10-16T02:03:41.000Z');
  assert.deepEqual(cards[0].latest.error, { type: 'ValueError', message: 'boom' });
  assert.deepEqual([cards[1].latest.failedStep, cards[1].latest.failedAt, cards[1].latest.error], [null, null, null]);
});
