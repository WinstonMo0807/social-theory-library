from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError

from catalog.models import (
    Asset, CatalogPublicationRevision, Contribution, DocumentRevision, EvidenceSpan,
    KnowledgeNode, Page, Person, ScholarProfile, Topic, WorkNodeRelation, WorkTopicRelation,
)
from catalog.services.viewpoint_search import _matching_evidence_span, viewpoint_search
from catalog.discovery_models import DiscoverySearchSession
from catalog.discovery_index_models import DiscoveryDocument
from catalog.models import SemanticIndexVersion
from catalog.services.discovery_sessions import execute_session
from catalog.services.discovery_sources import fingerprint, source_header, source_units
from .test_claim_pipeline_viewpoint_v300 import _claim, _source
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def search_result(asset, span, *, claim=None, filters=None):
    # Deliberately stale external hits must be checked against serving facts.
    row = {
        "id": "stale-index-hit", "asset_id": str(asset.pk),
        "work_id": str(asset.edition.work_id), "page_index": span.page_number,
        "snippet": f"未确认的索引文字 {span.original_text}",
        "title": "未确认的索引标题", "authors": ["未确认的索引作者"],
        "edition_slug": "unconfirmed-index-slug", "publication_year": 2099,
        "language": "en", "document_type": "journal_article",
    }
    return viewpoint_search(
        "贫困导致犯罪", filters=filters,
        retrieval_backend=lambda *args, **kwargs: {"results": [row]},
        claim_search_backend=lambda *args, **kwargs: {
            "hits": [{"claim_id": str(claim.pk)}] if claim else [],
        },
    )


@pytest.mark.parametrize("invalid", [
    "no_revision", "metadata_only", "withdrawn", "superseded", "other_edition",
    "unselected", "private", "restricted", "registered",
])
def test_stale_baseline_hit_cannot_bypass_publication_or_file_permissions(invalid):
    _work, edition, asset, document, spans = _source(title=f"公开资格 {invalid}", pages=1)
    if invalid != "no_revision":
        activate_catalog_revision(
            edition, reader_asset=asset, document_revision=document,
            fulltext_ready=invalid != "metadata_only",
        )
    if invalid == "withdrawn":
        edition.state = "withdrawn"
        edition.save(update_fields=["state", "updated_at"])
    elif invalid == "superseded":
        CatalogPublicationRevision.objects.filter(pk=edition.active_catalog_revision_id).update(status="superseded")
    elif invalid == "other_edition":
        _other_work, other, other_asset, other_document, _other_spans = _source(title="其他正式版本", pages=1)
        activate_catalog_revision(other, reader_asset=other_asset, document_revision=other_document)
        edition.active_catalog_revision = other.active_catalog_revision
        edition.save(update_fields=["active_catalog_revision", "updated_at"])
    elif invalid == "unselected":
        other = Asset.objects.create(
            edition=edition, kind="normalized", status="ready", sha256="f" * 64, version=2,
        )
        other_document = DocumentRevision.objects.create(
            asset=other, revision=1, is_active=True, source_checksum=other.sha256, text_checksum="c" * 64,
        )
        page = Page.objects.create(asset=other, index=1, text_source="embedded")
        spans = [EvidenceSpan.objects.create(
            document_revision=other_document, page=page, page_number=1,
            original_text=spans[0].original_text, normalized_text=spans[0].original_text,
            content_hash="b" * 64, quality=1,
        )]
        asset = other
    elif invalid in {"private", "restricted", "registered"}:
        asset.access_status = invalid
        asset.save(update_fields=["access_status", "updated_at"])
    result = search_result(asset, spans[0])
    assert result["baseline"]["results"] == []
    assert result["shadow"]["results"] == []
    assert result["metadata"]["unvalidated_baseline_results_excluded"] == 1


