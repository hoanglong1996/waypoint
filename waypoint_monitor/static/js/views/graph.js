/* Directed-graph view of one run: HTML node buttons over an inline SVG edge layer.
   Rules and geometry live in ../graph-model.js. Design: docs/design/pipeline-monitor-graph-update. */
import {
  MIN_SCALE, computeLayout, dimsOf, edgeInfo, edgeWidth, edgesOf, hasMapStep, layoutFor, neighbours, nodeStates, partition,
  pickLayout, readingOrder, simpleLayout,
} from '../graph-model.js';
import { mapAria, mapProgress } from '../map-model.js';
import { mapNodeHTML, mapIcon } from '../map-ui.js';
import { mountMapPanel, panelId, syncAddress } from './map.js';
import { parseRoute } from '../router.js';
import {
  esc, fmt, fmtDuration, groupKeys, groupLabel, groupSlot, hasCounts, hhmmss, isDone, metricsOver, overText, stepState,
} from '../model.js';
import {
  I, elapsedHTML, noticeFor, problemsHTML,
} from '../ui.js';
import { stepItemHTML } from './step.js';

const STATE_TXT = {
  ok: 'Fine', loss: 'Data loss', stopped: 'Not reported', unreached: 'Not reached',
  running: 'Running', waiting: 'Waiting', stalled: 'Stalled', died: 'Died', failed: 'Failed',
};
const STATE_LONG = {
  ok: 'fine', loss: 'possible data loss', stopped: 'not reported — the run stopped here', unreached: 'not reached',
  running: 'running now', waiting: 'waiting for an earlier step', stalled: 'stalled — alive but running far longer than expected, the run stopped here',
  died: 'died — the process is gone, the run stopped here',
  failed: 'failed — the step raised an error, later steps were not reached',
};
const STATE_ICON = { running: I.spinner, waiting: I.hourglass, stalled: I.alert, died: I.power, failed: I.failed };
const stateIcon = (s) => STATE_ICON[s] || (s === 'ok' ? I.check : s === 'loss' ? I.octagon : I.gap);
const nameWbr = (n) => esc(n).replace(/_/g, '_<wbr>');
const labelOf = (d) => d.label || d.name;
/* Stand-in steps for the loading skeleton, before any run (and so any flow) is known. */
const SKELETON_DEFS = ['a', 'b', 'c', 'd', 'e', 'f'].map((name, i) => ({
  name, label: name, group: null, inputs: i === 0 ? [] : [{ name: 'in', from: i === 4 ? 'b' : ['a', 'b', 'c', 'd', 'e'][i - 1] }],
}));

/* Selection survives a data refresh: remembered per mount point id. */
const keepSelected = new Map();

