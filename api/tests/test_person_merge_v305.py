from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from accounts.models import User
from catalog.models import (
    CatalogFieldDecision, Contribution, Edition, EditorialRevision, KnowledgePublicationEvent, Page,
    Person, PersonMergeRecord, PersonNameVariant, ResearchRun, ScholarProfile, TheoryTimelineEvent, Work,
)
from catalog.services.person_merges import merge_people, prepare_person_merge, rollback_person_merge, rollback_preview
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
from catalog.services.knowledge_publication import process_knowledge_event
from catalog.services.field_enrichment.service import FieldEnrichmentService
from ingestion.models import AuditEvent, FieldLock
from .publication_fixtures import acknowledge_catalog_projections, confirm_book_identity
from .v304_helpers import activate_catalog_revision
from .test_field_enrichment import FakeStructuredAdapter, _observation, _request
from .test_resilient_publication_v260 import create_item_with_files


pytestmark = pytest.mark.django_db


@pytest.fixture
def merge_owner(settings):
    owner = User.objects.create_superuser(username="person-merge-owner", email="person-merge-owner@example.test", password="local-test-only")
    settings.LIBRARY_OWNER_EMAIL = owner.email
    return owner


def pair():
    source = Person.objects.create(preferred_name="来源核验人物", authority_status="verified", birth_year=1930)
    target = Person.objects.create(preferred_name="保留核验人物", authority_status="verified", birth_year=1930)
    ensure_query_lexicon_state()
    return source, target


def apply(source, target, owner, *, key="person-merge-test"):
    preview = prepare_person_merge(source, target)
    assert preview["merge_execution_available"], preview["review_issues"]
    return merge_people(source.pk, target.pk, actor=owner, confirmed=True,
                        expected_fingerprint=preview["fingerprint"], idempotency_key=key)


def test_person_merge_moves_references_without_deleting_rows_and_can_reverse(merge_owner):
    source, target = pair()
    source.biography = "来源资料保留在原人物"
    source.save(update_fields=["biography", "updated_at"])
    target.biography = "保留人物资料不覆盖"
    target.save(update_fields=["biography", "updated_at"])
    work = Work.objects.create(title="原作品不改", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work)
    author = Contribution.objects.create(edition=edition, person=source, role="author", approved=True, source="manual-original")
    variant = PersonNameVariant.objects.create(person=source, name="来源旧译名", variant_type="alias", source_kind="editorial", is_verified=True)
    unreviewed = PersonNameVariant.objects.create(person=source, name="未经确认的称呼", variant_type="alias", source_kind="other", is_verified=False)
    profile = ScholarProfile.objects.create(person=source, slug="preserved-scholar-url", short_description="保留档案原文", editorial_status="published")
    timeline = TheoryTimelineEvent.objects.create(scholar=profile, event_type="scholar", title="既有时间线", start_year=1960)
    record = apply(source, target, merge_owner)
    source.refresh_from_db()
    author.refresh_from_db()
    variant.refresh_from_db()
    unreviewed.refresh_from_db()
    profile.refresh_from_db()
    assert source.authority_status == "merged" and source.merged_into_id == target.pk
    target.refresh_from_db()
    assert source.biography == "来源资料保留在原人物"
    assert target.biography == "保留人物资料不覆盖"
    assert author.person_id == target.pk and author.source == "manual-original" and author.approved
    assert variant.person_id == unreviewed.person_id == target.pk
    assert not unreviewed.is_verified
    assert profile.person_id == target.pk and profile.slug == "preserved-scholar-url"
    assert TheoryTimelineEvent.objects.get(pk=timeline.pk).scholar_id == profile.pk
    assert Person.objects.filter(pk=source.pk).exists()
    assert AuditEvent.objects.filter(action="person_merge", object_id=str(record.pk)).exists()
    preview = rollback_preview(record)
    assert preview["can_rollback"], preview
    rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=preview["fingerprint"])
    for row in (source, author, variant, unreviewed, profile, record):
        row.refresh_from_db()
    assert source.authority_status == "verified" and source.merged_into_id is None
    assert author.person_id == variant.person_id == unreviewed.person_id == profile.person_id == source.pk
    assert record.rolled_back_at is not None
    assert profile.short_description == "保留档案原文"


