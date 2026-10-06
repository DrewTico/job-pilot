"""Approval UI: static sandbox checks + offline actual loopback Chromium tests.

Browser tests require the established outside-sandbox approval gate. All browser
resources are confined to the assigned loopback server origin. External links
are inspected/intercepted, never actually navigated.
"""
import copy
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest

from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_service import ApprovalQueueService
from test_approvals import ready
from test_packets import setup

STATIC = Path(__file__).resolve().parents[1] / "src/job_agent/dashboard/static"


def test_static_no_html_execution_storage_or_remote_assets():
    js = (STATIC / "approval.js").read_text()
    html = (STATIC / "approval.html").read_text()
    css = (STATIC / "approval.css").read_text()
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                      "localStorage", "sessionStorage", "indexedDB", "serviceWorker"):
        assert forbidden not in js
    assert "textContent" in js and "createElement" in js
    for forbidden in ("http://", "https://", "<iframe", "<embed", "<object", "<img", "<style", "@import", "url("):
        assert forbidden not in html + css
    assert '<script src="/assets/approval.js" defer>' in html
    assert "unsafe-inline" not in html + css + js
    assert "prefetch" not in html + js and "prerender" not in html + js


def test_static_accessible_shell_and_codepoint_counter():
    html = (STATIC / "approval.html").read_text()
    js = (STATIC / "approval.js").read_text()
    css = (STATIC / "approval.css").read_text()
    assert 'lang="en"' in html and 'aria-live="polite"' in html
    assert "Array.from(field.value).length" in js and "field.maxLength = 4000" in js
    assert "pagehide" in js and "pageshow" in js
    assert ":focus-visible" in css and "prefers-reduced-motion" in css
    assert "min-height: 44px" in css and "white-space: pre-wrap" in css


def test_static_mode_neutral_title_banner_and_csrf_bootstrap():
    html = (STATIC / "approval.html").read_text()
    js = (STATIC / "approval.js").read_text()
    assert "<title>Job Pilot approval queue</title>" in html
    assert "Local only" not in html and "Tailnet only" not in html
    assert '<p id="access-mode">Loading access mode.' in html
    assert 'state.csrf = null;\n    const data = await api("/api/bootstrap");\n    state.csrf = data.csrf_token;' in js


@pytest.mark.parametrize("data,label", [
    ({"local_only": True, "origin": "http://127.0.0.1:8643"}, "Local only"),
    ({"local_only": False, "access_mode": "tailscale"}, "Tailnet only"),
])
def test_browser_bootstrap_access_mode_and_csrf(ui, ready, data, label):
    from playwright.sync_api import expect
    ui[3]["/api/bootstrap"] = {**data, "csrf_token": "test-bootstrap-token"}
    ui[3][f"/api/packets/{ready[2].id}/approve"] = (403, {"error": {"code": "csrf_failed"}})
    open_packet(ui, ready)
    page = ui[0]
    assert page.title() == "Job Pilot approval queue"
    expect(page.locator("#access-mode")).to_have_text(
        f"{label}. Review and decide on one exact packet version.")
    page.get_by_role("button", name="Approve", exact=True).click()
    page.get_by_role("button", name="Confirm approve", exact=True).click()
    expect(page.locator("#status")).to_have_text("Session changed. Reload the page before deciding.")
    assert ui[4][0][2]["x-job-pilot-csrf"] == "test-bootstrap-token"


def test_browser_failed_bootstrap_keeps_neutral_banner_and_stops_queue(ui):
    from playwright.sync_api import expect
    ui[3]["/api/bootstrap"] = (403, {"error": {"code": "csrf_failed"}})
    page = ui[0]; page.goto(ui[2])
    expect(page.locator("#status")).to_have_text("Session unavailable. Reload the page.")
    expect(page.locator("#access-mode")).to_have_text(
        "Loading access mode. Review and decide on one exact packet version.")
    assert not any("/api/queue" in url for url in ui[5])
    assert not ui[4]


