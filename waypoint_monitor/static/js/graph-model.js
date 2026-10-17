/* Steps are drawn from the run's own flow description: each step def is
   {name, label, group, inputs: [{name, from, dangling?}], col?, row?, unplanned?, noFlow?}.
   Defs flagged `unplanned` (reported but not in the flow) or `noFlow` (the run has no usable flow) are not placed. */
import { isDone, isLoss, stepState } from './model.js';

export const MIN_SCALE = 0.55; // below this the graph scrolls sideways instead of shrinking further

const isPlaced = (d) => !d.unplanned && !d.noFlow;

/** Split step indexes into those drawn in the graph and those that are not. */
export function partition(defs) {
  const out = { placed: [], other: [] };
  defs.forEach((d, i) => (isPlaced(d) ? out.placed : out.other).push(i));
  return out;
}

/**
 * One edge per consumer input: producer index -> consumer index, only between placed steps.
 * Inputs whose producer is unknown are returned by `stubsOf`. An edge that would close a cycle is dropped.
 */
export function edgesOf(defs) {
  const index = new Map(defs.map((d, i) => [d.name, i]));
  const all = [];
  defs.forEach((d, to) => {
    if (!isPlaced(d)) return;
    d.inputs.forEach((p, k) => {
      const from = index.get(p.from);
      if (p.dangling || from === undefined || !isPlaced(defs[from]) || from === to) return;
      all.push({ from, to, input: p.name, k, n: d.inputs.length });
    });
  });
  // depth-first search: an edge into a node still on the stack is a back edge (cycle) and is dropped
  const out = new Map();
  all.forEach((e) => (out.has(e.from) ? out.get(e.from).push(e) : out.set(e.from, [e])));
  const drop = new Set();
  const state = new Map(); // 1 = on stack, 2 = finished
  const visit = (u) => {
    state.set(u, 1);
    (out.get(u) || []).forEach((e) => {
      if (state.get(e.to) === 1) drop.add(e);
      else if (!state.has(e.to)) visit(e.to);
    });
    state.set(u, 2);
  };
  defs.forEach((d, i) => { if (isPlaced(d) && !state.has(i)) visit(i); });
  return all.filter((e) => !drop.has(e));
}

/** Inputs of placed steps whose producer is not in the flow: drawn as a flagged stub, never as an arrow. */
export function stubsOf(defs) {
  const index = new Map(defs.map((d, i) => [d.name, i]));
  const out = [];
  defs.forEach((d, to) => {
    if (!isPlaced(d)) return;
    d.inputs.forEach((p, k) => {
      const from = index.get(p.from);
      if (p.dangling || from === undefined || !isPlaced(defs[from])) out.push({ to, input: p.name, k, n: d.inputs.length });
    });
  });
  return out;
}

/**
 * Layered layout from the hand-offs. layer = longest path from a source (a `col` hint overrides it);
 * rows inside a layer follow the average row of the producers, at least 1 apart (a `row` hint overrides).
 * Returns one {layer, row} per def, null for steps that are not placed.
 */
