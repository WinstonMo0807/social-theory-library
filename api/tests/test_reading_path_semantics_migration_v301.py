from __future__ import annotations

import pytest
from django.db import transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_0038_backfills_explicit_semantics_only_for_adopted_candidates():
    connection = transaction.get_connection()
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(
            [("catalog", "0035_edition_publication_date_and_research_context")]
        )
        old_apps = executor.loader.project_state(
            [("catalog", "0035_edition_publication_date_and_research_context")]
        ).apps
        ReadingPath = old_apps.get_model("catalog", "ReadingPath")
        ReadingPathCandidate = old_apps.get_model("catalog", "ReadingPathCandidate")
        ReadingPathItem = old_apps.get_model("catalog", "ReadingPathItem")
        Work = old_apps.get_model("catalog", "Work")

        path = ReadingPath.objects.create(
            title="候选采用的阅读路径",
            slug="candidate-adopted-path-v301",
            introduction="理解国家与社会关系",
            audience="初学者",
            status="draft",
        )
        work = Work.objects.create(
            title="国家与社会",
            document_type="book",
            language="zh-CN",
        )
        item = ReadingPathItem.objects.create(
            reading_path=path,
            stage_name="问题起点",
            work=work,
            recommendation_reason="从基本问题进入",
            editorial_note="先了解国家概念",
        )
        ReadingPathCandidate.objects.create(
            title=path.title,
            target_audience=path.audience,
            learning_goal="较早采用但尚未回填的目标",
            stages=[
                {
                    "name": "问题起点",
                    "works": [
                        {
                            "work_id": str(work.id),
                            "reason": "从基本问题进入",
                            "prerequisite": "较早采用的前置要求",
                        }
                    ],
                }
            ],
            status="adopted",
            adopted_reading_path=path,
        )
        ReadingPathCandidate.objects.create(
            title=path.title,
            target_audience=path.audience,
            learning_goal="理解国家与社会关系",
            stages=[
                {
                    "name": "问题起点",
                    "works": [
                        {
                            "work_id": str(work.id),
                            "reason": "从基本问题进入",
                            "prerequisite": "先了解国家概念",
                        }
                    ],
                }
            ],
            status="adopted",
            adopted_reading_path=path,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0038_backfill_reading_path_semantics")])
        new_apps = executor.loader.project_state(
            [("catalog", "0038_backfill_reading_path_semantics")]
        ).apps
        PathAfter = new_apps.get_model("catalog", "ReadingPath")
        ItemAfter = new_apps.get_model("catalog", "ReadingPathItem")
        CanonicalRevisionAfter = new_apps.get_model(
            "catalog", "CanonicalObjectRevision"
        )
        DomainChangeAfter = new_apps.get_model("catalog", "DomainChangeEvent")
        migrated_path = PathAfter.objects.get(pk=path.pk)
        migrated_item = ItemAfter.objects.get(pk=item.pk)

        assert migrated_path.learning_goal == "理解国家与社会关系"
        assert migrated_path.introduction == "理解国家与社会关系"
        assert migrated_item.prerequisite == "先了解国家概念"
        assert migrated_item.editorial_note == "先了解国家概念"
        revision = CanonicalRevisionAfter.objects.get(
            object_type="reading_path",
            object_id=path.pk,
        )
        event = DomainChangeAfter.objects.get(
            idempotency_key=f"migration-v301-reading-path-semantics:{path.pk}"
        )
        assert revision.current_revision == 1
        assert event.canonical_revision == 1
        assert event.change_kind == "update"
        assert event.changed_fields == ["learning_goal", "stage_groups"]
        assert event.processed_at is None
        assert DomainChangeAfter.objects.filter(object_id=path.pk).count() == 1
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
