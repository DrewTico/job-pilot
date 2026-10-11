# Scope

**5D-1 COMPLETE AS AN IMPLEMENTATION CANDIDATE**, awaiting Andrew's staged-diff
review. Run 5D remains in progress; 5D-2 and 5D-3 are not started. Implementation
run starting branch was `main`; HEAD and
local `origin/main` both matched
`c4a2c7d351e085eb9a6513db943973ad110a321c`. Worktree, index and untracked inventory
were clean. Required project rules, roadmap and revision/approval reports were
read before edits. The approved builder calibration was not reopened.

# Product Contract

Immutable recorded Revise decision -> separately invoked existing revision
processor -> grounded generation -> distinct successor packet/version -> safe
publication -> final integrity verification -> later independent review.

Revise POST remains human intent recording only. It creates one immutable
decision and no work, successor, style update, model call, worker or application
event. Execution uses the existing processor, CLI or scheduler discovery path.
Successors start without decisions or current authorization; their later
decisions still confer no employer/application action.

# Production Changes

Only `src/job_agent/cli.py` changes in production. `cmd_revision_process` reuses
`dashboard.approval_app._existing_engine`, already used by the revision scheduler,
instead of `search_database`. The engine is disposed in `finally`, including
processor exceptions and simulated process-exit exceptions. Loading the reused
opener also stays inside the existing sanitized exception boundary. Arguments,
metadata, exit statuses 0/2/1 and sanitized failure wording are retained.

No revision processor, assembly, verifier, scheduler, decision, accounting,
security, schema, application, deployment or frontend production module changes.

# Tests Added/Extended

30 new parameterized cases, plus strengthened existing helpers/assertions:

| File | Added proof |
| --- | --- |
| `tests/test_packet_history.py` | Seven real-main storage rejection cases; one sanitized opener-import failure case; one real-main current-schema processing/replay case with legacy JSON present. Existing CLI tests now use an actual existing SQLite opener, not mocked storage discovery. |
| `tests/test_approval_api.py` | One complete protected HTTP Revise -> separate processor -> successor review -> fresh HTTP Approve proof, with model/application traps and historical snapshots. |
| `tests/test_scheduler.py` | One actual two-process CLI-main/RevisionOperations contention proof using independent engines, the real build lock, fake transport through the real accounting executor, and an actual style-publication counter. |
| `tests/test_revisions.py` | One source-fingerprint mismatch; three invalid retained decision-evidence cases; ten direct/restarted malformed-output/unsupported-claim cases; partial render failure; invalid pre-existing final directory; three actual CLI publication-restart seams. |

The shared `source_state` snapshot now compares the predecessor row, immutable
decision, artifact bytes, historical writing checkpoints, historical style
snapshot, retained company facts, all application events and canonical job rows.
Existing injected/actual-death crash proofs inherit these comparisons. The
offline fixture additionally traps real application runner and application-state
entry points. No existing test was removed; the mocked storage-discovery helper
was replaced with the actual existing-storage boundary.

# Tests That Failed First

Before any production source edit:

```sh
.venv/bin/pytest -q tests/test_packet_history.py -k real_entry_rejects_storage
```

Result: **6 failed, 1 passed, 70 deselected** in 5.16 seconds. Missing database,
missing parent, empty database, genuine v8 schema, legacy-only JSON and alternate
database cases demonstrated unwanted storage creation/initialization/migration or
import. Their exact filesystem-byte snapshots changed. The future-schema case
already rejected safely. This drove the existing-only opener replacement in the sole production file.

After replacing the opener:

```sh
.venv/bin/pytest -q tests/test_packet_history.py -k revision_cli
```

Result: **18 passed, 59 deselected** in 3.29 seconds.

During final review, the newly reused opener import was outside the existing
exception guard. A focused synthetic ImportError reproduction failed before its
correction:

```sh
.venv/bin/pytest -q tests/test_packet_history.py -k storage_opener_import --tb=short
```

**1 failed, 78 deselected** in 1.54 seconds. The smallest fix moves that import
inside the existing `try`; no optional package is installed or architecture
changed. The sanitized message/status and untouched temporary storage are now
proved. The subsequent real CLI selection was **20 passed, 59 deselected** in
3.88 seconds.

# Proofs That Passed Existing Behavior Immediately

The domain source was never changed to manufacture failures. The new input,
output and publication/restart proofs passed their first focused execution.
Existing candidate-before-claim/after-claim, retained-source binding, ambiguous
provider, budget, checkpoint reuse and actual-death matrices remain authoritative
and are rerun in validation.

