"""Offline Chromium on Python-delivered Next export. Synthetic data only."""
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready
from test_packets import setup

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'frontend/src/fixtures/review.json').read_text())
PACKETS = {p['packet_id']: p for p in FIXTURES['packets']}


def queue_item(packet):
    names = ('packet_id', 'version', 'company', 'title', 'location', 'score', 'tier', 'status', 'ready_at', 'cover_letter_acceptance', 'decision')
    return {**{name: packet[name] for name in names}, 'manual_needed_count': len(packet['screening']['manual_needed']), 'revision_state': packet['revision']['state'] if packet['decision'] == 'revise' else None, 'integrity': 'not_checked'}


@pytest.fixture
def review(ui):
    methods = []
    ui[0].on('request', lambda req: methods.append(req.method))
    def queue(req):
        query = parse_qs(urlsplit(req.url).query); section = query['section'][0]; offset = int(query['offset'][0])
        return {'section': section, 'limit': 25, 'offset': offset, 'items': [queue_item(PACKETS[f'{i:032x}']) for i in FIXTURES['sections'][section]][offset:offset + 25]}
    ui[3]['/api/queue'] = queue
    for identity, packet in PACKETS.items():
        ui[3][f'/api/packets/{identity}'] = copy.deepcopy(packet)
        ui[3][f'/api/packets/{identity}/decision-detail'] = {'decision_id': 'synthetic-record', 'decision': packet['decision'] or 'reject', 'created_at': '2026-10-01T14:10:00Z', 'reason_code': None, 'detail': None, 'feedback': 'Synthetic feedback' if packet['decision'] == 'revise' else None}
    ui[0].add_init_script("window.cspViolations=[];document.addEventListener('securitypolicyviolation',e=>window.cspViolations.push(e.violatedDirective))")
    yield ui
    assert not ui[4], 'Read-only workspace issued POST'
    assert all(method == 'GET' for method in methods), 'Read-only workspace issued a non-GET request'
    assert not any('/api/bootstrap' in url for url in ui[5]), 'Read-only workspace bootstrapped CSRF'
    assert not ui[0].evaluate('window.cspViolations'), 'CSP changed or incompatible runtime styling'


def open_review(review):
    page = review[0]; page.goto(review[2] + '/ui')
    expect(page.locator('.queue-row')).to_have_count(4)
    return page


def close_phone_sheet(page):
    if page.locator('.phone-app').count() and page.get_by_role('dialog').count():
        page.get_by_role('button', name='Close sheet', exact=True).click()


def evidence(page, name):
    if page.locator('.phone-app').count():
        close_phone_sheet(page)
        title = {'Package': 'Packet evidence', 'Screening': 'Screening'}.get(name, name)
        page.locator('.phone-package-row').filter(has=page.get_by_text(title, exact=True)).click()
    else:
        page.get_by_role('tablist', name='Evidence tabs').get_by_role('tab', name=name, exact=True).click()


def select(review, index=1):
    page = review[0]
    page.get_by_role('button', name=f"{PACKETS[f'{index:032x}']['company']} ").click()
    expect(page.locator('#packet-title')).to_have_text(PACKETS[f'{index:032x}']['title'])
    return page


@pytest.mark.parametrize('size', [(1440, 1000), (1024, 900), (768, 900), (390, 844), (320, 700)])
def test_responsive_review_exact_evidence_and_no_actions(review, size):
    page = review[0]; page.set_viewport_size({'width': size[0], 'height': size[1]}); open_review(review); select(review)
    expect(page.locator('.integrity-strip')).to_contain_text('Not authorized')
    evidence(page, 'Cover letter'); expect(page.locator('.cover-text')).to_have_text(PACKETS[f'{1:032x}']['cover_text'])
    evidence(page, 'History'); expect(page.locator('.fingerprint').first).to_have_text('a' * 64)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    close_phone_sheet(page)
    assert page.get_by_role('link', name='Open trusted decision UI').get_attribute('href') == '/'
    assert not page.get_by_role('button', name='Approve', exact=True).count()
    assert not page.get_by_role('button', name='Reject', exact=True).count()
    assert not page.get_by_role('button', name='Revise', exact=True).count()
    assert not any('bootstrap' in url for url in review[5])
    page.get_by_role('button', name='Back to queue', exact=True).click()
    expect(page.locator('.queue-row').first).to_be_focused()
    expect(page.locator('.queue-row')).to_have_count(4)


