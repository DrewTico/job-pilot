# Run 5B bounded self-hosted typography

October 9, 2026. Desktop typography packaging only. Stopping for Andrew's visual review. No commit, push, deployment, Run 5C, phone composition, production workflow, or design-reference edit.

## Checkpoint

Read `CLAUDE.md` first. Branch `main`, HEAD and `origin/main` both matched `3245f796f2d7931012f8a3c883526a0d15ba9bc9`. Preserved the intentionally dirty accepted Run 5B implementation. Starting status, name-only diff, stat, and protected-file hashes are recorded in `font-packaging-evidence/baseline.json`. No reset, clean, stash, restore, checkout, or discard.

Applied the local `frontend-design-pro` skill for the role assignment and visual inspection. The user's explicit authorization for exact pinned Fontsource packages governs this slice. Approved spec, prototype, and reference remain unchanged; the current accepted composition remains the baseline.

## A. Font provenance

Existing package.json, lockfile, node_modules, Next assets, export scripts, manifest loader, CSP, and browser fixtures were inspected. Next 16.4.0's internal development tooling contains Geist/Geist Mono binaries; Bricolage and Newsreader were absent. Those internal binaries were not reused. Fontsource supplies explicit family/license metadata, source attribution, license text, npm integrity records, and local WOFF2 files. Its documented [package installation workflow](https://fontsource.org/docs/getting-started/install) supports bundling fonts with the app.

| Family | Exact npm package | Version | License | Selected package asset |
| --- | --- | --- | --- | --- |
| Bricolage Grotesque | `@fontsource-variable/bricolage-grotesque` | 5.3.0 | OFL-1.1 | `files/bricolage-grotesque-latin-wght-normal.woff2` |
| Geist | `@fontsource-variable/geist` | 5.3.0 | OFL-1.1 | `files/geist-latin-wght-normal.woff2` |
| Geist Mono | `@fontsource/geist-mono` | 5.3.0 | OFL-1.1 | `files/geist-mono-latin-400-normal.woff2` |
| Newsreader | `@fontsource/newsreader` | 5.3.0 | OFL-1.1 | `files/newsreader-latin-400-normal.woff2` |

Verified npm package metadata and archive contents before using them. All four archives include explicit matching family metadata and SIL Open Font License 1.1 text. Exact npm tarball locations, lockfile SHA-512 integrity, family metadata, asset SHA-256 and byte size are in `font-packaging-evidence/font-provenance.json`.

Copyright holders: Bricolage Grotesque Project Authors (2022), Geist Project Authors (2024) for both Geist families, and Newsreader Project Authors (2020). Full notices and licenses are retained under `frontend/font-licenses/` and also preserved as license comments in the emitted manifest-hashed CSS. The distributed UI package therefore carries the licenses without another served file type or route.

Only four dependency entries were added, each exactly pinned, using npm with lifecycle scripts disabled. No unrelated dependencies. No scraping, font CDN download, unofficial mirror, browser-copied binary, next/font/google, inline binary, data URL, blob font, runtime JS loader, or third-party browser font service.

## B. Font payload

All files are upright Latin WOFF2. No italics, duplicate static/variable copies, extended-Latin files, other subsets, or unused distribution files enter the UI package.

Paths below are relative to `/ui/_next/static/media/`:

| Emitted file | CSS weight/range | Bytes |
| --- | --- | ---: |
| `bricolage-grotesque-latin-wght-normal.3e340e57.woff2` | 700–800 | 41,344 |
| `geist-latin-wght-normal.9ff55a8a.woff2` | 400–600 | 29,400 |
| `geist-mono-latin-400-normal.d4363d9d.woff2` | 400 | 9,864 |
| `newsreader-latin-400-normal.40164bd1.woff2` | 400 | 22,480 |
| **Total** | | **103,088** |

