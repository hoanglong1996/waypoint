/* Custom step metrics (specs/013-step-metrics): mapping, formatting, flags, the step table, the trend. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfig, mapRun } from '../js/api.js';
import {
  flagText, formatMetricValue, metric, metricTrend, metricsOver, overText, stepMetrics, trendMetricChoices,
} from '../js/model.js';
import { metricBadgeHTML, metricsTableHTML } from '../js/ui.js';
import { stepItemHTML } from '../js/views/step.js';
import { metricCardHTML } from '../js/views/history.js';

const apiMetric = (name, value, over = {}) => ({
  name, label: null, value, unit: null, declared: false, flag: null, updated_at: '2026-10-16T02:00:09Z', ...over,
});
const done = (name, over = {}) => ({
  name, state: 'done', inputs: [], output: 3, finished_at: '2026-10-16T02:00:08Z', ...over,
});
const flowOf = (decls) => ({
  label: 'Demo',
  steps: [
    { name: 'a', inputs: [] },
    { name: 'b', inputs: [{ name: 'x', from: 'a' }], ...(decls ? { metrics: decls } : {}) },
  ],
});
const apiRun = (steps, over = {}) => ({
  run_id: '20261016T020000Z', pipeline: 'demo', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:00:20Z',
  duration_seconds: 20, age_seconds: 60, stale: false, status: 'complete', running_step: null, first_missing_step: null,
  missing_count: 0, loss_steps: [], unreadable: 0, flow_status: 'ok', flow_problems: [], flow: flowOf(null), steps, ...over,
});

test('formatMetricValue: plain, compact, decimal, unit, not reported', () => {
  assert.equal(formatMetricValue(150, 'rows'), '150 rows');
  assert.equal(formatMetricValue(150), '150');
  assert.equal(formatMetricValue(12345), '12.3k');
  assert.equal(formatMetricValue(12000), '12k');
  assert.equal(formatMetricValue(2500000), '2.5M');
  assert.equal(formatMetricValue(0.25), '0.25');
  assert.equal(formatMetricValue(0.123456), '0.1235');
  assert.equal(formatMetricValue(-4), '-4');
  assert.equal(formatMetricValue(0, 'x'), '0 x');
  assert.equal(formatMetricValue(null), 'not reported');
  assert.equal(formatMetricValue(undefined, 'rows'), 'not reported');
});

test('mapRun maps a step’s metrics, flags and counts; an old payload maps to none', () => {
  const run = mapRun(apiRun([
    done('a'),
    done('b', {
      metrics: [apiMetric('rejected', 150, { label: 'Rejected', unit: 'rows', declared: true, flag: 'above' }), apiMetric('n', 2)],
      metrics_over: 1,
    }),
  ], { metrics_over: 1 }));
  const [first, second] = run.steps;
  assert.deepEqual(stepMetrics(first), []);
  assert.equal(first.metricsOver, 0);
  assert.equal(stepMetrics(second).length, 2);
  assert.deepEqual(
    { ...stepMetrics(second)[0], updatedAt: undefined },
    { name: 'rejected', label: 'Rejected', value: 150, unit: 'rows', declared: true, flag: 'above', updatedAt: undefined },
  );
  assert.equal(stepMetrics(second)[0].updatedAt.toISOString(), '2026-10-16T02:00:09.000Z');
  assert.equal(second.metricsOver, 1);
  assert.equal(metricsOver(second), 1);
  assert.equal(run.metricsOver, 1);
  assert.equal(metric(second), 3); // the output count is a different thing and unchanged
});

test('metrics are mapped for running, failed and died steps too', () => {
  const run = mapRun(apiRun([
    { name: 'a', state: 'running', started_at: '2026-10-16T02:00:00Z', elapsed_seconds: 5, metrics: [apiMetric('p', 1)] },
    { name: 'b', state: 'failed', started_at: '2026-10-16T02:00:00Z', failed_at: '2026-10-16T02:00:05Z', error: { type: 'E', traceback: '' }, metrics: [apiMetric('p', 2)] },
  ]));
  assert.equal(stepMetrics(run.steps[0])[0].value, 1);
  assert.equal(stepMetrics(run.steps[1])[0].value, 2);
  const died = mapRun(apiRun([{ name: 'a', state: 'died', started_at: '2026-10-16T02:00:00Z', last_seen_at: '2026-10-16T02:00:02Z', metrics: [apiMetric('p', 3)] }]));
  assert.equal(stepMetrics(died.steps[0])[0].value, 3);
});

test('a bad metric payload is cleaned, never trusted', () => {
  const run = mapRun(apiRun([done('a', { metrics: [{ name: 'm', value: '5', flag: 'weird', label: 7, unit: {} }] })]));
  const m = stepMetrics(run.steps[0])[0];
  assert.equal(m.value, null);
  assert.equal(m.flag, null);
  assert.equal(m.label, null);
  assert.equal(m.unit, null);
  assert.deepEqual(stepMetrics({ metrics: 'x' }), []);
  assert.deepEqual(stepMetrics(null), []);
});

test('flow declarations map to defs with camelCase limits', () => {
  const run = mapRun(apiRun([done('a'), done('b')], {
    flow: flowOf([{ name: 'rejected', label: 'Rejected', unit: 'rows', warn_above: 100, warn_below: null }]),
  }));
  assert.deepEqual(run.defs[1].metrics, [{ name: 'rejected', label: 'Rejected', unit: 'rows', warnAbove: 100, warnBelow: null }]);
  assert.deepEqual(run.defs[0].metrics, []);
});

test('flagText and overText give words with the limit', () => {
  assert.equal(flagText('above', { warnAbove: 100 }), 'above 100');
  assert.equal(flagText('below', { warnBelow: 90 }), 'below 90');
  assert.equal(flagText('above', null), 'above limit');
  assert.equal(flagText(null, { warnAbove: 1 }), '');
  assert.equal(overText(1), '1 metric over limit');
  assert.equal(overText(2), '2 metrics over limit');
});

const flaggedRun = () => mapRun(apiRun([
  done('a'),
  done('b', {
    metrics: [
      apiMetric('<b>rejected</b>', 150, { label: '<i>Rej</i>', unit: 'rows', declared: true, flag: 'above' }),
      apiMetric('cov', null, { declared: true }),
      apiMetric('plain', 12345),
    ],
    metrics_over: 1,
  }),
], { flow: flowOf([{ name: '<b>rejected</b>', label: '<i>Rej</i>', unit: 'rows', warn_above: 100 }, { name: 'cov', unit: '%', warn_below: 90 }]) }));

test('the metric table shows value with unit, not reported, a text flag, and escapes everything', () => {
  const run = flaggedRun();
  const html = metricsTableHTML(run.steps[1], run.defs[1]);
  assert.match(html, /class="xmetric"/);
  assert.match(html, /150 rows/);
  assert.match(html, /above 100/);
  assert.match(html, /not reported/);
  assert.match(html, /12\.3k/);
  assert.match(html, /title="12345"/); // the exact value
  assert.ok(!html.includes('<b>rejected</b>'));
  assert.ok(!html.includes('<i>Rej</i>'));
  assert.match(html, /&lt;i&gt;Rej&lt;\/i&gt;/);
  assert.ok(html.indexOf('Rej') < html.indexOf('cov') && html.indexOf('cov') < html.indexOf('plain'));
  assert.equal((html.match(/xmetric__flag/g) || []).length, 1);
});

test('a step without metrics renders no metric table or badge', () => {
  const run = flaggedRun();
  assert.equal(metricsTableHTML(run.steps[0], run.defs[0]), '');
  assert.equal(metricBadgeHTML(0), '');
  const list = stepItemHTML(run, [run], { staleHours: 26 }, 0, false);
  assert.ok(!list.includes('xmetric'));
  assert.ok(!list.includes('over limit'));
});

test('the step card shows the table and the over-limit badge in words', () => {
  const run = flaggedRun();
  const html = stepItemHTML(run, [run], { staleHours: 26 }, 1, false);
  assert.match(html, /class="xmetric"/);
  assert.match(html, /1 metric over limit/);
  const two = metricBadgeHTML(2);
  assert.match(two, /2 metrics over limit/);
  assert.match(two, /<svg/); // an icon as well as words
});

test('a running step shows its current metrics', () => {
  const run = mapRun(apiRun([
    done('a'),
    { name: 'b', state: 'running', started_at: '2026-10-16T02:00:00Z', elapsed_seconds: 5, metrics: [apiMetric('rows', 40)] },
  ], { status: 'running', running_step: 'b' }));
  const html = stepItemHTML(run, [run], { staleHours: 26 }, 1, false);
  assert.match(html, /rows/);
  assert.match(html, />40</);
});

/* ---------- trend ---------- */

