# Run 5C Trusted Decision Integration

The implementation report below preserves the historical results and Git state
at implementation completion. Andrew has since visually accepted the desktop
and phone trusted-decision baseline, pending checkpointing.

## Cleanup and staging review addendum

Cleanup audits the accepted implementation without changing source or test
behavior, security contracts, or visual presentation. The initial
48 modified/untracked paths are classified as 45 COMMIT, 3 REMOVE BEFORE COMMIT,
0 IGNORE, and 0 NEEDS ANDREW DECISION. The existing deferred-polish backlog is
also updated for staging, making 46 intended staged paths.

The durable evidence set contains 18 PNGs and the three isolated database proofs
plus `verification.json`. These redundant captures are removed:

- `desktop-reject-recorded-1440x900.png`: rejection recorded remains represented
  by the dedicated phone result and isolated Reject database proof.
- `desktop-revise-recorded-1440x900.png`: revision request recorded remains
  represented by the dedicated phone result and isolated Revise database proof.
- `phone-validation-390x844.png`: the same shared-form nonblank-feedback error
  remains represented by desktop validation and focused browser tests.

The original 21-image capture inventory below remains historical. Every other
listed image and all four JSON proofs are retained; `verification.json` keeps
the implementation results and adds the current retention manifest. Bootstrap
unavailable and the phone Reject/Revise results prove distinct supported states.

`docs/run5b/DEFERRED_CROSS_DEVICE_POLISH.md` remains the authoritative NON-BLOCKING
backlog and now includes the five accepted Run 5C polish items. None is implemented
during cleanup. No full or focused implementation suite is rerun for this
documentation/evidence cleanup; the validation counts below are historical
implementation results. Cleanup uses inventory, privacy, evidence-hash, and
staged-diff checks. A read-only production SQLite hash check still matches the
historical byte-identity proof; no decision request is made.

The staged whitespace check found and removed one extra blank line at the end
of `frontend/src/components/ui/mobile-sheet.tsx`. This is the only source cleanup
and changes no component behavior. No source or test behavior changed, so no
implementation tests were rerun.

No commit, push, deployment, production-service restart, production decision,
Run 5D work, integration matrix, or visual refinement is included. Stop for
Andrew's complete staged-diff review.

## Scope and starting checkpoint

Run 5C integrates the existing trusted human Approve / Reject / Revise recording
into `/ui`, preserving the accepted Run 5B desktop and dedicated phone layouts.
It adds a shared decision controller, explicit confirmations, bootstrap/lifecycle
handling, immutable-result presentation, GET reconciliation, and authoritative
queue/history refresh. No dependency or state-management framework was added.

The fail-closed starting checks were recorded before implementation:

```text
git branch --show-current: main
git rev-parse HEAD: 206435bc38aa4276271d1efcc9a35b03b3a82324
git rev-parse origin/main: 206435bc38aa4276271d1efcc9a35b03b3a82324
git status --short: empty
git diff --name-only: empty
git diff --cached --name-only: empty
```

`CLAUDE.md`, `AGENTS.md`, the existing contracts and the deferred Run 5B polish
document were read. Frontend-design-pro guidance was used for the scoped forms,
dock and accessibility review. No delegated agents were used.

## Backend contract freeze

Production decision routes, DTO definitions, persistence, database schema,
immutability, concurrency, security middleware, fingerprint authority, revision
processing and employer submission are unchanged. No tracked production Python,
deployment or extension file changed. The frontend contract generator only adds
the existing BootstrapResponse, TailscaleBootstrapResponse and DecisionResult
schemas to the source-owned snapshot. Python remains the server and authority;
the frontend remains a static Next.js export served under the existing CSP.

Only these consequential requests are implemented:

| Action | Existing endpoint | Exact JSON keys |
| --- | --- | --- |
| Approve | `POST /api/packets/{packet_id}/approve` | `expected_packet_fingerprint`, `expected_approval_view_fingerprint` |
| Reject | `POST /api/packets/{packet_id}/reject` | `expected_packet_fingerprint`, `reason_code`, `detail` |
| Revise | `POST /api/packets/{packet_id}/revise` | `expected_packet_fingerprint`, `feedback` |

All requests use same-origin browser credentials, no-store and redirect rejection.
POSTs use JSON and `X-Job-Pilot-CSRF`. No actor, numeric version, client evidence,
company, title or fit score is sent. No identity, Host, Origin or authentication
header is manufactured by the client.

