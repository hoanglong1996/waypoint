import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  appliedEnv, cardNumbers, cardReason, cardStatus, cardWhen, defaultEnv, envChoices, groupCards, homeSummary, orderEnvs,
} from '../js/model.js';

const head = (a, b, c) => [
  { key: 'first', step: 'a', label: 'A', value: a },
  { key: 'peak', step: 'b', label: 'B', value: b },
  { key: 'last', step: 'c', label: 'C', value: c },
];
function card(over = {}) {
  return {
    name: 'p', label: 'P', environments: ['prod', 'qa'], status: 'ok', needsAttention: false,
    generatedAt: new Date('2026-10-16T03:00:00Z'),
    latest: {
      runId: '20261016T020000Z', env: 'prod', status: 'complete', stale: false, startedAt: new Date('2026-10-16T02:00:00Z'),
      endedAt: new Date('2026-10-16T02:01:00Z'), ageSeconds: 3600, lossSteps: [], firstMissingStep: null,
      stalledStep: null, stalledSeconds: null, diedStep: null, lastSeenAt: null, unreadable: 0, headline: head(1, 2, 3),
    },
    ...over,
  };
}

test('card status words and tones', () => {
  assert.deepEqual(cardStatus(card({ status: 'running' })), { key: 'running', text: 'Running', tone: 'running', attn: false });
  assert.deepEqual(cardStatus(card({ status: 'stale' })), { key: 'stale', text: 'Stale', tone: 'warn', attn: true });
  assert.deepEqual(cardStatus(card({ status: 'incomplete' })), { key: 'incomplete', text: 'Incomplete', tone: 'bad', attn: true });
  assert.deepEqual(cardStatus(card({ status: 'lost' })), { key: 'lost', text: 'Lost data', tone: 'bad', attn: true });
  assert.deepEqual(cardStatus(card()), { key: 'ok', text: 'Completed', tone: 'ok', attn: false });
  assert.equal(cardStatus(card({ status: 'weird' })).key, 'ok');
});

test('the reason names the step that matters', () => {
  assert.deepEqual(cardReason(card({ status: 'stale' }), 26), { kind: 'stale', hours: 26 });
  assert.deepEqual(cardReason(card({ status: 'incomplete', latest: { ...card().latest, firstMissingStep: 'dedupe' } }), 26), { kind: 'stopped', step: 'dedupe' });
  assert.deepEqual(cardReason(card({ status: 'incomplete', latest: { ...card().latest, stalledStep: 'load', firstMissingStep: 'load' } }), 26), { kind: 'stalled', step: 'load' });
  assert.deepEqual(cardReason(card({ status: 'lost', latest: { ...card().latest, lossSteps: ['merge', 'save'] } }), 26), { kind: 'lost', step: 'merge' });
  assert.equal(cardReason(card(), 26), null);
  assert.equal(cardReason(card({ status: 'running' }), 26), null);
});

test('groups: attention first, each A to Z by label', () => {
  const cards = [
    card({ name: 'z', label: 'Zeta', needsAttention: true }),
    card({ name: 'b', label: 'beta' }),
    card({ name: 'a', label: 'Alpha' }),
    card({ name: 'm', label: 'Mid', needsAttention: true }),
  ];
  const g = groupCards(cards);
  assert.deepEqual(g.attention.map((c) => c.name), ['m', 'z']);
  assert.deepEqual(g.rest.map((c) => c.name), ['a', 'b']);
  assert.deepEqual(homeSummary(cards), { total: 4, attention: 2 });
});

test('card numbers keep their role; unreported steps keep a null value; a missing middle is dropped', () => {
  const n = cardNumbers(card({ latest: { ...card().latest, headline: head(5, null, null) } }));
  assert.deepEqual(n.map((x) => [x.role, x.step, x.value]), [['First step', 'a', 5], ['Largest step', 'b', null], ['Last step', 'c', null]]);
  const two = cardNumbers(card({ latest: { ...card().latest, headline: [
    { key: 'first', step: 'a', label: 'A', value: 5 }, { key: 'peak', step: null, label: null, value: null }, { key: 'last', step: 'b', label: 'B', value: 2 },
  ] } }));
  assert.deepEqual(two.map((x) => x.role), ['First step', 'Last step']);
});

test('when: finished, stopped, running and stalled', () => {
  assert.deepEqual(cardWhen(card()), { kind: 'finished', hours: 1 });
  assert.deepEqual(cardWhen(card({ status: 'incomplete' })), { kind: 'stopped', hours: 1 });
  assert.deepEqual(cardWhen(card({ status: 'running' })), { kind: 'running', seconds: 3600 });
  assert.deepEqual(cardWhen(card({ status: 'incomplete', latest: { ...card().latest, stalledStep: 'x', stalledSeconds: 1800 } })), { kind: 'stalled', seconds: 1800 });
});

