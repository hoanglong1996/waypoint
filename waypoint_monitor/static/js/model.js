/* Pure rules and formatting. No DOM access, so it can be unit-tested with `node --test`. */

export const STALE_FALLBACK_HOURS = 26;

export function stepOf(run, name) {
  for (const s of run.steps) if (s.name === name) return s;
  return null;
}

/**
 * A step's state: done, missing, running, stalled, died, failed, waiting or unplanned (reported, but not in the run's
 * flow description). Payloads without `state` (older servers) fall back to missing/done.
 */
export function stepState(step) {
  return step.state || (step.missing ? 'missing' : 'done');
}
export const isDone = (step) => !!step && stepState(step) === 'done';
/** Done or unplanned: the step reported counts. */
export const hasCounts = (step) => !!step && (stepState(step) === 'done' || stepState(step) === 'unplanned');

/** A step has possible data loss when it output exactly 0 but received input. */
export function isLoss(step) {
  if (!isDone(step) || step.output !== 0) return false;
  return step.inputs.some((i) => i.value > 0);
}

/** The value plotted/compared for a step: its output, or its first input when it returns nothing. */
export function metric(step) {
  if (!hasCounts(step)) return null;
  if (step.output != null) return step.output;
  return step.inputs[0] ? step.inputs[0].value : null;
}

/**
 * The three numbers shown for a run, taken from its own steps (no step names are built in):
 * the first step that reported, the step with the largest metric, and the last step that reported.
 * Each is {key, step, label, value}; `key` is the same for every run so values can be compared across runs.
 */
export const HEADLINE_KEYS = ['first', 'peak', 'last'];
export function headline(run) {
  const reported = run.steps.map((s, i) => ({ s, i })).filter(({ s }) => isDone(s));
  const defs = run.defs || [];
  const label = (i) => (defs[i] && defs[i].label) || run.steps[i].name;
  const pick = (key, entry) => ({
    key,
    step: entry ? entry.s.name : null,
    label: entry ? label(entry.i) : null,
    value: entry ? metric(entry.s) : null,
  });
  const withValue = reported.filter(({ s }) => metric(s) != null);
  const peak = withValue.reduce((best, e) => (!best || metric(e.s) > metric(best.s) ? e : best), null);
  return [
    pick('first', reported[0]),
    pick('peak', peak),
    pick('last', withValue.length ? withValue[withValue.length - 1] : null),
  ];
}
/** Column titles for the three headline numbers. */
export const HEADLINE_TITLE = { first: 'First step', peak: 'Largest step', last: 'Last step' };

/** Group keys of a run's flow in declared order, then any group used by a step but not declared. */
export function groupKeys(run) {
  const keys = run.flow ? run.flow.groups.map((g) => g.key) : [];
  (run.defs || []).forEach((d) => { if (d.group && !keys.includes(d.group)) keys.push(d.group); });
  return keys;
}
export function groupLabel(run, key) {
  const g = run.flow ? run.flow.groups.find((x) => x.key === key) : null;
  return g ? g.label : key;
}
/** Colour slot (0-7) of a group, by declared order; steps without a group use slot 3. */
export const GROUP_SLOTS = 8;
export function groupSlot(run, key) {
  const i = key ? groupKeys(run).indexOf(key) : -1;
  return i < 0 ? 3 : i % GROUP_SLOTS;
}

/** Status flags come from the API; this only reshapes them for the views. */
export function analyse(run) {
  return {
    complete: run.status === 'complete',
    running: run.status === 'running',
    runningStep: run.runningStep || null,
    firstMissing: run.firstMissingStep,
    missingCount: run.missingCount,
    loss: run.lossSteps,
    endedAt: run.endedAt,
    durationS: run.durationSeconds,
    stale: run.stale,
    ageH: run.ageSeconds / 3600,
    died: !!run.died,
    lastSeenAt: run.died ? run.died.lastSeenAt : null,
    failed: run.failed || null,
    duration: run.duration || null,
    bottleneck: run.bottleneck || null,
    bottleneckShare: bottleneckShare(run),
  };
}

/** The pill text of a slow run: how long it took against the typical duration. */
export function slowText(run, typical) {
  const d = run.duration;
  const took = d ? fmtDuration(d.seconds, { running: d.running }) : null;
  if (!typical || took == null) return 'Slower than usual';
  return 'Slower than usual: ' + took + ' vs ' + fmtDuration(typical.medianSeconds) + ' typical';
}

/**
 * Points of the "Run duration" chart, oldest first (`runs` are newest first), plus the median and
 * 95th-percentile lines. `minRuns` only words the note shown when there is no typical value yet.
 */
