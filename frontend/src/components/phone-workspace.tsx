import Head from 'next/head';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ArrowUpRight, CalendarDays, Check, ChevronLeft, ChevronRight, ClipboardCheck, FileSearch, FileText, History, LayoutGrid, ListChecks, MapPin, RefreshCw, ShieldAlert, ShieldCheck, Users, X } from 'lucide-react';
import { authorizationLabel, decisionLabel, sections, statusLabel } from '../lib/display';
import { companyPresentation, fitLabel, wordCount } from '../lib/review-presentation';
import type { Packet, Reader } from '../lib/types';
import type { useReviewWorkspace } from '../lib/use-review-workspace';
import { CompanyMark, CompanyName, EvidenceList, FitScoreRing, HeroTopography, PacketEvidence } from './packet-inspector';

type WorkspaceState = ReturnType<typeof useReviewWorkspace>;
type Sheet = 'why' | 'people' | 'cover' | 'resume' | 'screening' | 'history' | 'package';

// Source-owned dialog. Scroll locking uses a CSS class, never injected styles.
export function MobileSheet({title, subtitle, kind, onClose, children}: {title: string; subtitle: string; kind: Sheet; onClose: () => void; children: ReactNode}) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const subtitleId = useId();
  useEffect(() => {
    const previous = document.activeElement;
    document.documentElement.classList.add('phone-sheet-open');
    close.current?.focus();
    const contain = (event: FocusEvent) => { if (event.target instanceof Node && !dialog.current?.contains(event.target)) close.current?.focus(); };
    document.addEventListener('focusin', contain);
    return () => {
      document.documentElement.classList.remove('phone-sheet-open');
      document.removeEventListener('focusin', contain);
      if (previous instanceof HTMLElement && previous.isConnected && !previous.closest('[inert]')) previous.focus({preventScroll: true});
    };
  }, []);
  return <div className="phone-sheet-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={`phone-sheet phone-sheet-${kind}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={subtitleId} ref={dialog} onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
      if (event.key === 'Tab') {
        const nodes = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], [tabindex="0"]');
        if (!nodes?.length) return;
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <div className="phone-sheet-grabber" aria-hidden="true"/>
      <header className="phone-sheet-header"><div><h2 id={titleId}>{title}</h2><p id={subtitleId}>{subtitle}</p></div><button className="icon-button" ref={close} aria-label="Close sheet" onClick={onClose}><X size={20} aria-hidden="true"/></button></header>
      <div className="phone-sheet-scroll" tabIndex={0} aria-label={`${title} content`}>{children}</div>
    </div>
  </div>;
}

function PhoneNavigation() {
  return <nav className="phone-bottom-nav" aria-label="Workspace"><button disabled aria-label="Overview unavailable"><LayoutGrid size={21}/><span>Overview</span></button><a href="/ui" aria-current="page"><ClipboardCheck size={21}/><span>Review</span></a><button disabled aria-label="People unavailable"><Users size={21}/><span>People</span></button><button disabled aria-label="Calendar unavailable"><CalendarDays size={21}/><span>Calendar</span></button></nav>;
}

