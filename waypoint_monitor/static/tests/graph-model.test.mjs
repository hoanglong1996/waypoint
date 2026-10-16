import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  edgeInfo, edgesOf, edgeWidth, layoutFor, neighbours, nodeStates, partition, pickLayout, readingOrder,
} from '../js/graph-model.js';

const defs = [
  ['read_callrail_account', 'CallRail', []],
  ['read_callrail_call', 'CallRail', [['accounts', 'read_callrail_account']]],
  ['read_partners', 'Google Ads', []],
  ['read_instances', 'Google Ads', [['partners', 'read_partners']]],
  ['read_campaigns', 'Google Ads', [['instances', 'read_instances']]],
  ['read_gads_clickview', 'Google Ads', [['instances', 'read_instances']]],
  ['merge_calls_clickview', 'Merge', [['calls', 'read_callrail_call'], ['campaigns', 'read_campaigns'], ['clickview', 'read_gads_clickview']]],
  ['record_call_statistics', 'Persist', [['call_statistics', 'merge_calls_clickview']]],
  ['save_call_statistics', 'Persist', [['call_statistics', 'merge_calls_clickview']]],
];
const steps = defs.map(([name, group, inputs]) => ({ name, group, inputs: inputs.map(([n, from]) => ({ name: n, from })) }));
const edges = edgesOf(steps);
const idx = (name) => steps.findIndex((s) => s.name === name);

const OUT = [10, 1284, 6, 14, 92, 3410, 1284, null, null];
function mkRun({ lossAt = null, missingFrom = null } = {}) {
  const out = OUT.slice();
  if (lossAt != null) out[lossAt] = 0;
  return {
    steps: steps.map((s, i) => {
      if (missingFrom != null && i >= missingFrom) return { name: s.name, missing: true };
      const inputs = s.inputs.map((p) => {
        const v = out[idx(p.from)];
        return { name: p.name, value: v == null ? 0 : v };
      });
      return { name: s.name, inputs, output: out[i], finishedAt: new Date() };
    }),
  };
}

test('nine edges, merge has three inputs, instances two outputs', () => {
  assert.equal(edges.length, 9);
  assert.equal(edges.filter((e) => e.to === idx('merge_calls_clickview')).length, 3);
  assert.equal(edges.filter((e) => e.from === idx('read_instances')).length, 2);
  assert.equal(edges.filter((e) => e.from === idx('merge_calls_clickview')).length, 2);
});

test('neighbours are direct only', () => {
  const n = neighbours(edges, idx('merge_calls_clickview'));
  assert.deepEqual([...n.up].sort(), [idx('read_callrail_call'), idx('read_campaigns'), idx('read_gads_clickview')].sort());
  assert.equal(n.down.size, 2);
  assert.equal(neighbours(edges, 0).up.size, 0);
});

test('healthy run: all ok, nothing affected, all edges ok', () => {
  const run = mkRun();
  const ns = nodeStates(run, edges);
  assert.ok(ns.st.every((s) => s === 'ok'));
  assert.deepEqual(ns.affected, {});
  assert.ok(edges.every((e) => edgeInfo(run, e).state === 'ok'));
});

test('loss at campaigns: loss node, downstream affected, empty edge', () => {
  const run = mkRun({ lossAt: idx('read_campaigns') });
  const ns = nodeStates(run, edges);
  assert.equal(ns.st[idx('read_campaigns')], 'loss');
  assert.ok(ns.affected[idx('merge_calls_clickview')]);
  assert.ok(ns.affected[idx('save_call_statistics')]);
  assert.ok(!ns.affected[idx('read_callrail_call')]);
  const e = edges.find((x) => x.from === idx('read_campaigns'));
  assert.deepEqual(edgeInfo(run, e), { state: 'empty', value: 0 });
});

test('stopped run: first missing is stopped, later ones unreached, edges inactive', () => {
  const run = mkRun({ missingFrom: idx('read_gads_clickview') });
  const ns = nodeStates(run, edges);
  assert.equal(ns.st[idx('read_gads_clickview')], 'stopped');
  assert.equal(ns.st[idx('merge_calls_clickview')], 'unreached');
  assert.equal(ns.st[idx('read_campaigns')], 'ok');
  const e = edges.find((x) => x.from === idx('read_instances') && x.to === idx('read_gads_clickview'));
  assert.deepEqual(edgeInfo(run, e), { state: 'inactive', value: null });
});

test('edge count is the consumer input value', () => {
  const run = mkRun();
  run.steps[idx('read_callrail_call')].inputs[0].value = 9;
  const e = edges.find((x) => x.to === idx('read_callrail_call'));
  assert.equal(edgeInfo(run, e).value, 9);
});

test('edge width formula', () => {
  assert.equal(edgeWidth(0, 3410), 1.25);
  assert.ok(Math.abs(edgeWidth(3410, 3410) - 4) < 1e-9);
  assert.ok(edgeWidth(10, 3410) < edgeWidth(1284, 3410));
  assert.equal(edgeWidth(null, 10), 1.5);
});

