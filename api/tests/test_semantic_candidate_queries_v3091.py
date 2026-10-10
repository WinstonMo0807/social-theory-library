from hashlib import sha256

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import Edition, Page, Passage, PublicationState, SemanticChunk
from catalog.services.publication_eligibility import active_catalog_snapshot
from catalog.services.semantic_search import _keyword_candidates, _passage_keyword_candidates
from .test_opinion_search_v2 import _chunk


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["chunk", "passage"])
def test_candidate_snapshot_queries_do_not_grow_with_paragraphs(kind, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    seed = _chunk("社会行动的公开题名", "社会行动需要理解制度。", order=1)
    edition = seed.asset.edition
    factory = _keyword_candidates if kind == "chunk" else _passage_keyword_candidates
    if kind == "passage":
        page = Page.objects.create(asset=seed.asset, index=1, text_source="embedded")
        Passage.objects.create(page=page, order=0, text=seed.original_text, normalized_text=seed.normalized_text)
    with CaptureQueriesContext(connection) as first_queries:
        first = factory("社会", ["社会"], {}, limit=100)
    assert len(first) == 1

    if kind == "chunk":
        SemanticChunk.objects.bulk_create([
            SemanticChunk(
                asset=seed.asset, work=seed.work, order=index, page_start=1, page_end=1,
                original_text=seed.original_text, normalized_text=seed.normalized_text,
                language="zh-CN", document_type=seed.document_type,
                parser_version="test", chunk_version=seed.chunk_version,
                document_id=sha256(f"paragraph-{index}".encode()).hexdigest(),
                content_hash=seed.content_hash, index_status="ready",
            ) for index in range(1, 32)
        ])
    else:
        Passage.objects.bulk_create([
            Passage(page=page, order=index, text=seed.original_text, normalized_text=seed.normalized_text)
            for index in range(1, 32)
        ])
    with CaptureQueriesContext(connection) as many_queries:
        many = factory("社会", ["社会"], {}, limit=100)
    assert len(many) == 32
    assert len(many_queries) <= len(first_queries) + 1, (
        f"{kind}: one paragraph={len(first_queries)}, 32 paragraphs={len(many_queries)}"
    )

    seed.work.title = "尚未公开的新题名"
    seed.work.save(update_fields=["title"])
    fresh = factory("社会", ["社会"], {}, limit=100)
    assert active_catalog_snapshot(fresh[0][0].asset.edition, require_fulltext=True)["work"]["title"] == "社会行动的公开题名"
    Edition.objects.filter(pk=edition.pk).update(state=PublicationState.DRAFT)
    assert factory("社会", ["社会"], {}, limit=100) == []
