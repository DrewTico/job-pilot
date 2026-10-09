# Job Pilot: Application Review Screen (UI Spec)

This spec describes the approved design for Job Pilot's main screen: the **Application Review** screen, where Andrew reviews one job's application packet and decides Approve & Apply, Revise, or Reject.

Reference files that come with this spec (keep them in `docs/design/`):
- `job-pilot-review-prototype.html`: the approved prototype ("Option D"). It opens in any browser and is fully clickable. Use it as the **exact reference for colors, spacing, copy and behavior**. Do not copy its code (it bundles a design-tool runtime); rebuild the screen properly in the real frontend stack.
- `screens/1-review.png` to `screens/9-all-caught-up.png`: screenshots of every state: default review, the score breakdown, the resume reader, comment mode, revise (ask and changes), after approving (next job plus toast), the People tab, and all caught up.

Where this spec and the screenshot disagree, **this spec wins**. A screenshot shows only one state; this spec describes all of them.

---

## 1. Goals (what the screen must achieve)

1. Within 3 to 5 seconds Andrew can see: **how well the job fits**, **whether the resume matches or needs a new version**, **interview chance**, **whether the right people and their emails were found**, **why it matches**, and **location plus relocation assistance**.
2. **Approve & Apply, Revise and Reject are always visible.** They must never require scrolling.
3. **Detail is visible, never buried.** The must-sees are on screen; everything else (full cover letter, full resume, screening answers, people, history) is one click away in the right panel.
4. The whole screen **fits in one 1440×900 desktop viewport** without page scrolling. Individual panels may scroll internally.
5. It must look like a premium, distinctive product, **not a console or admin panel**: dark navy, blue and teal, rich but uncluttered.

---

## 2. Stack mapping

Build in the planned frontend stack:
- **Next.js (App Router) + TypeScript**
- **shadcn/ui** for primitives (Button, Tabs, Dialog, Popover, Tooltip, Textarea, Input, Toast/Sonner)
- **Tremor** only if useful for the small bars; plain divs/SVG are fine and closer to the design
- **Magic UI**: at most the two touches named in section 9 (score ring draw-in and the "all caught up" check)
- Fonts via `next/font/google`

The existing FastAPI backend stays the backend. Section 12 maps every UI element to data, and flags what the backend does not provide yet.

---

## 3. Design tokens

### Colors

| Token | Value | Use |
|---|---|---|
| `bg` | `#070D1A` | App background |
| `bg-glow-1` | radial, `rgba(94,208,194,0.09)` at top right | Subtle teal glow. **Tinted per company** (see 3.4) |
| `bg-glow-2` | radial, `rgba(106,167,255,0.06)` at bottom left | Subtle blue glow |
| `surface-1` | `#0E1729` | Tiles, cards |
| `surface-2` | `#0B1424` | Right evidence panel |
| `surface-queue` | `rgba(10,17,32,0.6)` | Queue column |
| `surface-bar` | `rgba(9,15,29,0.92)` + `backdrop-filter: blur(12px)` | Bottom action bar |
| `border` | `rgba(148,163,184,0.09)` to `0.12` | All hairlines |
| `text-1` | `#EEF0F3` | Primary text |
| `text-2` | `#BFC8D4` | Strong secondary |
| `text-3` | `#A3AEC0` | Secondary |
| `text-4` | `#8E9AAF` | Labels, captions |
| `teal` | `#5ED0C2` | Primary accent, success, "ready" |
| `teal-light` | `#8FE6DA` | Accent text on dark |
| `link` | `#7FDCCF` | Links |
| `blue` | `#6AA7FF` | Secondary accent, home marker, follow-ups |
| `amber` | `#F0B45C` (text `#F6CF95`) | Needs attention, warnings, "no relocation" |
| `red` | `#F08074` (text `#F4A49B`) | Failed or closed only |

Rules: **color only where it means something.** Teal means good or ready, amber means needs you, red means failed, blue means informational. Never rely on color alone: every colored state also has an icon or text (✓, !, ?, ⌂).

