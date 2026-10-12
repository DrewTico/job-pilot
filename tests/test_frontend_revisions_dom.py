"""5D-3: real static export, private API, synthetic separate execution only."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from playwright.sync_api import expect
from sqlmodel import Session, select

from job_agent.database import ApplicationPacket, PacketDecision
from job_agent.dashboard.approval_service import ApprovalQueueService
from job_agent.revisions import RevisionProcessor
from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready as ready_factory
from test_packets import setup, NOW

EVIDENCE = Path('/tmp/job-pilot-run5d3-premium-visual')


@pytest.fixture
def ready(setup, monkeypatch):
    result = ready_factory.__wrapped__(setup, monkeypatch)
    builder, directory = result[1], result[4]
    original = builder.executor.create
    calls = []
    def fake(**request):
        calls.append(request['task'])
        text = original(**request).content[0].text
        if request['task'] == 'tailor_resume': text = text.replace('Built Python software.', 'Built Python tools.')
        else:
            text = json.loads(text); text['candidate_lines'] = ['Built Python tools.']; text = json.dumps(text)
        return SimpleNamespace(content=[SimpleNamespace(type='text', text=text)])
    processor = RevisionProcessor(builder.engine, builder.settings, executor=SimpleNamespace(create=fake), clock=lambda: NOW)
    # Captured before the existing loopback fixture traps browser-triggered
    # generation. Tests invoke this directly, never through the frontend/API.
    execute = processor.process_revision
    return (*result, execute, calls)


@pytest.fixture
def revision_ui(ui, ready, monkeypatch):
    page = ui[0]
    page.add_init_script("window.cspViolations=[];document.addEventListener('securitypolicyviolation',e=>window.cspViolations.push(e.violatedDirective))")
    def forbidden(*args, **kwargs): raise AssertionError('Employer/model side effect forbidden')
    monkeypatch.setattr('job_agent.apply.runner.run_apply', forbidden)
    monkeypatch.setattr('job_agent.apply.runner._run_flow', forbidden)
    monkeypatch.setattr('job_agent.application_state.record_attempt', forbidden)
    monkeypatch.setattr('job_agent.application_state.update_status', forbidden)
    yield ui
    assert not page.evaluate('window.cspViolations')
    assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
    with ready[0].engine.connect() as c:
        assert c.exec_driver_sql('SELECT count(*) FROM application_events').scalar() == 0
    assert all(path.endswith(('/approve', '/reject', '/revise')) for path, _, _ in ui[4])
    assert not any('/apply' in url or '/submit' in url for url in ui[5])


def open_source(ui, ready, width):
    page = ui[0]; page.set_viewport_size({'width': width, 'height': 844 if width < 600 else 900})
    page.emulate_media(reduced_motion='reduce')
    page.goto(ui[2] + '/ui'); page.locator('.queue-row').first.click()
    expect(page.get_by_role('button', name='Revise', exact=True)).to_be_enabled()
    return page


def record(page, action):
    page.get_by_role('button', name=action.capitalize(), exact=True).click()
    if action == 'revise': page.get_by_label('Revision feedback (required)').fill('Use specific synthetic Python evidence.')
    if action == 'reject': page.get_by_label('Reason (required)').select_option('other')
    page.get_by_role('button', name={'approve': 'Record approval', 'reject': 'Record rejection', 'revise': 'Record revision request'}[action], exact=True).click()
    surface = page.get_by_role('region', name='Revision review') if action == 'revise' else page.locator('.decision-dock')
    expect(surface).to_contain_text({'approve': 'Approval recorded', 'reject': 'Rejection recorded', 'revise': 'Revision request recorded'}[action])
    if action == 'revise': expect(page.locator('.decision-dock')).to_have_count(0)


def execute(ready):
    directory = ready[4]
    facts = yaml.safe_load((directory / 'facts.yaml').read_text())
    facts['employers'][0]['real_bullets'].append('Built Python tools.')
    facts['employers'][0]['project_description'] = 'Built Python tools.'
    (directory / 'facts.yaml').write_text(yaml.safe_dump(facts))
    with Session(ready[0].engine) as s: decision = s.exec(select(PacketDecision).where(PacketDecision.packet_id == ready[2].id)).one()
    work = ready[5](decision.id)
    assert work.state == 'succeeded', work.failure_code
    with Session(ready[0].engine) as s: child = s.get(ApplicationPacket, work.successor_packet_id)
    assert child.id != ready[2].id and child.revision_decision_id == decision.id
    return child, decision


def comparison(page):
    page.get_by_role('button', name='Review changes', exact=True).click()
    expect(page.get_by_role('region', name='Revision comparison')).to_be_visible()


def close_comparison(page, width):
    if width < 600: page.get_by_role('button', name='Close sheet', exact=True).click()


def capture(page, name, width):
    if width in (390, 1440) and name in ('revision-requested', 'revision-processing', 'successor-decision-ready', 'trusted-comparison'):
        EVIDENCE.mkdir(exist_ok=True)
        page.screenshot(path=str(EVIDENCE / f'{name}-{width}.png'))


def geometry(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for control in page.locator('.revision-actions button, .decision-actions button').all():
        box = control.bounding_box()
        if box: assert box['height'] >= 44 and box['width'] >= 44
    scroller = page.locator('.phone-review-page:has(.phone-decision-result) > .phone-review-scroll')
    if scroller.count():
        box = scroller.bounding_box(); dock = page.locator('.decision-dock').bounding_box()
        assert box['y'] + box['height'] <= dock['y']
        scroller.evaluate('n=>n.scrollTop=n.scrollHeight')
        history = page.get_by_role('button', name='View packet history').bounding_box()
        assert history['y'] + history['height'] <= dock['y'] - 16


@pytest.mark.parametrize('width', [1440, 360, 390, 430, 480])
@pytest.mark.parametrize('state', ['requested', 'processing'])
def test_passive_revision_composition_has_one_status_and_no_bottom_dock(revision_ui, ready, width, state):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise')
    if state == 'processing':
        processor = ready[5].__self__
        def stop(name):
            if name == 'after_successor_allocation': raise SystemExit('test-only pause')
        processor._boundary = stop
        with pytest.raises(SystemExit): execute(ready)
        page.get_by_role('button', name='Refresh revision status').click()
    region = page.get_by_role('region', name='Revision review')
    title = 'Revision request recorded' if state == 'requested' else 'Generating revision'
    expect(region.get_by_role('heading', name=title, exact=True)).to_be_visible()
    expect(page.get_by_text(title, exact=True)).to_have_count(1)
    expect(region).to_contain_text('Generation is a separate step' if state == 'requested' else 'No successor is offered yet')
    expect(page.locator('.decision-dock, .phone-decision-result, .decision-queue-note')).to_have_count(0)
    assert 'No queued job on the refreshed first page.' not in page.locator('.app').inner_text()
    assert not page.get_by_role('button', name='Review successor v2').count()
    assert region.evaluate('n=>n.scrollHeight<=n.clientHeight && n.scrollWidth<=n.clientWidth')
    card = region.bounding_box()
    for control in region.locator('h2, button').all():
        box = control.bounding_box()
        assert box['y'] >= card['y'] and box['y'] + box['height'] <= card['y'] + card['height']
    geometry(page); capture(page, f'revision-{state}', width)
    if width >= 600: return
    history = page.get_by_role('button', name='View packet history', exact=True)
    context = page.locator('.phone-revision-packet').bounding_box()
    # The secondary context completes the waiting surface near the safe edge,
    # rather than leaving half the viewport inactive after the last control.
    assert 16 <= page.viewport_size['height'] - context['y'] - context['height'] <= 48
    assert abs(card['y'] + card['height'] - context['y']) <= 1
    history.scroll_into_view_if_needed()
    expect(history).to_be_in_viewport()
    assert history.evaluate('n=>{const r=n.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("button")===n}')
    assert history.bounding_box()['height'] >= 48
    history.click()
    expect(page.get_by_role('dialog', name='History')).to_be_visible()
    page.get_by_role('button', name='Close sheet', exact=True).click()
    session = page.context.new_cdp_session(page)
    session.send('Emulation.setSafeAreaInsetsOverride', {'insets': {'top': 20, 'right': 0, 'bottom': 34, 'left': 0}})
    assert page.locator('.phone-app').evaluate('n=>getComputedStyle(n).paddingTop') == '20px'
    assert page.locator('.phone-review-scroll').evaluate('n=>getComputedStyle(n).paddingBottom') == '58px'
    for height in (568, 700, 1000):
        page.set_viewport_size({'width': width, 'height': height})
        page.evaluate("document.documentElement.style.fontSize='100%';window.scrollTo(0,0)")
        geometry(page)
        page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        expect(history).to_be_in_viewport()
        assert history.bounding_box()['y'] + history.bounding_box()['height'] <= height - 34
        # Larger text grows the document and keeps both groups in natural flow.
        page.evaluate("document.documentElement.style.fontSize='200%'")
        assert page.evaluate('document.documentElement.scrollHeight > innerHeight')
        region.locator('h2').scroll_into_view_if_needed()
        expect(region.locator('h2')).to_be_in_viewport()
        geometry(page)
        history.scroll_into_view_if_needed()
        expect(history).to_be_in_viewport()
        assert page.locator('.phone-review-nav').bounding_box()['y'] >= 20
        geometry(page)
        page.get_by_role('button', name='Refresh revision status').focus()
        page.keyboard.press('Tab')
        expect(history).to_be_focused()
        assert history.evaluate('n=>getComputedStyle(n).outlineStyle') != 'none'
        page.keyboard.press('Enter')
        expect(page.get_by_role('dialog', name='History')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog', name='History')).to_have_count(0)
        expect(history).to_be_focused()
    session.detach()


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('failed_read', ['packet', 'queue'])
def test_revision_reconciliation_failure_keeps_recovery_visible(revision_ui, ready, width, failed_read):
    ui = revision_ui; page = open_source(ui, ready, width)
    path = f'/api/packets/{ready[2].id}' if failed_read == 'packet' else '/api/queue'
    ui[3][path] = (503, {'error': {'code': 'storage_unavailable'}})
    page.get_by_role('button', name='Revise', exact=True).click()
    page.get_by_label('Revision feedback (required)').fill('Use specific synthetic Python evidence.')
    page.get_by_role('button', name='Record revision request', exact=True).click()
    refresh = page.get_by_role('button', name='Refresh this packet', exact=True)
    expect(refresh).to_be_visible()
    if failed_read == 'packet':
        expect(page.locator('.decision-dock')).to_contain_text('Packet history refresh is unavailable')
        expect(page.locator('.decision-dock').get_by_role('alert')).to_be_visible()
    else:
        expect(page.locator('.decision-dock')).to_have_count(0)
        expect(page.get_by_role('region', name='Revision review')).to_contain_text('Revision request recorded')
    del ui[3][path]
    refresh.click()
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('Revision request recorded')
    expect(page.locator('.decision-dock')).to_have_count(0)
    expect(refresh).to_have_count(0)
    assert len(ui[4]) == 1


@pytest.mark.parametrize('width', [1440, 360, 390, 430, 480])
@pytest.mark.parametrize('action', ['approve', 'reject', 'revise'])
def test_complete_revision_review_and_fresh_successor_decision(revision_ui, ready, width, action):
    ui = revision_ui; page = open_source(ui, ready, width)
    old_preview = ready[0].preview_approval(ready[2].id, ready[2].fingerprint)
    record(page, 'revise')
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('Revision request recorded')
    assert not page.get_by_role('button', name='Review successor v2').count()
    assert not ready[6], 'Revise POST generated output'
    with ready[0].engine.connect() as c: assert c.exec_driver_sql('SELECT count(*) FROM packet_revision_work').scalar() == 0
    geometry(page); capture(page, 'revision-requested', width)
    child, predecessor_decision = execute(ready)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    assert len(ready[6]) == 2
    comparison(page)
    changes = page.get_by_role('region', name='Revision comparison')
    expect(changes).to_contain_text('Before v1')
    expect(changes).to_contain_text('After v2')
    expect(changes).to_contain_text('Both documents authenticated')
    expect(changes).to_contain_text('Built Python tools.')
    expect(changes.get_by_text('Authenticated · Changed', exact=True)).to_have_count(2)
    assert 'packet:' not in changes.inner_text() and '@@' not in changes.inner_text()
    assert ready[2].id not in changes.inner_text() and child.id not in changes.inner_text()
    expect(changes.locator('.diff-added .diff-document-text').first).to_contain_text('Built Python tools.')
    expect(changes.locator('.diff-removed .diff-document-text').first).to_contain_text('Built Python software.')
    geometry(page); capture(page, 'trusted-comparison', width); close_comparison(page, width)
    page.get_by_role('button', name='Review successor v2').click()
    expect(page.locator('.decision-dock')).to_contain_text('Reviewing packet v2')
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    expect(page.get_by_role('button', name='Review changes', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Reject', exact=True)).to_be_enabled()
    expect(page.get_by_role('button', name='Revise', exact=True)).to_be_enabled()
    geometry(page); capture(page, 'successor-decision-ready', width)
    # A valid session CSRF token alone grants no packet authority. Both exact
    # predecessor fingerprints fail on the real successor protected route.
    csrf = ui[4][0][2]['x-job-pilot-csrf']
    headers = {'Origin': ui[2], 'X-Job-Pilot-CSRF': csrf}
    path = ui[2] + f'/api/packets/{child.id}/approve'
    stale = ui[1].request.post(path, headers=headers, data={'expected_packet_fingerprint': ready[2].fingerprint, 'expected_approval_view_fingerprint': old_preview.approval_view_fingerprint})
    assert stale.status == 409 and stale.json()['error']['code'] == 'stale_packet', stale.json()
    stale = ui[1].request.post(path, headers=headers, data={'expected_packet_fingerprint': child.fingerprint, 'expected_approval_view_fingerprint': old_preview.approval_view_fingerprint})
    assert stale.status == 409 and stale.json()['error']['code'] == 'stale_approval_view', stale.json()
    record(page, action)
    geometry(page)
    assert ui[4][-1][0] == f'/api/packets/{child.id}/{action}'
    assert ui[4][-1][1]['expected_packet_fingerprint'] == child.fingerprint
    if action == 'approve':
        expect(page.locator('.decision-dock')).to_contain_text('No application submitted')
        assert ui[4][-1][1]['expected_approval_view_fingerprint'] != old_preview.approval_view_fingerprint
    if action == 'revise':
        expect(page.get_by_role('region', name='Revision review')).to_contain_text('Revision of v2')
        assert len(ready[6]) == 2
    with Session(ready[0].engine) as s:
        original = s.get(PacketDecision, predecessor_decision.id)
        successor_decision = s.exec(select(PacketDecision).where(PacketDecision.packet_id == child.id)).one()
        assert original.decision == 'revise' and successor_decision.decision == action
        assert successor_decision.id != original.id
    assert any(f'/api/packets/{ready[2].id}/revision-comparison/{child.id}' in u for u in ui[5])


@pytest.mark.parametrize('width', [360, 390, 430, 480, 1440])
def test_comparison_long_content_wraps_without_losing_exact_text_or_markers(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); child, _ = execute(ready)
    result = ApprovalQueueService(ready[0].engine, ready[1].settings).revision_comparison(ready[2].id, child.id).model_dump()
    long = 'Synthetic ' + 'W' * 180
    diff = f'--- packet:{ready[2].id}/version:1\n+++ packet:{child.id}/version:2\n@@ -1,2 +1,2 @@\n Retained context\n-Old  exact text\n+{long}\n'
    for kind in ('resume', 'cover'): result[kind].update(changed=True, diff=diff)
    ui[3][f'/api/packets/{ready[2].id}/revision-comparison/{child.id}'] = result
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    page.get_by_role('button', name='Refresh revision status').click()
    expect(page.get_by_role('button', name='Refresh revision status')).to_be_enabled()
    comparison(page)
    changes = page.get_by_role('region', name='Revision comparison')
    expect(changes.locator('.diff-added .diff-document-text').first).to_have_text(long)
    expect(changes.locator('.diff-removed .diff-document-text').first).to_have_text('Old  exact text', use_inner_text=False)
    assert changes.locator('.diff-removed .diff-document-text').first.evaluate('n=>n.textContent') == 'Old  exact text'
    expect(changes.locator('.diff-context .diff-document-text').first).to_have_text('Retained context')
    assert changes.locator('.diff-document-text').first.evaluate('n=>getComputedStyle(n).fontSize') == '13px'
    assert '@@' not in changes.inner_text() and 'packet:' not in changes.inner_text()
    for line in changes.locator('.diff-line').all():
        assert line.evaluate('n=>n.scrollWidth<=n.clientWidth')
        marker = line.locator('.diff-marker').bounding_box(); text = line.locator('.diff-document-text').bounding_box()
        assert marker['width'] >= 16 and marker['x'] + marker['width'] <= text['x']
    controls = changes.get_by_role('button', name='Refresh comparison')
    if width < 600:
        controls = controls.or_(page.get_by_role('button', name='Close sheet'))
        scroller = page.locator('.phone-sheet-scroll')
        assert scroller.evaluate('n=>n.scrollWidth<=n.clientWidth')
        changes.locator('.diff-added .diff-document-text').last.scroll_into_view_if_needed()
        assert scroller.evaluate('n=>n.scrollTop>0')
        expect(changes.locator('.diff-added .diff-document-text').last).to_be_in_viewport()
    for control in controls.all():
        box = control.bounding_box(); assert box['height'] >= 44 and box['width'] >= 44
    geometry(page)


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('state', ['unchanged', 'unavailable', 'integrity_failed', 'invalid_request', 'wrong_pair', 'successor_unavailable'])
def test_comparison_and_current_successor_failure_states(revision_ui, ready, width, state):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); child, _ = execute(ready)
    service = ApprovalQueueService(ready[0].engine, ready[1].settings)
    result = service.revision_comparison(ready[2].id, child.id).model_dump()
    if state == 'unchanged':
        for kind in ('resume', 'cover'): result[kind].update(changed=False, diff='')
    elif state in ('unavailable', 'integrity_failed', 'invalid_request'):
        result.update(status=state, resume=None, cover=None, revision_decision_id=None)
    elif state == 'wrong_pair': result['after']['packet_id'] = 'e' * 32
    else: ui[3][f'/api/packets/{child.id}'] = (404, {'error': {'code': 'not_found'}})
    ui[3][f'/api/packets/{ready[2].id}/revision-comparison/{child.id}'] = result
    page.get_by_role('button', name='Refresh revision status').click()
    if state in ('wrong_pair', 'successor_unavailable', 'integrity_failed', 'invalid_request'):
        expect(page.get_by_role('button', name='Review successor v2')).to_have_count(0)
    if state == 'successor_unavailable': expect(page.get_by_role('region', name='Revision review')).to_contain_text('Successor detail unavailable')
    comparison(page)
    changes = page.get_by_role('region', name='Revision comparison')
    text = {'unchanged': 'Authenticated · Unchanged', 'unavailable': 'Comparison unavailable', 'integrity_failed': 'Comparison integrity failed', 'invalid_request': 'Invalid revision relationship', 'wrong_pair': 'returned a different revision', 'successor_unavailable': 'Both documents authenticated'}[state]
    expect(changes).to_contain_text(text)
    if state not in ('unchanged', 'successor_unavailable'): assert 'Authenticated · Unchanged' not in changes.inner_text()
    geometry(page)


@pytest.mark.parametrize('width', [1440, 390])
def test_processing_status_and_late_comparison_navigation(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise')
    processor = ready[5].__self__
    def stop(name):
        if name == 'after_successor_allocation': raise SystemExit('test-only pause')
    processor._boundary = stop
    with pytest.raises(SystemExit): execute(ready)
    page.get_by_role('button', name='Refresh revision status').click()
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('Generating revision')
    assert not page.get_by_role('button', name='Review successor v2').count()
    capture(page, 'revision-processing', width)
    processor._boundary = lambda name: None
    # Resume the exact work without changing current candidate inputs again.
    with Session(ready[0].engine) as s: decision = s.exec(select(PacketDecision).where(PacketDecision.packet_id == ready[2].id)).one()
    work = ready[5](decision.id); assert work.state == 'succeeded'
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    delayed = []
    page.route(f'**/api/packets/{ready[2].id}/revision-comparison/{work.successor_packet_id}', lambda route: delayed.append(route))
    page.get_by_role('button', name='Refresh revision status').click()
    page.wait_for_timeout(100)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible()
    # Navigation clears/aborts the old comparison before the new packet read.
    page.get_by_role('button', name='Review successor v2').click()
    expect(page.locator('.decision-dock')).to_contain_text('Reviewing packet v2')
    assert delayed
    old = delayed.pop(0)
    try: old.continue_()
    except Exception: pass  # The browser may already have canceled the request.
    page.wait_for_timeout(100)
    assert not page.locator('.revision-changes').count()
    assert 'Revision of v1' not in page.get_by_role('region', name='Revision review').inner_text()
    page.goto(ui[2] + '/ui')
    assert not page.locator('.revision-changes, .revision-summary').count()


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('state', ['blocked', 'recovery_required', 'read_error'])
def test_truthful_status_errors_stop_refresh_and_offer_recovery(revision_ui, ready, width, state):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise')
    path = f'/api/packets/{ready[2].id}/revision-status'
    data = ApprovalQueueService(ready[0].engine, ready[1].settings).revision_status(ready[2].id).model_dump()
    ui[3][path] = (503, {'error': {'code': 'storage_unavailable'}}) if state == 'read_error' else {**data, 'state': state, 'failure_category': 'manual_review'}
    page.get_by_role('button', name='Refresh revision status').click()
    region = page.get_by_role('region', name='Revision review')
    expect(region).to_contain_text({'blocked': 'Processing stopped', 'recovery_required': 'No automatic retry', 'read_error': 'Current revision work and successor availability could not be confirmed'}[state])
    assert not page.get_by_role('button', name='Review successor v2').count()
    count = sum(path in u for u in ui[5]); page.wait_for_timeout(3200)
    assert sum(path in u for u in ui[5]) == count
    expect(page.get_by_role('button', name='Refresh revision status')).to_be_enabled()
    geometry(page)


@pytest.mark.parametrize('width', [1440, 390])
def test_successor_current_read_changes_cancel_confirmation_and_block_decisions(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); child, _ = execute(ready)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    page.get_by_role('button', name='Review successor v2').click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    # Actual current artifact damage in temporary storage, after historical success.
    (ready[4] / 'packets' / child.id / 'resume.pdf').write_bytes(b'Synthetic damaged successor')
    page.get_by_role('button', name='Refresh revision status').click()
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('not currently verified and ready')
    for action in ('Approve', 'Reject', 'Revise'): expect(page.get_by_role('button', name=action, exact=True)).to_be_disabled()
    assert len(ui[4]) == 1
    comparison(page)
    expect(page.get_by_role('region', name='Resume changes')).to_contain_text('Integrity failed')
    assert 'Authenticated · Unchanged' not in page.get_by_role('region', name='Revision comparison').inner_text()
    geometry(page)


@pytest.mark.parametrize('width', [1440, 390])
def test_late_integrity_result_cancels_fresh_successor_confirmation(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); child, _ = execute(ready)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    expect(page.get_by_role('button', name='Review changes')).to_be_visible()
    delayed = []
    page.route(f'**/api/packets/{ready[2].id}/revision-comparison/{child.id}', lambda route: delayed.append(route))
    page.get_by_role('button', name='Review successor v2').click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    page.get_by_role('button', name='Approve', exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert delayed
    result = ApprovalQueueService(ready[0].engine, ready[1].settings).revision_comparison(ready[2].id, child.id).model_dump()
    result.update(status='integrity_failed', resume=None, cover=None)
    delayed.pop(0).fulfill(json=result)
    expect(page.get_by_role('dialog')).to_have_count(0)
    for action in ('Approve', 'Reject', 'Revise'): expect(page.get_by_role('button', name=action, exact=True)).to_be_disabled()
    assert len(ui[4]) == 1


@pytest.mark.parametrize('width', [1440, 390])
def test_verified_successor_refreshes_queue_without_navigation_or_false_caught_up(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); child, _ = execute(ready)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    # Remain on the predecessor until Andrew chooses navigation.
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('Successor v2 verified for review')
    expect(page.locator('.decision-dock, .decision-queue-note')).to_have_count(0)
    page.get_by_role('button', name='Back to queue', exact=True).click()
    expect(page.locator('.queue-row')).to_have_count(1)
    assert 'all caught up' not in page.locator('.app').inner_text()
    page.locator('.queue-row').first.click()
    expect(page.locator('.decision-dock')).to_contain_text('Reviewing packet v2')
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    assert child.id in ui[5][-1] or any(f'/api/packets/{child.id}' in u for u in ui[5])


@pytest.mark.parametrize('width', [1440, 390])
def test_historical_successor_with_own_decision_does_not_request_another_decision(revision_ui, ready, width):
    ui = revision_ui; page = open_source(ui, ready, width); record(page, 'revise'); execute(ready)
    expect(page.get_by_role('button', name='Review successor v2')).to_be_visible(timeout=12000)
    page.get_by_role('button', name='Review successor v2').click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled(); record(page, 'approve')
    comparison(page)
    page.get_by_role('button', name='Inspect v1', exact=True).click()
    expect(page.get_by_role('region', name='Revision review')).to_contain_text('Its own decision is recorded.')
    expect(page.get_by_role('region', name='Revision review')).not_to_contain_text('A fresh decision is required.')
    assert len(ui[4]) == 2
