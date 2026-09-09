import pytest

from catalog.models import (
    CatalogFieldDecision, Edition, EditorialRevision, KnowledgeNode,
    LegacyKnowledgeMapping, PublicationBundleItem, TheorySchool, Work, WorkKnowledgeRelation, WorkNodeRelation,
)
from catalog.services.field_assistant import FieldAssistantService
from catalog.services.field_assistant.service import FieldAssistantError
from .test_publication_invariants_v305 import published_edition


pytestmark = pytest.mark.django_db


def mapped_theory():
    legacy = TheorySchool.objects.create(name="互动关系理论", slug="legacy-field-theory", editorial_status="published")
    node = KnowledgeNode.objects.create(
        canonical_name_zh=legacy.name, slug="canonical-field-theory",
        node_type="theory_tradition", status="published",
    )
    mapping = LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool", legacy_id=legacy.pk, node=node, migration_status="mapped",
    )
    return legacy, node, mapping


def adopt(edition, theory, actor):
    return FieldAssistantService().adopt(
        edition_id=edition.pk, field_name="theory", source_type="local_theory_school", source_id=theory.pk, actor=actor,
    )


@pytest.mark.parametrize("published", [False, True])
def test_legacy_theory_selection_only_writes_canonical_relation_or_editorial_draft(admin_user, published):
    legacy, node, _mapping = mapped_theory()
    if published:
        edition, public = published_edition("已发布作品的理论字段")
    else:
        work = Work.objects.create(title="草稿理论字段", document_type="book", language="zh-CN")
        edition = Edition.objects.create(work=work)
    saved = adopt(edition, legacy, admin_user)
    assert saved["saved"]
    assert saved["value"] == [{"id": str(node.pk), "name": node.canonical_name_zh}]
    assert not WorkKnowledgeRelation.objects.exists()
    assert not PublicationBundleItem.objects.filter(object_type="theory_school").exists()
    if published:
        draft = EditorialRevision.objects.get(target_type="work", target_id=edition.work_id, status="draft")
        assert draft.patch["knowledge"]["nodes"][0]["id"] == str(node.pk)
        assert draft.patch["knowledge"]["theories"] == []
        assert not WorkNodeRelation.objects.filter(work=edition.work).exists()
        public.refresh_from_db()
        assert public.snapshot == {"work": {"id": str(edition.work_id), "title": "已发布作品的理论字段"}}
    else:
        assert WorkNodeRelation.objects.filter(work=edition.work, node=node, status="published", reviewed_by=admin_user).exists()


@pytest.mark.parametrize("problem", ["missing_mapping", "wrong_type", "unpublished_target", "identity_mismatch"])
def test_unsafe_legacy_mapping_cannot_create_a_new_legacy_relation(admin_user, problem):
    legacy, node, mapping = mapped_theory()
    if problem == "missing_mapping":
        mapping.delete()
    elif problem == "wrong_type":
        KnowledgeNode.objects.filter(pk=node.pk).update(node_type="concept")
    elif problem == "unpublished_target":
        KnowledgeNode.objects.filter(pk=node.pk).update(status="draft")
    else:
        KnowledgeNode.objects.filter(pk=node.pk).update(canonical_name_zh="另一个不同理论")
    work = Work.objects.create(title="必须人工确认映射", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work)
    with pytest.raises(FieldAssistantError):
        adopt(edition, legacy, admin_user)
    assert not WorkKnowledgeRelation.objects.exists()
    assert not WorkNodeRelation.objects.exists()
    assert not CatalogFieldDecision.objects.exists()
    assert not PublicationBundleItem.objects.exists()


def test_existing_reviewed_legacy_relation_is_preserved_without_duplicate_field_identity(admin_user):
    legacy, node, _mapping = mapped_theory()
    work = Work.objects.create(title="保留历史关系", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work)
    historical = WorkKnowledgeRelation.objects.create(
        work=work, kind="theory_school", theory_school=legacy, approved=True, review_status="approved",
        reviewed_by=admin_user, evidence_text="既有人工证据，不能覆盖", source="historical_review",
    )
    before = WorkKnowledgeRelation.objects.filter(pk=historical.pk).values().get()
    saved = adopt(edition, legacy, admin_user)
    assert saved["value"] == [{"id": str(node.pk), "name": node.canonical_name_zh}]
    assert WorkKnowledgeRelation.objects.filter(pk=historical.pk).values().get() == before
    assert WorkKnowledgeRelation.objects.count() == 1


def test_canonical_adoption_rolls_back_if_recording_the_human_decision_fails(admin_user, monkeypatch):
    legacy, _node, _mapping = mapped_theory()
    work = Work.objects.create(title="采用事务边界", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work)

    def fail(*args, **kwargs):
        raise RuntimeError("decision unavailable")

    monkeypatch.setattr("catalog.services.field_assistant.service.record_edition_field_decision", fail)
    with pytest.raises(RuntimeError, match="decision unavailable"):
        adopt(edition, legacy, admin_user)
    assert not WorkNodeRelation.objects.exists()
    assert not WorkKnowledgeRelation.objects.exists()