export function computeLayout(defs, edges) {
  const pos = defs.map(() => null);
  const placedIdx = defs.map((d, i) => i).filter((i) => isPlaced(defs[i]));
  const prods = new Map(placedIdx.map((i) => [i, []]));
  const cons = new Map(placedIdx.map((i) => [i, []]));
  edges.forEach((e) => { prods.get(e.to).push(e.from); cons.get(e.from).push(e.to); });
  const indeg = new Map(placedIdx.map((i) => [i, prods.get(i).length]));
  const layer = new Map();
  const queue = placedIdx.filter((i) => indeg.get(i) === 0);
  const hint = (v) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null);
  while (queue.length) {
    const u = queue.shift();
    const fromProducers = prods.get(u).length ? Math.max(...prods.get(u).map((p) => layer.get(p) + 1)) : 0;
    const h = hint(defs[u].col);
    layer.set(u, h == null ? fromProducers : h);
    cons.get(u).forEach((c) => {
      indeg.set(c, indeg.get(c) - 1);
      if (indeg.get(c) === 0) queue.push(c);
    });
    queue.sort((a, b) => a - b);
  }
  const byLayer = new Map();
  placedIdx.forEach((i) => {
    const l = layer.get(i);
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l).push(i);
  });
  const rowOf = new Map();
  [...byLayer.keys()].sort((a, b) => a - b).forEach((l) => {
    const items = byLayer.get(l).map((i) => {
      const h = hint(defs[i].row);
      const ps = prods.get(i).filter((p) => rowOf.has(p));
      const want = h != null ? h : ps.length ? ps.reduce((t, p) => t + rowOf.get(p), 0) / ps.length : null;
      return { i, h, want };
    });
    const known = items.filter((x) => x.want != null).sort((a, b) => a.want - b.want || a.i - b.i);
    const free = items.filter((x) => x.want == null).sort((a, b) => a.i - b.i);
    let prev = -1;
    known.concat(free).forEach((x) => {
      const r = x.h != null ? x.h : Math.max(x.want == null ? prev + 1 : x.want, prev + 1);
      rowOf.set(x.i, r);
      prev = Math.max(prev, r);
    });
  });
  const minRow = placedIdx.length ? Math.min(...placedIdx.map((i) => rowOf.get(i))) : 0;
  placedIdx.forEach((i) => { pos[i] = { layer: layer.get(i), row: rowOf.get(i) - minRow }; });
  return pos;
}

/** Direct neighbours only. */
export function neighbours(edges, i) {
  const up = new Set();
  const down = new Set();
  edges.forEach((e) => {
    if (e.to === i) up.add(e.from);
    if (e.from === i) down.add(e.to);
  });
  return { up, down };
}

/**
 * stopped = first missing, unreached = later missing, loss, ok; affected = ok nodes downstream of a loss.
 * Live steps: running, waiting, and stalled, died or failed (stop points like `stopped`, so later missing steps are unreached).
 */
export function nodeStates(run, edges) {
  let firstMissing = -1;
  const st = [];
  const loss = [];
  run.steps.forEach((s, i) => {
    const state = stepState(s);
    if (state === 'running' || state === 'waiting') {
      st[i] = state;
    } else if (state === 'stalled' || state === 'died' || state === 'failed') {
      st[i] = state;
      if (firstMissing < 0) firstMissing = i;
    } else if (state === 'missing') {
      st[i] = firstMissing < 0 ? 'stopped' : 'unreached';
      if (firstMissing < 0) firstMissing = i;
    } else if (isLoss(s)) {
      st[i] = 'loss';
      loss.push(i);
    } else st[i] = 'ok';
  });
  const affected = {};
  const queue = loss.slice();
  while (queue.length) {
    const n = queue.shift();
    edges.forEach((e) => {
      if (e.from === n && !affected[e.to]) {
        affected[e.to] = true;
        queue.push(e.to);
      }
    });
  }
  Object.keys(affected).forEach((k) => {
    if (st[k] !== 'ok') delete affected[k];
  });
  return { st, affected };
}

/** inactive = producer or consumer not done; empty = count 0; else ok. Count = the consumer's recorded input. */
export function edgeInfo(run, e) {
  const prod = run.steps[e.from];
  const cons = run.steps[e.to];
  if (!isDone(prod) || !isDone(cons)) return { state: 'inactive', value: null };
  const v = cons.inputs[e.k] ? cons.inputs[e.k].value : null;
  return { state: v === 0 ? 'empty' : 'ok', value: v };
}

/** Line width in px, log scale against the largest edge count of the run. */
export function edgeWidth(value, max) {
  if (value == null) return 1.5;
  return 1.25 + (2.75 * Math.log10(value + 1)) / Math.log10(max + 1);
}

/* Geometry is computed in "flow space": u runs along the flow (left to right, or top to bottom), v across it.
   A node is {u, v, du, dv}; `toXY` maps flow space to the page for the chosen layout. */
