# Run 6A source normalization and provenance

Run 6A is an uncommitted offline candidate prepared for Andrew's staged-diff review.
Run 6 is not complete. Run 6B and Run 6C have not started. This is the first persisted Run 6
checkpoint report.

The Run 6 preflight was read-only and intentionally produced no repository file.
Andrew's self-contained implementation handoff embedded the authoritative
preflight contract. No separate preflight artifact was persisted, sought or
required. The older
roadmap's Run 5 status is historical; Andrew's current handoff authorizes 6A.

## Restart and architecture

Before edits, branch was `main`; HEAD and local origin/main both matched
`77cd88e3ca2258f11c7eda6714f6e7bf6e48af66`. Working tree, index and untracked
inventory were empty. Builder was `codex-cli 0.161.0` (with a read-only PATH-alias
warning). CLAUDE.md, AGENTS.md and the integration matrix were read. No builder
skill discovery, evaluation, installation or configuration change occurred.

The existing Python JobSource registry, immutable Job, search stages,
SearchRepository and schema v9 JSON payloads are extended. No parallel intake
service or ATS board-token discovery change exists. FreeHire, company research,
scoring, batch scheduling, packet generation and CLI implementations are intact.

## Sources and offline configuration

| Namespace | Repository contract | Input |
| --- | --- | --- |
| simplify-newgrad | SimplifyJobs/New-Grad-Positions | README.md HTML tables embedded in Markdown |
| simplify-internships | SimplifyJobs/Summer2027-Internships | README.md HTML tables embedded in Markdown |

Each namespace is separately selectable through existing SourceRef. For these
namespaces, `board` is an explicit lane token: 1-128 ASCII letters, digits, dots,
underscores or hyphens, beginning with a letter or digit. It is not a fetch URL
or filesystem path. A source needs an explicitly supplied OfflineSnapshot.
The normal factory supplies no snapshot and fetch raises the sanitized typed
`offline_snapshot_required` failure. No transport, file loader, redirect
following or production profile enablement was added.

The two original synthetic fixtures were authored locally. They are not copies
of upstream data or code and require no live source read or reuse assumption.
They model the semantic Company / Role / Location / Application / Age columns,
including reversed column order, td/th headers, category headings, colspan
boundaries, inherited company cells, badges, inline HTML/Markdown, multiple
locations and multiple links. The current upstream representation is not newly
verified by these offline fixtures.

## Parser and normalized contract

The standard-library HTMLParser treats content as inert data. Headers select
columns by semantics, independent of table, line or row positions. Unrelated
tables are ignored; recognizable drifting job headers fail closed. Table/row/
cell envelope errors reject the snapshot. Invalid rows have typed, locator-only
issues and make the snapshot partial. Inheritance is cleared at new tables,
headers, categories and rejected rows. Each inherited company records its
original valid parent locator; rowspan inheritance is not supported.

A Job contains source/id, company, plain title, display location, posting URL
and nullable apply URL. Multiple locations become one semicolon-separated display
with the full tuple retained in evidence. Jobs are never multiplied by location.
The existing non-null location field uses `Unknown` when absent; normalized
intake evidence retains null. Country, remote, sponsorship, relocation, posting
date and employment type remain unknown unless evidenced. This adapter supplies
none of those unsupported facts. Description stays empty because these README
rows are not full job descriptions.

Age is preserved as relative source evidence. It never becomes posted_at,
identity or a claim of closure. Labels such as the lock icon stay observed data.
Source family is a source classification, not student/graduation/term/citizenship
eligibility. Eligibility remains null; local classifications are empty.
First/last discovery time belongs to the existing JobIdentity fields. Each
refresh appends a SearchResult; historical results are not rewritten.

## Exact identity derivation and duplicate preparation

Identity kind is `derived_source_scoped`, version `simplify-link-v1`.

Select the single validated employer link in the Role cell, otherwise the single
employer link in Application, otherwise a recognized Simplify role link. Each of
the employer-posting, employer-application and source-role classes is checked for
ambiguity independently, even when a stronger class supplies identity. Multiple
distinct normalized URLs in any of those classes reject the row.