@pytest.mark.parametrize("blocked", ["identity", "profiles", "relation", "unverified", "draft"])
def test_merge_blocks_unresolved_identity_profile_and_reference_conflicts(merge_owner, blocked):
    source, target = pair()
    if blocked == "identity":
        target.birth_year = 1940
        target.save(update_fields=["birth_year", "updated_at"])
    elif blocked == "profiles":
        ScholarProfile.objects.create(person=source, slug="source-duplicate-profile")
        ScholarProfile.objects.create(person=target, slug="target-duplicate-profile")
    elif blocked == "relation":
        work = Work.objects.create(title="重复贡献者", document_type="book")
        edition = Edition.objects.create(work=work)
        Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
        Contribution.objects.create(edition=edition, person=target, role="author", approved=False)
    elif blocked == "unverified":
        source.authority_status = "draft"
        source.save(update_fields=["authority_status", "updated_at"])
    else:
        profile = ScholarProfile.objects.create(person=source, slug="editing-profile")
        EditorialRevision.objects.create(target_type="scholar_profile", target_id=profile.pk, revision=1,
                                        base_revision=0, status="draft", patch={"short_description": "未发布内容"}, idempotency_key="merge-open-draft")
    preview = prepare_person_merge(source, target)
    assert not preview["merge_execution_available"]
    with pytest.raises(ValueError):
        merge_people(source.pk, target.pk, actor=merge_owner, confirmed=True,
                     expected_fingerprint=preview["fingerprint"], idempotency_key=f"blocked-{blocked}")
    assert not PersonMergeRecord.objects.exists()
    source.refresh_from_db()
    assert source.merged_into_id is None


def test_merge_requires_owner_confirmation_and_fresh_fingerprint(merge_owner, reader_user):
    source, target = pair()
    preview = prepare_person_merge(source, target)
    kwargs = {"expected_fingerprint": preview["fingerprint"], "idempotency_key": "preconditions"}
    with pytest.raises(PermissionDenied):
        merge_people(source.pk, target.pk, actor=reader_user, confirmed=True, **kwargs)
    with pytest.raises(ValueError, match="确认"):
        merge_people(source.pk, target.pk, actor=merge_owner, confirmed=False, **kwargs)
    target.biography = "预览后已人工修改"
    target.save(update_fields=["biography", "updated_at"])
    with pytest.raises(ValueError, match="变化"):
        merge_people(source.pk, target.pk, actor=merge_owner, confirmed=True, **kwargs)
    assert not PersonMergeRecord.objects.exists()


def test_merge_publication_failure_rolls_back_entire_transaction(merge_owner):
    source, target = pair()
    work = Work.objects.create(title="事务失败原件保留", document_type="book")
    edition = Edition.objects.create(work=work)
    author = Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
    with patch("catalog.services.person_merges.create_entity_publication_event", side_effect=RuntimeError("controlled publication failure")):
        with pytest.raises(RuntimeError, match="controlled"):
            apply(source, target, merge_owner)
    source.refresh_from_db()
    author.refresh_from_db()
    assert source.authority_status == "verified" and source.merged_into_id is None
    assert author.person_id == source.pk
    assert not PersonMergeRecord.objects.exists()
    assert not AuditEvent.objects.filter(action="person_merge").exists()


def test_merge_is_idempotent_and_record_cannot_be_rewritten(merge_owner):
    source, target = pair()
    record = apply(source, target, merge_owner, key="repeatable-merge")
    repeat = merge_people(source.pk, target.pk, actor=merge_owner, confirmed=True,
                          expected_fingerprint=record.preview_fingerprint, idempotency_key="repeatable-merge")
    assert repeat.pk == record.pk and PersonMergeRecord.objects.count() == 1
    with pytest.raises(ValidationError):
        PersonMergeRecord.objects.filter(pk=record.pk).update(changes=[])
    with pytest.raises(ValidationError):
        record.delete()


