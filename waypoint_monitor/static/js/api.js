/* Fetching and mapping of the monitor API (see specs/002-pipeline-monitor-dashboard/contracts/api.md). */

export class DataStoreUnavailable extends Error {}

async function getJson(url) {
  let response;
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch (err) {
    throw new DataStoreUnavailable(String(err));
  }
  if (response.status === 503) throw new DataStoreUnavailable('Data store unavailable');
  if (!response.ok) {
    const err = new Error('Request failed (' + response.status + ')');
    err.status = response.status;
    throw err;
  }
  try {
    return await response.json();
  } catch (err) {
    throw new DataStoreUnavailable('Unreadable response');
  }
}

export async function loadConfig() {
  const c = await getJson('/api/config');
  return {
    environments: c.environments,
    refreshSeconds: c.refresh_seconds,
    retrySeconds: c.retry_seconds,
    staleHours: c.stale_hours,
    stallSeconds: c.stall_seconds,
    durationMinRuns: c.duration_min_runs || 5,
    durationWindowRuns: c.duration_window_runs || 30,
  };
}

/**
 * One card per pipeline that has a run, each with its newest run in any environment
 * (contracts/api.md, GET /api/overview). Already in display order: needs attention first.
 */
export async function loadOverview() {
  return mapOverview(await getJson('/api/overview'));
}

/** The overview body as the views use it. Failure fields are null for a server that sends none. */
export function mapOverview(body) {
  const generatedAt = new Date(body.generated_at);
  return {
    generatedAt,
    unreadableTotal: body.unreadable_total,
    cards: body.pipelines.map((p) => ({
      name: p.name,
      label: p.label || p.name,
      environments: p.environments,
      status: p.card_status,
      needsAttention: !!p.needs_attention,
      generatedAt,
      latest: {
        runId: p.latest.run_id,
        env: p.latest.env,
        status: p.latest.status,
        stale: p.latest.stale,
        startedAt: new Date(p.latest.started_at),
        endedAt: new Date(p.latest.ended_at),
        ageSeconds: p.latest.age_seconds,
        lossSteps: p.latest.loss_steps,
        firstMissingStep: p.latest.first_missing_step,
        stalledStep: p.latest.stalled_step,
        stalledSeconds: p.latest.stalled_seconds,
        diedStep: p.latest.died_step || null,
        lastSeenAt: p.latest.last_seen_at ? new Date(p.latest.last_seen_at) : null,
        failedStep: p.latest.failed_step || null,
        failedAt: p.latest.failed_at ? new Date(p.latest.failed_at) : null,
        error: p.latest.error || null,
        unreadable: p.latest.unreadable,
        durationSeconds: p.latest.duration_seconds == null ? null : p.latest.duration_seconds,
        durationRunning: !!p.latest.duration_running,
        slow: !!p.latest.slow,
        warnings: p.latest.warnings || 0,
        errors: p.latest.errors || 0,
        headline: p.latest.headline,
      },
    })),
  };
}

/** A step's metrics (specs/013 contracts/api.md); an old server sends none. Names, labels and units stay text. */
export function mapMetrics(list) {
  return (Array.isArray(list) ? list : []).map((m) => ({
    name: String(m.name),
    label: typeof m.label === 'string' ? m.label : null,
    value: typeof m.value === 'number' ? m.value : null,
    unit: typeof m.unit === 'string' ? m.unit : null,
    declared: !!m.declared,
    flag: m.flag === 'above' || m.flag === 'below' ? m.flag : null,
    updatedAt: m.updated_at ? new Date(m.updated_at) : null,
  }));
}

function mapStep(s) {
  const step = { ...mapStepBase(s), metrics: mapMetrics(s.metrics), metricsOver: s.metrics_over || 0 };
  // a map step carries its loop summary (specs/014); every other step stays exactly as before
  if (s.map && typeof s.map === 'object') step.map = mapMapSummary(s.map);
  return step;
}

const count = (v) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0);
const optNum = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/**
 * The loop summary of a map step (specs/014 contracts/api.md, `step.map`). All text stays text; counts are
 * non-negative integers; there is never a total number of items.
 */
