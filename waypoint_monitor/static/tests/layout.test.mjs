import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  computeLayout, edgesOf, layoutFor, readingOrder, stubsOf,
} from '../js/graph-model.js';

const def = (name, inputs = [], extra = {}) => ({
  name, label: name, group: null, inputs: inputs.map(([n, from]) => ({ name: n, from })), ...extra,
});
const idxOf = (defs, name) => defs.findIndex((d) => d.name === name);
const layerOf = (defs, pos, name) => pos[idxOf(defs, name)].layer;

/* ---------- geometry helpers ---------- */
const overlaps = (a, b) => a.x < b.x + b.w - 0.5 && b.x < a.x + a.w - 0.5 && a.y < b.y + b.h - 0.5 && b.y < a.y + a.h - 0.5;
function countOverlaps(nodes) {
  const r = nodes.filter(Boolean);
  let n = 0;
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) if (overlaps(r[i], r[j])) n++;
  return n;
}
/** Points along an SVG path made of absolute M, L, C and Z commands. */
function samplePath(d) {
  const toks = d.match(/[MLCZ][^MLCZ]*/g) || [];
  const pts = [];
  let cur = null;
  toks.forEach((t) => {
    const op = t[0];
    const n = t.slice(1).trim() ? t.slice(1).trim().split(/\s+/).map(Number) : [];
    if (op === 'M') { cur = [n[0], n[1]]; pts.push(cur); }
    if (op === 'L') {
      for (let k = 1; k <= 20; k++) pts.push([cur[0] + ((n[0] - cur[0]) * k) / 20, cur[1] + ((n[1] - cur[1]) * k) / 20]);
      cur = [n[0], n[1]];
    }
    if (op === 'C') {
      for (let k = 1; k <= 40; k++) {
        const u = k / 40;
        const m = 1 - u;
        pts.push([
          m * m * m * cur[0] + 3 * m * m * u * n[0] + 3 * m * u * u * n[2] + u * u * u * n[4],
          m * m * m * cur[1] + 3 * m * m * u * n[1] + 3 * m * u * u * n[3] + u * u * u * n[5],
        ]);
      }
      cur = [n[4], n[5]];
    }
  });
  return pts;
}
/** Edges whose path enters the rectangle of a step that is neither its producer nor its consumer. */
function countCrossings(L) {
  let n = 0;
  L.edges.forEach((g) => {
    const pts = samplePath(g.d);
    L.nodes.forEach((r, i) => {
      if (!r || i === g.e.from || i === g.e.to) return;
      if (pts.some(([x, y]) => x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h)) n++;
    });
  });
  return n;
}

/* ---------- shapes ---------- */
test('a chain gets one layer per step, all on one row', () => {
  const defs = [def('a'), def('b', [['x', 'a']]), def('c', [['x', 'b']]), def('d', [['x', 'c']])];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.deepEqual(pos.map((p) => p.layer), [0, 1, 2, 3]);
  assert.deepEqual(pos.map((p) => p.row), [0, 0, 0, 0]);
});

test('fan-out puts the consumers in one layer on separate rows', () => {
  const defs = [def('a'), def('b', [['x', 'a']]), def('c', [['x', 'a']]), def('d', [['x', 'a']])];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.deepEqual(pos.slice(1).map((p) => p.layer), [1, 1, 1]);
  assert.deepEqual(pos.slice(1).map((p) => p.row), [0, 1, 2]);
});

test('fan-in sits after its latest producer, at the average of their rows', () => {
  const defs = [def('a'), def('b'), def('c', [['x', 'a'], ['y', 'b']]), def('d', [['x', 'c']])];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.equal(pos[2].layer, 1);
  assert.equal(pos[2].row, 0.5);
  assert.equal(pos[3].layer, 2);
});

test('the CallRail shape lands in five layers with merge after its slowest producer', () => {
  const defs = [
    def('read_callrail_account'), def('read_callrail_call', [['accounts', 'read_callrail_account']]),
    def('read_partners'), def('read_instances', [['partners', 'read_partners']]),
    def('read_campaigns', [['instances', 'read_instances']]), def('read_gads_clickview', [['instances', 'read_instances']]),
    def('merge', [['calls', 'read_callrail_call'], ['campaigns', 'read_campaigns'], ['clickview', 'read_gads_clickview']]),
    def('record', [['s', 'merge']]), def('save', [['s', 'merge']]),
  ];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.deepEqual(pos.map((p) => p.layer), [0, 1, 0, 1, 2, 2, 3, 4, 4]);
  const L = layoutFor('lr', defs, edgesOf(defs), 1200);
  assert.equal(L.layers, 5);
  assert.equal(countOverlaps(L.nodes), 0);
  assert.equal(countCrossings(L), 0);
});

test('a skip edge is routed around the node in the layer it passes', () => {
  const defs = [def('a'), def('b', [['x', 'a']]), def('c', [['x', 'b'], ['y', 'a']])];
  const edges = edgesOf(defs);
  const skip = layoutFor('lr', defs, edges, 1200).edges.find((g) => g.skip);
  assert.ok(skip, 'a -> c spans two layers');
  for (const kind of ['lr', 'compact', 'tb']) {
    const L = layoutFor(kind, defs, edges, 700);
    assert.equal(countCrossings(L), 0, kind);
    assert.equal(countOverlaps(L.nodes), 0, kind);
  }
});

