"""Synthetic knowledge actions and publication cases for final acceptance; not run during implementation."""
from uuid import uuid4
import pytest
from django.http import Http404
from rest_framework.exceptions import NotFound, ValidationError
from catalog.models import Asset, KnowledgeNode, Person, ScholarProfile
from catalog.services import content_placements
from reading import knowledge_saves, privacy, research
from reading.knowledge_models import KnowledgeSaveReceipt, SavedKnowledgeNode
from tests.test_parallel_sources_20261020 import publish, span_for
from tests.test_privacy_atlas_20261018 import operation, command as privacy_command, run

pytestmark = pytest.mark.django_db


def node():
    return KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="合成概念条目",
        slug=f"synthetic-{uuid4()}", status="published")


def save(user, target, saved=True, **kwargs):
    data = {"saved": saved, "request_id": str(uuid4()),
        "expected_version": knowledge_saves.output(user, target.pk)["version"], **kwargs}
    return knowledge_saves.command(user, target.pk, data), data


def test_saved_node_owner_headers_and_staff_no_private_access(api_client, reader_user, admin_user):
    target = node()
    result, _ = save(reader_user, target)
    api_client.force_authenticate(admin_user)
    path = f"/api/reading/saved-knowledge/{target.pk}/"
    assert api_client.get(path).status_code == 403
    assert api_client.get(path, HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    other = api_client.get(path, HTTP_X_READER_OWNER=str(admin_user.pk))
    assert other.status_code == 200 and other.data["saved"] is False
    assert other["Cache-Control"] == "private, no-store"
    assert knowledge_saves.output(reader_user, target.pk)["record_id"] == result["record_id"]


def test_fixed_receipt_replay_after_unsave_cannot_resurrect(reader_user):
    target = node()
    first, data = save(reader_user, target)
    save(reader_user, target, False)
    replay = knowledge_saves.command(reader_user, target.pk, data)
    assert replay["saved"] is False and replay["receipt"]["applied_saved"] is True
    assert not SavedKnowledgeNode.objects.filter(user=reader_user).exists()
    with pytest.raises(research.ResearchConflict):
        knowledge_saves.command(reader_user, target.pk, {**data, "saved": False})
    with pytest.raises(research.ResearchConflict):
        knowledge_saves.command(reader_user, node().pk, data)
    assert first["node"]["title"] == target.canonical_name_zh


def test_cas_conflict_and_retention_off_keeps_existing_cancelable(reader_user):
    target = node()
    first, _ = save(reader_user, target)
    with pytest.raises(research.ResearchConflict):
        save(reader_user, target, False, expected_version="0")
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"saved_knowledge": False}})
    with pytest.raises(ValidationError):
        save(reader_user, node())
    result, _ = save(reader_user, target, False, expected_version=first["version"])
    assert result["saved"] is False


def test_withdrawn_node_hides_title_but_owner_can_cancel(reader_user):
    target = node()
    save(reader_user, target)
    KnowledgeNode.objects.filter(pk=target.pk).update(status="archived")
    state = knowledge_saves.output(reader_user, target.pk)
    assert state["saved"] is True and state["node"] is None
    record = SavedKnowledgeNode.objects.get(user=reader_user)
    assert target.canonical_name_zh not in str(privacy.export_item(reader_user, "saved_knowledge", record))
    assert privacy.describe_item(reader_user, "saved_knowledge", record)["title"] == "当前不可用的知识条目"
    assert save(reader_user, target, False)[0]["saved"] is False
    with pytest.raises(Http404):
        save(reader_user, target)


def test_privacy_export_delete_and_receipt_prevent_old_save_revival(reader_user, admin_user):
    target = node()
    _, data = save(reader_user, target)
    other, _ = save(admin_user, target)
    own = SavedKnowledgeNode.objects.get(user=reader_user)
    exported = operation(reader_user, categories=["saved_knowledge"])
    assert run(exported)["completed"] == 1
    records = privacy.download_operation(reader_user, exported.id)["records"]
    assert len(records) == 1 and records[0]["record"]["owner_id"] == str(reader_user.pk)
    with pytest.raises(NotFound):
        operation(reader_user, "erase", targets=[{"category": "saved_knowledge",
            "id": other["record_id"], "revision": own.updated_at.isoformat()}])
    erased = operation(reader_user, "erase", targets=[privacy.target_of(own, "saved_knowledge")])
    privacy_command(reader_user, erased, "confirm")
    assert run(erased)["completed"] == 1
    assert knowledge_saves.command(reader_user, target.pk, data)["saved"] is False
    assert KnowledgeSaveReceipt.objects.filter(user=reader_user).count() == 1
    assert KnowledgeNode.objects.filter(pk=target.pk).exists()