test('pickLayout breakpoints', () => {
  assert.equal(pickLayout(375).kind, 'tb');
  assert.equal(pickLayout(599).kind, 'tb');
  assert.equal(pickLayout(600).kind, 'compact');
  assert.equal(pickLayout(879).kind, 'compact');
  assert.equal(pickLayout(880).kind, 'lr');
  assert.equal(pickLayout(1440).scale, 1);
  assert.equal(pickLayout(1138 / 2 + 400).kind, 'lr');
  assert.equal(pickLayout(1000, 'compact').kind, 'compact');
  assert.equal(pickLayout(2000, 'compact').scale, 1.35);
});

test('an unplanned step goes to other and is not connected', () => {
  const extra = [...steps, { name: 'brand_new_step', group: null, unplanned: true, inputs: [] }];
  const p = partition(extra);
  assert.deepEqual(p.other, [9]);
  assert.equal(p.placed.length, 9);
  assert.equal(edgesOf(extra).length, 9);
  assert.equal(layoutFor('lr', extra, edgesOf(extra), 1200).nodes[9], null);
});

test('reading order is column by column', () => {
  assert.deepEqual(readingOrder(steps, edges).map((i) => steps[i].name), [
    'read_callrail_account', 'read_partners', 'read_callrail_call', 'read_instances',
    'read_campaigns', 'read_gads_clickview', 'merge_calls_clickview', 'record_call_statistics', 'save_call_statistics',
  ]);
});

test('layout shape is identical for every run and has a path per edge', () => {
  for (const kind of ['lr', 'compact', 'tb']) {
    const L = layoutFor(kind, steps, edges, 375);
    assert.equal(L.edges.length, 9);
    assert.ok(L.nodes.every(Boolean));
    assert.ok(L.edges.every((g) => g.d.startsWith('M')));
  }
  assert.equal(layoutFor('lr', steps, edges, 1200).W, 1138);
  assert.equal(layoutFor('compact', steps, edges, 700).W, 628);
});

/* ---------- live states (spec 004) ---------- */
function liveRun(runningAt, { stalled = false, died = false, waitingAfter = true } = {}) {
  const base = mkRun({ missingFrom: runningAt });
  return {
    steps: base.steps.map((s, i) => {
      if (i === runningAt) return { name: s.name, state: died ? 'died' : stalled ? 'stalled' : 'running', inputs: [], output: null, finishedAt: null };
      if (i > runningAt) {
        return stalled || died || !waitingAfter ? { name: s.name, state: 'missing', missing: true } : { name: s.name, state: 'waiting', inputs: [], output: null, finishedAt: null };
      }
      return { ...s, state: 'done' };
    }),
  };
}

test('running step and waiting steps get their own node states', () => {
  const { st, affected } = nodeStates(liveRun(3), edges);
  assert.deepEqual(st.slice(0, 3), ['ok', 'ok', 'ok']);
  assert.equal(st[3], 'running');
  assert.deepEqual(st.slice(4), ['waiting', 'waiting', 'waiting', 'waiting', 'waiting']);
  assert.ok(!st.includes('stopped') && !st.includes('unreached'));
  assert.deepEqual(affected, {});
});

test('a stalled step is the stop point; later missing steps are unreached', () => {
  const { st } = nodeStates(liveRun(3, { stalled: true }), edges);
  assert.equal(st[3], 'stalled');
  assert.deepEqual(st.slice(4), ['unreached', 'unreached', 'unreached', 'unreached', 'unreached']);
  assert.ok(!st.includes('stopped'));
});

test('a died step is the stop point; later missing steps are unreached', () => {
  const { st, affected } = nodeStates(liveRun(3, { died: true }), edges);
  assert.deepEqual(st.slice(0, 3), ['ok', 'ok', 'ok']);
  assert.equal(st[3], 'died');
  assert.deepEqual(st.slice(4), ['unreached', 'unreached', 'unreached', 'unreached', 'unreached']);
  assert.ok(!st.includes('stopped') && !st.includes('stalled'));
  assert.deepEqual(affected, {});
});

test('edges into or out of a step that is not done are inactive', () => {
  const run = liveRun(3);
  const into = edges.find((e) => e.to === idx('read_instances')); // producer done, consumer running
  assert.deepEqual(edgeInfo(run, into), { state: 'inactive', value: null });
  const out = edges.find((e) => e.from === idx('read_instances')); // producer running
  assert.equal(edgeInfo(run, out).state, 'inactive');
  const done = edges.find((e) => e.to === idx('read_callrail_call'));
  assert.equal(edgeInfo(run, done).state, 'ok');
});

test('legacy payloads without state still work', () => {
  const { st } = nodeStates(mkRun({ missingFrom: 6 }), edges);
  assert.equal(st[6], 'stopped');
  assert.equal(st[7], 'unreached');
});