### Typography

| Role | Font | Notes |
|---|---|---|
| Display: job title, score, tile values, section titles | **Bricolage Grotesque** (700 to 800, width ~88 to 92%) | Tight letter-spacing (-0.02 to -0.04em) |
| UI text | **Geist** (400/500/600) | Body 13 to 14.5px |
| Versions, fingerprints, emails, keyboard hints | **Geist Mono** | 10.5 to 12.5px |
| Reading cover letters | **Newsreader** (serif) | 16 to 17.5px, line-height ~1.7 |

Tile labels are 11px, weight 600, uppercase, letter-spacing 0.1em, `text-4`. Use tabular numerals for all numbers.

### Shape and depth

- Radii: hero 24px, tiles 18px, right panel 20px (top corners), queue cards 14px, buttons 13px, chips 15px (pill), logo tiles 11px (queue) / 16px (hero).
- Tiles get `inset 0 1px 0 rgba(255,255,255,0.03)` for a faint top highlight.
- The hero gets `0 20px 50px rgba(2,8,20,0.45)`; the primary button gets `0 8px 24px rgba(94,208,194,0.25)`.
- **No card-inside-card-inside-card.** At most one level of tiles on the page background.

### Per-company theming

Every job has a brand theme that recolors the hero gradient, its border, the score ring gradient, the logo tile and the background glow. The prototype's example themes:

| Company | Hero gradient (3 stops) | Ring | Logo tile |
|---|---|---|---|
| Northstar (teal) | `#0D2340 → #0D3446 → #0E4A49` | `#6AA7FF → #7FE3D5` | white `#F3F5F8`, navy mark |
| Atlas (indigo) | `#121A46 → #1A2566 → #273A86` | `#7FA0FF → #A9BEFF` | `#DDE3FF` |
| Meridian (purple) | `#1E1638 → #2B1F52 → #3A3172` | `#9F8BFF → #D3B6FF` | `#F0DDFB` |
| Harbor (copper) | `#2A1610 → #3E2216 → #5C331C` | `#FF9F6E → #FFC79A` | `#FBE9C8` |

In production, derive the theme from the company's brand color when known, otherwise pick deterministically from a fixed palette of these four plus a neutral navy. Keep text contrast at 4.5:1 or better over every gradient.

---

## 4. Layout (1440×900)

```
┌────┬──────────────┬──────────────────────────────────────────────────────┐
│Rail│ Queue        │ HERO (company, title, chips, score ring)             │
│64px│ 300px        ├───────────────────────────┬──────────────────────────┤
│    │              │ LEFT: must-sees           │ RIGHT: evidence panel    │
│    │              │ 2×2 tiles + Why/Watch     │ tabs + content           │
│    │              │ (flex 1 1 500px)          │ (flex 1 1 440px)         │
│    │              ├───────────────────────────┴──────────────────────────┤
│    │              │ ACTION BAR (always visible)                          │
└────┴──────────────┴──────────────────────────────────────────────────────┘
```

- The root is `height: 100vh` (minimum 820px), `overflow: hidden`. Only the queue list, the left pane and the right panel content scroll, internally.
- Main column padding: 18px top, 20px sides. Gap between hero, panes and bar: 14px.
- Scrollbars: thin, **invisible until hover** (`scrollbar-color: transparent` that becomes `rgba(148,163,184,0.28)` on hover; same for WebKit). The right panel's tab row never shows a scrollbar.
- Below 900px wide everything stacks and the page scrolls normally (mobile gets its own design later; see section 11).

---

## 5. Components

### 5.1 Icon rail (64px)

- Top: the Job Pilot logo mark (38px rounded square, teal-to-blue gradient, paper-plane glyph).
- Icons only, 44×44 hit areas, with tooltips and `aria-label`: Overview, Opportunities, **Applications (active)**, Contacts, Calendar, Analytics.
- Bottom: Settings and the profile avatar ("AC").
- Active item: teal icon on `rgba(94,208,194,0.12)`.

