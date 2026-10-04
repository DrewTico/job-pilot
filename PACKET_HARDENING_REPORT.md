Job Pilot M1 packet hardening report

This pass hardens the existing uncommitted packet slice. No commit, push, live
Anthropic call, live research, outbound action, approval record, discovery-filter
change, or production facts/answer-bank/resume edit was performed. Test candidate
inputs, research, provider responses and database files are synthetic and local.
No dependency was installed. Existing project rules and test coverage are retained.

The packet fingerprint commits the scoring fingerprint, hashes of both approved
input files, the explicit sanitized job/scoring writing context, sorted semantic
company-fact identities, tailoring and cover prompt contents, packet prompt
version, tailoring policy, verifier version, lint policy, tailoring/writing models,
GitHub readiness, GPA requirement, cover-letter acceptance and sorted unique
required screening questions. Style memory is not used by this slice and is not
hashed. The explicit writing context includes company, title, location,
description and other Job fields actually supplied to writing, with suspected
injection descriptions replaced by the exclusion placeholder.

Excluded inputs are database IDs, canonical row IDs, search-run IDs, search-result
IDs, scoring-work IDs, first/last observation bookkeeping, scoring status,
research retrieval time, packet/work states, capacity day, creation/update/ready
times and other operational metadata. Job source IDs, URLs, apply URLs and posting
timestamps are excluded from the direct writing-context hash because they are not
sent to writing. The required scoring fingerprint remains an input: changes made
upstream to that fingerprint invalidate packets. Approved source hashes commit
validated parsed values, preserving explicitly saved answer-bank fields. Raw file
hashes remain provenance only; comments, YAML formatting and dictionary order do
not cause another paid generation. Meaningful approved content changes invalidate
packets. Skills categories are ordered deterministically in writing context.

Public semantic fact identity uses whitespace-normalized and NFC-normalized text,
normalized company identity and the canonical source URL. Company identity is
case-folded. Fact text preserves case. Category and source title are omitted
because they are not supplied to writing; source titles still undergo the
injection gate. Retrieval time is provenance only. Database fact row IDs scope
that stable identity to a stable source/job key so each record can be checked
against its job context. Canonical database row IDs are relational references,
not semantic identity. Equivalent facts tomorrow reuse their identities and
packet version.

URLs require HTTP(S), a public host and no embedded credentials. Localhost and its
subdomains, .local/.internal hosts, nonglobal numeric addresses, reserved and
multicast addresses are rejected. Comparison normalizes scheme/host, default
ports, trailing slash, fragments, query-key ordering (preserving meaningful order
within repeated keys) and utm_*/gclid/fbclid tracking
parameters. Stored validated source URLs retain human-facing provenance. Either
duplicate canonical URL or duplicate case-folded fact text prevents a second fact
from counting. Exactly three unique usable facts are selected deterministically.
The configured researcher supplies all actual build research; selection and
dry-run never call its research method or a writing provider.

Resume grounding parses blocks. Each experience block must match one exact
approved (role, company, duration) triple, and its description, responsibilities,
achievements and metrics must belong to that same record. Project headings and
bullets are bound to one project. A project description that is not represented
in the current approved project schema is rejected rather than guessed. Summary,
education and certifications remain exact approved entries. Skills must retain
approved category/value membership. Truthful selection and reordering pass;
cross-record mixtures and recombinations of approved words/numbers fail. No fuzzy
semantic matching is used. Required GPA must be present and bind to the explicit
approved GPA field with exactly 3.18; another approved metric cannot authorize GPA.
A missing or incompatible approved GPA blocks before any provider request.
Rendered DOCX members and PDF text are compared with
local renders of the structurally verified face, in addition to the existing
format, no-drift, PDF and writing gates.

Every required question is in exactly one of answers or manual_needed. Stable
fields use only explicitly saved values; exact prepared-answer keys copy the
exact saved response. False is retained, permitted explicit empty/decline values
are retained, and unsaved demographic defaults are excluded. No model assembles
screening answers. Exact explicitly saved EEO field names and dotted field paths
are supported, with no natural-language question matching. Conflicting structured
facts/bank answers, blocked GitHub answers and incompatible GPA answers block
publication without rewriting the saved response. Ready/reuse validation also compares the complete screening
structure with the approved saved bank so corruption cannot silently omit or
invent a response.

Claims use a nonblocking Linux flock for cooperating local builders, unique packet
fingerprints/versions, BEGIN IMMEDIATE arbitration and a unique writing claim per
packet/task. Active contention raises packet_build_in_progress; the CLI explicitly
reports it and returns 2. No provider IO occurs under a SQLite write transaction.
The capacity day is sampled once during the claim and never reassigned. All
reserved packet states consume that original America/New_York day. Incomplete
research that never reserves a paid build does not consume capacity. Existing
legacy reservations without a capacity day are backfilled from their original
creation/claim timestamp, not migration time. Failed and unresolved prior-day
claims do not consume future-day capacity. Midnight, 23-hour spring-forward and
25-hour fall-back boundaries are tested.

