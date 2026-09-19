"""A30: 0055 changes model choices, not existing storage or older ORM writes."""
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext


@pytest.mark.django_db(transaction=True)
def test_0055_preserves_drafts_and_old_orm_writes_without_table_changes():
    before = [("catalog", "0054_v305_publication_mode_database_default")]
    after = [("catalog", "0055_v306_relation_timeline_editorial")]
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(before)
        old_apps = executor.loader.project_state(before).apps
        OldRevision = old_apps.get_model("catalog", "EditorialRevision")
        existing = OldRevision.objects.create(target_type="work", target_id=uuid4(), revision=1, idempotency_key="v306-old-before", patch={"title": "旧草稿保留"})
        executor = MigrationExecutor(connection)
        with CaptureQueriesContext(connection) as queries:
            executor.migrate(after)
        assert not any("ALTER TABLE" in query["sql"].upper() or "DROP TABLE" in query["sql"].upper() for query in queries)
        NewRevision = executor.loader.project_state(after).apps.get_model("catalog", "EditorialRevision")
        assert NewRevision.objects.get(pk=existing.pk).patch == {"title": "旧草稿保留"}
        new_draft = NewRevision.objects.create(target_type="timeline_event", target_id=uuid4(), revision=1, idempotency_key="v306-new-after", patch={"description": "新版待发布"})
        # Application rollback leaves the current database in place. Older
        # models can read new rows and continue their existing supported writes.
        assert OldRevision.objects.get(pk=new_draft.pk).patch == {"description": "新版待发布"}
        legacy_write = OldRevision.objects.create(target_type="topic", target_id=uuid4(), revision=1, idempotency_key="v306-old-after", patch={"name": "旧应用可写"})
        assert NewRevision.objects.get(pk=legacy_write.pk).patch == {"name": "旧应用可写"}
        existing.change_note = "旧应用继续修改备注"
        existing.save(update_fields=["change_note"])
        assert NewRevision.objects.get(pk=existing.pk).change_note == "旧应用继续修改备注"
        # Reversibility is checked only in this disposable database; production
        # rollback does not reverse migrations or discard new drafts.
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        assert OldRevision.objects.get(pk=new_draft.pk).patch == {"description": "新版待发布"}
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
