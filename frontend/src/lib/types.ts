export type Section = 'needs-review' | 'processing' | 'needs-attention' | 'history';
export type Decision = 'approve' | 'reject' | 'revise' | null;
export type Status = 'building' | 'packet_ready' | 'generation_failed' | 'research_incomplete' | 'recovery_required';
export type Authorization = 'not_approved' | 'currently_valid' | 'evidence_changed' | 'integrity_failed' | 'not_checked';
export interface QueueItem {
  packet_id: string; version: number; company: string; title: string; location: string | null;
  score: number; tier: string; status: Status; ready_at: string | null;
  cover_letter_acceptance: 'yes' | 'no' | 'unknown'; manual_needed_count: number;
  decision: Decision; revision_state: string | null; integrity: 'not_checked';
}
export interface Queue { section: Section; limit: number; offset: number; items: QueueItem[] }
export interface History {
  packet_id: string; version: number; status: Status; decision: Decision;
  created_at: string | null; updated_at: string | null; ready_at: string | null;
  revision_decision_id: string | null; source_packet_id: string | null;
  lineage_kind: 'unlinked' | 'revision' | 'corruption_recovery'; is_latest_allocated: boolean; is_latest_ready: boolean;
}
export interface Packet extends Omit<QueueItem, 'integrity' | 'manual_needed_count' | 'revision_state'> {
  expected_packet_fingerprint: string; integrity: 'passed' | 'failed' | 'not_checked'; current_authorization: Authorization;
  reasons: string[]; matched_requirements: string[]; missing_requirements: string[];
  cover_text: string | null; cover_integrity: 'available' | 'unavailable' | 'integrity_failed';
  screening: { answers: {question: string; answer: string | boolean | number | null}[]; manual_needed: string[] };
  company_facts: {text: string; source_title: string; source_url: string | null}[];
  history: History[];
  revision: {source_packet_id: string; decision_id: string | null; state: string; label: string;
    updated_at: string | null; successor_packet_id: string | null; successor_version: number | null;
    successor_status: Status | null; failure_category: string | null};
  artifacts: {kind: 'resume_pdf'; available: boolean; size: number | null}[];
  application_destination: {url: string | null; domain: string | null; authorization: Authorization};
  approval_preview: {packet_id: string; packet_version: number; expected_packet_fingerprint: string;
    expected_approval_view_fingerprint: string; application_url: string} | null;
}
export interface DecisionDetail { decision_id: string; decision: Exclude<Decision, null>; created_at: string; reason_code: string | null; detail: string | null; feedback: string | null }
export interface Diff { kind: 'resume' | 'cover'; left_packet_id: string; left_version: number; right_packet_id: string; right_version: number; status: 'available' | 'unavailable' | 'integrity_failed'; diff: string | null }
export interface Reader {
  queue(section: Section, offset: number, signal: AbortSignal): Promise<Queue>;
  packet(id: string, signal: AbortSignal): Promise<Packet>;
  decision(id: string, signal: AbortSignal): Promise<DecisionDetail>;
  diff(left: string, right: string, kind: 'resume' | 'cover', signal: AbortSignal): Promise<Diff>;
}
