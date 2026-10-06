# job-agent

An AI job-hunting agent. It discovers roles freshly posted on companies' public
Applicant Tracking System (ATS) boards, filters them to what you actually want,
and uses an LLM to score how well each one fits you — then prints a ranked table.

> **Status: Slices 1–4 shipped, plus a local dashboard and a Chrome extension.**
> Slice 1 does discovery + scoring; Slice 2 tailors your résumé to a matched job
> as an ATS-safe PDF, gated by a bidirectional no-drift honesty check; Slice 3
> adds a validated answer bank; Slice 4 does browser-based assisted apply that
> fills the real form but submits only behind an explicit `--submit` flag *and*
> your per-application approval. On top of those: a local web dashboard
> (search / tailor / track / apply), a Chrome MV3 extension that fills forms in
> your own logged-in browser, an application tracker, and a board-token
> discovery utility.

## Why this exists

Company career pages are backed by a handful of ATS vendors that expose **public,
no-auth JSON APIs**. Instead of scraping aggregators (which violates their terms),
`job-agent` reads these official endpoints directly, normalizes every board into
one shape, keeps only recently posted roles (default: the last 14 days) that match
your keywords and location, and spends an LLM call only on those survivors.

**Deliberate constraints:**

- **No scraping of LinkedIn / Indeed / Dice.** Discovery has two modes, both
  official public APIs: **per-company** ATS board endpoints (Greenhouse, Lever,
  Ashby, SmartRecruiters) enumerated from the board list in your profile, and
  **cross-company** query sources (SmartRecruiters search, Remotive, RemoteOK)
  that return jobs from many companies per keyword. Greenhouse/Lever/Ashby have
  no cross-company index, so the `discover` subcommand grows the board list by
  validating candidate company tokens against those same official APIs.
- **Application submission is never done via ATS APIs** (those submit endpoints
  need the employer's private key). Submission is browser-based and always stops
  at a human-approval gate.
- **Secrets and personal data are gitignored** (`.env`, `/data`, resume files).

## Quick start

The CLI has six subcommands — `search`, `tailor`, `apply`, `applications`,
`dashboard`, and `discover`. A bare invocation with no subcommand defaults to
`search`.

### Demo mode — no API key, no network

```bash
pip install -e .
playwright install chromium            # one-time, only needed for CLI `apply` and
                                       # the dashboard's controlled-window flow
python -m job_agent search --demo    # discover + score (mock jobs)
python -m job_agent tailor --demo    # tailor a FAKE resume to a FAKE JD -> sample PDF
python -m job_agent apply  --demo    # fill + "submit" a LOCAL fake form, end to end
```

`search --demo` runs the whole discovery pipeline against bundled mock jobs
(same filters/ranking as a real run, offline stand-ins for the source + scorer).
`tailor --demo` tailors a committed fake resume to a fake job and writes an
ATS-safe sample PDF + DOCX. `apply --demo` opens a committed local HTML form over
`file://` (zero network, no real employer), fills it from a fake answer bank +
fake resume, prints the full review, pauses for a simulated approval, "submits"
to the local page, and saves a confirmation screenshot — the entire assisted-apply
flow with no real-world side effects.

```
Pipeline: fetched 6 → keyword 5 → recency(30d) 5 → location 4 → seniority 4 → dedup 4 → experience 4
                        Ranked job matches
  #  Score  Verdict   Title                       Company            Location
  1   89    strong    Data Scientist, Growth      Meridian Labs      Austin, TX
  2   77    strong    Senior Data Engineer        Northwind Analytics Remote (US)
  3   77    strong    Machine Learning Engineer…  Cobalt AI          New York, NY
```

### Real run

```bash
cp .env.example .env                                  # add your ANTHROPIC_API_KEY
cp search_profile.example.yaml search_profile.yaml    # edit roles / companies / location
cp data/answer_bank.example.yaml data/answer_bank.yaml # fill your real apply answers
python -m job_agent search                            # fetch, filter, score, rank
python -m job_agent tailor --job <ID>                 # tailor your resume to a match
python -m job_agent apply  --job <ID>                 # assisted apply (dry-run by default)
python -m job_agent apply  --job <ID> --submit        # real submit (still needs your OK)
python -m job_agent dashboard                         # local web UI + extension backend
python -m job_agent applications                      # the tracked log of every attempt
python -m job_agent discover                          # grow the board list (see below)
```

`search` fetches live jobs from the boards in `search_profile.yaml`, filters to
the recency window (default 14 days), scores each survivor, prints them ranked
— hiding jobs you already applied to (`--include-applied` shows them) — and
saves the run to `data/job_pilot.sqlite3` (under `Settings.data_dir`). `tailor --job <ID>` (an ID from that
table) re-fetches the full JD, tailors your base résumé to it, runs the no-drift
gate, and writes `data/output/<company>_<role>.pdf` (+ `.docx`) plus a NOTES
block to review. `apply --job <ID>` opens that job's application in a
**visible** browser, fills it from your answer bank + tailored PDF, and shows a
full review — see below.

On first real use, existing `last_search.json` and `seen.json` are imported
transactionally. Malformed JSON stops cutover. Successful import leaves both
files unchanged; subsequent searches and readers use SQLite only. Demo commands
remain isolated. Job lookup accepts a unique external ID, `source:id`, or
`canonical:<uuid>`; ambiguous bare IDs produce an error.

Useful search flags: `--profile PATH`, `--limit N`, `--days N` (recency
window, default 14; `--max-age-hours N` overrides it for sub-day windows),
`--include-applied`, `--method {structured,tool}`.

## How it works

```
sources/ (Greenhouse, Lever, Ashby, SmartRecruiters
          + cross-company: sr-search, Remotive, RemoteOK)
   │  each fetch() -> list[Job]   (coded against real API shapes, not guesses)
   ▼
search.py   keyword ─▶ recency ─▶ location ─▶ seniority ─▶ dedup ─▶ experience
   │            every stage's survivor count is reported (no silent truncation)
   ▼
scoring.py  LLM fit score per surviving job  ─▶ ScoredJob {score, verdict, …}
   │
   ▼
cli.py      ranked rich table
```

**Normalization.** Every board becomes one immutable `Job`
(`models.py`): `id, title, company, location, url, apply_url, source,
posted_at` (tz-aware), `remote`, `country`, `description`. Each source was
written against a real captured response — see `tests/fixtures/`.

**Keyword pre-filter first.** Company boards carry hundreds of unrelated roles.
Titles are matched against your keywords *before* anything expensive, so no LLM
call is ever spent on an off-target job.

**Recency window (default 14 days, `--days`).** Uses each board's real post date (Greenhouse
`first_published`, Lever `createdAt`, Ashby `publishedAt`, SmartRecruiters
`releasedDate`). For the rare posting with no date, it falls back to a small
seen-ids cache under `/data` ("first observed within the window").

**Location rule.** Keep remote or in-country (US by default) roles; drop known
non-US roles even if remote; keep unknown-country roles for the scorer to weigh.
When a board leaves the country blank, it's inferred from the location text
(`geo.py`) so a clearly-foreign posting ("Bengaluru, India") is dropped here too.

**Seniority + experience filters (optional).** Two profile knobs keep
over-level roles out of results entirely — dropped before scoring, like the
location rule, not merely downranked:

- `max_seniority` (e.g. `senior`) drops titles ranked above it — Lead, Staff,
  Principal, Director, VP (`seniority.py`, title-only, runs before dedup).
