"""Run 5B additive static delivery policy and Run 4 boundary regressions."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_models import PacketDetail, QueueResponse, DecisionDetail, PacketDiffResult
from job_agent.dashboard.approval_security import SECURITY_HEADERS
from job_agent.dashboard.frontend_delivery import BUILD, load_assets
from test_approval_security import request
from test_approvals import ready
from test_packets import setup
from test_tailscale_api import remote, call
from test_tailscale_security import HOST, LOGIN, headers

ROOT = Path(__file__).resolve().parents[1]


def test_build_manifest_is_required_complete_and_fixture_free():
    assets = load_assets()
    assert assets and 'index.html' in assets, 'Run npm ci and npm run build first'
    assert all(name == 'index.html' or name.startswith('_next/static/') for name in assets)
    content = b''.join(value[0] for value in assets.values())
    for private in (b'northstar.invalid', b'Synthetic structured answer', b'Long Content Laboratory'):
        assert private not in content
    assert not any(name.endswith('.map') or '/demo-' in name for name in assets)
    physical = {str(path.relative_to(BUILD)) for path in BUILD.rglob('*') if path.is_file()}
    assert physical == set(assets) | {'manifest.json'}, 'Generated package contains unlisted bytes'


@pytest.fixture
def tiny_build(tmp_path):
    root = tmp_path / 'build'; root.mkdir()
    data = b'<!doctype html><title>Proof</title>'
    (root / 'index.html').write_bytes(data)
    manifest = {'version': 1, 'assets': {'index.html': {'type': 'text/html', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return root, manifest


@pytest.mark.parametrize('attack', ['../private.js', '/private.js', '_next/static/../../private.js', '_next/static/private.map', '.env', 'manifest.json', 'demo/index.html', '_next/static/a%2f.js', '_next/static/a\\b.js'])
def test_manifest_rejects_unapproved_paths(tiny_build, attack):
    root, manifest = tiny_build
    manifest['assets'][attack] = copy.deepcopy(manifest['assets']['index.html'])
    (root / 'manifest.json').write_text(json.dumps(manifest))
    assert load_assets(root) == {}


@pytest.mark.parametrize('change', ['bytes', 'hash', 'type', 'size', 'missing', 'symlink', 'manifest_symlink', 'invalid_json'])
def test_manifest_fail_closed(tiny_build, tmp_path, change):
    root, manifest = tiny_build
    if change == 'bytes': (root / 'index.html').write_bytes(b'TAMPERED')
    if change == 'hash': manifest['assets']['index.html']['sha256'] = '0' * 64
    if change == 'type': manifest['assets']['index.html']['type'] = 'text/javascript'
    if change == 'size': manifest['assets']['index.html']['size'] = True
    if change == 'missing': (root / 'index.html').unlink()
    if change == 'symlink':
        (root / 'index.html').unlink(); (root / 'index.html').symlink_to(tmp_path / 'private')
    (root / 'manifest.json').write_text(json.dumps(manifest))
    if change == 'manifest_symlink':
        (root / 'manifest.json').unlink(); (root / 'manifest.json').symlink_to(tmp_path / 'private')
    if change == 'invalid_json': (root / 'manifest.json').write_text('PRIVATE BAD JSON')
    assert load_assets(root) == {}


def test_missing_build_disables_only_ui(ready, monkeypatch, tmp_path):
    monkeypatch.setattr('job_agent.dashboard.frontend_delivery.load_assets', lambda: load_assets(tmp_path / 'missing'))
    app = create_approval_app(engine=ready[1].engine, settings=ready[1].settings)
    assert request(app, '/ui')[0] == 404
    assert request(app, '/')[0] == 200
    assert request(app, '/assets/approval.js')[0] == 200
    assert request(app, '/api/queue')[0] == 200


def test_all_packaged_assets_protected_exact_mime_no_store_and_no_side_effects(remote, ready):
    before = (ready[4] / 'test.sqlite').read_bytes()
    assets = load_assets(); assert assets
    for name, (content, mime) in assets.items():
        path = '/ui' if name == 'index.html' else '/ui/' + name
        status, secured, body, reads = call(remote[0], path)
        assert status == 200 and body == content and reads == 0
        assert secured[b'content-type'].startswith(mime.encode())
        for key, value in SECURITY_HEADERS.items(): assert secured[key.lower().encode()] == value.encode()
        assert request(remote[0], path, headers=[(b'host', HOST)])[0] == 401
        assert request(remote[0], path, headers=[(b'host', HOST), (b'tailscale-user-login', b'other@example.test')])[0] == 403
        assert request(remote[0], path, headers=[*headers(), (b'tailscale-user-login', LOGIN)])[0] == 401
        assert request(remote[0], path, headers=[(b'host', b'localhost:8643'), (b'tailscale-user-login', LOGIN)])[0] == 400
    assert call(remote[0], '/ui/')[0] == 200
    assert before == (ready[4] / 'test.sqlite').read_bytes()
    with ready[1].engine.connect() as connection: assert connection.exec_driver_sql('PRAGMA user_version').scalar() == 9


@pytest.mark.parametrize('path', ['/ui/../.env', '/ui/%2e%2e/.env', '/ui/_next/static/../../approval.js', '/ui/_next/static/private.map', '/ui/manifest.json', '/ui/index.html', '/ui/demo/', '/ui/demo/index.html', '/ui/src/lib/contracts.json', '/ui/_next/server/pages/index.js', '/ui/_next/static/not-listed.js', '/ui/.env', '/ui/facts.yaml', '/ui/_next/static//chunks/main.js'])
def test_requests_never_become_filesystem_paths(remote, path):
    assert call(remote[0], path)[0] == 404
    status, _, _, reads = request(remote[0], path, headers=[(b'host', HOST)])
    assert status == 401 and reads == 0


def test_auth_and_csrf_independent_on_frontend(remote):
    token = json.loads(call(remote[0], '/api/bootstrap')[2])['csrf_token'].encode()
    assert request(remote[0], '/ui', headers=[(b'host', HOST), (b'x-job-pilot-csrf', token)])[0] == 401
    assert request(remote[0], '/ui', headers=[(b'host', HOST), (b'tailscale-user-name', LOGIN), (b'x-forwarded-user', LOGIN)])[0] == 401
    assert request(remote[0], '/ui', headers=headers(), client=('10.0.0.5', 1234))[0] == 403
    assert request(remote[0], '/ui', method='POST', headers=headers(), body=b'PRIVATE')[0] == 403
    assert request(remote[0], '/ui', method='OPTIONS', headers=headers())[0] == 405
    assert request(remote[0], '/ui', headers=headers(), query='file=../.env')[0] == 404


def test_contract_snapshots_and_synthetic_fixtures():
    contract = json.loads((ROOT / 'frontend/src/lib/contracts.json').read_text())
    assert contract == {model.__name__: model.model_json_schema() for model in (QueueResponse, PacketDetail, DecisionDetail, PacketDiffResult)}
    fixtures = json.loads((ROOT / 'frontend/src/fixtures/review.json').read_text())
    assert fixtures['synthetic'] is True
    for raw in fixtures['packets']:
        packet = PacketDetail.model_validate(raw)
        assert packet.company.startswith('Synthetic · ')
        for fact in packet.company_facts: assert not fact.source_url or '.invalid/' in fact.source_url
        assert not packet.application_destination.url or '.invalid/' in packet.application_destination.url
    source = (ROOT / 'frontend/src/pages/index.tsx').read_text()
    assert 'fixtures' not in source
    assert BUILD.name == 'ui_build'
