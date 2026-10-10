import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { packetId } from './api';
import { errorMessage } from './display';
import type { Packet, Queue, Reader, Section } from './types';

// Shared read state, independent of desktop or future phone composition.
export function useReviewWorkspace(reader: Reader) {
  const [section, setSection] = useState<Section>('needs-review');
  const [offsets, setOffsets] = useState<Record<Section, number>>({'needs-review': 0, processing: 0, 'needs-attention': 0, history: 0});
  const [queue, setQueue] = useState<Queue | null>(null);
  const [queueError, setQueueError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [packetError, setPacketError] = useState('');
  const [generation, setGeneration] = useState(0);
  const [queueGeneration, setQueueGeneration] = useState(0);
  const queueRequest = useRef<AbortController | null>(null);
  const packetRequest = useRef<AbortController | null>(null);
  const selectedButton = useRef<HTMLButtonElement | null>(null);
  const current = useRef({selected, section, offset: 0});
  const offset = offsets[section];
  useEffect(() => { current.current = {selected, section, offset}; }, [selected, section, offset]);
  useEffect(() => {
    const controller = new AbortController(); queueRequest.current = controller;
    reader.queue(section, offset, controller.signal).then(result => {
      if (result.section !== section || result.offset !== offset || result.limit !== 25 || result.items.length > 25) throw new Error('unavailable');
      if (!controller.signal.aborted) setQueue(result);
    }).catch(error => { if (!controller.signal.aborted) setQueueError(errorMessage(error)); });
    return () => controller.abort();
  }, [section, offset, generation, queueGeneration, reader]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); packetRequest.current = controller;
    reader.packet(selected, controller.signal).then(result => {
      if (result.packet_id !== selected) throw new Error('unavailable');
      if (!controller.signal.aborted) setPacket(result);
    }).catch(error => { if (!controller.signal.aborted) setPacketError(errorMessage(error)); });
    return () => controller.abort();
  }, [selected, generation, reader]);
  useEffect(() => {
    // Never retain a private read snapshot across pagehide/BFCache restoration.
    const clear = () => { queueRequest.current?.abort(); packetRequest.current?.abort(); flushSync(() => { setQueue(null); setPacket(null); }); };
    const restore = () => { setQueueError(''); setPacketError(''); setGeneration(value => value + 1); };
    window.addEventListener('pagehide', clear); window.addEventListener('pageshow', restore);
    return () => { window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore); };
  }, []);
  function reload() { queueRequest.current?.abort(); packetRequest.current?.abort(); setQueue(null); setPacket(null); setQueueError(''); setPacketError(''); setGeneration(value => value + 1); }
  function select(id: string) {
    current.current.selected = id;
    packetRequest.current?.abort();
    setPacket(null); setPacketError('');
    try { packetId(id); if (selected === id) setGeneration(value => value + 1); setSelected(id); } catch { setSelected(null); setPacketError('Packet reference unavailable.'); }
  }
  function back() { current.current.selected = null; packetRequest.current?.abort(); setSelected(null); setPacket(null); setPacketError(''); requestAnimationFrame(() => selectedButton.current?.focus()); }
  function changeSection(value: string) { current.current = {selected: null, section: value as Section, offset: offsets[value as Section]}; queueRequest.current?.abort(); packetRequest.current?.abort(); setSection(value as Section); setQueue(null); setQueueError(''); setSelected(null); setPacket(null); setPacketError(''); }
  function paginate(next: number) { current.current = {selected: null, section, offset: next}; queueRequest.current?.abort(); packetRequest.current?.abort(); setOffsets({...offsets, [section]: next}); setQueue(null); setQueueError(''); setSelected(null); setPacket(null); }
  function applyDecisionRefresh(packet: Packet, needsReview: Queue | null) {
    if (current.current.selected === packet.packet_id) {
      packetRequest.current?.abort(); setPacket(packet); setPacketError('');
    }
    if (current.current.section === 'needs-review' && current.current.offset === 0) {
      queueRequest.current?.abort(); setQueue(needsReview); setQueueError(needsReview ? '' : 'Queue refresh unavailable. Retry before continuing.');
    } else {
      queueRequest.current?.abort(); setQueue(null); setQueueError(''); setQueueGeneration(value => value + 1);
    }
  }
  function nextQueued(id: string) {
    try { packetId(id); } catch { return; }
    queueRequest.current?.abort(); packetRequest.current?.abort();
    current.current = {selected: id, section: 'needs-review', offset: 0};
    setSection('needs-review'); setOffsets(values => ({...values, 'needs-review': 0}));
    setQueue(null); setQueueError(''); setSelected(id); setPacket(null); setPacketError(''); setQueueGeneration(value => value + 1);
  }
  return {section, queue, queueError, selected, packet, packetError, offset, selectedButton, reload, select, back, changeSection, paginate, applyDecisionRefresh, nextQueued};
}
