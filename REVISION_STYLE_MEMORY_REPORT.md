# Run 2 revision, style memory and versioned regeneration report

## Final integration result

Run 2 backend implementation and the complete established offline suite are
complete. The sections following this consolidated report retain historical
milestone evidence; their pending-work statements describe those earlier dates,
not the final state. Starting HEAD was `0f0ec1b fix: block candidate-name authority
in company facts`, with a clean working tree. HEAD is unchanged and all work is
uncommitted. No dependency was installed, no live service was used, and nothing
was pushed. Production changes stay within the original authorized file scope.

The established offline suite passed **2,348 tests**: **2,189** sandbox-compatible
tests in 273.63 seconds and **159** Chromium/FastAPI tests in 16.13 seconds. The
two disjoint selections cover all 2,348 cases confirmed by final collection.
Warnings / skips / xfails: **0 / 0 / 0**. Andrew explicitly approved the exact
outside-sandbox TEST-ONLY command before execution. The command was:

```sh
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py
```

Chromium launch and FastAPI TestClient require that existing outside-sandbox
split; these were offline fixture/local tests, not live application submission.
The final sandbox selection excluded exactly these ten files. No production
Python changed between its passing run and the passing complementary run.

### Schema, constraints and migration

Schema is **v9**. `style_memory_snapshots` stores hash (64 lowercase SHA-256 hex
primary key), exact canonical_content (NOT NULL, at most 65,536 UTF-8 bytes),
canonicalization_version (`style-nfc-lf-v1`) and UTC created_at metadata. Timestamp
is excluded from identity. Every service load checks canonical content/version
and recomputes SHA-256; mismatches fail closed. Persistent guards reject UPDATE,
DELETE and INSERT OR REPLACE of existing identities. Retained content is private
local preference data intentionally stored because hashes cannot reconstruct
historical prompts.

`ApplicationPacket` adds NOT NULL writing_prompt_version, nullable snapshot FK
style_memory_hash, and nullable unique decision FK revision_decision_id. CHECKs
and persistent INSERT/UPDATE guards enforce only v4/NULL or v5/non-NULL pairings.
Revision links require a supported immutable Andrew Revise record, exact source
fingerprint, same logical job and higher version. Writing/style/decision bindings
are immutable; replacement of revision successor identities is rejected.

`packet_revision_work` stores decision_id (PK/decision FK), state, base_style_hash
and target_style_hash (snapshot FKs), successor_packet_id (unique packet FK), UTC
created_at/updated_at and sanitized failure_code. Supported states are pending,
style_prepared, style_persisted, building, succeeded, blocked and recovery_required.
CHECKs enforce paired/required hashes, pending without bindings, building/succeeded
with successor and bounded machine codes. Relational triggers enforce a Revise
source, exact target/successor/decision/job/version relationships and ready
successor/ready_at for succeeded. Identity guards prevent switching bound hashes,
decision or successor. Transition guards permit operational changes; deletion
and replacement cannot erase idempotency evidence. Work is not append-only.

The v8-to-v9 migration is additive, in the existing BEGIN IMMEDIATE transaction,
without rebuilding old packet tables. Existing packets receive exact v4/NULL/NULL
bindings; no synthetic snapshot, fingerprint repair or evidence rewrite occurs.
Old data, indexes and triggers, including decision immutability, are preserved.
The genuine pre-change initializer fixture remains unchanged, SHA-256
`cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e`.
Three populated-v8 migration/rollback cases cover normal migration, injected
exception and actual process death after DDL/backfill before version bump. They
compare all original columns across thirteen tables and the exact original
schema/index/trigger definitions. Rollback restores exact valid v8 state; migrated
state is v9, foreign_key_check is clean, and new tables are initially empty.
Future schema versions fail closed. Direct DB red-team cases reject malformed
snapshots, unsupported versions/pairings, non-Revise links, duplicate successors,
wrong jobs/styles and non-ready succeeded work.

### Canonical style, publication and prompt identity

The user-approved canonicalizer decodes strict UTF-8, removes ALL consecutive
leading U+FEFF characters, converts CRLF then remaining CR to LF, normalizes NFC
and preserves every other character, including spaces/tabs/Markdown/blank lines,
embedded BOM, NUL and terminal newline presence. It is idempotent and never adds
a BOM or newline. Canonical bytes are limited to 65,536; raw input is bounded to
131,072 before decoding. Overflow is rejected without truncation. SHA-256 covers
the exact resulting UTF-8 bytes.

Absent style_memory.md reads empty without creating that file. Exact-name,
directory-constrained no-follow reads reject unsafe paths, symlinks, special or
nonprivate files. Cooperating readers take shared style_memory.lock; writers
take exclusive lock. Lock order is build -> style -> short DB transaction.
Publication writes/fsyncs a private same-directory temporary file, rechecks
destination/base safety, atomically replaces and fsyncs the directory. Readers
see whole old/new content. Unknown intervening content causes style_conflict
without overwrite. Style locks and transactions never span provider I/O.

Each entry has deterministic compact sorted JSON metadata: timestamp_utc, company,
title, source_packet_id/version, decision_id and feedback_utf8_bytes. Metadata is
escaped; feedback body retains exact canonical text. Outside separators are not
byte-counted. Marker-like text and NUL cannot confuse framing. Original decision
detail stays unchanged. Duplicate prevention comes from work and retained target
identity, never searching natural-language Markdown for decision IDs.

Legacy `v4-semantic-writing-cache` packets reconstruct exact original requests,
spacing, order, serialization and fingerprints with no style read or section.
Genuine pre-change packet/Approve evidence verifies after migration with nonempty
current style and a trap against reading it. New ordinary/revision packets use
`v5-style-memory-snapshot` and a non-NULL retained snapshot, including empty style.
Historical v5 reconstruction loads that exact snapshot, never mutable style.
Style edits alone cannot invalidate surviving historical writing identity;
current authoritative candidate truth/policy checks still apply.

