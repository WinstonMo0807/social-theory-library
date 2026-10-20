"""Parallel source/permission contracts; authored for final acceptance, not run here."""
from hashlib import sha256
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Asset, Edition, EvidenceSpan, Page, Passage, Work
from catalog.services import parallel_reading as parallel
from .v304_helpers import activate_catalog_revision


def publish(work=None, *, parent=None, access="public", fulltext=True, primary=True, text="Original source"):
    work = work or Work.objects.create(title=f"Published {uuid4()}", language="fr",
        translation_of=parent, cover="synthetic/parallel.jpg")
    edition = Edition.objects.create(work=work, state="published", is_primary=primary,
        public_slug=f"parallel-{uuid4()}", publication_year=2000)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        validation_status="valid", access_status=access, file=f"synthetic/{uuid4()}.pdf",
        sha256=uuid4().hex * 2, page_count=2)
    page = Page.objects.create(asset=asset, index=1, text=text)
    Page.objects.create(asset=asset, index=2, text="")
    activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext)
    return work, edition, asset, page


def span_for(edition, page, text=None, start=0, order=0):
    text = page.text if text is None else text
    passage = Passage.objects.create(page=page, order=order, text=text, start_offset=start, end_offset=start + len(text))
    return EvidenceSpan.objects.create(document_revision=edition.active_catalog_revision.document_revision,
        page=page, page_number=page.index, passage=passage, start_offset=start, end_offset=start + len(text),
        original_text=text, content_hash=sha256(text.encode()).hexdigest())


def ref(edition, asset, page, span=None):
    return {"asset_id": str(asset.pk), "document_revision_id": str(edition.active_catalog_revision.document_revision_id),
            "pdf_page": page.index, "content_hash": span.content_hash if span else sha256(page.text.encode()).hexdigest(),
            **({"evidence_span_id": str(span.pk)} if span else {})}


def page_url(asset, edition, **params):
    values = {"asset_id": str(asset.pk), "document_revision_id": str(edition.active_catalog_revision.document_revision_id),
              "page": 1, **params}
    from urllib.parse import urlencode
    return "/api/catalog/parallel/segments/?" + urlencode(values)


@pytest.mark.django_db
def test_versions_use_published_translation_chain_and_secondary_identity(api_client):
    original, primary, _, _ = publish()
    _, secondary, source, _ = publish(original, primary=False)
    translation, _, translated, _ = publish(parent=original)
    _, _, indirect, _ = publish(parent=translation)
    draft_link, _, excluded, _ = publish()
    draft_link.translation_of = original
    draft_link.save(update_fields=["translation_of"])
    Edition.objects.filter(pk=primary.pk).update(state="withdrawn")
    result = api_client.get("/api/catalog/parallel/versions/", {"asset_id": source.pk})
    assert result.status_code == 200 and result["Cache-Control"] == "private, no-store"
    ids = {row["asset_id"] for row in result.data["versions"]}
    assert {str(source.pk), str(translated.pk), str(indirect.pk)} <= ids
    assert str(excluded.pk) not in ids
    assert result.data["versions"][0]["edition_id"] == str(secondary.pk)
    assert f"edition_id={secondary.pk}" in result.data["versions"][0]["cover_url"]
    assert parallel.validate_pair(AnonymousUser(), source.pk, indirect.pk)[1].pk == indirect.edition_id


@pytest.mark.django_db
def test_versions_distinguish_real_metadata_and_current_authorization(api_client, admin_user):
    work, source_edition, source, _ = publish(fulltext=False)
    _, hidden, restricted, _ = publish(work, primary=False, access="restricted")
    metadata = Edition.objects.create(work=work, state="published", is_primary=False, public_slug=f"metadata-{uuid4()}")
    activate_catalog_revision(metadata, fulltext_ready=False)
    response = api_client.get("/api/catalog/parallel/versions/", {"asset_id": source.pk})
    assert response.status_code == 200
    items = {row["edition_id"]: row for row in response.data["versions"]}
    assert items[str(source_edition.pk)]["state"] == "metadata_only"
    assert items[str(source_edition.pk)]["asset_id"] == str(source.pk)
    assert items[str(metadata.pk)]["asset_id"] is None
    assert items[str(hidden.pk)]["asset_id"] is None
    scan = api_client.get("/api/catalog/parallel/segments/", {"asset_id": source.pk, "page": 1})
    assert scan.status_code == 200 and scan.data["state"] == "text_unavailable" and scan.data["segments"] == []
    api_client.force_authenticate(admin_user)
    authorized = api_client.get("/api/catalog/parallel/versions/", {"asset_id": source.pk})
    item = next(row for row in authorized.data["versions"] if row["edition_id"] == str(hidden.pk))
    assert item["asset_id"] == str(restricted.pk) and item["state"] == "available"


