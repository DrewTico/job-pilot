"""Run 5B first gate, using the existing offline Chromium fixture."""
from playwright.sync_api import expect

from test_approval_ui_dom import browser, loopback_server, ui
from test_approvals import ready
from test_packets import setup


def test_static_next_hydrates_under_unchanged_csp(ui):
    page = ui[0]
    page.add_init_script("window.cspViolations = []; document.addEventListener('securitypolicyviolation', e => window.cspViolations.push(e.violatedDirective));")
    response = page.goto(ui[2] + "/ui")
    assert response.status == 200
    tab = page.get_by_role('tab', name='Processing', exact=True)
    expect(tab).to_be_visible()
    tab.click()
    expect(tab).to_have_attribute('aria-selected', 'true')
    expect(page.locator('.app')).to_have_attribute('data-theme', 'dark')
    assert not page.evaluate("window.cspViolations")
    assert not ui[4]