Both v5 SYSTEM messages put explicit untrusted STYLE DATA instructions before
approved candidate facts, exact snapshot data and a fixed authoritative closing
reminder. Job-specific untrusted context stays in USER. Style guides wording,
selection and order only; facts, schema, lint, policies and actions remain gated.
`cached_system` is unchanged and useful for fixed version/facts/policy/snapshot.
There is no style-analysis call or provider transport redesign. Packet context
adds prompt version/canonicalization version/style hash. Writing fingerprints
retain task, model, system digest, user digest, prompt version and max tokens.
Style naturally changes system digests; packet/version/decision IDs are not extra
paid-request inputs. Canonical-equivalent styles retain request semantics.

### Revision lifecycle and authorization

`process_revision(decision_id)` proves immutable Revise/actor/policy/source/detail
bindings, creates/reuses one work row under the build lock, then prepares exact
base/target snapshots under exclusive style lock. It commits style_prepared
before filesystem replacement. Restart publishes retained target if current
equals base, recognizes already-published target, or blocks on third content.
It marks style_persisted and releases the style lock before successor work.
SQLite and filesystem are separate resources; the durable hashes/content bridge
their commits. Later edits do not recapture a prepared target or reappend feedback.

Feedback is saved even when source artifacts are damaged. Successor generation
requires locally valid retained job/scoring/company evidence, fact count/IDs/order,
safe sources/titles and exact bound predecessor cover USER request identity.
It never instantiates a production researcher, calls Tavily, refreshes expired
cache or uses company authority for candidate claims. Invalid retained evidence
blocks generation after feedback may have persisted.

Current facts.yaml/answer_bank.yaml are loaded before successor claim. Distinct
revision-v1 identity binds source ID/fingerprint, decision ID and current v5
context (truth, answers, retained evidence, models/policies/limits/style). One
short transaction allocates max version + 1 and links work/successor/decision.
Restart compares current context to the claimed fingerprint; later meaningful
candidate changes block rather than mutate that successor. It does not reuse
the corruption-recovery wrapper. Each successor has its own ID/fingerprint/path,
higher version, target snapshot and no decision. Predecessor packet, decision
and artifacts remain historical. v1 Revise never authorizes v2; each successor
requires independent future approval. A new Revise on v2 can produce v3.

Only this immutable-decision-validated allocation path sets capacity_day NULL;
there is no generic bypass parameter. Ordinary builds still reserve daily new-job
capacity. Normal _write_call/WritingWorkItem/AnthropicExecutor, llm_calls, monthly
budget and cache-token accounting apply. Exhausted budget blocks new admission;
matching succeeded requests may finish locally. Failed admission claims are not
reset when budget changes. Ambiguous provider outcomes remain recovery_required
without blind retry or duplicate paid calls. budget_blocked uses the existing
admission_denied classification, also covering unknown model pricing.

Assembly reuses existing writing gates, staging, authenticated publication and
integrity verification. Ready successors are reread/authenticated before marking
work succeeded. Success replay authenticates surviving output too. Failures are
sanitized machine codes; no raw private/provider errors are retained or logged.
Blocked/recovery_required work does not automatically reset on replay.

### Historical views, concurrency and privacy

Read-only list_packet_versions follows stored job/canonical aliases and sorts
version ASC then ID. It returns safe metadata, own decision and provable revision
or corruption-recovery linkage, with latest allocated separate from latest ready.
Failed newer rows do not hide earlier ready versions. It exposes no feedback,
style content, prompt, secret or filesystem path and never calls providers.

Resume diff uses authenticated resume.face.txt, manifest hash/size, safe regular
no-follow descriptor reads and local PDF/DOCX consistency, without OCR. Cover diff
authenticates successful bound checkpoint/request/output hash and exact validated
draft/stored-text relationship. Neither needs current eligibility/truth to show
historical content. Missing/damaged content returns unavailable/integrity_failed,
never reconstruction from another version. Unified diffs preserve terminal-newline
differences and label only packet/version identity. Diff/history is informational,
not approval or current authorization. No full diff is logged.

Twelve injected and twelve actual process-death revision phases cover before
preparation, prepared/publication/persisted commits, allocation, first/between/both
writing calls, staging, publication, packet_ready and before succeeded. Restarts
retain one append/target/successor and reuse succeeded calls. Additional ambiguous
claim/output and BOM recovery cases preserve safe behavior. Actual thread/multiple
connection tests cover same/different decisions, ordinary allocation pressure,
atomic style replacement and readers: no duplicate successor/entry or partial
content, and lock order is preserved.

Privacy tests include DEBUG/SQL logging traps. No feedback, style, prompts, resumes,
covers, screening answers or private truth inputs are logged. Snapshots intentionally
retain private preferences in the local DB. approvals.py, packet_verify.py and
llm.py are unchanged. Full approval regressions preserve stale tokens, exact URL,
append-only/one decision, replay-vs-current validation, all artifact/company/
screening/writing evidence, post-approval tampering and concurrency. Both v4/v5
preserve company_opening_references_candidate and exact candidate-name-token
attribution: company-source authority cannot authorize candidate claims.

### Validation counts and exact changed files

| Coverage | Cases passed in the complete suite |
| --- | ---: |
| Style/file/framing | 92 |
| Schema/snapshot/migration/legacy | 82 (including 3 populated-v8 migration/rollback) |
| v5 prompt/identity | 32 |
| Revision additions | 77 |
| Combined tests/test_revisions.py | 283 |
| History/diff/CLI additions | 70 |
| Approval core regression | 205 |
| Packet regression | 156 |
| Packet chaos regression | 207 |
| Database / company research / batch / scheduler / CLI defaults | 15 / 261 / 49 / 23 / 2 |
| Existing affected regression selection, including approvals/packets/chaos | 918 |
| Candidate/authority/grounding/poison/attribution named selection within packets/approvals/revisions | 87 |
| Original focused candidate/company authority milestone selection | 72 (earlier focused run; included in full regression) |
| Complete offline suite | 2348 |

