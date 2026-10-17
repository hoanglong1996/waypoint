/* One step as a timeline item (<li>). Used by the run page's list and the graph's "Selected step" panel. */
import { sparkline } from '../chart.js';
import { stepEventsHTML } from './events.js';
import { esc, fmt, hhmmss, isDone, isLoss, metric, metricsOver, stepOf, stepState } from '../model.js';
import {
  I, copyButtonHTML, deltaChip, durationHTML, elapsedHTML, lossPill, metricBadgeHTML, metricsTableHTML,
} from '../ui.js';

const svgClass = (svg, cls) => svg.replace('<svg', '<svg class="' + cls + '"');

/** The error of a failed step: type, message when stored, and the stack trace (scrollable, copyable). */
export function errorBlockHTML(run, s, compact) {
  const e = s.error;
  const head = '<span class="step__error-type mono">' + esc(e.type) + '</span>' +
    (e.message != null ? '<span class="step__error-msg">' + esc(e.message) + '</span>' : '<span class="step__error-msg faint">message not stored</span>');
  if (compact) return '<div class="step__error step__error--compact">' + head + '</div>';
  const copy = e.type + (e.message != null ? ': ' + e.message : '') + '\n\n' + e.traceback;
  return '<div class="step__error" role="group" aria-label="Error">' +
    '<div class="step__error-head"><div class="step__error-title">' + head + '</div>' +
    copyButtonHTML(run.env + '|' + run.id + '|' + s.name, copy) + '</div>' +
    (e.traceback ? '<pre class="step__trace" tabindex="0" aria-label="Stack trace">' + esc(e.traceback) + '</pre>' : '') + '</div>';
}

