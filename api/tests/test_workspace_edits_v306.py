from uuid import uuid4

import pytest

from catalog.models import CatalogFieldDecision, CatalogFieldDecisionLog, EditorialRevision
from catalog.services.cataloging_sessions import open_cataloging_session
from ingestion.models import AuditEvent, FieldLock, MetadataCandidate
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("published", [False, True])
def test_identity_prefills_save_together_preserving_roles_and_source(api_client, admin_user, published):
    from catalog.models import Contribution, Person, PublisherAuthority
    original_edition, snapshot = published_edition("公开身份填写") if published else (None, None)
    edition, base, payload = setup_workspace(api_client, admin_user, original_edition)
    people = [Person.objects.create(preferred_name=name, authority_status="verified") for name in ("原有作者", "新增作者甲", "新增作者乙")]
    Contribution.objects.create(edition=edition, person=people[0], role="author", approved=True)
    publisher = PublisherAuthority.objects.create(canonical_name="身份填写出版社", editorial_status="published")
    payload["edit_version"] = api_client.get(f"{base}?edition={edition.pk}").data["editing"]["edit_version"]
    rows = [{"person_id": str(person.pk), "role": "author", "order": index} for index, person in enumerate(people)]
    rows.append({"person_id": str(people[1].pk), "role": "translator", "order": 3})
    payload["sections"] = {"contributors": {"contributors": rows}, "bibliography": {"publisher": publisher.canonical_name, "publisher_authority_id": str(publisher.pk)}}
    payload["suggestions"] = [
        {"field_name": role, "source_type": "local_person", "source_id": str(person.pk), "selected_entity_id": str(person.pk), "selected_value": person.preferred_name}
        for role, person in (("author", people[1]), ("author", people[2]), ("translator", people[1]))
    ] + [{"field_name": "publisher", "source_type": "local_publisher", "source_id": str(publisher.pk), "selected_entity_id": str(publisher.pk), "selected_value": publisher.canonical_name}]
    response = api_client.post(base + "edits/", payload, format="json")
    assert response.status_code == 200, response.data
    result = response.data["data"]
    assert [(row["person_id"], row["role"]) for row in result["contributors"]["items"]] == [(row["person_id"], row["role"]) for row in rows]
    assert str(result["bibliography"]["publisher_authority_id"]) == str(publisher.pk)
    receipt = AuditEvent.objects.get(action="workspace.edits.saved", object_id=edition.pk)
    assert len(receipt.after["assistance"]) == 4
    assert receipt.after["assistance"][0]["field"] == "authors"
    assert receipt.after["assistance"][0]["selected_entity_id"] == str(people[1].pk)
    assert all(item["outcome"] == "used_unchanged" for item in receipt.after["assistance"])
    assert all(item["outcome_scope"] == "selected_identity" for item in receipt.after["assistance"] if item["field"] in {"authors", "translators"})
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="authors")
    assert decision.value == [str(person.pk) for person in people]
    assert decision.status == "needs_review"
    count = CatalogFieldDecisionLog.objects.count()
    retry = api_client.post(base + "edits/", payload, format="json")
    assert retry.status_code == 200 and retry.data["save_result"]["replayed"] is True
    assert CatalogFieldDecisionLog.objects.count() == count
    if published:
        edition.refresh_from_db()
        assert edition.publisher_authority_id is None
        assert list(edition.contributions.values_list("person_id", flat=True)) == [people[0].pk]
        snapshot.refresh_from_db()
        assert snapshot.snapshot["work"]["title"] == "公开身份填写"


def test_removed_identity_prefill_is_not_recorded_as_adopted(api_client, admin_user):
    from catalog.models import Person
    edition, base, payload = setup_workspace(api_client, admin_user)
    person = Person.objects.create(preferred_name="已移除的作者", authority_status="verified")
    payload["sections"] = {"contributors": {"contributors": []}}
    payload["suggestions"] = [{"field_name": "author", "source_type": "local_person", "source_id": str(person.pk), "selected_entity_id": str(person.pk)}]
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 200, result.data
    assert AuditEvent.objects.get(action="workspace.edits.saved").after["assistance"] == []
    assert not edition.contributions.exists()


