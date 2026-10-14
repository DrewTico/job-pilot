# Run 6B durable trustworthy intake

VERDICT: READY FOR ANDREW RUN 6B STAGED-DIFF REVIEW

Status: existing implementation preserved; the final evidence continuation passed complete offline validation and production safety checks. The uncommitted candidate is prepared for Andrew's staged-diff review under the authorized explicit-path staging gate. No commit or push. Run 6C is not started. Earlier implementation-session records below are historical; the continuation sections record the current checkpoint, with final index status in the durable staged manifest.

## Original implementation recovery checkpoint and rules

VERIFIED_START_SHA: `48368deef6fc329044317eba7e89aa4d55626d94`.

Independent local checks confirmed main, HEAD and origin/main at the supplied checkpoint. The recovery inventory was completely clean: status, name/status diff, diff stat, whitespace check, index and untracked inventory had no entries. There was no partial implementation to overwrite or unrelated work to classify. No fetch, reset, restore, clean, stash, merge or rebase occurred.

Read CLAUDE.md, AGENTS.md, the integration matrix and the committed Run 6A report. The original preflight was read only and had no separate artifact; no such file was sought. The existing approved builder stack remains sufficient: NO NEW SKILL REQUIRED. Codex CLI remains 0.161.0; no builder/dependency installation, update or configuration change. Its version command emitted the existing read-only PATH-alias warning.

## Architecture and demonstrated gaps

Reuse the native JobSource registry, immutable normalized Job, existing filter order, SQLiteSeenCache preparation, JobRepository canonical/source ownership, SearchRun/SearchResult JSON payloads, schema v9, BEGIN IMMEDIATE transaction pattern, scoring fingerprints/claims, packet build/style locks and exact-version packet/decision authority. No competing intake service, framework or database.

Actual code confirmed the two recovery findings: most Job.dedup_key values were company/title/location resemblance, dropping different source requisitions; search.run converted fetch exceptions into zero counts, and the CLI unconditionally published the resulting empty search. Both have focused regression proofs and corrections.

Production CLI discovery now supplies the durable observation/evidence write set to the existing persistence layer. Existing scheduled discovery already delegates to this CLI, so it inherits the intake corrections without new scheduler operations. Existing scoring orchestration remains outside intake. Provider-free operational mode and transport/scheduler improvements remain 6C work.

## Identity and retained duplicate evidence

Logical duplicate observations require exact `source:id`. Different requisitions, locations, internship terms, identity-bearing URLs, namespaces, ambiguous reposts and separate unproven source records survive resemblance. No new cross-source merge is performed. Previously attached identities keep their canonical owner; no historical reassignment or migration.

Within a validated source snapshot, conflicting exact identities quarantine the source as unavailable. FreeHire preserves native IDs byte-for-byte and compares retained full listing claims before description truncation, so different tails cannot hide a conflict. Conflicting normalized claims across configured lanes abort preparation before durable writes. Identical occurrences produce one candidate and retain each lane/locator/snapshot occurrence. FreeHire US and relocation observations share its public_slug source identity but preserve separate original query parameters.

A changed company or posting/apply URL against durable or legacy ownership, or changed title/location/term/category claims for a URL-derived Simplify identity, retains its original canonical owner and adds persistent `identity_changed_requires_review` with unresolved disposition. It cannot inherit downstream work/authority automatically. This is conservative quarantine, not proof that a new opportunity is equivalent. There is no automatic release/reassignment workflow in this milestone.

## Observations, lifecycle and completeness

Version `durable-intake-v1` stores all validated observations, including candidates rejected before scoring, in SearchRun JSON. Accepted results additionally retain admission reasons and an observation-run reference in SearchResult. Run 6A IntakeEvidence remains intact, including raw occurrences, derived identity, links, relative Age, flags, explicit nulls, source version and provenance. Its compatible kept/rejected labels do not replace the stronger accepted/rejected/unresolved durable disposition.

