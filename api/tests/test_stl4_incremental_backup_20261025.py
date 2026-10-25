"""Deferred acceptance definitions; no real backup or restore is invoked."""
from hashlib import sha256
from io import BytesIO
import json
import tarfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from distribution.backup_integrity import BackupIntegrityError, verify_archive
from distribution.incremental_backup import base_identity, matches_base, require_base
from distribution.models import BackupJob, BackupVerification
from distribution.storage_views import StorageCommandInput


def archive(root, name, assets, originals, base=None):
    database = b'isolated database fixture'
    manifest = {'schema': 2 if base else 1, 'database': 'database.dump',
                'database_sha256': sha256(database).hexdigest(), 'database_bytes': len(database),
                'include_originals': True, 'assets': assets}
    if base:
        manifest['incremental_base'] = base_identity(base)
    contents = {'database.dump': database, 'manifest.json': json.dumps(manifest).encode(), **originals}
    path = root / name
    with tarfile.open(path, 'w:gz') as bundle:
        for key, content in contents.items():
            info = tarfile.TarInfo(key); info.size = len(content)
            bundle.addfile(info, BytesIO(content))
    return SimpleNamespace(pk=uuid4(), archive_path=str(path), checksum=sha256(path.read_bytes()).hexdigest(),
                           include_originals=True, status='completed', incremental_base_id=base.pk if base else None)


def test_delta_verifies_base_and_changed_originals_without_restoring_deleted_files(settings, tmp_path):
    settings.NAS_BACKUP_ROOT = tmp_path
    old = {'id': str(uuid4()), 'kind': 'original', 'relative_path': 'old.pdf', 'sha256': sha256(b'old').hexdigest(), 'byte_size': 3}
    removed = {**old, 'id': str(uuid4()), 'relative_path': 'removed.pdf'}
    added = {**old, 'id': str(uuid4()), 'relative_path': 'new.pdf', 'sha256': sha256(b'new').hexdigest(), 'backup_storage': 'archive'}
    base = archive(tmp_path, 'base.tar.gz', [old, removed], {'originals/old.pdf': b'old', 'originals/removed.pdf': b'old'})
    delta = archive(tmp_path, 'delta.tar.gz', [{**old, 'backup_storage': 'base'}, added], {'originals/new.pdf': b'new'}, base)
    with patch('distribution.incremental_backup.require_base', return_value=base):
        report, manifest = verify_archive(delta, delta.checksum, return_manifest=True)
        assert report['originals_verified'] == 2 and report['base_originals_verified'] == 1
        assert not report['restore_verified']
        assert 'removed.pdf' not in {item['relative_path'] for item in manifest['assets']}
        (tmp_path / 'base.tar.gz').write_bytes(b'corrupt baseline')
        with pytest.raises(BackupIntegrityError):
            verify_archive(delta, delta.checksum)


def test_changes_cannot_reuse_a_different_asset_or_content():
    original = {'id': 'asset-1', 'relative_path': 'original.pdf', 'sha256': 'a' * 64, 'byte_size': 10}
    base = {'original.pdf': original}
    assert matches_base(original, base)
    for changed in ({'id': 'asset-2'}, {'sha256': 'b' * 64}, {'byte_size': 11}):
        assert not matches_base({**original, **changed}, base)


@pytest.mark.django_db
def test_latest_failed_verification_blocks_new_delta_and_dependent_baseline_is_protected(superadmin_user):
    base = BackupJob.objects.create(requested_by=superadmin_user, destination_path='unused', include_originals=True, status='completed', checksum='a' * 64)
    BackupVerification.objects.create(backup=base, requested_by=superadmin_user, expected_checksum=base.checksum, status='completed')
    assert require_base(base.pk, base.checksum).pk == base.pk
    delta = BackupJob.objects.create(requested_by=superadmin_user, destination_path='unused', include_originals=True, incremental_base=base, status='completed', checksum='b' * 64)
    with pytest.raises(BackupIntegrityError):
        require_base(delta.pk, delta.checksum)
    BackupVerification.objects.create(backup=base, requested_by=superadmin_user, expected_checksum=base.checksum, status='failed')
    with pytest.raises(BackupIntegrityError):
        require_base(base.pk, base.checksum)
    with pytest.raises(ProtectedError):
        base.delete()


@pytest.mark.django_db
def test_receipt_fixes_incremental_identity_and_preserves_one_job(superadmin_user, settings, tmp_path):
    settings.NAS_BACKUP_ROOT = tmp_path
    base = BackupJob.objects.create(requested_by=superadmin_user, destination_path=str(tmp_path), include_originals=True, status='completed', checksum='a' * 64)
    BackupVerification.objects.create(backup=base, requested_by=superadmin_user, expected_checksum=base.checksum, status='completed')
    client = APIClient(); client.force_authenticate(user=superadmin_user)
    client.credentials(HTTP_X_EDITOR_OWNER=str(superadmin_user.pk))
    url = '/api/distribution/storage/commands/'
    body = {'operation': 'create_backup', 'request_id': str(uuid4()), 'include_originals': True,
            'base_backup_id': str(base.pk), 'expected_base_checksum': base.checksum}
    with patch('distribution.storage_tasks.enqueue_authorized_backup'):
        first = client.post(url, body, format='json')
        assert first.status_code == 200
        assert client.post(url, body, format='json').data == first.data
        assert client.post(url, {**body, 'expected_base_checksum': 'b' * 64}, format='json').status_code == 409
    assert BackupJob.objects.filter(pk=body['request_id'], incremental_base=base).count() == 1


def test_disabled_plan_cannot_change_baseline_without_matching_checksum():
    data = {'operation': 'save_schedule', 'request_id': str(uuid4()), 'scope': 'incremental',
            'enabled': False, 'interval_hours': 24, 'expected_version': 'unconfigured', 'base_backup_id': str(uuid4())}
    assert not StorageCommandInput(data=data).is_valid()
