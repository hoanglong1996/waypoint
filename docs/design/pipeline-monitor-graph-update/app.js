/* =====================================================================
   Pipeline Monitor — app.js (prototype)
   Vanilla JS, no dependencies. Renders mock data into the static shell.

   Prototype URL params (handy for screenshots / reviews):
     ?state=healthy|incomplete|loss|stale|partial|loading|empty|error
     &tab=latest|history  &env=prod|qa  &theme=light|dark  &run=<index>  &step=<step name>
   ===================================================================== */
(function () {
  'use strict';

  /* ------------------------------------------------------------------
     Icons (inline SVG, stroke = currentColor)
     ------------------------------------------------------------------ */
  var I = {
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    checkCircle: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg>',
    xCircle: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/></svg>',
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>',
    octagon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.9 2.5h8.2l5.4 5.4v8.2l-5.4 5.4H7.9l-5.4-5.4V7.9Z"/><path d="M12 8v4.5M12 16h.01"/></svg>',
    clock: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    calendar: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>',
    timer: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4M9.5 2.5h5"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
    database: '<svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/></svg>',
    dbOff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 5.5c0 1.7-3.4 3-7.5 3-1.2 0-2.3-.1-3.3-.3M4.5 5.5c0-.9 1-1.7 2.6-2.3M4.5 5.5v13c0 1.7 3.4 3 7.5 3 2.9 0 5.4-.7 6.7-1.6M19.5 5.5V15M3 3l18 18"/></svg>',
    inbox: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Z"/></svg>',
    up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8"/></svg>',
    down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 9v8H9"/></svg>',
    flat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>',
    arrowIn: '<svg class="chip__arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h12M13 8l4 4-4 4"/></svg>',
    chev: '<svg class="run-row__chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-3.5M4 5v3.5h3.5M4 13a8 8 0 0 0 14.9 3.5M20 19v-3.5h-3.5"/></svg>',
    fileX: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5M10 13l4 4M14 13l-4 4"/></svg>',
    gap: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/></svg>',
    flow: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h14M13 7l5 5-5 5"/><circle cx="21" cy="12" r="1" /></svg>',
    list: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/></svg>',
    graph: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="4" width="6" height="5" rx="1.2"/><rect x="2.5" y="15" width="6" height="5" rx="1.2"/><rect x="15.5" y="9.5" width="6" height="5" rx="1.2"/><path d="M8.5 6.5h2.5a2 2 0 0 1 2 2V10a2 2 0 0 0 2 2M8.5 17.5h2.5a2 2 0 0 0 2-2V14a2 2 0 0 1 2-2"/></svg>'
  };

  /* ------------------------------------------------------------------
     Pipeline definition (fixed order)
     ------------------------------------------------------------------ */
  var STEPS = [
    { name: 'read_callrail_account',  group: 'CallRail',   inputs: [] },
    { name: 'read_callrail_call',     group: 'CallRail',   inputs: [['accounts', 0]] },
    { name: 'read_partners',          group: 'Google Ads', inputs: [] },
    { name: 'read_instances',         group: 'Google Ads', inputs: [['partners', 2]] },
    { name: 'read_campaigns',         group: 'Google Ads', inputs: [['instances', 3]] },
    { name: 'read_gads_clickview',    group: 'Google Ads', inputs: [['instances', 3]] },
    { name: 'merge_calls_clickview',  group: 'Merge',      inputs: [['calls', 1], ['campaigns', 4], ['clickview', 5]] },
    { name: 'record_call_statistics', group: 'Persist',    inputs: [['call_statistics', 6]], noOutput: true },
    { name: 'save_call_statistics',   group: 'Persist',    inputs: [['call_statistics', 6]], noOutput: true }
  ];

  /* ------------------------------------------------------------------
     Mock data
     ------------------------------------------------------------------ */
  var NOW = new Date(2026, 9, 15, 10, 12, 0);     // fixed "now" so renders are stable
  var STALE_HOURS = 26;

  function rng(seed) { var s = seed; return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }

  var BASE = {
    prod: { accounts: 10, calls: 1284, partners: 6, instances: 14, campaigns: 92, clickview: 3410 },
    qa:   { accounts: 3,  calls: 212,  partners: 2, instances: 4,  campaigns: 18, clickview: 540 }
  };

  function makeRun(env, d, rand, opts) {
    opts = opts || {};
    var b = BASE[env];
    var start = new Date(2026, 9, 15 - d, 2, 0, 0);
    start.setSeconds(start.getSeconds() + Math.floor(rand() * 240));
    var dow = start.getDay();
    var wk = (dow === 0 || dow === 6) ? 0.58 : 1;
    var n = function (v, spread) { return d === 0 ? v : Math.max(1, Math.round(v * wk * (1 + (rand() - 0.5) * spread))); };

    var out = [];
    out[0] = b.accounts;
    out[1] = n(b.calls, 0.22);
    out[2] = b.partners;
    out[3] = b.instances;
    out[4] = d === 0 ? b.campaigns : b.campaigns - Math.floor(rand() * 4) + (d > 20 ? -3 : 0);
    out[5] = n(b.clickview, 0.2);
    if (opts.lossAt === 1) out[1] = 0;
    if (opts.lossAt === 4) out[4] = 0;
    if (opts.lossAt === 5) out[5] = 0;
    out[6] = out[1];
    out[7] = null; out[8] = null;

    var t = new Date(start), dur = [1, 9, 1, 2, 4, 38, 6, 3, 5];
    var steps = STEPS.map(function (s, i) {
      t = new Date(t.getTime() + (dur[i] + Math.floor(rand() * 3)) * 1000);
      var inputs = s.inputs.map(function (p) { return { name: p[0], value: out[p[1]] }; });
      return { name: s.name, inputs: inputs, output: s.noOutput ? null : out[i], finishedAt: t };
    });
    (opts.missingFrom != null) && steps.forEach(function (s, i) { if (i >= opts.missingFrom) steps[i] = { name: s.name, missing: true }; });
    return { id: env + '-' + start.toISOString().slice(0, 10), env: env, startedAt: start, steps: steps, unreadable: opts.unreadable || 0 };
  }

  function buildRuns(env, scenario) {
    var rand = rng(env === 'prod' ? 4242 : 777);
    var anomalies = env === 'prod'
      ? { 4: { missingFrom: 8 }, 9: { lossAt: 5 }, 17: { missingFrom: 6 }, 23: { lossAt: 1 } }
      : { 6: { missingFrom: 7 } };
    var runs = [];
    for (var d = 0; d < 30; d++) {
      var o = anomalies[d] || {};
      if (d === 0) {
        if (scenario === 'incomplete') o = { missingFrom: 5 };   // stopped before read_gads_clickview
        if (scenario === 'loss') o = { lossAt: 4 };              // read_campaigns returned 0
        if (scenario === 'partial') o = { unreadable: 2 };
      }
      runs.push(makeRun(env, d, rand, o));
    }
    if (scenario === 'stale') runs.shift();          // last night's run never arrived
    if (scenario === 'empty') return [];
    return runs;                                     // newest first
  }

  /* ------------------------------------------------------------------
     Derived status
     ------------------------------------------------------------------ */
  function analyse(run) {
    var missing = run.steps.filter(function (s) { return s.missing; });
    var loss = run.steps.filter(isLoss);
    var finished = run.steps.filter(function (s) { return !s.missing; });
    var end = finished.length ? finished[finished.length - 1].finishedAt : run.startedAt;
    var ageH = (NOW - end) / 36e5;
    return {
      complete: missing.length === 0,
      firstMissing: missing.length ? missing[0].name : null,
      missingCount: missing.length,
      loss: loss,
      endedAt: end,
      durationS: Math.round((end - run.startedAt) / 1000),
      stale: ageH > STALE_HOURS,
      ageH: ageH
    };
  }
  function isLoss(s) {
    if (s.missing || s.output !== 0) return false;
    return s.inputs.some(function (i) { return i.value > 0; });
  }
  function stepOf(run, name) { for (var i = 0; i < run.steps.length; i++) if (run.steps[i].name === name) return run.steps[i]; return null; }
  function headline(run) {
    var acc = stepOf(run, 'read_callrail_account'), calls = stepOf(run, 'read_callrail_call'), save = stepOf(run, 'save_call_statistics');
    return {
      accounts: acc && !acc.missing ? acc.output : null,
      calls: calls && !calls.missing ? calls.output : null,
      saved: save && !save.missing ? save.inputs[0].value : null
    };
  }
  /* The value plotted / compared for a step: its output, or its main input when the step returns nothing */
  function metric(s) { if (!s || s.missing) return null; return s.output != null ? s.output : (s.inputs[0] ? s.inputs[0].value : null); }

  /* ------------------------------------------------------------------
     Formatting
     ------------------------------------------------------------------ */
  var nf = new Intl.NumberFormat('en-US');
  var fmt = function (n) { return n == null ? 'n/a' : nf.format(n); };
  var DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var p2 = function (n) { return (n < 10 ? '0' : '') + n; };
  var hhmm = function (d) { return p2(d.getHours()) + ':' + p2(d.getMinutes()); };
  var hhmmss = function (d) { return hhmm(d) + ':' + p2(d.getSeconds()); };
  var dayLabel = function (d) { return DAYS[d.getDay()] + ', ' + MONS[d.getMonth()] + ' ' + d.getDate(); };
  var shortDay = function (d) { return MONS[d.getMonth()] + ' ' + d.getDate(); };
  function ago(h) {
    if (h < 1) return Math.round(h * 60) + 'm ago';
    var hh = Math.floor(h), mm = Math.round((h - hh) * 60);
    return hh >= 48 ? Math.floor(hh / 24) + 'd ' + (hh % 24) + 'h ago' : hh + 'h ' + mm + 'm ago';
  }
  function dur(s) { return s >= 60 ? Math.floor(s / 60) + 'm ' + p2(s % 60) + 's' : s + 's'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function deltaChip(cur, prev, opts) {
    opts = opts || {};
    if (cur == null || prev == null) return '';
    if (prev === 0 && cur === 0) return '<span class="delta delta--flat">' + I.flat + '0%</span>';
    if (prev === 0) return '<span class="delta delta--up">' + I.up + 'new</span>';
    var pct = (cur - prev) / prev * 100;
    var r = Math.abs(pct) < 0.05 ? 0 : pct;
    var cls = r === 0 ? 'flat' : r > 0 ? 'up' : 'down';
    var ico = r === 0 ? I.flat : r > 0 ? I.up : I.down;
    var txt = (r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r).toFixed(Math.abs(r) >= 10 ? 0 : 1) + '%';
    var sr = r === 0 ? 'no change' : (r > 0 ? 'up ' : 'down ') + Math.abs(r).toFixed(1) + ' percent';
    return '<span class="delta delta--' + cls + '" title="vs previous run (' + fmt(prev) + ')">' + ico +
      '<span aria-hidden="true">' + txt + '</span><span class="sr-only">' + sr + (opts.label ? ' ' + opts.label : ' vs previous run') + '</span></span>';
  }

  /* ------------------------------------------------------------------
     Pills & badges (status = icon + text + color)
     ------------------------------------------------------------------ */
  function statusPill(a, size) {
    var cls = size ? ' pill--' + size : '';
    if (a.complete) return '<span class="pill pill--ok' + cls + '">' + I.checkCircle + 'Complete</span>';
    return '<span class="pill pill--bad' + cls + '">' + I.xCircle + 'Incomplete</span>';
  }
  function lossPill(n, size) {
    if (!n) return '';
    return '<span class="pill pill--bad pill--' + (size || 'sm') + '">' + I.octagon + (n === 1 ? 'Possible data loss' : n + ' steps with possible data loss') + '</span>';
  }
  function stalePill(a) { return '<span class="pill pill--warn pill--lg">' + I.clock + 'Stale · ' + ago(a.ageH).replace(' ago', '') + ' old</span>'; }

  /* ------------------------------------------------------------------
     Sparkline (inline SVG)
     ------------------------------------------------------------------ */
  function sparkline(values) {
    var W = 128, H = 36, pad = 3;
    var nums = values.filter(function (v) { return v != null; });
    if (!nums.length) return '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true"></svg>';
    var max = Math.max.apply(null, nums), min = Math.min.apply(null, nums.concat([0]));
    min = Math.min(min, max * 0.4); var span = (max - min) || 1;
    var x = function (i) { return pad + i * (W - pad * 2) / (values.length - 1); };
    var y = function (v) { return H - pad - (v - min) / span * (H - pad * 2); };
    var d = '', pen = false, dots = '';
    values.forEach(function (v, i) {
      if (v == null) { pen = false; return; }
      d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true;
      if (v === 0) dots += '<circle class="spark-zero" cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="2.2"/>';
    });
    var last = values[values.length - 1];
    if (last != null && last !== 0) dots += '<circle class="spark-dot" cx="' + x(values.length - 1).toFixed(1) + '" cy="' + y(last).toFixed(1) + '" r="2.6"/>';
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><path class="spark-line" vector-effect="non-scaling-stroke" d="' + d + '"/>' + dots + '</svg>';
  }

  /* ------------------------------------------------------------------
     Step list
     ------------------------------------------------------------------ */
  function stepsHTML(run, runs, compact) {
    var group = null, html = '<ol class="steps' + (compact ? ' steps--compact' : '') + '">';
    run.steps.forEach(function (s, i) {
      if (STEPS[i].group !== group) {
        group = STEPS[i].group;
        html += '<li class="steps__group" aria-hidden="true"><span class="eyebrow">' + group + '</span></li>';
      }
      html += stepItemHTML(run, runs, i, compact);
    });
    return html + '</ol>';
  }

  /* One step as a timeline item (<li>). Reused by the list and by the graph's details panel. */
  function stepItemHTML(run, runs, i, compact) {
    var idx = runs.indexOf(run);
    var prev = runs[idx + 1];
    var hist = runs.slice(idx, idx + 14).reverse();
    var maxOut = Math.max.apply(null, run.steps.map(function (s) { return metric(s) || 0; }).concat([1]));
    var html = '';
    (function (s) {
      var def = STEPS[i];
      var loss = isLoss(s), missing = !!s.missing;
      var state = missing ? 'missing' : loss ? 'loss' : 'ok';
      var nodeInner = missing ? (i + 1) : loss ? '!' : (i + 1);
      var statusText = missing ? 'not recorded' : loss ? 'possible data loss' : 'ok';

      html += '<li class="step step--' + state + '"><div class="step__rail" aria-hidden="true"><span class="step__node">' + nodeInner + '</span></div>';
      html += '<article class="step__card" aria-label="Step ' + (i + 1) + ', ' + s.name + ', ' + statusText + '">';

      // name + time
      html += '<div class="step__name"><div class="step__title">' + s.name + '</div><div class="step__time">';
      if (missing) html += '<span>No record</span>';
      else html += '<span title="Finished at">' + I.check.replace('<svg', '<svg class="ico--sm" style="width:12px;height:12px"') + '</span><span>' + hhmmss(s.finishedAt) + '</span>';
      if (loss) html += lossPill(1, 'sm');
      html += '</div></div>';

      // inputs
      html += '<div class="step__inputs" aria-label="Inputs">';
      if (missing) {
        def.inputs.length
          ? def.inputs.forEach(function (p) { html += '<span class="chip chip--none">expects ' + p[0] + '</span>'; })
          : html += '<span class="chip chip--none">input none</span>';
      } else if (!s.inputs.length) {
        html += '<span class="chip chip--none">input none</span>';
      } else {
        s.inputs.forEach(function (inp, k) {
          var from = STEPS[def.inputs[k][1]].name;
          html += '<span class="chip" title="from ' + from + '">' + I.arrowIn + inp.name + ' <b>' + fmt(inp.value) + '</b></span>';
        });
      }
      html += '</div>';

      // output
      if (missing) {
        html += '<div class="step__missing-msg">' + I.gap.replace('<svg', '<svg class="ico"') + '<span>Step did not report for this run</span></div>';
      } else {
        var m = metric(s), pm = prev ? metric(stepOf(prev, s.name)) : null;
        var barW = m ? Math.max(4, Math.log10(m + 1) / Math.log10(maxOut + 1) * 100) : 0;
        html += '<div class="step__output">';
        if (s.output == null) {
          html += '<div class="step__count step__count--na num">n/a</div><div class="step__sub">returns nothing</div>';
        } else {
          html += '<div class="step__count num">' + fmt(s.output) + '</div><div class="step__sub"><span>output</span>' + (compact ? '' : deltaChip(m, pm)) + '</div>';
          if (!compact) html += '<div class="step__bar" aria-hidden="true"><i style="width:' + barW.toFixed(1) + '%"></i></div>';
        }
        html += '</div>';
      }

      // sparkline (desktop list only)
      if (!compact) {
        var vals = hist.map(function (r) { return metric(stepOf(r, s.name)); });
        html += '<div class="step__spark" title="Last ' + vals.length + ' runs">' + sparkline(vals) +
          '<div class="spark-cap">' + (s.output == null && !missing ? 'input · ' : '') + vals.length + ' runs</div></div>';
      }
      html += '</article></li>';
    })(run.steps[i]);
    return html;
  }

  /* ------------------------------------------------------------------
     LATEST view
     ------------------------------------------------------------------ */
  function heroHTML(run, runs) {
    var a = analyse(run), h = headline(run);
    var prev = runs[runs.indexOf(run) + 1], ph = prev ? headline(prev) : {};
    var title = a.complete
      ? (a.loss.length ? 'Run finished, but one step lost data' : a.stale ? 'Latest run completed — but it’s old' : 'Last night’s run completed')
      : 'Run stopped before the end';
    var why = '';
    if (!a.complete) why = '<p class="hero__why">First missing step: <code>' + a.firstMissing + '</code>. ' + a.missingCount + ' of 9 steps did not report, so statistics were not saved for this run.</p>';
    else if (a.loss.length) why = '<p class="hero__why"><code>' + a.loss[0].name + '</code> received input but produced 0 items. Downstream steps ran, but their counts may be incomplete.</p>';

    var kpi = function (label, v, pv, missingTxt) {
      return '<div class="kpi' + (v == null ? ' kpi--missing' : '') + '"><span class="eyebrow">' + label + '</span>' +
        '<span class="kpi__value num">' + (v == null ? '—' : fmt(v)) + '</span>' +
        '<span class="kpi__foot">' + (v == null ? '<span class="faint" style="font-size:12px">' + missingTxt + '</span>' : deltaChip(v, pv)) + '</span></div>';
    };

    var cells = run.steps.map(function (s, i) {
      var st = s.missing ? 'missing' : isLoss(s) ? 'loss' : 'ok';
      var label = s.name + ': ' + (st === 'missing' ? 'not recorded' : st === 'loss' ? 'possible data loss' : 'ok');
      var ico = st === 'ok' ? I.check : st === 'loss' ? '!' : (i + 1);
      return '<li class="flow__cell flow__cell--' + st + '" title="' + label + '"><span class="sr-only">' + label + '</span><span aria-hidden="true">' + ico + '</span></li>';
    }).join('');

    return '<section class="card hero" aria-labelledby="hero-title">' +
      '<div>' +
        '<div class="hero__status">' + statusPill(a, 'lg') + (a.loss.length ? lossPill(a.loss.length, 'lg') : '') + (a.stale ? stalePill(a) : '') + '</div>' +
        '<h1 class="hero__title" id="hero-title">' + title + '</h1>' +
        '<div class="hero__meta">' +
          '<span>' + I.calendar + dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · started ' + hhmm(run.startedAt) + '</span>' +
          '<span>' + I.clock + 'finished ' + ago(a.ageH) + '</span>' +
          '<span>' + I.timer + dur(a.durationS) + '</span>' +
        '</div>' + why +
      '</div>' +
      '<div class="kpis">' +
        kpi('Accounts', h.accounts, ph.accounts, 'not read') +
        kpi('Calls', h.calls, ph.calls, 'not read') +
        kpi('Saved stats', h.saved, ph.saved, 'not saved') +
      '</div>' +
      '<div class="flow">' +
        '<div class="flow__groups" aria-hidden="true"><span>CallRail</span><span>Google Ads</span><span>Merge</span><span>Persist</span></div>' +
        '<ol class="flow__cells" aria-label="Step map">' + cells + '</ol>' +
        '<div class="flow__legend"><span>' + run.steps.filter(function (s) { return !s.missing; }).length + ' of 9 steps reported</span>' +
          (a.loss.length ? '<span>' + a.loss.length + ' with possible data loss</span>' : '') + '</div>' +
      '</div>' +
    '</section>';
  }

  function stepsHeadHTML(name, hint) {
    return '<div class="section-head section-head--steps"><h2 class="section-title">Steps</h2>' +
      (hint ? '<span class="faint section-hint">' + hint + '</span>' : '') + viewToggleHTML(name) + '</div>';
  }
  function viewToggleHTML(name) {
    var opt = function (v, ico, label) {
      return '<label class="segmented__opt"><input type="radio" name="' + name + '" value="' + v + '"' + (stepsView === v ? ' checked' : '') + '><span>' + ico + label + '</span></label>';
    };
    return '<fieldset class="segmented segmented--view"><legend class="sr-only">Step view</legend>' + opt('list', I.list, 'List') + opt('graph', I.graph, 'Graph') + '</fieldset>';
  }
  function renderLatest(runs) {
    var el = document.getElementById('view-latest');
    if (!runs.length) {
      if (stepsView !== 'graph') { el.innerHTML = emptyHTML(); return; }
      el.innerHTML = stepsHeadHTML('steps-view-latest') + '<section class="card graph-panel" id="latest-graph" aria-label="Pipeline graph"></section>';
      PMGraph.mount(document.getElementById('latest-graph'), { mode: 'ghost', ghostMsg:
        '<div class="empty__art">' + I.inbox + '</div><h2>No runs yet for ' + env + '</h2><p>The graph fills in after the first nightly run writes its step records.</p>' });
      return;
    }
    var run = runs[0];
    if (stepsView === 'graph') {
      el.innerHTML = heroHTML(run, runs) + stepsHeadHTML('steps-view-latest', 'Select a step to trace it') +
        '<section class="card graph-panel" id="latest-graph" aria-label="Pipeline graph"></section>' +
        '<section class="card graph-details" id="latest-graph-details" aria-live="polite" hidden></section>';
      var sel0 = params.get('select'), idx0 = null;
      STEPS.forEach(function (s, i) { if (s.name === sel0) idx0 = i; });
      PMGraph.mount(document.getElementById('latest-graph'), { run: run, runs: runs, mode: 'run', details: document.getElementById('latest-graph-details'), selected: idx0 });
    } else {
      el.innerHTML = heroHTML(run, runs) + stepsHeadHTML('steps-view-latest', 'Output per step · sparkline = last 14 runs') + stepsHTML(run, runs, false);
    }
  }

  /* ------------------------------------------------------------------
     HISTORY view
     ------------------------------------------------------------------ */
  var trendStep = 'read_callrail_call';

  function renderHistory(runs) {
    var el = document.getElementById('view-history');
    if (!runs.length) { el.innerHTML = emptyHTML(); return; }
    var opts = STEPS.map(function (s) { return '<option value="' + s.name + '"' + (s.name === trendStep ? ' selected' : '') + '>' + s.name + '</option>'; }).join('');

    var rows = runs.map(function (r, i) {
      var a = analyse(r), h = headline(r);
      var n = function (v, lbl) { return '<span class="run-row__n' + (v == null ? ' run-row__n--na' : '') + '"><span class="run-row__lbl">' + lbl + '</span>' + (v == null ? '—' : fmt(v)) + '</span>'; };
      return '<li><button class="run-row" type="button" data-run="' + i + '">' +
        '<span class="run-row__date">' + dayLabel(r.startedAt) + '<small>' + hhmm(r.startedAt) + ' · ' + dur(a.durationS) + '</small></span>' +
        '<span class="run-row__status">' + statusPill(a, 'sm') + '</span>' +
        n(h.accounts, 'Accounts') + n(h.calls, 'Calls') + n(h.saved, 'Saved') +
        '<span class="run-row__flags">' + (a.loss.length ? lossPill(a.loss.length, 'sm') : '') +
          (r.unreadable ? '<span class="pill pill--neutral pill--sm">' + I.fileX + r.unreadable + ' unreadable</span>' : '') + '</span>' +
        I.chev + '</button></li>';
    }).join('');

    el.innerHTML =
      '<section class="card trend" aria-labelledby="trend-title">' +
        '<div class="trend__head">' +
          '<div class="trend__pick"><h2 class="section-title" id="trend-title">Step trend</h2>' +
            '<label for="trend-step">Step</label><select id="trend-step" class="select">' + opts + '</select></div>' +
          '<div class="trend__stat" id="trend-stat"></div>' +
        '</div>' +
        '<div class="chart" id="chart" tabindex="0" role="img" aria-roledescription="line chart"></div>' +
        '<div class="chart__legend"><span><i class="lg-dot"></i>output per run</span><span><i class="lg-dot lg-dot--bad"></i>0 with input (possible loss)</span><span><i class="lg-dot lg-dot--gap"></i>step not recorded</span><span>Use ← → to move between runs</span></div>' +
      '</section>' +
      '<section class="card runs" aria-labelledby="runs-title">' +
        '<div class="section-head" style="padding:16px 20px"><h2 class="section-title" id="runs-title">Runs</h2><span class="faint" style="font-size:12px">' + runs.length + ' runs · last 30 days · newest first</span></div>' +
        '<div class="runs__head" aria-hidden="true"><span>Run</span><span>Status</span><span class="r">Accounts</span><span class="r">Calls</span><span class="r">Saved</span><span>Flags</span><span></span></div>' +
        '<ul class="runs__list">' + rows + '</ul>' +
      '</section>';

    document.getElementById('trend-step').addEventListener('change', function (e) { trendStep = e.target.value; drawTrend(runs); });
    el.querySelectorAll('.run-row').forEach(function (b) { b.addEventListener('click', function () { openDrawer(runs, +b.dataset.run, b); }); });
    drawTrend(runs);
  }

  /* ---- Trend chart ---- */
  function drawTrend(runs) {
    var box = document.getElementById('chart');
    var series = runs.slice().reverse();                               // oldest → newest
    var vals = series.map(function (r) { return metric(stepOf(r, trendStep)); });
    var W = Math.max(320, box.clientWidth || 900), H = box.clientWidth < 600 ? 200 : 240;
    var m = { l: 44, r: 12, t: 12, b: 26 };
    var nums = vals.filter(function (v) { return v != null; });
    var max = niceMax(Math.max.apply(null, nums.concat([1])));
    var x = function (i) { return m.l + i * (W - m.l - m.r) / Math.max(1, series.length - 1); };
    var y = function (v) { return m.t + (1 - v / max) * (H - m.t - m.b); };

    var g = '';
    for (var k = 0; k <= 4; k++) {
      var v = max * k / 4, yy = y(v).toFixed(1);
      g += '<line class="grid-line" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
           '<text class="axis-label" x="' + (m.l - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + compact(v) + '</text>';
    }
    var step = Math.ceil(series.length / (W < 600 ? 4 : 7));
    series.forEach(function (r, i) {
      if ((series.length - 1 - i) % step === 0) g += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + shortDay(r.startedAt) + '</text>';
    });

    // line + area, broken at gaps
    var line = '', area = '', seg = [];
    var flush = function () {
      if (!seg.length) return;
      line += 'M' + seg.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('L');
      area += 'M' + seg[0][0].toFixed(1) + ' ' + y(0) + 'L' + seg.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('L') + 'L' + seg[seg.length - 1][0].toFixed(1) + ' ' + y(0) + 'Z';
      seg = [];
    };
    var pts = '';
    vals.forEach(function (v, i) {
      if (v == null) { flush(); pts += '<circle class="pt pt--gap" cx="' + x(i).toFixed(1) + '" cy="' + y(0).toFixed(1) + '" r="3.5"/>'; return; }
      seg.push([x(i), y(v)]);
      var bad = v === 0 && isLoss(stepOf(series[i], trendStep));
      pts += '<circle class="pt' + (bad ? ' pt--bad' : '') + '" cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="' + (bad ? 3.5 : 2.5) + '"/>';
    });
    flush();

    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="height:' + H + 'px" aria-hidden="true">' +
      '<defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--chart-fill-top)"/><stop offset="1" stop-color="var(--chart-fill-bottom)"/></linearGradient></defs>' +
      g + '<path class="area" d="' + area + '"/><path class="line" d="' + line + '"/>' + pts +
      '<line class="cross" id="cross" x1="0" x2="0" y1="' + m.t + '" y2="' + (H - m.b) + '" visibility="hidden"/>' +
      '<circle class="focus-pt" id="focus-pt" r="5" cx="0" cy="0" visibility="hidden"/></svg>';

    var last = series.length - 1, lv = vals[last], pv = vals[last - 1];
    document.getElementById('trend-stat').innerHTML =
      '<span class="trend__value num">' + (lv == null ? '—' : fmt(lv)) + '</span>' + deltaChip(lv, pv) +
      '<span class="trend__label">Latest run (' + shortDay(series[last].startedAt) + ') vs previous run' + (STEPS.filter(function (s) { return s.name === trendStep; })[0].noOutput ? ' · step returns nothing, showing its input' : '') + '</span>';
    box.setAttribute('aria-label', trendStep + ' output for the last ' + series.length + ' runs. Latest ' + fmt(lv) + '.');

    // hover + keyboard
    var tip = document.getElementById('tooltip'), cross = box.querySelector('#cross'), fp = box.querySelector('#focus-pt'), svg = box.querySelector('svg');
    var cur = -1;
    function show(i, clientPos) {
      cur = i; var v = vals[i];
      var cx = x(i), cy = v == null ? y(0) : y(v);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      fp.setAttribute('cx', cx); fp.setAttribute('cy', cy); fp.setAttribute('visibility', v == null ? 'hidden' : 'visible');
      var prevV = i > 0 ? vals[i - 1] : null;
      tip.innerHTML = '<div class="tooltip__date">' + dayLabel(series[i].startedAt) + ' · ' + hhmm(series[i].startedAt) + '</div>' +
        '<div class="tooltip__val num">' + (v == null ? '<span class="faint">not recorded</span>' : fmt(v)) + deltaChip(v, prevV) + '</div>' +
        (v === 0 && isLoss(stepOf(series[i], trendStep)) ? '<div style="color:var(--bad);margin-top:4px">Possible data loss</div>' : '');
      tip.hidden = false;
      var r = svg.getBoundingClientRect(), sx = r.left + cx / W * r.width, sy = r.top + cy / H * r.height;
      var tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.min(window.innerWidth - tw - 8, Math.max(8, sx - tw / 2));
      var top = sy - th - 14; if (top < 64) top = sy + 14;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
      box.setAttribute('aria-valuetext', '');
    }
    function hide() { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); fp.setAttribute('visibility', 'hidden'); }
    svg.addEventListener('pointermove', function (e) {
      var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
      var i = Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, series.length - 1)));
      show(Math.max(0, Math.min(series.length - 1, i)));
    });
    svg.addEventListener('pointerleave', hide);
    box.onkeydown = function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
      e.preventDefault();
      var i = cur < 0 ? last : cur;
      i = e.key === 'Home' ? 0 : e.key === 'End' ? last : i + (e.key === 'ArrowRight' ? 1 : -1);
      show(Math.max(0, Math.min(last, i)));
    };
    box.onfocus = function () { show(cur < 0 ? last : cur); };
    box.onblur = hide;
    drawTrend._show = show;
  }
  function niceMax(v) { var p = Math.pow(10, Math.floor(Math.log10(v))); var n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }
  function compact(v) { return v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + 'k' : String(Math.round(v)); }

  /* ---- Drawer ---- */
  var lastFocus = null;
  var drawerState = null;
  function openDrawer(runs, i, trigger, keepFocus) {
    var run = runs[i], a = analyse(run), h = headline(run), prev = runs[i + 1], ph = prev ? headline(prev) : {};
    if (!keepFocus) lastFocus = trigger || document.activeElement;
    document.querySelectorAll('.run-row').forEach(function (b) { b.setAttribute('aria-current', String(+b.dataset.run === i)); });
    document.getElementById('drawer-title').textContent = dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · ' + hhmm(run.startedAt);
    var k = function (l, v, pv, t) { return '<div class="kpi"><span class="eyebrow">' + l + '</span><span class="kpi__value num">' + (v == null ? '—' : fmt(v)) + '</span><span class="kpi__foot">' + (v == null ? '<span class="faint" style="font-size:12px">' + t + '</span>' : deltaChip(v, pv)) + '</span></div>'; };
    document.getElementById('drawer-body').innerHTML =
      '<div class="drawer__summary">' + statusPill(a) + (a.loss.length ? lossPill(a.loss.length, '') : '') +
        '<span class="faint" style="font-size:13px">' + dur(a.durationS) + ' · ' + run.steps.filter(function (s) { return !s.missing; }).length + ' of 9 steps reported</span></div>' +
      (!a.complete ? '<div class="banner banner--bad" role="note">' + I.xCircle.replace('<svg', '<svg class="banner__icon"') + '<div><div class="banner__title">Incomplete run</div><div class="banner__text">First missing step: <span class="mono">' + a.firstMissing + '</span>.</div></div></div>' : '') +
      '<div class="kpis">' + k('Accounts', h.accounts, ph.accounts, 'not read') + k('Calls', h.calls, ph.calls, 'not read') + k('Saved stats', h.saved, ph.saved, 'not saved') + '</div>' +
      stepsHeadHTML('steps-view-drawer') +
      (stepsView === 'graph'
        ? '<div class="graph-panel graph-panel--bare" id="drawer-graph"></div><section class="graph-details graph-details--bare" id="drawer-graph-details" aria-live="polite" hidden></section>'
        : stepsHTML(run, runs, true));
    drawerState = { runs: runs, i: i };
    var d = document.getElementById('drawer');
    d.hidden = false; document.body.style.overflow = 'hidden';
    if (stepsView === 'graph') PMGraph.mount(document.getElementById('drawer-graph'), { run: run, runs: runs, mode: 'run', details: document.getElementById('drawer-graph-details'), prefer: 'compact' });
    if (!keepFocus) d.querySelector('.drawer__head [data-close]').focus();
  }
  function closeDrawer() {
    document.getElementById('drawer').hidden = true; document.body.style.overflow = '';
    document.querySelectorAll('.run-row').forEach(function (b) { b.removeAttribute('aria-current'); });
    if (lastFocus) lastFocus.focus();
  }
  document.querySelectorAll('#drawer [data-close]').forEach(function (b) { b.addEventListener('click', closeDrawer); });
  document.addEventListener('keydown', function (e) {
    var d = document.getElementById('drawer');
    if (d.hidden) return;
    if (e.key === 'Escape') closeDrawer();
    if (e.key === 'Tab') {                                       // simple focus trap
      var f = d.querySelectorAll('button, [href], select, [tabindex]:not([tabindex="-1"])');
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });

  /* ------------------------------------------------------------------
     States: loading, empty, error, banners
     ------------------------------------------------------------------ */
  function emptyHTML() {
    return '<section class="card empty" role="status"><div class="empty__art">' + I.inbox + '</div>' +
      '<h2>No runs yet for ' + env + '</h2>' +
      '<p>Runs show up here after the nightly pipeline writes its first step records to the <span class="mono">' + env + '</span> data store.</p>' +
      '<p class="faint" style="font-size:12px">The pipeline runs once a night, around 02:00.</p></section>';
  }
  function errorHTML() {
    return '<section class="card fatal" role="alert" aria-live="assertive"><div class="empty__art">' + I.dbOff + '</div>' +
      '<h2>Can’t reach the data store</h2>' +
      '<p>Pipeline Monitor couldn’t read run records for <span class="mono">' + env + '</span>. Counts are hidden until the connection is back, so you never see stale numbers as current.</p>' +
      '<code>ECONNREFUSED · step_records · ' + env + '</code>' +
      '<div class="retry"><button class="btn" type="button" id="retry">' + I.refresh.replace('<svg', '<svg class="ico"') + 'Retry now</button><span>Retrying automatically in 30s · last success 4m ago</span></div></section>';
  }
  function skeletonHTML() {
    var s = function (w, h, extra) { return '<span class="skel" style="width:' + w + ';height:' + h + 'px;' + (extra || '') + '"></span>'; };
    var hero = '<section class="card hero" aria-busy="true" aria-label="Loading latest run"><div style="display:flex;flex-direction:column;gap:12px">' +
      s('110px', 28, 'border-radius:999px') + s('min(380px,80%)', 26) + s('min(300px,70%)', 14) + '</div>' +
      '<div class="kpis">' + [1, 2, 3].map(function () { return '<div class="kpi" style="gap:8px">' + s('60px', 10) + s('96px', 36) + '</div>'; }).join('') + '</div>' +
      '<div class="flow"><div class="flow__cells">' + STEPS.map(function () { return s('100%', 28); }).join('') + '</div></div></section>';
    var steps = '<ol class="steps" aria-hidden="true">' + STEPS.map(function () {
      return '<li class="step"><div class="step__rail"><span class="step__node" style="border-color:var(--border-strong)"></span></div>' +
        '<div class="step__card"><div class="step__name" style="display:flex;flex-direction:column;gap:6px">' + s('70%', 14) + s('40%', 10) + '</div>' +
        '<div class="step__inputs">' + s('90px', 24) + '</div><div class="step__output">' + s('84px', 28) + '</div><div class="step__spark">' + s('128px', 36) + '</div></div></li>';
    }).join('') + '</ol>';
    if (stepsView === 'graph') steps = stepsHeadHTML('steps-view-latest') + '<section class="card graph-panel" id="latest-graph" aria-busy="true" aria-label="Loading pipeline graph"></section>';
    return '<span class="sr-only" role="status">Loading runs…</span>' + hero + steps;
  }
  function banner(kind, icon, title, text, role) {
    return '<div class="banner banner--' + kind + '" role="' + (role || 'status') + '">' + icon.replace('<svg', '<svg class="banner__icon"') +
      '<div><div class="banner__title">' + title + '</div><div class="banner__text">' + text + '</div></div></div>';
  }

  /* ------------------------------------------------------------------
     App shell: env, tabs, theme, live indicator, state switcher
     ------------------------------------------------------------------ */
  var params = new URLSearchParams(location.search);
  /* List | Graph choice: URL param > remembered choice > list */
  var stepsView = 'list';
  try { var sv = localStorage.getItem('pm-steps-view'); if (sv === 'graph' || sv === 'list') stepsView = sv; } catch (e) {}
  if (params.get('view') === 'graph' || params.get('view') === 'list') stepsView = params.get('view');
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.name || t.name.indexOf('steps-view') !== 0) return;
    stepsView = t.value;
    try { localStorage.setItem('pm-steps-view', stepsView); } catch (err) {}
    var where = t.name, drawerOpen = !document.getElementById('drawer').hidden;
    if (where === 'steps-view-drawer' && drawerState) openDrawer(drawerState.runs, drawerState.i, null, true);
    if (scenario === 'loading') { document.getElementById('view-latest').innerHTML = skeletonHTML(); if (stepsView === 'graph') PMGraph.mount(document.getElementById('latest-graph'), { mode: 'skeleton' }); }
    else if (scenario !== 'error') renderLatest(currentRuns);
    if (where === 'steps-view-latest' && drawerOpen && drawerState) openDrawer(drawerState.runs, drawerState.i, null, true);
    var back = document.querySelector('input[name="' + where + '"][value="' + stepsView + '"]');
    if (back) back.focus();
  });
  window.PM = { STEPS: STEPS, I: I, fmt: fmt, isLoss: isLoss, hhmmss: hhmmss, stepItemHTML: stepItemHTML };
  var env = params.get('env') || 'prod';
  var scenario = params.get('state') || 'healthy';
  var tab = params.get('tab') || 'latest';
  if (params.get('step')) trendStep = params.get('step');
  if (params.get('theme')) setTheme(params.get('theme'));
  var currentRuns = [];

  function render() {
    var banners = document.getElementById('banners');
    var latest = document.getElementById('view-latest'), history = document.getElementById('view-history');
    var live = document.getElementById('live');
    banners.innerHTML = '';
    live.classList.toggle('live--off', scenario === 'error' || scenario === 'loading');

    if (scenario === 'loading') {
      live.querySelector('span:last-child').textContent = 'Loading…';
      latest.innerHTML = skeletonHTML();
      if (stepsView === 'graph') PMGraph.mount(document.getElementById('latest-graph'), { mode: 'skeleton' });
      history.innerHTML = '<section class="card trend" aria-busy="true"><span class="skel" style="width:180px;height:18px"></span><span class="skel" style="width:100%;height:220px"></span></section>' +
        '<section class="card runs" aria-busy="true" style="padding:16px 20px;display:flex;flex-direction:column;gap:14px">' + [1, 2, 3, 4, 5, 6].map(function () { return '<span class="skel" style="width:100%;height:22px"></span>'; }).join('') + '</section>';
      return;
    }
    resetLive();
    if (scenario === 'error') {
      latest.innerHTML = errorHTML(); history.innerHTML = errorHTML();
      return;
    }
    currentRuns = buildRuns(env, scenario);
    if (currentRuns.length) {
      var a = analyse(currentRuns[0]);
      if (a.stale) banners.innerHTML += banner('warn', I.clock, 'No new run in the last ' + STALE_HOURS + ' hours',
        'The newest run finished ' + ago(a.ageH) + ' (' + dayLabel(a.endedAt) + ', ' + hhmm(a.endedAt) + '). Last night’s run may not have started — check the scheduler.', 'alert');
      if (currentRuns[0].unreadable) banners.innerHTML += banner('info', I.fileX, 'Some records could not be read',
        currentRuns[0].unreadable + ' step records for this run were malformed and skipped. Counts below come from the records that could be read.');
    }
    renderLatest(currentRuns);
    renderHistory(currentRuns);
  }

  // Tabs (roving tabindex, arrow keys)
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  function selectTab(name, focus) {
    tab = name;
    tabs.forEach(function (t) {
      var on = t.id === 'tab-' + name;
      t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
      if (on && focus) t.focus();
    });
    if (name === 'history' && currentRuns.length && scenario !== 'error' && scenario !== 'loading') drawTrend(currentRuns);
    if (name === 'latest') PMGraph.refresh(document.getElementById('latest-graph'));
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { selectTab(t.id.replace('tab-', '')); });
    t.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        var n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        selectTab(n.id.replace('tab-', ''), true);
      }
    });
  });

  // Environment
  document.querySelectorAll('input[name="env"]').forEach(function (r) {
    r.checked = r.value === env;
    r.addEventListener('change', function () { env = r.value; closeIfOpen(); render(); selectTab(tab); });
  });
  function closeIfOpen() { if (!document.getElementById('drawer').hidden) closeDrawer(); }

  // Theme
  function isDark() {
    var t = document.documentElement.getAttribute('data-theme');
    return t === 'dark' || (t !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('pm-theme', t); } catch (e) {}
    syncThemeLabel();
  }
  function syncThemeLabel() {
    var b = document.getElementById('theme-toggle');
    if (b) b.setAttribute('aria-label', isDark() ? 'Switch to light theme' : 'Switch to dark theme');
  }
  document.getElementById('theme-toggle').addEventListener('click', function () { setTheme(isDark() ? 'light' : 'dark'); });
  syncThemeLabel();

  // Live indicator ("Updated 12s ago"), ticks every second; a real app resets it on each poll
  var age = 12, liveTimer = null;
  function resetLive() {
    var live = document.getElementById('live');
    live.querySelector('span:last-child').innerHTML = scenario === 'error' ? 'Last updated 4m ago' : 'Updated <span id="live-age">' + age + 's</span> ago';
  }
  liveTimer = setInterval(function () {
    var el = document.getElementById('live-age'); if (!el) return;
    age = (age + 1) % 60;
    el.textContent = age < 2 ? 'just now' : age + 's';
    el.parentNode.firstChild.textContent = age < 2 ? 'Updated ' : 'Updated ';
  }, 1000);

  // Retry (prototype: just re-renders)
  document.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('#retry')) render(); });

  // Prototype state switcher
  var sel = document.getElementById('proto-state');
  sel.value = scenario;
  sel.addEventListener('change', function () { scenario = sel.value; closeIfOpen(); render(); selectTab(tab); });

  // Redraw chart on resize (keeps axis labels crisp)
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (tab === 'history' && currentRuns.length && scenario !== 'error' && scenario !== 'loading') drawTrend(currentRuns); }, 120); });

  render();
  selectTab(tab);
  if (params.get('run') != null && currentRuns.length) openDrawer(currentRuns, +params.get('run'));
  if (params.get('hover') != null && tab === 'history' && drawTrend._show) drawTrend._show(+params.get('hover'));
})();
