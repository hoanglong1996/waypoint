/* Page addresses (see specs/008-pipelines-home-page/contracts/routes.md). Pure: no DOM access. */

/**
 * Route of an address hash:
 *   #/ (or empty)               -> {name: 'home'}
 *   #/p/<id>                    -> {name: 'pipeline', page: 'history', id, env: null}  (same as /history)
 *   #/p/<id>/history[?env=<e>]  -> {name: 'pipeline', page: 'history', id, env}
 *   #/p/<id>/runs/<env>/<run>   -> {name: 'run', id, env, runId}
 *   ...?tab=events[&level=a,b][&step=s]  (run only) adds tab: 'events', levels: [...], step: s | null
 *   anything else               -> {name: 'notfound', id}
 * See specs/010-history-first-run-detail/contracts/routes.md.
 */
const RUN_ID = /^\d{8}T\d{6}Z$/;
const EVENT_LEVELS = ['info', 'warning', 'error'];

export function parseRoute(hash) {
  let h = String(hash || '').replace(/^#/, '') || '/';
  let query = '';
  const q = h.indexOf('?');
  if (q >= 0) {
    query = h.slice(q + 1);
    h = h.slice(0, q);
  }
  const parts = h.split('/').filter(Boolean);
  if (!parts.length) return { name: 'home' };
  const decode = (s) => {
    try {
      return decodeURIComponent(s);
    } catch (e) {
      return null;
    }
  };
  if (parts[0] === 'p' && parts[1]) {
    const id = decode(parts[1]);
    if (id && parts.length <= 3 && (!parts[2] || parts[2] === 'history')) {
      const env = new URLSearchParams(query).get('env');
      return { name: 'pipeline', id, page: 'history', env: env || null };
    }
    if (id && parts[2] === 'runs' && parts.length === 5) {
      const env = decode(parts[3]);
      const runId = decode(parts[4]);
      if (env && runId && RUN_ID.test(runId)) {
        const route = { name: 'run', id, env, runId };
        const params = new URLSearchParams(query);
        if (params.get('tab') === 'events') {
          route.tab = 'events';
          route.levels = (params.get('level') || '').split(',').filter((l) => EVENT_LEVELS.includes(l));
          route.step = params.get('step') || null;
        }
        return route;
      }
    }
  }
  return { name: 'notfound', id: parts[0] === 'p' ? decode(parts[1] || '') || '' : '' };
}

/** The hash for a route made by parseRoute (round-trips). */
export function buildRoute(route) {
  if (!route) return '#/';
  const base = '#/p/' + encodeURIComponent(route.id);
  if (route.name === 'run') {
    const run = base + '/runs/' + encodeURIComponent(route.env) + '/' + encodeURIComponent(route.runId);
    if (route.tab !== 'events') return run;
    const params = [];
    if (route.levels && route.levels.length) params.push('level=' + route.levels.join(','));
    if (route.step) params.push('step=' + encodeURIComponent(route.step));
    return run + '?tab=events' + (params.length ? '&' + params.join('&') : '');
  }
  if (route.name !== 'pipeline') return '#/';
  return base + '/history' + (route.env ? '?env=' + encodeURIComponent(route.env) : '');
}

/** The page title that follows the route. `when` is the run's start time as shown on the page. */
export function routeTitle(route, label, when) {
  const product = 'Waypoint Monitor';
  if (route.name === 'pipeline') return (label || route.id) + ' · History · ' + product;
  if (route.name === 'run') return (label || route.id) + ' · ' + (when || 'Run') + ' · ' + product;
  if (route.name === 'notfound') return 'Pipeline not found · ' + product;
  return product;
}