@pytest.mark.parametrize("access", ["registered", "private", "restricted"])
def test_viewpoint_keeps_explicit_authorized_viewer_access(access):
    _work, edition, asset, document, spans = _source(title=f"获准文件 {access}", pages=1)
    asset.access_status = access
    asset.save(update_fields=["access_status", "updated_at"])
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    result = search_result(asset, spans[0], filters={"_allowed_access_statuses": [access]})
    assert len(result["baseline"]["results"]) == 1


def test_previous_formal_document_remains_source_while_new_document_is_unpublished():
    _work, edition, asset, formal, spans = _source(title="保留正式正文", pages=1)
    activate_catalog_revision(edition, reader_asset=asset, document_revision=formal)
    formal.is_active = False
    formal.save(update_fields=["is_active", "updated_at"])
    pending = DocumentRevision.objects.create(
        asset=asset, revision=2, is_active=True,
        source_checksum=asset.sha256, text_checksum="e" * 64,
    )
    unapproved = EvidenceSpan.objects.create(
        document_revision=pending, page=spans[0].page, page_number=1,
        original_text="尚未正式发布的新正文", normalized_text="尚未正式发布的新正文",
        content_hash="d" * 64, quality=1,
    )
    result = search_result(asset, spans[0])
    assert len(result["baseline"]["results"]) == 1
    assert result["baseline"]["results"][0]["evidence"]["source"]["document_revision_id"] == str(formal.pk)
    assert search_result(asset, unapproved)["baseline"]["results"] == []


@pytest.mark.parametrize("derived", [False, True])
def test_viewpoint_metadata_and_text_use_formal_snapshot_not_draft_or_index(derived):
    work, edition, asset, document, spans = _source(title="正式作品标题", pages=1)
    person = Person.objects.create(preferred_name="正式作者", authority_status="verified")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    claim = _claim(
        document, spans[0], proposition=spans[0].original_text,
        polarity="positive", fingerprint="formal-viewpoint-claim",
    ) if derived else None
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    formal_slug = edition.public_slug
    work.title = "尚未发布的作品标题"
    work.document_type = "journal_article"
    work.save(update_fields=["title", "document_type", "updated_at"])
    person.preferred_name = "尚未发布的作者"
    person.save(update_fields=["preferred_name", "updated_at"])
    edition.publication_year = 2030
    edition.save(update_fields=["publication_year", "updated_at"])

    result = search_result(asset, spans[0], claim=claim)
    rows = result["shadow"]["results"] if derived else result["baseline"]["results"]
    row = next(row for row in rows if row["source_kind"] == "derived_claim") if derived else rows[0]
    assert row["work"] == {"id": str(work.pk), "title": "正式作品标题", "slug": formal_slug}
    assert row["authors"] == ["正式作者"]
    assert row["publication_year"] == 2024
    assert row["source_type"] == "book"
    assert row["proposition"] == spans[0].original_text
    assert "未确认的索引" not in str(row)
    assert "尚未发布" not in str(row)
    assert result["facets"]["works"][0]["label"] == "正式作品标题"
    assert "尚未发布" not in str(result["facets"])


def test_viewpoint_facets_do_not_expose_pending_canonical_relationships():
    work, edition, asset, document, spans = _source(title="正式筛选项", pages=1)

    def relationships(label):
        person = Person.objects.create(preferred_name=label, authority_status="verified")
        ScholarProfile.objects.create(person=person, slug=f"scholar-{person.pk}", editorial_status="published")
        Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
        node = KnowledgeNode.objects.create(
            node_type="theory_tradition", canonical_name_zh=label,
            slug=f"node-{person.pk}", status="published",
        )
        topic = Topic.objects.create(name=label, slug=f"topic-{person.pk}", editorial_status="published")
        WorkNodeRelation.objects.create(work=work, node=node, status="published")
        WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
        return person, node, topic

    formal_person, formal_node, formal_topic = relationships("已发布关系")
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    relationships("尚未发布的关系")
    result = search_result(asset, spans[0])
    assert [row["id"] for row in result["facets"]["scholars"]] == [str(formal_person.pk)]
    assert [row["id"] for row in result["facets"]["theories"]] == [str(formal_node.pk)]
    assert [row["id"] for row in result["facets"]["topics"]] == [str(formal_topic.pk)]
    assert "尚未发布" not in str(result["facets"])


