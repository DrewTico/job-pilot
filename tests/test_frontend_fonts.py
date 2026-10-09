"""Bounded first-party WOFF2 delivery and exact CSP expansion regressions."""
import hashlib
import json
import struct
from pathlib import Path

import pytest

from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_security import CSP
from job_agent.dashboard.frontend_delivery import load_assets, MAX_FONT_BYTES, MAX_FONT_TOTAL_BYTES
from test_frontend_delivery import tiny_build
from test_approval_security import request
from test_approvals import ready
from test_packets import setup

FONT = '_next/static/media/geist-latin-wght-normal.01234567.woff2'
CSS = '_next/static/css/fonts.css'


def add_asset(root, manifest, name, data, mime):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    manifest['assets'][name] = {'type': mime, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def save_manifest(root, manifest):
    (root / 'manifest.json').write_text(json.dumps(manifest))


def font_bytes(size=48):
    # Policy header fixture only; real WOFF2 parsing/loading is proved in Chromium.
    data = bytearray(size)
    data[:4] = b'wOF2'
    struct.pack_into('>I', data, 8, size)
    return bytes(data)


@pytest.fixture
def font_build(tiny_build):
    root, manifest = tiny_build
    add_asset(root, manifest, FONT, font_bytes(), 'font/woff2')
    add_asset(root, manifest, CSS, f'@font-face{{src:url("/ui/{FONT}")}}'.encode(), 'text/css')
    save_manifest(root, manifest)
    return root, manifest


def test_approved_woff2_snapshot_loads(font_build):
    assets = load_assets(font_build[0])
    assert assets[FONT] == (font_bytes(), 'font/woff2')


@pytest.mark.parametrize('name', [
    FONT.replace('.woff2', ext) for ext in ['.woff', '.ttf', '.otf', '.bin']
] + [
    FONT.replace('geist-latin-wght-normal', 'arbitrary-font'),
    FONT.replace('media/', 'media/nested/'),
    FONT.replace('media/', 'fonts/'),
    FONT.replace('01234567', 'bad-hash'),
    '../' + FONT, FONT.replace('media/', '../media/'),
    '/' + FONT, FONT + '?download=1', FONT.replace('media/', 'media/%2e%2e/'),
])
def test_font_extension_and_path_fail_closed(font_build, name):
    root, manifest = font_build
    manifest['assets'][name] = manifest['assets'].pop(FONT)
    save_manifest(root, manifest)
    assert load_assets(root) == {}


@pytest.mark.parametrize('attack', ['symlink', 'parent_symlink', 'hash', 'bytes', 'signature', 'length', 'mime', 'missing', 'undeclared', 'oversized'])
def test_font_package_integrity_fails_closed(font_build, tmp_path, attack):
    root, manifest = font_build
    path = root / FONT
    if attack == 'symlink':
        target = tmp_path / 'external.woff2'; target.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(target)
    if attack == 'parent_symlink':
        parent = path.parent; parent.rename(tmp_path / 'external-media'); parent.symlink_to(tmp_path / 'external-media')
    if attack == 'hash': manifest['assets'][FONT]['sha256'] = '0' * 64
    if attack == 'bytes': path.write_bytes(b'x' + path.read_bytes()[1:])
    if attack == 'signature': add_asset(root, manifest, FONT, b'BAD!' + font_bytes()[4:], 'font/woff2')
    if attack == 'length': add_asset(root, manifest, FONT, font_bytes() + b'extra', 'font/woff2')
    if attack == 'mime': manifest['assets'][FONT]['type'] = 'application/octet-stream'
    if attack == 'missing': path.unlink()
    if attack == 'undeclared': del manifest['assets'][FONT]
    if attack == 'oversized': add_asset(root, manifest, FONT, font_bytes(MAX_FONT_BYTES + 1), 'font/woff2')
    save_manifest(root, manifest)
    assert load_assets(root) == {}


def test_total_font_payload_is_bounded(font_build):
    root, manifest = font_build
    names = [FONT.replace('01234567', f'{i:08x}') for i in range(3)]
    for name in names: add_asset(root, manifest, name, font_bytes(MAX_FONT_BYTES), 'font/woff2')
    assert len(names) * MAX_FONT_BYTES > MAX_FONT_TOTAL_BYTES
    add_asset(root, manifest, CSS, ''.join(f'@font-face{{src:url(/ui/{name})}}' for name in [FONT, *names]).encode(), 'text/css')
    save_manifest(root, manifest)
    assert load_assets(root) == {}


def test_existing_total_package_bound_remains(font_build):
    root, manifest = font_build
    for i in range(4): add_asset(root, manifest, f'_next/static/chunks/large{i}.js', b' ' * 4_000_000, 'text/javascript')
    save_manifest(root, manifest)
    assert load_assets(root) == {}


@pytest.mark.parametrize('css', [
    '@font-face{src:url(https://fonts.gstatic.com/a.woff2)}',
    '@font-face{src:url(data:font/woff2;base64,AAAA)}',
    '@font-face{src:url(blob:font)}',
    '@import "https://fonts.googleapis.com/font.css";',
    '@font-face{src:url(/ui/' + FONT.replace('01234567', 'ffffffff') + ')}',
])
def test_css_font_references_require_declared_same_origin_assets(font_build, css):
    root, manifest = font_build
    add_asset(root, manifest, CSS, css.encode(), 'text/css'); save_manifest(root, manifest)
    assert load_assets(root) == {}


def test_fonts_are_immutable_exact_manifest_lookup_and_get_only(font_build, ready, monkeypatch):
    root, manifest = font_build
    monkeypatch.setattr('job_agent.dashboard.frontend_delivery.load_assets', lambda: load_assets(root))
    app = create_approval_app(engine=ready[1].engine, settings=ready[1].settings)
    original = (root / FONT).read_bytes()
    (root / FONT).write_bytes(b'changed after startup')
    (root / 'manifest.json').write_text('{}')
    status, headers, body, _ = request(app, '/ui/' + FONT)
    assert status == 200 and body == original and headers[b'content-type'] == b'font/woff2'
    assert headers[b'x-content-type-options'] == b'nosniff'
    assert headers[b'cache-control'] == b'no-store'
    # Even a physically present permitted filename cannot be requested undeclared.
    other = FONT.replace('01234567', 'ffffffff')
    add_asset(root, manifest, other, font_bytes(), 'font/woff2')
    for path in [other, FONT + '/', FONT.replace('media/', 'media//'), FONT.replace('.woff2', '.woff'),
                 '_next/static/media/../private.woff2', '%2e%2e/.env']:
        assert request(app, '/ui/' + path)[0] == 404
    for query in ['v=1', 'file=../.env', 'download=1']:
        assert request(app, '/ui/' + FONT, query=query)[0] == 404
    assert request(app, '/ui/' + FONT, method='POST', body=b'no')[0] == 403
    assert request(app, '/ui/' + FONT, method='OPTIONS')[0] == 405


@pytest.mark.parametrize('failure', ['missing', 'corrupt_font'])
def test_font_failure_disables_only_ui(font_build, ready, monkeypatch, failure):
    root, _ = font_build
    if failure == 'missing': root = root / 'missing'
    else: (root / FONT).write_bytes(b'corrupt')
    monkeypatch.setattr('job_agent.dashboard.frontend_delivery.load_assets', lambda: load_assets(root))
    app = create_approval_app(engine=ready[1].engine, settings=ready[1].settings)
    assert request(app, '/ui')[0] == 404
    assert request(app, '/ui/' + FONT)[0] == 404
    for path in ['/', '/assets/approval.js', '/api/queue']: assert request(app, path)[0] == 200


def test_csp_only_expands_font_source():
    previous = (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'none'; font-src 'none'; object-src 'none'; frame-src 'none'; "
        "worker-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none';"
    )
    assert CSP == previous.replace("font-src 'none'", "font-src 'self'")


def test_production_font_manifest_is_minimal_and_preserves_licenses():
    root = Path(__file__).resolve().parents[1]
    assets = load_assets()
    fonts = {name: content for name, (content, mime) in assets.items() if mime == 'font/woff2'}
    selected = {
        '@fontsource-variable/bricolage-grotesque': 'bricolage-grotesque-latin-wght-normal',
        '@fontsource-variable/geist': 'geist-latin-wght-normal',
        '@fontsource/geist-mono': 'geist-mono-latin-400-normal',
        '@fontsource/newsreader': 'newsreader-latin-400-normal',
    }
    assert len(fonts) == len(selected)
    assert sum(map(len, fonts.values())) == 103_088
    css = b'\n'.join(content for content, mime in assets.values() if mime == 'text/css').decode()
    for package, stem in selected.items():
        source = root / 'frontend/node_modules' / package
        package_data = json.loads((source / 'package.json').read_text())
        assert package_data['version'] == '5.3.0' and package_data['license'] == 'OFL-1.1'
        matched = [content for name, content in fonts.items() if name.split('/')[-1].startswith(stem + '.')]
        assert matched == [(source / 'files' / (stem + '.woff2')).read_bytes()]
        assert (source / 'LICENSE').read_text().strip() in css