function PhoneReview({packet, reader, state}: {packet: Packet; reader: Reader; state: WorkspaceState}) {
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const {queue, select, back} = state;
  const position = queue?.items.findIndex(item => item.packet_id === packet.packet_id) ?? -1;
  const total = queue?.items.length ?? 0;
  const resume = packet.artifacts.some(item => item.available);
  const cover = packet.cover_integrity === 'available' && packet.cover_text !== null;
  const manual = packet.screening.manual_needed.length;
  const theme = companyPresentation(packet.company, packet.packet_id).theme;
  useEffect(() => { window.scrollTo(0, 0); heading.current?.focus({preventScroll: true}); }, []);
  function navigate(index: number) { const item = queue?.items[index]; if (item) select(item.packet_id); }
  function open(value: string) { setSheet(value as Sheet); }
  const titles: Record<Sheet, string> = {why: `Why ${packet.score}?`, people: 'Right people', cover: 'Cover letter', resume: 'Resume', screening: 'Screening answers', history: 'History', package: 'Packet evidence'};
  return <article className={`phone-review theme-${theme}`} aria-labelledby="packet-title">
    <div className="phone-review-page" inert={sheet ? true : undefined}>
      <header className="phone-review-nav"><button className="quiet" aria-label="Back to queue" onClick={back}><ChevronLeft size={19}/>Queue</button><span>{position >= 0 ? `${position + 1} of ${total} loaded` : 'Outside loaded page'}</span><button className="quiet" aria-label="Next loaded job" disabled={position < 0 || position + 1 >= total} onClick={() => navigate(position + 1)}>Next<ChevronRight size={19}/></button></header>
      <div className="phone-review-content">
        <header className="phone-hero"><HeroTopography/><div className="phone-company"><CompanyMark company={packet.company} packetId={packet.packet_id}/><div><p className="company-label"><CompanyName company={packet.company} packetId={packet.packet_id}/></p><p className="hero-version">Packet v{packet.version} · {statusLabel[packet.status]}</p></div></div>
          <h1 id="packet-title" ref={heading} tabIndex={-1}>{packet.title}</h1><div className="phone-hero-chips"><span className="job-location"><MapPin size={13}/>{packet.location ?? 'Location unavailable'}</span><span className="phone-relocation">Relocation not stated</span></div>
          <button className="phone-score" aria-label={`Why this score: ${packet.score}`} aria-haspopup="dialog" onClick={() => setSheet('why')}><FitScoreRing score={packet.score}/><span className="fit-description"><strong>{fitLabel(packet.score)}</strong><span>Job fit · out of 100</span><span className="score-prompt">Why this score<ChevronRight size={15}/></span></span></button>
        </header>
        <section className="phone-must-see" aria-label="Job fit and must-see information">
          <section className="phone-info resume-tile"><h2 className="eyebrow">Resume</h2><p className="phone-tile-value">{resume ? 'Available' : 'Unavailable'}</p><div className="phone-document-motif" aria-hidden="true"><FileText size={22}/><span/><span/><span/></div><p className="signal-note">Match: Not available yet</p><button className="phone-tile-hit" aria-label="View resume package" aria-haspopup="dialog" onClick={() => setSheet('resume')}><ChevronRight size={14} aria-hidden="true"/></button></section>
          <section className="phone-info interview-tile"><h2 className="eyebrow">Interview</h2><p className="phone-tile-value phone-unknown">Not available yet</p><div className="unknown-meter" aria-hidden="true"><span/><span/><span/><span/><span/></div><p className="signal-note">No prediction available.</p></section>
          <section className="phone-info people-tile"><h2 className="eyebrow">Right people</h2><div className="phone-people-motif" aria-hidden="true"><Users size={26}/></div><p className="phone-tile-value phone-unknown">Not available yet</p><button className="phone-tile-link" aria-label="View people" aria-haspopup="dialog" onClick={() => setSheet('people')}>View details<ChevronRight size={14}/></button></section>
          <section className="phone-info location-tile"><h2 className="eyebrow">Location</h2><MapPin className="phone-location-icon" size={26} aria-hidden="true"/><p className="phone-location-value">{packet.location ?? 'Location unavailable'}</p><p className="signal-note">Relocation: Not stated</p></section>
        </section>
        <section className="phone-why-watch"><div className="strengths"><h2 className="eyebrow">Why it matches</h2><EvidenceList items={packet.reasons} empty="Match reasons unavailable."/></div><div className="gaps"><h2 className="eyebrow">Watch out</h2><EvidenceList items={packet.missing_requirements} empty="No missing requirements provided."/></div></section>
        <section className="phone-package" aria-label="Application package"><h2 className="eyebrow">Application package</h2>
          {[
            {kind: 'resume', state: resume ? 'available' : 'unavailable', icon: FileText, title: 'Resume', detail: `Packet v${packet.version} · PDF ${resume ? 'available' : 'unavailable'}`},
            {kind: 'cover', state: cover ? 'available' : packet.cover_integrity === 'integrity_failed' ? 'failed' : 'unavailable', icon: FileText, title: 'Cover letter', detail: cover ? `${wordCount(packet.cover_text!)} words · authenticated text` : packet.cover_integrity === 'integrity_failed' ? 'Integrity failed · Text withheld' : 'Cover text unavailable.'},
            {kind: 'screening', state: manual ? 'attention' : 'information', icon: ListChecks, title: 'Screening', detail: `${packet.screening.answers.length} answers · ${manual} manual-needed`},
            {kind: 'people', state: 'unavailable', icon: Users, title: 'People', detail: 'Not available yet'},
            {kind: 'history', state: 'information', icon: History, title: 'History', detail: 'Versions, decisions & comparisons'},
            {kind: 'package', state: 'information', icon: ShieldCheck, title: 'Packet evidence', detail: 'Integrity & company evidence'},
          ].map(row => <button key={row.kind} data-state={row.state} className={`phone-package-row ${row.kind === 'screening' && manual ? 'needs-attention' : ''}`} aria-haspopup="dialog" onClick={() => open(row.kind)}><span className="package-icon"><row.icon size={20}/></span><span><strong>{row.title}</strong><span>{row.detail}</span></span><ChevronRight size={17}/></button>)}
        </section>
        <section className={`integrity-strip ${packet.integrity === 'failed' || packet.current_authorization === 'evidence_changed' ? 'attention' : ''}`} aria-label="Authorization and integrity">{packet.integrity === 'failed' ? <ShieldAlert size={22}/> : <ShieldCheck size={22}/>}<div><strong>{authorizationLabel[packet.current_authorization]}</strong><p>Integrity {packet.integrity.replaceAll('_', ' ')} · Cover accepted: {packet.cover_letter_acceptance}</p></div></section>
        <nav className="phone-progression" aria-label="Loaded review navigation"><button className="quiet outlined" aria-label="Previous loaded job" disabled={position <= 0} onClick={() => navigate(position - 1)}><ChevronLeft size={16}/>Previous job</button><button className="quiet outlined" aria-label="Next loaded job at end" disabled={position < 0 || position + 1 >= total} onClick={() => navigate(position + 1)}>Next job<ChevronRight size={16}/></button></nav>
      </div>
      <footer className="decision-handoff phone-handoff"><div tabIndex={0} aria-label="Current packet context" title={`Packet ${packet.packet_id} · Version ${packet.version} · ${packet.company}`}><strong>Reviewing packet v{packet.version} · exact version only</strong><span className="sr-only"><CompanyName company={packet.company} packetId={packet.packet_id}/> · Packet {packet.packet_id}</span></div><a className="button primary" href="/">Open trusted decision UI<ArrowUpRight size={17}/></a></footer>
    </div>
    {sheet && <MobileSheet title={titles[sheet]} kind={sheet} subtitle={sheet === 'cover' && cover ? `${wordCount(packet.cover_text!)} words · Packet v${packet.version}` : `Packet v${packet.version} · ${companyPresentation(packet.company, packet.packet_id).name}`} onClose={() => setSheet(null)}>
      {sheet === 'why' ? <section className="phone-why-detail"><p className="muted">Detailed score breakdown not available yet.</p><div className="strengths"><h3 className="eyebrow">Fit reasons</h3><EvidenceList items={packet.reasons} empty="Match reasons unavailable."/></div><div><h3 className="eyebrow">Matched requirements</h3><EvidenceList items={packet.matched_requirements} empty="No matched requirements provided."/></div><div className="gaps"><h3 className="eyebrow">Listed gaps</h3><EvidenceList items={packet.missing_requirements} empty="No missing requirements provided."/></div><p className="score-note">Job fit is not an interview prediction.</p></section>
        : sheet === 'cover' && cover ? <article className="reader-paper phone-letter-paper"><p className="paper-label">COVER LETTER · PACKET V{packet.version}</p><p className="phone-letter-company"><CompanyName company={packet.company} packetId={packet.packet_id}/> · {packet.title}<span className="sr-only"> · Packet {packet.packet_id}</span></p><div className="exact-text reader-text cover-text">{packet.cover_text}</div></article>
        : <PacketEvidence packet={packet} reader={reader} onSelect={select} setTab={open} onReaderOpen={() => setSheet('cover')} active={sheet}/>}
    </MobileSheet>}
  </article>;
}

