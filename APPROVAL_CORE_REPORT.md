# Exact-packet approval core, Run 1

Start gate: HEAD `3d802bb fix: make completed packet versions immutable`;
`git status --short` was empty. Read CLAUDE.md, README.md and the three required
packet/research reports before implementation. No rules or architecture were
changed. No dependencies, live providers, employer activity, commit or push.

## Files and scope

Production changes are limited to `src/job_agent/database.py`,
`src/job_agent/packets.py`, `src/job_agent/tailor/render_pdf.py`, and the new
`src/job_agent/approvals.py`. Tests: new `tests/test_approvals.py` and genuine
`tests/fixtures/schema_v7.sql`; existing `tests/test_packets.py`,
`tests/test_packet_chaos.py`, `tests/test_database.py`, `tests/test_batch.py`, and
`tests/test_company_research.py`. Documentation: README.md and this report.
The additional existing tests change current-schema expectations, exclude the
new decision schema from comparisons of old indexes, and correctly mark a
synthetically constructed legacy schema as v6. A saved-prose fixture now uses
approved candidate words. No existing tests were removed. Packet orchestration
fixtures now use actual PDF extraction, preserving their separate gate seam.

## Schema and migration

Schema version is 8. `packet_decisions` columns are `id`, `packet_id`,
`packet_fingerprint`, `decision`, `actor`, `reason_code`, `detail`, `created_at`,
`evidence_version`, `evidence_json`. All are NOT NULL. The primary key is `id`;
`UNIQUE(packet_id)` allows one decision per immutable version; the foreign key
references `application_packets(id)` with foreign keys enabled on every connection.

CHECK constraints enforce approve/reject/revise; actor Andrew; evidence version
1; exactly 64 lowercase hexadecimal fingerprint characters; detail length at
most 4000; empty Approve reason/detail; empty Revise reason and nonblank feedback
after trimming Python-compatible Unicode whitespace; the six Reject reason codes.
Persistent triggers `packet_decisions_no_update` and `packet_decisions_no_delete`
abort every UPDATE and DELETE with `packet_decisions is append-only`, including
after database reopen. `packet_decisions_detail_length` additionally counts UTF-8
leading bytes when detail contains NUL, closing SQLite's native length(TEXT)
NUL-short-circuit gap without rejecting legitimate 4000-character Unicode text.
Direct SQL tests cover constraints, uniqueness, foreign keys, UPDATE/DELETE and
this NUL bypass. Service validation counts the original Python string, never
truncates it, and stores accepted feedback verbatim.

The genuine v7 fixture was dumped from the trusted checkpoint's actual initializer
before production edits, with only meaningless line-end whitespace stripped and
the genuine user_version retained. Migration uses the existing explicit
BEGIN IMMEDIATE transaction and creates the new table/triggers additively.
Legacy capacity backfill is confined to versions below 7; v7/v8 successors with
NULL capacity_day must remain NULL. A populated genuine-v7 test includes every
major old table, ready and damaged historical packets, a ready successor,
succeeded and in-progress writing, company facts, valid company research cache,
capacity reservations, indexes and triggers. It compares all old rows/indexes/
triggers exactly, including fingerprints, work state, cache JSON and NULL capacity.
A parameterized failure after decision-table creation proves full rollback of
populated data, schema and user_version to valid v7. A separate empty-v7 failure
test also remains. Foreign_key_check is clean before/after migration and rollback;
future versions 9/99 are rejected without modification.

## One authoritative verifier

`verify_packet_integrity()` in packets.py is the read-only entry point. Its
implementation reconstructs completed state under a caller-owned session with
autoflush disabled. Approval loads current facts.yaml and answer_bank.yaml through
the existing typed semantic-hash loaders. It constructs no PacketService provider
or researcher and performs no recovery. No directory creation, file staging,
publication, rename, file repair, provider, URL fetch or browser operation occurs.
Existing renderers accept in-memory binary streams; expected DOCX/PDF equivalence
is reproduced in memory. Fsync belongs to generation before its durable checkpoint,
not to read-only manifest inspection.