### 5.2 Review queue (300px)

**Header:**
- A search button: "Jump to a job or company" with a `Ctrl K` hint (opens the command palette, built later).
- Title "Ready for you" (Bricolage 19px) with "N of 8 done today" on the right.
- An **8-segment daily progress bar** (4px tall); completed segments are teal.

**Queue cards** (one per job, 14px radius). Grid: 40px logo tile | text | score.
- **Logo tile**: the company's brand color with its initial (or real logo when available).
- **Company** (14px, 600) and **title** (12.5px, wraps; never truncated).
- **Chip row:**
  - Location chip with a pin icon: "Austin · Hybrid", "Denver · On-site", "Remote · US".
  - Relocation chip, color-coded:
    - teal `✓ Relocation` / `✓ Housing stipend`
    - amber `! No relocation`
    - blue `⌂ Remote`
    - gray `? Relocation not stated`
- **Status line** with a 6px dot. Be specific: "Salary answer needed", "1 question: on-site 5 days?", "Ready to apply", "Tailoring resume · step 3 of 5", "Posting closed on Oct 8".
- **Progress bar** (4px, blue-to-teal) only while Job Pilot is still preparing the packet.
- **Note line** (11.5px, `text-4`): deadline or context, e.g. "Closes tomorrow", "No deadline listed", "Ready for review in about 10 minutes", "Removed automatically. Nothing was sent."
- **Score** on the right: Bricolage 22px with a tiny "FIT" label.

**Card states:**

| State | Look | Clickable |
|---|---|---|
| Selected | Teal-to-blue tinted background, teal border, teal score | n/a |
| Ready / needs you | Normal | Yes |
| Preparing | Muted score, hollow dot, progress bar | No |
| Failed / closed | Muted, red status | No |
| Applied | 60% opacity, "Applied just now", note "Follow-up reminder set" | No |
| Passed (rejected) | 60% opacity, "Passed", note "Hidden from future searches" | No |

**Footer:** "Next discovery · 1:00 PM" plus a shortcut legend (`A approve  R revise  X reject  J/K move`).

### 5.3 Hero (selected job)

A 24px-radius panel with the **company's brand gradient**, plus decorative SVG behind the content (pointer-events off):
- 6 faint concentric topographic ellipses at the right side (`rgba(255,255,255,0.075)`, 1px).
- A dotted "flight path" curve ending in a small dot, in the ring color.
- The decoration drifts slowly (translateX 0 to -24px, 14s, alternate). Disable with reduced motion.

**Left side:**
- 58px logo tile.
- Line 1: **Company** (600) · sector and size, e.g. "Lab instruments and analysis software · 400 people".
- **Job title**: Bricolage 40px, 700.
- Chips (30px pills, max 4):
  1. Location: "Austin, TX · Hybrid, 3 days"
  2. **Relocation**, always present and color-coded: teal "✓ Relocation assistance offered", amber "! No relocation assistance", neutral "⌂ Remote, no move needed"
  3. Level: "Entry level · New grad"
  4. Deadline (amber, clock icon) when one exists: "Closes Sun, Oct 12"

**Right side: the score block** (a button that opens "Why this score?"):
- A 112px ring: 8px stroke, a gradient in the brand's ring colors, filled to `score/100` of the circumference, starting at 12 o'clock. It draws in on load.
- The number in the center (Bricolage 42px, 800) with a "FIT" caption.
- To its right: the fit label ("Great fit" / "Strong fit" / "Good fit") in the ring's light color, a rank ("Best match in your queue"), "8 of 9 requirements met", and "Why this score ⌄".

### 5.4 "Why this score?" popover

- Opens below the score block (shadcn Popover). It is 360px wide and closes with ✕, Esc or clicking the score again.
- It shows 4 rows, each with a label, its weight, the value, a gradient bar and a one-line reason:
  - Skills match (40%): "Python, APIs, LLM apps, RAG all present"
  - Experience (30%)
  - Education (15%)
  - Location and move (15%)