export function PhoneWorkspace({state, reader, synthetic}: {state: WorkspaceState; reader: Reader; synthetic: boolean}) {
  const {section, queue, queueError, selected, packet, packetError, offset, selectedButton, reload, select, back, changeSection, paginate} = state;
  const caughtUp = section === 'needs-review' && offset === 0 && queue?.items.length === 0 && !queueError;
  return <div className="app phone-app" data-theme="dark"><Head><title>Job Pilot | Application review</title><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/></Head><a className="skip-link" href="#main">Skip to approval queue</a>{synthetic && <div className="demo-banner">Synthetic demo · Fictional packets only · No decision actions</div>}
    <main id="main" tabIndex={-1} aria-busy={Boolean(selected && !packet && !packetError)}>
      {selected ? packet ? <PhoneReview key={packet.packet_id} packet={packet} reader={reader} state={state}/> : <section className="phone-state phone-packet-state"><button className="quiet" aria-label="Back to queue" onClick={back}><ChevronLeft size={18}/>Queue</button><FileSearch size={38}/><h1>{packetError ? 'Evidence unavailable' : 'Opening your packet'}</h1><p role={packetError ? 'alert' : 'status'}>{packetError || 'Loading packet evidence.'}</p>{packetError && <button className="button primary" onClick={reload}>Retry packet</button>}</section>
        : <div className="phone-home"><header className="phone-home-header"><div><p className="phone-context">Application review</p>{!caughtUp && <h1>Ready for you</h1>}</div><button className="icon-button phone-reload" aria-label="Reload evidence" onClick={reload}><RefreshCw size={20}/></button></header>
          {caughtUp ? <section className="phone-state phone-caught-up"><div className="caught-up-symbol"><Check size={56}/></div><h1>You’re all caught up</h1><p>No packets currently need review.</p><button className="button primary" onClick={reload}><RefreshCw size={16}/>Reload queue</button><button className="quiet" onClick={() => changeSection('history')}>View packet history</button></section> : <>
            <section className="phone-loaded" aria-label="Loaded queue context"><div><strong>{queue ? `${queue.items.length} packets loaded` : 'Awaiting your queue'}</strong><span>Page {Math.floor(offset / 25) + 1}</span></div><div className="phone-loaded-track" aria-hidden="true">{queue?.items.map(item => <span key={item.packet_id}/>)}</div><div className="phone-loaded-section"><select aria-label="Queue section" value={section} onChange={event => changeSection(event.target.value)}>{Object.entries(sections).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>{queue?.items.length ? `${offset + 1} to ${offset + queue.items.length}` : 'Current page'}</span></div></section>
            <section className="phone-queue-content" aria-label={sections[section]}>
              <p className="phone-queue-status" role={queueError ? 'alert' : 'status'}>{queueError || (!queue ? 'Loading protected queue.' : !queue.items.length ? 'No packets on this page.' : '')}</p>{queueError && <button className="quiet" onClick={reload}>Retry queue</button>}
              <ol className="phone-queue-list">{queue?.items.map(item => <li key={item.packet_id}><button className={`queue-row phone-queue-card theme-${companyPresentation(item.company, item.packet_id).theme}`} data-packet-id={item.packet_id} ref={node => { if (node && selectedButton.current?.getAttribute('data-packet-id') === item.packet_id) selectedButton.current = node; }} aria-label={`${item.company} ${item.title}`} onClick={event => {selectedButton.current = event.currentTarget; select(item.packet_id);}}><span className="phone-card-main"><CompanyMark company={item.company} packetId={item.packet_id}/><span className="phone-card-copy"><span className="row-company"><CompanyName company={item.company} packetId={item.packet_id}/></span><span className="row-title">{item.title}</span></span><span className="row-score"><strong>{item.score}</strong><span>FIT</span></span></span><span className="phone-card-detail"><span className="row-location"><MapPin size={12}/>{item.location ?? 'Location unavailable'}</span><span className={`phone-card-status ${item.manual_needed_count ? 'attention' : ''}`} data-status={item.status}><span aria-hidden="true"/>{item.manual_needed_count ? `${item.manual_needed_count} manual-needed · ${statusLabel[item.status]}` : statusLabel[item.status]}</span><span className="phone-card-note">Packet v{item.version} · Cover accepted: {item.cover_letter_acceptance}</span>{item.decision && <span className="phone-card-note">{decisionLabel(item.decision)}</span>}{item.revision_state && <span className="phone-card-note">Revision: {item.revision_state.replaceAll('_', ' ')}</span>}</span></button></li>)}</ol>
              <div className="pagination"><button className="quiet" aria-label="Previous queue page" disabled={!queue || offset === 0} onClick={() => paginate(Math.max(0, offset - 25))}><ChevronLeft size={16}/>Previous</button><span className="pagination-label">Page {Math.floor(offset / 25) + 1}</span><button className="quiet" aria-label="Next queue page" disabled={!queue || queue.items.length < 25 || offset + 25 > 1_000_000} onClick={() => paginate(offset + 25)}>Next<ChevronRight size={16}/></button></div>
            </section>
          </>}
        </div>}
    </main>{!selected && <PhoneNavigation/>}
  </div>;
}
