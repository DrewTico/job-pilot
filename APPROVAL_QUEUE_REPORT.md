# Run 3 approval queue implementation record

## Milestone A: implemented, validated and approved

Starting HEAD: `c6c7647 feat: add revision style memory and versioned regeneration`.
`git status --short` was empty at the hard start gate. Read CLAUDE.md, README.md
and all five required safety/implementation reports before modifying source.
The inspected interfaces agree with the supplied architecture findings. No
rule, architecture, trusted approval semantics, schema or dependency changed.
No provider, employer-facing action, install, commit or push occurred.

Files changed through Milestone A:

```text
README.md
APPROVAL_QUEUE_REPORT.md
src/job_agent/cli.py
src/job_agent/packet_history.py
src/job_agent/dashboard/approval_app.py
src/job_agent/dashboard/approval_service.py
src/job_agent/dashboard/approval_models.py
src/job_agent/dashboard/approval_security.py
src/job_agent/dashboard/static/approval.html
src/job_agent/dashboard/static/approval.js
src/job_agent/dashboard/static/approval.css
tests/test_approval_queue.py
tests/test_approval_api.py
tests/test_approval_security.py
```

### Web and network architecture

`create_approval_app(settings=..., engine=..., port=8643)` creates an independent
FastAPI app, without mounting the legacy dashboard/extension router. The CLI is
`job-agent approval-queue --data-dir data --port 8643`. Port is bounded to
1..65535 and there is no host argument. Uvicorn uses host `127.0.0.1`,
`proxy_headers=False`, empty forwarded_allow_ips and `access_log=False`.

A pure ASGI boundary checks raw Host before routing or body reads. Exactly one
Host header is required, accepting only `127.0.0.1:<port>` or
`localhost:<port>`; at port 80 those two names may omit the port. Case variants,
trailing dots, wrong ports, userinfo, hostile DNS-rebinding-style names and
malformed values fail with sanitized 400 invalid_host. Actual ASGI server port,
loopback server/client addresses and plain HTTP are checked separately. Remote
peers/broad server endpoints fail closed with 403 local_only. Forwarded headers
are ignored. The CLI bind remains the listener boundary; the ASGI guard cannot
provide operating-system isolation from a deliberately rewritten launcher or
forged scopes. No identity authentication or remote access is claimed.

No CORSMiddleware or extension-origin allowance is installed. OPTIONS receives
no permissive headers. OpenAPI/docs/redoc are disabled. Response policy covers
shell/assets, JSON and errors: no-store, no-cache, nosniff, no-referrer, DENY,
camera/microphone/geolocation/payment/usb disabled. CSP:

```text
default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self';
img-src 'none'; font-src 'none'; object-src 'none'; frame-src 'none';
worker-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none';
```

### Read adapters and DTOs

Implemented routes are GET `/`, `/assets/approval.js`, `/assets/approval.css`,
`/api/queue`, `/api/packets/{packet_id}` and
`/api/packets/{packet_id}/history`. Asset handling is a two-name allowlist,
not an arbitrary directory server. The fixed HTML has no packet contents.
The small smoke shell fetches queue JSON and constructs textContent list items.
No innerHTML, remote resources, browser storage or service worker is used.

Explicit Pydantic v2 models shape queue, packet detail, preview, screening,
facts, artifacts, destination, history, revision summary and errors. Additional
future response DTO definitions carry no routes or mutation capability. ORM
rows/evidence_json, absolute paths, full answer bank, style content, prompt
contents and provider diagnostics are never returned.

Queue supports exactly section/limit/offset. Unknown optional filters are rejected
instead of silently applied. Default limit is 25, maximum 100; offset is bounded
to 0..1,000,000. A single bounded SQL SELECT uses explicit metadata columns and
JSON extraction/counting, without selecting cover, evidence, feedback or saved
answer-bank contents. Needs Review requires exact packet_ready, non-NULL ready_at
and absence of a decision for that packet. Sort is score DESC, ready_at ASC,
packet ID ASC. Versions are never collapsed. Processing includes undecided builds
and active/queued revisions; Needs Attention includes failed/research-incomplete/
recovery packets and blocked/recovery revisions; History includes decided packets.
The latter sections order updated_at DESC, packet ID ASC. Sections can overlap
where a historical decision still has processing/attention work. Every queue
integrity state is not_checked. No card verification/PDF reads occur.

Detail captures a read-only SQLite projection, closes the transaction, invokes
the trusted exact-fingerprint ApprovalService.preview_approval for an eligible
undecided ready packet, then captures/reconciles the projection again. It checks
exact identity/version/fingerprint, displayed URL, packet bindings, stored fact
order/content, screening, decision/revision metadata and domain-derived history.
It never silently substitutes a packet or synthesizes the view token. A changed
projection fails with stale_packet. No DB transaction spans the domain build lock.
The lock probe is nonblocking and returns packet_busy for observed contention;
releasing it does not prevent a subsequent race, and domain locking remains
authoritative. There is no new cancellation or recovery behavior.

Historical approved detail independently calls validate_approval_for_packet.
Historical Approve remains visible when current evidence changed or integrity
fails; it is never updated or deleted. Current validity is only a checked snapshot,
not perpetual authority. URLs are reviewed data, with no navigation in this shell.
Exactly stored packet-bound facts are displayed in order. Source/destination
strings reuse the existing local application-URL policy without DNS/fetching.
Unsafe URLs are withheld. Required screening answers/manual-needed questions
are projected from their exact packet structure; `saved` is excluded.

