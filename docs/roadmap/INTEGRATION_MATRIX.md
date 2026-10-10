# Job Pilot durable integration matrix

Status: documentation-only roadmap and top-level Run Builder Skill Gate policy amendment, awaiting Andrew's review. Run 5 is the current top-level Run: milestones 5A, 5B and 5C are complete; 5D is NEXT, NOT STARTED. No entry authorizes installation, account setup, sending, employer submission, deployment, or a change to existing rules.

Original roadmap starting checkpoint verified on 2026-10-10: branch `main`; HEAD and local `origin/main` both `69fb88f60c56f5e3ec8ae88c29619b31993f2b47` (`feat: add trusted Run 5C decisions`); `git status --short` empty. No fetch or external account access was needed.

Policy amendment starting checkpoint verified on 2026-10-10: branch `main`; HEAD and local `origin/main` both `f4e2cf88105eee40214d127e439bac4b233e6660` (`docs: add Job Pilot integration roadmap`); worktree and index clean, with no untracked files. No fetch or external account access was needed.

## Purpose and priority

This is the authoritative integration roadmap for repositories, services, browser tools, development skills, outreach capabilities, and the later JARVIS/OpenClaw layer. It supplements [CLAUDE.md](../../CLAUDE.md) and the implemented architecture; it does not silently amend either.

Every candidate must increase the probability of interviews/a job, materially reduce Andrew's manual workload, or both. Being interesting is insufficient.

**After Run 5C, prioritize jobs found → high-quality matches → strong tailored applications → timely applications → relevant connections/referrals → replies → interviews → offers. Reduce manual research, tailoring, form filling, tracking, and follow-up. Do not spend disproportionate time on infrastructure or visual novelty that does not improve those outcomes.**

Add external capability in this order:

**One component → one capability gap → isolated evaluation → measurable proof → safety/license review → tests → independent checkpoint.**

Review safety and licensing before running the isolated proof, and confirm them again before adoption. Prefer a small native adapter or one useful idea over importing a whole framework. Expected impact below is a hypothesis to measure, not an interview guarantee.

## Decision vocabulary

| Decision | Meaning |
| --- | --- |
| KEEP | Already evidenced in the existing system or development workflow; retain its proven scope. |
| INTEGRATE | Planned capability with a milestone and expected value; adoption still requires the quality gate. |
| EVALUATE | Promising candidate that must prove incremental value before adoption. |
| REFERENCE | Study selected ideas/patterns; do not add the whole project as a runtime dependency. |
| DEFER | Potential value, but no present gap justifies adoption. Reconsider at the stated trigger. |
| REJECT | Outside the planned architecture unless materially new evidence changes the decision. |
| BACKUP ONLY | Development fallback; never a Job Pilot production dependency. |
| OPTIONAL | Later improvement or user tooling; not required for the core loop. |

Decision cells use only these values. Qualifiers such as expand, later, user-only, unverified, and duplicate appear in notes or gates. INTEGRATE is a roadmap decision, not evidence that a component already exists or has passed review.

## Implemented baseline and evidence

The existing domain owns normalized jobs, filtering/deduplication/scoring, SQLite persistence, grounded packet generation, authenticated immutable artifacts, exact-version decisions, revision processing, and independent successor approval. The Python/FastAPI server remains the authority; the accepted static Next.js/TypeScript frontend runs under the existing CSP. Do not replace those boundaries with an external product or agent framework.

Evidence inspected at the checkpoint:

| Existing component | Evidence | Supported KEEP scope |
| --- | --- | --- |
| aravindpranav/job-agent | Configured `upstream` Git remote; [pyproject.toml](../../pyproject.toml) package/author metadata; [README.md](../../README.md); existing `src/job_agent` modules. | Original/base project extended into Job Pilot; no new upstream replacement or automatic merge. |
| Playwright | Dependency in [pyproject.toml](../../pyproject.toml); `tests/test_frontend_decisions_dom.py` and other DOM suites; `src/job_agent/apply/browser.py`; [Run 5C report](../run5c/RUN5C_TRUSTED_DECISION_REPORT.md). | Browser/UI tests and inherited assisted-apply code exist. Trusted-packet production employer execution is a future Run 8 capability. |
| FreeHire | `src/job_agent/sources/freehire.py`, registration in `sources/__init__.py`, `tests/test_freehire.py`. | Current normalized public job-discovery adapters, including relocation support. This inspection did not query a live source. |
| Tavily | `src/job_agent/tavily_research.py`, provider configuration, [company research report](../../COMPANY_RESEARCH_REPORT.md). | Implemented public company research where explicitly enabled; key presence alone does not enable it. Fixture mode remains distinct. |
| APScheduler | Pinned dependency in [pyproject.toml](../../pyproject.toml); `src/job_agent/scheduler.py`; README scheduler/revisions-only contracts. | Local discovery, model-batch operations, maintenance, and separately started revision scheduling. No implied outreach scheduler or employer submission. |
| Tailscale Serve | [Tailscale access report](../../TAILSCALE_ACCESS_REPORT.md), approval security modules, [service template](../../deploy/systemd/job-pilot-approval.service). | Validated private multi-device approval access with loopback listener and identity/Host/Origin/CSRF boundaries. No public hosting claim. |
| Bubblewrap | Tailscale access report, controlled DB-writer trace and bounded reproof sections. | Isolation used in validated diagnostic/test workflows with private shadow data. No evidence that all production Job Pilot runs inside Bubblewrap. |
| Frontend Design Pro | [accepted desktop implementation report](../run5b/APPROVED_DESKTOP_IMPLEMENTATION_REPORT.md), font report, premium polish report, Run 5C report. | Accepted development/design skill used for the frontend; not a runtime package. |

The [approval core report](../../APPROVAL_CORE_REPORT.md), [packet immutability report](../../PACKET_VERSION_IMMUTABILITY_REPORT.md), [revision/style report](../../REVISION_STYLE_MEMORY_REPORT.md), [approval queue report](../../APPROVAL_QUEUE_REPORT.md), [UI spec](../design/JOB_PILOT_REVIEW_UI_SPEC.md), and [deferred polish backlog](../run5b/DEFERRED_CROSS_DEVICE_POLISH.md) inform this roadmap. Historical report wording such as pending checkpointing does not override the verified current commit. Prototype People panels and application success screens are design intent, not implementation evidence.

No separately named build-brief file was located among the tracked documentation inspected. Existing rules and documented architecture remain binding; this matrix cannot authorize an unreviewed architecture change.

## Primary integration matrix

Risk cells describe the proposed use, including operational/account exposure. They are not completed security or license audits. Each candidate must resolve its exact upstream identity, version, license, data permissions, and requirements before use; ambiguous names remain unresolved rather than receiving a guessed repository URL.