Subset counts overlap and must not be summed. Revision crash matrix comprises
12 injected + 12 actual-death cases, plus 2 unknown-writing-claim and 3 leading-BOM
recovery cases. Revision concurrency adds 4 cases; style concurrency adds 2, and
schema concurrency adds 1. Migration/red-team and budget/no-Tavily/current-truth
tests are within the counts above. Warnings/skips/xfails are all zero.

Exact cumulative changed files:

```text
 M README.md
 M src/job_agent/cli.py
 M src/job_agent/database.py
 M src/job_agent/packets.py
 M tests/test_approvals.py
 M tests/test_batch.py
 M tests/test_company_research.py
 M tests/test_database.py
 M tests/test_packet_chaos.py
 M tests/test_packets.py
?? REVISION_STYLE_MEMORY_REPORT.md
?? src/job_agent/packet_history.py
?? src/job_agent/revisions.py
?? src/job_agent/style_memory.py
?? tests/fixtures/schema_v8.sql
?? tests/test_packet_history.py
?? tests/test_revisions.py
```

Final git diff --check is clean; git status remains the uncommitted changes above.
The preserved v8 fixture is newly tracked work, not a regenerated v9 approximation.
Existing test changes extend bindings/version expectations or use genuine trusted
old construction while retaining original safety assertions.

### Required YES/NO answers

| # | Question | Answer |
| --- | --- | --- |
| 1 | Can current mutable style reconstruct an old v5 packet? | NO |
| 2 | Can style changes alone invalidate a historical packet with valid bound snapshot? | NO |
| 3 | Can v5 exist without a bound style snapshot? | NO |
| 4 | Can legacy v4 accidentally acquire current style context? | NO |
| 5 | Can style override facts.yaml? | NO |
| 6 | Can style authorize an invented candidate skill/number? | NO |
| 7 | Can style override GitHub/GPA/degree/title policy? | NO |
| 8 | Can style weaken the 0f0ec1b company/candidate boundary? | NO |
| 9 | Can style allow company-source authority to assert a candidate claim? | NO |
| 10 | Can the same Revise append feedback twice? | NO |
| 11 | Can the same Revise create two successors? | NO |
| 12 | Can v1 Revise authorize v2? | NO |
| 13 | Can revision consume another new-job daily slot? | NO |
| 14 | Can revision bypass monthly LLM budget? | NO |
| 15 | Can revision blindly retry ambiguous provider outcome? | NO |
| 16 | Can revision call Tavily? | NO |
| 17 | Can expired cache TTL alone force revision research refresh? | NO |
| 18 | Can a crash after publication append feedback again? | NO |
| 19 | Can an unknown intervening style edit be overwritten silently? | NO |
| 20 | Can a historical style snapshot be updated/deleted? | NO |
| 21 | Can a missing historical resume be reconstructed from another packet for diff? | NO |
| 22 | Does resume diff use OCR? | NO |
| 23 | Does cover diff require an LLM? | NO |
| 24 | Can history/diff authorize a packet? | NO |
| 25 | Can a failed newer packet hide the older latest-ready packet? | NO |
| 26 | Can migration change legacy fingerprints? | NO |
| 27 | Can migration change existing approval evidence? | NO |
| 28 | Can a candidate-name company fact bypass survive in v5 generation? | NO |
| 29 | Is UI implemented in Run 2? | NO |
| 30 | Is authentication/Tailscale implemented in Run 2? | NO |
| 31 | Is application submission implemented in Run 2? | NO |

These answers describe supported code paths and enforced trust boundaries, not
immunity to equally privileged coherent corruption of trusted local evidence.

### Deferrals and known limitations

Run 3 provides queue/UI/API. Run 4 provides authentication/Tailscale/multi-device
access. No new submission, Gmail/Calendar/LinkedIn/referral transport or Settings
UI is added. Future safe Settings edits must reuse canonicalizer/atomic writer
and immutable snapshot persistence; there is no mutable DB current-style pointer.

Trusted configured local directories and cooperating Linux flock users are required.
Uncoordinated equally privileged writers can race namespace changes beyond cooperative
locking. SQLite/file publication is not atomic across resources. Hard death can leave
private orphan temp/staging files, never accepted as published content. Explicit manual
recovery must preserve immutable identities/paid claims; no recovery UI is supplied.
Historical diffs authenticate surviving local evidence and require compatible local
renderers, not universal historical truth proofs. Existing deterministic candidate
verification retains its established natural-language limits. Production Anthropic
may be used when real revision writing is needed; validation used offline fakes only.
No unresolved truth/approval bypass or architecture contradiction was found.

Implementation stops at this final milestone for Andrew's review under CLAUDE.md.

## Historical milestone record

Starting checkpoint: `0f0ec1b fix: block candidate-name authority in company facts`.
The original start gate found a clean tree. The genuine v8 initializer was dumped
before production edits into `tests/fixtures/schema_v8.sql`, with only line-end
whitespace removed and user_version retained. Andrew approved that milestone.
The fixture remains unchanged, SHA-256:
`cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e`.
Its round-trip produced the exact original schema, user_version 8 and a clean
foreign_key_check.

## Approved canonicalization amendment

The original one-leading-BOM rule was not idempotent for multiple leading BOMs:
exact canonical publication could reread as neither the retained base nor target.
Andrew explicitly approved removing ALL consecutive leading U+FEFF characters
under `style-nfc-lf-v1`. No extra BOM is prepended during publication.

Canonicalization uses strict UTF-8, removes that leading BOM sequence, replaces
CRLF with LF and remaining CR with LF, and normalizes NFC. All other content is
preserved, including embedded U+FEFF after the first non-BOM character, NUL,
spaces, tabs, Markdown, blank lines, trailing spaces and terminal newline presence.
The transformation is idempotent. Hashes are SHA-256 of exact canonical UTF-8
bytes. Canonical content is bounded at 65,536 bytes; raw input is independently
bounded at 131,072 bytes before decoding. Neither bound truncates input.

## Style-file milestone

Production addition: `src/job_agent/style_memory.py`. Tests are in the new
`tests/test_revisions.py`; README documents the incremental state.

