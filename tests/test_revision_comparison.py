"""Run 5D-2 exact historical reads using synthetic SQLite and artifact roots."""
import json
import shutil

import pytest
from sqlmodel import Session

from job_agent.database import ApplicationPacket, PacketRevisionWork, WritingWorkItem, database_session
from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_service import ApprovalQueueService
from job_agent.packet_history import diff_cover, diff_resume, list_packet_versions
from job_agent.packet_history import HistoryError
from test_packet_history import history_pair, trap_current_and_providers
from test_packets import setup as packet_setup, add_job
from test_revisions import offline_only, revision_setup, revision_successor
from test_approval_security import request


def compare(service, before, after):
    from job_agent.packet_history import compare_revision
    return compare_revision(service.engine, service.settings, before, after)


def storage_snapshot(service, directory):
    with service.engine.connect() as connection:
        names = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").scalars().all()
        rows = {name: connection.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY rowid').all()
                for name in names}
        schema = connection.exec_driver_sql("SELECT * FROM sqlite_master ORDER BY name").all()
        assert connection.exec_driver_sql("SELECT count(*) FROM application_events").scalar() == 0
    files = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    return rows, schema, files


def read_traps(monkeypatch, service):
    trap_current_and_providers(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("comparison_must_only_read_history")
    monkeypatch.setattr(service.executor, "create", forbidden)
    for target in ("job_agent.packets.PacketService.build_one",
                   "job_agent.revisions.RevisionProcessor.process_revision",
                   "job_agent.approvals.ApprovalService.preview_approval",
                   "job_agent.approvals.ApprovalService.validate_approval_for_packet"):
        monkeypatch.setattr(target, forbidden)


def test_exact_revision_change_identity_and_read_only(history_pair, monkeypatch):
    service, calls, directory, source, child, processor = history_pair
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    result = compare(service, source.id, child.id)
    assert result['status'] == 'available'
    assert result['before'] == dict(packet_id=source.id, version=source.version, fingerprint=source.fingerprint)
    assert result['after'] == dict(packet_id=child.id, version=child.version, fingerprint=child.fingerprint)
    assert result['revision_decision_id'] == child.revision_decision_id
    assert result['revision_state'] == 'succeeded'
    for kind, minus, plus in [('resume', '-- Built Python software.', '+- Built Python tools.'),
                              ('cover', '-Built Python software.', '+Built Python tools.')]:
        content = result[kind]
        assert content['status'] == content['before_status'] == content['after_status'] == 'available'
        assert content['changed'] is True and minus in content['diff'] and plus in content['diff']
        assert content['diff'].startswith(f'--- packet:{source.id}/version:1\n+++ packet:{child.id}/version:2\n')
    assert storage_snapshot(service, directory) == before
    assert len(calls) == 4
    assert result == compare(service, source.id, child.id)


def test_authenticated_unchanged_revision(revision_setup, monkeypatch):
    processor, service, calls, directory, source, decision = revision_setup
    child = revision_successor(processor, processor.process_revision(decision.id))
    read_traps(monkeypatch, service)
    result = compare(service, source.id, child.id)
    assert result['status'] == 'available'
    for kind in ('resume', 'cover'):
        assert result[kind]['status'] == 'available'
        assert result[kind]['changed'] is False and result[kind]['diff'] == ''


@pytest.mark.parametrize('damage', ['source_fingerprint', 'missing_work', 'wrong_successor', 'decision_evidence'])
def test_durable_relationship_damage_is_not_trusted(history_pair, monkeypatch, damage):
    service, calls, directory, source, child, processor = history_pair
    # Model external corruption only in temporary SQLite. Disable only the
    # relevant temporary trigger where necessary, then snapshot the damage.
    with service.engine.begin() as connection:
        if damage == 'source_fingerprint':
            connection.exec_driver_sql('UPDATE application_packets SET fingerprint=? WHERE id=?', ('f'*64, source.id))
        elif damage == 'decision_evidence':
            connection.exec_driver_sql('DROP TRIGGER packet_decisions_no_update')
            connection.exec_driver_sql('UPDATE packet_decisions SET evidence_json=? WHERE id=?', ('{}', child.revision_decision_id))
        else:
            if damage == 'missing_work':
                connection.exec_driver_sql('DROP TRIGGER revision_work_no_delete')
                connection.exec_driver_sql('DELETE FROM packet_revision_work WHERE decision_id=?', (child.revision_decision_id,))
            else:
                connection.exec_driver_sql('DROP TRIGGER revision_work_identity_immutable')
                connection.exec_driver_sql('DROP TRIGGER revision_work_binding_update')
                connection.exec_driver_sql('UPDATE packet_revision_work SET successor_packet_id=? WHERE decision_id=?',
                                           (source.id, child.revision_decision_id))
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    result = compare(service, source.id, child.id)
    assert result['status'] == 'integrity_failed'
    assert result['resume'] is None and result['cover'] is None
    with pytest.raises(HistoryError, match='^history_integrity_failed$'):
        list_packet_versions(service.engine, packet_id=child.id)
    assert storage_snapshot(service, directory) == before


def test_cover_checkpoint_substitution_with_identical_text_is_rejected(revision_setup):
    processor, service, calls, directory, source, decision = revision_setup
    child = revision_successor(processor, processor.process_revision(decision.id))
    assert child.cover_letter == source.cover_letter
    with database_session(service.engine) as session:
        packet = session.get(ApplicationPacket, child.id)
        packet.writing_fingerprints = {**packet.writing_fingerprints,
                                      'cover_letter': source.writing_fingerprints['cover_letter']}
        session.add(packet)
    result = compare(service, source.id, child.id)
    assert result['cover']['status'] == 'integrity_failed'
    assert result['cover']['changed'] is None and result['cover']['diff'] is None


def test_cover_authenticator_preserves_legitimate_shared_checkpoint(packet_setup):
    service, calls, directory = packet_setup
    row = add_job(service)
    source = service.build_one(row)
    with database_session(service.engine) as session:
        packet = session.get(ApplicationPacket, source.id)
        packet.status = 'recovery_required'
        session.add(packet)
    reused = service.build_one(row)
    assert reused.status == 'packet_ready' and reused.id != source.id
    assert reused.writing_fingerprints == source.writing_fingerprints and len(calls) == 2
    result = diff_cover(service.engine, service.settings, source.id, reused.id)
    assert result.status == 'available' and result.diff == ''


def test_lineage_skips_unrelated_allocated_version(revision_setup):
    processor, service, calls, directory, source, decision = revision_setup
    with database_session(service.engine) as session:
        unrelated = ApplicationPacket(job_key=source.job_key, version=2, fingerprint='e'*64,
            search_result_id=source.search_result_id, scoring_fingerprint=source.scoring_fingerprint,
            status='building', company='Acme', title='Engineer', score=80, tier='A')
        session.add(unrelated)
        session.flush()
    child = revision_successor(processor, processor.process_revision(decision.id))
    assert child.version == 3
    result = compare(service, source.id, child.id)
    assert result['status'] == 'available' and result['before']['version'] == 1
    assert compare(service, unrelated.id, child.id)['status'] == 'invalid_request'


def test_unfinished_successor_is_unavailable(revision_setup, monkeypatch):
    processor, service, calls, directory, source, decision = revision_setup
    def stop(name):
        if name == 'after_successor_allocation':
            raise SystemExit()
    processor._boundary = stop
    with pytest.raises(SystemExit):
        processor.process_revision(decision.id)
    with Session(service.engine) as session:
        child = session.get(ApplicationPacket, session.get(PacketRevisionWork, decision.id).successor_packet_id)
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    result = compare(service, source.id, child.id)
    assert result['status'] == 'unavailable' and result['revision_state'] == 'building'
    for kind in ('resume', 'cover'):
        assert result[kind]['before_status'] == 'available' and result[kind]['after_status'] == 'unavailable'
        assert result[kind]['changed'] is None and result[kind]['diff'] is None
    assert len(calls) == 2 and storage_snapshot(service, directory) == before


def test_missing_evidence_does_not_hide_other_side_integrity_failure(history_pair):
    service, calls, directory, source, child, processor = history_pair
    (directory / 'packets' / source.id / 'resume.face.txt').unlink()
    (directory / 'packets' / child.id / 'resume.face.txt').write_text('tampered')
    result = compare(service, source.id, child.id)
    assert result['status'] == result['resume']['status'] == 'integrity_failed'
    assert result['resume']['before_status'] == 'unavailable'
    assert result['resume']['after_status'] == 'integrity_failed'
    assert result['resume']['changed'] is None and result['resume']['diff'] is None


@pytest.mark.parametrize('case', ['reversed', 'same_packet', 'same_job', 'cross_job', 'missing_before', 'missing_after', 'malformed'])
def test_revision_comparison_rejects_untrusted_pairs(history_pair, case):
    service, calls, directory, source, child, processor = history_pair
    left, right = source.id, child.id
    if case == 'reversed':
        left, right = right, left
    elif case == 'same_packet':
        left = right
    elif case == 'same_job':
        with database_session(service.engine) as session:
            unrelated = ApplicationPacket(job_key=source.job_key, version=3, fingerprint='e'*64,
                search_result_id=source.search_result_id, scoring_fingerprint=source.scoring_fingerprint,
                status='building', company='Acme', title='Engineer', score=80, tier='A')
            session.add(unrelated)
            session.flush()
            left = unrelated.id
    elif case == 'cross_job':
        left = service.build_one(add_job(service, 'other')).id
    elif case == 'missing_before':
        left = 'f'*32
    elif case == 'missing_after':
        right = 'f'*32
    else:
        left = '../private'
    result = compare(service, left, right)
    assert result['status'] == ('unavailable' if case.startswith('missing') else 'invalid_request')
    assert result['before']['packet_id'] == left and result['after']['packet_id'] == right
    assert result['resume'] is None and result['cover'] is None


@pytest.mark.parametrize('side', ['before', 'after'])
@pytest.mark.parametrize('kind', ['resume', 'cover'])
@pytest.mark.parametrize('damage', ['missing', 'tampered', 'substitute'])
def test_revision_content_failures_never_mean_unchanged(history_pair, monkeypatch, side, kind, damage):
    service, calls, directory, source, child, processor = history_pair
    target, other = (source, child) if side == 'before' else (child, source)
    if kind == 'resume':
        path = directory / 'packets' / target.id / 'resume.face.txt'
        if damage == 'missing':
            path.unlink()
        elif damage == 'tampered':
            path.write_bytes(b'tampered')
        else:
            shutil.copyfile(directory / 'packets' / other.id / 'resume.face.txt', path)
    else:
        with database_session(service.engine) as session:
            checkpoint = session.get(WritingWorkItem, target.writing_fingerprints['cover_letter'])
            if damage == 'missing':
                session.delete(checkpoint)
            elif damage == 'tampered':
                checkpoint.output = 'tampered'
                session.add(checkpoint)
            else:
                packet = session.get(ApplicationPacket, target.id)
                packet.writing_fingerprints = {**packet.writing_fingerprints,
                    'cover_letter': other.writing_fingerprints['cover_letter']}
                session.add(packet)
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    result = compare(service, source.id, child.id)
    expected = 'unavailable' if damage == 'missing' else 'integrity_failed'
    assert result['status'] == result[kind]['status'] == result[kind][side + '_status'] == expected
    assert result[kind]['changed'] is None and result[kind]['diff'] is None
    assert storage_snapshot(service, directory) == before


def test_existing_generic_read_proofs(history_pair, monkeypatch):
    """Immediate existing proofs; generic reverse comparison remains permitted."""
    service, calls, directory, source, child, processor = history_pair
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    for operation in (diff_resume, diff_cover):
        forward = operation(service.engine, service.settings, source.id, child.id)
        reverse = operation(service.engine, service.settings, child.id, source.id)
        assert forward.status == reverse.status == 'available'
        assert reverse.diff.startswith(f'--- packet:{child.id}/version:2\n+++ packet:{source.id}/version:1\n')
    history = list_packet_versions(service.engine, packet_id=child.id)
    assert history[0]['decision'] == 'revise' and history[1]['decision'] is None
    assert history[1]['source_packet_id'] == source.id
    assert storage_snapshot(service, directory) == before


def test_exact_comparison_ignores_missing_current_inputs(history_pair, monkeypatch, caplog):
    service, calls, directory, source, child, processor = history_pair
    for name in ('facts.yaml', 'answer_bank.yaml', 'style_memory.md'):
        (directory / name).unlink()
    read_traps(monkeypatch, service)
    before = storage_snapshot(service, directory)
    service.engine.echo = True
    with caplog.at_level('DEBUG'):
        result = compare(service, source.id, child.id)
    assert result['status'] == 'available'
    assert 'Built Python' not in caplog.text and 'Prefer specific wording' not in caplog.text
    assert storage_snapshot(service, directory) == before


def test_protected_revision_comparison_contract(history_pair, monkeypatch):
    service, calls, directory, source, child, processor = history_pair
    read_traps(monkeypatch, service)
    app = create_approval_app(engine=service.engine, settings=service.settings)
    path = f'/api/packets/{source.id}/revision-comparison/{child.id}'
    before = storage_snapshot(service, directory)
    status, headers, body, _ = request(app, path)
    assert status == 200, body
    assert json.loads(body) == compare(service, source.id, child.id)
    assert headers[b'cache-control'] == b'no-store'
    assert str(directory).encode() not in body and b'evidence_json' not in body
    assert request(app, path, headers=[(b'host', b'attacker.example:8643')])[0] == 400
    assert request(app, path, query='unknown=PRIVATE')[0] == 422
    assert request(app, path, method='POST')[0] == 403
    assert request(app, f'/api/packets/{child.id}/revision-comparison/{source.id}')[0] == 200
    assert json.loads(request(app, f'/api/packets/{child.id}/revision-comparison/{source.id}')[2])['status'] == 'invalid_request'
    assert storage_snapshot(service, directory) == before


def test_revision_comparison_tailscale_boundary(history_pair, monkeypatch):
    from test_tailscale_security import HOST, headers, settings
    service, calls, directory, source, child, processor = history_pair
    read_traps(monkeypatch, service)
    app = create_approval_app(engine=service.engine, settings=settings(data_dir=directory), access='tailscale')
    path = f'/api/packets/{source.id}/revision-comparison/{child.id}'
    before = storage_snapshot(service, directory)
    assert request(app, path, headers=[(b'host', HOST)])[0] == 401
    assert request(app, path, headers=[(b'host', HOST), (b'tailscale-user-login', b'wrong@example.test')])[0] == 403
    assert request(app, path, headers=headers(), client=('10.0.0.5', 1234))[0] == 403
    assert request(app, path, headers=headers(), method='POST')[0] == 403
    status, secured, body, _ = request(app, path, headers=headers())
    assert status == 200 and json.loads(body) == compare(service, source.id, child.id)
    assert secured[b'cache-control'] == b'no-store'
    assert storage_snapshot(service, directory) == before


def test_successor_authorization_is_independent(history_pair):
    service, calls, directory, source, child, processor = history_pair
    adapter = ApprovalQueueService(service.engine, service.settings)
    before = storage_snapshot(service, directory)
    assert adapter.decision_detail(source.id).decision == 'revise'
    detail = adapter.detail(child.id)
    assert detail.decision is None and detail.current_authorization == 'not_approved'
    assert detail.approval_preview.packet_id == child.id
    assert detail.approval_preview.expected_packet_fingerprint == child.fingerprint
    assert storage_snapshot(service, directory) == before
