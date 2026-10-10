import { useEffect, useState, useSyncExternalStore } from 'react';
import { flushSync } from 'react-dom';
import { DecisionController } from './decision-controller';
import { decisionClient } from './decision-client';
import type { useReviewWorkspace } from './use-review-workspace';
import type { Reader } from './types';

export function useDecisions(reader: Reader, workspace: ReturnType<typeof useReviewWorkspace>, synthetic: boolean) {
  const [controller] = useState(() => new DecisionController(reader, decisionClient, workspace.applyDecisionRefresh));
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  useEffect(() => { controller.select(workspace.selected); }, [controller, workspace.selected]);
  useEffect(() => { controller.observe(workspace.packet); }, [controller, workspace.packet]);
  useEffect(() => {
    if (synthetic) return;
    void controller.bootstrap();
    const clear = () => flushSync(() => controller.clear());
    const restore = (event: PageTransitionEvent) => { if (event.persisted) { controller.clear(); void controller.bootstrap(); } };
    window.addEventListener('pagehide', clear); window.addEventListener('pageshow', restore);
    return () => { window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore); controller.clear(); };
  }, [controller, synthetic]);
  // Invalidate the target synchronously with navigation, before React effects
  // or any subsequent click can submit the previous confirmation.
  const navigation = {
    select: (id: string) => { controller.select(id); workspace.select(id); },
    back: () => { controller.select(null); workspace.back(); },
    changeSection: (value: string) => { controller.select(null); workspace.changeSection(value); },
    paginate: (offset: number) => { controller.select(null); workspace.paginate(offset); },
    reload: () => { controller.cancel(); workspace.reload(); },
  };
  const nextQueued = (id: string) => { controller.select(id); workspace.nextQueued(id); };
  return {controller, state, synthetic, navigation, nextQueued};
}
export type Decisions = ReturnType<typeof useDecisions>;