const trendRuns = (values, declared = true) => values.map((v, i) => mapRun(apiRun([
  done('a'),
  done('b', { metrics: v == null ? [] : [apiMetric('rejected', v, { declared, unit: 'rows' })] }),
], {
  run_id: '202610' + String(30 - i).padStart(2, '0') + 'T020000Z',
  flow: flowOf(declared ? [{ name: 'rejected', label: 'Rejected', unit: 'rows', warn_above: 100 }] : null),
})));

test('metricTrend: oldest to newest, gaps for not reported, median over reported runs only', () => {
  const runs = trendRuns([90, null, 110, 100, 50, 70]); // newest first
  const t = metricTrend(runs, 'b', 'rejected', 30, 5);
  assert.deepEqual(t.points.map((p) => p.value), [70, 50, 100, 110, null, 90]);
  assert.equal(t.median, 90); // 70, 50, 100, 110, 90 -> sorted 50 70 90 100 110
  assert.equal(t.sample, 5);
  assert.equal(t.warnAbove, 100);
  assert.equal(t.warnBelow, null);
  assert.equal(t.unit, 'rows');
  assert.equal(t.label, 'Rejected');
  assert.equal(t.note, null);
});

test('metricTrend: even count averages the middle two; the window cuts to the newest runs', () => {
  assert.equal(metricTrend(trendRuns([10, 20, 30, 40, 50, 60]), 'b', 'rejected', 30, 5).median, 35);
  assert.equal(metricTrend(trendRuns([10, 20, 30, 1000, 1000, 1000]), 'b', 'rejected', 3, 3).median, 20);
});

