import { useSyncExternalStore } from 'react';
import { PhoneWorkspace } from './phone-workspace';
import Head from 'next/head';
import { Check, ChevronLeft, ChevronRight, ClipboardCheck, Compass, FileSearch, LayoutGrid, BarChart3, CalendarDays, Users, Send, Settings, RefreshCw, MapPin, CircleDot } from 'lucide-react';
import { api } from '../lib/api';
import { decisionLabel, sections, statusLabel } from '../lib/display';
import { companyPresentation } from '../lib/review-presentation';
import { useReviewWorkspace } from '../lib/use-review-workspace';
import type { Reader } from '../lib/types';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { PacketInspector, CompanyMark, CompanyName } from './packet-inspector';

function subscribePhone(listener: () => void) {
  const media = window.matchMedia('(max-width: 599px)');
  media.addEventListener('change', listener);
  return () => media.removeEventListener('change', listener);
}
const phoneSnapshot = () => window.matchMedia('(max-width: 599px)').matches;
const serverSnapshot = () => false;

function AppRail() {
  return <aside className="app-rail"><a className="pilot-mark" href="/ui" aria-label="Job Pilot"><Send size={23} aria-hidden="true"/></a><nav aria-label="Workspace"><button disabled className="rail-item" aria-label="Overview unavailable" title="Overview: not available yet"><LayoutGrid/></button><button disabled className="rail-item" aria-label="Opportunities unavailable" title="Opportunities: not available yet"><Compass/></button><a className="rail-item nav-current" href="/ui" aria-current="page" aria-label="Applications" title="Applications"><ClipboardCheck/></a><button disabled className="rail-item" aria-label="Contacts unavailable" title="Contacts: not available yet"><Users/></button><button disabled className="rail-item" aria-label="Calendar unavailable" title="Calendar: not available yet"><CalendarDays/></button><button disabled className="rail-item" aria-label="Analytics unavailable" title="Analytics: not available yet"><BarChart3/></button></nav><div className="rail-bottom"><button disabled className="rail-item" aria-label="Settings unavailable" title="Settings: not available yet"><Settings/></button><span className="profile-mark" aria-label="Private workspace"><Check size={18}/></span></div></aside>;
}

