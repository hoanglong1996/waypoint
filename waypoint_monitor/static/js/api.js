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
  if (!response.ok) throw new Error('Request failed (' + response.status + ')');
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
  };
}

/**
 * One card per pipeline that has a run, each with its newest run in any environment
 * (contracts/api.md, GET /api/overview). Already in display order: needs attention first.
 */
export async function loadOverview() {
  const body = await getJson('/api/overview');
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
        unreadable: p.latest.unreadable,
        headline: p.latest.headline,
      },
    })),
  };
}

function mapStep(s) {
  if (s.missing) return { name: s.name, state: 'missing', missing: true };
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
      name: s.name, label: s.name, group: null, inputs: [], returnsNothing: false, col: null, row: null,
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
    flowStatus: r.flow_status || (flow ? 'ok' : 'missing'),
    flowProblems: r.flow_problems || [],
    flow,
    defs: defsFor(flow, steps),
    steps,
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
  return { runs: runs.slice(0, limit), unreadableTotal: bodies.reduce((n, body) => n + body.unreadable_total, 0) };
}
