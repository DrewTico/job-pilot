# Run 5D-2 History and Trustworthy Changes

**READY FOR ANDREW RUN 5D-2 STAGED-DIFF REVIEW.**

Implementation candidate for Andrew's review. Run 5D is not complete; 5D-3 is
not started. Start: `main`, HEAD and local `origin/main` both
`8d545c472f5bdef5186397f5592b168618b74688`, clean worktree/index/untracked inventory.
Project rules, integration matrix and Run 5C/5D-1 reports were read. No builder
gate was reopened, skill/config changed, dependency added or agent delegated.

## Product and lineage contract

`compare_revision` extends `packet_history.py`; no parallel history system.
BEFORE is the exact caller-selected predecessor, AFTER the exact successor.
The relationship authority is the successor's `revision_decision_id`, its
immutable Andrew Revise `PacketDecision`, and the corresponding
`PacketRevisionWork.successor_packet_id`. `_revision_source` authenticates the
predecessor fingerprint and retained decision audit version/status. The shared
relationship validator also checks exact job key, canonical identity, retained
search-result identity, increasing versions, work/successor identity and the
authenticated retained target style snapshot.

No version adjacency, latest packet, timestamp, filesystem or queue order grants
lineage. A v1 -> v3 revision with unrelated v2 is proved. Wrong same-job versions,
cross-job pairs, self-comparison and reversed caller direction return
`invalid_request`; inputs are never reordered. Generic diff APIs retain their
existing explicitly caller-directed behavior, including reverse comparisons.

History listing now uses the same durable relationship validator inside an
explicit read snapshot. Damaged purported revision links fail with sanitized
`history_integrity_failed`, rather than remaining revision-linked or silently
becoming unlinked. Existing corruption-recovery lineage is unchanged.

## Resume, cover and evidence semantics

Resume uses the existing fixed packet-directory reader, exact stored manifests,
bounded captured bytes, hashes, no-follow file access and local PDF/DOCX/face
consistency checks. Cover uses the existing retained style/checkpoint/draft
authenticator. Its new owned-claim check rejects substituting another checkpoint
even when text is identical; legitimate shared cached checkpoints still pass.
Both reuse `_unified` with exact packet/version BEFORE and AFTER headers and
terminal-newline markers. No historical output is regenerated or reconstructed.

Each content result carries `before_status`, `after_status`, `status`, `changed`
and `diff`. Native statuses remain `available`, `unavailable`, `integrity_failed`.

| Evidence | Serialized component status | changed | diff |
| --- | --- | --- | --- |
| Both sides authenticated, changed | `available` | true | Exact directed unified diff |
| Both sides authenticated, identical | `available` | false | Empty string |
| Missing/incomplete evidence | `unavailable` | null | null |
| Tampered/mismatched/unverifiable evidence | `integrity_failed` | null | null |

The DTO requires these status fields, and the generated JSON schema retains
their distinct literal values. Consumers use `status` and per-side statuses,
not null/empty-field inference. A missing packet returns overall `unavailable`;
an unverifiable relationship returns `integrity_failed`; a caller-selected pair
that is not the authenticated directed relationship returns `invalid_request`.
Those overall statuses remain explicit even when both components are null.

Both sides are inspected. Integrity failure takes priority over unavailable
evidence, so a missing predecessor cannot hide a tampered successor. Overall
comparison status aggregates resume/cover status, while each component retains
its own evidence status. Invalid or failed relationships expose no content diff.
Absent packets preserve requested IDs with unavailable identity fields. Failure
to open/read the outer storage snapshot produces sanitized `history_storage_error`
/ HTTP 503; unverifiable retained evidence fails closed as `integrity_failed`.

These are historical content checks, not a fresh truth/policy/readiness check or
current approval. They preserve the existing trusted-storage/hash threat model;
they do not claim protection against coordinated hostile rewriting of SQLite,
all checkpoints and artifact manifests. It requires compatible local PDF/DOCX
checkers and does not claim a global SQLite/filesystem transaction. No stronger
5D-1 verifier is weakened.

## Structured state and historical decisions

