from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_core import create_entity, entity_data, entity_for_legacy
from catalog.services.knowledge_profiles import submit_profile, profile_workspace
from catalog.services.knowledge_public import page_data, publish_page
from .test_manual_knowledge_sources import apply_all

pytestmark = pytest.mark.django_db


def test_same_name_organizations_keep_distinct_typed_identities(admin_user):
    first = create_entity({"kind": "organization", "label": "同名研究会", "profile": {"organization_type": "association", "country": "甲国"}}, admin_user)
    second = create_entity({"kind": "organization", "label": "同名研究会", "profile": {"organization_type": "association", "country": "乙国"}}, admin_user)
    assert first.organization_id != second.organization_id
    assert entity_for_legacy(first.organization).pk == first.pk
    assert entity_data(second)["profile"]["country"] == "乙国"
    with pytest.raises(ValidationError):
        create_entity({"kind": "event", "label": "日期错误", "profile": {"start_year": 2020, "end_year": 1900}}, admin_user)
    with pytest.raises(ValidationError):
        create_entity({"kind": "research_object", "label": "未知字段", "profile": {"unconstrained": {"anything": True}}}, admin_user)
    assert not m.Entity.objects.filter(kind="event").exists()


def test_profile_review_preserves_public_value_until_page_publication(admin_user):
    entity = create_entity({"kind": "research_object", "label": "隔离测试人群", "profile": {"object_kind": "population", "geographic_scope": "原地区"}}, admin_user)
    entity.status = "published"
    entity.save(update_fields=["status"])
    page = m.KnowledgePage.objects.create(entity=entity, slug="profile-review", title=entity.label, status="published")
    key = uuid4()
    base = profile_workspace(entity, admin_user)["profile_hash"]
    draft = submit_profile(entity, {"geographic_scope": "新地区", "temporal_scope": "限定时期"}, admin_user, request_id=key, base_hash=base)
    assert submit_profile(entity, {"geographic_scope": "新地区", "temporal_scope": "限定时期"}, admin_user, request_id=key, base_hash=base).pk == draft.pk
    outcome = apply_all(draft, admin_user)
    assert not outcome["blocked"], outcome
    from catalog.services.intelligence_queries import changeset_data
    assert len(changeset_data(draft, admin_user)["items"]) == 2
    entity.refresh_from_db()
    assert entity_data(entity)["profile"]["geographic_scope"] == "原地区"
    preview = page_data(page, admin_user, draft=True)
    assert preview["identity"]["profile"]["geographic_scope"] == "新地区"
    assert page_data(page, admin_user)["identity"]["profile"]["geographic_scope"] == "原地区"
    publish_page(page.pk, preview["revision_id"], admin_user)
    entity.refresh_from_db()
    assert entity_data(entity)["profile"]["geographic_scope"] == "新地区"
    assert m.EditorialRevision.objects.filter(target_type="research_object_profile", status="published").exists()
    assert publish_page(page.pk, preview["revision_id"], admin_user)["identity"]["profile"]["geographic_scope"] == "新地区"
    assert submit_profile(entity, {"geographic_scope": "新地区", "temporal_scope": "限定时期"}, admin_user, request_id=key, base_hash=base).pk == draft.pk


def test_profile_concurrent_change_blocks_local_group_without_losing_decision(admin_user):
    entity = create_entity({"kind": "research_object", "label": "基准测试对象"}, admin_user)
    draft = submit_profile(entity, {"unit_of_analysis": "组织"}, admin_user, request_id=uuid4(), base_hash=profile_workspace(entity, admin_user)["profile_hash"])
    entity.research_object.unit_of_analysis = "个人"
    entity.research_object.save(update_fields=["unit_of_analysis"])
    result = apply_all(draft, admin_user)
    assert result["blocked"] and not result["saved"]
    assert draft.items.filter(decision="accepted").count() == 2


@pytest.mark.parametrize("kind,profile", [("organization", {"organization_type": "association"}), ("event", {"event_type": "development", "source": "隔离测试出处", "start_year": 1900, "date_precision": "year"})])
def test_new_typed_identity_publishes_only_after_review(admin_user, kind, profile):
    from catalog.services.intelligence_changes import submit_draft
    from catalog.services.knowledge_public import public_entities
    scope = m.KnowledgePage.objects.create(slug=f"scope-{kind}", title="隔离测试范围", scope="测试输入")
    from tests.v304_helpers import activate_catalog_revision
    work = m.Work.objects.create(title="隔离测试资料来源")
    edition = m.Edition.objects.create(work=work, state="published", public_slug=f"profile-{kind}")
    activate_catalog_revision(edition, fulltext_ready=False)
    identity, patch, block = map(str, (uuid4(), uuid4(), uuid4()))
    draft = submit_draft(None, [
        {"id": identity, "kind": "entity", "payload": {"kind": kind, "label": "隔离测试身份", "definition": "隔离测试资料说明", "profile": profile}},
        {"id": patch, "kind": "wiki_patch", "dependencies": [identity], "payload": {"entity_id": {"change_item": identity}, "operation": "add", "block_id": block,
            "block": {"id": block, "type": "analysis", "style": "paragraph", "text": "人工测试说明", "references": [{"type": "work", "id": str(work.pk), "edition_id": str(edition.pk)}]}}},
    ], admin_user, request_id=uuid4(), origin="human", subject_work=work)
    assert not m.Entity.objects.exists()
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    entity = m.Entity.objects.get()
    assert not public_entities().exists()
    page = m.KnowledgePage.objects.get(entity=entity)
    preview = page_data(page, admin_user, draft=True)
    publish_page(page.pk, preview["revision_id"], admin_user)
    assert public_entities().filter(pk=entity.pk).exists()
    page.refresh_from_db()
    assert page_data(page, admin_user)["identity"]["profile"]


def test_backfill_preserves_organization_aliases_and_unconfirmed_identifiers(admin_user):
    row = m.OrganizationAuthority.objects.create(preferred_name="隔离测试学会", aliases=["隔离测试异名"], external_ids={"ror": "fixture-only"})
    identity = entity_for_legacy(row)
    assert identity.aliases.get().review_status == "legacy"
    assert identity.identifiers.get().value == "fixture-only"
    assert entity_data(identity, public=True)["identifiers"] == []
    assert entity_for_legacy(row).pk == identity.pk
