"""Only the new owner backup verification/rehearsal surface."""
from uuid import UUID, uuid4
from pathlib import Path
import hashlib
import io
import json
import tarfile

import pytest

from distribution.models import BackupJob
from ingestion.models import AuditEvent
from distribution.backup_checks import perform_check
from distribution.database_backup import DatabaseBackupError, extract_backup_database, file_sha256

pytestmark = pytest.mark.django_db


@pytest.fixture
def backup_check(api_client, superadmin_user, settings, tmp_path):
    settings.NAS_BACKUP_ROOT = tmp_path
    archive = tmp_path / 'own-backup.tar.gz'
    archive.write_bytes(b'fixture awaiting checksum verification')
    job = BackupJob.objects.create(requested_by=superadmin_user, status='completed',
        destination_path=str(tmp_path), archive_path=str(archive), checksum='a' * 64,
        manifest={'database_sha256': 'b' * 64, 'asset_count': 0})
    api_client.force_authenticate(superadmin_user)
    return job, f'/api/distribution/backups/{job.pk}/check/'


def request(job, operation='verify', **changes):
    return {'operation': operation, 'expected_checksum': job.checksum,
            'request_key': str(uuid4()), **changes}


def test_backup_checks_report_unknown_legacy_without_invented_times(api_client, backup_check):
    job, url = backup_check
    response = api_client.get(url)
    assert response.status_code == 200
    assert response['Cache-Control'] == 'private, no-store'
    assert response.data['verification'] is None
    assert response.data['rehearsal'] is None
    assert response.data['history']['count'] == 0 and response.data['history']['results'] == []
    job.refresh_from_db()
    assert job.manifest == {'database_sha256': 'b' * 64, 'asset_count': 0}


def test_backup_check_queue_replay_and_running_conflict(api_client, backup_check):
    job, url = backup_check
    body = request(job)
    queued = api_client.post(url, body, format='json')
    assert queued.status_code == 202
    assert queued.data['verification']['status'] == 'queued'
    assert queued.data['verification']['checked_at'] is None
    job.refresh_from_db()
    assert job.status == 'completed' and job.checksum == 'a' * 64
    assert job.manifest['asset_count'] == 0
    assert AuditEvent.objects.filter(action='backup.check.requested', object_id=str(job.pk)).count() == 1
    replay = api_client.post(url, body, format='json')
    assert replay.status_code == 200 and replay.data['replay'] is True
    assert AuditEvent.objects.filter(action='backup.check.requested', object_id=str(job.pk)).count() == 1
    assert api_client.post(url, request(job), format='json').status_code == 409
    assert api_client.post(url, {**body, 'operation': 'restore_rehearsal', 'confirm_isolated': True}, format='json').status_code == 409


def test_backup_check_owner_boundary_for_new_read_and_write(api_client, admin_user, backup_check):
    job, url = backup_check
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 403
    assert api_client.post(url, request(job), format='json').status_code == 403
    assert not AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk)).exists()


def test_backup_check_stale_digest_and_unconfirmed_restore_are_rejected(api_client, backup_check):
    job, url = backup_check
    assert api_client.post(url, request(job, expected_checksum='c' * 64), format='json').status_code == 409
    assert api_client.post(url, request(job, 'restore_rehearsal'), format='json').status_code == 400
    assert api_client.post(url, request(job, 'production'), format='json').status_code == 400
    assert not AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk)).exists()


