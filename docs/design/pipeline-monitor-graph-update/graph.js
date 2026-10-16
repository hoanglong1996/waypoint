/* =====================================================================
   Pipeline Monitor — graph.js
   Directed-graph view of one run. Vanilla JS + inline SVG, no libraries.

   The graph shape is FIXED (9 steps, 9 edges), so node positions are a
   hand-tuned layered layout, not an auto-layout engine. Three layouts:
     - "lr"      left → right, desktop (design width 1138px, scaled 0.77–1)
     - "compact" left → right, small nodes, no edge chips (drawer, tablet)
     - "tb"      top → bottom, 2 lanes (phones, < 600px container)

   Public API (used by app.js):
     PMGraph.mount(el, { run, runs, mode: 'run'|'skeleton'|'ghost', details: el|null,
                         prefer: 'auto'|'compact' })
   app.js exposes the shared helpers on window.PM (STEPS, icons, fmt …).
   ===================================================================== */
(function () {
  'use strict';

  var LABEL = ['Accounts', 'Calls', 'Partners', 'Instances', 'Campaigns', 'Click views', 'Merged calls', 'Record stats', 'Save stats'];
  var GROUP = ['callrail', 'callrail', 'gads', 'gads', 'gads', 'gads', 'merge', 'persist', 'persist'];
  var GROUP_NAME = { callrail: 'CallRail', gads: 'Google Ads', merge: 'Merge', persist: 'Persist' };
  /* Tab / reading order: column by column, top to bottom */
  var ORDER = [0, 2, 1, 3, 4, 5, 6, 7, 8];

  /* Edges come straight from the step definitions: consumer.inputs = [[inputName, producerIndex]] */
  function edgeList() {
    var out = [];
    PM.STEPS.forEach(function (s, to) {
      s.inputs.forEach(function (p, k) { out.push({ from: p[1], to: to, input: p[0], k: k, n: s.inputs.length }); });
    });
    return out;
  }

  /* ------------------------------------------------------------------
     Layouts. Each returns { kind, W, H, nodes[i]{x,y,w,h}, bands[], edges[] }
     edges[]: { e, d (svg path), arrow (svg path), chip {x,y,align} }
     ------------------------------------------------------------------ */
  var COLS = [0, 1, 0, 1, 2, 2, 3, 4, 4];
  var ROWS = [0, 0, 1.5, 1.5, 1, 2, 1, 0.5, 1.5];

  function layoutLR(compact) {
    var w = compact ? 100 : 154, h = compact ? 72 : 128, gap = compact ? 28 : 88;
    var top = compact ? 22 : 28, rs = h + (compact ? 20 : 28), pad = 8;
    var nodes = COLS.map(function (c, i) { return { x: pad + c * (w + gap), y: top + ROWS[i] * rs, w: w, h: h }; });
    var W = pad * 2 + 5 * w + 4 * gap, H = top + 2 * rs + h + 10;
    var bx = function (c) { return pad + c * (w + gap) - 8; };
    var split = top + h + 14;
    var bands = [
      { g: 'callrail', x: bx(0), y: 0, w: 2 * w + gap + 16, h: split - 6 },
      { g: 'gads', x: bx(0), y: split, w: 3 * w + 2 * gap + 16, h: H - split },
      { g: 'merge', x: bx(3), y: 0, w: w + 16, h: H },
      { g: 'persist', x: bx(4), y: 0, w: w + 16, h: H }
    ];
    var edges = edgeList().map(function (e) {
      var a = nodes[e.from], b = nodes[e.to];
      var sx = a.x + a.w, sy = a.y + a.h / 2, ex = b.x, ey = b.y + b.h * (e.k + 1) / (e.n + 1);
      var tip = ex - 7, d, chip;
      if (COLS[e.to] - COLS[e.from] > 1) {
        /* Skip edge (calls → merge): run straight through the empty row, bend only in the last gap */
        var tx = b.x - gap, c = gap * 0.55;
        d = 'M' + sx + ' ' + sy + 'L' + tx + ' ' + sy + 'C' + (tx + c) + ' ' + sy + ' ' + (tip - c) + ' ' + ey + ' ' + tip + ' ' + ey;
        chip = { x: (sx + tx) / 2, y: sy };
      } else {
        var c2 = (tip - sx) / 2;
        d = 'M' + sx + ' ' + sy + 'C' + (sx + c2) + ' ' + sy + ' ' + (tip - c2) + ' ' + ey + ' ' + tip + ' ' + ey;
        chip = { x: (sx + tip) / 2, y: (sy + ey) / 2 };
      }
      return { e: e, d: d, chip: chip, arrow: 'M' + (ex - 8) + ' ' + (ey - 4.5) + 'L' + ex + ' ' + ey + 'L' + (ex - 8) + ' ' + (ey + 4.5) + 'Z' };
    });
    return { kind: compact ? 'compact' : 'lr', W: W, H: H, nodes: nodes, bands: bands, edges: edges, chips: !compact };
  }

  function layoutTB(cw) {
    var gt = 22, lg = 12, w = Math.floor((cw - gt - lg) / 2), h = 124, mh = 96, rg = 64, top = 4;
    var A = gt, B = gt + w + lg;
    var lane = [A, A, B, B, A, B, A, A, B], layer = [0, 1, 0, 1, 2, 2, 3, 4, 4];
    var ys = [], y = top;
    [h, h, h, mh, h].forEach(function (hh, L) { ys[L] = y; y += hh + rg; });
    var nodes = lane.map(function (x, i) {
      return i === 6 ? { x: A, y: ys[3], w: B + w - A, h: mh } : { x: x, y: ys[layer[i]], w: w, h: h };
    });
    var W = cw, H = ys[4] + h + 6;
    var cx = function (n) { return n.x + n.w / 2; };
    var mergeIn = [A + 18, A + w / 2, B + w / 2];          // calls, campaigns, clickview ports on merge's top edge
    var edges = edgeList().map(function (e) {
      var a = nodes[e.from], b = nodes[e.to];
      var ex = e.to === 6 ? mergeIn[e.k] : cx(b), ey = b.y, tip = ey - 7, d, chip;
      var sx = e.from === 6 ? cx(b) : cx(a), sy = a.y + a.h;
      var gapMid = function (L) { return ys[L] - rg / 2; };
      if (e.from === 1 && e.to === 6) {
        /* calls → merge: leave Calls on its left side and run down the gutter, past Campaigns */
        var gx = 9, sy2 = a.y + a.h / 2;
        d = 'M' + a.x + ' ' + sy2 + 'C' + gx + ' ' + sy2 + ' ' + gx + ' ' + sy2 + ' ' + gx + ' ' + (sy2 + 16) +
            'L' + gx + ' ' + (ey - 34) + 'C' + gx + ' ' + (ey - 12) + ' ' + ex + ' ' + (tip - 16) + ' ' + ex + ' ' + tip;
        chip = { x: 2, y: gapMid(2) - 12, align: 'start' };
      } else {
        var c = (tip - sy) / 2;
        d = 'M' + sx + ' ' + sy + 'C' + sx + ' ' + (sy + c) + ' ' + ex + ' ' + (tip - c) + ' ' + ex + ' ' + tip;
        chip = { x: (sx + ex) / 2, y: (sy + tip) / 2 };
        if (e.from === 3 && e.to === 4) chip.y = gapMid(2) - 12;     // two chips share the gap above row 3:
        if (e.from === 3 && e.to === 5) chip.y = gapMid(2) + 12;     // stagger them vertically
      }
      return { e: e, d: d, chip: chip, arrow: 'M' + (ex - 4.5) + ' ' + (ey - 8) + 'L' + ex + ' ' + ey + 'L' + (ex + 4.5) + ' ' + (ey - 8) + 'Z' };
    });
    return { kind: 'tb', W: W, H: H, nodes: nodes, bands: [], edges: edges, chips: true };
  }

  /* Pick a layout from the container width. */
  function pickLayout(cw, prefer) {
    if (cw < 600) return { L: layoutTB(Math.max(300, cw)), scale: 1 };
    if (prefer !== 'compact' && cw >= 880) { var L = layoutLR(false); return { L: L, scale: Math.min(1, cw / L.W) }; }
    var C = layoutLR(true); return { L: C, scale: Math.min(1.35, cw / C.W) };
  }

  /* ------------------------------------------------------------------
     State per node / edge
     ------------------------------------------------------------------ */
  function nodeStates(run) {
    var firstMissing = -1, st = [], loss = [];
    run.steps.forEach(function (s, i) {
      if (s.missing) { st[i] = firstMissing < 0 ? 'stopped' : 'unreached'; if (firstMissing < 0) firstMissing = i; }
      else if (PM.isLoss(s)) { st[i] = 'loss'; loss.push(i); }
      else st[i] = 'ok';
    });
    /* "affected": ran fine but sits downstream of a loss step */
    var affected = {}, E = edgeList(), queue = loss.slice();
    while (queue.length) {
      var n = queue.shift();
      E.forEach(function (e) { if (e.from === n && !affected[e.to]) { affected[e.to] = true; queue.push(e.to); } });
    }
    return { st: st, affected: affected };
  }
  function edgeInfo(run, e) {
    var prod = run.steps[e.from], cons = run.steps[e.to];
    if (prod.missing || cons.missing) return { state: 'inactive', value: null };
    var v = cons.inputs[e.k] ? cons.inputs[e.k].value : null;
    return { state: v === 0 ? 'empty' : 'ok', value: v };
  }

  /* ------------------------------------------------------------------
     Rendering
     ------------------------------------------------------------------ */
  var STATE_TXT = { ok: 'Fine', loss: 'Data loss', stopped: 'Not reported', unreached: 'Not reached' };
  var STATE_LONG = { ok: 'fine', loss: 'possible data loss', stopped: 'not reported — the run stopped here', unreached: 'not reached' };
  function stateIcon(s) { return s === 'ok' ? PM.I.check : s === 'loss' ? PM.I.octagon : PM.I.gap; }
  function nameWbr(n) { return n.replace(/_/g, '_<wbr>'); }

  function build(el, o) {
    var P = PM, run = o.run, mode = o.mode || 'run';
    var cs = getComputedStyle(el);
    var cw = (el.clientWidth || 1100) - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    var pk = pickLayout(cw, o.prefer), L = pk.L, sc = pk.scale;
    var ns = run ? nodeStates(run) : null;
    var maxV = 1;
    if (run) L.edges.forEach(function (g) { var v = edgeInfo(run, g.e).value; if (v > maxV) maxV = v; });

    /* SVG: bands, edges, arrowheads */
    var svg = '<svg class="graph__svg" width="' + L.W + '" height="' + L.H + '" viewBox="0 0 ' + L.W + ' ' + L.H + '" aria-hidden="true">';
    L.bands.forEach(function (b) {
      svg += '<rect class="gband gband--' + b.g + '" x="' + b.x + '" y="' + b.y + '" width="' + b.w + '" height="' + b.h + '" rx="12"/>';
    });
    L.edges.forEach(function (g, j) {
      var info = run && mode === 'run' ? edgeInfo(run, g.e) : { state: mode === 'run' ? 'ok' : 'ghost', value: null };
      var wd = info.state === 'ok' && info.value != null ? (1.25 + 2.75 * Math.log10(info.value + 1) / Math.log10(maxV + 1)) : 1.5;
      svg += '<g class="gedge gedge--' + info.state + '" data-edge="' + j + '" data-from="' + g.e.from + '" data-to="' + g.e.to + '">' +
        '<path class="gedge__hit" d="' + g.d + '"/>' +
        '<path class="gedge__line" d="' + g.d + '" style="stroke-width:' + wd.toFixed(2) + 'px"/>' +
        (info.state === 'ok' && mode === 'run' ? '<path class="gedge__flow" d="' + g.d + '"/>' : '') +
        '<path class="gedge__arrow" d="' + g.arrow + '"/></g>';
    });
    svg += '</svg>';

    /* Band labels (HTML so they stay crisp and use the type scale) */
    var labels = L.bands.map(function (b) {
      return '<span class="gband-label gband-label--' + b.g + '" style="left:' + (b.x + 10) + 'px;top:' + (b.y + 6) + 'px">' + GROUP_NAME[b.g] + '</span>';
    }).join('');

    /* Edge chips */
    var chips = '';
    if (L.chips && mode === 'run') L.edges.forEach(function (g, j) {
      var info = edgeInfo(run, g.e);
      var val = info.state === 'inactive' ? '—' : P.fmt(info.value);
      chips += '<span class="gchip gchip--' + info.state + (L.kind === 'lr' ? ' gchip--stack' : '') + (g.chip.align === 'start' ? ' gchip--start' : '') +
        '" data-edge="' + j + '" style="left:' + g.chip.x.toFixed(1) + 'px;top:' + g.chip.y.toFixed(1) + 'px">' +
        '<span class="gchip__name">' + g.e.input + '</span><span class="gchip__sep" aria-hidden="true">&nbsp;·&nbsp;</span><b class="num">' + val + '</b></span>';
    });

    /* Nodes (real buttons, in reading order) */
    var nodesHTML = ORDER.map(function (i) {
      var n = L.nodes[i], s = run ? run.steps[i] : null, name = P.STEPS[i].name, grp = GROUP[i];
      var style = 'left:' + n.x + 'px;top:' + n.y + 'px;width:' + n.w + 'px;height:' + n.h + 'px';
      if (mode === 'skeleton') {
        return '<div class="gnode gnode--skel" style="' + style + '"><span class="skel" style="width:60%;height:12px"></span><span class="skel" style="width:85%;height:10px"></span><span class="skel" style="width:40%;height:20px;margin-top:auto"></span></div>';
      }
      var st = mode === 'ghost' ? 'ghost' : ns.st[i], aff = mode === 'run' && ns.affected[i] && st === 'ok';
      var count, time = '';
      if (mode === 'ghost') count = '<span class="gnode__count gnode__count--na">—</span>';
      else if (s.missing) count = '<span class="gnode__count gnode__count--na">—</span>';
      else if (s.output == null) count = '<span class="gnode__count gnode__count--na">n/a <small>· returns nothing</small></span>';
      else count = '<span class="gnode__count num">' + P.fmt(s.output) + '</span>';
      if (mode === 'run' && !s.missing) time = '<span class="gnode__time num">' + P.hhmmss(s.finishedAt) + '</span>';
      var aria = LABEL[i] + ', ' + name + ', ' + GROUP_NAME[grp] + '. ' +
        (mode === 'ghost' ? 'No data.' : 'State: ' + STATE_LONG[st] + '. ' + (s.missing ? '' : 'Output ' + (s.output == null ? 'n/a' : P.fmt(s.output)) + '.')) +
        (aff ? ' Downstream of a data-loss step.' : '');
      return '<button type="button" class="gnode gnode--' + st + (aff ? ' is-affected' : '') + '" data-i="' + i + '" style="' + style + '" aria-label="' + aria + '"' + (mode !== 'run' ? ' tabindex="-1"' : '') + '>' +
        '<span class="gnode__head">' +
          (mode === 'run' ? '<span class="gpill gpill--' + st + '">' + stateIcon(st) + '<span class="gpill__txt">' + STATE_TXT[st] + '</span></span>' : '') +
          (aff ? '<span class="gpill gpill--affected" title="Downstream of a data-loss step">' + P.I.down + '<span class="gpill__txt">affected</span></span>' : '') +
        '</span>' +
        '<span class="gnode__label"><i class="gdot gdot--' + grp + '" aria-hidden="true"></i>' + LABEL[i] + '</span>' +
        '<span class="gnode__name">' + nameWbr(name) + '</span>' +
        '<span class="gnode__foot">' + count + (L.kind !== 'compact' ? time : '') + '</span>' +
      '</button>';
    }).join('');

    var dirText = L.kind === 'tb' ? 'top to bottom' : 'left to right';
    var summary = mode === 'run' ? summaryText(run, ns) : '';
    el.innerHTML =
      '<div class="graph-head"><p class="graph-head__flow">' + P.I.flow + '<span>Data flows <b>' + dirText + '</b>. An arrow <span class="mono">A → B</span> means A’s output is B’s input.</span></p>' +
        (summary ? '<p class="graph-head__sum">' + summary + '</p>' : '') + '</div>' +
      '<div class="graph-stage" style="height:' + Math.ceil(L.H * sc) + 'px">' +
        '<div class="graph graph--' + L.kind + '" style="width:' + L.W + 'px;height:' + L.H + 'px;transform:scale(' + sc.toFixed(4) + ')" role="group" aria-label="Pipeline graph, ' + dirText + '">' +
          svg + labels + chips + nodesHTML +
        '</div>' +
        (mode === 'ghost' ? '<div class="graph-ghost-msg">' + (o.ghostMsg || '') + '</div>' : '') +
      '</div>' +
      (mode === 'run' ? legendHTML(L.kind) : '');

    if (mode === 'run') wire(el, o, L);
  }

  function summaryText(run, ns) {
    var reported = run.steps.filter(function (s) { return !s.missing; }).length;
    var parts = ['<span>' + reported + ' of 9 steps reported</span>'];
    var stop = ns.st.indexOf('stopped');
    if (stop >= 0) parts.push('<span class="t-warn">' + PM.I.gap + 'stopped at <span class="mono">' + PM.STEPS[stop].name + '</span></span>');
    var loss = ns.st.indexOf('loss');
    if (loss >= 0) parts.push('<span class="t-bad">' + PM.I.octagon + 'data loss at <span class="mono">' + PM.STEPS[loss].name + '</span></span>');
    return parts.join('');
  }

  function legendHTML(kind) {
    var I = PM.I;
    var ln = function (cls) { return '<svg class="lg-edge" viewBox="0 0 28 10" aria-hidden="true"><path class="' + cls + '" d="M1 5H20"/><path class="' + cls + '-arrow" d="M20 1.5L27 5L20 8.5Z"/></svg>'; };
    return '<div class="graph-legend" aria-label="Legend">' +
      '<div class="graph-legend__group"><span class="eyebrow">Steps</span>' +
        '<span class="gpill gpill--ok">' + I.check + '<span class="gpill__txt">Fine</span></span>' +
        '<span class="gpill gpill--loss">' + I.octagon + '<span class="gpill__txt">Data loss</span></span>' +
        '<span class="gpill gpill--stopped">' + I.gap + '<span class="gpill__txt">Not reported</span></span>' +
        '<span class="gpill gpill--unreached">' + I.gap + '<span class="gpill__txt">Not reached</span></span>' +
        '<span class="gpill gpill--affected">' + I.down + '<span class="gpill__txt">Downstream of a loss</span></span></div>' +
      '<div class="graph-legend__group"><span class="eyebrow">Arrows</span>' +
        '<span class="lg-item">' + ln('lg-ok') + 'items flow · thicker = more</span>' +
        '<span class="lg-item">' + ln('lg-empty') + '0 items</span>' +
        '<span class="lg-item">' + ln('lg-inactive') + 'not reached</span></div>' +
      '<div class="graph-legend__group"><span class="eyebrow">Groups</span>' +
        ['callrail', 'gads', 'merge', 'persist'].map(function (g) { return '<span class="lg-item"><i class="gdot gdot--' + g + '"></i>' + GROUP_NAME[g] + '</span>'; }).join('') +
      '</div>' +
      (kind === 'compact' ? '<p class="graph-legend__hint">Hover or focus a step to see its counts and arrows.</p>' : '') +
    '</div>';
  }

  /* ------------------------------------------------------------------
     Interaction: hover tooltips, select + neighbours, Esc / empty click
     ------------------------------------------------------------------ */
  function wire(el, o, L) {
    var P = PM, run = o.run, graph = el.querySelector('.graph'), tip = document.getElementById('tooltip');
    var E = L.edges.map(function (g) { return g.e; });

    function showTip(html, target) {
      tip.innerHTML = html; tip.hidden = false;
      var r = target.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.min(window.innerWidth - tw - 8, Math.max(8, r.left + r.width / 2 - tw / 2));
      var top = r.top - th - 10; if (top < 64) top = r.bottom + 10;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
    function hideTip() { tip.hidden = true; }

    function nodeTip(i) {
      var s = run.steps[i], def = P.STEPS[i], st = nodeStates(run).st[i];
      var ins = def.inputs.length ? def.inputs.map(function (p, k) {
        var v = s.missing ? '—' : P.fmt(s.inputs[k].value);
        return '<div>in: <b>' + p[0] + '</b> ' + v + ' <span class="faint">from ' + P.STEPS[p[1]].name + '</span></div>';
      }).join('') : '<div>in: none <span class="faint">(source step)</span></div>';
      var out = s.missing ? '—' : s.output == null ? 'n/a (returns nothing)' : P.fmt(s.output);
      return '<div class="tooltip__date"><span class="mono">' + def.name + '</span> · ' + GROUP_NAME[GROUP[i]] + '</div>' +
        '<div class="tooltip__rows">' + ins + '<div>out: <b>' + out + '</b></div>' +
        '<div class="faint">' + (s.missing ? STATE_LONG[st] : 'finished ' + P.hhmmss(s.finishedAt) + ' · ' + STATE_LONG[st]) + '</div></div>';
    }
    function edgeTip(j) {
      var e = E[j], info = edgeInfo(run, e);
      var v = info.state === 'inactive' ? 'not recorded' : P.fmt(info.value);
      return '<div class="tooltip__date"><span class="mono">' + P.STEPS[e.from].name + '</span> → <span class="mono">' + P.STEPS[e.to].name + '</span></div>' +
        '<div class="tooltip__val">' + e.input + ' · ' + v + '</div>' +
        (info.state === 'empty' ? '<div style="color:var(--bad)">0 items reached the next step</div>' : info.state === 'inactive' ? '<div class="faint">this hand-off did not happen</div>' : '');
    }

    graph.addEventListener('pointerover', function (ev) {
      var n = ev.target.closest('.gnode'), c = ev.target.closest('.gchip, .gedge');
      if (n) showTip(nodeTip(+n.dataset.i), n);
      else if (c) showTip(edgeTip(+(c.dataset.edge)), c.classList.contains('gedge') ? ev.target : c);
    });
    graph.addEventListener('pointerout', function (ev) { if (!ev.relatedTarget || !graph.contains(ev.relatedTarget) || !ev.relatedTarget.closest('.gnode, .gchip, .gedge')) hideTip(); });
    graph.addEventListener('focusin', function (ev) { var n = ev.target.closest('.gnode'); if (n) showTip(nodeTip(+n.dataset.i), n); });
    graph.addEventListener('focusout', hideTip);

    function select(i) {
      o.selected = i;
      var up = {}, down = {};
      E.forEach(function (e) { if (e.to === i) up[e.from] = 1; if (e.from === i) down[e.to] = 1; });
      graph.classList.toggle('is-selecting', i != null);
      graph.querySelectorAll('.gnode').forEach(function (n) {
        var k = +n.dataset.i;
        n.classList.toggle('is-selected', k === i);
        n.classList.toggle('is-hl', !!(i != null && (k === i || up[k] || down[k])));
        n.setAttribute('aria-pressed', String(k === i));
      });
      graph.querySelectorAll('.gedge, .gchip').forEach(function (g) {
        var e = E[+g.dataset.edge];
        g.classList.toggle('is-hl', !!(i != null && (e.from === i || e.to === i)));
      });
      if (o.details) renderDetails(i, up, down);
    }
    function renderDetails(i, up, down) {
      if (i == null) { o.details.innerHTML = ''; o.details.hidden = true; return; }
      var link = function (k) { return '<button type="button" class="chip chip--btn" data-goto="' + k + '">' + P.I.arrowIn + '<span class="mono">' + P.STEPS[k].name + '</span></button>'; };
      var ups = Object.keys(up).map(Number), downs = Object.keys(down).map(Number);
      o.details.hidden = false;
      o.details.innerHTML =
        '<div class="graph-details__head"><div><p class="eyebrow">Selected step</p><h3 class="graph-details__title">' + LABEL[i] + ' <span class="mono faint">' + P.STEPS[i].name + '</span></h3></div>' +
        '<button type="button" class="icon-btn" data-clear aria-label="Clear selection"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>' +
        '<div class="graph-details__rel"><span class="faint">Upstream</span>' + (ups.length ? ups.map(link).join('') : '<span class="chip chip--none">none (source)</span>') +
        '<span class="faint">Downstream</span>' + (downs.length ? downs.map(link).join('') : '<span class="chip chip--none">none (sink)</span>') + '</div>' +
        '<ol class="steps' + (o.prefer === 'compact' ? ' steps--compact' : '') + '">' + P.stepItemHTML(run, o.runs, i, o.prefer === 'compact') + '</ol>';
    }

    graph.addEventListener('click', function (ev) {
      var n = ev.target.closest('.gnode');
      if (n) { var i = +n.dataset.i; select(o.selected === i ? null : i); }
      else select(null);                                   // empty-space click clears
    });
    if (o.details) o.details.onclick = function (ev) {
      if (ev.target.closest('[data-clear]')) { var k = o.selected; select(null); var b = graph.querySelector('.gnode[data-i="' + k + '"]'); if (b) b.focus(); }
      var g = ev.target.closest('[data-goto]');
      if (g) { select(+g.dataset.goto); var nb = graph.querySelector('.gnode[data-i="' + g.dataset.goto + '"]'); if (nb) nb.focus(); }
    };
    el._pmClear = function () { if (o.selected == null) return false; var k = o.selected; select(null); var b = graph.querySelector('.gnode[data-i="' + k + '"]'); if (b) b.focus(); return true; };
    if (o.selected != null) select(o.selected);
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
    refresh: function (el) { if (el && el._pmOpts) build(el, el._pmOpts); }
  };
})();