## Shared architecture and state machine

`decision-client.ts` validates existing response schemas and sanitizes errors.
`decision-controller.ts` owns the token, target snapshots, state machine and one
global in-flight operation. `use-decisions.ts` installs it above the desktop/phone
split and connects lifecycle and synchronous navigation invalidation. Existing
workspace reads are extended with an exact-packet refresh callback and explicit
next-queued navigation. No backend authorization algorithm is duplicated.

| State | Meaning |
| --- | --- |
| BOOTSTRAP_UNAVAILABLE | Mutations disabled; explicit Enable decisions retry |
| READY | Supported bootstrap succeeded; no active mutation |
| CONFIRMING | Frozen packet context and action; editable action-specific fields |
| PENDING | One POST; competing/repeated actions and dialog closing disabled |
| RECORDED | Structured acknowledgement or exact safe reconciliation |
| AMBIGUOUS | Commit status/evidence unknown; safe GET recovery only |
| FAILED | Known rejection or confirmed conflict; explicit recovery |

There is no automatic mutation retry, automatic advancement, Undo, decision edit
or decision deletion. Selection wrappers invalidate confirmations synchronously.
Late reads/results stay keyed to the original packet. A different selected packet
cannot inherit success, target evidence, fields or confirmation state. Refresh
callbacks only replace packet detail when its ID is still selected. Queue reads
have their own generation guard.

The frozen target contains packet ID, displayed version, packet fingerprint,
approval-view fingerprint for Approve, company, title, action and the final
reason/text. IDs remain 32 lowercase hex characters; fingerprints remain 64
lowercase hex characters. Displayed version is presentation context, never a
new request authority. Field editing creates another frozen snapshot without
deriving new packet authority; submission retains that exact snapshot.

## CSRF and private security

Authenticated `GET /api/bootstrap` provides the supported process-owned token.
It lives only in a private controller field. It never enters storage, a cookie,
URL, report, screenshot, log or persisted state. Bootstrap failure disables all
mutations and offers an explicit retry. There is no legacy fallback.

`pagehide` aborts bootstrap, clears the token, drafts and result state, and
invalidates late work. Pending/ambiguous work retains only a minimal in-memory
recovery marker without submitted text. BFCache restoration clears again and
requires a new supported bootstrap. A transmitted request is not represented as
canceled. `csrf_failed` invalidates mutation readiness, preserves the recovery
barrier and requires explicit re-bootstrap and a fresh confirmation; it never
replays the POST. Reload starts with a new bootstrap and authoritative GETs.

Host, explicit-port, Origin, private identity, local-mode, loopback listener,
body bounds, strict DTOs, sanitized responses, no-store and CSP behavior remain
unchanged. Existing security regressions are retained and exercised.

## Action semantics and structured authority

Approve requires the returned exact approval preview and a passed integrity
state. The backend performs final integrity and current-evidence checks. Missing
or mismatching fingerprints cannot be overridden in the frontend. Confirmation
shows company, role, version, and the fact that recording approval submits no
application. Result copy is **Approval recorded** and **No application submitted**.
**Ready for next step** appears only when refreshed structured
`current_authorization` is `currently_valid`. Evidence-changed, integrity-failed
and not-checked states remain distinct. Historical approval is not permanent
current authorization.

Reject retains all six exact existing reason codes and labels:
`not_interested` / Not interested, `bad_fit` / Poor fit,
`company` / Company concern, `location` / Location,
`pay` / Compensation, `other` / Other. A reason is required; detail defaults to
an empty string and remains optional even for Other. Accepted detail is preserved
verbatim and limited to 4,000 Unicode code points. Result: **Rejection recorded**.

Revise requires non-whitespace feedback, using Python-compatible whitespace
semantics and a 4,000-code-point limit. Accepted feedback remains verbatim,
including the backend's existing Unicode/NUL behavior. Result:
**Revision request recorded**; **Revision generation is a separate step.**
Reject and Revise remain available with damaged artifacts when their supported
exact packet fingerprint exists; they are not tied to Approve eligibility.

Free-form DecisionResult.message is not a source of product truth. Results use
the submitted action, HTTP/error class, exact response identity, structured
historical state, decision detail and refreshed packet/current authorization.
Existing queued-revision copy is also normalized to the truthful immediate
request state when no structured successor exists.