export function stepItemHTML(run, runs, cfg, i, compact) {
  const idx = runs.indexOf(run);
  const prev = runs[idx + 1];
  const hist = runs.slice(idx, idx + 14).reverse();
  const maxOut = Math.max(...run.steps.map((s) => metric(s) || 0), 1);
  const s = run.steps[i];
  const def = run.defs[i];
  const unplanned = stepState(s) === 'unplanned';
  let html = '';
  const loss = isLoss(s);
  const live = stepState(s);
  const died = live === 'died';
  const failed = live === 'failed';
  const isLive = live === 'running' || live === 'waiting' || live === 'stalled';
  const missing = !!s.missing;
  const state = missing ? 'missing' : isLive || died || failed ? live : loss ? 'loss' : 'ok';
  const nodeInner = failed ? I.failed : missing || isLive || died ? i + 1 : loss ? '!' : i + 1;
  const statusText = missing ? 'not recorded' : isLive || died || failed ? live : loss ? 'possible data loss' : 'ok';
  const name = esc(def.label && def.label !== s.name ? def.label + ' · ' + s.name : s.name);

  html += '<li class="step step--' + state + '"><div class="step__rail" aria-hidden="true"><span class="step__node">' + nodeInner + '</span></div>';
  html += '<article class="step__card" aria-label="Step ' + (i + 1) + ', ' + name + ', ' + statusText + '">';

  html += '<div class="step__name"><div class="step__title">' + name + '</div><div class="step__time">';
  if (missing) html += '<span>No record</span>';
  else if (live === 'waiting') html += '<span>Not started</span>';
  else if (failed) {
    html += '<span>Started ' + (s.startedAt ? hhmmss(s.startedAt) : '') + ' · failed ' + (s.failedAt ? hhmmss(s.failedAt) : '') + '</span>';
    if (s.durationSeconds != null) html += '<span class="step__dur">' + I.stopwatch.replace('<svg', '<svg class="ico--sm" style="width:12px;height:12px"') + durationHTML(s.durationSeconds, { approx: s.durationApprox }) + '</span>';
  }
  else if (isLive || died) html += '<span>Started ' + (s.startedAt ? hhmmss(s.startedAt) : '') + '</span>';
  else if (!s.finishedAt) html += '<span>No finish time</span>';
  else {
    html += '<span title="Finished at">' + I.check.replace('<svg', '<svg class="ico--sm" style="width:12px;height:12px"') + '</span><span>' + hhmmss(s.finishedAt) + '</span>';
    if (s.durationSeconds != null) html += '<span class="step__dur">' + I.stopwatch.replace('<svg', '<svg class="ico--sm" style="width:12px;height:12px"') + durationHTML(s.durationSeconds, { approx: s.durationApprox }) + '</span>';
  }
  if (loss) html += lossPill(1, 'sm');
  html += metricBadgeHTML(metricsOver(s));
  if (unplanned) html += '<span class="pill pill--neutral pill--sm" title="Reported, but not in this run’s flow description">not in flow</span>';
  html += '</div></div>';

  html += '<div class="step__inputs" aria-label="Inputs">';
  if (died || failed) {
    html += '<span class="chip chip--none">input not recorded</span>';
  } else if (live === 'running' || live === 'stalled') {
    html += '<span class="chip chip--none">input pending</span>';
  } else if (missing || live === 'waiting') {
    if (def.inputs.length) def.inputs.forEach((p) => { html += '<span class="chip chip--none">expects ' + esc(p.name) + '</span>'; });
    else html += '<span class="chip chip--none">input none</span>';
  } else if (!s.inputs.length) {
    html += '<span class="chip chip--none">input none</span>';
  } else {
    s.inputs.forEach((inp, k) => {
      const from = def.inputs[k] ? ' title="from ' + esc(def.inputs[k].from) + '"' : '';
      html += '<span class="chip"' + from + '>' + I.arrowIn + esc(inp.name) + ' <b>' + fmt(inp.value) + '</b></span>';
    });
  }
  html += '</div>';

  if (live === 'running') {
    html += '<div class="step__live"><span class="step__live-text">' + I.spinner + '<span>Running · ' + elapsedHTML(s) + '</span></span>' +
      '<div class="step__progress" aria-hidden="true"><i></i></div></div>';
  } else if (failed) {
    html += '<div class="step__live"><span class="step__live-text">' + I.failed + '<span>Failed</span></span>' +
      '<span class="step__live-sub">the step raised an error</span></div>' + errorBlockHTML(run, s, compact);
  } else if (died) {
    html += '<div class="step__live"><span class="step__live-text">' + I.power + '<span>Died · last seen ' + (s.lastSeenAt ? hhmmss(s.lastSeenAt) : 'unknown') + '</span></span>' +
      '<span class="step__live-sub">process gone</span></div>';
  } else if (live === 'stalled') {
    html += '<div class="step__live"><span class="step__live-text">' + I.alert + '<span>Stalled · ' + elapsedHTML(s) + '</span></span>' +
      '<span class="step__live-sub">alive but not progressing</span></div>';
  } else if (live === 'waiting') {
    html += '<div class="step__live"><span class="step__live-text">' + I.hourglass + '<span>Waiting</span></span></div>';
  } else if (missing) {
    html += '<div class="step__missing-msg">' + svgClass(I.gap, 'ico') + '<span>Step did not report for this run</span></div>';
  } else {
    const m = metric(s);
    const pm = prev ? metric(stepOf(prev, s.name)) : null;
    const barW = m ? Math.max(4, (Math.log10(m + 1) / Math.log10(maxOut + 1)) * 100) : 0;
    html += '<div class="step__output">';
    if (s.output == null) {
      html += '<div class="step__count step__count--na num">n/a</div><div class="step__sub">returns nothing</div>';
    } else {
      html += '<div class="step__count num">' + fmt(s.output) + '</div><div class="step__sub"><span>output</span>' + (compact ? '' : deltaChip(m, pm)) + '</div>';
      if (!compact) html += '<div class="step__bar" aria-hidden="true"><i style="width:' + barW.toFixed(1) + '%"></i></div>';
    }
    html += '</div>';
  }

  if (!missing && live !== 'waiting') html += metricsTableHTML(s, def);

  if (!compact) {
    const vals = hist.map((r) => metric(stepOf(r, s.name)));
    html += '<div class="step__spark" title="Last ' + vals.length + ' runs">' + sparkline(vals) +
      '<div class="spark-cap">' + (s.output == null && isDone(s) ? 'input · ' : '') + vals.length + ' runs</div></div>';
  }
  if (!missing && live !== 'waiting' && run.pipeline) html += stepEventsHTML(run, s.name);
  html += '</article></li>';
  return html;
}
