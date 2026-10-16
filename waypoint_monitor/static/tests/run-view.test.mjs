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