export function mapMapSummary(m) {
  const c = m.counts || {};
  const d = m.duration || {};
  const detail = m.detail || {};
  const counts = { started: count(c.started), running: count(c.running), done: count(c.done), failed: count(c.failed) };
  return {
    state: typeof m.state === 'string' ? m.state : 'running',
    counts,
    inTotal: optNum(m.in_total),
    outTotal: optNum(m.out_total),
    lostItems: count(m.lost_items),
    concurrencyLimit: optNum(m.concurrency_limit),
    over: typeof m.over === 'string' ? m.over : null,
    loopSeconds: optNum(m.loop_seconds),
    duration: {
      count: count(d.count),
      medianMs: optNum(d.median_ms),
      p95Ms: optNum(d.p95_ms),
      approx: d.approx !== false,
      enough: !!d.enough,
    },
    slowest: (Array.isArray(m.slowest) ? m.slowest : []).filter((x) => x && typeof x.key === 'string').map((x) => ({ key: x.key, ms: optNum(x.ms) })),
    failedItems: (Array.isArray(m.failed_items) ? m.failed_items : []).filter((x) => x && typeof x.key === 'string').map((x) => ({
      key: x.key,
      step: typeof x.step === 'string' ? x.step : null,
      errorType: typeof x.error_type === 'string' ? x.error_type : null,
    })),
    inner: (Array.isArray(m.inner) ? m.inner : []).filter((x) => x && typeof x.name === 'string').map((x) => ({
      name: x.name, running: count(x.running), done: count(x.done), failed: count(x.failed), inCount: optNum(x.in), outCount: optNum(x.out),
    })),
    detail: {
      partial: !!detail.partial,
      kept: count(detail.kept),
      failedWithoutRecord: count(detail.failed_without_record),
    },
    unreadable: count(m.unreadable),
  };
}

/** One row of the items list (contracts/api.md). `currentStep` and `lossStep` are optional extras. */
export function mapItemRow(i) {
  return {
    key: String(i.key),
    index: count(i.index),
    state: typeof i.state === 'string' ? i.state : 'running',
    slow: !!i.slow,
    startedAt: i.started_at ? new Date(i.started_at) : null,
    durationMs: optNum(i.duration_ms),
    elapsedMs: optNum(i.elapsed_ms),
    failedStep: typeof i.failed_step === 'string' ? i.failed_step : null,
    errorType: typeof i.error_type === 'string' ? i.error_type : null,
    inCount: optNum(i.in),
    outCount: optNum(i.out),
    loss: !!i.loss,
    compact: !!i.compact,
    currentStep: typeof i.current_step === 'string' ? i.current_step : null,
    lossStep: typeof i.loss_step === 'string' ? i.loss_step : null,
    fetchedAt: Date.now(),
  };
}

/** A page of the items endpoint. */
export function mapItemsPage(b) {
  const c = b.counts || {};
  return {
    total: count(b.total),
    withRecord: count(b.with_record),
    counts: { failed: count(c.failed), running: count(c.running), done: count(c.done) },
    partial: !!b.partial,
    failedWithoutRecord: count(b.failed_without_record),
    matched: count(b.matched),
    hasMore: !!b.has_more,
    next: typeof b.next === 'string' ? b.next : null,
    unreadable: count(b.unreadable),
    items: (Array.isArray(b.items) ? b.items : []).map(mapItemRow),
  };
}

function mapItemStep(s) {
  const e = s.error && typeof s.error === 'object' ? s.error : null;
  return {
    name: String(s.name),
    state: typeof s.state === 'string' ? s.state : 'waiting',
    inputs: (Array.isArray(s.inputs) ? s.inputs : []).map((x) => ({ name: String(x.name), value: optNum(x.value) })),
    output: optNum(s.output),
    durationMs: optNum(s.duration_ms),
    startedAt: s.started_at ? new Date(s.started_at) : null,
    loss: !!s.loss,
    unplanned: !!s.unplanned,
    error: e ? {
      type: typeof e.type === 'string' ? e.type : 'Error',
      message: typeof e.message === 'string' ? e.message : null,
      traceback: typeof e.traceback === 'string' ? e.traceback : '',
    } : null,
    metrics: (Array.isArray(s.metrics) ? s.metrics : []).map((m) => ({
      name: String(m.name),
      label: typeof m.label === 'string' ? m.label : null,
      unit: typeof m.unit === 'string' ? m.unit : null,
      value: optNum(m.value),
      over: !!m.over,
    })),
  };
}