| Component | Type | Capability | Job Pilot integration point | Milestone | Decision | Expected interview/job impact | Expected manual-work reduction | Security/account risk | Dependency/maintenance risk | Integration approach | Acceptance gate / trigger | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aravindpranav/job-agent | Base repository | Existing discovery/application modules | Existing Python domain and CLI | Existing; all later runs | KEEP | Preserve working search and packet foundation | Reuse existing behavior | Existing safety gates remain authoritative | Upstream changes may conflict with local guarantees | Extend selected existing modules | Preserve contracts/tests; separately review any upstream reuse | Base provenance, not a replacement product |
| Playwright | Browser library/test tool | Deterministic browser control | DOM tests now; controlled employer runner later | Existing; expand in Run 8 | KEEP | Later reliable, timely applications | Later reduce form filling | HIGH for real employer actions/sessions; test sites isolated | Site changes and browser upkeep | Known/stable employer workflow → deterministic Playwright | Synthetic-site proof, exact approved-packet binding, stop on new questions; first real submission review | KEEP current scope; EXPAND later. Run 5C does not submit |
| FreeHire | Discovery source | Public role discovery | Existing source registry → Job model | Existing; benchmark in Run 6 | KEEP | Relevant discovery baseline | Reduce manual role searches | Untrusted postings; bounded public requests | Source availability/shape drift | Retain native adapters and existing filters | Monitor useful unique yield and source failures | No live availability claim in this milestone |
| Tavily | Research service | Public company evidence | Existing enabled research provider → packet evidence | Existing; compare coverage in Run 9 | KEEP | More specific grounded applications | Reduce company research | API key, external content; protect candidate data | Provider schema/cost/availability | Retain bounded transport, provenance and cache | Existing truth/privacy gates; enablement remains explicit | Company research is implemented; people outreach is not |
| APScheduler | Scheduling library | Existing local operations | Existing scheduler and revisions-only process | Existing; later Run 10 native jobs | KEEP | Timely preparation and later follow-ups | Reduce manual operation starts | Background work must not acquire send authority | Process lifecycle and lock/recovery behavior | Extend existing narrow jobs when justified | Durable state, idempotency, no unauthorized outbound actions | Model-batch submission is not employer submission |
| Tailscale Serve | Private access boundary | Authenticated device access | Loopback approval server | Existing; all review milestones | KEEP | Review opportunities sooner across devices | Reduce device handoff | HIGH if identity/header boundary is weakened | Service/configuration lifecycle | Preserve validated private access and checks | Identity, Host, Origin, CSRF, no-store, CSP regressions | No public exposure or remote account setup here |
| Bubblewrap | Isolation tool | Shadow-data diagnostics/testing | Validated local proof workflows | Existing; future isolated evaluations | KEEP | Indirect reliability benefit | Reduce damage/recovery during diagnostics | Scope mounts/network carefully; secrets stay outside proofs | Host/kernel/environment compatibility | Reuse bounded isolation where suitable | Prove production data and accounts untouched | Not asserted as universal production sandbox |
| Frontend Design Pro | Development/design skill | Accepted frontend design guidance | Builder workflow for the existing frontend | Existing; final product pass | KEEP | Indirect comprehension and review quality | Reduce design/review iteration | Reviewed instructions; existing security/CSP rules prevail | Competing skill instructions would add friction | Continue the accepted instruction set | Preserve accepted design, accessibility, truthful states and architecture | Development skill only; alternatives are evaluated separately below |
| SimplifyJobs/New-Grad-Positions | Source repository/data | Early-career/new-grad role coverage | Source adapter → existing Job model/search | Run 6 | INTEGRATE | More fresh relevant opportunities | Reduce board-by-board discovery | Untrusted links/data; source reuse permissions | Format drift, stale listings, GitHub outages | Small independently switchable data adapter | Useful unique eligible jobs after dedup; malformed/offline-source tests; license/data review | No whole-repo runtime import; no GitHub-wide dependency |
| SimplifyJobs/Summer2027-Internships | Source repository/data | Internship coverage | Separate source adapter → same search pipeline | Run 6 | INTEGRATE | More relevant eligible internships | Reduce seasonal internship search | Eligibility and dates must be evidenced | Season/format drift and availability | Separate switch; normalize/dedup/filter/score | Eligibility including student/date constraints, freshness, dedup and outage proof | Never infer Andrew is eligible from the source title |
| career-ops | Reference project | Source/company lists, evaluation, tracking, preparation, rejection analysis | Selected Job Pilot discovery/outcome procedures | Runs 6-10 as useful | REFERENCE | Better selection and interview preparation | Borrow better human-controlled procedures | Review content and licensing before reuse | Competing workflow assumptions | Inspect individual ideas only | A selected idea demonstrably improves current procedure | Exact upstream identity to resolve; never replace Job Pilot |
| JobSpy | Discovery library | Additional role coverage | Isolated source benchmark, then optional adapter | Run 6, only if coverage weak | EVALUATE | Useful only for incremental quality roles | Potentially reduce missed-source searches | HIGH scraping/platform risk; prohibited scraping/evasion excluded | Fragile sources and scraping maintenance | Benchmark permitted sources against baseline + SimplifyJobs | Incremental unique useful jobs after dedup justify risk/cost | Little added coverage or excessive maintenance means no adoption; not permanently rejected |
| promptfoo | Evaluation tooling | Repeatable AI output regression/evaluation | Development evaluation of owned prompts/outputs | Run 7 | EVALUATE | Fewer unsupported or weak application outputs | Reduce repetitive output review | Synthetic/redacted fixtures; provider keys and paid calls | Extra harness/config maintenance | Thin evaluation layer around existing pipeline | Useful coverage beyond current tests without a second product architecture | If gate passes, promote to INTEGRATE in Run 7 |
| RenderCV | Resume renderer | Structured deterministic rendering | Existing resume/artifact rendering boundary | Run 7 | EVALUATE | Potential readability/ATS improvement | Less template correction | Candidate data stays private; truth gates unchanged | Renderer/template/toolchain and format migration | Side-by-side output proof against current renderer | Material gains in quality, reproducibility, templates, ATS usability or maintenance with no safety regression | Keep working pipeline unless improvement is proven; companion skill evaluated separately |
| Stagehand | AI browser tooling | Interaction on unfamiliar/changing interfaces | Controlled employer runner fallback | Run 8 | EVALUATE | Fewer blocked eligible applications | Reduce unfamiliar-form handling | HIGH: sessions, page data, model decisions, accidental submit | Model/site variance and extra toolchain | Explicit escalation when deterministic logic is insufficient | Synthetic/test sites improve completion without weaker confirmation, approval, safety or unacceptable nondeterminism | Does not automatically replace Playwright |
| browser-use | Alternative AI browser framework | Alternative interface handling | Possible alternative to Stagehand | Run 8+, conditional | DEFER | Unproven beyond Stagehand | Unproven additional reduction | HIGH browser/model/session authority | Duplicated browser stacks | Consider one alternative only if needed | Stagehand fails, or clear superior capability is evidenced | Do not integrate competing AI browser frameworks together |
| Exa | Public search/research service | People discovery and company/person evidence | Native people research adapter → ranked contacts/evidence | Run 9 | INTEGRATE | More relevant referral paths | Reduce person/company research | Public/search-accessible professional data only; key and retention review | Service/schema/cost and result quality | Small adapter with provenance and minimal retention | Relevant evidenced contacts beyond existing research; privacy/source-permission review | No logged-in LinkedIn scraping; no durable free-tier promises |
| Hunter | Email discovery/verification service | Find/verify relevant work emails | Isolated contact-provider comparison | Run 9 | EVALUATE | Reach a relevant person via verified email | Reduce manual email lookup/checking | Professional-only data, API credentials, provider handling | Coverage, catch-all ambiguity, cost/reliability | Compare with Prospeo; choose ONE primary first | Coverage, discovery, verification, catch-all handling, useful-contact cost, reliability, privacy/security and upkeep | Winner may become INTEGRATE; other remains fallback/deferred unless additive value |
| Prospeo | Email discovery/verification service | Alternative work-email discovery/verification | Same comparison, not simultaneous adoption | Run 9 | EVALUATE | Same measurable relevant-contact goal | Same lookup/verification reduction | Same professional-data and credential review | Same coverage/cost/availability concerns | Compare on the same contact set and ground truth | Same gate as Hunter; unknown/catch-all is not verified deliverability | Do not integrate both for completeness |
| Apollo | Overlapping contact service | Possible extra people/email coverage | Future contact fallback | Run 9+, conditional | DEFER | Only if primary coverage insufficient | Only if it resolves repeated lookup gaps | Additional data processor/account exposure | Another overlapping provider and cost | Evaluate smallest missing capability later | Exa + chosen Hunter/Prospeo provider demonstrably insufficient | Not required for initial outreach |
| Reacher | Self-hosted verification candidate | Possible email verification | Future optional verification boundary | Run 9+, conditional | DEFER | Better verification only if reliable | Potentially reduce paid/manual verification | Network/reputation/privacy exposure; no evasion | Hosting, network constraints, deliverability uncertainty | Isolated self-hosted proof only after need | Provider too costly/incomplete, network supports reliable operation, upkeep justified | Never an outreach prerequisite |
| Gmail integration | Account/API adapter | Approved sends, replies, stop signals, notifications/status | Native outreach/outcome state and existing approval domain | Runs 9-10 | INTEGRATE | Relevant outreach and timely replies | Reduce sending/reply tracking/follow-up work | HIGH: mailbox OAuth and external sends; minimum scopes/local tokens | OAuth lifecycle, quotas, notification gaps | Draft → Andrew dashboard Approve record → exact approved send; bounded evidence ingestion | Account approval; first real send review; ambiguous-send/reply/stop/revocation tests | No bulk generic campaigns; LinkedIn notification evidence only where available |
| LinkedIn Connection Assist | Product capability/browser workflow | Relevant connection requests and truthful acceptance tracking | Native contact ranking/approval/audit and evidence state | Run 9 | INTEGRATE | Relevant connections/referrals; test reply/interview yield | Reduce selected request and acceptance tracking work | HIGH account/platform-policy risk; restriction possible | UI/policy/plan changes, ambiguous signals | OFF BY DEFAULT; explicitly enabled bounded request assistance; manual post-acceptance message | Scoped rule reconciliation, action approval, synthetic proof, dry-run/kill-switch/stop-control gates | Andrew accepts the proposed bounded risk; controls do not establish platform permission |
| Panniantong/agent-reach | Broader research candidate | Public/social sources not efficiently covered | Future narrow research adapter | Run 9+ | DEFER | Only from useful research gap closure | Only for repeated cross-source research failures | Broad shell/network/cookies must not be granted by default | Large ecosystem and platform-specific upkeep | Public-source proof of one gap first | Repeated measurable failures across several platform-specific sources despite web/Tavily/Exa | No real LinkedIn cookies/session by default; no whole-ecosystem install |
| Langfuse | Observability/evaluation candidate | Model traces and experiment comparisons | Optional boundary around existing accounting/evidence | Run 11, conditional | DEFER | Indirect quality learning | Potentially reduce debugging/experiment review | Prompt/person-data export risk and credentials | Extra tracing infrastructure/storage | Compare minimal tracing against existing internal mechanisms | Current logging insufficient for multi-stage traces, prompt evaluation, experiment comparison or production quality | Defer while existing observability suffices; not permanently rejected |
| LangChain | Orchestration framework | General model/agent composition | No planned runtime integration | Architecture review; no adoption run | REJECT | No demonstrated incremental gain | No demonstrated gap resolved | Expands tool/execution surface | Duplicates established architecture | No adoption | Only materially new gap evidence could reopen; rules still apply | Current no-agent-framework rule remains binding |
| CrewAI | Orchestration framework | General multi-agent composition | No planned runtime integration | Architecture review; no adoption run | REJECT | No demonstrated incremental gain | No demonstrated gap resolved | Additional agent/tool authority | Duplicate orchestration/runtime dependencies | No adoption | Same architecture/gap gate as LangChain | Popularity is not a capability gap |
| ApplyPilot | Autonomous application project | Alternative application workflow | No planned integration | Architecture review; no adoption run | REJECT | Poor fit with controlled approval model | Claimed automation does not justify boundary changes | Autonomous submission conflicts with explicit approval safety | License and architecture concerns need review, not assumptions | No adoption or blind submission-code reuse | Materially new evidence plus explicit architecture/license review to reconsider | Job Pilot builds an explicit safety boundary |
| Tremor | UI/chart toolkit | Aggregate analytics presentation | Later real outcome/source analytics | Final product pass after real analytics | DEFER | Indirect decisions from truthful analytics | Could reduce manual aggregate interpretation | Private analytics exposure; preserve CSP/accessibility | Extra UI dependencies | Small visualization only where needed | Authoritative real aggregates exist and improve decisions | No fake dashboard charts |
| Magic UI | UI effects toolkit | Restrained explanatory motion/effects | Accepted UI polish only | Final product pass | OPTIONAL | Indirect comprehension benefit | Only if it reduces review friction | CSP, accessibility and semantic-status correctness | Extra dependencies/effect upkeep | Prefer a small native effect; select only useful pieces | Improves comprehension, passes CSP, honors reduced motion, preserves status meaning | No novelty-only effects |
| Onlook | Development/design tool | Visual iteration | Builder workflow only | Final product pass | OPTIONAL | Indirect design quality | Faster useful design iteration | Workspace/source visibility and tool permissions | Tool setup/upkeep | Isolated optional development use | Measured iteration benefit without architecture change | Not runtime infrastructure |
| OpenCode | Builder fallback | Development/model routing | Development environment only | If primary builder unavailable | BACKUP ONLY | Indirect continuity | Avoid development interruption | Model routing, repository access and secret exposure | Provider capacity and tool correctness | Reviewed temporary fallback | Critical-change correctness and boundary preservation proven | Never a production dependency; free routing is not unlimited capacity |
| Aider | Builder fallback | Assisted code changes | Development environment only | If primary builder unavailable | BACKUP ONLY | Indirect continuity | Avoid development interruption | Repository/model/credential access | Provider/tool compatibility | Reviewed temporary fallback | Same reliability/security review; human checkpoint | Correctness outranks token savings |
| free-claude-code | Builder fallback candidate | Alternative model/provider routing | Development environment only | If primary builder unavailable | BACKUP ONLY | Indirect continuity only | Possible development continuity | UNVERIFIED provenance, credential/routing handling | Capacity promises and maintenance uncertain | Resolve exact project and audit before any use | Trusted provenance, terms, reliability and correct changes | No guaranteed free/unlimited capacity; no runtime use |
| affaan-m/ECC | Engineering reference | Selected procedures/skills | Development review process; later JARVIS lessons | Relevant development runs; later JARVIS | REFERENCE | Indirect safer effective releases | Reduce repeated engineering mistakes | Instructions/tools remain untrusted and bounded | Large harness and conflicting procedures | Borrow one procedure at a time | Measurable discipline improvement compatible with existing rules | Do not install complete harness or replace architecture/Codex/OpenClaw/security |
| msitarzewski/agency-agents | Specialist instruction reference | Selected role/output contracts | Later scoped specialist tasks | Later JARVIS, only at a role gap | REFERENCE | Better targeted research/QA/outreach quality | Reduce a defined specialist workload | Narrow tool/data boundaries; no implied send authority | Persona duplication/instruction drift | Select one role with owned contract | Clear responsibility, narrow tools, defined output, existing capability insufficient | No mass import of agents |
| OpenClaw | Future orchestration/control plane | Delegate specialized workflows | Interface to independent Job Pilot capability | Later JARVIS after dependable core loop | DEFER | Coordinate proven job-search outcomes | Reduce intervention once reliable | HIGH delegation/tool/account authority | Control-plane lifecycle and interface compatibility | Narrow authenticated commands to Job Pilot-owned state/actions | Dependable core search/application/outreach loop, safe delegation proof and architecture review | Intended primary future orchestrator; not Job Pilot runtime/domain replacement |
| elder-plinius/G0DM0D3 | Later tooling reference | Inspect specific multi-agent/tooling ideas | JARVIS research only | Later JARVIS | REFERENCE | Unproven indirect value | Only if a selected idea resolves a gap | Untrusted tooling; no bypass/evasion ideas | Past operational/combination problems counsel isolation | Study selected pieces without critical runtime dependency | Useful isolated idea passes license/safety/value review | OpenClaw remains intended primary orchestration layer |