function build(el, o) {
  const mode = o.mode || 'run';
  const { run } = o;
  const defs = run ? run.defs : mode === 'skeleton' ? SKELETON_DEFS : [];
  const simple = !!run && !run.flow;
  const groups = run ? groupKeys(run) : [];
  const edges = simple ? [] : edgesOf(defs);
  const cs = getComputedStyle(el);
  const cw = (el.clientWidth || 1100) - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const pk = pickLayout(cw, o.prefer, dimsOf(computeLayout(defs, edges)), hasMapStep(defs));
  const L = simple ? simpleLayout(defs, cw, o.prefer === 'compact') : layoutFor(pk.kind, defs, edges, cw, groups);
  const sc = simple ? 1 : pk.kind === 'tb' ? Math.max(MIN_SCALE, Math.min(1, cw / L.W)) : pk.scale;
  const scrolls = L.W * sc > cw + 1;
  const ns = run ? nodeStates(run, edges) : null;
  let maxV = 1;
  if (run) L.edges.forEach((g) => { const v = edgeInfo(run, g.e).value; if (v > maxV) maxV = v; });

  let svg = '<svg class="graph__svg" width="' + L.W + '" height="' + L.H + '" viewBox="0 0 ' + L.W + ' ' + L.H + '" aria-hidden="true">';
  L.bands.forEach((b) => {
    svg += '<rect class="gband g-' + groupSlot(run, b.g) + '" x="' + b.x + '" y="' + b.y + '" width="' + b.w + '" height="' + b.h + '" rx="12"/>';
  });
  L.edges.forEach((g, j) => {
    const info = run && mode === 'run' ? edgeInfo(run, g.e) : { state: mode === 'run' ? 'ok' : 'ghost', value: null };
    const wd = info.state === 'ok' ? edgeWidth(info.value, maxV) : 1.5;
    svg += '<g class="gedge gedge--' + info.state + '" data-edge="' + j + '" data-from="' + g.e.from + '" data-to="' + g.e.to + '">' +
      '<path class="gedge__hit" d="' + g.d + '"/>' +
      '<path class="gedge__line" d="' + g.d + '" style="stroke-width:' + wd.toFixed(2) + 'px"/>' +
      (info.state === 'ok' && mode === 'run' ? '<path class="gedge__flow" d="' + g.d + '"/>' : '') +
      '<path class="gedge__arrow" d="' + g.arrow + '"/></g>';
  });
  L.stubs.forEach((t) => {
    svg += '<g class="gedge gedge--dangling" data-stub="' + t.to + '"><path class="gedge__line" d="' + t.d + '"/><path class="gedge__arrow" d="' + t.arrow + '"/></g>';
  });
  svg += '</svg>';

  const labels = L.bands.map((b) =>
    '<span class="gband-label g-' + groupSlot(run, b.g) + '" style="left:' + (b.x + 10) + 'px;top:' + (b.y + 6) + 'px">' + esc(groupLabel(run, b.g)) + '</span>').join('');

  let chips = '';
  if (L.chips && mode === 'run') {
    L.edges.forEach((g, j) => {
      const info = edgeInfo(run, g.e);
      const val = info.state === 'inactive' ? '—' : fmt(info.value);
      chips += '<span class="gchip gchip--' + info.state + (L.kind === 'lr' ? ' gchip--stack' : '') + (g.chip.align === 'start' ? ' gchip--start' : '') +
        '" data-edge="' + j + '" style="left:' + g.chip.x.toFixed(1) + 'px;top:' + g.chip.y.toFixed(1) + 'px">' +
        '<span class="gchip__name">' + esc(g.e.input) + '</span><span class="gchip__sep" aria-hidden="true">&nbsp;·&nbsp;</span><b class="num">' + val + '</b></span>';
    });
  }

  const nodeHTML = (i, extraStyle) => {
    const n = L.nodes[i];
    const s = run ? run.steps[i] : null;
    const def = defs[i];
    const slot = run ? groupSlot(run, def.group) : 3;
    const style = n ? 'left:' + n.x + 'px;top:' + n.y + 'px;width:' + n.w + 'px;height:' + n.h + 'px' : extraStyle;
    if (mode === 'skeleton') {
      return '<div class="gnode gnode--skel" style="' + style + '"><span class="skel" style="width:60%;height:12px"></span><span class="skel" style="width:85%;height:10px"></span><span class="skel" style="width:40%;height:20px;margin-top:auto"></span></div>';
    }
    if (mode === 'run' && def.map && s && s.map) {
      return mapNodeHTML({ def, step: s, index: i, style, open: o.selected === i, panelId: panelId(def.name), label: labelOf(def) });
    }
    const st = mode === 'ghost' ? 'ghost' : ns.st[i];
    const aff = mode === 'run' && ns.affected[i] && st === 'ok';
    let count;
    let time = '';
    if (mode === 'run' && (st === 'running' || st === 'stalled')) count = '<span class="gnode__live">' + elapsedHTML(s) + '</span>';
    else if (mode === 'run' && st === 'failed') count = '<span class="gnode__live">' + (s.error ? esc(s.error.type) : 'failed') + '</span>';
    else if (mode === 'run' && st === 'died') count = '<span class="gnode__live">last seen ' + (s.lastSeenAt ? hhmmss(s.lastSeenAt) : '?') + '</span>';
    else if (mode === 'ghost' || !isDone(s)) count = '<span class="gnode__count gnode__count--na">—</span>';
    else if (s.output == null) count = '<span class="gnode__count gnode__count--na">n/a <small>· returns nothing</small></span>';
    else count = '<span class="gnode__count num">' + fmt(s.output) + '</span>';
    if (mode === 'run' && isDone(s)) time = '<span class="gnode__time num">' + hhmmss(s.finishedAt) + '</span>';
    const gname = def.group ? groupLabel(run, def.group) : '';
    const over = mode === 'run' && s ? metricsOver(s) : 0;
    const dur = mode === 'run' && s && s.durationSeconds != null && (isDone(s) || st === 'failed')
      ? '<span class="gnode__dur num" title="' + (s.durationApprox ? 'Estimated from the previous step' : 'Duration') + '">' + esc(fmtDuration(s.durationSeconds, { approx: s.durationApprox })) + '</span>'
      : '';
    const aria = labelOf(def) + ', ' + def.name + (gname ? ', ' + gname : '') + '. ' +
      (mode === 'ghost' ? 'No data.' : 'State: ' + STATE_LONG[st] + '. ' + (isDone(s) ? 'Output ' + (s.output == null ? 'n/a' : fmt(s.output)) + '.' : '')) +
      (s && s.durationSeconds != null && mode === 'run' ? ' Took ' + fmtDuration(s.durationSeconds, { approx: s.durationApprox }) + '.' : '') +
      (over ? ' ' + overText(over) + '.' : '') +
      (aff ? ' Downstream of a data-loss step.' : '');
    return '<button type="button" class="gnode gnode--' + st + (aff ? ' is-affected' : '') + '" data-i="' + i + '" style="' + style + '" aria-label="' + esc(aria) + '"' + (mode !== 'run' ? ' tabindex="-1"' : '') + '>' +
      '<span class="gnode__head">' +
        (mode === 'run' ? '<span class="gpill gpill--' + st + '">' + stateIcon(st) + '<span class="gpill__txt">' + STATE_TXT[st] + '</span></span>' : '') +
        (aff ? '<span class="gpill gpill--affected" title="Downstream of a data-loss step">' + I.down + '<span class="gpill__txt">affected</span></span>' : '') +
        (over ? '<span class="gpill gpill--metric" title="' + esc(overText(over)) + '">' + I.alert + '<span class="gpill__txt">' + over + (L.kind === 'compact' ? '' : ' over limit') + '</span></span>' : '') +
      '</span>' +
      '<span class="gnode__label"><i class="gdot g-' + slot + '" aria-hidden="true"></i>' + esc(labelOf(def)) + '</span>' +
      '<span class="gnode__namerow"><span class="gnode__name">' + nameWbr(def.name) + '</span>' + (L.kind !== 'compact' ? dur : '') + '</span>' +
      '<span class="gnode__foot">' + count + (L.kind !== 'compact' ? time : '') + '</span>' +
    '</button>';
  };

  const order = simple ? defs.map((d, i) => i) : readingOrder(defs, edges);
  const nodesHTML = order.map((i) => nodeHTML(i)).join('');
  // steps that reported but are not in the run's flow; with no flow at all they are all drawn as nodes instead
  const other = simple ? [] : partition(defs).other;
  const otherHTML = other.length && mode === 'run'
    ? '<div class="graph-other"><span class="eyebrow">Other steps</span><span class="faint graph-other__note">not in this run’s flow</span>' + other.map((i) => {
      const s = run.steps[i];
      return '<button type="button" class="chip chip--btn" data-i="' + i + '"><span class="mono">' + esc(defs[i].name) + '</span> ' +
        (hasCounts(s) ? (s.output == null ? 'n/a' : '<b>' + fmt(s.output) + '</b>') : stepState(s) === 'missing' ? 'not reported' : esc(stepState(s))) + '</button>';
    }).join('') + '</div>'
    : '';
  const noticeHTML = mode === 'run' ? noticeFor(run) : '';

  const dirText = L.kind === 'tb' ? 'top to bottom' : 'left to right';
  const summary = mode === 'run' ? summaryText(run, ns, defs) : '';
  el.innerHTML =
    '<div class="graph-head"><p class="graph-head__flow">' + I.flow + '<span>Data flows <b>' + dirText + '</b>. An arrow <span class="mono">A → B</span> means A’s output is B’s input.</span></p>' +
      (summary ? '<p class="graph-head__sum">' + summary + '</p>' : '') + '</div>' +
    noticeHTML +
    '<div class="graph-stage" style="height:' + (Math.max(Math.ceil(L.H * sc), mode === 'ghost' ? 220 : 0) + (scrolls ? 14 : 0)) + 'px' + (scrolls ? ';overflow-x:auto' : '') + '">' +
      '<div class="graph graph--' + L.kind + '" style="width:' + L.W + 'px;height:' + L.H + 'px;transform:scale(' + sc.toFixed(4) + ')" role="group" aria-label="Pipeline graph, ' + dirText + '">' +
        svg + labels + chips + nodesHTML +
      '</div>' +
      (mode === 'ghost' ? '<div class="graph-ghost-msg">' + (o.ghostMsg || '') + '</div>' : '') +
    '</div>' + otherHTML +
    (mode === 'run' ? legendHTML(L.kind, run, simple) : '') + (mode === 'run' ? problemsHTML(run) : '');

  if (mode === 'run') wire(el, o, L, edges, defs);
}

