import { useEffect, useState, useSyncExternalStore } from 'react';
import { flushSync } from 'react-dom';
import { RevisionController, revisionBinding } from './revision-controller';
import type { Packet, Reader } from './types';
export function useRevisionReview(packet: Packet | null, reader: Reader) {
  const [controller] = useState(() => new RevisionController(reader));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  useEffect(() => {controller.attach(packet);}, [controller, packet]);
  useEffect(() => {
    const clear = () => flushSync(() => controller.dispose());
    const restore = () => controller.attach(packet);
    window.addEventListener('pagehide', clear); window.addEventListener('pageshow', restore);
    return () => {window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore); controller.dispose();};
  }, [controller, packet]);
  // Never render an old selection during the effect handoff.
  const state = snapshot.binding === revisionBinding(packet) ? snapshot : null;
  return {state, refresh: controller.refresh, clear: () => controller.dispose()};
}
export type RevisionReview = ReturnType<typeof useRevisionReview>;