First-seen is stable in the durable writer. Last-seen advances only from valid observation timestamps; for offline snapshots it uses the actual snapshot observation time, not the refresh clock. Out-of-order observations fail atomically. Repeats are previously_seen; changed normalized jobs, retained full descriptions, source Age/term/category claims or source state are changed; new identities are newly_discovered. Earlier payloads are never rewritten by intake. Scoring's existing mutable assessment fields remain separate from source evidence.

Availability and freshness are distinct fields. Availability is observed, not_observed_complete, source_unavailable or incomplete_unknown. Complete absence requires every retained lane for that identity to be queried successfully with asserted complete coverage newer than its last valid observation. An outage or partial result cannot undo that admission decision; only a genuinely newer valid observation restores consideration. Historical positive snapshots remain unresolved after newer absence, and historical empty snapshots cannot replace newer useful results. Missing lanes/pages, partial results and outages cannot establish closure. A closed/inactive state requires an explicit typed adapter assertion; no adapter guesses it from absence, Age, lock icons or source-family names. Controlled tests prove both explicit markers. Current FreeHire and Simplify adapters do not invent an unsupported status mapping.

The explicit staleness policy is more than 30 days since the last valid observation. It is a local review/admission policy, never an employer-closure claim. Unobserved evidence inside that interval remains unknown. Listing recency remains the existing configurable freshness filter, with posted_at or stable first-observed basis and retained rejection reason. Simplify relative Age never becomes posted_at.

Coverage is complete, partial, unknown or unavailable per configured lane, with observation time, snapshot digest, row count and sanitized rejected-row issues. FreeHire is always partial because limit=100/offset=0 is one bounded page. Other native adapters without an explicit completeness contract remain unknown. A successful HTTP request or small row count is insufficient proof of exhaustive coverage.

## Publication and durability

An incomplete empty candidate set records an unpublished attempt and preserves the previous published search, including all-source failure. Healthy candidates can publish despite another unavailable lane, with partial completeness and warnings. A validated complete zero-candidate search publishes a truthful empty view. The published generated_at remains the prior time after a failed attempt; attempt details are retained in SearchRun history rather than rewriting that prior search.

prepare_intake validates identity/job/evidence agreement, filter disposition, occurrence coverage/time/digest, result membership, source markers and bounds before writing. Its immutable serialized body excludes cache-derived newness hints. Semantic run identity binds the observation/assessment write set and the existing scoring context. Scoring fingerprints and pending reservation costs are prepared before the writer begins; private candidate text is not added to durable intake metadata.

commit_intake revalidates the prepared fingerprint, then reuses BEGIN IMMEDIATE to reconcile current ownership/newness and atomically write canonical identities, historical observations, SearchRun, SearchResult and optional existing scoring queue references. There is no fetch, enrichment, model/provider request, employer operation or research inside this transaction. Replay returns the existing run; simultaneous consumers converge on one owner and the correct result uniqueness. A new valid refresh can append history without creating repeated paid-work fingerprints. Rollback and KeyboardInterrupt preserve earlier valid records.

Bounds: 10,000 fetched occurrences/identities per prepared intake, 16 MiB prepared/final durable payload, 16,384 characters per retained original listing, and the Run 6A field/URL bounds. Lifecycle reconciliation is also limited to 10,000 stored identities, failing atomically beyond that bound rather than silently truncating history. This lifetime bound and JSON history lookup cost are explicit current limits; larger-scale indexing/paging needs a separately reviewed design, not an unapproved schema change here.

## Filtering, downstream admission and authority

Filter order remains keyword, freshness, location, seniority, exact-identity dedup, enrichment, eligibility restrictions and experience. Explicit source inactive markers add a final deterministic rejection. Each observation retains checks performed, the first rejecting stage and reasons. FreeHire eligibility/experience gates inspect its bounded retained full description, including restrictions beyond the existing scoring-text cap; normalized scoring inputs and model weights remain unchanged. Unavailable enrichment or suspicious content stays unresolved for review. Accepted means accepted for downstream consideration; eligibility remains null. No restrictions found is not validated eligibility, citizenship, sponsorship, graduation or compensation acceptance.