def stub_external_hits(monkeypatch, asset, span):
    """Use real projection permission/facet gates with bounded fake transport.

    This fixture proves HTTP protocol and publication checks, not model quality.
    Even this deliberately stale index hit has to pass current source hydration.
    """
    edition = asset.edition
    edition.refresh_from_db()
    header = source_header("edition", edition)
    unit = next(row for row in source_units("edition", edition, header) if row["unit_id"] == str(span.pk))
    generation = SemanticIndexVersion.discovery_objects.create(uid=f"legacy-http-{uuid4().hex}", index_family="discovery",
        provider="userProvided", status="active", config_snapshot={"embedding_artifact": "fixture-embed", "reranker_artifact": "fixture-rerank"})
    doc = DiscoveryDocument.objects.create(generation=generation, channel="passages", source_type="edition",
        source_id=edition.pk, source_revision=header["source_revision"], scope_token=header["scope_token"],
        edition=edition, document_revision=span.document_revision, access_status=asset.access_status,
        text=span.original_text, normalized_text=span.original_text, input_hash=fingerprint(span.original_text),
        start_offset=0, end_offset=len(span.original_text), token_count=12, keyword_ready=True, vector_ready=True,
        payload={**header, **unit["metadata"], "unit_hash": fingerprint(span.original_text)})
    monkeypatch.setattr("catalog.services.discovery_sessions._enqueue", lambda *args: None)
    monkeypatch.setattr("catalog.services.discovery_projection.normalize_texts", lambda texts: {"texts": texts})
    monkeypatch.setattr("catalog.services.discovery_projection.embed_texts", lambda *args, **kwargs: {"vectors": [[0.0] * 384]})
    monkeypatch.setattr("catalog.services.discovery_inference.rerank", lambda query, docs, top_n=20, **kwargs:
                        {"results": [{"index": i, "relevance_score": 1.0} for i in range(min(top_n, len(docs)))]})
    monkeypatch.setattr("catalog.services.discovery_projection.meili", lambda *args, **kwargs:
                        {"hits": [{"id": str(doc.pk), "source_revision": doc.source_revision}]})


def completed_legacy_search(api_client, params):
    created = api_client.get("/api/catalog/viewpoint-search/", params)
    assert created.status_code == 202
    assert created.data["compatibility_notice"] and created.data["access_token"]
    session = DiscoverySearchSession.objects.get(pk=created.data["id"])
    execute_session(session.pk, session.generation, session.task_id)
    response = api_client.get(created.data["status_url"], HTTP_X_DISCOVERY_TOKEN=created.data["access_token"])
    assert response.status_code == 200
    assert response.data["status"] in {"completed", "partial"}
    return response


@pytest.mark.parametrize("access", ["registered", "private"])
def test_http_viewpoint_computes_access_from_session_not_query_parameters(
    api_client, reader_user, admin_user, monkeypatch, access,
):
    _work, edition, asset, document, spans = _source(title=f"HTTP 文件权限 {access}", pages=1)
    asset.access_status = access
    asset.save(update_fields=["access_status", "updated_at"])
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    stub_external_hits(monkeypatch, asset, spans[0])
    malicious = api_client.get("/api/catalog/viewpoint-search/", {"q": "贫困导致犯罪", "_allowed_access_statuses": access})
    assert malicious.status_code == 400
    assert DiscoverySearchSession.objects.count() == 0
    params = {"q": "贫困导致犯罪"}
    anonymous = completed_legacy_search(api_client, params)
    assert anonymous.status_code == 200 and anonymous.data["count"] == 0
    api_client.force_authenticate(reader_user)
    reader = completed_legacy_search(api_client, params)
    assert reader.status_code == 200
    assert reader.data["count"] == (1 if access == "registered" else 0)
    api_client.force_authenticate(admin_user)
    staff = completed_legacy_search(api_client, params)
    assert staff.status_code == 200 and staff.data["count"] == 1