def test_keyboard_tabs_skip_focus_and_touch_targets(review):
    page = open_review(review)
    page.keyboard.press('Tab'); expect(page.get_by_role('link', name='Skip to approval queue')).to_be_focused()
    page.keyboard.press('Enter'); expect(page.locator('#main')).to_be_focused()
    tab = page.get_by_role('tab', name='Needs review', exact=True); tab.focus()
    assert tab.evaluate('n=>getComputedStyle(n).outlineStyle') != 'none'
    page.keyboard.press('ArrowRight'); expect(page.get_by_role('tab', name='Processing', exact=True)).to_be_focused()
    # Manual activation keeps the current queue until Enter.
    expect(page.locator('.queue-row')).to_have_count(4)
    page.keyboard.press('Enter'); expect(page.locator('.queue-row')).to_have_count(1)
    page.get_by_role('tab', name='Needs review', exact=True).click(); expect(page.locator('.queue-row')).to_have_count(4)
    page.locator('.queue-row').first.focus(); page.keyboard.press('Enter'); expect(page.locator('#packet-title')).to_be_focused()
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('.phone-app .phone-hero')).to_be_visible()
    for node in page.locator('button:visible, a.button:visible').all(): assert node.bounding_box()['height'] >= 44


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_system_schemes_preserve_approved_dark_reduced_motion_contrast_and_screenshots(review, theme):
    page = review[0]; page.emulate_media(color_scheme=theme, reduced_motion='reduce'); open_review(review)
    assert page.locator('.app').evaluate('n=>getComputedStyle(n).colorScheme') == 'dark'
    assert page.locator('.queue-row').first.evaluate('n=>getComputedStyle(n).animationName') == 'none'
    def assert_contrast(selector):
        ratio = page.locator(selector).first.evaluate(r'''n => {
          const channels = value => value.match(/[\d.]+/g).map(Number);
          const luminance = value => {const [r,g,b]=value.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
          const parents=[];for(let p=n;p;p=p.parentElement)parents.unshift(p);
          let background=[7,13,26];
          for(const p of parents){const c=channels(getComputedStyle(p).backgroundColor);const alpha=c[3]??1;background=background.map((v,i)=>c[i]*alpha+v*(1-alpha));}
          const a=luminance(channels(getComputedStyle(n).color)), b=luminance(background);
          return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        }''')
        assert ratio >= 4.5, (selector, theme, ratio)
    for selector in ('.muted', '.row-title', '.row-evidence', '.nav-current', '.eyebrow', '.manual-badge'):
        assert_contrast(selector)
    output = ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions'; output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'desktop-queue-{theme}.png'), full_page=True)
    select(review)
    assert page.locator('.ring-value').evaluate('n=>getComputedStyle(n).animationName') == 'none'
    for selector in ('.score', '.signal-note', '.status-badge', '.decision-handoff p'):
        assert_contrast(selector)
    assert page.locator('.primary').evaluate("n=>getComputedStyle(n).color") == 'rgb(4, 22, 26)'
    assert page.locator('.primary').evaluate("n=>getComputedStyle(n).backgroundImage.includes('111, 216, 203')")
    for background in ([111,216,203], [94,196,224]):
        ratio = page.locator('.primary').evaluate(r"""(n,b) => {
          const l=c=>{const [r,g,b]=c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
          const a=l(getComputedStyle(n).color.match(/[\d.]+/g).slice(0,3).map(Number)), z=l(b);return(Math.max(a,z)+.05)/(Math.min(a,z)+.05);
        }""", background)
        assert ratio >= 4.5
    page.screenshot(path=str(output / f'desktop-inspector-{theme}.png'), full_page=True)
    evidence(page, 'Cover letter'); assert_contrast('.cover-text')
    evidence(page, 'History'); assert_contrast('.current-badge')