/** One item for the item view (contracts/api.md). */
export function mapItemDetail(b) {
  const e = b.error && typeof b.error === 'object' ? b.error : null;
  return {
    key: String(b.key),
    index: count(b.index),
    state: typeof b.state === 'string' ? b.state : 'running',
    slow: !!b.slow,
    compact: !!b.compact,
    startedAt: b.started_at ? new Date(b.started_at) : null,
    finishedAt: b.finished_at ? new Date(b.finished_at) : null,
    durationMs: optNum(b.duration_ms),
    elapsedMs: optNum(b.elapsed_ms),
    steps: (Array.isArray(b.steps) ? b.steps : []).map(mapItemStep),
    error: e ? {
      type: typeof e.type === 'string' ? e.type : 'Error',
      message: typeof e.message === 'string' ? e.message : null,
      traceback: typeof e.traceback === 'string' ? e.traceback : '',
    } : null,
    fetchedAt: Date.now(),
  };
}

const runBase = (pipeline, env, runId) =>
  '/api/runs/' + encodeURIComponent(pipeline) + '/' + encodeURIComponent(env) + '/' + encodeURIComponent(runId);

/**
 * A page of one map step's items. `params`: {state, slow, q, sort, order, failedFirst, limit, after}; empty values are left out.
 */
export async function loadItems(pipeline, env, runId, map, params = {}) {
  const q = [];
  if (params.state) q.push('state=' + encodeURIComponent(params.state));
  if (params.slow) q.push('slow=1');
  if (params.q) q.push('q=' + encodeURIComponent(params.q));
  if (params.sort) q.push('sort=' + encodeURIComponent(params.sort));
  if (params.order) q.push('order=' + encodeURIComponent(params.order));
  if (params.failedFirst) q.push('failed_first=1');
  if (params.limit) q.push('limit=' + params.limit);
  if (params.after) q.push('after=' + encodeURIComponent(params.after));
  const body = await getJson(runBase(pipeline, env, runId) + '/maps/' + encodeURIComponent(map) + '/items' + (q.length ? '?' + q.join('&') : ''));
  return mapItemsPage(body);
}

/** One item; null when it has no record of its own (404). */
export async function loadItem(pipeline, env, runId, map, key) {
  try {
    return mapItemDetail(await getJson(runBase(pipeline, env, runId) + '/maps/' + encodeURIComponent(map) + '/items/' + encodeURIComponent(key)));
  } catch (err) {
    if (err && err.status === 404) return null;
    throw err;
  }
}

