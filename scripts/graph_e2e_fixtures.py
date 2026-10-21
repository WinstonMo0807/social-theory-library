"""Disposable PDF52/53/55 graph fixtures over the extracted timeline sources.

Creates explicitly synthetic authority/relationship and bibliographic records.
Never edits any existing work, edition, file, publication snapshot or source text.
"""
from django.db import transaction


def fixture_id(number):
    return f"52000000-0000-4000-8000-{number:012d}"


IDS = {
    "center": fixture_id(101), "second": fixture_id(102), "third": fixture_id(103), "fourth": fixture_id(104),
    "hidden": fixture_id(105), "isolated": fixture_id(106), "subdiscipline": fixture_id(151),
    "edge_first": fixture_id(201), "edge_second": fixture_id(202), "edge_third": fixture_id(203),
    "edge_hidden": fixture_id(204), "candidate": fixture_id(205), "candidate_hidden": fixture_id(206),
    "scholar_edge": fixture_id(301), "evidence": fixture_id(401), "case_mismatch_evidence": fixture_id(402),
    "work": fixture_id(501),
}


def seed_graph(actor):
    from timeline_e2e_fixtures import IDS as timeline_ids, _isolated, _source
    _isolated()
    from catalog.models import (
        Contribution, Discipline, Edition, EditorialRevision, EvidenceSnippet, KnowledgeNode,
        KnowledgeNodeSubdiscipline, KnowledgeNodeTopic, KnowledgeRelation, PersonNodeRelation,
        PersonSubdisciplineRelation, PersonTopicRelation, ScholarProfile, ScholarRelation,
        Subdiscipline, Topic, TopicSubdisciplineRelation, Work, WorkNodeRelation,
        WorkSubdisciplineRelation, WorkTopicRelation,
    )
    from parallel_reader_e2e_fixtures import IDS as parallel_ids
    from tests.v304_helpers import activate_catalog_revision

    models = (Edition, EditorialRevision, EvidenceSnippet, KnowledgeNode, KnowledgeRelation,
              ScholarRelation, Subdiscipline, Work)
    identifiers = [fixture_id(number) for number in range(1, 614)]
    if any(model.objects.filter(pk__in=identifiers).exists() for model in models):
        raise RuntimeError("Graph fixture identifiers already exist; use a fresh disposable E2E directory")
    asset, span = _source(parallel_ids["left_asset"], 1)
    if "PARALLEL" not in span.original_text:
        raise RuntimeError("Graph sources require the actual extractor-created synthetic PDF text")
    discipline = Discipline.objects.get(pk=timeline_ids["discipline"], editorial_status="published")
    topic = Topic.objects.get(pk=timeline_ids["topic_a"], editorial_status="published")
    first = ScholarProfile.objects.select_related("person").get(pk=timeline_ids["scholar_a"], editorial_status="published")
    second = ScholarProfile.objects.select_related("person").get(pk=timeline_ids["scholar_b"], editorial_status="published")
    with transaction.atomic():
        nodes = {}
        for key, label in (("center", "中心概念"), ("second", "第二层概念"), ("third", "第三层概念"),
                           ("fourth", "第四节点"), ("hidden", "隐藏名称不得出现"), ("isolated", "孤立概念")):
            nodes[key] = KnowledgeNode.objects.create(id=IDS[key], node_type="concept",
                canonical_name_zh=f"GRAPH52 {label}", slug=f"e2e-graph-{key}",
                summary="仅用于隔离验收的合成图谱说明，不代表学术关系或历史事实。",
                status="draft" if key == "hidden" else "published", primary_discipline=discipline)
        edges = {}
        for key, left, right, relation, status in (
            ("edge_first", "center", "second", "influenced_by", "published"),
            ("edge_second", "second", "third", "extends", "published"),
            ("edge_third", "third", "fourth", "criticizes", "published"),
            ("edge_hidden", "center", "hidden", "extends", "published"),
            ("candidate", "center", "second", "criticizes", "pending"),
            ("candidate_hidden", "center", "hidden", "criticizes", "pending"),
        ):
            edges[key] = KnowledgeRelation.objects.create(id=IDS[key], source_node=nodes[left], target_node=nodes[right],
                relation_type=relation, direction="directed", status=status,
                description=f"GRAPH52 {key} 合成关系说明，仅验证真实记录的显示与权限。",
                evidence_source="隔离 PDF 仅验证准确出处，不用于证明合成历史关系。", reviewed_by=actor if status == "published" else None)
        branch = Subdiscipline.objects.create(id=IDS["subdiscipline"], name="GRAPH52 独立子学科",
            slug="e2e-graph-subdiscipline", discipline=discipline, editorial_status="published",
            description="独立子学科身份，不按名称合并知识节点。")
        PersonNodeRelation.objects.create(person=first.person, node=nodes["center"], status="published", relation_label="合成学者关联")
        KnowledgeNodeTopic.objects.create(node=nodes["center"], topic=topic, status="published", relation_label="合成主题关联")
        KnowledgeNodeSubdiscipline.objects.create(node=nodes["center"], subdiscipline=branch, status="published")
        PersonTopicRelation.objects.create(person=first.person, topic=topic, review_status="approved")
        PersonSubdisciplineRelation.objects.create(person=first.person, subdiscipline=branch, review_status="approved")
        TopicSubdisciplineRelation.objects.create(topic=topic, subdiscipline=branch, review_status="approved")
        relation = ScholarRelation.objects.create(id=IDS["scholar_edge"], source_scholar=first,
            target_scholar=second, relation_type="influence", direction="directed", status="published")
        revision = EditorialRevision.objects.create(target_type="scholar_relation", target_id=relation.pk,
            revision=1, status="published", idempotency_key="graph52-fixture-scholar-published", created_by=actor,
            materialized_preview={"source_scholar": str(first.pk), "target_scholar": str(second.pk),
                "relation_type": "influence", "direction": "directed", "summary": "GRAPH52 正式学者关系说明",
                "source": "合成关系的明确书目说明，没有原文链接。"})
        relation.active_revision = revision
        relation.save(update_fields=["active_revision"])
        EditorialRevision.objects.create(target_type="scholar_relation", target_id=relation.pk,
            revision=2, status="draft", idempotency_key="graph52-fixture-scholar-draft", created_by=actor,
            materialized_preview={**revision.materialized_preview, "summary": "GRAPH52 草稿正文不得公开"})
        for key, edge, quote in (("evidence", edges["edge_first"], span.original_text),
                                  ("case_mismatch_evidence", edges["edge_second"], span.original_text.lower())):
            EvidenceSnippet.objects.create(id=IDS[key], work=asset.edition.work, file=asset,
                knowledge_relation=edge, page_number=span.page_number, page_end=span.page_number,
                quote=quote, printed_page_label=span.printed_page_label, review_status="approved", reviewed_by=actor)
        work = Work.objects.create(id=IDS["work"], title="GRAPH52 合成图谱书目", document_type="book")
        WorkNodeRelation.objects.create(work=work, node=nodes["center"], status="published", role="general_mention")
        WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
        WorkSubdisciplineRelation.objects.create(work=work, subdiscipline=branch, review_status="approved")
        for index in range(13):
            edition = Edition.objects.create(id=fixture_id(601 + index), work=work, state="published",
                is_primary=index == 0, publication_mode="bibliographic", public_slug=f"e2e-graph-book-{index + 1}",
                version_label=f"明确合成书目版本 {index + 1}")
            Contribution.objects.create(edition=edition, person=first.person, role="author", approved=True)
            activate_catalog_revision(edition, fulltext_ready=False)
    return {**IDS, "scholar": str(first.pk), "topic": str(topic.pk), "source_asset": str(asset.pk),
            "source_edition": str(asset.edition_id), "source_revision": str(span.document_revision_id)}
