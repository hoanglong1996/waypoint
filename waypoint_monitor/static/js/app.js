/* App shell: address-driven views, header, theme, live indicator, polling, banners and states. */
import {
  DataStoreUnavailable, loadConfig, loadOverview, loadRuns,
} from './api.js';
import {
  appliedEnv, dayLabel, elapsedLabel, envChoices, findRun, hhmm, overviewSignature, retryIn, runSignature, updatedLabel,
} from './model.js';
import { buildRoute, parseRoute, routeTitle } from './router.js';
import {
  I, banner, errorHTML, getStepsView, historySkeletonHTML, notFoundHTML, runNotFoundHTML, setStepsView, skeletonHTML,
} from './ui.js';
import { mountGraph, refreshGraph } from './views/graph.js';
import { redrawTrend, renderHistory } from './views/history.js';
import { homeErrorHTML, homeSkeletonHTML, renderHome } from './views/home.js';
import { refreshEvents } from './views/events.js';
import { renderRun } from './views/run.js';

const $ = (id) => document.getElementById(id);
const DEFAULT_RETRY = 30;

const state = {
  cfg: null,
  route: parseRoute(location.hash),
  overview: null, // {cards, unreadableTotal, generatedAt}; null until the first load
  runs: [], // one environment's runs: the newest 30 for History, up to 100 for a run page
  unreadableTotal: 0,
  typical: null, // typical durations of the environment shown (History and run pages)
  status: 'loading', // loading | ok | error
  lastOkAt: null,
  nextAt: null,
  timer: null,
  gen: 0, // bumped on reload so late responses are ignored
  signature: null, // what is drawn; an unchanged fetch is not redrawn
  focusEnv: false, // after the environment filter changed, keep focus on the chosen option
  focusRun: false, // after a run page was opened, move focus to its heading once it is drawn
};

/* ---------- theme ---------- */
const isDark = () => {
  const t = document.documentElement.getAttribute('data-theme');
  return t === 'dark' || (t !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
};
function syncThemeLabel() {
  const b = $('theme-toggle');
  if (b) b.setAttribute('aria-label', isDark() ? 'Switch to light theme' : 'Switch to dark theme');
}
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try {
    localStorage.setItem('wp-theme', t);
  } catch (e) {
    /* storage unavailable: the choice just won't persist */
  }
  syncThemeLabel();
}

/* ---------- what the address means once the data is known ---------- */
const cardOf = (id) => (state.overview ? state.overview.cards.find((c) => c.name === id) : null);

/** When a run started, as shown in the breadcrumb and the page title. */
const runLabel = (run) => dayLabel(run.startedAt) + ', ' + hhmm(run.startedAt);

/**
 * The view to show. A pipeline that has not reported is "not found", and so is a run that is not in the
 * pipeline's runs, but both only once the data is known.
 */
function currentView() {
  const r = state.route;
  if (r.name === 'pipeline') {
    if (state.status === 'ok' && !cardOf(r.id)) return { kind: 'notfound', id: r.id };
    return { kind: 'history', id: r.id, card: cardOf(r.id) };
  }
  if (r.name === 'run') {
    const card = cardOf(r.id);
    if (state.status === 'ok' && !card) return { kind: 'notfound', id: r.id };
    const run = state.status === 'ok' ? findRun(state.runs, r.env, r.runId) : null;
    if (state.status === 'ok' && !run) return { kind: 'runnotfound', id: r.id, env: r.env, card };
    return { kind: 'run', id: r.id, env: r.env, card, run };
  }
  if (r.name === 'notfound' && r.id) {
    // A malformed run address of a pipeline that exists is a missing run, not a missing pipeline.
    if (state.status !== 'ok') return { kind: 'history', id: r.id, card: null };
    const card = cardOf(r.id);
    if (card) return { kind: 'runnotfound', id: r.id, env: null, card };
  }
  return { kind: r.name, id: r.id };
}

function showView(kind) {
  const shown = kind === 'runnotfound' ? 'notfound' : kind;
  ['home', 'history', 'run', 'notfound'].forEach((v) => {
    $('view-' + v).hidden = v !== shown;
  });
}