const SIZE = {
  lr: { du: 154, dv: 128, gapU: 88, gapV: 28, padU: 8, padV: 28 },
  compact: { du: 100, dv: 72, gapU: 28, gapV: 20, padU: 8, padV: 22 },
  tb: { du: 124, dv: 0, gapU: 92, gapV: 12, padU: 4, padV: 22 },
};
const TB_MIN_NODE = 110;
/* A map step's node (specs/014) carries a progress line, pills and a footer, so a flow that declares one gets larger
   nodes; a flow without one keeps the sizes above exactly. */
const MAP_SIZE = {
  lr: { du: 204, dv: 188 },
  compact: { du: 150, dv: 136 },
  tb: { du: 178, dv: 0 },
};
const TB_MIN_MAP_NODE = 200;
const sizeOf = (kind, hasMap) => (hasMap ? { ...SIZE[kind], ...MAP_SIZE[kind] } : SIZE[kind]);
/** Whether any step of the flow is a map step. */
export const hasMapStep = (defs) => defs.some((d) => !!d.map);

export const dimsOf = (pos) => {
  const rows = new Map();
  let layers = 0;
  pos.forEach((p) => {
    if (!p) return;
    layers = Math.max(layers, Math.floor(p.layer) + 1);
    rows.set(p.layer, (rows.get(p.layer) || 0) + 1);
  });
  return { layers: Math.max(1, layers), slots: Math.max(1, ...rows.values(), 1) };
};

/** Natural (unscaled) width of the left-to-right layouts for a number of layers. */
export const naturalWidth = (kind, layers, hasMap = false) => {
  const z = sizeOf(kind, hasMap);
  return z.padU * 2 + layers * z.du + (layers - 1) * z.gapU;
};

/** Choose the layout from the panel's inner width and the graph's size ({layers, slots}). */
export function pickLayout(cw, prefer, dims, hasMap = false) {
  const layers = dims ? dims.layers : 5;
  if (cw < 600) return { kind: 'tb', scale: 1 };
  const lr = naturalWidth('lr', layers, hasMap);
  if (prefer !== 'compact' && cw >= 880 && cw / lr >= 0.7) return { kind: 'lr', scale: Math.min(1, cw / lr) };
  const cp = naturalWidth('compact', layers, hasMap);
  return { kind: 'compact', scale: Math.max(MIN_SCALE, Math.min(1.35, cw / cp)) };
}

const num = (n) => Math.round(n * 10) / 10;

/**
 * Geometry. Returns { kind, W, H, nodes[i]|null, bands[], edges[{e, d, arrow, chip, skip}], stubs[], chips, layers }.
 * `groups` is the ordered list of group keys (bands are drawn only for a group that alone fills a run of layers).
 */