The only packet_history.py change exposes authenticated_cover_text as a narrow
public wrapper around the existing historical cover checkpoint authenticator.
It preserves exact stored text, requires historical completion, returns safe
available/unavailable/integrity_failed state, never reconstructs/regenerates,
and asserts no current truth/approval. Version history comes entirely from
list_packet_versions and is reshaped to safe metadata. No new lineage algorithm.

### Storage, privacy and errors

Production startup opens an existing SQLite file in mode=rw, verifies user_version
9 and enables foreign keys. It does not create a DB/directory, migrate, import
legacy state or create tables. Schema remains v9. Direct read tests compare
unchanged DB bytes, sqlite_master definitions, user_version and artifact bytes.
No changes to database.py, packets.py, approvals.py, packet_verify.py, revisions.py,
llm.py or tavily_research.py.

Trusted private_packet_logs wraps reads/domain operations. FastAPI validation
errors return only invalid_request, without rejected values. Explicit mappings
include stale_packet_fingerprint -> stale_packet,
packet_decision_conflict -> decision_conflict and
approval_evidence_changed -> approval_not_current. Storage/lock failures become
503 storage_unavailable; unexpected errors become 500 internal_error. Host and
all error responses carry the security policy. No private repr/traceback is
logged by the adapter. Access logging is disabled in the CLI.

### Validation so far

- New pure ASGI boundary + queue tests: **52 passed**, 1.13 seconds.
- New direct adapter/coherence/CLI/factory/full-app Host tests: **14 passed**,
  21 deselected, 8.69 seconds. Includes outbound traps on HTTP, socket/DNS,
  Anthropic construction, Tavily construction/research and packet building.
- Existing history/CLI-default/scheduler/database regression: **110 passed**,
  33.06 seconds.
- Unique new cases passed in the sandbox: **66**. New cases collected: **87**.
- After Andrew approved the exact TEST-ONLY command below, all **87 new tests
  passed outside the sandbox in 18.29 seconds**, including the 21 previously
  pending FastAPI route cases. Warnings/skips/xfails: **0/0/0**.
- Unique milestone coverage passed: **197 cases** (87 new + 110 existing).
  Repeated executions are not added to that total.
- Warnings/skips/xfails in completed runs: **0/0/0**.
- `git diff --check`: passed. Final status is the fourteen modified/untracked
  files listed above; starting HEAD remains unchanged. No commit or push.

The initial combined run was interrupted after boundary/queue progress when
the first FastAPI route hung at the established sandbox thread-wakeup limitation.
It is not counted as a successful run. The ASGI test helper now has a finite
timeout. Andrew explicitly approved the following exact TEST-ONLY command,
which was then executed successfully outside the sandbox:

```sh
.venv/bin/pytest -q tests/test_approval_security.py tests/test_approval_queue.py tests/test_approval_api.py
```

No edits, installs or live services are bundled into that command. API fixtures
use synthetic local packets and trapped outbound/provider seams. This is not
actual Uvicorn/Chromium integration validation. The existing ten-file browser/
FastAPI split and new real loopback browser fixture remain final Run 3 work.
Full regression/offline totals and responsive browser results are not yet claimed.

### Review gates and remaining work

Milestone A implementation and FastAPI route validation were completed, then
Andrew explicitly approved Milestone A and authorized Milestone B. The original
stop-before-B gate was honored under CLAUDE.md:
“Stop after every milestone for Andrew's review.”

CSRF/bootstrap and mutations belong to B. Complete responsive/accessibility UI,
PDF byte serving, decision-detail/diff/destination/status routes and polling belong
to C. The separate durable revisions-only scheduler belongs to D. Security/browser
red-team and complete split/regression validation belong to E. No mutation route,
FastAPI BackgroundTasks, provider generation, revision worker, automatic link
opening or submission is implemented in this milestone. No false complete-Run-3
claim is made. Full requested YES/NO audit follows the completed milestones.

The trusted local host, DB, candidate inputs and cooperating Linux locks remain
required. Equally privileged coherent local writers are outside those guarantees.
Historical views remain informational. No universal security/truth claim is made.
Run 4 defers identity authentication, Tailscale and multi-device/remote access.
Gmail/Calendar/LinkedIn automation, research refresh and automated employer
submission remain outside Run 3.

## Milestone B: implemented and validated, awaiting milestone review

Andrew explicitly approved Milestone A and instructed continuation to B only,
with a stop at the next review. CLAUDE.md was reread before changes. No trusted
domain file, schema, dependency, packet identity or approval semantics changed.
No live provider, employer, worker, commit or push was used.

Additional B edits are limited to the four new approval production modules,
tests/test_approval_api.py, tests/test_approval_security.py, README.md and this
report. The current cumulative fourteen-file workspace list above still applies.
The approved A changes in cli.py, packet_history.py, approval assets and queue
tests remain intact. A test formerly asserting absence of mutation/bootstrap
routes now checks the B behavior: unauthenticated POST fails with csrf_failed,
GET cannot make a decision, and the future revision-status route remains absent.
No prior safety assertion was removed.

### Synchronizer token, Origin and body boundary

ProcessCSRF uses secrets.token_urlsafe(32), providing 32 random bytes, at app
construction/startup. The server instance's token remains in memory only. It is
not persisted in DB/files/cookies or placed in URLs/browser storage/logs. Tabs
share that instance's token. A fresh app/server instance generates a new token;
old tokens fail. Bootstrap is an async local-only GET returning only the token,
local_only and the already validated local origin. Bootstrap does not read/write
the DB or call providers. Security headers and no CORS apply normally.