@pytest.mark.parametrize("kind", ["topic", "theory"])
def test_http_taxonomy_filter_uses_formal_relationships(api_client, monkeypatch, kind):
    work, edition, asset, document, spans = _source(title=f"HTTP 正式分类 {kind}", pages=1)

    def relate(label):
        if kind == "topic":
            entity = Topic.objects.create(name=label, slug=f"topic-{uuid4().hex}", editorial_status="published")
            WorkTopicRelation.objects.create(work=work, topic=entity, review_status="approved")
        else:
            entity = KnowledgeNode.objects.create(
                node_type="theory_tradition", canonical_name_zh=label,
                slug=f"theory-{uuid4().hex}", status="published",
            )
            WorkNodeRelation.objects.create(work=work, node=entity, status="published")
        return entity

    formal = relate("正式分类")
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    pending = relate("尚未发布的分类")
    stub_external_hits(monkeypatch, asset, spans[0])
    excluded = completed_legacy_search(api_client, {"q": "贫困导致犯罪", kind: str(pending.pk)})
    assert excluded.status_code == 200 and excluded.data["count"] == 0
    included = completed_legacy_search(api_client, {"q": "贫困导致犯罪", kind: str(formal.pk)})
    assert included.status_code == 200 and included.data["count"] == 1


@pytest.mark.parametrize("field", ["work_id", "author", "year_min"])
def test_http_stale_hits_cannot_bypass_formal_metadata_filters(api_client, monkeypatch, field):
    _work, edition, asset, document, spans = _source(title=f"HTTP 正式筛选 {field}", pages=1)
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    person = Person.objects.create(preferred_name="待公开作者关系", authority_status="verified")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    edition.publication_year = 2099
    edition.save(update_fields=["publication_year", "updated_at"])
    value = {"work_id": str(uuid4()), "author": str(person.pk), "year_min": 2030}[field]
    stub_external_hits(monkeypatch, asset, spans[0])
    response = completed_legacy_search(api_client, {"q": "贫困导致犯罪", field: value})
    assert response.status_code == 200 and response.data["count"] == 0


def test_claim_with_mismatched_primary_evidence_is_rejected():
    _work, edition, asset, document, spans = _source(title="正式命题", pages=1)
    activate_catalog_revision(edition, reader_asset=asset, document_revision=document)
    _private_work, _private_edition, private_asset, _private_document, private_spans = _source(title="非正式命题依据", pages=1)
    private_asset.access_status = "private"
    private_asset.save(update_fields=["access_status", "updated_at"])
    with pytest.raises(ValidationError) as rejected:
        _claim(
            document, private_spans[0], proposition="错误关联不能公开",
            polarity="positive", fingerprint="mismatched-primary-evidence",
        )
    assert "primary_evidence" in rejected.value.message_dict


def test_malformed_index_asset_identifier_is_rejected_as_unvalidated():
    assert _matching_evidence_span({"asset_id": "invalid-id", "page_index": 1, "snippet": "贫困导致犯罪"}) is None


def test_malformed_index_claim_identifier_is_rejected_as_unvalidated():
    result = viewpoint_search(
        "贫困导致犯罪",
        retrieval_backend=lambda *args, **kwargs: {"results": []},
        claim_search_backend=lambda *args, **kwargs: {"hits": [{"claim_id": "invalid-claim-id"}]},
    )
    assert result["shadow"]["results"] == []
    assert result["metadata"]["stale_or_invalid_claim_hits_excluded"] == 1