def prepare_archive(job, *, original=False, tampered=False, database_name='database.dump'):
    dump = b'own fixture database bytes'
    photo = b'own original fixture bytes'
    manifest = {'database': database_name, 'database_sha256': hashlib.sha256(dump).hexdigest(),
        'include_originals': original, 'database_metadata': {}, 'migration_heads': [],
        'assets': [{'kind': 'original', 'exists': True, 'relative_path': 'originals/own.pdf',
            'byte_size': len(photo), 'sha256': hashlib.sha256(photo).hexdigest()}] if original else []}
    with tarfile.open(job.archive_path, 'w:gz') as tar:
        items = [('manifest.json', json.dumps(manifest).encode()), (database_name, dump)]
        if original:
            items.append(('originals/originals/own.pdf', b'x' * len(photo) if tampered else photo))
        for name, content in items:
            member = tarfile.TarInfo(name); member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    job.checksum = file_sha256(Path(job.archive_path))
    job.include_originals = original
    job.manifest = {**job.manifest, 'database_sha256': manifest['database_sha256']}
    job.save(update_fields=['checksum', 'include_originals', 'manifest', 'updated_at'])
    return manifest


def test_real_archive_verification_records_time_without_rewriting_archive_or_job(api_client, backup_check):
    job, url = backup_check
    prepare_archive(job)
    before = Path(job.archive_path).read_bytes()
    body = request(job)
    assert api_client.post(url, body, format='json').status_code == 202
    perform_check(str(job.pk), 'verify', body['request_key'])
    response = api_client.get(url)
    checked = response.data['verification']
    assert checked['status'] == 'completed' and checked['checked_at'] and checked['started_at']
    assert checked['result']['archive_checksum'] == job.checksum
    assert checked['result']['database_checksum'] == job.manifest['database_sha256']
    assert checked['result']['original_files_restored'] is False
    assert Path(job.archive_path).read_bytes() == before
    job.refresh_from_db()
    assert job.status == 'completed' and job.manifest['asset_count'] == 0
    count = AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk)).count()
    perform_check(str(job.pk), 'verify', body['request_key'])
    assert AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk)).count() == count


def test_corrupt_archive_retains_failed_check_and_original_backup_state(api_client, backup_check):
    job, url = backup_check
    prepare_archive(job)
    body = request(job)
    assert api_client.post(url, body, format='json').status_code == 202
    with Path(job.archive_path).open('ab') as handle:
        handle.write(b'changed archive')
    with pytest.raises(DatabaseBackupError, match='checksum mismatch'):
        perform_check(str(job.pk), 'verify', body['request_key'])
    checked = api_client.get(url).data['verification']
    assert checked['status'] == 'failed' and checked['checked_at'] and checked['error_message']
    job.refresh_from_db()
    assert job.status == 'completed' and job.checksum == body['expected_checksum']


@pytest.mark.parametrize('tampered', [False, True])
def test_included_original_bytes_are_verified_not_just_manifest_labels(api_client, backup_check, tampered):
    job, url = backup_check
    prepare_archive(job, original=True, tampered=tampered)
    body = request(job)
    assert api_client.post(url, body, format='json').status_code == 202
    if tampered:
        with pytest.raises(DatabaseBackupError, match='original checksum mismatch'):
            perform_check(str(job.pk), 'verify', body['request_key'])
        assert api_client.get(url).data['verification']['status'] == 'failed'
    else:
        perform_check(str(job.pk), 'verify', body['request_key'])
        assert api_client.get(url).data['verification']['result']['originals_verified'] == 1


def test_backup_outside_configured_root_cannot_be_queued(api_client, backup_check, tmp_path):
    job, url = backup_check
    outside = tmp_path.parent / f'own-outside-{uuid4().hex}.tar.gz'
    outside.write_bytes(b'own outside-root fixture')
    job.archive_path = str(outside)
    job.save(update_fields=['archive_path', 'updated_at'])
    assert api_client.post(url, request(job), format='json').status_code == 400
    assert not AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk)).exists()


def test_database_extraction_rejects_path_traversal_without_writing_outside(api_client, backup_check, tmp_path):
    job, _ = backup_check
    prepare_archive(job, database_name='../outside.dump')
    destination = tmp_path / 'extract'; destination.mkdir()
    with pytest.raises(DatabaseBackupError, match='path is unsafe'):
        extract_backup_database(Path(job.archive_path), destination)
    assert not (tmp_path / 'outside.dump').exists()