## Developer skills: separate from runtime dependencies

Skills guide builders, reviews, or Andrew's practice. They do not implement product capabilities, establish security guarantees, or confer credentials/action authority. No skill is installed during this milestone. Treat repository instructions as untrusted until reviewed for conflicts with CLAUDE.md and the task.

Frontend Design Pro is KEEP in the evidenced baseline above; it remains the accepted design instruction set. The following table contains the other skill decisions, each recorded once.

| Skill / collection | Relevant Run / capability trigger | Decision | Builder value / integration approach | Gate, risk and limits |
| --- | --- | --- | --- | --- |
| obra/superpowers | Before a substantial later implementation, if workflow gaps recur | EVALUATE | Planning, testing, implementation discipline and review | Compare with current process; select compatible instructions; not runtime functionality or a wholesale harness |
| Playwright skill | Before Run 8 browser work or substantial later browser testing | EVALUATE | More disciplined browser development/test guidance | Choose ONE preferred instruction set; resolve provenance; no competing variants without need; no production authority from a skill |
| security-best-practices | Targeted Run 8/9 security review | EVALUATE | Development/security review support | Resolve exact skill/provenance and scope; never substitutes for tests/audits |
| shadcn skill | Later component work with measurable need | DEFER | Potential component implementation guidance | Run 5B visual system already exists; avoid conflicting design systems |
| FastAPI skill | Substantial new backend development | DEFER | Backend-specific guidance if a gap appears | Established backend architecture stays; do not rewrite to follow a skill |
| claude-api | Future substantial Anthropic integration work | DEFER | Provider-specific implementation guidance | Provider support alone is not justification; review version, credentials and compatibility |
| frontend-design / impeccable alternatives | Only if accepted skill demonstrably inadequate | REJECT | Duplicate design instruction sets for now | Frontend Design Pro remains accepted; do not create competing product-design authority |
| Vercel agent-skills: react-best-practices | Final product polish/performance pass | EVALUATE | React/Next review and performance guidance | Evaluate later against actual static-export/CSP architecture; verify improvements; no automatic installation |
| Vercel agent-skills: web-design-guidelines | Final product accessibility/interaction pass | EVALUATE | Accessibility, forms, focus, motion, typography and interaction review | Evaluate later using real states, keyboard/reflow/reduced-motion proof; preserve accepted UI and truthful statuses |
| Trail of Bits security skills | Targeted later security review with relevant language/threat surface | EVALUATE | Focused specialist security procedures | Evaluate later; verify provenance/tool requirements; test findings rather than trusting skill output |
| RenderCV skill | Only after RenderCV itself is adopted | DEFER | Guidance for the adopted renderer | Separate evaluation/license/provenance decision; renderer adoption does not auto-adopt its skill |
| Interview coach skill | Andrew's interview practice, when requested | OPTIONAL | USER-ONLY preparation and feedback | Private practice input; no Job Pilot runtime dependency or unsupported candidate claims |
| abide | Later, when maturity and concrete value are proven | DEFER | Potential builder discipline | Exact project/provenance and useful scope unresolved; no install based on name alone |
| ui-ux-pro-max | Later, only after provenance review and a design gap | DEFER | UNVERIFIED possible design guidance | No installation before review; compare against accepted design skill |
| Figma skill | No planned milestone; only a concrete later design need | REJECT | Not needed for current product | Reopen only for a specific gap; no account setup implied |
| GSAP skill | No planned milestone; only a concrete later motion need | REJECT | Not needed for current product | Current motion must stay restrained/CSP-compatible/reduced-motion-safe |
| Remotion skill | No planned milestone; only a concrete later video need | REJECT | Not needed for current product | Job-search workflow does not require a video stack |
| caveman | No planned milestone; only materially new evidence | REJECT | Not needed for current product | Resolve identity/review before any reconsideration |

