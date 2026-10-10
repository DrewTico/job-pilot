import { DecisionDock, DecisionConfirmation } from './decision-controls';
import type { Decisions } from '../lib/use-decisions';
import { type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, FileText, ShieldCheck, ShieldAlert, MapPin, Check, CircleAlert, ListChecks, Users, ChevronDown, ChevronRight, X, Maximize2, CircleHelp } from 'lucide-react';
import { authorizationLabel, date, decisionLabel, revisionLabel, errorMessage, safeUrl, statusLabel } from '../lib/display';
import { companyInitials, companyPresentation, fitLabel, wordCount } from '../lib/review-presentation';
import type { DecisionDetail, Diff, Packet, Reader } from '../lib/types';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';

export function CompanyMark({company, packetId}: {company: string; packetId: string}) { return <span className="company-mark" aria-hidden="true">{companyInitials(companyPresentation(company, packetId).name)}</span>; }
export function CompanyName({company, packetId}: {company: string; packetId: string}) {
  const {name, demo} = companyPresentation(company, packetId);
  const lastWord = name.lastIndexOf(' ') + 1;
  return <span className="company-identity" aria-label={company} title={company}>{demo ? <>{name.slice(0, lastWord)}<span className="company-provenance">{name.slice(lastWord)}<span className="demo-label">DEMO</span></span></> : name}</span>;
}
export function EvidenceList({items, empty}: {items: string[]; empty: string}) {
  return items.length ? <ul className="evidence-list">{items.map((item, i) => <li key={i}>{item}</li>)}</ul> : <p className="muted">{empty}</p>;
}
function Source({url, title}: {url: string | null; title: string}) {
  const safe = safeUrl(url);
  return safe ? <a className="source-link" href={safe} target="_blank" rel="noopener noreferrer">{title}<ArrowUpRight aria-hidden="true" size={14}/><span className="sr-only"> (opens in a new tab)</span></a> : <span className="muted">{title} · Link unavailable</span>;
}
export function FitScoreRing({score}: {score: number}) {
  const gradient = useId();
  return <div className="fit-ring"><svg viewBox="0 0 120 120" role="meter" aria-label="Job fit score" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score}><defs><linearGradient id={gradient} x1="0" y1="1" x2="1" y2="0"><stop className="ring-start"/><stop offset="1" className="ring-end"/></linearGradient></defs><circle className="ring-track" cx="60" cy="60" r="52"/><circle className="ring-value" cx="60" cy="60" r="52" pathLength="100" stroke={`url(#${gradient})`} strokeDasharray={`${score} 100`} transform="rotate(-90 60 60)"/></svg><div><strong className="score">{score}</strong><span>FIT</span></div></div>;
}
export function HeroTopography() {
  return <svg className="hero-topography" viewBox="0 0 650 260" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><g fill="none"><ellipse cx="590" cy="160" rx="270" ry="160"/><ellipse cx="590" cy="160" rx="230" ry="137"/><ellipse cx="590" cy="160" rx="190" ry="112"/><ellipse cx="590" cy="160" rx="145" ry="87"/><ellipse cx="590" cy="160" rx="105" ry="63"/><ellipse cx="590" cy="160" rx="65" ry="39"/><path className="topography-path" d="M150 260 Q350 75 650 36"/></g></svg>;
}
function DocumentReader({packet, onClose}: {packet: Packet; onClose: () => void}) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    close.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  return <div className="reader-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}><div className="document-reader" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="reader-title" onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
    if (event.key === 'Tab') {
      const nodes = dialog.current?.querySelectorAll<HTMLElement>('button, a[href], [tabindex="0"]');
      if (!nodes?.length) return;
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }}><header className={`reader-header theme-${companyPresentation(packet.company, packet.packet_id).theme}`}><CompanyMark company={packet.company} packetId={packet.packet_id}/><div><h2 id="reader-title">Cover letter</h2><p><CompanyName company={packet.company} packetId={packet.packet_id}/> · {packet.title}</p></div><span className="mono reader-version">Packet v{packet.version}</span><button ref={close} className="icon-button" aria-label="Close reader" onClick={onClose}><X size={20} aria-hidden="true"/></button></header><div className="reader-scroll" tabIndex={0} aria-label="Cover letter document"><article className="reader-paper"><p className="paper-label">COVER LETTER · PACKET V{packet.version}</p><h3><CompanyName company={packet.company} packetId={packet.packet_id}/></h3><div className="exact-text reader-text">{packet.cover_text}</div></article></div></div></div>;
}