def test_rehearsal_history_does_not_promote_intermediate_verification(api_client, backup_check, superadmin_user):
    job, url = backup_check
    key = str(uuid4())
    base = {'operation': 'restore_rehearsal', 'request_key': key, 'status': 'queued'}
    for action, item in [('requested', base), ('started', {**base, 'status': 'running'}),
                         ('verified', {**base, 'operation': 'verify', 'status': 'completed'})]:
        AuditEvent.objects.create(actor=superadmin_user, action=f'backup.check.{action}',
            object_type='backup_job', object_id=str(job.pk), request_id=key, after=item)
    history = api_client.get(url).data['history']
    assert history['count'] == 1 and history['results'][0]['operation'] == 'restore_rehearsal'
    assert history['results'][0]['status'] == 'running'


def test_queued_check_rechecks_owner_and_request_key_cannot_cross_actors(api_client, backup_check, admin_user, settings):
    job, url = backup_check
    body = request(job)
    assert api_client.post(url, body, format='json').status_code == 202
    settings.LIBRARY_OWNER_EMAIL = admin_user.email
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, body, format='json').status_code == 409
    with pytest.raises(DatabaseBackupError, match='权限已变化'):
        perform_check(str(job.pk), 'verify', body['request_key'])
    checked = api_client.get(url).data['verification']
    assert checked['status'] == 'failed' and '权限已变化' in checked['error_message']
    assert AuditEvent.objects.filter(action='backup.check.requested', object_id=str(job.pk)).count() == 1


@pytest.mark.postgres_integration
@pytest.mark.django_db(transaction=True)
def test_actual_postgres_backup_restore_and_disposal_preserve_source(api_client, superadmin_user, settings, tmp_path, monkeypatch):
    from django.db import connection
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from distribution.tasks import create_backup_archive
    if connection.vendor != 'postgresql':
        pytest.skip('Actual dump, restore and disposal require PostgreSQL.')
    settings.NAS_BACKUP_ROOT = tmp_path
    job = BackupJob.objects.create(requested_by=superadmin_user, destination_path=str(tmp_path), include_originals=False)
    create_backup_archive.run(str(job.pk)); job.refresh_from_db()
    archive_before = Path(job.archive_path).read_bytes()
    before = {}
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()'); source = cursor.fetchone()[0]
        for table in ('catalog_work', 'catalog_edition', 'accounts_user'):
            cursor.execute('SELECT COUNT(*) FROM ' + connection.ops.quote_name(table)); before[table] = cursor.fetchone()[0]
    with pytest.raises(CommandError, match='must be empty'):
        call_command('rehearse_database_restore', job.archive_path, confirm_disposable_database=source)
    # Only transport is stubbed: the archive, PostgreSQL dump/restore and queries are real.
    monkeypatch.setattr('distribution.tasks.run_backup_check.apply_async', lambda **kwargs: None)
    api_client.force_authenticate(superadmin_user)
    body = request(job, 'restore_rehearsal', confirm_isolated=True)
    url = f'/api/distribution/backups/{job.pk}/check/'
    assert api_client.post(url, body, format='json').status_code == 202
    perform_check(str(job.pk), 'restore_rehearsal', body['request_key'])
    response = api_client.get(url)
    result = response.data['rehearsal']
    assert result['status'] == 'completed' and result['result']['database_restored']
    assert result['result']['migration_heads_match'] and result['result']['isolated_database_removed']
    assert result['result']['row_counts'] == before and result['result']['original_files_restored'] is False
    assert response.data['history']['count'] == 1 and response.data['history']['results'][0]['status'] == 'completed'
    assert Path(job.archive_path).read_bytes() == archive_before
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()'); assert cursor.fetchone()[0] == source
        cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', ['stl_restore_rehearsal_' + UUID(body['request_key']).hex])
        assert cursor.fetchone() is None
        for table, count in before.items():
            cursor.execute('SELECT COUNT(*) FROM ' + connection.ops.quote_name(table)); assert cursor.fetchone()[0] == count
