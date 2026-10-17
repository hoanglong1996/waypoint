/* Map step panel (specs/014, design 3.2): summary, item flow, notices and the item list with search, status chips, the
   Slow toggle, sort and "Show more". It opens under the graph when a map node is selected (or inside the steps list).
   The list state lives in the address (?map=…&items=failed&slow=1&sort=duration-desc&q=acct), so a shared link opens the
   same view; data comes page by page from the items endpoint, 50 rows at a time, and is merged by item key on refresh. */
import { DataStoreUnavailable, loadItems } from '../api.js';
import {
  buildPanelQuery, chipsFor, countText, durationLine, effectiveStatus, innerDefs, ioText, itemRoute, itemsApiParams, itemsQuery,
  mapPartialNotice, mergePages, mergeRefresh, moreText, PAGE_SIZE, panelRoute, parsePanelQuery, slowDisabled, slowestLabel,
} from '../map-model.js';
import {
  emptyHTML, listHTML, moreHTML, noticesHTML, panelShellHTML, preselectHTML, stripHTML, summaryHTML, toolsHTML,
} from '../map-ui.js';
import { buildRoute, parseRoute } from '../router.js';

const POLL_MS = 5000;
const SEARCH_DEBOUNCE_MS = 150;

/* One entry per (environment, run, map step): the list state and what was loaded, kept across redraws of the page. */
const memory = new Map();
const keyOf = (run, name) => run.env + '|' + run.id + '|' + name;

/* Where the viewer was when an item was opened, so Back restores the scroll position and the focus on that row. */
let lastRow = null;
export const rememberRow = (run, name, key) => { lastRow = { k: keyOf(run, name), key, scrollY: window.scrollY, at: Date.now() }; };
const RETURN_WINDOW_MS = 4000;
/** The viewer is on the way back to the list: from now on the position and the row are restored for a few seconds. */
export const markReturn = (run, name) => { if (lastRow && lastRow.k === keyOf(run, name)) lastRow.at = Date.now(); };
export const returnInfo = (run, name) => (lastRow && lastRow.k === keyOf(run, name) ? lastRow : null);

/** Put the panel's state in the address without adding a history entry or reloading the page. */
export function syncAddress(run, name, state) {
  const route = name == null
    ? { name: 'run', id: run.pipeline, env: run.env, runId: run.id }
    : panelRoute(run, name, state);
  const hash = buildRoute(route);
  if (location.hash !== hash) history.replaceState(null, '', hash);
}

const panelId = (name) => 'map-panel-' + name;
export { panelId };

/**
 * Fill `el` (a section) with the panel of map step `step` of `run`.
 * `o`: {def, route, onClose, focus (move focus to the heading), live (poll while the run runs)}.
 */
