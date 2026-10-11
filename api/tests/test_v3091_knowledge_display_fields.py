import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import CatalogPublicationRevision, Discipline, Edition, KnowledgeNode, Person, ScholarProfile, Subdiscipline, Work
from catalog.serializers import AdminScholarSerializer, AdminWorkPagePreviewSerializer, DisciplineSerializer, EditionCompactSerializer
from catalog.services.editorial_revision import EditorialRevisionError, changed_editorial_patch
from catalog.theory_serializers import KnowledgeNodeDetailSerializer
from .editorial_fixtures import editorial_request

pytestmark = pytest.mark.django_db


def publish_saved(client, saved):
    assert saved.status_code == 202, saved.data
    result = client.post(
        f"/api/catalog/admin/editorial-revisions/{saved.data['editorial_revision']['id']}/publish/",
        {}, format="json",
    )
    assert result.status_code == 200, result.data


def test_theory_metadata_waits_for_publication_and_is_searchable(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition", canonical_name_zh="Display Theory", slug="display-theory",
        summary="Original summary", definition="Original definition", status="published",
    )
    fields = {"core_concepts": ["A real editorial concept"], "keywords": ["ScopeKeyword"],
              "summary_source": "Editor supplied source"}
    saved = editorial_request(api_client, "patch", f"/api/catalog/admin/theory-system/nodes/{node.pk}/", fields, format="json")
    node.refresh_from_db()
    assert node.core_concepts == [] and node.summary_source == ""
    publish_saved(api_client, saved)
    node.refresh_from_db()
    public = KnowledgeNodeDetailSerializer(node).data
    assert all(public[key] == value for key, value in fields.items())
    assert node.summary == "Original summary" and node.definition == "Original definition"
    assert node.versions.latest("version_number").snapshot["summary_source"] == fields["summary_source"]
    found = api_client.get("/api/catalog/admin/theory-system/nodes/?q=ScopeKeyword")
    assert found.status_code == 200 and str(node.pk) in {str(row["id"]) for row in found.data["results"]}
    with pytest.raises(EditorialRevisionError):
        changed_editorial_patch(target_type="knowledge_node", target=node, patch={"keywords": ["x" * 81]})


def test_discipline_selection_changes_display_without_changing_membership(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    parent = Discipline.objects.create(name="Display Discipline", slug="display-discipline", code="display-discipline", editorial_status="published")
    other = Discipline.objects.create(name="Other Discipline", slug="other-discipline", code="other-discipline")
    first = Subdiscipline.objects.create(name="A Child", slug="a-child", discipline=parent, editorial_status="published")
    second = Subdiscipline.objects.create(name="B Child", slug="b-child", discipline=parent, editorial_status="published")
    private = Subdiscipline.objects.create(name="Private Child", slug="private-child", discipline=parent)
    foreign = Subdiscipline.objects.create(name="Foreign Child", slug="foreign-child", discipline=other)
    ids = [str(second.pk), str(private.pk), str(first.pk)]
    saved = editorial_request(api_client, "patch", f"/api/catalog/admin/disciplines/{parent.pk}/", {"display_subdiscipline_ids": ids}, format="json")
    parent.refresh_from_db()
    assert parent.display_subdiscipline_ids is None
    publish_saved(api_client, saved)
    parent.refresh_from_db()
    assert parent.display_subdiscipline_ids == ids
    assert [row["id"] for row in DisciplineSerializer(parent).data["display_subdisciplines"]] == [str(second.pk), str(first.pk)]
    assert Subdiscipline.objects.filter(pk__in=[first.pk, second.pk, private.pk], discipline=parent).count() == 3
    with pytest.raises(EditorialRevisionError):
        changed_editorial_patch(target_type="discipline", target=parent, patch={"display_subdiscipline_ids": [str(foreign.pk)]})
    with pytest.raises(EditorialRevisionError):
        changed_editorial_patch(target_type="discipline", target=parent, patch={"display_subdiscipline_ids": ids * 2})


def test_scholar_notes_follow_selected_works_and_direct_drafts_use_the_same_limits():
    work = Work.objects.create(title="Display Note Work")
    profile = ScholarProfile.objects.create(person=Person.objects.create(preferred_name="Display Note Scholar"), slug="display-note-scholar")
    curation = {"essential_work_ids": [str(work.pk)], "essential_work_notes": {str(work.pk): "  A reason to read  "}}
    accepted = AdminScholarSerializer(instance=profile).validate_curation(curation)
    assert accepted["essential_work_notes"] == {str(work.pk): "A reason to read"}
    patch = changed_editorial_patch(target_type="scholar_profile", target=profile, patch={"curation": accepted})
    assert patch["curation"]["essential_work_notes"] == accepted["essential_work_notes"]
    profile.refresh_from_db()
    assert profile.curation == {}
    invalid = {"essential_work_ids": [str(work.pk)], "essential_work_notes": {str(work.pk): "x" * 501}}
    with pytest.raises(ValidationError):
        AdminScholarSerializer(instance=profile).validate_curation(invalid)
    with pytest.raises(EditorialRevisionError):
        changed_editorial_patch(target_type="scholar_profile", target=profile, patch={"curation": invalid})


def test_nonbook_saved_preview_uses_selected_edition_and_public_metadata_uses_active_snapshot():
    work = Work.objects.create(title="Display Thesis", document_type="thesis")
    edition = Edition.objects.create(work=work, state="published", degree_institution="Canonical University", degree_type="Canonical Degree")
    revision = CatalogPublicationRevision.objects.create(
        edition=edition, revision=1, status="active", metadata_ready=True,
        snapshot={"work": {"id": str(work.pk), "title": work.title}, "edition": {"degree_institution": "Published University", "degree_type": "Published Degree"}},
        content_fingerprint="f" * 64,
    )
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision"])
    public = EditionCompactSerializer(edition).data
    assert public["degree_institution"] == "Published University" and public["degree_type"] == "Published Degree"
    preview = AdminWorkPagePreviewSerializer(work, context={
        "preview_edition": edition,
        "editorial_preview": {"bibliography": {"edition_id": str(edition.pk), "values": {"degree_institution": "Saved Draft University", "degree_type": "Saved Draft Degree"}}},
    }).data
    assert preview["edition"]["id"] == str(edition.pk)
    assert preview["edition"]["degree_institution"] == "Saved Draft University"
    edition.refresh_from_db()
    assert edition.degree_institution == "Canonical University"
    legacy = Edition.objects.create(work=work, state="published", degree_institution="Later Canonical University", degree_type="Later Canonical Degree")
    legacy.active_catalog_revision = CatalogPublicationRevision.objects.create(
        edition=legacy, revision=1, status="active", metadata_ready=True,
        snapshot={"work": {"id": str(work.pk), "title": work.title}, "edition": {}},
        content_fingerprint="e" * 64,
    )
    legacy.save(update_fields=["active_catalog_revision"])
    old = EditionCompactSerializer(legacy).data
    assert old["degree_institution"] == "" and old["degree_type"] == ""
