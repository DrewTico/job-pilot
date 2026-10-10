import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const contracts = JSON.parse(readFileSync(new URL('../src/lib/contracts.json', import.meta.url)));
const fixtures = JSON.parse(readFileSync(new URL('../src/fixtures/review.json', import.meta.url)));
const packet = () => structuredClone(fixtures.packets[0]);
function modules(fetch = async () => { throw new Error('network'); }) {
  const cache = {};
  function load(name) {
    if (name.endsWith('.json')) return contracts;
    if (cache[name]) return cache[name];
    const source = readFileSync(new URL(`../src/lib/${name.replace('./', '')}.ts`, import.meta.url), 'utf8');
    const result = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true}});
    const module = {exports: {}};
    vm.runInNewContext(result.outputText, {exports: module.exports, module, require: load, fetch, AbortController});
    cache[name] = module.exports;
    return module.exports;
  }
  return {control: load('./decision-controller'), client: load('./decision-client')};
}
const json = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };
function harness() {
  const {control, client} = modules();
  const calls = [], refreshes = [];
  let p = packet();
  let detail = null;
  const reader = {
    packet: async id => { assert.equal(id, p.packet_id); return p; },
    decision: async () => { if (!detail) throw new Error('unavailable'); return detail; },
    queue: async () => ({section: 'needs-review', offset: 0, limit: 25, items: []}),
  };
  function result(action) {
    return {packet_id: p.packet_id, packet_version: p.version, decision_id: 'original-record', decision: action, historical: true,
      historical_state: {approve: 'approved_historically', reject: 'rejected', revise: 'revision_requested'}[action], current_authorization: 'currently_valid',
      message: 'Application submitted. Creates a new packet version.'};
  }
  function commit(action, body) {
    p = {...p, decision: action, current_authorization: action === 'approve' ? 'currently_valid' : 'not_approved'};
    detail = {decision_id: 'original-record', decision: action, reason_code: body.reason_code ?? null, detail: body.detail ?? null, feedback: body.feedback ?? null};
    return result(action);
  }
  const transport = {bootstrap: async () => 'memory-token', post: async (id, action, body, token) => {calls.push({id, action, body, token}); return commit(action, body);}};
  const controller = new control.DecisionController(reader, transport, (...data) => refreshes.push(data));
  controller.select(p.packet_id);
  return {control, client, controller, reader, transport, calls, refreshes, packet: () => p, commit, result};
}