Scoring planning, serialized standard claims and pending batch admission check retained intake evidence and immutable packet Reject decisions. Pending work blocked by later rejection does not reach the provider or reserve a new model call. Existing unique scoring and writing fingerprints, paid-work claims and packet fingerprints retain their responsibilities; intake never generates a packet or paid output.

Packet selection and build admission check current observation agreement, latest deterministic disposition, explicit complete absence, identity review, staleness and human Reject history before company research or paid writing. An older high-scored SearchResult cannot bypass a later filter rejection. A reappeared rejected source cannot produce a new packet solely by reappearing. The existing explicit damaged-artifact recovery path is preserved for the exact original source row: it authenticates retained facts/style and cached paid outputs, performs no research or fresh paid generation, refuses replayed source rows or changed inputs, and gives the successor no predecessor approval. Automatic selection remains blocked. The original independent HTTP approval regression is unchanged. Existing exact packet/version/approval fingerprints, artifact integrity, private Tailscale identity, Host/Origin/CSRF rules and immutable decisions are unchanged. No approval transfers across opportunities.

## FreeHire and offline Simplify compatibility

FreeHire remains supported. No extra request, pagination, scraper redesign or external traffic was introduced. Improvements cover unchanged native public_slug identity, one-page partial coverage, full retained listing claims, source snapshot hash, original per-lane query parameters, rejected-row disclosure, URL/field/body bounds, historical decisions and durable replay. Failure is distinct from an empty bounded response; neither is promoted to a complete source snapshot.

Both simplify-newgrad and simplify-internships have offline durability/provenance round-trip tests using authored fixtures and controlled adapters. Versioned source-scoped IDs, source/role/application URLs, snapshot hashes/revisions, company/title/location, relative Age, null semantics and security flags survive. Source adapters still require an explicit OfflineSnapshot, and ordinary factory use fails with offline_snapshot_required.

SIMPLIFYJOBS NOT PRODUCTION-ENABLED. Live adoption still requires current format/contract stability, licensing/reuse/permission review, useful unique yield, bounded transport and explicit accepted enablement. No live snapshot was fetched or permission inferred from public visibility.

## Security and side effects

External source content remains inert untrusted data. Run 6A URL/HTML safety is reused; unsafe URLs, controls, oversized fields and malformed write sets fail closed. Source exception bodies are omitted. The existing context-local private diagnostic boundary redacts SQL/SDK logs during durable writes, including DEBUG payload diagnostics; SQLite exceptions are sanitized after rollback. No complete source body, private candidate facts or secrets are logged by the new writer.

Tests cover conflicts, oversized/unsafe records, malicious instructions, incomplete/unknown coverage, timeout/rate-limit/outage behavior, stale snapshots, invalid markers, all-source and lane failures, rollback, restart, replay, concurrency, SQL diagnostic privacy, duplicate admission pressure and zero consequential intake side effects. Consequential-entry-point traps and temporary-table assertions prove no intake-created packets, model calls, decisions or application events. Existing isolated loopback browser and fake-provider tests remain test-only.

NO SCHEMA CHANGE: database.py, schema version and production SQL definitions are unchanged; temporary schema identity proofs pass. The deliberate SQLite fault test installs and removes a test trigger only in its temporary database. No production database connection, initialization or SearchRun was created by this implementation session.

## Red/green record

This section preserves the original implementation report's development history. Intermediate counts and `/tmp` artifact references are historical report entries, not newly recovered raw logs or additional acceptance evidence from this continuation. The independently recovered completed validation findings are identified in the following section.

