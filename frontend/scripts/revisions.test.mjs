import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createRequire } from 'node:module';
import { renderToStaticMarkup } from 'react-dom/server';
const contracts = JSON.parse(readFileSync(new URL('../src/lib/contracts.json', import.meta.url)));
const fixtures = JSON.parse(readFileSync(new URL('../src/fixtures/review.json', import.meta.url)));
function load(name, fetch) {
  const cache = {};
  function module(name) {
    if (name.endsWith('.json')) return contracts;
    if (cache[name]) return cache[name];
    const source = readFileSync(new URL(`../src/lib/${name.replace('./', '')}.ts`, import.meta.url), 'utf8');
    const result = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true}});
    const m = {exports: {}};
    vm.runInNewContext(result.outputText, {exports: m.exports, module: m, require: module, fetch, AbortController, setTimeout, clearTimeout});
    cache[name] = m.exports; return m.exports;
  }
  return module(name);
}
const deferred = () => { let resolve; const promise = new Promise(yes => {resolve = yes;}); return {promise, resolve}; };
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
function presentation(name = 'revision-review') {
  const source = readFileSync(new URL(`../src/components/${name}.tsx`, import.meta.url), 'utf8');
  const result = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}});
  const m = {exports: {}};
  const require = createRequire(import.meta.url);
  vm.runInNewContext(result.outputText, {exports: m.exports, module: m, require: path => {
    if (path === './packet-inspector') return {CompanyName: ({company}) => company};
    if (path === './ui/mobile-sheet') return {};
    if (path === '../lib/display') return load('./display');
    if (path === '../lib/decision-controller') return load('./decision-controller');
    return require(path);
  }});
  return m.exports;
}
test('requested and processing modules communicate truthful state once with a semantic heading', () => {
  for (const [state, title, body] of [['queued', 'Revision request recorded', 'Generation is a separate step'], ['building', 'Generating revision', 'No successor is offered yet']]) {
    const h = harness(state);
    const html = renderToStaticMarkup(presentation().RevisionSummary({packet: h.before, review: {state: {status: h.before.revision}, refresh() {}}, onChanges() {}, onSelect() {}}));
    assert.ok(html.includes(`<h2>${title}</h2>`));
    assert.equal(html.split(title).length - 1, 1);
    assert.ok(html.includes(body));
    assert.ok(!html.includes('Review successor'));
  }
});
test('passive revised packet has no dock while independent successor retains three decision controls', () => {
  const h = harness('succeeded');
  const decisions = {state: {phase: 'READY', ready: true}, controller: {}};
  const {DecisionDock} = presentation('decision-controls');
  assert.equal(renderToStaticMarkup(DecisionDock({packet: h.before, decisions})), '');
  const html = renderToStaticMarkup(DecisionDock({packet: h.after, decisions}));
  for (const text of ['Reviewing packet v2', 'Approve', 'Revise', 'Reject', 'No application submitted']) assert.ok(html.includes(text));
  assert.ok(!html.includes('No queued job'));
});
test('recorded revision recovery errors and refresh action stay visible in its module', () => {
  const h = harness();
  const decisions = {state: {phase: 'RECORDED', target: {packetId: h.before.packet_id, action: 'revise'}, refreshed: false, error: 'Decision recorded. Packet history refresh is unavailable. Refresh before continuing.'}, controller: {}};
  const html = renderToStaticMarkup(presentation().RevisionSummary({packet: h.before, decisions, review: {state: {status: h.before.revision}, refresh() {}}, onChanges() {}, onSelect() {}}));
  assert.ok(html.includes('role="alert"')); assert.ok(html.includes(decisions.state.error)); assert.ok(html.includes('Refresh this packet'));
  assert.ok(!html.includes('Next queued job'));
});
test('next queue action is retained without empty-page filler in the revision module', () => {
  const h = harness();
  const decisions = {state: {phase: 'RECORDED', target: {packetId: h.before.packet_id, action: 'revise'}, refreshed: true, next: {packet_id: 'e'.repeat(32)}}};
  const props = {packet: h.before, decisions, review: {state: {status: h.before.revision}, refresh() {}}, onChanges() {}, onSelect() {}};
  assert.ok(renderToStaticMarkup(presentation().RevisionSummary(props)).includes('Next queued job'));
  decisions.state.next = null;
  const html = renderToStaticMarkup(presentation().RevisionSummary(props));
  assert.ok(!html.includes('Next queued job')); assert.ok(!html.includes('No queued job'));
});
test('comparison presentation retains document text, whitespace, markers and separated passages without transport metadata', () => {
  const {documentChangeLines} = presentation();
  const diff = '--- packet:before/version:1\n+++ packet:after/version:2\n@@ -1,3 +1,3 @@\n context\n-old  text\n+new  text\n \n@@ -8 +8 @@\n-@@ literal content @@\n++++ literal pluses\n\\ No newline at end of file\n';
  const lines = JSON.parse(JSON.stringify(documentChangeLines(diff)));
  assert.deepEqual(lines.map(({kind, text}) => ({kind, text})), [
    {kind: 'context', text: 'context'}, {kind: 'removed', text: 'old  text'}, {kind: 'added', text: 'new  text'},
    {kind: 'context', text: ''}, {kind: 'removed', text: '@@ literal content @@'}, {kind: 'added', text: '+++ literal pluses'},
    {kind: 'note', text: '\\ No newline at end of file'},
  ]);
  assert.equal(lines[0].passage, 1); assert.equal(lines[4].passage, 2);
});
test('header-like and path-like changed document content is never filtered as metadata', () => {
  const {documentChangeLines} = presentation();
  const diff = '--- packet:before/version:1\n+++ packet:after/version:2\n@@ -1,2 +1,2 @@\n---- retained minus text\n++++ retained plus text\n packet:literal/version:7\n @@ -9 +9 @@\n';
  assert.deepEqual(Array.from(documentChangeLines(diff), l => l.text), ['--- retained minus text', '+++ retained plus text', 'packet:literal/version:7', '@@ -9 +9 @@']);
});
test('changed comparison renders human version/authentication labels and accessible additions/removals', () => {
  const h = harness('succeeded');
  for (const kind of ['resume', 'cover']) Object.assign(h.comparison[kind], {changed: true, diff: '--- packet:before/version:1\n+++ packet:after/version:2\n@@ -1 +1 @@\n-Old text\n+New text\n'});
  const html = renderToStaticMarkup(presentation().RevisionChanges({review: {state: {comparison: h.comparison}, refresh() {}}}));
  for (const text of ['Before v1', 'After v2', 'Both documents authenticated', 'Added: ', 'Removed: ', 'Old text', 'New text']) assert.ok(html.includes(text), text);
  for (const text of ['packet:before', '@@ -1', h.before.packet_id, h.after.packet_id, h.before.expected_packet_fingerprint, h.after.expected_packet_fingerprint]) assert.ok(!html.includes(text), text);
});
test('unchanged and failed/unavailable/invalid comparison presentations remain distinct', () => {
  for (const [status, message] of [['available', 'No content changes'], ['unavailable', 'Comparison unavailable'], ['integrity_failed', 'Comparison integrity failed'], ['invalid_request', 'Invalid revision relationship']]) {
    const h = harness('succeeded'); h.comparison.status = status;
    if (status !== 'available') {h.comparison.resume = null; h.comparison.cover = null;}
    const html = renderToStaticMarkup(presentation().RevisionChanges({review: {state: {comparison: h.comparison}, refresh() {}}}));
    assert.ok(html.includes(message));
    if (status !== 'available') {assert.ok(!html.includes('No content changes')); assert.ok(!html.includes('Authenticated · Unchanged'));}
  }
});
function harness(state = 'queued') {
  const before = structuredClone(fixtures.packets[0]);
  before.version = 1; before.decision = 'revise';
  before.revision = {source_packet_id: before.packet_id, decision_id: 'd'.repeat(32), state, label: state, updated_at: null,
    successor_packet_id: state === 'succeeded' ? 'b'.repeat(32) : null, successor_version: state === 'succeeded' ? 2 : null, successor_status: state === 'succeeded' ? 'packet_ready' : null, failure_category: null};
  const after = {...structuredClone(before), packet_id: 'b'.repeat(32), version: 2, decision: null, expected_packet_fingerprint: 'c'.repeat(64), current_authorization: 'not_approved'};
  after.approval_preview = {...after.approval_preview, packet_id: after.packet_id, packet_version: after.version, expected_packet_fingerprint: after.expected_packet_fingerprint, expected_approval_view_fingerprint: 'f'.repeat(64)};
  after.history = [{packet_id: after.packet_id, version: 2, lineage_kind: 'revision', source_packet_id: before.packet_id, revision_decision_id: before.revision.decision_id}];
  after.revision = {...before.revision, source_packet_id: after.packet_id, decision_id: null, state: 'none', successor_packet_id: null};
  const identity = p => ({packet_id: p.packet_id, version: p.version, fingerprint: p.expected_packet_fingerprint});
  const component = {status: 'available', before_status: 'available', after_status: 'available', changed: false, diff: ''};
  const comparison = {status: 'available', before: identity(before), after: identity(after), revision_decision_id: before.revision.decision_id, revision_state: 'succeeded', resume: {...component}, cover: {...component}};
  const calls = [], timers = new Map(); let next = 0;
  const reader = {revision: async id => {calls.push(['revision', id]); return before.revision;}, packet: async id => {calls.push(['packet', id]); return id === before.packet_id ? before : after;}, comparison: async (b, a) => {calls.push(['comparison', b, a]); return comparison;}};
  const {RevisionController} = load('./revision-controller');
  const controller = new RevisionController(reader, {set: callback => {timers.set(++next, callback); return next;}, clear: id => timers.delete(id)});
  const tick = async () => { const tasks = [...timers.values()]; timers.clear(); for (const task of tasks) task(); await settle(); };
  return {before, after, comparison, reader, calls, timers, controller, tick};
}
test('protected read client supports only exact revision status and comparison GETs', async () => {
  const h = harness('succeeded'), calls = [];
  const {api} = load('./api', async (path, options) => {calls.push([path, options]); return {ok: true, headers: new Map([['content-type', 'application/json']]), json: async () => path.endsWith('revision-status') ? h.before.revision : h.comparison};});
  await api.revision(h.before.packet_id, new AbortController().signal);
  await api.comparison(h.before.packet_id, h.after.packet_id, new AbortController().signal);
  assert.deepEqual(calls.map(c => c[0]), [`/api/packets/${h.before.packet_id}/revision-status`, `/api/packets/${h.before.packet_id}/revision-comparison/${h.after.packet_id}`]);
  for (const [, o] of calls) {assert.equal(o.method, 'GET'); assert.equal(o.redirect, 'error'); assert.equal(o.cache, 'no-store');}
});
test('recorded intent polls within a bound, terminal success fetches actual successor and exact comparison', async () => {
  const h = harness(); h.controller.attach(h.before); await settle();
  assert.equal(h.controller.snapshot().successor, null); assert.equal(h.calls.length, 1); assert.equal(h.timers.size, 1);
  h.before.revision = {...h.before.revision, state: 'building'}; await h.tick();
  assert.equal(h.controller.snapshot().status.state, 'building');
  h.before.revision = {...h.before.revision, state: 'succeeded', successor_packet_id: h.after.packet_id, successor_version: 2}; await h.tick();
  assert.equal(h.controller.snapshot().successor.packet_id, h.after.packet_id);
  assert.deepEqual(h.calls.slice(-2), [['packet', h.after.packet_id], ['comparison', h.before.packet_id, h.after.packet_id]]);
  assert.equal(h.timers.size, 0);
});
for (const state of ['blocked', 'recovery_required', 'unknown']) test(`${state} is terminal or fails closed`, async () => {
  const h = harness(state); h.controller.attach(h.before); await settle(); assert.equal(h.timers.size, 0); assert.equal(h.controller.snapshot().successor, null);
  if (state === 'unknown') assert.ok(h.controller.snapshot().error);
});
test('polling is bounded and explicit refresh starts a new useful window', async () => {
  const h = harness(); h.controller.attach(h.before); await settle(); for (let i = 0; i < 25; i++) await h.tick();
  assert.equal(h.calls.length, 20); assert.equal(h.timers.size, 0); assert.equal(h.controller.snapshot().paused, true);
  h.controller.refresh(); await settle(); assert.equal(h.timers.size, 1);
});
for (const damage of ['wrong_id', 'wrong_lineage', 'integrity', 'not_ready', 'unreadable']) test(`success alone does not permit review: ${damage}`, async () => {
  const h = harness('succeeded');
  if (damage === 'wrong_id') h.after.packet_id = 'e'.repeat(32);
  if (damage === 'wrong_lineage') h.after.history[0].revision_decision_id = 'e'.repeat(32);
  if (damage === 'integrity') h.after.integrity = 'failed';
  if (damage === 'not_ready') h.after.status = 'building';
  if (damage === 'unreadable') h.reader.packet = async () => {throw new Error('PRIVATE');};
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().successor, null); assert.ok(h.controller.snapshot().successorError);
});
for (const damage of ['pair', 'decision', 'fingerprint', 'version', 'semantics']) test(`comparison identity/semantics fail closed: ${damage}`, async () => {
  const h = harness('succeeded');
  if (damage === 'pair') h.comparison.before.packet_id = h.after.packet_id;
  if (damage === 'decision') h.comparison.revision_decision_id = 'e'.repeat(32);
  if (damage === 'fingerprint') h.comparison.after.fingerprint = 'e'.repeat(64);
  if (damage === 'version') h.comparison.after.version = 8;
  if (damage === 'semantics') h.comparison.resume.changed = null;
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().comparison, null); assert.ok(h.controller.snapshot().comparisonError);
});
for (const status of ['unavailable', 'integrity_failed', 'invalid_request']) test(`explicit ${status} with null data is retained, never unchanged`, async () => {
  const h = harness('succeeded'); Object.assign(h.comparison, {status, resume: null, cover: null, revision_decision_id: null});
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().comparison.status, status);
});
test('late status, successor and comparison reads cannot survive selection, identity change or disposal', async () => {
  for (const seam of ['revision', 'packet', 'comparison']) {
    const h = harness('succeeded'), late = deferred(); let signal;
    h.reader[seam] = async (...args) => {signal = args.at(-1); return late.promise;};
    h.controller.attach(h.before); await settle(); h.controller.attach(null);
    assert.equal(signal.aborted, true);
    late.resolve(seam === 'revision' ? h.before.revision : seam === 'packet' ? h.after : h.comparison); await settle();
    assert.equal(h.controller.snapshot().packetId, null); assert.equal(h.controller.snapshot().comparison, null);
    h.controller.attach(h.before); await settle(); h.controller.dispose(); assert.equal(h.timers.size, 0);
  }
  const h = harness(), late = deferred(); h.reader.revision = async () => late.promise;
  h.controller.attach(h.before); h.controller.attach({...h.before, revision: {...h.before.revision, decision_id: 'e'.repeat(32)}});
  late.resolve(h.before.revision); await settle(); assert.ok(h.controller.snapshot().error); assert.equal(h.timers.size, 0);
});
test('successor selection uses authenticated directed lineage and independent current packet', async () => {
  const h = harness('succeeded'); h.controller.attach(h.after); await settle();
  assert.equal(h.controller.snapshot().comparison.after.packet_id, h.after.packet_id);
  assert.equal(h.controller.snapshot().successor, null); assert.equal(h.after.decision, null); assert.equal(h.after.current_authorization, 'not_approved');
});
test('failed status read stops polling without claiming success or exposing errors', async () => {
  const h = harness(); h.reader.revision = async () => {throw new Error('PRIVATE');};
  h.controller.attach(h.before); await settle(); assert.equal(h.timers.size, 0); assert.equal(h.controller.snapshot().status, null);
  assert.equal(h.controller.snapshot().successor, null); assert.ok(!h.controller.snapshot().error.includes('PRIVATE'));
});
test('wrong revision source/decision status never starts successor reads', async () => {
  for (const field of ['source_packet_id', 'decision_id']) {
    const h = harness('succeeded'); h.reader.revision = async () => ({...h.before.revision, [field]: 'e'.repeat(32)});
    h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().successor, null); assert.equal(h.calls.length, 0); assert.ok(h.controller.snapshot().error);
  }
});
test('comparison preserves mixed per-side evidence and rejects contradictory available/empty data', async () => {
  const h = harness('succeeded');
  h.comparison.status = 'integrity_failed'; h.comparison.resume = {status: 'integrity_failed', before_status: 'unavailable', after_status: 'integrity_failed', changed: null, diff: null};
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().comparison.resume.before_status, 'unavailable');
  const {contentValid} = load('./revision-controller');
  assert.equal(contentValid({status: 'available', before_status: 'available', after_status: 'available', changed: true, diff: ''}), false);
  assert.equal(contentValid({status: 'unavailable', before_status: 'unavailable', after_status: 'available', changed: false, diff: ''}), false);
});
test('current successor verification is withdrawn on refresh, changed evidence and failed relationship', async () => {
  const h = harness('succeeded'); h.controller.attach(h.after); await settle(); assert.equal(h.controller.snapshot().currentVerified, true);
  h.after.integrity = 'failed'; h.controller.refresh(); assert.equal(h.controller.snapshot().currentVerified, false); await settle();
  assert.equal(h.controller.snapshot().currentVerified, false);
  h.after.integrity = 'passed'; h.comparison.status = 'integrity_failed'; h.comparison.resume = null; h.comparison.cover = null;
  h.controller.refresh(); await settle(); assert.equal(h.controller.snapshot().currentVerified, false);
});