function summaryText(run, ns, steps) {
  const reported = run.steps.filter(isDone).length;
  const parts = ['<span>' + reported + ' of ' + run.steps.length + ' steps reported</span>'];
  const running = ns.st.indexOf('running');
  if (running >= 0) parts.push('<span class="t-run">' + I.spinner + 'running <span class="mono">' + esc(steps[running].name) + '</span></span>');
  const stalled = ns.st.indexOf('stalled');
  if (stalled >= 0) parts.push('<span class="t-warn">' + I.alert + 'stalled at <span class="mono">' + esc(steps[stalled].name) + '</span></span>');
  const failed = ns.st.indexOf('failed');
  if (failed >= 0) parts.push('<span class="t-bad">' + I.failed + 'failed at <span class="mono">' + esc(steps[failed].name) + '</span></span>');
  const died = ns.st.indexOf('died');
  if (died >= 0) parts.push('<span class="t-bad">' + I.power + 'died at <span class="mono">' + esc(steps[died].name) + '</span></span>');
  const stop = ns.st.indexOf('stopped');
  if (stop >= 0) parts.push('<span class="t-warn">' + I.gap + 'stopped at <span class="mono">' + esc(steps[stop].name) + '</span></span>');
  const loss = ns.st.indexOf('loss');
  if (loss >= 0) parts.push('<span class="t-bad">' + I.octagon + 'data loss at <span class="mono">' + esc(steps[loss].name) + '</span></span>');
  return parts.join('');
}

