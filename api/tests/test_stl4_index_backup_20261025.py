"""Deferred index backup acceptance; local fixtures and mocked service only."""
from hashlib import sha256
from io import BytesIO
import json
import tarfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from distribution.backup_integrity import BackupIntegrityError, verify_archive
from distribution.index_backup import capture_search_index, _copy_dump
from distribution.models import BackupJob, BackupSchedule
from distribution.storage_tasks import dispatch_due_backups
from distribution.storage_views import StorageCommandInput


def configured(settings, tmp_path):
    settings.MEILISEARCH_URL = 'http://search-fixture:7700'
    settings.MEILISEARCH_MASTER_KEY = 'isolated-fixture-not-a-real-key'
    settings.MEILISEARCH_DUMP_ROOT = str(tmp_path)


@pytest.mark.django_db
def test_export_receipt_is_saved_before_poll_and_retry_does_not_post_again(settings, tmp_path, superadmin_user):
    configured(settings, tmp_path)
    staging = tmp_path / 'stage'; staging.mkdir()
    (tmp_path / 'fixture-dump.dump').write_bytes(b'index fixture')
    job = BackupJob.objects.create(requested_by=superadmin_user, destination_path=str(tmp_path), status='running',
                                  started_at=timezone.now(), include_indexes=True, index_only=True)
    enqueued = timezone.now().isoformat()
    def service(method, path):
        if path == '/version': return {'pkgVersion': '1.37.0'}
        if method == 'POST':
            job.refresh_from_db(); assert job.manifest['search_index_export']['task_uid'] is None
            return {'taskUid': 31, 'type': 'dumpCreation', 'enqueuedAt': enqueued}
        job.refresh_from_db(); assert job.manifest['search_index_export']['task_uid'] == 31
        return {'uid': 31, 'type': 'dumpCreation', 'enqueuedAt': enqueued, 'status': 'succeeded', 'details': {'dumpUid': 'fixture-dump'}}
    with patch('distribution.index_backup._request', side_effect=service) as request:
        result = capture_search_index(job, staging, lambda: None)
        assert result['sha256'] == sha256(b'index fixture').hexdigest()
        assert result['database_snapshot_shared'] is False
        retry = tmp_path / 'retry'; retry.mkdir()
        capture_search_index(job, retry, lambda: None)
        assert sum(call.args[0] == 'POST' for call in request.call_args_list) == 1


def test_unknown_export_and_changed_task_identity_never_submit_again(settings, tmp_path):
    configured(settings, tmp_path)
    receipt = {'endpoint': sha256(settings.MEILISEARCH_URL.encode()).hexdigest(), 'version': '1.37.0', 'task_uid': None}
    job = SimpleNamespace(manifest={'search_index_export': receipt})
    with patch('distribution.index_backup._request', return_value={'pkgVersion': '1.37.0'}) as request:
        with pytest.raises(BackupIntegrityError): capture_search_index(job, tmp_path, lambda: None)
        assert all(call.args[0] == 'GET' for call in request.call_args_list)
    receipt.update(task_uid=31, enqueued_at='old-instance-time')
    with patch('distribution.index_backup._request', side_effect=[{'pkgVersion': '1.37.0'}, {'uid': 31, 'type': 'dumpCreation', 'enqueuedAt': 'new-instance-time'}]) as request:
        with pytest.raises(BackupIntegrityError): capture_search_index(job, tmp_path, lambda: None)
        assert all(call.args[0] == 'GET' for call in request.call_args_list)


def test_dump_copy_refuses_path_escape_and_preserves_source(tmp_path):
    staging = tmp_path / 'stage'; staging.mkdir()
    with pytest.raises(BackupIntegrityError): _copy_dump(tmp_path, '../escape', staging, lambda: None)
    source = tmp_path / 'valid.dump'; source.write_bytes(b'preserve source')
    result = _copy_dump(tmp_path, 'valid', staging, lambda: None)
    assert source.read_bytes() == (staging / 'search-index.dump').read_bytes()
    assert result['byte_size'] == 15


def test_index_only_archive_does_not_claim_database_or_restoration(settings, tmp_path):
    settings.NAS_BACKUP_ROOT = tmp_path
    content = b'index fixture'
    manifest = {'schema': 3, 'index_only': True, 'include_originals': False, 'assets': [],
                'search_index': {'engine': 'meilisearch', 'filename': 'search-index.dump', 'version': '1.37.0',
                'scope': 'all-instance-indexes', 'database_snapshot_shared': False,
                'sha256': sha256(content).hexdigest(), 'byte_size': len(content)}}
    archive = tmp_path / 'index.tar.gz'
    with tarfile.open(archive, 'w:gz') as bundle:
        for name, payload in {'manifest.json': json.dumps(manifest).encode(), 'search-index.dump': content}.items():
            info = tarfile.TarInfo(name); info.size = len(payload); bundle.addfile(info, BytesIO(payload))
    checksum = sha256(archive.read_bytes()).hexdigest()
    row = SimpleNamespace(archive_path=str(archive), checksum=checksum, include_originals=False,
                          index_only=True, include_indexes=True, incremental_base_id=None)
    result = verify_archive(row, checksum)
    assert result['index_verified'] and not result['database_verified'] and not result['restore_verified']


@pytest.mark.django_db
def test_failed_scheduled_index_backup_pauses_before_any_remote_retry(superadmin_user, tmp_path, settings):
    configured(settings, tmp_path); settings.NAS_BACKUP_ROOT = tmp_path
    job = BackupJob.objects.create(requested_by=superadmin_user, destination_path=str(tmp_path), status='failed', include_indexes=True, index_only=True)
    plan = BackupSchedule.objects.create(scope='indexes', enabled=True, include_indexes=True, configured_by=superadmin_user,
                                       last_job=job, next_run_at=timezone.now())
    with patch('distribution.storage_tasks.enqueue_authorized_backup', side_effect=AssertionError('No automatic retry')):
        dispatch_due_backups.run()
    plan.refresh_from_db()
    assert not plan.enabled and plan.last_job_id == job.pk and plan.next_run_at is None


def test_index_only_cannot_include_originals_or_omit_index_payload():
    command = {'operation': 'create_backup', 'request_id': str(uuid4()), 'include_originals': False, 'index_only': True, 'include_indexes': True}
    assert StorageCommandInput(data=command).is_valid()
    for changed in ({'include_originals': True}, {'include_indexes': False}):
        assert not StorageCommandInput(data={**command, **changed}).is_valid()