test('environments are ordered prod first, then A to Z', () => {
  assert.deepEqual(orderEnvs(['qa', 'prod', 'dev']), ['prod', 'dev', 'qa']);
  assert.deepEqual(orderEnvs(['staging', 'qa']), ['qa', 'staging']);
});

test('default environment: prod when the pipeline has prod runs, else the newest run\'s', () => {
  assert.equal(defaultEnv(card()), 'prod');
  assert.equal(defaultEnv(card({ environments: ['qa'], latest: { ...card().latest, env: 'qa' } })), 'qa');
  assert.equal(defaultEnv(card({ environments: ['dev', 'qa'], latest: { ...card().latest, env: 'qa' } })), 'qa');
});

test('the address wins over the default; no address uses the default', () => {
  assert.equal(appliedEnv(card(), 'qa'), 'qa');
  assert.equal(appliedEnv(card(), null), 'prod');
  assert.equal(appliedEnv(card(), 'nowhere'), 'nowhere');
});

test('filter options: only environments with runs; an asked-for one without runs is added with a hint', () => {
  assert.deepEqual(envChoices(card({ environments: ['qa', 'prod'] }), 'prod'), [{ env: 'prod', hasRuns: true }, { env: 'qa', hasRuns: true }]);
  assert.deepEqual(envChoices(card({ environments: ['qa'] }), 'qa'), [{ env: 'qa', hasRuns: true }]);
  assert.deepEqual(envChoices(card({ environments: ['qa'] }), 'prod'), [{ env: 'qa', hasRuns: true }, { env: 'prod', hasRuns: false }]);
});

test('the overview signature ignores counters that change on every fetch', async () => {
  const { overviewSignature } = await import('../js/model.js');
  const a = [card({ latest: { ...card().latest, ageSeconds: 3600, stalledSeconds: 10 } })];
  const same = [card({ latest: { ...card().latest, ageSeconds: 3630, stalledSeconds: 40 }, generatedAt: new Date() })];
  assert.equal(overviewSignature(a), overviewSignature(same));
  const later = [card({ latest: { ...card().latest, ageSeconds: 3700 } })];
  assert.notEqual(overviewSignature(a), overviewSignature(later));
  const changed = [card({ status: 'lost' })];
  assert.notEqual(overviewSignature(a), overviewSignature(changed));
});

/* ---------- died cards (spec 009) ---------- */
const died = (over = {}) => card({
  status: 'died', needsAttention: true,
  latest: { ...card().latest, status: 'incomplete', firstMissingStep: 'load', diedStep: 'load', lastSeenAt: new Date('2026-10-16T02:57:00Z'), ...over },
});

test('died card: its own word, the bad tone, and it needs attention', () => {
  assert.deepEqual(cardStatus(died()), { key: 'died', text: 'Died', tone: 'bad', attn: true });
});

test('died card reason names the step the process was in', () => {
  assert.deepEqual(cardReason(died(), 26), { kind: 'died', step: 'load' });
});

test('died card time is how long ago it was last seen, not how long it ran', () => {
  assert.deepEqual(cardWhen(died()), { kind: 'died', seconds: 180 });
  assert.deepEqual(cardWhen(died(), 60), { kind: 'died', seconds: 240 });
  assert.deepEqual(cardWhen(died({ lastSeenAt: new Date('2026-10-16T03:30:00Z') })), { kind: 'died', seconds: 0 });
});

test('died is different from stalled and from incomplete', () => {
  const stalled = card({ status: 'incomplete', latest: { ...card().latest, stalledStep: 'load', stalledSeconds: 1000 } });
  assert.notEqual(cardStatus(died()).key, cardStatus(stalled).key);
  assert.notEqual(cardReason(died(), 26).kind, cardReason(stalled, 26).kind);
  assert.notEqual(cardWhen(died()).kind, cardWhen(stalled).kind);
});

test('died cards are grouped with the cards that need attention', () => {
  const g = groupCards([card({ name: 'a', label: 'A' }), died(), card({ name: 'z', label: 'Z' })]);
  assert.deepEqual(g.attention.map((c) => c.name), ['p']);
  assert.equal(g.rest.length, 2);
});

test('card wording tells a hung run from a dead one', () => {
  const stalled = card({ status: 'incomplete', latest: { ...card().latest, stalledStep: 'load', stalledSeconds: 1000 } });
  assert.equal(cardStatus(stalled).text, 'Incomplete');
  assert.equal(cardStatus(died()).text, 'Died');
  assert.deepEqual(cardReason(stalled, 26), { kind: 'stalled', step: 'load' });
  assert.deepEqual(cardReason(died(), 26), { kind: 'died', step: 'load' });
  assert.deepEqual([cardWhen(stalled).kind, cardWhen(died()).kind], ['stalled', 'died']);
});
