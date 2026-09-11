import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from catalog.models import (
    Contribution, Edition, EditorialRevision, Person, PersonNameVariant,
    QueryLexiconEntry, QueryLexiconGeneration, QueryLexiconState,
    ScholarProfile, TheoryTimelineEvent, Work,
)
from catalog.services import person_resolution
from catalog.services.person_resolution import duplicate_people, person_merge_preview
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def person(name="皮埃尔·布迪厄", **values):
    return Person.objects.create(preferred_name=name, authority_status="verified", **values)


def holding(author, title="合并预览文献"):
    work = Work.objects.create(title=title, document_type="book", language="zh-CN")
    edition = Edition.objects.create(
        work=work, state="published", publication_mode="bibliographic", public_slug=f"person-preview-{work.pk}",
    )
    relation = Contribution.objects.create(edition=edition, person=author, role="author", approved=True)
    return work, edition, relation


def test_duplicate_people_use_names_and_identifiers_without_merging():
    source = person(external_ids={"viaf": "12345"}, birth_year=1930)
    same_name = person(birth_year=1930)
    same_identifier = person("Different authority label", external_ids={"viaf": "12345"}, birth_year=1940)
    raw_alias = person("Unreviewed label", aliases=[source.preferred_name])
    result = duplicate_people(source)
    assert {row["person"]["id"] for row in result["results"]} == {str(same_name.pk), str(same_identifier.pk)}
    identifier_row = next(row for row in result["results"] if row["person"]["id"] == str(same_identifier.pk))
    assert {row["field"] for row in identifier_row["identity_conflicts"]} == {"birth_year"}
    assert any(row["kind"] == "external_identifier" for row in identifier_row["matches"])
    assert result["automatic_merge"] is False
    assert not Person.objects.filter(merged_into__isnull=False).exists()
    raw_alias.refresh_from_db()
    assert source.preferred_name in raw_alias.aliases


def test_verified_name_variant_can_find_a_different_canonical_name():
    source = person("Pierre Bourdieu")
    target = person()
    PersonNameVariant.objects.create(
        person=target, name="Pierre Bourdieu", language="en", variant_type="alias",
        source_kind="editorial", is_verified=True,
    )
    assert duplicate_people(source)["results"][0]["person"]["id"] == str(target.pk)
    PersonNameVariant.objects.filter(person=target).update(is_verified=False)
    assert duplicate_people(source)["results"] == []


@pytest.mark.parametrize("source_id,target_id", [(12345, "12345"), ("12345", 12345)])
def test_duplicate_lookup_accepts_legacy_integer_authority_ids(source_id, target_id):
    source = person("来源标识符人物", external_ids={"viaf": source_id})
    target = person("另一名称人物", external_ids={"viaf": target_id})
    assert duplicate_people(source)["results"][0]["person"]["id"] == str(target.pk)


def test_duplicate_lookup_does_not_strip_significant_identifier_zeros():
    source = person("来源编号人物", external_ids={"authority": "000123"})
    person("另一编号人物", external_ids={"authority": 123})
    assert duplicate_people(source)["results"] == []


@pytest.mark.parametrize("scheme", ["isnull", "contains", "exact", "in"])
def test_identifier_keys_are_json_keys_not_lookup_operators(scheme):
    source = person("标识符来源", external_ids={scheme: "same-id"})
    target = person("标识符目标", external_ids={scheme: "same-id"})
    person("相似但不同的编号", external_ids={scheme: "different-id"})
    assert {row["person"]["id"] for row in duplicate_people(source)["results"]} == {str(target.pk)}


def test_duplicate_candidates_are_bounded_and_closed_authorities_are_excluded():
    source = person("重名候选")
    candidates = [person("重名候选") for _ in range(3)]
    archived = person("重名候选")
    archived.authority_status = "archived"
    archived.save(update_fields=["authority_status", "updated_at"])
    result = duplicate_people(source, limit=2)
    assert len(result["results"]) == 2 and result["has_more"] is True
    assert {row["person"]["id"] for row in result["results"]}.issubset({str(row.pk) for row in candidates})


