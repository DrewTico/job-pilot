import { Check, ChevronRight, MessageSquare, ShieldCheck, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { authorizationLabel } from '../lib/display';
import { canDecide, rejectReasons } from '../lib/decision-controller';
import type { Decisions } from '../lib/use-decisions';
import type { Packet } from '../lib/types';
import { CompanyName } from './packet-inspector';
import { MobileSheet } from './ui/mobile-sheet';

const recorded = {approve: 'Approval recorded', reject: 'Rejection recorded', revise: 'Revision request recorded'};
const supporting = {approve: 'No application submitted', reject: 'This decision applies to this exact packet.', revise: 'Revision generation is a separate step.'};
const confirmTitle = {approve: 'Record approval?', reject: 'Record rejection?', revise: 'Record revision request?'};
const confirmButton = {approve: 'Record approval', reject: 'Record rejection', revise: 'Record revision request'};

export function PhoneDecisionResult({packet, decisions, onHistory}: {packet: Packet; decisions: Decisions; onHistory: () => void}) {
  const {state} = decisions;
  const target = state.target;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (state.phase === 'RECORDED') heading.current?.focus({preventScroll: true}); }, [state.phase]);
  if (state.phase !== 'RECORDED' || target?.packetId !== packet.packet_id) return null;
  return <section className="phone-decision-result" aria-label="Recorded decision">
    <div className="decision-record-symbol" aria-hidden="true"><Check size={42}/></div>
    <p className="eyebrow">Exact packet v{target.version}</p>
    <h1 tabIndex={-1} ref={heading}>{recorded[target.action]}</h1>
    <p className="decision-result-boundary">{supporting[target.action]}</p>
    <div className="decision-result-packet"><strong>{target.company}</strong><p>{target.title}</p></div>
    {target.action === 'approve' && <p className="decision-result-authorization">{state.authorization === 'currently_valid' ? 'Ready for next step' : authorizationLabel[state.authorization]}</p>}
    <button className="quiet outlined" onClick={onHistory}>View packet history</button>
  </section>;
}

export function DecisionDock({packet, decisions, phone = false}: {packet: Packet; decisions: Decisions; phone?: boolean}) {
  const {state, controller, synthetic} = decisions;
  const target = state.target?.packetId === packet.packet_id ? state.target : null;
  const isRecorded = target && state.phase === 'RECORDED';
  const barrier = target && ['AMBIGUOUS', 'FAILED'].includes(state.phase);
  const disabled = synthetic || !state.ready || state.busy || Boolean(packet.decision) || ['CONFIRMING', 'PENDING', 'RECORDED', 'AMBIGUOUS', 'FAILED'].includes(state.phase);
  return <footer className={`decision-handoff decision-dock ${phone ? 'phone-handoff phone-decision-dock' : ''}`} aria-label="Packet decisions">
    <span className="dock-icon" aria-hidden="true">{isRecorded ? <Check size={21}/> : <ShieldCheck size={21}/>}</span>
    <div className="decision-context" tabIndex={0} aria-label="Current packet context">
      <strong>{isRecorded ? recorded[target.action] : `Reviewing packet v${packet.version}`} {!isRecorded && <> · <CompanyName company={packet.company} packetId={packet.packet_id}/></>}</strong>
      <p role="status" aria-live="polite">{isRecorded ? supporting[target.action] : state.busy ? target ? 'Recording decision. Please wait.' : 'A decision for another packet is being confirmed.' : barrier ? state.error : synthetic ? 'Demo decisions unavailable.' : !state.ready ? state.error || 'Enabling trusted decisions.' : packet.decision ? `${recorded[packet.decision]} · Immutable decision` : 'Exact packet only · No application submitted'}</p>
      {isRecorded && target.action === 'approve' && <p>{state.authorization === 'currently_valid' ? 'Ready for next step' : authorizationLabel[state.authorization]}</p>}
      {isRecorded && state.error && <p role="alert">{state.error}</p>}
      {!isRecorded && !barrier && state.ready && !packet.decision && !canDecide(packet, 'approve') && <p>Approval evidence unavailable. Reject or Revise may still be available.</p>}
    </div>
    <div className="decision-actions">
      {!synthetic && !state.ready && <button className="quiet outlined" disabled={state.busy} onClick={() => void controller.bootstrap()}>Enable decisions</button>}
      {(barrier || isRecorded && !state.refreshed) && <button className="quiet outlined" disabled={state.busy} onClick={() => void controller.recover()}>Refresh this packet</button>}
      {isRecorded && state.refreshed && state.next && <button className="button primary" onClick={() => decisions.nextQueued(state.next!.packet_id)}>Next queued job<ChevronRight size={16}/></button>}
      {isRecorded && state.refreshed && !state.next && <span className="decision-queue-note">No queued job on the refreshed first page.</span>}
      {!packet.decision && !isRecorded && !barrier && <>
        <button className="button primary" disabled={disabled || !canDecide(packet, 'approve')} onClick={() => controller.begin(packet, 'approve')}><Check size={16}/>Approve</button>
        <button className="button decision-revise" disabled={disabled || !canDecide(packet, 'revise')} onClick={() => controller.begin(packet, 'revise')}><MessageSquare size={16}/>Revise</button>
        <button className="button decision-reject" disabled={disabled || !canDecide(packet, 'reject')} onClick={() => controller.begin(packet, 'reject')}><X size={16}/>Reject</button>
      </>}
    </div>
  </footer>;
}