Writing states are in_progress, succeeded, failed and recovery_required. Claims
record packet reference, model, prompt name/version, update time and a sanitized
reason. Successful text is checkpointed before parsing, grounding or rendering.
Budget/pricing admission rejection is failed; potentially ambiguous provider
exceptions are recovery_required. A hard death leaves in_progress, which remains
fail-closed without age-based timeout or retry. Changed writing requests within
one packet/task cannot create a second paid claim. Raw provider errors, private
prompts and keys are not operational metadata. Context-local log redaction also
covers synchronous SDK, SQL and PDF DEBUG messages during build, selection and
listing; ordinary unrelated application logs remain unchanged. No automatic operator-review
resolution was added.

Publication creates a fresh packets/.staging/<safe-id>-<unique> directory. Only
resume.pdf, resume.docx and resume.face.txt are accepted. Every artifact must be
nonempty, regular, within the packet tree and not a symlink; PDF and DOCX containers
are checked, and bounded file/ZIP sizes limit malformed artifacts. SHA-256 and
size manifests use relative artifact names. File and directory fsync precede a
durable verified DB manifest checkpoint. Linux renameat2(RENAME_NOREPLACE)
atomically publishes without clobbering a racing final directory. Only then is
packet_ready committed. Ordinary failures remove staging safely and preserve any
final directory. Orphan staging is never accepted. A pre-existing unverified final
directory or mismatched published manifest requires review before any provider
call. Packet listing exposes the generated packet ID and original capacity day.

Fresh schema v6 has CHECK constraints for packet status, cover acceptance,
verifier/lint status, writing state and basic ready-state consistency; packet
fingerprint, job/version and packet/task claims are unique. Additive upgrades of
earlier development v6 files enforce equivalent enum/ready restrictions with
triggers, add writing references and metadata, and enforce immutable capacity
reservations. Service-level ready invariants additionally require three unique
existing same-job/company facts with exact semantic prompt provenance, complete
screening classification and values, both succeeded writing tasks, the verified
cover checkpoint, complete artifact manifest, passed gates and present scoring
and packet fingerprints. Ready reuse rechecks facts, screening, cover and hashes.

All requested audit groups have implementation and offline regression evidence:

| Audit | Implementation/evidence |
| --- | --- |
| A, B, C | Semantic context/fact helpers; metadata/retrieval/URL variants reuse; unsafe URL rejection and unique fact dedupe. |
| D | Local ranking/dry-run; configured, including falsey, researcher only; build continues past actual reused packets. |
| E, U | Two employers/projects, swapped identities/dates/descriptions/bullets/metrics/tools and recombined words rejected; truthful subsets/reordering accepted. |
| F, T | Exact saved/prepared answers, false and explicit demographic values; unknown questions manual; no missing classification; corruption rejected. |
| G, V | Atomic immutable day reservations, cap 8 over 20 concurrent workers, all reserved states, prior-day unresolved work, midnight/DST and final-slot process race. |
| H, I | One packet/version and at most one request per writing task in two-process races; durable checkpoints and explicit unknown work. |
| J | Enum CHECKs/triggers, unique claims, immutable reservation trigger and impossible-ready service tests. |
| K, L, M | Real staging/publishing, content binding, no-replace race, symlinks/FIFO/collision/pre-existing directory/truncation/hash tests, and published-before-ready restart. |
| N | Missing/wrong-company/wrong-job/duplicate/modified fact IDs all fail closed. |
| O | HTTP/live-client/apply/browser/submit/approval/tracker/dashboard outbound traps; no application events or job state mutations; no email/calendar/LinkedIn implementations or tool execution in packet writing. |
| P | All specified instruction fixtures excluded/flagged; immutable candidate facts; no tools or outbound actions. |
| Q | Three secret/private/provider markers in failures and approved synthetic sources; captured logs, errors, CLI and operational metadata do not leak them; employer-facing saved answers remain exact. |
| R | Populated genuine v5 file with all eight old tables, exact raw-row/index comparison, preserved append-only triggers, empty new tables, clean FK check and user_version=6; earlier migration tests preserved; legacy v6 additive upgrade also tested. |
| S | New service/reopened engine, research insertion order, JSON ordering, retrieval/URL equivalence and meaningful-input invalidation; exact writing claim guard and stable selection keys. |
| W | Fault seams and actual process-death tests described below; provider outcomes remain fake/offline. |
| X | Read-only packet building/recovery/failure/ready-day and writing in_progress/recovery counts; legacy unknown capacity-day count is reported as unknown. |
| Y | Actual verifier, grounding parser, SQLite transactions, capacity arbitration, writing claims, renderer and publisher exercised; fake providers only. |
| Z | New chaos suite, focused suite, complete sandbox/outside-sandbox suite, diff and status checks. |