Compute UTF-8 SHA-256 over Python JSON serialization of
`["simplify-link-v1", namespace, normalized_identity_link]`, using separators
`(',', ':')`. Job.id is `derived:v1:` followed by the lowercase hexadecimal hash.
The link itself is retained as identity_basis. A Simplify UUID extracted from
`/j/UUID` or `/p/UUID` is link_identity_evidence only, never a proven immutable
upstream ID. Titles, table/row positions, Age and repository season names do
not participate in identity.

Identical/formatting-only repeats produce one candidate with all raw occurrences
and links. Configured lanes preserve their individual occurrence evidence before
search filtering. Same-identity conflicts within a snapshot reject the entire
snapshot, including conflicting location/term/title/application fields; there
is no last-row-wins rule. Different identity-bearing URLs remain distinct even
when company, title and location match. Cross-namespace identities remain
separate. A narrow Job.dedup_key branch preserves these source identities through
the existing search stage; the existing sources' dedupe behavior is unchanged.
No fuzzy/cross-source merge, identity reassignment or durable dedupe redesign was
introduced.

## Evidence and persistence

IntakeEvidence is a typed frozen companion, version `intake-v1`; it is not part
of Job or scoring input. It retains namespace, repository, document URL, lane,
family, observed_at, nullable revision, parser `simplify-readme-v1`, adapter
`simplify-offline-v1`, SHA-256 snapshot, complete/partial status, derived identity
kind/version/basis and source external id.

Every occurrence retains raw row HTML, snapshot-local table/row/character-offset
locator, category, lane, observation time, revision, snapshot hash, parser/
adapter version, completeness, original and normalized links with labels/kinds,
normalized fields, relative Age, inherited fields/parent locators, extracted
markers and field transformations. The locator identifies a row within its
snapshot; it is not a stable cross-snapshot identity. Non-Application cells have
explicit original-cell-HTML transformations; the full raw row retains Application
HTML. Transformations also retain plain-text normalization, inherited company,
multi-location display and safe URL normalization. Security/content flags and source versus local classifications
remain explicit. Repeated occurrence stamps prevent merged lanes or snapshots
from losing their individual evidence.

SearchOutcome retains evidence for all normalized observations before filtering.
Partial snapshots emit a sanitized search warning. SearchRepository accepts the
optional typed evidence map, validates identity and normalized Job agreement,
requires evidence for every Simplify result, and places it in existing SearchRun
and SearchResult JSON. SearchRun also retains evidence for filtered observations.
The surviving Job never receives volatile observation data. The existing CLI is
not wired to this optional argument in 6A; no live Simplify job can reach it.
Provider-free operational wiring belongs to 6C.

NO SCHEMA CHANGE. Schema remains v9, with no migration, table, column, version
bump, backfill or production initialization. The temporary SQLite proof checks
sqlite_master/user_version, canonical owner continuity and historical payloads.

## URLs, bounds and security

All parsed cell anchors outside suppressed active HTML are retained in each
accepted row. The full raw row also retains the original HTML. Role posting and
Application employer URLs retain separate ownership. Where only one employer
Application link exists, it is an observed endpoint used for both posting and
apply; no endpoint is invented. A source-only role link can supply Job.url with
apply_url null. Company/source-navigation/other links never become arbitrary
application endpoints. Rejected unsafe rows retain only sanitized issues, not
credential-bearing URLs or bodies.

Reuse the existing offline CompanyFact.public_url destination validation and
its research boundary for embedded private IP labels. Reject unsupported
schemes, credentials (including empty userinfo), malformed/blank hosts/ports,
URL whitespace/control characters, private/local/non-global literals and
embedded private IP hostnames. No DNS, redirect or HTTP call occurs. DNS
rebinding/destination-resolution proof remains part of later transport work.

