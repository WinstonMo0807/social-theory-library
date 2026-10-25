"""Export the configured search instance into the existing private backup archive."""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import time

from django.conf import settings
from django.utils import timezone
from catalog.services.discovery_projection import meili, DiscoveryIndexError
from .backup_integrity import BackupIntegrityError
from .models import BackupJob


def index_backup_configured():
    return bool(settings.MEILISEARCH_DUMP_ROOT and settings.MEILISEARCH_URL and settings.MEILISEARCH_MASTER_KEY)


def _request(method, path):
    try:
        result = meili(method, path)
    except DiscoveryIndexError as error:
        raise BackupIntegrityError('索引导出服务未返回可确认结果。已登记的导出任务会保留；不要据此认定远端未执行。') from error
    if not isinstance(result, dict):
        raise BackupIntegrityError('索引导出服务返回了无法识别的记录。')
    return result


def _copy_dump(root, dump_uid, staging, guard):
    if not isinstance(dump_uid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', dump_uid):
        raise BackupIntegrityError('索引导出文件身份无效。')
    source = root / (dump_uid + '.dump')
    if source.is_symlink() or source.resolve().parent != root:
        raise BackupIntegrityError('索引导出文件离开已配置的共享目录。')
    descriptor = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    digest = sha256(); size = 0
    with os.fdopen(descriptor, 'rb') as origin:
        before = os.fstat(origin.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= int(getattr(settings, 'BACKUP_VERIFY_MAX_BYTES', 2 * 1024**4)):
            raise BackupIntegrityError('索引导出不是可用的完整文件或超出单次备份范围。')
        with (staging / 'search-index.dump').open('xb') as destination:
            while chunk := origin.read(1024 * 1024):
                guard(); size += len(chunk)
                if size > before.st_size:
                    raise BackupIntegrityError('索引导出在读取期间增长，未登记完成。')
                destination.write(chunk); digest.update(chunk)
        after = os.fstat(origin.fileno())
        current = source.stat()
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        if size != before.st_size or identity(before) != identity(after) or identity(before) != identity(current):
            raise BackupIntegrityError('索引导出在复制期间发生变化，未登记完成。')
    return {'filename': 'search-index.dump', 'sha256': digest.hexdigest(), 'byte_size': size}


def capture_search_index(job, staging, guard):
    if not index_backup_configured():
        raise BackupIntegrityError('索引备份共享目录尚未配置，请先完成同一索引实例的只读导出挂载。')
    root = Path(settings.MEILISEARCH_DUMP_ROOT).resolve()
    if not root.is_dir():
        raise BackupIntegrityError('索引导出共享目录不可读，未发起远端导出。')
    endpoint = sha256(settings.MEILISEARCH_URL.rstrip('/').encode()).hexdigest()
    version = _request('GET', '/version').get('pkgVersion')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9A-Za-z.+_-]{1,64}', version):
        raise BackupIntegrityError('无法登记检索服务版本，未发起索引导出。')
    receipt = job.manifest.get('search_index_export') if isinstance(job.manifest, dict) else None
    if receipt and (not isinstance(receipt, dict) or receipt.get('endpoint') != endpoint or receipt.get('version') != version):
        raise BackupIntegrityError('检索实例配置已变化，不能复用此前的导出任务。')
    if receipt and type(receipt.get('task_uid')) is not int:
        raise BackupIntegrityError('上次索引导出响应未知。请核对该实例的任务记录；本次不会重新提交导出。')
    if not receipt:
        receipt = {'endpoint': endpoint, 'version': version, 'requested_at': timezone.now().isoformat(), 'task_uid': None}
        job.manifest = {**job.manifest, 'search_index_export': receipt}
        guard()
        if not BackupJob.objects.filter(pk=job.pk, status='running', started_at=job.started_at).update(manifest=job.manifest, updated_at=timezone.now()):
            raise BackupIntegrityError('原备份已关闭，未提交索引导出。')
        response = _request('POST', '/dumps')
        task_uid, enqueued_at = response.get('taskUid'), response.get('enqueuedAt')
        if type(task_uid) is not int or task_uid < 0 or response.get('type') != 'dumpCreation' or not isinstance(enqueued_at, str) or len(enqueued_at) > 80:
            raise BackupIntegrityError('索引导出响应缺少可信任务身份，请核对远端记录，不自动重发。')
        receipt = {**receipt, 'task_uid': task_uid, 'enqueued_at': enqueued_at}
        job.manifest = {**job.manifest, 'search_index_export': receipt}
        BackupJob.objects.filter(pk=job.pk, status='running', started_at=job.started_at).update(manifest=job.manifest, updated_at=timezone.now())
    # ponytail: bounded synchronous polling in the original worker; very large
    # instances need resumable delivery, never a second automatic POST on timeout.
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        guard()
        task = _request('GET', '/tasks/' + str(receipt['task_uid']))
        if type(task.get('uid')) is not int or task['uid'] != receipt['task_uid'] or task.get('type') != 'dumpCreation' or task.get('enqueuedAt') != receipt.get('enqueued_at'):
            raise BackupIntegrityError('远端导出任务身份已变化，不能读取同编号的其他任务。')
        status_value = task.get('status')
        if status_value == 'succeeded':
            break
        if status_value not in {'enqueued', 'processing'}:
            raise BackupIntegrityError('索引导出未成功。原索引保留；请核对任务服务后重新选择备份。')
        time.sleep(2)
    else:
        raise BackupIntegrityError('索引导出仍未完成。任务编号已保留，重试会继续核对同一导出，不重复提交。')
    details = task.get('details')
    dump_uid = details.get('dumpUid') if isinstance(details, dict) else None
    result = _copy_dump(root, dump_uid, staging, guard)
    if _request('GET', '/version').get('pkgVersion') != version:
        raise BackupIntegrityError('索引服务版本在备份期间变化，导出文件保留，未登记归档完成。')
    return {**result, 'engine': 'meilisearch', 'version': version, 'task_uid': receipt['task_uid'],
            'dump_uid': dump_uid, 'scope': 'all-instance-indexes', 'database_snapshot_shared': False}
