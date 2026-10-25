"""Deferred signed-file pagination, isolation and partial-history checks."""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import json
import os
from uuid import uuid4

import pytest
from django.core import signing
from django.utils import timezone
from rest_framework.test import APIClient

from distribution.models import BackupJob
from distribution.restore_history import report_window, read_report, SALT

URL = '/api/distribution/storage/rehearsals/'


def report_file(root, checked_at, checksum='a'*64, **overrides):
    directory = root / 'rehearsals'; directory.mkdir(exist_ok=True)
    path = directory / f"{checked_at.strftime('%Y%m%dT%H%M%S')}-{uuid4()}.json"
    body = {'status':'restored', 'checked_at':checked_at.isoformat(), 'archive_sha256':checksum,
            'database':'private database name', **overrides}
    path.write_text(json.dumps({'signed_report':signing.dumps(body, salt=SALT)}), encoding='utf-8')
    os.utime(path, (checked_at.timestamp(), checked_at.timestamp()))
    return path


def test_more_than_500_report_files_remain_reachable_with_bounded_reads(tmp_path, settings):
    settings.NAS_BACKUP_ROOT = tmp_path
    start = timezone.now() - timedelta(days=2)
    for index in range(523):
        report_file(tmp_path, start+timedelta(seconds=index))
    as_of = timezone.now(); after=''; seen=set()
    while True:
        with patch('distribution.restore_history.read_report', wraps=read_report) as read:
            page = report_window(after=after, as_of=as_of)
        assert read.call_count <= 20 and page['candidate_count'] == 523
        current={row['id'] for row in page['results']}
        assert not seen & current
        seen.update(current)
        assert 'private database name' not in str(page)
        if not page['next_after']:break
        after=page['next_after']
    assert len(seen)==523


def test_bad_reports_and_filtered_windows_are_not_success_or_end_of_history(tmp_path, settings):
    settings.NAS_BACKUP_ROOT=tmp_path; start=timezone.now()-timedelta(hours=1)
    report_file(tmp_path,start,'a'*64)
    for index in range(1,22):report_file(tmp_path,start+timedelta(seconds=index),'b'*64)
    malformed=report_file(tmp_path,start+timedelta(seconds=30),'a'*64)
    malformed.write_text('{"signed_report":"invalid"}',encoding='utf-8')
    oversized=report_file(tmp_path,start+timedelta(seconds=31),'a'*64)
    oversized.write_text('x'*65537,encoding='utf-8')
    first=report_window(checksum='a'*64)
    assert first['results']==[] and first['unverified_count']==2 and first['next_after']
    second=report_window(after=first['next_after'],as_of=first['as_of'],checksum='a'*64)
    assert len(second['results'])==1 and second['results'][0]['archive_sha256']=='a'*64
    with patch('distribution.restore_history.os.scandir',side_effect=PermissionError):
        unavailable=report_window()
    assert unavailable['source_status']=='unavailable' and unavailable['results']==[]
    settings.NAS_BACKUP_ROOT=tmp_path/'missing-backup-volume'
    assert report_window()['source_status']=='unavailable'


def test_changed_report_and_future_signed_time_are_not_used(tmp_path, settings):
    settings.NAS_BACKUP_ROOT=tmp_path; now=timezone.now()
    path=report_file(tmp_path,now-timedelta(minutes=1)); previous=path.stat()
    path.write_text('changed',encoding='utf-8')
    os.utime(path,(previous.st_atime,previous.st_mtime))
    with pytest.raises(ValueError):read_report(path,previous,now)
    future=report_file(tmp_path,now+timedelta(days=1))
    os.utime(future,(now.timestamp()-10,now.timestamp()-10))
    result=report_window(as_of=now)
    assert not result['results'] and result['unverified_count']==2


def client_for(actor):
    client=APIClient();client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client


@pytest.mark.django_db
def test_api_cursor_scope_owner_and_archive_filters(superadmin_user, admin_user, reader_user, settings, tmp_path):
    settings.NAS_BACKUP_ROOT=tmp_path; start=timezone.now()-timedelta(days=1)
    for index in range(22):report_file(tmp_path,start+timedelta(seconds=index))
    backup=BackupJob.objects.create(requested_by=superadmin_user,destination_path='unused',checksum='a'*64)
    client=client_for(superadmin_user)
    first=client.get(URL,{'backup_id':str(backup.pk)})
    assert first.status_code==200 and first['Cache-Control']=='private, no-store'
    assert len(first.data['results'])==20 and first.data['next_cursor']
    second=client.get(URL,{'backup_id':str(backup.pk),'cursor':first.data['next_cursor']})
    assert second.status_code==200 and len(second.data['results'])==2
    assert client.get(URL,{'cursor':first.data['next_cursor']}).status_code==400
    assert client.get(URL,{'cursor':'invalid'}).status_code==400
    assert client.get(URL+'?cursor=a&cursor=b').status_code==400
    assert client.get(URL,{'page':2}).status_code==400
    assert client_for(admin_user).get(URL).status_code==403
    assert client_for(reader_user).get(URL).status_code==403
    assert client.get(URL,HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code==403
    with patch('distribution.restore_history_views.report_window',return_value={'source_status':'available','source_identity':'different-directory'}):
        assert client.get(URL,{'backup_id':str(backup.pk),'cursor':first.data['next_cursor']}).status_code==409
