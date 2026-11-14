"""Request-local reuse must retain withdrawal and published-content boundaries."""
import pytest

from catalog.models import Edition, PublicationState, Topic, Work, WorkTopicRelation
from catalog.serializers import EditionCompactSerializer
from .v304_helpers import activate_catalog_revision


@pytest.mark.django_db
def test_home_reuse_does_not_survive_a_publication_withdrawal(api_client):
    work = Work.objects.create(title="公开版本", document_type="book")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED,
                                     is_primary=True, public_slug="performance-public")
    activate_catalog_revision(edition, fulltext_ready=False)
    first = api_client.get("/api/catalog/home/").json()
    assert first["works"][0] == first["random_works"][0]
    Work.objects.filter(pk=work.pk).update(title="尚未发布的修改")
    assert api_client.get("/api/catalog/home/").json()["works"][0]["title"] == "公开版本"
    Edition.objects.filter(pk=edition.pk).update(state=PublicationState.WITHDRAWN)
    withdrawn = api_client.get("/api/catalog/home/").json()
    assert withdrawn["works"] == withdrawn["random_works"] == []


@pytest.mark.django_db
def test_edition_representation_rechecks_taxonomy_and_discards_local_snapshot():
    work = Work.objects.create(title="版本边界", document_type="book")
    edition = Edition.objects.create(work=work, state=PublicationState.PUBLISHED,
                                     is_primary=True, public_slug="performance-taxonomy")
    topic = Topic.objects.create(name="公开主题", slug="performance-topic", editorial_status="published")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    activate_catalog_revision(edition, fulltext_ready=False)
    edition.refresh_from_db()
    serializer = EditionCompactSerializer()
    assert serializer._public_snapshot(edition)["knowledge"]["topics"]
    first = serializer.to_representation(edition)
    assert not hasattr(serializer, "_representation_snapshot")
    Topic.objects.filter(pk=topic.pk).update(editorial_status="archived")
    # Reusing the serializer itself must not retain the previous visibility read.
    assert serializer._public_snapshot(edition)["knowledge"]["topics"] == []
    assert serializer.to_representation(edition) == first
    assert not hasattr(serializer, "_representation_snapshot")