The reader opens only `style_memory.md` beneath the configured existing data
directory, using a pinned directory descriptor and O_NOFOLLOW/O_NONBLOCK.
Symlink directories/ancestors and symlink files, special files, multiple hard
links, foreign ownership and group/world file permissions are rejected. Reads
are bounded and strict; detected in-place changes during reads cause conflict.
An absent style file returns empty content and is not created by reading. The
private sibling lock can be created by a read.

Cooperating readers use shared flock; writers use exclusive flock. Callers must
acquire packets/.build.lock before the style lock and open short database
transactions afterward. No database transaction or provider operation is added
by this module. Locked descriptor operations cannot be reused after context exit;
publication requires the exclusive lock.

Publication validates canonical content/hash/version agreement, checks the
expected base, creates an exclusive private same-directory temporary file,
writes and flushes complete bytes, fsyncs the file, rechecks destination safety
and base identity, replaces atomically, and fsyncs the directory. No in-place
rewrite or copy/delete publication is used. Normal failures clean up temporary
files. Hard death can leave an orphan temporary file; it is never read as style
content or accepted as published evidence.

The recovery helper requires retained canonical base and target values. Current
base permits exact target publication. Current target means publication already
happened; directory fsync is repeated. Any third content causes sanitized
`style_conflict` without overwrite. It never rebuilds feedback from current style.
This is the filesystem half of the forthcoming database recovery bridge. No
cross-resource atomicity is claimed. Durable snapshots/work must be committed
before this helper and style_persisted marked only after successful return.

## Entry framing and privacy

One framed entry contains timestamp_utc, company, title, source_packet_id,
source_packet_version, decision_id and feedback_utf8_bytes in deterministic compact
sorted JSON. Metadata controls/Unicode are JSON escaped; angle brackets and
ampersands are escaped so metadata cannot terminate the HTML comment. Canonical
feedback follows the header unchanged; its byte count determines its extent.
Outside separators do not enter that count. Embedded NUL, newlines, whitespace,
Unicode and end-marker-like user text remain data. No decision-ID substring search
is used. This pure constructor does not mutate decisions or independently supply
durable append idempotency.

The module logs no feedback or style content. Errors contain sanitized machine
codes and suppress low-level error messages. Retained canonical values contain
private content and must not be exposed by future history metadata helpers.
The eventual snapshot DB will intentionally retain private style content for
historical prompt reconstruction; it has not been added in this milestone.

## Validation

Style/file/framing suite: **92 passed**, warnings/skips/xfails **0/0/0**.
Coverage includes 1/2/3 leading BOMs, embedded BOM, idempotence, canonical Unicode
and line-ending equivalence, substantive whitespace differences, exact bounds,
overflow, strict encoding, absent reads, path/lock safety, permissions, forged
canonical identities, framing and privacy. Publication order is asserted as file
fsync, replacement, directory fsync.

Recovery coverage includes 12 injected crash cases across before publication,
after replacement and after directory fsync with 0/1/2/3 leading BOMs; six actual
os._exit process-death cases with 1/2/3 leading BOMs before/after replacement; and
three recoverable storage-failure cases. Actual death also proves OS lock release.
Two thread-concurrency tests exercise blocked readers during staging and repeated
publications with three simultaneous readers. Only whole old/new values are
accepted. Unknown edits during staging and after prior publication are rejected;
retained target identity is unchanged.

Focused unchanged packet/approval company-authority, candidate-grounding,
candidate-name-token and poisoned-opening regressions: **72 passed**, 289
deselected, warnings/skips/xfails **0/0/0**. The complete approval/packet and
established offline suites remain required after the upcoming integrated changes.

## Schema v9 and retained-snapshot milestone

Schema advances from v8 to v9. New `style_memory_snapshots` columns are hash
(primary key), canonical_content (NOT NULL), canonicalization_version (NOT NULL),
and created_at (UTC metadata). CHECKs enforce text hashes of exactly 64 lowercase
hex characters, canonical text bounded to 65,536 UTF-8 bytes using BLOB length
(including bytes after NUL), and the supported canonicalization version. Persistent
UPDATE/DELETE guards make rows immutable. A separate INSERT guard prevents
SQLite INSERT OR REPLACE from bypassing DELETE guards under default recursive
trigger settings. The creation timestamp is excluded from semantic identity.

`ensure_style_snapshot` creates/reuses exact validated canonical content inside
the caller's short transaction; it does not commit. `load_style_snapshot` rereads
retained state and recomputes exact canonical form/hash on every service load,
including repeat loads. Unsupported versions, missing rows, wrong keys and
noncanonical content fail closed. Noncanonical stored content is rejected even
when its stored key correctly hashes those noncanonical raw bytes. SQL logging
is redacted through the existing private packet log context; echo/DEBUG tests
contain no private snapshot marker.

ApplicationPacket adds writing_prompt_version (NOT NULL), style_memory_hash
(nullable snapshot FK), and revision_decision_id (nullable decision FK, unique
when non-NULL). A fresh-schema CHECK and persistent INSERT/UPDATE guards enforce
v4/NULL or v5/non-NULL,
reject unsupported versions, and require revision successors to reference a
matching immutable Andrew Revise decision, its predecessor fingerprint, the same
job key/canonical relationship and a higher version. Writing/style/revision
bindings cannot be changed after insertion. Revision successor replacement is
also blocked. No additional predecessor column was invented.

`packet_revision_work` columns are decision_id (primary key, decision FK), state,
base_style_hash and target_style_hash (snapshot FKs), successor_packet_id (unique
packet FK), created_at, updated_at and failure_code. States are pending,
style_prepared, style_persisted, building, succeeded, blocked and recovery_required.
CHECKs enforce paired hashes, no pending bindings, required prepared/persisted/
building/succeeded hashes, required building/succeeded successor, and sanitized
ASCII machine failure codes of at most 80 characters. Relational guards require
an actual matching Revise decision and exact target/successor/style/job/version
relationships. Succeeded transitions require packet_ready and ready_at present;
this structural check does not replace the forthcoming full successor verifier.