The same verifier runs during first generation before completed checkpoint,
published pre-ready recovery, and completed packet reuse. Its builder-owned
prepublication options allow that builder's exact input snapshot and staging
location; approval always inspects current local inputs and the exact published
packet directory. The old ready-invariant entry point delegates to this verifier.
An actual builder loaded from checkpoint 3d802bb produces a packet which the new
verifier successfully approves and revalidates, proving historical request
reconstruction rather than relying only on a rewritten test approximation.

Checks include exact packet identity/readiness, scoring work provenance and score,
semantic context fingerprint, actual completed predecessor chains for successor
fingerprints, exact company bindings/usability/injection policy, screening
reconstruction, both exact writing requests and succeeded outputs, cover parsing
and verified text, raw resume parsing/truth/grounding, existing gate/no-drift/format,
allowed gate/fitting relationship, final-face truth/grounding, exact artifact
filenames, bounded regular nonsymlink files, PDF/DOCX container checks, manifest
sizes/hashes, rendered PDF sections/page budget/scope/truth, DOCX member equivalence,
PDF text equivalence, and an unchanged manifest at the end of artifact verification.
Any failure is sanitized and creates no Approve record. It does not repair the
packet. Historical completed-version generation immutability is preserved.

Raw writing output is deliberately not equated to the final face. The existing
_gate normalizes headers, cleans text, trims caps and reorders skills. The final
face must equal that result or a sequence of at most 30 existing
`drop_last_responsibility()` transformations, respecting its role floor and never
changing achievements. No additions, arbitrary edits or alternative candidate
lines are authorized by this relationship. Tests preserve legitimate gating and
bounded fitting and reject forged projects/employers/dates/numbers/skills/faces,
even with newly rendered matching files and a forged matching manifest.

## Binding and completed evidence

The packet fingerprint remains semantic INPUT identity, including current facts/
answer-bank identities, scoring snapshot, company semantic IDs, prompts/policies,
question identity and writing context. Its meaning was not redefined and it alone
cannot prove completed deliverables. Successor identities retain the established
completed-predecessor wrapping semantics.

Approve evidence_version 1 stores deterministically canonical JSON with exactly:

- `packet_version`
- `scoring_fingerprint`
- `artifact_manifest`: exact filename-keyed map of `sha256` and byte `size`
- `company_fact_ids`: sorted exact semantic_fact_id values, not storage IDs
- `writing`: task-keyed maps containing `task`, `request_fingerprint`, `output_hash`
- `cover_letter_sha256`: SHA-256 of the exact validated UTF-8 cover text
- `application_url`: exact validated currently resolved destination string

No document body, screening blob, candidate files, prompts, raw research, absolute
path, timestamp, inode or random evidence value is duplicated. Company row IDs
remain packet-bound relational references. Each bound semantic identity and its
job-scoped storage ID are recomputed, and current local usability/source/injection
rules rerun. Retrieval-time-only changes do not invalidate approval.

Screening uses one shared generation/verification path. Exact question keys,
saved values and manual_needed are deterministically reconstructed; bank semantic
identity is part of the packet input fingerprint. Only prepared candidate-authored prose selected by exact required question key
also runs the existing verify_text machinery, covering defined lexical,
numeric, degree, Simpro title, GitHub and GPA policies. Structured authorization,
relocation, enum and demographic answers are not forced through prose grounding.
Regression tests reject invented skills/tools/projects/numeric claims even when
a malicious test also recomputes the current packet fingerprint and snapshot.
No new LLM or universal natural-language truth checker was introduced.

Both writing tasks reconstruct the exact system/user hashes and existing
writing_fingerprint semantics. Every metadata field, succeeded state, output,
parse and recomputed output_hash is checked. Unknown/failed/recovery-required
work fails. Semantic checkpoints intentionally need not belong to the current
packet ID, allowing the established cross-version reuse.

Application URL resolution uses store.resolve_apply_url on the bound current
SearchResult. Local public HTTP(S) validation rejects invalid hosts, credentials,
private/reserved addresses, local/reserved suffixes and known wildcard aliases.
It neither resolves DNS nor fetches anything and stores the original string.
Before initial approval, a changed valid public URL requires a new preview and
its completed-view fingerprint; a stale preview cannot authorize that destination. After approval, changing that resolved destination fails
canonical evidence comparison, even though URLs are not direct packet writing
inputs. No normalized substitute is stored.