@pytest.mark.parametrize("field", ["author", "translator", "publisher"])
def test_matched_identity_prefill_keeps_original_metadata_source(api_client, admin_user, field):
    from catalog.models import Person, PublisherAuthority
    edition, base, payload = setup_workspace(api_client, admin_user)
    label = "来源可追溯的馆内对象"
    entity = (PublisherAuthority.objects.create(canonical_name=label, editorial_status="published") if field == "publisher"
              else Person.objects.create(preferred_name=label, authority_status="verified"))
    candidate = MetadataCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(), field_name=field, value=label, source="isolated_pdf_fixture")
    lookup = api_client.post("/api/catalog/admin/field-assistant/lookup/", {"object_type": "edition", "object_id": str(edition.pk), "field_name": field}, format="json")
    assert lookup.status_code == 200, lookup.data
    suggestion = lookup.data["results"][0]
    assert suggestion["entity"]["id"] == str(entity.pk)
    assert suggestion["action"]["source_type"] == "metadata"
    payload["suggestions"] = [{"field_name": field, **suggestion["action"], "selected_entity_id": str(entity.pk)}]
    payload["sections"] = ({"bibliography": {"publisher": label, "publisher_authority_id": str(entity.pk)}} if field == "publisher"
                           else {"contributors": {"contributors": [{"person_id": str(entity.pk), "role": field}]}})
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 200, result.data
    candidate.refresh_from_db()
    assert candidate.lifecycle == "accepted"
    canonical = {"author": "authors", "translator": "translators", "publisher": "publisher"}[field]
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name=canonical)
    assert decision.candidate_id == candidate.pk
    assert decision.provenance["outcome"] == "used_unchanged"


def test_publisher_prefill_edited_as_text_drops_authority_but_preserves_original_suggestion(api_client, admin_user):
    from catalog.models import PublisherAuthority
    edition, base, payload = setup_workspace(api_client, admin_user)
    publisher = PublisherAuthority.objects.create(canonical_name="原建议出版社", editorial_status="published")
    payload["suggestions"] = [{"field_name": "publisher", "source_type": "local_publisher", "source_id": str(publisher.pk), "selected_entity_id": str(publisher.pk)}]
    payload["sections"] = {"bibliography": {"publisher": "人工核对的版本署名", "publisher_authority_id": None}}
    response = api_client.post(base + "edits/", payload, format="json")
    assert response.status_code == 200, response.data
    edition.refresh_from_db()
    assert edition.publisher_authority_id is None
    assert edition.publisher == "人工核对的版本署名"
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="publisher")
    assert decision.provenance["suggested_value"] == "原建议出版社"
    assert decision.provenance["outcome"] == "used_after_edit"


@pytest.mark.parametrize("invalid", ["wrong_person", "wrong_role", "locked", "unavailable"])
def test_identity_prefill_cannot_bypass_identity_role_or_lock(api_client, admin_user, invalid):
    from catalog.models import Person
    from ingestion.models import EntityResolutionCandidate
    edition, base, payload = setup_workspace(api_client, admin_user)
    person = Person.objects.create(preferred_name="同名人物", authority_status="verified")
    other = Person.objects.create(preferred_name="同名人物", authority_status="verified")
    candidate = EntityResolutionCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(), target_type="person", source_name=person.preferred_name,
        candidate_entity_type="person", candidate_entity_id=str(person.pk), label=person.preferred_name,
        supporting_properties={"contribution_role": "translator" if invalid == "wrong_role" else "author"})
    if invalid == "locked":
        FieldLock.objects.create(edition=edition, field_name="authors", locked_by=admin_user, locked_value=[], reason="已核对版权页")
    if invalid == "unavailable":
        person.authority_status = "merged"
        person.merged_into = other
        person.save()
    chosen = other if invalid == "wrong_person" else person
    payload["edit_version"] = api_client.get(f"{base}?edition={edition.pk}").data["editing"]["edit_version"]
    payload["sections"]["contributors"] = {"contributors": [{"person_id": str(chosen.pk), "role": "author"}]}
    payload["suggestions"] = [{"field_name": "author", "source_type": "entity_resolution", "source_id": str(candidate.pk), "selected_entity_id": str(chosen.pk), "selected_value": person.preferred_name}]
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 400, result.data
    edition.refresh_from_db()
    candidate.refresh_from_db()
    assert edition.work.title == "完整保存测试"
    assert candidate.status == "proposed"
    assert not edition.contributions.exists()