## Run hierarchy

A **TOP-LEVEL RUN** is a major product-development phase, such as Run 5, Run 6, Run 7, Run 8, Run 9, Run 10 or Run 11. A milestone/subphase is work inside one of those Runs. The current established structure is:

| Top-level Run | Milestone/subphase | Scope | Status |
| --- | --- | --- | --- |
| RUN 5 | 5A | Frontend architecture/foundation | COMPLETE |
| RUN 5 | 5B | Desktop + phone review experience | COMPLETE |
| RUN 5 | 5C | Trusted Approve / Reject / Revise decisions | COMPLETE |
| RUN 5 | 5D | Revision execution + successor packet/version + change/diff review | NEXT / NOT STARTED |

**5A / 5B / 5C / 5D are not independent top-level Runs. 5D is the final currently planned milestone of Run 5.** Completing 5D completes Run 5 under the currently planned roadmap. An explicit future roadmap decision could amend that scope; this document does not claim the Run can never be amended.

## Run-level Builder Skill Gate

**ONE BUILDER SKILL GATE PER TOP-LEVEL RUN.** The normal permanent policy begins with Run 6. Perform the gate at the start of each new top-level Run, before Run preflight/architecture and before implementation planning becomes locked. Inspect **ALL currently known work planned for the Run**, and map capabilities across all known milestones/subphases, rather than only the first milestone. Establish the stack once for the entire Run whenever reasonably possible.

**THIS GATE APPLIES TO BUILDER SKILLS.** Its purpose is to determine whether the existing stack effectively supports the whole Run, or whether a justified development skill could materially improve planning, architecture review, implementation quality, testing, debugging, security review, browser automation, accessibility, performance, provider/API correctness, visual/product quality, consistency, or reduction of repetitive prompting.

This Run-level review is separate from the higher-bar **External Integration Quality Gate** (the Mandatory integration quality gate below) for runtime repositories, external services, production dependencies, credentialed integrations and consequential account behavior. A builder skill does not acquire runtime or account authority. If its proposed use requires those capabilities, their applicable integration and approval gates still apply. Do not merge the two gates.

### Effective sufficiency and anti-bloat

**NO NEW SKILL REQUIRED is a valid, successful Run-level Builder Skill Gate result and may be the default outcome. The review gate is mandatory; discovery, evaluation, and installation of another skill are not.** No builder skill becomes mandatory merely because it is listed. Superpowers remains one candidate among the full inventory, with no privileged or mandatory status.

Sufficient does not merely mean technically capable. The current builder stack is **effectively sufficient** only when it supports the whole known Run adequately across:

- Capability.
- Quality.
- Reliability.
- Efficiency.
- Safety.
- Testability.
- Maintainability.

A technically capable stack may still justify evaluation for a **specific, material deficiency**: substantially worse implementation quality, recurring mistakes, weak testing/review capability, security blind spots, excessive debugging, disproportionate repetitive prompting, significant workflow inefficiency, or poor consistency. Minor convenience improvements do not justify adding tooling.

If the currently approved/available stack is effectively sufficient, pass the gate without discovering, evaluating, or installing another skill. Starting a Run or advancing to another already-planned milestone alone does not justify adding skills. Do not replace an effective skill merely because a newer one exists, install overlapping skills "just in case," or optimize for the number of installed skills. Establish **the smallest sufficient Run-level stack**.

### Cumulative skill inventory

**docs/roadmap/INTEGRATION_MATRIX.md remains the single durable builder-skill inventory.** Its **Developer skills: separate from runtime dependencies** section above, including the reference to the accepted Frontend Design Pro baseline, holds the cumulative inventory. Do not create `BUILDER_SKILL_REGISTRY.md` or another parallel registry.

When a Run-level gate discovers a genuinely useful new skill for a concrete, relevant Job Pilot engineering gap, record it back into that inventory. Preserve:

- Skill name.
- Source/repository/provider, including unresolved provenance when applicable.
- Relevant capability.
- Relevant Run(s), with milestone/subphase scope when useful.
- Current status: **EVALUATE / KEEP / DEFER / REJECT**.
- Brief reason for that status.
- Important overlap, conflict, or provenance note when relevant.

The inventory is cumulative across Runs. Future Run-level gates begin with it and consider relevant previously recorded skills before searching for new ones. Do not add interesting-but-irrelevant skills merely to catalog them. These recording requirements do not change existing entries or their decisions.

Useful future skills may come from official/vendor collections, trusted GitHub repositories, developer recommendations, relevant community recommendations, tools Andrew provides, or targeted research for a concrete Run-level material gap. Discovery is capability-gap-driven, not novelty-driven. A newer skill does not automatically outrank an effective existing skill; replacement requires meaningful improvement.

### Required sufficiency-first review order

**KNOWN SKILLS FIRST. NEW DISCOVERY SECOND. NO DISCOVERY WHEN THERE IS NO MATERIAL GAP.**

