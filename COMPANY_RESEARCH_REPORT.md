# Production company-fact research slice

Start: HEAD `c4d18f3 feat: add hardened grounded application packets`, verified
with `git --no-pager log -5 --oneline`; `git status --short` was empty.
`CLAUDE.md` was read before editing. No dependencies were installed. During the
prior offline-only implementation and audit, no live
Tavily, Anthropic, web, source-page, LinkedIn, email or submission calls occurred.
No approval records, production candidate-file changes, commits or pushes occurred.

## Changed files

| File | Purpose |
| --- | --- |
| `src/job_agent/tavily_research.py` | Fixed-endpoint transport, queries, extraction, source policy, validated persistent cache. |
| `src/job_agent/config.py` | Explicit provider selection, excluded/repr-hidden SecretStr key, validated 1–30 day TTL. |
| `src/job_agent/database.py` | Additive transactional schema v7 and `company_research_cache`. |
| `src/job_agent/packets.py` | Local provider selection and production cover-first ordering after existing dedupe gate. |
| `src/job_agent/research.py` | Module docstring updated; existing research helpers unchanged. |
| `src/job_agent/ops.py` | Three read-only aggregate cache counts. |
| `tests/test_company_research.py` | 261 synthetic offline research, packet integration, privacy, cache and migration cases after the audit correction. |
| `tests/fixtures/schema_v6.sql` | Actual empty schema produced by the checkpoint's v6 initializer in an isolated process. |
| `tests/test_database.py` | v7 table/version expectations and rejection of future versions 8/99. |
| `tests/test_packets.py`, `tests/test_batch.py` | Only legitimate current-schema version expectations updated. |
| `tests/test_packet_chaos.py` | v7 expectation; genuine-v5 setup excludes the new cache and preserves comparison of all old indexes. |
| `README.md` | Configuration, privacy, cost bounds, extraction, caching, failure behavior and limits. |
| `COMPANY_RESEARCH_REPORT.md` | This evidence record. |

## Provider and network contract

Fixture remains the default. `TAVILY_API_KEY` alone does not enable production
research. Only explicit `JOB_AGENT_COMPANY_RESEARCH_PROVIDER=tavily` selects it;
a nonblank key is required, even for a cached operation. Missing credentials fail
closed during actual research rather than falling back to fixtures. Invalid
provider names fail local validation. Exact custom/falsey injected researchers
remain authoritative. Construction, migration, selection, ranking, dry-run, list,
ops and scheduler status do not research.

Only the public company and public title plus static code-owned words enter the
JSON query. No candidate name, email, phone, address, location, GPA, resume,
facts.yaml/answer-bank content, screening answers, projects, employer history,
private prompts, full description, matched requirements or missing requirements
enter Tavily requests. Request-capture tests include private input-file, job/scoring,
GPA and answer-bank markers and ordinary synthetic contact/project/employer values.
All are absent. The API key appears only in Authorization, never the body/query.
Public company/title are assumed to be public employer/job data; injected private
text deliberately placed in those fields is outside that input classification.

NFC normalization, control/quote replacement and whitespace collapse produce
quoted search data. Normalized fields over 160 characters or blank fields fail
locally, without truncation/collision or a request.

* Query A: `"<company>" "<job title>" engineering product technology`.
* Query B: `"<company>" company product mission engineering recent`.

Query B runs only after a valid Query A response fails to provide three safe
unique facts including a cover-eligible one. A sufficient A makes one request;
an insufficient valid A makes at most two. Provider content cannot create a new
query. Transport/provider/request-level schema errors stop immediately; B is never an error
retry. There are no automatic retries of any query. A later operator-triggered
build can initiate a new operation. Missing keys/invalid context make zero calls.

Transport is existing httpx with explicit `HTTPTransport(retries=0, trust_env=False)`
and `Client(follow_redirects=False, trust_env=False)`. The sole endpoint is
`POST https://api.tavily.com/search`. Authentication is bearer Authorization.
Parameters: advanced search, general topic, eight results, no answer, no images,
`include_raw_content="text"`. No configurable base URL, source fetch, crawling,
SDK, tools, or LLM research exists. The REST shape was exercised offline and
subsequently verified for live compatibility by the controlled smoke test below.

Timeout is 12 seconds per connect/read/write/pool phase, with a 12-second elapsed
guard between streamed chunks and at completion. This is finite IO bounding,
not a hard wall-clock interrupt of an already-blocked phase or OS DNS resolution.
Bodies are streamed with a 2,000,000-byte buffer limit; error/redirect bodies are
not read and compressed bodies are rejected. At most eight results per query,
200,000 raw characters/result, 300 title characters, 2,048 URL characters and
500 selected-statement characters are accepted. Request-level failures remain
fatal: non-200 HTTP, transport/timeout, oversized body, malformed JSON, non-object
root, missing/non-list results, and more than eight results. Once the bounded
results list is valid, each row is independent untrusted data. Non-object rows,
missing or non-string URL/title/raw_content (including null), and unusable rows
are skipped without discarding other valid results. No partial field salvage or
content fallback is used. Existing size, URL, source, Unicode, key and injection
checks remain intact.

