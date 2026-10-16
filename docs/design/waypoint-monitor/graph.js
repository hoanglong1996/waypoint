/* =====================================================================
   Waypoint Monitor — graph.js
   Directed-graph view of one run, drawn from the run's OWN flow
   description. Vanilla JS + inline SVG, no libraries.

   Layout = a small layered (Sugiyama-style) algorithm:
     1. hand-offs come from step inputs (input.from → step); loops are
        already removed by the model (the offending edge is dropped)
     2. layer (column) = longest path from a source; optional `col` hint
     3. edges that skip layers get invisible "dummy" waypoints
     4. order + position inside a layer = average position of the
        producers (barycenter), optional `row` hint, then a 1-D block
        placement that keeps items apart without drifting
   Three orientations / sizes:
     "lr"      left → right, desktop
     "compact" left → right, small nodes, no edge chips (drawer, tablet)
     "tb"      top → bottom (phones, < 600px)
   Runs without a usable flow description use SIMPLE MODE: steps in the
   order they reported, no edges, no bands.

   Public API (used by app.js):
     PMGraph.mount(el, { run, runs, mode: 'run'|'skeleton'|'ghost', model,
                         details: el|null, prefer: 'auto'|'compact', selected: name })
   ===================================================================== */
(function () {
  'use strict';

  var SIZES = {
    lr:      { w: 154, h: 128, main: 88, cross: 34, dummy: 30, label: 22, pad: 8, bandPad: 8 },
    compact: { w: 100, h: 72,  main: 30, cross: 26, dummy: 12, label: 16, pad: 6, bandPad: 6 },
    tb:      { w: 138, h: 124, main: 64, cross: 18, dummy: 22, label: 18, pad: 8, bandPad: 6 }
  };

  /* ------------------------------------------------------------------
     Layout
     ------------------------------------------------------------------ */
  function layout(m, kind, cw, wOverride) {
    var S = {}; for (var k in SIZES[kind]) S[k] = SIZES[kind][k];
    var lr = kind !== 'tb';
    if (!lr) S.w = wOverride || Math.max(120, Math.min(160, Math.floor((cw - 2 * S.pad - S.cross) / 2)));
    var N = m.steps.length, E = m.edges, problems = [];
    var preds = m.steps.map(function () { return []; }), succs = m.steps.map(function () { return []; });
    E.forEach(function (e) { preds[e.to].push(e.from); succs[e.from].push(e.to); });

    /* 1–2. topological order (declaration order breaks ties) → layers */
    var indeg = preds.map(function (p) { return p.length; }), q = [], topo = [];
    for (var i = 0; i < N; i++) if (!indeg[i]) q.push(i);
    while (q.length) { q.sort(function (a, b) { return a - b; }); var u = q.shift(); topo.push(u); succs[u].forEach(function (v) { if (--indeg[v] === 0) q.push(v); }); }
    var col = [];
    topo.forEach(function (u) {
      var c = preds[u].reduce(function (mx, p) { return Math.max(mx, col[p] + 1); }, 0);
      var hint = m.steps[u].def.col;
      if (hint != null) { if (hint >= c) c = hint; else problems.push('Column hint ' + hint + ' for ' + m.steps[u].name + ' was ignored: it would place the step before one of its inputs.'); }
      col[u] = c;
    });
    var nL = N ? Math.max.apply(null, col) + 1 : 0;

    /* 3. items = real nodes + dummy waypoints on long edges */
    var nodeSize = lr ? S.h : S.w;
    var items = [], nodeItem = [];
    m.steps.forEach(function (s, i) { nodeItem[i] = items.push({ t: 'n', i: i, layer: col[i], size: nodeSize, preds: [], ord: i, hint: s.def.row }) - 1; });
    var chains = E.map(function (e) {
      var ch = [], prev = nodeItem[e.from];
      for (var L = col[e.from] + 1; L < col[e.to]; L++) { var id = items.push({ t: 'd', layer: L, size: S.dummy, preds: [prev], ord: e.from + 0.5 }) - 1; ch.push(id); prev = id; }
      items[nodeItem[e.to]].preds.push(prev);
      return ch;
    });

    /* 4. positions along the cross axis, layer by layer */
    var pos = [], unit = nodeSize + S.cross;
    var sep = function (a, b) { return (items[a].size + items[b].size) / 2 + (items[a].t === 'd' || items[b].t === 'd' ? S.cross * 0.6 : S.cross); };
    for (var L = 0; L < nL; L++) {
      var its = []; items.forEach(function (it, id) { if (it.layer === L) its.push(id); });
      var maxWant = null;
      its.forEach(function (id) {
        var it = items[id];
        if (it.t === 'n' && it.hint != null) it.want = it.hint * unit;
        else if (it.preds.length) it.want = it.preds.reduce(function (s, p) { return s + pos[p]; }, 0) / it.preds.length;
        else it.want = null;
        if (it.want != null) maxWant = maxWant == null ? it.want : Math.max(maxWant, it.want);
      });
      its.filter(function (id) { return items[id].want == null; }).sort(function (a, b) { return items[a].ord - items[b].ord; })
        .forEach(function (id, k) { items[id].want = maxWant == null ? k * unit : maxWant + unit * (k + 1); });
      its.sort(function (a, b) { return items[a].want - items[b].want || items[a].ord - items[b].ord; });
      /* block placement: keep wanted positions where possible, push apart where needed */
      var blocks = [];
      its.forEach(function (id) {
        blocks.push({ ids: [id], wants: [items[id].want], pos: [items[id].want] });
        while (blocks.length > 1) {
          var A = blocks[blocks.length - 2], B = blocks[blocks.length - 1];
          if (B.pos[0] - A.pos[A.pos.length - 1] >= sep(A.ids[A.ids.length - 1], B.ids[0])) break;
          var ids = A.ids.concat(B.ids), wants = A.wants.concat(B.wants), rel = [0];
          for (var r = 1; r < ids.length; r++) rel[r] = rel[r - 1] + sep(ids[r - 1], ids[r]);
          var shift = wants.reduce(function (s, w, j) { return s + w - rel[j]; }, 0) / ids.length;
          blocks.splice(-2, 2, { ids: ids, wants: wants, pos: rel.map(function (x) { return x + shift; }) });
        }
      });
      blocks.forEach(function (b) { b.ids.forEach(function (id, j) { pos[id] = b.pos[j]; }); });
    }

    /* normalise: leave room for band labels (lr) / band sides (tb) */
    var lead = lr ? S.label : S.bandPad;
    var minC = Infinity, maxC = -Infinity;
    items.forEach(function (it, id) {
      minC = Math.min(minC, pos[id] - it.size / 2 - (it.t === 'n' ? lead : 0));
      maxC = Math.max(maxC, pos[id] + it.size / 2 + (it.t === 'n' ? S.bandPad : 0));
    });
    if (!isFinite(minC)) { minC = 0; maxC = 0; }
    var off = -minC;
    var mainAt = function (Lx) { return lr ? S.pad + Lx * (S.w + S.main) : S.label + 4 + Lx * (S.h + S.main); };
    var nodes = m.steps.map(function (s, i) {
      var c = pos[nodeItem[i]] + off;
      return lr ? { x: mainAt(col[i]), y: c - S.h / 2 + 0, w: S.w, h: S.h } : { x: S.pad + c - S.w / 2, y: mainAt(col[i]), w: S.w, h: S.h };
    });
    var W = lr ? S.pad * 2 + nL * S.w + Math.max(0, nL - 1) * S.main : S.pad * 2 + (maxC - minC);
    var H = lr ? (maxC - minC) + 4 : mainAt(nL - 1) + S.h + 10;
    var wp = function (id) { var c = pos[id] + off; var Lx = items[id].layer; return lr ? { x: mainAt(Lx) + S.w / 2, y: c } : { x: S.pad + c, y: mainAt(Lx) + S.h / 2 }; };

    /* ports: inputs enter the consumer in the order their edges arrive */
    var incoming = m.steps.map(function () { return []; });
    E.forEach(function (e, ei) {
      var ch = chains[ei], last = ch.length ? wp(ch[ch.length - 1]) : center(nodes[e.from]);
      incoming[e.to].push({ t: 'e', ei: ei, at: lr ? last.y : last.x });
    });
    m.dangling.forEach(function (d, di) { var n = nodes[d.to]; incoming[d.to].push({ t: 'd', di: di, at: (lr ? n.y + n.h / 2 : n.x + n.w / 2) + 0.1 * (di + 1) }); });
    var portOf = { e: {}, d: {} };
    incoming.forEach(function (list, j) {
      list.sort(function (a, b) { return a.at - b.at; });
      var n = nodes[j];
      list.forEach(function (it, r) {
        var f = (r + 1) / (list.length + 1);
        portOf[it.t][it.t === 'e' ? it.ei : it.di] = lr ? { x: n.x, y: n.y + n.h * f } : { x: n.x + n.w * f, y: n.y };
      });
    });
    function center(n) { return { x: n.x + n.w / 2, y: n.y + n.h / 2 }; }

    /* paths: smooth cubic between layers, straight through dummy waypoints */
    function curve(a, b) {
      if (lr) { var dx = (b.x - a.x) / 2; return 'C' + r1(a.x + dx) + ' ' + r1(a.y) + ' ' + r1(b.x - dx) + ' ' + r1(b.y) + ' ' + r1(b.x) + ' ' + r1(b.y); }
      var dy = (b.y - a.y) / 2; return 'C' + r1(a.x) + ' ' + r1(a.y + dy) + ' ' + r1(b.x) + ' ' + r1(b.y - dy) + ' ' + r1(b.x) + ' ' + r1(b.y);
    }
    var edges = E.map(function (e, ei) {
      var a = nodes[e.from], P = portOf.e[ei];
      var start = lr ? { x: a.x + a.w, y: a.y + a.h / 2 } : { x: a.x + a.w / 2, y: a.y + a.h };
      var d = 'M' + r1(start.x) + ' ' + r1(start.y), cur = start, firstEnd = null;
      chains[ei].forEach(function (id) {
        var c = wp(id), inP = lr ? { x: c.x - S.w / 2, y: c.y } : { x: c.x, y: c.y - S.h / 2 }, outP = lr ? { x: c.x + S.w / 2, y: c.y } : { x: c.x, y: c.y + S.h / 2 };
        d += curve(cur, inP) + 'L' + r1(outP.x) + ' ' + r1(outP.y);
        if (!firstEnd) firstEnd = inP;
        cur = outP;
      });
      var tip = lr ? { x: P.x - 7, y: P.y } : { x: P.x, y: P.y - 7 };
      d += curve(cur, tip);
      if (!firstEnd) firstEnd = tip;
      return { e: e, d: d, arrow: arrow(P), chip: { x: (start.x + firstEnd.x) / 2, y: (start.y + firstEnd.y) / 2 } };
    });
    function arrow(P) {
      return lr ? 'M' + r1(P.x - 8) + ' ' + r1(P.y - 4.5) + 'L' + r1(P.x) + ' ' + r1(P.y) + 'L' + r1(P.x - 8) + ' ' + r1(P.y + 4.5) + 'Z'
                : 'M' + r1(P.x - 4.5) + ' ' + r1(P.y - 8) + 'L' + r1(P.x) + ' ' + r1(P.y) + 'L' + r1(P.x + 4.5) + ' ' + r1(P.y - 8) + 'Z';
    }
    /* dangling inputs: a short dashed stub, never a full arrow */
    var stubs = m.dangling.map(function (dg, di) {
      var P = portOf.d[di], len = lr ? 34 : 28;
      var s0 = lr ? { x: P.x - len, y: P.y } : { x: P.x, y: P.y - len }, s1 = lr ? { x: P.x - 7, y: P.y } : { x: P.x, y: P.y - 7 };
      return { dg: dg, d: 'M' + r1(s0.x) + ' ' + r1(s0.y) + 'L' + r1(s1.x) + ' ' + r1(s1.y), arrow: arrow(P) };
    });

    /* group bands = bounding box of each group's nodes */
    var bands = [];
    m.groups.forEach(function (g) {
      var ns = nodes.filter(function (n, i) { return m.steps[i].group === g.id; });
      if (!ns.length) return;
      var x0 = Math.min.apply(null, ns.map(function (n) { return n.x; })) - S.bandPad, y0 = Math.min.apply(null, ns.map(function (n) { return n.y; })) - S.label;
      var x1 = Math.max.apply(null, ns.map(function (n) { return n.x + n.w; })) + S.bandPad, y1 = Math.max.apply(null, ns.map(function (n) { return n.y + n.h; })) + S.bandPad;
      bands.push({ g: g, x: x0, y: y0, w: x1 - x0, h: y1 - y0 });
    });
    if (bands.length) {
      /* bands may need a little room past the node box */
      var bx0 = Math.min.apply(null, bands.map(function (b) { return b.x; })), by0 = Math.min.apply(null, bands.map(function (b) { return b.y; }));
      var sx = bx0 < 0 ? -bx0 : 0, sy = by0 < 0 ? -by0 : 0;
      if (sx || sy) {
        nodes.forEach(function (n) { n.x += sx; n.y += sy; });
        bands.forEach(function (b) { b.x += sx; b.y += sy; });
        var tr = function (dstr) { return dstr.replace(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g, function (_, a, b) { return r1(+a + sx) + ' ' + r1(+b + sy); }); };
        edges.forEach(function (g) { g.d = tr(g.d); g.arrow = tr(g.arrow); g.chip.x += sx; g.chip.y += sy; });
        stubs.forEach(function (st) { st.d = tr(st.d); st.arrow = tr(st.arrow); });
        W += sx; H += sy;
      }
      W = Math.max(W, Math.max.apply(null, bands.map(function (b) { return b.x + b.w; })) + 2);
      H = Math.max(H, Math.max.apply(null, bands.map(function (b) { return b.y + b.h; })) + 2);
    }
    return { kind: kind, lr: lr, W: Math.ceil(W), H: Math.ceil(H), S: S, nodes: nodes, edges: edges, stubs: stubs, bands: bands, chips: kind !== 'compact', problems: problems };
  }
  function r1(v) { return Math.round(v * 10) / 10; }

  /* Pick a layout from the available width. */
  function pick(m, cw, prefer) {
    if (cw >= 600) {
      if (prefer !== 'compact') { var L = layout(m, 'lr', cw), s = cw / L.W; if (s >= 0.77) return { L: L, scale: Math.min(1, s) }; }
      var C = layout(m, 'compact', cw), sc = cw / C.W; if (sc >= 0.8) return { L: C, scale: Math.min(1.35, sc) };
    }
    var T = layout(m, 'tb', cw);
    /* phones: narrow the nodes first (down to 104px) so text stays full size; scale only as a last resort */
    if (T.W > cw) T = layout(m, 'tb', cw, Math.max(104, T.S.w - Math.ceil((T.W - cw) / 2) - 1));
    return { L: T, scale: Math.min(1, cw / T.W) };
  }

  /* ------------------------------------------------------------------
     State helpers
     ------------------------------------------------------------------ */
  function valueIn(s, input) { var v; s.inputs.forEach(function (x) { if (x.name === input) v = x.value; }); return v; }
  function edgeInfo(m, e) {
    var a = m.steps[e.from], b = m.steps[e.to], v = valueIn(b, e.input);
    var live = { running: 1, waiting: 1 };
    if (live[a.state] || live[b.state]) return { state: 'pending', value: v === undefined ? null : v };
    if (!a.rec || !b.rec || v === undefined) return { state: 'inactive', value: null };
    return { state: v === 0 ? 'empty' : 'ok', value: v };
  }

  /* ------------------------------------------------------------------
     Rendering
     ------------------------------------------------------------------ */
  function nameWbr(n) { return PM.esc(n).replace(/_/g, '_<wbr>'); }
  function stateIcon(st) { return PM.STATE[st] ? PM.STATE[st].icon : ''; }

  function nodeHTML(s, style, mode, m, L, order) {
    var P = PM, esc = P.esc;
    if (mode === 'skeleton') return '<div class="gnode gnode--skel" style="' + style + '"><span class="skel" style="width:60%;height:12px"></span><span class="skel" style="width:85%;height:10px"></span><span class="skel" style="width:40%;height:20px;margin-top:auto"></span></div>';
    var st = mode === 'ghost' ? 'ghost' : s.state, r = s.rec, aff = mode === 'run' && m.affected[s.name] && st === 'ok';
    var count, foot2 = '';
    if (mode === 'ghost' || st === 'stopped' || st === 'unreached') count = '<span class="gnode__count gnode__count--na">—</span>';
    else if (st === 'waiting') { count = '<span class="gnode__count gnode__count--na">—</span>'; foot2 = '<span class="gnode__time">Not started</span>'; }
    else if (st === 'running' || st === 'stalled') { count = P.elapsedHTML(r.startedAt, 'gnode__count gnode__count--' + st); foot2 = '<span class="gnode__time">' + (st === 'running' ? 'running' : 'stalled') + '</span>'; }
    else if (r.output == null) count = '<span class="gnode__count gnode__count--na">n/a <small>· returns nothing</small></span>';
    else count = '<span class="gnode__count num">' + P.fmt(r.output) + '</span>';
    if (!foot2 && mode === 'run' && r && r.finishedAt) foot2 = '<span class="gnode__time num">' + P.hhmmss(r.finishedAt) + '</span>';
    var both = s.label !== s.name ? s.label + ' (' + s.name + ')' : s.name;
    var aria = both + (s.groupTitle ? ', group ' + s.groupTitle : '') + '. ' +
      (mode === 'ghost' ? 'No data.' : 'State: ' + P.STATE[st].long + '. ' + (r && r.state === 'done' ? 'Output ' + (r.output == null ? 'n/a' : P.fmt(r.output)) + '.' : '')) +
      (aff ? ' Downstream of a data-loss step.' : '');
    return '<button type="button" class="gnode gnode--' + st + (aff ? ' is-affected' : '') + (order ? ' gnode--simple' : '') + '" data-name="' + esc(s.name) + '" style="' + style + '" aria-label="' + esc(aria) + '"' + (mode !== 'run' ? ' tabindex="-1"' : '') + '>' +
      (order ? '<span class="gnode__order num" aria-hidden="true">' + order + '</span>' : '') +
      '<span class="gnode__head">' +
        (mode === 'run' ? '<span class="gpill gpill--' + st + '">' + stateIcon(st) + '<span class="gpill__txt">' + P.STATE[st].txt + '</span></span>' : '') +
        (aff ? '<span class="gpill gpill--affected" title="Downstream of a data-loss step">' + P.I.down + '<span class="gpill__txt">affected</span></span>' : '') +
      '</span>' +
      '<span class="gnode__label">' + (s.slot != null ? '<i class="gdot g-' + s.slot + '" aria-hidden="true"></i>' : '') + esc(s.label) + '</span>' +
      (s.label !== s.name ? '<span class="gnode__name">' + nameWbr(s.name) + '</span>' : '') +
      '<span class="gnode__foot">' + count + (L && L.kind === 'compact' ? '' : foot2) + '</span>' +
    '</button>';
  }

  function build(el, o) {
    var P = PM, esc = P.esc, mode = o.mode || 'run';
    var m = o.model || P.model(o.run);
    var cs = getComputedStyle(el);
    var cw = (el.clientWidth || 1100) - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    var body;

    if (m.simple) {
      /* SIMPLE MODE: no flow description → steps in the order they reported, no edges, no bands */
      body = P.simpleNotice(m.run) +
        '<div class="graph-head"><p class="graph-head__flow">' + P.I.list + '<span>Steps in the order they reported. Hand-offs are unknown, so no arrows are drawn.</span></p>' +
        '<p class="graph-head__sum">' + summaryText(m) + '</p></div>' +
        '<div class="graph-simple" role="group" aria-label="Steps in report order">' +
          m.steps.map(function (s, k) { return nodeHTML(s, '', mode, m, null, k + 1); }).join('') + '</div>' +
        legendHTML(m, null) + problemsHTML(m, []);
      el.innerHTML = body;
      if (mode === 'run') wire(el, o, m, null);
      return;
    }

    var pk = pick(m, cw, o.prefer), L = pk.L, sc = pk.scale;
    var maxV = 1;
    if (mode === 'run') L.edges.forEach(function (g) { var v = edgeInfo(m, g.e).value; if (v > maxV) maxV = v; });

    var svg = '<svg class="graph__svg" width="' + L.W + '" height="' + L.H + '" viewBox="0 0 ' + L.W + ' ' + L.H + '" aria-hidden="true">';
    L.bands.forEach(function (b) { svg += '<rect class="gband g-' + b.g.slot + '" x="' + r1(b.x) + '" y="' + r1(b.y) + '" width="' + r1(b.w) + '" height="' + r1(b.h) + '" rx="12"/>'; });
    L.edges.forEach(function (g, j) {
      var info = mode === 'run' ? edgeInfo(m, g.e) : { state: mode === 'skeleton' ? 'ghost' : 'ghost', value: null };
      var wd = info.state === 'ok' ? (1.25 + 2.75 * Math.log10(info.value + 1) / Math.log10(maxV + 1)) : 1.5;
      svg += '<g class="gedge gedge--' + info.state + '" data-edge="' + j + '">' +
        '<path class="gedge__hit" d="' + g.d + '"/>' +
        '<path class="gedge__line" d="' + g.d + '" style="stroke-width:' + wd.toFixed(2) + 'px"/>' +
        (info.state === 'ok' ? '<path class="gedge__flow" d="' + g.d + '"/>' : '') +
        '<path class="gedge__arrow" d="' + g.arrow + '"/></g>';
    });
    L.stubs.forEach(function (st, k) {
      svg += '<g class="gedge gedge--dangling" data-stub="' + k + '"><path class="gedge__hit" d="' + st.d + '"/><path class="gedge__line" d="' + st.d + '"/><path class="gedge__arrow" d="' + st.arrow + '"/></g>';
    });
    svg += '</svg>';

    var labels = L.bands.map(function (b) {
      return '<span class="gband-label g-' + b.g.slot + '" style="left:' + r1(b.x + 10) + 'px;top:' + r1(b.y + 4) + 'px;max-width:' + r1(b.w - 16) + 'px">' + esc(b.g.title) + '</span>';
    }).join('');

    /* edge chips with simple collision avoidance */
    var chips = '';
    if (L.chips && mode === 'run') {
      var cl = L.edges.map(function (g, j) {
        var info = edgeInfo(m, g.e), val = info.state === 'inactive' ? '—' : info.value == null ? '…' : P.fmt(info.value);
        var stack = L.kind === 'lr';
        var w = stack ? Math.min(80, Math.max(g.e.input.length * 6, val.length * 7.5) + 12) : (g.e.input.length + val.length + 3) * 6.2 + 14;
        return { j: j, x: g.chip.x, y: g.chip.y, w: w, h: stack ? 32 : 20, info: info, val: val, input: g.e.input, stack: stack };
      });
      for (var pass = 0; pass < 3; pass++) {
        cl.sort(function (a, b) { return a.y - b.y; });
        for (var a = 0; a < cl.length; a++) for (var b = a + 1; b < cl.length; b++) {
          var A = cl[a], B = cl[b];
          if (Math.abs(A.x - B.x) < (A.w + B.w) / 2 + 2 && Math.abs(A.y - B.y) < (A.h + B.h) / 2 + 2) {
            var need = (A.h + B.h) / 2 + 2 - Math.abs(A.y - B.y);
            A.y -= need / 2; B.y += need / 2;
          }
        }
      }
      chips = cl.map(function (c) {
        return '<span class="gchip gchip--' + c.info.state + (c.stack ? ' gchip--stack' : '') + '" data-edge="' + c.j + '" style="left:' + r1(c.x) + 'px;top:' + r1(c.y) + 'px">' +
          '<span class="gchip__name">' + esc(c.input) + '</span><span class="gchip__sep" aria-hidden="true">&nbsp;·&nbsp;</span><b class="num">' + c.val + '</b></span>';
      }).join('');
    }

    /* nodes as real buttons, in reading order (layer, then position) */
    var orderIdx = m.steps.map(function (s, i) { return i; }).sort(function (a, b) {
      var na = L.nodes[a], nb = L.nodes[b];
      return L.lr ? (na.x - nb.x || na.y - nb.y) : (na.y - nb.y || na.x - nb.x);
    });
    var nodesHTML = orderIdx.map(function (i) {
      var n = L.nodes[i];
      return nodeHTML(m.steps[i], 'left:' + r1(n.x) + 'px;top:' + r1(n.y) + 'px;width:' + n.w + 'px;height:' + n.h + 'px', mode, m, L);
    }).join('');

    var dirText = L.lr ? 'left to right' : 'top to bottom';
    body =
      '<div class="graph-head"><p class="graph-head__flow">' + P.I.flow + '<span>Data flows <b>' + dirText + '</b>. An arrow <span class="mono">A → B</span> means A’s output is B’s input.</span></p>' +
        (mode === 'run' ? '<p class="graph-head__sum">' + summaryText(m) + '</p>' : '') + '</div>' +
      '<div class="graph-stage" style="height:' + Math.ceil(L.H * sc) + 'px">' +
        '<div class="graph graph--' + L.kind + (L.kind === 'tb' && L.S.w < 130 ? ' graph--narrow' : '') + '" style="width:' + L.W + 'px;height:' + L.H + 'px;transform:scale(' + sc.toFixed(4) + ')" role="group" aria-label="Pipeline graph, ' + dirText + '">' +
          svg + labels + chips + nodesHTML +
        '</div>' +
        (mode === 'ghost' ? '<div class="graph-ghost-msg">' + (o.ghostMsg || '') + '</div>' : '') +
      '</div>' +
      (mode === 'run' ? otherHTML(m) + legendHTML(m, L) + problemsHTML(m, L.problems) : '');
    el.innerHTML = body;
    if (mode === 'run') wire(el, o, m, L);
  }

  function summaryText(m) {
    var P = PM, I = P.I, reported = m.run.records.length;
    var total = m.simple ? reported : m.steps.length + m.other.length;
    var parts = ['<span>' + reported + ' of ' + total + ' steps reported</span>'];
    var find = function (st) { for (var i = 0; i < m.all.length; i++) if (m.all[i].state === st) return m.all[i]; return null; };
    var run = find('running'), stl = find('stalled'), stop = find('stopped'), loss = find('loss');
    if (run) parts.push('<span class="t-run">' + I.spin + 'running <span class="mono">' + P.esc(run.name) + '</span></span>');
    if (stl) parts.push('<span class="t-warn">' + I.alert + 'stalled at <span class="mono">' + P.esc(stl.name) + '</span></span>');
    if (stop) parts.push('<span class="t-warn">' + I.gap + 'stopped at <span class="mono">' + P.esc(stop.name) + '</span></span>');
    if (loss) parts.push('<span class="t-bad">' + I.octagon + 'data loss at <span class="mono">' + P.esc(loss.name) + '</span></span>');
    return parts.join('');
  }

  /* Steps reported but not in the run's flow description */
  function otherHTML(m) {
    if (!m.other.length) return '';
    return '<div class="graph-other"><span class="eyebrow">Other steps</span><span class="graph-other__note">not in this run’s flow</span>' +
      m.other.map(function (s) {
        return '<button type="button" class="chip chip--btn graph-other__chip" data-other="' + PM.esc(s.name) + '" aria-pressed="false">' +
          '<span class="graph-other__ico gpill--' + s.state + '">' + stateIcon(s.state) + '</span>' + PM.esc(s.label) + (s.label !== s.name ? ' <span class="mono faint">' + PM.esc(s.name) + '</span>' : '') + '</button>';
      }).join('') + '</div>';
  }

  function problemsHTML(m, extra) {
    var list = m.problems.concat(extra || []);
    if (!list.length) return '';
    return '<details class="graph-problems"><summary>' + PM.I.alert + 'Problems in this run’s description (' + list.length + ')</summary><ul>' +
      list.map(function (p) { return '<li>' + PM.esc(p) + '</li>'; }).join('') + '</ul></details>';
  }

  function legendHTML(m, L) {
    var I = PM.I, S = PM.STATE;
    var pill = function (st, txt) { return '<span class="gpill gpill--' + st + '">' + S[st].icon + '<span class="gpill__txt">' + (txt || S[st].txt) + '</span></span>'; };
    var ln = function (cls) { return '<svg class="lg-edge" viewBox="0 0 28 10" aria-hidden="true"><path class="' + cls + '" d="M1 5H20"/><path class="' + cls + '-arrow" d="M20 1.5L27 5L20 8.5Z"/></svg>'; };
    var html = '<div class="graph-legend" aria-label="Legend">' +
      '<div class="graph-legend__group"><span class="eyebrow">Steps</span>' + pill('ok') + pill('loss') + pill('stopped') + pill('unreached') +
        '<span class="gpill gpill--affected">' + I.down + '<span class="gpill__txt">Downstream of a loss</span></span></div>' +
      '<div class="graph-legend__group"><span class="eyebrow">Live</span>' + pill('running') + pill('waiting') + pill('stalled') + '</div>';
    if (L) {
      html += '<div class="graph-legend__group"><span class="eyebrow">Arrows</span>' +
        '<span class="lg-item">' + ln('lg-ok') + 'items flow · thicker = more</span>' +
        '<span class="lg-item">' + ln('lg-empty') + '0 items</span>' +
        '<span class="lg-item">' + ln('lg-pending') + 'pending</span>' +
        '<span class="lg-item">' + ln('lg-inactive') + 'not reached</span>' +
        '<span class="lg-item"><svg class="lg-edge" viewBox="0 0 28 10" aria-hidden="true"><path class="lg-dangling" d="M8 5H20"/><path class="lg-dangling-arrow" d="M20 1.5L27 5L20 8.5Z"/></svg>from a step outside the flow</span></div>';
      if (m.groups.length) html += '<div class="graph-legend__group"><span class="eyebrow">Groups</span>' +
        m.groups.map(function (g) { return '<span class="lg-item"><i class="gdot g-' + g.slot + '"></i>' + PM.esc(g.title) + '</span>'; }).join('') + '</div>';
    }
    if (L && L.kind === 'compact') html += '<p class="graph-legend__hint">Hover or focus a step to see its counts and arrows.</p>';
    return html + '</div>';
  }

  /* ------------------------------------------------------------------
     Interaction: hover tooltips, select + neighbours, Esc / empty click
     ------------------------------------------------------------------ */
  function wire(el, o, m, L) {
    var P = PM, esc = P.esc, run = m.run, graph = el.querySelector('.graph') || el.querySelector('.graph-simple'), tip = document.getElementById('tooltip');
    var E = m.edges;

    function showTip(html, target) {
      tip.innerHTML = html; tip.hidden = false;
      var r = target.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.min(window.innerWidth - tw - 8, Math.max(8, r.left + r.width / 2 - tw / 2));
      var top = r.top - th - 10; if (top < 64) top = r.bottom + 10;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
    function hideTip() { tip.hidden = true; }

    function nodeTip(name) {
      var s = m.byName[name], r = s.rec;
      var ins = s.inputs.length ? s.inputs.map(function (inp) {
        var v = inp.value === undefined ? '—' : P.fmt(inp.value);
        var from = inp.from ? '<span class="faint">from ' + esc(inp.from) + (inp.fromInFlow ? '' : ' (not in this flow)') + '</span>' : '';
        return '<div>in: <b>' + esc(inp.name) + '</b> ' + v + ' ' + from + '</div>';
      }).join('') : '<div>in: none <span class="faint">(source step)</span></div>';
      var out = !r || r.state !== 'done' ? '—' : r.output == null ? 'n/a (returns nothing)' : P.fmt(r.output);
      var when = !r ? P.STATE[s.state].long
        : r.state === 'done' ? 'finished ' + P.hhmmss(r.finishedAt) + ' · ' + P.STATE[s.state].long
        : P.STATE[s.state].long + ' · started ' + P.hhmmss(r.startedAt) + ' · ' + P.elapsedHTML(r.startedAt);
      return '<div class="tooltip__date"><b>' + esc(s.label) + '</b>' + (s.label !== s.name ? ' · <span class="mono">' + esc(s.name) + '</span>' : '') + (s.groupTitle ? ' · ' + esc(s.groupTitle) : '') + '</div>' +
        '<div class="tooltip__rows">' + ins + '<div>out: <b>' + out + '</b></div><div class="faint">' + when + '</div>' +
        (s.notInFlow ? '<div class="faint">not in this run’s flow</div>' : '') + '</div>';
    }
    function edgeTip(j) {
      var e = E[j], info = edgeInfo(m, e);
      var v = info.state === 'inactive' ? 'not recorded' : info.value == null ? 'not yet known' : P.fmt(info.value);
      return '<div class="tooltip__date"><span class="mono">' + esc(m.steps[e.from].name) + '</span> → <span class="mono">' + esc(m.steps[e.to].name) + '</span></div>' +
        '<div class="tooltip__val">' + esc(e.input) + ' · ' + v + '</div>' +
        (info.state === 'empty' ? '<div style="color:var(--bad)">0 items reached the next step</div>'
          : info.state === 'inactive' ? '<div class="faint">this hand-off did not happen</div>'
          : info.state === 'pending' ? '<div class="faint">pending: a step on this arrow is running or waiting</div>' : '');
    }
    function stubTip(k) {
      var d = m.dangling[k];
      return '<div class="tooltip__date"><span class="mono">' + esc(d.from) + '</span> → <span class="mono">' + esc(m.steps[d.to].name) + '</span></div>' +
        '<div class="tooltip__val">' + esc(d.input) + '</div><div class="faint">from ' + esc(d.from) + ' (not in this flow)</div>';
    }

    graph.addEventListener('pointerover', function (ev) {
      var n = ev.target.closest('.gnode'), c = ev.target.closest('.gchip, .gedge');
      if (n) showTip(nodeTip(n.dataset.name), n);
      else if (c && c.dataset.stub != null) showTip(stubTip(+c.dataset.stub), ev.target);
      else if (c && c.dataset.edge != null) showTip(edgeTip(+c.dataset.edge), c.classList.contains('gedge') ? ev.target : c);
    });
    graph.addEventListener('pointerout', function (ev) { if (!ev.relatedTarget || !graph.contains(ev.relatedTarget) || !ev.relatedTarget.closest('.gnode, .gchip, .gedge')) hideTip(); });
    graph.addEventListener('focusin', function (ev) { var n = ev.target.closest('.gnode'); if (n) showTip(nodeTip(n.dataset.name), n); });
    graph.addEventListener('focusout', hideTip);

    function select(name) {
      o.selected = name;
      var i = -1; m.steps.forEach(function (s, k) { if (s.name === name) i = k; });
      var inGraph = i >= 0 && L;
      var up = {}, down = {};
      if (inGraph) E.forEach(function (e) { if (e.to === i) up[e.from] = 1; if (e.from === i) down[e.to] = 1; });
      graph.classList.toggle('is-selecting', !!inGraph);
      graph.querySelectorAll('.gnode').forEach(function (n) {
        var k = -1; m.steps.forEach(function (s, x) { if (s.name === n.dataset.name) k = x; });
        n.classList.toggle('is-selected', n.dataset.name === name);
        n.classList.toggle('is-hl', !!(inGraph && (k === i || up[k] || down[k])));
        n.setAttribute('aria-pressed', String(n.dataset.name === name));
      });
      graph.querySelectorAll('.gedge, .gchip').forEach(function (g) {
        if (g.dataset.edge == null) { g.classList.toggle('is-hl', !!(inGraph && m.dangling[+g.dataset.stub] && m.dangling[+g.dataset.stub].to === i)); return; }
        var e = E[+g.dataset.edge];
        g.classList.toggle('is-hl', !!(inGraph && (e.from === i || e.to === i)));
      });
      el.querySelectorAll('[data-other]').forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.other === name)); c.classList.toggle('is-selected', c.dataset.other === name); });
      if (o.details) renderDetails(name, up, down);
    }
    function renderDetails(name, up, down) {
      if (name == null) { o.details.innerHTML = ''; o.details.hidden = true; return; }
      var s = m.byName[name];
      var link = function (k) { return '<button type="button" class="chip chip--btn" data-goto="' + esc(m.steps[k].name) + '">' + P.I.arrowIn + '<span class="mono">' + esc(m.steps[k].name) + '</span></button>'; };
      var ups = Object.keys(up).map(Number), downs = Object.keys(down).map(Number);
      var outside = s.inputs.filter(function (x) { return x.from && !x.fromInFlow; }).map(function (x) {
        return '<span class="chip chip--dangling" title="from ' + esc(x.from) + ' (not in this flow)">' + P.I.arrowIn + '<span class="mono">' + esc(x.from) + '</span>&nbsp;(not in this flow)</span>';
      }).join('');
      var rel = m.simple ? '<span class="faint">Hand-offs are unknown for this run.</span>'
        : s.notInFlow ? '<span class="faint">Not in this run’s flow, so its hand-offs are unknown.</span>'
        : '<span class="faint">Upstream</span>' + (ups.length || outside ? ups.map(link).join('') + outside : '<span class="chip chip--none">none (source)</span>') +
          '<span class="faint">Downstream</span>' + (downs.length ? downs.map(link).join('') : '<span class="chip chip--none">none (sink)</span>');
      o.details.hidden = false;
      o.details.innerHTML =
        '<div class="graph-details__head"><div><p class="eyebrow">Selected step</p><h3 class="graph-details__title">' + esc(s.label) + (s.label !== s.name ? ' <span class="mono faint">' + esc(s.name) + '</span>' : '') + '</h3></div>' +
        '<button type="button" class="icon-btn" data-clear aria-label="Clear selection"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>' +
        '<div class="graph-details__rel">' + rel + '</div>' +
        '<ol class="steps' + (o.prefer === 'compact' ? ' steps--compact' : '') + '">' + P.stepItemHTML(run, o.runs, name, o.prefer === 'compact') + '</ol>';
    }
    function focusName(name) {
      var b = el.querySelector('.gnode[data-name="' + CSS.escape(name) + '"]') || el.querySelector('[data-other="' + CSS.escape(name) + '"]');
      if (b) b.focus();
    }

    graph.addEventListener('click', function (ev) {
      var n = ev.target.closest('.gnode');
      if (n) select(o.selected === n.dataset.name ? null : n.dataset.name);
      else select(null);                                   // empty-space click clears
    });
    var oth = el.querySelector('.graph-other');
    if (oth) oth.addEventListener('click', function (ev) {
      var c = ev.target.closest('[data-other]'); if (!c) return;
      select(o.selected === c.dataset.other ? null : c.dataset.other);
    });
    if (o.details) o.details.onclick = function (ev) {
      if (ev.target.closest('[data-clear]')) { var k = o.selected; select(null); if (k) focusName(k); }
      var g = ev.target.closest('[data-goto]');
      if (g) { select(g.dataset.goto); focusName(g.dataset.goto); }
    };
    el._pmClear = function () { if (o.selected == null) return false; var k = o.selected; select(null); focusName(k); return true; };
    if (o.selected != null && m.byName[o.selected]) select(o.selected);
  }

  /* Esc clears the selection before anything else (e.g. before closing the drawer) */
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var mounted = Array.prototype.slice.call(document.querySelectorAll('[data-graph-mount]')).reverse();
    for (var k = 0; k < mounted.length; k++) {
      if (mounted[k].offsetParent !== null && mounted[k]._pmClear && mounted[k]._pmClear()) { ev.stopImmediatePropagation(); ev.preventDefault(); return; }
    }
  }, true);

  /* Re-layout on resize (debounced); keeps selection */
  var rt;
  window.addEventListener('resize', function () {
    clearTimeout(rt);
    rt = setTimeout(function () {
      document.querySelectorAll('[data-graph-mount]').forEach(function (el) { if (el._pmOpts && el.offsetParent !== null) build(el, el._pmOpts); });
    }, 120);
  });

  window.PMGraph = {
    mount: function (el, o) { el.setAttribute('data-graph-mount', ''); el._pmOpts = o; build(el, o); },
    refresh: function (el) { if (el && el._pmOpts) build(el, el._pmOpts); },
    layout: layout          /* exposed for tests */
  };
})();
