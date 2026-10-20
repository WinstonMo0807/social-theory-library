"""Synthetic PDF24–27 regressions, authored but not run during development."""
from hashlib import sha256
from uuid import uuid4

import pytest

from catalog.models import Asset, Contribution, Edition, EvidenceSpan, KnowledgeNode, Page, Person, Topic, Work, WorkNodeRelation, WorkTopicRelation
from .v304_helpers import activate_catalog_revision

URL = "/api/catalog/search/"


def search(client, **params):
    return client.get(URL, {"context": "global", "scope": "catalog", **params})


def publish(work=None, *, title="合成公开作品", language="en", year=2001, primary=True, author=None, readable=False, fulltext=""):
    work = work or Work.objects.create(title=title, document_type="book", language=language)
    work.language = language
    work.save(update_fields=["language"])
    edition = Edition.objects.create(work=work, state="published", is_primary=primary, public_slug=f"synthetic-{uuid4()}", publication_year=year, publisher="合成已发表出版社")
    if author:
        Contribution.objects.create(edition=edition, person=author, role="author", approved=True)
    asset = None
    if readable:
        asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", access_status="public",
            file=f"synthetic/{uuid4()}.pdf", sha256=uuid4().hex * 2, page_count=1)
        page = Page.objects.create(asset=asset, index=1, text=fulltext)
    revision = activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=bool(readable))
    if readable and fulltext:
        EvidenceSpan.objects.create(document_revision=revision.document_revision, page=page, page_number=1, start_offset=0, end_offset=len(fulltext),
            original_text=fulltext, normalized_text=fulltext.lower(), content_hash=sha256(fulltext.encode()).hexdigest())
    return work, edition, asset


@pytest.mark.django_db
def test_empty_catalog_has_no_invented_totals_or_versions(api_client):
    response = search(api_client)
    assert response.status_code == 200 and response.data["scope"] == "catalog"
    assert response.data["works"] == [] and response.data["pagination"]["total"] == 0
    assert response.data["facets"]["year_histogram"] == []
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_search_and_representation_use_published_values_not_editorial_drafts(api_client):
    author = Person.objects.create(preferred_name="Synthetic Frozen Author", aliases=["Frozen alias"])
    work, edition, _ = publish(title="Frozen Title", author=author)
    work.title, work.abstract, work.language = "Secret Draft Title", "Secret Draft Abstract", "fr"
    work.save(update_fields=["title", "abstract", "language"])
    edition.publisher, edition.publication_year = "Secret Draft Publisher", 2099
    edition.save(update_fields=["publisher", "publication_year"])
    author.preferred_name = "Secret Draft Person"
    author.save(update_fields=["preferred_name"])
    response = search(api_client, q="Frozen alias", match=["author"])
    assert response.status_code == 200 and response.data["counts"]["works"] == 1
    row = response.data["works"][0]
    assert row["title"] == "Frozen Title" and row["language"] == "en"
    assert row["editions"][0]["publication_year"] == 2001
    assert row["editions"][0]["publisher"] == "合成已发表出版社"
    assert "Secret Draft" not in str(response.data)
    assert search(api_client, q="Secret Draft").data["counts"]["works"] == 0


@pytest.mark.django_db
def test_filters_must_match_one_edition_and_result_expands_all_public_versions(api_client):
    work, first, _ = publish(language="en", year=1990)
    _, second, _ = publish(work, language="fr", year=2020, primary=False)
    assert search(api_client, language=["en"], year_min=2010).data["counts"]["works"] == 0
    response = search(api_client, language=["fr"], year_min=2010)
    assert response.data["pagination"]["total"] == 1
    row = response.data["works"][0]
    assert row["matched_edition_ids"] == [str(second.pk)]
    assert {version["id"] for version in row["editions"]} == {str(first.pk), str(second.pk)}
    assert row["edition"]["id"] == str(first.pk)


@pytest.mark.django_db
def test_version_sort_cannot_multiply_work_pages_or_facet_counts(api_client):
    work, _, _ = publish(title="A", year=2000)
    publish(work, primary=False, year=2000)
    other, _, _ = publish(title="B", year=2024)
    first = search(api_client, sort="year", page_size=1).data
    second = search(api_client, sort="year", page_size=1, page=2).data
    assert first["pagination"] == {"page": 1, "page_size": 1, "total": 2, "total_pages": 2}
    assert str(first["works"][0]["id"]) == str(other.pk)
    assert str(second["works"][0]["id"]) == str(work.pk)
    assert first["facets"]["year_histogram"] == [{"year": 2000, "count": 1}, {"year": 2024, "count": 1}]


@pytest.mark.django_db
def test_secondary_only_and_withdrawn_primary_do_not_expose_draft_work(api_client):
    publish(primary=False, title="Secondary only")
    work, first, _ = publish(title="Withdraw primary")
    publish(work, primary=False)
    first.state = "withdrawn"
    first.save(update_fields=["state"])
    assert search(api_client).data["counts"]["works"] == 0