Raw Host and loopback validation precede CSRF. Every unsafe HTTP method requires
exactly one Origin and one X-Job-Pilot-CSRF header. Origin must be exactly the
HTTP origin of the accepted Host at the configured port. The localhost and
127.0.0.1 names cannot be interchanged within a request. Port 80 explicitly
supports omitted-port browser serialization for the same accepted name. Missing,
null, foreign, malformed or mismatched origins and missing/bad/duplicate tokens
fail with sanitized 403 csrf_failed before reading a private body. Token bytes
use hmac.compare_digest. Forwarded headers never substitute Host/Origin.

Mutations require application/json (optionally UTF-8 charset) and identity/no
content encoding. Declared and actual/streamed body size are limited to 65,536
bytes before FastAPI can buffer/parse them. The bound accommodates JSON-escaped
4000-astral-codepoint feedback without weakening the 4000-character domain limit.
Invalid/duplicate/mismatched content lengths are rejected. Oversize returns
413 invalid_request; incompatible body headers return 422 invalid_request.
No rejected values are echoed. FastAPI remains the JSON and DTO parser.

### Exact domain mutation adapter

New routes:

```text
GET  /api/bootstrap
POST /api/packets/{packet_id}/approve
POST /api/packets/{packet_id}/reject
POST /api/packets/{packet_id}/revise
```

ApproveRequest requires both opaque 64-hex expected fingerprints. RejectRequest
requires the packet fingerprint, exactly one of not_interested/bad_fit/company/
location/pay/other, and optional exact detail <=4000 characters. ReviseRequest
requires the packet fingerprint and exact feedback <=4000 characters; the trusted
service enforces nonblank feedback. Strings are strict and are not normalized,
rewritten, trimmed or summarized. All request DTOs forbid extra fields, including
body packet_id, evidence_json, feedback on Approve or provider/action settings.

The web adapter probes existing build-lock availability, then calls exactly
ApprovalService.approve/reject/revise with the supplied expectations and values.
It never calls preview_approval during a POST, never substitutes a fresh view
token, creates no evidence, and inserts no decision itself. The existing domain
build lock, BEGIN IMMEDIATE and unique packet decision remain authoritative.
Known contention before a decision returns 503 packet_busy; the probe does not
claim to eliminate later races. Domain replay and conflicts are unchanged.

Safe DecisionResult returns decision/packet/version/type/time, historical state,
current authorization, and a timestamp only when current validation succeeded.
After Approve, validate_approval_for_packet is called separately before asserting
currently_valid. Historical replay can return evidence_changed/integrity_failed.
If a post-commit check observes busy, it returns historical approval with current
authorization not_checked, never optimistic current validity. Committed decisions
are not deleted if checking/storage or response delivery subsequently fails;
the exact domain replay handles a dropped response. The current checked snapshot
is not permanent authorization or a license to skip later destination validation.

Reject stores the domain reason/detail without altering packets or filters.
Revise only commits its durable decision: no work row, style write, successor,
provider generation, in-memory background work or FastAPI BackgroundTasks. The
response includes /api/packets/<id>/revision-status and the exact safe message:
“Creates a new packet version. The new version needs its own approval.” The
status route/UI polling and separately running worker remain C/D work.

Errors reuse A's explicit mappings, including stale_packet_fingerprint,
packet_decision_conflict and approval_evidence_changed. Missing/malformed/extra
request fields return sanitized invalid_request; GET on a decision route is 405.
Historical evidence_json and private feedback/detail are absent from mutation
responses. Unexpected/SQL errors and logs remain sanitized; private_packet_logs
wraps domain calls and metadata shaping. Access logging remains disabled.

### Validation and current gate

- Current security + queue sandbox selection: **82 passed**, 0.74 seconds.
- Current direct adapter/boundary/bootstrap selection: **40 passed**,
  **66 deselected**, 20.06 seconds.
- Existing complete approval-core regression: **205 passed**, 111.49 seconds.
- Current unique new Run 3 cases passed in sandbox: **122**. Collected cumulative
  Run 3 cases: **188**.
- After Andrew approved the exact TEST-ONLY command below, the complete current
  Run 3 selection passed **188 tests in 51.09 seconds outside the sandbox**,
  including all 66 previously pending FastAPI route cases.
- Unique current Run 3 plus approval-core regression coverage: **393 cases**
  (188 + 205). Repeated sandbox executions are not added to this total.
- Warnings/skips/xfails in completed final selections: **0/0/0**.
- Python compilation and git diff --check: passed.

Direct tests prove exact input forwarding, no substituted expectations,
4000-codepoint/NUL preservation, restarted-adapter idempotency, no HTTP revision
generation, unchanged bootstrap DB bytes, post-commit evidence-change detection,
and busy checks that never assert current validity. Passed HTTP cases cover
all mutation boundary failures, missing/extra/invalid private fields, stale packet
and view tokens, exact replay/changed conflicts, two tabs, concurrent duplicate
actions/Approve-vs-Reject/Approve-vs-Revise, packet artifact failure, current
authorization after replay, dropped Revise response/API restart, invalid JSON,
maximum Unicode feedback, privacy/logging, and schema v9 preservation.
All approval API fixtures trap socket/DNS, HTTP send, Anthropic construction,
Tavily construction/research, packet building and RevisionProcessor processing.
No new HTTP action can contact employers or providers.

The B FastAPI selection stopped at the explicit test-only approval gate before
execution, as required by Run 3. Andrew approved the following exact command,
which then completed successfully and validated the new B mutation implementation:

```sh
.venv/bin/pytest -q tests/test_approval_security.py tests/test_approval_queue.py tests/test_approval_api.py
```

No edits/installs/live services were bundled into that command. Milestone B is
implemented and validated. Work stops for Andrew's Milestone B review before C
under CLAUDE.md: “Stop after every milestone for Andrew's review.”
Actual Uvicorn/Chromium/responsive
integration, worker lifecycle and full Run 3 regression/split totals remain
later milestones. The full Run 3 final audit is not yet claimed.


## Milestone C implementation and test gate

Andrew explicitly approved Milestone B and authorized C. No worker or scheduler
changes are included in C. Schema remains v9; no dependencies were added and no
trusted approval, revision, verifier, packet or database module was modified.

C changes the approval app/service and three fixed assets, extends API tests,
adds tests/test_approval_ui_dom.py, updates README and this report, and narrowly
refactors packet_history.py's existing historical artifact reader. The reader
now returns captured authenticated bytes for reuse by the PDF route; resume
diff still reads the authenticated face through the same checks. Pinned
no-follow directory descriptors, regular-file/single-link checks, exact manifest
names, sizes and SHA-256, bounded reads, and existing PDF/DOCX/face consistency
validation are preserved. No arbitrary path, FileResponse reopen or Range
support is introduced. Only the fixed resume.pdf route is exposed.

New GET routes provide revision status, separate decision detail, application
destination, resume/cover diffs and the fixed authenticated PDF. Status reads
only durable local metadata and remains available during a build lock. Labels
cover queued, pending, style_prepared, style_persisted, building, succeeded,
blocked and recovery_required. Failure categories are allowlisted; feedback is
returned only by the separate decision-detail route. Diffs use existing domain
helpers; no OCR, LLM or reconstruction is introduced. All new route responses
retain the local boundary, no-store and security headers. A failed integrity
preview returns coherent detail without an Approve token; exact Reject/Revise
identity remains available through the trusted services. Invalid preview
content cannot supply a review destination or authorize a packet.

The plain JavaScript UI implements all four queue sections, exact-version
navigation, cover paragraphs, screening/manual-needed warnings, ordered bound
facts, history/diffs and explicit local PDF navigation. Untrusted values use
textContent and safe element construction. Source links independently require
HTTP(S) URLs without credentials; all external links use noopener noreferrer.
No remote assets, HTML/Markdown execution, inline scripts/styles, storage or
service worker are used. Tokens stay in memory, pageshow invalidates authority
and refetches, and stale decisions refresh without automatically retrying POST.

Inline decision confirmations identify company, role and version. Reject has
required reason and field-linked errors. Revise preserves exact feedback with a
4000-codepoint counter and explains independent successor approval. Decisions
wait for server confirmation. Revision polling runs every five seconds only
while nonterminal, stops on terminal states/navigation, and never claims an ETA.
Application navigation requires separate current validation and repeats that
validation on explicit click. No employer fetch, redirect or automatic browser
navigation exists. Validation is a point-in-time snapshot, not permanent
permission; changes after a successful check remain a trust boundary.

CSS uses a desktop queue rail and bounded prose, then a single-column phone
layout with Back to queue. Controls have 44px minimum height, long strings wrap,
cover text preserves newlines and diffs scroll inside their own container.
Semantic headings, labels, visible focus, keyboard-operable inline panels,
field errors, polite status announcements and reduced-motion rules are present.
Actual desktop/phone and keyboard browser results are still pending below.

A narrow test-only Uvicorn fixture binds 127.0.0.1 with the OS-assigned test port
passed to both app policy and Uvicorn. Proxy headers and access logging are off.
Browser contexts fail attempted non-local resources; source/employer navigation
is intercepted rather than performed. Provider, HTTP-client, packet-build and
revision-processing traps are installed after offline packet fixture setup.
The server never starts the separate revision worker.

Validation completed in the sandbox:

- Existing packet history plus current security/queue: **152 passed**, 34.12s.
- Current direct adapter/boundary/bootstrap and static UI checks: **60 passed**,
  **80 deselected**, 27.97s.
- Unique current Run 3 sandbox cases: **142**; existing history regression: **70**.
- Full current Run 3 collection: **222 cases**, including **12 Chromium cases**.
- Completed selections: **0 warnings, 0 skips, 0 xfails**.
- Python compilation and git diff --check passed.

An initial status test illegally skipped pending -> style_prepared before
style_persisted; the existing database guard correctly rejected it. The fixture
now follows the durable transitions. No production guard was altered.

STOP before outside-sandbox Uvicorn/Chromium execution, per the explicit Run 3
instruction. The exact pending TEST-ONLY command is:

```sh
.venv/bin/pytest -q tests/test_approval_security.py tests/test_approval_queue.py tests/test_approval_api.py tests/test_approval_ui_dom.py
```

No edits, installations, provider or employer activity are bundled into this
command. Actual browser responsiveness, PDF new-tab behavior, DOM flows and the
complete current FastAPI selection are not yet claimed as passing. After this
approved validation, stop for Andrew's Milestone C review under CLAUDE.md:
“Stop after every milestone for Andrew's review.” Milestone D worker lifecycle,
E red team, complete regression/split totals and final Run 3 audit remain deferred.


### Milestone C approved test execution and review stop

Andrew approved the exact outside-sandbox TEST-ONLY command above. Its final
execution passed **222 tests in 77.27 seconds**, including **12 actual Chromium
cases** and all current FastAPI/security/queue/API cases. There were **0 warnings,
0 skips and 0 xfails**. The 70 existing historical-reader regression cases had
already passed in the sandbox. Unique current Run 3 plus that affected history
regression coverage is **292 cases**; repeated runs are not added to this total.
The previous B approval-core regression remains 205 passed, but full current
Run 3 regression and established offline/browser split totals await E.