- Footer note: "Scored against your facts.yaml with rubric v3. Nothing outside your real experience counts."

### 5.5 Left pane: the must-see tiles (2×2 grid, 12px gap)

Each tile is `surface-1`, 18px radius, 16 to 18px padding, with an uppercase label, a big Bricolage value (26px) and a small visual.

**1. Resume match**
- Value: "Strong" / "Good". Link at top right: "Open v6" (opens the document reader on the resume).
- Visual: **9 small squares**, one per core requirement. Teal = met, half amber = partial, gray = missing.
- Footer: teal "✓ No new resume needed", or amber "! A v7 with more Go could help".

**2. Interview chance**
- Value: "High" / "Medium" / "Low".
- Visual: a **5-segment meter** that fills with a blue-to-teal gradient (`#6AA7FF #63B6EA #60C3D6 #5ED0C2`).
- Footer: a one-line reason: "Strong fit, fresh posting, recruiter reachable".

**3. Right people**
- Value: "2 found" with "1 of 2 emails verified" beside it. Link: "View emails" (opens the People tab).
- **One row per person:** a 34px avatar (initials on a gradient) with a ✓ (teal) or ? (amber) badge; name; short role; an email chip "✓ Email" (teal) or "? Email" (amber).
- If fewer than 2 people were found, add a dashed placeholder row: "Looking for the hiring manager · Job Pilot checks again tonight".

**4. Location**
- Header right: the city name.
- Visual: a **dot-matrix map of the contiguous US** (see section 8), with a blue home dot at Cutler Bay and a curved dashed teal flight path to the job city, marked with a teal dot and label.
- Remote jobs: no path; a larger ring around home labeled "Remote, from home".
- Footer: distance plus relocation, colored by relocation status: "About 1,110 miles · relocation package offered" (teal) / "About 1,720 miles · you would pay for the move" (amber) / "Fully remote · no move or relocation needed".

**Below the tiles, the "Why it matches / Watch out" card**, in two columns:
- **Why it matches** (teal label): 3 items with teal ✓.
- **Watch out** (amber label): 2 items with amber !.

### 5.6 Right panel: evidence (tabs)

Tabs (13.5px, a 2px teal underline when active): **Package · Cover letter · Resume · Screening (badge if a question needs you) · People · History**. The default tab is **Package**.

**Package**
- A checklist of 4 clickable rows, each opening its tab: Resume, Cover letter, Screening questions, Outreach contacts.
  - Each row: a 34px status icon (teal ✓ or amber !), name, detail line ("157 words · lint passed"), and a state word on the right ("Ready" / "Answer" / "Could improve"). Rows that need attention get a faint amber background.
- **"Coming up": a 7-day calendar strip** (Thu 9 to Wed 15). Each day is a 62px tile with weekday, date and a colored dot:
  - teal = today (tile also gets a teal-to-blue gradient and border)
  - amber = posting closes
  - blue = follow-up with a contact
- Under it, an agenda list: "Today · Review and apply", "Sun 12 · Posting closes", "Tue 14 · Follow up with Sarah Chen".

**Cover letter**
- Meta line: "157 words · lint passed · traced to facts.yaml" and an **"Open full view"** button.
- The full letter in Newsreader serif.

**Resume**
- Meta line and an "Open full view" button.
- A paper-style preview (`#F6F4EE` background, dark text) with **tailored lines highlighted** in soft teal.

**Screening**
- If a question needs Andrew, an amber card at the top shows the question, a note ("Job Pilot never guesses pay. Your answer is saved for next time."), an input with a label, and a "Save" button.
- Below it, all answered questions as label/answer rows.

**People**
- One card per contact: avatar, name, a relevance pill ("High relevance" teal / "Likely team match" blue), the role, the **email in Geist Mono** with "✓ verified" or "? pattern guess", and a one-line reason why this person matters.
- Footer: "Outreach is drafted after you approve. Nothing is sent without you."