## Decisions, locking and current authorization

ApprovalService exposes preview_approval(packet_id, expected_packet_fingerprint),
approve(packet_id, expected_packet_fingerprint, expected_approval_view_fingerprint),
reject(..., reason_code, detail=''), revise(..., feedback), and
validate_approval_for_packet(...). A module-level future-validation entry point
also exists. Actor Andrew and derived evidence are service-owned. Every decision
requires the exact row and expected fingerprint; stale actions fail before
idempotency or insertion. Reject and Revise do not require intact deliverables;
the existing packet root and lock must be available. They store only version/
status audit metadata and never claim integrity passed.

The existing packets/.build.lock coordinates cooperating processes. Decisions
open that existing lock without creating roots or deliverables, then open a
session and BEGIN IMMEDIATE before packet/decision reads. All local verification
and insertion are one explicit writer transaction, with no provider/network IO
and no retries. UNIQUE(packet_id) supplies the durable final arbitration.
Separate-engine/connection thread races test Approve/Approve, Approve/Reject,
Approve/Revise and Reject/Revise. They run with the real lock and, separately,
with a test-only bypass of the file lock to demonstrate SQLite arbitration itself.
Identical Approves return one record; conflicts have one winner, one sanitized
conflict and one row. No deadlock or duplicate record was observed.

Replay compares exact semantic requests: packet/fingerprint/decision/Andrew,
plus exact Reject reason/detail or exact Revise body. Changed decisions/reasons/
details/feedback conflict. Approve replay additionally requires the digest of the stored immutable canonical
evidence and returns historical semantics without reverification. It cannot substitute for current authorization validation.

validate_approval_for_packet takes the build lock, requires exact ready packet
and ready_at, a matching Andrew Approve/evidence version 1, reruns the full verifier
with freshly loaded inputs, and compares canonical evidence strings exactly.
It returns only decision/packet identity and evidence. Tampering preserves the
historical decision while invalidating current authorization. Tests independently
alter PDF/DOCX/face/manifest/URL/writing output/hash/request/state/company facts/
screening/bank/facts, and prove replay remains historical but validation fails.
A successor requires its own independent Approve.

Reject only captures one of six reasons and optional <=4000-character detail;
it does not modify packets, artifacts or search filters. Revise is only a durable
nonblank <=4000-character request. Spaces, Unicode, NUL and newlines are retained;
4001 characters fail. It never writes style_memory.md or creates a successor.

## Privacy, isolation and trust boundaries

All decision/verifier paths use the existing context-local log redaction,
including SQL DEBUG/echo and PDF diagnostics. Feedback and candidate contents
are not logged or included in exception messages. Storage exceptions are reduced
to a machine code rather than exposing SQL parameters. Evidence contains only
allowed public URL/hash/semantic/manifest metadata. No API keys are stored.
Traps cover socket connections, external DNS, real httpx transport/client sends,
Anthropic construction, Tavily construction/research, Playwright/browser entry,
writing calls, publication and mkdir across all decision types and validation.
No fictitious email/Gmail/Calendar/LinkedIn integrations were added for testing.

Job Pilot's lock coordinates cooperating processes, not arbitrary hostile local
writers. SQLite and filesystem are separate resources. Host/DB/input-file write
permissions remain trusted, and a process that bypasses the lock can race file
inspection. Current authorization is therefore revalidated again before future
submission. There is no tamper-proof storage or retained original-byte archive.
Deterministic verifiers enforce defined rules but are not universal semantic truth
proofs. Lexical public URL checks do not establish DNS resolution or publisher
ownership. Company claims are not independently corroborated. Supported PDF
reading orders remain conservative and fail closed. Linux flock and trustworthy
local storage remain required. The decision transaction holds the SQLite writer
lock during bounded local verification; it performs no long provider work.

## Validation results

