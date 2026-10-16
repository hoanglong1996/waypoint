/* =====================================================================
   Waypoint Monitor — app.js (prototype)
   Vanilla JS, no dependencies. Renders mock data into the static shell.

   The monitor is generic: every run carries its own FLOW DESCRIPTION
   (groups + steps + hand-offs). Nothing about a specific pipeline is
   hard-coded in the views; the mock pipelines below are only data.

   Routes (hash): #/  ·  #/p/<id>  ·  #/p/<id>/history?env=<env>
   Design-time URL params (screenshots / reviews; not part of the product):
     ?state=healthy|incomplete|loss|stale|partial|running|running-start|stalled|
            other|simple-missing|simple-unreadable|simple-version|long|many|
            loading|empty|error
     &theme=light|dark &view=list|graph &run=<index> &select=<step name> &step=<trend step>
   Storage keys: wp-theme, wp-steps-view
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
    dbOff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 5.5c0 1.7-3.4 3-7.5 3-1.2 0-2.3-.1-3.3-.3M4.5 5.5c0-.9 1-1.7 2.6-2.3M4.5 5.5v13c0 1.7 3.4 3 7.5 3 2.9 0 5.4-.7 6.7-1.6M19.5 5.5V15M3 3l18 18"/></svg>',
    inbox: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Z"/></svg>',
    route: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/></svg>',
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
    graph: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="4" width="6" height="5" rx="1.2"/><rect x="2.5" y="15" width="6" height="5" rx="1.2"/><rect x="15.5" y="9.5" width="6" height="5" rx="1.2"/><path d="M8.5 6.5h2.5a2 2 0 0 1 2 2V10a2 2 0 0 0 2 2M8.5 17.5h2.5a2 2 0 0 0 2-2V14a2 2 0 0 1 2-2"/></svg>',
    /* Live states. The spinner is a partial ring: with motion off it simply stops rotating. */
    spin: '<svg class="spin" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" opacity=".25"/><path d="M21 12a9 9 0 0 0-9-9"/></svg>',
    hourglass: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 3h11M6.5 21h11M8 3v2.5c0 2.3 4 4.2 4 6.5s-4 4.2-4 6.5V21M16 3v2.5c0 2.3-4 4.2-4 6.5s4 4.2 4 6.5V21"/></svg>'
  };

  /* ------------------------------------------------------------------
     Mock pipelines. In the product these come from discovery: each
     pipeline has a label, and each RUN carries its flow description.
     kpis = which counts the hero shows (also data, not code).
     ------------------------------------------------------------------ */
  var PIPELINES = [
    {
      id: 'callrail', label: 'CallRail', trendStep: 'read_callrail_call', scenario: 'healthy',
      envs: [
        { env: 'prod', seed: 4242, hour: 2, scale: 1, anomalies: { 4: { missingFrom: 'save_call_statistics' }, 9: { lossAt: 'read_gads_clickview' }, 17: { missingFrom: 'merge_calls_clickview' }, 23: { lossAt: 'read_callrail_call' } } },
        { env: 'qa', seed: 515, hour: 1, scale: 0.17, anomalies: { 6: { missingFrom: 'merge_calls_clickview' } } }
      ],
      kpis: [
        { label: 'Accounts', short: 'Accounts', step: 'read_callrail_account', use: 'output' },
        { label: 'Calls', short: 'Calls', step: 'read_callrail_call', use: 'output' },
        { label: 'Saved stats', short: 'Saved', step: 'save_call_statistics', use: 'input' }
      ],
      groups: [
        { id: 'callrail', title: 'CallRail' }, { id: 'gads-setup', title: 'Google Ads setup' },
        { id: 'gads-data', title: 'Google Ads data' }, { id: 'merge', title: 'Merge' },
        { id: 'stats', title: 'Statistics' }, { id: 'storage', title: 'Storage' }
      ],
      steps: [
        { name: 'read_callrail_account', label: 'Accounts', group: 'callrail', inputs: [], base: 10, dur: 1 },
        { name: 'read_callrail_call', label: 'Calls', group: 'callrail', inputs: [{ name: 'accounts', from: 'read_callrail_account' }], base: 1284, spread: 0.22, weekly: true, dur: 9 },
        { name: 'read_partners', label: 'Partners', group: 'gads-setup', inputs: [], base: 6, dur: 1 },
        { name: 'read_instances', label: 'Instances', group: 'gads-setup', inputs: [{ name: 'partners', from: 'read_partners' }], base: 14, dur: 2 },
        { name: 'read_campaigns', label: 'Campaigns', group: 'gads-data', inputs: [{ name: 'instances', from: 'read_instances' }], base: 92, jitter: 4, dur: 4 },
        { name: 'read_gads_clickview', label: 'Click views', group: 'gads-data', inputs: [{ name: 'instances', from: 'read_instances' }], base: 3410, spread: 0.2, weekly: true, dur: 38 },
        { name: 'merge_calls_clickview', label: 'Merged calls', group: 'merge', inputs: [{ name: 'calls', from: 'read_callrail_call' }, { name: 'campaigns', from: 'read_campaigns' }, { name: 'clickview', from: 'read_gads_clickview' }], pass: 'read_callrail_call', dur: 6 },
        { name: 'record_call_statistics', label: 'Record stats', group: 'stats', inputs: [{ name: 'call_statistics', from: 'merge_calls_clickview' }], base: null, dur: 3 },
        { name: 'save_call_statistics', label: 'Save stats', group: 'storage', inputs: [{ name: 'call_statistics', from: 'merge_calls_clickview' }], base: null, dur: 5 }
      ]
    },
    {
      id: 'google-ads', label: 'Google Ads', trendStep: 'read_gads_clickview', scenario: 'loss',
      envs: [
        { env: 'prod', seed: 777, hour: 2, scale: 1, anomalies: { 6: { missingFrom: 'write_clickview_rows' } } },
        { env: 'qa', seed: 31, hour: 1, scale: 0.2, anomalies: {} }
      ],
      kpis: [
        { label: 'Instances', short: 'Instances', step: 'read_instances', use: 'output' },
        { label: 'Click views', short: 'Click views', step: 'read_gads_clickview', use: 'output' },
        { label: 'Rows written', short: 'Written', step: 'write_clickview_rows', use: 'output' }
      ],
      groups: [{ id: 'gads', title: 'Google Ads' }, { id: 'transform', title: 'Transform' }, { id: 'warehouse', title: 'Warehouse' }],
      steps: [
        { name: 'read_partners', label: 'Partners', group: 'gads', inputs: [], base: 6, dur: 1 },
        { name: 'read_instances', label: 'Instances', group: 'gads', inputs: [{ name: 'partners', from: 'read_partners' }], base: 14, dur: 2 },
        { name: 'read_campaigns', label: 'Campaigns', group: 'gads', inputs: [{ name: 'instances', from: 'read_instances' }], base: 92, jitter: 4, dur: 4 },
        { name: 'read_gads_clickview', label: 'Click views', group: 'gads', inputs: [{ name: 'instances', from: 'read_instances' }], base: 3410, spread: 0.2, weekly: true, dur: 38 },
        { name: 'enrich_clickview', label: 'Enrich', group: 'transform', inputs: [{ name: 'clickview', from: 'read_gads_clickview' }, { name: 'campaigns', from: 'read_campaigns' }], pass: 'read_gads_clickview', dur: 7 },
        { name: 'dedupe_clickview', label: 'Deduplicate', group: 'transform', inputs: [{ name: 'rows', from: 'enrich_clickview' }], pass: 'enrich_clickview', ratio: 0.97, dur: 3 },
        { name: 'write_clickview_rows', label: 'Write rows', group: 'warehouse', inputs: [{ name: 'rows', from: 'dedupe_clickview' }], pass: 'dedupe_clickview', dur: 11 }
      ]
    },
    {
      id: 'facebook', label: 'Facebook', trendStep: 'read_insights', scenario: 'stale',
      envs: [{ env: 'prod', seed: 99, hour: 2, scale: 1, anomalies: {} }],
      kpis: [
        { label: 'Ad accounts', short: 'Accounts', step: 'read_ad_accounts', use: 'output' },
        { label: 'Insight rows', short: 'Insights', step: 'read_insights', use: 'output' },
        { label: 'Rows written', short: 'Written', step: 'write_insight_rows', use: 'output' }
      ],
      groups: [{ id: 'meta', title: 'Facebook' }, { id: 'warehouse', title: 'Warehouse' }],
      steps: [
        { name: 'read_ad_accounts', label: 'Ad accounts', group: 'meta', inputs: [], base: 4, dur: 1 },
        { name: 'read_insights', label: 'Ad insights', group: 'meta', inputs: [{ name: 'accounts', from: 'read_ad_accounts' }], base: 2860, spread: 0.18, weekly: true, dur: 14 },
        { name: 'convert_currency', label: 'Convert currency', group: 'meta', inputs: [{ name: 'insights', from: 'read_insights' }], pass: 'read_insights', dur: 2 },
        { name: 'write_insight_rows', label: 'Write rows', group: 'warehouse', inputs: [{ name: 'rows', from: 'convert_currency' }], pass: 'convert_currency', dur: 6 }
      ]
    },
    {
      /* appeared on its own after its first run (qa only, still running) */
      id: 'microsoft-ads', label: 'Microsoft Ads', trendStep: 'read_campaign_performance', scenario: 'first-run',
      envs: [{ env: 'qa', seed: 61, hour: 1, scale: 1, anomalies: {} }],
      kpis: [
        { label: 'Accounts', short: 'Accounts', step: 'read_accounts', use: 'output' },
        { label: 'Performance rows', short: 'Rows', step: 'read_campaign_performance', use: 'output' },
        { label: 'Rows written', short: 'Written', step: 'write_performance_rows', use: 'output' }
      ],
      groups: [{ id: 'msads', title: 'Microsoft Ads' }, { id: 'warehouse', title: 'Warehouse' }],
      steps: [
        { name: 'read_accounts', label: 'Accounts', group: 'msads', inputs: [], base: 3, dur: 1 },
        { name: 'read_campaign_performance', label: 'Performance', group: 'msads', inputs: [{ name: 'accounts', from: 'read_accounts' }], base: 640, spread: 0.2, dur: 20 },
        { name: 'write_performance_rows', label: 'Write rows', group: 'warehouse', inputs: [{ name: 'rows', from: 'read_campaign_performance' }], pass: 'read_campaign_performance', dur: 5 }
      ]
    }
  ];

  /* Design-time extras for the Home page: a very long name, and 18 more pipelines */
  var LONG_PIPE = (function () {
    var x = JSON.parse(JSON.stringify(PIPELINES[0]));
    x.id = 'callrail-eu-backfill'; x.label = 'CallRail — enterprise call tracking with campaign attribution (EU accounts, nightly backfill)';
    x.scenario = 'incomplete'; x.envs = [{ env: 'prod', seed: 4343, hour: 2, scale: 0.4, anomalies: {} }];
    return x;
  })();
  var MANY_PIPES = ['Amazon Ads', 'Apple Search Ads', 'Bing Ads', 'Criteo', 'DV360', 'LinkedIn Ads', 'Outbrain', 'Pinterest Ads', 'Quora Ads',
    'Reddit Ads', 'Snapchat Ads', 'Spotify Ads', 'Taboola', 'The Trade Desk', 'TikTok Ads', 'X Ads', 'Xandr', 'Yahoo DSP'].map(function (label, i) {
    var sc = ['healthy', 'healthy', 'loss', 'healthy', 'stale', 'healthy', 'incomplete', 'healthy', 'first-run', 'healthy', 'healthy', 'healthy', 'stalled', 'healthy', 'running', 'healthy', 'healthy', 'healthy'][i];
    return {
      id: label.toLowerCase().replace(/[^a-z0-9]+/g, '-'), label: label, trendStep: 'read_report', scenario: sc,
      envs: i % 3 === 0 ? [{ env: 'prod', seed: 100 + i * 37, hour: 2, scale: 1, anomalies: {} }, { env: 'qa', seed: 900 + i, hour: 1, scale: 0.2, anomalies: {} }]
        : [{ env: sc === 'first-run' ? 'qa' : 'prod', seed: 100 + i * 37, hour: 2, scale: 1, anomalies: {} }],
      kpis: [
        { label: 'Accounts', short: 'Accounts', step: 'read_accounts', use: 'output' },
        { label: 'Report rows', short: 'Rows', step: 'read_report', use: 'output' },
        { label: 'Rows written', short: 'Written', step: 'write_rows', use: 'output' }
      ],
      groups: [{ id: 'src', title: label }, { id: 'warehouse', title: 'Warehouse' }],
      steps: [
        { name: 'read_accounts', label: 'Accounts', group: 'src', inputs: [], base: 2 + i % 9, dur: 1 },
        { name: 'read_report', label: 'Report rows', group: 'src', inputs: [{ name: 'accounts', from: 'read_accounts' }], base: 400 + (i * 397) % 5000, spread: 0.2, weekly: true, dur: 6 + i % 20 },
        { name: 'normalize_rows', label: 'Normalize', group: 'warehouse', inputs: [{ name: 'rows', from: 'read_report' }], pass: 'read_report', dur: 2 },
        { name: 'write_rows', label: 'Write rows', group: 'warehouse', inputs: [{ name: 'rows', from: 'normalize_rows' }], pass: 'normalize_rows', dur: 4 }
      ]
    };
  });

  /* ------------------------------------------------------------------
     Mock runs
     ------------------------------------------------------------------ */
  var NOW = new Date(2026, 9, 15, 10, 12, 0);       // fixed "now" so renders are stable
  var LOADED = Date.now();
  function nowMs() { return NOW.getTime() + (Date.now() - LOADED); }   // ticks forward for live timers
  var STALE_HOURS = 26;
  function rng(seed) { var s = seed; return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  function flowOf(pipe) {
    return { version: 2, groups: clone(pipe.groups), steps: pipe.steps.map(function (s) {
      var d = { name: s.name, label: s.label, group: s.group, inputs: clone(s.inputs) };
      if (s.col != null) d.col = s.col; if (s.row != null) d.row = s.row;
      return d;
    }) };
  }

  function makeRun(pipe, d, rand, o, ec) {
    o = o || {}; ec = ec || pipe.envs[0];
    var live = !!(o.running || o.runningStart);
    var start = live ? new Date(NOW.getTime() - (o.runningStart ? 6e3 : 48e3)) : new Date(2026, 9, 15 - d, ec.hour, 0, 0);
    if (!live) start.setSeconds(start.getSeconds() + Math.floor(rand() * 240));
    var wk = (start.getDay() === 0 || start.getDay() === 6) ? 0.58 : 1;
    var out = {}, fin = {}, recs = [];
    pipe.steps.forEach(function (s) {
      var v;
      if (s.pass) v = Math.round(out[s.pass] * (s.ratio || 1));
      else if (s.base == null) v = null;
      else if (d === 0) v = Math.max(1, Math.round(s.base * ec.scale));
      else v = Math.max(1, Math.round(s.base * ec.scale * (s.weekly ? wk : 1) * (1 + (rand() - 0.5) * (s.spread || 0))) - (s.jitter ? Math.floor(rand() * s.jitter) : 0));
      if (o.lossAt === s.name) v = 0;
      out[s.name] = v;
      /* a step starts when all its producers have finished (branches run in parallel) */
      var t0 = s.inputs.reduce(function (m, inp) { return fin[inp.from] && fin[inp.from] > m ? fin[inp.from] : m; }, start);
      var t1 = new Date(t0.getTime() + (s.dur + Math.floor(rand() * 3)) * 1000);
      fin[s.name] = t1;
      recs.push({ name: s.name, label: s.label, state: 'done', startedAt: t0, finishedAt: t1,
        inputs: s.inputs.map(function (inp) { return { name: inp.name, value: out[inp.from] }; }),
        output: (s.base === null && !s.pass) ? null : v });
    });
    var names = pipe.steps.map(function (s) { return s.name; });
    var cut = function (name) { var k = names.indexOf(name); return k < 0 ? recs : recs.slice(0, k); };
    if (o.missingFrom) recs = cut(o.missingFrom);
    if (o.running) {
      var k = names.indexOf(o.running), r = recs[k];
      r.state = 'running'; r.finishedAt = null; r.output = null;
      /* steps in other branches that finished before the running step started stay; later ones have not started */
      recs = recs.slice(0, k + 1).filter(function (x) { return x === r || x.finishedAt < r.startedAt || names.indexOf(x.name) < k; });
    }
    if (o.runningStart) recs = [];
    if (o.stalled) {
      var ks = names.indexOf(o.stalled), rs = recs[ks];
      rs.state = 'stalled'; rs.finishedAt = null; rs.output = null; rs.expectedS = 40;
      recs = recs.slice(0, ks + 1);
    }
    var run = { id: pipe.id + '-' + ec.env + '-' + start.toISOString().slice(0, 16), pipeline: pipe.id, env: ec.env, startedAt: start, live: live,
      flow: flowOf(pipe), flowStatus: 'ok', problems: [], records: recs, unreadable: o.unreadable || 0 };

    if (o.other) {
      /* the run reports two steps that its flow description does not list, and one
         declared input points at a producer that is not in the flow (dangling) */
      var merge = run.flow.steps.filter(function (s) { return s.name === 'merge_calls_clickview'; })[0];
      merge.inputs.push({ name: 'tags', from: 'read_call_tags' });
      var camp = run.flow.steps.filter(function (s) { return s.name === 'read_campaigns'; })[0];
      camp.inputs.push({ name: 'stats', from: 'record_call_statistics' });       // makes a loop → dropped
      var callRec = recs[1];
      recs.splice(2, 0, { name: 'read_call_tags', label: 'Call tags', state: 'done', startedAt: callRec.startedAt,
        finishedAt: new Date(callRec.finishedAt.getTime() + 2000), inputs: [{ name: 'accounts', value: 10 }], output: 2140 });
      recs.filter(function (x) { return x.name === 'merge_calls_clickview'; })[0].inputs.push({ name: 'tags', value: 2140 });
      var last = recs[recs.length - 1];
      recs.push({ name: 'refresh_call_cache', label: 'Refresh call cache', state: 'done', startedAt: last.finishedAt,
        finishedAt: new Date(last.finishedAt.getTime() + 2000), inputs: [], output: null });
    }
    if (o.flowStatus) {
      run.flow = null; run.flowStatus = o.flowStatus;
      if (o.flowStatus === 'unreadable') run.problems = ['Could not parse the flow description: unexpected end of input at position 412 (expected “]” to close “steps”).'];
      if (o.flowStatus === 'version') run.recordVersion = 3;
    }
    return run;
  }

  /* All runs of a pipeline, every environment, newest first.
     The design-time scenario only changes the newest run of the first environment. */
  function buildRuns(pipe, scenario) {
    if (scenario === 'empty') return [];
    if (scenario === 'first-run') { var e0 = pipe.envs[0]; return [makeRun(pipe, 0, rng(e0.seed), { running: pipe.steps[1].name }, e0)]; }
    var all = [];
    pipe.envs.forEach(function (ec, ei) {
      var rand = rng(ec.seed), runs = [];
      for (var d = 0; d < 30; d++) {
        var o = ec.anomalies[d] || {};
        if (d === 0 && ei === 0) {
          var pick = function (a, b) { return pipe.steps.some(function (s) { return s.name === a; }) ? a : b; };
          if (scenario === 'incomplete') o = { missingFrom: pick('read_gads_clickview', pipe.steps[Math.floor(pipe.steps.length / 2)].name) };
          if (scenario === 'loss') o = { lossAt: pick('read_campaigns', pipe.steps[1].name) };
          if (scenario === 'partial') o = { unreadable: 2 };
          if (scenario === 'running') o = { running: pick('read_gads_clickview', pipe.steps[1].name) };
          if (scenario === 'running-start') o = { runningStart: true };
          if (scenario === 'stalled') o = { stalled: pick('read_gads_clickview', pipe.steps[1].name) };
          if (scenario === 'other' && pipe.steps.some(function (s) { return s.name === 'merge_calls_clickview'; })) o = { other: true };
          if (scenario === 'simple-missing') o = { flowStatus: 'missing' };
          if (scenario === 'simple-unreadable') o = { flowStatus: 'unreadable' };
          if (scenario === 'simple-version') o = { flowStatus: 'version' };
        }
        runs.push(makeRun(pipe, d, rand, o, ec));
      }
      if (scenario === 'stale') runs.shift();          // last night's run never arrived
      all = all.concat(runs);
    });
    return all.sort(function (x, y) { return y.startedAt - x.startedAt; });
  }

  /* ------------------------------------------------------------------
     MODEL: one normalised view of a run, used by every screen.
       m.steps   flow steps in declaration order (or report order in simple mode)
       m.other   reported steps that are NOT in the flow description
       m.groups  [{id, title, slot}] slot = colour slot 0–7 in declaration order
       m.edges   kept hand-offs {from, to, input} (indices into m.steps)
       m.dangling inputs whose producer is not in the flow {to, input, from}
       m.problems human-readable problems with the description
     Each step: {name, label, group, slot, inputs[{name, from, fromInFlow, value}],
                 rec, state: ok|loss|running|waiting|stalled|stopped|unreached, notInFlow}
     ------------------------------------------------------------------ */
  function model(run) {
    if (run._m) return run._m;
    var recs = {};
    run.records.forEach(function (r) { recs[r.name] = r; });
    var order = run.records.slice().sort(function (a, b) { return (a.finishedAt || a.startedAt) - (b.finishedAt || b.startedAt); }).map(function (r) { return r.name; });
    var m = { run: run, simple: !run.flow, flowStatus: run.flowStatus || 'ok', groups: [], steps: [], other: [], edges: [], dangling: [], problems: (run.problems || []).slice(), byName: {}, affected: {} };
    var inFlow = {}, groupOf = {};
    if (run.flow) {
      run.flow.steps.forEach(function (d) { inFlow[d.name] = true; });
      m.groups = run.flow.groups.map(function (g, i) { var x = { id: g.id, title: g.title, slot: i % 8 }; groupOf[g.id] = x; return x; });
    }
    function vstep(def, rec, notInFlow) {
      var g = def.group != null ? groupOf[def.group] : null;
      return {
        name: def.name, label: def.label || (rec && rec.label) || def.name, group: g ? g.id : null, groupTitle: g ? g.title : null, slot: g ? g.slot : null,
        def: def, rec: rec || null, notInFlow: !!notInFlow,
        inputs: def.inputs.map(function (inp) {
          var v; if (rec) rec.inputs.forEach(function (x) { if (x.name === inp.name) v = x.value; });
          return { name: inp.name, from: inp.from || null, fromInFlow: inp.from ? !!inFlow[inp.from] : null, value: v };
        })
      };
    }
    var recDef = function (n) { return { name: n, label: recs[n].label, inputs: recs[n].inputs.map(function (x) { return { name: x.name, from: null }; }) }; };
    if (run.flow) {
      run.flow.steps.forEach(function (d) { m.steps.push(vstep(d, recs[d.name], false)); });
      order.forEach(function (n) { if (!inFlow[n]) m.other.push(vstep(recDef(n), recs[n], true)); });
      /* hand-offs, dangling inputs, loops */
      var idx = {}; run.flow.steps.forEach(function (d, i) { idx[d.name] = i; });
      var E = [];
      run.flow.steps.forEach(function (d, j) {
        d.inputs.forEach(function (inp) {
          if (!inp.from) return;
          if (idx[inp.from] == null) {
            m.dangling.push({ to: j, input: inp.name, from: inp.from });
            m.problems.push('Input “' + inp.name + '” of ' + d.name + ' names ' + inp.from + ' as its producer, but ' + inp.from + ' is not in this run’s flow description, so it is drawn as a short dashed stub.');
          } else E.push({ from: idx[inp.from], to: j, input: inp.name });
        });
      });
      /* Loops: find a cycle, drop the edge that points furthest BACK in declaration
         order (that is the hand-off that "closes" the loop), repeat until acyclic. */
      var keep = E.slice();
      for (;;) {
        var color = [], stack = [], found = null, adj = m.steps.map(function () { return []; });
        keep.forEach(function (e, ei) { adj[e.from].push(ei); });
        var dfs = function (u) {
          color[u] = 1; stack.push(u);
          for (var t = 0; t < adj[u].length && !found; t++) {
            var v = keep[adj[u][t]].to;
            if (color[v] === 1) {
              found = [];
              for (var k = stack.indexOf(v); k < stack.length; k++) {
                var a = stack[k], b = k + 1 < stack.length ? stack[k + 1] : v;
                for (var x = 0; x < keep.length; x++) if (keep[x].from === a && keep[x].to === b) { found.push(x); break; }
              }
            } else if (!color[v]) dfs(v);
          }
          stack.pop(); color[u] = 2;
        };
        for (var r = 0; r < m.steps.length && !found; r++) if (!color[r]) dfs(r);
        if (!found) break;
        var best = found.reduce(function (bi, ei) { return (keep[ei].from - keep[ei].to) > (keep[bi].from - keep[bi].to) ? ei : bi; }, found[0]);
        var de = keep.splice(best, 1)[0];
        m.problems.push('The hand-offs form a loop: ' + m.steps[de.from].name + ' → ' + m.steps[de.to].name + ' (' + de.input + ') was left out of the graph so the rest can still be drawn.');
      }
      m.edges = keep;
      if (m.other.length) m.problems.push(m.other.length + ' reported step' + (m.other.length > 1 ? 's are' : ' is') + ' not in the flow description (' + m.other.map(function (s) { return s.name; }).join(', ') + '); listed under “Other steps”.');
    } else {
      order.forEach(function (n) { m.steps.push(vstep(recDef(n), recs[n], false)); });
    }

    /* states */
    var all = m.steps.concat(m.other);
    var anyStalled = run.records.some(function (r) { return r.state === 'stalled'; });
    var seenMissing = false;
    all.forEach(function (s) {
      var r = s.rec;
      if (r) s.state = r.state === 'running' ? 'running' : r.state === 'stalled' ? 'stalled' : isLoss(s) ? 'loss' : 'ok';
      else if (run.live) s.state = 'waiting';
      else if (anyStalled || seenMissing) s.state = 'unreached';
      else { s.state = 'stopped'; seenMissing = true; }
    });
    /* downstream of a loss step (via kept hand-offs) */
    var q = []; m.steps.forEach(function (s, i) { if (s.state === 'loss') q.push(i); });
    while (q.length) { var u = q.shift(); m.edges.forEach(function (e) { if (e.from === u && !m.affected[m.steps[e.to].name]) { m.affected[m.steps[e.to].name] = true; q.push(e.to); } }); }
    all.forEach(function (s, k) { s.pos = k + 1; m.byName[s.name] = s; });
    m.all = all;
    run._m = m;
    return m;
  }
  function isLoss(s) {
    var r = s.rec;
    if (!r || r.state !== 'done' || r.output !== 0) return false;
    return r.inputs.some(function (i) { return i.value > 0; });
  }
  function recOf(run, name) { var s = model(run).byName[name]; return s && s.rec && s.rec.state === 'done' ? s.rec : null; }
  /* The value plotted / compared for a step: its output, or its main input when the step returns nothing */
  function metric(run, name) { var r = recOf(run, name); if (!r) return null; return r.output != null ? r.output : (r.inputs[0] ? r.inputs[0].value : null); }

  function analyse(run) {
    var m = model(run);
    var by = function (st) { return m.all.filter(function (s) { return s.state === st; }); };
    var running = by('running'), stalled = by('stalled'), loss = by('loss');
    var missing = m.steps.filter(function (s) { return s.state === 'stopped' || s.state === 'unreached'; });
    var done = run.records.filter(function (r) { return r.finishedAt; });
    var end = done.length ? new Date(Math.max.apply(null, done.map(function (r) { return r.finishedAt.getTime(); }))) : run.startedAt;
    var status = run.live ? 'running' : stalled.length ? 'stalled' : missing.length ? 'incomplete' : 'complete';
    var ageH = (NOW - end) / 36e5;
    return {
      status: status, complete: status === 'complete', live: status === 'running',
      running: running, stalled: stalled, loss: loss, missing: missing,
      firstMissing: missing.length ? missing[0].name : null,
      reported: run.records.length, total: m.simple ? run.records.length : m.steps.length + m.other.length,
      endedAt: end, durationS: Math.round((end - run.startedAt) / 1000),
      stale: status !== 'running' && ageH > STALE_HOURS, ageH: ageH
    };
  }
  function headline(run, pipe) {
    return pipe.kpis.map(function (k) {
      var r = recOf(run, k.step);
      if (!r) return null;
      return k.use === 'input' ? (r.inputs[0] ? r.inputs[0].value : null) : r.output;
    });
  }

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
  /* Elapsed time for live steps: "42 s", "3m 05s", "1h 02m" */
  function elapsedText(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    if (s < 60) return s + ' s';
    if (s < 3600) return Math.floor(s / 60) + 'm ' + p2(s % 60) + 's';
    return Math.floor(s / 3600) + 'h ' + p2(Math.floor(s % 3600 / 60)) + 'm';
  }
  /* A span the 1-second ticker keeps up to date */
  function elapsedHTML(since, cls) {
    return '<span class="js-elapsed num' + (cls ? ' ' + cls : '') + '" data-since="' + since.getTime() + '">' + elapsedText(nowMs() - since.getTime()) + '</span>';
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function deltaChip(cur, prev, opts) {
    opts = opts || {};
    if (cur == null || prev == null) return '';
    if (prev === 0 && cur === 0) return '<span class="delta delta--flat">' + I.flat + '0%</span>';
    if (prev === 0) return '<span class="delta delta--up">' + I.up + 'new</span>';
    var pct = (cur - prev) / prev * 100;
    var r = Math.abs(pct) < 0.05 ? 0 : pct;
    var cls = r === 0 ? 'flat' : r > 0 ? 'up' : 'down';
    var icon = r === 0 ? I.flat : r > 0 ? I.up : I.down;
    var txt = (r > 0 ? '+' : r < 0 ? '−' : '') + Math.abs(r).toFixed(Math.abs(r) >= 10 ? 0 : 1) + '%';
    var sr = r === 0 ? 'no change' : (r > 0 ? 'up ' : 'down ') + Math.abs(r).toFixed(1) + ' percent';
    return '<span class="delta delta--' + cls + '" title="vs previous run (' + fmt(prev) + ')">' + icon +
      '<span aria-hidden="true">' + txt + '</span><span class="sr-only">' + sr + (opts.label ? ' ' + opts.label : ' vs previous run') + '</span></span>';
  }

  /* ------------------------------------------------------------------
     Pills & badges (status = icon + text + colour)
     ------------------------------------------------------------------ */
  function statusPill(a, size) {
    var cls = size ? ' pill--' + size : '';
    if (a.status === 'running') return '<span class="pill pill--running' + cls + '">' + I.spin + 'Running</span>';
    if (a.status === 'stalled') return '<span class="pill pill--warn' + cls + '">' + I.alert + 'Stalled</span>';
    if (a.complete) return '<span class="pill pill--ok' + cls + '">' + I.checkCircle + 'Complete</span>';
    return '<span class="pill pill--bad' + cls + '">' + I.xCircle + 'Incomplete</span>';
  }
  function lossPill(n, size) {
    if (!n) return '';
    return '<span class="pill pill--bad pill--' + (size || 'sm') + '">' + I.octagon + (n === 1 ? 'Possible data loss' : n + ' steps with possible data loss') + '</span>';
  }
  function stalePill(a) { return '<span class="pill pill--warn pill--lg">' + I.clock + 'Stale · ' + ago(a.ageH).replace(' ago', '') + ' old</span>'; }
  /* Step-state vocabulary shared by list, step map, graph and legend */
  var STATE = {
    ok: { txt: 'Fine', long: 'fine', icon: I.check },
    loss: { txt: 'Data loss', long: 'possible data loss', icon: I.octagon },
    stopped: { txt: 'Not reported', long: 'not reported — the run stopped here', icon: I.gap },
    unreached: { txt: 'Not reached', long: 'not reached', icon: I.gap },
    running: { txt: 'Running', long: 'running now', icon: I.spin },
    waiting: { txt: 'Waiting', long: 'waiting for an earlier step', icon: I.hourglass },
    stalled: { txt: 'Stalled', long: 'stalled — running far longer than expected', icon: I.alert }
  };
  /* Environment tag: same look on Home cards, the Latest hero and the drawer */
  function envTag(env, lg) { return '<span class="env-tag' + (lg ? ' env-tag--lg' : '') + '"><span class="sr-only">Environment </span>' + esc(env) + '</span>'; }
  function notInFlowPill() { return '<span class="pill pill--neutral pill--sm pill--nif">not in flow</span>'; }

  /* ------------------------------------------------------------------
     Sparkline (inline SVG)
     ------------------------------------------------------------------ */
  function sparkline(values) {
    var W = 128, H = 36, pad = 3;
    var nums = values.filter(function (v) { return v != null; });
    if (!nums.length) return '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true"></svg>';
    var max = Math.max.apply(null, nums), min = Math.min.apply(null, nums.concat([0]));
    min = Math.min(min, max * 0.4); var span = (max - min) || 1;
    var x = function (i) { return pad + i * (W - pad * 2) / Math.max(1, values.length - 1); };
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
     Notice for runs without a usable flow description (list + graph)
     ------------------------------------------------------------------ */
  function simpleNotice(run) {
    var t = run.flowStatus === 'unreadable' ? 'Flow description unreadable'
      : run.flowStatus === 'version' ? 'Unsupported record version: this run was written by a newer pipeline library, showing steps in the order they reported'
      : 'No flow description for this run, showing steps in the order they reported';
    return '<p class="graph-notice" role="note">' + I.info + '<span>' + t + '</span></p>';
  }

  /* ------------------------------------------------------------------
     Step list
     ------------------------------------------------------------------ */
  function groupHead(title, slot) {
    return '<li class="steps__group" aria-hidden="true"><span class="eyebrow">' + (slot != null ? '<i class="gdot g-' + slot + '"></i>' : '') + esc(title) + '</span></li>';
  }
  function stepsHTML(run, runs, compact) {
    var m = model(run), html = '';
    if (m.simple) html += simpleNotice(run);
    html += '<ol class="steps' + (compact ? ' steps--compact' : '') + '">';
    var group;
    m.steps.forEach(function (s) {
      if (!m.simple && s.group !== group) { group = s.group; html += groupHead(s.groupTitle || 'Ungrouped', s.slot); }
      html += stepItemHTML(run, runs, s.name, compact);
    });
    if (m.other.length) {
      html += groupHead('Not in this run’s flow', null);
      m.other.forEach(function (s) { html += stepItemHTML(run, runs, s.name, compact); });
    }
    return html + '</ol>';
  }

  /* One step as a timeline item (<li>). Reused by the list and by the graph's details panel. */
  function stepItemHTML(run, runs, name, compact) {
    var m = model(run), s = m.byName[name];
    var idx = runs.indexOf(run), prev = runs[idx + 1];
    var hist = runs.slice(idx, idx + 14).reverse();
    var maxOut = Math.max.apply(null, m.all.map(function (x) { return metric(run, x.name) || 0; }).concat([1]));
    var st = s.state, r = s.rec, missing = st === 'stopped' || st === 'unreached';
    var cls = missing ? 'missing' : st;
    var nodeInner = st === 'loss' ? '!' : st === 'running' ? I.spin : st === 'waiting' ? I.hourglass : st === 'stalled' ? I.alert : s.pos;
    var title = s.label !== s.name
      ? '<span class="step__label">' + esc(s.label) + '</span><span class="step__sep" aria-hidden="true"> · </span><span class="step__tech">' + esc(s.name) + '</span>'
      : '<span class="step__tech step__tech--solo">' + esc(s.name) + '</span>';
    var html = '<li class="step step--' + cls + '"><div class="step__rail" aria-hidden="true"><span class="step__node">' + nodeInner + '</span></div>';
    html += '<article class="step__card" aria-label="Step ' + s.pos + ', ' + esc(s.label) + (s.label !== s.name ? ' (' + s.name + ')' : '') + ', ' + STATE[st].long + (s.notInFlow ? ', not in this run’s flow' : '') + '">';

    /* name + time row */
    html += '<div class="step__name"><div class="step__title">' + title + '</div><div class="step__time">';
    if (st === 'running') html += '<span class="t-run">' + I.spin + 'Running</span><span>started ' + hhmmss(r.startedAt) + '</span>';
    else if (st === 'stalled') html += '<span class="t-warn">' + I.alert + 'Stalled</span><span>started ' + hhmmss(r.startedAt) + '</span>';
    else if (st === 'waiting') html += '<span class="t-wait">' + I.hourglass + 'Not started</span>';
    else if (missing) html += '<span>No record</span>';
    else html += '<span title="Finished at">' + I.check.replace('<svg', '<svg style="width:12px;height:12px"') + '</span><span>' + hhmmss(r.finishedAt) + '</span>';
    if (st === 'loss') html += lossPill(1, 'sm');
    if (s.notInFlow) html += notInFlowPill();
    html += '</div></div>';

    /* inputs */
    html += '<div class="step__inputs" aria-label="Inputs">';
    if (!s.inputs.length) html += '<span class="chip chip--none">input none</span>';
    else s.inputs.forEach(function (inp) {
      var from = inp.from ? 'from ' + inp.from + (inp.fromInFlow ? '' : ' (not in this flow)') : '';
      if (inp.value === undefined) html += '<span class="chip chip--none"' + (from ? ' title="' + esc(from) + '"' : '') + '>expects ' + esc(inp.name) + '</span>';
      else html += '<span class="chip' + (inp.from && !inp.fromInFlow ? ' chip--dangling' : '') + '"' + (from ? ' title="' + esc(from) + '"' : '') + '>' + I.arrowIn + esc(inp.name) + ' <b>' + fmt(inp.value) + '</b></span>';
    });
    html += '</div>';

    /* output */
    if (st === 'running' || st === 'stalled') {
      html += '<div class="step__output step__output--live">' + elapsedHTML(r.startedAt, 'step__count step__count--' + st) +
        '<div class="step__sub">' + (st === 'running' ? 'running' : 'stalled' + (r.expectedS ? ' · usually ~' + r.expectedS + ' s' : '')) + '</div>' +
        (st === 'running' ? '<div class="step__progress" aria-hidden="true"><i></i></div>' : '') + '</div>';
    } else if (st === 'waiting') {
      html += '<div class="step__missing-msg step__wait-msg">' + I.hourglass.replace('<svg', '<svg class="ico"') + '<span>waiting for an earlier step</span></div>';
    } else if (missing) {
      html += '<div class="step__missing-msg">' + I.gap.replace('<svg', '<svg class="ico"') + '<span>' + (st === 'stopped' ? 'Step did not report for this run' : 'Not reached: the run stopped earlier') + '</span></div>';
    } else {
      var mv = metric(run, s.name), pm = prev ? metric(prev, s.name) : null;
      var barW = mv ? Math.max(4, Math.log10(mv + 1) / Math.log10(maxOut + 1) * 100) : 0;
      html += '<div class="step__output">';
      if (r.output == null) html += '<div class="step__count step__count--na num">n/a</div><div class="step__sub">returns nothing</div>';
      else {
        html += '<div class="step__count num">' + fmt(r.output) + '</div><div class="step__sub"><span>output</span>' + (compact ? '' : deltaChip(mv, pm)) + '</div>';
        if (!compact) html += '<div class="step__bar" aria-hidden="true"><i style="width:' + barW.toFixed(1) + '%"></i></div>';
      }
      html += '</div>';
    }

    /* sparkline (desktop list only) */
    if (!compact) {
      var vals = hist.map(function (x) { return metric(x, s.name); });
      html += '<div class="step__spark" title="Last ' + vals.length + ' runs">' + sparkline(vals) +
        '<div class="spark-cap">' + (r && r.output == null && st === 'ok' ? 'input · ' : '') + vals.length + ' runs</div></div>';
    }
    return html + '</article></li>';
  }

  /* ------------------------------------------------------------------
     LATEST view
     ------------------------------------------------------------------ */
  function kpiHTML(label, v, pv, placeholder) {
    return '<div class="kpi' + (v == null ? ' kpi--missing' : '') + '"><span class="eyebrow">' + esc(label) + '</span>' +
      '<span class="kpi__value num">' + (v == null ? '—' : fmt(v)) + '</span>' +
      '<span class="kpi__foot">' + (v == null ? '<span class="faint" style="font-size:12px">' + placeholder + '</span>' : deltaChip(v, pv)) + '</span></div>';
  }
  function stepMapHTML(run, a) {
    var m = model(run), segs = [];
    if (!m.simple) {
      m.steps.forEach(function (s) {
        var last = segs[segs.length - 1];
        if (last && last.group === s.group) last.n++; else segs.push({ group: s.group, title: s.groupTitle || 'Ungrouped', slot: s.slot, n: 1 });
      });
      if (m.other.length) segs.push({ group: '__other', title: 'Other', slot: null, n: m.other.length });
    }
    var list = m.simple ? m.steps : m.all;
    var cells = list.map(function (s) {
      var st = s.state, c = (st === 'stopped' || st === 'unreached') ? 'missing' : st;
      var label = s.name + ': ' + STATE[st].long + (s.notInFlow ? ' (not in flow)' : '');
      var icon = st === 'ok' ? I.check : st === 'loss' ? '!' : st === 'running' ? I.spin : st === 'waiting' ? I.hourglass : st === 'stalled' ? I.alert : s.pos;
      return '<li class="flow__cell flow__cell--' + c + '" title="' + esc(label) + '"><span class="sr-only">' + esc(label) + '</span><span aria-hidden="true">' + icon + '</span></li>';
    }).join('');
    var cols = 'grid-template-columns:repeat(' + Math.max(1, list.length) + ',minmax(0,1fr))';
    var legend = '<span>' + a.reported + ' of ' + (m.simple ? a.reported : m.steps.length + m.other.length) + ' steps reported</span>' +
      (a.running.length ? '<span class="t-run">' + I.spin + 'running ' + a.running[0].name + '</span>' : '') +
      (a.stalled.length ? '<span class="t-warn">' + I.alert + 'stalled at ' + a.stalled[0].name + '</span>' : '') +
      (a.loss.length ? '<span>' + a.loss.length + ' with possible data loss</span>' : '') +
      (m.simple ? '<span>in the order they reported</span>' : '');
    return '<div class="flow">' +
      (segs.length ? '<div class="flow__groups" aria-hidden="true" style="grid-template-columns:' + segs.map(function (g) { return g.n + 'fr'; }).join(' ') + '">' +
        segs.map(function (g) { return '<span>' + (g.slot != null ? '<i class="gdot g-' + g.slot + '"></i>' : '') + esc(g.title) + '</span>'; }).join('') + '</div>' : '') +
      '<ol class="flow__cells" aria-label="Step map" style="' + cols + '">' + cells + '</ol>' +
      '<div class="flow__legend">' + legend + '</div></div>';
  }

  function heroHTML(run, runs) {
    var a = analyse(run), h = headline(run, pipe);
    var prev = runs[runs.indexOf(run) + 1], ph = prev ? headline(prev, pipe) : [];
    var title, why = '', meta;
    if (a.status === 'running') {
      title = 'A run is in progress';
      why = a.running.length
        ? '<p class="hero__why">Running now: <code>' + esc(a.running[0].name) + '</code>. The page updates by itself every few seconds.</p>'
        : '<p class="hero__why">Started, waiting for the first step to report.</p>';
    } else if (a.status === 'stalled') {
      var sr = a.stalled[0].rec;
      title = 'Run stalled at a step';
      why = '<p class="hero__why"><code>' + esc(a.stalled[0].name) + '</code> has been running for ' + elapsedHTML(sr.startedAt) +
        (sr.expectedS ? ', far longer than the usual ~' + sr.expectedS + ' s' : '') + '. The run stopped here; later steps were not reached.</p>';
    } else if (!a.complete) {
      title = 'Run stopped before the end';
      why = '<p class="hero__why">First missing step: <code>' + esc(a.firstMissing) + '</code>. ' + a.missing.length + ' of ' + model(run).steps.length + ' steps did not report.</p>';
    } else {
      title = a.loss.length ? 'Run finished, but one step lost data' : a.stale ? 'Latest run completed — but it’s old' : 'Last night’s run completed';
      if (a.loss.length) why = '<p class="hero__why"><code>' + esc(a.loss[0].name) + '</code> received input but produced 0 items. Downstream steps ran, but their counts may be incomplete.</p>';
    }
    if (a.status === 'running') {
      /* while running: no "finished … ago", no duration */
      meta = '<span>' + I.calendar + dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · started ' + hhmm(run.startedAt) + '</span>';
    } else {
      meta = '<span>' + I.calendar + dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · started ' + hhmm(run.startedAt) + '</span>' +
        (a.status === 'stalled' ? '' : '<span>' + I.clock + 'finished ' + ago(a.ageH) + '</span><span>' + I.timer + dur(a.durationS) + '</span>');
    }
    var placeholder = a.status === 'running' ? 'in progress' : 'not reported';
    return '<section class="card hero" aria-labelledby="hero-title">' +
      '<div>' +
        '<div class="hero__status">' + statusPill(a, 'lg') + envTag(run.env, true) + (a.loss.length ? lossPill(a.loss.length, 'lg') : '') + (a.stale ? stalePill(a) : '') + '</div>' +
        '<h1 class="hero__title" id="hero-title">' + title + '</h1>' +
        '<div class="hero__meta">' + meta + '</div>' + why +
      '</div>' +
      '<div class="kpis">' + pipe.kpis.map(function (k, i) { return kpiHTML(k.label, h[i], ph[i], placeholder); }).join('') + '</div>' +
      stepMapHTML(run, a) +
    '</section>';
  }

  function stepsHeadHTML(name, hint) {
    return '<div class="section-head section-head--steps"><h2 class="section-title">Steps</h2>' +
      (hint ? '<span class="faint section-hint">' + hint + '</span>' : '') + viewToggleHTML(name) + '</div>';
  }
  function viewToggleHTML(name) {
    var opt = function (v, icon, label) {
      return '<label class="segmented__opt"><input type="radio" name="' + name + '" value="' + v + '"' + (stepsView === v ? ' checked' : '') + '><span>' + icon + label + '</span></label>';
    };
    return '<fieldset class="segmented segmented--view"><legend class="sr-only">Step view</legend>' + opt('list', I.list, 'List') + opt('graph', I.graph, 'Graph') + '</fieldset>';
  }
  function flowModel() { return model({ flow: flowOf(pipe), flowStatus: 'ok', records: [], live: false, startedAt: NOW }); }
  function renderLatest(runs) {
    var el = document.getElementById('view-latest');
    if (!runs.length) {
      if (stepsView !== 'graph') { el.innerHTML = emptyHTML(); return; }
      el.innerHTML = stepsHeadHTML('steps-view-latest') + '<section class="card graph-panel" id="latest-graph" aria-label="Pipeline graph"></section>';
      PMGraph.mount(document.getElementById('latest-graph'), { mode: 'ghost', model: flowModel(), ghostMsg:
        '<div class="empty__art">' + I.inbox + '</div><h2>No runs yet for ' + esc(pipe.label) + '</h2><p>The graph fills in after the first run writes its flow description and step records.</p>' });
      return;
    }
    var run = runs[0];
    if (stepsView === 'graph') {
      el.innerHTML = heroHTML(run, runs) + stepsHeadHTML('steps-view-latest', 'Select a step to trace it') +
        '<section class="card graph-panel" id="latest-graph" aria-label="Pipeline graph"></section>' +
        '<section class="card graph-details" id="latest-graph-details" aria-live="polite" hidden></section>';
      PMGraph.mount(document.getElementById('latest-graph'), { run: run, runs: runs, mode: 'run', details: document.getElementById('latest-graph-details'), selected: params.get('select') || null });
    } else {
      el.innerHTML = heroHTML(run, runs) + stepsHeadHTML('steps-view-latest', 'Output per step · sparkline = last 14 runs') + stepsHTML(run, runs, false);
    }
  }

  /* ------------------------------------------------------------------
     HISTORY view
     ------------------------------------------------------------------ */
  var trendStep = null;

  /* ---- Environment filter (History) ----
     Lists only environments that have runs for this pipeline, plus the applied
     one if the address asks for an environment without runs. Default: prod if
     the pipeline has prod runs, otherwise the environment of its newest run. */
  function envOptions(runsAll) {
    var counts = {};
    runsAll.forEach(function (r) { counts[r.env] = (counts[r.env] || 0) + 1; });
    var list = Object.keys(counts).sort(function (a, b) { return a === 'prod' ? -1 : b === 'prod' ? 1 : a.localeCompare(b); });
    return { list: list, counts: counts };
  }
  function appliedEnv(runsAll) {
    if (route.env) return route.env;
    return envOptions(runsAll).counts.prod ? 'prod' : runsAll[0].env;
  }
  function envBarHTML(o, env, n) {
    var list = o.list.slice(); if (list.indexOf(env) < 0) list.push(env);
    var opt = function (v) {
      return '<label class="segmented__opt"><input type="radio" name="env" value="' + esc(v) + '"' + (v === env ? ' checked' : '') + '><span>' + esc(v) +
        (o.counts[v] ? '' : '<small class="segmented__hint">no runs</small>') + '</span></label>';
    };
    return '<section class="card envbar" aria-label="Environment filter">' +
      '<div class="envbar__field"><span class="envbar__label" id="env-label">Environment</span>' +
      '<div class="segmented segmented--env" role="radiogroup" aria-labelledby="env-label">' + list.map(opt).join('') + '</div></div>' +
      '<p class="envbar__note">' + (n ? 'Showing <b>' + n + '</b> ' + esc(env) + ' runs. The trend, the runs list and run details use this environment.'
        : 'No ' + esc(env) + ' runs for this pipeline.') + '</p></section>';
  }
  function noRunsEnvHTML(env) {
    return '<section class="card empty" role="status"><div class="empty__art">' + I.inbox + '</div>' +
      '<h2>No runs in this environment</h2><p>' + esc(pipe.label) + ' has no runs in <span class="env-tag">' + esc(env) + '</span> yet. Choose another environment above.</p></section>';
  }
  function wireEnv(el) {
    el.querySelectorAll('input[name="env"]').forEach(function (r) {
      r.addEventListener('change', function () { focusEnvAfter = true; location.hash = '#/p/' + encodeURIComponent(pipe.id) + '/history?env=' + encodeURIComponent(r.value); });
    });
  }
  var focusEnvAfter = false;

  function renderHistory(runsAll) {
    var el = document.getElementById('view-history');
    if (!runsAll.length) { el.innerHTML = emptyHTML(); return; }
    var eo = envOptions(runsAll), env = appliedEnv(runsAll);
    var runs = runsAll.filter(function (r) { return r.env === env; });
    var bar = envBarHTML(eo, env, runs.length);
    if (!runs.length) { el.innerHTML = bar + noRunsEnvHTML(env); wireEnv(el); historyRuns = []; return; }
    historyRuns = runs;
    var fm = flowModel();
    if (!trendStep || !fm.byName[trendStep]) trendStep = pipe.trendStep;
    var opts = fm.steps.map(function (s) { return '<option value="' + s.name + '"' + (s.name === trendStep ? ' selected' : '') + '>' + esc(s.label) + ' · ' + s.name + '</option>'; }).join('');

    var rows = runs.map(function (r, i) {
      var a = analyse(r), h = headline(r, pipe);
      var n = function (v, lbl) { return '<span class="run-row__n' + (v == null ? ' run-row__n--na' : '') + '"><span class="run-row__lbl">' + lbl + '</span>' + (v == null ? '—' : fmt(v)) + '</span>'; };
      return '<li><button class="run-row" type="button" data-run="' + i + '">' +
        '<span class="run-row__date">' + dayLabel(r.startedAt) + '<small>' + hhmm(r.startedAt) + ' · ' + (a.status === 'running' ? 'in progress' : dur(a.durationS)) + '</small></span>' +
        '<span class="run-row__status">' + statusPill(a, 'sm') + '</span>' +
        pipe.kpis.map(function (k, j) { return n(h[j], k.short); }).join('') +
        '<span class="run-row__flags">' + (a.loss.length ? lossPill(a.loss.length, 'sm') : '') +
          (r.unreadable ? '<span class="pill pill--neutral pill--sm">' + I.fileX + r.unreadable + ' unreadable</span>' : '') + '</span>' +
        I.chev + '</button></li>';
    }).join('');

    el.innerHTML = bar +
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
        '<div class="runs__head" aria-hidden="true"><span>Run</span><span>Status</span>' + pipe.kpis.map(function (k) { return '<span class="r">' + esc(k.short) + '</span>'; }).join('') + '<span>Flags</span><span></span></div>' +
        '<ul class="runs__list">' + rows + '</ul>' +
      '</section>';

    document.getElementById('trend-step').addEventListener('change', function (e) { trendStep = e.target.value; drawTrend(runs); });
    el.querySelectorAll('.run-row').forEach(function (b) { b.addEventListener('click', function () { openDrawer(runs, +b.dataset.run, b); }); });
    wireEnv(el);
    drawTrend(runs);
  }
  var historyRuns = [];

  /* ---- Trend chart ---- */
  function drawTrend(runs) {
    var box = document.getElementById('chart');
    if (!box) return;
    var series = runs.slice().reverse();                               // oldest → newest
    var vals = series.map(function (r) { return metric(r, trendStep); });
    var W = Math.max(320, box.clientWidth || 900), H = box.clientWidth < 600 ? 200 : 240;
    var mg = { l: 44, r: 12, t: 12, b: 26 };
    var nums = vals.filter(function (v) { return v != null; });
    var max = niceMax(Math.max.apply(null, nums.concat([1])));
    var x = function (i) { return mg.l + i * (W - mg.l - mg.r) / Math.max(1, series.length - 1); };
    var y = function (v) { return mg.t + (1 - v / max) * (H - mg.t - mg.b); };
    var lossAt = function (i) { var s = model(series[i]).byName[trendStep]; return s && s.state === 'loss'; };

    var g = '';
    for (var k = 0; k <= 4; k++) {
      var v = max * k / 4, yy = y(v).toFixed(1);
      g += '<line class="grid-line" x1="' + mg.l + '" x2="' + (W - mg.r) + '" y1="' + yy + '" y2="' + yy + '"/>' +
           '<text class="axis-label" x="' + (mg.l - 8) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + compact(v) + '</text>';
    }
    var stepN = Math.ceil(series.length / (W < 600 ? 4 : 7));
    series.forEach(function (r, i) {
      if ((series.length - 1 - i) % stepN === 0) g += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + shortDay(r.startedAt) + '</text>';
    });

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
      var bad = v === 0 && lossAt(i);
      pts += '<circle class="pt' + (bad ? ' pt--bad' : '') + '" cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="' + (bad ? 3.5 : 2.5) + '"/>';
    });
    flush();

    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="height:' + H + 'px" aria-hidden="true">' +
      '<defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--chart-fill-top)"/><stop offset="1" stop-color="var(--chart-fill-bottom)"/></linearGradient></defs>' +
      g + '<path class="area" d="' + area + '"/><path class="line" d="' + line + '"/>' + pts +
      '<line class="cross" id="cross" x1="0" x2="0" y1="' + mg.t + '" y2="' + (H - mg.b) + '" visibility="hidden"/>' +
      '<circle class="focus-pt" id="focus-pt" r="5" cx="0" cy="0" visibility="hidden"/></svg>';

    var last = series.length - 1, lv = vals[last], pv = vals[last - 1];
    var def = flowModel().byName[trendStep];
    var nothing = def && recOf(series[last], trendStep) && recOf(series[last], trendStep).output == null;
    document.getElementById('trend-stat').innerHTML =
      '<span class="trend__value num">' + (lv == null ? '—' : fmt(lv)) + '</span>' + deltaChip(lv, pv) +
      '<span class="trend__label">Latest run (' + shortDay(series[last].startedAt) + ') vs previous run' + (nothing ? ' · step returns nothing, showing its input' : '') + '</span>';
    box.setAttribute('aria-label', trendStep + ' output for the last ' + series.length + ' runs. Latest ' + fmt(lv) + '.');

    var tip = document.getElementById('tooltip'), cross = box.querySelector('#cross'), fp = box.querySelector('#focus-pt'), svg = box.querySelector('svg');
    var cur = -1;
    function show(i) {
      cur = i; var v = vals[i];
      var cx = x(i), cy = v == null ? y(0) : y(v);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      fp.setAttribute('cx', cx); fp.setAttribute('cy', cy); fp.setAttribute('visibility', v == null ? 'hidden' : 'visible');
      var prevV = i > 0 ? vals[i - 1] : null;
      var live = model(series[i]).byName[trendStep];
      var noVal = live && (live.state === 'running' || live.state === 'waiting') ? 'in progress' : 'not recorded';
      tip.innerHTML = '<div class="tooltip__date">' + dayLabel(series[i].startedAt) + ' · ' + hhmm(series[i].startedAt) + '</div>' +
        '<div class="tooltip__val num">' + (v == null ? '<span class="faint">' + noVal + '</span>' : fmt(v)) + deltaChip(v, prevV) + '</div>' +
        (v === 0 && lossAt(i) ? '<div style="color:var(--bad);margin-top:4px">Possible data loss</div>' : '');
      tip.hidden = false;
      var r = svg.getBoundingClientRect(), sx = r.left + cx / W * r.width, sy = r.top + cy / H * r.height;
      var tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = Math.min(window.innerWidth - tw - 8, Math.max(8, sx - tw / 2));
      var top = sy - th - 14; if (top < 64) top = sy + 14;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
    function hide() { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); fp.setAttribute('visibility', 'hidden'); }
    svg.addEventListener('pointermove', function (e) {
      var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
      var i = Math.round((px - mg.l) / ((W - mg.l - mg.r) / Math.max(1, series.length - 1)));
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
  var lastFocus = null, drawerState = null;
  function openDrawer(runs, i, trigger, keepFocus) {
    var run = runs[i], a = analyse(run), h = headline(run, pipe), prev = runs[i + 1], ph = prev ? headline(prev, pipe) : [];
    if (!keepFocus) lastFocus = trigger || document.activeElement;
    document.querySelectorAll('.run-row').forEach(function (b) { b.setAttribute('aria-current', String(+b.dataset.run === i)); });
    document.getElementById('drawer-title').textContent = dayLabel(run.startedAt) + ', ' + run.startedAt.getFullYear() + ' · ' + hhmm(run.startedAt);
    var placeholder = a.status === 'running' ? 'in progress' : 'not reported';
    document.getElementById('drawer-body').innerHTML =
      '<div class="drawer__summary">' + statusPill(a) + envTag(run.env) + (a.loss.length ? lossPill(a.loss.length, '') : '') +
        '<span class="faint" style="font-size:13px">' + (a.status === 'running' ? 'in progress' : dur(a.durationS)) + ' · ' + a.reported + ' of ' + a.total + ' steps reported</span></div>' +
      (a.status === 'incomplete' ? '<div class="banner banner--bad" role="note">' + I.xCircle.replace('<svg', '<svg class="banner__icon"') + '<div><div class="banner__title">Incomplete run</div><div class="banner__text">First missing step: <span class="mono">' + esc(a.firstMissing) + '</span>.</div></div></div>' : '') +
      '<div class="kpis">' + pipe.kpis.map(function (k, j) { return kpiHTML(k.label, h[j], ph[j], placeholder); }).join('') + '</div>' +
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
    if (e.key === 'Tab') {
      var f = d.querySelectorAll('button, [href], select, input, summary, [tabindex]:not([tabindex="-1"])');
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
      '<h2>No runs yet for ' + esc(pipe.label) + '</h2>' +
      '<p>Runs show up here after this pipeline writes its first step records.</p></section>';
  }
  function errorHTML(home) {
    return '<section class="card fatal" role="alert" aria-live="assertive"><div class="empty__art">' + I.dbOff + '</div>' +
      '<h2>Can’t reach the data store</h2>' +
      '<p>Waypoint Monitor couldn’t read run records' + (home ? '' : ' for <b>' + esc(pipe.label) + '</b>') + '. Counts are hidden until the connection is back, so you never see stale numbers as current.</p>' +
      '<code>ECONNREFUSED · step_records' + (home ? '' : ' · ' + esc(pipe.id)) + '</code>' +
      '<div class="retry"><button class="btn" type="button" id="retry">' + I.refresh.replace('<svg', '<svg class="ico"') + 'Retry now</button>' +
      '<span>Retrying automatically in <span class="js-countdown num" data-left="30">30</span>s · last success 4m ago</span></div></section>';
  }
  function skeletonHTML() {
    var s = function (w, h, extra) { return '<span class="skel" style="width:' + w + ';height:' + h + 'px;' + (extra || '') + '"></span>'; };
    var n = pipe.steps.length;
    var hero = '<section class="card hero" aria-busy="true" aria-label="Loading latest run"><div style="display:flex;flex-direction:column;gap:12px">' +
      s('110px', 28, 'border-radius:999px') + s('min(380px,80%)', 26) + s('min(300px,70%)', 14) + '</div>' +
      '<div class="kpis">' + pipe.kpis.map(function () { return '<div class="kpi" style="gap:8px">' + s('60px', 10) + s('96px', 36) + '</div>'; }).join('') + '</div>' +
      '<div class="flow"><div class="flow__cells" style="grid-template-columns:repeat(' + n + ',minmax(0,1fr))">' + pipe.steps.map(function () { return s('100%', 28); }).join('') + '</div></div></section>';
    var steps = '<ol class="steps" aria-hidden="true">' + pipe.steps.map(function () {
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
     HOME page: every pipeline at once
     Card = newest run of the pipeline in ANY environment.
     Order: "Needs attention" (stale, incomplete, lost data) first, then
     the rest; A to Z inside each group.
     ------------------------------------------------------------------ */
  function allPipelines() {
    var list = PIPELINES.slice();
    if (scenario === 'long') list.push(LONG_PIPE);
    if (scenario === 'many') list = list.concat(MANY_PIPES);
    return list;
  }
  function findPipe(id) { var l = allPipelines(); for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i]; return null; }

  /* The design-time state switches the pipeline you are looking at; other pipelines keep their own mock state */
  var HOME_ONLY = { many: 1, long: 1 };
  function scenarioFor(p) {
    return (scenarioExplicit && route.name === 'pipeline' && pipe === p && !HOME_ONLY[scenario]) ? scenario : (p.scenario || 'healthy');
  }
  var runCache = {};
  function runsFor(p) {
    var key = p.id + '|' + scenarioFor(p);
    if (!runCache[key]) runCache[key] = buildRuns(p, scenarioFor(p));
    return runCache[key];
  }

  /* Card status: Running · Stale · Incomplete · Lost data · Completed (first match wins) */
  function cardStatus(run, a) {
    if (a.status === 'running') return { key: 'running', txt: 'Running', icon: I.spin, tone: 'running', attn: false };
    if (a.stale) return { key: 'stale', txt: 'Stale', icon: I.clock, tone: 'warn', attn: true, reason: 'Last night’s run is missing (expected every ' + STALE_HOURS + ' h at most)' };
    if (a.status === 'stalled') return { key: 'incomplete', txt: 'Incomplete', icon: I.xCircle, tone: 'bad', attn: true, reason: 'Stalled at <code>' + esc(a.stalled[0].name) + '</code>' };
    if (a.status === 'incomplete') return { key: 'incomplete', txt: 'Incomplete', icon: I.xCircle, tone: 'bad', attn: true, reason: 'Stopped at <code>' + esc(a.firstMissing) + '</code>' };
    if (a.loss.length) return { key: 'lost', txt: 'Lost data', icon: I.octagon, tone: 'bad', attn: true, reason: '<code>' + esc(a.loss[0].name) + '</code> received input but returned 0' };
    return { key: 'ok', txt: 'Completed', icon: I.checkCircle, tone: 'ok', attn: false };
  }
  function cardWhen(run, a) {
    if (a.status === 'running') return 'running for ' + elapsedHTML(run.startedAt);
    if (a.status === 'stalled') return 'stalled for ' + elapsedHTML(a.stalled[0].rec.startedAt);
    if (a.status === 'incomplete') return 'stopped ' + ago(a.ageH);
    return 'finished ' + ago(a.ageH);
  }
  /* Three headline numbers: first step, largest step, last step (same look as the hero KPIs) */
  function cardNumbers(run, a) {
    var m = model(run), list = m.steps;
    if (!list.length) return [];
    var first = list[0], last = list[list.length - 1], largest = null, best = -1;
    list.slice(1, -1).forEach(function (s) { var v = metric(run, s.name); if (v != null && v > best) { best = v; largest = s; } });
    if (!largest && list.length > 2) largest = list[1];
    return [['First step', first], ['Largest step', largest], ['Last step', last]].filter(function (x) { return x[1]; }).map(function (x) {
      return { role: x[0], step: x[1], value: metric(run, x[1].name) };
    });
  }
  function cardHTML(item) {
    var p = item.p, run = item.run, a = item.a, st = item.st, nums = cardNumbers(run, a);
    var placeholder = a.status === 'running' ? 'in progress' : 'not reported';
    var aria = p.label + ', ' + run.env + ', ' + st.txt + (st.attn ? ', needs attention' : '') + ', ' + cardWhen(run, a).replace(/<[^>]+>/g, '') + '. ' +
      nums.map(function (n) { return n.role + ' ' + n.step.label + ': ' + (n.value == null ? placeholder : fmt(n.value)); }).join(', ') + '.';
    return '<li class="pgrid__item"><a class="pcard pcard--' + st.key + (st.attn ? ' pcard--attn pcard--' + st.tone : '') + '" href="#/p/' + encodeURIComponent(p.id) + '" aria-label="' + esc(aria) + '">' +
      (st.attn ? '<span class="pcard__flag pcard__flag--' + st.tone + '">' + I.alert + 'Needs attention</span>' : '') +
      '<span class="pcard__top"><span class="pcard__name" title="' + esc(p.label) + '">' + esc(p.label) + '</span>' + envTag(run.env) + '</span>' +
      '<span class="pcard__status"><span class="pill pill--sm pill--' + st.tone + '">' + st.icon + st.txt + '</span><span class="pcard__when">' + cardWhen(run, a) + '</span></span>' +
      (st.reason ? '<span class="pcard__reason">' + st.reason + '</span>' : '') +
      '<span class="pcard__nums">' + nums.map(function (n) {
        return '<span class="pnum' + (n.value == null ? ' pnum--missing' : '') + '"><span class="eyebrow pnum__label">' + esc(n.step.label) + '</span>' +
          '<span class="pnum__value num">' + (n.value == null ? '—' : fmt(n.value)) + '</span>' +
          '<span class="pnum__name" title="' + n.role + ': ' + esc(n.step.name) + '">' + (n.value == null ? placeholder : esc(n.step.name)) + '</span></span>';
      }).join('') + '</span>' +
      '<span class="pcard__go" aria-hidden="true">Open' + I.chev.replace('run-row__chev', 'pcard__chev') + '</span>' +
    '</a></li>';
  }
  function homeHead(count, attn) {
    var sum = count == null ? '' : count + ' pipeline' + (count === 1 ? '' : 's') + (attn ? ' · <b class="t-attn">' + attn + ' need' + (attn === 1 ? 's' : '') + ' attention</b>' : ' · all fine') +
      ' · each card shows the newest run in any environment';
    return '<div class="home__head"><h1 class="home__title">Pipelines</h1>' + (sum ? '<p class="home__sum">' + sum + '</p>' : '') + '</div>';
  }
  function renderHome() {
    var el = document.getElementById('view-home'), banners = document.getElementById('banners');
    document.title = 'Pipelines · Waypoint Monitor';
    if (scenario === 'loading') {
      var sk = function (w, h, extra) { return '<span class="skel" style="width:' + w + ';height:' + h + 'px;' + (extra || '') + '"></span>'; };
      el.innerHTML = homeHead(null) + '<span class="sr-only" role="status">Loading pipelines…</span><ul class="pgrid" aria-hidden="true">' + [1, 2, 3, 4, 5, 6].map(function () {
        return '<li class="pgrid__item"><div class="pcard pcard--skel">' + sk('55%', 18) + sk('130px', 22, 'border-radius:999px') +
          '<span class="pcard__nums">' + [1, 2, 3].map(function () { return '<span class="pnum" style="gap:6px">' + sk('60%', 10) + sk('70%', 26) + sk('80%', 10) + '</span>'; }).join('') + '</span></div></li>';
      }).join('') + '</ul>';
      return;
    }
    if (scenario === 'error') { el.innerHTML = homeHead(null) + errorHTML(true); return; }
    if (scenario === 'empty' || scenario === 'no-pipelines') {
      el.innerHTML = homeHead(null) + '<section class="card empty" role="status"><div class="empty__art">' + I.route + '</div>' +
        '<h2>No pipelines yet</h2><p>Pipelines appear here after their first run.</p></section>';
      return;
    }
    var items = allPipelines().map(function (p) {
      var runs = runsFor(p); if (!runs.length) return null;
      var a = analyse(runs[0]);
      return { p: p, run: runs[0], a: a, st: cardStatus(runs[0], a) };
    }).filter(Boolean);
    var byName = function (x, y) { return x.p.label.localeCompare(y.p.label); };
    var attn = items.filter(function (i) { return i.st.attn; }).sort(byName), rest = items.filter(function (i) { return !i.st.attn; }).sort(byName);
    if (scenario === 'partial') banners.innerHTML = banner('info', I.fileX, 'Some records could not be read',
      '3 step records across 2 pipelines were malformed and skipped. The cards use the records that could be read.');
    var group = function (title, list, attnGroup) {
      return '<section class="home__group" aria-labelledby="g-' + (attnGroup ? 'attn' : 'rest') + '">' +
        '<h2 class="home__group-title' + (attnGroup ? ' home__group-title--attn' : '') + '" id="g-' + (attnGroup ? 'attn' : 'rest') + '">' + (attnGroup ? I.alert : '') + title +
        '<span class="home__count num">' + list.length + '</span></h2>' +
        '<ul class="pgrid">' + list.map(cardHTML).join('') + '</ul></section>';
    };
    el.innerHTML = homeHead(items.length, attn.length) +
      (attn.length ? group('Needs attention', attn, true) : '') +
      (rest.length ? group(attn.length ? 'Healthy and running' : 'All pipelines', rest, false) : '');
  }

  function renderNotFound(id) {
    document.title = 'Pipeline not found · Waypoint Monitor';
    document.getElementById('view-notfound').innerHTML =
      '<section class="card empty notfound" role="alert"><div class="empty__art">' + I.route + '</div>' +
      '<h1 class="notfound__title">Pipeline not found</h1>' +
      '<p>' + (id ? 'No pipeline called <span class="mono">' + esc(id) + '</span> has reported a run.' : 'This address does not match a page.') + ' Check the address, or pick a pipeline from the list.</p>' +
      '<a class="btn btn--primary" href="#/">' + I.chev.replace('run-row__chev', 'ico ico--flip') + 'All pipelines</a></section>';
  }

  /* ------------------------------------------------------------------
     App shell: routing, header, theme, live indicator, timers
     Routes (hash based, so reload and sharing return to the same view):
       #/                          Home
       #/p/<id>                    Latest
       #/p/<id>/history?env=prod   History, one environment
       anything else               "Pipeline not found"
     ------------------------------------------------------------------ */
  var params = new URLSearchParams(location.search);
  /* List | Graph choice: URL param > remembered choice > list */
  var stepsView = 'list';
  try { var sv = localStorage.getItem('wp-steps-view'); if (sv === 'graph' || sv === 'list') stepsView = sv; } catch (e) {}
  if (params.get('view') === 'graph' || params.get('view') === 'list') stepsView = params.get('view');
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.name || t.name.indexOf('steps-view') !== 0) return;
    stepsView = t.value;
    try { localStorage.setItem('wp-steps-view', stepsView); } catch (err) {}
    var where = t.name, drawerOpen = !document.getElementById('drawer').hidden;
    if (where === 'steps-view-drawer' && drawerState) openDrawer(drawerState.runs, drawerState.i, null, true);
    if (scenario === 'loading') { document.getElementById('view-latest').innerHTML = skeletonHTML(); if (stepsView === 'graph') PMGraph.mount(document.getElementById('latest-graph'), { mode: 'skeleton', model: flowModel() }); }
    else if (scenario !== 'error') renderLatest(currentRuns);
    if (where === 'steps-view-latest' && drawerOpen && drawerState) openDrawer(drawerState.runs, drawerState.i, null, true);
    var back = document.querySelector('input[name="' + where + '"][value="' + stepsView + '"]');
    if (back) back.focus();
  });

  var scenario = params.get('state') || 'healthy';
  var scenarioExplicit = params.has('state');
  if (params.get('step')) trendStep = params.get('step');
  if (params.get('theme')) setTheme(params.get('theme'));

  var route = { name: 'home' }, pipe = PIPELINES[0], lastPipeId = null;
  function parseRoute() {
    var h = location.hash.replace(/^#/, '') || '/', q = '', qi = h.indexOf('?');
    if (qi >= 0) { q = h.slice(qi + 1); h = h.slice(0, qi); }
    var qs = new URLSearchParams(q), parts = h.split('/').filter(Boolean);
    if (!parts.length) return { name: 'home' };
    if (parts[0] === 'p' && parts[1] && parts.length <= 3 && (!parts[2] || parts[2] === 'history')) {
      return { name: 'pipeline', id: decodeURIComponent(parts[1]), page: parts[2] === 'history' ? 'history' : 'latest', env: qs.get('env') };
    }
    return { name: 'notfound', id: parts[0] === 'p' ? decodeURIComponent(parts[1] || '') : '' };
  }

  window.PM = { I: I, fmt: fmt, hhmmss: hhmmss, esc: esc, model: model, STATE: STATE, stepItemHTML: stepItemHTML, elapsedHTML: elapsedHTML, simpleNotice: simpleNotice };
  var currentRuns = [];

  /* Header: Home shows brand + live + theme. Pipeline pages add a context bar:
     "All pipelines" back link · pipeline name · Latest | History tabs. */
  function syncHeader() {
    var bar = document.getElementById('ctxbar'), onPipe = route.name === 'pipeline';
    bar.hidden = !onPipe;
    if (!onPipe) return;
    var id = encodeURIComponent(pipe.id), nameEl = document.getElementById('ctx-name');
    nameEl.textContent = pipe.label; nameEl.title = pipe.label;
    var tl = document.getElementById('tab-latest'), th = document.getElementById('tab-history');
    tl.href = '#/p/' + id;
    th.href = '#/p/' + id + '/history' + (route.page === 'history' && route.env ? '?env=' + encodeURIComponent(route.env) : '');
    if (route.page === 'latest') { tl.setAttribute('aria-current', 'page'); th.removeAttribute('aria-current'); }
    else { th.setAttribute('aria-current', 'page'); tl.removeAttribute('aria-current'); }
  }
  function showView(id) {
    ['view-home', 'view-latest', 'view-history', 'view-notfound'].forEach(function (v) { document.getElementById(v).hidden = v !== id; });
  }

  function render() {
    route = parseRoute();
    if (route.name === 'pipeline') {
      var p = findPipe(route.id);
      if (!p) route = { name: 'notfound', id: route.id }; else pipe = p;
    }
    if (route.name === 'pipeline' && pipe.id !== lastPipeId) { trendStep = params.get('step') || null; lastPipeId = pipe.id; }
    var banners = document.getElementById('banners'), live = document.getElementById('live');
    banners.innerHTML = '';
    syncHeader();
    live.classList.toggle('live--off', scenario === 'error' || scenario === 'loading');
    if (scenario === 'loading') live.querySelector('span:last-child').textContent = 'Loading…'; else resetLive();

    if (route.name === 'home') { showView('view-home'); renderHome(); return; }
    if (route.name === 'notfound') { showView('view-notfound'); renderNotFound(route.id); return; }

    document.title = pipe.label + ' · ' + (route.page === 'history' ? 'History' : 'Latest') + ' · Waypoint Monitor';
    var latest = document.getElementById('view-latest'), history = document.getElementById('view-history');
    showView(route.page === 'history' ? 'view-history' : 'view-latest');
    if (scenario === 'loading') {
      latest.innerHTML = skeletonHTML();
      if (stepsView === 'graph') PMGraph.mount(document.getElementById('latest-graph'), { mode: 'skeleton', model: flowModel() });
      history.innerHTML = '<section class="card trend" aria-busy="true"><span class="skel" style="width:180px;height:18px"></span><span class="skel" style="width:100%;height:220px"></span></section>' +
        '<section class="card runs" aria-busy="true" style="padding:16px 20px;display:flex;flex-direction:column;gap:14px">' + [1, 2, 3, 4, 5, 6].map(function () { return '<span class="skel" style="width:100%;height:22px"></span>'; }).join('') + '</section>';
      return;
    }
    if (scenario === 'error') { latest.innerHTML = errorHTML(); history.innerHTML = errorHTML(); return; }
    currentRuns = runsFor(pipe);
    if (currentRuns.length) {
      var a = analyse(currentRuns[0]);
      if (a.stale) banners.innerHTML += banner('warn', I.clock, 'No new run in the last ' + STALE_HOURS + ' hours',
        'The newest run finished ' + ago(a.ageH) + ' (' + dayLabel(a.endedAt) + ', ' + hhmm(a.endedAt) + '). Last night’s run may not have started — check the scheduler.', 'alert');
      if (currentRuns[0].unreadable) banners.innerHTML += banner('info', I.fileX, 'Some records could not be read',
        currentRuns[0].unreadable + ' step records for this run were malformed and skipped. Counts below come from the records that could be read.');
    }
    if (route.page === 'history') renderHistory(currentRuns);
    else renderLatest(currentRuns);
    if (focusEnvAfter) { focusEnvAfter = false; var r = document.querySelector('input[name="env"]:checked'); if (r) r.focus(); }
  }

  window.addEventListener('hashchange', function () { closeIfOpen(); render(); if (!focusEnvAfter) window.scrollTo(0, 0); });
  function closeIfOpen() { if (!document.getElementById('drawer').hidden) closeDrawer(); }

  // Theme (key: wp-theme)
  function isDark() {
    var t = document.documentElement.getAttribute('data-theme');
    return t === 'dark' || (t !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('wp-theme', t); } catch (e) {}
    syncThemeLabel();
  }
  function syncThemeLabel() {
    var b = document.getElementById('theme-toggle');
    if (b) b.setAttribute('aria-label', isDark() ? 'Switch to light theme' : 'Switch to dark theme');
  }
  document.getElementById('theme-toggle').addEventListener('click', function () { setTheme(isDark() ? 'light' : 'dark'); });
  syncThemeLabel();

  // Live indicator ("Updated 12s ago"); a real app resets it on each poll
  var age = 12;
  function resetLive() {
    var live = document.getElementById('live');
    live.querySelector('span:last-child').innerHTML = scenario === 'error' ? 'Last updated 4m ago' : 'Updated <span id="live-age">' + age + 's</span> ago';
  }
  setInterval(function () {
    var el = document.getElementById('live-age');
    if (el) { age = (age + 1) % 60; el.textContent = age < 2 ? 'just now' : age + 's'; }
    /* live step timers count up; the retry countdown counts down */
    document.querySelectorAll('.js-elapsed').forEach(function (t) { t.textContent = elapsedText(nowMs() - +t.dataset.since); });
    document.querySelectorAll('.js-countdown').forEach(function (t) { var n = +t.dataset.left - 1; if (n < 0) n = 30; t.dataset.left = n; t.textContent = n; });
  }, 1000);

  // Retry (prototype: just re-renders)
  document.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('#retry')) render(); });

  /* ---- DESIGN-TIME TOOL: state switcher (not part of the product) ---- */
  var sel = document.getElementById('proto-state');
  if (sel) {
    sel.value = scenario;
    sel.addEventListener('change', function () { scenario = sel.value; scenarioExplicit = true; runCache = {}; closeIfOpen(); render(); });
  }

  // Redraw chart on resize
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (route.page === 'history' && historyRuns.length && scenario !== 'error' && scenario !== 'loading') drawTrend(historyRuns); }, 120); });

  render();
  if (params.get('run') != null && route.page === 'history' && historyRuns.length) openDrawer(historyRuns, +params.get('run'));
  if (params.get('hover') != null && route.page === 'history' && drawTrend._show) drawTrend._show(+params.get('hover'));
})();
