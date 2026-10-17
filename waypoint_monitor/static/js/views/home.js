/* Home page: one card per pipeline (newest run in any environment), needs-attention group first.
   A card opens that pipeline's history on the environment of the run it shows. */
import {
  ago, cardNumbers, cardReason, cardStatus, cardWhen, elapsedLabel, esc, fmt, fmtDuration, groupCards, homeSummary,
} from '../model.js';
import { buildRoute } from '../router.js';
import { I, countChipsHTML, durationHTML, elapsedHTML, envTag } from '../ui.js';

const ICON = {
  running: I.spinner, failed: I.failed, died: I.power, stale: I.clock, incomplete: I.xCircle, lost: I.octagon, ok: I.checkCircle,
};

function whenHTML(card, w) {
  if (w.kind === 'running') return 'running for ' + elapsedHTML({ elapsedSeconds: w.seconds, fetchedAt: card.fetchedAt });
  if (w.kind === 'stalled') return 'stalled for ' + elapsedHTML({ elapsedSeconds: w.seconds, fetchedAt: card.fetchedAt });
  if (w.kind === 'died') return 'last seen ' + elapsedHTML({ elapsedSeconds: w.seconds, fetchedAt: card.fetchedAt }) + ' ago';
  if (w.kind === 'failed') return 'failed ' + ago(w.hours);
  return (w.kind === 'stopped' ? 'stopped ' : 'finished ') + ago(w.hours);
}
const whenText = (w) => {
  if (w.kind === 'running') return 'running for ' + elapsedLabel(w.seconds);
  if (w.kind === 'stalled') return 'stalled for ' + elapsedLabel(w.seconds);
  if (w.kind === 'died') return 'last seen ' + elapsedLabel(w.seconds) + ' ago';
  if (w.kind === 'failed') return 'failed ' + ago(w.hours);
  return (w.kind === 'stopped' ? 'stopped ' : 'finished ') + ago(w.hours);
};

function reasonHTML(r) {
  if (!r) return '';
  if (r.kind === 'stale') return 'Last night’s run is missing (expected every ' + r.hours + ' h at most)';
  if (r.kind === 'failed') {
    return 'Failed at <code>' + esc(r.step) + '</code>: <b>' + esc(r.errorType) + '</b>' +
      (r.message ? ' <span class="pcard__msg">' + esc(r.message) + '</span>' : '');
  }
  if (r.kind === 'died') return 'Died at <code>' + esc(r.step) + '</code> (the process is gone)';
  if (r.kind === 'stalled') return 'Stalled at <code>' + esc(r.step) + '</code> (alive, not progressing)';
  if (r.kind === 'stopped') return 'Stopped at <code>' + esc(r.step) + '</code>';
  return '<code>' + esc(r.step) + '</code> received input but returned 0';
}

export function cardHTML(card, cfg) {
  const st = cardStatus(card);
  const l = card.latest;
  const nums = cardNumbers(card);
  const w = cardWhen(card);
  const placeholder = card.status === 'running' ? 'in progress' : 'not reported';
  const reason = cardReason(card, cfg.staleHours);
  const aria = card.label + ', ' + l.env + ', ' + st.text + (st.attn ? ', needs attention' : '') + ', ' + whenText(w) + '. ' +
    nums.map((n) => n.role + ' ' + n.label + ': ' + (n.value == null ? placeholder : fmt(n.value))).join(', ') + '.' +
    (l.durationSeconds != null ? ' Latest run took ' + fmtDuration(l.durationSeconds, { running: l.durationRunning }) + '.' : '') +
    (l.warnings ? ' ' + l.warnings + (l.warnings === 1 ? ' warning.' : ' warnings.') : '') + (l.errors ? ' ' + l.errors + (l.errors === 1 ? ' error.' : ' errors.') : '');
  const tone = st.tone === 'running' ? 'run' : st.tone;
  return (
    '<li class="pgrid__item"><a class="pcard pcard--' + st.key + (st.attn ? ' pcard--attn pcard--' + st.tone : '') +
    '" href="' + esc(buildRoute({ name: 'pipeline', id: card.name, page: 'history', env: l.env })) + '" aria-label="' + esc(aria) + '">' +
    (st.attn ? '<span class="pcard__flag pcard__flag--' + st.tone + '">' + I.alert + 'Needs attention</span>' : '') +
    '<span class="pcard__top"><span class="pcard__name" title="' + esc(card.label) + '">' + esc(card.label) + '</span>' + envTag(l.env) + '</span>' +
    '<span class="pcard__status"><span class="pill pill--sm pill--' + tone + '">' + ICON[st.key] + st.text + '</span>' +
    '<span class="pcard__when">' + whenHTML(card, w) + '</span></span>' +
    (l.durationSeconds != null || l.warnings || l.errors
      ? '<span class="pcard__dur">' + (l.durationSeconds != null ? '<span title="Duration of the latest run">' + I.stopwatch + durationHTML(l.durationSeconds, { running: l.durationRunning }) + '</span>' : '') +
        countChipsHTML({ warnings: l.warnings, errors: l.errors }) + '</span>' : '') +
    (reason ? '<span class="pcard__reason">' + reasonHTML(reason) + '</span>' : '') +
    '<span class="pcard__nums">' + nums.map((n) =>
      '<span class="pnum' + (n.value == null ? ' pnum--missing' : '') + '"><span class="eyebrow pnum__label">' + esc(n.label) + '</span>' +
      '<span class="pnum__value num">' + (n.value == null ? '—' : fmt(n.value)) + '</span>' +
      '<span class="pnum__name" title="' + n.role + ': ' + esc(n.step) + '">' + (n.value == null ? placeholder : esc(n.step)) + '</span></span>',
    ).join('') + '</span></a></li>'
  );
}