Normalize scheme/host/default port and only these explicit tracking keys:
utm_source, utm_medium, utm_campaign, utm_term, utm_content, gclid, fbclid.
Preserve other query keys, values, ordering, repeated parameters, path spelling,
trailing slashes and fragments. Original decoded href values and exact row HTML
remain available; identity-bearing query differences produce different IDs.

| Bound | Implemented maximum |
| --- | --- |
| UTF-8 source bytes | 4 MiB |
| HTML table rows, including headers/unrelated tables | 10,000 |
| Raw row | 16,384 characters |
| Company/title/category/link label | 512 characters |
| Location/Application text | 2,048 characters |
| URL | 2,048 characters |
| Age/revision/lane | 128 characters |

A hard limit rejects the snapshot with a typed sanitized failure; nothing is
silently truncated and labeled complete. Invalid UTF-8 and forbidden Unicode
control/replacement characters fail closed. HTML script/style/iframe/object
content is suppressed from normalized text and flagged; event attributes are
flagged. Injection signals inspect both original HTML and normalized text.
Detection does not grant execution or instruction authority. External text is
never evaluated, rendered, passed to a browser or executed by this adapter.

Timeout, rate-limit, interrupted-fetch and unavailable outcomes can be represented
by an explicit incomplete offline envelope and produce typed failures. No
transport retry behavior is implemented or claimed. A failed source does not
invalidate a healthy source in the existing search loop. All-source publication
protection and complete-refresh lifecycle handling remain 6B work.

## Filtering and later milestones

Existing keyword, freshness, location, seniority, eligibility and experience
stages retain their current order. No scoring/ranking or candidate-fact change
occurred. Passing a retention filter does not prove eligibility. Filter disposition
is `pending` in intake evidence; durable admission and retained reasons are not
claimed by 6A. Existing unknown-date freshness uses first observation without
changing Job.posted_at.

6B must implement conservative verified ATS/canonical relationships, retained
filter reasons, complete-refresh lifecycle, truthful freshness basis, replay/
idempotency, complete atomic write-set admission, all-source failure protection
and new-packet safeguards. The two-refresh temporary proof exercises existing
owner/history capability, not a claim that the full durable intake is complete.

6C must implement provider-free operation, source metrics/status, bounded
transport and destination resolution, accepted source enablement and scheduler
integration. No 6B/6C implementation was started.

SIMPLIFYJOBS NOT PRODUCTION-ENABLED.

Remaining live-adoption gate: independently verify current representation and
upstream contract stability, reuse/license/permission basis, source quality and
useful unique yield, bounded transport, then obtain accepted live enablement.
Public visibility is not a reuse-permission determination. Career-ops is
reference-only; no JobSpy was added. FreeHire and Tavily keep their current roles.

## Red/green record

Genuine implementation failures:

- Initial focused collection failed because IntakeEvidence did not exist.
- First implementation run: 34 failed, 3 passed. Of those failures, 33 exposed
  an HTMLParser `offset` name collision and one was the helper correction below.
  Renaming the parser method to source_offset fixed the implementation failures.
- Four additional tests failed for missing original HTML transformations,
  hidden table drift, invisible partial-source status and missing-evidence
  persistence admission. All were corrected and passed.
- Six later assertions failed for five invalid lane configurations and missing
  per-lane occurrence evidence. Validation and occurrence aggregation fixed them.
- Two further assertions failed for missing persisted completeness and injection
  text split by inline HTML. Both were corrected and passed.
- Self-review identified explicit port 0 being removed. Its new focused assertion
  failed (1 failed, 55 deselected). Preserve every non-default explicit port;
  the subsequent focused suite passed all 56 tests.
- Three Unicode normalization assertions failed: NFC expansion exceeded company/
  title bounds and emitted an unsanitized Age validation exception. Check both
  original and normalized lengths; all three regressions pass.
- A duplicate-attribute assertion failed because an earlier unsafe href could be
  overwritten. Reject duplicate attributes as malformed HTML; it now passes.
  A new per-table Markdown category check passed immediately. Heading positions
  are indexed once to avoid repeatedly scanning growing document prefixes.
  All 61 focused tests then passed.