function legendHTML(kind, run, simple) {
  const ln = (cls) => '<svg class="lg-edge" viewBox="0 0 28 10" aria-hidden="true"><path class="' + cls + '" d="M1 5H20"/><path class="' + cls + '-arrow" d="M20 1.5L27 5L20 8.5Z"/></svg>';
  return '<div class="graph-legend" aria-label="Legend">' +
    '<div class="graph-legend__group"><span class="eyebrow">Steps</span>' +
      '<span class="gpill gpill--ok">' + I.check + '<span class="gpill__txt">Fine</span></span>' +
      '<span class="gpill gpill--loss">' + I.octagon + '<span class="gpill__txt">Data loss</span></span>' +
      '<span class="gpill gpill--stopped">' + I.gap + '<span class="gpill__txt">Not reported</span></span>' +
      '<span class="gpill gpill--unreached">' + I.gap + '<span class="gpill__txt">Not reached</span></span>' +
      '<span class="gpill gpill--affected">' + I.down + '<span class="gpill__txt">Downstream of a loss</span></span>' +
      '<span class="gpill gpill--running">' + I.spinner + '<span class="gpill__txt">Running</span></span>' +
      '<span class="gpill gpill--waiting">' + I.hourglass + '<span class="gpill__txt">Waiting</span></span>' +
      '<span class="gpill gpill--stalled">' + I.alert + '<span class="gpill__txt">Stalled</span></span>' +
      '<span class="gpill gpill--died">' + I.power + '<span class="gpill__txt">Died</span></span>' +
      '<span class="gpill gpill--failed">' + I.failed + '<span class="gpill__txt">Failed</span></span></div>' +
    (hasMapStep(run.defs) ? '<div class="graph-legend__group"><span class="eyebrow">Loops</span>' +
      '<span class="lg-item"><span class="mn-tag">' + mapIcon('loop').replace('class="mic"', 'class="mic mic--s"') + 'Map</span>one step that repeats the same steps for many items</span></div>' : '') +
    (simple ? '' : '<div class="graph-legend__group"><span class="eyebrow">Arrows</span>' +
      '<span class="lg-item">' + ln('lg-ok') + 'items flow · thicker = more</span>' +
      '<span class="lg-item">' + ln('lg-empty') + '0 items</span>' +
      '<span class="lg-item">' + ln('lg-inactive') + 'not reached</span></div>') +
    (groupKeys(run).length ? '<div class="graph-legend__group"><span class="eyebrow">Groups</span>' +
      groupKeys(run).map((g) => '<span class="lg-item"><i class="gdot g-' + groupSlot(run, g) + '"></i>' + esc(groupLabel(run, g)) + '</span>').join('') +
    '</div>' : '') +
    (kind === 'compact' ? '<p class="graph-legend__hint">Hover or focus a step to see its counts and arrows.</p>' : '') +
  '</div>';
}