export function PacketInspector({packet, reader, onSelect, onBack, position, decisions}: {decisions: Decisions; packet: Packet; reader: Reader; onSelect: (id: string) => void; onBack: () => void; position: string}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const scoreBlock = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState('package');
  const [scoreOpen, setScoreOpen] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);
  const scoreId = useId();
  useEffect(() => {
    heading.current?.focus();
  }, [packet.packet_id, packet.decision, reader]);
  useEffect(() => {
    if (!scoreOpen) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setScoreOpen(false); scoreBlock.current?.querySelector('button')?.focus(); } };
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !scoreBlock.current?.contains(event.target)) setScoreOpen(false); };
    document.addEventListener('keydown', escape); document.addEventListener('pointerdown', outside);
    return () => { document.removeEventListener('keydown', escape); document.removeEventListener('pointerdown', outside); };
  }, [scoreOpen]);
  const manual = packet.screening.manual_needed.length;
  const resumeAvailable = packet.artifacts.some(item => item.available);
  const coverAvailable = packet.cover_integrity === 'available' && packet.cover_text !== null;
  return <article className={`inspector theme-${companyPresentation(packet.company, packet.packet_id).theme}`} aria-labelledby="packet-title">
    <div className="inspector-shell" inert={readerOpen || ['CONFIRMING', 'PENDING'].includes(decisions.state.phase) || undefined}>
      <header className="job-hero"><HeroTopography/><div className="hero-job"><CompanyMark company={packet.company} packetId={packet.packet_id}/><div className="hero-copy"><div className="hero-company-line"><p className="company-label"><CompanyName company={packet.company} packetId={packet.packet_id}/></p><span className="hero-version">Packet v{packet.version}</span></div><h2 id="packet-title" ref={heading} tabIndex={-1}>{packet.title}</h2><div className="hero-chips"><span className="job-location"><MapPin size={14} aria-hidden="true"/>{packet.location ?? 'Location unavailable'}</span><span className="status-badge" data-status={packet.status}>{statusLabel[packet.status]}</span></div><div className="hero-context"><button className="quiet back-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true"/>Back to queue</button><span className="context-position">{position}</span></div></div></div>
        <div className="fit-summary" ref={scoreBlock}><button className="score-button" aria-expanded={scoreOpen} aria-controls={scoreId} onClick={() => setScoreOpen(value => !value)}><FitScoreRing score={packet.score}/><span className="fit-description"><strong>{fitLabel(packet.score)}</strong><span>Job fit · out of 100</span><span className="score-prompt">Why this score<ChevronDown size={15} aria-hidden="true"/></span></span></button>
        {scoreOpen && <section id={scoreId} className="score-explanation" aria-label="Score explanation"><div className="section-heading"><h3>Why {packet.score}?</h3><button className="icon-button" aria-label="Close score explanation" onClick={() => setScoreOpen(false)}><X size={18}/></button></div><p className="muted">Detailed score breakdown not available yet.</p><h4>Fit reasons</h4><EvidenceList items={packet.reasons} empty="Match reasons unavailable."/><h4>Matched requirements</h4><EvidenceList items={packet.matched_requirements} empty="No matched requirements provided."/><div className="gaps"><h4>Listed gaps</h4><EvidenceList items={packet.missing_requirements} empty="No missing requirements provided."/></div><p className="score-note">Job fit is not an interview prediction.</p></section>}</div>
      </header>
      <div className="review-panes"><section className="left-detail" aria-label="Job fit and must-see information"><div className="must-see-grid">
        <section className="info-tile resume-tile"><div className="tile-heading"><h3 className="eyebrow">Resume</h3><button className="tile-link" onClick={() => setTab('resume')}>View package<ChevronRight size={13}/></button></div><p className="tile-value">{resumeAvailable ? 'Available' : 'Unavailable'}</p><div className="document-motif" aria-hidden="true"><FileText size={26}/><span/><span/><span/></div><p className="signal-note">Packet v{packet.version} · PDF artifact</p><p className="tile-detail">Match <span>Not available yet</span></p></section>
        <section className="info-tile interview-tile"><div className="tile-heading"><h3 className="eyebrow">Interview</h3><CircleHelp size={16} aria-hidden="true"/></div><p className="tile-value unavailable-value">Not available yet</p><div className="unknown-meter" aria-hidden="true"><span/><span/><span/><span/><span/></div><p className="signal-note">No interview prediction available.</p></section>
        <section className="info-tile people-tile"><div className="tile-heading"><h3 className="eyebrow">Right people</h3><button className="tile-link" onClick={() => setTab('people')}>View<ChevronRight size={13}/></button></div><p className="tile-value unavailable-value">Not available yet</p><div className="people-motif" aria-hidden="true"><Users size={32}/><span/><span/></div><p className="signal-note">Contacts and emails are unavailable.</p></section>
        <section className="info-tile location-tile"><div className="tile-heading"><h3 className="eyebrow">Location</h3><MapPin size={16} aria-hidden="true"/></div><p className="location-value">{packet.location ?? 'Location unavailable'}</p><div className="location-motif" aria-hidden="true"><span/><span/><MapPin size={30}/></div><p className="tile-detail">Relocation <span>Not stated</span></p></section>
      </div><section className="match-risk"><div className="strengths"><h3 className="eyebrow">Why it matches</h3><EvidenceList items={packet.reasons} empty="Match reasons unavailable."/></div><div className="gaps"><h3 className="eyebrow">Watch out</h3><EvidenceList items={packet.missing_requirements} empty="No missing requirements provided."/></div></section></section>
      <section className="evidence-panel" aria-label="Packet evidence"><Tabs value={tab} onValueChange={setTab} activationMode="manual" className="evidence-tabs"><TabsList aria-label="Evidence tabs"><TabsTrigger value="package">Package</TabsTrigger><TabsTrigger value="cover">Cover letter</TabsTrigger><TabsTrigger value="resume">Resume</TabsTrigger><TabsTrigger value="screening">Screening{manual > 0 && <span className="tab-count">{manual}</span>}</TabsTrigger><TabsTrigger value="people">People</TabsTrigger><TabsTrigger value="history">History</TabsTrigger></TabsList>
        <PacketEvidence packet={packet} reader={reader} onSelect={onSelect} setTab={setTab} onReaderOpen={() => setReaderOpen(true)}/>
      </Tabs></section></div>
      <DecisionDock packet={packet} decisions={decisions}/>
    </div><DecisionConfirmation decisions={decisions}/>{readerOpen && coverAvailable && <DocumentReader packet={packet} onClose={() => setReaderOpen(false)}/>}
  </article>;
}

