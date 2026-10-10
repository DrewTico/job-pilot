"""Dedicated phone review on the Python-delivered export under its real CSP.

All packets are isolated synthetic fixtures. Requests remain confined to the
fixture's loopback origin; production SQLite is never a writable test target.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect

from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready
from test_packets import setup
from test_frontend_ui_dom import PACKETS, FIXTURES, queue_item, review

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/run5b/phone-implementation-evidence'


def phone(review, width=390):
    page = review[0]
    page.set_viewport_size({'width': width, 'height': 844})
    page.emulate_media(reduced_motion='reduce')
    page.goto(review[2] + '/ui')
    expect(page.locator('.phone-app')).to_be_visible()
    expect(page.locator('.queue-row')).to_have_count(4)
    return page


def choose(page, index=0):
    page.locator('.queue-row').nth(index).click()
    expect(page.locator('.phone-hero')).to_be_visible()


def sheet(page, name):
    if page.get_by_role('dialog').count():
        page.get_by_role('button', name='Close sheet', exact=True).click()
    page.locator('.phone-package-row').filter(has=page.get_by_text(name, exact=True)).click()
    expect(page.get_by_role('dialog')).to_be_visible()


def capture(page, name):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE / f'{name}-390x844.png'))


def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def targets(page):
    assert page.locator('button:not(:disabled), a[href], select').evaluate_all('''nodes => nodes.filter(n => n.getClientRects().length && !n.closest('[inert]') && !n.classList.contains('skip-link')).every(n => {const r=n.getBoundingClientRect();return r.width>=44 && r.height>=44})''')


@pytest.mark.parametrize('width', [360, 390, 430, 480])
def test_phone_composition_navigation_and_touch_targets(review, width):
    page = phone(review, width)
    assert not page.locator('.app-rail, .queue-pane, .evidence-panel').count()
    no_overflow(page); targets(page)
    expect(page.locator('.phone-bottom-nav [aria-current]')).to_have_text('Review')
    choose(page)
    expect(page.locator('#packet-title')).to_be_focused()
    expect(page.get_by_role('meter', name='Job fit score')).to_have_attribute('aria-valuenow', '94')
    assert page.locator('.phone-must-see').evaluate('n=>getComputedStyle(n).gridTemplateColumns.split(" ").length') == 2
    no_overflow(page); targets(page)
    dock = page.locator('.phone-handoff').bounding_box()
    assert dock['x'] == 0 and dock['width'] == width and dock['y'] + dock['height'] <= 844
    assert page.locator('.phone-review-content').evaluate('n=>parseFloat(getComputedStyle(n).paddingBottom)') >= dock['height']
    assert 'env(safe-area-inset-bottom)' in (ROOT / 'frontend/src/styles/phone.css').read_text()
    first_theme = page.locator('.phone-review').get_attribute('class')
    page.get_by_role('button', name='Next loaded job', exact=True).click()
    expect(page.locator('#packet-title')).to_have_text(PACKETS[f'{2:032x}']['title'])
    assert page.locator('.phone-review').get_attribute('class') != first_theme
    assert not page.locator('.cover-text, .phone-sheet').count()
    page.get_by_role('button', name='Previous loaded job', exact=True).click()
    expect(page.locator('#packet-title')).to_have_text(PACKETS[f'{1:032x}']['title'])
    page.get_by_role('button', name='Back to queue', exact=True).click()
    expect(page.locator('.queue-row').first).to_be_focused()
    assert not any('bootstrap' in url for url in review[5])
    assert not review[4]


def test_phone_visual_evidence_and_read_only_sheets(review):
    page = phone(review)
    capture(page, 'p1-queue')
    choose(page); capture(page, 'p2-review-top')
    page.locator('.phone-why-watch').evaluate('n=>window.scrollTo(0,window.scrollY+n.getBoundingClientRect().top-180)')
    capture(page, 'p3-review-scrolled')
    page.evaluate('window.scrollTo(0,0)')
    why = page.get_by_role('button', name='Why this score:', exact=False)
    why.click()
    dialog = page.get_by_role('dialog', name='Why 94?')
    expect(dialog).to_contain_text('Detailed score breakdown not available yet.')
    assert '40%' not in dialog.inner_text()
    capture(page, 'p4-why')
    expect(page.get_by_role('button', name='Close sheet')).to_be_focused()
    page.keyboard.press('Shift+Tab'); expect(page.locator('.phone-sheet-scroll')).to_be_focused()
    page.keyboard.press('Tab'); expect(page.get_by_role('button', name='Close sheet')).to_be_focused()
    assert page.locator('.phone-sheet').evaluate('n=>getComputedStyle(n).animationName') == 'none'
    assert page.locator('.ring-value').evaluate('n=>getComputedStyle(n).animationName') == 'none'
    page.keyboard.press('Escape'); expect(why).to_be_focused()
    assert not page.evaluate('document.documentElement.classList.contains("phone-sheet-open")')
    sheet(page, 'People')
    expect(page.get_by_role('dialog', name='Right people')).to_contain_text('Not available yet')
    assert not page.locator('a[href^="mailto:"]').count()
    capture(page, 'p5-people-unavailable')
    sheet(page, 'Cover letter')
    expect(page.locator('.reader-text')).to_have_text(PACKETS[f'{1:032x}']['cover_text'])
    assert page.locator('.reader-text').evaluate('n=>getComputedStyle(n).fontFamily').startswith('Newsreader')
    capture(page, 'p8-letter')
    sheet(page, 'Screening'); expect(page.get_by_role('dialog')).to_contain_text('Manual review needed')
    assert not page.locator('input, textarea').count()
    sheet(page, 'History'); expect(page.locator('.fingerprint').first).to_have_text('a' * 64)
    capture(page, 'history')
    # Backdrop dismisses the modal and returns focus to its opener.
    page.locator('.phone-sheet-backdrop').click(position={'x': 8, 'y': 8})
    assert not page.get_by_role('dialog').count()
    expect(page.locator('.phone-package-row').filter(has=page.get_by_text('History', exact=True))).to_be_focused()
    page.get_by_role('button', name='Next loaded job', exact=True).click()
    expect(page.locator('.phone-hero')).to_be_visible(); capture(page, 'p10-second-company')
    assert not page.get_by_role('button', name='Approve', exact=True).count()
    assert not page.get_by_role('button', name='Revise', exact=True).count()
    assert not page.get_by_role('button', name='Reject', exact=True).count()


def test_phone_empty_loading_api_error_and_integrity_evidence(review):
    page = phone(review)
    review[3]['/api/queue'] = {'section': 'needs-review', 'limit': 25, 'offset': 0, 'items': []}
    page.get_by_role('button', name='Reload evidence').click()
    expect(page.get_by_role('heading', name='You’re all caught up')).to_be_visible()
    capture(page, 'p11-caught-up')
    assert not page.locator('.phone-handoff').count()
    review[3]['/api/queue'] = (500, {'error': {'code': 'unavailable', 'detail': 'PRIVATE_SECRET'}})
    page.get_by_role('button', name='Reload evidence').click()
    expect(page.locator('.phone-queue-status[role=alert]')).to_have_text('Review unavailable. Retry, or open the trusted decision UI.'); capture(page, 'queue-error')
    assert not page.get_by_text('PRIVATE_SECRET').count()
    assert not page.locator('.phone-caught-up').count()
    page.reload()
    pending = []
    page.route('**/api/queue?*', lambda route: pending.append(route))
    page.get_by_role('button', name='Reload evidence').click()
    expect(page.get_by_text('Loading protected queue.', exact=True)).to_be_visible()
    capture(page, 'queue-loading')
    pending[-1].fulfill(json={'section': 'needs-review', 'limit': 25, 'offset': 0, 'items': [queue_item(PACKETS[f'{5:032x}'])]})
    choose(page)
    sheet(page, 'Cover letter')
    expect(page.get_by_role('dialog')).to_contain_text('Cover integrity failed. Text withheld.')
    assert not page.locator('.reader-text').count()
    capture(page, 'integrity-failed')


@pytest.mark.parametrize('width', [360, 390, 430, 480])
def test_phone_long_text_missing_location_and_zoom(review, width):
    p = review[3][f'/api/packets/{9:032x}']
    p['location'] = None
    p['company'] = 'Synthetic · Long Company Evidence Cooperative for Accessible Application Review and Authenticated Research'
    p['title'] = 'Software Engineer for Accessible Long Form Research Collections and Authenticated Application Evidence Review'
    p['reasons'] = ['Synthetic requirement ' + 'W' * 90]
    page = phone(review, width); choose(page, 3)
    expect(page.locator('.company-label .company-identity')).to_have_attribute('aria-label', p['company'])
    expect(page.locator('.phone-hero')).to_contain_text('Location unavailable')
    expect(page.locator('#packet-title')).to_have_text(p['title'])
    no_overflow(page)
    page.evaluate("document.documentElement.style.fontSize='200%'")
    no_overflow(page)
    page.evaluate('window.scrollTo(0,document.documentElement.scrollHeight)')
    progression = page.get_by_role('button', name='Previous loaded job', exact=True).bounding_box()
    assert progression['y'] + progression['height'] <= page.locator('.phone-handoff').bounding_box()['y']
    sheet(page, 'People'); no_overflow(page)
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Back to queue', exact=True).click(); no_overflow(page)


def test_phone_selection_privacy_late_read_and_page_lifecycle(review):
    page = phone(review)
    choose(page)
    sheet(page, 'Cover letter')
    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert not page.locator('.reader-text, .phone-hero, .queue-row').count()
    assert not page.evaluate('document.documentElement.classList.contains("phone-sheet-open")')
    page.evaluate("window.dispatchEvent(new Event('pageshow'))")
    expect(page.locator('.phone-hero')).to_be_visible()
    assert not page.get_by_role('dialog').count()
    sheet(page, 'Cover letter'); page.keyboard.press('Escape')
    delayed = []
    path = f'**/api/packets/{2:032x}'
    page.route(path, lambda route: delayed.append(route))
    page.get_by_role('button', name='Next loaded job', exact=True).click()
    expect(page.get_by_text('Loading packet evidence.', exact=True)).to_be_visible()
    assert not page.locator('.reader-text, .phone-hero, .phone-handoff').count()
    assert delayed
    page.get_by_role('button', name='Back to queue', exact=True).click()
    choose(page)
    try:
        delayed[0].fulfill(json=PACKETS[f'{2:032x}'])
    except Exception as exc:
        assert 'Invalid InterceptionId' in str(exc) or 'Target' in str(exc)
    expect(page.locator('#packet-title')).to_have_text(PACKETS[f'{1:032x}']['title'])
    assert not page.get_by_role('dialog').count()


def test_phone_later_empty_page_never_claims_caught_up(review):
    def pages(req):
        query = parse_qs(urlsplit(req.url).query)
        offset = int(query['offset'][0])
        return {'section': query['section'][0], 'limit': 25, 'offset': offset, 'items': [queue_item(PACKETS[f'{1:032x}']) | {'packet_id': f'{i + 100:032x}'} for i in range(25)] if offset == 0 else []}
    review[3]['/api/queue'] = pages
    page = review[0]; page.set_viewport_size({'width': 390, 'height': 844}); page.goto(review[2] + '/ui')
    expect(page.locator('.queue-row')).to_have_count(25)
    page.get_by_role('button', name='Next queue page').click()
    expect(page.get_by_text('No packets on this page.', exact=True)).to_be_visible()
    assert not page.locator('.phone-caught-up').count()
    page.get_by_role('button', name='Previous queue page').click()
    expect(page.locator('.queue-row')).to_have_count(25)


def test_phone_authenticated_diff_exact_content_and_failure_withholding(review):
    page = phone(review); choose(page); sheet(page, 'History')
    path = f'/api/packets/{90:032x}/diff/cover/{1:032x}'
    data = {'kind': 'cover', 'left_packet_id': f'{90:032x}', 'left_version': 1, 'right_packet_id': f'{1:032x}', 'right_version': 2, 'status': 'available', 'diff': '- Synthetic previous text\n+ Synthetic current text'}
    review[3][path] = data
    page.get_by_role('button', name='Cover diff v1').click(); expect(page.locator('.diff-text')).to_have_text(data['diff'])
    review[3][path] = {**data, 'status': 'integrity_failed', 'diff': 'PRIVATE_DIFF'}
    page.get_by_role('button', name='Cover diff v1').click()
    expect(page.get_by_text('Comparison integrity failed.', exact=True)).to_be_visible()
    assert not page.locator('.diff-text').count()
    assert not page.get_by_text('PRIVATE_DIFF').count()


@pytest.mark.parametrize('code, text', [
    ('authentication_required', 'Access unavailable. Reopen Job Pilot through your authorized connection.'),
    ('packet_integrity_failed', 'Packet integrity could not be verified. Review it in the trusted decision UI.'),
])
def test_phone_packet_failures_never_render_caught_up_or_private_evidence(review, code, text):
    page = phone(review)
    review[3][f'/api/packets/{1:032x}'] = (403 if code == 'authentication_required' else 409, {'error': {'code': code, 'detail': 'PRIVATE_CONFIG'}})
    page.locator('.queue-row').first.click()
    expect(page.locator('.phone-packet-state [role=alert]')).to_have_text(text)
    assert not page.locator('.phone-hero, .phone-caught-up, .reader-text, .phone-handoff').count()
    assert not page.get_by_text('PRIVATE_CONFIG').count()
    page.get_by_role('button', name='Back to queue').click()
    expect(page.locator('.queue-row').first).to_be_focused()


def test_phone_long_document_scroll_focus_and_actual_fonts(review):
    from test_frontend_font_dom import assert_font
    packet = review[3][f'/api/packets/{1:032x}']
    packet['cover_text'] = (packet['cover_text'] + '\n\n') * 20
    page = phone(review); choose(page)
    assert_font(page, '#packet-title', 'Bricolage Grotesque')
    assert_font(page, '.hero-version', 'Geist')
    sheet(page, 'Cover letter')
    expect(page.locator('.reader-text')).to_have_text(packet['cover_text'])
    assert_font(page, '.reader-text', 'Newsreader')
    scroller = page.locator('.phone-sheet-scroll')
    assert scroller.evaluate('n=>n.scrollHeight>n.clientHeight')
    scroller.evaluate('n=>n.scrollTop=n.scrollHeight')
    assert scroller.evaluate('n=>n.scrollTop>0')
    expect(page.get_by_role('button', name='Close sheet')).to_be_in_viewport()
    page.locator('.phone-review-nav button').first.evaluate('n=>n.focus()')
    assert page.evaluate('document.activeElement.closest("[role=dialog]") !== null')
    page.keyboard.press('Escape')
    assert not page.evaluate('document.documentElement.classList.contains("phone-sheet-open")')
    sheet(page, 'History'); assert_font(page, '.fingerprint', 'Geist Mono')


def test_phone_palette_and_unavailable_text_contrast(review):
    page = phone(review); choose(page)
    for theme in ['teal', 'indigo', 'purple', 'copper', 'navy']:
        ratios = page.locator('.phone-review').evaluate(r'''(n,theme) => {
          n.className='phone-review theme-'+theme;
          const colors=getComputedStyle(n.querySelector('.phone-hero')).backgroundImage.match(/rgba?\([^)]+\)/g).map(c=>c.match(/[\d.]+/g).slice(0,3).map(Number));
          const l=c=>{const [r,g,b]=c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
          return ['.company-label','.hero-version','#packet-title','.job-location','.phone-relocation','.fit-description>strong','.fit-description>span','.score'].flatMap(s=>{
            const a=l(getComputedStyle(n.querySelector(s)).color.match(/[\d.]+/g).slice(0,3).map(Number));
            return colors.map(c=>{const b=l(c);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05)});
          });
        }''', theme)
        assert min(ratios) >= 4.5, (theme, ratios)
    for selector in ['.phone-info .eyebrow', '.phone-info .signal-note', '.phone-info .phone-unknown', '.phone-tile-link']:
        ratio = page.locator(selector).first.evaluate(r'''n=>{
          const l=c=>{const [r,g,b]=c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*r+.7152*g+.0722*b};
          const a=l(getComputedStyle(n).color.match(/[\d.]+/g).slice(0,3).map(Number)), b=l([14,23,41]);
          return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        }''')
        assert ratio >= 4.5, (selector, ratio)


def test_phone_emulated_safe_areas_and_short_browser_height(review):
    page = phone(review)
    session = page.context.new_cdp_session(page)
    session.send('Emulation.setSafeAreaInsetsOverride', {'insets': {'top': 20, 'right': 0, 'bottom': 34, 'left': 0}})
    assert page.locator('.phone-app').evaluate('n=>getComputedStyle(n).paddingTop') == '20px'
    assert page.locator('.phone-bottom-nav').evaluate('n=>getComputedStyle(n).paddingBottom') == '46px'
    choose(page)
    assert page.locator('.phone-handoff').evaluate('n=>getComputedStyle(n).paddingBottom') == '50px'
    page.set_viewport_size({'width': 390, 'height': 700})
    button = page.get_by_role('link', name='Open trusted decision UI').bounding_box()
    assert button['y'] + button['height'] <= 700 - 34
    page.evaluate('window.scrollTo(0,400)')
    assert page.locator('.phone-review-nav').bounding_box()['y'] == 20
    sheet(page, 'People')
    assert page.locator('.phone-sheet-scroll').evaluate('n=>getComputedStyle(n).paddingBottom') == '62px'
    page.keyboard.press('Escape'); no_overflow(page)
    session.detach()


def test_phone_short_evidence_links_have_touch_targets_and_untrusted_text_stays_inert(review):
    packet = review[3][f'/api/packets/{1:032x}']
    attack = '<img src="https://evil.invalid/x" onerror="window.pwned=1"><script>window.pwned=1</script>'
    packet['cover_text'] = attack
    packet['company_facts'][0]['source_title'] = 'X'
    page = phone(review); choose(page); sheet(page, 'Packet evidence')
    source = page.locator('.source-link').first
    assert source.bounding_box()['width'] >= 44 and source.bounding_box()['height'] >= 44
    sheet(page, 'Cover letter')
    expect(page.locator('.reader-text')).to_have_text(attack)
    assert not page.locator('.reader-text img, .reader-text script').count()
    assert page.evaluate('window.pwned === undefined')