Restart outcomes are explicit:

| Crash boundary | Durable evidence and restart |
| --- | --- |
| 1. Before packet DB claim | No reservation or writing claim; a fresh claim may proceed. |
| 2. After packet claim commit | Original day stays reserved; no writing claim means generation may start safely. |
| 3. Before writing claim | No request for that task; a claim may proceed. |
| 4. After writing claim, before provider | in_progress remains ambiguous; operator review, no provider retry. |
| 5. Known admission/provider failure | Sanitized failed or recovery-required evidence; no automatic repayment. |
| 6. Provider may have started, then hard death | in_progress remains unknown; no retry. |
| 7. Successful output before checkpoint | Lost success is still unknown; no retry or invented output. |
| 8. After writing checkpoint | Reuse that output; only a never-claimed next task may call its fake/approved executor. |
| 9. Between resume and cover generation | Resume checkpoint reused; cover may run once only if never claimed. |
| 10. After both outputs | Revalidate cached outputs and render locally, no writing calls. |
| 11. During staging render | Partial staging removed on ordinary exit or ignored after hard death; reconstruct locally from checkpoints. |
| 12. Rendered but not verified | No final artifacts trusted; re-render and verify locally. |
| 13. Verified before atomic rename | Verified DB checkpoint exists but staging is not a ready packet; deterministic local reconstruction may republish. |
| 14. Renamed before ready commit | Authenticate final files against the checkpoint, facts/screening/cover/writing gates, then finalize; no writing call. |
| 15. After ready commit | Validate existing ready packet and return canonical version; no writing call. |

SystemExit seams cover each logical phase, with separate known-failure and
provider-started cases. Actual os._exit deaths cover lost provider output,
checkpointed output and atomic publication. Two independent processes race the
same fingerprint and the last capacity slot. Foreign keys and reservation bounds
are checked after restart cases.

Validation refreshed on 2026-10-04 from the existing working tree: 190
chaos/red-team cases and 90 packet cases (280 passed in 21.55s); 586 focused
cases covering packets/verifier/research/answers/career facts/tailoring/lint/
rendering/PDF/accounting/ops/database/migrations/CLI/batch/scoring/scheduler
(586 passed in 26.49s); 1,446 complete offline tests, split into 1,287 sandbox
cases and 159 outside-sandbox browser/FastAPI cases. No final test warnings,
failures, skips or xfails. The full split passed in 29.16s and 9.94s respectively.
Chromium cannot launch inside the sandbox (Operation not
permitted), and FastAPI TestClient hangs there; the affected existing suites run
outside it. The saved Ashby fixture aborts all resource requests, preventing its
reCAPTCHA iframe from contacting external sites.

The initial sandbox browser failure and interrupted TestClient run are environment
limitations, not reported as passing tests. Final validation uses the successful
complete split. git diff --check is clean. git status remains dirty/uncommitted;
its exact final output is reported in the final response. Existing uncommitted
README/config/CLI/database/input-loader/scoring tests, packet files and cover
prompt were preserved and extended. This pass also changes ops and the saved DOM
fixture's network isolation, and adds the chaos tests and this report.

This is not a claim of universal bulletproofness. Remaining trust boundaries and
operational limitations are explicit:

- Public source records are checked for identity, uniqueness, public URL safety
  and prompt provenance, but this offline slice cannot independently corroborate
  their factual assertions against a live publisher. A dishonest configured
  researcher/local research fixture can supply falsely attributed company facts.
- The local filesystem, SQLite database and approved input files must be protected
  from a hostile process with the same write privileges. Pre-existing symlinks,
  malformed artifacts and cooperating-process races are defended and tested;
  arbitrary concurrent namespace/file/DB tampering by that privileged writer can
  still defeat path/content checks or corrupt records. Path operations are not an
  end-to-end hostile-writer isolation boundary.
- A crash after a provider accepted work but before the success checkpoint cannot
  recover the lost text offline. It stays unknown and blocks automatically repeated
  spend, even when that means manual review of a request that never actually ran.
- Exact extraction and artifact content equivalence can reject truthful alternative
  formatting, paraphrases or LibreOffice reading orders. These are fail-closed
  availability limits; no fuzzy fallback or additional paid repair call is used.
