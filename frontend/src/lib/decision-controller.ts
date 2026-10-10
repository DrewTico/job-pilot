import { packetId } from './api';
import { DecisionFailure, type DecisionTransport } from './decision-client';
import type { Authorization, DecisionDetail, DecisionResult, Packet, Queue, Reader } from './types';

export const rejectReasons = {not_interested: 'Not interested', bad_fit: 'Poor fit', company: 'Company concern', location: 'Location', pay: 'Compensation', other: 'Other'};
export type Action = 'approve' | 'reject' | 'revise';
export type Phase = 'BOOTSTRAP_UNAVAILABLE' | 'READY' | 'CONFIRMING' | 'PENDING' | 'RECORDED' | 'AMBIGUOUS' | 'FAILED';
export interface Target {
  readonly packetId: string; readonly version: number; readonly fingerprint: string; readonly approvalFingerprint: string | null;
  readonly company: string; readonly title: string; readonly action: Action; readonly reason: string; readonly text: string;
}
export interface DecisionState {
  phase: Phase; ready: boolean; busy: boolean; uncertain: boolean; target: Target | null; error: string;
  authorization: Authorization; decisionId: string | null; next: Queue['items'][number] | null; refreshed: boolean;
}
const initial = (): DecisionState => ({phase: 'BOOTSTRAP_UNAVAILABLE', ready: false, busy: false, uncertain: false, target: null, error: '', authorization: 'not_checked', decisionId: null, next: null, refreshed: false});
const fingerprint = (value: string | null | undefined) => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export function canDecide(packet: Packet, action: Action) {
  try { packetId(packet.packet_id); } catch { return false; }
  if (packet.decision || !fingerprint(packet.expected_packet_fingerprint)) return false;
  if (action !== 'approve') return true;
  const preview = packet.approval_preview;
  return packet.integrity === 'passed' && Boolean(preview && preview.packet_id === packet.packet_id && preview.packet_version === packet.version &&
    preview.expected_packet_fingerprint === packet.expected_packet_fingerprint && fingerprint(preview.expected_approval_view_fingerprint));
}
export function validation(target: Target) {
  if (target.action === 'reject' && !Object.hasOwn(rejectReasons, target.reason)) return 'Choose a reason.';
  // Python str.strip whitespace, including NEL/control separators, excluding
  // BOM. Validate emptiness without changing accepted text.
  if (target.action === 'revise' && /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/.test(target.text)) return 'Enter revision feedback.';
  if (Array.from(target.text).length > 4000) return 'Use 4,000 characters or fewer.';
  return '';
}
export function decisionBody(target: Target): Record<string, string> {
  const base = {expected_packet_fingerprint: target.fingerprint};
  if (target.action === 'approve') return {...base, expected_approval_view_fingerprint: target.approvalFingerprint!};
  if (target.action === 'reject') return {...base, reason_code: target.reason, detail: target.text};
  return {...base, feedback: target.text};
}
export function decisionError(code: string) {
  const copy: Record<string, string> = {
    csrf_failed: 'Session changed. Enable decisions again before confirming a new decision.',
    invalid_host: 'Private access unavailable. Check the address and retry.', authentication_required: 'Private access required. Reconnect and retry.',
    local_only: 'Private access unavailable. Reconnect and retry.', authorization_failed: 'Private access denied. Reconnect and retry.', unauthorized_identity: 'Private access denied. Reconnect and retry.',
    not_found: 'This packet is unavailable. Refresh the queue.',
    stale_packet: 'Packet changed. Refresh and review it before deciding.', stale_approval_view: 'Approval evidence changed. Refresh and review it before approving.',
    decision_conflict: 'An existing decision prevents this action. Refresh this packet to review its history.',
    packet_integrity_failed: 'Approval blocked by packet integrity. Refresh the evidence. Reject or Revise may still be available.',
    approval_not_current: 'Approval evidence is no longer current. Refresh the evidence before approving.',
    invalid_request: 'Decision could not be recorded. Review the fields and refresh this packet.',
    packet_busy: 'Packet is busy. Refresh this packet before deciding again.', storage_unavailable: 'Storage unavailable. Refresh this packet to confirm its decision status.',
  };
  return copy[code] ?? 'Decision unavailable. Refresh this packet before deciding again.';
}

