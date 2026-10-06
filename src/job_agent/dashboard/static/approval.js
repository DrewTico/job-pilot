"use strict";
(() => {
  const state = {csrf: null, section: "needs-review", offset: 0, selected: null,
    detail: null, epoch: 0, queueEpoch: 0, ready: false, submitting: false, timer: null};
  const $ = id => document.getElementById(id);
  const names = {"needs-review": "Needs Review", processing: "Processing", "needs-attention": "Needs Attention", history: "History"};
  const auth = {not_approved: "Not approved", currently_valid: "Approved, currently valid",
    evidence_changed: "Approved historically; current evidence changed", integrity_failed: "Approved historically; packet integrity needs review",
    not_checked: "Current authorization not checked"};
  const errors = {stale_packet: "Packet changed. Review the refreshed packet before approving.",
    stale_approval_view: "Packet changed. Review the refreshed packet before approving.",
    decision_conflict: "This exact packet already has a different decision. Review its recorded decision.",
    packet_integrity_failed: "Packet integrity needs review. Approval is unavailable.",
    packet_busy: "Packet generation is busy. Try again when it finishes.", csrf_failed: "Session changed. Reload the page before deciding.",
    invalid_request: "Check the required fields and character limits.", approval_not_current: "Historical approval is no longer current. Review is required."};
  const say = text => { $("status").textContent = text; };
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function button(text, fn, cls) {
    const node = el("button", text, cls); node.type = "button"; node.addEventListener("click", fn); return node;
  }
  function idOK(id) { return typeof id === "string" && /^[a-f0-9]{32}$/.test(id); }
  function packetPath(id) { if (!idOK(id)) throw new Error("invalid_request"); return `/api/packets/${id}`; }
  function safeURL(value) {
    if (typeof value !== "string" || /[\s\x00-\x1f\x7f]/u.test(value)) return null;
    try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? value : null; }
    catch { return null; }
  }
  function externalLink(label, value) {
    if (!safeURL(value)) return el("span", `${label} (URL unavailable)`);
    const link = el("a", label); link.href = value; link.target = "_blank"; link.rel = "noopener noreferrer"; return link;
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {cache: "no-store", credentials: "same-origin", ...options});
    let data; try { data = await response.json(); } catch { throw new Error("unavailable"); }
    if (!response.ok) throw new Error(data && data.error && errors[data.error.code] ? data.error.code : "unavailable");
    return data;
  }
  async function bootstrap() { state.csrf = null; const data = await api("/api/bootstrap"); state.csrf = data.csrf_token; }
  function stopPolling() { if (state.timer !== null) clearTimeout(state.timer); state.timer = null; }
  function invalidate() {
    state.ready = false; stopPolling();
    for (const node of $("detail").querySelectorAll("[data-action]")) node.disabled = true;
    const link = $("manual-application"); if (link) { link.removeAttribute("href"); link.setAttribute("aria-disabled", "true"); }
  }
  function current(d) { return state.ready && state.detail === d && state.selected === d.packet_id && !state.submitting && !d.decision; }
  function canApprove(d) {
    const p = d.approval_preview;
    return current(d) && d.integrity === "passed" && p && p.packet_id === d.packet_id && p.packet_version === d.version &&
      p.expected_packet_fingerprint === d.expected_packet_fingerprint && typeof p.expected_approval_view_fingerprint === "string";
  }
  async function loadQueue() {
    const epoch = ++state.queueEpoch;
    try {
      const data = await api(`/api/queue?section=${state.section}&limit=25&offset=${state.offset}`);
      if (epoch !== state.queueEpoch) return;
      $("queue").replaceChildren(); $("queue-heading").textContent = names[state.section];
      for (const item of data.items) {
        if (!idOK(item.packet_id)) continue;
        const li = el("li"), card = button("", () => loadDetail(item.packet_id), "queue-card");
        card.setAttribute("aria-current", item.packet_id === state.selected ? "true" : "false");
        card.append(el("strong", item.company), el("span", item.title), el("span", item.location || "Location not retained"),
          el("span", `Score ${item.score} / Tier ${item.tier} / v${item.version}`, "card-meta"), el("span", `Ready: ${item.ready_at || "Not ready"}`),
          el("span", `Cover accepted: ${item.cover_letter_acceptance} / Manual needed: ${item.manual_needed_count}`),
          el("span", `Decision: ${item.decision || "None"}${item.revision_state ? ` / Revision: ${item.revision_state}` : ""}`), el("span", "Integrity: Not checked"));
        li.append(card); $("queue").append(li);
      }
      if (!data.items.length) $("queue").append(el("li", "No packets in this section."));
      $("previous").disabled = state.offset === 0; $("next").disabled = data.items.length < 25;
    } catch (error) { say(errors[error.message] || "Queue unavailable. Reload to try again."); }
  }
  function section(parent, title, content) {
    const node = el("section", null, "review-section"); node.append(el("h3", title)); if (content) node.append(content); parent.append(node); return node;
  }
  function list(parent, title, items) {
    if (!items.length) return;
    const node = section(parent, title), ul = el("ul"); for (const text of items) ul.append(el("li", text)); node.append(ul);
  }
  function renderRevision(parent, revision) {
    parent.replaceChildren(el("h3", "Revision status"), el("p", revision.label));
    if (revision.updated_at) parent.append(el("p", `Updated: ${revision.updated_at}`));
    if (revision.failure_category) parent.append(el("p", `Attention category: ${revision.failure_category}`));
    if (revision.successor_packet_id && idOK(revision.successor_packet_id)) parent.append(
      el("p", `Successor v${revision.successor_version}: ${revision.successor_status}. Requires its own approval.`),
      button(`Open successor v${revision.successor_version}`, () => loadDetail(revision.successor_packet_id)));
  }
  function pollRevision(d, epoch) {
    stopPolling();
    if (!["queued", "pending", "style_prepared", "style_persisted", "building"].includes(d.revision.state)) return;
    state.timer = setTimeout(async () => {
      if (epoch !== state.epoch || state.selected !== d.packet_id) return;
      try {
        const revision = await api(`${packetPath(d.packet_id)}/revision-status`);
        if (epoch !== state.epoch) return;
        d.revision = revision; renderRevision($("revision"), revision); say(revision.label); pollRevision(d, epoch);
      } catch { say("Revision status unavailable. Refresh this exact packet to try again."); }
    }, 5000);
  }
  function renderHistory(parent, d, epoch) {
    const disclosure = el("details"); disclosure.append(el("summary", "History and diffs (informational, not approval)"));
    const ul = el("ul", null, "history");
    for (const item of d.history) {
      const li = el("li"); li.append(button(`Open v${item.version}`, () => loadDetail(item.packet_id)),
        el("span", `${item.status} / Decision: ${item.decision || "None"} / ${item.lineage_kind}`),
        el("span", `Ready: ${item.ready_at || "Not ready"}${item.is_latest_allocated ? " / Latest allocated" : ""}${item.is_latest_ready ? " / Latest ready" : ""}`)); ul.append(li);
    }
    const label = el("label", "Compare this version with"); label.htmlFor = "diff-version";
    const select = el("select"); select.id = "diff-version";
    for (const item of d.history) if (item.packet_id !== d.packet_id && idOK(item.packet_id)) {
      const option = el("option", `v${item.version} / ${item.status}`); option.value = item.packet_id; select.append(option);
    }
    const output = el("pre", "Select a version to compare.", "diff"); output.tabIndex = 0; output.setAttribute("aria-label", "Packet diff");
    const controls = el("div", null, "action-row");
    for (const kind of ["resume", "cover"]) {
      const compare = button(`Compare ${kind}`, async () => {
        if (!idOK(select.value)) return;
        output.textContent = "Loading authenticated historical diff.";
        try {
          const result = await api(`${packetPath(d.packet_id)}/diff/${kind}/${select.value}`);
          if (epoch !== state.epoch) return;
          output.textContent = result.status === "available" ? result.diff || "No changes." : `Diff ${result.status}. Historical content is not reconstructed.`;
        } catch { output.textContent = "Diff unavailable. No current approval is implied."; }
      }); compare.disabled = !select.options.length; controls.append(compare);
    }
    disclosure.append(ul, label, select, controls, output); parent.append(disclosure);
  }
  function renderDestination(parent, d, epoch) {
    const container = section(parent, "Application destination review"), value = d.application_destination;
    container.append(el("p", value.domain ? `Domain: ${value.domain}` : "Destination unavailable."), el("p", value.url || "A valid exact preview is required.", "url"));
    const status = el("p", auth[value.authorization] || "Current authorization not checked"); container.append(status);
    if (d.decision !== "approve") { container.append(el("p", "Review only. Manual application opens only after a currently valid approval.")); return; }
    const link = el("a", "Open manual application", "button-link"); link.id = "manual-application";
    link.target = "_blank"; link.rel = "noopener noreferrer"; link.setAttribute("aria-disabled", "true");
    const check = button("Check application validity", async () => {
      link.removeAttribute("href"); link.setAttribute("aria-disabled", "true");
      try {
        const result = await api(`${packetPath(d.packet_id)}/application-destination`);
        if (epoch !== state.epoch) return;
        status.textContent = auth[result.authorization] || "Current authorization not checked";
        if (result.authorization === "currently_valid" && safeURL(result.url)) { link.href = result.url; link.setAttribute("aria-disabled", "false"); }
      } catch (error) { status.textContent = errors[error.message] || "Current authorization not checked"; }
    });
    async function navigate(event) {
      event.preventDefault();
      if (!link.hasAttribute("href") || epoch !== state.epoch || !state.ready) return;
      link.removeAttribute("href"); link.setAttribute("aria-disabled", "true");
      try {
        // Revalidate on every explicit click. Historical approval is not authority.
        const result = await api(`${packetPath(d.packet_id)}/application-destination`);
        if (epoch !== state.epoch) return;
        status.textContent = auth[result.authorization] || "Current authorization not checked";
        if (result.authorization === "currently_valid" && safeURL(result.url)) window.open(result.url, "_blank", "noopener,noreferrer");
      } catch (error) { status.textContent = errors[error.message] || "Current authorization not checked"; }
    }
    link.addEventListener("click", navigate); link.addEventListener("auxclick", navigate);
    link.addEventListener("contextmenu", event => event.preventDefault()); container.append(check, link);
  }
  function renderActions(parent, d, epoch) {
    const area = section(parent, "Exact-version decision"); area.id = "actions";
    area.append(el("p", `${d.company} / ${d.title} / v${d.version}`));
    if (d.decision) {
      area.append(el("p", `Recorded decision: ${d.decision}. Decisions cannot be edited.`));
      const content = el("div"); area.append(content);
      api(`${packetPath(d.packet_id)}/decision-detail`).then(result => {
        if (epoch !== state.epoch) return;
        content.append(el("p", `Decision time: ${result.created_at}`));
        if (result.reason_code) content.append(el("p", `Reason: ${result.reason_code}`));
        if (result.detail !== null) content.append(el("p", result.detail, "prose"));
        if (result.feedback !== null) content.append(el("p", result.feedback, "prose"));
      }).catch(() => { content.textContent = "Decision detail unavailable."; }); return;
    }
    const row = el("div", null, "action-row"), panel = el("div"); panel.id = "confirmation";
    for (const action of ["approve", "revise", "reject"]) {
      const control = button(action[0].toUpperCase() + action.slice(1), () => confirm(action, d, panel), action === "approve" ? "primary" : action === "reject" ? "destructive" : "");
      control.dataset.action = action; control.disabled = action === "approve" ? !canApprove(d) : !current(d); row.append(control);
    }
    area.append(row, panel); if (!canApprove(d)) area.append(el("p", "Approve requires a successful exact-version integrity preview."));
  }
  function confirm(action, d, panel) {
    if (!current(d) || (action === "approve" && !canApprove(d))) return;
    panel.replaceChildren(); panel.className = "confirmation";
    const heading = el("h4", `${action[0].toUpperCase() + action.slice(1)} ${d.company} / ${d.title} / v${d.version}?`); heading.tabIndex = -1;
    panel.append(heading); heading.focus();
    let field, reason;
    const fieldError = el("p", "", "field-error"); fieldError.id = "decision-error"; fieldError.setAttribute("role", "status");
    if (action === "revise" || action === "reject") {
      if (action === "revise") panel.append(el("p", "This creates a new packet version. The current packet remains unchanged. The new version must be reviewed and approved separately."));
      if (action === "reject") {
        const label = el("label", "Reason (required)"); label.htmlFor = "reject-reason";
        reason = el("select"); reason.id = "reject-reason"; reason.required = true; reason.setAttribute("aria-describedby", fieldError.id);
        for (const [code, name] of [["", "Choose a reason"], ["not_interested", "Not interested"], ["bad_fit", "Poor fit"], ["company", "Company concern"], ["location", "Location"], ["pay", "Compensation"], ["other", "Other"]]) {
          const option = el("option", name); option.value = code; reason.append(option);
        } panel.append(label, reason);
      }
      const label = el("label", action === "revise" ? "Revision feedback (required)" : "Detail (optional)"); label.htmlFor = "decision-text";
      field = el("textarea"); field.id = "decision-text"; field.maxLength = 4000; field.rows = 5; field.required = action === "revise";
      field.setAttribute("aria-describedby", "character-count decision-error");
      const counter = el("p", "0 / 4000 characters used. 4000 remaining."); counter.id = "character-count";
      const count = () => { const used = Array.from(field.value).length; counter.textContent = `${used} / 4000 characters used. ${4000 - used} remaining.`; };
      field.addEventListener("input", count);
      function insertExact(text) {
        const next = field.value.slice(0, field.selectionStart) + text + field.value.slice(field.selectionEnd);
        if (Array.from(next).length > 4000) { fieldError.textContent = "At most 4000 Unicode characters. Text was not truncated."; return; }
        field.setRangeText(text, field.selectionStart, field.selectionEnd, "end"); count();
      }
      // Native maxlength counts UTF-16 units. Keep the attribute while preserving
      // full codepoint-counted paste/astral input; never silently truncate feedback.
      field.addEventListener("paste", event => { event.preventDefault(); insertExact(event.clipboardData.getData("text/plain")); });
      field.addEventListener("beforeinput", event => {
        if (!event.isComposing && typeof event.data === "string" && event.inputType.startsWith("insert") && /[\uD800-\uDBFF]/u.test(field.value + event.data)) {
          event.preventDefault(); insertExact(event.data);
        }
      });
      panel.append(label, field, counter);
    }
    panel.append(fieldError); const controls = el("div", null, "action-row");
    const submit = button(`Confirm ${action}`, async () => {
      if (!current(d) || (action === "approve" && !canApprove(d))) return;
      fieldError.textContent = "";
      if (reason) reason.removeAttribute("aria-invalid"); if (field) field.removeAttribute("aria-invalid");
      if (reason && !reason.value) { fieldError.textContent = "Choose a reason."; reason.setAttribute("aria-invalid", "true"); reason.focus(); return; }
      if (field && (Array.from(field.value).length > 4000 || (action === "revise" && !field.value.trim()))) {
        fieldError.textContent = "Use nonblank feedback of at most 4000 characters."; field.setAttribute("aria-invalid", "true"); field.focus(); return;
      }
      const body = {expected_packet_fingerprint: d.expected_packet_fingerprint};
      if (action === "approve") body.expected_approval_view_fingerprint = d.approval_preview.expected_approval_view_fingerprint;
      if (action === "reject") { body.reason_code = reason.value; body.detail = field.value; }
      if (action === "revise") body.feedback = field.value;
      const epoch = state.epoch; state.submitting = true; invalidate();
      try {
        const result = await api(`${packetPath(d.packet_id)}/${action}`, {method: "POST", headers: {"Content-Type": "application/json", "X-Job-Pilot-CSRF": state.csrf}, body: JSON.stringify(body)});
        const notice = result.message || `Recorded ${action} for ${d.company} / ${d.title} / v${d.version}. ${auth[result.current_authorization] || "Current authorization not checked"}.`;
        say(notice); state.submitting = false; loadQueue(); if (epoch === state.epoch) await loadDetail(d.packet_id, notice);
      } catch (error) {
        state.submitting = false; const notice = errors[error.message] || "Decision response unavailable. Refresh this exact packet to check its recorded decision."; say(notice);
        if (error.message === "csrf_failed") { state.csrf = null; fieldError.textContent = notice; return; }
        if (epoch === state.epoch && ["stale_packet", "stale_approval_view", "decision_conflict"].includes(error.message)) await loadDetail(d.packet_id, notice);
        else fieldError.textContent = notice;
      }
    }); submit.dataset.action = action;
    controls.append(submit, button("Cancel", () => {
      panel.replaceChildren(); panel.className = ""; const original = $("detail").querySelector(`[data-action="${action}"]`); if (original) original.focus();
    })); panel.append(controls);
  }
  function renderDetail(d, epoch) {
    const article = $("detail"); article.replaceChildren();
    const heading = el("h2", `${d.company} / ${d.title}`); heading.id = "packet-heading"; heading.tabIndex = -1;
    article.append(heading, el("p", `Exact packet v${d.version}`, "version"), el("p", `Score ${d.score} / Tier ${d.tier} / ${d.location || "Location not retained"} / ${d.status}`),
      el("p", `Integrity: ${d.integrity === "passed" ? "Passed" : d.integrity === "failed" ? "Needs review" : "Not checked"}`), el("p", auth[d.current_authorization] || "Current authorization not checked"));
    const jump = el("a", "Go to exact-version decision"); jump.href = "#actions"; article.append(jump);
    list(article, "Match reasons", d.reasons); list(article, "Matched requirements", d.matched_requirements); list(article, "Missing requirements", d.missing_requirements);
    renderDestination(article, d, epoch);
    const resume = section(article, "Resume");
    if (d.artifacts.some(item => item.kind === "resume_pdf" && item.available)) {
      const link = el("a", `Open resume PDF / v${d.version}`, "button-link"); link.href = `${packetPath(d.packet_id)}/artifacts/resume.pdf`; link.target = "_blank"; link.rel = "noopener noreferrer"; resume.append(link);
    } else resume.append(el("p", "Resume unavailable."));
    const cover = section(article, "Cover letter", el("p", d.cover_text === null ? `Cover ${d.cover_integrity}.` : d.cover_text, "prose")); cover.append(el("p", `Employer accepts cover letters: ${d.cover_letter_acceptance}`));
    const screening = section(article, "Screening answers and manual-needed questions");
    for (const answer of d.screening.answers) {
      const disclosure = el("details"); disclosure.append(el("summary", answer.question), el("p", String(answer.answer), "prose")); screening.append(disclosure);
    }
    for (const question of d.screening.manual_needed) screening.append(el("p", `Manual needed: ${question}`, "manual-needed"));
    if (!d.screening.answers.length && !d.screening.manual_needed.length) screening.append(el("p", "No packet-required screening questions."));
    screening.append(el("p", "If the application asks a new question not represented here, stop and return to Job Pilot rather than inventing an answer."));
    const facts = section(article, "Packet-bound company facts");
    for (const fact of d.company_facts) { const item = el("div", null, "fact"); item.append(el("p", fact.text), externalLink(fact.source_title || "Source", fact.source_url)); facts.append(item); }
    renderHistory(article, d, epoch);
    const revision = section(article, "Revision status"); revision.id = "revision"; revision.setAttribute("aria-live", "polite"); renderRevision(revision, d.revision);
    renderActions(article, d, epoch); heading.focus();
  }
  async function loadDetail(id, notice) {
    if (!idOK(id)) return;
    invalidate(); const epoch = ++state.epoch; state.selected = id; state.detail = null;
    document.body.classList.add("view-detail"); $("refresh").disabled = false; $("detail").replaceChildren(el("h2", "Loading exact packet."));
    try {
      const d = await api(packetPath(id)); if (epoch !== state.epoch || state.selected !== id) return;
      if (d.packet_id !== id) throw new Error("stale_packet");
      state.detail = d; state.ready = Boolean(state.csrf) && !state.submitting;
      renderDetail(d, epoch); pollRevision(d, epoch); say(notice || `Review ${d.company} / ${d.title} / v${d.version}.`); loadQueue();
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.ready = false; $("detail").replaceChildren(el("h2", "Exact packet unavailable."), el("p", errors[error.message] || "Refresh to try again.")); say(errors[error.message] || "Packet unavailable.");
    }
  }
  $("sections").addEventListener("click", event => {
    const control = event.target.closest("button[data-section]"); if (!control) return;
    invalidate(); ++state.epoch; state.selected = null; state.detail = null; state.section = control.dataset.section; state.offset = 0;
    document.body.classList.remove("view-detail"); $("refresh").disabled = true; $("detail").replaceChildren(el("h2", "Select a packet to review"));
    for (const node of $("sections").querySelectorAll("button")) node.setAttribute("aria-pressed", String(node === control)); loadQueue();
  });
  $("previous").addEventListener("click", () => { state.offset = Math.max(0, state.offset - 25); loadQueue(); });
  $("next").addEventListener("click", () => { state.offset += 25; loadQueue(); });
  $("back").addEventListener("click", () => { invalidate(); ++state.epoch; document.body.classList.remove("view-detail"); state.detail = null; $("queue-heading").tabIndex = -1; $("queue-heading").focus(); });
  $("refresh").addEventListener("click", async () => { try { if (!state.csrf) await bootstrap(); if (state.selected) await loadDetail(state.selected); } catch { say("Session unavailable. Reload the page."); } });
  window.addEventListener("pagehide", invalidate);
  window.addEventListener("pageshow", async () => {
    invalidate(); ++state.epoch;
    try { await bootstrap(); await loadQueue(); if (state.selected) await loadDetail(state.selected); else say("Select an exact packet to review."); }
    catch { say("Session unavailable. Reload the page."); }
  });
})();
