import { ArrowRight, GitCompareArrows, RefreshCw } from 'lucide-react';
import type { Packet, RevisionContentDiff } from '../lib/types';
import type { RevisionReview } from '../lib/use-revision-review';
import type { Decisions } from '../lib/use-decisions';
const labels: Record<string, string> = {
  queued: 'Revision request recorded', pending: 'Preparing revision', style_prepared: 'Saving revision preferences',
  style_persisted: 'Preparing new packet', building: 'Generating revision', succeeded: 'Revision work completed',
  blocked: 'Revision needs attention', recovery_required: 'Manual recovery required', none: 'No revision requested',
};
export function RevisionSummary({packet, review, decisions, onChanges, onSelect}: {packet: Packet; review: RevisionReview; decisions?: Decisions; onChanges: () => void; onSelect: (id: string) => void}) {
  const {state, refresh} = review;
  const linked = packet.history.some(item => item.packet_id === packet.packet_id && item.lineage_kind === 'revision');
  if (packet.decision !== 'revise' && !linked) return null;
  const status = state?.status;
  const recordedDecision = decisions?.state.phase === 'RECORDED' && decisions.state.target?.packetId === packet.packet_id && decisions.state.target.action === 'revise' ? decisions.state : null;
  return <section className="revision-summary" aria-label="Revision review" data-state={status?.state ?? 'loading'}>
    <div className="revision-heading"><GitCompareArrows size={19} aria-hidden="true"/><div><p className="eyebrow">{linked && packet.decision !== 'revise' ? `Reviewing successor v${packet.version}` : `Revision of v${packet.version}`}</p><h2>{state?.error || (status ? labels[status.state] : 'Checking revision status')}</h2></div></div>
    <p role="status" aria-live="polite">{state?.error ? 'Current revision work and successor availability could not be confirmed.' : status?.state === 'queued' ? 'Generation is a separate step. Waiting for revision processing.' : state?.loading ? 'Reading current revision evidence.' : status?.state === 'succeeded' ? state?.successor ? `Successor v${state.successor.version} verified for review. ${state.successor.decision ? "Its own decision is recorded." : "A fresh decision is required."}` : linked && !state?.successorError ? 'This version needs its own decision. No predecessor approval transfers.' : 'Checking current successor availability.' : status?.state === 'blocked' ? `Processing stopped. Attention: ${status.failure_category ?? 'manual review'}.` : status?.state === 'recovery_required' ? 'The outcome needs manual recovery. No automatic retry.' : status?.state === 'none' ? 'No revision work recorded.' : 'Revision processing is active. No successor is offered yet.'}</p>
    {state?.successorError && <p className="revision-error" role="alert">{state.successorError}</p>}
    {state?.paused && <p>Automatic refresh paused. Check status again when needed.</p>}
    {recordedDecision?.error && <p className="revision-error" role="alert">{recordedDecision.error}</p>}
    <div className="revision-actions">
      {state?.successor && <button className="quiet outlined" onClick={() => onSelect(state.successor!.packet_id)}>Review successor v{state.successor.version}<ArrowRight size={16}/></button>}
      {(state?.comparison || state?.comparisonError) && <button className="quiet outlined" onClick={onChanges}>Review changes</button>}
      <button className="quiet" disabled={state?.loading} onClick={refresh} aria-label="Refresh revision status"><RefreshCw size={15}/>Check status</button>
      {recordedDecision && !recordedDecision.refreshed && <button className="quiet outlined" disabled={recordedDecision.busy} onClick={() => void decisions!.controller.recover()}>Refresh this packet</button>}
      {recordedDecision?.refreshed && recordedDecision.next && <button className="quiet outlined" onClick={() => decisions!.nextQueued(recordedDecision.next!.packet_id)}>Next queued job<ArrowRight size={16}/></button>}
    </div>
  </section>;
}
const sideLabel = {available: 'Authenticated', unavailable: 'Unavailable', integrity_failed: 'Integrity failed'};
// Presentation only: retain every document line and missing-newline marker.
// File headers and hunk coordinates belong to the unified-diff transport.
export function documentChangeLines(diff: string) {
  const lines = diff.split('\n');
  if (lines[0]?.startsWith('--- ') && lines[1]?.startsWith('+++ ')) lines.splice(0, 2);
  if (lines.at(-1) === '') lines.pop();
  let passage = 0;
  return lines.flatMap(line => {
    if (/^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@$/.test(line)) { passage++; return []; }
    const marker = line[0];
    const kind = marker === '+' ? 'added' : marker === '-' ? 'removed' : marker === ' ' ? 'context' : 'note';
    return [{kind, text: kind === 'note' ? line : line.slice(1), passage}];
  });
}
function ContentChanges({title, content}: {title: string; content: RevisionContentDiff | null}) {
  const label = !content ? 'Comparison unavailable' : content.status === 'available' ? content.changed ? 'Authenticated · Changed' : 'Authenticated · Unchanged' : content.status === 'integrity_failed' ? 'Integrity failed · Changes withheld' : 'Unavailable · Changes unknown';
  const lines = content?.status === 'available' && content.changed ? documentChangeLines(content.diff!) : [];
  return <section className="revision-content" aria-label={`${title} changes`} data-state={content?.status ?? 'unavailable'}>
    <h4>{title}</h4><p className="comparison-state">{label}</p>
    {content && <dl className="comparison-sides"><div><dt>Before</dt><dd>{sideLabel[content.before_status]}</dd></div><div><dt>After</dt><dd>{sideLabel[content.after_status]}</dd></div></dl>}
    {lines.length > 0 && <><p className="diff-key"><span>+ Added</span><span>- Removed</span><span>Context retained</span></p>
      <div className="revision-diff">{lines.map((line, index) => <div key={index} className={`diff-line diff-${line.kind}${index > 0 && line.passage !== lines[index - 1].passage ? ' diff-passage' : ''}`}>
        {index > 0 && line.passage !== lines[index - 1].passage && <span className="sr-only">Next changed passage</span>}
        <span className="diff-marker" aria-hidden="true">{line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : ''}</span>
        <span className="sr-only">{line.kind === 'added' ? 'Added: ' : line.kind === 'removed' ? 'Removed: ' : line.kind === 'context' ? 'Context: ' : ''}</span>
        <span className="diff-document-text">{line.text}</span>
      </div>)}</div></>}
    {content?.status === 'available' && !content.changed && <p className="muted">No content changes between these versions.</p>}
  </section>;
}
export function RevisionChanges({review}: {review: RevisionReview}) {
  const state = review.state;
  if (!state?.comparison && !state?.comparisonError) return null;
  const c = state.comparison;
  return <section className="revision-changes evidence-section" aria-label="Revision comparison">
    <div className="section-heading"><h3>What changed</h3><button className="quiet" disabled={state.loading} onClick={review.refresh}>Refresh comparison</button></div>
    {state.comparisonError && <p role="alert">{state.comparisonError}</p>}
    {c && <><p className="comparison-direction">Before v{c.before.version ?? '?'} <ArrowRight size={15} aria-label="to"/> After v{c.after.version ?? '?'}</p>
      <p role="status" className="comparison-overall">{c.status === 'available' ? 'Both documents authenticated' : c.status === 'invalid_request' ? 'Invalid revision relationship. Changes withheld.' : c.status === 'integrity_failed' ? 'Comparison integrity failed. Review each document’s evidence state.' : 'Comparison unavailable in whole or in part. Changes are unknown where evidence is missing.'}</p>
      <ContentChanges title="Resume" content={c.resume}/><ContentChanges title="Cover letter" content={c.cover}/>
      <p className="muted comparison-limit">Screening and manual-needed changes cannot be independently authenticated. Review this packet’s current answers separately. Content comparison does not grant approval.</p>
    </>}
  </section>;
}