def setup_workspace(client, actor, edition=None):
    client.force_authenticate(actor)
    if edition is None:
        session, _ = open_cataloging_session(actor=actor, source_type="manual", title="完整保存测试", document_type="report")
        edition = session.edition
    base = f"/api/catalog/admin/library/works/{edition.work_id}/"
    response = client.get(f"{base}?edition={edition.pk}")
    assert response.status_code == 200, response.data
    payload = {"edition_id": str(edition.pk), "request_id": str(uuid4()),
               "edit_version": response.data["editing"]["edit_version"],
               "sections": {"work": {"title": "整份新题名"}, "bibliography": {"publication_year": 2020}}}
    return edition, base, payload


def test_A13_whole_save_and_timeout_retry_are_one_audit_receipt(api_client, admin_user):
    edition, base, payload = setup_workspace(api_client, admin_user)
    first = api_client.post(base + "edits/", payload, format="json")
    assert first.status_code == 200, first.data
    assert first.data["data"]["work"]["title"] == "整份新题名"
    assert first.data["data"]["bibliography"]["publication_year"] == 2020
    logs = CatalogFieldDecisionLog.objects.count()
    retry = api_client.post(base + "edits/", payload, format="json")
    assert retry.status_code == 200, retry.data
    assert retry.data["save_result"]["replayed"] is True
    assert CatalogFieldDecisionLog.objects.count() == logs
    assert AuditEvent.objects.filter(action="workspace.edits.saved", object_id=edition.pk).count() == 1
    payload["sections"]["work"]["title"] = "不能重用编号"
    assert api_client.post(base + "edits/", payload, format="json").status_code == 409


def test_A14_second_section_failure_rolls_back_the_first(api_client, admin_user):
    edition, base, payload = setup_workspace(api_client, admin_user)
    payload["sections"]["contributors"] = {"contributors": [{"person_id": str(uuid4()), "role": "author", "order": 0}]}
    response = api_client.post(base + "edits/", payload, format="json")
    assert response.status_code == 400, response.data
    edition.refresh_from_db()
    assert edition.work.title == "完整保存测试"
    assert edition.publication_year is None
    assert not AuditEvent.objects.filter(action="workspace.edits.saved").exists()


def test_A14_published_draft_change_invalidates_old_window_without_public_leak(api_client, admin_user):
    edition, original = published_edition("读者仍见旧题名")
    edition, base, payload = setup_workspace(api_client, admin_user, edition)
    first = api_client.post(base + "edits/", payload, format="json")
    assert first.status_code == 200, first.data
    edition.refresh_from_db()
    original.refresh_from_db()
    assert edition.work.title == "读者仍见旧题名"
    assert original.snapshot["work"]["title"] == "读者仍见旧题名"
    assert first.data["data"]["work"]["title"] == "整份新题名"
    assert EditorialRevision.objects.filter(target_id=edition.work_id, status="draft").count() == 1
    payload["request_id"] = str(uuid4())
    payload["sections"]["work"]["title"] = "旧窗口覆盖"
    assert api_client.post(base + "edits/", payload, format="json").status_code == 409


