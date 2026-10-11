"""Checks derive evidence from immutable archives; restore only a new disposable DB."""
from copy import deepcopy
from pathlib import Path, PurePosixPath
from uuid import UUID
import hashlib
import tarfile
import tempfile

from django.conf import settings
from django.db import connection, connections, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from common.capabilities import Capability, has_capability

from ingestion.models import AuditEvent
from .database_backup import (DatabaseBackupError, applied_migration_heads, extract_backup_database,
    file_sha256, redact_backup_error, rehearse_database_archive)
from .models import BackupJob


class BackupCheckConflict(APIException):
    status_code = 409
    default_detail = "备份或检查任务已变化。请重新读取后再核对。"


def archive_path(job):
    root = settings.NAS_BACKUP_ROOT.resolve()
    path = Path(job.archive_path).resolve()
    if job.status != 'completed' or not job.checksum or not job.archive_path:
        raise ValidationError("只能校验已完成且有校验值的备份。")
    if root not in path.parents or not path.is_file():
        raise ValidationError("备份归档未位于可读取的备份根目录内。")
    return path


def current_check(job, operation):
    item = job.manifest.get('backup_checks', {}).get(operation)
    return item if isinstance(item, dict) and item.get('archive_checksum') == job.checksum else None


def check_state(job, page=1):
    requested = AuditEvent.objects.filter(action='backup.check.requested', object_type='backup_job',
        object_id=str(job.pk), after__operation='restore_rehearsal').order_by('-created_at', '-id')
    count = requested.count()
    keys = list(requested.values_list('request_id', flat=True)[(page - 1) * 10:page * 10])
    events = AuditEvent.objects.filter(object_type='backup_job', object_id=str(job.pk),
        action__startswith='backup.check.', request_id__in=keys,
        after__operation='restore_rehearsal').order_by('-created_at', '-id')
    latest = {}
    for event in events:
        latest.setdefault(event.request_id, event.after)
    return {'backup_id': str(job.pk), 'verification': current_check(job, 'verify'),
        'rehearsal': current_check(job, 'restore_rehearsal'), 'replay': False,
        'history': {'count': count, 'page': page, 'next_page': page + 1 if page * 10 < count else None,
            'previous_page': page - 1 if page > 1 else None, 'results': [latest[key] for key in keys]}}


def _record(job, item, action, actor):
    manifest = deepcopy(job.manifest)
    checks = manifest.setdefault('backup_checks', {})
    checks[item['operation']] = item
    job.manifest = manifest
    job.save(update_fields=['manifest', 'updated_at'])
    AuditEvent.objects.create(actor=actor, action=f'backup.check.{action}', object_type='backup_job',
        object_id=str(job.pk), request_id=item['request_key'], after=item)


def queue_check(job_id, actor, data):
    operation, key = data['operation'], str(data['request_key'])
    with transaction.atomic():
        job = BackupJob.objects.select_for_update().get(pk=job_id)
        if data['expected_checksum'] != job.checksum:
            raise BackupCheckConflict()
        receipt = AuditEvent.objects.filter(action='backup.check.requested',
            object_type='backup_job', object_id=str(job.pk), request_id=key).first()
        if receipt:
            if receipt.actor_id != actor.pk or receipt.after['operation'] != operation or receipt.after['archive_checksum'] != data['expected_checksum']:
                raise BackupCheckConflict("同一请求标识不能用于另一项检查。")
            result = check_state(job)
            result['replay'] = True
            return result
        archive_path(job)
        if any((current_check(job, name) or {}).get('status') in ('queued', 'running') for name in ('verify', 'restore_rehearsal')):
            raise BackupCheckConflict("该备份正在检查，请等待实际结果后再操作。")
        item = {'operation': operation, 'request_key': key, 'status': 'queued',
            'requested_at': timezone.now().isoformat(), 'started_at': None, 'checked_at': None,
            'archive_checksum': job.checksum, 'error_message': '', 'result': {}}
        _record(job, item, 'requested', actor)
        from .tasks import run_backup_check

        def dispatch():
            try:
                run_backup_check.apply_async(args=[str(job.pk), operation, key], queue=settings.BACKUP_CHECK_TASK_QUEUE)
            except Exception:
                with transaction.atomic():
                    locked = BackupJob.objects.select_for_update().get(pk=job.pk)
                    state = current_check(locked, operation)
                    if state and state['request_key'] == key and state['status'] == 'queued':
                        state = {**state, 'status': 'failed', 'checked_at': timezone.now().isoformat(),
                            'error_message': '检查未能进入任务队列，请重新核对后重试。'}
                        _record(locked, state, 'failed', actor)
                raise APIException("检查未能进入任务队列，请重试。")
        transaction.on_commit(dispatch)
        return check_state(job)