@pytest.fixture
def loopback_server(ready, monkeypatch):
    """Test-only real Uvicorn; socket allocation supplies the app's actual port."""
    import uvicorn
    builder = ready[1]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    application = create_approval_app(engine=builder.engine, settings=builder.settings, port=port)
    config = uvicorn.Config(application, host="127.0.0.1", port=port, proxy_headers=False,
        forwarded_allow_ips="", access_log=False, log_level="critical", lifespan="on")
    server = uvicorn.Server(config)
    errors = []
    def run():
        try: server.run(sockets=[sock])
        except BaseException as exc: errors.append(type(exc).__name__)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline: time.sleep(.01)
    assert server.started and not errors, "test-only loopback server failed to start"
    def forbidden(*args, **kwargs): raise AssertionError("provider or employer call from approval browser fixture")
    for path in ("anthropic.Anthropic.__init__", "job_agent.tavily_research.TavilyCompanyResearcher.__init__",
        "job_agent.tavily_research.TavilyCompanyResearcher.research", "httpx.Client.send", "httpx.AsyncClient.send",
        "job_agent.revisions.RevisionProcessor.process_revision", "job_agent.packets.PacketService.build_one"):
        monkeypatch.setattr(path, forbidden)
    # Uvicorn only accepts connections. Browser/driver transport stays in its
    # own process; any Python-side outbound socket/DNS call is a test failure.
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    try: yield f"http://127.0.0.1:{port}", application
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()
        assert not thread.is_alive() and not errors


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def ui(browser, loopback_server):
    origin, _ = loopback_server
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    external, overrides, posted, requests, script_errors = [], {}, [], [], []
    def route_request(route):
        req = route.request
        parsed = urlsplit(req.url)
        if f"{parsed.scheme}://{parsed.netloc}" != origin:
            external.append(req.url); route.abort(); return
        requests.append(req.url)
        if req.method == "POST": posted.append((parsed.path, req.post_data_json, req.headers))
        value = overrides.get(parsed.path)
        if value is not None:
            result = value(req) if callable(value) else value
            status, data = result if isinstance(result, tuple) else (200, result)
            route.fulfill(status=status, json=data); return
        route.continue_()
    context.route("**/*", route_request)
    page = context.new_page(); page.on("pageerror", lambda error: script_errors.append(str(error)))
    try: yield page, context, origin, overrides, posted, requests
    finally:
        context.close()
        assert not external, "browser attempted a non-loopback resource"
        assert not script_errors, "approval UI emitted a JavaScript error"


def open_packet(ui, ready):
    from playwright.sync_api import expect
    page, _, origin, _, _, _ = ui
    page.goto(origin)
    expect(page.locator(".queue-card")).to_have_count(1)
    page.locator(".queue-card").click()
    expect(page.locator("#packet-heading")).to_have_text("Acme / Engineer")
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_enabled()