export function DecisionConfirmation({decisions, phone = false}: {decisions: Decisions; phone?: boolean}) {
  const {state, controller} = decisions;
  const target = state.target;
  useEffect(() => {
    if (state.error && state.phase === 'CONFIRMING') document.querySelector<HTMLElement>('.decision-form [aria-invalid="true"]')?.focus();
  }, [state.error, state.phase]);
  if (!target || !['CONFIRMING', 'PENDING'].includes(state.phase)) return null;
  const pending = state.phase === 'PENDING';
  const field = target.action === 'reject' ? 'detail' : 'feedback';
  const count = Array.from(target.text).length;
  return <div className={phone ? 'decision-phone-modal' : 'decision-desktop-modal'}>
    <MobileSheet kind={`decision-${target.action}`} title={confirmTitle[target.action]} subtitle={`Packet v${target.version} · ${target.company}`} onClose={() => controller.cancel()} pending={pending} initialField={target.action !== 'approve'}>
      <form className="decision-form" onSubmit={event => {event.preventDefault(); void controller.submit();}} noValidate>
        <div className="decision-exact-context"><p className="eyebrow">{target.action === 'approve' ? 'Approval' : target.action === 'reject' ? 'Rejection' : 'Revision request'} · Exact packet v{target.version}</p><h3>{target.title}</h3><p>{target.company}</p></div>
        <p className="decision-consent">{target.action === 'approve' ? 'This records your approval for this exact packet. It does not submit an application to the employer.' : target.action === 'revise' ? 'This action records a revision request. Revision generation is a separate step.' : 'This records a rejection for this exact packet. The decision cannot be edited or undone.'}</p>
        {target.action === 'reject' && <div className="decision-field"><label htmlFor="decision-reason">Reason (required)</label><select id="decision-reason" disabled={pending} value={target.reason} aria-invalid={state.error === 'Choose a reason.'} aria-describedby={state.error ? 'decision-validation' : undefined} onChange={event => controller.edit(event.target.value, target.text)}><option value="">Choose a reason</option>{Object.entries(rejectReasons).map(([code, label]) => <option value={code} key={code}>{label}</option>)}</select></div>}
        {target.action !== 'approve' && <div className="decision-field"><label htmlFor={`decision-${field}`}>{target.action === 'revise' ? 'Revision feedback (required)' : 'Detail (optional)'}</label><textarea id={`decision-${field}`} disabled={pending} rows={phone ? 6 : 5} value={target.text} aria-invalid={Boolean(state.error) && state.error !== 'Choose a reason.'} aria-describedby={`decision-count${state.error ? ' decision-validation' : ''}`} onChange={event => controller.edit(target.reason, event.target.value)}/><p id="decision-count" className={`decision-count ${count > 4000 ? 'over-limit' : ''}`}>{count.toLocaleString('en-US')} / 4,000 characters</p></div>}
        {state.error && <p id="decision-validation" role="alert" className="decision-validation">{state.error}</p>}
        <p className="decision-pending" role="status" aria-live="polite">{pending ? 'Recording decision. Keep this packet open while its status is confirmed.' : ''}</p>
        <div className="decision-form-actions"><button className={`button ${target.action === 'approve' ? 'primary' : target.action === 'reject' ? 'decision-reject' : 'decision-revise'}`} disabled={pending} type="submit">{pending ? 'Recording…' : confirmButton[target.action]}</button><button type="button" className="quiet outlined" disabled={pending} onClick={() => controller.cancel()}>Cancel</button></div>
      </form>
    </MobileSheet>
  </div>;
}
