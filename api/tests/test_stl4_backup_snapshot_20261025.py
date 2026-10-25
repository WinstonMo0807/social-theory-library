"""Deferred snapshot/WAL acceptance; never invokes a real PostgreSQL dump."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import sqlite3
import subprocess

import pytest

from distribution.backup_snapshot import capture_backup_snapshot, inventory_records
from distribution.database_backup import create_database_dump, DatabaseDumpResult, DatabaseBackupError


def test_sqlite_backup_captures_committed_wal_pages_without_mutating_source(tmp_path):
    source=tmp_path/'live.sqlite3'; destination=tmp_path/'backup'; destination.mkdir()
    writer=sqlite3.connect(source)
    try:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('CREATE TABLE sample (value TEXT)')
        writer.execute('INSERT INTO sample VALUES (?)',('committed WAL content',)); writer.commit()
        connection=SimpleNamespace(settings_dict={'ENGINE':'django.db.backends.sqlite3','NAME':str(source)})
        result=create_database_dump(destination,connection)
        copy=sqlite3.connect(destination/result.filename)
        try: assert copy.execute('SELECT value FROM sample').fetchone()==('committed WAL content',)
        finally: copy.close()
        assert writer.execute('SELECT count(*) FROM sample').fetchone()[0]==1
        assert result.metadata['snapshot_scope']=='sqlite-online-backup'
        assert 'catalog_inventory_snapshot' not in result.metadata
    finally: writer.close()


def test_postgres_dump_receives_exported_snapshot_as_a_separate_argument(tmp_path):
    fake=SimpleNamespace(settings_dict={'ENGINE':'django.db.backends.postgresql','NAME':'fixture','HOST':'localhost','PORT':5432,'USER':'fixture','PASSWORD':''})
    def complete(command, **kwargs):
        assert command[command.index('--snapshot')+1]=='00000003-0000001B-1'
        assert kwargs.get('shell') is not True
        Path(command[command.index('--file')+1]).write_bytes(b'fixture dump')
        return subprocess.CompletedProcess(command,0,'','')
    with patch('distribution.database_backup.inspect_postgres_backup_runtime',return_value={}),patch('distribution.database_backup.subprocess.run',side_effect=complete):
        result=create_database_dump(tmp_path,fake,snapshot='00000003-0000001B-1')
    assert result.metadata['snapshot_scope']=='shared-exported-snapshot'
    with pytest.raises(DatabaseBackupError):create_database_dump(tmp_path,fake,snapshot='invalid snapshot;')


def test_catalog_and_migrations_are_read_before_snapshot_transaction_closes(tmp_path):
    active=[]; calls=[]
    @contextmanager
    def atomic():
        active.append(True)
        try: yield
        finally: active.pop(); calls.append('closed')
    cursor=Mock();cursor.fetchone.return_value=('00000003-0000001B-1',)
    context=Mock(); context.__enter__=Mock(return_value=cursor);context.__exit__=Mock(return_value=False)
    connection=SimpleNamespace(vendor='postgresql',in_atomic_block=False,cursor=lambda:context)
    data=DatabaseDumpResult('database.dump',1,'a'*64,{})
    row=(uuid4(),uuid4(),'historical original','original','original.pdf','b'*64,10)
    def dump(*args,**kwargs):
        assert active and kwargs['snapshot']=='00000003-0000001B-1'; calls.append('dump'); return data
    def inventory():
        assert active; calls.append('inventory'); return Mock(iterator=lambda **kwargs:iter([row]))
    def heads():
        assert active; calls.append('migrations'); return ['catalog.0088']
    with patch('distribution.backup_snapshot.connection',connection),patch('distribution.backup_snapshot.transaction.atomic',atomic), \
         patch('distribution.backup_snapshot.create_database_dump',side_effect=dump),patch('distribution.backup_snapshot.inventory_query',side_effect=inventory), \
         patch('distribution.backup_snapshot.applied_migration_heads',side_effect=heads):
        result, migrations, records=capture_backup_snapshot(tmp_path)
    assert calls==['dump','inventory','migrations','closed']
    assert result.metadata['catalog_inventory_snapshot'] is True and records[0]['id']==str(row[0])
    assert migrations==['catalog.0088']
    assert cursor.execute.call_args_list[0].args[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'


def test_inventory_limit_fails_instead_of_silently_truncating():
    row=(uuid4(),uuid4(),'original','original','original.pdf','a'*64,10)
    with patch('distribution.backup_snapshot.MAX_ASSETS',1),pytest.raises(DatabaseBackupError):
        inventory_records([row,row])