@pytest.mark.django_db
def test_fulltext_only_uses_current_valid_non_stale_public_evidence(api_client):
    work, edition, asset = publish(readable=True, fulltext="Synthetic immutable evidence")
    response = search(api_client, q="immutable", match=["fulltext"])
    assert response.data["counts"]["works"] == 1
    EvidenceSpan.objects.filter(document_revision=edition.active_catalog_revision.document_revision).update(is_stale=True)
    assert search(api_client, q="immutable", match=["fulltext"]).data["counts"]["works"] == 0
    EvidenceSpan.objects.filter(document_revision=edition.active_catalog_revision.document_revision).update(is_stale=False)
    asset.validation_status = "invalid"
    asset.save(update_fields=["validation_status"])
    assert search(api_client, q="immutable", match=["fulltext"]).data["counts"]["works"] == 0
    row = search(api_client, access=["metadata"]).data["works"][0]
    assert row["edition"]["readable_asset"] is None
    assert row["edition"]["availability"] == "metadata"


@pytest.mark.django_db
def test_unpublished_or_old_document_cannot_match_fulltext(api_client):
    work, edition, asset = publish(readable=True, fulltext="Current public passage")
    other = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", access_status="public",
        is_current=False, file="synthetic/unpublished.pdf", sha256=uuid4().hex * 2)
    from catalog.models import DocumentRevision
    revision = DocumentRevision.objects.create(asset=other, revision=1, source_checksum=other.sha256, text_checksum="0" * 64)
    page = Page.objects.create(asset=other, index=1, text="Secret unactivated evidence")
    EvidenceSpan.objects.create(document_revision=revision, page=page, page_number=1, start_offset=0, end_offset=27,
        original_text=page.text, normalized_text=page.text.lower(), content_hash=sha256(page.text.encode()).hexdigest())
    assert search(api_client, q="unactivated", match=["fulltext"]).data["counts"]["works"] == 0


@pytest.mark.django_db
def test_snapshot_relations_are_required_and_withdrawn_nodes_disappear(api_client):
    work = Work.objects.create(title="Synthetic relation holding", document_type="book")
    topic = Topic.objects.create(name="Frozen Topic", slug="frozen-topic", editorial_status="published")
    theory = KnowledgeNode.objects.create(canonical_name_zh="Frozen Theory", slug="frozen-theory", node_type="theory_tradition", status="published")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    WorkNodeRelation.objects.create(work=work, node=theory, status="published")
    publish(work)
    new_topic = Topic.objects.create(name="Secret Draft Relation", slug="secret-relation", editorial_status="published")
    WorkTopicRelation.objects.create(work=work, topic=new_topic, review_status="approved")
    response = search(api_client, topic=["frozen-topic"], theory=["frozen-theory"])
    assert response.data["counts"]["works"] == 1
    assert search(api_client, topic=["secret-relation"]).data["counts"]["works"] == 0
    assert "Secret Draft" not in str(response.data)
    theory.status = "draft"
    theory.save(update_fields=["status"])
    assert search(api_client, theory=["frozen-theory"]).data["counts"]["works"] == 0
    assert search(api_client).data["facets"]["theories"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("access,validation,readable", [("public", "valid", True), ("inherit", "valid", True),
    ("registered", "valid", False), ("private", "valid", False), ("restricted", "valid", False), ("public", "pending", False)])
def test_catalog_reading_links_always_use_anonymous_public_access(api_client, admin_user, access, validation, readable):
    _, _, asset = publish(readable=True)
    asset.access_status, asset.validation_status = access, validation
    asset.save(update_fields=["access_status", "validation_status"])
    api_client.force_authenticate(admin_user)
    response = search(api_client, access=["readable" if readable else "metadata"])
    assert response.data["counts"]["works"] == 1
    assert bool(response.data["works"][0]["edition"]["readable_asset"]) == readable


@pytest.mark.django_db
@pytest.mark.parametrize("params", [{"year_min": 2026, "year_max": 2000}, {"match": ["unknown"]}, {"page": 0},
    {"page_size": 100}, {"q": "x" * 501}, {"language": ["en"] * 31}, {"access": ["private"]}])
def test_invalid_filters_return_actionable_400(api_client, params):
    assert search(api_client, **params).status_code == 400


@pytest.mark.django_db
def test_literal_like_characters_and_quotes_are_not_sql_wildcards(api_client):
    person = Person.objects.create(preferred_name="Synthetic 100%_Author")
    publish(author=person)
    assert search(api_client, q="100%_", match=["author"]).data["counts"]["works"] == 1
    assert search(api_client, q="x%' OR 1=1 --", match=["author"]).data["counts"]["works"] == 0
