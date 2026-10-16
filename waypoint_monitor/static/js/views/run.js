/* Run page: hero, flow strip and the steps timeline of one run (the former Latest page). */
import {
  HEADLINE_TITLE, analyse, ago, dayLabel, dur, esc, fmt, groupLabel, headline, heroTitle, hhmm, isDone, isLoss,
  isNewest, stepOf, stepState, metric,
} from '../model.js';
import {
  I, deltaChip, envTag, getStepsView, lossPill, stalePill, statusPill, stepsHeadHTML,
} from '../ui.js';
import { mountGraph } from './graph.js';
import { stepItemHTML } from './step.js';

const svgClass = (svg, cls) => svg.replace('<svg', '<svg class="' + cls + '"');

export { stepItemHTML };

export function stepsHTML(run, runs, cfg, compact) {
  let group = null;
  let html = '<ol class="steps' + (compact ? ' steps--compact' : '') + '">';
  run.steps.forEach((s, i) => {
    const def = run.defs[i];
    const g = def.unplanned ? '' : def.group || '';
    if (g !== group) {
      group = g;
      const title = g ? groupLabel(run, g) : def.unplanned ? 'Not in this run’s flow' : '';
      if (title) html += '<li class="steps__group" aria-hidden="true"><span class="eyebrow">' + esc(title) + '</span></li>';
    }
    html += stepItemHTML(run, runs, cfg, i, compact);
  });
  return html + '</ol>';
}

export function heroHTML(run, runs, cfg) {
  const a = analyse(run);
  const h = headline(run);
  const prev = runs[runs.indexOf(run) + 1];
  const newest = isNewest(runs, run);
  const title = heroTitle(a, newest);
  const total = run.steps.length;
  let why = '';
  if (a.died) {
    why = '<p class="hero__why">The process stopped sending signs of life' + (a.lastSeenAt ? ' after ' + hhmm(a.lastSeenAt) + ' (last seen ' + ago((Date.now() - a.lastSeenAt.getTime()) / 3600000) + ')' : '') +
      ', so it is not just slow. First missing step: <code>' + esc(a.firstMissing) + '</code>. ' + a.missingCount + ' of ' + total + ' steps did not report, so statistics were not saved for this run.</p>';
  } else if (a.running) {
    why = a.runningStep
      ? '<p class="hero__why">Running now: <code>' + esc(a.runningStep) + '</code>. The page updates by itself every few seconds.</p>'
      : '<p class="hero__why">Started, waiting for the first step to report. The page updates by itself every few seconds.</p>';
  } else if (!a.complete) {
    why = '<p class="hero__why">First missing step: <code>' + esc(a.firstMissing) + '</code>. ' + a.missingCount + ' of ' + total + ' steps did not report, so statistics were not saved for this run.</p>';
  } else if (a.loss.length) {
    why = '<p class="hero__why"><code>' + esc(a.loss[0]) + '</code> received input but produced 0 items. Downstream steps ran, but their counts may be incomplete.</p>';
  }

  const kpi = (label, v, pv, missingTxt, stepLabel) =>
    '<div class="kpi' + (v == null ? ' kpi--missing' : '') + '"><span class="eyebrow">' + label + (stepLabel ? ' · ' + esc(stepLabel) : '') + '</span>' +
    '<span class="kpi__value num">' + (v == null ? '—' : fmt(v)) + '</span>' +
    '<span class="kpi__foot">' + (v == null ? '<span class="faint" style="font-size:12px">' + missingTxt + '</span>' : deltaChip(v, pv)) + '</span></div>';

  const cells = run.steps.map((s, i) => {
    const live = stepState(s);
    const isLive = live === 'running' || live === 'waiting' || live === 'stalled' || live === 'died';
    const st = s.missing ? 'missing' : isLive ? live : isLoss(s) ? 'loss' : 'ok';
    const label = s.name + ': ' + (st === 'missing' ? 'not recorded' : isLive ? live : st === 'loss' ? 'possible data loss' : 'ok');
    const ico = st === 'ok' ? I.check : st === 'running' ? I.spinner : st === 'died' ? I.power : st === 'loss' ? '!' : i + 1;
    return '<li class="flow__cell flow__cell--' + st + '" title="' + esc(label) + '"><span class="sr-only">' + esc(label) + '</span><span aria-hidden="true">' + ico + '</span></li>';
  }).join('');

  // group labels sized by how many consecutive steps each group has
  const groups = [];
  run.defs.forEach((d) => {
    const key = d.unplanned ? '' : d.group || '';
    if (groups.length && groups[groups.length - 1].key === key) groups[groups.length - 1].n++;
    else groups.push({ key, n: 1 });
  });
  const groupLabels = groups.map((g) => '<span>' + esc(g.key ? groupLabel(run, g.key) : '') + '</span>').join('');
  const groupCols = groups.map((g) => g.n + 'fr').join(' ');
  const reported = run.steps.filter(isDone).length;

  return (
    '<section class="card hero" aria-labelledby="hero-title"><div>' +
    '<div class="hero__status">' + statusPill(a, 'lg') + envTag(run.env, true) + (a.loss.length ? lossPill(a.loss.length, 'lg') : '') + (a.stale && newest ? stalePill(a) : '') + '</div>' +
    '<h1 class="hero__title" id="hero-title" tabindex="-1">' + title + '</h1>' +
    '<div class="hero__meta">' +
    '<span>' + I.calendar + dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · started ' + hhmm(run.startedAt) + '</span>' +
    (a.running || a.died ? '' : '<span>' + I.clock + 'finished ' + ago(a.ageH) + '</span><span>' + I.timer + dur(a.durationS) + '</span>') +
    '</div>' + why + '</div>' +
    '<div class="kpis">' + h.map((k) => {
      const prevStep = prev && k.step ? stepOf(prev, k.step) : null;
      return kpi(HEADLINE_TITLE[k.key], k.value, prevStep ? metric(prevStep) : null, a.running ? 'in progress' : 'not reported', k.label);
    }).join('') + '</div>' +
    '<div class="flow"><div class="flow__groups" style="grid-template-columns:' + groupCols + '" aria-hidden="true">' + groupLabels + '</div>' +
    '<ol class="flow__cells" aria-label="Step map" style="grid-template-columns:repeat(' + Math.max(1, run.steps.length) + ',minmax(0,1fr))">' + cells + '</ol>' +
    '<div class="flow__legend"><span>' + reported + ' of ' + total + ' steps reported</span>' +
    (a.loss.length ? '<span>' + a.loss.length + ' with possible data loss</span>' : '') + '</div></div></section>'
  );
}

/** The page of one run (`run` is one of `runs`, which are newest first and of the same environment). */
export function renderRun(el, run, runs, cfg) {
  if (getStepsView() === 'graph') {
    el.innerHTML = heroHTML(run, runs, cfg) + stepsHeadHTML('steps-view-run', 'Select a step to trace it') +
      '<section class="card graph-panel" id="run-graph" aria-label="Pipeline graph"></section>' +
      '<section class="card graph-details" id="run-graph-details" aria-live="polite" hidden></section>';
    mountGraph(document.getElementById('run-graph'), {
      cfg, run, runs, mode: 'run', details: document.getElementById('run-graph-details'),
    });
  } else {
    el.innerHTML = heroHTML(run, runs, cfg) + stepsHeadHTML('steps-view-run', 'Output per step · sparkline = last 14 runs') + stepsHTML(run, runs, cfg, false);
  }
}
