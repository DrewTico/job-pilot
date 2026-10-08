# Run 4 authenticated Tailscale and multi-device access report

## Current Run 4 status

| Milestone | Status |
| --- | --- |
| A: application authentication boundary | COMPLETE |
| B: real Tailscale / Serve validation | COMPLETE |
| C: real authenticated multi-device approval access | COMPLETE |
| D: approval queue lifecycle | COMPLETE |
| E: final regression and security closeout | COMPLETE |
| Run 4 | COMPLETE |

Run 4 completes authenticated private Tailscale multi-device access to the Job
Pilot approval queue, preserving existing packet/approval/revision safety
boundaries. It does not complete the broader product or roadmap, automated
employer submission, revision processing, Windows boot orchestration or the
future UI redesign.

The historical B/C documentation/sign-off pass started at `ed28f72 fix: show approval access
mode accurately`, with `main` and `origin/main` aligned and a clean working tree.
The completed B/C session evidence below is supplied by Andrew as authoritative
operator observations, not a new live validation performed during this pass.
Runs 1-3 use one report per broader Run with accumulated milestone history;
this report continues that convention for Run 4.

The Milestone A historical body/evidence below is preserved unchanged. Its untested/deferred and
stop-before-B statements describe the end of A; B and C subsequently closed
those real-environment limitations. Milestones A, B, C, D and E are COMPLETE.
Earlier milestone stop/deferred statements are historical; the E closeout below
records the final supplied evidence, not new runtime validation in this pass.
At the end of C, the production approval queue was restored, then
intentionally stopped for milestone sign-off. This does not assert that the full Job Pilot pipeline
is running.

## Historical Milestone A: application authentication boundary

Starting HEAD: `f103915 feat: add secure local approval queue and revision worker`.
The start gate confirmed that HEAD and a clean working tree. Read CLAUDE.md,
README and the five required implementation/safety reports; reinspected approval
app/security/service/models, CLI/settings and Run 3 queue/API/security/UI tests.
No rule or architecture change, new dependency or frontend framework.

Implementation and complete deterministic validation are finished. Andrew
approved the exact outside-sandbox test-only command before execution. This is
Milestone A only. No Milestone B operation has begun. Work stops for review.

## Exact file scope

```text
README.md
TAILSCALE_ACCESS_REPORT.md
src/job_agent/config.py
src/job_agent/cli.py
src/job_agent/dashboard/approval_security.py
src/job_agent/dashboard/approval_app.py
src/job_agent/dashboard/approval_models.py
tests/test_tailscale_security.py
tests/test_tailscale_api.py
```

Schema remains **v9**. All seven prohibited domain production files have an empty
Git diff: approvals.py, packet_verify.py, packets.py, revisions.py, database.py,
llm.py and tavily_research.py. ApprovalQueueService, history helpers, frontend and
existing tests are unchanged. No identity/device state or special privileges were
added to SQLite. Exact packet and approval-view fingerprints, decision replay,
conflict, revision/history, truth and immutable-version semantics remain owned
by the existing domain service.

## Mode and private configuration contract

`approval-queue` defaults to `--access local`, preserving Run 3 Host policy,
local HTTP Origin, process CSRF, response headers and exact bootstrap fields.
Neither Tailscale setting is required in local mode. Tailscale configuration
alone never activates authentication mode.

`--access tailscale` requires both `JOB_AGENT_APPROVAL_TAILSCALE_LOGIN` and
`JOB_AGENT_APPROVAL_TAILSCALE_HOST`. Settings uses SecretStr, repr=False and
exclude=True. Values are loaded without trimming or empty-to-None conversion;
empty, absent and invalid configuration fails before storage opening. Validation
is mode-specific so unused private configuration cannot break local mode.
Startup diagnostics omit exception detail and both values.

Supported login: one printable ASCII byte sequence of length 1–512, no whitespace,
controls, comma, wildcard characters `*?[]` or RFC2047 encoded words. Equality is
exact bytes with no decoding fallback, normalization, alias or suffix matching.
Unsupported future operator login representations require deliberate extension
before setup, never silent normalization.

Supported hostname: lowercase device and tailnet DNS labels followed by `.ts.net`.
Each label is 1–63 bytes, starts/ends alphanumeric and contains only lowercase
ASCII letters, digits and internal hyphens; total length at most 253 bytes.
No scheme/path/port/userinfo/wildcard/trailing dot/localhost/IP form is accepted.
Private values never enter bootstrap JSON, settings serialization, SQLite or logs.
Only synthetic identities/hostnames appear in tests and documentation.

Both commands always call Uvicorn with host 127.0.0.1, proxy_headers=False,
forwarded_allow_ips empty, access_log=False. There is no --host option. No
Tailscale CLI, subprocess, control-plane/API client, token storage or service
management was added to the application.

## Request contract and order

The existing pure ASGI middleware was extended instead of duplicating the domain
adapter. Local mode retains its original Host-before-endpoint ordering and exact
accepted authorities, including port-80 local behavior. Tailscale mode enforces:

1. Actual ASGI server exactly `(127.0.0.1, configured_port)`, client IPv4 loopback,
   backend scheme HTTP, reusing the original Run 3 endpoint predicate.
2. Exactly one raw Host header equal to the configured hostname. Only the canonical
   external HTTPS authority without an explicit port is accepted, including when
   the backend happens to use port 80. Even explicit :443 is refused.
3. Exactly one raw Tailscale-User-Login header with supported bytes and exact
   configured login equality, on every HTTP request and method.
4. Unsafe methods require exactly one Origin equal to the configured
   `https://<host>` and one valid X-Job-Pilot-CSRF token.
5. Existing bounded JSON/content-type/encoding/length handling, then FastAPI DTO
   parsing/routing and the unchanged approval domain operation.

Failures at steps 1–4 do not consume a private body. Authentication covers shell,
assets, bootstrap, queue, details, history, status, decision detail, diffs,
application destination, PDF, mutations and unknown/404 paths. Forwarded and
X-Forwarded-* headers are ignored; they cannot establish a client, Host, identity,
backend scheme or external Origin. User name/profile picture are never authority
or loaded. Cookies/query/body are not identity sources. Tagged devices without a
user identity and shared external users with another login are denied.

Authenticated bootstrap returns only csrf_token, local_only=false and
access_mode=tailscale; neither host nor login is returned. The UI already uses
only csrf_token and needs no asset change. Local bootstrap retains csrf_token,
local_only=true and its local origin. CSRF remains random process memory, no
cookie/storage/log/DB, changes after restart, and never substitutes for identity.
Identity never substitutes for CSRF. Existing exact packet/view DTO requirements
are applied after the transport boundary.

All Run 3 security headers and CSP remain byte-for-byte unchanged. No CORS,
remote images/profile pictures, CDN/fonts/analytics, unsafe-inline/unsafe-eval
or remotely reachable listener was added. The private packet logging context
continues to suppress domain/SQL diagnostics. New boundary failures log nothing.

## Sanitized error mapping

| Condition | HTTP status / machine code |
| --- | --- |
| Untrusted backend/client/scheme | 403 local_only |
| Missing/duplicate/nonexact Host | 400 invalid_host |
| Missing/empty/duplicate/ambiguous/oversized/unsupported identity | 401 authentication_required |
| Supported identity with nonmatching exact bytes | 403 authorization_failed |
| Missing/invalid/duplicate Origin or CSRF | 403 csrf_failed |
| Body/header/DTO validation | 422 invalid_request; oversize 413 invalid_request |
| Startup private configuration | invalid_approval_access_configuration, sanitized CLI failure |

All other error mappings remain Run 3's existing sanitized codes. No expected or
received login, hostname, raw header, body, CSRF, evidence, fingerprint, path,
SQL or exception internals are returned in failures.

## Trust assumptions and real-environment limitation

The read-only architecture pass selected WSL-local Tailscale Serve -> HTTP
loopback -> Job Pilot 127.0.0.1:8643. Windows/WSL Tailscale were not detected,
WSL2 networking is NAT, and systemd is available/running. This placement has
**NOT** been proven in the real environment. Milestone A did not repeat discovery
or perform any installation/configuration/network smoke.

Synthetic scope tests demonstrate policy logic only. They do not prove Serve's
actual Host/identity forwarding, IPv4 loopback client with ephemeral port, exact
backend server tuple or HTTP scheme. A deliberately replaced launcher, forged
scope or equally privileged malicious local process lies inside the trusted-host
boundary; such a local process can forge an identity header. No stronger host
isolation is claimed. The existing filesystem/DB/cooperating-lock limitations and
point-in-time destination-validation limitations remain unchanged.

## Deterministic validation

New tests collected: **185** (109 config/CLI/pure ASGI; 76 full-app/adapter).
Whole established suite collected: **2,786** (2,601 preserved + 185 new).

Completed sandbox selections:

- Focused config/CLI/local security/new Tailscale security: **196 passed**,
  final 0.82 seconds.
- Security/queue/config/CLI/new boundary/static UI selection: **203 passed**,
  20 deselected, 0.93 seconds. Four port-80 local cases whose names contain
  browser were deselected here but passed in the focused run above.
- Final new full-app authentication/async-bootstrap/source audit plus existing
  static UI: **72 passed**, 22 deselected, 28.21 seconds.
- Existing Run 3 direct adapter/factory/CLI/async-bootstrap/mutation-boundary
  selection: **52 passed**, 74 deselected, 24.19 seconds.
- Complete established sandbox-compatible offline split, including all affected
  domain regressions: **2,407 passed**, 271.83 seconds; no warnings/skips/xfails.

