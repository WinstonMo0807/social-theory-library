"""PDF68–71 acceptance definitions. Reserved for the final unified run."""
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.http import QueryDict
from rest_framework.exceptions import ValidationError

from catalog.models import (ClaimEvidence, CuratedClaim, EditorialRevision, EvidenceSpan, KnowledgeNode, KnowledgeNodeTopic,
    Person, ReadingPath, ScholarProfile, Topic, WorkTopicRelation)
from catalog.serializers import AdminTopicSerializer
from catalog.services import editorial_issues, shared_curation
from catalog.services.editorial_revision import create_editorial_revision
from catalog.services.public_reading_paths import capture_reading_path_publication
from catalog.services.public_topics import (capture_topic_publication, preview_topic, public_topic_detail, public_topic_directory,
    topic_follow_summary, validate_topic_parent)
from .test_reading_paths_20261021 import source
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def topic(name="Synthetic topic", **values):
    return Topic.objects.create(name=name + str(uuid4()), slug=f"topic-{uuid4()}", editorial_status="published", **values)


def quotes(row, actor, count=1):
    _work, _edition, asset, publication = source()
    page = asset.pages.get(index=1)
    texts = [f"Synthetic topic quotation {index:02}." for index in range(count)]
    page.text = " ".join(texts)
    page.save(update_fields=["text"])
    spans = []
    for text in texts:
        offset = page.text.index(text)
        spans.append(EvidenceSpan.objects.create(document_revision=publication.document_revision, page=page, page_number=1,
            start_offset=offset, end_offset=offset + len(text), original_text=text, normalized_text=text, content_hash=sha256(text.encode()).hexdigest()))
    saved = shared_curation.save_curation("topic", row.pk, {"items": [{"source_type": "span", "source_id": str(span.pk)} for span in spans]}, actor)
    shared_curation.publish_curation("topic", row.pk, saved["edit_version"], actor)
    return saved["items"], asset, spans


def test_hierarchy_formal_identity_and_follow_do_not_read_unpublished_changes(admin_user):
    parent, other = topic("Parent"), topic("Other")
    row = topic(parent=parent)
    formal = capture_topic_publication(row, actor=admin_user)
    original_name, original_slug = row.name, row.slug
    with pytest.raises(ValidationError):
        validate_topic_parent(parent, row.pk)
    Topic.objects.filter(pk=row.pk).update(name="Unpublished name", slug="unpublished-slug", parent=other)
    result = public_topic_detail(original_slug)
    assert result["name"] == original_name and result["parent"]["id"] == str(parent.pk)
    assert result["breadcrumbs"][-1]["id"] == str(parent.pk)
    assert topic_follow_summary(row.pk)["public_revision"] == f"{formal.pk}:{formal.revision}"
    with pytest.raises(ValidationError):
        validate_topic_parent(row, row.pk)
    Topic.objects.filter(pk=row.pk).update(editorial_status="archived")
    assert topic_follow_summary(row.pk) is None


def test_directory_parent_union_search_and_curated_work_sort_are_exact(admin_user):
    left, right, outside = topic("Left"), topic("Right"), topic("Outside")
    first, second = topic("MATCH first", parent=left), topic("MATCH second", parent=right)
    editions = [source(fulltext=False)[1] for _ in range(2)]
    first.curation = {"edition_ids": [str(row.pk) for row in editions]}
    first.save(update_fields=["curation"])
    capture_topic_publication(first, actor=admin_user)
    params = QueryDict("", mutable=True)
    params.setlist("parent", [str(left.pk), str(right.pk)])
    params.update(q="MATCH", sort="works", page_size="1")
    data = public_topic_directory(params)
    assert data["count"] == 2 and data["results"][0]["id"] == str(first.pk)
    assert data["results"][0]["work_count"] == data["results"][0]["edition_count"] == 2
    assert len(data["selected_parents"]) == 2 and data["next"]
    params.appendlist("parent", str(uuid4()))
    assert public_topic_directory(params)["count"] == 0
    assert outside.pk not in {first.pk, second.pk}