- Linux/WSL flock, fsync and renameat2 on a trustworthy local filesystem are required.
  Unsupported publication primitives fail closed. Distributed/network filesystems
  and non-Linux platforms are not covered by this local concurrency design.
- Reusing one database with different data roots, bypassing this service via direct
  SQL, or deliberate provider/executor implementations that secretly retry requests
  are outside the tested contract. Production Anthropic retries are disabled.
- Prompt-injection detection is conservative and finite. Unrecognized wording may
  enter the user-data context, but extractive structural provenance and the absence
  of tool/outbound execution remain independent gates.

Under the tested local service contract, there is no observed remaining path to
false candidate claims, duplicate paid requests for the same packet/task, accepted
partial/corrupt packets, reservation overshoot, silent missing screening answers
or outbound action. The dishonest-researcher and hostile-local-writer boundaries
above remain relevant to falsely sourced company claims, corruption and possible
bypasses if the trusted host or configured executor is compromised.

Continuation review: all requested hardening areas were already implemented.
No demonstrated safety gap required an implementation change, so this continuation
preserved all code and tests and only refreshed this report. No safety test was
disabled. No production private file was modified, and no commit/push or live
API/web/outbound operation was performed.

The retained uncommitted files and their reasons are:

| File | Reason |
| --- | --- |
| src/job_agent/packets.py | Claims, semantic identity, cached writing, verification, staging/publication and recovery. |
| src/job_agent/packet_verify.py | Extractive candidate truth and structural employer/project provenance. |
| src/job_agent/research.py | Explicit local research boundary, public URL validation, dedupe and semantic fact identity. |
| prompts/cover_letter_v1.txt | Structured sourced/extractive cover output contract. |
| tests/test_packets.py | Offline packet behavior and safety regressions. |
| tests/test_packet_chaos.py | Adversarial boundaries, concurrency, corruption and process-death integration. |
| src/job_agent/database.py | Schema v6 packet/fact/writing persistence, constraints and preservation migrations. |
| src/job_agent/ops.py | Read-only recovery and writing-state visibility. |
| src/job_agent/apply/answer_bank.py | Explicit saved-value semantic hash, raw provenance hash and private validation-error redaction. |
| src/job_agent/tailor/career_facts.py | Validated candidate semantic hash, raw provenance hash and private validation-error redaction. |
| src/job_agent/config.py | GitHub readiness gate. |
| src/job_agent/cli.py | Local packet build/list entry points and sanitized failures/contention. |
| tests/test_database.py | Schema v6 table/version expectations and future-version rejection. |
| tests/test_batch.py | Migration expectations updated to v6 while preserving scoring/FK checks. |
| tests/test_apply_ashby_dom.py | Legitimate shared offline-test compatibility: abort saved fixture resources, including its external reCAPTCHA iframe; no form behavior or safety assertion removed. |
| README.md | Packet usage, safety contracts and operational limits. |
| PACKET_HARDENING_REPORT.md | Audit evidence, refreshed validation and limitations. |

Explicit final risk assessment for the ten requested failure classes:

1. False candidate information: no known admitted generated path under the approved
   ledger contract; exact saved answers remain trusted approved input and are not
   independently proven true by this slice.
2. Cross-employer/project mixing: structural block checks reject it in resumes;
   cover candidate lines are exact approved statements and cannot add attribution.
3. Duplicate paid generation: no known automatic path for the same request under
   the local service contract; identical requests share durable claims across
   packet versions. A secretly retrying custom executor remains outside it.
4. Corrupt/partial artifacts: no known accepted service path; hostile same-privilege
   concurrent tampering remains the documented host trust boundary.
5. Daily-cap overshoot: no known service path; immutable original-day reservations
   and serialized SQLite claims passed thread/process and midnight/DST tests.
6. Unsourced company claims: generated openings must copy supplied source facts,
   but falsely attributed assertions from a dishonest researcher remain possible
   because publisher corroboration is not performed offline.
7. Missing screening answers: every required key has an exact saved answer or an
   explicit manual-needed classification; ready/reuse corruption is rejected.
8. Outbound without approval: no packet action path; fake-provider outbound traps
   and unchanged application state passed. Production writing itself can call the
   configured paid provider, but this validation used only offline fakes.
9. Transient metadata regeneration: excluded metadata and formatting do not change
   semantic identities; upstream scoring-fingerprint changes can create a packet
   version, while identical writing requests still reuse checkpoints.
10. Ambiguous automatic retry: none; in-progress/recovery-required work blocks
    automatically repeated requests, including across screening-only versions.

Final git diff --check passed. Final status retains the same 10 modified tracked
files and seven untracked files listed above; there are no production private-file
changes. All requested implementation and test work remains uncommitted.