def test_rollback_rejects_later_human_changes(merge_owner):
    source, target = pair()
    record = apply(source, target, merge_owner)
    before = rollback_preview(record)
    target.biography = "合并后的人工内容"
    target.save(update_fields=["biography", "updated_at"])
    record = PersonMergeRecord.objects.select_related("source_person", "target_person").get(pk=record.pk)
    assert not rollback_preview(record)["can_rollback"]
    with pytest.raises(ValueError, match="不能"):
        rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=before["fingerprint"])
    target.refresh_from_db()
    assert target.biography == "合并后的人工内容"


@pytest.mark.parametrize("acknowledged", [False, True])
def test_published_work_keeps_serving_snapshot_and_manual_review_during_merge_and_rollback(merge_owner, acknowledged):
    source, target = pair()
    work = Work.objects.create(title="正式书目保持可用", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work, state="published", publication_mode="bibliographic", public_slug="person-merge-published-work")
    author = Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
    confirm_book_identity(edition, merge_owner)
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="authors")
    reviewer = decision.confirmed_by_id
    lock = FieldLock.objects.create(edition=edition, field_name="authors", locked_by=merge_owner,
                                   locked_value=[str(source.pk)], reason="原人工确认")
    active = activate_catalog_revision(edition, fulltext_ready=False)
    record = apply(source, target, merge_owner)
    original_event = KnowledgePublicationEvent.objects.get(pk__in=record.event_ids, catalog_revision__edition=edition)
    edition.refresh_from_db()
    decision.refresh_from_db()
    lock.refresh_from_db()
    assert edition.active_catalog_revision_id == active.pk
    assert decision.value == lock.locked_value == [str(target.pk)]
    assert decision.status == "confirmed" and decision.confirmed_by_id == reviewer
    assert lock.reason == "原人工确认"
    assert active.snapshot["contributions"][0]["person_id"] == str(source.pk)
    if acknowledged:
        acknowledge_catalog_projections(edition)
    record = PersonMergeRecord.objects.select_related("source_person", "target_person").get(pk=record.pk)
    preview = rollback_preview(record)
    assert preview["can_rollback"], preview
    rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=preview["fingerprint"])
    author.refresh_from_db()
    decision.refresh_from_db()
    lock.refresh_from_db()
    assert author.person_id == source.pk
    assert decision.value == lock.locked_value == [str(source.pk)]
    assert KnowledgePublicationEvent.objects.filter(payload__isnull=False, catalog_revision__edition=edition).count() == 2
    restored = acknowledge_catalog_projections(edition)
    assert edition.active_catalog_revision.snapshot["contributions"][0]["person_id"] == str(source.pk)
    process_knowledge_event(original_event.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == restored.catalog_revision_id


def test_rollback_failure_keeps_applied_merge_and_all_references(merge_owner):
    source, target = pair()
    profile = ScholarProfile.objects.create(person=source, slug="rollback-failure-profile")
    record = apply(source, target, merge_owner)
    preview = rollback_preview(record)
    with patch("catalog.services.person_merges.create_entity_publication_event", side_effect=RuntimeError("controlled rollback failure")):
        with pytest.raises(RuntimeError, match="controlled"):
            rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=preview["fingerprint"])
    source.refresh_from_db()
    profile.refresh_from_db()
    record.refresh_from_db()
    assert source.authority_status == "merged" and source.merged_into_id == target.pk
    assert profile.person_id == target.pk and record.rolled_back_at is None
    assert not AuditEvent.objects.filter(action="person_merge_rollback").exists()


def test_rollback_rejects_new_relationships_and_keeps_them(merge_owner):
    source, target = pair()
    record = apply(source, target, merge_owner)
    work = Work.objects.create(title="合并后新关系", document_type="book")
    edition = Edition.objects.create(work=work)
    author = Contribution.objects.create(edition=edition, person=target, role="author", approved=True)
    preview = rollback_preview(record)
    assert not preview["can_rollback"]
    with pytest.raises(ValueError):
        rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=record.rollback_fingerprint)
    assert Contribution.objects.filter(pk=author.pk, person=target, approved=True).exists()