def test_A15_A24_edited_prefill_retains_candidate_and_final_value_without_training_permission(api_client, admin_user):
    edition, base, payload = setup_workspace(api_client, admin_user)
    candidate = MetadataCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(), field_name="abstract", value="建议简介", source="isolated_prefill_test")
    payload["sections"]["work"]["abstract"] = "管理员修正后的简介"
    payload["suggestions"] = [{"field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk), "selected_value": "建议简介"}]
    response = api_client.post(base + "edits/", payload, format="json")
    assert response.status_code == 200, response.data
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="abstract")
    assert decision.value == "管理员修正后的简介"
    assert decision.candidate_id == candidate.pk
    assert decision.provenance["suggested_value"] == "建议简介"
    assert decision.provenance["outcome"] == "used_after_edit"
    assert decision.status == "needs_review"
    receipt = AuditEvent.objects.get(action="workspace.edits.saved", object_id=edition.pk)
    assert receipt.after["training_eligibility"] == "not_reviewed"
    assert receipt.after["correctness"] == "not_evaluated"
    assert receipt.after["assistance"][0]["final_value"] == decision.value
    assert receipt.after["assistance"][0]["candidate_id"] == str(candidate.pk)
    count = CatalogFieldDecisionLog.objects.count()
    assert api_client.post(base + "edits/", payload, format="json").status_code == 200
    assert CatalogFieldDecisionLog.objects.count() == count


@pytest.mark.parametrize("bad_source", ["locked", "other_edition", "rejected"])
def test_A15_invalid_prefill_does_not_save_any_section(api_client, admin_user, bad_source):
    edition, base, payload = setup_workspace(api_client, admin_user)
    session = edition.cataloging_sessions.first()
    if bad_source == "other_edition":
        session, _ = open_cataloging_session(actor=admin_user, source_type="manual", title="另一本书")
    candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name="abstract", value="无效建议", source="isolated_prefill_test", lifecycle="rejected" if bad_source == "rejected" else "proposed")
    if bad_source == "locked":
        FieldLock.objects.create(edition=edition, field_name="abstract", locked_by=admin_user, locked_value="人工保留值")
        payload["edit_version"] = api_client.get(f"{base}?edition={edition.pk}").data["editing"]["edit_version"]
    payload["sections"]["work"]["abstract"] = "无效建议"
    payload["suggestions"] = [{"field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk), "selected_value": "无效建议"}]
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 400, result.data
    edition.refresh_from_db()
    assert edition.work.title == "完整保存测试"
    assert not AuditEvent.objects.filter(action="workspace.edits.saved").exists()


def test_A26_exact_edition_and_backend_permission_are_required(api_client, admin_user, reader_user):
    edition, base, payload = setup_workspace(api_client, admin_user)
    payload["edition_id"] = str(uuid4())
    assert api_client.post(base + "edits/", payload, format="json").status_code == 400
    api_client.force_authenticate(reader_user)
    payload["edition_id"] = str(edition.pk)
    assert api_client.post(base + "edits/", payload, format="json").status_code == 403


def test_A07_edited_prefill_points_to_latest_draft_not_superseded_one(api_client, admin_user):
    edition, _ = published_edition("公开旧书目")
    session, _ = open_cataloging_session(actor=admin_user, source_type="existing", edition_id=edition.pk)
    edition, base, payload = setup_workspace(api_client, admin_user, edition)
    candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name="abstract", value="初始建议", source="isolated_test")
    payload["sections"]["work"]["abstract"] = "人工改写的建议"
    payload["suggestions"] = [{"field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk), "selected_value": "初始建议"}]
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 200, result.data
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="abstract")
    latest = EditorialRevision.objects.get(pk=decision.provenance["editorial_revision_id"])
    assert latest.status == "draft"
    assert latest.patch["abstract"] == decision.value == "人工改写的建议"
    edition.refresh_from_db()
    assert edition.work.abstract == ""


def test_A16_unsaved_context_never_silently_saves_or_schedules_old_context(api_client, admin_user, monkeypatch):
    from catalog.services.field_assistant.refresh import ResearchOrchestrator
    def unexpected(*args, **kwargs):
        pytest.fail("Unconfirmed form context must not dispatch research")
    monkeypatch.setattr(ResearchOrchestrator, "prepare", unexpected)
    edition, base, _ = setup_workspace(api_client, admin_user)
    response = api_client.post("/api/catalog/admin/field-assistant/lookup/", {
        "object_type": "edition", "object_id": str(edition.pk), "field_name": "abstract", "refresh": True,
        "confirmed_context": {"title": "尚未保存的新题名"},
    }, format="json")
    assert response.status_code == 200, response.data
    assert response.data["refresh"]["state"] == "not_enabled"
    assert api_client.get(f"{base}?edition={edition.pk}").data["data"]["work"]["title"] == "完整保存测试"


def test_clearing_prefill_does_not_count_as_acceptance(api_client, admin_user):
    edition, base, payload = setup_workspace(api_client, admin_user)
    candidate = MetadataCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(), field_name="abstract", value="放弃的填入值", source="isolated_test")
    payload["sections"]["work"]["abstract"] = ""
    payload["suggestions"] = [{"field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk), "selected_value": "放弃的填入值"}]
    result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 200, result.data
    candidate.refresh_from_db()
    assert candidate.lifecycle == "proposed"
    assert AuditEvent.objects.get(action="workspace.edits.saved").after["assistance"] == []


@pytest.mark.parametrize("other_edition", [False, True])
def test_A15_legacy_adoption_also_preserves_work_level_manual_lock(api_client, admin_user, other_edition):
    from catalog.models import Edition
    edition, _base, _payload = setup_workspace(api_client, admin_user)
    lock_edition = Edition.objects.create(work=edition.work) if other_edition else edition
    FieldLock.objects.create(edition=lock_edition, field_name="abstract", locked_by=admin_user, locked_value="人工锁定")
    candidate = MetadataCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(), field_name="abstract", value="不能覆盖人工锁", source="isolated_test")
    response = api_client.post("/api/catalog/admin/field-assistant/adopt/", {
        "edition_id": str(edition.pk), "field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk),
    }, format="json")
    assert response.status_code == 400, response.data
    candidate.refresh_from_db()
    edition.refresh_from_db()
    assert candidate.lifecycle == "proposed"
    assert edition.work.abstract == ""


@pytest.mark.parametrize("path", ["whole", "work_only", "legacy_section", "legacy_work_only", "assistant"])
def test_A03_another_edition_cannot_replace_the_existing_unpublished_draft(api_client, admin_user, path):
    from catalog.models import Edition
    edition, _ = published_edition("多版本作品")
    edition, base, first_payload = setup_workspace(api_client, admin_user, edition)
    assert api_client.post(base + "edits/", first_payload, format="json").status_code == 200
    pending = EditorialRevision.objects.get(target_id=edition.work_id, status="draft")
    original_patch = dict(pending.patch)
    other = Edition.objects.create(work=edition.work, version_label="另一出版版本")
    _other, _base, payload = setup_workspace(api_client, admin_user, other)
    step = "work" if path.endswith("work_only") else "bibliography"
    payload["sections"] = {"work": {"title": "不能串入另一个版本"}} if step == "work" else {"bibliography": {"publication_year": 2019}}
    if path == "assistant":
        session, _ = open_cataloging_session(actor=admin_user, source_type="existing", edition_id=other.pk)
        candidate = MetadataCandidate.objects.create(cataloging_session=session, field_name="abstract", value="另一版本建议", source="isolated_test")
        result = api_client.post("/api/catalog/admin/field-assistant/adopt/", {"edition_id": str(other.pk), "field_name": "abstract", "source_type": "metadata", "source_id": str(candidate.pk)}, format="json")
        candidate.refresh_from_db()
        assert candidate.lifecycle == "proposed"
    elif path.startswith("legacy"):
        result = api_client.patch(f"{base}sections/{step}/?edition={other.pk}", {"data": payload["sections"][step], "confirm_section": False}, format="json")
    else:
        result = api_client.post(base + "edits/", payload, format="json")
    assert result.status_code == 409, result.data
    pending.refresh_from_db()
    assert pending.status == "draft"
    assert pending.patch == original_patch
    assert EditorialRevision.objects.filter(target_id=edition.work_id, status="draft").count() == 1