Final complete established offline suite: **1,888 passed**. The final sandbox
split passed **1,729** in 145.87 seconds; the already-approved exact test-only
Chromium/FastAPI split passed **159** in 9.66 seconds outside the sandbox.
Warnings / skips / xfails: **0 / 0 / 0** in both final runs. All affected suites
are included in that final run after the source-policy correction.
164 new approval cases include 3 migration cases, 8 concurrency cases and 82
named integrity/tampering/URL/screening/NUL red-team cases (these are subsets,
not additive totals). Final review also added current Tavily source/title/extraction and credential-marker
checks using existing pure local helpers. Two regressions show that oversized
or credential-bearing source titles invalidate authorization even though titles
are intentionally excluded from semantic_fact_id. No provider is constructed
or invoked by these checks.

Existing direct SQL constraints and append-only tests are
additional red-team coverage. The affected regression run passed 815 cases.

## Explicit answers for Run 1

All dangerous paths below are NO under the documented local service contract.
Company/screening changes refer to meaningful bound state, not harmless YAML
formatting or company retrieval timestamps.

| # | Question | Answer |
| --- | --- | --- |
| 1 | Can packet_ready alone create approval? | NO |
| 2 | Can input fingerprint alone prove completed deliverables? | NO |
| 3 | Can approval authorize another version? | NO |
| 4 | Can stale expected fingerprint create a decision? | NO |
| 5 | Can missing artifacts pass Approve? | NO |
| 6 | Can altered artifact bytes pass Approve against their manifest? | NO |
| 7 | Can symlink artifacts pass Approve? | NO |
| 8 | Can forged manifest/content bypass completed content verification? | NO |
| 9 | Can a changed approved application URL remain valid? | NO |
| 10 | Can changed bound company semantics remain valid? | NO |
| 11 | Can changed bound screening remain valid? | NO |
| 12 | Can tested invented prepared-screening claims pass Approve? | NO |
| 13 | Can corrupted writing output/hash remain valid? | NO |
| 14 | Can recovery_required writing pass Approve? | NO |
| 15 | Can two concurrent Approves create two rows? | NO |
| 16 | Can one packet record conflicting decisions? | NO |
| 17 | Can a decision row be updated? | NO |
| 18 | Can a decision row be deleted? | NO |
| 19 | Can Approve call Anthropic? | NO |
| 20 | Can Approve call Tavily? | NO |
| 21 | Can Approve contact an employer? | NO |
| 22 | Can Reject call providers/network? | NO |
| 23 | Can Revise call providers/network? | NO |
| 24 | Does Revise write style_memory.md? | NO |
| 25 | Does Revise create a successor? | NO |
| 26 | Can Approve replay substitute for current validation? | NO |
| 27 | Can current validation survive bound evidence tampering? | NO |
| 28 | Is new-core submission implemented? | NO |
| 29 | Is new-core dashboard/UI implemented? | NO |
| 30 | Is new-core auth/Tailscale/multi-device implemented? | NO |

Run 2: style memory and revised packet generation. Run 3: queue/dashboard/UI and
HTTP approval API. Run 4: login/authentication, Tailscale, phone/multi-device access.
Gmail, email sending, referral research, Playwright application submission and
all employer-facing activity remain later bounded work.


Final `git diff --check`: passed. HEAD remains 3d802bb. Final working tree is
intentionally uncommitted:

```text
 M README.md
 M src/job_agent/database.py
 M src/job_agent/packets.py
 M src/job_agent/tailor/render_pdf.py
 M tests/test_batch.py
 M tests/test_company_research.py
 M tests/test_database.py
 M tests/test_packet_chaos.py
 M tests/test_packets.py
?? APPROVAL_CORE_REPORT.md
?? src/job_agent/approvals.py
?? tests/fixtures/schema_v7.sql
?? tests/test_approvals.py
```

The exact approved outside-sandbox test-only command, rerun after the final local
source-policy correction, was:

```bash
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py
```

Its outside-sandbox requirement comes from the established Chromium launch and
FastAPI TestClient sandbox limitations documented in the prerequisite reports.
No source edits, installs, provider calls or shell writes were bundled into that
approval. No observed unresolved approval bypass remains within the defined
local service trust boundary; the limitations above continue to apply.

## Independent audit correction

