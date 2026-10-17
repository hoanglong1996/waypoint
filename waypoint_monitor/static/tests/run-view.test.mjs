import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  findRun, heroTitle, isNewest, runRoute,
} from '../js/model.js';

const run = (id, env = 'prod') => ({ id, env, pipeline: 'callrail' });
const runs = [run('20261016T020000Z'), run('20261015T020000Z'), run('20261014T020000Z', 'qa')];

test('findRun finds a run by id and environment, else null', () => {
  assert.equal(findRun(runs, 'prod', '20261015T020000Z'), runs[1]);
  assert.equal(findRun(runs, 'qa', '20261014T020000Z'), runs[2]);
  assert.equal(findRun(runs, 'prod', '20261014T020000Z'), null); // same id, other environment
  assert.equal(findRun(runs, 'prod', '20200101T000000Z'), null);
  assert.equal(findRun([], 'prod', '20261015T020000Z'), null);
});

test('isNewest is true only for the first run of the list', () => {
  assert.equal(isNewest(runs, runs[0]), true);
  assert.equal(isNewest(runs, runs[1]), false);
  assert.equal(isNewest([], runs[0]), false);
});

test('runRoute addresses a run by its own pipeline, environment and id', () => {
  assert.deepEqual(runRoute('callrail', runs[1]), {
    name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z',
  });
});

test('the newest run is the first history row and opens its own page', () => {
  assert.deepEqual(runRoute('callrail', runs[0]).runId, '20261016T020000Z');
  const newer = [run('20261017T020000Z'), ...runs];
  assert.equal(runRoute('callrail', newer[0]).runId, '20261017T020000Z');
  assert.equal(isNewest(newer, newer[0]), true);
  assert.equal(isNewest(newer, runs[0]), false);
});

const a = (over) => ({
  died: null, running: false, complete: true, loss: [], stale: false, ...over,
});

test('heroTitle keeps the latest wording only for the newest run', () => {
  assert.equal(heroTitle(a(), true), 'Last night’s run completed');
  assert.equal(heroTitle(a({ stale: true }), true), 'Latest run completed — but it’s old');
  assert.equal(heroTitle(a(), false), 'Run completed');
  assert.equal(heroTitle(a({ stale: true }), false), 'Run completed');
});

test('heroTitle for problem states does not depend on the run being newest', () => {
  for (const newest of [true, false]) {
    assert.equal(heroTitle(a({ died: {} }), newest), 'The pipeline process died');
    assert.equal(heroTitle(a({ running: true }), newest), 'A run is in progress');
    assert.equal(heroTitle(a({ complete: false }), newest), 'Run stopped before the end');
    assert.equal(heroTitle(a({ loss: ['x'] }), newest), 'Run finished, but one step lost data');
  }
});

/* ---------- Events tab (specs/012-duration-and-run-events) ---------- */
import { mapEvent } from '../js/api.js';
import { eventNotes, filterSummary, stepChoices } from '../js/model.js';
import { eventRowHTML } from '../js/views/events.js';