Operational states can advance through the expected preparation/publication/
building/success sequence, or become blocked/recovery_required. Blocked and
succeeded are terminal for state transitions. Recovery_required can return only
to guarded operational phases; this does not itself authorize provider retry.
The forthcoming processor must retain existing writing-ambiguity safeguards.
Once bound, decision, base, target, successor and creation metadata cannot silently
switch. Work deletion/replacement is rejected so retries cannot lose their durable
identity. The whole work row is not append-only: legitimate state and operational
metadata updates are tested.

## Migration, legacy compatibility and rollback

Migration uses the existing explicit BEGIN IMMEDIATE transaction. It adds packet
columns with v4/NULL/NULL defaults, creates tables/indexes/triggers, checks bindings
and foreign keys, then sets user_version 9 immediately before commit. Existing
packet tables are not rebuilt, and old fingerprints, writing responses/claims,
company facts/cache, decisions, approval evidence, capacity, scoring/batches and
application events are not rewritten. No fake legacy snapshot is created. A
pre-v9 file already containing nonlegacy packet bindings fails closed rather than
being silently adopted. Future versions 10/99 are rejected without modification.

The genuine populated v8 migration test uses checkpoint 0f0ec1b's actual ORM,
builder and approval code with an isolated test-only SQLModel registry. It contains
ready and damaged historical packets, succeeded and unresolved writing work,
Approve and Revise records with exact feedback, company facts/cache, scoring,
capacity, canonical job identities, LLM calls/batches and application events.
Every original column value across all thirteen old tables, and every old
index/trigger definition, is compared exactly. New tables are empty; all packets
are bound to v4/NULL/NULL; foreign_key_check is clean and user_version is 9.

Historical Approve still validates with its identical evidence after migration.
Current nonempty style is present, and a trap rejects any attempt to read it.
The current reconstructed resume/cover system/user strings equal the trusted v8
builder's exact strings. Existing completed fingerprints/writing work/decisions
remain exact. Damaged old artifacts remain damaged and fail integrity checks;
their Revise feedback is preserved unchanged.

An injected exception and a separate actual os._exit interrupt after all new DDL,
backfill and guards but before the final version bump. Both restore the exact
original populated v8 rows, complete schema/index/trigger definitions,
user_version 8 and clean foreign_key_check. Concurrent independent initializers
also converge to one identical valid v9 schema.

Older v6/v7 preservation tests now use the genuine trusted old mappings to populate
old packet tables. Comparisons project every original column while accounting
only for the added v9 columns and explicitly new indexes/triggers. Old preservation,
append-only, rollback and capacity assertions remain active. Schema expectations
in database/batch/packet/chaos tests advance to v9.

At the schema-only milestone, packet runtime still used v4. A narrow verifier guard rejected v5 and unsupported
bindings pending v5 reconstruction (superseded by the milestone below): v9 schema support alone must
not let new bindings use old reconstruction. No v4 prompt bytes, serialization,
fingerprinting or company/candidate truth checks changed. approvals.py and
packet_verify.py are untouched; decision triggers remain byte-for-byte unchanged.

Validation: the expanded style/schema suite passed **174 cases**, including the
original 92 style cases and 82 schema/snapshot/migration/legacy cases. Three are
genuine populated-v8 migration/rollback cases. The prior combined affected run
passed **1,060 cases** before the final replacement guards and additional tests;
the final sandbox-compatible offline run is recorded below when complete. All
recorded successful runs have warnings/skips/xfails **0/0/0**. Early failures were
outdated version expectations and current ORM usage against old schemas; they
were corrected while preserving all original safety assertions.

## Remaining Run 2 milestones and trust boundaries

Schema is now v9. Immutable snapshot/work tables, packet bindings, v8-to-v9
migration/rollback, exact legacy compatibility, v5 prompts, version-aware
reconstruction and ordinary packet style binding are implemented.
Revision processing, durable idempotency, successor allocation, capacity/budget
integration and the full requested crash matrix are implemented.
CLI, history and diffs are now implemented. Final Run 2 integration validation
and final reporting remain pending.
No completed packet, approval core, candidate/company verifier, candidate-name
boundary, transport, research, capacity or budget behavior was weakened.

The configured host/data directory and cooperating local lock users remain
trusted. An uncoordinated hostile process can race operations after the final
check or replace namespace/lock state; this is not isolation from equally
privileged writers. Linux flock, local atomic replace and fsync are required.
Unknown filesystem failures remain fail-closed and recoverable only when retained
base/target evidence agrees. No universal safety claim is made.

Run 3 queue/UI/API and Run 4 authentication/Tailscale/multi-device access remain
deferred. No application submission, live service, dependency installation, commit
or push was performed.

Style-file milestone workspace checks: `git diff --check` passed. HEAD remains `0f0ec1b`.
The v8 fixture hash is unchanged. Current status contains modified README.md and
untracked REVISION_STYLE_MEMORY_REPORT.md, src/job_agent/style_memory.py,
tests/test_revisions.py and the previously approved tests/fixtures/schema_v8.sql.
No other files changed. This milestone stops for Andrew's review as required by
CLAUDE.md and the current user instruction.

## Schema milestone final validation and workspace

The complete established sandbox-compatible offline split passed **2,010 tests**
in 196.19 seconds, including all **205 approval tests**, the candidate/company
authority regressions, packet/chaos, database, batch, research, scheduler and CLI
tests. The equivalent fresh-schema prompt/style CHECK was then added alongside
the already-tested persistent migration guards; the final focused
style/schema/packet/database run passed **345 tests** in 18.04 seconds. This final
run includes all **174 style/schema tests**. Warnings/skips/xfails were **0/0/0**
in every successful final run. The 159-test outside-sandbox Chromium/FastAPI split
has not been run for this milestone; complete established offline validation
remains pending final Run 2 integration. No live test was performed.