def test_rollback_preserves_later_nested_json_timestamp_values(merge_owner):
    source, target = pair()
    work = Work.objects.create(title="人工JSON日期保护", document_type="book")
    edition = Edition.objects.create(work=work)
    Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
    lock = FieldLock.objects.create(
        edition=edition, field_name="authors", locked_by=merge_owner,
        locked_value={"people": [str(source.pk)], "updated_at": "人工记录一"},
    )
    record = apply(source, target, merge_owner)
    lock.refresh_from_db()
    lock.locked_value = {"people": [str(target.pk)], "updated_at": "合并后的人工记录"}
    lock.save(update_fields=["locked_value", "updated_at"])
    preview = rollback_preview(record)
    assert not preview["can_rollback"]
    with pytest.raises(ValueError):
        rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=record.rollback_fingerprint)
    lock.refresh_from_db()
    assert lock.locked_value["updated_at"] == "合并后的人工记录"


def test_queued_research_prevents_identity_merge(merge_owner):
    source, target = pair()
    work = Work.objects.create(title="正在排队的研究", document_type="book")
    edition = Edition.objects.create(work=work)
    Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
    research = ResearchRun.objects.create(
        work=work, edition=edition, requested_by=merge_owner, status=ResearchRun.Status.QUEUED,
        idempotency_key="person-merge-queued-research", context_fingerprint="f" * 64,
        context_snapshot={"person_id": str(source.pk)}, active_step="contributors",
        context_version="test", contract_version="test", planner_version="test",
    )
    preview = prepare_person_merge(source, target)
    assert not preview["merge_execution_available"]
    assert preview["context_impact"]["pending"]["research_runs"] == 1
    research.refresh_from_db()
    assert research.status == ResearchRun.Status.QUEUED


def test_bulk_upsert_cannot_rewrite_merge_history(merge_owner):
    source, target = pair()
    record = apply(source, target, merge_owner)
    original = dict(record.source_snapshot)
    record.source_snapshot = {"overwritten": True}
    with pytest.raises(ValidationError):
        PersonMergeRecord.objects.bulk_create(
            [record], update_conflicts=True, update_fields=["source_snapshot"], unique_fields=["id"],
        )
    record.refresh_from_db()
    assert record.source_snapshot == original


def test_pending_generic_candidate_prevents_merge_without_rewriting_candidate(merge_owner):
    source, target = pair()
    adapter = FakeStructuredAdapter([_observation(
        field_name="name_variant", value={"name": "待审核别名", "language": "zh", "variant_type": "alias"},
        identity_claims={"name": source.preferred_name, "birth_year": source.birth_year},
    )])
    result = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("person", source.pk, ["name_variant"]), actor=merge_owner,
    )
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    original_value = dict(candidate.proposed_value)
    preview = prepare_person_merge(source, target)
    assert not preview["merge_execution_available"]
    assert preview["context_impact"]["pending"]["catalog.EnrichmentCandidate"] == 1
    with pytest.raises(ValueError):
        merge_people(source.pk, target.pk, actor=merge_owner, confirmed=True,
                     expected_fingerprint=preview["fingerprint"], idempotency_key="pending-candidate")
    candidate.refresh_from_db()
    assert candidate.target_id == source.pk and candidate.proposed_value == original_value


