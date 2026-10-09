// Job Pilot themes are deterministic decoration, never official company branding.
export const companyThemes = ['teal', 'indigo', 'purple', 'copper', 'navy'] as const;
function companyHash(company: string) {
  let hash = 0;
  for (const character of company.trim().toLowerCase()) hash = (hash * 31 + character.codePointAt(0)!) >>> 0;
  return hash;
}
export function companyTheme(company: string) {
  return companyThemes[companyHash(company) % companyThemes.length];
}
// Reserved source-owned demo IDs AND name fingerprints, not a prefix rule.
// Keep fixture payloads out of the production export. Unknown names stay exact.
const demoIdentities: Record<string, number> = {
  '1': 1438442783, '2': 910160099, '3': 54934180, '4': 3615407179,
  '5': 3879258745, '6': 185831095, '7': 4035909851, '8': 1004843737,
  '9': 2213461082, '5a': 1438442783,
};
export function companyPresentation(company: string, packetId: string) {
  const identity = /^0{30}[0-9a-f]{2}$/.test(packetId) ? packetId.slice(-2).replace(/^0/, '') : '';
  const demo = company.startsWith('Synthetic · ') && demoIdentities[identity] === companyHash(company);
  const name = demo ? company.slice('Synthetic · '.length) : company;
  const theme = demo && (identity === '1' || identity === '5a') ? 'teal'
    : demo && identity === '2' ? 'purple'
    : demo && identity === '4' ? 'copper' : companyTheme(name);
  return {name, demo, theme};
}
export function companyInitials(company: string) {
  return company.trim().split(/\s+/u).filter(word => /[\p{L}\p{N}]/u.test(word)).slice(0, 2).map(word => Array.from(word)[0]).join('').toUpperCase() || '?';
}
export function fitLabel(score: number) {
  return score >= 90 ? 'Great fit' : score >= 80 ? 'Strong fit' : score >= 65 ? 'Potential fit' : 'Lower fit';
}
export function wordCount(text: string) { return text.trim() ? text.trim().split(/\s+/u).length : 0; }