def detail_json(ready):
    return ApprovalQueueService(ready[0].engine, ready[1].settings).detail(ready[2].id).model_dump()


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)], ids=["desktop", "phone"])
def test_browser_responsive_exact_review_and_confirmation(ui, ready, size):
    from playwright.sync_api import expect
    page = ui[0]; page.set_viewport_size({"width": size[0], "height": size[1]})
    open_packet(ui, ready)
    expect(page.locator(".version")).to_have_text("Exact packet v1")
    page.get_by_role("button", name="Approve", exact=True).click()
    expect(page.locator("#confirmation h4")).to_have_text("Approve Acme / Engineer / v1?")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for box in page.locator("#confirmation button").all(): assert box.bounding_box()["height"] >= 44
    assert page.evaluate("document.activeElement.tagName") == "H4"
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_focused()
    # Enlarged text must remain usable without clipping or page overflow.
    page.evaluate("document.documentElement.style.fontSize = '200%'")
    assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == "32px"
    page.get_by_role("button", name="Revise", exact=True).click()
    expect(page.get_by_label("Revision feedback (required)")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Cancel", exact=True).click()
    if size[0] == 390:
        page.get_by_role("button", name="Back to queue").click()
        expect(page.locator("#queue-pane")).to_be_visible()
        expect(page.locator("#detail-pane")).not_to_be_visible()


def test_browser_xss_text_and_unsafe_urls_remain_inert(ui, ready):
    from playwright.sync_api import expect
    data = detail_json(ready)
    attack = '<img src="https://evil.example/x" onerror="window.pwned=1"><script>window.pwned=1</script>'
    data.update(company=attack, title="LongTitle" * 80, cover_text=attack, reasons=[attack], location="LongLocation" * 80)
    data["company_facts"] = [{"text": attack, "source_title": attack, "source_url": "javascript:window.pwned=1"}]
    data["screening"] = {"answers": [{"question": attack, "answer": attack}], "manual_needed": [attack]}
    ui[3][f"/api/packets/{ready[2].id}"] = data
    page = ui[0]; page.set_viewport_size({"width": 390, "height": 844}); page.goto(ui[2])
    page.locator(".queue-card").click()
    expect(page.locator("#packet-heading")).to_contain_text(attack)
    assert page.locator("#detail img, #detail script, #detail iframe, #detail object").count() == 0
    assert page.locator('a[href^="javascript:"]').count() == 0
    assert page.evaluate("window.pwned === undefined")
    page.get_by_role("button", name="Revise", exact=True).click()
    expect(page.locator("#confirmation h4")).to_contain_text(attack)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_browser_unicode_counter_labels_and_verbatim_revise(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    page.get_by_role("button", name="Revise", exact=True).click()
    feedback = "😀é\n  Exact feedback  "
    page.get_by_label("Revision feedback (required)").fill(feedback)
    expect(page.locator("#character-count")).to_contain_text(f"{len(feedback)} / 4000")
    expect(page.locator("#decision-text")).to_have_attribute("maxlength", "4000")
    page.get_by_role("button", name="Confirm revise", exact=True).click()
    expect(page.locator("#status")).to_have_text("Creates a new packet version. The new version needs its own approval.")
    expect(page.locator("#revision")).to_contain_text("Revision queued; awaiting worker")
    assert ui[4][0][1] == {"expected_packet_fingerprint": ready[2].fingerprint, "feedback": feedback}
    assert ui[4][0][2].get("x-job-pilot-csrf")
    assert page.evaluate("localStorage.length === 0 && sessionStorage.length === 0")


def test_browser_reject_reason_field_error_and_exact_mapping(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    page.get_by_role("button", name="Reject", exact=True).click()
    page.get_by_role("button", name="Confirm reject", exact=True).click()
    expect(page.locator("#decision-error")).to_have_text("Choose a reason.")
    expect(page.get_by_label("Reason (required)")).to_be_focused()
    page.get_by_label("Reason (required)").select_option("pay")
    page.get_by_label("Detail (optional)").fill(" Exact compensation concern ")
    page.get_by_role("button", name="Confirm reject", exact=True).click()
    expect(page.locator("#actions")).to_contain_text("Recorded decision: reject")
    assert ui[4][0][1]["reason_code"] == "pay"
    assert ui[4][0][1]["detail"] == " Exact compensation concern "


def test_browser_approve_requires_exact_retained_tokens(ui, ready):
    from playwright.sync_api import expect
    expected = detail_json(ready)["approval_preview"]
    open_packet(ui, ready); page = ui[0]
    page.get_by_role("button", name="Approve", exact=True).click()
    assert not ui[4]
    page.get_by_role("button", name="Confirm approve", exact=True).click()
    expect(page.locator("#actions")).to_contain_text("Recorded decision: approve")
    assert ui[4][0][1] == {"expected_packet_fingerprint": expected["expected_packet_fingerprint"],
        "expected_approval_view_fingerprint": expected["expected_approval_view_fingerprint"]}
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "true")


def test_browser_stale_view_refresh_requires_new_explicit_click(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    path = f"/api/packets/{ready[2].id}/approve"
    ui[3][path] = (409, {"error": {"code": "stale_approval_view"}})
    page.get_by_role("button", name="Approve", exact=True).click()
    page.get_by_role("button", name="Confirm approve", exact=True).click()
    expect(page.locator("#status")).to_have_text("Packet changed. Review the refreshed packet before approving.")
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_enabled()
    assert len(ui[4]) == 1 and page.locator("#confirmation button").count() == 0
    page.wait_for_timeout(100); assert len(ui[4]) == 1


def test_browser_pageshow_invalidates_and_refetches_before_action(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    page.get_by_role("button", name="Approve", exact=True).click()
    previous = len([url for url in ui[5] if url.endswith(ready[2].id)])
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true})); window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_enabled()
    assert len([url for url in ui[5] if url.endswith(ready[2].id)]) > previous
    assert page.locator("#confirmation button").count() == 0 and not ui[4]


def test_browser_manual_destination_revalidated_on_click_no_external_navigation(ui, ready):
    from playwright.sync_api import expect
    service, _, p, _, _ = ready
    preview = service.preview_approval(p.id, p.fingerprint)
    service.approve(p.id, p.fingerprint, preview.approval_view_fingerprint)
    page = ui[0]; page.goto(ui[2]); page.get_by_role("button", name="History", exact=True).click()
    expect(page.locator(".queue-card")).to_have_count(1); page.locator(".queue-card").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "true")
    page.get_by_role("button", name="Check application validity").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "false")
    page.evaluate("() => { window.jobPilotTestNavigations = []; window.open = (...args) => { window.jobPilotTestNavigations.push(args); return null; }; }")
    path = f"/api/packets/{p.id}/application-destination"
    ui[3][path] = {"url": "https://example.com/changed", "domain": "example.com", "authorization": "evidence_changed"}
    page.locator("#manual-application").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "true")
    expect(page.locator("#detail")).to_contain_text("Approved historically; current evidence changed")
    assert page.evaluate("window.jobPilotTestNavigations") == []


