"""Real Chromium font resolution and same-origin network proof, synthetic UI only."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Error, expect

from job_agent.dashboard.frontend_delivery import load_assets
from test_frontend_ui_dom import review, open_review, select, evidence
from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready
from test_packets import setup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/run5b/phone-implementation-evidence/font-proof'


def platform_fonts(page, selector):
    session = page.context.new_cdp_session(page)
    try:
        session.send('DOM.enable'); session.send('CSS.enable')
        root = session.send('DOM.getDocument')['root']['nodeId']
        node = session.send('DOM.querySelector', {'nodeId': root, 'selector': selector})['nodeId']
        return session.send('CSS.getPlatformFontsForNode', {'nodeId': node})['fonts']
    finally:
        session.detach()


def assert_font(page, selector, family):
    node = page.locator(selector).first
    computed = node.evaluate('''n => {const s=getComputedStyle(n);return {family:s.fontFamily,weight:s.fontWeight,size:s.fontSize}}''')
    assert computed['family'].split(',')[0].strip('" ') == family
    faces = node.evaluate('''async n => {
        const s=getComputedStyle(n), spec=`${s.fontWeight} ${s.fontSize} ${s.fontFamily.split(',')[0]}`;
        const loaded=await document.fonts.load(spec,n.textContent);await document.fonts.ready;
        return {check:document.fonts.check(spec,n.textContent),status:document.fonts.status,
          faces:loaded.map(f=>({family:f.family,status:f.status,weight:f.weight,style:f.style,display:f.display}))};
    }''')
    assert faces['check'] and faces['status'] == 'loaded'
    assert faces['faces'] and all(f['family'] == family and f['status'] == 'loaded' and f['display'] == 'swap' for f in faces['faces'])
    actual = platform_fonts(page, selector)
    assert any(f['isCustomFont'] and f['glyphCount'] > 0 and f['familyName'].startswith(family) for f in actual), actual
    return {'computed': computed, 'font_face_set': faces, 'platform_fonts': actual}


def test_exact_fonts_and_zero_third_party_requests_at_1440x900(review):
    page = review[0]; page.set_viewport_size({'width': 1440, 'height': 900})
    page.emulate_media(reduced_motion='reduce')
    requests, font_responses = [], []
    page.on('request', lambda req: requests.append({'url': req.url, 'type': req.resource_type, 'method': req.method}))
    page.on('response', lambda response: font_responses.append({'url': response.url, 'status': response.status}) if response.request.resource_type == 'font' else None)
    open_review(review); select(review)
    resolved = {}
    for role, selector, family in [
        ('hero_title', '#packet-title', 'Bricolage Grotesque'),
        ('ready_for_you', '.queue-top h1', 'Bricolage Grotesque'),
        ('fit_score', '.score', 'Bricolage Grotesque'),
        ('ordinary_ui', '.row-title', 'Geist'),
        ('company_line', '.company-label', 'Geist'),
        ('demo_badge', '.demo-label', 'Geist'),
        ('fit_label', '.fit-description>strong', 'Bricolage Grotesque'),
        ('tile_value', '.tile-value', 'Bricolage Grotesque'),
    ]:
        resolved[role] = assert_font(page, selector, family)
    selectors = ['.job-hero', '.review-panes', '.decision-handoff', '.company-label', '.demo-label', '.score',
        '.fit-ring>div>span', '.row-company', '.row-title', '.tile-value', '.location-value', '.job-location',
        '.status-badge', '.manual-badge', '.evidence-panel .tabs-trigger', '.queue-tabs>.tabs-list>.tabs-trigger', '.button', '.packet-signals']
    metrics = {selector: page.locator(selector).evaluate_all('''nodes => nodes.map(n=>{
        const s=getComputedStyle(n),b=n.getBoundingClientRect();return {text:n.innerText,x:b.x,y:b.y,width:b.width,height:b.height,
          font:s.fontFamily,fontSize:s.fontSize,weight:s.fontWeight,lineHeight:s.lineHeight,tracking:s.letterSpacing,
          padding:s.padding,border:s.borderWidth,radius:s.borderRadius,align:s.alignItems,justify:s.justifyContent};})''') for selector in selectors}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUTPUT / 'review-1440x900.png'))
    page.locator('.hero-company-line').screenshot(path=str(OUTPUT / 'hero-company-detail.png'))
    page.locator('.decision-handoff').screenshot(path=str(OUTPUT / 'dock-detail.png'))
    evidence(page, 'History')
    resolved['technical_mono'] = assert_font(page, '.fingerprint', 'Geist Mono')
    evidence(page, 'Cover letter')
    resolved['cover_letter'] = assert_font(page, '.cover-text', 'Newsreader')
    page.get_by_role('button', name='Open full view').click()
    expect(page.get_by_role('dialog', name='Cover letter')).to_be_visible()
    resolved['cover_letter_reader'] = assert_font(page, '.reader-text', 'Newsreader')
    page.screenshot(path=str(OUTPUT / 'reader-1440x900.png'))
    page.keyboard.press('Escape')
    third_party = [r for r in requests if not r['url'].startswith(review[2] + '/')]
    assert not third_party
    assert all(r['method'] == 'GET' for r in requests)
    fonts = [r for r in requests if r['type'] == 'font']
    expected = {name for name, (_, mime) in load_assets().items() if mime == 'font/woff2'}
    assert len(expected) == 4
    assert {urlsplit(r['url']).path.removeprefix('/ui/') for r in fonts} == expected
    assert all(r['url'].startswith(review[2] + '/ui/_next/static/media/') for r in fonts)
    assert len(font_responses) == 4 and all(r['status'] == 200 for r in font_responses)
    assert not page.evaluate('window.cspViolations')
    (OUTPUT / 'browser-proof.json').write_text(json.dumps({'viewport': {'width': 1440, 'height': 900},
        'resolved_fonts': resolved, 'font_requests': fonts, 'font_responses': font_responses,
        'requests': requests, 'third_party_request_count': len(third_party), 'csp_violations': [], 'metrics': metrics}, indent=2) + '\n')


def test_font_proof_rejects_silent_fallback(review):
    page = review[0]
    page.route('**/bricolage-grotesque-latin-wght-normal.*.woff2', lambda route: route.abort())
    open_review(review); select(review)
    page.evaluate('document.fonts.ready')
    # The CSS family still names Bricolage; actual glyphs must fail the proof.
    assert page.locator('#packet-title').evaluate('n=>getComputedStyle(n).fontFamily').startswith('"Bricolage Grotesque"')
    actual = platform_fonts(page, '#packet-title')
    assert not any(f['isCustomFont'] and f['familyName'].startswith('Bricolage Grotesque') for f in actual)
    with pytest.raises((AssertionError, Error)):
        assert_font(page, '#packet-title', 'Bricolage Grotesque')