**History**
- A vertical timeline: a teal dot and line for each completed step, and a hollow dot for "Awaiting your review · Now".
- Steps: Job discovered on FreeHire, Scored N, Company research completed, Resume v6 tailored, Packet v2 generated.

### 5.7 Action bar (always visible)

- Pinned at the bottom of the main column, full width, translucent with blur.
- Left: a shield icon, "**Reviewing packet v2 · {Company}**", and under it "Exact version only · N more waiting".
- Right, in order:
  1. **Reject**: ghost button, `X` key hint
  2. **Revise**: secondary button (`#14213A`, hairline border), `R` hint
  3. **Approve & Apply**: primary; teal gradient `#6FD8CB → #5EC4E0`, dark text `#04161A`, 700 weight, glow shadow; `A` hint
- All buttons are 46px tall (comfortable touch targets) and show their keyboard hint in a small `kbd`.

The bar's labels change with the mode (section 6.3).

### 5.8 Document reader (full view)

- A full-screen overlay over the app: dimmed and blurred backdrop (`rgba(4,8,18,0.72)` + blur 10px).
- Top bar: company logo tile, document title ("Cover letter" / "Resume"), "{Company} · {Title}", a version pill ("packet v2 · current"), then **Comment** (toggle), **Download PDF**, and **✕** (Esc).
- Center: the document on a **paper page** (`#F7F5EF`, up to 720px wide, 56/64px padding, deep shadow).
  - Letter in Newsreader 17.5px with a date line.
  - Resume with Education, Experience (tailored lines highlighted and tagged "TAILORED"), and Skills.
- Right sidebar (300px): **Revision notes**.

**Comment mode (highlight and comment):**
1. Turn on **Comment**. Paragraphs become clickable and get a soft hover highlight.
2. Clicking a paragraph selects it (teal tint plus a 3px left inset bar). The sidebar shows the quote, a textarea ("What should change here?") and **Add note**.
3. Notes collect in the sidebar list with their quotes. Paragraphs that already have a note get a faint amber tint.
4. **"Revise with these notes"** closes the reader and opens the Revise panel with the notes attached.

---

## 6. Flows and states

### 6.1 Selecting a job

Clicking a reviewable queue card (or pressing J/K) selects it. The **hero theme, ring, all four tiles, the map, the right panel and the action bar update** to that job. The tab resets to Package, and the revise, popover and reader states close.

### 6.2 Approve & Apply / Reject

1. Record the decision for the **exact packet version shown** (section 12, Safety).
2. Show a **toast** centered near the top:
   - Approve: teal ✓, "Applied to {Company}. Submit link opened, follow-up scheduled."
   - Reject: gray, "Passed on {Company}."
   - Both have **Undo** and ✕.
3. Mark the queue card Applied or Passed (dimmed, no longer clickable).
4. **Automatically select the next pending job.**
5. When no pending jobs remain, show **All caught up** (6.5).

Undo restores the decision and reselects that job. It must cancel any follow-up actions that have not happened yet.

### 6.3 Revise (simple flow)

| Step | Right panel shows | Bar title / subtitle | Secondary | Primary |
|---|---|---|---|---|
| 0 Review | Tabs | "Reviewing packet v2 · Co" / "Exact version only · N more waiting" | Revise (R) | Approve & Apply (A) |
| 1 Ask | "What should Job Pilot change?" textarea, any notes from the reader, optional chips (Shorter cover letter, Stronger resume match, Address the gaps, More confident tone), "Job Pilot remembers your notes, so future packets need fewer fixes." | "Revising packet v2" / "Nothing changes until you approve" | Cancel (Esc) | **Fix it** (Enter) |
| 2 Result | **"Here's what changed" v2 → v3**: old text struck through in red, new text highlighted in teal, word count change, resume +/− lines, "Fit score unchanged at N. Nothing is sent until you approve v3." | "Packet v3 is ready" / "Review it before anything is sent" | Undo (Esc) | **Review v3** (Enter) → back to review on the new version, Cover letter tab |

