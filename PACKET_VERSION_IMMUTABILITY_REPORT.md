# Packet version immutability prerequisite

Starting HEAD: `879c7bb feat: add production company research`.
The start-state gate confirmed that exact HEAD and an empty `git status --short`.
Read and followed `CLAUDE.md` before edits. No dependency, schema, approval,
authentication, UI, style-memory or submission changes. No live providers,
employer sites, commits or pushes.

## Original problematic path

`PacketService._build_one_locked` selected a row by its unique context fingerprint.
For `packet_ready`, a failed fact/manifest/ready-invariant check changed that row
into `recovery_required` and returned it. On a later call the same fingerprint
selected the same row; the generic existing-row path reset it to `building`.
If its published directory was absent, generation reused or requested writing,
rendered a fresh staging tree, and checkpointed a new manifest and final cover
onto that same row before publication. The final ready transition reused its id
and version. A surviving directory instead entered published recovery, which
checked the durable manifest and never replaced that directory.

The existing system retains writing outputs and artifact hashes, not authoritative
original PDF/DOCX byte copies. Exact restoration is therefore not implemented.

## Changes and invariant

Only `src/job_agent/packets.py` changed in production. `ready_at` already records
successful readiness, survives lifecycle failure, and is set only at the ready
transition. Rows with that marker and a non-ready lifecycle state are never
admitted to generation or published recovery again.

The existing fingerprint has a uniqueness constraint. A deterministic successor
fingerprint is `digest({"recovery_of": predecessor.id,
"packet_fingerprint": predecessor_fingerprint})`. Recovery follows this chain
until it finds a valid ready successor, an unfinished successor to resume, or an
unused identity. The old fingerprint is untouched. Existing job version allocation
creates `max(version)+1`, under the existing filesystem build lock and database
`BEGIN IMMEDIATE` transaction. No schema change is required.

Ready reuse still validates facts, artifact hashes and completed evidence. It now
also verifies face grounding and rendered PDF/DOCX content against that face.
An integrity failure changes only lifecycle status and failure reason, and returns
the damaged version. A subsequent explicitly requested build creates/resumes its
successor. This preserves the existing two-call detection/recovery behavior.

The successor identity is a recovery identity rather than the original plain
context digest. Writing identity remains the original semantic request identity.

## Recovery, artifacts and history

Before first readiness, the existing durable claim/checkpoint, staging, atomic
publication and published-recovery paths remain intact. The crash matrix now
explicitly asserts version 1 throughout its original first-build cases, including
unknown outcomes and successful restart. Successor crashes similarly resume v2.

After readiness, old manifest, cover, writing references, fingerprint, timestamp
and capacity reservation are not updated by regeneration. Each successor has a
new row, id, directory, manifest and final cover. No-replace publication is
unchanged; no completed artifact tree is deleted or overwritten by recovery.
Any externally missing/corrupt files stay missing/corrupt. Surviving old files
remain available as historical evidence, including through the original directory
where it still exists. A hostile symlink is rejected as valid packet evidence and
is not replaced or followed for publication.

Valid successful semantic writing checkpoints are reused across recovery versions
without additional provider calls. Unknown/recovery-required writing checkpoints
continue to block, including across versions. Paid execution still uses the
unchanged executor and monthly budget admission path. A successor has no new
`capacity_day` reservation; the predecessor retains the original reservation.
The capacity-limit-one regression proves v2 completes with the original daily slot
already occupied. Other new jobs still use the original capacity admission rules.

## Concurrency and red team

The existing nonblocking root build lock serializes recovery. Contenders either
receive `packet_build_in_progress` or reuse the same successor; deterministic
fingerprint lookup and existing job/version uniqueness prevent additional claims.
A two-thread race asserts exactly two rows total, one completed replacement, and
no additional writing calls. Existing actual two-process locking/capacity and
no-replace publication race tests remain unchanged.

Added regression cases cover deleted ready directories, deleted PDF, modified PDF,
DOCX and face bytes, altered database manifests, symlink directory replacement,
rendered-verifier rejection, and valid altered PDF/DOCX/face with matching forged
manifests. The forged PDF case uses real offline PDF extraction instead of the
fixture's fixed-text extractor. Each case snapshots evidence after external damage
and proves recovery does not modify it, creates ready v2 in a distinct directory,
reuses valid writing, preserves capacity, and subsequently reuses v2.

Successor crashes are injected after packet claim, after reused durable writing,
after verified durable manifest checkpoint, and after publication before readiness.
All resume the same v2 while leaving v1 evidence unchanged. The after-writing case
uses `after_both_outputs`: successful cached work returns before
`after_writing_checkpoint`, so no fresh paid checkpoint occurs in that recovery.
The original crash matrix separately exercises actual paid-output checkpoint
crashes. An additional unknown-writing successor regression remains fail-closed.

## Validation

17 new parameterized regression cases; one existing crash matrix assertion extended.
Initial packet/chaos run: 293 passed before the final four added cases.
Final targeted new regressions: 17 passed, 190 deselected.

The exact requested combined command initially collected no tests because
`tests/test_ops.py` does not exist. Neither does `tests/test_cli.py` in this checkout.
The corresponding existing `test_scheduler.py` and `test_cli_defaults.py` were used;
packet chaos and company research also exercise ops status. No tests were removed.

Final required groups and complete sandbox split: results recorded below.
The established ten-file Chromium/FastAPI split requires outside-sandbox execution
as documented in COMPANY_RESEARCH_REPORT.md. Execution initially stopped at the
requested approval boundary. Andrew then approved the exact test-only command,
which passed all 159 tests in 11.73 seconds. Full offline validation is complete.

## Explicit answers

| Question | Answer |
| --- | --- |
| 1. Can completed ready versions receive different regenerated bytes under the same id/version? | NO |
| 2. Can their completed cover be silently replaced under the same version? | NO |
| 3. Can their final manifest be replaced to describe different completed files? | NO |
| 4. Can damaged ready v1 regenerate as new v2? | YES |
| 5. Can legitimate pre-ready recovery complete the same version? | YES |
| 6. Can successor integrity recovery consume a second new-job daily slot? | NO |
| 7. Can identical writing work be reused across recovery versions? | YES |
| 8. Can concurrent recovery create uncontrolled duplicate successor versions? | NO |
| 9. Is schema v8 implemented? | NO |
| 10. Is approval decision logic implemented? | NO |

## Limitations

This enforces the builder invariant, not filesystem or database access controls.
External writers can destroy files or alter database evidence; there is no retained
byte archive, tamper-proof database, distributed coordination or restoration claim.
The existing `ready_at` marker and historical fingerprints must remain trusted
persistent database evidence. Unknown provider outcomes require review and are
never automatically repaid. Detection returns the damaged row; regeneration is a
subsequent build operation. Future approval logic is outside this prerequisite.

## Final validation and workspace

- Required existing regression groups: **647 passed**, 34.35 seconds.
- Complete established sandbox split: **1,565 passed**, 39.92 seconds.
- Approved outside-sandbox Chromium/FastAPI split: **159 passed**, 11.73 seconds.
- Warnings / skips / xfails in all final runs: **0 / 0 / 0**.
- Full offline total for this change: **1,724 passed** (1,565 + 159).
- `git diff --check`: passed.
- `git status --short`: modified README.md, src/job_agent/packets.py and
  tests/test_packet_chaos.py; untracked PACKET_VERSION_IMMUTABILITY_REPORT.md.
- HEAD remains 879c7bb. No commit or push.

Exact approved test-only command executed outside the sandbox:

```bash
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py
```
