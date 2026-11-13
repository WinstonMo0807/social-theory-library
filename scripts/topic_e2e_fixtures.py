"""Synthetic PDF68–71 inputs; called only by the disposable runner, never self-run."""
from uuid import NAMESPACE_URL, uuid5
from django.db import transaction


def fixture_id(key):
    return str(uuid5(NAMESPACE_URL, "stl4-topic-20261021:" + key))


IDS = {key: fixture_id(key) for key in ("technology", "society", "algorithm", "empty", "overlap", "question", "debate", "concept",
    "work", "edition", "asset", "bib_work", "bib_edition", "person", "scholar", "withdrawn_person", "withdrawn_scholar",
    "issue", "planned_item", "path", "stage", "path_item")}
SLUG = "stl4-topic-technology"


def seed_topics(actor):
    from timeline_e2e_fixtures import _isolated, _source
    from parallel_reader_e2e_fixtures import IDS as parallel_ids, copy_fixture_pdf
    _isolated()
    from catalog.models import (Asset, Contribution, Edition, EvidenceSpan, KnowledgeNode, KnowledgeNodeTopic, Page, Person,
        PersonTopicRelation, ReadingPath, ReadingPathItem, ReadingPathStage, RecommendationIssue, ScholarProfile, Topic, Work, WorkTopicRelation)
    from catalog.services import shared_curation, editorial_issues
    from catalog.services.public_topics import capture_topic_publication
    from catalog.services.public_reading_paths import capture_reading_path_publication
    from tests.v304_helpers import activate_catalog_revision
    if Topic.objects.filter(pk__in=IDS.values()).exists():
        raise RuntimeError("Topic fixtures already exist; use a fresh isolated runner directory")
    original, excerpt = _source(parallel_ids["left_asset"], 1)
    with transaction.atomic():
        parent = Topic.objects.create(id=IDS["society"], name="TOPIC69 合成社会主题", slug="stl4-topic-society", editorial_status="published")
        topic = Topic.objects.create(id=IDS["technology"], name="TOPIC71 合成技术主题", slug=SLUG, parent=parent,
            description="隔离验收主题导读，不是真实学术资料。", problem_statement="用真实来源验证版本与公开边界。",
            search_aliases=["TOPIC69 已确认别名"], core_questions=["旧导读文本不能冒充规范问题。"],
            timeline=[["1900", "合成时间线", "保留旧主题时间线元组。"]], editorial_status="published")
        Topic.objects.create(id=IDS["algorithm"], name="TOPIC69 合成算法主题", slug="stl4-topic-algorithm", parent=topic, editorial_status="published")
        Topic.objects.create(id=IDS["empty"], name="TOPIC71 空主题", slug="stl4-topic-empty", editorial_status="published")
        Topic.objects.create(id=IDS["overlap"], name="TOPIC69 合成交叉主题", slug="stl4-topic-overlap", search_aliases=["TOPIC69 已确认别名"], editorial_status="published")
        nodes = []
        for key, kind, title in (("question", "research_problem", "TOPIC71 规范研究问题"), ("debate", "debate", "TOPIC71 规范争论"), ("concept", "concept", "TOPIC71 规范概念")):
            node = KnowledgeNode.objects.create(id=IDS[key], node_type=kind, canonical_name_zh=title, slug="stl4-topic-" + key, status="published")
            KnowledgeNodeTopic.objects.create(node=node, topic=topic, status="published", relation_label="隔离验收正式关系")
            nodes.append(node)
        for index in range(13):
            node = KnowledgeNode.objects.create(id=fixture_id(f"question-{index}"), node_type="research_problem", canonical_name_zh=f"TOPIC71 分页问题 {index + 1:02}", slug=f"stl4-topic-question-{index}", status="published", sort_order=index + 1)
            KnowledgeNodeTopic.objects.create(node=node, topic=topic, status="published")
        person = Person.objects.create(id=IDS["person"], preferred_name="TOPIC71 合成学者", authority_status="verified")
        scholar = ScholarProfile.objects.create(id=IDS["scholar"], person=person, slug="stl4-topic-scholar", editorial_status="published")
        hidden_person = Person.objects.create(id=IDS["withdrawn_person"], preferred_name="TOPIC71 撤回学者", authority_status="verified")
        hidden = ScholarProfile.objects.create(id=IDS["withdrawn_scholar"], person=hidden_person, slug="stl4-topic-withdrawn", editorial_status="published")
        PersonTopicRelation.objects.create(person=person, topic=topic, review_status="approved")
        work = Work.objects.create(id=IDS["work"], title="TOPIC71 准确版本原文", document_type="book")
        edition = Edition.objects.create(id=IDS["edition"], work=work, state="published", public_slug="stl4-topic-source", is_primary=True, version_label="准确公开版")
        asset = copy_fixture_pdf(original, edition, IDS["asset"], "synthetic-topic.pdf")
        pages = {row.index: Page.objects.create(asset=asset, index=row.index, text=row.text, printed_label=row.printed_label) for row in original.pages.order_by("index")}
        Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
        WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
        publication = activate_catalog_revision(edition, reader_asset=asset)
        span = EvidenceSpan.objects.create(document_revision=publication.document_revision, page=pages[1], page_number=1,
            start_offset=excerpt.start_offset, end_offset=excerpt.end_offset, original_text=excerpt.original_text,
            normalized_text=excerpt.normalized_text, content_hash=excerpt.content_hash, printed_page_label=excerpt.printed_page_label)
        curation = shared_curation.save_curation("topic", topic.pk, {"edit_version": "0", "items": [{"source_type": "span", "source_id": str(span.pk), "group_title": "主题原文", "reason": "准确隔离PDF出处。"}]}, actor)
        shared_curation.publish_curation("topic", topic.pk, curation["edit_version"], actor)
        bib_work = Work.objects.create(id=IDS["bib_work"], title="TOPIC71 纯书目", document_type="book")
        bib = Edition.objects.create(id=IDS["bib_edition"], work=bib_work, state="published", public_slug="stl4-topic-bibliography", is_primary=True, publication_mode="bibliographic")
        WorkTopicRelation.objects.create(work=bib_work, topic=topic, review_status="approved")
        activate_catalog_revision(bib, fulltext_ready=False)
        path = ReadingPath.objects.create(id=IDS["path"], slug="stl4-topic-reading-path", title="TOPIC71 正式研究路径", status="published")
        path.topics.add(topic)
        stage = ReadingPathStage.objects.create(id=IDS["stage"], reading_path=path, name="准确来源", position=0)
        ReadingPathItem.objects.create(id=IDS["path_item"], reading_path=path, stage=stage, stage_name=stage.name, work=work, edition=edition,
            asset=asset, document_revision=publication.document_revision, material_kind="work", position=0)
        capture_reading_path_publication(path, actor=actor)
        issue = RecommendationIssue.objects.create(id=IDS["issue"], title="TOPIC71 明确策划", slug="stl4-topic-issue", created_by=actor)
        editorial_issues.save_issue(issue.pk, {"edit_version": "0", "title": issue.title, "introduction": "仅供隔离验收。", "public_byline": "合成编辑",
            "items": [{"id": IDS["planned_item"], "kind": "planned", "title": "TOPIC71 明确计划", "authors": "合成作者", "note": "明确列入计划，不代表馆藏全文。"}]}, actor)
        editorial_issues.publish_issue(issue.pk, editorial_issues.edit_version("recommendation_issue", issue.pk), actor)
        topic.curation = {"question_node_ids": [str(nodes[0].pk)], "debate_node_ids": [str(nodes[1].pk)], "concept_node_ids": [str(nodes[2].pk)],
            "foundational_edition_ids": [str(edition.pk)], "disputed_edition_ids": [str(bib.pk)], "related_scholar_ids": [str(scholar.pk), str(hidden.pk)],
            "reading_path_ids": [str(path.pk)], "issue_ids": [str(issue.pk)], "featured_source_id": curation["items"][0]["id"]}
        topic.save(update_fields=["curation", "updated_at"])
        capture_topic_publication(topic, actor=actor)
        hidden.editorial_status = "archived"
        hidden.save(update_fields=["editorial_status", "updated_at"])
    return {**IDS, "slug": SLUG, "source_reference_id": curation["items"][0]["id"]}