These overlapping selections are not summed as unique coverage. One preliminary
broader existing API selection inadvertently included its threaded shell test,
hit the documented sandbox thread-wakeup timeout after 12 passes and was
interrupted. It is not a successful run or an application bypass; the corrected
52-case selection above passed. No production policy or safety assertion was
weakened to accommodate the environment.

The approved outside-sandbox tests covered all current Run 3 API/UI, new authenticated
threaded reads/actions and the original ten-file Chromium/FastAPI split. New
adapter cases assert required exact fingerprints, stale packet/view failure,
replay/conflicts, independent successor approval, historical/current distinction,
application destination revalidation, schema/DB nonmutation and privacy.
Socket/connect/DNS, HTTP client, Anthropic, Tavily, packet-build/revision,
subprocess and browser-entry traps surround authenticated request operations.
The recovery successor is built from offline fake fixtures before request traps.
Existing UI tests confine Chromium to their assigned local test origin and spy
employer navigation rather than contacting employers.

Approved exact TEST-ONLY outside-sandbox command executed:

```sh
.venv/bin/pytest -q tests/test_apply_open.py tests/test_dashboard_apply.py tests/test_apply_ashby_dom.py tests/test_search_state.py tests/test_dashboard.py tests/test_application_state.py tests/test_grounded_yesno.py tests/test_extension_scan_dom.py tests/test_extension_fill_dom.py tests/test_extension_api.py tests/test_approval_api.py tests/test_approval_ui_dom.py tests/test_tailscale_api.py
```

This preserves the established split and adds the focused authenticated adapter
file. It contains no installation, setup, remote listener, provider/employer/live
Tailscale activity, commit or push. The complete disjoint suite passed: **2,407
sandbox + 379 outside = 2,786**. The outside split passed in **123.93 seconds**,
with no warnings/skips/xfails. All 185 new cases and all 2,601 preserved cases
passed, including 16 actual Chromium approval UI cases. Focused runs overlap
this total.
Section 23 of Andrew's Run 4 request explicitly requires stopping and requesting
approval before this established test-only outside-sandbox command.

## Required explicit answers

These answers describe the supported application contract under the documented
trusted-host assumptions. Dynamic adapter/browser validation passed as recorded
above; actual Tailscale Serve and multi-device access remain untested.

| # | Question | Answer |
| --- | --- | --- |
| 1 | Did schema change? | NO |
| 2 | Did approval domain semantics change? | NO |
| 3 | Does local mode still work without Tailscale config? | YES |
| 4 | Can Tailscale mode start without configured login? | NO |
| 5 | Can Tailscale mode start without configured host? | NO |
| 6 | Can Tailscale mode bind 0.0.0.0? | NO |
| 7 | Can localhost Host access a Tailscale-mode process? | NO |
| 8 | Can wildcard *.ts.net Host pass? | NO |
| 9 | Can X-Forwarded-Host authorize a request? | NO |
| 10 | Can a non-loopback client supply Tailscale-User-Login and authenticate? | NO |
| 11 | Can missing identity authenticate? | NO |
| 12 | Can wrong identity authenticate? | NO |
| 13 | Can display name authenticate? | NO |
| 14 | Can profile picture authenticate? | NO |
| 15 | Can a valid CSRF token authenticate the user? | NO |
| 16 | Can valid identity bypass CSRF? | NO |
| 17 | Can HTTP Origin mutate? | NO |
| 18 | Can foreign/null Origin mutate? | NO |
| 19 | Does bootstrap return CSRF before authentication in Tailscale mode? | NO |
| 20 | Can remote mode omit packet fingerprint requirements? | NO |
| 21 | Can remote mode omit approval-view fingerprint for Approve? | NO |
| 22 | Does app code invoke tailscale CLI? | NO |
| 23 | Does app code call Tailscale APIs? | NO |
| 24 | Does app configure Serve? | NO |
| 25 | Does app configure Funnel? | NO |
| 26 | Does app expose a public listener? | NO |
| 27 | Were Anthropic/Tavily called? | NO |
| 28 | Was any employer contacted? | NO |
| 29 | Was Tailscale installed/logged in/configured? | NO |
| 30 | Is real multi-device access proven yet? | NO |

## Next privileged gates, strictly deferred

After completed Milestone A validation and Andrew's review, Milestone B needs
explicit operator authorization for controlled installation, login/setup and
WSL-local Serve/HTTPS configuration, plus review of the exact commands/policy
and any privileged operations. It must prove real ASGI observations and safe
Host/identity/Origin/CSRF behavior through Serve before claiming multi-device
access. If observations require broad bind, non-loopback trust or generic
forwarded-header trust, stop and return for architecture review. Funnel/public
exposure and policy changes are not implied by this implementation.

No install, sudo, Tailscale login/up/Serve/Funnel/HTTPS/policy change, WSL networking
change, provider/employer activity, commit or push occurred. HEAD is unchanged.
Python compilation and `git diff --check` pass. Final working tree has exactly
the nine intended modified/new files listed above. Complete offline validation
is finished. STOP for Andrew's Milestone A review; no Milestone B, commit or push.