Final `git diff --check` passed. HEAD remains `0f0ec1b`. The genuine v8 fixture's
SHA-256 remains `cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e`.
The exact cumulative workspace status is:

```text
 M README.md
 M src/job_agent/database.py
 M src/job_agent/packets.py
 M tests/test_approvals.py
 M tests/test_batch.py
 M tests/test_company_research.py
 M tests/test_database.py
 M tests/test_packet_chaos.py
 M tests/test_packets.py
?? REVISION_STYLE_MEMORY_REPORT.md
?? src/job_agent/style_memory.py
?? tests/fixtures/schema_v8.sql
?? tests/test_revisions.py
```

The existing style canonicalizer/reader/lock/writer/framing/recovery implementation
was preserved; only snapshot service helpers were added to that module. All
production files remain within the authorized Run 2 scope. No dependencies,
live services, commits or pushes. Stopped for the next CLAUDE.md milestone review
as Andrew requested. The next milestone is v5 prompt/snapshot binding and
per-packet historical reconstruction, preserving exact v4 behavior.


## v5 writing and historical reconstruction milestone

New ordinary packet claims read canonical style under the shared style lock and
retain/bind its immutable snapshot within the short BEGIN IMMEDIATE claim
transaction. Empty style is a real content-addressed snapshot. The build lock
precedes the style lock, which precedes the database transaction; style locks are
released before provider I/O. Snapshot timestamps use independent UTC metadata
rather than sampling the capacity clock, preserving midnight admission behavior.

Both v5 writing SYSTEM messages contain explicit style-as-DATA instructions before
approved facts, exact byte-count-framed style content, and a fixed authoritative
closing reminder. Job context remains untrusted USER content. No style analysis
call or provider transport change is introduced; cached_system remains unchanged.
Style cannot authorize skills, numbers, company-to-candidate attribution, GitHub,
GPA, degree, title, banned phrases, schema changes or actions. The trusted
0f0ec1b packet_verify.py and approvals.py remain untouched.

Packet context includes v5, canonicalization version and style hash. The original
writing_fingerprint algorithm is unchanged; packet IDs/version/lineage do not
enter paid-request identity. Meaningful style changes alter packet and both
writing identities; CRLF/LF and NFC-equivalent content reuse exact semantics.
Successful checkpoints still reuse without another provider call; unknown
provider outcomes remain recovery_required without blind retry. Existing
monthly accounting/cache-token/admission tests now exercise v5 ordinary packets.

Historical verification dispatches on the stored packet prompt version. Legacy
v4 dictionaries, SYSTEM/USER bytes and request serialization remain exact; the
genuine migration regression compares reconstructed requests against trusted
pre-change code and validates its existing Approve despite nonempty current style.
v5 loads only the packet snapshot, checks exact canonical/hash agreement, then
reconstructs writing identity. Changing, deleting or symlinking the current file
does not substitute current preferences into old requests. Current candidate
truth/policy verification still applies. Unsupported or inconsistent bindings
fail closed. Revision-bound packets remain explicitly rejected until their
distinct identity reconstruction lands with the next processor milestone.

New tests cover ordinary binding, SYSTEM boundaries/caching, semantic changes and
equivalence, historical snapshot isolation, style changes during provider calls,
malicious style against existing grounding/policies and candidate-name attribution,
exact checkpoint reuse, ambiguous outcomes, ordinary capacity, and four packet
crash/restart points (claim, first checkpoint, both outputs and publication).
The style/schema/v5 suite passes 206 tests. Two wider regression failures exposed
an extra snapshot clock sample and a legacy test populated through the new v5
builder; both were corrected, with their original capacity/preservation assertions
retained. The legacy test now uses the trusted historical builder.

Final v5 milestone validation: **2,042 passed in 201.56 seconds** in the
established sandbox-compatible offline suite (the same ten Chromium/FastAPI
files excluded by the documented split). Warnings/skips/xfails: **0/0/0**.
This includes all 206 style/schema/v5 cases and the full sandbox approval, packet,
chaos, company-research, database, batch, scheduler and CLI regressions. The
outside-sandbox Chromium/FastAPI split remains unrun in Run 2 and is required
for final integration validation; this is not a complete established-suite claim.

The genuine pre-change schema_v8.sql SHA-256 remains
cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e.
HEAD remains 0f0ec1b. git diff --check passes. This milestone changes packets.py,
tests/test_revisions.py, tests/test_approvals.py, tests/test_packet_chaos.py, README.md
and this report; earlier approved schema/style/test changes remain in the working
tree. No dependencies, live services, commits or pushes. No changes to
packet_verify.py, approvals.py or llm.py.

Stopped for Andrew's review under CLAUDE.md: “Stop after every milestone for
Andrew's review.” Next is the revision processor and distinct revision identity,
with its durable feedback/publication/claim protocol and existing writing gates.
History/diffs and the narrow CLI remain later Run 2 work. Run 3 queue/UI/API,
Run 4 authentication/Tailscale/multi-device access, and submission remain deferred.


## Revision processing and successor generation milestone

Starting HEAD remains 0f0ec1b; this continues the approved fixture/style/schema/v5
working changes. Production scope is the new revisions.py and existing packets.py;
no additional production file or dependency is needed. Schema stays v9 and the
genuine schema_v8.sql fixture is unchanged. approvals.py, packet_verify.py and
llm.py remain untouched.

RevisionProcessor.process_revision accepts only an immutable decision ID. Source
validation requires a Revise record, supported Andrew/evidence policy, exact
source fingerprint, valid accepted free text and the Run 1 audit evidence shape.
It never mutates decisions. Processing acquires the existing safe build lock
(blocking for cooperating concurrent revisions) and creates one pending work row.
An exclusive style lock follows; short DB transactions come last. No transaction
or style lock spans provider work. Ordinary builds retain their existing
nonblocking build-lock behavior.