- A conflicting-source-marker assertion failed (1 failed, 61 deselected).
  Include extracted markers in the snapshot conflict comparison; all 62
  focused tests passed. No marker is interpreted as eligibility or closure.
- A valueless href assertion failed with a TypeError (1 failed, 62 deselected).
  Validate the attribute type before URL parsing; the row now has a sanitized
  unsafe_url issue. All 63 final focused tests pass.

Immediate proof: document/control/format bounds already passed in the initial
implementation; after the parser collision fix, unsafe destination checks,
unknown dates, inheritance boundaries, identity/link retention and family
classification passed. Separate posting/apply ownership, identity-bearing query
preservation, conflicting location/term quarantine, invalid UTF-8 and raw-record
bounds passed when their additional assertions were first run. Application-text
bounds also passed immediately. Existing security policy was reused without
weakening its tests.

Fixture/harness corrections: the malformed-envelope assertion initially passed
an unsupported helper keyword; replaced it with an actual naive timestamp.
UTC JSON may use Z; the round-trip assertion now compares datetimes instead of
requiring +00:00 spelling. Large parameterized fixtures gained short IDs to keep
failure output bounded. No fixture contract or existing assertion was weakened.
Two sandbox compatibility attempts stalled at the documented ASGI worker-thread
boundary and were interrupted; identical test-only escalated reruns are the
counted evidence, not those incomplete attempts. An early full-suite attempt
was interrupted for the demonstrated port-normalization correction: 419 passed
in 67.95 seconds, exit 2 (KeyboardInterrupt). It is not counted as complete
validation. A second attempt was interrupted for the demonstrated Unicode
normalization boundary correction: exit 130 during browser teardown, without
a final count summary (progress had reached 48%). No complete validation is
claimed for it. A third incomplete attempt was interrupted for the demonstrated
marker-conflict fix.
Its final count was unavailable during interrupted browser teardown. Full
regression was started before edge-case review was finished; that was a process
mistake. These interrupted attempts are disclosed, not presented as successful
complete runs.

## Completed implementation validation (historical)

- A: `.venv/bin/pytest -q tests/test_simplify.py --tb=short`: 63 passed,
  2.53 seconds, exit 0.
- B: source/search/search-state/config compatibility: 207 passed,
  2.20 seconds, exit 0.
- C: URL/security/filter compatibility: 471 passed,
  5.43 seconds, exit 0.
- D: database/batch/scoring/import/packet compatibility: 293 passed,
  14.55 seconds, exit 0.
- E: `.venv/bin/python -m compileall -q src/job_agent tests/test_simplify.py`:
  exit 0. No established Python static/type command is configured in pyproject;
  no new tool was installed. `git diff --check`: exit 0.
- F: `.venv/bin/pytest -q`: **3,140 passed, 23 warnings**,
  901.86 seconds (15:01), exit 0. No failures or skips. Warnings come from
  unchanged multiprocessing fork tests: 7 packet chaos, 12 revisions,
  4 scheduler. This is the sole completed full run on the final candidate;
  the three interrupted attempts above are not counted as completed runs.

Counts overlap and must not be added. Exact compatibility commands:

```sh
.venv/bin/pytest -q tests/test_sources.py tests/test_freehire.py tests/test_search.py tests/test_search_state.py tests/test_config.py --tb=short
.venv/bin/pytest -q tests/test_company_research.py tests/test_apply_open.py tests/test_scan_metadata.py tests/test_eligibility.py tests/test_experience.py tests/test_geo.py tests/test_seniority.py --tb=short
.venv/bin/pytest -q tests/test_database.py tests/test_batch.py tests/test_scoring.py tests/test_search_import.py tests/test_packets.py --tb=short
```

The final full command is `.venv/bin/pytest -q` in the established test-only
outside-sandbox environment.

## Production-data safety and side effects

