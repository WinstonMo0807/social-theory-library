from __future__ import annotations

import pytest

from catalog.models import (
    DocumentType,
    Discipline,
    Edition,
    KnowledgeNode,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
    LegacyKnowledgeMapping,
    TheorySchool,
    Subdiscipline,
    Topic,
    Work,
    WorkKnowledgeRelation,
    WorkNodeRelation,
    WorkTopicRelation,
)
from catalog.management.commands.v3_foundation_inventory import (
    _legacy_write_call_sites,
    build_inventory,
)
from catalog.services.canonical_identity import CanonicalIdentityError, mapped_node_for_legacy
from catalog.services.work_editor import save_workflow_section
from catalog.theory_serializers import AdminKnowledgeNodeSerializer
from ingestion.models import MetadataCandidate, UploadBatch, UploadItem
from ingestion.services.taxonomy import suggest_relations


pytestmark = pytest.mark.django_db


def test_workflow_legacy_theory_input_writes_only_canonical_relations(admin_user):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="3.0 规范关系写入",
        language="zh-CN",
    )
    edition = Edition.objects.create(work=work, version_label="测试版")
    theory = TheorySchool.objects.create(
        name="待兼容理论",
        slug="v3-workflow-legacy-theory",
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh=theory.name,
        slug="v3-workflow-canonical-theory",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=theory.id,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    topic = Topic.objects.create(name="规范主题", slug="v3-workflow-topic")

    save_workflow_section(
        edition,
        "knowledge",
        {
            "theories": [
                {
                    "id": theory.id,
                    "role": "foundational",
                    "strength": "high",
                    "is_primary": True,
                }
            ],
            "topics": [{"id": topic.id, "is_primary": True}],
            "nodes": [],
        },
        actor=admin_user,
    )

    relation = WorkNodeRelation.objects.get(work=work, node=node)
    assert relation.role == WorkNodeRelation.Role.FOUNDATIONAL
    assert relation.status == "published"
    assert WorkTopicRelation.objects.filter(work=work, topic=topic).exists()
    assert WorkKnowledgeRelation.objects.filter(work=work).count() == 0


def test_admin_cannot_create_duplicate_topic_identity_as_knowledge_node():
    serializer = AdminKnowledgeNodeSerializer(
        data={
            "node_type": KnowledgeNode.NodeType.TOPIC,
            "canonical_name_zh": "重复主题身份",
            "slug": "duplicate-topic-identity",
            "status": "draft",
        }
    )

    assert serializer.is_valid() is False
    assert "node_type" in serializer.errors


def test_admin_cannot_convert_existing_node_into_duplicate_identity_type():
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="规范概念",
        slug="canonical-concept-before-type-change",
        status="draft",
    )
    serializer = AdminKnowledgeNodeSerializer(
        node,
        data={"node_type": KnowledgeNode.NodeType.SUBDISCIPLINE},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert "node_type" in serializer.errors


def test_node_uses_independent_subdiscipline_and_topic_relations(
    api_client,
    admin_user,
):
    discipline = Discipline.objects.create(
        name="3.0 独立身份学科",
        slug="sociology-independent-relation",
        code="SOC-V3",
        editorial_status="published",
    )
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="3.0 独立身份子学科",
        slug="historical-sociology-independent",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="国家形成",
        slug="state-formation-independent",
        editorial_status="published",
    )
    api_client.force_authenticate(admin_user)

    created = api_client.post(
        "/api/catalog/admin/theory-system/nodes/",
        {
            "node_type": KnowledgeNode.NodeType.THEORY_TRADITION,
            "canonical_name_zh": "国家形成理论",
            "slug": "state-formation-theory-independent",
            "status": "published",
            "subdiscipline_links": [
                {
                    "subdiscipline_id": str(subdiscipline.id),
                    "is_primary": True,
                    "relation_role": "home",
                    "status": "published",
                }
            ],
            "topic_links": [
                {
                    "topic_id": str(topic.id),
                    "relation_label": "核心研究主题",
                    "status": "published",
                }
            ],
        },
        format="json",
    )

    assert created.status_code == 201
    node = KnowledgeNode.objects.get(pk=created.data["id"])
    assert KnowledgeNodeSubdiscipline.objects.filter(
        node=node,
        subdiscipline=subdiscipline,
        status="published",
    ).exists()
    assert KnowledgeNodeTopic.objects.filter(
        node=node,
        topic=topic,
        status="published",
    ).exists()
    public = api_client.get(
        f"/api/catalog/theory-system/nodes/{node.slug}/"
    )
    assert public.status_code == 200
    assert public.data["subdiscipline_links"][0]["subdiscipline"]["id"] == str(
        subdiscipline.id
    )
    assert public.data["topic_links"][0]["topic"]["id"] == str(topic.id)


def test_ingestion_taxonomy_only_writes_safe_normalized_relations(admin_user):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="马克思主义与权力",
        language="zh-CN",
    )
    theory = TheorySchool.objects.create(name="马克思主义", slug="marxism")
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh=theory.name,
        slug="marxism-canonical-v3",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=theory.id,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    topic = Topic.objects.create(name="权力", slug="power", editorial_status="published")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="taxonomy.pdf")

    suggest_relations(work, "马克思主义讨论权力与阶级斗争。", upload_item=item)

    assert WorkNodeRelation.objects.filter(
        work=work,
        node=node,
        status="pending",
        source="keyword_classifier_v3",
    ).exists()
    assert WorkTopicRelation.objects.filter(
        work=work,
        topic=topic,
        review_status="suggested",
        source="keyword_classifier_v3",
    ).exists()
    assert not WorkKnowledgeRelation.objects.filter(work=work).exists()