export function durationSeries(runs, typical, minRuns = 5) {
  const points = runs.slice().reverse().map((r) => ({
    id: r.id,
    startedAt: r.startedAt,
    seconds: r.duration ? r.duration.seconds : null,
    slow: !!(r.duration && r.duration.slow),
    running: !!(r.duration && r.duration.running),
    complete: !!(r.duration && r.duration.complete),
  }));
  return {
    points,
    median: typical ? typical.medianSeconds : null,
    p95: typical ? typical.p95Seconds : null,
    enough: !!typical,
    note: typical ? null : 'Not enough history yet (needs ' + minRuns + ' completed runs)',
  };
}

/** The bottleneck step's share of the run's duration as a whole percent, or null when it cannot be told. */
function bottleneckShare(run) {
  const total = run.duration ? run.duration.seconds : null;
  const step = run.bottleneck ? stepOf(run, run.bottleneck) : null;
  if (!step || step.durationSeconds == null || !total || total <= 0) return null;
  return Math.min(100, Math.round((step.durationSeconds / total) * 100));
}

/**
 * Change of `cur` against `prev`.
 * none: a value is missing; flat: no change (incl. 0 -> 0); new: prev was 0; up/down with pct.
 */
export function deltaPct(cur, prev) {
  if (cur == null || prev == null) return { kind: 'none', pct: null };
  if (prev === 0 && cur === 0) return { kind: 'flat', pct: 0 };
  if (prev === 0) return { kind: 'new', pct: null };
  const pct = ((cur - prev) / prev) * 100;
  const r = Math.abs(pct) < 0.05 ? 0 : pct;
  return { kind: r === 0 ? 'flat' : r > 0 ? 'up' : 'down', pct: r };
}

/** Values of a step's metric over the newest `n` runs (runs are newest first), oldest -> newest. */
export function series(runs, stepName, n) {
  return runs
    .slice(0, n)
    .reverse()
    .map((r) => metric(stepOf(r, stepName)));
}

/* ---------- formatting ---------- */
const nf = new Intl.NumberFormat('en-US');
export const fmt = (n) => (n == null ? 'n/a' : nf.format(n));
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const p2 = (n) => (n < 10 ? '0' : '') + n;
export const hhmm = (d) => p2(d.getHours()) + ':' + p2(d.getMinutes());
export const hhmmss = (d) => hhmm(d) + ':' + p2(d.getSeconds());
export const dayLabel = (d) => DAYS[d.getDay()] + ', ' + MONS[d.getMonth()] + ' ' + d.getDate();
export const shortDay = (d) => MONS[d.getMonth()] + ' ' + d.getDate();

/** "42m ago", "3h 05m ago", "2d 4h ago" from a number of hours. */
export function ago(h) {
  if (h < 1) return Math.round(h * 60) + 'm ago';
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return hh >= 48 ? Math.floor(hh / 24) + 'd ' + (hh % 24) + 'h ago' : hh + 'h ' + mm + 'm ago';
}

/**
 * A duration for people: `37s`, `4m 05s`, `1h 04m`, `2d 03h`; `<1s` below one second; a dash when unavailable.
 * `approx` puts a leading ≈ (estimated from the previous step), `running` a trailing … (still counting).
 */
export function fmtDuration(seconds, { approx = false, running = false } = {}) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const s = Math.floor(seconds);
  let text;
  if (s < 1) text = '<1s';
  else if (s < 60) text = s + 's';
  else if (s < 3600) text = Math.floor(s / 60) + 'm ' + p2(s % 60) + 's';
  else if (s < 86400) text = Math.floor(s / 3600) + 'h ' + p2(Math.floor((s % 3600) / 60)) + 'm';
  else text = Math.floor(s / 86400) + 'd ' + p2(Math.floor((s % 86400) / 3600)) + 'h';
  return (approx ? '≈' : '') + text + (running ? '…' : '');
}

export const dur = (s) => (s >= 60 ? Math.floor(s / 60) + 'm ' + p2(s % 60) + 's' : s + 's');

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export function compact(v) {
  return v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + 'k' : String(Math.round(v));
}

export function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/** "42 s", "3m 05s", "1h 02m" for a running step; never negative. */
export function elapsedLabel(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return s + ' s';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + p2(s % 60) + 's';
  return Math.floor(s / 3600) + 'h ' + p2(Math.floor((s % 3600) / 60)) + 'm';
}

/**
 * Stable string over the runs that ignores counters that change on every fetch (a step's elapsed
 * time, a run's age). A one-minute age bucket keeps "ended Xm ago" and the stale flag current; a
 * running run leaves it out so its spinner is not redrawn by it. Equal signatures mean no redraw.
 */