def test_normalized_questions_and_discussion_counts_require_current_public_evidence(admin_user):
    row = topic(core_questions=["Legacy prose is not a normalized question"])
    question = KnowledgeNode.objects.create(node_type="research_problem", canonical_name_zh="Synthetic canonical problem", slug=f"problem-{uuid4()}", status="published")
    KnowledgeNodeTopic.objects.create(topic=row, node=question, status="published")
    references, asset, spans = quotes(row, admin_user)
    claim = CuratedClaim.objects.create(node=question, kind="major_response", proposition="Synthetic editorial response", status="published")
    ClaimEvidence.objects.create(claim=claim, evidence_span=spans[0], role="supports")
    CuratedClaim.objects.create(node=question, kind="debate_position", proposition="Private draft position", status="draft")
    result = public_topic_detail(row.slug)
    assert result["questions"]["count"] == 1
    assert result["questions"]["results"][0]["response_count"] == 1
    assert result["questions"]["results"][0]["discussion_count"] == 0
    asset.sha256 = "b" * 64
    asset.save(update_fields=["sha256"])
    result = public_topic_detail(row.slug)
    assert result["questions"]["results"][0]["response_count"] == 0 and result["evidence"]["count"] == 0


def test_directory_retains_canonical_theory_filter_without_matching_legacy_names():
    row = topic()
    theory = KnowledgeNode.objects.create(node_type="theory_tradition", canonical_name_zh="Synthetic theory", slug=f"theory-{uuid4()}", status="published")
    relation = KnowledgeNodeTopic.objects.create(topic=row, node=theory, status="published")
    for value in (str(theory.pk), theory.slug):
        result = public_topic_directory({"theory": value})
        assert [item["id"] for item in result["results"]] == [str(row.pk)]
    relation.status = "draft"
    relation.save(update_fields=["status"])
    assert public_topic_directory({"theory": str(theory.pk)})["count"] == 0


def test_no_fulltext_and_explicit_planned_materials_are_not_conflated(admin_user):
    row = topic()
    work, edition, _asset, _revision = source(fulltext=False)
    WorkTopicRelation.objects.create(topic=row, work=work, review_status="approved")
    activate_catalog_revision(edition, fulltext_ready=False)
    issue = editorial_issues.create_issue({"title": "Synthetic topic issue", "items": [{"kind": "planned", "title": "Explicit synthetic planned material"}]}, admin_user)
    editorial_issues.publish_issue(issue.pk, editorial_issues.edit_version("recommendation_issue", issue.pk), admin_user)
    row.curation = {"issue_ids": [str(issue.pk)]}
    row.save(update_fields=["curation"])
    result = public_topic_detail(row.slug)
    assert result["work_facets"] == {"all": 2, "readable": 0, "no_fulltext": 1, "planned": 1}
    bibliography = public_topic_detail(row.slug, {"availability": "no_fulltext"})["works"]["results"]
    assert len(bibliography) == 1 and bibliography[0]["edition_id"] == str(edition.pk)
    planned = public_topic_detail(row.slug, {"availability": "planned"})["works"]["results"]
    assert len(planned) == 1 and planned[0]["edition_id"] is None and not planned[0]["reader_href"]


