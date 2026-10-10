# Deferred Cross-Device Polish

## Status

- This is the authoritative NON-BLOCKING polish backlog for the accepted Run 5B desktop, Run 5B phone, and Run 5C trusted-decision baselines.
- Run 5B desktop baseline is accepted, committed, and pushed at `46e8b2f1c94bc58bd575a77f1b8cb615fa2eddbd`.
- Run 5B phone baseline is accepted, committed, and pushed at `206435bc38aa4276271d1efcc9a35b03b3a82324`.
- Run 5C trusted-decision baseline is visually accepted by Andrew, pending checkpointing.
- The items below are intentionally deferred until later real-data states and workflows make final treatment meaningful.
- These are NON-BLOCKING polish items, NOT Run 5B or Run 5C blockers. The accepted baselines are not the final forever-polished UI.
- This backlog does not authorize fabrication of unsupported data or premature implementation of future workflows.
- No item below was implemented during phone baseline or Run 5C cleanup and staging.

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

- Re-evaluate vertical footprint with the accepted Run 5C decision controls during the later final polish pass.
- Run 5C has replaced the temporary read-only trusted handoff; its current decision presentation is accepted.

### 6. Mobile sparse-state sheets

- Reconsider vertical sizing/composition for sparse truthful states beyond Right People.
- Sheets should not occupy excessive empty space solely because future data is unavailable.

## Run 5C decision experience

These newly accepted polish items are NON-BLOCKING. Current presentation and recovery semantics are accepted. Do not implement these items now.

### 1. Phone recorded-state duplication

The phone Approval Recorded screen currently communicates Approval recorded, No application submitted, and Ready for next step in the main success surface and again in the persistent lower region.

Later evaluate reducing duplicate informational copy. Likely direction:

- The main success surface owns the detailed recorded-state explanation.
- The persistent lower region focuses primarily on the next safe action.

Do not change it now.

### 2. Ambiguous vs conflict visual distinction

AMBIGUOUS and CONFLICT correctly share a conservative stop-and-refresh pattern.

Later evaluate a subtle visual distinction using heading, icon, or semantic status treatment without changing recovery semantics. Do not make either state more aggressive or encourage mutation replay.

### 3. Reject / Revise dialog and sheet height

Re-evaluate desktop dialog and phone sheet vertical rhythm using realistic short feedback, long feedback, long rejection detail, and validation errors.

Current presentation is accepted. Do not shrink controls merely for compactness.

### 4. Post-decision "outside loaded page" treatment

The decided packet may correctly remain visible after the refreshed Needs Review queue no longer contains it.

Later refine wording and visual emphasis so it is unmistakable that this is the just-decided historical packet and it is no longer an active Needs Review item. Do not alter authoritative queue behavior.

### 5. Final decision-dock polish

Re-evaluate desktop and phone decision-region sizing during the final cross-device polish pass after later workflows exist. Do not change Run 5C action semantics.

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
- All items remain NON-BLOCKING.
- No item authorizes unsupported behavior, employer submission, revision generation, automatic decision replay, or broad redesign.