Browser validation passed at **1440 x 900** and **390 x 844**, including no page
horizontal overflow, bounded diff scrolling, 44px confirmation controls,
confirmation focus/cancel restoration, safe XSS text rendering, unsafe URL
rejection, exact Unicode feedback and reject reasons, exact Approve tokens,
stale-view refresh without POST retry, pageshow invalidation, terminal polling
stop, and failed-preview Approve disabling. A PDF opened in an explicit local
new tab; its endpoint returned the exact authenticated bytes and PDF MIME type.
The application click rechecked current validity, disabled the changed
destination and performed no external navigation. All browser resource requests
were confined to the assigned local origin; provider/employer traps passed.

Initial browser runs exposed two test-harness defects, not domain changes:
headless Chromium's PDF viewer commits without a normal load event, so the PDF
test now waits for commit; and Playwright automatically invoked a function
returned by the navigation-spy setup expression, so setup now uses a function
block returning no function. The application test waits for the completed
validation response and asserts an empty navigation-call list. Intermediate
runs were 220 passed / 2 failed and 221 passed / 1 failed; the final full run above
passed. No production safety rule was weakened to accommodate these failures.

Final git diff --check passed. The working tree contains the intended uncommitted
Run 3 changes; no commit, push, dependency installation, live provider test,
employer request or scheduler worker start occurred. Milestone C is implemented
and validated. STOP for Andrew's review under CLAUDE.md, before Milestone D.


## Milestone D: separate durable revision worker

Andrew approved Milestone C and explicitly authorized D. D changes only
src/job_agent/scheduler.py, src/job_agent/cli.py, tests/test_scheduler.py,
README.md and this report. Trusted domain modules are unchanged. Schema remains
v9; no dependency, new durable DB state, migration or import was added.

The CLI is `job-agent scheduler --revisions-only --data-dir <dir>`.
`--revisions-only` is mutually exclusive with the existing `--once` modes.
The normal scheduler's schedules, service construction and defaults remain
unchanged. Revision mode does not load a scoring profile or construct discovery,
batch or maintenance services. README documents separate approval-server and
worker terminals/processes. Starting the approval server never starts a worker.

The worker reuses the approval adapter's existing-v9 engine opener without
creating a FastAPI app/server. It refuses absent/wrong-version storage without
creating or migrating a job database. Its revision_scheduler.lock uses the
existing nonblocking flock convention, is never unlinked, and permits only one
worker per data directory. The normal scheduler retains scheduler.lock so both
modes can coexist. The trusted global packet build lock remains authoritative
for simultaneous packet/revision operations.

At startup the worker immediately scans once, then APScheduler registers only
one revision interval job: 10 seconds, max_instances=1, coalesce=True and bounded
misfire handling. SIGTERM restores signal state and releases resources; a signal
during the initial scan prevents subsequent scheduler start. Domain processing
is allowed to finish safely; no new cancellation semantics were introduced.

Discovery selects only committed Revise decisions with no work row or work in
pending, style_prepared, style_persisted or building. It excludes succeeded,
blocked and recovery_required. SQL selects just decision IDs and creation times
in bounded 100-row pages, ordered by creation time and ID using keyset cursors.
Read sessions close before sequential RevisionProcessor.process_revision calls.
A scan-level lock skips overlapping scans. There is no work reset, blind retry,
provider retry loop, forced recovery or alternate revision identity algorithm.
Errors are logged as machine operation codes and decision IDs, without exception
text, feedback, paths, prompts or provider bodies. Domain calls use the existing
private-packet logging guard.

The existing processor owns durable work/style/writing checkpoints, budget and
LLM accounting, exact predecessor/successor identity and independent successor
approval. Crash/restart uses those records. An ambiguous provider outcome remains
recovery_required and is excluded from later scans. Terminal work is not
reprocessed automatically. Anthropic can run only through the trusted processor
and executor under their existing safeguards. Tavily, employer HTTP, application
submission and browser-lifetime background work are absent.

Tests validate startup discovery of a committed decision with no work, actual
existing-v9 storage opening, absence of unrelated schedules/services,
creation-time/ID order, sequential calls, overlap exclusion, duplicate scan
convergence, separate cross-process launch locks and coexistence with the normal
scheduler. Twelve crash boundary cases restart through worker discovery. Two
additional tests kill an actual worker process at after_writing_checkpoint and
after_ready_commit: flock is released on process death, status remains building,
restart succeeds with one successor and exactly two fake revision-provider calls
across both processes. Completed work is not selected again and its successor
has no automatic Approve. Queued/building/succeeded status integrates with the
existing local status adapter. Blocked and ambiguous recovery states remain
excluded, with no automatic provider retry.

The entire existing revision regression covers actual process-death checkpoints,
current-truth changes, immutable versions/decisions, no duplicate successor,
monthly budget/accounting/checkpoint reuse and no-Tavily behavior. Test fixtures
trap sockets, DNS, real Anthropic and Tavily construction/research; all provider
responses are offline fakes. No outside-sandbox server/browser command was needed
for D, and no provider or employer activity was performed.

Validation:

- Scheduler + complete existing revision + CLI regression: **332 passed**,
  73.02 seconds (before adding the two worker process-death cases).
