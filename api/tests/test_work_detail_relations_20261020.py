"""Synthetic PDF33–35 relationship regressions; reserved for final acceptance."""
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import (
    Contribution, Edition, EditorialRevision, JournalIssueArticle, KnowledgeNode,
    Person, ReadingPath, ReadingPathItem, RecommendationIssue, ScholarProfile,
    Topic, Work, WorkNodeRelation, WorkTopicRelation,
)
from catalog.services.work_detail_relations import public_issue_contents, public_work_relations
from catalog.catalog_search_serializers import CatalogEditionSerializer
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def publish(work=None, *, kind="book", primary=True, people=()):
    work = work or Work.objects.create(title=f"Synthetic {uuid4()}", document_type=kind)
    edition = Edition.objects.create(work=work, state="published", is_primary=primary, public_slug=f"synthetic-{uuid4()}")
    for person in people:
        Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    activate_catalog_revision(edition, fulltext_ready=False)
    return work, edition


def test_relationships_belong_to_selected_snapshot_and_recheck_public_endpoints():
    work = Work.objects.create(title="Synthetic version-specific associations")
    node = KnowledgeNode.objects.create(canonical_name_zh="Published concept", slug="published-concept", node_type="concept", status="published")
    topic = Topic.objects.create(name="Published topic", slug="published-topic", editorial_status="published")
    person = Person.objects.create(preferred_name="Published contributor", authority_status="verified")
    scholar = ScholarProfile.objects.create(person=person, slug="public-contributor", editorial_status="published")
    _, primary = publish(work)
    WorkNodeRelation.objects.create(work=work, node=node, status="published")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    _, selected = publish(work, primary=False, people=[person])
    assert public_work_relations(work, primary)["concepts"] == []
    selected_data = public_work_relations(work, selected)
    assert [row["id"] for row in selected_data["concepts"]] == [str(node.pk)]
    assert [row["id"] for row in selected_data["topics"]] == [str(topic.pk)]
    assert [row["id"] for row in selected_data["scholars"]] == [str(scholar.pk)]
    node.status = "draft"
    node.save(update_fields=["status"])
    topic.editorial_status = "draft"
    topic.save(update_fields=["editorial_status"])
    person.authority_status = "unverified"
    person.save(update_fields=["authority_status"])
    withdrawn = public_work_relations(work, selected)
    assert withdrawn["concepts"] == withdrawn["topics"] == withdrawn["scholars"] == []
    person_data = CatalogEditionSerializer(selected).data["contributors"][0]["person"]
    assert person_data["preferred_name"] == "Published contributor"
    assert person_data["scholar_slug"] is None
    assert person_data["portrait"] == "" and person_data["portrait_media"] is None


def test_related_works_match_published_snapshots_after_query_not_first_page():
    topic = Topic.objects.create(name="Shared synthetic topic", slug="shared-topic", editorial_status="published")
    source = Work.objects.create(title="Source synthetic work")
    other = Work.objects.create(title="Related synthetic work")
    for work in (source, other):
        WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    _, source_edition = publish(source)
    _, other_edition = publish(other)
    WorkTopicRelation.objects.filter(work=other).delete()
    for _ in range(7):
        publish()
    values = public_work_relations(source, source_edition)["works"]
    assert [row["id"] for row in values] == [str(other.pk)]
    other_edition.state = "withdrawn"
    other_edition.save(update_fields=["state"])
    assert public_work_relations(source, source_edition)["works"] == []


def test_unpublished_relationship_changes_cannot_create_related_work():
    source, selected = publish()
    target, _ = publish()
    topic = Topic.objects.create(name="Unpublished relation", slug="new-draft-relation", editorial_status="published")
    for work in (source, target):
        WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    values = public_work_relations(source, selected)
    assert values["topics"] == values["works"] == []


def test_related_reading_paths_require_explicit_work_item_and_public_status():
    work, selected = publish()
    public = ReadingPath.objects.create(title="Direct public path", slug="direct-path", status="published")
    private = ReadingPath.objects.create(title="Draft path", slug="draft-path", status="draft")
    unrelated = ReadingPath.objects.create(title="Unrelated public path", slug="unrelated-path", status="published")
    for path in (public, private):
        ReadingPathItem.objects.create(reading_path=path, work=work, stage_name="Synthetic stage")
    assert [row["id"] for row in public_work_relations(work, selected)["reading_paths"]] == [str(public.pk)]
    assert unrelated.pk != public.pk


def test_issue_membership_and_article_links_use_published_snapshots():
    article, selected = publish(kind="journal_article")
    old_slug = selected.public_slug
    issue_work = Work.objects.create(title="Synthetic journal issue", document_type="journal_issue")
    issue = Edition.objects.create(work=issue_work, state="published", is_primary=True, public_slug="synthetic-issue")
    entry = JournalIssueArticle.objects.create(issue=issue, article_work=article, title="Published issue entry", page_range="3–9")
    activate_catalog_revision(issue, fulltext_ready=False)
    entry.delete()
    selected.public_slug = "unpublished-slug"
    selected.save(update_fields=["public_slug"])
    result = public_work_relations(article, selected)["journal_issues"]
    assert len(result) == 1 and result[0]["id"] == str(issue_work.pk)
    assert result[0]["contents"][0]["title"] == "Published issue entry"
    assert result[0]["contents"][0]["article_href"] == f"/works/{old_slug}"
    selected.state = "withdrawn"
    selected.save(update_fields=["state"])
    assert public_issue_contents(result[0]["contents"])[0]["article_href"] == ""


def test_scheduled_and_draft_curations_do_not_expose_unpublished_membership():
    work, edition = publish()
    now = timezone.now()
    for status in ("published", "draft"):
        issue = RecommendationIssue.objects.create(title=f"Mutable {status}", slug=f"synthetic-curation-{status}")
        revision = EditorialRevision.objects.create(
            target_type="recommendation_issue", target_id=issue.pk, revision=1, status=status,
            materialized_preview={"title": f"Frozen {status}", "introduction": "Synthetic published introduction",
                "items": [{"id": str(uuid4()), "kind": "catalog", "edition_id": str(edition.pk), "work_id": str(work.pk)}]},
        )
        issue.active_revision, issue.display_from = revision, now
        issue.save(update_fields=["active_revision", "display_from"])
    curations = public_work_relations(work, edition)["curations"]
    assert len(curations) == 1 and curations[0]["title"] == "Frozen published"
    assert curations[0]["summary"] == "Synthetic published introduction"


def test_unrelated_or_withdrawn_selected_edition_cannot_return_relations():
    work, selected = publish()
    other, _ = publish()
    assert all(value == [] for value in public_work_relations(other, selected).values())
    selected.state = "withdrawn"
    selected.save(update_fields=["state"])
    assert all(value == [] for value in public_work_relations(work, selected).values())