export function runSignature(runs) {
  return JSON.stringify(runs.map((r) => {
    const { ageSeconds, ...rest } = r;
    // a running run's duration counts up on every fetch: it is not a change worth a redraw
    const duration = r.duration && r.duration.running ? { ...r.duration, seconds: null } : r.duration;
    return {
      ...rest,
      duration,
      ageBucket: r.status === 'running' ? null : Math.floor(ageSeconds / 60),
      steps: r.steps.map(({ elapsedSeconds, fetchedAt, ...s }) => s),
    };
  }));
}

/** Live indicator text: seconds since the last successful fetch. */
export function updatedLabel(seconds) {
  if (seconds < 2) return 'just now';
  if (seconds < 60) return seconds + 's ago';
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
  return Math.floor(seconds / 3600) + 'h ago';
}

/** Seconds left before the next retry, never below 0. */
export function retryIn(nextAt, now) {
  return Math.max(0, Math.ceil((nextAt - now) / 1000));
}

/* ---------- home page cards (a card is one pipeline's newest run in any environment) ---------- */

/**
 * Card status, first match wins: Running, Failed, Died, Stale, Incomplete, Lost data, Completed (the server
 * decides; this adds the words and tone). Everything but Running and Completed needs attention.
 */
const CARD_STATUS = {
  running: { text: 'Running', tone: 'running', attn: false },
  failed: { text: 'Failed', tone: 'bad', attn: true },
  died: { text: 'Died', tone: 'bad', attn: true },
  stale: { text: 'Stale', tone: 'warn', attn: true },
  incomplete: { text: 'Incomplete', tone: 'bad', attn: true },
  lost: { text: 'Lost data', tone: 'bad', attn: true },
  ok: { text: 'Completed', tone: 'ok', attn: false },
};
export function cardStatus(card) {
  const key = CARD_STATUS[card.status] ? card.status : 'ok';
  return { key, ...CARD_STATUS[key] };
}

/** Why a card needs attention: {kind, step?, hours?}, or null. */
export function cardReason(card, staleHours) {
  const l = card.latest;
  if (card.status === 'failed') {
    const e = l.error || {};
    return { kind: 'failed', step: l.failedStep, errorType: e.type || 'Error', message: e.message == null ? null : e.message };
  }
  if (card.status === 'died') return { kind: 'died', step: l.diedStep };
  if (card.status === 'stale') return { kind: 'stale', hours: staleHours };
  if (card.status === 'incomplete') {
    return l.stalledStep ? { kind: 'stalled', step: l.stalledStep } : { kind: 'stopped', step: l.firstMissingStep };
  }
  if (card.status === 'lost') return { kind: 'lost', step: l.lossSteps[0] };
  return null;
}

/** Needs-attention cards first (Failed ones lead them), then the rest; each group A to Z by label. */
export function groupCards(cards) {
  const byLabel = (x, y) => x.label.localeCompare(y.label) || x.name.localeCompare(y.name);
  const isFailed = (c) => c.status === 'failed';
  const failedFirst = (x, y) => (isFailed(x) === isFailed(y) ? byLabel(x, y) : isFailed(x) ? -1 : 1);
  return {
    attention: cards.filter((c) => c.needsAttention).sort(failedFirst),
    rest: cards.filter((c) => !c.needsAttention).sort(byLabel),
  };
}

export const CARD_ROLE = { first: 'First step', peak: 'Largest step', last: 'Last step' };

/** The three numbers of a card; `value` null means the step has not reported. */
export function cardNumbers(card) {
  return card.latest.headline.filter((h) => h.step).map((h) => ({ ...h, role: CARD_ROLE[h.key] }));
}

/** What the card says about time: running for X, stalled for X, last seen X ago (died), failed Xh ago, stopped Xh ago, finished Xh ago. */
export function cardWhen(card, nowSeconds) {
  const l = card.latest;
  if (card.status === 'running') {
    return { kind: 'running', seconds: Math.max(0, Math.floor((card.generatedAt.getTime() - l.startedAt.getTime()) / 1000)) };
  }
  if (card.status === 'failed') {
    return { kind: 'failed', hours: (l.ageSeconds + (nowSeconds || 0)) / 3600 };
  }
  if (card.status === 'died') {
    const seen = l.lastSeenAt ? Math.floor((card.generatedAt.getTime() - l.lastSeenAt.getTime()) / 1000) : 0;
    return { kind: 'died', seconds: Math.max(0, seen + (nowSeconds || 0)) };
  }
  if (card.status === 'incomplete' && l.stalledStep) return { kind: 'stalled', seconds: l.stalledSeconds == null ? 0 : l.stalledSeconds };
  const hours = (l.ageSeconds + (nowSeconds || 0)) / 3600;
  return { kind: card.status === 'incomplete' ? 'stopped' : 'finished', hours };
}

