import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext

from catalog.models import Edition


def test_publication_mode_has_both_application_and_database_defaults():
    field = Edition._meta.get_field("publication_mode")
    assert field.default == "document"
    assert field.db_default == "document"


@pytest.mark.django_db(transaction=True)
def test_0054_allows_legacy_edition_inserts_and_preserves_existing_modes():
    executor = MigrationExecutor(connection)
    before = [("catalog", "0053_v305_knowledge_image_media")]
    after = [("catalog", "0054_v305_publication_mode_database_default")]
    try:
        executor.migrate(before)
        before_apps = executor.loader.project_state(before).apps
        WorkBefore = before_apps.get_model("catalog", "Work")
        EditionBefore = before_apps.get_model("catalog", "Edition")
        work = WorkBefore.objects.create(title="回退兼容书目", document_type="book")
        document = EditionBefore.objects.create(work_id=work.pk, publication_mode="document")
        bibliographic = EditionBefore.objects.create(work_id=work.pk, publication_mode="bibliographic")
        legacy_apps = executor.loader.project_state(
            [("catalog", "0042_v304_journal_issue_articles")]
        ).apps
        LegacyEdition = legacy_apps.get_model("catalog", "Edition")

        # Reproduce the old model's omitted-column failure before the migration.
        with pytest.raises(IntegrityError), transaction.atomic():
            LegacyEdition.objects.create(work_id=work.pk)

        executor = MigrationExecutor(connection)
        executor.migrate(after)
        with CaptureQueriesContext(connection) as captured:
            legacy = LegacyEdition.objects.create(work_id=work.pk)
        insert = next(query["sql"] for query in captured if query["sql"].lstrip().upper().startswith("INSERT"))
        assert "publication_mode" not in insert
        assert Edition.objects.get(pk=legacy.pk).publication_mode == "document"
        assert Edition.objects.get(pk=document.pk).publication_mode == "document"
        assert Edition.objects.get(pk=bibliographic.pk).publication_mode == "bibliographic"

        legacy_bibliographic = LegacyEdition.objects.get(pk=bibliographic.pk)
        legacy_bibliographic.version_label = "旧版更新其他字段"
        legacy_bibliographic.save(update_fields=["version_label"])
        bibliographic_after = Edition.objects.get(pk=bibliographic.pk)
        assert bibliographic_after.publication_mode == "bibliographic"
        assert bibliographic_after.version_label == "旧版更新其他字段"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