/* ---------- header: brand · live · theme, plus the context bar on pipeline pages ---------- */
function syncHeader(view) {
  const bar = $('ctxbar');
  const onPipe = view.kind === 'history' || view.kind === 'run' || view.kind === 'runnotfound';
  bar.hidden = !onPipe;
  if (!onPipe) return;
  const label = view.card ? view.card.label : view.id;
  const name = $('ctx-name');
  name.textContent = label;
  name.title = label;
  const isRun = view.kind === 'run' || view.kind === 'runnotfound';
  if (isRun) {
    // the pipeline name is the back control: its history, with the environment of the run
    name.href = buildRoute({ name: 'pipeline', id: view.id, page: 'history', env: view.env || null });
    name.removeAttribute('aria-current');
  } else {
    name.href = buildRoute({ name: 'pipeline', id: view.id, page: 'history', env: state.route.env });
    name.setAttribute('aria-current', 'page');
  }
  const run = view.kind === 'run' ? $('ctx-run') : null;
  $('ctx-chev').hidden = view.kind !== 'run';
  $('ctx-run').hidden = view.kind !== 'run';
  if (run) run.textContent = view.run ? runLabel(view.run) : 'Run';
}

/* ---------- rendering ---------- */
function renderBanners(view) {
  const el = $('banners');
  el.innerHTML = '';
  if (state.status !== 'ok') return;
  if (view.kind === 'home') {
    const n = state.overview.unreadableTotal;
    if (n) {
      el.innerHTML += banner(
        'info', I.fileX, 'Some records could not be read',
        n + ' step records were malformed and skipped. The cards use the records that could be read.',
      );
    }
    return;
  }
  if (!view.card) return;
  const l = view.card.latest;
  // The stale warning is about the pipeline's newest run: on a run page only when that run is it.
  const showStale = view.kind === 'history'
    || (view.kind === 'run' && view.run && l.runId === view.run.id && l.env === view.run.env);
  if (l.stale && showStale) {
    const ageH = l.ageSeconds / 3600;
    el.innerHTML += banner(
      'warn', I.clock, 'No new run in the last ' + state.cfg.staleHours + ' hours',
      'The newest run finished ' + Math.round(ageH) + 'h ago (' + dayLabel(l.endedAt) + ', ' + hhmm(l.endedAt) + '). The run may not have started — check the scheduler.',
      'alert',
    );
  }
  if (state.unreadableTotal && (view.kind === 'history' || view.kind === 'run')) {
    el.innerHTML += banner(
      'info', I.fileX, 'Some records could not be read',
      state.unreadableTotal + ' step records were malformed and skipped. Counts below come from the records that could be read.',
    );
  }
}

/** What the History filter offers and applies for this pipeline (spec FR-008 to FR-011). */
function envInfo(card) {
  const applied = appliedEnv(card, state.route.env);
  return {
    applied,
    label: card.label,
    pipelineId: card.name,
    choices: envChoices(card, applied),
    onChange: (env) => {
      state.focusEnv = true;
      location.hash = buildRoute({ name: 'pipeline', id: card.name, page: 'history', env });
    },
  };
}

