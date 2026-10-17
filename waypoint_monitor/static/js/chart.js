/* Hand-drawn SVG charts, themed through CSS variables. */
import {
  compact, dayLabel, fmt, fmtDuration, esc, formatMetricValue, hhmm, isLoss, metric, niceMax, shortDay, stepOf,
} from './model.js';
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


/**
 * "Run duration" chart: one point per run (`series` from `durationSeries`, oldest first), a dashed median
 * line, a band up to the 95th percentile and a diamond with the word "slow" on flagged runs, so the flag is
 * not told by colour alone. Same keyboard and pointer behaviour as `drawTrend`.
 */
/** Smallest axis maximum, in seconds, whose quarters are round (1m, 5m, 15m, 1h ...). */
const DURATION_MAXES = [4, 8, 12, 20, 40, 60, 120, 240, 480, 600, 1200, 2400, 3600, 7200, 14400, 28800, 43200, 86400];
export function niceDurationMax(v) {
  const hit = DURATION_MAXES.find((m) => m >= v);
  return hit || Math.ceil(v / 86400) * 86400;
}

export function drawDuration(box, statEl, tip, series) {
  const pts = series.points;
  const width = box.clientWidth || 900;
  const W = Math.max(320, width);
  const H = width < 600 ? 200 : 240;
  const m = { l: 54, r: 12, t: 12, b: 26 };
  const known = pts.map((p) => p.seconds).filter((v) => v != null);
  const max = niceDurationMax(Math.max(...known, series.p95 || 0, 1) * 1.08);
  const x = (i) => m.l + (i * (W - m.l - m.r)) / Math.max(1, pts.length - 1);
  const y = (v) => m.t + (1 - v / max) * (H - m.t - m.b);

  let g = '';
  for (let k = 0; k <= 4; k++) {
    const yy = y((max * k) / 4).toFixed(1);
    g +=
      '<line class="grid-line" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
      '<text class="axis-label" x="' + (m.l - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + fmtDuration((max * k) / 4) + '</text>';
  }
  const every = Math.ceil(pts.length / (W < 600 ? 4 : 7));
  pts.forEach((p, i) => {
    if ((pts.length - 1 - i) % every === 0) {
      g += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + shortDay(p.startedAt) + '</text>';
    }
  });

  let band = '';
  let lines = '';
  if (series.enough) {
    const top = y(series.p95).toFixed(1);
    const mid = y(series.median).toFixed(1);
    band = '<rect class="dband" x="' + m.l + '" y="' + top + '" width="' + (W - m.l - m.r) + '" height="' + Math.max(0, mid - top).toFixed(1) + '"/>';
    lines =
      '<line class="dmedian" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + mid + '" y2="' + mid + '"/>' +
      '<text class="axis-label dlabel" x="' + (m.l + 6) + '" y="' + (Number(mid) - 4) + '" text-anchor="start">median ' + fmtDuration(series.median) + '</text>' +
      '<text class="axis-label dlabel" x="' + (m.l + 6) + '" y="' + (Number(top) - 4) + '" text-anchor="start">p95 ' + fmtDuration(series.p95) + '</text>';
  }

  let line = '';
  let seg = [];
  const flush = () => {
    if (seg.length) line += 'M' + seg.map((p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L');
    seg = [];
  };
  let dots = '';
  pts.forEach((p, i) => {
    if (p.seconds == null) {
      flush();
      dots += '<circle class="pt pt--gap" cx="' + x(i).toFixed(1) + '" cy="' + y(0).toFixed(1) + '" r="3.5"/>';
      return;
    }
    seg.push([x(i), y(p.seconds)]);
    const cx = x(i).toFixed(1);
    const cy = y(p.seconds).toFixed(1);
    if (p.slow) {
      dots += '<path class="pt pt--slow" d="M' + cx + ' ' + (cy - 6) + 'L' + (Number(cx) + 6) + ' ' + cy + 'L' + cx + ' ' + (Number(cy) + 6) + 'L' + (Number(cx) - 6) + ' ' + cy + 'Z"/>' +
        '<text class="axis-label dslow" x="' + cx + '" y="' + (cy - 10) + '" text-anchor="middle">slow</text>';
    } else {
      dots += '<circle class="pt' + (p.complete ? '' : ' pt--open') + '" cx="' + cx + '" cy="' + cy + '" r="2.5"/>';
    }
  });
  flush();

  box.innerHTML =
    '<svg viewBox="0 0 ' + W + ' ' + H + '" style="height:' + H + 'px" aria-hidden="true">' + g + band + lines +
    '<path class="line" d="' + line + '"/>' + dots +
    '<line class="cross" id="dcross" x1="0" x2="0" y1="' + m.t + '" y2="' + (H - m.b) + '" visibility="hidden"/></svg>';

  const last = pts.length - 1;
  const lp = pts[last];
  statEl.innerHTML = series.enough
    ? '<span class="trend__value num">' + fmtDuration(series.median) + '</span><span class="trend__label">Typical (median) · slow end ' +
      fmtDuration(series.p95) + ' · ' + 'over the newest completed runs</span>'
    : '<span class="trend__label">' + series.note + '</span>';
  box.setAttribute('aria-label', 'Run duration for the last ' + pts.length + ' runs. Latest ' + fmtDuration(lp ? lp.seconds : null, { running: lp && lp.running }) + '.' +
    (series.enough ? ' Typical ' + fmtDuration(series.median) + '.' : ''));

  const cross = box.querySelector('#dcross');
  const svg = box.querySelector('svg');
  let cur = -1;
  function show(i) {
    cur = i;
    const p = pts[i];
    const cx = x(i);
    cross.setAttribute('x1', cx);
    cross.setAttribute('x2', cx);
    cross.setAttribute('visibility', 'visible');
    tip.innerHTML =
      '<div class="tooltip__date">' + dayLabel(p.startedAt) + ' · ' + hhmm(p.startedAt) + '</div>' +
      '<div class="tooltip__val num">' + (p.seconds == null ? '<span class="faint">unavailable</span>' : fmtDuration(p.seconds, { running: p.running })) + '</div>' +
      (series.enough ? '<div class="faint">median ' + fmtDuration(series.median) + '</div>' : '') +
      (p.slow ? '<div style="color:var(--warn);margin-top:4px">Slower than usual</div>' : '') +
      (!p.complete && p.seconds != null && !p.running ? '<div class="faint">not completed: not part of the typical value</div>' : '');
    tip.hidden = false;
    const cy = p.seconds == null ? y(0) : y(p.seconds);
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
  }
  svg.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, pts.length - 1)));
    show(Math.max(0, Math.min(last, i)));
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

/**
 * One declared metric across runs (specs/013 contracts/ui.md). `trend` is `metricTrend(...)`: points oldest to
 * newest (null = not reported, a gap), a dashed median line when there is one, a dotted line per limit, and a
 * diamond marker (not colour alone) on a point over a limit. Arrow keys move between runs like the other charts.
 */
export function drawMetricTrend(box, statEl, tip, trend) {
  const pts = trend.points;
  const width = box.clientWidth || 900;
  const W = Math.max(320, width);
  const H = width < 600 ? 200 : 240;
  const m = { l: 54, r: 12, t: 12, b: 26 };
  const known = pts.map((p) => p.value).filter((v) => v != null);
  const limits = [trend.warnAbove, trend.warnBelow].filter((v) => v != null);
  const hi = Math.max(...known, ...limits, trend.median == null ? 0 : trend.median, 1);
  const lo = Math.min(0, ...known, ...limits);
  const max = niceMax(hi * 1.08);
  const min = lo < 0 ? -niceMax(-lo * 1.08) : 0;
  const x = (i) => m.l + (i * (W - m.l - m.r)) / Math.max(1, pts.length - 1);
  const y = (v) => m.t + (1 - (v - min) / (max - min)) * (H - m.t - m.b);
  const unit = trend.unit;

  let g = '';
  for (let k = 0; k <= 4; k++) {
    const v = min + ((max - min) * k) / 4;
    const yy = y(v).toFixed(1);
    g += '<line class="grid-line" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
      '<text class="axis-label" x="' + (m.l - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + formatMetricValue(v) + '</text>';
  }
  const every = Math.ceil(pts.length / (W < 600 ? 4 : 7));
  pts.forEach((p, i) => {
    if ((pts.length - 1 - i) % every === 0) {
      g += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + shortDay(p.startedAt) + '</text>';
    }
  });

  let lines = '';
  // the median label sits at the right end and the limit labels at the left, so they do not overlap
  const hline = (cls, v, text) => {
    const yy = y(v).toFixed(1);
    const right = cls === 'mmedian';
    lines += '<line class="' + cls + '" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
      '<text class="axis-label dlabel" x="' + (right ? W - m.r - 6 : m.l + 6) + '" y="' + (right ? Number(yy) + 12 : Number(yy) - 4) + '" text-anchor="' + (right ? 'end' : 'start') + '">' + text + '</text>';
  };
  if (trend.median != null) hline('mmedian', trend.median, 'median ' + formatMetricValue(trend.median, unit));
  if (trend.warnAbove != null) hline('mlimit', trend.warnAbove, 'warn above ' + formatMetricValue(trend.warnAbove, unit));
  if (trend.warnBelow != null) hline('mlimit', trend.warnBelow, 'warn below ' + formatMetricValue(trend.warnBelow, unit));

  let line = '';
  let seg = [];
  const flush = () => {
    if (seg.length) line += 'M' + seg.map((p) => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L');
    seg = [];
  };
  let dots = '';
  pts.forEach((p, i) => {
    const cx = x(i).toFixed(1);
    if (p.value == null) {
      flush();
      dots += '<circle class="pt pt--gap" cx="' + cx + '" cy="' + y(min).toFixed(1) + '" r="3.5"/>';
      return;
    }
    seg.push([x(i), y(p.value)]);
    const cy = y(p.value).toFixed(1);
    dots += p.flag
      ? '<path class="pt pt--over" d="M' + cx + ' ' + (cy - 6) + 'L' + (Number(cx) + 6) + ' ' + cy + 'L' + cx + ' ' + (Number(cy) + 6) + 'L' + (Number(cx) - 6) + ' ' + cy + 'Z"/>'
      : '<circle class="pt" cx="' + cx + '" cy="' + cy + '" r="2.5"/>';
  });
  flush();

  box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="height:' + H + 'px" aria-hidden="true">' + g + lines +
    '<path class="line" d="' + line + '"/>' + dots +
    '<line class="cross" id="mcross" x1="0" x2="0" y1="' + m.t + '" y2="' + (H - m.b) + '" visibility="hidden"/></svg>';

  const last = pts.length - 1;
  const lp = pts[last];
  statEl.innerHTML = trend.median != null
    ? '<span class="trend__value num">' + esc(formatMetricValue(trend.median, unit)) + '</span><span class="trend__label">Median over the newest ' + trend.sample + ' runs that reported it</span>'
    : '<span class="trend__label">' + esc(trend.note) + '</span>';
  box.setAttribute('aria-label', (trend.label || 'Metric') + ' for the last ' + pts.length + ' runs. Latest ' +
    (lp && lp.value != null ? formatMetricValue(lp.value, unit) : 'not reported') + '.' +
    (trend.median != null ? ' Median ' + formatMetricValue(trend.median, unit) + '.' : ''));

  const cross = box.querySelector('#mcross');
  const svg = box.querySelector('svg');
  let cur = -1;
  function show(i) {
    cur = i;
    const p = pts[i];
    const cx = x(i);
    cross.setAttribute('x1', cx);
    cross.setAttribute('x2', cx);
    cross.setAttribute('visibility', 'visible');
    tip.innerHTML = '<div class="tooltip__date">' + dayLabel(p.startedAt) + ' · ' + hhmm(p.startedAt) + '</div>' +
      '<div class="tooltip__val num">' + (p.value == null ? '<span class="faint">not reported</span>' : esc(formatMetricValue(p.value, unit))) + '</div>' +
      (trend.median != null ? '<div class="faint">median ' + esc(formatMetricValue(trend.median, unit)) + '</div>' : '') +
      (p.flag ? '<div style="color:var(--warn);margin-top:4px">Over the limit (' + p.flag + ')</div>' : '');
    tip.hidden = false;
    const cy = p.value == null ? y(min) : y(p.value);
    const r = svg.getBoundingClientRect();
    const sx = r.left + (cx / W) * r.width;
    const sy = r.top + (cy / H) * r.height;
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - tw - 8, Math.max(8, sx - tw / 2)) + 'px';
    let top = sy - th - 14;
    if (top < 64) top = sy + 14;
    tip.style.top = top + 'px';
  }
  function hide() {
    tip.hidden = true;
    cross.setAttribute('visibility', 'hidden');
  }
  svg.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, pts.length - 1)));
    show(Math.max(0, Math.min(last, i)));
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