const ROUTE = { name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z' };
const entry = (over = {}) => mapEvent({
  id: 'r:info:3', ts: '2026-10-15T02:03:41.482Z', level: 'info', step: 'load', message: 'Loaded batch 3',
  fields: { rows: 1200, source: 'api' }, source: 'pipeline', kind: 'custom', ...over,
});

test('eventRowHTML shows time, level as icon and word, step chip, message and field chips', () => {
  const html = eventRowHTML(entry(), ROUTE);
  assert.match(html, /event--info/);
  assert.match(html, /<span>Info<\/span>/);
  assert.match(html, /<svg/);
  assert.match(html, /href="#\/p\/callrail\/runs\/prod\/20261015T020000Z\?tab=events&amp;step=load"/);
  assert.match(html, /Loaded batch 3/);
  assert.match(html, /rows<\/span> <b>1,200<\/b>/);
  assert.match(html, /source<\/span> <b>api<\/b>/);
  assert.doesNotMatch(html, /tag-monitor/);
});

test('eventRowHTML words each level and tags derived entries as the monitor\u2019s', () => {
  assert.match(eventRowHTML(entry({ level: 'warning' }), ROUTE), /<span>Warning<\/span>/);
  assert.match(eventRowHTML(entry({ level: 'error' }), ROUTE), /<span>Error<\/span>/);
  const derived = eventRowHTML(entry({ source: 'monitor', kind: 'step_failed', level: 'error', step: null }), ROUTE);
  assert.match(derived, /tag-monitor/);
  assert.match(derived, /event--derived/);
  assert.doesNotMatch(derived, /event__step/);
});

test('eventRowHTML escapes everything: markup in a message, step or field is text', () => {
  const html = eventRowHTML(entry({
    message: '<img src=x onerror=alert(1)>', step: '"><script>x</script>', fields: { 'a-b': '<b>bold</b>' },
  }), ROUTE);
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /<script/);
  assert.doesNotMatch(html, /<b>bold<\/b>/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('a message that was not stored says so, never "null"', () => {
  const html = eventRowHTML(entry({ message: null, fields: null }), ROUTE);
  assert.match(html, /message not stored/);
  assert.doesNotMatch(html, /null|undefined/);
});

test('filterSummary counts the filtered and all events', () => {
  assert.equal(filterSummary(41, 41), '41 events');
  assert.equal(filterSummary(1, 1), '1 event');
  assert.equal(filterSummary(6, 41), '6 of 41 events');
  assert.equal(filterSummary(0, 41), '0 of 41 events');
});

test('eventNotes: dropped, nothing sent by the pipeline, unreadable', () => {
  assert.deepEqual(eventNotes({ dropped: 0, recorded: 5, unreadable: 0 }), []);
  assert.match(eventNotes({ dropped: 36, recorded: 500 })[0], /36 events were dropped/);
  assert.match(eventNotes({ dropped: 1, recorded: 5 })[0], /1 event was dropped/);
  assert.match(eventNotes({ recorded: 0 })[0], /No events were sent by this run/);
  assert.match(eventNotes({ recorded: 0 })[0], /0\.4\.0/);
  assert.match(eventNotes({ recorded: 3, unreadable: 2 })[0], /2 unreadable event records skipped/);
  assert.equal(eventNotes({ dropped: 2, recorded: 0, unreadable: 1 }).length, 3);
});

test('stepChoices lists the run\u2019s steps, then steps only an event names', () => {
  const run = { steps: [{ name: 'a' }, { name: 'b' }] };
  assert.deepEqual(stepChoices(run, [entry({ step: 'b' }), entry({ step: 'z' }), entry({ step: null })]), ['a', 'b', 'z']);
});

/* ---------- counts on cards and rows, and a step's own events (specs/012 US5) ---------- */
import { mapRun } from '../js/api.js';
import { stepEventsHTML, stepEventsListHTML } from '../js/views/events.js';
import { countChipsHTML } from '../js/ui.js';

test('countChipsHTML shows nothing for zero warnings and errors', () => {
  assert.equal(countChipsHTML({ warnings: 0, errors: 0 }), '');
  assert.equal(countChipsHTML({}), '');
});

test('countChipsHTML shows warning and error chips with icons and words for screen readers', () => {
  const html = countChipsHTML({ warnings: 2, errors: 1 });
  assert.match(html, /<b class="num">2<\/b><span class="sr-only"> warnings<\/span>/);
  assert.match(html, /<b class="num">1<\/b><span class="sr-only"> error<\/span>/);
  assert.equal((html.match(/<svg/g) || []).length, 2);
  const onlyErrors = countChipsHTML({ warnings: 0, errors: 3 });
  assert.doesNotMatch(onlyErrors, /warning/);
  assert.match(onlyErrors, /3<\/b><span class="sr-only"> errors/);
  assert.match(countChipsHTML({ warnings: 1, errors: 0 }), /1<\/b><span class="sr-only"> warning</);
});

test('mapRun maps event counts, zeros for a server that sends none', () => {
  const base = {
    run_id: '20261016T020000Z', pipeline: 'p', env: 'qa', started_at: '2026-10-16T02:00:00Z', ended_at: '2026-10-16T02:00:15Z',
    duration_seconds: 15, age_seconds: 60, stale: false, status: 'complete', running_step: null, first_missing_step: null,
    missing_count: 0, loss_steps: [], unreadable: 0, died: null, failed: null, flow: null, steps: [],
  };
  assert.deepEqual(mapRun({ ...base, event_counts: { warning: 2, error: 1 } }).eventCounts, { warning: 2, error: 1 });
  assert.deepEqual(mapRun(base).eventCounts, { warning: 0, error: 0 });
});

const stepEvent = (n) => mapEvent({
  id: 'r:info:' + n, ts: '2026-10-15T02:03:41.482Z', level: 'info', step: 'load', message: 'm' + n, fields: null, source: 'pipeline', kind: 'custom',
});

test('a step shows at most its 10 newest events and a link to the timeline filtered to it', () => {
  const events = Array.from({ length: 14 }, (_, i) => stepEvent(i + 1));
  const html = stepEventsListHTML(events, 14, ROUTE, 'load');
  assert.equal((html.match(/class="event /g) || []).length, 10);
  assert.match(html, />m14</);
  assert.doesNotMatch(html, />m4</);
  assert.match(html, /href="#\/p\/callrail\/runs\/prod\/20261015T020000Z\?tab=events&amp;step=load"/);
  assert.match(html, /View all in timeline \(14 events\)/);
});

test('a step with no events says so and still links to the timeline', () => {
  const html = stepEventsListHTML([], 0, ROUTE, 'load');
  assert.match(html, /No events for this step/);
  assert.match(html, /View all in timeline/);
  assert.doesNotMatch(html, /\(0 events\)/);
});

test('the step disclosure carries what is needed to load its events, escaped', () => {
  const html = stepEventsHTML({ pipeline: 'callrail', env: 'prod', id: '20261015T020000Z' }, '"><b>x</b>');
  assert.match(html, /<details class="step__events"/);
  assert.match(html, /data-ev-pipeline="callrail"/);
  assert.doesNotMatch(html, /<b>x<\/b>/);
});