export function layoutFor(kind, defs, edges, cw, groups = []) {
  const pos = computeLayout(defs, edges);
  const { layers, slots } = dimsOf(pos);
  const hasMap = hasMapStep(defs);
  const z = sizeOf(kind, hasMap);
  const tb = kind === 'tb';
  const toXY = tb ? (u, v) => [v, u] : (u, v) => [u, v];
  let dv = z.dv;
  let slotOf = (p) => p.row;
  if (tb) {
    const rank = new Map();
    pos.forEach((p, i) => { if (p) { if (!rank.has(p.layer)) rank.set(p.layer, []); rank.get(p.layer).push(i); } });
    const slot = new Map();
    rank.forEach((list) => list.sort((a, b) => pos[a].row - pos[b].row || a - b).forEach((i, r) => slot.set(i, r)));
    const inner = Math.max(300, cw) - z.padV - 6;
    dv = Math.max(hasMap ? TB_MIN_MAP_NODE : TB_MIN_NODE, Math.floor((inner - z.gapV * (slots - 1)) / slots));
    slotOf = (p, i) => slot.get(i);
  }
  const nodesUV = defs.map((d, i) => {
    const p = pos[i];
    if (!p) return null;
    return { u: z.padU + p.layer * (z.du + z.gapU), v: z.padV + slotOf(p, i) * (dv + z.gapV), du: z.du, dv, layer: p.layer };
  });
  const placed = nodesUV.filter(Boolean);
  const vEnd = placed.length ? Math.max(...placed.map((n) => n.v + n.dv)) : z.padV + dv;
  const uEnd = placed.length ? Math.max(...placed.map((n) => n.u + n.du)) : z.padU + z.du;
  const vMax = vEnd + (tb ? 6 : 18);
  const W = tb ? Math.max(Math.max(300, cw), vEnd + 6) : uEnd + z.padU;
  const H = tb ? uEnd + 6 : vMax;
  const rect = (n) => {
    const [x, y] = toXY(n.u, n.v);
    return tb ? { x, y, w: n.dv, h: n.du } : { x, y, w: n.du, h: n.dv };
  };
  const nodes = nodesUV.map((n) => (n ? rect(n) : null));

  // free channels across the flow: the middle of every gap between occupied v-ranges, plus both margins
  const spans = placed.map((n) => [n.v, n.v + n.dv]).sort((a, b) => a[0] - b[0]);
  const channels = [z.padV / 2, vEnd + (tb ? 3 : 9)];
  for (let k = 1; k < spans.length; k++) if (spans[k][0] > spans[k - 1][1]) channels.push((spans[k][0] + spans[k - 1][1]) / 2);
  const MARGIN = 6;
  const clear = (v, l0, l1) => !placed.some((n) => n.layer > l0 && n.layer < l1 && v > n.v - MARGIN && v < n.v + n.dv + MARGIN);

  const path = (cmds) => cmds.map(([op, ...a]) => {
    const pts = [];
    for (let k = 0; k < a.length; k += 2) pts.push(...toXY(a[k], a[k + 1]).map(num));
    return op + pts.join(' ');
  }).join('');
  const arrow = (u, v) => path([['M', u - 8, v - 4.5], ['L', u, v], ['L', u - 8, v + 4.5], ['Z']]);

  const portV = (n, k, cnt) => n.v + (n.dv * (k + 1)) / (cnt + 1);
  const out = edges.map((e) => {
    const a = nodesUV[e.from];
    const b = nodesUV[e.to];
    const su = a.u + a.du;
    const sv = a.v + a.dv / 2;
    const eu = b.u;
    const ev = portV(b, e.k, e.n);
    const tip = eu - 7;
    const skip = b.layer - a.layer > 1;
    let cmds;
    let chip;
    let zone = [su, eu]; // where the chip may sit along the flow without covering a node
    if (!skip) {
      const c = (tip - su) / 2;
      cmds = [['M', su, sv], ['C', su + c, sv, tip - c, ev, tip, ev]];
      chip = [(su + tip) / 2, (sv + ev) / 2];
    } else {
      const g = z.gapU;
      const cv = [sv, ...channels].filter((v) => clear(v, a.layer, b.layer)).sort((p, q) => Math.abs(p - sv) - Math.abs(q - sv))[0];
      const tu = eu - g * 0.8;
      const c = (tip - tu) / 2;
      cmds = cv === sv
        ? [['M', su, sv], ['L', tu, sv], ['C', tu + c, sv, tip - c, ev, tip, ev]]
        : [['M', su, sv], ['C', su + g * 0.4, sv, su + g * 0.4, cv, su + g * 0.8, cv], ['L', tu, cv], ['C', tu + c, cv, tip - c, ev, tip, ev]];
      // on a channel the chip waits in the first gap, which no node occupies; on the straight run it sits mid-way
      chip = cv === sv ? [(su + tu) / 2, sv] : [su + g * 0.45, cv];
      zone = cv === sv ? [su, tu] : [su, su + g];
    }
    return { e, d: path(cmds), chip: { u: chip[0], v: chip[1] }, zone, arrow: arrow(tip + 7, ev), skip };
  });
  // Chips that would sit on top of each other are nudged apart. Left to right they stack across the flow;
  // top to bottom they are wide, so they stagger along the flow inside the gap between two layers.
  const placedChips = [];
  out.forEach((g) => {
    let { u, v } = g.chip;
    if (tb) {
      const [lo, hi] = g.zone;
      const free = (cu) => placedChips.every((c) => Math.abs(c.v - v) >= 92 || Math.abs(c.u - cu) >= 22);
      const pick = [0, 22, -22, 44, -44].map((d) => u + d).find((cu) => cu >= lo + 12 && cu <= hi - 12 && free(cu));
      if (pick !== undefined) u = pick;
    } else {
      placedChips.forEach((c) => {
        if (Math.abs(c.u - u) < 70 && Math.abs(c.v - v) < 20) v = c.v + (v >= c.v ? 20 : -20);
      });
    }
    placedChips.push({ u, v });
    const [x, y] = toXY(u, v);
    g.chip = { x: num(x), y: num(y) };
  });

  const stubs = stubsOf(defs).map((st) => {
    const b = nodesUV[st.to];
    const ev = portV(b, st.k, st.n);
    const tip = b.u - 7;
    const len = Math.min(26, z.gapU - 10);
    return { ...st, d: path([['M', tip - len, ev], ['L', tip, ev]]), arrow: arrow(tip + 7, ev) };
  });

  const bands = [];
  // the top-to-bottom layout has no room above a node for a band label, so groups show as colour only there
  (tb ? [] : groups).forEach((key) => {
    const mine = defs.map((d, i) => i).filter((i) => pos[i] && defs[i].group === key);
    if (!mine.length) return;
    const lo = Math.min(...mine.map((i) => pos[i].layer));
    const hi = Math.max(...mine.map((i) => pos[i].layer));
    const alone = defs.every((d, i) => !pos[i] || pos[i].layer < lo || pos[i].layer > hi || d.group === key);
    const contiguous = mine.length >= 1 && [...Array(hi - lo + 1).keys()].every((k) => mine.some((i) => pos[i].layer === lo + k));
    if (!alone || !contiguous) return;
    const u0 = z.padU + lo * (z.du + z.gapU) - 8;
    const u1 = z.padU + hi * (z.du + z.gapU) + z.du + 8;
    const [x, y] = toXY(u0, 0);
    bands.push(tb ? { g: key, x: 0, y, w: W, h: u1 - u0 } : { g: key, x, y: 0, w: u1 - u0, h: H });
  });
  return { kind, W, H, nodes, bands, edges: out, stubs, chips: !tb ? kind !== 'compact' : true, layers };
}