The HTTP and process proofs required test-harness corrections: the first HTTP
run timed out at the documented sandbox FastAPI thread boundary; the first
outside run and process run named the `jobs` table incorrectly; a later HTTP
request incorrectly forwarded the whole preview DTO instead of its two supported
request fingerprints. The strict DTO correctly rejected it. Only tests changed
for these corrections. These failures did not identify another production gap.

# Revision CLI Storage Boundary

The actual `main(["revision-process", ...])` path is covered. The opener uses the
configured exact `job_pilot.sqlite3` filename with SQLite `mode=rw` and requires
`SCHEMA_VERSION` (currently 9). It enables foreign keys without DDL. There is no
storage discovery, alternate-file selection, initializer, migration, legacy
import or recovery fallback.

Missing database/parent, empty database, genuine v8, future version, legacy-only
storage and alternate-named current database all fail with exit 1 and exactly
`Revision operation failed; details omitted.` Their file inventories and bytes
remain unchanged, and the processor is not entered. Current-schema storage
processes a real synthetic decision normally and replays into the same successor.
Legacy JSON beside accepted current storage stays byte-identical; sqlite_master
and user_version remain unchanged. Existing review-state exit 2 is retained.

# HTTP Intent / Execution Separation

The synthetic app uses the normal Host/Origin/process-CSRF/DTO/domain path. During
Revise POST, processor, build and fake-model calls are forbidden. Immediately
afterwards: one Revise, one original packet, zero revision work, no style file,
no additional model call, zero application events/status changes. The separate
processor then creates/consumes one work record and exactly one successor, which
passes `verify_packet_integrity`. The original decision, packet and history are
unchanged. No server or persistent worker is started by the POST.

# Concurrency / Idempotency

Two real local child processes start through a barrier, open independent database
engines, and attempt the same decision through CLI main and RevisionOperations.
The winner holds the existing build lock after successor allocation until the
parent observes both lock attempts. No provider call occurs before release.

Final durable state: one succeeded work row, one retained decision/source
binding, two total packets with distinct IDs/versions/fingerprints, one revision
successor, two succeeded new writing checkpoints, two successful LLM accounting
records, and two fake transport calls. Exactly one style `publish` completes;
the retained style contains the decision entry once. The successor has no
decision, final integrity passes, historical snapshots remain identical, and
application state remains unchanged. No new queue/lease/lock mechanism is added.

The two writing tasks are the existing `tailor_resume` request and the existing
`cover_letter` request, not two attempts at the same task. In
`PacketService._assemble_claimed_packet`, resume generation calls `_write_call`
once with `tailor_resume`; structured cover generation calls it once with
`cover_letter`. `_writing_requests` reconstructs these two distinct requests,
and `writing_fingerprint` includes the task, model, system/user hashes, prompt
version and token limit. `_write_call` durably claims each fingerprint before
provider access, reuses authenticated successful output and refuses automatic
retry of an unfinished or uncertain claim. The revision build lock spans this
pipeline for both cooperating consumers.

The concurrency proof requires exactly two accounting records whose actual
executor task names are exactly `{tailor_resume, cover_letter}`, both succeeded,
and exactly two fake transport calls, with a third call forbidden. Thus each
distinct intended task accounts for one fresh provider call for this decision
and its retained request inputs. The fake transport chooses its response by
call order, but the accounting task names come from the production executor
arguments, independently of those fake response labels. Final
`verify_packet_integrity` additionally authenticates both task-bound request
fingerprints and retained outputs. This proves at most one fresh provider call
per distinct writing task under the tested cooperating-process contract;
duplicate paid work for the same retained request is prevented. It does not
claim live-provider validation or distributed/hostile-writer isolation.

# Model / Accounting Safety

All new generation uses controlled fake responses. The process race uses the
actual `AnthropicExecutor` admission/accounting path with a fake messages
transport; its two accounting records have successful status and retained cache
usage. Existing budget-denial, successful-checkpoint reuse at exhausted budget,
admission preservation and ambiguous-outcome tests are retained and rerun.

Malformed/unsupported outputs are durably hashed successful output checkpoints,
then rejected by parsing/truth gates. Crash-before-parse restart consumes those
same checkpoints without another provider call. Replaying blocked work does not
reset it or its claims. Unknown paid outcomes remain recovery_required, not
automatically retried. Accounting architecture is unchanged.

