"""Run 5C: actual export, CSP/security middleware and temporary SQLite only.

Every decision is confined to the synthetic loopback app. Providers, generation,
Python outbound networking and build entry points are forbidden by its fixture.
No production service is restarted, reconfigured or used as a mutation target.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect
from sqlmodel import Session, select

from job_agent.database import PacketDecision
from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready as ready_factory
from test_packets import setup, add_job

EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/run5c/decision-implementation-evidence'


@pytest.fixture
def ready(setup, monkeypatch):
    result = ready_factory.__wrapped__(setup, monkeypatch)
    row = add_job(result[1], id='run5c-second', score=75, title='Synthetic platform engineer')
    second = result[1].build_one(row)
    assert second.status == 'packet_ready'
    return result


@pytest.fixture
def decisions(ui, ready, monkeypatch):
    page = ui[0]
    page.add_init_script("window.cspViolations=[];window.opened=[];window.open=(...args)=>{window.opened.push(args);return null};document.addEventListener('securitypolicyviolation',e=>window.cspViolations.push(e.violatedDirective))")
    def forbidden(*args, **kwargs):
        raise AssertionError('Run 5C must not invoke submission, an LLM or a worker')
    import job_agent.apply.runner as runner
    import job_agent.apply.submit as submit
    for module in (runner, submit):
        for name, value in vars(module).copy().items():
            if callable(value) and getattr(value, '__module__', '') == module.__name__:
                monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(ready[1].executor, 'create', forbidden)
    before = db_state(ready)
    yield ui
    assert not page.evaluate('window.cspViolations')
    assert not page.evaluate('window.opened')
    assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
    assert page.evaluate('document.cookie') == ''
    allowed = {f'/api/packets/{id}/{action}' for id in before['packet_ids'] for action in ('approve', 'reject', 'revise')}
    assert all(path in allowed for path, _, _ in ui[4])
    assert all(not any(name.startswith('tailscale-') or name in ('authorization', 'x-forwarded-user') for name in headers) for _, _, headers in ui[4])
    assert not any('/apply' in url or '/submit' in url or '/application-destination' in url or '/revision-status' in url for url in ui[5])
    after = db_state(ready)
    assert after['packets'] == before['packets']
    assert after['events'] == before['events']
    assert after['revisions'] == before['revisions']
    assert not (ready[4] / 'style_memory.md').exists()


def db_state(ready):
    with ready[0].engine.connect() as conn:
        return {'packet_ids': conn.exec_driver_sql('SELECT id FROM application_packets ORDER BY id').scalars().all(),
                'packets': conn.exec_driver_sql('SELECT * FROM application_packets ORDER BY id').all(),
                'events': conn.exec_driver_sql('SELECT * FROM application_events ORDER BY id').all(),
                'revisions': conn.exec_driver_sql('SELECT * FROM packet_revision_work ORDER BY decision_id').all(),
                'decisions': conn.exec_driver_sql('SELECT * FROM packet_decisions ORDER BY id').all()}


def open_packet(decisions, ready, width=1440):
    page = decisions[0]
    page.set_viewport_size({'width': width, 'height': 844 if width < 600 else 900})
    page.emulate_media(reduced_motion='reduce')
    page.goto(decisions[2] + '/ui')
    expect(page.locator('.queue-row')).to_have_count(2)
    page.locator('.queue-row').first.click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    expect(page.locator('#packet-title')).to_have_text(ready[2].title)
    return page


def capture(page, name):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE / f'{name}.png'))


def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [360, 390, 430, 480, 1440])
def test_decision_forms_context_keyboard_validation_and_geometry(decisions, ready, width):
    page = open_packet(decisions, ready, width)
    no_overflow(page)
    for action in ('Approve', 'Reject', 'Revise'):
        opener = page.get_by_role('button', name=action, exact=True)
        assert opener.bounding_box()['height'] >= 44
        opener.click()
        dialog = page.get_by_role('dialog')
        expect(dialog).to_contain_text('Acme')
        expect(dialog).to_contain_text('Engineer')
        expect(dialog).to_contain_text('Exact packet v1')
        no_overflow(page)
        if action == 'Approve':
            expect(dialog).to_contain_text('It does not submit an application to the employer.')
            expect(page.get_by_role('button', name='Close sheet')).to_be_focused()
        else:
            label = 'Reason (required)' if action == 'Reject' else 'Revision feedback (required)'
            expect(page.get_by_label(label)).to_be_focused()
            primary = 'Record rejection' if action == 'Reject' else 'Record revision request'
            page.get_by_role('button', name=primary, exact=True).click()
            expect(dialog.locator('[role=alert]')).to_have_text('Choose a reason.' if action == 'Reject' else 'Enter revision feedback.')
            field = page.get_by_label('Detail (optional)' if action == 'Reject' else 'Revision feedback (required)')
            field.fill('😀' * 4001)
            if action == 'Reject': page.get_by_label('Reason (required)').select_option('other')
            page.get_by_role('button', name=primary, exact=True).click()
            expect(dialog.locator('[role=alert]')).to_have_text('Use 4,000 characters or fewer.')
            assert not decisions[4]
            expect(page.locator('#decision-count')).to_contain_text('4,001 / 4,000')
        # Trap includes native form fields and keeps background keyboard inert.
        page.get_by_role('button', name='Close sheet').focus()
        page.keyboard.press('Shift+Tab')
        expect(page.get_by_role('button', name='Cancel', exact=True)).to_be_focused()
        page.keyboard.press('Tab')
        expect(page.get_by_role('button', name='Close sheet')).to_be_focused()
        page.keyboard.press('Escape')
        expect(opener).to_be_focused()
        assert not page.get_by_role('dialog').count()
        assert not decisions[4]
    page.evaluate("document.documentElement.style.fontSize='200%'")
    page.get_by_role('button', name='Revise', exact=True).click()
    no_overflow(page)
    assert page.locator('.phone-sheet-scroll').evaluate('n=>getComputedStyle(n).overflowY') == 'auto'
    assert page.locator('.phone-sheet').evaluate('n=>getComputedStyle(n).animationName') == 'none'


@pytest.mark.parametrize('action', ['approve', 'reject', 'revise'])
@pytest.mark.parametrize('width', [1440, 390])
def test_real_decisions_write_one_immutable_record_only_and_refresh_history(decisions, ready, action, width):
    page = open_packet(decisions, ready, width)
    before = db_state(ready)
    preview = ready[0].preview_approval(ready[2].id, ready[2].fingerprint)
    page.get_by_role('button', name=action.capitalize(), exact=True).click()
    if action == 'reject':
        page.get_by_label('Reason (required)').select_option('other')
        page.get_by_label('Detail (optional)').fill('  Exact 😀 reason\n ')
    if action == 'revise': page.get_by_label('Revision feedback (required)').fill('  Exact 😀 feedback\n ')
    button = {'approve': 'Record approval', 'reject': 'Record rejection', 'revise': 'Record revision request'}[action]
    page.get_by_role('button', name=button, exact=True).click()
    title = {'approve': 'Approval recorded', 'reject': 'Rejection recorded', 'revise': 'Revision request recorded'}[action]
    expect(page.locator('.decision-dock')).to_contain_text(title)
    if width == 1440: expect(page.locator('.queue-row')).to_have_count(1)
    refreshed_queue = decisions[1].request.get(decisions[2] + '/api/queue?section=needs-review&limit=25&offset=0').json()
    assert len(refreshed_queue['items']) == 1 and all(item['packet_id'] != ready[2].id for item in refreshed_queue['items'])
    expect(page.get_by_role('button', name='Next queued job', exact=True)).to_be_visible()
    if width == 1440: expect(page.locator('#packet-title')).to_have_text(ready[2].title)
    else: expect(page.get_by_role('region', name='Recorded decision')).to_contain_text(ready[2].title)
    if action == 'approve':
        expect(page.locator('.decision-dock')).to_contain_text('No application submitted')
        expect(page.locator('.decision-dock')).to_contain_text('Ready for next step')
        assert decisions[4][0][1] == {'expected_packet_fingerprint': ready[2].fingerprint, 'expected_approval_view_fingerprint': preview.approval_view_fingerprint}
    if action == 'revise':
        expect(page.locator('.decision-dock')).to_contain_text('Revision generation is a separate step.')
        assert 'Creates a new packet version' not in page.locator('.decision-dock').inner_text()
    if action in ('reject', 'revise'):
        capture(page, f'{"desktop" if width == 1440 else "phone"}-{action}-recorded-{"1440x900" if width == 1440 else "390x844"}')
    if width == 1440: page.get_by_role('tablist', name='Evidence tabs').get_by_role('tab', name='History', exact=True).click()
    else: page.get_by_role('button', name='View packet history', exact=True).click()
    expect(page.locator('.history-current')).to_contain_text({'approve': 'Historical approval', 'reject': 'Historical rejection', 'revise': 'Revision requested'}[action])
    after = db_state(ready)
    assert len(after['decisions']) == len(before['decisions']) + 1
    # Replay the captured exact DTO through the real app, synthetic only.
    path, body, headers = decisions[4][0]
    response = decisions[1].request.post(decisions[2] + path, data=body, headers={'Origin': decisions[2], 'X-Job-Pilot-CSRF': headers['x-job-pilot-csrf']})
    assert response.ok
    assert len(db_state(ready)['decisions']) == len(after['decisions'])
    assert after['packets'] == before['packets'] and after['events'] == before['events'] and after['revisions'] == before['revisions']
    proof = {'action': action, 'packet_decisions_delta': 1, 'exact_replay_delta': 0, 'application_packets_unchanged': True,
             'packet_revision_work_delta': 0, 'application_events_delta': 0, 'provider_worker_employer_calls': 0}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f'database-{action}.json').write_text(json.dumps(proof, indent=2) + '\n')


@pytest.mark.parametrize('reason', ['not_interested', 'bad_fit', 'company', 'location', 'pay', 'other'])
def test_reject_all_six_codes_and_optional_detail(decisions, ready, reason):
    page = open_packet(decisions, ready, 390)
    page.get_by_role('button', name='Reject', exact=True).click()
    page.get_by_label('Reason (required)').select_option(reason)
    page.get_by_role('button', name='Record rejection', exact=True).click()
    expect(page.locator('.decision-dock')).to_contain_text('Rejection recorded')
    with Session(ready[0].engine) as session:
        record = session.exec(select(PacketDecision)).one()
        assert record.reason_code == reason and record.detail == ''


@pytest.mark.parametrize('action', ['reject', 'revise'])
def test_damaged_artifact_keeps_recovery_decisions_available(decisions, ready, action):
    (ready[4] / 'packets' / ready[2].id / 'resume.pdf').write_bytes(b'Synthetic damaged PDF')
    page = decisions[0]; page.goto(decisions[2] + '/ui'); page.locator('.queue-row').first.click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name=action.capitalize(), exact=True)).to_be_enabled()
    page.get_by_role('button', name=action.capitalize(), exact=True).click()
    if action == 'reject': page.get_by_label('Reason (required)').select_option('other')
    else: page.get_by_label('Revision feedback (required)').fill('Review this synthetic artifact.')
    page.get_by_role('button', name='Record rejection' if action == 'reject' else 'Record revision request', exact=True).click()
    expect(page.locator('.decision-dock')).to_contain_text('recorded')


def test_bootstrap_unavailable_and_csrf_explicit_retry_without_post_replay(decisions, ready):
    decisions[3]['/api/bootstrap'] = (401, {'error': {'code': 'authentication_required', 'private': 'PRIVATE_SENTINEL'}})
    page = decisions[0]; page.goto(decisions[2] + '/ui'); page.locator('.queue-row').first.click()
    for action in ('Approve', 'Reject', 'Revise'): expect(page.get_by_role('button', name=action, exact=True)).to_be_disabled()
    expect(page.locator('.decision-dock')).to_contain_text('Decisions unavailable.')
    capture(page, 'desktop-bootstrap-unavailable-1440x900')
    decisions[3].pop('/api/bootstrap')
    page.get_by_role('button', name='Enable decisions').click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    decisions[3][f'/api/packets/{ready[2].id}/approve'] = (403, {'error': {'code': 'csrf_failed', 'detail': 'PRIVATE_SENTINEL'}})
    page.get_by_role('button', name='Approve', exact=True).click(); page.get_by_role('button', name='Record approval', exact=True).click()
    expect(page.locator('.decision-dock')).to_contain_text('Session changed.')
    assert 'PRIVATE_SENTINEL' not in page.locator('.app').inner_text()
    page.get_by_role('button', name='Enable decisions').click()
    expect(page.get_by_role('button', name='Refresh this packet')).to_be_enabled()
    page.get_by_role('button', name='Refresh this packet').click()
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    assert len(decisions[4]) == 1


def test_pending_double_click_close_and_late_response_after_selection(decisions, ready):
    page = open_packet(decisions, ready)
    delayed = []
    path = f'**/api/packets/{ready[2].id}/reject'
    page.route(path, lambda route: delayed.append(route))
    page.get_by_role('button', name='Reject', exact=True).click(); page.get_by_label('Reason (required)').select_option('pay')
    page.get_by_role('button', name='Record rejection', exact=True).dblclick()
    expect(page.get_by_role('button', name='Recording…', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Close sheet', exact=True)).to_be_disabled()
    page.keyboard.press('Escape'); expect(page.get_by_role('dialog')).to_be_visible()
    assert len(delayed) == 1
    # Selecting from the desktop queue invalidates A's dialog; global pending
    # still prevents a consequential action for B.
    page.locator('.queue-row').nth(1).evaluate('node => node.click()')
    expect(page.locator('#packet-title')).to_have_text('Synthetic platform engineer')
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_disabled()
    response = delayed[0].fetch(); delayed[0].fulfill(response=response)
    expect(page.get_by_role('button', name='Approve', exact=True)).to_be_enabled()
    expect(page.locator('#packet-title')).to_have_text('Synthetic platform engineer')
    assert 'Rejection recorded' not in page.locator('.decision-dock').inner_text()
    assert not page.get_by_role('button', name='Next queued job', exact=True).count()
    page.unroute(path)


@pytest.mark.parametrize('mode', ['committed', 'no_commit', 'unknown', 'approve_unknown'])
def test_transport_ambiguity_uses_safe_gets_and_never_replays(decisions, ready, mode):
    page = open_packet(decisions, ready, 390)
    transmitted = []
    action = 'approve' if mode == 'approve_unknown' else 'revise'
    path = f'**/api/packets/{ready[2].id}/{action}'
    def lose_response(route):
        transmitted.append(True)
        if mode in ('committed', 'approve_unknown'):
            response = route.fetch()
            assert response.ok
        if mode == 'unknown': decisions[3][f'/api/packets/{ready[2].id}'] = (503, {'error': {'code': 'storage_unavailable'}})
        route.abort('failed')
    page.route(path, lose_response)
    page.get_by_role('button', name=action.capitalize(), exact=True).click()
    if action == 'revise': page.get_by_label('Revision feedback (required)').fill(' Exact synthetic 😀 feedback ')
    page.get_by_role('button', name='Record approval' if action == 'approve' else 'Record revision request', exact=True).click()
    expected = {'committed': 'Revision request recorded', 'no_commit': 'No decision was found', 'unknown': 'Decision status could not be confirmed', 'approve_unknown': 'original approval evidence could not be confirmed'}[mode]
    expect(page.locator('.decision-dock')).to_contain_text(expected)
    assert len(transmitted) == 1
    assert not page.locator('.phone-caught-up').count()
    if mode == 'unknown': capture(page, 'phone-ambiguous-390x844')
    if mode == 'no_commit':
        page.get_by_role('button', name='Refresh this packet').click()
        expect(page.get_by_role('button', name='Revise', exact=True)).to_be_enabled()
        assert len(transmitted) == 1
    page.unroute(path)


def test_two_tab_conflict_refreshes_history_without_success_or_advancement(decisions, ready):
    page = open_packet(decisions, ready, 390)
    second = decisions[1].new_page(); second.goto(decisions[2] + '/ui'); second.locator('.queue-row').first.click()
    page.get_by_role('button', name='Approve', exact=True).click()
    second.get_by_role('button', name='Reject', exact=True).click(); second.get_by_label('Reason (required)').select_option('other')
    second.get_by_role('button', name='Record rejection', exact=True).click(); expect(second.locator('.decision-dock')).to_contain_text('Rejection recorded')
    page.get_by_role('button', name='Record approval', exact=True).click()
    expect(page.locator('.decision-dock')).to_contain_text('An existing decision prevents this action.')
    assert 'Approval recorded' not in page.locator('.decision-dock').inner_text()
    assert not page.get_by_role('button', name='Next queued job', exact=True).count()
    capture(page, 'phone-conflict-390x844')
    second.close()


def test_pagehide_bfcache_clear_confirmation_and_require_new_bootstrap(decisions, ready):
    page = open_packet(decisions, ready, 390)
    page.get_by_role('button', name='Revise', exact=True).click(); page.get_by_label('Revision feedback (required)').fill('PRIVATE_DRAFT_SENTINEL')
    before = sum(url.endswith('/api/bootstrap') for url in decisions[5])
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
    assert not page.get_by_role('dialog').count()
    assert 'PRIVATE_DRAFT_SENTINEL' not in page.content()
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
    expect(page.get_by_role('button', name='Revise', exact=True)).to_be_enabled()
    assert sum(url.endswith('/api/bootstrap') for url in decisions[5]) > before
    assert not decisions[4]
    page.get_by_role('button', name='Revise', exact=True).click(); expect(page.get_by_label('Revision feedback (required)')).to_have_value('')
    page.keyboard.press('Escape'); page.reload()
    expect(page.locator('.queue-row')).to_have_count(2)
    page.locator('.queue-row').first.click()
    expect(page.get_by_role('button', name='Revise', exact=True)).to_be_enabled()
    assert not decisions[4]


@pytest.mark.parametrize('width', [1440, 390])
def test_durable_visual_evidence_forms_recorded_explicit_next_and_caught_up(decisions, ready, width):
    page = open_packet(decisions, ready, width)
    prefix = 'desktop' if width == 1440 else 'phone'; size = '1440x900' if width == 1440 else '390x844'
    capture(page, f'{prefix}-decision-dock-{size}')
    for action in ('Approve', 'Reject', 'Revise'):
        page.get_by_role('button', name=action, exact=True).click()
        if action == 'Reject':
            page.get_by_label('Reason (required)').select_option('pay'); page.get_by_label('Detail (optional)').fill('Synthetic detail: compensation falls outside this role’s target range.')
        if action == 'Revise': page.get_by_label('Revision feedback (required)').fill('Synthetic feedback: make the opening specific to the company and keep every claim grounded in the existing evidence.')
        capture(page, f'{prefix}-{action.lower()}-confirmation-{size}')
        if action == 'Revise':
            page.get_by_label('Revision feedback (required)').fill('  ')
            page.get_by_role('button', name='Record revision request', exact=True).click()
            expect(page.locator('#decision-validation')).to_be_visible()
            capture(page, f'{prefix}-validation-{size}')
        page.keyboard.press('Escape')
    page.get_by_role('button', name='Approve', exact=True).click(); page.get_by_role('button', name='Record approval', exact=True).click()
    expect(page.get_by_role('button', name='Next queued job', exact=True)).to_be_visible()
    capture(page, f'{prefix}-approval-recorded-{size}')
    page.get_by_role('button', name='Next queued job', exact=True).click()
    expect(page.locator('#packet-title')).to_have_text('Synthetic platform engineer')
    if width == 390: capture(page, f'{prefix}-next-queued-job-{size}')
    # Authoritative first page becomes empty through an isolated second decision.
    if width == 390:
        page.get_by_role('button', name='Reject', exact=True).click(); page.get_by_label('Reason (required)').select_option('not_interested'); page.get_by_role('button', name='Record rejection', exact=True).click()
        expect(page.locator('.decision-dock')).to_contain_text('Rejection recorded')
        page.get_by_role('button', name='Back to queue', exact=True).click()
        expect(page.get_by_role('heading', name='You’re all caught up')).to_be_visible()
        capture(page, f'{prefix}-caught-up-{size}')
