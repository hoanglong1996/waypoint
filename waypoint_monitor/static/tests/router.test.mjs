import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildRoute, parseRoute, routeTitle } from '../js/router.js';

test('an empty hash and #/ are the home page', () => {
  assert.deepEqual(parseRoute(''), { name: 'home' });
  assert.deepEqual(parseRoute('#'), { name: 'home' });
  assert.deepEqual(parseRoute('#/'), { name: 'home' });
  assert.deepEqual(parseRoute(undefined), { name: 'home' });
});

test('#/p/<id> is the history page of that pipeline', () => {
  assert.deepEqual(parseRoute('#/p/callrail'), { name: 'pipeline', id: 'callrail', page: 'history', env: null });
});

test('a run has its own address: pipeline, environment and run id', () => {
  assert.deepEqual(parseRoute('#/p/callrail/runs/prod/20261015T020000Z'), {
    name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z',
  });
});

test('a malformed run address is not found, keeping the pipeline', () => {
  assert.deepEqual(parseRoute('#/p/callrail/runs/prod/nope'), { name: 'notfound', id: 'callrail' });
  assert.deepEqual(parseRoute('#/p/callrail/runs//20261015T020000Z'), { name: 'notfound', id: 'callrail' });
  assert.deepEqual(parseRoute('#/p/callrail/runs/prod'), { name: 'notfound', id: 'callrail' });
  assert.deepEqual(parseRoute('#/p/callrail/runs/prod/20261015T020000Z/x'), { name: 'notfound', id: 'callrail' });
});

test('run addresses round-trip, including encoded names', () => {
  const route = { name: 'run', id: 'google ads/v2', env: 'qa', runId: '20261015T020000Z' };
  const hash = buildRoute(route);
  assert.equal(hash, '#/p/google%20ads%2Fv2/runs/qa/20261015T020000Z');
  assert.deepEqual(parseRoute(hash), route);
});

test('history carries an optional environment', () => {
  assert.deepEqual(parseRoute('#/p/callrail/history'), { name: 'pipeline', id: 'callrail', page: 'history', env: null });
  assert.deepEqual(parseRoute('#/p/callrail/history?env=qa'), { name: 'pipeline', id: 'callrail', page: 'history', env: 'qa' });
  assert.deepEqual(parseRoute('#/p/callrail/history?env='), { name: 'pipeline', id: 'callrail', page: 'history', env: null });
});

test('pipeline names are url-encoded and decoded', () => {
  const route = { name: 'pipeline', id: 'google ads/v2', page: 'history', env: 'prod' };
  const hash = buildRoute(route);
  assert.equal(hash, '#/p/google%20ads%2Fv2/history?env=prod');
  assert.deepEqual(parseRoute(hash), route);
});

test('unknown shapes are not found, keeping the id that was asked for', () => {
  assert.deepEqual(parseRoute('#/nope'), { name: 'notfound', id: '' });
  assert.deepEqual(parseRoute('#/p'), { name: 'notfound', id: '' });
  assert.deepEqual(parseRoute('#/p/x/other'), { name: 'notfound', id: 'x' });
  assert.deepEqual(parseRoute('#/p/x/history/more'), { name: 'notfound', id: 'x' });
  assert.deepEqual(parseRoute('#/p/%E0%A4%A'), { name: 'notfound', id: '' });
});

test('building a route round-trips', () => {
  for (const hash of ['#/', '#/p/a/history', '#/p/a/history?env=qa', '#/p/a/runs/prod/20261015T020000Z']) {
    assert.equal(buildRoute(parseRoute(hash)), hash);
  }
  // the bare pipeline address is history; it is rebuilt in its explicit form
  assert.equal(buildRoute(parseRoute('#/p/a')), '#/p/a/history');
  assert.equal(buildRoute({ name: 'notfound', id: 'x' }), '#/');
});

test('the page title follows the route', () => {
  assert.equal(routeTitle({ name: 'home' }), 'Waypoint Monitor');
  assert.equal(routeTitle({ name: 'pipeline', id: 'c', page: 'history' }, 'CallRail'), 'CallRail · History · Waypoint Monitor');
  assert.equal(routeTitle({ name: 'run', id: 'c', env: 'prod', runId: '20261015T020000Z' }, 'CallRail', 'Oct 15, 02:00'), 'CallRail · Oct 15, 02:00 · Waypoint Monitor');
  assert.equal(routeTitle({ name: 'run', id: 'c', env: 'prod', runId: '20261015T020000Z' }), 'c · Run · Waypoint Monitor');
  assert.equal(routeTitle({ name: 'notfound', id: 'x' }), 'Pipeline not found · Waypoint Monitor');
});

test('a run page can ask for the Events tab, with level and step filters', () => {
  const base = '#/p/callrail/runs/prod/20261015T020000Z';
  assert.deepEqual(parseRoute(base + '?tab=events'), {
    name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z', tab: 'events', levels: [], step: null,
  });
  assert.deepEqual(parseRoute(base + '?tab=events&level=warning,error&step=load'), {
    name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z', tab: 'events', levels: ['warning', 'error'], step: 'load',
  });
  // unknown levels are dropped; any other tab is the default Steps tab
  assert.deepEqual(parseRoute(base + '?tab=events&level=debug,info').levels, ['info']);
  assert.deepEqual(parseRoute(base + '?tab=steps'), { name: 'run', id: 'callrail', env: 'prod', runId: '20261015T020000Z' });
});

test('Events tab addresses round-trip, including encoded step names', () => {
  for (const hash of [
    '#/p/a/runs/prod/20261015T020000Z?tab=events',
    '#/p/a/runs/prod/20261015T020000Z?tab=events&level=error',
    '#/p/a/runs/prod/20261015T020000Z?tab=events&level=info,warning&step=read%20x',
  ]) {
    assert.equal(buildRoute(parseRoute(hash)), hash);
  }
  const route = { name: 'run', id: 'a', env: 'qa', runId: '20261015T020000Z', tab: 'events', levels: [], step: 'a/b' };
  assert.deepEqual(parseRoute(buildRoute(route)), route);
});

test('a run address without the tab has no query', () => {
  const route = { name: 'run', id: 'a', env: 'qa', runId: '20261015T020000Z', tab: 'steps', levels: ['error'] };
  assert.equal(buildRoute(route), '#/p/a/runs/qa/20261015T020000Z');
});

test('the item page keeps its List | Graph choice in the address', () => {
  const base = '#/p/g/runs/prod/20261017T020301Z/steps/accounts/items/acct-7';
  assert.equal(parseRoute(base).view, undefined);
  assert.equal(parseRoute(base + '?view=graph').view, 'graph');
  assert.equal(parseRoute(base + '?view=nope').view, undefined);
  assert.equal(buildRoute(parseRoute(base + '?view=list')), base + '?view=list');
  assert.equal(buildRoute(parseRoute(base)), base);
});
