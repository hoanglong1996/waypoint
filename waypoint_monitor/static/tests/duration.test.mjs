/* Durations (specs/012-duration-and-run-events): formatting, mapping and the bottleneck line. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mapOverview, mapRun } from '../js/api.js';
import { analyse, fmtDuration } from '../js/model.js';

test('fmtDuration: seconds, minutes, hours, days', () => {
  assert.equal(fmtDuration(37), '37s');
  assert.equal(fmtDuration(245), '4m 05s');
  assert.equal(fmtDuration(3840), '1h 04m');
  assert.equal(fmtDuration(2 * 86400 + 3 * 3600 + 120), '2d 03h');
  assert.equal(fmtDuration(59), '59s');
  assert.equal(fmtDuration(60), '1m 00s');
  assert.equal(fmtDuration(3600), '1h 00m');
});

test('fmtDuration: zero is <1s, unavailable is a dash', () => {
  assert.equal(fmtDuration(0), '<1s');
  assert.equal(fmtDuration(null), '—');
  assert.equal(fmtDuration(undefined), '—');
  assert.equal(fmtDuration(-5), '—');
  assert.equal(fmtDuration(NaN), '—');
});

test('fmtDuration: approximate gets a leading ≈, running a trailing ellipsis', () => {
  assert.equal(fmtDuration(245, { approx: true }), '≈4m 05s');
  assert.equal(fmtDuration(245, { running: true }), '4m 05s…');
  assert.equal(fmtDuration(245, { approx: true, running: true }), '≈4m 05s…');
  assert.equal(fmtDuration(null, { approx: true }), '—');
});

const done = (name, over = {}) => ({
  name, state: 'done', inputs: [], output: 3, finished_at: '2026-10-16T02:00:08Z', ...over,
});
const apiRun = (steps, over = {}) => ({
  run_id: '20261016T020000Z', pipeline: 'demo', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:10:00Z',
  duration_seconds: 600, age_seconds: 60, stale: false, status: 'complete', running_step: null, first_missing_step: null,
  missing_count: 0, loss_steps: [], unreadable: 0, died: null, failed: null, flow_status: 'ok', flow_problems: [], flow: null,
  steps, ...over,
});

test('mapStep maps duration, approximate flag and start of a finished step', () => {
  const run = mapRun(apiRun([
    done('a', { duration_seconds: 130, duration_approx: false, started_at: '2026-10-16T02:00:00Z' }),
    done('b', { duration_seconds: 20, duration_approx: true }),
    done('c'),
  ]));
  assert.equal(run.steps[0].durationSeconds, 130);
  assert.equal(run.steps[0].durationApprox, false);
  assert.equal(run.steps[0].startedAt.toISOString(), '2026-10-16T02:00:00.000Z');
  assert.equal(run.steps[1].durationApprox, true);
  assert.equal(run.steps[1].startedAt, null);
  // a server that sends no duration
  assert.equal(run.steps[2].durationSeconds, null);
  assert.equal(run.steps[2].durationApprox, false);
});

test('mapStep keeps the duration of a failed step', () => {
  const run = mapRun(apiRun([
    done('a'),
    { name: 'b', state: 'failed', started_at: '2026-10-16T02:00:10Z', failed_at: '2026-10-16T02:00:41Z', duration_seconds: 31, duration_approx: false, error: { type: 'E', traceback: '' } },
  ], { status: 'incomplete', failed: { step: 'b', index: 2, failed_at: '2026-10-16T02:00:41Z' } }));
  assert.equal(run.steps[1].durationSeconds, 31);
});

test('mapRun maps duration and bottleneck, null for an older server', () => {
  const run = mapRun(apiRun([done('a')], {
    duration: { seconds: 655, running: false, complete: true, slow: false }, bottleneck: 'a',
  }));
  assert.deepEqual(run.duration, { seconds: 655, running: false, complete: true, slow: false });
  assert.equal(run.bottleneck, 'a');
  const old = mapRun(apiRun([done('a')]));
  assert.equal(old.duration, null);
  assert.equal(old.bottleneck, null);
});

test('analyse exposes the bottleneck and its share of the run', () => {
  const run = mapRun(apiRun([
    done('a', { duration_seconds: 100 }), done('b', { duration_seconds: 380 }), done('c', { duration_seconds: 120 }),
  ], { duration: { seconds: 600, running: false, complete: true, slow: false }, bottleneck: 'b' }));
  const a = analyse(run);
  assert.equal(a.bottleneck, 'b');
  assert.equal(a.bottleneckShare, 63);
  assert.equal(a.duration.seconds, 600);
});

test('analyse has no bottleneck without two durations or without a run duration', () => {
  const run = mapRun(apiRun([done('a', { duration_seconds: 100 })]));
  assert.equal(analyse(run).bottleneck, null);
  assert.equal(analyse(run).bottleneckShare, null);
  const zero = mapRun(apiRun([done('a'), done('b', { duration_seconds: 10 })], {
    duration: { seconds: 0, running: false, complete: true, slow: false }, bottleneck: 'b',
  }));
  assert.equal(analyse(zero).bottleneckShare, null);
});

test('mapOverview maps the latest run duration, running flag, slow flag and counts', () => {
  const body = {
    generated_at: '2026-10-16T03:00:00Z', unreadable_total: 0,
    pipelines: [{
      name: 'p', label: 'P', environments: ['prod'], card_status: 'ok', needs_attention: false,
      latest: {
        run_id: '20261016T020000Z', env: 'prod', status: 'complete', stale: false, started_at: '2026-10-16T02:00:00Z',
        ended_at: '2026-10-16T02:10:00Z', age_seconds: 60, loss_steps: [], first_missing_step: null, stalled_step: null,
        stalled_seconds: null, unreadable: 0, headline: [], duration_seconds: 600, duration_running: false, slow: true,
        warnings: 2, errors: 1,
      },
    }],
  };
  const l = mapOverview(body).cards[0].latest;
  assert.equal(l.durationSeconds, 600);
  assert.equal(l.durationRunning, false);
  assert.equal(l.slow, true);
  assert.equal(l.warnings, 2);
  assert.equal(l.errors, 1);
  delete body.pipelines[0].latest.duration_seconds;
  delete body.pipelines[0].latest.warnings;
  const old = mapOverview(body).cards[0].latest;
  assert.equal(old.durationSeconds, null);
  assert.equal(old.warnings, 0);
});

/* ---------- Slower than usual and the duration chart (US2) ---------- */
import { mapTypical } from '../js/api.js';
import { durationSeries, slowText } from '../js/model.js';