The upstream weight-variable binaries retain their supplied axes (Bricolage 200–800, Geist 100–900); CSS exposes only the role ranges actually used. No binary modification or custom font subsetting. The Bricolage weight-only variable file is smaller than the combined static 700 and 800 files (44,228 bytes). Its larger multi-axis file is not packaged. Geist uses one variable file for 400/500/600. Newsreader 500 and Mono 500 are not needed.

Static `@font-face` declarations in `frontend/src/styles/fonts.css` use the exact family names, normal style, correct weight/range, local bundled WOFF2 URL, and `font-display: swap`. `--display`, `--ui`, `--mono`, and `--reading` retain consistent role assignment. Display weights are 700/800; UI weights are 400/500/600. General section headings use UI; the hero, queue heading, score, fit label, major values, and empty heading use display. Technical fingerprints and identifiers use Mono. Cover text and the full reader use Newsreader 400.

## C. CSP

Previous: `font-src 'none'`

Final: `font-src 'self'`

The exact CSP regression compares the entire policy with the previous string after that single replacement. No other directive relaxed:

```text
default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self';
img-src 'none'; font-src 'self'; object-src 'none'; frame-src 'none';
worker-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none';
```

No unsafe-inline, unsafe-eval, data, blob, or external origin introduced. Security headers, authentication and trusted decision semantics remain frozen.

## D. Bounded delivery

The exporter follows only local font URLs in packaged CSS, validates their paths/WOFF2 header/length, and adds exact entries with SHA-256, byte size and `font/woff2`. It does not scan arbitrary media or create a static mount. It rejects symlink assets and parents.

Font paths must exactly match:

```text
_next/static/media/{one of the four selected Latin font basenames}.{8 lowercase hex characters}.woff2
```

No additional directories, basenames, extensions, query strings, or unlisted request paths. Python preserves exact manifest lookup and an immutable verified in-memory snapshot. Missing/corrupt/undeclared CSS font references disable the complete `/ui` package; the trusted root remains available.

Additional bounds: **100,000 bytes per font**, **250,000 aggregate font bytes**. Existing restrictions stay at **4,000,000 bytes per other asset**, **15,000,000 bytes per package**, **500 entries**, and **100,000-byte manifest**. WOFF2 receives explicit `font/woff2` with existing nosniff/no-store headers. No TTF/OTF/WOFF or generic binary type is permitted.

Next automatically emits a redundant same-origin preconnect tag for CSS font imports. Packaging removes only that exact generated tag before applying the unchanged strict HTML validator. All other unexpected links still fail, and script/style policy was not widened.

Final package: **17 assets**, **726,813 asset bytes**, including the four fonts and license-bearing CSS. Atomic package replacement and snapshot behavior remain intact.

## E. Font security tests

The final combined suite passed **129 tests**: **36 font delivery/security tests**, **2 font browser tests**, and **91 existing delivery/CSP/DOM/trusted-UI tests**, with no failed or skipped tests.

Focused checks cover successful approved WOFF2 delivery; all disallowed extensions; unknown/invalid/nested/absolute/traversal paths; font and parent symlinks; corrupt bytes, hash, signature, header length, MIME and missing files; undeclared CSS references; individual/aggregate font bounds and existing total package bounds; same-origin CSS; immutable startup snapshot; physically present undeclared fonts remaining inaccessible; query and path restrictions; GET-only behavior; missing/corrupt frontend disabling only `/ui`; minimal licensed production payload; and exactly one CSP directive replacement.

No old assertion removed or weakened. Existing DOM test captures now write only to the new evidence directory, preserving the pre-font evidence.

## F. Real-browser proof

Viewport **1440×900**, headless Chromium, real Python-delivered exported UI, isolated existing synthetic/demo data. No mock HTML or production records.

| Element | Computed first family | Computed weight |
| --- | --- | --- |
| Hero job title | Bricolage Grotesque | 700 |
| Ready for you | Bricolage Grotesque | 700 |
| Fit score | Bricolage Grotesque | 800 |
| Normal UI / queue title | Geist | 400 |
| Company line | Geist | 600 |
| DEMO | Geist | 500 |
| Great fit / major value | Bricolage Grotesque | 700 |
| Technical fingerprint | Geist Mono | 400 |
| Cover text and full reader | Newsreader | 400 |