def test_historical_stale_current_revision_unavailable_and_long_states(review):
    page = open_review(review)
    select(review, 3); evidence(page, 'Cover letter'); expect(page.get_by_text('Cover text unavailable.', exact=True)).to_be_visible()
    expect(page.get_by_text('Location unavailable', exact=True)).to_have_count(3)
    page.get_by_role('button', name='Back to queue', exact=True).click(); select(review, 9)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Back to queue', exact=True).click()
    page.get_by_role('tablist', name='Queue section').get_by_role('tab', name='History', exact=True).click(); expect(page.locator('.queue-row')).to_have_count(3)
    select(review, 6); expect(page.locator('.integrity-strip')).to_contain_text('Historical approval')
    expect(page.locator('.integrity-strip')).to_contain_text('Evidence changed: authorization stale')
    page.get_by_role('button', name='Back to queue', exact=True).click(); select(review, 7)
    expect(page.locator('.integrity-strip')).to_contain_text('Current authorization valid')
    page.get_by_role('button', name='Back to queue', exact=True).click()
    page.get_by_role('tab', name='Processing', exact=True).click(); expect(page.locator('.queue-row')).to_have_count(1)
    select(review, 4); evidence(page, 'History'); expect(page.get_by_text('Revision queued; awaiting worker', exact=True)).to_be_visible()
    page.get_by_role('button', name='Back to queue', exact=True).click()
    page.get_by_role('tab', name='Needs attention', exact=True).click(); expect(page.locator('.queue-row')).to_have_count(1)
    select(review, 5); evidence(page, 'Cover letter'); expect(page.get_by_text('Cover integrity failed. Text withheld.', exact=True)).to_be_visible()


def test_diff_availability_and_exact_content(review):
    page = open_review(review); select(review)
    path = f"/api/packets/{90:032x}/diff/cover/{1:032x}"
    response = {'kind': 'cover', 'left_packet_id': f'{90:032x}', 'left_version': 1, 'right_packet_id': f'{1:032x}', 'right_version': 2, 'status': 'available', 'diff': '- Synthetic previous text\n+ Synthetic current text'}
    review[3][path] = response
    evidence(page, 'History')
    page.get_by_role('button', name='Cover diff v1', exact=True).click(); expect(page.locator('.diff-text')).to_have_text(response['diff'])
    review[3][path] = {**response, 'status': 'integrity_failed', 'diff': 'PRIVATE_TEXT_MUST_BE_WITHHELD'}
    page.get_by_role('button', name='Cover diff v1', exact=True).click()
    expect(page.get_by_text('Comparison integrity failed.', exact=True)).to_be_visible()
    assert not page.get_by_text('PRIVATE_TEXT_MUST_BE_WITHHELD').count()


def test_untrusted_text_urls_and_csp_remain_inert(review):
    p = review[3][f'/api/packets/{1:032x}']
    attack = '<img src="https://evil.invalid/x" onerror="window.pwned=1"><script>window.pwned=1</script>'
    p['cover_text'] = attack; p['company_facts'][0]['source_url'] = 'javascript:alert(1)'
    page = open_review(review); select(review)
    evidence(page, 'Cover letter'); expect(page.locator('.cover-text')).to_have_text(attack)
    assert not page.locator('.cover-text img, .cover-text script').count()
    assert page.evaluate('window.pwned === undefined')
    assert not page.locator('a[href^="javascript:"]').count()
    # Browser actually enforces the original inline-script prohibition.
    page.evaluate("()=>{const s=document.createElement('script');s.textContent='window.inlineRan=true';document.head.append(s)}")
    assert page.evaluate('window.inlineRan === undefined')
    assert 'script-src-elem' in page.evaluate('window.cspViolations')
    page.evaluate('window.cspViolations=[]')


def test_errors_empty_unknown_and_no_stale_packet_retention(review):
    page = open_review(review); select(review)
    review[3][f'/api/packets/{1:032x}'] = (409, {'error': {'code': 'stale_packet', 'detail': 'PRIVATE_CONFIG'}})
    page.get_by_role('button', name='Reload evidence').click()
    expect(page.get_by_text('Evidence changed during this read. Reload to review the current packet.', exact=True)).to_be_visible()
    assert not page.locator('.cover-text').count()
    assert not page.get_by_text('PRIVATE_CONFIG').count()
    page.get_by_role('button', name='Back to queue', exact=True).click()
    review[3]['/api/queue'] = {'section': 'needs-review', 'limit': 25, 'offset': 0, 'items': []}
    page.get_by_role('button', name='Reload evidence').click(); expect(page.get_by_text('No packets on this page.', exact=True)).to_be_visible()
    review[3]['/api/queue'] = {'section': 'needs-review', 'limit': 25, 'offset': 0, 'items': [{**queue_item(PACKETS[f'{1:032x}']), 'integrity': 'maybe_fine'}]}
    page.get_by_role('button', name='Reload evidence').click()
    expect(page.get_by_text('Review unavailable. Retry, or open the trusted decision UI.', exact=True)).to_be_visible()


