/* Page addresses (see specs/008-pipelines-home-page/contracts/routes.md). Pure: no DOM access. */

/**
 * Route of an address hash:
 *   #/ (or empty)               -> {name: 'home'}
 *   #/p/<id>                    -> {name: 'pipeline', page: 'history', id, env: null}  (same as /history)
 *   #/p/<id>/history[?env=<e>]  -> {name: 'pipeline', page: 'history', id, env}
 *   #/p/<id>/runs/<env>/<run>   -> {name: 'run', id, env, runId}
 *   ...?tab=events[&level=a,b][&step=s]  (run only) adds tab: 'events', levels: [...], step: s | null
 *   ...?map=<step>[&items=failed|running|done|all][&slow=1][&sort=duration-desc][&q=text]  (run only) adds map, items, slow, sort, q
 *   #/p/<id>/runs/<env>/<run>/steps/<map>/items/<key>[?view=list|graph] -> {name: 'item', id, env, runId, map, key[, view]}  (specs/014)
 *   anything else               -> {name: 'notfound', id}
 * See specs/010-history-first-run-detail/contracts/routes.md.
 */
const RUN_ID = /^\d{8}T\d{6}Z$/;
const EVENT_LEVELS = ['info', 'warning', 'error'];
const MAP_NAME = /^[a-z0-9_]{1,64}$/;
const ITEM_KEY = /^[A-Za-z0-9_.-]{1,64}$/;
/** Query parameters that only describe the open map panel; they never change which data a page needs. */
export const PANEL_PARAMS = ['map', 'items', 'slow', 'sort', 'q'];

/** The hash without the map panel's parameters, for telling whether the page's data changed. */
export function withoutPanel(hash) {
  const h = String(hash || '');
  const q = h.indexOf('?');
  if (q < 0) return h;
  const params = new URLSearchParams(h.slice(q + 1));
  PANEL_PARAMS.forEach((k) => params.delete(k));
  params.delete('view'); // the item page's List | Graph choice
  const rest = params.toString();
  return h.slice(0, q) + (rest ? '?' + rest : '');
}

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
        const map = params.get('map');
        if (map && MAP_NAME.test(map)) {
          route.map = map;
          PANEL_PARAMS.slice(1).forEach((k) => { if (params.get(k)) route[k] = params.get(k); });
        }
        return route;
      }
    }
    if (id && parts[2] === 'runs' && parts.length === 9 && parts[5] === 'steps' && parts[7] === 'items') {
      const env = decode(parts[3]);
      const runId = decode(parts[4]);
      const map = decode(parts[6]);
      const key = decode(parts[8]);
      if (env && runId && RUN_ID.test(runId) && map && MAP_NAME.test(map) && key && ITEM_KEY.test(key)) {
        const view = new URLSearchParams(query).get('view');
        return view === 'list' || view === 'graph' ? { name: 'item', id, env, runId, map, key, view } : { name: 'item', id, env, runId, map, key };
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
    if (route.tab !== 'events') {
      if (!route.map) return run;
      const panel = ['map=' + encodeURIComponent(route.map)];
      PANEL_PARAMS.slice(1).forEach((k) => { if (route[k]) panel.push(k + '=' + encodeURIComponent(route[k])); });
      return run + '?' + panel.join('&');
    }
    const params = [];
    if (route.levels && route.levels.length) params.push('level=' + route.levels.join(','));
    if (route.step) params.push('step=' + encodeURIComponent(route.step));
    return run + '?tab=events' + (params.length ? '&' + params.join('&') : '');
  }
  if (route.name === 'item') {
    return base + '/runs/' + encodeURIComponent(route.env) + '/' + encodeURIComponent(route.runId) +
      '/steps/' + encodeURIComponent(route.map) + '/items/' + encodeURIComponent(route.key) +
      (route.view === 'list' || route.view === 'graph' ? '?view=' + route.view : '');
  }
  if (route.name !== 'pipeline') return '#/';
  return base + '/history' + (route.env ? '?env=' + encodeURIComponent(route.env) : '');
}

/** The page title that follows the route. `when` is the run's start time as shown on the page. */
export function routeTitle(route, label, when) {
  const product = 'Waypoint Monitor';
  if (route.name === 'pipeline') return (label || route.id) + ' · History · ' + product;
  if (route.name === 'run') return (label || route.id) + ' · ' + (when || 'Run') + ' · ' + product;
  if (route.name === 'item') return route.key + ' · ' + route.map + ' · ' + (label || route.id) + ' · ' + product;
  if (route.name === 'notfound') return 'Pipeline not found · ' + product;
  return product;
}