export function Workspace({reader = api, synthetic = false}: {reader?: Reader; synthetic?: boolean}) {
  const state = useReviewWorkspace(reader);
  const phone = useSyncExternalStore(subscribePhone, phoneSnapshot, serverSnapshot);
  if (phone) return <PhoneWorkspace state={state} reader={reader} synthetic={synthetic}/>;
  const {section, queue, queueError, selected, packet, packetError, offset, selectedButton, reload, select, back, changeSection, paginate} = state;
  const emptyFirstPage = section === 'needs-review' && offset === 0 && queue?.items.length === 0 && !queueError;
  const position = queue?.items.findIndex(item => item.packet_id === selected) ?? -1;
  return <div className="app" data-theme="dark">
    <Head><title>Job Pilot | Application review</title><meta name="viewport" content="width=device-width, initial-scale=1"/></Head>
    <a className="skip-link" href="#main">Skip to approval queue</a>
    {synthetic && <div className="demo-banner">Synthetic demo · Fictional packets only · No decision actions</div>}
    <AppRail/>
    <section className={`queue-pane ${selected ? 'queue-with-selection' : ''}`} aria-label="Approval queue sections">
      <header className="queue-top"><div><p className="eyebrow">Application review</p><h1>Ready for you</h1></div><button className="icon-button" aria-label="Reload evidence" title="Reload evidence" onClick={reload}><RefreshCw size={17} aria-hidden="true"/></button></header>
      <Tabs className="queue-tabs" value={section} onValueChange={changeSection} activationMode="manual"><TabsList aria-label="Queue section">{Object.entries(sections).map(([value, label]) => <TabsTrigger key={value} value={value}>{label}</TabsTrigger>)}</TabsList>
      {Object.entries(sections).map(([value, label]) => <TabsContent key={value} value={value} className="queue-content"><div className="queue-heading"><h2>{label}</h2><span className="muted">{queue ? `${queue.items.length} loaded` : 'Awaiting data'}</span></div>
        <p className="queue-status" role="status">{queueError || (!queue ? 'Loading protected queue.' : queue.items.length === 0 ? 'No packets on this page.' : `Showing ${offset + 1} to ${offset + queue.items.length}.`)}</p>
        {queueError && <button className="quiet" onClick={reload}>Retry queue</button>}
        {queue && <ol className="queue-list">{queue.items.map(item => <li key={item.packet_id}><button className={`queue-row theme-${companyPresentation(item.company, item.packet_id).theme} ${selected === item.packet_id ? 'selected' : ''}`} aria-label={`${item.company} ${item.title}`} aria-pressed={selected === item.packet_id} aria-current={selected === item.packet_id ? 'true' : undefined} onClick={event => { selectedButton.current = event.currentTarget; select(item.packet_id); }}>
          <span className="queue-card-main"><CompanyMark company={item.company} packetId={item.packet_id}/><span className="queue-copy"><span className="row-company"><CompanyName company={item.company} packetId={item.packet_id}/></span><span className="row-title">{item.title}</span></span><span className="row-score"><strong>{item.score}</strong><span>FIT</span></span></span>
          <span className="queue-card-detail"><span className="row-location"><MapPin size={12} aria-hidden="true"/>{item.location ?? 'Location unavailable'}</span><span className="row-state" data-status={item.status}><CircleDot size={11} aria-hidden="true"/>{statusLabel[item.status]}{item.manual_needed_count > 0 && <span className="manual-badge">{item.manual_needed_count} manual</span>}</span><span className="row-evidence">Packet v{item.version} · Cover accepted: {item.cover_letter_acceptance}</span>{item.decision && <span className="row-decision">{decisionLabel(item.decision)}</span>}{item.revision_state && <span className="row-evidence">Revision: {item.revision_state.replaceAll('_', ' ')}</span>}</span>
        </button></li>)}</ol>}
        <div className="pagination" aria-label="Queue pagination"><button className="quiet" aria-label="Previous queue page" disabled={offset === 0 || !queue} onClick={() => paginate(Math.max(0, offset - 25))}><ChevronLeft size={15} aria-hidden="true"/>Previous</button><span className="pagination-label">Page {Math.floor(offset / 25) + 1}</span><button className="quiet" aria-label="Next queue page" disabled={!queue || queue.items.length < 25 || offset + 25 > 1_000_000} onClick={() => paginate(offset + 25)}>Next<ChevronRight size={15} aria-hidden="true"/></button></div>
      </TabsContent>)}</Tabs>
      <p className="queue-footer"><ClipboardCheck size={14} aria-hidden="true"/>Read-only review · Exact packet versions</p>
    </section>
    <main id="main" className={`detail-pane ${selected ? 'has-selection' : ''}`} tabIndex={-1} aria-busy={Boolean(selected && !packet && !packetError)}>
      {packet ? <PacketInspector key={packet.packet_id} packet={packet} reader={reader} onSelect={select} onBack={back} position={position >= 0 && queue ? `${position + 1} of ${queue.items.length} loaded` : 'Outside loaded page'}/> : <div className="detail-empty">{selected ? <><button className="quiet" onClick={back}><ChevronLeft size={16} aria-hidden="true"/>Back to queue</button><FileSearch aria-hidden="true" size={36}/><h2>{packetError ? 'Evidence unavailable' : 'Opening your packet'}</h2><p role={packetError ? 'alert' : 'status'}>{packetError || 'Loading packet evidence.'}</p>{packetError && <button className="quiet" onClick={reload}>Retry packet</button>}</> : emptyFirstPage ? <><div className="caught-up-symbol"><Check size={56} aria-hidden="true"/></div><p className="eyebrow">Review queue</p><h2>You’re all caught up</h2><p>No packets currently need review.</p><button className="button primary" onClick={reload}><RefreshCw size={16} aria-hidden="true"/>Reload queue</button></> : <><div className="empty-symbol"><FileSearch aria-hidden="true" size={36}/></div><p className="eyebrow">One application at a time</p><h2>Select an application</h2><p>Review the fit and evidence for one exact packet version.</p><a className="quiet" href="/">Open trusted decision UI<ChevronRight size={16} aria-hidden="true"/></a></>}</div>}
    </main>
  </div>;
}