def test_ingestion_taxonomy_keeps_wrong_type_mapping_as_candidate(admin_user):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="女性主义研究",
        language="zh-CN",
    )
    theory = TheorySchool.objects.create(name="女性主义", slug="feminism")
    wrong_node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh=theory.name,
        slug="feminism-wrong-type",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=theory.id,
        node=wrong_node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="unmapped.pdf")

    suggest_relations(work, "女性主义与父权制分析。", upload_item=item)

    assert not WorkNodeRelation.objects.filter(work=work).exists()
    assert not WorkKnowledgeRelation.objects.filter(work=work).exists()
    candidate = MetadataCandidate.objects.get(
        upload_item=item,
        field_name="knowledge_nodes",
        value="女性主义",
    )
    assert candidate.evidence["reason"] == "missing_or_inactive_reviewed_theory_mapping"
    with pytest.raises(CanonicalIdentityError, match="映射类型错误"):
        mapped_node_for_legacy("TheorySchool", theory.id)


def test_same_type_but_mismatched_mapping_never_becomes_canonical():
    theory = TheorySchool.objects.create(
        name="批判国家理论",
        slug="critical-state-theory-mismatch",
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="政治经济人类学",
        slug="political-economy-anthropology-mismatch",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=theory.id,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="映射安全清单测试",
        language="zh-CN",
    )
    WorkKnowledgeRelation.objects.create(
        work=work,
        kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
        theory_school=theory,
        approved=True,
        review_status="approved",
        source="inventory-safety-test",
    )

    with pytest.raises(CanonicalIdentityError, match="identity_mismatch"):
        mapped_node_for_legacy("TheorySchool", theory.id)
    inventory = build_inventory()
    assert inventory["canonical_identity"]["mapping_safety_findings"] == {
        "identity_mismatch": 1,
    }
    assert inventory["retirement_gate"]["legacy_mapping_targets_safe"] is False


def test_legacy_theory_writers_return_explicit_retirement_error(api_client, admin_user):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="旧写入口测试",
        language="zh-CN",
    )
    theory = TheorySchool.objects.create(name="旧理论", slug="legacy-writer-theory")
    api_client.force_authenticate(admin_user)

    relation_response = api_client.post(
        "/api/catalog/admin/knowledge-relations/work-theories/",
        {
            "work": str(work.id),
            "theory_school": str(theory.id),
            "kind": "theory_school",
        },
        format="json",
    )
    theory_response = api_client.post(
        "/api/catalog/admin/theory-schools/",
        {"name": "不得创建", "slug": "must-not-create"},
        format="json",
    )

    assert relation_response.status_code == 409
    assert relation_response.data["code"] == "legacy_work_theory_write_retired"
    assert theory_response.status_code == 409
    assert theory_response.data["code"] == "legacy_theory_school_write_retired"
    assert not WorkKnowledgeRelation.objects.filter(work=work).exists()
    assert not TheorySchool.objects.filter(slug="must-not-create").exists()


@pytest.mark.parametrize(
    "kind",
    [
        "theory-disciplines",
        "theory-subdisciplines",
        "theory-hierarchy",
        "theory-relations",
        "topic-theories",
    ],
)
def test_all_legacy_theory_relation_writers_are_read_only_compatibility(
    api_client,
    admin_user,
    kind,
):
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        f"/api/catalog/admin/knowledge-relations/{kind}/",
        {},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "legacy_theory_relation_write_retired"
    assert response.data["replacement"].startswith(
        "/api/catalog/admin/theory-system/"
    )


def test_inventory_detects_real_legacy_writer_sites(tmp_path):
    source = tmp_path / "legacy_writer.py"
    source.write_text(
        "from catalog.models import TheorySchool\n"
        "TheorySchool.objects.create(name='unsafe')\n",
        encoding="utf-8",
    )

    assert _legacy_write_call_sites(tmp_path) == [
        {
            "model": "TheorySchool",
            "operation": "create",
            "path": "legacy_writer.py",
            "line": 2,
            "source": "TheorySchool.objects.create(name='unsafe')",
        }
    ]
    assert build_inventory()["canonical_identity"]["legacy_write_call_site_count"] == 0


def test_metadata_review_rejects_free_legacy_theory_and_published_direct_edit(
    api_client,
    admin_user,
):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="元数据复核原值",
        language="zh-CN",
    )
    edition = Edition.objects.create(work=work, version_label="测试版")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="metadata-review.pdf",
        edition=edition,
    )
    api_client.force_authenticate(admin_user)
    payload = {
        "title": "不得写入的新值",
        "document_type": "book",
        "language": "zh-CN",
        "publication_year": 2026,
        "publisher": "测试出版社",
        "authors": [],
        "theory_schools": ["未经身份确认的新理论"],
        "topics": [],
        "retry_publication": False,
    }

    response = api_client.put(
        f"/api/ingestion/items/{item.id}/review/",
        payload,
        format="json",
    )
    assert response.status_code == 400
    work.refresh_from_db()
    assert work.title == "元数据复核原值"
    assert not TheorySchool.objects.filter(name="未经身份确认的新理论").exists()

    edition.state = "published"
    edition.save(update_fields=["state", "updated_at"])
    payload["theory_schools"] = []
    response = api_client.put(
        f"/api/ingestion/items/{item.id}/review/",
        payload,
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "editorial_revision_required"
    work.refresh_from_db()
    assert work.title == "元数据复核原值"