/** Placed step indexes in reading (tab) order: layer by layer, top to bottom. */
export function readingOrder(defs, edges) {
  const pos = computeLayout(defs, edges);
  return defs.map((d, i) => i).filter((i) => pos[i])
    .sort((a, b) => pos[a].layer - pos[b].layer || pos[a].row - pos[b].row || a - b);
}

/**
 * Layout for a run with no usable flow description: every step that reported in a plain grid, in the order
 * given, with no arrows. Same result shape as `layoutFor`.
 */
export function simpleLayout(defs, cw, compact) {
  const z = compact ? SIZE.compact : SIZE.lr;
  const cols = Math.max(1, Math.floor((cw + z.gapU) / (z.du + z.gapU)));
  const nodes = defs.map((d, i) => ({
    x: z.padU + (i % cols) * (z.du + z.gapU),
    y: z.padV + Math.floor(i / cols) * (z.dv + z.gapV),
    w: z.du,
    h: z.dv,
  }));
  const rows = Math.max(1, Math.ceil(defs.length / cols));
  return {
    kind: compact ? 'compact' : 'lr',
    W: z.padU * 2 + cols * z.du + (cols - 1) * z.gapU,
    H: z.padV + rows * z.dv + (rows - 1) * z.gapV + 10,
    nodes, bands: [], edges: [], stubs: [], chips: false, layers: cols,
  };
}
