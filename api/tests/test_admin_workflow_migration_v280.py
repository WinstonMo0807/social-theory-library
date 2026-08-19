from __future__ import annotations

import pytest
from django.db import transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_0031_preserves_legacy_reading_path_items_as_independent_stages():
    connection = transaction.get_connection()
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("catalog", "0030_knowledgenodealias_is_verified_and_more")])
        old_apps = executor.loader.project_state(
            [("catalog", "0030_knowledgenodealias_is_verified_and_more")]
        ).apps
        ReadingPath = old_apps.get_model("catalog", "ReadingPath")
        ReadingPathItem = old_apps.get_model("catalog", "ReadingPathItem")
        Work = old_apps.get_model("catalog", "Work")

        path = ReadingPath.objects.create(
            title="迁移前阅读路径",
            slug="workflow-v280-migration-path",
            status="draft",
        )
        work = Work.objects.create(
            title="迁移前作品",
            document_type="journal_article",
            language="zh-CN",
        )
        item = ReadingPathItem.objects.create(
            reading_path=path,
            stage_name="争论背景",
            stage_description="先理解问题来源。",
            work=work,
            reading_order=7,
            recommendation_reason="迁移必须保留",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0031_admin_workflow_v280")])
        new_apps = executor.loader.project_state(
            [("catalog", "0031_admin_workflow_v280")]
        ).apps
        ItemAfter = new_apps.get_model("catalog", "ReadingPathItem")
        StageAfter = new_apps.get_model("catalog", "ReadingPathStage")
        migrated = ItemAfter.objects.get(pk=item.pk)
        stage = StageAfter.objects.get(pk=migrated.stage_id)

        assert stage.reading_path_id == path.id
        assert stage.name == "争论背景"
        assert stage.description == "先理解问题来源。"
        assert stage.position == 7
        assert migrated.position == 7
        assert migrated.stage_name == "争论背景"
        assert migrated.recommendation_reason == "迁移必须保留"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