/* Hover/focus tooltips, selection + neighbours, Selected-step panel. */
function wire(el, o, L, edges, steps) {
  const { run, cfg } = o;
  const graph = el.querySelector('.graph');
  const tip = document.getElementById('tooltip');
  const states = nodeStates(run, edges).st;

  function showTip(html, target) {
    tip.innerHTML = html;
    tip.hidden = false;
    const r = target.getBoundingClientRect();
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    const left = Math.min(window.innerWidth - tw - 8, Math.max(8, r.left + r.width / 2 - tw / 2));
    let top = r.top - th - 10;
    if (top < 64) top = r.bottom + 10;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  const hideTip = () => { tip.hidden = true; };

  function nodeTip(i) {
    const s = run.steps[i];
    const def = steps[i];
    if (def.map && s.map) {
      return '<div class="tooltip__date"><span class="mono">' + esc(def.name) + '</span> · map step</div>' +
        '<div class="tooltip__rows"><div>' + esc(mapProgress(s.map)) + '</div>' +
        (s.map.lostItems > 0 ? '<div style="color:var(--bad)">items lost data</div>' : '') +
        '<div class="faint">' + (o.selected === i ? 'items are shown below' : 'select to show its items') + '</div></div>';
    }
    const ins = def.inputs.length
      ? def.inputs.map((p, k) => {
        const v = s.missing || !s.inputs[k] ? '—' : fmt(s.inputs[k].value);
        return '<div>in: <b>' + esc(p.name) + '</b> ' + v + ' <span class="faint">from ' + esc(p.from) + (p.dangling ? ' (not in this flow)' : '') + '</span></div>';
      }).join('')
      : '<div>in: none <span class="faint">(source step)</span></div>';
    const out = !isDone(s) ? '—' : s.output == null ? 'n/a (returns nothing)' : fmt(s.output);
    return '<div class="tooltip__date"><span class="mono">' + esc(def.name) + '</span> · ' + esc(def.group ? groupLabel(run, def.group) : 'no group') + '</div>' +
      '<div class="tooltip__rows">' + ins + '<div>out: <b>' + out + '</b></div>' +
      (s.durationSeconds != null ? '<div>took <b>' + esc(fmtDuration(s.durationSeconds, { approx: s.durationApprox })) + '</b>' + '</div>' : '') +
      '<div class="faint">' + (isDone(s) ? 'finished ' + hhmmss(s.finishedAt) + ' · ' + STATE_LONG[states[i]]
        : s.startedAt ? 'started ' + hhmmss(s.startedAt) + ' · ' + STATE_LONG[states[i]] : STATE_LONG[states[i]]) + '</div></div>';
  }
  function edgeTip(j) {
    const e = edges[j];
    const info = edgeInfo(run, e);
    const pending = [e.from, e.to].some((k) => ['running', 'waiting'].includes(stepState(run.steps[k])));
    const v = info.state === 'inactive' ? (pending ? 'not finished yet' : 'not recorded') : fmt(info.value);
    return '<div class="tooltip__date"><span class="mono">' + esc(steps[e.from].name) + '</span> → <span class="mono">' + esc(steps[e.to].name) + '</span></div>' +
      '<div class="tooltip__val">' + esc(e.input) + ' · ' + v + '</div>' +
      (info.state === 'empty' ? '<div style="color:var(--bad)">0 items reached the next step</div>'
        : info.state === 'inactive' ? '<div class="faint">' + (pending ? 'this hand-off has not happened yet' : 'this hand-off did not happen') + '</div>' : '');
  }

  graph.addEventListener('pointerover', (ev) => {
    const n = ev.target.closest('.gnode');
    const c = ev.target.closest('.gchip, .gedge');
    if (n) showTip(nodeTip(+n.dataset.i), n);
    else if (c) showTip(edgeTip(+c.dataset.edge), c.classList.contains('gedge') ? ev.target : c);
  });
  graph.addEventListener('pointerout', (ev) => {
    if (!ev.relatedTarget || !graph.contains(ev.relatedTarget) || !ev.relatedTarget.closest('.gnode, .gchip, .gedge')) hideTip();
  });
  graph.addEventListener('focusin', (ev) => { const n = ev.target.closest('.gnode'); if (n) showTip(nodeTip(+n.dataset.i), n); });
  graph.addEventListener('focusout', hideTip);

  /* A map step opens its panel under the graph (design 3.2); every other step opens the "Selected step" details. */
  const isMapAt = (i) => i != null && !!steps[i].map && !!run.steps[i].map;
  function renderMapPanel(i, fromUser) {
    if (!o.mapPanel) return;
    if (!isMapAt(i)) {
      if (!o.mapPanel.hidden || o.mapPanel.innerHTML) {
        o.mapPanel.hidden = true;
        o.mapPanel.innerHTML = '';
        if (o.mapPanel._mpTimer) clearInterval(o.mapPanel._mpTimer);
      }
      if (parseRoute(location.hash).map) syncAddress(run, null);
      return;
    }
    mountMapPanel(o.mapPanel, {
      run, step: run.steps[i], def: steps[i], route: o.route, live: run.status === 'running', focus: !!fromUser,
      onClose: () => {
        const k = o.selected;
        select(null);
        focusNode(k);
      },
    });
  }

  function renderDetails(i, up, down, fromUser) {
    renderMapPanel(i, fromUser);
    if (!o.details) return;
    if (i == null || isMapAt(i)) {
      o.details.innerHTML = '';
      o.details.hidden = true;
      return;
    }
    const link = (k) => '<button type="button" class="chip chip--btn" data-goto="' + k + '">' + I.arrowIn + '<span class="mono">' + esc(steps[k].name) + '</span></button>';
    const ups = [...up];
    const downs = [...down];
    o.details.hidden = false;
    o.details.innerHTML =
      '<div class="graph-details__head"><div><p class="eyebrow">Selected step</p><h3 class="graph-details__title">' + esc(labelOf(steps[i])) +
      ' <span class="mono faint">' + esc(steps[i].name) + '</span></h3></div>' +
      '<button type="button" class="icon-btn" data-clear aria-label="Clear selection"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>' +
      '<div class="graph-details__rel"><span class="faint">Upstream</span>' + (ups.length ? ups.map(link).join('') : '<span class="chip chip--none">none (source)</span>') +
      '<span class="faint">Downstream</span>' + (downs.length ? downs.map(link).join('') : '<span class="chip chip--none">none (sink)</span>') + '</div>' +
      '<ol class="steps' + (o.prefer === 'compact' ? ' steps--compact' : '') + '">' + stepItemHTML(run, o.runs, cfg, i, o.prefer === 'compact') + '</ol>';
  }

  function select(i, fromUser) {
    o.selected = i;
    keepSelected.set(el.id, i);
    const { up, down } = i == null ? { up: new Set(), down: new Set() } : neighbours(edges, i);
    graph.classList.toggle('is-selecting', i != null);
    graph.querySelectorAll('.gnode').forEach((n) => {
      const k = +n.dataset.i;
      n.classList.toggle('is-selected', k === i);
      n.classList.toggle('is-hl', i != null && (k === i || up.has(k) || down.has(k)));
      if (n.classList.contains('gnode--map')) {
        // a map node is a disclosure: it opens and closes its panel
        const open = k === i;
        n.setAttribute('aria-expanded', String(open));
        n.setAttribute('aria-label', mapAria(labelOf(steps[k]), run.steps[k].map, open));
        const foot = n.querySelector('.mn-foot__txt');
        if (foot) foot.textContent = open ? 'Hide items' : 'Show items';
      } else n.setAttribute('aria-pressed', String(k === i));
    });
    graph.querySelectorAll('.gedge, .gchip').forEach((g) => {
      const e = edges[+g.dataset.edge];
      g.classList.toggle('is-hl', i != null && (e.from === i || e.to === i));
    });
    renderDetails(i, up, down, fromUser);
  }
  const focusNode = (k) => { const b = graph.querySelector('.gnode[data-i="' + k + '"]'); if (b) b.focus(); };

  const onClick = (ev) => {
    const n = ev.target.closest('[data-i]');
    if (n) select(o.selected === +n.dataset.i ? null : +n.dataset.i, true);
    else if (ev.currentTarget === graph) select(null); // empty-space click clears
  };
  graph.addEventListener('click', onClick);
  const other = el.querySelector('.graph-other');
  if (other) other.addEventListener('click', onClick);
  if (o.details) {
    o.details.onclick = (ev) => {
      if (ev.target.closest('[data-clear]')) {
        const k = o.selected;
        select(null);
        focusNode(k);
      }
      const g = ev.target.closest('[data-goto]');
      if (g) {
        select(+g.dataset.goto, true);
        focusNode(g.dataset.goto);
      }
    };
  }
  el._pmClear = () => {
    if (o.selected == null) return false;
    const k = o.selected;
    select(null);
    focusNode(k);
    return true;
  };
  if (o.selected != null && o.selected < steps.length) select(o.selected);
}

/* Esc clears the selection before anything else (e.g. before leaving the page). */
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape') return;
  const mounted = Array.from(document.querySelectorAll('[data-graph-mount]')).reverse();
  for (const m of mounted) {
    if (m.offsetParent !== null && m._pmClear && m._pmClear()) {
      ev.stopImmediatePropagation();
      ev.preventDefault();
      return;
    }
  }
}, true);

/* Re-layout on resize (debounced); keeps selection. */
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    document.querySelectorAll('[data-graph-mount]').forEach((el) => {
      if (el._pmOpts && el.offsetParent !== null) build(el, el._pmOpts);
    });
  }, 120);
});

/** mountGraph(el, {cfg, run, runs, mode: 'run'|'skeleton'|'ghost', details, prefer: 'auto'|'compact', ghostMsg, selected}) */
export function mountGraph(el, o) {
  el.setAttribute('data-graph-mount', '');
  if (o.mode === 'run' && o.route && o.route.map && o.run) {
    // an address that names an open map panel (a shared link, Back from an item) opens it
    const at = o.run.defs.findIndex((d) => d.name === o.route.map && d.map);
    if (at >= 0 && o.run.steps[at] && o.run.steps[at].map) o.selected = at;
  }
  if (o.selected === undefined && o.mode === 'run') o.selected = keepSelected.get(el.id);
  el._pmOpts = o;
  build(el, o);
}

export function refreshGraph(el) {
  if (el && el._pmOpts) build(el, el._pmOpts);
}