## Extractive grounding and packet preservation

No model or Tavily answer participates in extraction. NFC, entity/HTML cleanup,
limited Markdown formatting cleanup and whitespace collapse preserve source
words. Selection yields contiguous source statements, never paraphrases,
sentence combinations, subject insertion, pronoun changes or invented metrics.
Block/line boundaries remain distinct. Facts require 8–45 words, a period, a
declarative predicate, a subject rather than an initial verb, and bounded length.
Noise, cookie/privacy/legal/navigation text, headings/fragments, calls to action,
promotional superlatives, malformed Unicode and suspected directives are rejected.
"We" may remain unchanged in a secondary fact. A result title or selected statement
must naturally identify the company; source truth and publisher attribution are
still not independently proven.

Exactly three unique facts are selected through unchanged `usable_facts`,
`CompanyFact`, canonical URL and normalized-text gates. At least one source
statement must naturally name the company with normalized word boundaries and
the existing verifier's literal casefold comparison. It comes first in production
output and writing context. No verifier or packet fingerprint algorithm changed.

Existing private/local/reserved IP, local suffix, credential and scheme rejection
remains intact. Additional production rejection covers reserved/local-use suffixes,
all specified social domains and their subdomains, Glassdoor, Indeed, additional
known job boards/ATS copies and obvious job/career paths. Known wildcard/loopback aliases and private/reserved IPv4
labels embedded in public-looking hostnames are also rejected without DNS.
A company-name host match is preferred, followed by recognized public news, product/docs, engineering/
blog and other public sources. This heuristic never asserts domain ownership.
Original URLs remain provenance; fragments/tracking/default ports dedupe, while
ordered repeated query values remain meaningful.

Existing packet/content injection gates apply to titles and extracted statements,
with additional conservative directive checks. No remote instruction can change
queries, settings, tools, candidate facts, screening answers or approval state.
Detection is finite; deterministic extraction, no research tool execution and
existing candidate/cover verifiers are independent safeguards.

Unsuccessful research returns no usable set or raises a sanitized boundary error.
The packet becomes `research_incomplete`, reserves no capacity_day, calls no
Anthropic, generates no resume/cover, creates no published artifacts and creates
no approval or outbound action. The existing packet lock file/directory can exist.
Successful research follows the existing claims, truth gates, writing checkpoints,
artifact validation/publication and recovery paths unchanged.

Semantic identity still excludes retrieved_at. Tests refresh identical source
sentences with canonical-equivalent URLs and a new retrieval time: same packet ID,
fingerprint, fact IDs and two original writing calls. A meaningful fact change
creates version 2, reuses the identical resume request and pays only the changed
cover request in the synthetic executor.

## Cache, migration and privacy

Schema v7 adds only `company_research_cache`. Fields: fingerprint primary key,
provider, researcher version, normalized company/title, final fact JSON,
created/refreshed/expiry timestamps; expiry has an index. No key, prompt, private
input or full raw webpage/provider response is stored.

The SHA-256 fingerprint commits to provider `tavily`, version
`tavily-v1-query1-extract1-sources1`, normalized casefolded company and title.
Query/extraction/source-policy changes require deliberate version changes.
Time, keys, IDs and random values are excluded. TTL defaults to seven days and
accepts 1–30. Successful cache entries alone are persisted, transactionally after
network IO. Fresh entries are revalidated and return the exact serialized facts,
original URLs and retrieved_at; reopening the database makes zero calls.
Expired entries require new bounded research. Failed/incomplete refresh preserves
the old record but never serves it. Unsafe/injected/malformed/partial research
cannot become a successful cache entry. Corrupt fresh entries fail closed without
an automatic paid repair. Persisted expiry governs existing entries.

The genuine-v6 migration test starts with the actual checkpoint schema and
populates all eleven old tables, including ready packets and an in-progress
writing claim. It compares every old row/value and all indexes/triggers exactly.
All survive; fingerprints, writing claims and capacity days remain identical.
Append-only history, immutable capacity and writing safety triggers still reject
mutations. Cache starts empty; `PRAGMA user_version=7` and foreign_key_check has
no rows. Injected failure after cache table creation rolls back to identical v6
schema/version. Existing older migration/FK tests remain active. Future versions
are rejected without changes.

