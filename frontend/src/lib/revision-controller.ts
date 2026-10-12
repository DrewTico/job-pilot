import { packetId } from './api';
import type { Packet, Reader, RevisionComparison, RevisionContentDiff, RevisionStatus } from './types';

const nonterminal = new Set(['queued', 'pending', 'style_prepared', 'style_persisted', 'building']);
const known = new Set([...nonterminal, 'none', 'succeeded', 'blocked', 'recovery_required']);
export interface RevisionState {
  currentVerified: boolean; packetId: string | null; binding: string; status: RevisionStatus | null; loading: boolean; paused: boolean; error: string;
  successor: Packet | null; successorError: string; comparison: RevisionComparison | null; comparisonError: string;
}
const empty = (): RevisionState => ({currentVerified: false, packetId: null, binding: '', status: null, loading: false, paused: false, error: '', successor: null, successorError: '', comparison: null, comparisonError: ''});
type Timer = {set: (callback: () => void) => ReturnType<typeof setTimeout>; clear: (id: ReturnType<typeof setTimeout>) => void};
export function revisionBinding(packet: Packet | null) {
  const row = packet?.history.find(item => item.packet_id === packet.packet_id);
  return packet ? JSON.stringify([packet.packet_id, packet.expected_packet_fingerprint, packet.decision, packet.integrity, packet.status, packet.approval_preview, packet.revision, row]) : '';
}
export function contentValid(c: RevisionContentDiff | null) {
  if (!c) return false;
  if (c.status === 'available') return c.before_status === 'available' && c.after_status === 'available' &&
    typeof c.changed === 'boolean' && typeof c.diff === 'string' && (c.changed ? c.diff.length > 0 : c.diff === '');
  return c.changed === null && c.diff === null && (c.status === 'integrity_failed' ?
    [c.before_status, c.after_status].includes('integrity_failed') :
    [c.before_status, c.after_status].includes('unavailable') && ![c.before_status, c.after_status].includes('integrity_failed'));
}
export function comparisonValid(c: RevisionComparison, before: Packet, afterId: string, after: Packet | null, decisionId: string) {
  if (c.before.packet_id !== before.packet_id || c.after.packet_id !== afterId) return false;
  if (c.before.version !== null && c.before.version !== before.version || c.before.fingerprint !== null && c.before.fingerprint !== before.expected_packet_fingerprint) return false;
  if (after && (c.after.version !== null && c.after.version !== after.version || c.after.fingerprint !== null && c.after.fingerprint !== after.expected_packet_fingerprint)) return false;
  if (c.revision_decision_id !== null && c.revision_decision_id !== decisionId) return false;
  if (c.status === 'invalid_request') return c.resume === null && c.cover === null;
  if (!c.resume && !c.cover) return c.status !== 'available';
  if (!contentValid(c.resume) || !contentValid(c.cover) || c.revision_decision_id !== decisionId ||
      c.before.version !== before.version || c.before.fingerprint !== before.expected_packet_fingerprint ||
      c.after.version === null || c.after.version <= before.version || !c.after.fingerprint || !/^[0-9a-f]{64}$/.test(c.after.fingerprint) ||
      after && (c.after.version !== after.version || c.after.fingerprint !== after.expected_packet_fingerprint)) return false;
  const statuses = [c.resume!.status, c.cover!.status];
  return c.status === (statuses.includes('integrity_failed') ? 'integrity_failed' : statuses.includes('unavailable') ? 'unavailable' : 'available');
}
function linked(after: Packet, before: Packet, id: string) {
  const row = after.history.find(item => item.packet_id === after.packet_id);
  return after.packet_id !== before.packet_id && after.version > before.version && row?.version === after.version &&
    row.lineage_kind === 'revision' && row.source_packet_id === before.packet_id && row.revision_decision_id === id;
}
// Shared read integration for both existing presentations. No worker or mutation.
export class RevisionController {
  private state = empty();
  private listeners = new Set<() => void>();
  private request: AbortController | null = null;
  private timeout: ReturnType<typeof setTimeout> | null = null;
  private packet: Packet | null = null;
  private key = '';
  constructor(private reader: Reader, private timer: Timer = {set: callback => setTimeout(callback, 3000), clear: id => clearTimeout(id)}) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private publish(change: Partial<RevisionState>) {this.state = {...this.state, ...change}; this.listeners.forEach(listener => listener());}
  private stop() {this.request?.abort(); if (this.timeout !== null) this.timer.clear(this.timeout); this.timeout = null;}
  attach(packet: Packet | null) {
    const row = packet?.history.find(item => item.packet_id === packet.packet_id);
    const key = revisionBinding(packet);
    if (key === this.key) return;
    this.stop(); this.key = key; this.packet = packet; this.state = empty();
    this.publish({packetId: packet?.packet_id ?? null, binding: key});
    if (packet && (packet.decision === 'revise' || row?.lineage_kind === 'revision')) this.refresh();
  }
  dispose() {this.stop(); this.key = ''; this.packet = null; this.publish(empty());}
  refresh = () => {
    this.stop(); if (!this.packet) return;
    const request = new AbortController(); this.request = request;
    this.publish({currentVerified: false, loading: true, paused: false, error: '', successor: null, successorError: '', comparison: null, comparisonError: ''});
    void this.load(this.packet, request, 0);
  };
  private async load(packet: Packet, request: AbortController, attempt: number) {
    const signal = request.signal;
    try {
      const own = packet.history.find(item => item.packet_id === packet.packet_id);
      // A successor can have its own Revise request. Show that request first;
      // the previous comparison remains accessible through version history.
      const predecessor = packet.decision === 'revise' ? packet : own?.source_packet_id ? await this.reader.packet(own.source_packet_id, signal) : null;
      if (signal.aborted) return;
      if (!predecessor || predecessor.packet_id !== (packet.decision === 'revise' ? packet.packet_id : own?.source_packet_id) || predecessor.decision !== 'revise') throw new Error('unavailable');
      const decisionId = packet.decision === 'revise' ? packet.revision.decision_id : own?.revision_decision_id;
      if (!decisionId) throw new Error('unavailable');
      const status = await this.reader.revision(predecessor.packet_id, signal);
      if (signal.aborted) return;
      if (status.source_packet_id !== predecessor.packet_id || status.decision_id !== decisionId || !known.has(status.state)) throw new Error('unavailable');
      this.publish({status, loading: false});
      if (nonterminal.has(status.state)) {
        if (attempt + 1 < 20) this.timeout = this.timer.set(() => {this.timeout = null; void this.load(packet, request, attempt + 1);});
        else this.publish({paused: true});
        return;
      }
      if (status.state !== 'succeeded') return;
      if (!status.successor_packet_id) {this.publish({successorError: 'Revision work completed. Successor detail is currently unavailable.'}); return;}
      const afterId = packetId(status.successor_packet_id);
      let after: Packet | null = null;
      try {
        const detail = await this.reader.packet(afterId, signal);
        if (signal.aborted) return;
        if (detail.packet_id !== afterId || detail.version !== status.successor_version || !linked(detail, predecessor, decisionId) ||
            packet.decision !== 'revise' && (afterId !== packet.packet_id || detail.expected_packet_fingerprint !== packet.expected_packet_fingerprint)) throw new Error('unavailable');
        after = detail;
        if (detail.status !== 'packet_ready' || detail.integrity !== 'passed') this.publish({successorError: 'Successor is not currently verified and ready. Refresh its evidence before deciding.'});
        else if (packet.packet_id !== afterId) this.publish({successor: detail});
        else if (detail.approval_preview?.expected_approval_view_fingerprint !== packet.approval_preview?.expected_approval_view_fingerprint) this.publish({successorError: 'Successor approval evidence changed. Reload this packet before deciding.'});
        else this.publish({currentVerified: true});
      } catch {if (!signal.aborted) this.publish({successorError: 'Successor detail unavailable or its revision identity could not be verified. Retry the read.'});}
      if (signal.aborted) return;
      try {
        const comparison = await this.reader.comparison(predecessor.packet_id, afterId, signal);
        if (signal.aborted) return;
        if (comparison.after.version !== null && comparison.after.version !== status.successor_version || !comparisonValid(comparison, predecessor, afterId, after, decisionId)) throw new Error('unavailable');
        this.publish({comparison});
        const successorIntegrityFailed = [comparison.resume?.after_status, comparison.cover?.after_status].includes('integrity_failed');
        if (successorIntegrityFailed) this.publish({currentVerified: false, successor: null, successorError: 'Successor content integrity failed. Review unavailable. Check its current evidence.'});
        // A failed relationship cannot offer a review handoff even if a
        // separately obtained detail snapshot looked ready.
        if (comparison.status === 'invalid_request' || comparison.status === 'integrity_failed' && !comparison.resume && !comparison.cover) this.publish({currentVerified: false, successor: null, successorError: 'Revision relationship could not be authenticated. Successor review unavailable.'});
      } catch {if (!signal.aborted) this.publish({currentVerified: false, comparisonError: 'Comparison unavailable or returned a different revision. Retry the read.', successor: null});}
    } catch {if (!signal.aborted) this.publish({loading: false, status: null, error: 'Revision status unavailable or its identity changed. Refresh to check again.', successor: null, comparison: null});}
  }
}
