"""A full database snapshot plus file changes against one verified full baseline."""
from .models import BackupJob
from .backup_integrity import BackupIntegrityError, verify_archive, _name


def require_base(identifier, checksum=None):
    base = BackupJob.objects.filter(pk=identifier, status='completed', include_originals=True, incremental_base__isnull=True).first()
    if not base or not base.checksum or checksum is not None and base.checksum != checksum:
        raise BackupIntegrityError('增量基准必须是指定的已完成全量原件备份，且归档身份未变化。')
    last = base.verifications.filter(expected_checksum=base.checksum).order_by('-created_at','-pk').first()
    if not last or last.status != 'completed':
        raise BackupIntegrityError('请先完成这份全量备份的归档校验，再将其作为增量基准。')
    return base


def verified_base_manifest(base):
    if base.incremental_base_id or not base.include_originals or base.status != 'completed':
        raise BackupIntegrityError('增量备份只引用一份完整原件基准，不串联其他增量归档。')
    _, manifest = verify_archive(base, base.checksum, return_manifest=True)
    if manifest.get('schema') != 1 or manifest.get('incremental_base'):
        raise BackupIntegrityError('基准备份不是完整的独立原件归档。')
    return {item['relative_path']: item for item in manifest['assets'] if item.get('kind') == 'original'}


def base_identity(base):
    return {'id': str(base.pk), 'archive_sha256': base.checksum}


def matches_base(record, originals):
    previous = originals.get(_name(record['relative_path']))
    return bool(previous and previous.get('id') == record['id'] and previous.get('sha256') == record['sha256']
                and record['sha256'] and (not previous.get('byte_size') or not record.get('byte_size') or previous['byte_size'] == record['byte_size']))