function EvidenceSurface({value, active, children, className}: {value: string; active?: string; children: ReactNode; className: string}) {
  if (active !== undefined) return active === value ? <div className={className}>{children}</div> : null;
  return <TabsContent value={value} className={className}>{children}</TabsContent>;
}

// Identical evidence and authenticated comparisons for either presentation.
export function PacketEvidence({packet, reader, onSelect, setTab, onReaderOpen, active}: {packet: Packet; reader: Reader; onSelect: (id: string) => void; setTab: (value: string) => void; onReaderOpen: () => void; active?: string}) {
  const [decision, setDecision] = useState<DecisionDetail | null>(null);
  const [decisionError, setDecisionError] = useState(false);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [diffMessage, setDiffMessage] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (packet.decision) reader.decision(packet.packet_id, controller.signal).then(result => { if (!controller.signal.aborted) setDecision(result); }).catch(() => { if (!controller.signal.aborted) setDecisionError(true); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [packet.packet_id, packet.decision, reader]);
  async function compare(id: string, kind: 'resume' | 'cover') {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setDiff(null); setDiffMessage('Loading comparison.');
    try { const result = await reader.diff(id, packet.packet_id, kind, controller.signal);
      if (!controller.signal.aborted) { setDiff(result); setDiffMessage(result.status === 'available' ? '' : result.status === 'integrity_failed' ? 'Comparison integrity failed.' : 'Comparison unavailable.'); }
    } catch (error) { if (!controller.signal.aborted) setDiffMessage(errorMessage(error)); }
  }
  const currentVersion = packet.history.find(item => item.packet_id === packet.packet_id);
  const resumeAvailable = packet.artifacts.some(item => item.available);
  const coverAvailable = packet.cover_integrity === 'available' && packet.cover_text !== null;
  const coverState = packet.cover_integrity === 'integrity_failed' ? 'Cover integrity failed. Text withheld.' : 'Cover text unavailable.';
  const words = coverAvailable ? wordCount(packet.cover_text!) : null;
  const manual = packet.screening.manual_needed.length;
  return <>
        <EvidenceSurface active={active} value="package" className="evidence-content"><div className="package-list">
          <button className="package-row" onClick={() => setTab('resume')}><span className={`package-icon ${resumeAvailable ? '' : 'unknown'}`}><FileText size={20}/></span><span><strong>Resume</strong><span>Packet v{packet.version} · PDF artifact</span></span><span className="package-state">{resumeAvailable ? 'Available' : 'Unavailable'}</span></button>
          <button className="package-row" onClick={() => setTab('cover')}><span className={`package-icon ${coverAvailable ? '' : 'attention'}`}>{coverAvailable ? <Check size={20}/> : <CircleAlert size={20}/>}</span><span><strong>Cover letter</strong><span>{words === null ? coverState : `${words} words · authenticated text`}</span></span><span className="package-state">{coverAvailable ? 'Available' : packet.cover_integrity === 'integrity_failed' ? 'Withheld' : 'Unavailable'}</span></button>
          <button className={`package-row ${manual ? 'needs-attention' : ''}`} onClick={() => setTab('screening')}><span className={`package-icon ${manual ? 'attention' : ''}`}><ListChecks size={20}/></span><span><strong>Screening questions</strong><span>{packet.screening.answers.length} answers · {manual} manual-needed</span></span><span className="package-state">{manual ? 'Needs you' : 'Review'}</span></button>
          <button className="package-row" onClick={() => setTab('people')}><span className="package-icon unknown"><Users size={20}/></span><span><strong>People</strong><span>Not available yet</span></span><ChevronRight size={16}/></button>
        </div><section className={`integrity-strip ${packet.current_authorization === 'evidence_changed' || packet.integrity === 'failed' ? 'attention' : ''}`} aria-label="Authorization and integrity">{packet.integrity === 'passed' ? <ShieldCheck size={22}/> : <ShieldAlert size={22}/>}<div><strong>{authorizationLabel[packet.current_authorization]}</strong><p>{decisionLabel(packet.decision)} · Integrity {packet.integrity === 'not_checked' ? 'not checked' : packet.integrity}</p></div></section>
        <dl className="packet-signals"><div><dt>Resume PDF</dt><dd>{resumeAvailable ? 'Available' : 'Unavailable'}</dd></div><div><dt>Packet v{packet.version}</dt><dd>{currentVersion?.is_latest_ready ? 'Latest ready' : currentVersion ? 'Not latest ready' : 'Latest state unavailable'}</dd></div><div><dt>Manual review</dt><dd>{manual} to review</dd></div><div><dt>Cover evidence</dt><dd>Cover {packet.cover_integrity === 'available' ? 'available' : packet.cover_integrity === 'integrity_failed' ? 'withheld: integrity failed' : 'unavailable'}</dd></div></dl><p className="muted acceptance-note">Cover accepted: {packet.cover_letter_acceptance}</p>
        <section className="evidence-section company-evidence"><h3>Company evidence</h3>{packet.company_facts.length ? <ol className="facts">{packet.company_facts.map((fact, i) => <li key={i}><p>{fact.text}</p><Source url={fact.source_url} title={fact.source_title}/></li>)}</ol> : <p className="muted">Company facts unavailable. No evidence substituted.</p>}</section></EvidenceSurface>
        <EvidenceSurface active={active} value="cover" className="evidence-content">{active !== 'cover' && <div className="section-heading"><div><h3>Cover letter</h3><p className="muted">{words === null ? 'Text unavailable' : `${words} words · Packet v${packet.version}`}</p></div>{coverAvailable && <button className="quiet outlined" onClick={() => onReaderOpen()}><Maximize2 size={15}/>Open full view</button>}</div>}{coverAvailable ? <div className="exact-text cover-text">{packet.cover_text}</div> : <p className="state-message">{coverState}</p>}</EvidenceSurface>
        <EvidenceSurface active={active} value="resume" className="evidence-content"><h3>Resume</h3><div className="resume-package"><FileText size={48} aria-hidden="true"/><h4>Packet v{packet.version} · Resume PDF</h4><p>{resumeAvailable ? 'Available in the trusted decision UI' : 'Unavailable'}</p>{packet.artifacts.map((item, i) => <p key={i} className="mono">{item.kind} · {item.available ? 'Available' : 'Unavailable'}{item.size !== null ? ` · ${item.size.toLocaleString('en-US')} bytes` : ''}</p>)}</div><p className="muted">Resume body and match assessment are not available yet.</p><p className="muted">Use the trusted decision UI below to view the packet’s PDF.</p></EvidenceSurface>
        <EvidenceSurface active={active} value="screening" className="evidence-content"><h3>Screening answers</h3><div className="manual-section"><h4>Manual review needed · {manual}</h4><EvidenceList items={packet.screening.manual_needed} empty="No manual-needed questions provided."/></div>{packet.screening.answers.length ? <dl className="answers">{packet.screening.answers.map((item, i) => <div key={i}><dt>{item.question}</dt><dd className="exact-text">{item.answer === null ? 'Answer unavailable' : String(item.answer)}</dd></div>)}</dl> : <p className="muted">No screening answers provided.</p>}</EvidenceSurface>
        <EvidenceSurface active={active} value="people" className="evidence-content"><div className="people-unavailable"><div className="empty-symbol"><Users size={36}/></div><p className="eyebrow">Right people</p><h3>Not available yet</h3><p className="muted">Contact evidence is not available for this packet.</p></div></EvidenceSurface>
        <EvidenceSurface active={active} value="history" className="evidence-content"><section className="evidence-section"><h3>Decision record</h3><p>{decisionLabel(packet.decision)}</p>{decision ? <dl className="answers"><div><dt>Recorded</dt><dd>{date(decision.created_at)}</dd></div>{decision.reason_code && <div><dt>Reason</dt><dd>{decision.reason_code}</dd></div>}{decision.detail !== null && <div><dt>Decision detail</dt><dd className="exact-text">{decision.detail}</dd></div>}{decision.feedback !== null && <div><dt>Revision feedback</dt><dd className="exact-text">{decision.feedback}</dd></div>}</dl> : packet.decision && <p className="muted">{decisionError ? 'Decision detail unavailable.' : 'Loading decision record.'}</p>}</section>
        <section className="evidence-section"><h3>Revision</h3><p>{revisionLabel(packet.revision)}</p><p className="muted">Updated: {date(packet.revision.updated_at)}</p>{packet.revision.failure_category && <p>Attention category: {packet.revision.failure_category}</p>}{packet.revision.successor_packet_id && <button className="quiet" onClick={() => onSelect(packet.revision.successor_packet_id!)}>Inspect successor v{packet.revision.successor_version ?? '?'}<ArrowUpRight size={16}/></button>}</section>
        <section className="evidence-section"><h3>Version history</h3>{packet.history.length ? <ol className="history-list">{packet.history.map(item => <li key={item.packet_id} className={item.packet_id === packet.packet_id ? 'history-current' : ''}><div className="history-node" aria-hidden="true"/><div className="history-entry"><div className="history-title"><strong>Version {item.version}</strong>{item.packet_id === packet.packet_id && <span className="current-badge">Viewing</span>}{item.is_latest_ready && <span className="current-badge">Latest ready</span>}{item.is_latest_allocated && <span className="muted">Latest allocated</span>}</div><span>{statusLabel[item.status]} · {decisionLabel(item.decision)}</span><p className="muted">Created {date(item.created_at)} · {item.lineage_kind.replaceAll('_', ' ')}</p><p className="muted">Ready {date(item.ready_at)} · Updated {date(item.updated_at)}</p>{item.source_packet_id && <p className="muted">Source packet <span className="mono">{item.source_packet_id}</span></p>}{item.revision_decision_id && <p className="muted">Revision record <span className="mono">{item.revision_decision_id}</span></p>}<div className="history-actions">{item.packet_id !== packet.packet_id && <><button className="quiet outlined" onClick={() => onSelect(item.packet_id)}>Inspect v{item.version}</button><button className="quiet outlined" onClick={() => compare(item.packet_id, 'resume')}>Resume diff v{item.version}</button><button className="quiet outlined" onClick={() => compare(item.packet_id, 'cover')}>Cover diff v{item.version}</button></>}</div></div></li>)}</ol> : <p className="muted">Version history unavailable.</p>}<p role="status">{diffMessage}</p>{diff?.status === 'available' && <><h4>{diff.kind === 'resume' ? 'Resume' : 'Cover'} comparison · v{diff.left_version} to v{diff.right_version}</h4><pre className="exact-text diff-text">{diff.diff ?? 'Comparison text unavailable.'}</pre></>}</section>
        <section className="evidence-section identity"><h3>Packet identity</h3><dl><dt>Packet ID</dt><dd className="mono">{packet.packet_id}</dd><dt>Expected packet fingerprint</dt><dd className="mono fingerprint">{packet.expected_packet_fingerprint}</dd><dt>Ready at</dt><dd>{date(packet.ready_at)}</dd>{packet.approval_preview && <><dt>Approval view fingerprint</dt><dd className="mono fingerprint">{packet.approval_preview.expected_approval_view_fingerprint}</dd></>}</dl></section>
        <section className="evidence-section"><h3>Application destination</h3><p className="muted">Destination authorization: {authorizationLabel[packet.application_destination.authorization]}</p>{packet.application_destination.url && safeUrl(packet.application_destination.url) ? <p className="exact-text">{packet.application_destination.url}</p> : <p className="muted">Application destination unavailable.</p>}</section></EvidenceSurface>
  </>;
}