test('bootstrap is required, fails closed, retries only on explicit bootstrap', async () => {
  const h = harness();
  h.controller.begin(h.packet(), 'reject'); assert.equal(h.controller.snapshot().target, null);
  h.transport.bootstrap = async () => { throw new Error('private exception'); };
  await h.controller.bootstrap(); assert.equal(h.controller.snapshot().ready, false);
  h.controller.select('b'.repeat(32)); assert.match(h.controller.snapshot().error, /Decisions unavailable/);
  assert.equal(h.calls.length, 0); assert.ok(!h.controller.snapshot().error.includes('private exception'));
  h.transport.bootstrap = async () => 'new-token'; await h.controller.bootstrap();
  assert.equal(h.controller.snapshot().phase, 'READY');
});
for (const action of ['approve', 'reject', 'revise']) test(`${action}: frozen exact DTO, one POST, canonical result and safe refresh`, async () => {
  const h = harness(); await h.controller.bootstrap();
  const p = h.packet(); const id = p.packet_id, fp = p.expected_packet_fingerprint, view = p.approval_preview.expected_approval_view_fingerprint;
  h.controller.begin(p, action); h.controller.edit('other', '  😀é\u0000\n Exact text  ');
  p.company = 'Changed later'; p.title = 'Changed later';
  assert.notEqual(h.controller.snapshot().target.company, 'Changed later');
  await h.controller.submit();
  const expected = action === 'approve' ? {expected_packet_fingerprint: fp, expected_approval_view_fingerprint: view} : action === 'reject' ?
    {expected_packet_fingerprint: fp, reason_code: 'other', detail: '  😀é\u0000\n Exact text  '} : {expected_packet_fingerprint: fp, feedback: '  😀é\u0000\n Exact text  '};
  assert.deepEqual(json(h.calls[0].body), expected); assert.equal(h.calls[0].id, id);
  assert.equal(h.controller.snapshot().phase, 'RECORDED'); assert.equal(h.refreshes.length, 1);
  assert.equal(h.controller.snapshot().target.packetId, id); assert.equal(h.controller.snapshot().next, null);
  await h.controller.submit(); assert.equal(h.calls.length, 1);
});
for (const reason of ['not_interested', 'bad_fit', 'company', 'location', 'pay', 'other']) test(`reject accepts existing ${reason} with optional empty detail`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), 'reject'); h.controller.edit(reason, ''); await h.controller.submit();
  assert.equal(h.calls[0].body.reason_code, reason); assert.equal(h.calls[0].body.detail, '');
});
for (const [action, reason, text, error] of [
  ['reject', '', '', 'Choose a reason.'], ['reject', 'invented', '', 'Choose a reason.'],
  ['revise', '', '', 'Enter revision feedback.'], ['revise', '', '\n  \t', 'Enter revision feedback.'],
  ['revise', '', '😀'.repeat(4001), 'Use 4,000 characters or fewer.'], ['reject', 'other', '😀'.repeat(4001), 'Use 4,000 characters or fewer.'],
]) test(`${action} validation: ${error} (${reason || 'blank'})`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), action); h.controller.edit(reason, text); await h.controller.submit();
  assert.equal(h.calls.length, 0); assert.equal(h.controller.snapshot().error, error);
});
for (const action of ['reject', 'revise']) test(`${action} counts Unicode code points at 4000, preserves text`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), action); h.controller.edit('other', '😀'.repeat(4000)); await h.controller.submit();
  assert.equal(h.controller.snapshot().phase, 'RECORDED'); assert.equal(Array.from(h.calls[0].body[action === 'reject' ? 'detail' : 'feedback']).length, 4000);
});
test('failed integrity or preview blocks only Approve; malformed authority blocks all actions', () => {
  const {control} = modules(); const p = packet(); p.integrity = 'failed'; p.approval_preview = null;
  assert.equal(control.canDecide(p, 'approve'), false); assert.equal(control.canDecide(p, 'reject'), true); assert.equal(control.canDecide(p, 'revise'), true);
  for (const fingerprint of ['', 'A'.repeat(64), 'a'.repeat(63), undefined]) for (const action of ['approve', 'reject', 'revise']) {
    assert.equal(control.canDecide({...p, expected_packet_fingerprint: fingerprint}, action), false);
  }
  for (const change of [{packet_id: 'b'.repeat(32)}, {packet_version: 999}, {expected_packet_fingerprint: 'b'.repeat(64)}, {expected_approval_view_fingerprint: ''}]) {
    const intact = packet(); intact.approval_preview = {...intact.approval_preview, ...change}; assert.equal(control.canDecide(intact, 'approve'), false);
  }
});
test('cancel, reopen and selection switch invalidate the old confirmation', async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), 'revise'); h.controller.edit('', 'private draft');
  h.controller.cancel(); h.controller.begin(h.packet(), 'revise'); assert.equal(h.controller.snapshot().target.text, '');
  h.controller.select('b'.repeat(32)); await h.controller.submit(); assert.equal(h.calls.length, 0);
  h.controller.select(h.packet().packet_id); assert.equal(h.controller.snapshot().target, null);
});
test('late A POST cannot overwrite B, and competing or double-click POSTs are suppressed', async () => {
  const h = harness(); await h.controller.bootstrap(); const delayed = deferred(); h.transport.post = (...args) => {h.calls.push(args); return delayed.promise;};
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); const pending = h.controller.submit();
  await h.controller.submit(); h.controller.begin(h.packet(), 'revise'); assert.equal(h.calls.length, 1);
  h.controller.select('b'.repeat(32)); assert.equal(h.controller.snapshot().busy, true); assert.equal(h.controller.snapshot().target, null);
  delayed.resolve(h.commit('reject', {reason_code: 'other', detail: ''})); await pending;
  assert.equal(h.refreshes.length, 1); assert.equal(h.refreshes[0][0].packet_id, h.packet().packet_id);
  assert.equal(h.controller.snapshot().phase, 'READY'); assert.equal(h.controller.snapshot().target, null);
});
for (const code of ['csrf_failed', 'stale_packet', 'stale_approval_view', 'decision_conflict', 'packet_integrity_failed', 'approval_not_current', 'packet_busy', 'invalid_request', 'invalid_host', 'authentication_required', 'authorization_failed']) test(`known ${code} never replays POST`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async () => {h.calls.push(true); throw new h.client.DecisionFailure(code);};
  h.controller.begin(h.packet(), 'approve'); await h.controller.submit(); assert.equal(h.controller.snapshot().phase, 'FAILED'); assert.equal(h.calls.length, 1);
  if (['csrf_failed', 'invalid_host', 'authentication_required', 'authorization_failed'].includes(code)) {
    assert.equal(h.controller.snapshot().ready, false); await h.controller.bootstrap(); assert.equal(h.calls.length, 1);
  }
});
for (const action of ['reject', 'revise']) test(`${action} lost acknowledgement reconciles exact committed text without POST replay`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async (id, action, body) => {h.calls.push(id); h.commit(action, body); throw new Error('network');};
  h.controller.begin(h.packet(), action); h.controller.edit('pay', ' exact 😀 '); await h.controller.submit();
  assert.equal(h.controller.snapshot().phase, 'RECORDED'); assert.equal(h.calls.length, 1);
});
test('ambiguous approval preserves uncertainty about original approval-view binding', async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async (id, action, body) => {h.calls.push(id); h.commit(action, body); throw new Error('network');};
  h.controller.begin(h.packet(), 'approve'); await h.controller.submit(); assert.equal(h.controller.snapshot().phase, 'AMBIGUOUS'); assert.equal(h.calls.length, 1);
});
test('ambiguous no-commit needs safe refresh and a new explicit confirmation', async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async () => {h.calls.push(true); throw new Error('network before transmission');};
  h.controller.begin(h.packet(), 'revise'); h.controller.edit('', 'text'); await h.controller.submit(); assert.equal(h.controller.snapshot().phase, 'FAILED');
  h.controller.begin(h.packet(), 'revise'); assert.equal(h.controller.snapshot().phase, 'FAILED'); await h.controller.recover();
  assert.equal(h.controller.snapshot().phase, 'READY'); assert.equal(h.calls.length, 1); h.controller.begin(h.packet(), 'revise'); assert.equal(h.controller.snapshot().target.text, '');
});
test('unresolved ambiguity and mismatching existing decision never imply success', async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async () => {throw new Error('network');}; h.reader.packet = async () => {throw new Error('network');};
  h.controller.begin(h.packet(), 'revise'); h.controller.edit('', 'text'); await h.controller.submit(); assert.equal(h.controller.snapshot().phase, 'AMBIGUOUS');
  h.reader.packet = async () => h.packet(); h.commit('reject', {reason_code: 'other', detail: ''}); await h.controller.recover();
  assert.equal(h.controller.snapshot().phase, 'FAILED'); assert.match(h.controller.snapshot().error, /existing decision/);
});
test('pagehide clears token and private drafts; late bootstrap cannot restore readiness', async () => {
  const h = harness(); const delayed = deferred(); h.transport.bootstrap = () => delayed.promise; const pending = h.controller.bootstrap();
  h.controller.clear(); delayed.resolve('stale-token'); await pending; assert.equal(h.controller.snapshot().ready, false);
  h.transport.bootstrap = async () => 'fresh'; await h.controller.bootstrap(); h.controller.begin(h.packet(), 'revise'); h.controller.edit('', 'PRIVATE_DRAFT'); h.controller.clear();
  assert.equal(h.controller.snapshot().ready, false); assert.equal(h.controller.snapshot().target, null);
});
test('pending pagehide clears form and requires GET recovery after restoration', async () => {
  const h = harness(); await h.controller.bootstrap(); const delayed = deferred(); h.transport.post = () => delayed.promise;
  h.controller.begin(h.packet(), 'revise'); h.controller.edit('', 'PRIVATE_DRAFT'); const pending = h.controller.submit(); h.controller.clear();
  h.controller.observe(h.packet()); assert.equal(h.controller.snapshot().phase, 'AMBIGUOUS'); assert.equal(h.controller.snapshot().target.text, '');
  delayed.resolve(h.result('revise')); await pending; await h.controller.bootstrap(); h.controller.begin(h.packet(), 'revise'); assert.equal(h.controller.snapshot().phase, 'AMBIGUOUS');
  await h.controller.recover(); assert.equal(h.controller.snapshot().phase, 'FAILED'); await h.controller.recover(); assert.equal(h.controller.snapshot().phase, 'READY');
});
test('acknowledged decision survives failed queue/history refresh but never offers stale next', async () => {
  const h = harness(); await h.controller.bootstrap(); h.reader.queue = async () => {throw new Error('network');};
  h.controller.begin(h.packet(), 'approve'); await h.controller.submit(); assert.equal(h.controller.snapshot().phase, 'RECORDED'); assert.equal(h.controller.snapshot().refreshed, false); assert.equal(h.controller.snapshot().next, null);
});
test('historical approval uses refreshed structured current authorization', async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async (id, action, body) => {const r = h.commit(action, body); h.packet().current_authorization = 'evidence_changed'; return r;};
  h.controller.begin(h.packet(), 'approve'); await h.controller.submit(); assert.equal(h.controller.snapshot().authorization, 'evidence_changed');
});
test('client emits only same-origin supported decision paths and required headers', async () => {
  const calls = [];
  const {client} = modules(async (path, options) => {calls.push([path, options]); return {ok: true, headers: new Map([['content-type', 'application/json']]), json: async () => path === '/api/bootstrap' ? {csrf_token: 'ephemeral', local_only: false, access_mode: 'tailscale'} : {...harness().result('reject'), created_at: 'now', current_authorization_checked_at: null, revision_status_uri: null}};});
  const token = await client.decisionClient.bootstrap(new AbortController().signal);
  await client.decisionClient.post(packet().packet_id, 'reject', {expected_packet_fingerprint: 'a'.repeat(64), reason_code: 'other', detail: ''}, token);
  assert.deepEqual(Object.keys(calls[1][1].headers).sort(), ['Accept', 'Content-Type', 'X-Job-Pilot-CSRF']);
  for (const [, options] of calls) {assert.equal(options.credentials, 'same-origin'); assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'error');}
  await assert.rejects(() => client.decisionClient.post('../apply', 'approve', {}, token)); assert.equal(calls.length, 2);
});
test('source owns no persistent token sink, identity header, employer or revision execution', () => {
  const source = ['decision-client', 'decision-controller', 'use-decisions'].map(n => readFileSync(new URL(`../src/lib/${n}.ts`, import.meta.url), 'utf8')).join('\n');
  for (const forbidden of ['localStorage', 'sessionStorage', 'indexedDB', 'document.cookie', 'console.', 'Tailscale-User', 'Authorization:', 'window.open', '/apply', '/submit', 'revision-process']) assert.ok(!source.includes(forbidden), forbidden);
  const controls = readFileSync(new URL('../src/components/decision-controls.tsx', import.meta.url), 'utf8');
  assert.ok(!controls.includes('.message')); assert.ok(controls.includes('No application submitted')); assert.ok(controls.includes('Revision generation is a separate step.'));
});