Before mutation-capable tests, read-only SHA-256, size, device, inode and mtime_ns
were measured for all 12 regular files under the configured production `data`
root. Production SQLite SHA-256 was
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`, size
241,664 bytes, device 2096, inode 216020, mtime_ns 1791404174236327816.
No production writable database was opened. Tests mutate pytest temporary roots.
Before manifest: `/tmp/job-pilot-run6a-production-before.json`.
After manifest: `/tmp/job-pilot-run6a-production-after.json`.
All 12 files and the complete inventory matched exactly: SHA-256, size, device,
inode and mtime_ns. SQLite retained the hash, size and identity metadata above.
A read-only check of environment/.env/default resolution confirmed the configured
production root matched the before manifest. No secrets were exported.

New tests trap socket connections, HTTP sends, Anthropic/executor construction,
packet-service construction, browser startup and application submission. Temporary
SQLite has no application events, packets or model-call records. The established
full suite includes isolated synthetic browser regressions; those do not exercise
browser discovery, production accounts or employer submissions.

NO LIVE MODEL/PROVIDER CALLS. NO APPLICATION SUBMISSION. No live Simplify,
FreeHire, Tavily or Anthropic request, outreach or production SearchRun occurred.

## Implementation handoff manifest (historical)

| Classification | Path |
| --- | --- |
| PRODUCTION | src/job_agent/config.py |
| PRODUCTION | src/job_agent/models.py |
| PRODUCTION | src/job_agent/search.py |
| PRODUCTION | src/job_agent/search_state.py |
| PRODUCTION | src/job_agent/sources/__init__.py |
| PRODUCTION | src/job_agent/sources/simplify.py |
| TEST | tests/test_simplify.py |
| FIXTURE | tests/fixtures/simplify/newgrad.md |
| FIXTURE | tests/fixtures/simplify/internships.md |
| DOCUMENTATION | docs/run6/RUN6A_SOURCE_NORMALIZATION_PROVENANCE_REPORT.md |

GENERATED/REMOVE, produced by the existing frontend decision screenshot tests:

- Restored to HEAD bytes: docs/run5c/decision-implementation-evidence/desktop-bootstrap-unavailable-1440x900.png
- Restored to HEAD bytes: docs/run5c/decision-implementation-evidence/phone-approval-recorded-390x844.png
- Restored to HEAD bytes: docs/run5c/decision-implementation-evidence/phone-reject-recorded-390x844.png
- Restored to HEAD bytes: docs/run5c/decision-implementation-evidence/phone-revise-recorded-390x844.png
- Removed new generated file: docs/run5c/decision-implementation-evidence/desktop-reject-recorded-1440x900.png
- Removed new generated file: docs/run5c/decision-implementation-evidence/desktop-revise-recorded-1440x900.png
- Removed new generated file: docs/run5c/decision-implementation-evidence/phone-validation-390x844.png

Their test-owned paths were verified in tests/test_frontend_decisions_dom.py.
Prior tracked screenshots were preserved by byte comparison against HEAD.
No generated screenshot remains in the candidate. UNEXPECTED: none.
Safety manifests/test storage stay outside the repository. No dependency/lockfile,
schema, production profile, rules, builder skill/configuration, scheduler/batch/CLI
or packet implementation edits.

## Implementation handoff Git state (historical)

Branch remains main; HEAD and local origin/main remain
`77cd88e3ca2258f11c7eda6714f6e7bf6e48af66`. Builder remains
`codex-cli 0.161.0`. Final status:

```text
 M src/job_agent/config.py
 M src/job_agent/models.py
 M src/job_agent/search.py
 M src/job_agent/search_state.py
 M src/job_agent/sources/__init__.py
?? docs/run6/
?? src/job_agent/sources/simplify.py
?? tests/fixtures/simplify/
?? tests/test_simplify.py
```

`git diff --stat` (tracked files only; five new files are in the manifest):

```text
 src/job_agent/config.py           |  12 +++-
 src/job_agent/models.py           | 125 +++++++++++++++++++++++++++++++++++++-
 src/job_agent/search.py           |  12 +++-
 src/job_agent/search_state.py     |  24 +++++++-
 src/job_agent/sources/__init__.py |   6 ++
 5 files changed, 173 insertions(+), 6 deletions(-)
