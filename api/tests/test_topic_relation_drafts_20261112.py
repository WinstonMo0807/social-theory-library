"""Published topic relation edits accumulate without changing formal rows."""
import pytest

from catalog.models import (
    CanonicalObjectRevision, Discipline, EditorialRevision, Subdiscipline,
    Topic, TopicDisciplineRelation, TopicSubdisciplineRelation,
)
from catalog.services.editorial_drafts import save_object_editorial_patch
from .test_reading_paths_20261021 import source

pytestmark = pytest.mark.django_db


def test_sequential_relation_edits_preserve_content_and_publish_together(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    edition = source(fulltext=False)[1]
    topic = Topic.objects.create(name="制度与社会", slug="relation-draft-test", editorial_status="published", curation={"edition_ids": [str(edition.pk)]})
    discipline = Discipline.objects.get_or_create(name="社会学", defaults={"slug": "draft-soc"})[0]
    first, second = [Subdiscipline.objects.create(name=name, slug=slug, discipline=discipline) for name, slug in
                     [("组织社会学", "draft-org"), ("政治社会学", "draft-pol")]]
    original = TopicSubdisciplineRelation.objects.create(topic=topic, subdiscipline=first, review_status="approved")
    save_object_editorial_patch("topic", topic.pk, {"description": "制度与社会关系的研究。"}, actor=admin_user)
    url = "/api/catalog/admin/knowledge-relations/"

    removed = api_client.delete(f"{url}topic-subdisciplines/{original.pk}/")
    assert removed.status_code == 202
    assert removed.data["publication_required"] is True
    added = api_client.post(f"{url}topic-subdisciplines/", {
        "topic": str(topic.pk), "subdiscipline": str(second.pk),
        "relation_label": "政治权力与社会组织", "review_status": "approved",
    }, format="json")
    assert added.status_code == 202, added.data
    # Re-adding a pending relation updates it rather than creating duplicates.
    repeated = api_client.post(f"{url}topic-subdisciplines/", {
        "topic": str(topic.pk), "subdiscipline": str(second.pk),
        "relation_label": "权力与制度运行", "review_status": "approved",
    }, format="json")
    assert repeated.status_code == 202, repeated.data
    added_discipline = api_client.post(f"{url}topic-disciplines/", {
        "topic": str(topic.pk), "discipline": str(discipline.pk),
        "is_primary": True, "review_status": "approved",
    }, format="json")
    assert added_discipline.status_code == 202, added_discipline.data
    drafts = EditorialRevision.objects.filter(target_type="topic", target_id=topic.pk, status="draft")
    assert drafts.count() == 1
    revision = drafts.get()
    assert revision.patch["description"] == "制度与社会关系的研究。"
    assert revision.patch["subdiscipline_relations"] == [{
        "subdiscipline_id": str(second.pk), "relation_label": "权力与制度运行", "review_status": "approved",
    }]
    assert revision.patch["discipline_relations"][0]["discipline_id"] == str(discipline.pk)
    assert TopicSubdisciplineRelation.objects.filter(pk=original.pk).exists()
    assert not TopicDisciplineRelation.objects.filter(topic=topic).exists()

    published = api_client.post(f"/api/catalog/admin/editorial-revisions/{revision.pk}/publish/", {}, format="json")
    assert published.status_code == 200, published.data
    topic.refresh_from_db()
    assert topic.description == "制度与社会关系的研究。"
    assert list(topic.subdiscipline_relations.values_list("subdiscipline_id", flat=True)) == [second.pk]
    assert topic.discipline_relations.get().discipline_id == discipline.pk


def test_addition_preserves_other_pending_relations_and_rejects_stale_base(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    topic = Topic.objects.create(name="发展与分层", slug="relation-merge-test", editorial_status="published")
    discipline = Discipline.objects.get_or_create(name="社会学", defaults={"slug": "merge-soc"})[0]
    subs = [Subdiscipline.objects.create(name=f"子学科{i}", slug=f"merge-sub-{i}", discipline=discipline) for i in range(3)]
    url = "/api/catalog/admin/knowledge-relations/topic-subdisciplines/"
    for sub in subs[:2]:
        response = api_client.post(url, {"topic": str(topic.pk), "subdiscipline": str(sub.pk), "review_status": "approved"}, format="json")
        assert response.status_code == 202, response.data
    revision = EditorialRevision.objects.get(target_type="topic", target_id=topic.pk, status="draft")
    assert {row["subdiscipline_id"] for row in revision.patch["subdiscipline_relations"]} == {str(sub.pk) for sub in subs[:2]}
    canonical = CanonicalObjectRevision.objects.get(object_type="topic", object_id=topic.pk)
    canonical.current_revision += 1
    canonical.save(update_fields=["current_revision"])
    rejected = api_client.post(url, {"topic": str(topic.pk), "subdiscipline": str(subs[2].pk)}, format="json")
    assert rejected.status_code == 400
    assert "正式资料已变化" in rejected.data["detail"]
    assert not topic.subdiscipline_relations.exists()
    assert EditorialRevision.objects.filter(target_type="topic", target_id=topic.pk, status="draft").count() == 1