def verify_archive(job, destination):
    archive = archive_path(job)
    checksum = file_sha256(archive)
    if checksum != job.checksum:
        raise DatabaseBackupError("Backup archive checksum mismatch.")
    manifest, dump = extract_backup_database(archive, destination)
    if manifest['database_sha256'] != job.manifest.get('database_sha256'):
        raise DatabaseBackupError("Database checksum does not match the recorded BackupJob.")
    if bool(manifest.get('include_originals')) != job.include_originals:
        raise DatabaseBackupError("Backup originals scope does not match the recorded BackupJob.")
    originals = 0
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        if len({member.name for member in members}) != len(members):
            raise DatabaseBackupError("Backup archive has duplicate members.")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise DatabaseBackupError("Backup archive has an unsafe member.")
        if job.include_originals:
            for asset in manifest.get('assets', []):
                if asset['kind'] != 'original' or not asset['exists']:
                    continue
                relative = PurePosixPath(asset['relative_path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise DatabaseBackupError("Backup original path is unsafe.")
                member = bundle.getmember(str(PurePosixPath('originals') / relative))
                if not member.isfile() or member.size != asset['byte_size']:
                    raise DatabaseBackupError("Backup original size mismatch.")
                with bundle.extractfile(member) as handle:
                    digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                if digest != asset['sha256']:
                    raise DatabaseBackupError("Backup original checksum mismatch.")
                originals += 1
    if file_sha256(archive) != checksum:
        raise DatabaseBackupError("Backup archive changed during verification.")
    return {'archive_checksum': checksum, 'database_checksum': manifest['database_sha256'],
        'archive_bytes': archive.stat().st_size, 'database_bytes': dump.stat().st_size,
        'originals_verified': originals, 'original_files_restored': False}


def restore_isolated(job, request_key):
    if connection.vendor != 'postgresql' or connection.in_atomic_block:
        raise DatabaseBackupError("An autocommit PostgreSQL connection is required for a disposable rehearsal.")
    name = 'stl_restore_rehearsal_' + UUID(request_key).hex
    source = str(connection.settings_dict['NAME'])
    assert name != source and name.startswith('stl_restore_rehearsal_') and len(name) < 63
    configuration = deepcopy(connection.settings_dict)
    configuration.update(NAME=name, CONN_MAX_AGE=0, ATOMIC_REQUESTS=False)
    target = connections['default'].__class__(configuration, alias=name)
    created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [name])
            if cursor.fetchone():
                raise DatabaseBackupError("Disposable rehearsal database already exists; it will not be reused.")
            cursor.execute('CREATE DATABASE ' + connection.ops.quote_name(name))
            created = True
            cursor.execute('REVOKE CONNECT ON DATABASE ' + connection.ops.quote_name(name) + ' FROM PUBLIC')
        report = rehearse_database_archive(archive_path(job), target, confirmation=name)
        if sorted(applied_migration_heads(target)) != sorted(report['migration_heads']):
            raise DatabaseBackupError("Restored migration heads do not match the backup manifest.")
        counts = {}
        with target.cursor() as cursor:
            for table in ('catalog_work', 'catalog_edition', 'accounts_user'):
                cursor.execute('SELECT COUNT(*) FROM ' + target.ops.quote_name(table))
                counts[table] = int(cursor.fetchone()[0])
        return {'database_restored': True, 'migration_heads_match': True, 'row_counts': counts,
            'target_server_version': report['target_server_version'], 'pg_restore_version': report['pg_restore_version'],
            'isolated_database_removed': True, 'original_files_restored': False}
    finally:
        target.close()
        if created:
            assert name == 'stl_restore_rehearsal_' + UUID(request_key).hex and name != source
            with connection.cursor() as cursor:
                cursor.execute('DROP DATABASE ' + connection.ops.quote_name(name))


def perform_check(job_id, operation, request_key):
    with transaction.atomic():
        job = BackupJob.objects.select_for_update().select_related('requested_by').get(pk=job_id)
        item = current_check(job, operation)
        if not item or item['request_key'] != request_key or item['status'] != 'queued':
            return
        receipt = AuditEvent.objects.get(action='backup.check.requested', object_type='backup_job',
            object_id=str(job.pk), request_id=request_key)
        actor = receipt.actor
        item = {**item, 'status': 'running', 'started_at': timezone.now().isoformat()}
        _record(job, item, 'started', actor)
    try:
        if not has_capability(actor, Capability.RUN_BACKUP):
            raise DatabaseBackupError("系统所有者权限已变化，检查已停止，备份归档保留。")
        with tempfile.TemporaryDirectory(prefix='backup-check-') as temporary:
            result = verify_archive(job, Path(temporary))
        verified_at = timezone.now().isoformat()
        with transaction.atomic():
            locked = BackupJob.objects.select_for_update().get(pk=job.pk)
            verification = {**item, 'operation': 'verify', 'status': 'completed', 'checked_at': verified_at, 'result': result}
            _record(locked, verification, 'verified', actor)
        if operation == 'restore_rehearsal':
            result = {**result, **restore_isolated(job, request_key)}
        item = {**item, 'status': 'completed', 'checked_at': timezone.now().isoformat(), 'result': result}
        action = 'completed'
    except Exception as exc:
        item = {**item, 'status': 'failed', 'checked_at': timezone.now().isoformat(),
            'error_message': redact_backup_error(str(exc), secrets=(settings.DATABASES['default'].get('PASSWORD'),))}
        action = 'failed'
    with transaction.atomic():
        locked = BackupJob.objects.select_for_update().get(pk=job.pk)
        current = current_check(locked, operation)
        if not current or current['request_key'] != request_key:
            raise BackupCheckConflict("任务结果与当前检查身份不一致，原记录保留。")
        _record(locked, item, action, actor)
    if action == 'failed':
        raise DatabaseBackupError(item['error_message'])