```

`git diff --check`: exit 0, no output.
`git diff --cached --name-only`: empty. Nothing staged.
Only the ten intended Run 6A files remain changed/untracked.

## Implementation self-review (historical)

Full production diff, new parser, synthetic fixtures and tests reviewed for live
calls/enablement, false dates/eligibility, row-position identity, URL conflation,
lost provenance, query stripping, private destinations, field bounds, unsafe
content, fuzzy merging and historical reassignment. Only the focused 6A extension
points above change. Final manifest/whitespace/index verification passed after the
completed full suite and screenshot cleanup; nothing is staged.

NO COMMIT. NO PUSH. NO RUN 6B. NO RUN 6C. NO LIVE SOURCE ENABLEMENT.
NO SCHEMA CHANGE. NO BUILDER-SKILL CHANGES. NO PRODUCTION DATA MUTATION.
NO APPLICATION SUBMISSION. NO OUTREACH.

The implementation stopped for Andrew's review. Andrew subsequently authorized
final cleanup and explicit staging, recorded below.

## Final cleanup and staged-review handoff

The cleanup restart matched main, HEAD and local origin/main at
`77cd88e3ca2258f11c7eda6714f6e7bf6e48af66`, with builder `codex-cli 0.161.0`.
The index was empty. The ten paths in the implementation manifest were the
complete changed/untracked inventory; each is classified COMMIT. There was no
unrelated work, additional substantive path or unresolved Andrew decision.

The full candidate was audited against source, tests and synthetic fixtures.
Cleanup changed only this report: precise link-ambiguity behavior, transformation
coverage, snapshot-local locator scope, validation/history labels and this
handoff. No production, test or fixture behavior changed during cleanup.

The implementation counts above are retained historical results supported by
the implementation report and Andrew's handoff, not newly rerun cleanup tests.
No separate retained Run 6A pytest log was found among the related temporary
artifacts inspected. The authoritative completed full result remains 3,140
passed, 23 existing multiprocessing/fork warnings, zero failures and zero skips.
The three interrupted full-suite attempts remain non-completed validation.

New cleanup validation: full candidate review, privacy/generated-artifact scan,
read-only production manifest comparison, `git diff --check`, explicit-path
staging, complete staged-diff review and `git diff --cached --check`. Whitespace
checks passed with no output. The full suite was not rerun because cleanup was
documentation-only. No secrets, private candidate/employer data, debug dumps,
build outputs, caches, screenshots or unexpected machine-specific paths were
found in the candidate. No artifact removal was needed in cleanup.

Both retained production manifests matched exactly. A fresh read-only file
inventory/hash/stat comparison also matched all 12 recorded files, including
size, device, inode and mtime_ns. SQLite remained 241,664 bytes with SHA-256
`da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`.
SQLite was read only as bytes, never opened through a database connection.
The temporary safety manifests are local audit evidence, not product paths or
committed artifacts.

Exactly the ten COMMIT paths were staged using explicit paths. The full staged
diff matches the audited candidate. `git diff --name-only` and
`git ls-files --others --exclude-standard` are empty. Branch and both refs remain
at the cleanup restart checkpoint. The historical unstaged status above is the
earlier implementation handoff, not the final staging state.

SIMPLIFYJOBS NOT PRODUCTION-ENABLED.
NO COMMIT. NO PUSH. NO RUN 6B. NO RUN 6C. NO LIVE SOURCE ENABLEMENT.
NO SCHEMA CHANGE. NO BUILDER-SKILL CHANGES. NO PRODUCTION DATA MUTATION.
NO LIVE MODEL/PROVIDER CALLS. NO APPLICATION SUBMISSION. NO OUTREACH.

Proposed commit subject: `feat: add Run 6A source provenance`.

VERDICT: READY FOR ANDREW RUN 6A STAGED-DIFF REVIEW