## Milestone B: real Tailscale / Serve validation COMPLETE

Operator-observed validation confirmed that Tailscale was installed and connected
inside WSL and the WSL Job Pilot node was online. Tailscale Serve was configured
as tailnet-only HTTPS and proxied to `http://127.0.0.1:8643`:

```text
tailnet HTTPS -> Tailscale Serve -> HTTP loopback -> Job Pilot 127.0.0.1:8643
```

Job Pilot remained bound only to IPv4 loopback. No `0.0.0.0` or other broad
backend bind was introduced, and no Tailscale Funnel/public exposure was enabled.
The real Serve trust boundary was exercised in the actual WSL environment. The
real path demonstrated the intended Host, Tailscale identity, HTTPS Origin and
CSRF boundary through Serve. Direct/spoofed-header behavior was tested rather
than accepted as authority; generic forwarded headers continued to supply no
application authority.

B closed the real-environment limitation explicitly left open at the end of A.
No approval-domain semantics changed, no employer-facing submission occurred,
and no provider operation was part of B. The trusted-host limitation remains:
an equally privileged compromised local process can forge identity headers.
Real Serve validation does not establish stronger local-host isolation.

## Milestone C: real multi-device validation COMPLETE

### Real iPhone access and narrowed authorization

A real iPhone accessed the authenticated Job Pilot approval queue successfully
with Tailscale enabled. The same access failed with Tailscale disabled. The
tailnet Grant was narrowed to the authorized user -> Job Pilot node -> `tcp:443`.
The external path remained tailnet-only and the backend remained loopback-only:

```text
iPhone -> tailnet HTTPS -> Tailscale Serve -> loopback-only Job Pilot approval queue
```

This completes real authenticated multi-device approval access. It does not
claim public Internet access.

### Production isolation and first exact-content failure

A retained production-data baseline was captured before controlled testing.
Production baseline comparison passed before the phone test. Synthetic phone-test
state existed only in isolated temporary databases under `/tmp`; these are test
evidence locations, not required runtime configuration. No synthetic state was
moved into production for demonstration or history.

The first real iPhone attempt persisted all three decision types: Approve,
Reject and Revise. Its durable Reject had `reason_code = bad_fit` and an empty
string detail. The controlled C target required `detail = Exact reason`, so the
independent verifier correctly returned:

```text
FAIL: reject_audit_mismatch
```

This was a failed exact-content run, not a passing validation. Reject detail is
optional in normal product semantics; this controlled test required the exact
expected detail. The failed synthetic database was preserved and was not
rewritten, reused, weakened or mutated to manufacture a passing result.

### Fresh retry and independent final pass

A completely fresh synthetic retry database was created and independently
seed-verified before phone interaction. Andrew repeated all three actions from
the real iPhone. The independent post-phone verifier returned:

```text
Verified three synthetic packets and manual decisions.
verify-decisions exit=0
```

Independent production comparison after the successful retry returned:

```text
Production baseline matches explicit expectations.
compare-baseline exit=0
```

Final durable counts in the successful synthetic retry were:

```text
packet_decisions = 3
revision_work = 0
application_events = 0
```

Here `revision_work` is the supplied count label for durable revision work
(the repository table is `packet_revision_work`), not a new schema/table.
The exact durable decisions were:

| Decision | Actor | Reason / reason_code | Detail / feedback |
| --- | --- | --- | --- |
| Approve | Andrew | empty | empty |
| Revise | Andrew | empty | Make the synthetic packet more concise. |
| Reject | Andrew | bad_fit | Exact reason |

No revision worker ran during these phone decision requests. No application event
was created, no employer-facing submission occurred, and no provider/employer
operation occurred. No synthetic decision entered production. Append-only decision
behavior was preserved; the failed record was not repaired into the retry result.
HTTP Revise recorded a durable request only, without automatic revision processing.
The independent baseline comparison establishes that this synthetic validation
did not modify the production Job Pilot data set.

### Production approval queue restoration and runtime scope

After successful synthetic validation, production data again matched the retained
pre-test baseline. The authenticated approval queue was successfully started
against the real production data directory, still backed by `127.0.0.1:8643`,
with Tailscale Serve as the tailnet-only HTTPS front door. The approval queue was
then intentionally stopped for milestone sign-off.

This proves restoration and successful startup of the production approval queue,
one Job Pilot component. Search/discovery, scoring, packet generation, revision
processing, scheduling and future submission have separate runtime lifecycles.
It does not prove full Job Pilot runtime orchestration or that Job Pilot is
currently running. The production queue contained no synthetic phone-test history
because the tests were deliberately isolated; that is expected, not missing data.
Existing trusted-host, filesystem/DB/cooperating-lock and point-in-time
validation limitations remain unchanged.

## Historical Milestone C documentation sign-off and review stop

