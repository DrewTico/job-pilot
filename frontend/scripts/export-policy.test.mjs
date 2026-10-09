import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateHtml, removeSelfFontHint, approvedAsset, fontReferences, validateFont, MAX_FONT_BYTES } from './export-policy.mjs';
const files = ['index.html', '_next/static/chunks/main.js', '_next/static/css/main.css'];
test('allows self assets and inert Next data under the original CSP', () => {
  assert.doesNotThrow(() => validateHtml('<link rel="stylesheet" href="/ui/_next/static/css/main.css"><script src="/ui/_next/static/chunks/main.js" defer></script><script type="application/json">{"props":{}}</script>', files));
});
test('fails closed on inline execution, styles, external and unlisted assets', () => {
  for (const html of ['<script>run()</script>', '<style>body{}</style>', '<main style="color:red">', '<button onclick="run()">', '<img src="/image.png">', '<iframe src="/">', '<script src="https://cdn.invalid/main.js"></script>', '<script src="/ui/_next/static/chunks/unknown.js"></script>', '<link href="https://fonts.invalid/style.css">']) {
    assert.throws(() => validateHtml(html, files));
  }
});

const font = '_next/static/media/geist-latin-wght-normal.01234567.woff2';
test('removes only the redundant exact Next same-origin font hint', () => {
  const hint = '<link data-next-font="" rel="preconnect" href="/" crossorigin="anonymous"/>';
  assert.equal(removeSelfFontHint(hint + '<main>Review</main>'), '<main>Review</main>');
  assert.doesNotThrow(() => validateHtml(removeSelfFontHint(hint), files));
  const external = hint.replace('href="/"', 'href="https://fonts.gstatic.com"');
  assert.equal(removeSelfFontHint(external), external);
  assert.throws(() => validateHtml(removeSelfFontHint(external), files));
});
test('permits only approved hashed Latin WOFF2 references in static CSS', () => {
  assert.equal(approvedAsset(font), true);
  assert.deepEqual(fontReferences(`@font-face{src:url("/ui/${font}") format("woff2");font-display:swap}`), [font]);
  for (const path of [font.replace('.woff2', '.woff'), font.replace('.woff2', '.ttf'), font.replace('.woff2', '.otf'),
    font.replace('geist-latin-wght-normal', 'unapproved'), font.replace('media/', 'media/nested/'),
    font.replace('01234567', 'not-a-hash'), font.replace('media/', '../media/'), `${font}?query=1`]) {
    assert.equal(approvedAsset(path), false);
    assert.throws(() => fontReferences(`@font-face{src:url('/ui/${path}')}`));
  }
});
test('rejects remote, inline, undeclared shapes and CSS imports without relaxing HTML', () => {
  for (const url of ['https://fonts.gstatic.com/a.woff2', 'https://cdn.jsdelivr.net/a.woff2',
    'https://unpkg.com/a.woff2', 'data:font/woff2;base64,AAAA', 'blob:font', '//fonts.invalid/a.woff2', '../media/a.woff2']) {
    assert.throws(() => fontReferences(`@font-face{src:url(${url})}`));
  }
  assert.throws(() => fontReferences('@import "https://fonts.googleapis.com/font.css"'));
  assert.throws(() => validateHtml(`<link rel="preload" as="font" href="/ui/${font}">`, [...files, font]));
});
test('font bytes have bounded WOFF2 signature and length', () => {
  const bytes = Buffer.alloc(48); bytes.write('wOF2'); bytes.writeUInt32BE(bytes.length, 8);
  assert.doesNotThrow(() => validateFont(font, bytes));
  for (const value of [Buffer.alloc(48), bytes.subarray(0, 47), Buffer.alloc(MAX_FONT_BYTES + 1)]) {
    assert.throws(() => validateFont(font, value));
  }
  const corrupt = Buffer.from(bytes); corrupt.writeUInt32BE(100, 8);
  assert.throws(() => validateFont(font, corrupt));
});