const TYPICAL = { median_seconds: 612, p95_seconds: 745, sample: 24, window: 30, multiple: 2, slow_after_seconds: 1224 };

test('mapTypical maps the typical values, null when the server sends none', () => {
  assert.deepEqual(mapTypical(TYPICAL), {
    medianSeconds: 612, p95Seconds: 745, sample: 24, window: 30, multiple: 2, slowAfterSeconds: 1224,
  });
  assert.equal(mapTypical(null), null);
  assert.equal(mapTypical(undefined), null);
});

test('mapRun keeps duration.slow', () => {
  const run = mapRun(apiRun([done('a')], { duration: { seconds: 2100, running: false, complete: true, slow: true } }));
  assert.equal(run.duration.slow, true);
});

test('slowText says how long the run took against the typical duration', () => {
  const run = mapRun(apiRun([done('a')], { duration: { seconds: 2100, running: false, complete: true, slow: true } }));
  assert.equal(slowText(run, mapTypical(TYPICAL)), 'Slower than usual: 35m 00s vs 10m 12s typical');
  const running = mapRun(apiRun([done('a')], { duration: { seconds: 2100, running: true, complete: false, slow: true } }));
  assert.equal(slowText(running, mapTypical(TYPICAL)), 'Slower than usual: 35m 00s… vs 10m 12s typical');
  assert.equal(slowText(run, null), 'Slower than usual');
});

const runOf = (id, seconds, over = {}) => mapRun(apiRun([done('a')], {
  run_id: id, duration: { seconds, running: false, complete: true, slow: false }, ...over,
}));