API credentials use excluded/repr-hidden SecretStr settings. The existing
context-local packet log redaction also wraps direct researcher calls, including
HTTP/SQL DEBUG diagnostics. Errors never expose response bodies or transport
exception messages. Tests capture CLI, errors, logs, cache and operational packet
metadata using synthetic key/private/provider markers. Request bodies contain no
private markers; outputs/metadata contain no error/key markers. Public facts are
intentionally persisted as public facts; private screening answers remain exact
in existing employer-facing packet data as before.

Ops executes a read-only SQL aggregate over expiry, exposing only
research_cache_entries/fresh/expired. These are timestamp-based counts, not an
ops-time validation or refresh of fact contents. No URLs/text/keys appear and no
research or Anthropic calls occur.

## Validation and red-team evidence

The following original implementation runs are historical; the audit correction
validation below supersedes their final counts.

Incremental new research tests ran first; the initial 208 passed. Three initial
SQLite datetime-adapter warnings in new ops SQL were corrected by explicit UTC
string binding, without warning suppression. Additional subject/context/markup/
transport/migration cases bring the final research suite to 222 passing cases.
The final URL red-team review also found and closed a lexical alias gap: known
wildcard/loopback domains and hostnames containing obvious private/reserved IPv4
labels could otherwise pass. Seven regression cases bring the final count to 229.

| Validation | Result |
| --- | --- |
| New research suite | 229 passed, 3.99 s |
| Packet + chaos suites | 90 + 190 = 280 passed, included in focused/full runs |
| Initial packet/chaos/database/scheduler regression | 318 passed, 24.33 s |
| Other affected config/CLI/scheduler/batch/scoring/LLM/database/import suites | 249 passed, 7.00 s |
| Final combined focused suite | 758 passed, 32.15 s |
| Complete sandbox split | 1,516 passed, 35.19 s |
| Established outside-sandbox browser/FastAPI split | 159 passed, 9.53 s |
| Complete offline total | 1,675 passed |
| Final warnings / skips / xfails | 0 / 0 / 0 |
| `git diff --check` | Passed |

The established outside split is test_apply_open, test_dashboard_apply,
test_apply_ashby_dom, test_search_state, test_dashboard, test_application_state,
test_grounded_yesno, test_extension_scan_dom, test_extension_fill_dom and
test_extension_api. Local Chromium/FastAPI sandbox limitations are documented
in PACKET_HARDENING_REPORT.md. New research tests trap socket connect, DNS,
real HTTP transport and real Anthropic construction; all provider work is fake.

| Attempted failure class | Regression evidence |
| --- | --- |
| 1. Private data transmission | Captured public-only payload with private input/job/scoring markers; outbound traps. |
| 2. Key leak | SecretStr serialization, Authorization-only capture, response echo rejection, CLI/DEBUG/cache checks. |
| 3–5. Excess calls, unnecessary B, hidden retries | Sufficient A=1; insufficient valid A≤2; provider/transport/schema failure=1; explicit transport flags. |
| 6–7. Provider changes queries/instructions | Title/sentence injection matrix; exact code-owned query sequence and no successful cache. |
| 8–9. Invention, paraphrase, clause joining | Exact cleaned substring assertions; unchanged "we"; no subject inference; line/HTML/table/script block tests. |
| 10–11. Unsafe/social/job sources | Private/reserved/credential/scheme/suffix/social/subdomain/board/path matrices; no DNS calls. |
| 12. Raw data cached | Raw-page navigation and unused-answer markers absent; only selected fact JSON persisted. |
| 13. Stale fallback | Failed expired refresh leaves identical old row but returns no facts. |
| 14–15. Paid writing/capacity on incomplete | Packet integration proves no writing rows/calls, no capacity_day, no artifacts. |
| 16–18. Dry-run/list/ops research | Research traps on service and CLI operations; read-only aggregate tests. |
| 19. Retrieval-only repeated spend | Same packet/fact identity after refresh; unchanged writing call count. |
| 20. Damaged v6 state | Genuine populated snapshot, exact raw-row/index/trigger comparison, FK and rollback tests. |

## Explicit dangerous-path answers

Under the implemented local service contract, all fifteen answers are **NO**:

| # | Question | Answer |
| --- | --- | --- |
| 1 | Known automatic path sending candidate-private fields to Tavily? | NO |
| 2 | Known path inventing/paraphrasing company facts? | NO |
| 3 | Known path accepting a lexically private/unsafe source URL? | NO |
| 4 | Known path treating provider injection as executable instructions? | NO |
| 5 | Tavily during dry-run? | NO |
| 6 | Tavily during packet list? | NO |
| 7 | Tavily during ops? | NO |
| 8 | Anthropic when research is incomplete? | NO |
| 9 | Incomplete research newly reserves packet capacity? | NO |
| 10 | One uncached research operation exceeds two calls? | NO |
| 11 | Failed provider request automatically retried? | NO |
| 12 | Tavily key enters logs/database/cache/CLI output? | NO |
| 13 | Tavily failure silently falls back to fixtures? | NO |
| 14 | Expired facts silently served after refresh failure? | NO |
| 15 | Retrieval-time-only changes force duplicate paid writing? | NO |