def test_person_merge_http_requires_owner_and_allows_confirmed_merge_and_rollback(api_client, reader_user, merge_owner):
    source, target = pair()
    endpoint = f"/api/catalog/admin/people/{source.pk}/merge/"
    preview_endpoint = f"/api/catalog/admin/people/{source.pk}/merge-preview/"
    api_client.force_authenticate(reader_user)
    assert api_client.post(endpoint, {}, format="json").status_code == 403
    administrator = User.objects.create_user(username="non-owner-merger", email="non-owner-merger@example.test", password="local-test-only", role="admin", is_staff=True)
    api_client.force_authenticate(administrator)
    assert api_client.post(endpoint, {}, format="json").status_code == 403
    api_client.force_authenticate(merge_owner)
    preview = api_client.get(preview_endpoint, {"target_person": str(target.pk)})
    assert preview.status_code == 200 and preview.data["merge_execution_available"] is True
    assert preview.data["execution_guidance"]
    payload = {"target_person": str(target.pk), "fingerprint": preview.data["fingerprint"], "idempotency_key": "http-confirmed-merge", "confirmed": False}
    assert api_client.post(endpoint, payload, format="json").status_code == 409
    payload["confirmed"] = True
    applied = api_client.post(endpoint, payload, format="json")
    assert applied.status_code == 200, applied.data
    assert applied.data["status"] == "applied"
    assert applied["Cache-Control"] == "private, no-store"
    assert api_client.post(endpoint, payload, format="json").data["id"] == applied.data["id"]
    detail_endpoint = f"/api/catalog/admin/people/merge-records/{applied.data['id']}/"
    detail = api_client.get(detail_endpoint)
    assert detail.status_code == 200 and detail.data["rollback"]["can_rollback"] is True
    restored = api_client.post(f"{detail_endpoint}rollback/", {"fingerprint": detail.data["rollback"]["fingerprint"], "confirmed": True}, format="json")
    assert restored.status_code == 200, restored.data
    assert restored.data["status"] == "rolled_back" and restored.data["rollback_event_ids"]
    source.refresh_from_db()
    assert source.authority_status == "verified"
    repeated = api_client.post(f"{detail_endpoint}rollback/", {"fingerprint": detail.data["rollback"]["fingerprint"], "confirmed": True}, format="json")
    assert repeated.status_code == 200 and repeated.data["status"] == "rolled_back"
    assert AuditEvent.objects.filter(action="person_merge_rollback", object_id=applied.data["id"]).count() == 1
    api_client.force_authenticate(reader_user)
    assert api_client.get(detail_endpoint).status_code == 403


def test_document_backed_merge_and_rollback_leave_files_and_later_reader_notes_unchanged(
    merge_owner, reader_user, settings, tmp_path,
):
    from reading.models import Annotation
    from reading.services import encrypt_private_text

    source, target = pair()
    _work, edition, original, normalized = create_item_with_files(settings, tmp_path, title="人物合并文件与笔记保护")
    Contribution.objects.create(edition=edition, person=source, role="author", approved=True)
    page = Page.objects.create(asset=normalized, index=1, text="正式文档原文", normalized_text="正式文档原文", text_source="embedded")
    edition.state = "published"
    edition.save(update_fields=["state", "updated_at"])
    confirm_book_identity(edition, merge_owner)
    active = activate_catalog_revision(edition, reader_asset=normalized)
    with original.file.open("rb") as handle:
        original_bytes = handle.read()
    with normalized.file.open("rb") as handle:
        reader_bytes = handle.read()
    record = apply(source, target, merge_owner)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == active.pk
    acknowledge_catalog_projections(edition)
    assert edition.active_catalog_revision.reader_asset_id == normalized.pk
    note = Annotation.objects.create(
        user=reader_user, asset=normalized, page=page, kind="note", selector={"page_index": 1},
        quote="正式文档原文", body_ciphertext=encrypt_private_text("合并后新增的私人笔记"), asset_sha256=normalized.sha256,
    )
    ciphertext = note.body_ciphertext
    record = PersonMergeRecord.objects.select_related("source_person", "target_person").get(pk=record.pk)
    preview = rollback_preview(record)
    assert preview["can_rollback"], preview
    rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=preview["fingerprint"])
    acknowledge_catalog_projections(edition)
    assert edition.active_catalog_revision.reader_asset_id == normalized.pk
    assert edition.active_catalog_revision.snapshot["contributions"][0]["person_id"] == str(source.pk)
    note.refresh_from_db()
    assert note.asset_id == normalized.pk and note.page_id == page.pk
    assert note.body_ciphertext == ciphertext and note.quote == "正式文档原文"
    with original.file.open("rb") as handle:
        assert handle.read() == original_bytes
    with normalized.file.open("rb") as handle:
        assert handle.read() == reader_bytes