- Updated scheduler/security/queue/static-UI sandbox selection: **129 passed**,
  **16 deselected**, 15.43 seconds. Deselection excludes browser cases and four
  port-80 cases whose names include browser; those already passed in C.
- Final updated scheduler + CLI selection after strengthening real storage
  startup coverage: **51 passed**, 15.64 seconds.
- These runs overlap; their counts must not be summed as unique coverage.
- Completed selections: **0 warnings, 0 skips, 0 xfails**.
- Python compilation, CLI help inspection and git diff --check passed.

One initial startup test used the shared fixture's test.sqlite filename whereas
production requires job_pilot.sqlite3. Final startup coverage copies the fixture
with SQLite backup into the production filename and opens it through the real
existing-v9 opener. Production storage rules were not relaxed.

No commit, push, dependency install, API background worker or domain change.
The working tree retains the authorized cumulative Run 3 changes. STOP for
Andrew's Milestone D review under CLAUDE.md: “Stop after every milestone for
Andrew's review.” Milestone E security/integration red team, full regression and
established sandbox/browser split, final validation totals and final Run 3 audit
remain pending. Run 4 authentication/Tailscale/multi-device access remains deferred.


## Milestone E: sandbox red team complete; outside test approval required

Andrew approved D and authorized E with an explicit stop before every required
outside-sandbox test command. E has changed tests/test_approval_security.py,
tests/test_approval_ui_dom.py, README.md and this report only. No production
safety or domain semantics needed changing during the audit. README now removes
obsolete Run 2 statements that the implemented Run 3 UI/API remain deferred.

Cumulative exact changed files from starting c6c7647 (initial tree clean):

```text
README.md
APPROVAL_QUEUE_REPORT.md
src/job_agent/cli.py
src/job_agent/scheduler.py
src/job_agent/packet_history.py
src/job_agent/dashboard/approval_app.py
src/job_agent/dashboard/approval_service.py
src/job_agent/dashboard/approval_models.py
src/job_agent/dashboard/approval_security.py
src/job_agent/dashboard/static/approval.html
src/job_agent/dashboard/static/approval.js
src/job_agent/dashboard/static/approval.css
tests/test_scheduler.py
tests/test_approval_queue.py
tests/test_approval_api.py
tests/test_approval_security.py
tests/test_approval_ui_dom.py
```

### Consolidated route and boundary audit

GET / returns only the fixed shell. GET /assets/approval.js and
/assets/approval.css are the only allowlisted assets. GET /api/bootstrap returns
only process token/local metadata. GET /api/queue has bounded explicit metadata
SQL and no card verification. GET /api/packets/{id} reconciles the exact detail
snapshot around trusted preview/current validation. GET /api/packets/{id}/history,
/revision-status, /decision-detail and /application-destination project only
needed local data through the existing services. GET /api/packets/{left}/diff/
resume/{right} and /diff/cover/{right} use the trusted historical helpers.
GET /api/packets/{id}/artifacts/resume.pdf returns captured authenticated bytes.
POST /api/packets/{id}/approve, /reject and /revise call the existing ApprovalService
only. No legacy router, docs, arbitrary artifact/path download, redirect or
provider-generation route is installed.

Host/DNS rebinding, exact Origin, process CSRF, bounded JSON, sanitized errors,
no CORS, security headers, MIME/referrer/frame policy, strict opaque expectations,
exact replay/conflicts and append-only decisions are preserved. Current validity
is separately checked, never inferred from history/diff/queue metadata. Raw
provider errors, evidence_json, paths, prompts, candidate input files and unused
answer-bank content are excluded from web DTOs/logs. Decision detail is narrowly
separated from history. Browser authority stays in memory; restores invalidate
and refetch. No fingerprint or CSRF is placed in URLs or persisted browser state.

The red-team checks exercise hostile/duplicate Host and forwarded headers,
missing/foreign/null Origin and tokens, preflight/GET mutation denial, private
validation errors, stale tokens, action races, packet-view reconciliation,
traversal/private-file attempts, symlink/manifest/container tampering, bounded
captured PDF responses and offline resume/cover diffs. The new streamed-body
case proves that chunking without Content-Length cannot exceed 65,536 bytes or
reach downstream mutation parsing. Existing concurrency tests cover duplicate
Approve/Reject/Revise and opposing actions with exact domain replay afterward.
Worker scans converge through the trusted lock/checkpoints and exclude terminal
or ambiguous recovery states.

The source audit finds no provider/employer HTTP or process_revision call in the
approval web modules, no BackgroundTasks, permissive CORS, FileResponse reopen,
HTML insertion API, browser persistence, service worker or remote product asset.
API fixtures trap sockets/DNS/HTTP clients/providers/builds/revision generation.
The browser fixture now also traps Python-side outbound sockets and DNS, while
Chromium resource interception permits only its assigned local server origin.
No source/employer external link is actually navigated by tests.

New pending actual-browser red-team cases check real-Uvicorn rebinding-style
Hosts, localhost alias consistency, forwarded-header nonauthority, mutation
Origin, preflight and GET denial, private file/artifact requests, all PDF security
headers and ignored Range (bounded full response). They exercise two actual
browser tabs replaying one exact approval, current destination opening only after
an explicit revalidated click (window.open is spied, never externally navigated),
inline-script CSP enforcement and keyboard confirmation focus. Existing desktop
1440x900 and phone 390x844 checks now also enlarge text to 200% and inspect page
overflow. These new actual-browser checks are collected, not yet executed.

### Completed E validation and pending split

- Required affected approval/packet/revision/history/scheduler/CLI/database/
  company-research/batch/chaos plus security/queue regression: **1,380 passed**,
  261.60 seconds.