The Reject button is hidden during steps 1 and 2.

### 6.4 "Why this score?"

Toggled by clicking the score block. See 5.4.

### 6.5 All caught up

Replaces the hero, panes and bar:
- A 132px animated check: a circle draws in, then the check stroke draws.
- "**You're all caught up**" (Bricolage 48px, 800).
- "N applied and M passed today. Job Pilot looks for new roles at 1:00 PM."
- Four stat cards (Mercury style): Applied this week · Average fit · Follow-ups set · **Days to Dec 31** (highlighted with a teal-to-blue gradient).
- **Goal track**: a bar from "Sep 27 · build started" to "Goal: signed offer by Dec 31", filled to today with a white marker, and "Day X of 95" under it.

---

## 7. Keyboard

Shortcuts are active when focus is inside the app and **not** in an input or textarea.

| Key | Action |
|---|---|
| `A` | Approve & Apply (review mode only) |
| `R` | Open Revise |
| `X` | Reject |
| `J` / `K` | Next / previous pending job |
| `Enter` | Revise step 1 → Fix it; step 2 → Review v3 |
| `Esc` | Close the reader, then the popover, then Revise (in that order) |
| `Ctrl K` | Command palette (later) |

A and X are high-impact. Require a short confirm pattern, or rely on the Undo toast; **never** submit to an employer directly from a keypress (section 12).

---

## 8. The US map (Location tile)

- SVG with `viewBox="0 0 190 102"`, rendered about 108px tall.
- Projection used for every point: **x = (lon + 125) × 3.2, y = (49 − lat) × 4**.
- The outline is a simplified contiguous-US polygon (the exact `d` path is in `job-pilot-review-prototype.html`; search for `M1,2.4` and copy it). Draw it twice:
  1. Fill `rgba(148,163,184,0.06)`, stroke `rgba(170,190,215,0.30)` at 0.6
  2. A **dot pattern** fill: 3.2-unit grid, dot radius 0.62, `rgba(170,190,215,0.42)`. This gives the dot-matrix look.
- **Home**, Cutler Bay (lon -80.35, lat 25.58) → (142.9, 93.7): a blue dot (r 2.6) and a ring (r 5; r 9 for remote). Label "Cutler Bay" at (138, 100.5), right-aligned, below and left of the dot, so the path never crosses it.
- **Destination**: a teal dot (r 3.2) and ring (r 7), with the city label placed on the side the path does not come from. Each city defines its own label offset and anchor.
- **Flight path**: a quadratic curve from home to destination. Control point = midpoint + perpendicular × 0.22 × distance, using the perpendicular that points up (negative y). Dashed teal, 1.3 stroke, `2.4 2.4` dash.
- City coordinates should come from a small static lookup (or geocoding cached once). Never call a map service from the UI.

---

## 9. Motion

All motion respects `prefers-reduced-motion: reduce` (no animation).

