import type { Authorization, Decision, Status } from './types';
export const sections = { 'needs-review': 'Needs review', processing: 'Processing', 'needs-attention': 'Needs attention', history: 'History' } as const;
export const statusLabel: Record<Status, string> = {packet_ready: 'Packet ready', building: 'Building', generation_failed: 'Generation failed', research_incomplete: 'Research incomplete', recovery_required: 'Recovery required'};
export const authorizationLabel: Record<Authorization, string> = {not_approved: 'Not authorized', currently_valid: 'Current authorization valid', evidence_changed: 'Evidence changed: authorization stale', integrity_failed: 'Integrity failed: not authorized', not_checked: 'Current authorization not checked'};
export function decisionLabel(value: Decision) { return value === 'approve' ? 'Historical approval' : value === 'reject' ? 'Historical rejection' : value === 'revise' ? 'Revision requested' : 'No decision'; }
export function date(value: string | null) {
  if (!value) return 'Unavailable';
  const time = new Date(value);
  return Number.isNaN(time.valueOf()) ? 'Unavailable' : new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(time) + ' UTC';
}
export function safeUrl(value: string | null) {
  if (!value || /[\u0000-\u0020\u007f]/.test(value)) return null;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function errorMessage(error: unknown) {
  const code = error instanceof Error ? error.message : '';
  if (code === 'authentication_required' || code === 'unauthorized_identity') return 'Access unavailable. Reopen Job Pilot through your authorized connection.';
  if (['stale_packet', 'stale_approval_view', 'approval_not_current'].includes(code)) return 'Evidence changed during this read. Reload to review the current packet.';
  if (code === 'packet_integrity_failed') return 'Packet integrity could not be verified. Review it in the trusted decision UI.';
  return 'Review unavailable. Retry, or open the trusted decision UI.';
}
