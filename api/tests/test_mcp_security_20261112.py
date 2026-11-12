"""Adversarial MCP inputs, only against an isolated synthetic database."""
from uuid import uuid4
import pytest

from catalog.models import (Edition, Person, Contribution, ScholarProfile, ScholarRelation, Topic,
    Discipline, TopicDisciplineRelation, WorkTopicRelation, EditorialRevision, Asset, Page, DocumentRevision, EvidenceSpan)
from catalog.editorial_read import current_editorial_version
from catalog.services.workspace_edits import workspace_edit_version
from ingestion.models import FieldLock
from tests.test_local_mcp_curation_20261112 import domain, setup

pytestmark = pytest.mark.django_db


def test_nested_bibliography_cannot_bypass_publisher_lock(admin_user):
    work, edition, op, baseline = setup(admin_user)
    FieldLock.objects.create(edition=edition, field_name="publisher", locked_by=admin_user, locked_value="已核准出版社")
    op.update(expected_version=workspace_edit_version(edition), data={"bibliography": {"edition_id": str(edition.pk), "values": {"publisher": "不应被自动写入的出版社"}}})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert EditorialRevision.objects.count() == baseline


def test_different_edition_hint_cannot_bypass_target_lock(admin_user):
    work, edition, op, baseline = setup(admin_user)
    other = Edition.objects.create(work=work, publication_mode="bibliographic")
    FieldLock.objects.create(edition=edition, field_name="publisher", locked_by=admin_user, locked_value="已核准出版社")
    op.update(target_type="edition", target_id=str(edition.pk), edition_id=str(other.pk),
              expected_version=current_editorial_version("edition", edition.pk), data={"publisher": "错误版本的改写"})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert EditorialRevision.objects.count() == baseline


def test_work_contributor_wrapper_cannot_drop_existing_author(admin_user):
    work, edition, op, baseline = setup(admin_user)
    people = [Person.objects.create(preferred_name=name) for name in ("原有作者", "另一作者")]
    for person in people:
        Contribution.objects.create(edition=edition, person=person, role="author")
    op.update(expected_version=workspace_edit_version(edition), data={"contributors": {"edition_id": str(edition.pk),
        "values": {"contributors": [{"person_id": str(people[1].pk), "role": "author", "order": 0}]}}})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert EditorialRevision.objects.count() == baseline


def test_topic_relation_list_cannot_be_cleared(admin_user):
    work, edition, op, baseline = setup(admin_user)
    topic = Topic.objects.create(name="关联主题", slug="mcp-security-topic")
    WorkTopicRelation.objects.create(work=work, topic=topic)
    discipline = Discipline.objects.create(name="合成学科", slug="mcp-security-discipline")
    TopicDisciplineRelation.objects.create(topic=topic, discipline=discipline)
    op.update(target_type="topic", target_id=str(topic.pk), expected_version=current_editorial_version("topic", topic.pk), data={"discipline_relations": []})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert EditorialRevision.objects.count() == baseline


def test_existing_unrelated_scholar_relation_cannot_be_rebound_into_scope(admin_user):
    work, edition, op, baseline = setup(admin_user)
    people = [Person.objects.create(preferred_name=f"合成人物{i}") for i in range(3)]
    profiles = [ScholarProfile.objects.create(person=p, slug=f"mcp-security-person-{i}") for i, p in enumerate(people)]
    Contribution.objects.create(edition=edition, person=people[0], role="author")
    relation = ScholarRelation.objects.create(source_scholar=profiles[1], target_scholar=profiles[2], relation_type="influence")
    op.update(kind="scholar_relation", target_id=str(relation.pk), expected_version="0", data={
        "source_scholar": str(profiles[0].pk), "target_scholar": str(profiles[2].pk), "relation_type": "influence", "summary": "越界改写"})
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert EditorialRevision.objects.count() == baseline


def evidence_fixture(admin_user, access_status):
    work, edition, op, baseline = setup(admin_user)
    asset = Asset.objects.create(edition=edition, kind="normalized", file="mcp-security.pdf", is_current=True,
        status="ready", validation_status="valid", access_status=access_status, sha256="f" * 64, page_count=1)
    page = Page.objects.create(asset=asset, index=1, text="非公开原文")
    revision = DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256, text_checksum="e" * 64)
    span = EvidenceSpan.objects.create(page=page, document_revision=revision, page_number=1, start_offset=0, end_offset=5,
        original_text="非公开原文", content_hash="d" * 64)
    topic = Topic.objects.create(name="来源主题", slug="mcp-security-source-topic")
    WorkTopicRelation.objects.create(work=work, topic=topic)
    op.update(kind="evidence_curation", target_type="topic", target_id=str(topic.pk), expected_version="0",
              data={"items": [{"source_type": "span", "source_id": str(span.pk), "reason": "不能通过保存回显受限原文"}]})
    return op, span, baseline


@pytest.mark.parametrize("access_status", ["private", "restricted"])
def test_draft_save_cannot_reveal_private_evidence(admin_user, access_status):
    op, span, baseline = evidence_fixture(admin_user, access_status)
    result = domain.save({"operations": [op]}, domain.actor())
    assert not result["ok"], result
    assert "非公开原文" not in str(result)
    assert EditorialRevision.objects.count() == baseline


def test_old_curation_response_does_not_reveal_now_private_source(admin_user):
    op, span, baseline = evidence_fixture(admin_user, "public")
    saved = domain.save({"operations": [op]}, domain.actor())
    assert saved["ok"], saved
    span.page.asset.access_status = "private"
    span.page.asset.save(update_fields=["access_status"])
    safe = domain.redact_sources(saved)
    assert "非公开原文" not in str(safe)
    assert safe["results"][0]["result"]["items"][0]["source"]["available"] is False