No additional structured field changes were appropriate. Screening snapshots
(`saved`, `answers`, `manual_needed`) exist on packets, but independent historical
authentication requires old candidate/answer-bank inputs not retained as complete
versioned inputs. Current bank reconstruction would substitute current truth.
Screening/manual-needed diffs are therefore deferred, not represented as empty.

Lifecycle status, latest allocated, latest ready, work state and current artifact
availability can change after completion. They are not immutable historical
before/after readiness facts. Existing history retains its separately named
latest/status metadata; the new contract reports per-side content availability
without inventing historical readiness changes or a universal packet diff.
The returned `revision_state` is operational work metadata at read time, not a
historical structured change or current authorization assertion. For 5D-3,
screening/manual-needed and historical readiness comparison remain unsupported
until independently authenticated historical inputs are available.

PacketDecision reads remain exact packet-only. The predecessor Revise stays on
the predecessor; a new successor initially has no decision, `not_approved`, and
its own approval preview/fingerprint. Any later successor decision and current
authorization are evaluated independently. Comparison returns no authorization token or
current authorization assertion. Existing approval/detail validation remains
independent and Run 5C decision DTOs/POSTs/persistence are unchanged.

## Protected API / DTO changes

Added read-only
`GET /api/packets/{before_id}/revision-comparison/{after_id}` for 5D-3. It returns
`RevisionComparison`, containing `HistoricalPacketIdentity` for each side
(packet ID, version, fingerprint), the authoritative revision decision ID/work
state, overall native status and two nullable `RevisionContentDiff` results.
Exact identities prevent consumers from attaching one pair's result to another.
Untrusted relationships are explicit HTTP 200 typed results with
`status=invalid_request`; malformed path IDs/query parameters are sanitized 422.

Existing same-origin private middleware, Tailscale identity, Host, Origin/CSRF,
CSP/no-store and sanitized exception boundaries remain. The endpoint accepts no
query parameters or mutation body. No route triggers generation. Only the
contract generator/snapshot and their equality test changed mechanically in
frontend-related paths; no TypeScript, component, styling or UI behavior changed.

## Read-only, provider and employer proof

All tests use temporary SQLite/artifact roots and synthetic packets. Snapshot
proofs compare every table, sqlite_master, SQLite/file bytes, decisions, writing
checkpoints, style/fact retention and application/job state before/after reads,
including deliberately damaged temporary evidence. No history mutation,
repair-on-read, new work, submission or application event occurs.

During comparison/history reads: **NO MODEL / PROVIDER CALLS**. Tests trap fake
executor access, real Anthropic construction, socket/DNS, Tavily, current
candidate loading, style-file access, builds, revision execution and approval
validation. Fixture preparation uses controlled fake generation only. Exact
comparison still succeeds after current facts/bank/style files are deleted.
Debug logging does not expose cover/resume text or revision feedback.

Application runner, CLI apply, attempt/status/job-state writers are trapped by
the established offline fixture. Full-table snapshots and explicit zero
application-event assertions prove no employer/application side effect.

**NO SCHEMA CHANGE.** Database/migration source and schema version 9 are unchanged.
Corruption tests disable selected triggers only inside temporary SQLite to model
external damage, then prove reads do not repair or alter that damaged storage.

## Production-data safety

Reused the Run 5D-1 read-only inventory/hash procedure before mutation-capable
tests. All 12 regular files under the configured production data root were
measured by SHA-256, size, device, inode and mtime_ns; no SQLite connection was
opened to production, and no contents were exported.