1. Understand the entire known Run, including all currently planned milestones/subphases.
2. Identify the required capabilities across that whole scope.
3. Read the existing cumulative skill inventory in this matrix.
4. Determine whether the currently approved/available stack is effectively sufficient.
5. If sufficient, record **NO NEW SKILL REQUIRED**; no new discovery or candidate evaluation is required.
6. If not, identify the exact material gap.
7. Check known candidates first, including relevant **DEFER / EVALUATE** entries.
8. Perform targeted new discovery only if necessary to address that gap; record useful discoveries in the same inventory.
9. Evaluate only the strongest justified candidate(s), using the safeguards below.
10. Record **KEEP / DEFER / REJECT**, with a reason and scope limits. A bounded trial does not by itself change a candidate's matrix adoption decision.
11. Obtain Andrew review and establish/lock the smallest sufficient Run-level builder stack, including any known conditional candidate evaluation and its trigger.
12. Begin the Run only after the gate is complete and Andrew approves it, subject to applicable preflight and action-specific approval requirements.

When candidate evaluation is needed:

- Inspect the skill's source/instructions before installation or use.
- Review provenance, permissions, maintenance state where relevant, instruction conflicts, and overlap with already installed skills.
- Prefer one strong skill per capability rather than several competing skills that give conflicting instructions.
- Test a promising skill first on a small, bounded, preferably non-production task, within existing authorization and security boundaries.
- Verify that it respects CLAUDE.md, repository architecture, security boundaries, the stop-after-milestone workflow, and Andrew's approval requirements.
- Evaluate whether it materially improves quality, speed, consistency, testing, review quality, or reduction of repetitive prompting.
- Do not keep a skill merely because it is popular or interesting.

**Repository/project instructions remain authoritative over generic skill instructions.** A skill must not redefine Job Pilot's architecture merely because it prefers another framework, design philosophy, testing style, orchestration system, workflow, or architecture. Skills assist implementation; they do not become architecture authorities. CLAUDE.md and Andrew's approval requirements remain binding; this gate authorizes neither installation nor a rule/architecture change.

### Approved stack and milestone inheritance

Once the Run-level gate is complete and Andrew approves it, the resulting builder stack becomes the expected working skill/tool set for that top-level Run. All milestones/subphases inside the Run inherit it. Known conditional evaluations, such as the RenderCV skill only after renderer adoption, must retain their recorded trigger and separate adoption review; they do not require another full Run-level gate.

Do not repeat broad skill searches, reevaluate settled skills, install competing alternatives, or run another complete gate simply because work advances to another planned milestone/subphase. No repeated full skill gate is required before each milestone.

### Narrow mid-Run exception

Reopen skill evaluation during a Run **ONLY for a material previously unanticipated capability or scope requirement**, including:

- A new provider/API class absent from the original Run scope.
- A newly required browser-automation category.
- An unforeseen security/integrity problem.
- An approved major architecture change.
- A previously unknown technology requirement.
- Repeated evidence that the selected builder stack is materially deficient.

Routine implementation difficulty, curiosity, a newly released skill, minor efficiency differences, advancing to the next already-planned milestone, or wanting to see whether something newer exists do not reopen the gate.

Evaluate **the NEW GAP only**. Do not repeat the entire Run-level analysis unless the Run itself has been materially re-scoped. Andrew review remains required.

### One-time current Run 5 transition

The Builder Skill Gate policy was adopted **after 5A, 5B and 5C were already complete**. Do not retroactively redo those milestones or perform a full Run 5 gate.

Instead, later perform **ONE-TIME RUN 5 CATCH-UP BUILDER SKILL GATE**, covering **ONLY the remaining known Run 5 scope: milestone 5D**. This is a historical transition caused by adopting the policy late in Run 5. It does not redefine 5D as a top-level Run and does not establish a precedent for gating every milestone.

The future catch-up gate must inspect the entire currently known 5D scope at once. Potential capability areas, to be confirmed against repository evidence at that future gate, include:

- Recorded Revise decision consumption and revision execution.
- Revision worker/process behavior.
- Successor/new packet version creation and predecessor/successor identity.
- Packet/version integrity and packet fingerprints.
- Approval-view fingerprints where relevant.
- Idempotency, concurrency and retries.
- Failure/recovery and crash/restart semantics.
- LLM revision boundaries, evidence/provenance and unsupported factual-change prevention.
- Before/after change representation and human diff/change review.
- Subsequent independent decision flow.
- Backend testing.
- Frontend/browser validation if 5D actually includes it.
- Production-data isolation and no accidental employer submission.

Establish the skill stack for **ALL remaining 5D work** using the same effective-sufficiency, inventory, anti-bloat and Andrew-review requirements. No repeated full gate within 5D follows unless the narrow material-gap exception applies. After 5D, Run 5 is complete under the **currently planned** roadmap. Beginning with Run 6, use the normal one-gate-per-top-level-Run policy.

**This documentation amendment neither performs the catch-up gate nor starts 5D. Andrew must review this policy amendment first.**

### Proactive responsibility, bounded scope

Andrew should not need to remember or manually re-surface previously collected skills. At the **START OF EACH TOP-LEVEL RUN**, the workflow proactively reads the cumulative inventory, maps relevant skills to all known Run capabilities, checks effective sufficiency, and identifies real gaps. The one-time Run 5 catch-up review applies that responsibility to the remaining 5D scope.

Proactive does not mean continuously searching during a Run. The gate remains bounded and must not delay useful work by continually collecting skills. Ask **"Is the current stack effectively sufficient for this entire known Run?"** Review known guidance first; document an exact material gap before discovering more.

### Run-level capability examples

Review the entire known scope of each top-level Run, not merely its first milestone. These are review candidates, not completed evaluations or installation approvals. Earlier review of a known candidate does not alter the existing skill-table decisions or authorize broader adoption.

| Top-level Run / transition scope | Run-level builder-skill capability review | Possible value / boundary |
| --- | --- | --- |
| CURRENT RUN 5 TRANSITION / REMAINING 5D | At the future one-time catch-up gate, first ask whether currently installed/available skills are effectively sufficient for all remaining 5D work. If yes, record NO NEW SKILL REQUIRED. Otherwise, initial candidates may include Superpowers, security-best-practices, and one Playwright skill if actual 5D UI/browser work materially benefits, plus any other relevant known skill supported by the capability analysis; evaluate only candidates addressing the exact identified gap | Implementation planning, test-first discipline, successor-packet safety review, diff/review testing, and security/integrity checks. Candidates are not mandatory installations. Milestone 5D remains NEXT, NOT STARTED; it is not a top-level Run. |
| RUN 6: discovery expansion | Inspect all currently planned Run 6 discovery/source work; review skills relevant to source adapters, API/data ingestion, normalization, deduplication, and robustness/testing | Do not invent a need for a skill if native implementation is already clear. |
| RUN 7: application intelligence | Inspect all currently planned Run 7 application-intelligence work; review skills relevant to model/provider APIs, prompt evaluation, structured generation, and deterministic artifact generation | If RenderCV is adopted, evaluate its skill then, not before. |
| RUN 8: controlled application execution | Inspect all currently planned Run 8 controlled-application-execution work. Possible candidates: one Playwright skill, browser automation testing skill, and security-best-practices | Prefer one strong instruction set per capability; browser guidance and testing may overlap and do not confer employer-action authority. |
| RUN 9: people / referrals / outreach | Inspect all currently planned Run 9 people/referral/outreach work; review skills relevant to Gmail/API integration, privacy/security, external-account workflows, and controlled browser automation | The Builder Skill Gate does NOT override high-risk LinkedIn requirements or CLAUDE.md restrictions. Any policy conflict requires its own separately approved scoped policy/architecture decision BEFORE Run 9 implementation. |
| FINAL PRODUCT PASS | Frontend Design Pro: KEEP; Vercel react-best-practices: evaluate; Vercel web-design-guidelines: evaluate; targeted security/accessibility review skills | Preserve the accepted design and architecture; use targeted guidance for actual product quality gaps. |

For the final product pass, inspect the complete known pass scope once before locking its builder stack; its listed reviews do not create full gates for each polish task. Later major work uses a gate when it starts a new top-level Run, not merely because another milestone begins. No additional numbered Run or milestone is created here.

