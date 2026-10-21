"""Synthetic PDF56/57 events over already extracted, published test PDFs.

Only the disposable E2E runner may call seed_timeline(actor). The event dates,
people and classifications are explicitly synthetic. Quoted passages come from
the actual parallel fixture extraction; no existing Work, Edition, Asset,
DocumentRevision or publication snapshot is modified. This seed is not executed
during development.
"""
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone


def fixture_id(number):
    return f"56000000-0000-4000-8000-{number:012d}"


IDS = {
    "discipline": fixture_id(1), "empty_discipline": fixture_id(2),
    "topic_a": fixture_id(11), "topic_b": fixture_id(12), "hidden_topic": fixture_id(13),
    "node_a": fixture_id(21), "node_b": fixture_id(22),
    "node_both": fixture_id(23), "hidden_node": fixture_id(24),
    "person_a": fixture_id(31), "person_b": fixture_id(32), "hidden_person": fixture_id(33),
    "scholar_a": fixture_id(41), "scholar_b": fixture_id(42), "hidden_scholar": fixture_id(43),
    "legacy_theory": fixture_id(51),
    "source_left": fixture_id(61), "source_right": fixture_id(62),
    "hidden_edition": fixture_id(71),
    "publication": fixture_id(101), "translation": fixture_id(102),
    "concept": fixture_id(103), "range": fixture_id(104),
    "approximate": fixture_id(105), "undated": fixture_id(106),
    "draft": fixture_id(107), "legacy": fixture_id(108),
    "hidden_targets": fixture_id(109), "scan_source": fixture_id(110),
    "end_only": fixture_id(111),
    "page_first": fixture_id(200), "page_last": fixture_id(225),
}


def _isolated():
    database = settings.DATABASES["default"]
    path = Path(database["NAME"]).resolve()
    if (database["ENGINE"] != "django.db.backends.sqlite3"
            or not path.parent.name.startswith("stl-v305-e2e-")
            or path.name != "local_fixture.sqlite3"
            or Path(settings.MEDIA_ROOT).resolve() != path.parent / "media"):
        raise RuntimeError("Timeline fixtures require the disposable E2E SQLite database and its own media directory")


def _source(asset_id, page_number, span_offset=0):
    from catalog.models import Asset, EvidenceSpan
    from catalog.services.publication_eligibility import public_editions

    asset = Asset.objects.select_related("edition__active_catalog_revision__document_revision").get(pk=asset_id)
    revision = asset.edition.active_catalog_revision
    if (asset.kind != "normalized" or asset.status != "ready" or asset.validation_status != "valid"
            or asset.access_status != "public" or not asset.file
            or not public_editions(require_fulltext=True).filter(pk=asset.edition_id).exists()
            or revision.reader_asset_id != asset.pk
            or revision.document_revision.asset_id != asset.pk):
        raise RuntimeError("Timeline sources require the real, active and publicly readable parallel PDF extraction")
    span = EvidenceSpan.objects.select_related("page", "passage").filter(
        document_revision_id=revision.document_revision_id, page__asset=asset,
        page_number=page_number, page__index=page_number, is_stale=False,
    ).order_by("start_offset", "pk")[span_offset:span_offset + 1].first()
    if (span is None or not span.original_text or span.passage is None
            or span.page.text[span.start_offset:span.end_offset] != span.original_text
            or span.content_hash != sha256((span.passage.normalized_text or span.passage.text).encode()).hexdigest()):
        raise RuntimeError("Timeline quotation requires an exact extractor-created paragraph and revision identity")
    return asset, span