Starting SQLite: SHA-256
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`,
241,664 bytes, device 2096, inode 216020, mtime_ns 1791404174236327816.
After the complete suite, the regular-file inventory and all five measured
attributes match exactly for all 12 files, including the SQLite values above.
This is new current-run measurement, not reuse of historical 5D-1 evidence.
Measurement manifests stay outside the repository as
`job-pilot-run5d2-production-before.json` / `job-pilot-run5d2-production-after.json`.

## Current-run test-first record

Genuine red -> minimal change -> focused green:

- New exact comparison: selection `exact_revision_change or authenticated_unchanged
  or existing_generic_read or successor_authorization` initially **2 failed,
  2 passed, 20 deselected**, missing comparison function. Implemented the bounded
  comparison; non-HTTP selection then **23 passed, 1 deselected**.
- Protected route: selection `protected` initially **1 failed, 23 deselected**,
  HTTP 404. Added the read route/DTO. The subsequent outside-sandbox run exposed
  unexpected query acceptance (**1 failed, 27 deselected**); added the existing
  request-query refusal pattern. Then **1 passed, 27 deselected**.
- History relationship corruption: selection `durable_relationship` initially
  **4 failed, 24 deselected** because history did not fail closed. Shared the
  validator; then **4 passed, 24 deselected**.
- Identical-text cover checkpoint substitution: selection `checkpoint_substitution
  or lineage_skips or unfinished or missing_evidence or ignores_missing` initially
  **1 failed, 4 passed, 28 deselected**. Bound the owned writing claim; focused
  substitution then **1 passed, 33 deselected**.

All commands used `.venv/bin/pytest -q tests/test_revision_comparison.py -k
'<selection>' --tb=short`. Immediate proof tests include existing directed generic
diffs/read immutability and independent successor authorization (the initial two
passes); nonadjacent lineage, unfinished successor, missing/tamper precedence and
missing-current-input independence also passed immediately after the new contract
existed. No failure was manufactured for behavior already correct.

Harness/environment: the first implemented HTTP test hit the established sandbox
FastAPI worker-thread timeout and was rerun with test-only escalation. No fixture
correction was needed. The read-only production measurement helper initially
treated directories as nonregular files; it was corrected to skip directories
before any mutation-capable test and successfully captured all 12 regular files.

## Historical implementation validation in increasing scope

A. Focused:

```sh
.venv/bin/pytest -q tests/test_revision_comparison.py --tb=short
```

**35 passed**, 25.40 seconds, exit 0.

B. Established neighboring regression:

```sh
.venv/bin/pytest -q tests/test_revisions.py tests/test_scheduler.py tests/test_packet_history.py tests/test_packets.py tests/test_packet_chaos.py tests/test_approvals.py tests/test_approval_api.py tests/test_approval_queue.py tests/test_approval_service_unit.py tests/test_database.py tests/test_approval_security.py tests/test_tailscale_api.py tests/test_tailscale_security.py tests/test_apply_submit.py tests/test_apply_handoff.py tests/test_llm.py tests/test_cli_defaults.py
```

**1,477 passed**, 389.75 seconds, exit 0; no warnings, skips or failures.

C. Applicable static/contract checks:

```sh
PYTHONPATH=src .venv/bin/python frontend/scripts/generate-contracts.py
.venv/bin/pytest -q tests/test_frontend_delivery.py -k contract_snapshots_and_synthetic_fixtures
.venv/bin/python -m compileall -q src/job_agent tests
git diff --check
```

Generator exit 0; contract equality **1 passed, 35 deselected**, 0.72 seconds.
Compilation and whitespace checks exit 0 with no output. No new formatter/type
checker or dependency introduced.

D. Complete established offline suite, once after candidate completion:

```sh
.venv/bin/pytest -q
```

**3,015 passed, 23 warnings**, 616.49 seconds (10:16), exit 0; no failures,
skips or xfails. Warnings are DeprecationWarning from unchanged multiprocessing
fork tests: 7 packet chaos, 12 revision, 4 scheduler. The complete suite ran
once after candidate completion; no behavioral source/test changes followed the
focused run. Counts overlap and must not be summed. Threaded ASGI/browser
tests use the established outside-sandbox test-only environment, with temporary
storage and controlled providers; no production revision is executed.

## Complete candidate manifest / review

| Classification | Path |
| --- | --- |
| PRODUCTION | `src/job_agent/packet_history.py` |
| PRODUCTION | `src/job_agent/dashboard/approval_app.py` |
| PRODUCTION | `src/job_agent/dashboard/approval_models.py` |
| PRODUCTION | `src/job_agent/dashboard/approval_service.py` |
| PRODUCTION (mechanical contract generator) | `frontend/scripts/generate-contracts.py` |
| PRODUCTION (generated contract, retain) | `frontend/src/lib/contracts.json` |
| TEST | `tests/test_revision_comparison.py` |
| TEST (mechanical contract equality) | `tests/test_frontend_delivery.py` |
| DOCUMENTATION | `docs/run5d/RUN5D2_HISTORY_TRUSTWORTHY_CHANGES_REPORT.md` |

The full suite regenerated the known Run 5C capture outputs. Three traced
untracked PNGs were removed after preservation outside the repository:
`desktop-reject-recorded-1440x900.png`, `desktop-revise-recorded-1440x900.png`,
`phone-validation-390x844.png`. The traced tracked
`desktop-bootstrap-unavailable-1440x900.png` was restored to its measured Git blob
(SHA-256 `0e725358db1710a10c542bfd51a3ee4beea9957f64b7106fa15fd4694d97d404`).
All 22 historical evidence file hashes match the before-test baseline. Copies
and cleanup hashes stay in `job-pilot-run5d2-generated-evidence` outside the repo.
No capture helper, accepted image, frontend layout or private data is changed.
Remaining GENERATED/REMOVE: **NONE**. UNEXPECTED: **NONE**.

At implementation completion, the complete tracked diff, new test file and
report were inspected for inferred
lineage, reversed direction, unavailable-as-unchanged, hidden integrity failures,
mutation/repair, provider calls, current-state substitution, authorization
inheritance, private/path leakage, schema/UI creep and unrelated changes. Only
the nine manifest paths remained uncommitted; the index was empty. Final whitespace and
new-file trailing-whitespace checks passed. HEAD/local origin/main remained at the
starting checkpoint on main. No schema, application, revision execution,
security middleware, frontend UI, skill/config, deployment or unrelated refactor
is intended. Stop conditions encountered: **NONE**; durable lineage was sufficient.

5D-3 desktop/phone history presentation, diff sheets, stale-response handling,
visual states and deferred polish remain out of scope. Consumers must respect
exact pair identity and per-component evidence status, and obtain current
authorization separately. No historical screening/readiness values are invented.

## Cleanup and staging review

Cleanup started with `main`, HEAD and local `origin/main` at the parent checkpoint
above, an empty index and exactly the nine intended paths. The complete source,
test and generated-contract diff was reviewed again. No additional path or
contract defect required a stop. Privacy review found only synthetic test data,
schema definitions and implementation metadata; no secret, real resume content,
private candidate/employer data, machine-specific temporary path or debug output
was added. No task-owned temporary file remained to remove.

Cleanup changes are documentation-only: explicit serialized result semantics,
the mutable meaning of `revision_state`, historical validation labeling and this
staging record. No production or test behavior changed during cleanup.

New cleanup validation, separate from the historical implementation runs above:

- Generated-contract equality: **1 passed, 35 deselected** (0.66 seconds).
- In-memory DTO JSON serialization: **7 checks passed**, covering changed,
  unchanged, unavailable, integrity-failed and invalid-relationship results,
  including null components. Distinct required status values survive serialization.
- Worktree and staged `git diff --check`: clean.
- Full suite was not rerun because cleanup did not change behavior.

All nine paths in the candidate manifest are classified **COMMIT** and explicitly
staged. **IGNORE**, **REMOVE BEFORE COMMIT** and **NEEDS ANDREW DECISION** are empty.
The staged manifest contains exactly those nine paths. No intended work remains
unstaged, and the untracked inventory is empty. Branch, HEAD and local
`origin/main` remain unchanged. Production storage was not opened or modified
during this cleanup; the production comparison above is implementation evidence.

NO COMMIT. NO PUSH. NO 5D-3. NO FRONTEND REDESIGN. NO SCHEMA CHANGE.
NO BUILDER-SKILL CHANGES. NO PRODUCTION REVISION EXECUTION.
NO PRODUCTION DATA MUTATION. NO EMPLOYER SUBMISSION.

STOPPED FOR ANDREW RUN 5D-2 STAGED-DIFF REVIEW.