## Remaining trust boundaries

No universal safety or source-truth claim is made. Tavily and publishers can
return false claims or falsely attributed content. Source ownership, DNS
resolution and current public accessibility are not verified: URL validation is
lexical, and source pages are never fetched. Unknown aggregators or injection
wordings may evade finite rejection lists. Strict extraction, English predicates,
sentence punctuation and line boundaries reduce coverage and may reject usable
prose; source facts can still fail existing downstream writing lint.

The host, public company/title classification, local candidate files, SQLite and
configured custom researchers/executors remain trusted. A hostile process with
the same write rights can tamper with them. Deliberately injected transports or
executors that secretly perform other network actions are outside this production
transport contract. Packet builds retain the existing local serialization;
independent direct researcher invocations are separate bounded operations and
do not share a distributed in-flight credit reservation. A crash before successful
cache commit can lose research and a later explicit operation can spend again.
No daily Tavily-wide budget or provider-credit reconciliation was added.

The REST contract was subsequently verified for live compatibility by the
controlled smoke test below; source truth was not independently verified.
12-second phase timeouts and elapsed guards are not an absolute OS-level deadline.
No dependency, architecture change, packet safety weakening or unresolved
observed duplicate-writing/private-transmission failure required a hard stop.

Final working tree is intentionally modified/uncommitted: the fourteen files
listed above. No commit or push was performed.


## Narrow per-result audit correction

This correction changes exactly `src/job_agent/tavily_research.py`,
`tests/test_company_research.py`, and `COMPANY_RESEARCH_REPORT.md`. All other
working-tree changes predated this correction and were preserved. The production
change replaces the individual-row structural exception with a skip; request
validation, source/injection checks, query loop, cache and packet behavior remain
unchanged. No live provider calls, dependency installs, commits or pushes occurred.

Added 37 regression cases: 35 unusable-row variants each mixed with three good
rows, one conditional Query B case, and one all-unusable packet integration case.
Five individual-row cases formerly classified as fatal request errors were moved
out of that classification and covered by the new matrix. Net increase: 32 cases.

The matrix proves null/missing/non-string raw_content, missing/non-string
URL/title, non-object rows, blank/oversized fields, unsafe/blocked sources,
malformed Unicode, key markers, injection and content-only fallback attempts
preserve exactly the three good facts with one request and a valid cache entry.
Bad rows plus insufficient good rows use exactly A and B; all unusable rows across
both produce research_incomplete with no cache, Anthropic/writing calls, capacity
or artifacts. FakeTransport asserts every operation stays at most two calls.
Malformed JSON, non-object root, missing/non-list results and excessive results
remain in the fatal-request matrix, which proves one call and no cache alongside
provider/transport/timeout failures. Existing privacy, source, injection, cache,
no-retry, packet-capacity and Anthropic-blocking regressions all pass.

| Correction validation | Result |
| --- | --- |
| Company research suite | 261 passed, 5.09 s |
| Packet + chaos + affected database/config/CLI/scheduler/batch | 380 passed, 26.13 s |
| Complete sandbox split | 1,548 passed, 34.57 s |
| Established outside-sandbox browser/FastAPI split | 159 passed, 10.08 s |
| Complete established offline total | 1,707 passed |
| Warnings / skips / xfails | 0 / 0 / 0 |
| git diff --check | Passed |

The browser/FastAPI split stalled under the sandbox and was interrupted before
results, then passed outside the sandbox with offline fixtures. The same ten-file
split documented above was used. Ops behavior is covered by the company research
suite; all remaining tests are included in the complete offline run. Final git
status retains the original modified/untracked production slice; no commit or
push was made.

## Controlled live Tavily smoke test

The prior offline-only implementation and audit had already passed before this
controlled live Tavily smoke test occurred. The test used a temporary SQLite
database and synthetic public job context only: company = `Microsoft`,
title = `Software Engineer`, source = `demo`. No candidate `facts.yaml`, answer
bank, resume, production database, or Anthropic call was involved.

The live researcher successfully returned exactly three facts. Returned sources
included Microsoft-owned pages and one third-party public page. This verifies
live compatibility of `POST https://api.tavily.com/search`, Bearer authentication,
advanced/general search, `include_raw_content="text"`, and the current response
parsing/extraction path. The exact number of Tavily requests is not asserted.

This result does not independently verify source truth or establish universal
safety. The remaining trust boundaries documented above still apply.