test('a cycle is broken: one edge dropped, layout still finishes', () => {
  const defs = [def('a', [['x', 'b']]), def('b', [['x', 'a']])];
  const edges = edgesOf(defs);
  assert.equal(edges.length, 1);
  const pos = computeLayout(defs, edges);
  assert.ok(pos.every(Boolean));
  assert.equal(countOverlaps(layoutFor('lr', defs, edges, 1200).nodes), 0);
});

test('a step that feeds itself adds no edge', () => {
  assert.equal(edgesOf([def('a', [['x', 'a']])]).length, 0);
});

test('col and row hints override the automatic position', () => {
  const defs = [def('a'), def('b', [['x', 'a']], { col: 3, row: 2 }), def('c', [['x', 'a']])];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.equal(pos[1].layer, 3);
  assert.equal(pos[1].row, 2 - 0); // rows are shifted so the smallest is 0; a is row 0
  assert.equal(pos[0].layer, 0);
  assert.equal(pos[2].layer, 1);
});

test('unhinted steps are placed around hinted ones', () => {
  const defs = [def('a', [], { row: 0 }), def('b'), def('c')];
  const pos = computeLayout(defs, edgesOf(defs));
  assert.deepEqual(pos.map((p) => p.row), [0, 1, 2]);
});

test('a producer that is not in the flow becomes a stub, not an edge', () => {
  const defs = [def('a'), { ...def('b', [['x', 'a'], ['y', 'ghost']]) }];
  assert.equal(edgesOf(defs).length, 1);
  const stubs = stubsOf(defs);
  assert.deepEqual(stubs.map((s) => [s.to, s.input]), [[1, 'y']]);
  const L = layoutFor('lr', defs, edgesOf(defs), 1200);
  assert.equal(L.stubs.length, 1);
  assert.ok(L.stubs[0].d.startsWith('M'));
  assert.equal(stubsOf([def('a'), def('b', [['x', 'a']], {})]).length, 0);
  assert.equal(stubsOf([def('a'), { ...def('b'), inputs: [{ name: 'x', from: 'a', dangling: true }] }]).length, 1);
});

test('reading order is layer by layer, top to bottom', () => {
  const defs = [def('a'), def('b'), def('c', [['x', 'a']]), def('d', [['x', 'b']])];
  assert.deepEqual(readingOrder(defs, edgesOf(defs)).map((i) => defs[i].name), ['a', 'b', 'c', 'd']);
});

test('groups get a band only when they alone fill a run of layers', () => {
  const defs = [
    def('a', [], { group: 'src' }), def('b', [['x', 'a']], { group: 'mid' }), def('c', [['x', 'b']], { group: 'mid' }),
    def('d', [['x', 'c']], { group: 'out' }),
  ];
  const L = layoutFor('lr', defs, edgesOf(defs), 1200, ['src', 'mid', 'out']);
  assert.deepEqual(L.bands.map((b) => b.g), ['src', 'mid', 'out']);
  const mixed = [def('a', [], { group: 'g1' }), def('b', [], { group: 'g2' })];
  assert.deepEqual(layoutFor('lr', mixed, edgesOf(mixed), 1200, ['g1', 'g2']).bands, []);
});

/* ---------- larger graphs ---------- */
/** Deterministic pseudo-random DAG: every step reads from one or two earlier steps, so layers vary in width. */
function bigFlow(n) {
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const defs = [];
  for (let i = 0; i < n; i++) {
    const inputs = [];
    if (i >= 1 && rnd() < 0.85) inputs.push(['a', 's' + Math.max(0, i - 1 - Math.floor(rnd() * 3))]);
    if (i >= 4 && rnd() < 0.4) inputs.push(['b', 's' + Math.floor(rnd() * (i - 2))]);
    const uniq = inputs.filter((p, k) => inputs.findIndex((q) => q[1] === p[1]) === k);
    defs.push(def('s' + i, uniq));
  }
  return defs;
}

function measure(defs, kind, cw) {
  const edges = edgesOf(defs);
  const t0 = performance.now();
  const L = layoutFor(kind, defs, edges, cw);
  const ms = performance.now() - t0;
  return { L, ms, overlaps: countOverlaps(L.nodes), crossings: countCrossings(L), edges: edges.length };
}

test('30 steps: no node overlaps and no edge through another node, in every layout', () => {
  const defs = bigFlow(30);
  for (const [kind, cw] of [['lr', 1200], ['compact', 700], ['tb', 375]]) {
    const m = measure(defs, kind, cw);
    console.log(`30 steps ${kind}: ${m.edges} edges, ${m.L.layers} layers, overlaps ${m.overlaps}, crossings ${m.crossings}, ${m.ms.toFixed(1)} ms`); // eslint-disable-line no-console
    assert.equal(m.overlaps, 0, kind + ' overlaps');
    assert.equal(m.crossings, 0, kind + ' crossings');
  }
});

test('50 steps: laid out in under 100 ms with no overlaps', () => {
  const defs = bigFlow(50);
  const m = measure(defs, 'lr', 1200);
  console.log(`50 steps lr: ${m.edges} edges, ${m.L.layers} layers, overlaps ${m.overlaps}, crossings ${m.crossings}, ${m.ms.toFixed(1)} ms`); // eslint-disable-line no-console
  assert.ok(m.ms < 100, m.ms + ' ms');
  assert.equal(m.overlaps, 0);
  assert.equal(measure(defs, 'tb', 375).overlaps, 0);
});

test('100 steps still lay out', () => {
  const m = measure(bigFlow(100), 'compact', 900);
  assert.equal(m.overlaps, 0);
  assert.ok(m.ms < 500);
});