def test_pagination_preserves_section_offsets_without_fake_totals(review):
    def pages(req):
        query = parse_qs(urlsplit(req.url).query); section = query['section'][0]; offset = int(query['offset'][0])
        return {'section': section, 'limit': 25, 'offset': offset, 'items': [queue_item(PACKETS[f'{1:032x}']) | {'packet_id': f'{i + 100:032x}'} for i in range(25)] if offset == 0 else []}
    review[3]['/api/queue'] = pages
    page = review[0]; page.goto(review[2] + '/ui'); expect(page.locator('.queue-row')).to_have_count(25)
    page.get_by_role('button', name='Next queue page').click(); expect(page.get_by_text('No packets on this page.', exact=True)).to_be_visible()
    page.get_by_role('tablist', name='Queue section').get_by_role('tab', name='History', exact=True).click(); expect(page.locator('.queue-row')).to_have_count(25)
    page.get_by_role('tab', name='Needs review', exact=True).click(); expect(page.get_by_text('Page 2', exact=True)).to_be_visible()
    page.get_by_role('button', name='Previous queue page').click(); expect(page.locator('.queue-row')).to_have_count(25)


def test_actual_protected_api_integration_and_test_database_unchanged(ui, ready):
    before = (ready[4] / 'test.sqlite').read_bytes()
    page = ui[0]; page.goto(ui[2] + '/ui'); expect(page.locator('.queue-row')).to_have_count(1)
    page.locator('.queue-row').click(); evidence(page, 'Cover letter'); expect(page.locator('.cover-text')).to_have_text(ready[2].cover_letter)
    assert not ui[4]
    assert before == (ready[4] / 'test.sqlite').read_bytes()