The correction started at HEAD 3d802bb with the existing Run 1 changes
uncommitted, including approval-core-review.txt. No existing work was discarded.
The independent audit found that input identity did not bind the completed view
shown to Andrew: a current public URL B could replace rendered URL A before
Approve. The correction computes `approval_view_fingerprint` using the existing
SHA-256 canonical JSON digest over exactly the verifier's completed evidence.
No evidence fields, schema version, migration or answer-bank hashing changed.

The read-only `preview_approval()` takes the existing build lock, requires the
exact packet/input fingerprint, runs full integrity verification, and returns
only packet ID/version/input fingerprint, completed-view fingerprint and exact
validated URL. It performs no database mutation, document-body disclosure or
provider/network/browser work. Approve requires both expected fingerprints and
rejects a changed completed view with `stale_approval_view` before insertion.
An exact retry compares the expected view token to the stored immutable evidence
without current verification. Current authorization still reruns full integrity
and compares canonical current evidence exactly to stored evidence.

Screening truth verification now checks only prepared prose selected into the
packet by exact required question key, honoring structured-field precedence.
Unused prepared answers no longer cause unrelated candidate truth failures.
Selected invented skills, tools, projects and numbers remain blocked before
writing and at approval time. Structured answers and existing GPA/GitHub/
sponsorship/relocation checks remain intact. Unused-answer edits still change
the existing answer-bank semantic hash and packet input identity.

New regressions cover deterministic/read-only preview, retrieval-time stability,
URL A-to-B stale views, current B approval, historical replay/token conflict,
completed evidence tampering between preview and approval, required tokens,
selected versus unused screening, required-question changes, and unchanged
answer-bank hashing. Existing outbound traps now cover preview as well as Approve.

| # | Correction audit question | Answer |
| --- | --- | --- |
| 1 | Can a dashboard that rendered URL A approve URL B using A's stale view token? | NO |
| 2 | Can Approve succeed without the expected completed-view fingerprint? | NO |
| 3 | Can changed completed evidence between preview and Approve silently pass? | NO |
| 4 | Can an unused unrelated prepared answer make a packet fail truth validation? | NO |
| 5 | Can a selected invented prepared answer pass? | NO |
| 6 | Can post-approval evidence tampering remain valid authorization? | NO |
| 7 | Did this correction change schema version? | NO |
| 8 | Did this correction add submission/UI/auth/provider activity? | NO |

Correction validation results are recorded below separately from the original
Run 1 counts. No commit or push was performed.

Correction validation:

- Complete `tests/test_approvals.py`: **199 passed**, including **35 new cases**,
  in 107.58 seconds. This includes the new stale-view and selected-screening tests,
  plus the existing migration, concurrency and outbound isolation tests.
- Affected packet + chaos + database/migration + company-research + scheduler +
  CLI-default + batch tests: **647 passed** in 62.22 seconds.
- Complete established sandbox-compatible offline split: **1,764 passed** in
  173.68 seconds. Warnings / skips / xfails: **0 / 0 / 0** in all three runs.
- The correction's complete established offline total is **1,923 passed**:
  1,764 sandbox-compatible cases plus **159 passed** in 11.39 seconds in the
  established Chromium/FastAPI split. Warnings / skips / xfails: **0 / 0 / 0**.
  Andrew explicitly approved this exact TEST-ONLY outside-sandbox command, which
  completed successfully:

```bash
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py
```

No edits, installs or live-provider activity are included in that command.
Final correction `git diff --check`: passed. HEAD remains **3d802bb**.
Final correction `git status --short`:

```text
 M README.md
 M src/job_agent/database.py
 M src/job_agent/packets.py
 M src/job_agent/tailor/render_pdf.py
 M tests/test_batch.py
 M tests/test_company_research.py
 M tests/test_database.py
 M tests/test_packet_chaos.py
 M tests/test_packets.py
?? APPROVAL_CORE_REPORT.md
?? approval-core-review.txt
?? src/job_agent/approvals.py
?? tests/fixtures/schema_v7.sql
?? tests/test_approvals.py
```

All existing Run 1 work remains uncommitted. This correction changed only
approvals.py, packets.py, test_approvals.py, README.md and this report.