def test_unsaved_preview_parent_clear_and_quote_beyond_first_page_do_not_publish(api_client, admin_user):
    parent, alternate = topic("Parent"), topic("Alternate")
    row = topic(parent=parent)
    references, _asset, _spans = quotes(row, admin_user, 13)
    row.curation = {"featured_source_id": references[0]["id"]}
    row.save(update_fields=["curation"])
    capture_topic_publication(row, actor=admin_user)
    draft = create_editorial_revision(target_type="topic", target_id=row.pk, patch={"description": "Saved draft introduction"}, actor=admin_user, idempotency_key=f"topic-preview-{uuid4()}")
    before = EditorialRevision.objects.count()
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/"
    response = api_client.post(url, {"parent": str(alternate.pk), "curation": {"featured_source_id": references[-1]["id"]}}, format="json")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    projected = response.data["perspective"]["data"]
    assert projected["description"] == "Saved draft introduction"
    assert projected["parent"]["id"] == str(alternate.pk) and projected["breadcrumbs"][-1]["id"] == str(alternate.pk)
    assert projected["featured_quote"]["id"] == references[-1]["id"]
    assert references[-1]["id"] not in {item["id"] for item in projected["evidence"]["results"]}
    published = response.data["perspectives"]["published"]["data"]
    assert published["parent"]["id"] == str(parent.pk) and published["featured_quote"]["id"] == references[0]["id"]
    cleared = api_client.post(url, {"parent": None, "curation": {"featured_source_id": None}}, format="json")
    assert cleared.data["perspective"]["data"]["parent"] is None and cleared.data["perspective"]["data"]["breadcrumbs"] == []
    assert cleared.data["perspective"]["data"]["featured_quote"] is None
    row.refresh_from_db(); draft.refresh_from_db()
    assert row.parent_id == parent.pk and row.curation["featured_source_id"] == references[0]["id"]
    assert draft.patch == {"description": "Saved draft introduction"} and EditorialRevision.objects.count() == before


def test_preview_rejects_cycles_wrong_types_foreign_sources_and_reader_access(api_client, admin_user, reader_user):
    row, other = topic(), topic("Other")
    child = topic("Child", parent=row)
    references, _asset, _spans = quotes(other, admin_user)
    concept = KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="Wrong question type", slug=f"concept-{uuid4()}", status="published")
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/"
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, {"parent": None}, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    for body in ({"parent": str(child.pk)}, {"curation": {"question_node_ids": [str(concept.pk)]}},
        {"curation": {"featured_source_id": references[0]["id"]}}, {"curation": {"private_text": "forbidden"}}):
        assert api_client.post(url, body, format="json").status_code == 400


def test_legacy_work_paths_and_person_ids_keep_identity_without_guessing_editions():
    work, edition, _asset, _revision = source(fulltext=False)
    person = Person.objects.create(preferred_name="Synthetic legacy person", authority_status="verified")
    profile = ScholarProfile.objects.create(person=person, slug=f"legacy-person-{uuid4()}", editorial_status="published")
    row = topic(curation={"foundational_work_ids": [str(work.pk)], "related_scholar_ids": [str(person.pk)],
        "reading_paths": [{"title": "Legacy inline route", "work_ids": [str(work.pk)]}]})
    serializer = AdminTopicSerializer(row, data={"curation": row.curation}, partial=True)
    assert serializer.is_valid(), serializer.errors
    result = public_topic_detail(row.slug)
    assert result["legacy"]["curated_works"]["foundational"][0]["id"] == str(work.pk)
    assert "edition_id" not in result["legacy"]["curated_works"]["foundational"][0]
    assert result["legacy"]["reading_paths"][0]["works"][0]["id"] == str(work.pk)
    assert result["legacy"]["related_scholars"][0]["id"] == str(person.pk)
    assert result["legacy"]["related_scholars"][0]["profile_id"] == str(profile.pk)
    edition.state = "draft"; edition.save(update_fields=["state"])
    assert public_topic_detail(row.slug)["legacy"]["reading_paths"][0]["unavailable_work_ids"] == [str(work.pk)]


def test_path_membership_uses_formal_topic_snapshot_and_current_permission(admin_user):
    row = topic()
    path = ReadingPath.objects.create(title="Formal topic path", slug=f"topic-path-{uuid4()}", status="published")
    path.topics.add(row)
    capture_reading_path_publication(path, actor=admin_user)
    path.topics.clear()
    assert public_topic_detail(row.slug)["paths"]["count"] == 1
    path.status = "draft"; path.save(update_fields=["status"])
    assert public_topic_detail(row.slug)["paths"]["count"] == 0