@pytest.mark.parametrize('width', [320, 390, 768, 1024, 1440])
def test_mobile_text_zoom_reflow(review, width):
    page = review[0]; page.set_viewport_size({'width': width, 'height': 900}); open_review(review); select(review, 9)
    page.evaluate("document.documentElement.style.fontSize='200%'")
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    handoff = page.locator('.decision-handoff')
    box = handoff.bounding_box()
    assert box['y'] >= 0 and box['y'] + box['height'] <= 900
    evidence(page, 'History'); page.locator('.fingerprint').first.scroll_into_view_if_needed()
    identity = page.locator('.fingerprint').first.bounding_box()
    if page.locator('.phone-app').count():
        assert identity['y'] + identity['height'] <= page.locator('.phone-sheet').bounding_box()['y'] + page.locator('.phone-sheet').bounding_box()['height']
        close_phone_sheet(page)
    else:
        assert identity['y'] + identity['height'] <= handoff.bounding_box()['y']
    page.get_by_role('button', name='Back to queue', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_page_lifecycle_clears_private_snapshot_and_rereads(review):
    page = open_review(review); select(review); evidence(page, 'Cover letter')
    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert page.locator('.cover-text').count() == 0
    assert page.locator('.queue-row').count() == 0
    before = len(review[5])
    page.evaluate("window.dispatchEvent(new Event('pageshow'))")
    expect(page.locator('#packet-title')).to_be_visible(); evidence(page, 'Cover letter')
    expect(page.locator('.cover-text')).to_have_text(PACKETS[f'{1:032x}']['cover_text'])
    assert len(review[5]) > before


@pytest.mark.parametrize('size', [(1440, 900), (1024, 900), (768, 900), (390, 844), (320, 700)])
def test_summary_uses_packet_evidence_and_handoff_stays_reachable(review, size):
    page = review[0]; page.set_viewport_size({'width': size[0], 'height': size[1]})
    open_review(review); select(review)
    meter = page.get_by_role('meter', name='Job fit score')
    expect(meter).to_have_attribute('aria-valuenow', str(PACKETS[f'{1:032x}']['score']))
    if page.locator('.phone-app').count():
        evidence(page, 'Package')
    expect(page.locator('.packet-signals')).to_contain_text('Resume PDFAvailable')
    expect(page.locator('.packet-signals')).to_contain_text('Latest ready')
    expect(page.locator('.packet-signals')).to_contain_text('0 to review')
    evidence(page, 'History'); expect(page.locator('.history-current')).to_contain_text('Viewing')
    handoff = page.get_by_role('link', name='Open trusted decision UI')
    def in_viewport():
        close_phone_sheet(page)
        box = handoff.bounding_box()
        assert box['y'] >= 0 and box['y'] + box['height'] <= size[1]
        assert handoff.evaluate('n => {const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}')
    in_viewport()
    evidence(page, 'Cover letter'); page.locator('.cover-text').scroll_into_view_if_needed(); in_viewport()
    evidence(page, 'History'); page.locator('.fingerprint').first.scroll_into_view_if_needed(); in_viewport()
    page.get_by_role('button', name='Back to queue', exact=True).click()
    expect(page.locator('.queue-row').first).to_be_focused()
    select(review, 3)
    if page.locator('.phone-app').count():
        evidence(page, 'Package')
    expect(page.locator('.packet-signals')).to_contain_text('Resume PDFUnavailable')
    expect(page.locator('.packet-signals')).to_contain_text('Cover unavailable')


@pytest.mark.parametrize('width', [1024, 1440])
def test_approved_desktop_composition_and_capture(review, width):
    page = review[0]; page.set_viewport_size({'width': width, 'height': 900})
    page.emulate_media(reduced_motion='reduce')
    open_review(review); select(review)
    output = ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions'; output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'first-review-{width}x900.png'))
    assert page.evaluate('document.documentElement.scrollHeight <= innerHeight')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.app-rail').bounding_box()['width'] == 64
    assert page.locator('.queue-pane').bounding_box()['width'] == (300 if width == 1440 else 260)
    expect(page.get_by_role('tablist', name='Evidence tabs').get_by_role('tab')).to_have_count(6)
    expect(page.get_by_role('tablist', name='Evidence tabs').get_by_role('tab', name='Package', exact=True)).to_have_attribute('aria-selected', 'true')
    expect(page.locator('.interview-tile')).to_contain_text('Not available yet')
    expect(page.locator('.people-tile')).to_contain_text('Not available yet')
    expect(page.locator('.resume-tile')).to_contain_text('Match Not available yet')
    expect(page.locator('.location-tile')).to_contain_text('Not stated')
    for text in ['40 / 30', 'rubric v3', '8 of 9 requirements', 'Sarah Chen', 'days to', 'applications submitted']:
        assert text not in page.locator('.app').inner_text()
    dock = page.locator('.decision-handoff').bounding_box()
    hero = page.locator('.job-hero').bounding_box()
    panes = page.locator('.review-panes').bounding_box()
    assert hero['y'] + hero['height'] <= panes['y']
    assert panes['y'] + panes['height'] <= dock['y']
    assert dock['y'] + dock['height'] <= 900
    output = ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions'; output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f'review-{width}x900.png'))
    if width == 1440:
        page.get_by_role('button', name='Why this score', exact=False).click()
        expect(page.get_by_role('region', name='Score explanation')).to_contain_text('Detailed score breakdown not available yet')
        page.screenshot(path=str(output / 'score-1440x900.png'))
        page.keyboard.press('Escape')
        assert not page.get_by_role('region', name='Score explanation').count()
        evidence(page, 'People'); expect(page.locator('.people-unavailable')).to_contain_text('Not available yet')
        page.screenshot(path=str(output / 'people-1440x900.png'))


def test_read_only_reader_keyboard_focus_exact_text_and_selection_reset(review):
    page = open_review(review); select(review); evidence(page, 'Cover letter')
    opener = page.get_by_role('button', name='Open full view'); opener.click()
    dialog = page.get_by_role('dialog', name='Cover letter')
    expect(dialog).to_be_visible()
    expect(dialog.locator('.reader-text')).to_have_text(PACKETS[f'{1:032x}']['cover_text'])
    expect(page.get_by_role('button', name='Close reader')).to_be_focused()
    page.keyboard.press('Shift+Tab'); expect(dialog.locator('.reader-scroll')).to_be_focused()
    page.keyboard.press('Tab'); expect(page.get_by_role('button', name='Close reader')).to_be_focused()
    (ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions').mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions/reader-1440x900.png'))
    page.keyboard.press('Escape'); expect(opener).to_be_focused()
    assert not dialog.count()
    select(review, 2)
    expect(page.get_by_role('tablist', name='Evidence tabs').get_by_role('tab', name='Package', exact=True)).to_have_attribute('aria-selected', 'true')
    assert not page.locator('.cover-text').count()
    assert not page.get_by_role('dialog').count()
    assert not page.get_by_role('region', name='Score explanation').count()