- Initial gap tests: 5 failed, demonstrating lost requisitions, identity conflicts, missing decisions, source exception-body exposure and missing publication completeness.
- First implementation compatibility run: 5 failed, 140 passed. Corrected first-occurrence ordering, compatible partial/failure warning detail and legacy cache writes. The existing dedup fixture used different requisition IDs as a supposed duplicate; it now repeats the same ID while retaining all original stage assertions. Distinct requisitions have a separate preservation proof. Then 145 passed.
- New persistence tests: 5 failed, 5 passed before persist_intake existed. After implementation: 1 failed, 9 passed because SearchRun's jobs map omitted result admission additions. Corrected the consistent payload; later relevant compatibility suite passed 323.
- FreeHire proofs: 3 failed before partial coverage/raw records/rejected-row handling; corrected and later source-focused compatibility passed 243.
- A new multi-location fixture initially chose Canada, correctly triggering the existing US location filter. Corrected it to a second US location; this was a fixture issue, not a dedup implementation failure.
- Broad regression: 1 failed, 969 passed; an added admission check consumed the fixed packet clock and broke the established midnight-capacity test. Corrected by sampling the clock lazily only for durable evidence; existing test unchanged.
- Stale-snapshot and untruncated-claim assertions failed genuinely and were corrected. A third failure in that run used a model alias without verified pricing; corrected the fixture to the already supported versioned model, without changing pricing or installing anything.
- Directly forged prepared body failed with KeyError rather than a sanitized rejection; corrected pretransaction validation.
- Two paid-admission assertions failed: standard claims and already-queued scoring could bypass later intake rejection. Added checks at those existing serialized admission boundaries; both now pass without invoking a real provider.
- Replay/scoring-context assertion failed because equal observations with different explicit scoring contexts reused one run. Bind the existing context fingerprint and precomputed plans; the focused intake/batch suite then passed 100.
- Late lifecycle edge review: one outage-after-absence assertion failed, then two historical positive/empty snapshot assertions failed. Corrected the retained absence decision and capture-time comparisons, including publication protection. These are genuine corrections, not fixture changes.
- Final native-identity and full-description review: a public_slug preservation assertion failed because an unnecessary trim could rekey existing identities. Preserve the committed native ID contract without migration. Two further assertions exposed clearance/experience restrictions beyond the scoring text cap; use bounded retained full description for those existing deterministic filters, preserving scoring inputs.
- A derived-URL internship-term reuse assertion failed: a changed term could retain automatic admission under the old URL-derived identity. Quarantine changed derived title/location/term/category evidence as unresolved while preserving canonical ownership; no historical reassignment or migration.
- Full-description change classification: two stronger assertions failed because changed source tails were classified previously_seen after normalized truncation. Compare retained source claims as well as normalized Jobs. The first harness attempt read the preserved published search rather than the unpublished rejected attempt; corrected that read before recording the genuine failures.
- Completed full regression exposed one Run 5 compatibility failure: 1 failed, 3,200 passed, 23 existing fork warnings in 902.93 seconds, exit 1. `test_successor_independent_http_approval` requires explicit recovery of a damaged rejected packet and separate successor approval. The new global Reject gate was too broad. Preserve exact-owned-row artifact repair using authenticated cached writing and retained facts, while refusing automatic readmission, replayed rows, changed inputs and fresh research/generation. The unchanged Run 5 recovery/approval suite passed 744 tests; the intake/packet/Tailscale suite passed 294. A new repair-only proof failed before the correction; new replay/style/input guards pass. Failed full log: `/tmp/job-pilot-run6b-failed-full-pytest.log`. The required final full regression follows this demonstrated correction; the failed run is not presented as successful or summed with it.
- Immediate passing proofs include preserved canonical ownership, offline Simplify provenance, unknown eligibility, valid zero results, rollback/restart, concurrent ownership, malicious content review, URL safety, temporary schema identity and zero consequential intake side effects.

One sandbox compatibility attempt stalled at the existing ASGI worker-thread boundary documented by Run 6A and was interrupted (exit 130, no completed count). The same tests passed outside that restriction. This incomplete attempt is not successful validation. No existing assertion was weakened to manufacture green. An initial full-suite attempt reached 49% without reported assertion failures, then was interrupted for the demonstrated outage-after-absence gap. Exit 130 during browser teardown, with no completed summary/count; log retained at `/tmp/job-pilot-run6b-incomplete-full-pytest.log`. Starting that attempt before lifecycle edge review was fully finished was a sequencing mistake. It is not counted as a completed full regression. The sole completed full run on the final candidate follows all demonstrated corrections and final focused regression. The additional completed but failed full candidate run is recorded below.

