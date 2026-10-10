import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

// Source-owned dialog. Scroll locking uses a CSS class, never injected styles.
export function MobileSheet({title, subtitle, kind, onClose, children, pending = false, initialField = false}: {title: string; subtitle: string; kind: string; onClose: () => void; children: ReactNode; pending?: boolean; initialField?: boolean}) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const subtitleId = useId();
  useEffect(() => {
    const previous = document.activeElement;
    document.documentElement.classList.add('phone-sheet-open');
    (initialField ? dialog.current?.querySelector<HTMLElement>('select, textarea') : null)?.focus();
    if (!dialog.current?.contains(document.activeElement)) close.current?.focus();
    const contain = (event: FocusEvent) => { if (event.target instanceof Node && !dialog.current?.contains(event.target)) (dialog.current?.querySelector<HTMLElement>('button:not(:disabled), select:not(:disabled), textarea:not(:disabled)') ?? dialog.current)?.focus(); };
    document.addEventListener('focusin', contain);
    return () => {
      document.documentElement.classList.remove('phone-sheet-open');
      document.removeEventListener('focusin', contain);
      if (previous instanceof HTMLElement && previous.isConnected && !previous.closest('[inert]')) previous.focus({preventScroll: true});
    };
  }, [initialField]);
  return <div className="phone-sheet-backdrop" onClick={event => { if (event.target === event.currentTarget) if (!pending) onClose(); }}>
    <div className={`phone-sheet phone-sheet-${kind}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={subtitleId} ref={dialog} tabIndex={-1} onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); if (!pending) onClose(); }
      if (event.key === 'Tab') {
        const nodes = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]');
        if (!nodes?.length) return;
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <div className="phone-sheet-grabber" aria-hidden="true"/>
      <header className="phone-sheet-header"><div><h2 id={titleId}>{title}</h2><p id={subtitleId}>{subtitle}</p></div><button className="icon-button" ref={close} disabled={pending} aria-label="Close sheet" onClick={onClose}><X size={20} aria-hidden="true"/></button></header>
      <div className="phone-sheet-scroll" tabIndex={0} aria-label={`${title} content`}>{children}</div>
    </div>
  </div>;
}