### Normal top-level Run lifecycle, beginning with Run 6

```text
NEW TOP-LEVEL RUN
        ↓
RUN-LEVEL BUILDER SKILL GATE
        ↓
INSPECT COMPLETE KNOWN RUN SCOPE
        ↓
MAP CAPABILITIES ACROSS ALL KNOWN MILESTONES/SUBPHASES
        ↓
REVIEW CUMULATIVE BUILDER SKILL INVENTORY
        ↓
ASSESS EFFECTIVE SUFFICIENCY
        ↓
EVALUATE ONLY JUSTIFIED SKILLS (IF A MATERIAL GAP EXISTS)
        ↓
ANDREW REVIEW
        ↓
ESTABLISH / LOCK RUN BUILDER STACK
        ↓
RUN PREFLIGHT / ARCHITECTURE
        ↓
MILESTONE A
        ↓
MILESTONE B
        ↓
MILESTONE C
        ↓
...
        ↓
RUN COMPLETE
```

The milestone letters illustrate sequence only; they do not invent additional roadmap milestones. Milestones inherit the approved Run stack and continue to require focused tests, applicable regression/security/UX review, and Andrew review. Stop after each milestone for Andrew's review; checkpoint only when authorized. Applicable external integration gates and action-specific approvals remain prerequisites to the actions they govern.

## Run 5, milestone 5D: existing revision pipeline first

Milestone 5D is NEXT and has not started. It is the final currently planned milestone inside the current top-level Run 5, following completed 5A, 5B and 5C. The one-time catch-up gate above must occur later, before 5D implementation. Its goal is:

**Recorded Revise decision → revision execution → successor/new packet version → exact diff → human review → independent approval.**

Backend `RevisionProcessor`, durable revision work/checkpoints, style snapshots, successor allocation and informational diff/history support already exist from earlier runs. Run 5C connects trusted decision recording to the accepted frontend; its immediate Revise action creates no work, successor, style update, model call, or worker invocation. Run 5D should validate and connect the existing pipeline to the accepted experience, extending only demonstrated gaps. Do not claim that revision execution is absent everywhere or already complete in the accepted frontend.

Core revision semantics stay Job Pilot-owned. The predecessor/decision/artifacts stay immutable; the successor has its own identity/version/fingerprint and needs independent approval. A Revise record does not authorize the successor or any outbound action. Keep exact truth/policy/evidence gates, budget accounting, idempotency, sanitized failures and conservative ambiguous-outcome recovery. Do not force an external repository into Run 5D. Prompt evaluation may later help assess revision quality without owning revision state.

## Runs 6-8: discover, improve, execute

### Run 6: discovery expansion

Both SimplifyJobs adapters follow:

**Source data → Job Pilot source adapter → existing Job normalization → deduplication → eligibility/filter checks → scoring → existing packet workflow.**

Preserve the current pipeline's owned filtering/order and identity rules; this sequence describes required responsibilities, not permission to reorder working stages blindly. Validate freshness and employer links, retain source provenance, distinguish first-observed time from authoritative posting time, and avoid invented dates/eligibility. Each source can be disabled independently. GitHub unavailability must produce an honest source failure while other sources remain usable; do not make the whole application depend on GitHub. Prefer local captured fixtures for parser/failure tests.

Compare discovery over a fixed representative window using unique useful eligible jobs after deduplication, duplicate rate, stale/closed listings and manual review time. Only evaluate JobSpy when baseline plus SimplifyJobs coverage is demonstrably weak. Permit no scraping or evasion contrary to existing rules. If extra quality coverage is small or upkeep/platform risk excessive, do not integrate it. Career-ops remains selective reference material through Run 10: company/source lists, evaluation, tracking, interview preparation, rejection analysis and human-controlled patterns.

### Run 7: application intelligence

Evaluate promptfoo on resume tailoring, cover letters, screening responses, research summaries, revision quality, groundedness and unsupported claims. Establish representative synthetic fixtures, current-test coverage and human-review baseline first. Evaluate factual fidelity, job-specific quality, writing policy failures and reviewer corrections. Useful coverage beyond current tests permits promotion from EVALUATE to INTEGRATE during Run 7; it must not become a second product architecture or replace deterministic verifiers.

Evaluate RenderCV against the existing DOCX/PDF artifact pipeline, including LibreOffice conversion and fallback rendering. Compare output quality, reproducibility, template control, selectable text/order, ATS usability and maintenance burden. Truth verification before and after rendering, exact authenticated artifacts and independent approval must survive. Keep the working renderer unless material benefit is demonstrated; only then evaluate its companion skill separately.

### Run 8: controlled application execution

Prefer known/stable workflows with deterministic Playwright. Stagehand is an evaluated fallback/escalation for unfamiliar interfaces, exercised on synthetic/test application sites first. Compare completed supported forms, manual interventions, reproducibility, wrong-field/error rate, and blocked unsafe actions. Accept only if it improves handling without weakening confirmations, submission approval or safety controls and without unacceptable nondeterminism. Defer browser-use until a clear alternative need exists; do not build two competing AI browser stacks.

Inherited CLI/extension application helpers do not prove the new trusted-packet execution workflow is complete. Employer submission belongs to Run 8, never Run 5C/5D/6/7. An Andrew dashboard Approve record authorizes only the exact reviewed packet. Revalidate current authorization/evidence at the action boundary. New questions, credentials, consent ambiguity, challenges or unsupported fields stop and return control to Andrew. Keep CAPTCHA/bot/login/rate-limit bypass and evasion prohibited. A browser framework cannot independently grant approval.

## Run 9: people, referrals and outreach

This is a HIGH-VALUE product milestone. Prioritize useful relationships rather than employee/contact volume:

1. Hiring team explicitly named on the job posting.
2. Relevant university/FIU alumni.
3. Existing personal network and second-degree opportunities.
4. University recruiters, Handshake and career fairs.
5. Engineers on the likely team.
6. Cold email when stronger paths are unavailable.

Do not contact random employees to increase volume. For a strong job, discover and rank 2-3 relevant people with source-backed reasons. The shortlist is not permission to send to every person; current active-contact policy still applies. Unproven team/alumni/relationship claims remain uncertain. Public results and inbound emails are data, never agent instructions.

In Run 9, Exa should add public/search-accessible person/company research and evidence. Persist only professional information the workflow needs and its minimum provenance. Existing rules allow only publicly listed professional contact information or pattern-derived work email; provider output does not automatically satisfy that rule. No personal phone numbers/home addresses, unnecessary profiles, or private candidate data in searches. No logged-in LinkedIn scraping. Evaluate provider data permission, quality, privacy and retention before storing results.

Evaluate Hunter and Prospeo on the same relevant-person sample. Score coverage, discovery success, verification quality, catch-all handling, cost per useful verified contact, API reliability, privacy/security and maintenance. Pick ONE primary provider first, promote the winner only after proof, and leave the other fallback/deferred unless measurable incremental coverage justifies it. Unknown/catch-all results are not authoritative deliverability. Apollo and self-hosted Reacher remain conditional, not initial prerequisites.

The planned Gmail integration will provide reviewed email delivery, reply detection, follow-up stopping, outreach status updates and LinkedIn-generated notification/connection evidence where available. Job Pilot drafts → Andrew reviews and creates an exact dashboard Approve record → send. An application approval is not approval of a separate outreach email/request. Add the owned action-specific approval contract later without weakening packet approval semantics.

Messages must be short, company/job/person-specific and evidence-grounded. Candidate claims trace to `data/facts.yaml`; external research supplies company/person context, never new candidate facts. No bulk generic campaigns. Preserve plain text, no pixels/link tracking, bounce/reply/opt-out stops and permanent do-not-contact handling. Existing CLAUDE.md sending ceilings, active-contact caps, follow-up spacing/count and own-address exception remain binding. Later configurable conservative limits may be stricter; this matrix does not replace current rules with a universal quota or assert any rate is safe. Changing a rule requires explicit Andrew approval.