/** Summary line under the "Pipelines" title. */
export function homeSummary(cards) {
  const attn = cards.filter((c) => c.needsAttention).length;
  return { total: cards.length, attention: attn };
}

/* ---------- environment filter (History) ---------- */

/** prod first, then the others A to Z. */
export function orderEnvs(envs) {
  return [...envs].sort((a, b) => (a === 'prod' ? -1 : b === 'prod' ? 1 : a.localeCompare(b)));
}

/** prod when the pipeline has prod runs, else the environment of its newest run. */
export function defaultEnv(card) {
  return card.environments.includes('prod') ? 'prod' : card.latest.env;
}

/** The environment History applies: the one in the address, else the default. */
export function appliedEnv(card, requested) {
  return requested || defaultEnv(card);
}

/** Options of the filter: environments with runs, plus the applied one when the address asked for another. */
export function envChoices(card, applied) {
  const list = orderEnvs(card.environments).map((env) => ({ env, hasRuns: true }));
  if (!card.environments.includes(applied)) list.push({ env: applied, hasRuns: false });
  return list;
}

/**
 * Stable string over the home cards that ignores counters that change on every fetch (age within the
 * same minute, how long a step has been running), so an unchanged overview is not redrawn.
 */
export function overviewSignature(cards) {
  return JSON.stringify(cards.map((c) => {
    const { generatedAt, ...rest } = c;
    const { ageSeconds, stalledSeconds, durationSeconds, ...latest } = c.latest;
    // a running run's duration counts up on every fetch; a finished run's is part of what is drawn
    const duration = c.latest.durationRunning ? null : durationSeconds;
    return { ...rest, latest: { ...latest, duration, ageBucket: c.status === 'running' ? null : Math.floor(ageSeconds / 60) } };
  }));
}

/* ---------- run pages (specs/010-history-first-run-detail) ---------- */

/** The run with this id in this environment (the same id can exist in two), or null. */
export function findRun(runs, env, runId) {
  return runs.find((r) => r.env === env && r.id === runId) || null;
}

/** The runs History lists: every run (`'all'`), or only those a failed step stopped (`'failed'`). */
export function filterRuns(runs, mode) {
  return mode === 'failed' ? runs.filter((r) => !!r.failed) : runs;
}

/** True for the first (newest) run of a newest-first list. */
export function isNewest(runs, run) {
  return runs.length > 0 && runs[0] === run;
}

/** The route of a run's own page. */
export function runRoute(pipelineId, run) {
  return { name: 'run', id: pipelineId, env: run.env, runId: run.id };
}

/** The run page's headline. "Last night" and "Latest" wording only makes sense for the newest run. */
export function heroTitle(a, newest) {
  if (a.failed) return 'A step failed';
  if (a.died) return 'The pipeline process died';
  if (a.running) return 'A run is in progress';
  if (!a.complete) return 'Run stopped before the end';
  if (a.loss.length) return 'Run finished, but one step lost data';
  if (!newest) return 'Run completed';
  return a.stale ? 'Latest run completed — but it’s old' : 'Last night’s run completed';
}

/* ---------- run events (specs/012-duration-and-run-events) ---------- */

/** The levels of an event in display order, with the word shown next to its icon. */
export const EVENT_LEVELS = [
  { key: 'info', word: 'Info' },
  { key: 'warning', word: 'Warning' },
  { key: 'error', word: 'Error' },
];
export const eventWord = (level) => (EVENT_LEVELS.find((l) => l.key === level) || EVENT_LEVELS[0]).word;

/** "6 of 41 events" while filtered, "41 events" when everything matches. */
export function filterSummary(matched, total) {
  return matched === total ? total + ' event' + (total === 1 ? '' : 's') : matched + ' of ' + total + ' events';
}

/** The notes above the timeline: what was dropped, whether the pipeline sent anything, what was unreadable. */
export function eventNotes({ dropped = 0, recorded = 0, unreadable = 0 }) {
  const notes = [];
  if (dropped > 0) notes.push(dropped + ' event' + (dropped === 1 ? ' was' : 's were') + ' dropped because the limit was reached (the oldest info events go first).');
  if (recorded === 0) notes.push('No events were sent by this run. Pipelines on waypoint-etl 0.4.0 or later can send their own with waypoint_etl.log().');
  if (unreadable > 0) notes.push(unreadable + ' unreadable event record' + (unreadable === 1 ? '' : 's') + ' skipped.');
  return notes;
}

/** `step` must be one of these to be chosen in the step filter: the run's steps, then any other named by an event. */
export function stepChoices(run, events) {
  const names = run.steps.map((s) => s.name);
  events.forEach((e) => { if (e.step && !names.includes(e.step)) names.push(e.step); });
  return names;
}