Pending reads safe current style, constructs deterministic framed feedback with
the immutable decision UTC timestamp and source metadata, persists immutable
base/target snapshots and style_prepared work before replacing the file. Restart
loads those exact contents, comparing current hash against base/target. Unknown
third content blocks without overwrite. Publication precedes style_persisted.
These commits bridge separate SQLite/filesystem resources; there is no claimed
cross-resource atomicity. Repeated requests never scan Markdown for IDs or
reappend feedback, and later edits cannot change prepared target identity.

After style persistence, the processor loads current candidate truth/answer bank
using the existing local verifier constructor, which never creates a researcher.
The prior completed-verifier job/scoring/company evidence block is extracted
unchanged into a shared local helper. It checks count, semantic IDs, job/company,
source safety/injection and production source-title/selection rules. Revision additionally authenticates exact retained public facts/order/job context
against the predecessor successful cover request user hash and fingerprint,
independently of old candidate SYSTEM content or damaged artifacts. This evidence
validation and allocation run in the same short transaction. Revision
keeps predecessor fact IDs/order and never consults cache expiry or invokes
Tavily, fixtures, employer HTTP or any other research transport. Existing
candidate-attribution and exact-name-token gates still authenticate generated
cover output; style does not authorize candidate facts.

Damaged old artifacts/cover/manifest are not required to save feedback or
construct a successor from sufficient retained job/scoring/facts evidence. Invalid
retained evidence blocks after feedback persistence. Invalid current candidate
files likewise preserve feedback without generating.

A short BEGIN IMMEDIATE claims the successor and links work/decision in one
transaction. Identity is exactly revision-v1 with predecessor ID/fingerprint,
immutable decision ID, and current v5 context. Version is max(existing versions)
plus one. The successor has its own ID, directory, fingerprint, target snapshot
and no decision. Predecessor rows, artifacts and immutable Revise remain unchanged.
A second Revise against v2 can create v3; replay of the first decision returns its
original successor. No corruption-recovery fingerprint wrapper is reused.

The successor's capacity_day is NULL only in this decision-validated allocation
path. There is no generic public capacity bypass. Packet assembly is extracted
into a shared private method with no allocation/admission/research logic,
preserving existing writing calls, truth/grounding/lint, rendered artifacts,
checkpointing, prepublication verification and atomic publication. Revision-aware
verification checks the distinct lineage identity/work/style/job/version/facts
bindings before all the same writing and artifact gates. It does not authorize
any packet or inherit the predecessor decision.

Restart reconstructs current inputs against the durably claimed fingerprint;
changed facts/answer bank block instead of adopting a new identity. Successful
writing checkpoints reuse exact requests. Exhausted budget denies new production
executor admission, with failed admission work unchanged if budget later grows.
Already-succeeded matching outputs finish locally without paid calls at exhausted
budget. Existing llm_calls/cache-token accounting is unchanged. Unknown provider
outcomes or orphan in-progress writing claims enter recovery_required without
blind retry. Blocked/recovery_required work has no automatic reset path.

After publication/packet_ready, the processor rereads and authenticates surviving
artifacts and reloads authoritative candidate inputs before marking work succeeded.
Ready-but-tampered surviving output cannot converge to success. Previously
succeeded replay also authenticates; historical completion is not ongoing approval
authority, and post-completion damage yields a sanitized failure.

Privacy continues through existing private_packet_logs across snapshot, work and
provider operations. Normal DEBUG/SQL echo tests assert feedback/style content is
absent. Failure codes omit private inputs, prompts and raw provider errors. Private
snapshot content remains intentionally stored locally for reconstruction.

Tests include all twelve requested injected crash points plus actual os._exit
at each point, preserving one append/target/successor, predecessor state and
completed-call reuse. Additional unknown-claim/provider-output crash tests prove
no blind reissue. Concurrent same/different decisions use real threads/connections
and flock; normal builds waiting on atomic style publication read whole content,
and ordinary/revision allocation pressure retains unique ascending versions.
Leading 1/2/3 BOM recovery remains canonical/idempotent.

Version history, authenticated resume/cover diffs, and the narrow local CLI are
still pending the next Run 2 milestone. Run 3 queue/UI/API and Run 4
authentication/Tailscale/multi-device access remain deferred. No submission or
live-service capability/test is added. Equally privileged uncoordinated hostile
filesystem/DB writers remain outside cooperative-lock guarantees. Hard death can
leave orphan private staging/temp files, which are never accepted as published
content. Manual recovery must preserve durable evidence rather than resetting
paid claims; no recovery UI is provided in this milestone.

Collected milestone coverage: style/schema/v5/revision suite **283 cases**
(92 style/file, 82 schema/migration, 32 v5, 77 revision/concurrency/budget additions).
Revision crash coverage is **12 injected + 12 actual process-death cases**,
plus **2 unknown-writing-claim cases** and **3 leading-BOM publication recovery
cases**. Revision/build concurrency coverage adds **4 cases** using real
threads/connections/locks. Existing approval core has **205 cases**, packet
suite **156**, packet chaos **207**. All remain collected for final validation.

Additional source-request red-team tests reject re-keyed/reordered company facts,
changed job context, missing bound cover work, and changed request hashes/identity
before allocation. Exact matching successful requests owned by another packet
reuse without another provider call. Success replay ignores mutable current style
but authenticates the surviving publication. Unsafe lock/storage exceptions are
sanitized. budget_blocked uses the existing admission_denied checkpoint category
(which includes unknown model pricing); failed admission is never automatically
reset on replay.


Final revision milestone validation: **2,119 passed in 250.33 seconds** in
the established sandbox-compatible offline suite. Warnings/skips/xfails:
**0/0/0**. This includes all 283 style/schema/v5/revision cases, all 205
approval-core regressions, 156 packet and 207 chaos cases, and the affected
database/company-research/batch/scheduler/CLI and candidate-authority suites.
The same ten Chromium/FastAPI files remain excluded by the existing split;
outside-sandbox validation remains pending final Run 2 integration. This is
not a claim that the complete established offline suite has run in Run 2.
The earlier broad run passed 2,110 cases before final source-request binding
checks and additional tests; the final 2,119 run validates the finished code.