function mapStepBase(s) {
  if (s.missing) return { name: s.name, state: 'missing', missing: true };
  if (s.state === 'failed') {
    // The step raised: no counts. Keep when it began and failed, and what the error said (text, never HTML).
    const error = s.error || {};
    return {
      name: s.name,
      state: 'failed',
      inputs: [],
      output: null,
      finishedAt: null,
      startedAt: s.started_at ? new Date(s.started_at) : null,
      failedAt: s.failed_at ? new Date(s.failed_at) : null,
      durationSeconds: s.duration_seconds == null ? null : s.duration_seconds,
      durationApprox: !!s.duration_approx,
      error: {
        type: typeof error.type === 'string' ? error.type : 'Error',
        message: typeof error.message === 'string' ? error.message : null,
        traceback: typeof error.traceback === 'string' ? error.traceback : '',
      },
    };
  }
  if (s.state === 'died') {
    // The process is gone: no counts, and no running clock. Keep when it began and when it was last seen.
    return {
      name: s.name,
      state: 'died',
      inputs: [],
      output: null,
      finishedAt: null,
      startedAt: s.started_at ? new Date(s.started_at) : null,
      lastSeenAt: s.last_seen_at ? new Date(s.last_seen_at) : null,
    };
  }
  if (s.state === 'running' || s.state === 'stalled' || s.state === 'waiting') {
    // Not finished: no counts yet. Empty inputs and a null output keep list/graph code safe.
    return {
      name: s.name,
      state: s.state,
      inputs: [],
      output: null,
      finishedAt: null,
      startedAt: s.started_at ? new Date(s.started_at) : null,
      elapsedSeconds: s.elapsed_seconds == null ? null : s.elapsed_seconds,
      fetchedAt: Date.now(),
    };
  }
  return {
    name: s.name,
    state: s.state === 'unplanned' ? 'unplanned' : 'done',
    inputs: (s.inputs || []).map((i) => ({ name: i.name, value: i.value })),
    output: s.output == null ? null : s.output,
    finishedAt: s.finished_at ? new Date(s.finished_at) : null,
    startedAt: s.started_at ? new Date(s.started_at) : null,
    durationSeconds: s.duration_seconds == null ? null : s.duration_seconds,
    durationApprox: !!s.duration_approx,
  };
}

/** The run's flow description as the views use it, or null when the run has none. */
function mapFlow(f) {
  if (!f) return null;
  return {
    label: f.label || null,
    groups: (f.groups || []).map((g) => ({ key: g.key, label: g.label || g.key })),
    steps: (f.steps || []).map((s) => ({
      name: s.name,
      label: s.label || s.name,
      group: s.group || null,
      inputs: (s.inputs || []).map((i) => ({ name: i.name, from: i.from, dangling: !!i.dangling })),
      returnsNothing: !!s.returns_nothing,
      col: typeof s.col === 'number' ? s.col : null,
      row: typeof s.row === 'number' ? s.row : null,
      metrics: mapDecls(s.metrics),
      ...(s.map && typeof s.map === 'object' ? { map: mapDecl(s.map) } : {}),
    })),
  };
}

const mapDecls = (list) => (list || []).map((m) => ({
  name: String(m.name),
  label: typeof m.label === 'string' ? m.label : null,
  unit: typeof m.unit === 'string' ? m.unit : null,
  warnAbove: typeof m.warn_above === 'number' ? m.warn_above : null,
  warnBelow: typeof m.warn_below === 'number' ? m.warn_below : null,
}));

/** A map step's declaration in the flow: where its items come from, the concurrency limit, the item flow. */
function mapDecl(m) {
  return {
    over: typeof m.over === 'string' ? m.over : null,
    maxConcurrency: optNum(m.max_concurrency),
    steps: (Array.isArray(m.steps) ? m.steps : []).filter((x) => x && typeof x.name === 'string').map((x) => ({
      name: x.name,
      label: typeof x.label === 'string' && x.label ? x.label : x.name,
      inputs: (Array.isArray(x.inputs) ? x.inputs : []).map((i) => ({ name: String(i.name), from: String(i.from) })),
      metrics: mapDecls(x.metrics),
    })),
  };
}

/**
 * One def per entry of `run.steps` (same order): the flow's definition of that step, or a stand-in for a step
 * that reported but is not in the flow (`unplanned`) or belongs to a run with no usable flow (`noFlow`).
 */
export function defsFor(flow, steps) {
  const byName = new Map(flow ? flow.steps.map((d) => [d.name, d]) : []);
  return steps.map((s) => {
    const d = byName.get(s.name);
    if (d) return d;
    return {
      name: s.name, label: s.name, group: null, inputs: [], returnsNothing: false, col: null, row: null, metrics: [],
      unplanned: !!flow, noFlow: !flow,
    };
  });
}