Live paid/provider calls: **NO**. Research refresh: **NO**.

# Failure / Recovery

Source fingerprint mismatch and malformed/missing/version-mismatched decision
audit evidence reject before work/style/successor creation. Current candidate
changes before allocation are handled by existing tests; material changes after
claim block the original identity rather than allocating a replacement.
Existing retained evidence/request-authentication tests cover changed facts,
order, source URLs/titles, job/scoring context and missing/changed cover requests.

New cases reject malformed resume text, unsupported resume claims, invalid cover
JSON, invalid structured cover fields and unsupported cover claims. They remain
blocked with generation_failed, no ready_at, no final directory or successor
decision, sanitized failure recording and unchanged history/checkpoints on replay.
Partial render failure cleans its private staging tree and publishes nothing.
An invalid existing final directory is retained byte-for-byte, performs no new
model work, and leaves recovery_required with the original successor identity.

# Publication / Integrity

The real CLI is interrupted after verified artifact checkpoint, after atomic
publication and after packet-ready commit before revision success. Restart and
replay finish the same allocated successor with the same authenticated writing
checkpoints and exactly two revision model calls total. Final integrity is
verified before success and again on replay. No alternate successor identity is
allocated. Verified staging is private until publication; a prepublication
restart may rerender from authenticated outputs under the existing contract.

Existing no-replace/atomic publication, invalid-survivor verification, injected
crash and actual process-death matrices are retained. Ambiguous output before
durable checkpoint is covered by the existing unknown-writing-claim tests and
never blindly paid again. No new recovery machinery or overwrite path is added.

# Historical Immutability

Successor creation is additive. Strengthened snapshots preserve predecessor
identity, fingerprint, row, decision, artifact bytes, historical model/output
checkpoints, historical style snapshot and retained company evidence. The HTTP
proof additionally snapshots the source SearchResult. External damage in negative
tests is deliberately synthetic and is snapshotted after damage; processing
neither repairs it nor manufactures replacement history.

# Independent Successor Authorization

The actual revision successor has its own ID, version, packet fingerprint,
artifact tree and decision relationship. It begins with no PacketDecision and
`not_approved`. Normal protected detail verifies its current artifacts/evidence
and returns its own approval preview. Predecessor packet fingerprint fails with
stale_packet; predecessor approval-view fingerprint with the child's correct
packet fingerprint fails with stale_approval_view.

Only a fresh exact successor HTTP Approve creates its own distinct decision and
passes current authorization validation. The predecessor Revise remains intact;
success replay creates neither another successor nor another model call. Existing
one-decision-per-version and exact packet/view authorization infrastructure is
unchanged. No predecessor Approve/Reject/Revise is copied to the child.

# Employer / Application Separation

Explicit traps cover `run_apply`, `_run_flow`, CLI apply, attempt recording,
status update and job-state upsert. Socket/DNS, real provider and research seams
remain forbidden. HTTP and process proofs assert zero application events and
zero application-status transitions; shared snapshots compare all event/job
rows through generation and recovery. Approval still records a decision only.
Revision execution made no employer submission, application runner invocation
or outreach call.

# Schema

**NO SCHEMA CHANGE**

SCHEMA_VERSION remains 9. `database.py`, schema fixtures, migrations and decision
DTO/security/persistence source have no diff. CLI current-storage tests compare
sqlite_master and user_version before/after. Rejected-storage tests compare bytes.
Old-schema creation/migration inside existing regression fixtures targets only
temporary SQLite and is test setup/regression, never the production CLI boundary.

# Production Data Safety

Before any mutation-capable test, existing config (`JOB_AGENT_DATA_DIR` and its
default), README and the deployment template identified `data/job_pilot.sqlite3`
and the `data` artifact/input root. Read-only SHA-256, size, device, inode and
mtime_ns evidence was captured for all 12 regular production data files, without
reading SQLite through a mutation-capable connection or exporting contents.