- `experience_years` (e.g. `5`) drops a job whose JD *unambiguously requires*
  clearly more — a hard-cued minimum ("required", "must", "minimum", "at least")
  of `experience_years + 3` or higher. Soft phrasings never drop: "8+ years
  preferred (or equivalent)" and bare figures survive; "8 years required" goes
  for a 5-year candidate (`experience.py`, runs after enrichment so every
  source's full JD is present).

Both are off when unset, so existing profiles are unaffected. The scorer then
only ranks roles that already fit your level and years.

### Scoring

Scoring uses `settings.scoring_model` (default `claude-sonnet-5-5`), configurable
via `JOB_AGENT_SCORING_MODEL`. Tailoring uses `JOB_AGENT_TAILORING_MODEL`
(default `claude-sonnet-5-5`); the classification setting is
`JOB_AGENT_CLASSIFICATION_MODEL` (default `claude-haiku-4-5-20251001`).
An explicitly supplied `JOB_AGENT_MODEL` is the legacy fallback for task settings;
explicit task overrides win. The model returns strict
JSON — `{score 0-100, verdict strong|possible|skip, reasons[],
matched_requirements[], missing_requirements[], target_tier}` — via structured outputs (`output_config.format`).
Output is parsed defensively: on malformed JSON it retries once, and if it still
fails the job is kept but marked `unscored` rather than crashing the run.

A **tool-use** path that returns the same JSON as a forced tool call is also
implemented as a reliability fallback (`--method tool`).

### Growing the board list (`discover`)

Greenhouse, Lever, and Ashby have **no** public cross-company index (verified
live: their board APIs 404/401 without a company token, and there is no public
token directory). `discover` widens coverage the only permitted way: it takes a
text file of candidate company names (`data/candidate_companies.txt`), derives
token guesses ("Modern Treasury" → `moderntreasury`, `modern-treasury`), probes
each against the official per-board APIs at ~2 requests/second, caches every
verdict so re-runs are free, and writes the validated entries in
`search_profile.yaml` format to `data/output/discovered_boards.yaml`. It never
edits your profile — you merge the entries you want by hand.

## Résumé tailoring (Slice 2)

`tailor` turns a matched job into an **ATS-safe PDF** tailored to that JD, plus a
NOTES block — and it is built around an **honesty gate**: it can rewrite emphasis
and wording, but it cannot fabricate.

- **Immutable career facts.** The base résumé (`.docx`) is parsed once into
  `data/facts.yaml` (gitignored) — the source of truth. Company names,
  titles, and durations are fixed; the tailoring model is constrained to them.
- **No invented metrics.** Only real numbers from the career facts are cited,
  woven into achievements. If a role has no real metric, a specific *qualitative*
  achievement is written instead — the résumé face never carries a `[METRIC …]`
  placeholder or bracket. Suggestions to add a real figure go in the NOTES block
  only, phrased as questions you can answer with a true number.
- **No invented certs/skills.** Only real certifications print; JD-valued certs you
  lack go to NOTES as "suggested to obtain". Gaps are flagged, never faked.
- **No-drift gate (`verify.py`) — bidirectional.** Before any PDF is written,
  the output is checked against the career facts in **both directions**: a
  fabricated or altered employer, an uncredentialed cert, or a metric number
  with no basis in the facts **fails the build loudly** — and so does an
  **omitted real employer** (every employer in the facts must appear; dropping
  a role misrepresents the career exactly like inventing one). A separate
  **scope-qualifier gate** rejects scale inflation ("multi-terabyte",
  "enterprise-scale", "firm-wide") unless the exact phrase appears in the facts
  — checked on the face *and* re-checked on the rendered artifact.
- **Professional, ATS-safe output.** A clean single-column `.docx` is the source
  of truth: large bold name with contact beneath, CAPS section headings under a
  thin rule, bold company names with **right-aligned dates**, role titles in
  *italics*, real `•` bullets, Calibri, no em-dashes. Skills stay pipe-free
  `Category: value` lines in the gated text; the renderer lays them out as a
  **two-column borderless table** in the `.docx` and PDF. The **PDF is produced
  from the `.docx` with LibreOffice** so the two match exactly (falls back to a
  bundled-font reportlab renderer if LibreOffice isn't installed). A format gate
  rejects brackets, pipes, em-dashes, company-blurb project descriptions,
  over-cap bullet counts, or missing certs; the output is then fitted to 3 pages
  and its text **extracted back out** and asserted selectable with sections in
  order. A PDF that fails extraction is a failed build.

Scoring, tailoring, and screening writing default to **`claude-sonnet-5-5`**.

## Assisted apply (Slice 4)

`apply` opens a job's real application form in a **visible** browser, fills it
from your answer bank + tailored PDF, shows you everything it will submit, and
submits **only** with both a `--submit` flag *and* your explicit approval. It is
built to be cautious by construction — the safety rules live in the code, not
just the docs:

- **Two independent locks on submit.** A real submission needs `--submit` on the
  command line **and** an in-session `approve` at the review gate. Missing either
  → dry-run or skipped, never sent (`submit.py:submit_block_reason`). Default is
  preview/dry-run. One approval submits exactly one application — there is no
  batch path.
- **Never guesses an answer.** Fields are filled only from your answer bank or
  résumé (`filler.py` is a pure `fields → FillPlan` function). An unmatched or
  ambiguous field is recorded as *unfilled with a reason* and surfaced in the
  review; a required one blocks approval until you `edit` it in or `skip`.
- **Never handles credentials or captchas.** It never creates accounts, types
  passwords, or solves captchas. On a login / account-creation / captcha it
  **pauses**, tells you what to do in the *same* browser window, waits for you to
  do it yourself, then re-checks the page is clear and resumes from where it
  paused — no reload, no lost state (`handoff.py`).
- **Full review before anything is sent.** The review prints every value *and its
  source* (e.g. `career_facts.email`, `answer_bank.salary_expectation`) plus every
  field left empty, then waits for `approve` / `edit <sel>=<val>` / `skip`
  (`review.py`). On a real submit it captures a confirmation screenshot and
  appends the outcome to `data/apply/apply_log.jsonl`.
- **Screening questions: grounded drafts, never unreviewed.** Unfilled questions
  are routed (`screening.py`): *factual* → answer bank/career facts only (blank +
  flagged if absent, no LLM); *consent/EEO* → always pauses; *free-text* ("why
  us?", "describe a project") → a Sonnet 5.5 draft grounded ONLY in your career facts +
  answer bank + this JD, run through a no-fabrication gate (unknown employers,
  unbanked metrics, "I've used their product" claims → regenerate once, else
  `[GATE-FLAGGED]`). Drafts appear at the review tagged `[AI-DRAFT]` /
  `[NEEDS-INPUT]` / `[GATE-FLAGGED]`, are editable inline, and can never be
  auto-approved. Approved answers are cached (gitignored) and re-reviewed on
  repeat questions. Factual yes/no questions the career facts settle explicitly
  come back tagged `[GROUNDED]` with the grounding fact shown ("Yes — JPMorgan:
  deployed ML models to production…") — veto-first, see the extension section.

Scope: Greenhouse / Lever / Ashby embedded forms are fully fillable; for Workday
/ iCIMS it fills what's public then pauses for you to log in — it never attempts
account creation. Playwright drives the browser (`playwright install chromium`
once). The pure logic (classification, mapping, gates, blocker detection) is
fully unit-tested with no browser; only the thin driver touches Playwright.

## Dashboard + Chrome extension

`python -m job_agent dashboard` serves a local web UI (**127.0.0.1 only**, not
configurable — it fronts personal data with no auth layer). It is also the
backend the Chrome extension talks to.

**The dashboard** shows the last search as a ranked table with each job's
tracked state joined in, and drives the same CLI code paths:

- **Search / Tailor / Resume** buttons run the real pipeline and show the output.
- **Scan metadata + new-job tracking.** The jobs-table header shows the last
  scan (as a relative time), total jobs, sources queried, and how many jobs
  were first seen in that scan; rows first seen in the current scan carry a
  **NEW** badge, and a "newest first" sort option orders by first-seen time
  ("best match" stays the default). Every number comes from persisted scan
  data — anything unavailable is omitted, never guessed. Baseline rule: on the
  first scan after the seen cache is empty there is no earlier scan to be "new
  since", so no row is badged and the new-count is omitted rather than showing
  a misleading number.
- **Application tracker** (`application_state.py`, gitignored
  `data/job_pilot.sqlite3`): per-job status (saved / applied / interviewing /
  offer / rejected), notes, and follow-up dates. Jobs with an in-flight
  application are hidden from search results by default, in both the CLI and
  the UI. A one-click **Mark applied / Undo** works whether or not autofill
  ever ran. First real tracking use atomically imports `applications.json`, if
  present, and records the cutover in SQLite. The original bytes remain unchanged;
  subsequent tracking never reads or writes that file. Invalid legacy data aborts
  the cutover. Attempt outcomes and pipeline edits append immutable events, with
  source-scoped identities and canonical job relationships. `apply_log.jsonl`
  remains a separate audit artifact.
- **Apply** opens the job's stored apply URL in **your own Chrome** (real
  profile, extensions loaded — `open -a "Google Chrome"`, falling back to your
  default browser) and queues a fill task for the extension; the extension's
  fill status reports back into the panel. No automation-controlled window in
  this path. The previous Playwright-assisted flow — separate visible window,
  in-UI review gate, explicit submit — is still available as **"Open controlled
  window instead"**.

**The Chrome MV3 extension** (`extension/`) fills Greenhouse / Ashby / Lever
application forms in your own logged-in browser, from the same answer bank +
career facts, via the local backend only (CORS admits chrome-extension origins
exclusively; pin yours with `JOB_AGENT_EXTENSION_ID`). Same non-negotiables as
the CLI flow: **never submits, never touches consent/legal boxes, never evades
bot detection, never talks to any external server**. The popup groups results
into *filled / drafts to review / needs your answer / you must confirm*; AI
drafts and `[GROUNDED]` facts-backed yes/no answers (each shown with the fact
that grounds it) are inserted only by your explicit click. **Load instructions,
setup, and the manual test checklist: [extension/README.md](extension/README.md).**

## Project layout

```
src/job_agent/
  models.py          Job, ScoredJob (frozen Pydantic v2 models)
  config.py          .env + search_profile.yaml loading & validation
  http.py            shared httpx client (timeout, retries, error mapping)
  sources/           one module per ATS + JobSource base
                     (greenhouse, lever, ashby, smartrecruiters
                      + cross-company: sr_search, remotive, remoteok)
  search.py          fetch → keyword → recency → location → seniority → dedup → experience
  geo.py             infer a country from free-text location (US-vs-foreign)
  seniority.py       title → seniority level (for the max_seniority filter)
  experience.py      required years-of-experience parsed from a JD
  scoring.py         LLM fit scoring (structured + tool-use paths)
  seen_cache.py      seen-ids cache for the no-post-date fallback
  demo_data.py       mock jobs + offline scorer for search --demo
  store.py           persist a search run for `tailor --job`; resolve apply URLs
  discovery.py       board-token discovery (probe official ATS APIs, cached)
  cli.py             search / tailor / apply / applications / dashboard / discover
  tailor/
    extract.py       base resume (.docx) -> data/facts.yaml
    career_facts.py  frozen CareerFacts models + allow-lists
    tailor.py        mega prompt + facts + JD -> Sonnet -> resume + NOTES
    render_pdf.py    ATS-safe PDF + editable .docx (two-column skills layout)
    verify.py        bidirectional no-drift gate + scope gate + PDF text gate
    textnorm.py      normalization shared by rendering and the no-drift gate
    jd_fetch.py      re-fetch the full JD at tailor time
    demo/            committed FAKE facts / JD / stub response
  apply/
    answer_bank.py   frozen answer-bank models + load/validate; contact merged
                     from career_facts (Slice 3)
    fields.py        immutable FormField / FillPlan value types
    form_reader.py   read + classify a form's controls (pure classify + DOM scan)
    filler.py        pure answer-bank -> FillPlan mapping; apply plan to the page
    grounded.py      facts-grounded yes/no answers ([GROUNDED], veto-first)
    screening.py     question routing + honesty-gated essay drafts
    review.py        human review gate (approve / edit / skip); blocks on missing
    handoff.py       pause/resume for login / captcha / account (pure detection)
    submit.py        two-lock submit gate + screenshot + JSONL log
    tracker.py       application log: statuses, notes, applied-jobs markers
    runner.py        orchestrates one application end to end
    browser.py       lazy Playwright launch (visible for real runs)
    prompt_io.py     console-IO seam so the gates are testable offline
    demo_apply.py    the `apply --demo` offline flow
    demo/            committed local fake form + fake answers + fake resume
  dashboard/
    app.py           FastAPI app: jobs/track/tailor/apply routes (127.0.0.1)
    service.py       thin service layer over the CLI's own functions
    apply_session.py live assisted-apply session (the CLI review gate over HTTP)
    extension_api.py the extension's endpoints (fill-values, task hand-off)
    static/          the dashboard UI (single index.html)
extension/           Chrome MV3 extension (see extension/README.md)
prompts/tailor_megaprompt.txt           the tailoring mega prompt
tests/               pytest + respx (sources, filters, scoring, tailoring, PDF,
                     answer bank, apply: mapping / review / handoff / submit,
                     tracker, dashboard, extension API, grounded answers,
                     discovery)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests are fully offline: source parsers run against saved fixtures via `respx`,
and the scorer is exercised with a fake client (valid output, retry-then-succeed,
and the unscored fallback).

## Roadmap

- ✅ Slice 1 — discovery + LLM fit scoring
- ✅ Slice 2 — résumé tailoring → ATS-safe PDF with a bidirectional no-drift
  honesty gate
- ✅ Slice 3 — application answer bank (`apply/answer_bank.py`): validated,
  gitignored PII store; work-auth required, EEO opt-in/declinable, contact merged
  from career facts. Template: `data/answer_bank.example.yaml`.
- ✅ Slice 4 — assisted apply in a visible browser (Playwright): fills from the
  bank + tailored PDF, pauses on login/captcha/unknown fields, shows a full
  review, and submits only behind `--submit` + per-application approval. Runs
  end to end offline via `apply --demo` against a local fake form.
- ✅ Local dashboard — search / tailor / track / apply from a web UI bound to
  127.0.0.1, with an application tracker and applied-jobs hiding.
- ✅ Chrome MV3 extension — fills forms in your own logged-in browser via the
  local backend; dashboard hand-off (open in Chrome, fill status reported back).
- ✅ Grounded yes/no answers — factual questions the career facts settle
  explicitly, tagged `[GROUNDED]` with the fact shown, veto-first.
- ✅ Board-token discovery (`discover`) — grow the Greenhouse/Lever/Ashby board
  list from candidate company names via the official APIs.
- ✅ Scan metadata + new-job tracking — per-survivor first-seen records, a
  scan-summary header, NEW badges, and a newest-first sort (baseline-safe:
  the first scan after an empty cache badges nothing).

## LLM accounting and budget

Screening answers use `JOB_AGENT_WRITING_MODEL` (Sonnet 5.5), not the
classification model. Explicit task overrides win over `JOB_AGENT_MODEL`;
otherwise the task defaults above apply. Classification remains deterministic;
no classification LLM feature was added.

`JOB_AGENT_SCORE_THRESHOLD=65`, `JOB_AGENT_MAX_PACKETS_PER_DAY=8`, and
`JOB_AGENT_MONTHLY_BUDGET_USD=40.00` are the defaults. All Anthropic attempts
use independent transactions in `data/job_pilot.sqlite3` (schema v5). The `llm_calls`
table stores usage, costs, latency and safe operational identifiers, never
prompt bodies or provider error details. SDK automatic retries are disabled.
Malformed scoring responses still count as paid attempts; each retry must pass
admission again. Unknown model pricing blocks before network execution.

Standard prices per 1M tokens:

| Model | Input | Output | 5-minute cache write | Cache read |
| --- | --- | --- | --- | --- |
| Sonnet 5.5 (`claude-sonnet-5-5`) | $2.00 | $10.00 | $2.50 | $0.20 |
| Haiku 4.5 (`claude-haiku-4-5-20251001`) | $1.00 | $5.00 | $1.25 | $0.10 |

Batch cost accounting applies the 50% batch modifier to every represented
billed category: ordinary input, output, cache creation/write, and cache reads.
Manual Message Batches submission and reconciliation are implemented. Unknown/custom model pricing fails closed;
an override requires a verified pricing-registry key before any paid request.

Monthly accounting uses UTC calendar months and Decimal arithmetic. At 80%
committed exposure (recorded spend + outstanding reservations), the budget
service exposes a warning; at 100% committed exposure admission pauses.
Admission also reserves a conservative text-input bound and maximum output,
so requests can be rejected below 100% when remaining funds are insufficient.
Concurrent reservations count against the cap. Immediately before admission,
the same `BEGIN IMMEDIATE` transaction reconciles standard synchronous
reservations at least one hour old. It marks them failed, charges the higher of
the reservation or existing estimated cost, clears the reservation, and preserves
operational metadata with a reconciliation marker. This deliberately overcounts
when actual usage is unknown; even a late completion cannot lower this charge.
Fresh standard and all batch reservations remain outstanding. Reconciliation
is retained even if admission is denied; reservations are never silently deleted.
Provider failures without usage record zero tokens, not invented spend.

Scoring caches stable system instructions once and repeated candidate data in
a user text block before separate untrusted posting data. Tailoring and writing
cache only stable system instructions. Cache usage comes from actual responses;
short prompts may not meet provider cache minimums. This slice is validated
with fake clients only, not with paid API calls.

Production search scores postings younger than 48 hours immediately; exactly
48 hours and older are queued. Future dates are fresh. Missing dates defer unless
an identity persisted before this scan proves first observation under 48 hours.
`JOB_AGENT_IMMEDIATE_SCORING_MAX_AGE_HOURS=48` overrides the boundary.

Schema v5 adds `scoring_work_items` and `llm_batches`. Work states are pending,
submitted, succeeded, retryable, failed, and submission_unknown. A unique SHA-256
fingerprint includes public job data, model, prompt name/version and prompt hash,
candidate summary hash, and supplied company facts. Private candidate content is
not stored in either new table. Completed identical scores are reused. Changed
inputs block old pending work from submission rather than rebuilding it with
new private context. A new search creates work for the changed input.

Manual commands (only `pending` is entirely local):

```bash
python -m job_agent batch pending
python -m job_agent batch submit --profile data/search_profile.yaml
python -m job_agent batch status
python -m job_agent batch reconcile
```

All commands accept `--data-dir`. Submit selects newest postings first, then FIFO
with stable ID tie breaks, up to `JOB_AGENT_MAX_BATCH_ITEMS=100` and a conservative
20 MiB request payload cap. Packet limits do not constrain scoring. An atomic
reservation admits the largest affordable priority prefix at the 50% batch rate;
no fitting items means no provider request. All outstanding reservations,
including prior-month batches, count toward committed exposure. No token-count
request is made. Custom IDs use `sw_<work UUID hex>_<attempt>`.

Creation exceptions retain reservations and mark submission_unknown. A crash
between reservation and recording the provider ID likewise needs manual recovery;
never automatically resubmit these items. Operators must independently establish
whether the provider accepted the batch before recovering its ID or releasing
reservations. This slice has no automatic retry or recovery command.

Status performs one idempotent retrieve per known batch. Reconcile streams results
only for ended batches and matches custom IDs rather than order. Paid successes
use returned usage including cache fields, even if output validation fails.
Malformed output becomes retryable without an automatic paid retry. Errored,
canceled, and expired items clear reservations with zero billed cost; invalid
requests become failed, while other errors, cancellations and expiry become
retryable. Unknown result types or missing paid usage retain reservations.
Repeated reconciliation does not duplicate charges or scores. Scores propagate
only to still-unscored search results with the exact same fingerprint.

Next slice: 11 PM ET orchestration. No scheduler, packet selection, or live
Anthropic compatibility test is included here.

## License

MIT

### Local scheduler and operational status

```bash
job-agent scheduler --profile search_profile.yaml --data-dir data
job-agent ops status --data-dir data
# Optional explicit one-time operations, using the same services and lock:
job-agent scheduler --once maintenance --data-dir data
job-agent scheduler --once batch --profile search_profile.yaml --data-dir data
```

Keep the scheduler process running. APScheduler uses `America/New_York` with
DST-aware timezone rules: discovery/search Monday-Friday at 06:30 and 13:00,
batch submission daily at 23:00, and safe batch maintenance hourly at minute 10.
Stop with Ctrl+C or SIGTERM. Startup logs identify the data directory, timezone
and registered schedules; execution logs contain only operational summaries.

Each job allows one instance, coalesces missed duplicates, and has a 15-minute
misfire grace period. Both discovery schedules share an operation lock; batch
submission and maintenance share another. Nightly batch submission waits for that
lock; maintenance skips if it is held. A Linux/WSL local file lock prevents
two scheduler processes for the same data directory. Do not delete
`scheduler.lock` while a scheduler is running. This is local process protection,
not a distributed lock. Fingerprint claims and database reservations remain the
final duplicate-request safeguards.

Discovery uses the CLI production search path and its existing filters and
atomic persistence. Jobs younger than 48 hours use immediate standard scoring;
older jobs queue for deferred scoring. Nightly submission first maintains known
batches, then submits eligible pending work with the existing budget, priority,
item-count and request-size limits. Maintenance only retrieves trusted existing
batch statuses and reconciles ended results. It never creates a batch and skips
unknown submissions. Fully reconciled batches are not polled again.

`ops status` reads SQLite in read-only mode with zero provider/network calls.
It reports scoring state counts, known batch progress, ended unreconciled batches,
batches without trusted IDs, monthly spend, reserved exposure, budget, warning
and paused flags. A database must already exist with the current schema.
`submission_unknown` and `standard_in_progress` require separate operator review.
Reservations and durable claims fail closed after ambiguous outcomes. Retryable
and failed work is not automatically retried. No recovery mutation commands are
provided; do not infer whether an unknown provider request was billed.

This scheduler discovers and scores jobs only. It does not tailor resumes,
submit applications, send outreach, or apply to jobs automatically.

### Local application packets (M1)

```bash
job-agent packets build --data-dir data --dry-run
job-agent packets build --data-dir data --limit 3
job-agent packets list --data-dir data
```

Build selects successfully scored jobs at or above `settings.score_threshold`
(default 65), highest score first with stable job-key ties. It excludes applied
or submitted jobs. Selection is local and provisional: exact reuse is checked
only after the configured researcher returns its actual facts. Build walks ranked
candidates past reused packets. Every paid build reserves its original
America/New_York `capacity_day` against `max_packets_per_day` (default 8),
including failed or unresolved builds for that day. Prior-day reservations never
consume later days. Linux builds use a nonblocking local lock and SQLite claims;
active contention is reported explicitly. Interrupted paid claims require operator
review and are never automatically re-paid. `--limit` bounds returned attempts.
`--profile` is accepted for command consistency; packet generation uses existing
scoring snapshots and approved facts, without changing discovery filters.
Dry-run reads local inputs and reports selection without LLM or research-provider
calls. Listing reads only packet metadata and does not print private answers.

Research is behind `CompanyResearcher.research(job)`. The default provider is
`fixture`: `data/company_research.json` maps company names to lists
of objects with `text`, public `source_url`, `source_title` (optional), timezone-aware
`retrieved_at`, `company`, and optional `category`.
Exactly three usable sourced facts are required. Duplicate normalized URLs or
texts and suspected instruction-injection snippets are excluded. Incomplete or
invalid research produces `research_incomplete`, never fabricated facts.

Production company research is explicitly opt-in:

```bash
export JOB_AGENT_COMPANY_RESEARCH_PROVIDER=tavily
# Set TAVILY_API_KEY in your local environment/.env; never commit it.
export JOB_AGENT_COMPANY_RESEARCH_CACHE_DAYS=7
```

`TAVILY_API_KEY` is required and must be nonblank. A key alone never enables
Tavily. Unknown provider names fail configuration validation. Missing credentials
or provider failures never switch to fixtures. Explicitly injected researchers,
including falsey objects, remain authoritative.

Only public company name, public job title, and code-owned static search words
are transmitted. Candidate name, contact details, GPA, resume, projects,
employment history, facts.yaml, answer-bank values, private prompts, matched or
missing requirements, and the full job description are never sent to Tavily.
Public company/title fields undergo NFC normalization, control/quote replacement
and whitespace collapse; blank values or values over 160 normalized characters
fail closed. They are quoted data, never interpreted as instructions.

Query A is `"<company>" "<job title>" engineering product technology`.
Only when a valid response leaves fewer than three safe unique facts with a
company-named opening does Query B run:
`"<company>" company product mission engineering recent`.
An uncached valid-context operation makes one or at most two Tavily Search calls.
Missing keys/invalid context can fail locally without a call. Provider/transport
errors stop that operation immediately; there are no automatic retries, including
timeouts, ambiguous transmission, authentication errors, rate limits, server
errors, malformed JSON or malformed structural schemas. An operator-triggered
later build may attempt fresh research.

Requests use only `POST https://api.tavily.com/search`, bearer authentication,
advanced/general search, eight results, raw text, no generated answer and no images.
Redirects, environment proxies and HTTP retries are disabled. Job Pilot never
fetches returned source URLs. Each connect/read/write/pool phase has a 12-second
timeout; a 12-second elapsed guard is checked as response chunks arrive and at
completion. This is not a hard wall-clock interrupt of an already-blocked IO
phase. Response bodies stream into a buffer capped at 2,000,000 bytes; compressed
responses are rejected. Each query processes at most eight results. Per-result
limits are 200,000 raw-content characters, 300 title characters and 2,048 URL
characters. Oversized bodies fail the request; unsuitable oversized results are
discarded without storing their content.

Extraction is deterministic and uses no Anthropic, other LLM, or Tavily answer.
Facts are complete contiguous source statements after NFC, entity/HTML and
limited Markdown cleanup and whitespace collapse. Paragraph/line boundaries
remain boundaries. Sentences must end in a period, contain a declarative predicate,
have 8–45 words and at most 500 characters. Noise, navigation, boilerplate,
calls to action, malformed text and suspected directives are rejected. There is
no paraphrase, clause joining, inferred subject, or replacement of "we" with the
company. Each retained result must name the company in its title or selected
statement; unrelated source statements cannot acquire a company attribution
merely from search relevance. Exactly three unique validated facts are required. At least one must
naturally name the company and satisfy the existing opening-name comparison;
production facts are ordered with that fact first. The cover verifier is unchanged.

Existing public-URL validation and canonical URL/text deduplication remain active.
Private/local/reserved addresses, credentials and unsafe schemes are rejected.
Known wildcard/loopback alias domains and obvious private/reserved IPv4 labels
embedded in public-looking hostnames are also rejected without DNS lookups.
Social sources (including LinkedIn, Facebook, Instagram, X/Twitter, Reddit,
TikTok), Glassdoor, Indeed, known additional job boards/ATS copies, and obvious
job/career URL paths are excluded, including subdomains. Selection prefers a
company-name host match, recognized public news sources, product/docs pages,
then engineering/blog pages; host matching is a preference, not proof of ownership.
Both result titles and extracted statements pass packet injection checks and
additional conservative directive/noise checks. Provider content cannot generate
queries, invoke tools or change configuration, candidate facts or approval state.

SQLite schema v7 additively introduces `company_research_cache`. Its SHA-256 key
commits to provider, researcher/query/extraction/source-policy version, normalized
company and meaningful title context. Keys, timestamps, packet IDs and random
values do not enter that identity. The cache stores only three selected public
facts and operational metadata, never raw webpages, full responses or API keys.
The default TTL is seven days; `JOB_AGENT_COMPANY_RESEARCH_CACHE_DAYS` accepts
1–30. Fresh valid entries survive restart and return exact cached facts with their
original URLs and retrieval provenance, making zero requests. Expired entries
require refresh. A failed refresh preserves the old row but never serves it;
incomplete/unsafe results never replace successful cache data. Corrupt fresh cache
entries fail closed. Retrieval-time-only or canonical-URL-equivalent changes keep
fact IDs and packet fingerprints stable and do not repeat paid writing. Meaningful
fact changes can create a new packet version.

Research failure produces `research_incomplete`: no Anthropic writing, no packet
capacity reservation, no resume/cover generation and no published artifacts.
Selection, dry-run, packet list, ops and scheduler status remain offline; startup
and migration never research. Ops reports only aggregate cache entry/fresh/expired
counts, never source text, URLs or secrets. There is no people research, LinkedIn
research, approval creation, application submission, email or outreach in this slice.
Provider truth, publisher attribution and unknown domain credibility remain trust
boundaries: source pages are not independently fetched or corroborated, and strict
extraction can fail on legitimate prose. URL checks are lexical and perform no DNS
lookups; they cannot establish public DNS resolution or publisher ownership.
See [the research validation report](COMPANY_RESEARCH_REPORT.md).

Packets contain a tailored resume PDF/DOCX with packet-relative artifact names,
SHA-256 hashes and byte sizes, a cover letter of at most 200 words, deterministic cover-letter acceptance
(`yes`/`no` only from explicit stored metadata, otherwise `unknown`), saved screening
answers, company-fact references, and an empty referral list with `not_implemented`
status. People research is deferred. There is no LinkedIn automation or outreach.

`facts.yaml` is the sole candidate ledger, loaded through the existing typed loader.
M1 writing fails closed: substantive resume lines and cover-letter candidate lines
must use approved facts verbatim; tailoring selects and reorders those lines.
Every employer's role, company, duration, description, bullets and metrics must
belong to one approved employer record. Project headers and bullets likewise
remain bound to one approved project. Skills keep exact categories and values;
summary, education and certifications remain extractive.
Existing resume format, employer/date/no-drift and PDF gates remain active. This
conservative restriction may fail otherwise valid paraphrases, requiring manual
review. Unsupported skills, tools, projects, numbers, degree/title changes,
unauthorized GitHub links and GPA fail verification. GPA is omitted unless explicit
stored metadata requires it, and then must be exactly 3.18. The writing lint blocks
em/en dashes and the existing banned phrases. Cover-letter company assertions must
be exact supplied source facts, and the opening must name the company.

`answer_bank.yaml` uses the existing typed loader. Only explicitly saved values
are copied, including work authorization, salary, relocation, start date and
saved demographics. Default demographic declines are not synthesized. Required
screening keys have exactly one exact saved answer or a `manual_needed` entry.
An exact prepared-answer match copies its full text without rewriting. Explicit
false and explicitly saved permitted empty demographic values remain saved;
unsaved defaults never become answers. No model fills those gaps.

Schema v6 transactionally adds `company_facts`, `application_packets` and
`writing_work_items` while preserving scoring and application history. Fingerprints
commit validated semantic facts/answer-bank source hashes, scoring fingerprint, the explicit
sanitized writing context, semantic company facts, prompt contents and versions,
policy/verifier versions, task models, GitHub readiness, GPA requirements,
cover-letter acceptance and the required screening-question set. Search-run and
DB IDs, observed bookkeeping, packet/work states, and research retrieval times
are excluded. Raw file hashes remain provenance; YAML formatting, comments and
dictionary ordering do not cause another paid generation. Company facts normalize company and text and compare canonical
public URLs, including ordered queries and removal of common tracking parameters;
human-visible validated source URLs are retained. Style memory is not used. Private source text is not stored in fingerprint metadata. Changed
inputs create preserved packet versions in separate packet-ID directories.
Identical successful writing responses are durably checkpointed before downstream
validation/rendering, so assembly retries reuse them. Unknown or failed writing
claims need review rather than automatic spend. Writing claims also record packet,
model, prompt version, updated time and sanitized recovery reason, with allowed
state constraints and one claim per packet/task. All production writing calls use
`AnthropicExecutor`, task-specific models and `llm_calls` accounting, pricing and
monthly budget gates; no database write transaction spans provider I/O.

This command builds local review artifacts only. It creates no approval and has
no email, application, calendar, form, or submission operation. The separate exact-packet decision backend is documented below; packet commands
do not create decisions or submit applications.

Artifacts render into fresh `packets/.staging/` directories. Regular-file, size,
ZIP, PDF, truth and content-equivalence checks precede a durable manifest
checkpoint and Linux atomic no-replace publication to the generated packet-ID
directory. Files and directories are fsynced. A crash after publication can
finalize from the checked manifest and succeeded writing outputs without another
provider request. Unexpected final files or unverifiable integrity require review;
partial staging directories never count as ready packets. Ops status reports
packet building/recovery/failure and writing unknown/recovery counts without IO to
providers. See [the hardening evidence and limits](PACKET_HARDENING_REPORT.md).

An application packet version becomes immutable for completed deliverables after
its first `packet_ready` transition. Valid ready packets reuse that exact version.
Post-ready corruption is marked `recovery_required`; a subsequent build generates
an independently identified successor version with its own artifact directory,
manifest, cover and completed evidence. It never silently regenerates into the
completed version. Successful semantic writing checkpoints may be reused across
versions, and integrity recovery does not reserve another new-job daily packet
slot. Normal paid-writing budget gates still apply.

Pre-ready crash recovery may still complete the same version, including recovery
from a durable writing or publication checkpoint. Publication retains its
no-replace protection. External hostile filesystem mutation cannot be undone
magically: deleted or corrupted original bytes are not retained for exact
restoration. The historical database evidence and any surviving artifacts remain
under the original version. Future approval records can therefore refer to one
exact immutable completed packet version.

### Run 3 local approval queue: Milestones A through D

```sh
job-agent approval-queue --data-dir data --port 8643
```

This separate approval application binds exactly `127.0.0.1`. Port defaults to
8643 and accepts 1..65535; there is no host option. It requires an existing
schema-v9 database and does not migrate or import data on startup. The legacy
dashboard and its extension routes remain separate and unchanged.

Milestone A provides a fixed local read-only shell and JSON queue, exact packet
detail and version history. The queue keeps every undecided ready version,
ordered by score descending, ready time ascending, then packet ID. Cards start
with integrity not checked. Detail uses the trusted approval preview and
reconciles the displayed packet bindings afterward; a changed snapshot returns
`stale_packet` and must be reviewed again. Historical approval is displayed
separately from current validation. Historical cover text uses the existing
writing-checkpoint authenticator. Screening exposes required saved answers and
manual-needed questions, never the complete answer bank.

Requests accept only exact configured local Host authorities and loopback
endpoints. Proxy headers are disabled and cannot redefine this origin. There is
no permissive CORS, documentation API, remote asset, cacheable private response,
or inline script/style. Security headers include a restrictive CSP, no-store,
no-referrer, frame denial and nosniff. This is local-only access, without identity
authentication. Run 4 owns authentication, Tailscale and multi-device access.

Milestone B adds `GET /api/bootstrap` and exact-packet POST endpoints for
`approve`, `reject` and `revise`. Bootstrap returns a process-scoped synchronizer
token generated from 32 cryptographically random bytes. It stays in memory and
changes when the server restarts. Every mutation requires the
`X-Job-Pilot-CSRF` header and an exact local HTTP Origin matching the already
validated Host. Origin/token rejection happens before private body reads.
Mutations require bounded JSON, forbid extra fields, and sanitize validation
errors without echoing private input.

Approve requires both the displayed packet fingerprint and approval-view
fingerprint. It never refreshes stale expectations during POST. A stale packet
or view needs another explicit review and click. Exact replay returns the
existing historical decision; current authorization is checked independently
before being reported as valid. A busy post-commit check reports current
authorization not checked while preserving the committed decision.

Reject requires one of the six trusted reasons and optional detail of at most
4000 Unicode characters; it does not tune search filters. Revise preserves exact
nonblank feedback of at most 4000 Unicode characters and commits only the Revise
decision. It does not generate, write style preferences, or start a worker in
the HTTP request. Its response includes a revision-status URI.
Creates a new packet version. The new version needs its own
approval. Exact requests replay; changed requests conflict. A dropped response
or API/browser restart does not erase a committed Revise decision.

Milestone C adds the responsive Needs Review, Processing, Needs Attention and
History sections, exact-version detail and inline decision confirmations.
Desktop uses a queue rail and readable detail area; narrow screens use a single
column with Back to queue. Private text enters the page through text nodes.
Authority tokens stay in memory; restored pages refetch before allowing actions.

Resume PDFs open only on explicit click in a separate local tab. The server
returns captured authenticated bytes after the existing historical artifact
checks, without accepting a caller path. Cover text preserves paragraphs;
screening distinguishes saved answers from manual-needed questions. If the
application asks a new question not represented here, stop and return to Job
Pilot rather than inventing an answer. Company facts remain packet-bound and
source links open only on explicit click without a referrer. History and local
resume/cover diffs are informational and never authorize a packet.

Revision status polls every five seconds while work is nonterminal. It provides
state labels, not progress percentages or ETAs. A successor requires independent
review and approval. Exact historical Reject detail or Revise feedback is fetched
separately and displayed as plain text. This server does not start a worker.

Run the approval server and revision worker in separate terminals/processes:

```sh
# Terminal 1
job-agent approval-queue --data-dir data --port 8643

# Terminal 2
job-agent scheduler --revisions-only --data-dir data
```

The revisions-only mode scans immediately on startup and then every 10 seconds
using APScheduler. It registers only revision processing; no discovery, batch or
maintenance schedule runs. `--revisions-only` cannot be combined with `--once`.
It opens only an existing schema-v9 database and requires no scoring profile.
Normal scheduler behavior remains unchanged.

A separate data-directory process lock permits one revision worker alongside
the normal scheduler. Work is selected in decision-time/ID order: committed
Revise decisions without work, or pending, style-prepared, style-persisted or
building work. Succeeded, blocked and recovery-required work is excluded.
Processing is sequential through the existing RevisionProcessor, whose global
build lock and durable checkpoints remain authoritative. Restarts recover from
those checkpoints, without resetting claims or blindly retrying ambiguous
provider outcomes. Committed requests survive browser/API shutdown. Legitimate
revision generation may call Anthropic under existing budget/checkpoint rules;
the worker never calls Tavily or an employer. Blocked or recovery-required work
requires manual review; no automatic recovery command is added.

Historical Approve and current validity remain separate. The manual application
link requires a current destination check, then revalidates on explicit click
before opening the exact URL. The server never fetches the employer URL. No
automatic navigation, form filling, upload or submission is added. Run 4 will
add authenticated multi-device access; responsive layout does not enable remote
phone access in Run 3.

### Exact packet decisions (Run 1)

Schema v8 adds the local `ApprovalService` backend for Approve, Reject and Revise
requests. Approval means Andrew authorized **this exact completed packet row and
version**. Completed versions remain immutable. The packet input fingerprint
identifies semantic inputs; it alone cannot prove completed deliverables.
Approve runs the shared read-only integrity verifier and records canonical
completed evidence, including artifact hashes, writing checkpoints, company
semantic fact IDs, cover-text hash and the exact current public application URL.
No URL is fetched. `preview_approval(packet_id, expected_packet_fingerprint)`
returns safe metadata and a deterministic `approval_view_fingerprint` of the
canonical completed evidence. Approve requires both the expected packet fingerprint
and that expected view fingerprint. A stale rendered destination or completed
view fails without creating a decision. Stale packet fingerprints fail for every
decision. Reject and Revise do not require a completed-view fingerprint.

One packet receives one append-only decision, enforced by SQLite constraints and
persistent UPDATE/DELETE blocking triggers. Identical requests replay the existing
record; changed requests conflict. An Approve replay is historical and does not
prove current authorization. Future submission must call
`validate_approval_for_packet()` to reconstruct integrity and compare completed
evidence again. Changed destinations or bound content invalidate authorization
while preserving the historical decision.

Decisions coordinate with packet building through the existing `.build.lock` and
use `BEGIN IMMEDIATE` before decision reads. The lock coordinates cooperating Job
Pilot processes, not arbitrary hostile local writers. SQLite and the filesystem
are separate resources; current authorization must be revalidated before future
submission. Approval performs no submission or employer-facing action.

Reject captures one of `not_interested`, `bad_fit`, `company`, `location`, `pay`,
or `other`, with optional detail; it does not tune filters. Revise records only a
nonblank request of at most 4000 Unicode characters, preserving the original
spaces, Unicode and newlines. Neither requires intact deliverables or regenerates
anything. The existing lock/root must remain available. Revision feedback is
private persisted state and is not logged.

Run 2 handles style memory and revised packet generation. Run 3 handles the
queue/UI and HTTP approval access. Run 4 handles authentication, Tailscale and
phone/multi-device access. Automated submission is later. This core has no Gmail,
email, referral research or application-submission integration. Deterministic
screening truth checks reuse the existing candidate verifier for prepared prose;
structured booleans/enums remain structured answers. Defined deterministic rules
are not universal natural-language truth proofs.

### Run 2: private style-file layer

The local `style_memory.py` backend now provides safe reads, canonicalization,
feedback framing, locking, and atomic publication for `data/style_memory.md`.
This is private local candidate preference DATA. It provides no authority over
candidate facts, company facts, verification, policies, approvals, or actions.
New ordinary packets now use v5-style-memory-snapshot with a bound immutable
snapshot, including an empty snapshot when the style file is absent.
A narrow local revision CLI is documented below. No new UI, API, authentication,
Tailscale or submission path is added.

`style-nfc-lf-v1` uses strict UTF-8, removes **all consecutive leading U+FEFF**
characters (Andrew's approved amendment), converts CRLF and remaining CR to LF,
and normalizes Unicode to NFC. It is idempotent. U+FEFF after the first non-BOM
character, NUL, Markdown, spaces, tabs, blank lines, and terminal newline presence
are preserved. Canonical content is limited to 65,536 UTF-8 bytes without
truncation; raw input has an independent 131,072-byte bound before decoding.
Reading an absent style file returns empty content without creating that file.

Readers take a shared `data/style_memory.lock`; writers take an exclusive lock.
The required acquisition order is packet build lock, then style lock, then short
database transactions. Style files and locks must be private, regular, singly
linked files owned by the current user. Symlink paths and special files fail
closed. Writers fsync a private same-directory temporary file, recheck the current
base hash, atomically replace the destination, and fsync its directory. They
publish exact canonical bytes without adding a BOM. Cooperating readers see
complete content; uncoordinated hostile local writers remain a trust boundary.

Feedback framing uses sorted compact JSON metadata and the exact canonical
feedback byte length. Separators are outside the counted body, so NUL and
marker-like feedback are preserved. This helper does not itself authorize or
deduplicate feedback. Schema v9 now retains immutable snapshots and revision work;
the revision processor uses them for durable idempotency. The file recovery helper accepts retained
base/target content: it publishes from the base, recognizes an already-published
target, and rejects unknown third content without overwriting it. SQLite and file
publication are separate resources; the durable revision state bridges their commits.
Future Settings edits will use this writer plus immutable snapshot persistence.

### Run 2: schema v9 and retained snapshots

Schema v9 adds `style_memory_snapshots`, `packet_revision_work`, and the packet
bindings `writing_prompt_version`, `style_memory_hash`, `revision_decision_id`.
Migration from v8 is additive and transactional. All existing packets retain
their exact fingerprints, decisions, evidence, writing work and artifacts, and
receive v4/NULL/NULL bindings. No fake legacy style snapshot is created.

Snapshots retain exact private canonical style content, its SHA-256 key,
canonicalization version, and UTC creation metadata. Creation metadata is excluded
from identity. Load helpers recheck exact canonical form and recompute the content
hash on every load. Persistent guards reject UPDATE, DELETE and replacement of
snapshot identities. The database intentionally stores this private preference
content because hashes alone cannot reconstruct historical writing requests.

Packet guards accept only v4 without style or v5 with an existing snapshot. Each
Revise decision can bind at most one successor. Revision bindings require the
immutable Revise record, matching predecessor fingerprint, same logical job and
a higher version. Work guards preserve base/target/successor identities while
allowing valid operational state transitions; succeeded transitions require a
ready successor with ready_at present. Deleted/replaced work cannot silently
discard durable idempotency evidence. These are storage invariants, not approval.

Legacy v4-semantic-writing-cache packets reconstruct their exact original
requests without any style section or mutable style-file read. New v5 packets
include their exact bound snapshot in both writing SYSTEM messages, between an
explicit untrusted STYLE DATA boundary and a fixed authoritative closing reminder.
Facts, verifier/lint and GitHub/GPA/degree/title policies remain authoritative;
company sources cannot authorize candidate claims, including exact candidate-name
tokens. Prompt caching uses the existing cached_system mechanism without an extra
style-analysis call or transport change.

New packet semantic identity includes prompt version, canonicalization version
and style hash. Writing identity retains the existing algorithm: style changes
alter SYSTEM hashes, while canonical-equivalent content allows exact checkpoint
reuse. Historical v5 verification loads and authenticates retained snapshot content
and hash, never current style_memory.md. Later style edits alone do not invalidate
historical packets. Current authoritative truth/policy checks still apply.
The build lock precedes a shared style lock and a short snapshot/packet claim
transaction; the style lock is released before provider work. Existing daily
capacity, monthly budget, accounting and ambiguous-outcome rules remain active.
The local revision CLI, version history and diffs are implemented below.
Run 2 integration validation is complete: 2,348 offline tests passed, including
the established approved Chromium/FastAPI split. The consolidated evidence,
required safety answers and limitations are in
[REVISION_STYLE_MEMORY_REPORT.md](REVISION_STYLE_MEMORY_REPORT.md).


### Run 2: revision processing

`RevisionProcessor(engine, settings).process_revision(decision_id)` accepts only
an immutable Revise decision ID. It validates its Andrew/policy/source binding,
preserves the original decision feedback unchanged, and appends one framed
canonical feedback entry to private style memory. Durable work binds immutable
base/target snapshots before publication. After a crash, base means publish the
retained target, target means publication already happened, and unknown third
content means `style_conflict` without overwrite or another append. Later edits
cannot change an already-prepared target. There is no mutable DB current-style
pointer and no atomicity claim across SQLite and the filesystem.

The processor releases the style lock before generation and retains the packet
build lock. It uses current facts/answer bank and locally validates predecessor
job/scoring/company evidence against the retained successful cover request,
preserving fact IDs/order independently of old candidate inputs. It never constructs a
researcher, calls Tavily or reads cache expiry to refresh research. Damaged old
artifacts do not prevent feedback persistence; insufficient local evidence blocks
generation after feedback is saved.

Each decision creates at most one immutable successor, using a distinct
revision-v1 identity, same logical job, max allocated version plus one, its own
ID/directory/fingerprint and the retained target snapshot. Once claimed, changed
candidate inputs on restart fail closed instead of changing that successor.
The predecessor and its decision/artifacts stay historical. **v1's Revise does
not authorize v2:** v2 starts without a decision and needs independent approval.
A new Revise on v2 may create v3.

The narrow validated revision path uses no additional new-job daily slot. Normal
new builds still enforce capacity. Monthly LLM budget, llm_calls/cache accounting,
writing checkpoints, truth/lint and publication gates remain active. Exact
succeeded checkpoints can finish locally even at exhausted budget; new generation
is denied. Ambiguous provider outcomes enter recovery_required and are not blindly
retried. Blocked/recovery_required work requires manual review; there is no new
automatic reset or provider-retry command. Replayed success authenticates the
surviving successor, and final completion reloads authoritative candidate inputs.
The narrow CLI below exposes this operation. Run 3 adds the separate local
approval UI/API described above. Authentication/Tailscale and submission remain
deferred.


### Run 2 local revision command and historical views

Process an existing immutable Revise decision:

```sh
python -m job_agent revision-process --decision-id <immutable-revise-id> --data-dir data
```

The command accepts only the decision ID and optional data directory. It does
not accept feedback, an arbitrary packet rewrite, capacity bypass, provider URL,
apply or submit flags. It reports safe decision/successor IDs, state and sanitized
failure code. Exit 0 means succeeded, 2 means work needs review, and 1 means a
sanitized operation failure. Production writing may use the existing Anthropic
executor when needed; there is no research refresh or submission capability.

`packet_history.list_packet_versions(engine, packet_id=...)` also accepts exactly
one `job_key=...` or `canonical_job_id=...` selector. It follows stored packet
job/canonical relationships and retained JobIdentity aliases, sorts by version
then stable packet ID, and exposes safe metadata only. Decision type and derived
revision/recovery lineage are informational. Unknown predecessor links remain
unlinked. Latest allocated and latest ready are separate: a failed newer packet
does not hide an older ready packet. No feedback, prompts, snapshot contents,
filesystem paths or secrets are returned.

`diff_resume(engine, settings, left_packet_id, right_packet_id)` and `diff_cover(...)`
compare two versions of the same logical job locally. Resume differences use
strict UTF-8 `resume.face.txt` bytes after no-follow/regular-file/containment and
exact manifest filename/hash/size checks, plus consistent PDF/DOCX rendering
from that face. PDF selectable text is read only for consistency; **no OCR** is
used and the diff source is the authenticated face. Reads are pinned to directory
descriptors, files are bounded to 20 MB each, and DOCX expansion to 100 MB.
Cover differences authenticate the successful bound writing checkpoint, request
fingerprint, output hash, parsed draft and exact stored cover relationship;
checkpoint/cover text is bounded to 1 MB. Neither helper loads current candidate
truth, checks current eligibility, calls an LLM, or repairs missing content.

Results contain an available deterministic unified diff or a sanitized
unavailable/integrity_failed/invalid_request status. Labels contain packet/version
identity only. Original line endings and terminal newline presence are preserved,
with explicit missing-newline markers. Full content/diffs are not logged.
These historical views **do not approve or authorize a packet**. Current
authoritative truth, policy, URL, artifact and stale-view checks still apply to
independent approval. The Run 3 section describes the local queue/UI/API.
Settings editing, Run 4 authentication/Tailscale/multi-device access and
submission remain deferred.

### Run 4 Milestone A: authenticated Tailscale access policy

The approval command defaults to local mode, preserving Run 3:

```sh
job-agent approval-queue --data-dir data --port 8643
job-agent approval-queue --access local --data-dir data --port 8643
```

Application support for a future operator-managed Tailscale Serve proxy is explicit:

```sh
job-agent approval-queue --access tailscale --data-dir data --port 8643
```

Both modes bind only `127.0.0.1`, with proxy headers and access logging disabled.
There is no host option. This command does not install Tailscale, log in, configure
Serve/Funnel/HTTPS, change policy or contact Tailscale APIs. **Real Serve placement
and multi-device access have not been tested.** Milestone B requires separate
operator approval and controlled setup/smoke testing.

Tailscale mode requires both private environment/.env settings:
`JOB_AGENT_APPROVAL_TAILSCALE_LOGIN` and `JOB_AGENT_APPROVAL_TAILSCALE_HOST`.
They use excluded, non-repr `SecretStr` fields and never enter SQLite, bootstrap
JSON or startup output. Local mode requires neither and ignores these settings.
Login is one exact printable ASCII identity of 1–512 bytes, without whitespace,
controls, commas, wildcard characters (`*?[]`) or RFC2047 encoded words. No
trimming, case folding, Unicode normalization or alias/suffix matching occurs.
Unsupported future operator representations must be deliberately supported before
setup can proceed. Host is a lowercase DNS name with exactly device and tailnet
labels before `.ts.net`, valid 1–63 character DNS labels and at most 253 bytes.
Schemes, paths, ports, userinfo, wildcards, trailing dots, localhost and IPs fail.
Keep actual private values in the local environment/.env, never committed docs.

Every HTTP request, including shell, assets, bootstrap, PDFs and unknown paths,
requires the actual ASGI server `127.0.0.1:<configured-port>`, IPv4 loopback client
and HTTP backend scheme. Then exactly one raw Host must equal the configured
hostname, without an explicit port (canonical external HTTPS authority). Direct
localhost browser access to this mode fails. Exactly one raw
`Tailscale-User-Login` must have the supported byte representation and exactly
match the configured login. Display name, profile picture, forwarded headers,
cookies, query parameters and request bodies supply no identity authority.
Missing/invalid identity returns `401 authentication_required`; supported but
nonmatching identity returns `403 authorization_failed`. Neither reveals values.

Mutation additionally requires exactly one Origin equal to
`https://<configured-host>` and the existing process-memory CSRF token, followed
by Run 3's bounded JSON/DTO checks and exact packet/view expectations. The origin
is configured, never derived from the backend HTTP scheme or forwarded headers.
Rejected authentication/Origin/CSRF requests do not read private bodies. Restart
invalidates old CSRF tokens and still requires identity. Authenticated bootstrap
returns only `csrf_token`, `local_only: false` and `access_mode: tailscale`; local
bootstrap retains its exact Run 3 fields. Same-origin UI resources, CSP, no CORS,
security headers, private log suppression and all domain semantics are preserved.

Synthetic ASGI tests establish application policy only. Milestone B must prove
that WSL-local Serve actually supplies the required Host, identity and loopback
scope in this NAT environment. An equally privileged malicious local process can
forge identity headers and remains inside the trusted-host boundary. This is
not isolation from a compromised host. See [TAILSCALE_ACCESS_REPORT.md](TAILSCALE_ACCESS_REPORT.md).