def test_entry_citation_does_not_fabricate_book_authorship(api_client, settings):
    settings.PUBLIC_WEB_URL = "https://example.invalid"
    target = node()
    path = f"/api/catalog/theory-system/nodes/{target.slug}/citation/"
    result = api_client.get(path)
    assert result.status_code == 200 and result.data["published_at"] is None
    assert result.data["url"] == f"https://example.invalid/theories/nodes/{target.slug}"
    assert "[网页条目]" in result.data["text"] and "佚名" not in result.data["text"]
    KnowledgeNode.objects.filter(pk=target.pk).update(status="draft")
    assert api_client.get(path).status_code == 404


def published_usage(admin_user):
    target = node()
    _, edition, asset, page = publish(text="Synthetic source about a synthetic concept.")
    span = span_for(edition, page)
    person = Person.objects.create(preferred_name="合成来源作者", authority_status="verified",
        original_name="Synthetic source author", birth_year=1901, portrait="synthetic/private-portrait.png")
    profile = ScholarProfile.objects.create(person=person, slug=f"synthetic-person-{uuid4()}", editorial_status="draft")
    data = {"action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": [
        {"id": str(uuid4()), "target": {"type": "span", "id": str(span.pk)}, "concept_usage": {
            "term": "synthetic", "language": "en", "usage_type": "definition", "review_status": "confirmed",
            "interpretation": "合成的编辑解释", "source_person_id": str(person.pk), "attribution_note": "合成原文明确署名",
            "title": "合成用法标题", "explanatory_object": "合成的解释对象", "period": "测试时期", "context": "测试语境"}}]}
    saved = content_placements.command("node", target.pk, data, admin_user)
    content_placements.command("node", target.pk, {"action": "publish", "request_id": str(uuid4()),
        "expected_revision": saved["expected_revision"]}, admin_user)
    return target, asset, profile


def test_usage_projection_preserves_attribution_without_draft_profile_leak(admin_user):
    target, _, profile = published_usage(admin_user)
    result = content_placements.read("node", target.pk, public=True)["public_detail"]
    usage = result["usages"][0]
    assert usage["explanatory_object"] == "合成的解释对象" and usage["source"]["document_revision_id"]
    assert usage["author"]["name"] == profile.person.preferred_name
    assert usage["author"]["portrait_url"] == usage["author"]["scholar_slug"] == ""
    assert usage["author"]["birth_year"] is None
    assert result["unavailable_usage_count"] == 0
    ScholarProfile.objects.filter(pk=profile.pk).update(editorial_status="published")
    visible = content_placements.read("node", target.pk, public=True)["public_detail"]["usages"][0]
    assert visible["author"]["birth_year"] == 1901 and visible["author"]["scholar_slug"] == profile.slug


@pytest.mark.parametrize("field,value", [("access_status", "restricted"), ("validation_status", "invalid"), ("status", "failed")])
def test_withdrawn_usage_exposes_only_unavailable_count(admin_user, field, value):
    target, asset, _ = published_usage(admin_user)
    Asset.objects.filter(pk=asset.pk).update(**{field: value})
    result = content_placements.read("node", target.pk, public=True)["public_detail"]
    assert result["usages"] == [] and result["unavailable_usage_count"] == 1
    assert "Synthetic source" not in str(result) and "合成的编辑解释" not in str(result)


def test_concept_optional_comparison_fields_do_not_relax_confirmation(admin_user):
    reference = {"type": "span", "id": str(uuid4())}
    with pytest.raises(ValidationError):
        content_placements._concept_usage({"term": "synthetic", "review_status": "confirmed",
            "title": "有标题但没有作者或归属依据"}, reference, "node")
    with pytest.raises(ValidationError):
        content_placements._concept_usage({"term": "synthetic", "unreviewed_author": "invalid"}, reference, "node")