## Recovered historical completed validation

Final focused compatibility command:

```sh
.venv/bin/pytest -q tests/test_durable_intake.py tests/test_sources.py tests/test_freehire.py tests/test_simplify.py tests/test_search.py tests/test_search_state.py tests/test_database.py tests/test_search_import.py tests/test_batch.py tests/test_packets.py tests/test_packet_chaos.py tests/test_scheduler.py tests/test_approval_security.py tests/test_tailscale_security.py tests/test_tailscale_api.py tests/test_revisions.py tests/test_approvals.py --tb=short
```

Result: 1,582 passed in 284.24 seconds, exit 0, no warning summary. This includes all 59 new durable-intake tests plus the six packet admission/recovery regression cases. Counts overlap all intermediate suites and must not be added.

Compile check: `.venv/bin/python -m compileall -q src/job_agent tests/test_durable_intake.py tests/test_packets.py tests/test_search.py`, exit 0. `git diff --check`, exit 0. No established Python static/type-check command exists in pyproject; no new tool was installed.

Historical full offline regression: `.venv/bin/pytest -q`, **3,205 passed, 23 warnings**, 840.88 seconds (14:00), exit 0; no failures or skips. Warnings were the multiprocessing/fork cases: 7 packet chaos, 12 revisions, 4 scheduler. This was the completed passing full run in the original implementation session. The prior audit recovered original Codex execution evidence supporting this count and the focused 1,582 result. The earlier **3,285 claim is unsupported and withdrawn**; it is not another passing run and must not be substituted or added to other counts. The original complete raw log at the reported `/tmp/job-pilot-run6b-full-pytest.log` is unavailable. No raw transcript has been manufactured or reconstructed. Historical Run 6A counts are not current validation.

Recovered session evidence is retained as the supplied, verified continuation findings: original full command, 3,205 passes, 23 warnings and exit 0; original focused command above, 1,582 passes and exit 0. The continuation does not include original session identifiers or raw tool-record excerpts, so none is invented. `historical-validation.json` in the persistent evidence directory records that source and limitation.

## Historical production-data measurements

Before tests, the configured production root was resolved read only through existing settings; secrets were not printed. SHA-256, size, device, inode and mtime_ns were recorded for all 12 regular files. SQLite was read as bytes, never opened through a writable database connection.

Before manifest: `/tmp/job-pilot-run6b-production-before.json`.

SQLite before: 241,664 bytes; SHA-256 `da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`; device 2096; inode 216020; mtime_ns 1791404174236327816.

The original report recorded that all 12 files and the complete inventory matched exactly after the full regression, including SHA-256, size, device, inode and mtime_ns. Reported after manifest: `/tmp/job-pilot-run6b-production-after.json`. These complete historical manifests are unavailable to this continuation. The documented SQLite baseline is independently supported by the committed Run 6A report. Fresh measurements below verify the current production files and this continuation's own test run; they do not retroactively reconstruct the historical inventories or prove every historical file comparison.

## Original candidate manifest and self-review

| Classification | Path |
| --- | --- |
| PRODUCTION | src/job_agent/models.py |
| PRODUCTION | src/job_agent/search.py |
| PRODUCTION | src/job_agent/search_state.py |
| PRODUCTION | src/job_agent/sources/base.py |
| PRODUCTION | src/job_agent/sources/freehire.py |
| PRODUCTION | src/job_agent/batch.py |
| PRODUCTION | src/job_agent/cli.py |
| PRODUCTION | src/job_agent/packets.py |
| TEST | tests/test_durable_intake.py (new) |
| TEST | tests/test_search.py |
| TEST | tests/test_packets.py |
| DOCUMENTATION | docs/run6/RUN6B_DURABLE_TRUSTWORTHY_INTAKE_REPORT.md (new) |