Computed stacks retain ordinary fallback faces, but the proof also requires nonempty loaded FontFaceSet entries, `document.fonts.check`, loaded readiness, and Chromium `CSS.getPlatformFontsForNode` custom-font glyph usage. Blocking Bricolage leaves the CSS family name intact but triggers proof failure, explicitly checking against silent fallback.

Chromium internal family names: `Bricolage Grotesque 96pt ExtraBold`, `Geist`, `Geist Mono`, and `Newsreader 16pt 16pt`; all are custom fonts with actual glyph counts. Computed CSS family names match the approved roles.

**Third-party browser requests: 0. Third-party font requests: 0. CSP violations: 0.** All four requested fonts returned 200 under the same test origin's `/ui/_next/static/media/` paths. `font-packaging-evidence/browser-proof.json` records computed styles, FontFaceSet data, glyph resolution, metrics and every request.

## G. Deterministic builds

Ran the existing `npm run build` twice from equivalent final frontend source state. Both optimized static builds and packages succeeded. Source hashes are checked before/after. Manifest bytes, all asset filenames, SHA-256 hashes, sizes, types, and four font entries are identical. Every current packaged byte hash matches its manifest entry.

Both manifest SHA-256 values:

```text
2fd53f777b9d8654ede7a4f8910649ef94ba0cf2d5d493b7d1396d0ecbc15bb9
```

Evidence: `manifest-build-1.json`, `manifest-build-2.json`, `build-1.log`, `build-2.log`, `build-1-source-hashes.json`, and `deterministic-build.json`. No nondeterminism waiver.

## H. Newly run validation

From `frontend/`:

```sh
npm run lint
npm run typecheck
npm test
npm audit --json --cache /tmp/job-pilot-font-npm-cache --fetch-retries=0 --fetch-timeout=10000
npm run build
npm run build
```

Lint/typecheck: exit 0. Frontend/export-policy tests: **11 passed**, zero failed/skipped. Audit: **0 vulnerabilities**, 253 reported dependencies. Two final builds: exit 0, each 17 packaged assets.

From repository root, final delivery/CSP/font/browser/trusted-UI suite:

```sh
.venv/bin/pytest -q tests/test_frontend_fonts.py tests/test_frontend_font_dom.py tests/test_frontend_delivery.py tests/test_frontend_proof.py tests/test_frontend_ui_dom.py tests/test_approval_ui_dom.py
```

**129 passed in 79.20 seconds**, zero failed/skipped. Log: `font-packaging-evidence/frontend-security-browser.log`.

Relevant safety regressions:

```sh
.venv/bin/pytest -q tests/test_approval_security.py tests/test_tailscale_security.py tests/test_tailscale_api.py tests/test_approval_api.py tests/test_approval_service_unit.py tests/test_approval_queue.py tests/test_database.py tests/test_approvals.py tests/test_packets.py tests/test_packet_history.py tests/test_packet_chaos.py tests/test_revisions.py tests/test_apply_handoff.py tests/test_apply_submit.py tests/test_apply_review.py tests/test_apply_screening.py tests/test_application_state.py tests/test_application_import.py tests/test_apply_tracker.py tests/test_scoring.py
```

**1,544 passed in 362.22 seconds**, zero failed/skipped. Log: `font-packaging-evidence/regressions.log`.

Earlier focused completed checks: 71 font/delivery tests before the final production-license test; 2 desktop composition captures; 2 browser font tests. Counts overlap the final suite and are not added again.