- Exact known sandbox adapter/bootstrap/boundary/static UI selection:
  **60 passed**, **84 deselected**, 29.29 seconds.
- Complete established sandbox-compatible offline split, excluding the original
  ten Chromium/FastAPI files plus approval API/UI files: **2,298 passed**,
  266.86 seconds.
- Successful final selections have **0 warnings, 0 skips, 0 xfails**.
- These executions overlap and are not summed as unique cases.
- Whole current suite collection: **2,601 cases**. Disjoint final split is
  **2,298 sandbox + 303 outside-sandbox**. Total final passing count is pending.
- The pending outside split includes **159 established cases**, **126 approval
  API cases**, and **18 approval UI cases** (16 actual Chromium, 2 static).

An initial broad red-team selection accidentally included the threaded
busy-detail FastAPI test in the sandbox: **132 passed, 1 timeout, 94 deselected**.
It hit the documented sandbox worker-thread wake-up limitation. The exact known
sandbox selection then passed all 60 cases above. The threaded case remains in
the pending approved-outside selection; no timeout workaround or production
safety change was introduced. No outside command was automatically executed.

Python compilation and git diff --check pass. HEAD is still c6c7647. Git diff for
approvals.py, packet_verify.py, revisions.py, llm.py, tavily_research.py,
database.py, packets.py and pyproject.toml is empty. SCHEMA_VERSION remains 9;
request tests compare sqlite_master and user_version before/after and worker
storage tests refuse absent/v8 storage without migration. No dependencies,
commit, push, live provider test, employer-facing request or submission occurred.

STOP for approval of this exact TEST-ONLY outside-sandbox command:

```sh
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py tests/test_approval_api.py tests/test_approval_ui_dom.py
```

The command contains only tests, preserving the established ten-file split and
adding the two approval files requiring FastAPI/Chromium execution. No edits,
installs, live providers or employer actions are bundled with approval. E and
Run 3 final validation are not declared complete until this split passes.

### Known trust boundaries and Run 4 deferrals

Run 3 is local-only and has no identity authentication. A trusted local user or
local process can read local professional data and obtain the process token;
CSRF is a browser request boundary, not user identity. Supported CLI binding is
exactly 127.0.0.1 with no host option; non-loopback ASGI peers/endpoints are refused.
A deliberately replaced launcher/forged ASGI scopes and compromised local OS
are outside that guarantee. Application destination validity is a checked
snapshot; explicit clicks revalidate, and no permanent authorization is claimed.
Noncooperating filesystem/DB writers remain outside cooperative lock guarantees.
PDF viewing uses bounded full captured bytes without Range and depends on the
browser's own viewer; headless tests check navigation commit and authenticated
response rather than promising viewer rendering. No automatic manual recovery,
ETA, cancellation or service-management layer is added.

Run 4 owns identity authentication, Tailscale and authenticated multi-device/
remote-phone access. Remote/public/LAN/tunnel hosting is absent from Run 3.
Gmail, Calendar, LinkedIn automation, UI-triggered Tavily refresh and automated
employer submission remain outside this run; no future submission capability
is promised by the approval link. The API/UI only support local review and
explicit manual navigation after current validation.


## Final Run 3 validation and audit

Andrew approved the exact E TEST-ONLY outside-sandbox command recorded above.
The final execution passed **303 tests in 87.48 seconds**, with **0 warnings,
0 skips and 0 xfails**. This supersedes the earlier pending E validation gate.
The established legacy browser/FastAPI split passed all **159 cases**; new
approval API/UI files passed **144 cases**, including **16 actual Chromium
cases**. Together with the complete disjoint sandbox split, all **2,601 offline
cases passed**: **2,298 sandbox + 303 browser/FastAPI**. The full split execution
time was 354.34 seconds (266.86 + 87.48), excluding repeated focused regressions.
The 1,380-case affected regression and 60-case direct/static selection are
additional overlapping evidence, not added to the unique full-suite count.
The four new approval files contain 227 cases; 26 further scheduler cases were
added, preserving the established 2,348-case baseline.

The new real-server Host/Origin/CORS and private-path tests passed. Both local
Host authorities share the process token while exposing their matching origin.
Forwarded headers cannot change it. PDF responses retain every security header,
serve exact captured bytes and ignore Range with a bounded full 200 response.
Two actual tabs replay the same exact approval into one durable decision.
Current valid application navigation is attempted only after an explicit click
and another current validation, with the exact URL and noopener/noreferrer;
the test spies the call and performs no employer navigation. Changed current
evidence disables the link without navigation. Inline script execution is
blocked by CSP. Keyboard Tab/Enter and focus restoration pass. Desktop
1440x900 and phone 390x844 pass with no page horizontal overflow, including
200% enlarged text and usable inline revision confirmation. Diffs retain their
own horizontal scroll container. Local PDF new-tab navigation/bytes, XSS text,
Unicode counting, stale refresh, pageshow invalidation and terminal polling
also pass. Browser interception and Python socket/DNS/provider/HTTP/build traps
prove approval-server and browser outbound isolation in these offline fixtures.

Initial E outside execution was **302 passed / 1 failed** in 88.18 seconds:
Playwright's string wait_for_function invoked eval, which the required CSP
correctly blocked. The test now uses a locator-polled DOM marker set by the
navigation spy; no unsafe-eval or production CSP exception was added. The first
edit matched the other navigation spy, so an already-collected rerun was
**302 passed / 1 failed** in 92.54 seconds. The intended spy was corrected and
the final exact full selection above passed. These were test-harness fixes;
no production approval, rendering or navigation policy changed.