def seed_timeline(actor):
    _isolated()
    from catalog.models import (
        Asset, Discipline, Edition, EvidenceSnippet, KnowledgeNode, KnowledgeNodeTopic,
        Person, ScholarProfile, TheorySchool, TheoryTimelineEvent, TimelineEventRelation, Topic,
    )
    from parallel_reader_e2e_fixtures import IDS as parallel_ids

    identifiers = [fixture_id(number) for number in range(1, 226)]
    models = (Discipline, Edition, EvidenceSnippet, KnowledgeNode, Person, ScholarProfile,
              TheorySchool, TheoryTimelineEvent, Topic)
    if any(model.objects.filter(pk__in=identifiers).exists() for model in models):
        raise RuntimeError("Timeline fixture identifiers already exist; use a fresh disposable E2E directory")

    # Validate dependencies before any synthetic row is written.
    left, left_span = _source(parallel_ids["left_asset"], 1)
    right, right_span = _source(parallel_ids["right_asset"], 2, 2)
    scan = Asset.objects.select_related("edition__active_catalog_revision").get(pk=parallel_ids["scan_asset"])
    if (scan.edition.is_primary or scan.edition.work_id != left.edition.work_id
            or scan.edition.active_catalog_revision.fulltext_ready
            or any(page.text.strip() for page in scan.pages.all())):
        raise RuntimeError("Timeline secondary-edition fixture must remain the real image-only parallel scan")
    now = timezone.now()
    with transaction.atomic():
        # A new synthetic draft may reference the existing work, but none of
        # that work's published editions, sources or snapshots is overwritten.
        hidden_edition = Edition.objects.create(id=IDS["hidden_edition"], work=left.edition.work,
            is_primary=False, state="draft", public_slug="e2e-timeline-hidden-edition",
            version_label="TL56未公开版本不得出现")
        discipline = Discipline.objects.create(id=IDS["discipline"], name="TL56时间线学科",
            code="tl56", slug="e2e-timeline-discipline", editorial_status="published",
            description="仅用于隔离时间线验收的合成学科。")
        Discipline.objects.create(id=IDS["empty_discipline"], name="TL56空学科",
            code="tl56-empty", slug="e2e-timeline-empty", editorial_status="published")
        topics, nodes, scholars = {}, {}, {}
        for key, suffix, status in (("a", "甲", "published"), ("b", "乙", "published"), ("hidden", "未公开", "draft")):
            topic_key = f"topic_{key}" if key != "hidden" else "hidden_topic"
            topics[key] = Topic.objects.create(id=IDS[topic_key], name=f"TL56主题{suffix}",
                slug=f"e2e-timeline-topic-{key}", description="合成主题，只用于筛选验收。", editorial_status=status)
        for key, suffix, status in (("a", "甲", "published"), ("b", "乙", "published"),
                                    ("both", "交叉", "published"), ("hidden", "未公开", "draft")):
            node_key = f"node_{key}" if key != "hidden" else "hidden_node"
            nodes[key] = KnowledgeNode.objects.create(id=IDS[node_key], node_type="concept",
                canonical_name_zh=f"TL56概念{suffix}", slug=f"e2e-timeline-node-{key}",
                summary="合成时间线概念，不代表真实学术结论。", primary_discipline=discipline, status=status)
            for topic in ([topics["a"], topics["b"]] if key == "both" else [topics[key]]):
                KnowledgeNodeTopic.objects.create(node=nodes[key], topic=topic, status="published",
                    relation_label="隔离验收关联", source="isolated-timeline-fixture", reviewed_by=actor, reviewed_at=now)
        for key, suffix, status in (("a", "甲", "published"), ("b", "乙", "published"), ("hidden", "未公开", "draft")):
            person_key = f"person_{key}" if key != "hidden" else "hidden_person"
            scholar_key = f"scholar_{key}" if key != "hidden" else "hidden_scholar"
            person = Person.objects.create(id=IDS[person_key], preferred_name=f"TL56作者{suffix}",
                original_name=f"Synthetic TL56 author {key}",
                authority_status="verified" if status == "published" else "draft")
            scholars[key] = ScholarProfile.objects.create(id=IDS[scholar_key], person=person,
                slug=f"e2e-timeline-scholar-{key}", editorial_status=status,
                short_description="只用于隔离测试的合成人物，未改写测试 PDF 的真实元数据。")
        legacy = TheorySchool.objects.create(id=IDS["legacy_theory"], name="TL56历史流派",
            slug="e2e-timeline-legacy", editorial_status="published",
            description="未映射旧条目，保留真实历史身份的合成兼容案例。")
        snippets = {}
        for key, asset, span, node in (("left", left, left_span, nodes["a"]), ("right", right, right_span, nodes["b"])):
            snippets[key] = EvidenceSnippet.objects.create(id=IDS[f"source_{key}"], work=asset.edition.work,
                file=asset, node=node, page_number=span.page_number, page_end=span.page_number,
                quote=span.original_text, extraction_method="text_layer", review_status="approved", reviewed_by=actor)

        def event(key, title, year, *, end=None, precision="year", kind="publication",
                  author="a", node="a", edition=None, source=None, approved=True, **extra):
            values = dict(id=IDS[key], title=f"TL56CASE {title}", description="明确标注的合成时间线事件，不是历史事实。",
                start_year=year, end_year=end, date_precision=precision, event_type=kind,
                discipline=discipline, scholar=scholars[author] if author else None,
                subject_edition=edition, work=edition.work if edition else None,
                review_status="approved" if approved else "suggested",
                reviewed_by=actor if approved else None, reviewed_at=now if approved else None,
                display_order=int(IDS[key][-3:]), **extra)
            if source:
                asset, span = (left, left_span) if source == "left" else (right, right_span)
                values.update(evidence_asset=asset, evidence_page=span.page_number,
                    evidence_printed_label=span.printed_page_label, evidence_text=span.original_text,
                    source="真实隔离 PDF 提取段落，仅核对来源身份，不作为上述合成历史断言的证据。")
            row = TheoryTimelineEvent.objects.create(**values)
            if node:
                TimelineEventRelation.objects.create(event=row, node=nodes[node], relation_type="subject")
            if author:
                # The direct and normalized scholar target deliberately overlap;
                # multi-select matching must not duplicate the event.
                TimelineEventRelation.objects.create(event=row, scholar=scholars[author], relation_type="subject")
            if source:
                TimelineEventRelation.objects.create(event=row, evidence=snippets[source], relation_type="evidence")
            return row

        event("publication", "合成原版发表", 1867, edition=left.edition, source="right")
        event("translation", "合成译本发表", 1867, kind="translation",
              author="b", node="b", edition=right.edition, source="left")
        concept = event("concept", "合成概念使用", 1867, kind="concept_proposed",
                        node="both", edition=scan.edition, source="right")
        TimelineEventRelation.objects.create(event=concept, scholar=scholars["b"], relation_type="context")
        event("range", "合成时间范围", 1908, end=1912, precision="range", kind="concept_proposed",
              author="b", date_label="约1910年（1908—1912）", source="right")
        event("approximate", "合成约年", 1936, precision="approximate", kind="institution",
              node="b", date_label="约1936年")
        event("undated", "合成年代未定", None, precision="unknown", kind="development",
              date_label="年代待考")
        event("draft", "未公开事件不得出现", 1867, approved=False)
        event("legacy", "合成历史条目事件", 1888, kind="school_formation",
              author=None, node=None, theory_school=legacy, source="left")
        event("hidden_targets", "公开事件隐藏关联", 1950, kind="scholar",
              author="hidden", node="hidden", edition=hidden_edition)
        event("scan_source", "扫描来源尚无文字", 1960, edition=left.edition,
              evidence_asset=scan, evidence_page=1, source=None)
        event("end_only", "仅记录终年", None, end=1924, precision="unknown",
              kind="theoretical_turn", date_label="仅知1924年")
        for index in range(26):
            row = TheoryTimelineEvent.objects.create(id=fixture_id(200 + index),
                title=f"TL56PAGE 分页事件{index + 1:02d}", description="只用于分页与全范围年份聚合的合成事件。",
                start_year=1950 + index, date_precision="year", event_type="publication",
                discipline=discipline, scholar=scholars["a" if index % 2 == 0 else "b"],
                review_status="approved", reviewed_by=actor, reviewed_at=now, display_order=index)
            TimelineEventRelation.objects.create(event=row, node=nodes["a" if index % 2 == 0 else "b"],
                                                relation_type="subject")
    return {**IDS, "sources": {
        "left": {"asset_id": str(left.pk), "edition_id": str(left.edition_id), "span_id": str(left_span.pk),
                 "document_revision_id": str(left_span.document_revision_id), "page": left_span.page_number},
        "right": {"asset_id": str(right.pk), "edition_id": str(right.edition_id), "span_id": str(right_span.pk),
                  "document_revision_id": str(right_span.document_revision_id), "page": right_span.page_number},
        "scan": {"asset_id": str(scan.pk), "edition_id": str(scan.edition_id)},
    }}