test('metricTrend: fewer reported runs than the minimum gives points but no median', () => {
  const t = metricTrend(trendRuns([10, null, 20]), 'b', 'rejected', 30, 5);
  assert.equal(t.median, null);
  assert.deepEqual(t.points.map((p) => p.value), [20, null, 10]);
  assert.match(t.note, /Not enough history/);
});

test('metricTrend: limits come from the newest run that declares the metric', () => {
  const runs = trendRuns([5, 6]);
  runs[0].defs[1] = { ...runs[0].defs[1], metrics: [] }; // the newest run stopped declaring it
  assert.equal(metricTrend(runs, 'b', 'rejected', 30, 1).warnAbove, 100);
});

test('trendMetricChoices lists only steps that declare metrics, and nothing when none do', () => {
  assert.deepEqual(trendMetricChoices(trendRuns([1, 2])), [{ step: 'b', metrics: [{ name: 'rejected', label: 'Rejected' }] }]);
  assert.deepEqual(trendMetricChoices(trendRuns([1, 2], false)), []);
  assert.deepEqual(trendMetricChoices([]), []);
});

test('the History card appears only when a metric is declared, and escapes the picker', () => {
  assert.equal(metricCardHTML([]), '');
  const html = metricCardHTML([{ step: 'b', metrics: [{ name: 'rejected', label: '<i>Rejected</i>' }, { name: 'other', label: null }] }]);
  assert.match(html, /Metric trend/);
  assert.match(html, /id="mtrend-step"/);
  assert.match(html, /id="mtrend-metric"/);
  assert.match(html, /&lt;i&gt;Rejected&lt;\/i&gt;/);
  assert.match(html, />other</);
});

test('loadConfig maps the median window next to the minimum run count', async () => {
  const real = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    environments: ['prod'], refresh_seconds: 5, retry_seconds: 30, stale_hours: 26, stall_seconds: 900,
    duration_min_runs: 4, duration_window_runs: 12,
  }) });
  try {
    const cfg = await loadConfig();
    assert.equal(cfg.durationMinRuns, 4);
    assert.equal(cfg.durationWindowRuns, 12);
  } finally {
    globalThis.fetch = real;
  }
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ environments: [] }) });
  try {
    assert.equal((await loadConfig()).durationWindowRuns, 30); // an older server sends none
  } finally {
    globalThis.fetch = real;
  }
});