Reviewed the complete production diff, new tests and callers for historical reassignment, lost evidence, false closure/freshness/eligibility, duplicate paid work, authority weakening, live source enablement, dependency/schema changes, private data, unrelated frontend work and employer behavior. None is authorized or introduced. The pre-full-run screenshot inventory preserved all 18 existing test-owned PNGs under /tmp; all 18 PNGs now match those measured pre-run bytes after regression. No user work is involved.

Final artifact classification: four tracked test-produced PNG changes were returned to their preserved before bytes; three new test-produced PNGs (desktop-reject-recorded-1440x900, desktop-revise-recorded-1440x900, phone-validation-390x844) were archived under `/tmp/job-pilot-run6b-generated-screenshots` and removed from the repository. Their producer is tests/test_frontend_decisions_dom.py. No unrelated file was reset, restored or deleted. No generated artifact remains in the candidate.

Original implementation-session Git state: main; HEAD and local origin/main equal VERIFIED_START_SHA. Ten intended tracked paths modified and two new paths untracked. Index empty at that checkpoint. The final continuation's authorized staging and current Git state are recorded separately below.

Final tracked diff stat (the new test/report files are additional untracked outputs):

```text
 src/job_agent/batch.py            |  23 ++-
 src/job_agent/cli.py              |  49 +++--
 src/job_agent/models.py           |  50 +++++-
 src/job_agent/packets.py          |  90 +++++++++-
 src/job_agent/search.py           | 294 +++++++++++++++++++-----------
 src/job_agent/search_state.py     | 365 +++++++++++++++++++++++++++++++++++++-
 src/job_agent/sources/base.py     |   4 +-
 src/job_agent/sources/freehire.py |  55 +++++-
 tests/test_packets.py             |  93 ++++++++++
 tests/test_search.py              |   4 +-
 10 files changed, 886 insertions(+), 141 deletions(-)
```

## Limitations, deferred work and next step

Native sources lacking asserted coverage stay unknown; FreeHire stays first-page partial. No DNS/destination-resolution or bounded operational transport redesign, retries, provider-free command mode, source metrics/status UI, live source benchmarking/acceptance, licensing adoption, identity-review release workflow or large-scale historical indexing is claimed. No historical identity backfill or reassignment. Explicit source states need a validated adapter contract; icons/absence are insufficient. Existing source evidence is retained by domain writes, not by new schema triggers.

Run 6C remains not started: provider-free operation, accepted live enablement, bounded transport and destination resolution, operational source metrics/status and scheduling improvements remain deferred. PinchTab remains an optional Run 8 evaluation candidate; it was not installed or evaluated.

Andrew's final evidence continuation authorizes staging the explicit Run 6B paths only after every gate passes. It does not authorize commit or push. No schema, production mutation, history destruction, decision weakening, proven-equivalence shortcut, new dependency or outbound action is required. NO COMMIT. NO PUSH. NO RUN 6C. NO LIVE SOURCE ENABLEMENT. NO SCHEMA CHANGE. NO PRODUCTION DATA MUTATION. NO PAID/MODEL/PROVIDER CALLS. NO APPLICATION SUBMISSION. NO OUTREACH.

## Final evidence continuation and durable storage

The supplied absolute directory is `/home/andrew/.local/state/job-pilot/run6b-evidence`; it was read directly from Andrew's prompt, without assuming an environment variable. The actual command environment first returned `OSError: [Errno 30] Read-only file system`. A narrowly scoped one-time escalated probe then created, read and removed a harmless file successfully. The successful execution record is chunk `24663d`, exit 0. Global sandbox settings were not changed. Consequential records use this directory, with one-time permission for their writes, rather than `/tmp` storage.

The starting checks confirmed main, HEAD equal to local origin/main, subject `feat: add Run 6A source provenance`, an empty index, ten intended modified paths and exactly the two intended new files. Commit values in `candidate-before.json` were derived from Git. No historical evidence search was repeated. No existing code or test implementation was changed by this continuation.

Although the report's file manifest and diff sizes match the current candidate, there is no independently retained tested-candidate byte fingerprint in the supplied recovery findings. The historical result cannot reliably be bound to the exact present bytes. For that reason, one fresh complete offline regression was announced and started, with its full stdout/stderr, exit code and candidate hashes captured durably. Missing raw output alone was not the reason for rerunning. No additional full regression or repeat focused suite is planned after a passing result.