Use minimum Google scopes and local OAuth tokens, reconcile notification gaps, distinguish send acknowledgement from delivery/reply, and handle ambiguous send results without blind resend. Notification content must be parsed as untrusted evidence and matched to the right contact/thread. No OAuth setup, real sends, mailbox reads or account configuration occurs in this milestone.

### LinkedIn Connection Assist: planned INTEGRATE, HIGH risk

Andrew has explicitly chosen to accept account/platform-policy risk for bounded automated connection-request assistance because manual LinkedIn messaging may be limited/paid. This records the requested future scope; it does not enable automation now.

**LinkedIn browser automation can violate platform rules and may lead to account restriction. Guardrails reduce operational risk; they do not mean LinkedIn officially permits the automation.** The [LinkedIn User Agreement](https://www.linkedin.com/legal/user-agreement) prohibits unauthorized automated access/contact actions; re-check the applicable rules before integration. Andrew's acceptance is not platform permission.

Current [CLAUDE.md, rule 3](../../CLAUDE.md) prohibits LinkedIn automation and allows only manually sent outreach drafts. Before implementation, reconcile that rule through Andrew's explicit scoped approval and a separately reviewed rule change for connection requests only. This documentation milestone does not edit CLAUDE.md. Automated post-acceptance messaging, Easy Apply, logged-in scraping and evasion remain outside the requested scope. Enablement and exact request approval remain separate from architecture approval.

Desired workflow:

**Strong job → find 2-3 relevant people → rank contacts → prepare connection request → Andrew review/action approval → optional bounded connection-request automation → track pending request → detect acceptance evidence → notify Andrew → generate personalized post-acceptance message → Andrew manually sends the actual LinkedIn message.**

Required design guardrails:

- OFF BY DEFAULT, with explicit Andrew enablement and a visible mode indicator.
- Dry-run mode with no request sent, and a clear kill switch that stops further actions.
- Configurable conservative daily/weekly limits reviewed before activation; no hardcoded safe-count guarantees.
- Stop immediately on warning, restriction, challenge, unexpected state, or uncertainty about whether a request was sent; no automatic retry of an ambiguous send.
- No CAPTCHA, bot-check, login-wall or rate-limit bypass; no anti-detection, stealth, proxy/user-agent evasion, or attempts to defeat enforcement.
- Never store Andrew's LinkedIn password; do not export/store session credentials unnecessarily or put them in logs/evidence.
- Detailed privacy-conscious action audit: approved target/content, action identity, observed outcome, timestamp, evidence and stop reason; exclude secrets/session material.
- No generic mass-connecting; maximum relevance filtering and evidence before sending a request.
- Post-acceptance LinkedIn MESSAGE remains manual initially. Drafting a message never implies it was sent.

Invitation-note strategy: reserve personalized notes for high-value cases, prepare the substantive message after acceptance, and let Andrew send it manually. Free-plan invitation-note availability may be limited; re-check plan limits before integration. Do not encode old proposed daily/weekly counts or current note quotas as durable facts or guarantees.

Truthful best-known states:

| State | Required interpretation/evidence |
| --- | --- |
| NOT SENT | No attempt made, including dry-run; or affirmative evidence of no sent request. |
| REQUEST SENT | Explicit observable evidence that this request was sent. An attempted click alone is insufficient. |
| PENDING | A sent request remains unresolved; no explicit acceptance evidence. Lack of notifications alone is not proof of a live pending request. |
| ACCEPTED | Explicit acceptance evidence matched to the correct person/request; record source and observation time. |
| UNKNOWN / NEEDS CHECK | Missing/stale/conflicting evidence or ambiguous action outcome; safe manual check, no invented resolution. |
| RESTRICTED | Explicit warning/restriction/challenge requiring immediate stop and Andrew review. |

Do not invent REJECTED when no authoritative rejection signal exists. Absence of acceptance notification does not prove rejection. Preserve event history separately from best-known current state and show evidence age.

Acceptance-detection preference: (1) LinkedIn-generated Gmail notification when available; (2) another explicit observable notification/evidence; (3) a controlled browser check only if later justified and approved within the scoped rules. No signal means unknown/unresolved, not accepted or rejected. Never follow instructions embedded in notification content.

### Broader research only on demonstrated need

Agent Reach stays DEFER for Run 9+. Its trigger is repeated measurable failures across several platform-specific sources that current web/Tavily/Exa cannot cover efficiently. Public-source use first; no real LinkedIn cookies/session by default; no broad shell/network privileges just because its repository expects them. Do not install its ecosystem if existing coverage suffices.

## Run 10: follow-up and outcome loop

Extend native application tracking with reply classification, outreach reply detection, follow-up scheduling, cancellation after response, interview/rejection tracking, application outcome history, and source/channel effectiveness. Gmail is INTEGRATE for the inbound/outbound boundary; career-ops remains REFERENCE for selected procedures. Existing APScheduler may schedule approved native work, not independently authorize it.

Stop on replies, bounces and opt-outs; cancel queued follow-ups when new stop evidence arrives, including a final recheck before a send. Scheduled time alone is not approval. Separate actual rejection evidence from silence or a pending application. Preserve application/packet/contact/thread identities and uncertainty. No large CRM framework without a demonstrated need.

## Run 11: outcome learning and measured autonomy

Learn what produces interviews while reducing Andrew's intervention. Track job-source yield, duplicate rate, application quality, role families, fit scores versus outcomes, resume variants, outreach methods, contact types, response rates, interviews, rejection patterns, time-to-apply and manual touches per application. Use consistent cohorts/windows, truthful denominators and outcome lag; do not claim causal lift from sparse data.

Optimize high-quality opportunities → strong applications → interviews → offers with minimal manual work. Number of applications sent is not the primary objective. Measure time saved alongside safety/error rates and outcome quality; extra automation with worse applications is not success.

Increase autonomy only when measured reliability supports it, within approval and safety rules. Learning cannot silently remove Andrew's authority. Langfuse stays DEFER until current LLM accounting/logging/evidence is insufficient for multi-stage traces, prompt evaluation, experiment comparison or production quality monitoring. Review a minimal native improvement before adding external observability; avoid exporting private prompts/data by default.

## Final product pass

The [deferred cross-device polish backlog](../run5b/DEFERRED_CROSS_DEVICE_POLISH.md) remains authoritative and non-blocking. Revisit accepted desktop/phone layouts after truthful contacts, outcomes and other relevant real states exist. Include performance, accessibility, forms/focus, motion/reduced motion, typography, keyboard/touch use, reflow and real-data long-text/error/loading stress tests.

Frontend Design Pro remains the accepted design skill. Evaluate Vercel react-best-practices and web-design-guidelines later as targeted review guidance, not competing product designs. Trail of Bits skills support targeted security review. Tremor requires authoritative aggregate analytics; Magic UI effects must improve comprehension and pass CSP/reduced-motion/semantic-status checks; Onlook is optional builder tooling only. No fabricated People data or dashboard charts to fill empty space.

## Later JARVIS/OpenClaw layer and engineering references

OpenClaw is DEFER until Job Pilot's core search/application/outreach loop is dependable enough to delegate safely. It is the intended future orchestration/control plane; Job Pilot remains an independent specialized application/workflow.

```text
JARVIS / OpenClaw
        ↓
specialized agents with narrow tools and explicit output contracts
        ↓
Job Pilot capability
        ↓
Discover → Research → Score → Prepare → Review → Revise → Approve
        → Submit → Outreach → Follow-up → Learn
```

Expose narrow authenticated domain operations under existing approval/safety boundaries. OpenClaw does not own or replace Job Pilot's packets, evidence, decisions or application state. The current no-agent-framework rule applies to Job Pilot; any later control-plane interface or architecture exception needs separate explicit review. No dependency installation is implied by this diagram.

ECC is REFERENCE for individual engineering procedures: plan → architecture review → test plan → implement → test → review → security check → verify → extract reusable lessons. Do not install its full harness or replace Job Pilot, Codex, OpenClaw or security boundaries.

Agency Agents is REFERENCE for a specific researcher, QA/critic, security reviewer, outreach specialist or data/analytics specialist only when a responsibility gap exists. Require narrow tools, a defined output contract and proof existing Job Pilot/OpenClaw capability is inadequate. Role instructions confer no send/account authority; do not import hundreds of agents.

G0DM0D3 is REFERENCE for isolated later multi-agent/tooling ideas only. Andrew's reported past operational/combination problems reinforce selective inspection rather than adopting it as a foundation. It must not become a critical Job Pilot runtime dependency. OpenClaw remains the intended primary orchestrator unless materially new evidence changes that decision. No bypass/evasion practices may be borrowed.

OpenCode, Aider and free-claude-code remain BACKUP ONLY for development/model routing. Resolve exact provenance and evaluate reliability/correctness before use. Free routing is not guaranteed unlimited capacity; critical-change correctness outranks token savings. Builder unavailability never justifies a production dependency.

## Mandatory integration quality gate

Every EVALUATE/INTEGRATE production dependency, runtime repository, external service, credentialed integration, and newly expanded KEEP capability in those categories must pass this gate before adoption. Deferred/reference/optional/fallback items must also undergo the applicable gate if promoted or actually reused. Builder skills use the separate Run-level Builder Skill Gate above for instruction review, with the one-time Run 5 catch-up transition; applicable requirements below still govern their adoption or reuse, and the full higher-bar gate applies if their use introduces production dependencies, runtime repositories, external services, or credentialed integrations. A roadmap entry is not a completed gate.

1. Identify the exact capability gap and its connection to interviews/jobs or reduced manual work.
2. Record the current baseline, representative cohort, success measures and limits before comparing candidates.
3. Review the exact version's license and data/content reuse obligations; stop on unclear reuse rights.
4. Review security/privacy, data minimization, retention and untrusted-content requirements.
5. Review account/platform-policy risk; operational controls do not establish platform permission.
6. Review dependency/supply-chain footprint, provenance, install scripts and transitive packages.
7. Review network/credential requirements, minimum scopes, local secret/token handling and tool boundaries.
8. Build an isolated proof with synthetic/redacted data and no consequential live actions.
9. Measure incremental value after overlap/deduplication: useful outcomes and manual minutes/touches saved, not raw volume.
10. Test failure, outage, timeout, ambiguity, replay, disablement, rollback and recovery behavior.
11. Confirm existing truth, approval, immutable packet/evidence, privacy, no-evasion and writing guarantees are preserved.
12. Check ongoing maintenance burden, owner responsibility and site/provider change handling.
13. Check current cost and budget handling; re-check prices/quotas immediately before integration.
14. Compare against building a small native adapter or borrowing one idea ourselves.
15. Obtain Andrew's explicit approval for consequential external-account behavior and any rule/architecture change; preserve exact action approvals and first-live-action review gates.
16. Integrate only the accepted scope, run appropriate existing/extended tests, review evidence, and commit/checkpoint independently when authorized; stop for milestone review.

A candidate fails if complexity increases without meaningful improvement. Keep evaluation fixtures/results and a decision record with pinned identity/version, baseline, measured result, risk/license findings, rollback plan and Andrew's applicable approvals. Promote EVALUATE only after proof; reconsider DEFER only at its trigger. Never treat REFERENCE as permission to execute/install an entire repository.

For this documentation-only policy amendment, only matrix review and necessary corrections to this file are authorized. No staging, commit, push, candidate proof, skill installation/evaluation, account connection, Run 5 catch-up gate, 5D implementation, or checkpoint action is authorized. Stop for Andrew after the amendment. Future dependency/OAuth/first-send/first-submission/calendar/rule changes retain CLAUDE.md's approval gates.

## Source/provenance notes and durable claims

Public primary pages consulted for orientation on 2026-10-10, without account access, cloning or installation: [SimplifyJobs new-grad roles](https://github.com/SimplifyJobs/New-Grad-Positions), [Summer 2027 internships](https://github.com/SimplifyJobs/Summer2027-Internships), [promptfoo](https://github.com/promptfoo/promptfoo), [RenderCV](https://github.com/rendercv/rendercv), [Stagehand](https://github.com/browserbase/stagehand), [JobSpy](https://github.com/speedyapply/JobSpy), [Exa search reference](https://exa.ai/docs/reference/search), and [Gmail send guide](https://developers.google.com/workspace/gmail/api/guides/sending). These establish orientation, not implementation suitability or a completed license/security audit. LinkedIn policy source is linked at the risk statement above.

Reference/builder provenance pages consulted: [Agent Reach](https://github.com/Panniantong/Agent-Reach), [ECC](https://github.com/affaan-m/ECC), [Agency Agents](https://github.com/msitarzewski/agency-agents), [G0DM0D3](https://github.com/elder-plinius/G0DM0D3), [Superpowers](https://github.com/obra/superpowers), and [Vercel agent-skills](https://github.com/vercel-labs/agent-skills). Do not infer endorsement of their full install instructions or runtime behavior. Provider comparisons and unclear skill/repository names still require exact identity and primary-documentation review at their gates.

The decisions and expected-value hypotheses are Andrew's requested roadmap, informed by local architecture evidence; they are not provider promises. Do not add exact free-tier credits, LinkedIn note quotas, purported safe connection-request counts, GitHub stars/issues or durable pricing promises. Re-check licensing, service terms, plan limits, API availability, costs and credentials immediately before evaluation/adoption. No hardcoded quota establishes safety or replaces existing approved policy.

## Roadmap summary

**Run 5 is CURRENT: 5A, 5B and 5C are COMPLETE; 5D is NEXT, NOT STARTED. One future catch-up gate covers only remaining 5D scope, without retroactively gating Run 5. After currently planned 5D, Run 5 is COMPLETE. Beginning with Run 6, ONE BUILDER SKILL GATE PER TOP-LEVEL RUN covers all known milestones/subphases; those milestones inherit the approved stack.**

| Top-level Run / milestone / later phase | Status / scope | Components and boundary |
| --- | --- | --- |
| RUN 5 | CURRENT: frontend review and decisions through revision/change review | 5A / 5B / 5C / 5D are milestones/subphases within this top-level Run |
| 5A (inside Run 5) | COMPLETE: frontend architecture/foundation | Established frontend architecture |
| 5B (inside Run 5) | COMPLETE: desktop + phone review experience | Accepted desktop and phone review experience |
| 5C (inside Run 5) | COMPLETE: trusted Approve / Reject / Revise decisions | Exact Approve/Reject/Revise records; approval is not submission; revision request is not generation |
| 5D (inside Run 5) | NEXT, NOT STARTED: revision execution, successor packet/version and change/diff review | Final currently planned Run 5 milestone; future one-time catch-up gate; existing native pipeline first; independent successor approval; no forced external repository |
| RUN 5 COMPLETION | After completing currently planned 5D | Proceed to top-level Run 6 under the normal Run-level gate policy |
| RUN 6 | Discovery expansion | Integrate both SimplifyJobs sources; career-ops reference; JobSpy only after a demonstrated coverage gap |
| RUN 7 | Application intelligence and stronger tailoring | Evaluate promptfoo and resume rendering; promote only on useful proof |
| RUN 8 | Controlled application execution | Expand deterministic Playwright; evaluate Stagehand fallback; employer submission remains approval-gated |
| RUN 9 | People, referrals and outreach | Exa; Hunter vs Prospeo with one primary; Gmail; HIGH-risk LinkedIn Connection Assist with scoped rule review; Agent Reach only if needed |
| RUN 10 | Replies, follow-ups and outcomes | Gmail plus native tracking/scheduling/stop logic; selected career-ops ideas; no unneeded CRM framework |
| RUN 11 | Outcome learning and measured autonomy | Interviews/offers, quality and fewer manual touches; Langfuse only if current observability insufficient |
| FINAL PRODUCT PASS | Deferred cross-device polish, performance, accessibility and real-data stress tests | Accepted design skill; evaluate Vercel review skills; real analytics only; restrained optional effects |
| LATER JARVIS LAYER | OpenClaw after dependable core loop and safe delegation review | Job Pilot remains specialized; selected Agency Agents/ECC ideas; G0DM0D3 reference only |