Current milestone files: src/job_agent/revisions.py (new), src/job_agent/packets.py,
tests/test_revisions.py, README.md and this report. All prior approved
style/schema/migration/test changes remain in the working tree. HEAD is still
0f0ec1b. The genuine fixture SHA-256 is still
cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e.
git diff --check passes. No changes to packet_verify.py, approvals.py or llm.py.
No dependencies installed, live services called, commits or pushes.

Stopped at the requested milestone review under CLAUDE.md: “Stop after every
milestone for Andrew's review.” Next is local version history, authenticated
resume/cover diffs and the narrow revision-processing CLI, followed by remaining
Run 2 integration validation/reporting. UI/API/queue, authentication/Tailscale,
multi-device access and application submission remain deferred as specified.


## Version history, authenticated diffs and narrow CLI milestone

HEAD remains 0f0ec1b. This continues the approved style/schema/v5/revision
working changes. Production scope: new packet_history.py, cli.py, and a narrow
optional byte-input seam in packets.py's existing artifact-content verifier.
The default path-based verifier retains its exact behavior. No changes to
approvals.py, packet_verify.py, company/candidate attribution, provider transport
or schema. Genuine schema_v8.sql is preserved.

list_packet_versions accepts exactly one packet/job key/canonical ID selector.
It follows stored packet canonical bindings and retained JobIdentity aliases,
including legacy NULL-canonical packets. Ordering is version ASC then packet ID.
Safe metadata includes timestamps, state, fingerprints, prompt/style bindings,
revision ID, own decision type, derived source linkage, and separate latest
allocated/ready flags. Failed newer rows cannot hide earlier ready rows. Explicit
revision links derive from immutable decision metadata; corruption-recovery
links derive only from the existing exact predecessor fingerprint wrapper. No
link is invented for unlinked rows. Feedback/evidence bodies are not selected
from decisions and snapshot contents are not loaded by history metadata.

Resume diff reads exact surviving resume.face.txt bytes via pinned directory
descriptors and O_NOFOLLOW, rejects symlinks/special files/hard-linked faces,
requires exact expected filenames and manifest SHA-256/size agreement, bounds
each artifact to 20 MB and DOCX expansion to 100 MB, and decodes strict UTF-8.
It feeds safely captured bytes to the existing deterministic PDF/DOCX consistency
checker, avoiding path reopens. Selectable PDF text is used for consistency only;
the actual diff source is face text and no OCR is involved. Re-rendering uses
in-memory buffers and creates no files. Missing/damaged content returns a
sanitized unavailable/integrity_failed result and is never reconstructed from
another version.

Cover diff loads the bound successful cover WritingWorkItem, verifies task,
prompt binding/name, max tokens, system/user hashes, original request fingerprint,
output hash and strict parsed draft, then requires the exact stored cover joining
relationship and fixed closing. Retained v5 snapshot bindings are checked without
reading mutable style. Content is bounded to 1 MB. It does not regenerate prose
or call current candidate truth/policy validators. ready_at is evidence of
historical completion, even if later status/current eligibility has changed.
The informational integrity claim rests on surviving local manifest/checkpoint
evidence and its content relationship; it is not a new historical truth proof or
protection against an equally privileged writer coherently rewriting all trusted
DB/filesystem evidence. Current renderer compatibility remains required for
local rendered-content checks.

Both sides must belong to the same stored logical job relationship. Unified
diffs are deterministic, use packet/version labels only, and preserve original
line endings/terminal newline differences with explicit missing-LF markers. No
absolute artifact paths, feedback or prompts appear in labels/metadata/errors.
Full diff/content is never logged; DEBUG/SQL/PDF logs reuse private_packet_logs.
Helpers are read-only and do not mutate decisions, approve, validate current
authorization, submit or call providers. Tests delete current facts/answer bank/
style files and disable current-input/provider seams while historical views work.

The CLI command is revision-process --decision-id ID [--data-dir DIR]. Its only
authority is the existing immutable Revise record. No feedback/packet-rewrite/
capacity-bypass/provider-URL/apply/submit arguments exist. It reports safe IDs,
work state and sanitized failure code; exits 0/2/1 for success/review/error. Main
dispatch and legacy default CLI behavior are preserved. Invocation uses the
existing revision processor and can use normal Anthropic writing only when
needed; tests supply fake/local provider seams. It does not create decisions or
inherit predecessor approval.

Tests cover v1/v2/v3 lineage, failed-newer/latest-ready separation, stable ordering,
canonical aliases, corruption-recovery distinction, genuine migrated v4 history
and diffs with current inputs unavailable, deterministic additions/removals/
changes/newlines, face/PDF/DOCX/manifest/symlink/FIFO/UTF-8/size failures, cover
checkpoint/output/draft tampering, no missing-content reconstruction, no provider
calls/current eligibility gate, privacy and exact DB/file nonmutation. CLI tests
cover repeated real local processing, safe output, blocked/invalid decisions,
required ID, forbidden flags and top-level dispatch.

The backend feature set for Run 2 is implemented. Final established offline
validation (including the existing outside-sandbox Chromium/FastAPI split) and
the final consolidated Run 2 report remain pending the next review. No new UI/API,
authentication/Tailscale/multi-device access, Settings UI or submission is added.

Milestone validation: 70 history/diff/CLI cases passed. The combined history,
packet, revision and CLI-default selection passed 511 tests in 101.54 seconds.
The complete sandbox-compatible offline selection passed 2189 tests in 273.63
seconds, with no warnings, skips or xfails reported. The existing ten-file
Chromium/FastAPI split was excluded and remains pending final validation; this
is not a claim that the entire established offline suite has been completed.
git diff --check passed. The genuine schema_v8.sql fixture SHA-256 remains
cf18c06dfc0419c996519b3c8bec98be292b1aadf01ed82405dc2e793808171e.
HEAD remains 0f0ec1b; approvals.py, packet_verify.py and llm.py have no changes.
No dependencies, live services, commits or pushes were used. Work stops here
for the CLAUDE.md milestone review before final integration validation.