## Ambiguous responses and conflicts

Transport loss, unreadable successful responses and uncertain server failures
can follow a commit. They enter AMBIGUOUS, never definite failure, and never
trigger another POST. Safe protected reads request the exact packet (including
history), exact decision detail and the first Needs Review page.

Matching Reject reason/detail or Revise feedback, action, fingerprint, packet
version and decision identity can prove the expected decision was recorded.
Successful exact reads showing no decision permit only explicit refresh and a
new confirmation. Failed or inconclusive reads keep ambiguity visible. Queue
failure cannot produce Next queued job or caught-up.

An approval whose acknowledgement is lost remains conservative: the existing
DecisionDetail read does not expose the original approval-view fingerprint.
Even a matching historical approval cannot prove that exact original evidence.
The UI says an approval exists but its original evidence could not be confirmed,
directs the user to history and does not replay the decision. This supported
unresolved-ambiguity state requires no backend contract change.

A structured decision_conflict remains a conflict even if a subsequent GET
finds the same action. History/queue are refreshed without converting it to
success or advancing. Exact replays retain the original immutable decision;
changed Reject reason/detail or Revise feedback conflict. One global in-flight
guard suppresses double clicks and competing actions.

## Queue, next job and caught-up

After persistence, exact packet/history and authoritative first-page Needs
Review data are refreshed. The result stays bound to the decided packet. Next
queued job is an explicit button derived only from the successful fresh queue
after exclusion of that packet. It never automatically selects another job.
An authoritative successful empty first page is required for caught-up; loading,
failed, later-page or ambiguous results do not qualify. Pending/unresolved
decisions additionally block caught-up presentation.

## Employer and revision boundaries

**APPROVE != EMPLOYER SUBMISSION.** No employer URL is automatically opened.
There is no submission route, apply runner, extension submit, form fill,
application-event writer, application-outcome success state or contact action
in this integration. Real-browser tests restrict POSTs to the three packet
decision paths, forbid external resources/window.open, and install failing
provider/employer/LLM/revision call guards. Database snapshots prove no
application event or application-packet mutation for each direct decision.

Immediate Revise records one immutable human request. It creates no revision
work, successor packet, style memory, LLM call or worker invocation. No worker
or production service was started or inspected for this milestone. A separately
operator-started processor can consume durable requests later; the UI correctly
describes generation as a separate step.

## Desktop, phone and accessibility

The accepted rail, queue, hero, evidence cards, typography, colors and geometry
remain. The temporary decision handoff is replaced by a desktop dock and focused
modal, plus a dedicated phone dock, bottom sheets and recorded-result composition.
Approve is primary, Revise uses attention styling, Reject uses destructive styling
with explicit text. Both presentations share controller semantics and field forms.

The existing source-owned MobileSheet is extracted and extended with select,
textarea, initial field focus, focus containment/return, Escape, visible close,
internal scrolling, CSS scroll lock and safe-area padding. Pending closing is
blocked rather than falsely suggesting cancellation. Buttons/phone controls
are at least 44px; real labels, visible focus, associated errors, live pending/
error statuses, Unicode counters and reduced motion are present.

Actual export/browser checks cover 360, 390, 430, 480 and 1440px widths, long
context, long text, keyboard use, sheet scrolling, validation, pending, recorded,
conflict, ambiguity, bootstrap-unavailable and the accepted baseline reflow tests.
Primary evidence is 390x844 phone and 1440x900 desktop. Screens were inspected;
the decision sheets were corrected to keep an opaque surface and preserve the
accepted palette. Unrelated cross-device polish remains deferred.

## Isolated database and side-effect proof

Every mutation/browser capture uses temporary synthetic SQLite, an isolated
approval app and dynamically allocated loopback ports. These exercise real
production routes, security middleware, CSRF, DTO validation, persistence and
Python static delivery. Production approval service and real packets are never
mutation targets. No personal documents are used for durable evidence.

| Synthetic direct decision | packet_decisions | Exact replay additional rows | packet_revision_work | application_events | application_packets |
| --- | --- | --- | --- | --- | --- |
| Approve | +1 | +0 | +0 | +0 | byte-for-byte equivalent row snapshot |
| Reject | +1 | +0 | +0 | +0 | byte-for-byte equivalent row snapshot |
| Revise | +1 | +0 | +0 | +0 | byte-for-byte equivalent row snapshot |

