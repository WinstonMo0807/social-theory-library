"""Read the original signed rehearsal files in bounded, navigable windows."""
from datetime import timezone as datetime_timezone
from hashlib import sha256
from heapq import nlargest
import json
import os
import re
import stat

from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.dateparse import parse_datetime

NAME = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\.json$')
SHA = re.compile(r'^[a-f0-9]{64}$')
SALT = 'stl-backup-restore-rehearsal-v1'
DETAIL = '已在空白隔离 PostgreSQL 中完成导入；应用功能、文件和索引恢复仍待核对。'


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def read_report(path, expected, as_of):
    """Read at most 64 KiB, refuse special files and never expose report internals."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or identity(before) != identity(expected) or before.st_size > 65536:
            raise ValueError('Report changed or exceeds the read limit')
        raw = handle.read(65537)
        if len(raw) > 65536 or identity(os.fstat(handle.fileno())) != identity(before):
            raise ValueError('Report changed during read')
    envelope = json.loads(raw)
    token = envelope.get('signed_report') if isinstance(envelope, dict) else None
    if not isinstance(token, str) or token.startswith('.'):
        raise ValueError('Unsupported report envelope')
    report = signing.loads(token, salt=SALT)
    if not isinstance(report, dict) or report.get('status') != 'restored':
        raise ValueError('No successful isolated restore evidence')
    checked_at = parse_datetime(report.get('checked_at', '')) if isinstance(report.get('checked_at'), str) else None
    checksum = report.get('archive_sha256')
    if not checked_at or timezone.is_naive(checked_at) or checked_at > as_of or not isinstance(checksum, str) or not SHA.fullmatch(checksum):
        raise ValueError('Invalid report identity')
    if checked_at.astimezone(datetime_timezone.utc).strftime('%Y%m%dT%H%M%S') != path.name[:15]:
        raise ValueError('Report filename does not match its signed time')
    return {'id': sha256(path.name.encode()).hexdigest(), 'checked_at': checked_at.isoformat(), 'archive_sha256': checksum,
            'status': 'database_restored', 'detail': DETAIL}


def report_window(*, after='', as_of=None, checksum=None, limit=20):
    """Scan names only across the directory; open at most limit selected files."""
    as_of = as_of or timezone.now()
    root = settings.NAS_BACKUP_ROOT.resolve()
    directory = root / 'rehearsals'
    result = {'as_of': as_of, 'source_status': 'available', 'source_identity': '', 'candidate_count': 0,
              'inspected_count': 0, 'unverified_count': 0, 'filtered_count': 0, 'directory_errors': 0,
              'results': [], 'next_after': '', 'notice': '按原签名文件目录分页。文件数不是成功演练数；只核对签名与报告身份，不执行恢复。'}
    try:
        if not root.is_dir():
            raise OSError('Backup root is unavailable')
        if directory.is_symlink():
            raise OSError('Unsupported report directory')
        if not directory.exists():
            result['source_status'] = 'missing'
            result['notice'] = '尚未建立恢复演练记录目录。'
            return result
        original = directory.lstat()
        if directory.is_symlink() or not stat.S_ISDIR(original.st_mode):
            raise OSError('Unsupported report directory')
        result['source_identity'] = sha256(f'{directory}:{original.st_dev}:{original.st_ino}'.encode()).hexdigest()
        def candidates(entries):
            for entry in entries:
                if not NAME.fullmatch(entry.name):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_mtime > as_of.timestamp():
                        continue
                    result['candidate_count'] += 1
                    if not after or entry.name < after:
                        yield entry.name, info
                except OSError:
                    result['directory_errors'] += 1
        with os.scandir(directory) as entries:
            selected = nlargest(limit + 1, candidates(entries), key=lambda item: item[0])
        if len(selected) > limit:
            result['next_after'] = selected[limit - 1][0]
        for name, info in selected[:limit]:
            result['inspected_count'] += 1
            try:
                report = read_report(directory / name, info, as_of)
                if checksum and report['archive_sha256'] != checksum:
                    result['filtered_count'] += 1
                    continue
                result['results'].append(report)
            except (OSError, ValueError, TypeError, KeyError, RecursionError, signing.BadSignature):
                result['unverified_count'] += 1
        current = directory.lstat()
        if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise OSError('Report directory changed')
        result['results'].sort(key=lambda report: parse_datetime(report['checked_at']), reverse=True)
    except OSError:
        result.update(source_status='unavailable', results=[], next_after='', notice='无法安全读取恢复记录目录，请核对备份挂载与权限；这不代表没有恢复记录。')
    return result
