import { readFile, mkdir, writeFile, rename, mkdtemp, rm, lstat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateHtml, removeSelfFontHint, approvedAsset, fontReferences, validateFont, FONT_PATH, MAX_FONT_TOTAL_BYTES } from './export-policy.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.resolve(root, '../src/job_agent/dashboard/ui_build');
// No directory is mounted. Only this manifest's exact paths can be delivered.
const build = JSON.parse(await readFile(path.join(root, '.next/build-manifest.json'), 'utf8'));
const files = [...new Set(['index.html', ...[
  ...build.polyfillFiles, ...build.lowPriorityFiles,
  ...build.pages['/'], ...build.pages['/_app'], ...build.pages['/_error'],
].map(name => `_next/${name}`)])];
// Demo HTML and its unique fixture chunk are intentionally absent.
// Follow only approved packaged CSS references, never scan/mount arbitrary media.
for (const name of [...files].filter(name => name.endsWith('.css'))) {
  for (const font of fontReferences(await readFile(path.join(root, 'out', name), 'utf8'))) {
    if (!files.includes(font)) files.push(font);
  }
}
for (const name of files) {
  if (name !== 'index.html' && !approvedAsset(name)) {
    throw new Error('Unapproved export asset');
  }
}
const assets = {};
const contents = new Map();
let fontTotal = 0;
for (const name of files.sort()) {
  const candidate = path.join(root, 'out', name);
  for (let part = candidate; part !== path.dirname(part); part = path.dirname(part)) {
    if ((await lstat(part)).isSymbolicLink()) throw new Error('Symlink export asset');
  }
  let bytes = await readFile(candidate);
  if (FONT_PATH.test(name)) {
    validateFont(name, bytes);
    fontTotal += bytes.length;
    if (fontTotal > MAX_FONT_TOTAL_BYTES) throw new Error('Font payload exceeds bound');
  }
  if (name.endsWith('.html')) {
    bytes = Buffer.from(removeSelfFontHint(bytes.toString()));
    validateHtml(bytes.toString(), files);
  }
  contents.set(name, bytes);
  assets[name] = { sha256: createHash('sha256').update(bytes).digest('hex'), size: bytes.length,
    type: name.endsWith('.html') ? 'text/html' : FONT_PATH.test(name) ? 'font/woff2' : name.endsWith('.css') ? 'text/css' : 'text/javascript' };
}
// Replace only this script's generated package. No stale/unlisted bytes remain.
// A running Python process keeps its verified in-memory snapshot throughout.
const staging = await mkdtemp(`${output}.staging-`);
const previous = `${output}.previous-${process.pid}`;
let movedPrevious = false;
try {
  for (const [name, bytes] of contents) {
    await mkdir(path.dirname(path.join(staging, name)), { recursive: true });
    await writeFile(path.join(staging, name), bytes);
  }
  await writeFile(path.join(staging, 'manifest.json'), JSON.stringify({ version: 1, assets }, null, 2) + '\n');
  try { await rename(output, previous); movedPrevious = true; }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  try { await rename(staging, output); }
  catch (error) { if (movedPrevious) await rename(previous, output); throw error; }
  if (movedPrevious) await rm(previous, { recursive: true, force: true });
} finally {
  await rm(staging, { recursive: true, force: true });
}
console.log(`Packaged ${files.length} approved assets; no source maps, error pages or generic mount.`);