Fresh command: `.venv/bin/pytest -q`. Command-execution session: `47683`, completed output chunk `d6e7c4`, exit 0; launcher PID 5236, pytest PID 5247. Start: `2026-10-14T01:39:52.732850+00:00`; finish: `2026-10-14T01:55:16.466962+00:00`. **3,205 passed, 23 warnings in 914.33 seconds**, with no failures or skips. The wrapper's wall time was 923.73 seconds. Warnings remain 7 packet-chaos, 12 revisions and 4 scheduler multiprocessing/fork deprecations, without suppression. The full original output of this new execution is `full-offline-pytest.log`; `full-offline-result.json` records the command, timestamps, exit and log SHA-256. `parsed-regression-summary.json` records the actual summary. This is additional independent validation, not a reconstruction of the missing historical raw log, and its count is not added to the historical counts.

`candidate-before.json` binds the tested implementation and test bytes. After completion, all 11 implementation/test files matched those exact hashes, recorded in `candidate-binding.json`; only this documentation correction was excluded. No code fix was required and no passing focused suite was repeated. Compile and whitespace checks passed, with their commands and exit codes in `static-checks.json`.

Fresh production inventory: 12 regular files, no SQLite writable connection. The SQLite SHA-256, 241,664-byte size, device 2096, inode 216020 and mtime_ns 1791404174236327816 all match the documented baseline above and the committed Run 6A report. `production-before.json` records every current file; `production-historical-comparison.json` distinguishes supported baseline fields from missing historical manifests. The actual `production-after.json` and `production-before-after.json` prove exact before/after equality for all 12 files, including SHA-256, size, device, inode, mtime_ns and inventory. Added, removed and changed production files: none. This measurement belongs to the new run only.

Three tracked test-written PNGs (phone-approval-recorded-390x844, phone-reject-recorded-390x844, phone-revise-recorded-390x844) were archived and restored to their exact pre-run bytes. Three generated PNGs (desktop-reject-recorded-1440x900, desktop-revise-recorded-1440x900, phone-validation-390x844) were archived and removed from the repository. Their producer is `tests/test_frontend_decisions_dom.py`. All existing Run 5C artifact bytes match the durable pre-test backup, including its JSON files. `test-artifact-cleanup.json` records that classification and restoration; `pretest-run5c-artifacts/` and `generated-run5c-artifacts/` retain the evidence. No unrelated file was restored or removed.

## Final security and correctness audit

