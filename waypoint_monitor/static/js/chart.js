/* Hand-drawn SVG charts, themed through CSS variables. */
import { compact, dayLabel, fmt, hhmm, isLoss, metric, niceMax, shortDay, stepOf } from './model.js';
import { deltaChip } from './ui.js';

/** 128x36 sparkline. `values` oldest -> newest; null breaks the line. */
export function sparkline(values) {
  const W = 128;
  const H = 36;
  const pad = 3;
  const nums = values.filter((v) => v != null);
  if (!nums.length) return '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true"></svg>';
  const max = Math.max(...nums);
  let min = Math.min(...nums, 0);
  min = Math.min(min, max * 0.4);
  const span = max - min || 1;
  const x = (i) => pad + (i * (W - pad * 2)) / Math.max(1, values.length - 1);
  const y = (v) => H - pad - ((v - min) / span) * (H - pad * 2);
  let d = '';
  let pen = false;
  let dots = '';
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
    pen = true;
    if (v === 0) dots += '<circle class="spark-zero" cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="2.2"/>';
  });
  const last = values[values.length - 1];
  if (last != null && last !== 0) {
    dots += '<circle class="spark-dot" cx="' + x(values.length - 1).toFixed(1) + '" cy="' + y(last).toFixed(1) + '" r="2.6"/>';
  }
  return (
    '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><path class="spark-line" vector-effect="non-scaling-stroke" d="' + d + '"/>' + dots + '</svg>'
  );
}

/**
 * Trend area chart for one step over the given runs (newest first).
 * Returns a cleanup-free object with `show(i)` so callers can drive it (used by tests/manual checks).
 */
export function drawTrend(box, statEl, tip, runs, stepDef) {
  const series = runs.slice().reverse(); // oldest -> newest
  const stepName = stepDef.name;
  const vals = series.map((r) => metric(stepOf(r, stepName)));
  const width = box.clientWidth || 900;
  const W = Math.max(320, width);
  const H = width < 600 ? 200 : 240;
  const m = { l: 44, r: 12, t: 12, b: 26 };
  const nums = vals.filter((v) => v != null);
  const max = niceMax(Math.max(...nums, 1));
  const x = (i) => m.l + (i * (W - m.l - m.r)) / Math.max(1, series.length - 1);
  const y = (v) => m.t + (1 - v / max) * (H - m.t - m.b);

  let g = '';
  for (let k = 0; k <= 4; k++) {
    const yy = y((max * k) / 4).toFixed(1);
    g +=
      '<line class="grid-line" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
      '<text class="axis-label" x="' + (m.l - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + compact((max * k) / 4) + '</text>';
  }
  const stepEvery = Math.ceil(series.length / (W < 600 ? 4 : 7));
  series.forEach((r, i) => {
    if ((series.length - 1 - i) % stepEvery === 0) {
      g += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + shortDay(r.startedAt) + '</text>';
    }
  });

  let line = '';
  let area = '';
  let seg = [];
  const pt = (p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1);
  const flush = () => {
    if (!seg.length) return;
    line += 'M' + seg.map(pt).join('L');
    area += 'M' + seg[0][0].toFixed(1) + ' ' + y(0) + 'L' + seg.map(pt).join('L') + 'L' + seg[seg.length - 1][0].toFixed(1) + ' ' + y(0) + 'Z';
    seg = [];
  };
  let pts = '';
  vals.forEach((v, i) => {
    if (v == null) {
      flush();
      pts += '<circle class="pt pt--gap" cx="' + x(i).toFixed(1) + '" cy="' + y(0).toFixed(1) + '" r="3.5"/>';
      return;
    }
    seg.push([x(i), y(v)]);
    const bad = v === 0 && isLoss(stepOf(series[i], stepName));
    pts += '<circle class="pt' + (bad ? ' pt--bad' : '') + '" cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="' + (bad ? 3.5 : 2.5) + '"/>';
  });
  flush();

  box.innerHTML =
    '<svg viewBox="0 0 ' + W + ' ' + H + '" style="height:' + H + 'px" aria-hidden="true">' +
    '<defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--chart-fill-top)"/><stop offset="1" stop-color="var(--chart-fill-bottom)"/></linearGradient></defs>' +
    g + '<path class="area" d="' + area + '"/><path class="line" d="' + line + '"/>' + pts +
    '<line class="cross" id="cross" x1="0" x2="0" y1="' + m.t + '" y2="' + (H - m.b) + '" visibility="hidden"/>' +
    '<circle class="focus-pt" id="focus-pt" r="5" cx="0" cy="0" visibility="hidden"/></svg>';

  const last = series.length - 1;
  const lv = vals[last];
  const pv = vals[last - 1];
  const noOutputNote = stepDef.returnsNothing ? ' · step returns nothing, showing its input' : '';
  statEl.innerHTML =
    '<span class="trend__value num">' + (lv == null ? '—' : fmt(lv)) + '</span>' + deltaChip(lv, pv) +
    '<span class="trend__label">Latest run (' + shortDay(series[last].startedAt) + ') vs previous run' + noOutputNote + '</span>';
  box.setAttribute('aria-label', stepName + ' ' + (stepDef.returnsNothing ? 'input' : 'output') + ' for the last ' + series.length + ' runs. Latest ' + fmt(lv) + '.');

  const cross = box.querySelector('#cross');
  const fp = box.querySelector('#focus-pt');
  const svg = box.querySelector('svg');
  let cur = -1;
  function show(i) {
    cur = i;
    const v = vals[i];
    const cx = x(i);
    const cy = v == null ? y(0) : y(v);
    cross.setAttribute('x1', cx);
    cross.setAttribute('x2', cx);
    cross.setAttribute('visibility', 'visible');
    fp.setAttribute('cx', cx);
    fp.setAttribute('cy', cy);
    fp.setAttribute('visibility', v == null ? 'hidden' : 'visible');
    const prevV = i > 0 ? vals[i - 1] : null;
    tip.innerHTML =
      '<div class="tooltip__date">' + dayLabel(series[i].startedAt) + ' · ' + hhmm(series[i].startedAt) + '</div>' +
      '<div class="tooltip__val num">' + (v == null ? '<span class="faint">not recorded</span>' : fmt(v)) + deltaChip(v, prevV) + '</div>' +
      (v === 0 && isLoss(stepOf(series[i], stepName)) ? '<div style="color:var(--bad);margin-top:4px">Possible data loss</div>' : '');
    tip.hidden = false;
    const r = svg.getBoundingClientRect();
    const sx = r.left + (cx / W) * r.width;
    const sy = r.top + (cy / H) * r.height;
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    const left = Math.min(window.innerWidth - tw - 8, Math.max(8, sx - tw / 2));
    let top = sy - th - 14;
    if (top < 64) top = sy + 14;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hide() {
    tip.hidden = true;
    cross.setAttribute('visibility', 'hidden');
    fp.setAttribute('visibility', 'hidden');
  }
  svg.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, series.length - 1)));
    show(Math.max(0, Math.min(series.length - 1, i)));
  });
  svg.addEventListener('pointerleave', hide);
  box.onkeydown = (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    let i = cur < 0 ? last : cur;
    i = e.key === 'Home' ? 0 : e.key === 'End' ? last : i + (e.key === 'ArrowRight' ? 1 : -1);
    show(Math.max(0, Math.min(last, i)));
  };
  box.onfocus = () => show(cur < 0 ? last : cur);
  box.onblur = hide;
  return { show, hide };
}