def test_preview_is_read_only_and_covers_direct_profile_and_publication_references():
    source = person("来源人物", birth_year=1930, portrait="public/people/source.jpg")
    target = person("保留人物", birth_year=1940)
    source_profile = ScholarProfile.objects.create(person=source, slug="source-person-profile")
    ScholarProfile.objects.create(person=target, slug="target-person-profile")
    work, edition, relation = holding(source)
    Contribution.objects.create(edition=edition, person=target, role="author", approved=False, order=2)
    publication = activate_catalog_revision(edition, fulltext_ready=False)
    TheoryTimelineEvent.objects.create(
        scholar=source_profile, event_type="scholar", title="来源学者时间线", start_year=1960,
    )
    ensure_query_lexicon_state()
    with CaptureQueriesContext(connection) as captured:
        preview = person_merge_preview(source, target)
    assert all(not row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")) for row in captured)
    assert preview["coverage"]["person_fk_types"] == 11
    assert preview["coverage"]["preserved_audit_fk_types"] == 2
    assert preview["coverage"]["profile_fk_types"] == 5
    assert len(preview["references"]) == 14
    contributions = next(row for row in preview["references"] if row["model"] == "catalog.Contribution")
    assert contributions["source_count"] == contributions["target_count"] == 1
    assert contributions["collisions"][0]["source_id"] == str(relation.pk)
    assert "approved" in contributions["collisions"][0]["different_fields"]
    assert preview["affected_works"][0]["id"] == str(work.pk)
    assert preview["publication_revisions"][0]["id"] == str(publication.pk)
    assert "snapshot" not in preview["publication_revisions"][0]
    assert "two_scholar_profiles" in {row["code"] for row in preview["review_issues"]}
    assert preview["identity_conflicts"][0]["field"] == "birth_year"
    assert preview["source"]["portrait"] == "public/people/source.jpg"
    assert preview["complete_reference_listing"] is True
    assert preview["merge_execution_available"] is False
    assert person_merge_preview(source, target)["fingerprint"] == preview["fingerprint"]
    relation.refresh_from_db()
    source.refresh_from_db()
    assert relation.person_id == source.pk and relation.approved
    assert source.merged_into_id is None


def lexicon_entry(generation, person, term):
    return QueryLexiconEntry.objects.create(
        generation=generation, entity_type="person", entity_id=person.pk,
        term=term, normalized_term=term, language="zh-CN", term_type="alias",
        source_kind="person_name_variant", trust_level="verified", source_ref="test:person-preview",
        source_fingerprint="a" * 64, admin_resolvable=True, public_active=True,
    )


def test_preview_uses_only_active_lexicon_generation_and_never_writes():
    source, target = person("来源词条"), person("保留词条")
    state = ensure_query_lexicon_state()
    source_entry = lexicon_entry(state.active_generation, source, "活动来源别名")
    target_entry = lexicon_entry(state.active_generation, target, "活动保留别名")
    retired = QueryLexiconGeneration.objects.create(
        status="retired", normalization_version=state.normalization_version,
        source_registry_version=state.source_registry_version,
    )
    historical_entry = lexicon_entry(retired, source, "退役词典中的旧别名")
    with CaptureQueriesContext(connection) as captured:
        preview = person_merge_preview(source, target)
    assert all(not row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for row in captured)
    lexicon = preview["lexicon_entries"]
    assert lexicon["available"] is True and lexicon["scope"] == "active_generation"
    assert lexicon["generation_id"] == str(state.active_generation_id)
    assert lexicon["source"] == lexicon["target"] == 1
    assert [row["id"] for row in lexicon["source_rows"]] == [str(source_entry.pk)]
    assert [row["id"] for row in lexicon["target_rows"]] == [str(target_entry.pk)]
    assert lexicon["source_rows"][0]["public_active"] is True
    assert "退役词典中的旧别名" not in str(lexicon)
    assert QueryLexiconEntry.objects.filter(pk=historical_entry.pk).exists()
    source_entry.public_active = False
    source_entry.save(update_fields=["public_active"])
    assert person_merge_preview(source, target)["fingerprint"] != preview["fingerprint"]


def test_preview_does_not_initialize_missing_lexicon():
    source = person("空词典预览")
    QueryLexiconState.objects.all().delete()
    generations_before = QueryLexiconGeneration.objects.count()
    with CaptureQueriesContext(connection) as captured:
        preview = person_merge_preview(source)
    assert all(not row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for row in captured)
    assert preview["lexicon_entries"]["available"] is False
    assert preview["lexicon_entries"]["status"] == "not_initialized"
    assert preview["complete_reference_listing"] is False
    assert "lexicon_unavailable" in {row["code"] for row in preview["review_issues"]}
    assert "bounded_preview" not in {row["code"] for row in preview["review_issues"]}
    assert not QueryLexiconState.objects.exists()
    assert QueryLexiconGeneration.objects.count() == generations_before


def test_preview_reports_inconsistent_lexicon_without_repair():
    source = person("错误词典指针")
    state = ensure_query_lexicon_state()
    QueryLexiconGeneration.objects.filter(pk=state.active_generation_id).update(status="retired")
    preview = person_merge_preview(source)
    assert preview["lexicon_entries"]["available"] is False
    assert preview["lexicon_entries"]["status"] == "inconsistent"
    assert preview["complete_reference_listing"] is False
    assert "bounded_preview" not in {row["code"] for row in preview["review_issues"]}
    state.active_generation.refresh_from_db()
    assert state.active_generation.status == "retired"


def test_preview_marks_truncated_lexicon_as_incomplete(monkeypatch):
    source = person("有界词典预览")
    state = ensure_query_lexicon_state()
    lexicon_entry(state.active_generation, source, "第一个词")
    lexicon_entry(state.active_generation, source, "第二个词")
    monkeypatch.setattr(person_resolution, "REFERENCE_LIMIT", 1)
    preview = person_merge_preview(source)
    assert preview["lexicon_entries"]["source"] == 2
    assert len(preview["lexicon_entries"]["source_rows"]) == 1
    assert preview["lexicon_entries"]["truncated"] is True
    assert preview["complete_reference_listing"] is False


def test_preview_fingerprint_changes_with_current_reference_values():
    source, target = person("甲"), person("乙")
    _work, _edition, relation = holding(source)
    before = person_merge_preview(source, target)["fingerprint"]
    Contribution.objects.filter(pk=relation.pk).update(order=10)
    assert person_merge_preview(source, target)["fingerprint"] != before


def test_preview_reports_identity_conflicts_and_existing_drafts():
    source = person("甲", external_ids={"orcid": "one"})
    target = person("乙", external_ids={"orcid": "two"})
    profile = ScholarProfile.objects.create(person=source, slug="draft-source-profile")
    EditorialRevision.objects.create(
        target_type="scholar_profile", target_id=profile.pk, revision=1, base_revision=0,
        status="draft", patch={"short_description": "待发布"}, idempotency_key="person-preview-draft",
    )
    preview = person_merge_preview(source, target)
    assert any(row["field"] == "external_ids.orcid" for row in preview["identity_conflicts"])
    assert "pending_editorial_drafts" in {row["code"] for row in preview["review_issues"]}


def test_preview_marks_truncated_scope_instead_of_claiming_completeness(monkeypatch):
    source, target = person("甲"), person("乙")
    holding(source, "第一本")
    holding(source, "第二本")
    monkeypatch.setattr(person_resolution, "REFERENCE_LIMIT", 1)
    result = person_merge_preview(source, target)
    assert result["complete_reference_listing"] is False
    assert "bounded_preview" in {row["code"] for row in result["review_issues"]}
    contributions = next(row for row in result["references"] if row["model"] == "catalog.Contribution")
    assert contributions["source_count"] == 2 and len(contributions["source_rows"]) == 1


def test_preview_rejects_unknown_reference_inventory_and_self_merge(monkeypatch):
    source = person()
    with pytest.raises(ValueError, match="不能相同"):
        person_merge_preview(source, source)
    monkeypatch.setattr(person_resolution, "PERSON_REFERENCES", person_resolution.PERSON_REFERENCES[1:])
    with pytest.raises(ValueError, match="引用结构"):
        person_merge_preview(source)


def test_resolution_api_preserves_staff_and_owner_boundaries(api_client, reader_user, settings):
    source, target = person(), person()
    duplicates_url = f"/api/catalog/admin/people/{source.pk}/duplicates/"
    preview_url = f"/api/catalog/admin/people/{source.pk}/merge-preview/"
    assert api_client.get(duplicates_url).status_code in {401, 403}
    api_client.force_authenticate(reader_user)
    assert api_client.get(duplicates_url).status_code == 403
    editor = User.objects.create_user(username="person-preview-editor", email="person-preview-editor@example.test", password="local-preview-only", role="editor", is_staff=True)
    api_client.force_authenticate(editor)
    assert api_client.get(duplicates_url).status_code == 200
    assert api_client.get(preview_url, {"target_person": str(target.pk)}).status_code == 403
    administrator = User.objects.create_user(username="person-preview-admin", email="person-preview-admin@example.test", password="local-preview-only", role="admin", is_staff=True)
    api_client.force_authenticate(administrator)
    assert api_client.get(preview_url, {"target_person": str(target.pk)}).status_code == 403
    owner = User.objects.create_superuser(username="person-preview-owner", email="person-preview-owner@example.test", password="local-preview-only")
    settings.LIBRARY_OWNER_EMAIL = owner.email
    api_client.force_authenticate(owner)
    response = api_client.get(preview_url, {"target_person": str(target.pk)})
    assert response.status_code == 200, response.data
    assert response["Cache-Control"] == "private, no-store"
    assert response.data["merge_execution_available"] is True
    assert response.data["execution_policy"] == "person-merge-noncolliding-v1"
    assert api_client.post(preview_url, {"target_person": str(target.pk)}, format="json").status_code == 405
    assert api_client.get(preview_url, {"target_person": "invalid"}).status_code == 400
    assert api_client.get(duplicates_url, {"limit": 51}).status_code == 400
    source.refresh_from_db()
    assert source.merged_into_id is None
