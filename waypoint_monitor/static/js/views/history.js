/* History view: step trend chart and the runs list. A run opens as its own page (views/run.js). */
import { drawTrend } from '../chart.js';
import {
  HEADLINE_TITLE, analyse, dayLabel, dur, esc, fmt, headline, hhmm, runRoute,
} from '../model.js';
import { buildRoute } from '../router.js';
import {
  I, emptyHTML, lossPill, statusPill, unreadablePill,
} from '../ui.js';

let trendStep = null;
let ctx = { runs: [], cfg: null };

const $ = (id) => document.getElementById(id);

/** Every step seen in these runs (newest run first, then older runs' extra steps), for the trend picker. */
export function trendSteps(runs) {
  const seen = new Map();
  runs.forEach((r) => r.defs.forEach((d) => { if (!seen.has(d.name)) seen.set(d.name, d); }));
  return [...seen.values()];
}

/** The "Environment" filter card above the trend: a radio group of the pipeline's environments. */
export function envBarHTML(info, count) {
  const opt = (c) =>
    '<label class="segmented__opt"><input type="radio" name="env" value="' + esc(c.env) + '"' + (c.env === info.applied ? ' checked' : '') + '><span>' + esc(c.env) +
    (c.hasRuns ? '' : '<small class="segmented__hint">no runs</small>') + '</span></label>';
  return (
    '<section class="card envbar" aria-label="Environment filter">' +
    '<div class="envbar__field"><span class="envbar__label" id="env-label">Environment</span>' +
    '<div class="segmented segmented--env" role="radiogroup" aria-labelledby="env-label">' + info.choices.map(opt).join('') + '</div></div>' +
    '<p class="envbar__note">' + (count
      ? 'Showing <b>' + count + '</b> ' + esc(info.applied) + ' run' + (count === 1 ? '' : 's') + '. The trend and the runs list use this environment.'
      : 'No ' + esc(info.applied) + ' runs for this pipeline.') + '</p></section>'
  );
}

function noRunsEnvHTML(info) {
  return (
    '<section class="card empty" role="status"><div class="empty__art">' + I.inbox + '</div>' +
    '<h2>No runs in this environment</h2><p>' + esc(info.label) + ' has no runs in <span class="env-tag">' + esc(info.applied) + '</span> yet. Choose another environment above.</p></section>'
  );
}

function wireEnv(el, info) {
  el.querySelectorAll('input[name="env"]').forEach((r) =>
    r.addEventListener('change', () => info.onChange(r.value)),
  );
}

/**
 * `envInfo` = {choices, applied, label, pipelineId, onChange}: the environment filter. The runs are already the
 * ones of the applied environment, so the trend and the list follow it.
 */
export function renderHistory(el, runs, cfg, envInfo) {
  ctx = { runs, cfg };
  const bar = envInfo ? envBarHTML(envInfo, runs.length) : '';
  if (!runs.length) {
    el.innerHTML = bar + (envInfo ? noRunsEnvHTML(envInfo) : emptyHTML());
    if (envInfo) wireEnv(el, envInfo);
    return;
  }
  const choices = trendSteps(runs);
  if (!choices.some((s) => s.name === trendStep)) trendStep = choices.length ? choices[0].name : null;
  const opts = choices
    .map((s) => '<option value="' + esc(s.name) + '"' + (s.name === trendStep ? ' selected' : '') + '>' + esc(s.name) + '</option>')
    .join('');

  const num = (v, lbl) =>
    '<span class="run-row__n' + (v == null ? ' run-row__n--na' : '') + '"><span class="run-row__lbl">' + lbl + '</span>' + (v == null ? '—' : fmt(v)) + '</span>';
  const pipelineId = (envInfo && envInfo.pipelineId) || runs[0].pipeline;
  const rows = runs
    .map((r, i) => {
      const a = analyse(r);
      const h = headline(r);
      return (
        '<li><a class="run-row" href="' + esc(buildRoute(runRoute(pipelineId, r))) + '" data-id="' + esc(r.id) + '">' +
        '<span class="run-row__date">' + dayLabel(r.startedAt) + (i === 0 ? '<span class="tag-new">Newest</span>' : '') + '<small>' + hhmm(r.startedAt) + ' · ' + dur(a.durationS) + '</small></span>' +
        '<span class="run-row__status">' + statusPill(a, 'sm') + '</span>' +
        h.map((k) => num(k.value, HEADLINE_TITLE[k.key])).join('') +
        '<span class="run-row__flags">' + (a.loss.length ? lossPill(a.loss.length, 'sm') : '') + unreadablePill(r.unreadable) + '</span>' +
        I.chev + '</a></li>'
      );
    })
    .join('');

  el.innerHTML = bar +
    '<section class="card trend" aria-labelledby="trend-title"><div class="trend__head">' +
    '<div class="trend__pick"><h2 class="section-title" id="trend-title">Step trend</h2>' +
    '<label for="trend-step">Step</label><select id="trend-step" class="select">' + opts + '</select></div>' +
    '<div class="trend__stat" id="trend-stat"></div></div>' +
    '<div class="chart" id="chart" tabindex="0" role="img" aria-roledescription="line chart"></div>' +
    '<div class="chart__legend"><span><i class="lg-dot"></i>value per run</span><span><i class="lg-dot lg-dot--bad"></i>0 with input (possible loss)</span><span><i class="lg-dot lg-dot--gap"></i>step not recorded</span><span>Use ← → to move between runs</span></div></section>' +
    '<section class="card runs" aria-labelledby="runs-title">' +
    '<div class="section-head" style="padding:16px 20px"><h2 class="section-title" id="runs-title">Runs</h2><span class="faint" style="font-size:12px">' + runs.length + ' runs · newest first</span></div>' +
    '<div class="runs__head" aria-hidden="true"><span>Run</span><span>Status</span>' + ['first', 'peak', 'last'].map((k) => '<span class="r">' + HEADLINE_TITLE[k] + '</span>').join('') + '<span>Flags</span><span></span></div>' +
    '<ul class="runs__list">' + rows + '</ul></section>';

  if (envInfo) wireEnv(el, envInfo);
  $('trend-step').addEventListener('change', (e) => {
    trendStep = e.target.value;
    redrawTrend();
  });
  redrawTrend();
}

export function redrawTrend() {
  const box = $('chart');
  if (!box || !ctx.runs.length) return;
  const def = trendSteps(ctx.runs).find((s) => s.name === trendStep);
  if (!def) return;
  drawTrend(box, $('trend-stat'), $('tooltip'), ctx.runs, def);
}