function render() {
  const view = currentView();
  const cfg = state.cfg;
  const retry = cfg ? cfg.retrySeconds : DEFAULT_RETRY;
  const label = view.card && view.card.label;
  if (view.kind === 'history') document.title = routeTitle({ name: 'pipeline', id: view.id, page: 'history' }, label);
  else if (view.kind === 'run') document.title = routeTitle({ name: 'run', id: view.id, env: view.env }, label, view.run ? runLabel(view.run) : null);
  else if (view.kind === 'runnotfound') document.title = 'Run not found · Waypoint Monitor';
  else document.title = routeTitle({ name: view.kind, id: view.id });
  syncHeader(view);
  renderBanners(view);
  syncLive();
  showView(view.kind);

  if (view.kind === 'notfound') {
    $('view-notfound').innerHTML = notFoundHTML(view.id);
    return;
  }
  if (view.kind === 'runnotfound') {
    $('view-notfound').innerHTML = runNotFoundHTML(view.id, view.env, view.card && view.card.label);
    return;
  }
  const home = $('view-home');
  const runEl = $('view-run');
  const history = $('view-history');
  if (state.status === 'loading') {
    if (view.kind === 'home') home.innerHTML = homeSkeletonHTML();
    else if (view.kind === 'run') {
      runEl.innerHTML = skeletonHTML(6, cfg ? getStepsView() : 'list');
      if (cfg && getStepsView() === 'graph') mountGraph($('run-graph'), { cfg, mode: 'skeleton' });
    } else history.innerHTML = historySkeletonHTML();
    return;
  }
  if (state.status === 'error') {
    if (view.kind === 'home') home.innerHTML = homeErrorHTML(errorHTML(retry));
    else (view.kind === 'run' ? runEl : history).innerHTML = errorHTML(retry);
    syncLive();
    return;
  }
  if (view.kind === 'home') {
    renderHome(home, state.overview.cards, cfg, state.lastOkAt);
    return;
  }
  if (view.kind === 'run') {
    renderRun(runEl, view.run, state.runs, cfg, state.typical, state.route);
    refreshGraph($('run-graph')); // laid out while hidden
    if (state.focusRun) {
      state.focusRun = false;
      const h = $('hero-title');
      if (h) h.focus({ preventScroll: true });
    }
    return;
  }
  renderHistory(history, state.runs, cfg, envInfo(view.card), state.typical);
  redrawTrend();
  if (state.focusEnv) {
    state.focusEnv = false;
    const checked = document.querySelector('input[name="env"]:checked');
    if (checked) checked.focus();
  }
}

/* ---------- live indicator and retry countdown (ticks every second) ---------- */
function syncLive() {
  const live = $('live');
  const label = live.querySelector('span:last-child');
  const off = state.status !== 'ok';
  live.classList.toggle('live--off', off);
  if (state.status === 'loading') {
    label.textContent = 'Loading…';
    return;
  }
  const since = state.lastOkAt ? Math.floor((Date.now() - state.lastOkAt) / 1000) : null;
  if (state.status === 'error') {
    label.textContent = since == null ? 'Not updated yet' : 'Last updated ' + updatedLabel(since);
    document.querySelectorAll('[data-retry-in]').forEach((n) => {
      n.textContent = state.nextAt ? retryIn(state.nextAt, Date.now()) : '';
    });
    document.querySelectorAll('[data-last-success]').forEach((n) => {
      n.textContent = since == null ? '' : ' · last success ' + updatedLabel(since);
    });
    return;
  }
  label.textContent = 'Updated ' + updatedLabel(since == null ? 0 : since);
}

/* ---------- data loading and polling ---------- */
function schedule(seconds) {
  clearTimeout(state.timer);
  state.nextAt = Date.now() + seconds * 1000;
  state.timer = setTimeout(refresh, seconds * 1000);
}