def test_browser_pdf_explicit_local_new_tab_link_and_response(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    link = page.get_by_role("link", name="Open resume PDF / v1")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    path = f"/api/packets/{ready[2].id}/artifacts/resume.pdf"
    with page.expect_popup() as popup:
        link.click()
    tab = popup.value
    # Headless Chromium commits its PDF viewer without an ordinary page load.
    tab.wait_for_load_state("commit")
    assert any(url.endswith(path) for url in ui[5])
    response = ui[1].request.get(ui[2] + path)
    assert response.ok and response.headers["content-type"] == "application/pdf"
    assert response.body() == (ready[4] / "packets" / ready[2].id / "resume.pdf").read_bytes()


def test_browser_history_diff_scroll_and_poll_stops_terminal(ui, ready):
    from playwright.sync_api import expect
    data = detail_json(ready); successor = "2" * 32
    data["history"].append({**data["history"][0], "packet_id": successor, "version": 2})
    data["decision"] = "revise"; data["approval_preview"] = None
    data["revision"].update(state="queued", label="Revision queued; awaiting worker")
    path = f"/api/packets/{ready[2].id}"
    ui[3][path] = data
    ui[3][path + "/decision-detail"] = {"decision_id": "1" * 32, "decision": "revise", "created_at": "now", "reason_code": None, "detail": None, "feedback": "<script>private</script>"}
    ui[3][path + f"/diff/resume/{successor}"] = {"status": "available", "diff": "+" + "X" * 5000}
    ui[3][path + "/revision-status"] = {**data["revision"], "state": "blocked", "label": "Revision needs attention", "failure_category": "manual_review"}
    page = ui[0]; page.set_viewport_size({"width": 390, "height": 844}); page.clock.install(); page.goto(ui[2]); page.locator(".queue-card").click()
    expect(page.locator("#packet-heading")).to_have_text("Acme / Engineer")
    page.get_by_text("History and diffs (informational, not approval)", exact=True).click()
    page.get_by_role("button", name="Compare resume", exact=True).click()
    expect(page.locator(".diff")).to_contain_text("X" * 100)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator(".diff").evaluate("node => node.scrollWidth > node.clientWidth")
    page.clock.run_for(5100)
    expect(page.locator("#revision")).to_contain_text("Revision needs attention")
    count = len([url for url in ui[5] if url.endswith("revision-status")]); page.clock.run_for(11000)
    assert len([url for url in ui[5] if url.endswith("revision-status")]) == count == 1
    assert page.locator("#actions script").count() == 0


def test_browser_failed_preview_keeps_approve_disabled(ui, ready):
    from playwright.sync_api import expect
    data = detail_json(ready); data.update(integrity="failed", approval_preview=None)
    ui[3][f"/api/packets/{ready[2].id}"] = data
    page = ui[0]; page.goto(ui[2]); page.locator(".queue-card").click()
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Reject", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="Revise", exact=True)).to_be_enabled()



def test_browser_real_server_boundary_private_paths_and_no_cors(ui, ready):
    from job_agent.dashboard.approval_security import SECURITY_HEADERS
    from job_agent.database import PacketDecision
    from sqlmodel import Session, select
    context, origin = ui[1], ui[2]
    authority = urlsplit(origin).netloc
    for host in ("attacker.example", "127.0.0.1.attacker.example:" + str(urlsplit(origin).port),
                 authority + ".", "localhost:1"):
        response = context.request.get(origin + "/api/bootstrap", headers={"Host": host})
        assert response.status == 400 and response.json() == {"error": {"code": "invalid_host"}}
        for key, value in SECURITY_HEADERS.items(): assert response.headers[key.lower()] == value
    bootstrap = context.request.get(origin + "/api/bootstrap", headers={
        "Forwarded": "for=192.168.1.2;host=evil.example;proto=https",
        "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https", "X-Forwarded-For": "192.168.1.2"})
    assert bootstrap.ok and bootstrap.json()["origin"] == origin
    alias = context.request.get(origin + "/api/bootstrap", headers={"Host": f"localhost:{urlsplit(origin).port}"})
    assert alias.ok and alias.json()["origin"] == f"http://localhost:{urlsplit(origin).port}"
    assert alias.json()["csrf_token"] == bootstrap.json()["csrf_token"]
    packet_path = f"/api/packets/{ready[2].id}"
    for foreign in (None, "null", "https://evil.example", origin.replace("127.0.0.1", "localhost")):
        headers = {"X-Job-Pilot-CSRF": bootstrap.json()["csrf_token"]}
        if foreign is not None: headers["Origin"] = foreign
        response = context.request.post(origin + packet_path + "/revise", headers=headers, data={
            "expected_packet_fingerprint": ready[2].fingerprint, "feedback": "PRIVATE feedback"})
        assert response.status == 403 and response.json() == {"error": {"code": "csrf_failed"}}
    preflight = context.request.fetch(origin + packet_path + "/approve", method="OPTIONS", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert preflight.status == 405 and not any(key.startswith("access-control-") for key in preflight.headers)
    assert context.request.get(origin + packet_path + "/approve").status == 405
    for path in ("/facts.yaml", "/answer_bank.yaml", "/.env", "/assets/facts.yaml",
                 "/assets/%2e%2e/facts.yaml", packet_path + "/artifacts/resume.docx",
                 packet_path + "/artifacts/resume.face.txt"):
        response = context.request.get(origin + path)
        assert response.status == 404 and response.json() == {"error": {"code": "not_found"}}
    response = context.request.get(origin + packet_path + "/artifacts/resume.pdf?path=/facts.yaml")
    assert response.status == 422 and response.json() == {"error": {"code": "invalid_request"}}
    pdf = context.request.get(origin + packet_path + "/artifacts/resume.pdf", headers={"Range": "bytes=0-9"})
    assert pdf.status == 200 and "content-range" not in pdf.headers
    assert pdf.body() == (ready[4] / "packets" / ready[2].id / "resume.pdf").read_bytes()
    for key, value in SECURITY_HEADERS.items(): assert pdf.headers[key.lower()] == value
    with Session(ready[0].engine) as session: assert not session.exec(select(PacketDecision)).all()


def test_browser_two_tabs_exact_approve_replay_has_one_decision(ui, ready):
    from playwright.sync_api import expect
    from sqlmodel import Session, select
    from job_agent.database import PacketDecision
    open_packet(ui, ready)
    second = ui[1].new_page()
    second_ui = (second, *ui[1:])
    open_packet(second_ui, ready)
    for page in (ui[0], second): page.get_by_role("button", name="Approve", exact=True).click()
    ui[0].get_by_role("button", name="Confirm approve", exact=True).click()
    expect(ui[0].locator("#actions")).to_contain_text("Recorded decision: approve")
    second.get_by_role("button", name="Confirm approve", exact=True).click()
    expect(second.locator("#actions")).to_contain_text("Recorded decision: approve")
    assert len(ui[4]) == 2 and ui[4][0][1] == ui[4][1][1]
    assert ui[4][0][2]["x-job-pilot-csrf"] == ui[4][1][2]["x-job-pilot-csrf"]
    with Session(ready[0].engine) as session: assert len(session.exec(select(PacketDecision)).all()) == 1
    second.close()


def test_browser_valid_manual_destination_opens_only_after_explicit_revalidated_click(ui, ready):
    from playwright.sync_api import expect
    service, _, packet, _, _ = ready
    preview = service.preview_approval(packet.id, packet.fingerprint)
    service.approve(packet.id, packet.fingerprint, preview.approval_view_fingerprint)
    page = ui[0]; page.goto(ui[2]); page.get_by_role("button", name="History", exact=True).click()
    expect(page.locator(".queue-card")).to_have_count(1); page.locator(".queue-card").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "true")
    page.evaluate("() => { window.jobPilotTestNavigations = []; window.open = (...args) => { window.jobPilotTestNavigations.push(args); document.documentElement.setAttribute('data-job-pilot-test-navigation', 'recorded'); return null; }; }")
    page.get_by_role("button", name="Check application validity").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "false")
    assert page.evaluate("window.jobPilotTestNavigations") == []
    before = len([url for url in ui[5] if url.endswith("application-destination")])
    page.locator("#manual-application").click()
    expect(page.locator("#manual-application")).to_have_attribute("aria-disabled", "true")
    expect(page.locator("html")).to_have_attribute("data-job-pilot-test-navigation", "recorded")
    assert page.evaluate("window.jobPilotTestNavigations") == [[preview.application_url, "_blank", "noopener,noreferrer"]]
    assert len([url for url in ui[5] if url.endswith("application-destination")]) == before + 1


def test_browser_csp_blocks_inline_execution_and_confirmation_keyboard(ui, ready):
    from playwright.sync_api import expect
    open_packet(ui, ready); page = ui[0]
    page.evaluate("() => { const script = document.createElement('script'); script.textContent = 'window.jobPilotInjected = true'; document.head.append(script); }")
    assert page.evaluate("window.jobPilotInjected === undefined")
    page.get_by_role("button", name="Approve", exact=True).click()
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Confirm approve", exact=True)).to_be_focused()
    outline = page.get_by_role("button", name="Confirm approve", exact=True).evaluate("node => getComputedStyle(node).outlineStyle")
    assert outline != "none"
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Cancel", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("button", name="Approve", exact=True)).to_be_focused()
    assert not ui[4]