This pass changes only this report and the current Run 4 wording in README.md.
Milestone A history and older Run 1-3 reports remain intact. No production code,
tests, schema, data, private configuration, approval/packet/revision semantics or
security boundaries changed. No dependency, live network call, workflow start,
Tailscale/Serve/Grant/Funnel/listener/networking change, staging, commit or push
was performed during this documentation pass.

The documentation uses generic architecture and exact supplied synthetic test
results, without private login/hostname, authentication or CSRF values, secrets,
private environment contents or unnecessary temporary absolute paths.
No supplied operator evidence conflicts with the inspected repository contract;
the B/C results are recorded as operator evidence rather than newly rerun checks.

STOP for Andrew's Run 4 Milestone C review under CLAUDE.md:
“Stop after every milestone for Andrew's review.” Milestone D has NOT STARTED.

## Milestone D: approval queue lifecycle COMPLETE

### Historical preparation/design state

This preparation pass started with a clean working tree at `ec9a206 docs: record
Run 4 Tailscale validation`; `main` and `origin/main` were aligned there. The
completed read-only lifecycle inspection supplied by Andrew is authoritative
evidence, not a new live inspection or lifecycle validation in this pass:

- WSL PID 1 is systemd; the installed version supports the user-service design.
- Andrew's user manager is running and lingering is already enabled.
- No Job Pilot systemd unit, approval queue or revision worker was running.
- `tailscaled` is independently enabled/running as a system service; Tailscale
  is online. Serve retains tailnet-only HTTPS :443 to `http://127.0.0.1:8643`.
- No Funnel entry exists. No Tailscale, Serve, Grant/policy, firewall or WSL
  networking change is needed.
- Reliable Windows boot startup of WSL has not been proven. Starting a service
  inside running WSL and starting WSL at Windows boot are distinct. Windows
  startup automation is an optional future decision outside this slice.

Selected architecture B is **user-level systemd for the approval queue only**,
with no sudo/root installation requirement. The revision worker is deliberately
excluded from autostart: it scans durable revision work immediately and then
every 10 seconds, and may begin eligible Anthropic writing. The normal scheduler
is also excluded. Manual commands remain separate:

```sh
.venv/bin/job-agent approval-queue --access tailscale --data-dir data --port 8643
# Only when Andrew intentionally requests revision processing:
.venv/bin/job-agent scheduler --revisions-only --data-dir data
```

### Historical repository preparation artifacts and configuration evidence

`deploy/systemd/job-pilot-approval.service` is a template only, intended for a
future operator copy to `~/.config/systemd/user/job-pilot-approval.service`.
It uses Type=exec, the existing virtualenv approval command, explicit production
data path and port 8643, on-failure restart with a 10-second delay and three
starts per 300 seconds, SIGTERM/control-group stop with a finite 30-second
timeout, UMask=0077, LimitCORE=0 and journal stdout/stderr. WantedBy=default.target
is declarative installation metadata, not installation or enablement. There are
no other execution hooks, worker commands, network-online/tailscaled ownership
dependencies, private values, Environment/EnvironmentFile assignments, Tailscale
configuration commands or aggressive sandbox directives.