test('a newer successor approval preview cannot authorize the older confirmation view', async () => {
  const h = harness('succeeded');
  h.reader.packet = async id => id === h.before.packet_id ? h.before : {...h.after, approval_preview: {...h.after.approval_preview, expected_approval_view_fingerprint: 'e'.repeat(64)}};
  h.controller.attach(h.after); await settle(); assert.equal(h.controller.snapshot().currentVerified, false); assert.ok(h.controller.snapshot().successorError);
});
test('authenticated comparison cannot omit successor identity when current detail is unavailable', async () => {
  const h = harness('succeeded'); h.reader.packet = async () => {throw new Error('unavailable');};
  h.comparison.after.version = null; h.comparison.after.fingerprint = null;
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().comparison, null); assert.ok(h.controller.snapshot().comparisonError);
});
test('known successor-side comparison integrity failure withdraws the predecessor review handoff', async () => {
  const h = harness('succeeded'); h.comparison.status = 'integrity_failed';
  h.comparison.resume = {status: 'integrity_failed', before_status: 'available', after_status: 'integrity_failed', changed: null, diff: null};
  h.controller.attach(h.before); await settle(); assert.equal(h.controller.snapshot().successor, null); assert.ok(h.controller.snapshot().successorError);
});
test('historical predecessor content failure does not transfer failure to independently verified successor', async () => {
  const h = harness('succeeded'); h.comparison.status = 'integrity_failed';
  h.comparison.resume = {status: 'integrity_failed', before_status: 'integrity_failed', after_status: 'available', changed: null, diff: null};
  h.controller.attach(h.after); await settle(); assert.equal(h.controller.snapshot().currentVerified, true);
  assert.equal(h.controller.snapshot().comparison.resume.before_status, 'integrity_failed');
});
