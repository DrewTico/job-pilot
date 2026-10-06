# Run 4 Milestone A: application authentication boundary

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