def test_successful_empty_first_page_has_no_invented_outcomes(review):
    review[3]['/api/queue'] = {'section': 'needs-review', 'limit': 25, 'offset': 0, 'items': []}
    page = review[0]; page.goto(review[2] + '/ui')
    expect(page.get_by_role('heading', name='You’re all caught up')).to_be_visible()
    expect(page.get_by_text('No packets currently need review.', exact=True)).to_be_visible()
    assert not page.locator('.decision-handoff').count()
    (ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions').mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ROOT / 'docs/run5b/phone-implementation-evidence/desktop-regressions/empty-1440x900.png'))


def test_pending_old_selection_cannot_replace_current_packet(review):
    page = open_review(review)
    delayed = []
    path = f'**/api/packets/{1:032x}'
    page.route(path, lambda route: delayed.append(route))
    page.locator('.queue-row').first.click()
    expect(page.get_by_text('Loading packet evidence.', exact=True)).to_be_visible()
    assert delayed
    select(review, 2)
    # An aborted old request can finish at the server without restoring old private data.
    try:
        delayed[0].fulfill(json=PACKETS[f'{1:032x}'])
    except Exception as exc:
        assert 'Invalid InterceptionId' in str(exc) or 'Target' in str(exc)
    expect(page.locator('#packet-title')).to_have_text(PACKETS[f'{2:032x}']['title'])
    assert not page.locator('.cover-text').count()
    page.unroute(path)


def test_company_palette_text_contrast_and_independent_panel_scrolling(review):
    packet = review[3][f'/api/packets/{1:032x}']
    packet['reasons'] = ['Synthetic fit evidence for scrolling: ' + 'reviewable evidence ' * 8 for _ in range(8)]
    packet['company_facts'] *= 8
    page = open_review(review); select(review)
    for theme in ['teal', 'indigo', 'purple', 'copper', 'navy']:
        ratios = page.locator('.inspector').evaluate(r'''(n,theme) => {
          n.className='inspector theme-'+theme;
          const colors=getComputedStyle(n.querySelector('.job-hero')).backgroundImage.match(/rgba?\([^)]+\)/g).map(c=>c.match(/[\d.]+/g).slice(0,3).map(Number));
          const luminance=c=>{const [r,g,b]=c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
          return ['.company-label','.hero-version','#packet-title','.job-location','.status-badge','.fit-description>strong','.fit-description>span','.score'].flatMap(s=>{
            const a=luminance(getComputedStyle(n.querySelector(s)).color.match(/[\d.]+/g).slice(0,3).map(Number));
            return colors.map(c=>{const b=luminance(c);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
          });
        }''', theme)
        assert ratios and min(ratios) >= 4.5, (theme, ratios)
    for selector in ['.left-detail', '.evidence-content']:
        assert page.locator(selector).evaluate('n=>n.scrollHeight>n.clientHeight')
        page.locator(selector).evaluate('n=>n.scrollTop=n.scrollHeight')
        assert page.locator(selector).evaluate('n=>n.scrollTop>0')
    expect(page.locator('.facts li').last).to_be_in_viewport()
    assert page.evaluate('document.documentElement.scrollHeight<=innerHeight')
    assert page.locator('.decision-handoff').bounding_box()['y'] + page.locator('.decision-handoff').bounding_box()['height'] <= 900


def test_known_demo_identity_is_subordinate_and_unknown_company_stays_exact(review):
    page = open_review(review); select(review)
    expect(page.locator('.inspector')).to_have_class('inspector theme-teal')
    expect(page.locator('.company-label')).to_have_text('Northstar InstrumentsDEMO')
    expect(page.locator('.company-label .company-identity')).to_have_attribute('aria-label', PACKETS[f'{1:032x}']['company'])
    expect(page.locator('.decision-handoff')).to_contain_text('Reviewing packet v2 · Northstar InstrumentsDEMO')
    expect(page.locator('.queue-row').first).to_have_attribute('aria-label', PACKETS[f'{1:032x}']['company'] + ' ' + PACKETS[f'{1:032x}']['title'])
    page.get_by_role('button', name='Back to queue', exact=True).click()
    review[3][f'/api/packets/{1:032x}']['company'] = 'Synthetic · Arbitrary Production Name'
    select(review)
    expect(page.locator('.company-label')).to_have_text('Synthetic · Arbitrary Production Name')
    assert not page.locator('.company-label .demo-label').count()
