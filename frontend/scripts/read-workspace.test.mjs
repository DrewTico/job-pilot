import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const contracts = JSON.parse(readFileSync(new URL('../src/lib/contracts.json', import.meta.url)));
function load(name, fetch) {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const result = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true}});
  const module = {exports: {}};
  vm.runInNewContext(result.outputText, {exports: module.exports, module, require: () => contracts, fetch, URL, AbortController, Intl, Date});
  return module.exports;
}
test('read client restricts requests to same-origin GET with no redirects or storage', async () => {
  const calls = [];
  const {api} = load('api', async (path, options) => {
    calls.push([path, options]);
    return {ok: true, headers: new Map([['content-type', 'application/json']]), json: async () => ({section: 'history', offset: 25, limit: 25, items: []})};
  });
  await api.queue('history', 25, new AbortController().signal);
  assert.equal(calls[0][0], '/api/queue?section=history&limit=25&offset=25');
  assert.equal(calls[0][1].method, 'GET');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(calls[0][1].cache, 'no-store');
  assert.equal(calls[0][1].redirect, 'error');
  for (const id of ['../approve', 'https://evil.invalid', '0'.repeat(31), 'A'.repeat(32)]) {
    await assert.rejects(async () => api.packet(id, new AbortController().signal), /invalid_request/);
  }
  await assert.rejects(() => api.queue('history&action=approve', 0, new AbortController().signal), /invalid_request/);
  assert.equal(calls.length, 1);
});
test('unknown enum, missing evidence and malformed responses fail closed', async () => {
  const {valid} = load('api');
  const fixtures = JSON.parse(readFileSync(new URL('../src/fixtures/review.json', import.meta.url)));
  for (const packet of fixtures.packets) assert.equal(valid(packet, contracts.PacketDetail), true);
  const packet = fixtures.packets[0];
  assert.equal(valid({...packet, current_authorization: 'looks_good'}, contracts.PacketDetail), false);
  assert.equal(valid({...packet, integrity: null}, contracts.PacketDetail), false);
  assert.equal(valid({...packet, constructor: 'unexpected'}, contracts.PacketDetail), false);
  assert.equal(valid({...packet, cover_text: null}, contracts.PacketDetail), true);
  const {api} = load('api', async () => ({ok: true, headers: new Map([['content-type', 'application/json']]), json: async () => ({items: []})}));
  await assert.rejects(() => api.queue('needs-review', 0, new AbortController().signal), /unavailable/);
});
test('unsafe URLs and private error messages remain inert or sanitized', () => {
  const {safeUrl, errorMessage, decisionLabel, authorizationLabel} = load('display');
  for (const url of ['javascript:alert(1)', 'data:text/html,test', '//evil.invalid', 'https://user:secret@evil.invalid', 'https://evil.invalid/\n']) assert.equal(safeUrl(url), null);
  assert.equal(safeUrl('https://source.invalid/fact'), 'https://source.invalid/fact');
  assert.equal(decisionLabel('approve'), 'Historical approval');
  assert.match(authorizationLabel.evidence_changed, /stale/);
  assert.equal(errorMessage('PRIVATE_TOKEN'), 'Review unavailable. Retry, or open the trusted decision UI.');
});

test('presentation derives only deterministic decoration, fit labels and exact word counts', () => {
  const {companyTheme, companyThemes, companyInitials, fitLabel, wordCount} = load('review-presentation');
  for (const company of ['Northstar', 'Atlas', 'Meridian', 'Harbor', '<script>bad</script>', '']) {
    assert.ok(companyThemes.includes(companyTheme(company)));
    assert.equal(companyTheme(company), companyTheme(company));
  }
  assert.equal(companyInitials('Northstar Instruments'), 'NI');
  assert.equal(fitLabel(94), 'Great fit');
  assert.equal(fitLabel(78), 'Potential fit');
  assert.equal(wordCount('  Exact text\n\nwith spaces.  '), 4);
  assert.equal(wordCount(''), 0);
});

test('only known synthetic packet identities get demo display names and curated palettes', () => {
  const {companyPresentation, companyTheme} = load('review-presentation');
  const fixtures = JSON.parse(readFileSync(new URL('../src/fixtures/review.json', import.meta.url)));
  for (const packet of fixtures.packets) {
    const display = companyPresentation(packet.company, packet.packet_id);
    assert.equal(display.demo, true);
    assert.equal(display.name, packet.company.slice('Synthetic · '.length));
    assert.equal(packet.company.startsWith('Synthetic · '), true);
  }
  assert.equal(companyPresentation(fixtures.packets[0].company, fixtures.packets[0].packet_id).theme, 'teal');
  for (const [company, id] of [
    ['Synthetic · Arbitrary Production Name', '0'.repeat(31) + '1'],
    ['Synthetic · Northstar Instruments', 'a'.repeat(32)],
    ['Northstar Instruments', '0'.repeat(31) + '1'],
    ['Synthetic · Northstar Instruments extra', '0'.repeat(31) + '1'],
    ['Synthetic · Northstar Instruments', '../1'],
  ]) {
    const display = companyPresentation(company, id);
    assert.equal(display.name, company);
    assert.equal(display.demo, false);
    assert.equal(display.theme, companyTheme(company));
  }
});