@pytest.mark.django_db
def test_segment_pagination_and_focus_retain_exact_reference(api_client):
    texts = [f"Paragraph {index:02d}" for index in range(23)]
    _, edition, asset, page = publish(text="\n".join(texts))
    spans, start = [], 0
    for index, text in enumerate(texts):
        spans.append(span_for(edition, page, text, start, index))
        start += len(text) + 1
    response = api_client.get(page_url(asset, edition))
    assert response.status_code == 200 and response.data["state"] == "ready"
    assert len(response.data["segments"]) == 20
    assert response.data["next_offset"] == 20 and response.data["next_page"] == 2
    focused = api_client.get(page_url(asset, edition, focus=str(spans[21].pk)))
    assert focused.status_code == 200 and focused.data["offset"] == 20
    chosen = focused.data["segments"][1]
    assert chosen["id"] == str(spans[21].pk) and chosen["text"] == texts[21]
    assert chosen["reference"]["source_status"] == "available"
    assert chosen["reference"]["document_revision_id"] == str(edition.active_catalog_revision.document_revision_id)
    assert f"edition_id={edition.pk}" in chosen["reference"]["cover_url"]
    assert api_client.get(page_url(asset, edition, document_revision_id=str(uuid4()))).status_code == 409
    assert api_client.get(page_url(asset, edition, focus=str(uuid4()))).status_code == 404


@pytest.mark.django_db
def test_page_range_focus_inside_passage_uses_its_segment_window(api_client):
    texts = [f"Actual paragraph {index:02d} with a selectable middle" for index in range(23)]
    _, edition, asset, page = publish(text="\n\n".join(texts))
    passages, start = [], 0
    for order, text in enumerate(texts):
        passages.append(Passage.objects.create(page=page, order=order, text=text,
            start_offset=start, end_offset=start + len(text)))
        start += len(text) + 2
    selected = passages[21]
    focus = f"{asset.pk}:1:range:{selected.start_offset + 8}:{selected.end_offset - 4}"
    response = api_client.get(page_url(asset, edition, focus=focus))
    assert response.status_code == 200 and response.data["offset"] == 20
    assert response.data["segments"][1]["text"] == selected.text
    assert response.data["segments"][1]["reference"]["selection_start"] == selected.start_offset
    gap = f"{asset.pk}:1:range:{passages[20].end_offset}:{selected.start_offset + 1}"
    assert api_client.get(page_url(asset, edition, focus=gap)).status_code == 404
    Passage.objects.filter(pk=selected.pk).update(text="Changed text no longer at this range")
    assert api_client.get(page_url(asset, edition, focus=focus)).status_code == 409


@pytest.mark.django_db
def test_unstructured_and_empty_pages_never_invent_paragraphs(api_client):
    _, edition, asset, _ = publish(text="Unstructured true page text")
    response = api_client.get(page_url(asset, edition))
    assert response.data["state"] == "unstructured"
    assert response.data["segments"][0]["text"] == "Unstructured true page text"
    assert "页内文字" in response.data["segments"][0]["label"]
    assert api_client.get(page_url(asset, edition, page=2)).data["state"] == "empty"
    assert api_client.get(page_url(asset, edition, page=3)).status_code == 404


@pytest.mark.django_db
def test_private_read_access_never_becomes_public_calibration_permission(admin_user):
    work, left, left_asset, left_page = publish(access="restricted")
    _, right, right_asset, _ = publish(work, primary=False)
    left_ref = ref(left, left_asset, left_page)
    assert parallel.resolve_parallel_reference(left_ref, admin_user)["source_status"] == "available"
    parallel.validate_pair(admin_user, left_asset.pk, right_asset.pk)
    with pytest.raises((ValidationError, NotFound)):
        parallel.resolve_parallel_reference(left_ref, admin_user, public=True)
    with pytest.raises(NotFound):
        parallel.validate_pair(admin_user, left_asset.pk, right_asset.pk, public=True)
    _, _, unrelated, _ = publish()
    with pytest.raises(ValidationError):
        parallel.validate_pair(admin_user, right_asset.pk, unrelated.pk)
    with pytest.raises(ValidationError):
        parallel.resolve_parallel_reference({**left_ref, "content_hash": "0" * 64}, admin_user)


