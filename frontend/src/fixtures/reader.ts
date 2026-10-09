import data from './review.json';
import type { Packet, QueueItem, Reader } from '../lib/types';
const packets = data.packets as unknown as Packet[];
function find(id: string) { const packet = packets.find(item => item.packet_id === id); if (!packet) throw new Error('unavailable'); return packet; }
export const fixtureReader: Reader = {
  queue: async (section, offset) => ({section, offset, limit: 25, items: data.sections[section].slice(offset, offset + 25).map(index => {
    const p = find(index.toString(16).padStart(32, '0'));
    return {packet_id: p.packet_id, version: p.version, company: p.company, title: p.title, location: p.location, score: p.score, tier: p.tier, status: p.status, ready_at: p.ready_at, cover_letter_acceptance: p.cover_letter_acceptance, manual_needed_count: p.screening.manual_needed.length, decision: p.decision, revision_state: p.decision === 'revise' ? p.revision.state : null, integrity: 'not_checked'} as QueueItem;
  })}),
  packet: async id => find(id),
  decision: async id => ({decision_id: 'synthetic-record', decision: find(id).decision ?? 'reject', created_at: '2026-10-01T14:10:00Z', reason_code: null, detail: null, feedback: find(id).decision === 'revise' ? 'Synthetic feedback: make the evidence more specific.' : null}),
  diff: async (left, right, kind) => ({kind, left_packet_id: left, right_packet_id: right, left_version: find(left).version, right_version: find(right).version, status: 'available', diff: '- Synthetic previous wording\n+ Synthetic revised wording'}),
};