Final architecture: separate create_approval_app, exact loopback CLI binding,
raw Host boundary, process-memory CSRF plus matching Origin, no CORS, fixed
same-origin assets, restrictive CSP/security headers, no-store private data,
explicit Pydantic DTOs, trusted domain-service adapters, coherent exact detail,
independent current authorization and captured authenticated PDF bytes. Queue
cards remain uncertified metadata. Exact Approve expectations are never replaced;
Reject/Revise exact replay and changed-body conflict semantics remain domain-owned.
Revise commits durable work intent without HTTP generation, and its separate
revision-only scheduler discovers it independently of server/browser lifetime.
The worker retains Run 2 identity, truth, budget, checkpoint and recovery rules;
terminal work is not automatically retried and successors require new approval.
History and local face/cover diffs never authorize anything.

Error mapping remains sanitized: 400 invalid_host; 403 csrf_failed/local_only;
404 not_found/artifact_unavailable; 422 invalid_request (413 for oversized body);
409 stale_packet/stale_approval_view/decision_conflict/packet_integrity_failed/
approval_not_current/artifact_integrity_failed; 503 packet_busy/storage_unavailable;
500 internal_error. No exception representation, SQL, traceback, rejected private
input, evidence_json, provider body, prompt or token is echoed/logged. Normal
approval access logging is disabled. DTOs are QueueItem, PacketDetail,
ApprovalPreview, DecisionResult, RevisionStatus, HistoryItem, PacketDiffResult,
ArtifactMetadata, DecisionDetail, ErrorResponse and BootstrapResponse, with
narrow screening/fact/destination/queue wrapper DTOs.

Schema unchanged proof: SCHEMA_VERSION=9; database.py and schema source have no
diff; request tests compare sqlite_master and user_version before/after;
worker startup only opens existing v9 and rejects missing/v8 storage. No new
dependencies or frontend build pipeline were added. Starting HEAD was c6c7647
with clean status, and final HEAD is unchanged. The cumulative 17-file list in
E above is exact. All seven prohibited domain-production files and pyproject.toml
remain unchanged. Final compilation and git diff --check pass. Git status lists
only the five modified tracked files and twelve intended new files. No commit,
push, live provider test, employer-facing request, submission or remote service
was performed. Milestone E and Run 3 implementation/validation are complete.
STOP for Andrew's final review; no Run 4 work begins automatically.

### Required YES/NO audit

Answers describe the supported Run 3 CLI/application and trusted local runtime,
not a maliciously replaced launcher or compromised OS. Current authorization
is a point-in-time validation; application clicks revalidate it rather than
claiming permanent validity.

| # | Question | Answer |
|---|---|---|
| 1 | Can approval UI bind to 0.0.0.0? | NO |
| 2 | Can approval UI accept arbitrary Host? | NO |
| 3 | Can forwarded headers redefine approval origin? | NO |
| 4 | Is approval API permissive CORS? | NO |
| 5 | Can a mutation succeed without valid CSRF? | NO |
| 6 | Can a mutation succeed from a foreign/null Origin? | NO |
| 7 | Can GET mutate a decision? | NO |
| 8 | Can untrusted job/company text become executable HTML/JS? | NO |
| 9 | Can an arbitrary filesystem path be served? | NO |
| 10 | Can a symlinked resume be served? | NO |
| 11 | Can queue-card metadata alone create approval? | NO |
| 12 | Can Approve omit expected packet fingerprint? | NO |
| 13 | Can Approve omit expected approval-view fingerprint? | NO |
| 14 | Can server silently refresh a stale approval-view fingerprint during POST? | NO |
| 15 | Can Reject omit expected packet fingerprint? | NO |
| 16 | Can Revise omit expected packet fingerprint? | NO |
| 17 | Can the same packet receive two different decisions? | NO |
| 18 | Can v1 Revise authorize v2? | NO |
| 19 | Can HTTP Revise directly perform provider generation? | NO |
| 20 | Can browser/API restart lose a committed Revise request? | NO |
| 21 | Can revision worker call Tavily? | NO |
| 22 | Can revision worker bypass LLM budget/checkpoint rules? | NO |
| 23 | Can revision worker blindly retry recovery_required? | NO |
| 24 | Can a succeeded revision successor be shown as approved automatically? | NO |
| 25 | Can application destination open automatically? | NO |
| 26 | Does approval server fetch employer URLs? | NO |
| 27 | Can an application link be enabled as currently authorized after validation becomes stale? | NO; stale validation disables it, and clicks revalidate |
| 28 | Can source/application links leak dashboard referrer? | NO |
| 29 | Does approval UI load remote fonts/CDNs/analytics? | NO |
| 30 | Does browser private state use localStorage/sessionStorage? | NO |
| 31 | Can history/diff authorize a packet? | NO |
| 32 | Does resume diff use OCR? | NO |
| 33 | Does cover diff call LLM? | NO |
| 34 | Can queue/detail/approve/reject/revise HTTP call Anthropic? | NO |
| 35 | Can queue/detail/approve/reject/revise HTTP call Tavily? | NO |
| 36 | Does Run 3 change schema v9? | NO |
| 37 | Does Run 3 implement remote authentication? | NO |
| 38 | Does Run 3 implement Tailscale? | NO |
| 39 | Does Run 3 automate application submission? | NO |

Known trust boundaries and exact Run 4 deferrals remain as documented immediately
above. This implementation is not described as universally secure or bulletproof.