async function refresh() {
  clearTimeout(state.timer);
  const gen = state.gen;
  const route = state.route;
  try {
    if (!state.cfg) {
      state.cfg = await loadConfig();
    }
    const overview = await loadOverview();
    if (gen !== state.gen) return;
    let data = { runs: [], unreadableTotal: 0, typical: null };
    const card = route.name === 'pipeline' || route.name === 'run' ? overview.cards.find((c) => c.name === route.id) : null;
    if (card && route.name === 'pipeline') {
      // one environment; one that has no runs is not asked for
      const env = appliedEnv(card, route.env);
      if (card.environments.includes(env) && state.cfg.environments.includes(env)) {
        data = await loadRuns(state.cfg.environments, card.name, env);
      }
    } else if (card && state.cfg.environments.includes(route.env)) {
      // a run page: the run's own environment, as many runs as the API gives, so older runs open too.
      // An environment that does not exist is not asked for: the run is simply not found.
      data = await loadRuns(state.cfg.environments, card.name, route.env, 100);
    }
    if (gen !== state.gen) return;
    // A reload every few seconds must not restart spinners or drop focus, so redraw only when
    // something other than elapsed time / same-minute age changed.
    const sig = location.hash + '|' + overviewSignature(overview.cards) + '|' + overview.unreadableTotal + '|' + runSignature(data.runs) + '|' + data.unreadableTotal + '|' + JSON.stringify(data.typical);
    const unchanged = state.status === 'ok' && sig === state.signature;
    state.overview = overview;
    state.runs = data.runs;
    state.unreadableTotal = data.unreadableTotal;
    state.typical = data.typical;
    state.status = 'ok';
    state.lastOkAt = Date.now();
    if (unchanged) syncLive();
    else {
      state.signature = sig;
      render();
    }
    // a running run keeps adding events: reload the ones shown (filters and scroll stay)
    if (route.name === 'run' && route.tab === 'events') refreshEvents();
    schedule(state.cfg.refreshSeconds);
  } catch (err) {
    if (gen !== state.gen) return;
    if (!(err instanceof DataStoreUnavailable)) console.error(err); // eslint-disable-line no-console
    state.status = 'error';
    state.runs = [];
    state.signature = null;
    render();
    schedule(state.cfg ? state.cfg.retrySeconds : DEFAULT_RETRY);
  }
}

/** Load for the current address. `quiet` keeps what is drawn until the new data arrives (environment filter). */
function load(quiet) {
  state.gen += 1;
  state.signature = null;
  if (!quiet) {
    state.status = 'loading';
    state.runs = [];
    render();
  }
  refresh();
}

/* ---------- navigation: the address decides the view ---------- */
window.addEventListener('hashchange', () => {
  const before = state.route;
  state.route = parseRoute(location.hash);
  const route = state.route;
  const sameHistory = before.name === 'pipeline' && route.name === 'pipeline' && before.id === route.id;
  // Same run, only the tab or the events filters changed: the data is loaded, so just redraw.
  if (state.status === 'ok' && before.name === 'run' && route.name === 'run' && before.id === route.id
    && before.env === route.env && before.runId === route.runId) {
    render();
    return;
  }
  state.focusRun = route.name === 'run';
  if (!state.focusEnv) window.scrollTo(0, 0);
  // From a history to one of its runs the run is already loaded: show it at once, then refresh.
  if (state.status === 'ok' && before.name === 'pipeline' && route.name === 'run' && before.id === route.id
    && findRun(state.runs, route.env, route.runId)) {
    render();
    state.focusRun = true; // the refresh below redraws the page, so focus the heading after that one
    load(true);
    return;
  }
  load(sameHistory && state.status === 'ok');
});

/* ---------- List | Graph choice (run page) ---------- */
document.addEventListener('change', (e) => {
  const t = e.target;
  if (!t.name || t.name.indexOf('steps-view') !== 0) return;
  setStepsView(t.value);
  if (state.status === 'ok' && currentView().kind === 'run') render();
  const back = document.querySelector('input[name="' + t.name + '"][value="' + getStepsView() + '"]');
  if (back) back.focus();
});

/* ---------- boot ---------- */
$('theme-toggle').addEventListener('click', () => setTheme(isDark() ? 'light' : 'dark'));
syncThemeLabel();

document.addEventListener('click', (e) => {
  if (e.target.closest && e.target.closest('[data-retry]')) refresh();
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearTimeout(state.timer);
  } else if (state.status !== 'loading') {
    refresh();
  }
});

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (currentView().kind === 'history' && state.status === 'ok') redrawTrend();
  }, 120);
});

/* Running/stalled steps count up between reloads, from the elapsed time and moment of the last fetch. */
function tickElapsed() {
  const now = Date.now();
  document.querySelectorAll('[data-elapsed]').forEach((n) => {
    n.textContent = elapsedLabel(Number(n.dataset.elapsed) + (now - Number(n.dataset.fetched)) / 1000);
  });
}

setInterval(() => {
  if (document.hidden) return;
  syncLive();
  tickElapsed();
}, 1000);

load();

