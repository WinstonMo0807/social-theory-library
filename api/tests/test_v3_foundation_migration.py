from __future__ import annotations

import pytest
from django.db import transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_0033_backfills_only_confirmed_canonical_relation_targets():
    connection = transaction.get_connection()
    old_target = [("catalog", "0032_healthcheckrun_healthincident_recoveryaction_and_more")]
    new_target = [("catalog", "0033_v3_knowledge_data_foundation")]
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        Work = old_apps.get_model("catalog", "Work")
        Edition = old_apps.get_model("catalog", "Edition")
        Asset = old_apps.get_model("catalog", "Asset")
        TheorySchool = old_apps.get_model("catalog", "TheorySchool")
        Topic = old_apps.get_model("catalog", "Topic")
        KnowledgeNode = old_apps.get_model("catalog", "KnowledgeNode")
        LegacyKnowledgeMapping = old_apps.get_model("catalog", "LegacyKnowledgeMapping")
        WorkKnowledgeRelation = old_apps.get_model("catalog", "WorkKnowledgeRelation")

        work = Work.objects.create(
            document_type="book",
            title="3.0 关系迁移作品",
            language="zh-CN",
        )
        edition = Edition.objects.create(work=work, version_label="迁移测试版")
        asset = Asset.objects.create(
            edition=edition,
            kind="normalized",
            file="public/migration-test.pdf",
            sha256="a" * 64,
            byte_size=128,
            status="ready",
        )
        theory = TheorySchool.objects.create(
            name="3.0 关系迁移理论",
            slug="v3-relation-migration-theory",
        )
        topic = Topic.objects.create(
            name="3.0 关系迁移主题",
            slug="v3-relation-migration-topic",
        )
        node = KnowledgeNode.objects.create(
            node_type="theory_tradition",
            canonical_name_zh=theory.name,
            slug="v3-relation-migration-node",
            status="published",
        )
        LegacyKnowledgeMapping.objects.create(
            legacy_model="TheorySchool",
            legacy_id=theory.id,
            node=node,
            migration_status="mapped",
        )
        WorkKnowledgeRelation.objects.create(
            work=work,
            kind="theory_school",
            theory_school=theory,
            role="foundational",
            strength="high",
            approved=True,
            is_primary=True,
            review_status="approved",
            source="migration-test",
            confidence=1,
            evidence_asset=asset,
            evidence_page=7,
            evidence_printed_label="5",
            evidence_text="这段原文支持规范理论关系。",
        )
        WorkKnowledgeRelation.objects.create(
            work=work,
            kind="topic",
            topic=topic,
            strength="medium",
            approved=True,
            is_primary=True,
            review_status="approved",
            source="migration-test",
            confidence=1,
        )
        wrong_theory = TheorySchool.objects.create(
            name="错误类型映射理论",
            slug="v3-wrong-type-migration-theory",
        )
        wrong_node = KnowledgeNode.objects.create(
            node_type="concept",
            canonical_name_zh=wrong_theory.name,
            slug="v3-wrong-type-migration-node",
            status="published",
        )
        LegacyKnowledgeMapping.objects.create(
            legacy_model="TheorySchool",
            legacy_id=wrong_theory.id,
            node=wrong_node,
            migration_status="mapped",
        )
        WorkKnowledgeRelation.objects.create(
            work=work,
            kind="theory_school",
            theory_school=wrong_theory,
            approved=True,
            review_status="approved",
            source="migration-test-invalid-mapping",
        )
        mismatched_theory = TheorySchool.objects.create(
            name="名称不一致的旧理论",
            slug="v3-mismatched-migration-theory",
        )
        mismatched_node = KnowledgeNode.objects.create(
            node_type="theory_tradition",
            canonical_name_zh="完全不同的规范理论",
            slug="v3-mismatched-migration-node",
            status="published",
        )
        LegacyKnowledgeMapping.objects.create(
            legacy_model="TheorySchool",
            legacy_id=mismatched_theory.id,
            node=mismatched_node,
            migration_status="mapped",
        )
        WorkKnowledgeRelation.objects.create(
            work=work,
            kind="theory_school",
            theory_school=mismatched_theory,
            approved=True,
            review_status="approved",
            source="migration-test-identity-mismatch",
        )
        unreviewed_theory = TheorySchool.objects.create(
            name="未审核迁移理论",
            slug="v3-unreviewed-migration-theory",
        )
        unreviewed_node = KnowledgeNode.objects.create(
            node_type="theory_tradition",
            canonical_name_zh=unreviewed_theory.name,
            slug="v3-unreviewed-migration-node",
            status="draft",
        )
        LegacyKnowledgeMapping.objects.create(
            legacy_model="TheorySchool",
            legacy_id=unreviewed_theory.id,
            node=unreviewed_node,
            migration_status="mapped",
        )
        WorkKnowledgeRelation.objects.create(
            work=work,
            kind="theory_school",
            theory_school=unreviewed_theory,
            approved=False,
            review_status="suggested",
            source="migration-test-unreviewed",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        WorkNodeRelation = new_apps.get_model("catalog", "WorkNodeRelation")
        WorkTopicRelation = new_apps.get_model("catalog", "WorkTopicRelation")
        EvidenceSnippet = new_apps.get_model("catalog", "EvidenceSnippet")
        NewWorkKnowledgeRelation = new_apps.get_model("catalog", "WorkKnowledgeRelation")

        node_relation = WorkNodeRelation.objects.get(work_id=work.id, node_id=node.id)
        assert node_relation.role == "foundational_work"
        assert node_relation.status == "published"
        assert node_relation.is_primary is True
        evidence = EvidenceSnippet.objects.get(work_node_relation_id=node_relation.id)
        assert evidence.file_id == asset.id
        assert evidence.page_number == 7
        assert evidence.printed_page_label == "5"
        assert evidence.quote == "这段原文支持规范理论关系。"
        assert evidence.review_status == "approved"
        topic_relation = WorkTopicRelation.objects.get(work_id=work.id, topic_id=topic.id)
        assert topic_relation.review_status == "approved"
        assert topic_relation.is_primary is True
        assert not WorkNodeRelation.objects.filter(node_id=wrong_node.id).exists()
        assert not WorkNodeRelation.objects.filter(node_id=mismatched_node.id).exists()
        assert not WorkNodeRelation.objects.filter(node_id=unreviewed_node.id).exists()
        assert NewWorkKnowledgeRelation.objects.filter(work_id=work.id).count() == 5
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