test('a refreshed packet or approval preview invalidates confirmation without mutation', async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), 'approve');
  h.controller.observe({...h.packet(), approval_preview: {...h.packet().approval_preview, expected_approval_view_fingerprint: 'c'.repeat(64)}});
  assert.equal(h.controller.snapshot().target, null); await h.controller.submit(); assert.equal(h.calls.length, 0);
});
test('next job uses only refreshed first-page queue and is never selected automatically', async () => {
  const h = harness(); await h.controller.bootstrap();
  h.reader.queue = async () => ({section: 'needs-review', limit: 25, offset: 0, items: [{packet_id: 'b'.repeat(32), title: 'Next exact job'}]});
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  assert.equal(h.controller.snapshot().next.packet_id, 'b'.repeat(32)); assert.equal(h.controller.snapshot().target.packetId, h.packet().packet_id);
});
test('a stale queue retaining the decided packet does not enable next or caught-up', async () => {
  const h = harness(); await h.controller.bootstrap();
  h.reader.queue = async () => ({section: 'needs-review', limit: 25, offset: 0, items: [{packet_id: h.packet().packet_id}]});
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  assert.equal(h.controller.snapshot().refreshed, false); assert.equal(h.controller.snapshot().next, null);
});
for (const change of [{packet_id: 'b'.repeat(32)}, {packet_version: 999}, {decision: 'approve'}, {historical_state: 'approved_historically'}, {historical: false}]) test(`mismatched result authority ${Object.keys(change)[0]} is never success`, async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async () => ({...h.result('reject'), ...change});
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  assert.notEqual(h.controller.snapshot().phase, 'RECORDED'); assert.equal(h.controller.snapshot().next, null);
});
test('known decision conflict remains failure even if GET finds the same action', async () => {
  const h = harness(); await h.controller.bootstrap();
  h.transport.post = async (id, action, body) => {h.commit(action, body); throw new h.client.DecisionFailure('decision_conflict');};
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  assert.equal(h.controller.snapshot().phase, 'FAILED'); assert.equal(h.controller.snapshot().next, null);
});
test('uncertainty follows an unresolved packet across queue navigation', async () => {
  const h = harness(); await h.controller.bootstrap(); h.transport.post = async () => {throw new Error('network');}; h.reader.packet = async () => {throw new Error('network');};
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  h.controller.select(null); assert.equal(h.controller.snapshot().uncertain, true); assert.equal(h.controller.snapshot().target, null);
});
test('late recovery uses the original record, never a new selection snapshot', async () => {
  const h = harness(); await h.controller.bootstrap(); h.reader.queue = async () => {throw new Error('network');};
  h.controller.begin(h.packet(), 'reject'); h.controller.edit('other', ''); await h.controller.submit();
  const delayed = deferred(); h.reader.packet = () => delayed.promise; const recovering = h.controller.recover(); h.controller.select('b'.repeat(32));
  delayed.resolve(h.packet()); await recovering; assert.equal(h.controller.snapshot().target, null);
  h.controller.select(h.packet().packet_id); assert.equal(h.controller.snapshot().target.packetId, h.packet().packet_id); assert.equal(h.controller.snapshot().phase, 'RECORDED');
});
test('Unicode whitespace validation agrees with Python while preserving BOM and NUL', async () => {
  const h = harness(); await h.controller.bootstrap(); h.controller.begin(h.packet(), 'revise');
  for (const text of ['\u0085', '\u001c', '\u2003\u00a0']) {
    h.controller.edit('', text); await h.controller.submit(); assert.equal(h.calls.length, 0); assert.equal(h.controller.snapshot().error, 'Enter revision feedback.');
  }
  h.controller.edit('', '\ufeff\u0000'); await h.controller.submit(); assert.equal(h.calls[0].body.feedback, '\ufeff\u0000');
});
