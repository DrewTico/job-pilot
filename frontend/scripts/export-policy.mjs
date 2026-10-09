export const FONT_PATH = /^_next\/static\/media\/(?:bricolage-grotesque-latin-wght-normal|geist-latin-wght-normal|geist-mono-latin-400-normal|newsreader-latin-400-normal)\.[0-9a-f]{8}\.woff2$/;
export const MAX_FONT_BYTES = 100_000;
export const MAX_FONT_TOTAL_BYTES = 250_000;

export function removeSelfFontHint(html) {
  // Next adds this redundant hint for CSS-imported fonts without font preloads.
  // Omit exactly its same-origin tag; all other links retain the strict policy.
  return html.replaceAll('<link data-next-font="" rel="preconnect" href="/" crossorigin="anonymous"/>', '');
}

export function approvedAsset(name) {
  return !name.includes('..') && (FONT_PATH.test(name) || /^_next\/static\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.(js|css)$/.test(name));
}

export function fontReferences(css) {
  if (/@import\b/i.test(css)) throw new Error('Unapproved runtime CSS import');
  return [...css.matchAll(/url\(\s*["']?([^\s"')]+)["']?\s*\)/g)].map(match => {
    const url = match[1];
    if (!url.startsWith('/ui/') || !FONT_PATH.test(url.slice(4))) throw new Error('Unapproved CSS asset');
    return url.slice(4);
  });
}

export function validateFont(name, bytes) {
  if (!FONT_PATH.test(name) || bytes.length < 48 || bytes.length > MAX_FONT_BYTES ||
      bytes.toString('ascii', 0, 4) !== 'wOF2' || bytes.readUInt32BE(8) !== bytes.length) throw new Error('Unapproved font bytes');
}

export function validateHtml(html, assets) {
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (/\btype="application\/json"/.test(match[1])) {
      if (/\bsrc=/.test(match[1])) throw new Error('External data script');
      continue;
    }
    const source = match[1].match(/\bsrc="\/ui\/(_next\/static\/[^" ]+\.js)"/);
    if (!source || match[2].trim() || !assets.includes(source[1])) throw new Error('Executable inline or unapproved script');
  }
  for (const link of html.matchAll(/<link\b[^>]*href="([^" ]+)"/g)) {
    if (!link[1].startsWith('/ui/') || !assets.includes(link[1].slice(4)) || !link[1].endsWith('.css')) throw new Error('Unapproved runtime stylesheet');
  }
  if (/<style\b|\sstyle=|\son\w+=|<img\b|<iframe\b|<object\b|<embed\b/.test(html)) throw new Error('CSP-incompatible HTML');
}
