# Deferred Cross-Device Polish

## Status

- This is the authoritative non-blocking polish backlog for the accepted Run 5B desktop and phone baselines.
- Run 5B desktop baseline is accepted, committed, and pushed at `46e8b2f1c94bc58bd575a77f1b8cb615fa2eddbd`.
- Run 5B phone baseline is visually accepted by Andrew, pending checkpointing.
- The items below are intentionally deferred until later real-data states and Run 5C+ functionality make final treatment meaningful.
- These are polish items, NOT Run 5B blockers. The accepted baselines are not the final forever-polished UI.
- This backlog does not authorize fabrication of unsupported data or premature implementation of future workflows.
- No item below was implemented during phone baseline cleanup and staging.

## Desktop

### 1. Evidence-panel empty-space balance

- Revisit the right evidence panel's vertical balance once truthful contacts, interview analysis, relocation information, deadlines/history, and other genuine data exist.
- Do not fabricate content merely to fill space.

### 2. Queue density

- Stress-test unusually long real company names, job titles, locations, statuses, and badges.
- Preserve the accepted approximate 300px queue composition unless real-data evidence shows a better treatment is needed.

### 3. Chip / badge / icon micro-alignment

- Recheck optical centering across all real states.
- Include DEMO, readiness, manual-attention, location, metadata, tabs, icon containers, and status families.

### 4. Interaction polish

- Final hover/focus treatment.
- Restrained state transitions.
- Reduced-motion equivalents.
- Keyboard interaction polish.
- Completion/state-change motion where genuinely useful.

### 5. Real-data states

Re-evaluate layout/presentation once truthful support exists for:

- contacts
- interview analysis
- relocation assistance
- richer resume analysis
- real decision workflows
- application outcomes

Do not pre-fill or fake these states.

### 6. Typography / spacing

- Perform final optical typography and spacing review using representative real jobs and long content.
- Re-evaluate dense metadata rows and vertical rhythm with real data.

## Phone

### 1. Right People empty state

- Current unavailable-state sheet truthfully contains little content but occupies too much vertical space.
- Later evaluate a content-height, shorter bounded, or otherwise more intentional sparse-state sheet.
- Once real contacts exist, allow the sheet to grow naturally with content.
- Never fabricate contacts simply to fill the screen.

### 2. Scrolled review top edge

- Revisit the slightly abrupt partial-card clipping / transition beneath the sticky phone header in the scrolled review state.
- Preserve useful context while making the scroll transition feel intentional.

### 3. Queue density

- Stress-test realistic long company names, titles, locations, statuses, badges, and multi-line combinations.
- Maintain readability without making the queue unnecessarily sparse.

### 4. Document reader

- Revisit paper padding.
- Paragraph rhythm.
- Long-document scrolling.
- Reader/sheet height.
- Realistic longer cover letters.
- Safe-area behavior during extended reading.

### 5. Trusted decision region

- Re-evaluate vertical footprint when Run 5C introduces real decision controls.
- The current read-only trusted handoff is intentionally temporary.

### 6. Mobile sparse-state sheets

- Reconsider vertical sizing/composition for sparse truthful states beyond Right People.
- Sheets should not occupy excessive empty space solely because future data is unavailable.

## Cross-device

1. Final desktop/phone typography consistency.
2. Final desktop/phone spacing consistency.
3. Shared badge/chip/icon optical alignment.
4. Focus, hover, touch, and keyboard treatment.
5. Reduced-motion behavior.
6. Completion/state-change motion.
7. 200% text and reflow behavior.
8. Long-text stress testing.
9. Real-data stress testing.
10. Empty/loading/error/integrity-state visual consistency.
11. Final review at desktop 1440×900 and phone widths 360px, 390px, 430px, and 480px.
12. Review differences between synthetic fixture states and realistic production states.
13. Perform the final polish pass only after functional states that materially affect these layouts actually exist.

## Guardrails

- Do not interpret this backlog as authorization to invent unsupported data.
- Do not implement Run 5C behavior merely to satisfy a visual item.
- Do not sacrifice current security/data-truth guarantees for visual completeness.