The three `database-*.json` artifacts also record zero provider/worker/employer
calls. Production SQLite's starting SHA-256 was
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`.
The final verification artifact records the after-validation hash and equality.
No production database contents are included in evidence.

## Newly run validation

Commands below describe this implementation's validation, not historical counts.

1. `PYTHONPATH=src .venv/bin/python frontend/scripts/generate-contracts.py`:
   schema generation passed; production DTO definitions unchanged.
2. From `frontend`, `npm run lint && npm run typecheck && npm test && npm run build`:
   lint and typecheck passed; **66 individual tests passed, 0 failed**;
   static export/packaging passed with **17 approved assets**.
3. From `frontend`, `npm audit --json --cache /tmp/job-pilot-run5c-npm-audit-cache`:
   **0 vulnerabilities**, **253 dependencies**; no dependency/lockfile change.
4. `.venv/bin/pytest -q tests/test_approval_api.py tests/test_approval_security.py tests/test_tailscale_api.py tests/test_tailscale_security.py tests/test_approval_service_unit.py tests/test_approval_queue.py tests/test_approvals.py tests/test_revisions.py tests/test_apply_submit.py tests/test_apply_handoff.py tests/test_database.py`:
   **920 passed, 0 failed**, 272.09 seconds.
5. `.venv/bin/pytest -xq tests/test_frontend_decisions_dom.py tests/test_frontend_phone_dom.py tests/test_frontend_ui_dom.py tests/test_frontend_delivery.py tests/test_frontend_proof.py tests/test_frontend_fonts.py tests/test_frontend_font_dom.py tests/test_approval_ui_dom.py`:
   **177 passed, 0 failed**, 162.94 seconds.
6. `.venv/bin/pytest -q`: **2,950 passed, 0 failed**, 550.03 seconds;
   21 multiprocessing `fork()` deprecation warnings across packet chaos,
   revision and scheduler tests. The complete suite ran after both focused
   suites passed; no source change followed those validations.

Node subprocesses, Chromium/threaded ASGI and npm registry access use the managed
environment's approved outside-sandbox execution. Initial restricted attempts
were retried with the required approval. No package was installed. Intermediate
implementation failures were fixed before the final successful focused runs.
Existing read-only DOM fixtures still prohibit writes; their now-visible mutation
controls are explicitly asserted disabled when bootstrap fails. Their screenshots
go to `/tmp`, preserving accepted Run 5B artifacts. No existing test was removed.

The new controller/client tests cover exact DTOs, authority guards, all reasons,
Unicode code-point boundaries, whitespace/BOM/NUL, stale confirmation, late reads
and mutations, duplicate suppression, bootstrap failure, pagehide, acknowledgement
loss, exact reconciliation, conflict preservation and current authorization.
The 27 new browser cases exercise actual decisions on both presentations,
damaged-artifact recovery, native forms/focus, five widths, delayed POSTs,
two-tab conflicts, BFCache/reload, explicit next job and authoritative caught-up.
Existing API/security tests supply the real endpoint checks for missing/invalid
fingerprints, stale evidence, replay/concurrency, malformed JSON/extra fields,
Origin/Host/identity/CSRF independence, restart tokens, content type/body bounds,
private logging and the frozen persistence/revision/submission boundaries.

## Implementation visual captures (historical inventory)

All files below were captured in `docs/run5c/decision-implementation-evidence/`
from the actual exported UI, synthetic database and protected Python server.
`docs/design/` is unchanged.

Desktop 1440x900:

- `desktop-decision-dock-1440x900.png`
- `desktop-approve-confirmation-1440x900.png`
- `desktop-reject-confirmation-1440x900.png`
- `desktop-revise-confirmation-1440x900.png`
- `desktop-approval-recorded-1440x900.png`
- `desktop-reject-recorded-1440x900.png`
- `desktop-revise-recorded-1440x900.png`
- `desktop-validation-1440x900.png`
- `desktop-bootstrap-unavailable-1440x900.png`

Phone 390x844:

- `phone-decision-dock-390x844.png`
- `phone-approve-confirmation-390x844.png`
- `phone-reject-confirmation-390x844.png`
- `phone-revise-confirmation-390x844.png`
- `phone-approval-recorded-390x844.png`
- `phone-reject-recorded-390x844.png`
- `phone-revise-recorded-390x844.png`
- `phone-validation-390x844.png`
- `phone-ambiguous-390x844.png`
- `phone-conflict-390x844.png`
- `phone-next-queued-job-390x844.png`
- `phone-caught-up-390x844.png`

The approval-recorded screenshot includes the explicit Next queued job offer;
the next-job screenshot shows the second synthetic packet after that button was
clicked. Caught-up follows a real decision and successful empty first-page GET.
The final verification artifact lists image hashes/dimensions and inspection.

## Changed files and final review

Frontend implementation:

- `frontend/scripts/generate-contracts.py`
- `frontend/src/components/decision-controls.tsx` (new)
- `frontend/src/components/ui/mobile-sheet.tsx` (new, extracted/extended source-owned pattern)
- `frontend/src/components/packet-inspector.tsx`
- `frontend/src/components/phone-workspace.tsx`
- `frontend/src/components/workspace.tsx`
- `frontend/src/lib/contracts.json`
- `frontend/src/lib/decision-client.ts` (new)
- `frontend/src/lib/decision-controller.ts` (new)
- `frontend/src/lib/display.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/lib/use-decisions.ts` (new)
- `frontend/src/lib/use-review-workspace.ts`
- `frontend/src/pages/_app.tsx`
- `frontend/src/styles/decisions.css` (new)

Tests and test-only synthetic helpers:

- `frontend/scripts/decisions.test.mjs` (new)
- `tests/test_frontend_decisions_dom.py` (new; contains isolated synthetic helpers/instrumentation)
- `tests/test_frontend_delivery.py`
- `tests/test_frontend_font_dom.py`
- `tests/test_frontend_phone_dom.py`
- `tests/test_frontend_ui_dom.py`

Documentation:

- `frontend/README.md`
- `docs/run5c/RUN5C_TRUSTED_DECISION_REPORT.md` (new)

Implementation-completion evidence: the 21 PNGs listed above, new `database-approve.json`,
`database-reject.json`, `database-revise.json`, and `verification.json` in the
scoped evidence directory. No other durable files are intended.

## Final database, privacy and Git audit

Production SQLite's final SHA-256 is
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`,
identical to the before-validation hash. Production bytes remained unchanged.
Privacy: **PASS**. Proposed source, documentation and evidence were inspected for
credentials/tokens, private candidate/documents/application content, database
artifacts, metadata, browser temporary files and generated dependencies/caches.
No such content was found. PNGs contain only IHDR, IDAT and IEND chunks, with no
embedded text metadata. CSRF values and private feedback are absent from durable
artifacts; code mentions schema/header names without exposing token values.