test('durationSeries: one point per run, oldest first, with the median and p95 lines', () => {
  const runs = [
    runOf('20261016T020000Z', 2100, { duration: { seconds: 2100, running: false, complete: true, slow: true } }),
    runOf('20261015T020000Z', 600),
    runOf('20261014T020000Z', null, { status: 'incomplete', duration: { seconds: null, running: false, complete: false, slow: false } }),
  ];
  const s = durationSeries(runs, mapTypical(TYPICAL));
  assert.deepEqual(s.points.map((p) => p.id), ['20261014T020000Z', '20261015T020000Z', '20261016T020000Z']);
  assert.deepEqual(s.points.map((p) => p.seconds), [null, 600, 2100]);
  assert.deepEqual(s.points.map((p) => p.slow), [false, false, true]);
  assert.equal(s.median, 612);
  assert.equal(s.p95, 745);
  assert.equal(s.enough, true);
  assert.equal(s.note, null);
});

test('durationSeries without typical values says there is not enough history', () => {
  const s = durationSeries([runOf('20261016T020000Z', 600)], null, 5);
  assert.equal(s.enough, false);
  assert.equal(s.median, null);
  assert.equal(s.note, 'Not enough history yet (needs 5 completed runs)');
  assert.equal(s.points.length, 1);
});

/* ---------- a counting-up duration must not make every refresh redraw the page ---------- */
import { overviewSignature, runSignature } from '../js/model.js';

test('runSignature ignores the duration of a running run but not of a finished one', () => {
  const running = (seconds) => mapRun(apiRun([done('a')], { status: 'running', duration: { seconds, running: true, complete: false, slow: false } }));
  assert.equal(runSignature([running(10)]), runSignature([running(15)]));
  const finished = (seconds) => mapRun(apiRun([done('a')], { duration: { seconds, running: false, complete: true, slow: false } }));
  assert.notEqual(runSignature([finished(10)]), runSignature([finished(15)]));
  // the slow flag of a running run still redraws
  const slow = mapRun(apiRun([done('a')], { status: 'running', duration: { seconds: 10, running: true, complete: false, slow: true } }));
  assert.notEqual(runSignature([running(10)]), runSignature([slow]));
});

test('overviewSignature ignores the duration of a running card but not of a finished one', () => {
  const card = (over) => ({
    name: 'p', label: 'P', status: 'ok', generatedAt: new Date(), environments: ['prod'],
    latest: { ageSeconds: 100, stalledSeconds: null, durationSeconds: 600, durationRunning: false, slow: false, ...over },
  });
  assert.equal(overviewSignature([card({ durationSeconds: 5, durationRunning: true })]), overviewSignature([card({ durationSeconds: 9, durationRunning: true })]));
  assert.notEqual(overviewSignature([card({ durationSeconds: 5 })]), overviewSignature([card({ durationSeconds: 9 })]));
});

/* ---------- older pipelines: no durations, no events (specs/012 US7) ---------- */
import { eventNotes } from '../js/model.js';

// run.js pulls in the graph view, which registers a keydown handler when it loads
globalThis.document ??= { addEventListener() {}, getElementById() { return null; } };
globalThis.window ??= { addEventListener() {}, matchMedia() { return { matches: false }; }, innerWidth: 1200 };
const { heroHTML } = await import('../js/views/run.js');

test('a run with no durations at all renders dashes, never NaN, undefined, null or a negative', () => {
  const run = mapRun(apiRun([
    done('a'), done('b', { duration_seconds: null, duration_approx: true }),
  ], { duration: { seconds: null, running: false, complete: true, slow: false } }));
  run.pipeline = 'p';
  const html = heroHTML(run, [run], { staleHours: 26 }, null);
  assert.doesNotMatch(html, /NaN|undefined|null|-\d+s/);
  const older = mapRun(apiRun([done('a'), done('b')]));
  const html2 = heroHTML(older, [older], { staleHours: 26 }, null);
  assert.doesNotMatch(html2, /NaN|undefined|null/);
  assert.doesNotMatch(html2, /Slowest|Slower than usual/);
});

test('an older run with no events gets the upgrade note and no scary wording', () => {
  const [note] = eventNotes({ dropped: 0, recorded: 0, unreadable: 0 });
  assert.match(note, /waypoint-etl 0\.4\.0/);
  assert.doesNotMatch(note, /error|missing|failed|corrupt/i);
});
