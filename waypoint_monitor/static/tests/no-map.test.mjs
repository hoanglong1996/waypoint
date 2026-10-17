/* A run with no map step must look exactly as before specs/014. The golden file was produced by the code of the
   commit before the map step work (same fixture, UTC, a fixed clock); every part of it is compared here. */
process.env.TZ = 'UTC';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import { mapRun } from '../js/api.js';
import {
  computeLayout, dimsOf, edgesOf, layoutFor, pickLayout,
} from '../js/graph-model.js';
import { groupKeys, runSignature } from '../js/model.js';
import { buildRoute, parseRoute } from '../js/router.js';
import { stepItemHTML } from '../js/views/step.js';

const read = (name) => JSON.parse(fs.readFileSync(new URL('./fixtures/' + name, import.meta.url), 'utf8'));
const golden = read('no-map-golden.json');

const withClock = (fn) => {
  const real = Date.now;
  Date.now = () => 1790000000000;
  try {
    return fn();
  } finally {
    Date.now = real;
  }
};

const run = withClock(() => mapRun(read('no-map-run.json')));
const plain = (v) => JSON.parse(JSON.stringify(v));

test('the run maps to exactly the same data, with no map fields anywhere', () => {
  assert.deepEqual(plain(run), golden.run);
  assert.equal(JSON.stringify(run).includes('"map"'), false);
  assert.equal(run.steps.some((s) => 'map' in s), false);
  assert.equal(run.defs.some((d) => 'map' in d), false);
});

test('the signature that decides redraws is unchanged', () => {
  assert.equal(runSignature([run]), golden.signature);
});

test('every step of the list is drawn byte for byte as before', () => {
  const cfg = { staleHours: 26 };
  withClock(() => {
    run.steps.forEach((s, i) => {
      assert.equal(stepItemHTML(run, [run], cfg, i, false), golden.items[i], 'step ' + s.name);
      assert.equal(stepItemHTML(run, [run], cfg, i, true), golden.itemsCompact[i], 'compact step ' + s.name);
    });
  });
});

test('the graph geometry is unchanged for a flow without a map step, at every width', () => {
  const edges = edgesOf(run.defs);
  const dims = dimsOf(computeLayout(run.defs, edges));
  [1200, 900, 700, 500].forEach((cw) => {
    const pk = pickLayout(cw, 'auto', dims);
    assert.deepEqual(plain({ pk, L: layoutFor(pk.kind, run.defs, edges, cw, groupKeys(run)) }), golden.layouts[cw], 'width ' + cw);
    assert.deepEqual(plain({ pk: pickLayout(cw, 'compact', dims), L: layoutFor('compact', run.defs, edges, cw, []) }), golden.layouts[cw + 'c'], 'compact ' + cw);
  });
});

test('existing addresses parse and build as before', () => {
  Object.keys(golden.routes).forEach((h) => {
    const r = parseRoute(h);
    assert.deepEqual(plain(r), golden.routes[h].r, h);
    assert.equal(buildRoute(r), golden.routes[h].back, h);
  });
});

test('a flow with a map step gets larger nodes; a flow without one does not', async () => {
  const { hasMapStep, pickLayout: pick } = await import('../js/graph-model.js');
  assert.equal(hasMapStep(run.defs), false);
  assert.equal(hasMapStep([{ name: 'a', map: { steps: [] } }]), true);
  // the natural width with a map step is wider, so the same panel may switch to the compact layout sooner
  const dims = { layers: 5, slots: 1 };
  assert.equal(pick(900, 'auto', dims).kind, 'lr');
  assert.equal(pick(900, 'auto', dims, true).kind, 'compact');
});
