"""Capture the original database, catalog inventory and migration heads together."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import UUID

from django.db import connection, transaction
from catalog.models import Asset
from .database_backup import DatabaseBackupError, create_database_dump, applied_migration_heads

MAX_ASSETS = 99998  # Verifier's 100000-file ceiling also includes DB and manifest.


def inventory_query():
    # Backups include historical/recycled rows, even if a public manager hides them.
    return Asset._base_manager.order_by('pk').values_list('id', 'edition_id', 'edition__work__title', 'kind', 'file', 'sha256', 'byte_size')[:MAX_ASSETS + 1]


def inventory_records(rows):
    result = []
    for row in rows:
        if len(result) >= MAX_ASSETS:
            raise DatabaseBackupError('馆藏清单超出单次备份校验范围，未生成部分清单备份。')
        result.append({'id': str(UUID(str(row[0]))), 'edition_id': str(UUID(str(row[1]))), 'title': row[2],
                       'kind': row[3], 'relative_path': row[4], 'sha256': row[5], 'byte_size': row[6]})
    return result


def capture_backup_snapshot(destination: Path):
    if connection.vendor == 'postgresql':
        if connection.in_atomic_block:
            raise DatabaseBackupError('备份快照必须在独立任务的事务边界开始。')
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                cursor.execute('SELECT pg_export_snapshot()')
                snapshot = cursor.fetchone()[0]
            database = create_database_dump(destination, snapshot=snapshot)
            assets = inventory_records(inventory_query().iterator(chunk_size=200))
            heads = applied_migration_heads()
        # End the read-only transaction before copying files or updating task state.
        database.metadata['catalog_inventory_snapshot'] = True
        return database, heads, assets
    if connection.vendor == 'sqlite':
        database = create_database_dump(destination)
        archive_database = destination / database.filename
        sql, parameters = inventory_query().query.get_compiler(connection=connection).as_sql()
        with closing(sqlite3.connect(archive_database.resolve().as_uri()+'?mode=ro', uri=True)) as snapshot:
            assets = inventory_records(snapshot.execute(sql, parameters))
            applied = snapshot.execute('SELECT app, name FROM django_migrations').fetchall()
        heads = applied_migration_heads(applied_migrations=applied)
        database.metadata['catalog_inventory_snapshot'] = True
        return database, heads, assets
    raise DatabaseBackupError('当前数据库不支持一致的数据库与馆藏清单备份。')