function headHTML(summary) {
  const sum = summary
    ? summary.total + ' pipeline' + (summary.total === 1 ? '' : 's') +
      (summary.attention ? ' · <b class="t-attn">' + summary.attention + ' need' + (summary.attention === 1 ? 's' : '') + ' attention</b>' : ' · all fine') +
      ' · each card shows the newest run in any environment'
    : '';
  return '<div class="home__head"><h1 class="home__title">Pipelines</h1>' + (sum ? '<p class="home__sum">' + sum + '</p>' : '') + '</div>';
}

export function homeSkeletonHTML() {
  const sk = (w, h, extra) => '<span class="skel" style="width:' + w + ';height:' + h + 'px;' + (extra || '') + '"></span>';
  return headHTML(null) + '<span class="sr-only" role="status">Loading pipelines…</span><ul class="pgrid" aria-hidden="true">' +
    [1, 2, 3, 4, 5, 6].map(() =>
      '<li class="pgrid__item"><div class="pcard pcard--skel">' + sk('55%', 18) + sk('130px', 22, 'border-radius:999px') +
      '<span class="pcard__nums">' + [1, 2, 3].map(() => '<span class="pnum" style="gap:6px">' + sk('60%', 10) + sk('70%', 26) + sk('80%', 10) + '</span>').join('') + '</span></div></li>',
    ).join('') + '</ul>';
}

export function homeEmptyHTML() {
  return headHTML(null) + '<section class="card empty" role="status"><div class="empty__art">' + I.route + '</div>' +
    '<h2>No pipelines yet</h2><p>Pipelines appear here after their first run.</p></section>';
}

export function homeErrorHTML(errorHTML) {
  return headHTML(null) + errorHTML;
}

export function renderHome(el, cards, cfg, fetchedAt) {
  if (!cards.length) {
    el.innerHTML = homeEmptyHTML();
    return;
  }
  const withFetch = cards.map((c) => ({ ...c, fetchedAt }));
  const g = groupCards(withFetch);
  const group = (title, list, attn) =>
    '<section class="home__group" aria-labelledby="g-' + (attn ? 'attn' : 'rest') + '">' +
    '<h2 class="home__group-title' + (attn ? ' home__group-title--attn' : '') + '" id="g-' + (attn ? 'attn' : 'rest') + '">' + (attn ? I.alert : '') + title +
    '<span class="home__count num">' + list.length + '</span></h2>' +
    '<ul class="pgrid">' + list.map((c) => cardHTML(c, cfg)).join('') + '</ul></section>';
  el.innerHTML = headHTML(homeSummary(cards)) +
    (g.attention.length ? group('Needs attention', g.attention, true) : '') +
    (g.rest.length ? group(g.attention.length ? 'Healthy and running' : 'All pipelines', g.rest, false) : '');
}