export function mapRun(r) {
  const steps = r.steps.map(mapStep);
  const flow = mapFlow(r.flow);
  return {
    id: r.run_id,
    pipeline: r.pipeline || null,
    env: r.env,
    startedAt: new Date(r.started_at),
    endedAt: new Date(r.ended_at),
    durationSeconds: r.duration_seconds,
    duration: r.duration
      ? { seconds: r.duration.seconds == null ? null : r.duration.seconds, running: !!r.duration.running, complete: !!r.duration.complete, slow: !!r.duration.slow }
      : null,
    metricsOver: r.metrics_over || 0,
    eventCounts: { warning: (r.event_counts && r.event_counts.warning) || 0, error: (r.event_counts && r.event_counts.error) || 0 },
    ageSeconds: r.age_seconds,
    stale: r.stale,
    status: r.status,
    runningStep: r.running_step || null,
    firstMissingStep: r.first_missing_step,
    missingCount: r.missing_count,
    lossSteps: r.loss_steps,
    unreadable: r.unreadable,
    died: r.died
      ? { judgedAt: new Date(r.died.judged_at), lastSeenAt: new Date(r.died.last_seen_at), recorded: !!r.died.recorded }
      : null,
    failed: r.failed
      ? { step: r.failed.step, index: r.failed.index, failedAt: new Date(r.failed.failed_at) }
      : null,
    flowStatus: r.flow_status || (flow ? 'ok' : 'missing'),
    flowProblems: r.flow_problems || [],
    flow,
    defs: defsFor(flow, steps),
    steps,
  };
}

/** The typical durations of a pipeline and environment (specs/012 data-model.md), or null. */
export function mapTypical(t) {
  if (!t) return null;
  return {
    medianSeconds: t.median_seconds, p95Seconds: t.p95_seconds, sample: t.sample, window: t.window,
    multiple: t.multiple, slowAfterSeconds: t.slow_after_seconds,
  };
}

/**
 * Runs of `pipeline`, newest first: from the one environment `env`, or merged from every environment when
 * `env` is not given. `limit` is how many to ask each environment for (the API allows up to 100).
 */
export async function loadRuns(environments, pipeline, env, limit = 30) {
  const list = env ? [env] : environments;
  const bodies = await Promise.all(list.map((e) => getJson(
    '/api/runs?env=' + encodeURIComponent(e) + '&pipeline=' + encodeURIComponent(pipeline) + '&limit=' + limit,
  )));
  const runs = bodies.flatMap((body) => body.runs.map(mapRun)).sort((x, y) => (y.id < x.id ? -1 : y.id > x.id ? 1 : 0));
  // typical values belong to one environment: only an answer for a single environment has them
  const typical = bodies.length === 1 ? mapTypical(bodies[0].typical) : null;
  return { runs: runs.slice(0, limit), unreadableTotal: bodies.reduce((n, body) => n + body.unreadable_total, 0), typical };
}

/** One timeline entry of the events endpoint as the views use it (all text stays text). */
export function mapEvent(e) {
  return {
    id: e.id,
    ts: new Date(e.ts),
    level: e.level,
    step: e.step || null,
    message: typeof e.message === 'string' ? e.message : null,
    fields: e.fields && typeof e.fields === 'object' ? e.fields : null,
    source: e.source === 'monitor' ? 'monitor' : 'pipeline',
    kind: e.kind || 'custom',
    ...(typeof e.item === 'string' ? { item: e.item } : {}),
  };
}

/**
 * A page of a run's timeline (GET /api/runs/{pipeline}/{env}/{run}/events, contracts/api.md).
 * `levels` is a list of levels (empty = all), `step` an exact step name or null.
 */
export async function loadEvents(pipeline, env, runId, { levels = [], step = null, item = null, offset = 0, limit = 200 } = {}) {
  const q = ['offset=' + offset, 'limit=' + limit];
  if (levels.length) q.push('level=' + levels.join(','));
  if (step) q.push('step=' + encodeURIComponent(step));
  if (item) q.push('item=' + encodeURIComponent(item));
  const body = await getJson('/api/runs/' + encodeURIComponent(pipeline) + '/' + encodeURIComponent(env) + '/' + encodeURIComponent(runId) + '/events?' + q.join('&'));
  return {
    events: body.events.map(mapEvent),
    total: body.total,
    matched: body.matched,
    hasMore: !!body.has_more,
    recorded: body.recorded || 0,
    dropped: body.dropped || 0,
    unreadable: body.unreadable || 0,
  };
}
