"""Human citation and immutable assertion edits; fixtures are not scholarly evidence."""
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError, PermissionDenied
from catalog import models as m
from catalog.services import intelligence_changes as changes
from catalog.services.knowledge_workspace import submit_page_assertion, source_hash
from catalog.services.knowledge_core import page_content
from catalog.services.intelligence_queries import changeset_data

pytestmark = pytest.mark.django_db


def apply_all(draft, actor):
    keys = list(map(str, draft.items.values_list("pk", flat=True)))
    draft = changes.review(draft.pk, [{"id": key, "decision": "accepted"} for key in keys], actor, expected_version=draft.version)
    result = changes.apply(draft.pk, keys, actor, request_id=uuid4(), expected_version=draft.version)
    return result


def test_human_citation_uses_same_review_without_fabricated_revision(admin_user, reader_user):
    entity = m.Entity.objects.create(kind="concept", label="测试概念")
    page = m.KnowledgePage.objects.create(entity=entity, slug="citation", title="人工出处")
    payload = {"text":"测试命题", "expression":"editorial_judgment", "source_citation":"人工填写的测试出处，定位尚未核实", "evidence":[]}
    key = uuid4()
    with pytest.raises(PermissionDenied):
        submit_page_assertion(page, payload, reader_user, request_id=key)
    draft = submit_page_assertion(page, payload, admin_user, request_id=key)
    assert submit_page_assertion(page, payload, admin_user, request_id=key).pk == draft.pk
    assert not m.Assertion.objects.exists()
    assert not m.DocumentRevision.objects.exists()
    result = apply_all(draft, admin_user)
    assert not result["blocked"], result
    statement = m.Assertion.objects.get()
    assert statement.source_quality == "human_citation" and statement.status == "draft"
    assert statement.sources.get().work_id is None
    assert statement.sources.get().citation == payload["source_citation"]
    assert not statement.evidence.exists()
    assert changeset_data(draft, admin_user)["document_revision_id"] is None
    assert page_content(page)[0][0]["references"][0]["id"] == str(statement.pk)
    for origin in ("external", "intelligence"):
        with pytest.raises(ValidationError):
            changes.submit_draft(None, [], admin_user, request_id=uuid4(), origin=origin, subject_entity=entity)


def test_assertion_revision_is_atomic_and_conflicts_without_overwriting(admin_user):
    entity = m.Entity.objects.create(kind="concept", label="修订测试")
    page = m.KnowledgePage.objects.create(entity=entity, slug="assertion-revision", title="修订")
    payload = {"text":"原人工命题", "expression":"editorial_judgment", "source_citation":"测试出处", "evidence":[]}
    apply_all(submit_page_assertion(page, payload, admin_user, request_id=uuid4()), admin_user)
    old = m.Assertion.objects.get()
    patch = {**payload, "text":"新人工命题", "supersedes_id":str(old.pk), "base_hash":source_hash("assertion", old.pk)}
    pending = submit_page_assertion(page, patch, admin_user, request_id=uuid4())
    m.Assertion.objects.filter(pk=old.pk).update(text="同期另一人工修改")
    outcome = apply_all(pending, admin_user)
    assert outcome["blocked"] and not outcome["saved"]
    assert m.Assertion.objects.count() == 1
    old.refresh_from_db()
    assert old.text == "同期另一人工修改"
    assert pending.items.filter(decision="accepted").count() == 2
    patch["base_hash"] = source_hash("assertion", old.pk)
    current = submit_page_assertion(page, patch, admin_user, request_id=uuid4())
    result = apply_all(current, admin_user)
    assert not result["blocked"], result
    new = m.Assertion.objects.get(supersedes=old)
    assert new.text == "新人工命题" and new.status == "draft"
    old.refresh_from_db()
    assert old.text == "同期另一人工修改"


def test_page_publication_includes_reviewed_new_identity_and_preserves_old_source(admin_user):
    from tests.v304_helpers import activate_catalog_revision
    from catalog.services.knowledge_public import page_data, publish_page, public_entities
    work = m.Work.objects.create(title="实体发布测试作品")
    edition = m.Edition.objects.create(work=work, state="published", public_slug="identity-publish")
    activate_catalog_revision(edition, fulltext_ready=False)
    person_id, concept_id, assertion_id, patch_id, block_id = [str(uuid4()) for _ in range(5)]
    items = [
        {"id":person_id,"kind":"entity","payload":{"kind":"person","label":"独立测试人物","definition":"仅供隔离测试的资料"}},
        {"id":concept_id,"kind":"entity","payload":{"kind":"concept","label":"独立测试概念","definition":"隔离测试定义"}},
        {"id":assertion_id,"kind":"assertion","payload":{"text":"隔离测试关系","predicate":"uses","expression":"editorial_judgment",
            "source_citation":"隔离测试出处", "participants":[{"role":"subject","entity_id":{"change_item":person_id}},
            {"role":"object","entity_id":{"change_item":concept_id}}]}},
        {"id":patch_id,"kind":"wiki_patch","payload":{"work_id":str(work.pk),"operation":"add","block_id":block_id,
            "block":{"id":block_id,"type":"analysis","text":"隔离测试关系","references":[{"type":"assertion","id":{"change_item":assertion_id}}]}}},
    ]
    draft = changes.submit_draft(None,items,admin_user,request_id=uuid4(),origin="human",subject_work=work)
    result = apply_all(draft,admin_user)
    assert not result["blocked"], result
    page = m.KnowledgePage.objects.get(work=work)
    preview = page_data(page, admin_user, draft=True)
    assert {v["label"] for v in preview["publication_scope"]["entities"]} == {"独立测试人物","独立测试概念"}
    assert not public_entities().exists()
    publish_page(page.pk,preview["revision_id"],admin_user)
    assert public_entities().count() == 2
    assert m.ScholarProfile.objects.get().editorial_status == "published"
    assert m.Person.objects.get().authority_status == "verified"
    assert len(page_data(m.KnowledgePage.objects.get(pk=page.pk),admin_user)["assertions"]) == 1