| Element | Animation |
|---|---|
| Score ring | stroke-dashoffset draws in, 1.2s, `cubic-bezier(.2,.7,.2,1)` (**Magic UI touch #1**) |
| Hero content, tab content | fade and rise 8px, 0.38s ease-out |
| Popover, toast, reader page | scale 0.96 → 1 and rise, 0.28s |
| Bars (interview meter, why-score bars, queue progress, goal track) | grow from the left, 0.9s |
| Hero topography | slow drift, 14s alternate, infinite |
| All caught up | circle draws (0.7s), then the check (0.5s, 0.35s delay) (**Magic UI touch #2**) |
| Queue cards | 0.25s background, border and opacity transitions on state change |

No other decorative animation.

---

## 10. Accessibility

- Real `<button>`, `<a>`, `<input>` and `<label>` everywhere. Icon-only buttons get `aria-label` and a tooltip.
- Tabs use `role="tablist"` / `role="tab"` with `aria-selected`. The queue uses `aria-current` for the selected job and `aria-disabled` for jobs that can't be clicked.
- Toggles (Comment, revise chips) use `aria-pressed`. The score button uses `aria-expanded`.
- The toast uses `role="status"`. The reader is a modal dialog with focus trapped and returned on close.
- Text contrast is 4.5:1 or better, including over every company gradient. Hit areas are at least 44px.
- Visible focus ring: a 2px `#7FDCCF` outline with 2px offset.

---

## 11. Out of scope for this screen (later)

- The **Overview** dashboard (Mercury-style stats, the December 31 tracker) and the **command palette** (Ctrl K).
- The **phone version** is designed (section 13) but should be built after the desktop screen works.
- A compact queue mode for long queues (show only the selected card in full).

---

## 12. Data contract and safety

### 12.1 What each element needs

TypeScript shape for one reviewable job. Fields marked **NEW** do not exist in the backend yet. Do not invent values for them: render an "unknown" or "not available yet" state until the backend provides them, and propose the backend changes as their own bounded slices.

```ts
type Relocation = "offered" | "not_offered" | "remote" | "unknown";

interface ReviewJob {
  id: string;                       // canonical job id
  company: string;
  companySector?: string;           // NEW (company research)
  companySize?: string;             // NEW
  brand?: { gradient: [string, string, string]; ring: [string, string]; logoBg: string; logoFg: string; logoUrl?: string }; // NEW (or derived)
  title: string;
  level: string;                    // "Entry level", "Internship"...
  location: { city?: string; region?: string; mode: "remote" | "hybrid" | "onsite"; lat?: number; lon?: number };
  relocation: Relocation;           // from FreeHire relocation + posting text
  relocationDetail?: string;        // "Housing stipend"
  closesAt?: string;                // NEW if not stored
  fit: {
    score: number;                  // existing scoring (threshold 65)
    label: string;                  // derived from score
    reasons: string[];              // existing "fit reasons" → Why it matches
    gaps: string[];                 // existing "gaps" → Watch out
    requirementsMet: number;        // NEW unless scorer returns it
    requirementsTotal: number;      // NEW
    breakdown?: { label: string; weight: number; value: number; note: string }[]; // NEW: add to the scoring contract
    rankInQueue: number;            // derived
  };
  resume: { version: string; match: "strong" | "good" | "weak"; needsNewVersion: boolean; note: string; tailoredLines: string[] };
  interview?: { level: "high" | "medium" | "low"; segments: 1|2|3|4|5; reason: string }; // NEW (needs a defined, honest method)
  people?: { name: string; role: string; email?: string; emailVerified: boolean; relevance: string; why: string }[]; // NEW (M3 outreach)
  packet: { version: string; fingerprint: string; coverLetter: string; wordCount: number; lintPassed: boolean };
  screening: { answered: { q: string; a: string }[]; needsUser?: { q: string; note: string; hint: string } };
  history: { label: string; at: string; done: boolean }[];   // existing packet/approval history
  status: "ready" | "needs_you" | "preparing" | "failed" | "applied" | "passed";
  statusDetail: string;             // "Tailoring resume · step 3 of 5"
  progress?: number;                // 0 to 100 while preparing
}
```

### 12.2 Safety rules (non-negotiable, same as the existing approval core)

- **Approve, Reject and Revise act on the exact packet version and view fingerprint on screen.** Send the existing CSRF token and fingerprints. If the packet changed underneath, show a "This packet changed, review the new version" state instead of approving.
- **"Approve & Apply" does not auto-submit to employers** in M1. It records the approval and then opens the manual submit link, which is what the toast says.
- Undo must only reverse things that have not left the machine yet.
- Nothing is ever sent to a contact from this screen. Outreach is drafted only after approval and needs its own approval.
- Screening questions that need Andrew (salary, on-site commitment, availability) are **never auto-answered**. Saved answers go to the answer bank.
- Revision notes are saved verbatim as revision intent and style memory. They can never add facts that are not in `facts.yaml`.
- The screen keeps working behind the existing Tailscale-only, authenticated boundary. No new public endpoints, no third-party calls from the browser, and no remote fonts beyond `next/font` self-hosting.

### 12.3 Suggested build order (one bounded Codex slice each)

1. Next.js app shell, design tokens, fonts, rail, queue (static data), action bar
2. Hero, score ring, the four tiles and Why/Watch, wired to real scoring and packet data; unknown states for NEW fields
3. Right panel tabs with real packet content; document reader (read mode, PDF download)
4. Approve / Reject / Revise wired to the existing approval API, with the toast, undo, auto-advance and all caught up
5. Keyboard shortcuts, motion, accessibility pass, reduced motion
6. Comment mode in the reader, plus revise notes into revision intent and style memory
7. Backend slices for the NEW fields (score breakdown, interview chance, contacts, relocation and deadline normalization, company theme), one at a time

---

## 13. Phone version

Reference: `job-pilot-phone-prototype.html` (opens in any browser; best viewed at phone width or on a phone) and `screens/phone/`.

Same tokens, fonts, colors, company themes, data and safety rules as desktop. The pattern is **one job at a time** (Copilot Money review queue, Things 3 feel), with details in **bottom sheets** instead of side panels. Designed at 390×844; must work from 360 to 480px wide. All touch targets are at least 44px; inputs use 16px text so iOS does not zoom.

### 13.1 Screens

**Queue (home)**
- Date line, then "Ready for you" (Bricolage 34px) and the profile avatar.
- A progress card (teal-to-blue tint): "N of 8 reviewed today", "N waiting", an 8-segment bar, and "83 days to your December 31 goal".
- Job cards (20px radius): logo tile, company, title, location chip, relocation chip, a specific status, a progress bar while preparing, a note line, and a big score at the right. Same states as desktop section 5.2.
- Bottom tab bar: Overview · **Review** · People · Calendar.

**Review (one job)**
- Top bar: "‹ Queue", "1 of 4", "Next ›".
- Hero card in the company's gradient with the topographic decoration: logo, company and sector, title (Bricolage 29px), chips (location, relocation, deadline), and a tappable score panel (84px ring, fit label, "8 of 9 requirements met", "Why this score ›").
- A 2×2 grid of must-see tiles: Resume (9 squares; tap opens the resume), Interview (5 segments), Right people (avatar stack with ✓/? badges, "2 found", "View emails ›"), Location (the dot-matrix US map with the flight path).
- Why it matches / Watch out card.
- Application package list (60px rows: Resume, Cover letter, Screening, Contacts), each opening its sheet.
- Coming up: the 7-day strip plus agenda.
- **Sticky action bar**, always visible above a strong fade: "Reviewing packet v2 · exact version only", then a 54px round **Reject** (✕), **Revise**, and a full-width **Approve & Apply**.

**Bottom sheets** (slide up, 26px top radius, grabber, title, subtitle and a 44px close button; tap the dimmed backdrop to close):
- Why N? (score breakdown), Cover letter (paper style, serif), Resume (paper style, tailored lines highlighted), Screening (the question that needs Andrew at the top), Right people (contact cards with full emails).
- Revise: textarea, optional chips, a full-width **Fix it** → "Here's what changed" (struck-through old text, highlighted new text, resume +/−) → **Review v3** (opens the new cover letter) or **Undo**.

**Applied / Passed confirmation** (full screen): an animated check with a pulse ring, "Applied to {Company}", "Submit link opened. Follow-up reminder set.", **Next: {next company}**, and **Undo**.

**All caught up**: the same content as desktop section 6.5, stacked (2×2 stat cards, goal track, replay).

### 13.2 Phone-specific rules

- Never show desktop keyboard hints on phone.
- Sheets trap focus and close with the backdrop, the ✕ button, or a swipe down (when built).
- Swipe gestures (right to approve, left to pass) are optional later; the buttons must always exist, and a swipe must go through the same confirmation and undo.
- Respect safe areas (`env(safe-area-inset-bottom)`) under the action bar and tab bar.