| Review | Conclusion and concrete evidence |
| --- | --- |
| Run 5 rejected-artifact recovery | Normal selection still blocks immutable Reject history. Explicit repair binds `search_result_id`, exact job key, canonical owner and a completed predecessor. `_retained_packet_evidence` authenticates scoring and company facts; request fingerprints, models, prompt/style, output hashes and screening evidence must match. A valid rejected packet returns no repair admission. A damaged packet first becomes `recovery_required`; its successor uses cached writing and retained facts. Replay rows, changed style and changed writing inputs are refused. The unchanged `test_successor_independent_http_approval` verifies the successor starts unapproved and needs its own exact HTTP approval. No predecessor decision or approval transfers. |
| Run 6B packet admission | Current normalized job agreement, accepted deterministic disposition, identity quarantine, complete absence, staleness and immutable Reject checks precede research. Admission is checked again in the serialized packet claim. Repair waives only the human-Reject admission check after authenticating its repair inputs; deterministic intake, ownership, score, terminal application state and identity gates remain active. |
| Durable deduplication and lifecycle | Exact source IDs keep distinct requisitions and namespaces; duplicate occurrences retain lane evidence. Existing canonical ownership is preserved. Changed identity claims remain quarantined. Complete absence requires all retained lanes with newer complete coverage. Partial pages, unknown coverage and outages cannot prove closure or undo complete absence. Old snapshots cannot restore admission after newer absence or replace a newer useful view. |
| Atomicity, replay and concurrency | Preparation validates and bounds the immutable write set and precomputes existing scoring plans outside the writer. `BEGIN IMMEDIATE` serializes ownership and writes identities, observations, runs, results and queue references in one transaction. Semantic replay includes scoring context. Fault, SQLite-trigger and KeyboardInterrupt proofs cover rollback; concurrent same-run and distinct-refresh tests cover one owner and result uniqueness. Existing packet build/style locks and atomic publication remain in use. |
| FreeHire provenance and completeness | Native `public_slug` is preserved byte-for-byte. Full bounded retained listing claims detect conflicting or changed tails and control deterministic restriction filters. Request parameters, hashes and rejected-row issues survive. Limit 100/offset 0 always remains partial. No extra network request or live enablement was introduced. |
| SimplifyJobs offline compatibility | Both source namespaces round-trip authored offline fixtures with IDs, URLs, hashes, revision, nulls, relative Age and flags. Relative Age never becomes `posted_at`. Factory construction still requires an explicit offline snapshot. No live source or licensing permission was inferred. |
| Schema v9 and side effects | `database.py`, schema definitions, dependencies and migration files are outside the candidate. Temporary-schema SQL and `user_version == 9` proofs remain. Intake tests trap sockets, Anthropic construction, packet construction and submission, and assert no packet, decision, application-event, model-call or unrequested scoring-work rows. Full browser/provider compatibility tests remain synthetic and isolated. |
| Privacy and complete diff | All eight production diffs, all three test files and the full report were inspected. Source exceptions omit bodies; durable writes reuse SQL/SDK diagnostic redaction and sanitize SQLite errors. No candidate facts or secrets were added to intake metadata or evidence records. `.env` remains ignored. Rules, architecture, approvals, outreach, schema, dependencies and live profiles were unchanged. No demonstrated defect required a code change. |

Limits remain explicit: 10,000 identities and JSON-history lookup cost; bounded first-page FreeHire coverage; unknown completeness for adapters without a coverage contract; no automatic identity-review release; no transport/DNS redesign or live contract/licensing acceptance. These proofs concern supported application entry points and isolated tests, not arbitrary malicious concurrent edits to the local database. Existing fork warnings will be recorded without suppression.

## Final staging and evidence review checkpoint

Every remaining changed or untracked path is classified in the 12-file candidate manifest above: eight production, three tests and one documentation file. No unexpected candidate file remains. All validation and safety gates passed before staging. Staging is restricted to those explicit paths, with no `git add .` or `git add -A`. No commit or push is authorized.

`staged-manifest.json` records the completed final index, Git-derived branch/HEAD/origin/main, per-file classification and SHA-256, and absence of unstaged/unexpected untracked work. `staged-diff.patch` contains the entire staged diff for review; `audit-record.md` is the final report copy. Final inspection covers the complete staged production, test and documentation diff and whitespace check. `evidence-integrity.json` records actual command-environment readability and hashes of the persistent artifacts. Readability is verified again after writing the final records, before the final success verdict. The original missing logs/manifests and absent original session identifiers remain declared limitations; new evidence does not erase those limitations. Andrew reviews the staged candidate next. No unresolved correctness or safety blocker was demonstrated in this continuation.

## Proposed permanent evidence policy (not adopted)

Proposed for Andrew's separate approval: before mutation-capable validation, resolve and probe an explicit durable evidence directory that survives nightly WSL restarts. Persist the exact command, UTC times, execution-session identifiers, full raw stdout/stderr, exit code, Git-derived HEAD/base values, candidate file hashes and diff, and actual read-only production before/after inventories. Verify every consequential artifact is readable before claiming success or staging. Use `/tmp` only for disposable scratch, never the sole validation evidence. Retain interrupted/failed records with their true exit and limitations; never reconstruct missing raw transcripts. Evidence must respect existing privacy and diagnostic-redaction rules; never copy secrets or OAuth tokens into validation records. This checkpoint records the proposal only. `CLAUDE.md` and `AGENTS.md` are unchanged.