The working directory is `%h/projects/job-pilot`; the executable and explicit
data path share that prefix. Local systemd.service(5) accepts command-line
specifiers and systemd.unit(5) defines `%h` as the service manager user's home.
Local systemd.exec(5) documents WorkingDirectory path semantics. To resolve its
specifier behavior explicitly, the matching upstream systemd 259
[working-directory parser](https://github.com/systemd/systemd/blob/v259/src/core/load-fragment.c)
calls unit_path_printf, and the
[specifier implementation](https://github.com/systemd/systemd/blob/v259/src/core/unit-printf.c)
uses the shared table containing the home-directory specifier. This establishes
support in both fields without hardcoding an operator home path.

Installed python-dotenv 1.2.3 source was inspected without loading private
configuration. `load_settings()` still calls `load_dotenv()` with no arguments;
normal CLI execution searches upward from the caller source location. The
current editable import resolves to repository `src/job_agent/config.py`.
Two isolated subprocess tests copy the unchanged loader into a controlled
temporary editable layout and prove discovery of its temporary `.env` from
the repository working directory and a different working directory. Children
have an empty inherited environment and isolated import paths. No private
`.env` is read, changed or copied. No config.py change or secret EnvironmentFile
is required. Existing environment overrides retain precedence.

Both private settings, `JOB_AGENT_APPROVAL_TAILSCALE_LOGIN` and
`JOB_AGENT_APPROVAL_TAILSCALE_HOST`, must be valid before any live authenticated
start. `.env.example` now documents commented placeholders only, with real
values confined to `.env` and normal local-mode defaults unchanged. The supplied
inspection established that the private `.env` is gitignored, user-owned and
0600; its values were not inspected in this pass.

No production Python, schema v9, domain, packet, revision or authentication
change is required. Startup opens existing SQLite storage without migration,
import or schema creation, generates process-local CSRF state and starts no
worker, Anthropic operation or employer contact.

### Historical preparation validation and review boundary

Repository tests inspect the service as data, never call systemctl, and cover
the exclusive command, paths, restart/stop/privacy contracts, absence of other
execution/install/network hooks and controlled dotenv discovery.

Sandbox validation for this exact slice:

```sh
.venv/bin/pytest -q tests/test_approval_service_unit.py tests/test_config.py tests/test_cli_defaults.py tests/test_tailscale_security.py tests/test_approval_security.py
# 201 passed in 1.37s (includes all five new tests)
.venv/bin/pytest -q tests/test_approval_api.py -k 'factory_only_opens_existing_v9_without_mutation or cli_loopback_only_and_port_bounds'
# 2 passed, 124 deselected in 2.09s
.venv/bin/pytest -q tests/test_tailscale_api.py -k 'bootstrap_auth_private_restart_no_storage or no_tailscale_management_in_approval_code'
# 2 passed, 74 deselected in 3.13s
.venv/bin/python -m py_compile tests/test_approval_service_unit.py
git diff --check
```

All commands above exited 0. These focused selections total 205 distinct passing
tests, covering the template, settings, CLI, local/Tailscale boundaries, existing
v9-only startup and private bootstrap/restart contract. No full Milestone E
regression, threaded/browser validation or live lifecycle test was run.

Earlier sandbox `systemd-analyze --user --generators=no verify` failed before
unit parsing because the Codex sandbox denied SO_PASSCRED on a handoff timestamp
socket (exit 1). A system-scope offline parser attempt failed at the same point
(exit 1). Neither is a passing unit verification or live service operation;
those failures remain recorded as sandbox limitations.

Andrew explicitly approved the following TEST-ONLY, read-only outside-sandbox
verification, which then ran against the real installed user-scope systemd v259
parser:

```sh
systemd-analyze --user --generators=no --recursive-errors=no verify "$PWD/deploy/systemd/job-pilot-approval.service"
```

Result: exit code 0; stdout and stderr were empty; no warnings or errors were
emitted. The proposed unit passed actual parser verification. `--user` selected
the user-service context, `--generators=no` prevented generator execution, and
`--recursive-errors=no` made errors in the specified unit affect the result.
No installation, unit copy, daemon reload, enablement or service start occurred.
The command did not read private `.env` or modify repository files, production
data or manager configuration. Parser verification does not establish live
lifecycle behavior. The user service can manage the queue once WSL and its user
manager are running; it does not prove Windows automatically starts WSL or that
the service keeps WSL alive indefinitely. Windows boot / WSL startup automation
remains a separate optional future decision.

Post-verification sandbox follow-up: `.venv/bin/pytest -q
tests/test_approval_service_unit.py` exited 0 with 5 passed in 0.41s;
`git diff --check` exited 0 with no output.

At the end of preparation, journal privacy and actual lifecycle behavior still
required controlled live validation. No live unit copy, installation, daemon
reload, enablement or start/stop/restart occurred during that preparation pass.
The subsequent operator validation below supersedes that pending live-validation
boundary.

### Completed live operator validation

Andrew supplied the following completed operator evidence. These observations
were not rerun during this documentation repair:

- The reviewed user-systemd approval service was installed; user daemon-reload
  succeeded. Controlled start/stop/start and systemd restart succeeded.
  Controlled systemd restart changed MainPID and produced fresh process-local
  CSRF state. One controlled SIGKILL caused one `Restart=on-failure` recovery
  with a new PID and fresh process-local CSRF state. The service was enabled
  successfully.
- A full WSL shutdown/restart was performed. The enabled approval service returned
  automatically after WSL restarted. Exactly one approval queue ran; the revision
  worker and normal scheduler remained absent.
- The listener remained exactly `127.0.0.1:8643`; schema remained v9. The production
  SQLite hash remained unchanged across the WSL interruption.
- Tailscale returned online. Serve remained the private tailnet HTTPS -> loopback
  proxy; Funnel remained absent. Authenticated Tailscale bootstrap still succeeded.
- Private Tailscale login/hostname were absent from the current-boot service journal.

This is a **user systemd service for the approval queue only**. Revision processing
remains **manual/on-demand**; neither the revision worker nor the normal scheduler
is automatic. Job Pilot does not own `tailscaled` or the Serve/Funnel lifecycle.
The validated access path remains private, with no public exposure.

The successful WSL interruption test proves behavior once WSL itself is
started/restarted. Windows automatically launching WSL at Windows boot has **NOT
been proven**. This evidence does not establish that the service keeps WSL alive
indefinitely. Controlled restart and crash recovery each produced fresh
process-local CSRF state; the WSL interruption test did not separately perform
a pre/post token comparison.

### Historical Milestone D sign-off status

**Milestone D is COMPLETE. Milestone E is NOT STARTED.**
This is not completion of all Run 4 or full Job Pilot runtime orchestration.

## Milestone E: final regression and security closeout COMPLETE

### Evidence provenance and starting checkpoint

This section records Andrew's supplied operator/test evidence and final
independent static audit. These checks were not rerun for documentation closeout.
E began from `58e8fb0ef08a11efcceeaf6571a4a3c6fdb57e6b`,
`feat: add approval queue user service`, with `main` and `origin/main` aligned.
The documentation start gate confirmed that checkpoint and exactly the two
reviewed modified files: `src/job_agent/dashboard/extension_api.py` and
`tests/test_extension_api.py`. This closeout edits only README.md and this report.

### Initial complete regression findings

The first monolithic pytest run collected and passed all **2795 tests**, but
reported **21 Python 3.12 multiprocessing DeprecationWarnings**:

| File | Warnings |
| --- | --- |
| tests/test_packet_chaos.py | 7 |
| tests/test_revisions.py | 12 |
| tests/test_scheduler.py | 2 |

All originated in `multiprocessing/popen_fork.py`, warning that `fork()` from a
multithreaded process may deadlock. The production SQLite **file hash changed**
during that run. Schema remained v9, SQLite quick_check was OK, all 15 production
business/application tables contained zero rows, and no WAL/SHM/journal sidecar
remained. The approval service stayed active and loopback-only; no production
business row mutation was found. This initial run was **not the final accepted
regression**.

### Controlled DB-writer trace and root cause

A controlled Bubblewrap trace used a **private copy** of production data.
Pytest collection itself did not mutate the shadow production-path DB. The first
mutating test was
`tests/test_extension_api.py::test_file_fields_pause_and_the_response_recommends_the_tailored_pdf`.
The real production DB remained unchanged throughout the trace.

Source inspection established this path:

```text
create_app(data_dir=tmp_path)
  -> create_extension_router(data_dir=tmp_path)
  -> /api/extension/fill-values
  -> load_settings() independently retains another/default data_dir
  -> company/context + API key eagerly constructs screening.make_llm_generate(settings)
  -> AnthropicExecutor without an explicit engine
  -> initialize_database(settings.data_dir / "job_pilot.sqlite3")
```

Thus an app/test using an injected alternate data directory could touch the
repository-default SQLite accounting path. The offending request did not even
contain unresolved free text requiring LLM drafting.

### Bounded repair and targeted reproof

The repair changes exactly `src/job_agent/dashboard/extension_api.py` and
`tests/test_extension_api.py`. It copies Settings with Pydantic `model_copy` to
make the extension router's injected `data_dir` authoritative for screening LLM
accounting, without mutating global Settings. Before constructing the generator
or accounting path, it checks the same existing
`screening.classify_question(..., reason) == "free_text"` predicate used by
`apply_drafts`. No unresolved free-text need means no `make_llm_generate`
construction. Drafting capability metadata, grounding, review, gating and actual
drafting when free text requires it are preserved. No schema or trusted
approval-domain production code changed.

The regression assertions prove:

1. API key plus company context with no unresolved free text does not call
   `make_llm_generate`.
2. Real unresolved free text supplies `make_llm_generate` with `settings.data_dir`
   equal to the synthetic directory passed to `create_app`, even when
   `JOB_AGENT_DATA_DIR` points elsewhere.

Focused `tests/test_extension_api.py` validation: **24 passed**. The exact original
offending test under Bubblewrap shadow production data: **1 passed**. Both the
shadow production-path SQLite and real production SQLite remained byte-for-byte
unchanged. Result: **PASS - DATABASE-PATH DEFECT REPAIR VERIFIED**.

### Multiprocessing warning isolation

Each originally warning-producing file was rerun in its own **fresh pytest
process** with `-W error::DeprecationWarning`:

| File | Result |
| --- | --- |
| tests/test_packet_chaos.py | 207 passed |
| tests/test_revisions.py | 283 passed |
| tests/test_scheduler.py | 49 passed |

No promoted DeprecationWarning failed any file; production SQLite remained
unchanged. The controlled results identify the original 21 warnings as a
monolithic-process test-run artifact: later fork-based tests ran after threads
had existed in the same long-lived pytest process. No production multiprocessing
behavior was changed merely to suppress the artifact. These results do not
establish that Python has no general fork hazard.

### Accepted complete deterministic/offline regression

The final accepted suite used the established **disjoint** test architecture,
with DeprecationWarning promoted to an error:

| Disjoint partition | Passed | Exit |
| --- | --- | --- |
| Sandbox-compatible complement | 2412 | 0 |
| Established outside FastAPI/Chromium/API split | 383 | 0 |
| Unique complete current suite | **2795 / 2795** | |

Targeted reproof and warning-isolation reruns are not added to this unique total.
After the suite, production SQLite hash and approval-service PID were unchanged;
`ActiveState=active`, `SubState=running`, `NRestarts=0`. The listener remained
exactly `127.0.0.1:8643`, production schema remained v9, and `git diff --check`
passed. Result: **PASS - COMPLETE DISJOINT OFFLINE REGRESSION**.

### Controlled final real-tailnet security smoke

The final live smoke used the existing configured environment. It changed no
Serve, tailnet policy, login, systemd configuration or production data. Its
starting and final repository state contained only the two reviewed repair files
at checkpoint `58e8fb0`. The supplied observations passed:

- Approval service active; backend exactly loopback-only; Tailscale self state
  available. Serve remained tailnet-only, proxying to `127.0.0.1:8643`.
  Funnel/public Serve permission was absent.
- Authenticated HTTPS bootstrap succeeded with normal TLS certificate
  verification, without `-k`. It returned `access_mode=tailscale`,
  `local_only=false` and a present process CSRF token.
- Deliberately spoofed `Tailscale-User-Login` headers were replaced by the
  Serve-authenticated identity. Foreign Host was rejected.
- Exact authenticated identity plus exact HTTPS Origin plus CSRF reached routing.
  Identity without CSRF was rejected; foreign Origin was rejected.
- CSRF sent directly to the loopback backend without Tailscale identity was
  rejected. Direct Tailscale-IP and WSL-IP access to port 8643 was unreachable.
- Production SQLite hash, approval-service PID/restart state and schema v9 were
  unchanged. The repository still contained only the reviewed repair and
  `git diff --check` passed.

Result: **PASS - CONTROLLED RUN 4 E REAL-TAILNET SECURITY SMOKE**.
Private tailnet hostname, login and CSRF values are intentionally not recorded.

### Final independent static source audit

After runtime validation, a fresh GPT-6 Astra independent **read-only** static
source audit returned **VERDICT: PASS**, with **0 BLOCKER, 0 HIGH, 0 MEDIUM and
0 LOW**. It changed no files and confirmed:

- Screening accounting is bound to injected `data_dir`; requests without free
  text do not construct `make_llm_generate`; actual free-text requests still use
  existing screening drafting. Schema remains v9 and grounding/review behavior
  is not weakened.
- The exact supported Tailscale login remains required. `Tailscale-User-Name`
  is not authority; duplicate login headers fail. Generic `X-Forwarded-*`
  headers and wildcard/suffix Host matching grant no authority.
- Foreign/HTTP mutation Origin is rejected in Tailscale mode. Identity cannot
  bypass CSRF, and CSRF cannot authenticate direct backend access. The supported
  authenticated CLI binds `127.0.0.1`; local and Tailscale modes remain distinct.
- Run 4 adds no weaker approval-domain path. Approval reads/actions initiate no
  Anthropic or Tavily operation, contact no employer and submit no application.
- The systemd unit launches only `approval-queue`, does not configure Serve/Funnel
  and embeds no private identity. All eight protected trusted-domain production
  files had empty diffs.

One **INFO** observation noted that the extension test module's autouse fixture
neutralizes dotenv/API-key influence but does not isolate every possible
unrelated ambient setting. The audit explicitly determined this does not
invalidate either regression assertion; it was not a defect finding.

### Final scope, trust assumptions and operational limitations

**A: COMPLETE. B: COMPLETE. C: COMPLETE. D: COMPLETE. E: COMPLETE.
Run 4: COMPLETE.** This means authenticated private Tailscale multi-device access
to the Job Pilot approval queue, preserving existing packet/approval/revision
safety boundaries. Runtime results above are tested observations in the configured
environment; static confirmations are source-audited behavior. Neither removes
the following trust assumptions or limitations:

- The backend binds only `127.0.0.1`. Serve is operator-managed; Funnel is not
  used or permitted for this deployment. Serve identity-header trust applies
  only behind the trusted local Serve proxy with this loopback-only backend.
  Exact configured tailnet Host and authorized login are required; generic
  forwarded headers grant no authority.
- CSRF and exact packet/view/current-evidence checks remain required. An equally
  privileged malicious local process remains inside the trusted-host boundary
  and can forge identity headers. This is not protection from a compromised
  local host. Existing filesystem/DB/cooperating-lock and point-in-time
  validation limitations remain.
- Tailscale/network configuration is not stored in the Job Pilot DB. Schema
  remains v9. Approval access does not automate employer submission.
- The persistent service runs **approval-queue only**. Revision processing stays
  independent/manual/on-demand; a Revise decision does not imply an automatically
  running revision worker. The service does not launch the normal scheduler.
- The user-level systemd approval service has been proven to return automatically
  after WSL itself shuts down and later starts. Windows boot automatically
  launching WSL has **not been proven** and remains a separate environment/
  operations concern. Keeping WSL alive indefinitely is also not established.
- Automated job submission, revision processing, Windows boot orchestration,
  the future UI redesign and the broader Job Pilot product/roadmap are not
  declared complete by this closeout.

This documentation-only closeout leaves the two reviewed repair files unchanged.
No runtime validation, private configuration inspection, database access, service
operation, commit or push is part of this pass. Stop for Andrew's review.