@pytest.mark.django_db
def test_candidates_bound_exact_file_recheck_text_and_never_confirm(api_client, monkeypatch):
    work, left, left_asset, left_page = publish(text="Source claim")
    _, right, right_asset, right_page = publish(work, primary=False, text="Target claim")
    span = span_for(right, right_page)
    calls = []

    def retrieve(query, channel, filters, access, **kwargs):
        calls.append((query, channel, filters, access, kwargs))
        valid = {"asset_id": str(right_asset.pk), "document_revision_id": str(right.active_catalog_revision.document_revision_id),
            "pdf_page": 1, "evidence_span_id": str(span.pk), "unit_start_offset": 0,
            "unit_end_offset": len(span.original_text), "text": span.original_text}
        return {"rows": [{**valid, "asset_id": str(left_asset.pk)}, {**valid, "text": "invented"}, valid, valid],
                "warnings": [{"code": "dense_unavailable", "message": "向量检索暂不可用。"}]}

    monkeypatch.setattr(parallel, "retrieve_discovery_channel", retrieve)
    response = api_client.post("/api/catalog/parallel/candidates/", {"left_reference": {**ref(left, left_asset, left_page), "evidence_span_id": None},
        "target_asset_id": str(right_asset.pk), "target_document_revision_id": str(right.active_catalog_revision.document_revision_id)}, format="json")
    assert response.status_code == 200 and response.data["state"] == "partial"
    assert calls[0][2] == {"_asset_id": str(right_asset.pk)} and calls[0][4]["limit"] == 24
    assert len(response.data["candidates"]) == 1
    assert response.data["candidates"][0]["status"] == "pending"
    assert response.data["candidates"][0]["text"] == "Target claim"
    assert response.data["allows_no_correspondence"] is True


@pytest.mark.django_db
def test_candidates_return_at_most_six_and_old_revision_never_retrieves(api_client, monkeypatch):
    work, left, left_asset, left_page = publish()
    texts = [f"Target {index}" for index in range(7)]
    _, right, right_asset, right_page = publish(work, primary=False, text="\n".join(texts))
    rows, start = [], 0
    for index, text in enumerate(texts):
        span = span_for(right, right_page, text, start, index)
        rows.append({"asset_id": str(right_asset.pk), "document_revision_id": str(right.active_catalog_revision.document_revision_id),
            "pdf_page": 1, "evidence_span_id": str(span.pk), "unit_start_offset": 0, "unit_end_offset": len(text), "text": text})
        start += len(text) + 1
    calls = []

    def retrieve(*args, **kwargs):
        calls.append(args)
        return {"rows": rows, "warnings": []}

    monkeypatch.setattr(parallel, "retrieve_discovery_channel", retrieve)
    body = {"left_reference": ref(left, left_asset, left_page), "target_asset_id": str(right_asset.pk),
            "target_document_revision_id": str(uuid4())}
    assert api_client.post("/api/catalog/parallel/candidates/", body, format="json").status_code == 409
    assert calls == []
    body["target_document_revision_id"] = str(right.active_catalog_revision.document_revision_id)
    response = api_client.post("/api/catalog/parallel/candidates/", body, format="json")
    assert response.status_code == 200 and response.data["state"] == "ready"
    assert len(response.data["candidates"]) == 6


@pytest.mark.django_db
@pytest.mark.parametrize("result", ["unavailable", "empty", "withdrawn_during_retrieval"])
def test_candidate_failures_do_not_manufacture_alignment(api_client, monkeypatch, result):
    work, left, left_asset, left_page = publish()
    _, right, right_asset, _ = publish(work, primary=False)

    def retrieve(*args, **kwargs):
        if result == "unavailable":
            raise parallel.DiscoveryIndexError("index_unavailable")
        if result == "withdrawn_during_retrieval":
            Edition.objects.filter(pk=right.pk).update(state="withdrawn")
        return {"rows": [], "warnings": []}

    monkeypatch.setattr(parallel, "retrieve_discovery_channel", retrieve)
    response = api_client.post("/api/catalog/parallel/candidates/", {"left_reference": ref(left, left_asset, left_page),
        "target_asset_id": str(right_asset.pk), "target_document_revision_id": str(right.active_catalog_revision.document_revision_id)}, format="json")
    if result == "withdrawn_during_retrieval":
        assert response.status_code == 404
    else:
        assert response.status_code == 200 and response.data["state"] == result
        assert response.data["candidates"] == []


@pytest.mark.django_db
def test_discovery_cover_uses_its_selected_edition():
    from catalog.services.discovery_sources import edition_metadata_header
    _, edition, _, _ = publish()
    assert f"edition_id={edition.pk}" in edition_metadata_header(edition)["bibliography"]["cover_url"]