export function mountMapPanel(el, o) {
  const { run, step, def } = o;
  const name = step.name;
  const label = (def && def.label) || name;
  const id = panelId(name);
  const mem = memory.get(keyOf(run, name)) || {};
  memory.set(keyOf(run, name), mem);
  const { map } = step;
  const declared = innerDefs(def);
  // the address is the truth (a shared link, Back from an item); without panel values in it the remembered state stays
  const here = parseRoute(location.hash);
  const fromRoute = here.name === 'run' && here.map === name ? here : null;
  mem.state = fromRoute ? parsePanelQuery(fromRoute) : mem.state || parsePanelQuery(null);
  const state = mem.state;
  let gen = 0;
  let loading = false;
  let error = false;
  let debounce = null;

  if (el._mpTimer) clearInterval(el._mpTimer);
  syncAddress(run, name, state);
  el.id = id;
  el.className = 'mp-card mp-panel';
  el.setAttribute('aria-labelledby', id + '-title');
  el.hidden = false;
  el.innerHTML = panelShellHTML({ id, label, name });
  const $ = (k) => el.querySelector('[data-mp="' + k + '"]');
  const hrefFor = (key) => buildRoute(itemRoute(run, name, key));
  const showTools = () => map.counts.started > 0;

  const chipsNow = () => chipsFor(mem.page, state, map);

  function paintSummary() {
    $('sum').innerHTML = summaryHTML({
      map, line: durationLine(map), slowest: slowestLabel(map), io: ioText(map),
      slowestHref: slowestLabel(map) ? hrefFor(slowestLabel(map).key) : '#',
    });
    $('strip').innerHTML = stripHTML(map, declared);
    $('notices').innerHTML = noticesHTML(mapPartialNotice(map, mem.page ? mem.page.withRecord : null));
  }

  function paintTools() {
    const tools = $('tools');
    tools.hidden = !showTools();
    if (!showTools()) return;
    if (!tools.firstChild) {
      tools.innerHTML = toolsHTML({ id, chips: chipsNow(), state, slowDisabled: slowDisabled(map), slowOn: state.slow });
    }
    // in place, so the search box keeps its text and focus while the numbers change
    chipsNow().forEach((c) => {
      const b = tools.querySelector('[data-mp-chip="' + c.id + '"]');
      if (!b) return;
      b.setAttribute('aria-pressed', String(c.pressed));
      b.disabled = c.disabled;
      b.querySelector('.mp-n').textContent = String(c.n.toLocaleString('en-US'));
    });
    const slow = tools.querySelector('[data-mp-slow]');
    slow.setAttribute('aria-pressed', String(state.slow));
    slow.disabled = slowDisabled(map);
    const sort = tools.querySelector('[data-mp-sort]');
    if (sort.value !== state.sort) sort.value = state.sort;
    const dir = tools.querySelector('[data-mp-dir]');
    dir.textContent = state.dir === 'asc' ? '↑ Asc' : '↓ Desc';
    dir.setAttribute('aria-label', state.dir === 'asc' ? 'Sort direction: ascending. Switch to descending' : 'Sort direction: descending. Switch to ascending');
    const q = tools.querySelector('[data-mp-q]');
    if (document.activeElement !== q && q.value !== state.q) q.value = state.q;
    $('hint').innerHTML = !state.touched && effectiveStatus(state, map) === 'failed' && mem.page
      ? preselectHTML(mem.page.withRecord) : '';
  }

  function paintList() {
    const list = $('list');
    const more = $('more');
    const count = $('count');
    const put = (node, html) => { if (node._html !== html) { node._html = html; node.innerHTML = html; } };
    if (!showTools()) {
      count.textContent = '';
      put(list, emptyHTML(map.state === 'done' ? 'empty-loop' : 'none'));
      put(more, '');
      return;
    }
    const page = mem.page;
    const rows = mem.rows || [];
    if (!page) {
      count.textContent = '';
      put(list, error
        ? '<div class="mp-empty"><strong>Items could not be loaded.</strong><span>The page tries again by itself.</span></div>'
        : '<div class="mp-empty" role="status"><span>Loading items…</span></div>');
      put(more, '');
      return;
    }
    count.textContent = countText(page, state, map);
    if (!rows.length) {
      const bits = [];
      if (state.q.trim()) bits.push('Key contains “' + state.q.trim() + '”');
      const status = effectiveStatus(state, map);
      if (status !== 'all') bits.push(status[0].toUpperCase() + status.slice(1));
      if (state.slow) bits.push('Slow');
      put(list, emptyHTML('nomatch', bits.join(' · ')));
      put(more, '');
      return;
    }
    // the rows are redrawn in one go, but the row that has focus is given focus again
    const focused = document.activeElement && el.contains(document.activeElement) ? document.activeElement.getAttribute('data-key') : null;
    const html = listHTML(rows, map, hrefFor);
    const redraw = list._html !== html;
    put(list, html);
    if (redraw && focused) {
      const row = rowFor(focused);
      if (row) row.focus({ preventScroll: true });
    }
    put(more, page.hasMore ? moreHTML(moreText(page, rows.length, state, map), page.matched - rows.length) : '');
  }

  const rowFor = (key) => Array.from(el.querySelectorAll('.mp-row')).find((r) => r.getAttribute('data-key') === key) || null;

  function paintAll() {
    paintSummary();
    paintTools();
    paintList();
  }

  /** Read the first `want` matching items (several requests when more than a page is on screen). */
  async function fetchUpTo(want, after) {
    let out = [];
    let cursor = after;
    let last = null;
    while (out.length < want) {
      const p = await loadItems(run.pipeline, run.env, run.id, name, itemsApiParams(state, map, { limit: Math.min(200, want - out.length), after: cursor }));
      last = p;
      out = out.concat(p.items);
      if (!p.hasMore || !p.next) break;
      cursor = p.next;
    }
    return { items: out, last };
  }

  async function reload() {
    gen += 1;
    const mine = gen;
    mem.rows = [];
    mem.page = null;
    error = false;
    paintAll();
    await load(mine, PAGE_SIZE, null, false);
  }

  async function load(mine, want, after, merge) {
    loading = true;
    try {
      const { items, last } = await fetchUpTo(want, after);
      if (mine !== gen) return;
      mem.rows = merge === 'append' ? mergePages([mem.rows, items]) : merge ? mergeRefresh(mem.rows, items) : items;
      mem.page = last;
      mem.query = itemsQuery(state, map);
      error = false;
    } catch (err) {
      if (mine !== gen) return;
      if (!(err instanceof DataStoreUnavailable)) console.error(err); // eslint-disable-line no-console
      error = true;
    } finally {
      if (mine === gen) loading = false;
    }
    if (mine !== gen) return;
    paintAll();
    restoreReturn();
  }

  /** Re-read what is on screen and merge it in by key: rows keep their place, new ones go to the end. */
  async function refresh() {
    if (loading || !showTools() || !mem.page) return;
    const mine = gen;
    await load(mine, Math.max(PAGE_SIZE, (mem.rows || []).length), null, true);
  }

  async function showMore() {
    if (loading || !mem.page || !mem.page.hasMore) return;
    gen += 1;
    const mine = gen;
    const before = mem.rows.length;
    const btn = el.querySelector('[data-mp-more]');
    if (btn) btn.disabled = true;
    await load(mine, PAGE_SIZE, mem.page.next, 'append');
    const added = (mem.rows || []).length - before;
    $('announce').textContent = added > 0 ? added + ' more item' + (added === 1 ? '' : 's') + ' shown' : '';
    const again = el.querySelector('[data-mp-more]');
    if (again) again.focus({ preventScroll: true });
  }

  function restoreReturn() {
    // the page may draw the panel more than once while it opens, so the way back is honoured for a few seconds
    const back = returnInfo(run, name);
    if (!back || Date.now() - back.at > RETURN_WINDOW_MS) return;
    const row = rowFor(back.key);
    window.scrollTo(0, back.scrollY);
    if (row) row.focus({ preventScroll: true });
  }

  function changed(opts = {}) {
    if (opts.touch) state.touched = true;
    syncAddress(run, name, state);
    reload();
  }

  /* ---------- events ---------- */
  // text typed a moment ago counts before anything else is chosen (the search waits 150 ms before it reloads)
  const takeTypedQuery = () => {
    const box = el.querySelector('[data-mp-q]');
    if (box && box.value !== state.q) {
      clearTimeout(debounce);
      state.q = box.value;
      state.touched = true;
    }
  };
  el.addEventListener('click', (ev) => {
    const t = ev.target instanceof Element ? ev.target : null;
    if (!t) return;
    if (t.closest('[data-mp-chip], [data-mp-slow], [data-mp-dir], [data-mp-showall]')) takeTypedQuery();
    const chip = t.closest('[data-mp-chip]');
    if (chip && !chip.disabled) {
      state.status = chip.getAttribute('data-mp-chip');
      changed({ touch: true });
      return;
    }
    if (t.closest('[data-mp-slow]')) {
      if (!slowDisabled(map)) {
        state.slow = !state.slow;
        changed({ touch: true });
      }
      return;
    }
    if (t.closest('[data-mp-dir]')) {
      state.dir = state.dir === 'asc' ? 'desc' : 'asc';
      changed();
      return;
    }
    if (t.closest('[data-mp-more]')) {
      showMore();
      return;
    }
    if (t.closest('[data-mp-showall]')) {
      state.status = 'all';
      changed({ touch: true });
      return;
    }
    if (t.closest('[data-mp-clear]')) {
      state.status = 'all';
      state.slow = false;
      state.q = '';
      changed({ touch: true });
      return;
    }
    if (t.closest('[data-mp-close]')) {
      if (o.onClose) o.onClose();
      return;
    }
    const row = t.closest('.mp-row');
    const slowest = t.closest('[data-mp-slowest]');
    if (row) rememberRow(run, name, row.getAttribute('data-key'));
    else if (slowest) {
      const sl = slowestLabel(map);
      if (sl) rememberRow(run, name, sl.key);
    }
  });
  el.addEventListener('input', (ev) => {
    const q = ev.target instanceof Element ? ev.target.closest('[data-mp-q]') : null;
    if (!q) return;
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.q = q.value;
      changed({ touch: true });
    }, SEARCH_DEBOUNCE_MS);
  });
  el.addEventListener('change', (ev) => {
    const sel = ev.target instanceof Element ? ev.target.closest('[data-mp-sort]') : null;
    if (!sel) return;
    takeTypedQuery();
    state.sort = sel.value;
    state.dir = sel.value === 'duration' ? 'desc' : 'asc';
    changed();
  });
  el.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && o.onClose) {
      ev.stopPropagation();
      ev.preventDefault();
      o.onClose();
    }
  });

  /* ---------- first paint, then the data ---------- */
  paintAll();
  if (o.focus) el.querySelector('.mp-panel__title').focus();
  const sameList = mem.page && mem.query === itemsQuery(state, map);
  if (sameList) {
    // drawn from what was loaded before the page was redrawn, then brought up to date in place
    paintAll();
    restoreReturn();
    refresh();
  } else {
    mem.rows = [];
    mem.page = null;
    gen += 1;
    load(gen, PAGE_SIZE, null, false);
  }

  // keep the list current while the run is running; stops by itself when the panel leaves the page
  if (o.live) {
    el._mpTimer = setInterval(() => {
      if (!el.isConnected) {
        clearInterval(el._mpTimer);
        return;
      }
      if (!document.hidden) refresh();
    }, POLL_MS);
  }
}

/** The list state last used for a map step (filters, sort, search), for the way back from an item. */
export const savedPanelState = (run, name) => (memory.get(keyOf(run, name)) || {}).state || parsePanelQuery(null);

/** Forget the list of a map step (used by tests and when a run is gone). */
export const forgetPanels = () => memory.clear();

export { buildPanelQuery };