Starting production SQLite SHA-256:
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`
(241,664 bytes). After the final complete suite, the inventory and all 12 files
matched the before evidence exactly: SHA-256, size, device, inode and mtime_ns.
SQLite remained device 2096, inode 216020, mtime_ns 1791404174236327816.
Measurement manifests are retained outside the repository as
`job-pilot-run5d1-production-before.json` and
`job-pilot-run5d1-production-after.json`; no production contents are exported.
All new mutations use pytest temporary SQLite/artifact roots. No production
revision execution or production decision request is part of validation.

# Historical Implementation Validation Results

Commands and counts below are from the completed implementation run, not newly
rerun during cleanup; selections overlap and are not summed. All mutation
storage is synthetic and providers are controlled.

Targeted revision/scheduler/history/API/CLI regression:

```sh
.venv/bin/pytest -q tests/test_revisions.py tests/test_scheduler.py tests/test_packet_history.py tests/test_approval_api.py tests/test_cli_defaults.py
```

**559 passed** in 178.31 seconds. Shared historical snapshots and the final
publication counter were strengthened while that already-collected run was
executing; the final focused, neighborhood and full runs validate those additions.

Earlier focused 29 cases before the final startup-error adjustment:

```sh
.venv/bin/pytest -q tests/test_revisions.py tests/test_scheduler.py tests/test_packet_history.py tests/test_approval_api.py -k 'real_entry_rejects_storage or main_current_storage or separate_execution or process_consumers_converge or source_fingerprint_mismatch or retained_decision_authority or invalid_output_retains or partial_render_exception or invalid_existing_final or cli_restart_preserves' --tb=short
```

**29 passed, 528 deselected** in 13.92 seconds. The final review subsequently added one opener-import failure case and moved
that import into the existing sanitized guard. Final revalidation below covers
that last production/test adjustment.

Revision/packet/approval/security/accounting/application-trap neighborhood (before the final startup guard):

```sh
.venv/bin/pytest -q tests/test_revisions.py tests/test_scheduler.py tests/test_packet_history.py tests/test_packets.py tests/test_packet_chaos.py tests/test_approvals.py tests/test_approval_api.py tests/test_approval_queue.py tests/test_approval_service_unit.py tests/test_database.py tests/test_approval_security.py tests/test_tailscale_api.py tests/test_tailscale_security.py tests/test_apply_submit.py tests/test_apply_handoff.py tests/test_llm.py tests/test_cli_defaults.py
```

**1,476 passed** in 379.72 seconds. No warnings, skips, xfails or failures were
reported by these successful targeted, focused or neighborhood runs.

Established applicable Python compilation/whitespace checks:

```sh
.venv/bin/python -m compileall -q src/job_agent tests
git diff --check
```

Both exit 0 with no output. No Python formatter/linter/type-checker is configured
in the project's established toolchain; none was invented or installed. Frontend
source and its toolchain are unchanged. The untracked report's whitespace is
also checked separately.

Final focused cases after the startup-error adjustment:

```sh
.venv/bin/pytest -q tests/test_revisions.py tests/test_scheduler.py tests/test_packet_history.py tests/test_approval_api.py -k 'real_entry_rejects_storage or storage_opener_import or main_current_storage or separate_execution or process_consumers_converge or source_fingerprint_mismatch or retained_decision_authority or invalid_output_retains or partial_render_exception or invalid_existing_final or cli_restart_preserves' --tb=short
```

**30 passed, 528 deselected** in 13.04 seconds.

Final history/CLI regression:

```sh
.venv/bin/pytest -q tests/test_packet_history.py
```

**79 passed** in 33.92 seconds. No source/test changes follow these runs.

The first complete offline run was already collected before the final startup
adjustment; it passed **2,979 tests, 23 multiprocessing fork deprecation warnings**
in 604.91 seconds. It is supplementary evidence, not the final complete-suite
claim.

The same neighborhood command above was rerun after the final startup guard:
**1,477 passed** in 401.77 seconds, no warnings/skips/xfails/failures. Python
compilation and `git diff --check` were then rerun and both exited 0.

Final complete established offline regression, after all source/test changes:

```sh
.venv/bin/pytest -q
```

**2,980 passed, 23 warnings** in 572.91 seconds (9:32), exit 0. Warnings are
DeprecationWarning from the existing multiprocessing fork tests (7 packet chaos,
12 revision, 4 scheduler) after threaded tests; no failures or skipped tests.
The outside-sandbox executions are
test-only because threaded ASGI and the existing browser suite require that
environment; no new dependency or live provider is bundled into them.

# Known Limitations / Deferred 5D-2 / 5D-3 Work

These are local cooperating Linux processes using the existing flock/SQLite
contract, not distributed workers or isolation from equally privileged hostile
writers. The existing opener assumes trusted configured storage/path namespace.
SQLite and filesystem publication are separate resources. Hard death may leave
private orphan staging files; authenticated retained outputs may be reused, while
ambiguous claims require manual review without deletion/reset. No universal
natural-language truth, historical repair, live provider or real employer claim
is made. HTTP generation integration uses an isolated synthetic ASGI app; browser
behavior remains the existing offline regression contract.

5D-2 history/diff review integration and 5D-3 remaining product work are deferred.
No frontend redesign, deferred cross-device polish, builder configuration,
Tailscale/deployment change, persistent worker or application/outreach work.

# Files Changed

| Classification | Path |
| --- | --- |
| PRODUCTION | `src/job_agent/cli.py` |
| TEST | `tests/test_packet_history.py` |
| TEST | `tests/test_revisions.py` |
| TEST | `tests/test_scheduler.py` |
| TEST | `tests/test_approval_api.py` |
| DOCUMENTATION | `README.md` |
| DOCUMENTATION | `docs/run5d/RUN5D1_EXECUTION_SUCCESSOR_INTEGRITY_REPORT.md` |

Production safety measurement JSON and temporary test storage stay outside the
uncommitted repository manifest. No durable generated/build asset is added.

The existing `tests/test_frontend_decisions_dom.py` capture helper writes to the
historical Run 5C evidence directory when the full offline suite runs. It
regenerated three untracked captures removed in the accepted 5C cleanup and
changed one tracked bootstrap-unavailable PNG. These are traced test-generated
outputs, not 5D implementation evidence. After the final suite, the three
verified untracked generated files were removed:

- `desktop-reject-recorded-1440x900.png`
- `desktop-revise-recorded-1440x900.png`
- `phone-validation-390x844.png`

The tracked `desktop-bootstrap-unavailable-1440x900.png` was restored to its
exact original Git blob, verified byte-identical with SHA-256
`0e725358db1710a10c542bfd51a3ee4beea9957f64b7106fa15fd4694d97d404`.
Generated copies and cleanup hashes are retained only in the temporary
`job-pilot-run5d1-generated-evidence` directory outside the repository. No capture test, frontend source or
accepted design is changed. Final repository GENERATED/REMOVE and UNEXPECTED
classifications contain no remaining paths; no repository EVIDENCE path is added.

# Stop Conditions Encountered

**NONE.** The demonstrated CLI defect was within approved scope. No other
production-source change, architectural exception or material capability gap
was required. Test sandbox escalation followed the established test-only path.

At implementation handoff, the complete uncommitted source/test/documentation
diff was reviewed, the manifest was exactly the seven paths above, and the index
was empty. Branch, HEAD and local origin/main matched the starting checkpoint.
The implementation whitespace check passed. Schema/security/accounting/
application/deployment/frontend, instruction and skill/config paths had no diff.
No real credential or machine-specific production path was introduced, and no
generated/build artifact remained in the manifest.

# Cleanup / Staging Review

Cleanup started on `main` with HEAD and local `origin/main` both still at
`c4a2c7d351e085eb9a6513db943973ad110a321c`, nothing staged, and exactly the seven
intended changed/untracked files. Every candidate file was classified COMMIT;
there were no unexpected or unresolved paths. Existing ignored local data,
dependencies, caches and build outputs remain ignored and are not staged.

Only this report needed cleanup edits: clarify the distinct resume/cover tasks
and per-task concurrency proof, distinguish historical validation and handoff
state from cleanup/staging, remove temporary absolute evidence paths, and state
the implementation-candidate completion status. README accurately describes
the storage contract and needed no cleanup edit. Production and tests are
unchanged during cleanup.

New cleanup validation is limited to working-tree/staged whitespace checks,
report whitespace/privacy/path/conflict scans, exact manifest/content review and
read-only comparison of the retained historical production manifests. Those
manifests match for all 12 measured files, including the documented SQLite
metadata; this is not a new measurement of production files. No pytest suite,
compile check, live provider or production revision execution is rerun during
cleanup. No generated file is removed during cleanup.

The final candidate uses the explicit seven-path manifest above for staging and
Andrew's complete staged-diff review. No intended work remains unstaged and no
unexpected untracked file remains after staging. Staged whitespace checks pass.

NO COMMIT. NO PUSH. NO 5D-2. NO 5D-3. NO FRONTEND REDESIGN.
NO BUILDER-SKILL CHANGES. NO PRODUCTION REVISION EXECUTION. NO EMPLOYER SUBMISSION.

READY FOR ANDREW RUN 5D-1 STAGED-DIFF REVIEW.