Final branch, HEAD and origin/main remain the starting values. `git diff --check`
passes with no output. `git diff --cached --name-only` is empty. The final short
status (the untracked directory contains the report and scoped evidence above):

```text
 M frontend/README.md
 M frontend/scripts/generate-contracts.py
 M frontend/src/components/packet-inspector.tsx
 M frontend/src/components/phone-workspace.tsx
 M frontend/src/components/workspace.tsx
 M frontend/src/lib/contracts.json
 M frontend/src/lib/display.ts
 M frontend/src/lib/types.ts
 M frontend/src/lib/use-review-workspace.ts
 M frontend/src/pages/_app.tsx
 M tests/test_frontend_delivery.py
 M tests/test_frontend_font_dom.py
 M tests/test_frontend_phone_dom.py
 M tests/test_frontend_ui_dom.py
?? docs/run5c/
?? frontend/scripts/decisions.test.mjs
?? frontend/src/components/decision-controls.tsx
?? frontend/src/components/ui/mobile-sheet.tsx
?? frontend/src/lib/decision-client.ts
?? frontend/src/lib/decision-controller.ts
?? frontend/src/lib/use-decisions.ts
?? frontend/src/styles/decisions.css
?? tests/test_frontend_decisions_dom.py
```

`verification.json` records the expanded 48-file inventory, image hashes and
dimensions, successful checks, unchanged backend paths and database equality.
Review is limited to decision forms, wording, recorded states,
conflict/ambiguity handling and desktop/phone visuals. Generated revisions,
employer submission, Undo/edit/delete, unrelated cross-device polish and Run 5D+
remain deferred. Andrew's review is pending; no checkpoint action is taken.

**NO COMMIT. NO PUSH. NO STAGING. RUN 5D NOT STARTED.**

VERDICT: READY FOR ANDREW RUN 5C VISUAL REVIEW