// One source-owned controller above both presentations. Tokens and private form
// text live only in this instance, never in persistent storage or URL state.
export class DecisionController {
  private token: string | null = null;
  private bootstrapRequest: AbortController | null = null;
  private bootstrapError = '';
  private lifecycle = 0;
  private selection: string | null = null;
  private operation = false;
  private records = new Map<string, DecisionState>();
  private interrupted = new Map<string, Target>();
  private listeners = new Set<() => void>();
  private state = initial();
  constructor(private reader: Reader, private transport: DecisionTransport,
    private refreshed: (packet: Packet, queue: Queue | null) => void) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(state: DecisionState) { this.state = {...state, ready: Boolean(this.token), busy: this.operation,
    uncertain: this.interrupted.size > 0 || Array.from(this.records.values()).some(record => ['PENDING', 'AMBIGUOUS'].includes(record.phase))}; this.listeners.forEach(listener => listener()); }
  private save(id: string, state: DecisionState) { this.records.set(id, state); if (this.selection === id) this.publish(state); }
  select(id: string | null) {
    if (id === this.selection) return;
    this.selection = id;
    // Confirmation drafts cannot survive a selection switch.
    for (const [key, value] of this.records) if (value.phase === 'CONFIRMING') this.records.delete(key);
    this.publish(id && this.records.get(id) || {...initial(), phase: this.token ? 'READY' : 'BOOTSTRAP_UNAVAILABLE', error: this.token ? '' : this.bootstrapError});
  }
  async bootstrap() {
    this.bootstrapRequest?.abort(); this.token = null; this.bootstrapError = '';
    const request = new AbortController(); this.bootstrapRequest = request;
    this.publish({...this.state, error: this.state.target ? this.state.error : ''});
    try {
      const token = await this.transport.bootstrap(request.signal);
      if (request.signal.aborted) return;
      this.token = token;
      this.publish({...this.state, phase: this.state.phase === 'BOOTSTRAP_UNAVAILABLE' ? 'READY' : this.state.phase});
    } catch {
      if (!request.signal.aborted) {
        this.bootstrapError = 'Decisions unavailable. Retry private access to enable decisions.';
        this.publish({...this.state, error: this.bootstrapError});
      }
    }
  }
  clear() {
    this.lifecycle++; this.token = null; this.bootstrapError = ''; this.bootstrapRequest?.abort();
    // A transmitted mutation is not canceled by pagehide. Keep only a minimal
    // recovery marker, discard feedback and confirmation snapshots.
    for (const [id, record] of this.records) if (record.target && ['PENDING', 'AMBIGUOUS'].includes(record.phase)) {
      this.interrupted.set(id, Object.freeze({...record.target, company: '', title: '', reason: '', text: ''}));
    }
    this.records.clear();
    this.publish(initial());
  }
  observe(packet: Packet | null) {
    if (this.state.phase === 'CONFIRMING' && (!packet || packet.packet_id !== this.state.target?.packetId ||
        packet.expected_packet_fingerprint !== this.state.target.fingerprint || packet.decision ||
        this.state.target.action === 'approve' && packet.approval_preview?.expected_approval_view_fingerprint !== this.state.target.approvalFingerprint)) this.cancel();
    if (packet && packet.packet_id === this.selection && this.interrupted.has(packet.packet_id) && this.state.phase !== 'AMBIGUOUS') {
      const target = Object.freeze({...this.interrupted.get(packet.packet_id)!, company: packet.company, title: packet.title});
      this.save(packet.packet_id, {...initial(), phase: 'AMBIGUOUS', target, error: 'A decision was interrupted. Refresh this packet to confirm its status before deciding again.'});
    }
  }
  begin(packet: Packet, action: Action) {
    if (!this.token || this.operation || this.selection !== packet.packet_id || !canDecide(packet, action) ||
        ['PENDING', 'AMBIGUOUS', 'FAILED', 'RECORDED'].includes(this.state.phase)) return;
    const target = Object.freeze({packetId: packet.packet_id, version: packet.version, fingerprint: packet.expected_packet_fingerprint,
      approvalFingerprint: action === 'approve' ? packet.approval_preview!.expected_approval_view_fingerprint : null,
      company: packet.company, title: packet.title, action, reason: '', text: ''});
    this.save(packet.packet_id, {...initial(), phase: 'CONFIRMING', target});
  }
  edit(reason: string, text: string) {
    if (this.state.phase !== 'CONFIRMING' || !this.state.target) return;
    this.save(this.state.target.packetId, {...this.state, target: Object.freeze({...this.state.target, reason, text}), error: ''});
  }
  cancel() {
    if (this.state.phase !== 'CONFIRMING') return;
    if (this.selection) this.records.delete(this.selection);
    this.publish({...initial(), phase: this.token ? 'READY' : 'BOOTSTRAP_UNAVAILABLE'});
  }
  async submit() {
    const target = this.state.target;
    if (!this.token || this.operation || this.state.phase !== 'CONFIRMING' || !target || this.selection !== target.packetId) return;
    const error = validation(target);
    if (error) { this.save(target.packetId, {...this.state, error}); return; }
    const lifecycle = this.lifecycle;
    this.operation = true;
    this.save(target.packetId, {...this.state, phase: 'PENDING', error: ''});
    try {
      const result = await this.transport.post(target.packetId, target.action, decisionBody(target), this.token);
      if (result.packet_id !== target.packetId || result.packet_version !== target.version || result.decision !== target.action || !result.decision_id ||
          result.historical_state !== {approve: 'approved_historically', reject: 'rejected', revise: 'revision_requested'}[target.action] || !result.historical) throw new Error('ambiguous');
      if (lifecycle !== this.lifecycle) return;
      await this.reconcileTarget(target, result, lifecycle);
    } catch (error) {
      if (lifecycle !== this.lifecycle) return;
      if (error instanceof DecisionFailure && error.code !== 'storage_unavailable') {
        if (['csrf_failed', 'authentication_required', 'authorization_failed', 'unauthorized_identity', 'invalid_host', 'local_only'].includes(error.code)) this.token = null;
        this.save(target.packetId, {...initial(), phase: 'FAILED', target, error: decisionError(error.code)});
        // Conflict refresh never converts a conflicting existing decision into success.
        if (error.code === 'decision_conflict') await this.refreshConflict(target, lifecycle);
      } else {
        this.save(target.packetId, {...initial(), phase: 'AMBIGUOUS', target, error: 'Decision status could not be confirmed. Refresh this packet before deciding again.'});
        await this.reconcileTarget(target, null, lifecycle);
      }
    } finally { this.operation = false; this.publish(this.state); }
  }
  private async readPacket(target: Target) {
    const packet = await this.reader.packet(target.packetId, new AbortController().signal);
    if (packet.packet_id !== target.packetId) throw new Error('unavailable');
    return packet;
  }
  private async readQueue() {
    const queue = await this.reader.queue('needs-review', 0, new AbortController().signal);
    if (queue.section !== 'needs-review' || queue.offset !== 0 || queue.limit !== 25 || queue.items.length > 25) throw new Error('unavailable');
    return queue;
  }
  private matches(target: Target, packet: Packet, decision: DecisionDetail, result: DecisionResult | null) {
    return packet.version === target.version && packet.expected_packet_fingerprint === target.fingerprint && packet.decision === target.action && decision.decision === target.action &&
      Boolean(decision.decision_id) && (!result || decision.decision_id === result.decision_id) &&
      (target.action !== 'reject' || decision.reason_code === target.reason && (decision.detail ?? '') === target.text) &&
      (target.action !== 'revise' || decision.feedback === target.text);
  }
  private async reconcileTarget(target: Target, result: DecisionResult | null, lifecycle: number) {
    try {
      const [packet, queue] = await Promise.all([this.readPacket(target), this.readQueue().catch(() => null)]);
      const decision = packet.decision ? await this.reader.decision(target.packetId, new AbortController().signal) : null;
      if (lifecycle !== this.lifecycle) return;
      if (decision) this.interrupted.delete(target.packetId);
      this.refreshed(packet, queue);
      if (decision && this.matches(target, packet, decision, result)) {
        // An ambiguous approval read cannot prove which approval-view evidence
        // another tab used. DecisionDetail does not expose that fingerprint.
        if (!result && target.action === 'approve') {
          this.save(target.packetId, {...initial(), phase: 'AMBIGUOUS', target, error: 'An approval exists for this packet. Its original approval evidence could not be confirmed. Review the packet history; do not repeat this decision.'});
          return;
        }
        const refreshed = Boolean(queue && !queue.items.some(item => item.packet_id === target.packetId));
        this.save(target.packetId, {...initial(), phase: 'RECORDED', target, authorization: packet.current_authorization,
          decisionId: decision.decision_id, refreshed, next: refreshed ? queue!.items[0] ?? null : null});
      } else if (decision) {
        this.save(target.packetId, {...initial(), phase: 'FAILED', target, error: decisionError('decision_conflict')});
      } else if (result) {
        this.save(target.packetId, {...initial(), phase: 'RECORDED', target, decisionId: result.decision_id, authorization: 'not_checked', error: 'Decision recorded. Packet history refresh is unavailable. Refresh before continuing.'});
      } else {
        // A successful exact read proves no decision at that read. A fresh
        // confirmation is still required; concurrent changes remain server checked.
        this.save(target.packetId, {...initial(), phase: 'FAILED', target, error: 'No decision was found on refresh. Review this packet before confirming a new decision.'});
        this.interrupted.delete(target.packetId);
      }
    } catch {
      if (lifecycle !== this.lifecycle) return;
      this.save(target.packetId, {...initial(), phase: result ? 'RECORDED' : 'AMBIGUOUS', target, decisionId: result?.decision_id ?? null, authorization: 'not_checked',
        error: result ? 'Decision recorded. Packet history refresh is unavailable. Refresh before continuing.' : 'Decision status could not be confirmed. Refresh this packet before deciding again.'});
    }
  }
  private async refreshConflict(target: Target, lifecycle: number) {
    try {
      const [packet, queue] = await Promise.all([this.readPacket(target), this.readQueue().catch(() => null)]);
      if (packet.decision) await this.reader.decision(target.packetId, new AbortController().signal);
      if (lifecycle === this.lifecycle) this.refreshed(packet, queue);
    } catch { /* Keep the sanitized conflict and explicit refresh available. */ }
  }
  async recover() {
    const record = this.state;
    const target = record.target;
    if (!target || this.operation || !['FAILED', 'AMBIGUOUS', 'RECORDED'].includes(record.phase)) return;
    const lifecycle = this.lifecycle;
    this.operation = true; this.publish(this.state);
    try {
      if (record.phase === 'AMBIGUOUS') await this.reconcileTarget(target, null, lifecycle);
      else {
        const [packet, queue] = await Promise.all([this.readPacket(target), this.readQueue().catch(() => null)]);
        const decision = packet.decision ? await this.reader.decision(target.packetId, new AbortController().signal) : null;
        if (lifecycle !== this.lifecycle) return;
        if (packet.decision) this.interrupted.delete(target.packetId);
        this.refreshed(packet, queue);
        if (!packet.decision) {
          this.interrupted.delete(target.packetId);
          this.records.delete(target.packetId);
          if (this.selection === target.packetId) this.publish({...initial(), phase: this.token ? 'READY' : 'BOOTSTRAP_UNAVAILABLE'});
        } else if (record.phase === 'RECORDED') {
          if (!decision || !this.matches(target, packet, decision, null) || decision.decision_id !== record.decisionId) {
            this.save(target.packetId, {...initial(), phase: 'FAILED', target, error: decisionError('decision_conflict')});
          } else {
            const refreshed = Boolean(queue && !queue.items.some(item => item.packet_id === target.packetId));
            this.save(target.packetId, {...record, authorization: packet.current_authorization, refreshed, next: refreshed ? queue!.items[0] ?? null : null, error: ''});
          }
        }
      }
    } catch { /* Do not clear a recovery barrier on a failed GET. */ }
    finally { this.operation = false; this.publish(this.state); }
  }
}