Sandbox limitations were handled through the established outside-sandbox execution path. Registry DNS was blocked; Next's sandboxed TypeScript worker could not return parsable output; sandboxed local ASGI requests timed out; sandboxed Node tests reported wrappers only. Final outside-sandbox commands give the real pass counts above. An initial exporter rejection revealed Next's redundant preconnect tag and its actual eight-character media hash shape; these were resolved with exact bounded rules, retaining strict validation. No security/test workaround or assertion weakening.

## I. Database and frozen boundaries

Production `data/job_pilot.sqlite3` is guarded by a temporary byte snapshot, never opened as a writable test DB. Tests use existing temporary SQLite fixtures. No production workflow was started.

**Production DB byte-identical after every build, test and capture.** Size: **241,664 bytes**. Before/after SHA-256: `da1796bc37cd43868ed999c89a4f11c1c65bad7c1ce671f8d15552d7526994e2`. The 249-file baseline guard confirms exactly the ten scoped source/config/test files changed; all other baseline files, including protected design, earlier evidence, business/backend/data files, remain unchanged. New files are the font CSS/licenses, focused tests, and review evidence/report. Details: `font-packaging-evidence/verification.json`.

No business route, DTO, schema, scoring, packet/approval/revision semantics, DB behavior, Tailscale/systemd/auth, Host/identity/Origin validation, CSRF behavior, GET-only UI access, or trusted decision handoff changed. No fabricated capability/data. No file under `docs/design/` or the pre-font evidence directory changed.

## J. Visual comparison

- Approved reference: `docs/design/screens/1-review.png`.
- Pre-font accepted baseline: `docs/run5b/premium-polish-evidence/review-1440x900.png`.
- Post-font real UI: `docs/run5b/font-packaging-evidence/review-1440x900.png`.
- Viewport: **1440×900**.

Actually inspected all three screenshots, the full Newsreader reader, and company/dock detail captures. The post-font UI has a clearer display hierarchy and more distinctive hero/score/tile forms. Geist gives the company line, queue names/titles, tabs, labels, badges and handoff a consistent, closer-to-reference character. Newsreader improves the document reading surface. This is a clear perceptual improvement over the system substitutes; Andrew retains visual acceptance authority.

Rechecked DEMO, location chips, Packet ready, manual badges, queue section navigation, evidence tabs, FIT caption, tile labels, primary button and dock DEMO for baseline/centering/padding/border/cap-height/icon alignment. **No optical geometry corrections needed or made.** All accepted size, padding, gap, line-height, radius, border, color and layout rules remain unchanged. Font-role weight normalization is the only change beyond font-family assignment.

Measured hero, content-pane, dock, queue navigation and FIT-caption rectangles match the pre-font snapshot. Natural glyph width/wrapping changes are visible in badges and body text; all content and handoff remain reachable under the existing scrolling model. `font-packaging-evidence/optical-comparison.json` records the comparison. No broad restyling or dedicated mobile layout.

## K. Phone

PHONE DESIGN NOT IMPLEMENTED IN THIS PASS

## L. Git

Final `git status --short`:

```text
 M .gitignore
 M src/job_agent/dashboard/approval_app.py
 M src/job_agent/dashboard/approval_security.py
?? RUN_5B_IMPLEMENTATION_REPORT.md
?? docs/
?? frontend/
?? job-pilot-design-updated.zip
?? job-pilot-design-updated.zip:Zone.Identifier
?? job-pilot-design.zip
?? job-pilot-design.zip:Zone.Identifier
?? src/job_agent/dashboard/frontend_delivery.py
?? tests/test_frontend_delivery.py
?? tests/test_frontend_font_dom.py
?? tests/test_frontend_fonts.py
?? tests/test_frontend_proof.py
?? tests/test_frontend_ui_dom.py
```

Branch `main`, HEAD and `origin/main` remain at the required checkpoint. Existing dirty work is preserved. No rule or build-brief architecture edit.

`git diff --check`: exit 0, no output.

NO COMMIT
NO PUSH

## M. Review checkpoint

VERDICT: READY FOR ANDREW DESKTOP VISUAL REVIEW
