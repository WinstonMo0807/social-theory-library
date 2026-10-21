"""Synthetic PDF58–60 inputs for the existing isolated runner. Never self-run."""
from django.db import transaction


def fixture_id(number):
    return f"58000000-0000-4000-8000-{number:012d}"


IDS = {"path": fixture_id(1), "stage_one": fixture_id(11), "stage_two": fixture_id(12),
       "chapter_one": fixture_id(21), "chapter_two": fixture_id(22), "node_item": fixture_id(23),
       "no_fulltext_item": fixture_id(24), "withdrawn_item": fixture_id(25),
       "node": fixture_id(31), "work": fixture_id(41), "edition": fixture_id(42), "topic": fixture_id(51),
       "debate": fixture_id(61), "hidden_path": fixture_id(71)}


def seed_reading_paths(actor):
    from timeline_e2e_fixtures import _isolated, _source
    from parallel_reader_e2e_fixtures import IDS as parallel_ids
    _isolated()
    from catalog.models import Edition, EditorialRevision, KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage, Topic, Work
    from catalog.services.public_reading_paths import capture_reading_path_publication
    from catalog.services.editorial_drafts import save_object_editorial_patch
    from tests.v304_helpers import activate_catalog_revision
    if any(model.objects.filter(pk__in=IDS.values()).exists() for model in (Edition, KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage, Topic, Work)):
        raise RuntimeError("Reading-path fixtures already exist; use a fresh isolated runner directory")
    asset, span = _source(parallel_ids["left_asset"], 1)
    if not span.document_revision_id or "PARALLEL" not in span.original_text:
        raise RuntimeError("Reading paths require the actual extracted synthetic PDF revision")
    with transaction.atomic():
        topic = Topic.objects.create(id=IDS["topic"], name="PATH58 合成学习主题", slug="e2e-path-topic", editorial_status="published")
        node = KnowledgeNode.objects.create(id=IDS["node"], canonical_name_zh="PATH58 合成概念导读", slug="e2e-path-node", node_type="concept", status="published")
        debate = KnowledgeNode.objects.create(id=IDS["debate"], canonical_name_zh="PATH58 合成相关争论", slug="e2e-path-debate", node_type="debate", status="published")
        work = Work.objects.create(id=IDS["work"], title="PATH58 已公开书目暂无全文", document_type="book")
        edition = Edition.objects.create(id=IDS["edition"], work=work, state="published", publication_mode="bibliographic", public_slug="e2e-path-bibliographic", version_label="合成书目版")
        activate_catalog_revision(edition, fulltext_ready=False)
        path = ReadingPath.objects.create(id=IDS["path"], title="PATH58 从材料进入理论", slug="e2e-reading-path",
            status="published", introduction="仅供隔离验收的合成路径，不代表学术课程或真实研究结论。",
            learning_goal="验证完整路径、准确材料与私人进度的边界。", audience="没有相关基础的读者", estimated_reading="约两周", estimated_weeks=2,
            prerequisite="无需先修材料；此说明为明确编辑内容。", curator_note="通过真实记录验证界面，不从同名作品推断来源。",
            credits=[{"name": "隔离验收编辑", "role": "策划"}], learning_questions=["路径如何保留原材料身份？"], related_debate_ids=[str(debate.pk)])
        path.topics.add(topic)
        first = ReadingPathStage.objects.create(id=IDS["stage_one"], reading_path=path, name="第一阶段 · 阅读材料", position=0,
            description="两个同作品选段保留为不同材料。", estimated_reading="约一周", learning_questions=["两个材料的准确位置是什么？"])
        second = ReadingPathStage.objects.create(id=IDS["stage_two"], reading_path=path, name="第二阶段 · 概念与补充", position=1,
            description="条目和无全文书目同样保留。", estimated_reading="约一周", related_debate_ids=[str(debate.pk)])
        for index, key in enumerate(("chapter_one", "chapter_two")):
            ReadingPathItem.objects.create(id=IDS[key], reading_path=path, stage=first, stage_name=first.name,
                work=asset.edition.work, edition=asset.edition, asset=asset, document_revision=span.document_revision,
                material_kind="chapter", chapter_title=f"PATH58 同页合成选段{index + 1}", page_start=1, page_end=1,
                printed_page_label=span.printed_page_label, position=index, reading_order=index, is_required=True,
                recommendation_reason="直接核对隔离PDF的真实第一页面。", editorial_note="PATH58 私人编辑备注不得公开")
        ReadingPathItem.objects.create(id=IDS["node_item"], reading_path=path, stage=second, stage_name=second.name,
            node=node, material_kind="node", position=0, reading_order=2)
        ReadingPathItem.objects.create(id=IDS["no_fulltext_item"], reading_path=path, stage=second, stage_name=second.name,
            work=work, edition=edition, position=1, reading_order=3, recommendation_reason="保留书目信息；全文尚未提供。")
        withdrawn = ReadingPathItem.objects.create(id=IDS["withdrawn_item"], reading_path=path, stage=second, stage_name=second.name,
            work=asset.edition.work, edition=asset.edition, asset=asset, document_revision=span.document_revision,
            position=2, reading_order=4, recommendation_reason="新版撤回前的合成整部材料。")
        old = capture_reading_path_publication(path, actor=actor, change_note="首次发布合成路径")
        withdrawn.status = "withdrawn"
        withdrawn.save(update_fields=["status"])
        latest = capture_reading_path_publication(path, actor=actor, change_note="撤回补充材料，保留原有阅读记录")
        save_object_editorial_patch("reading_path", path.pk, {"curator_note": "PATH58 尚未发布的策划说明不得公开"}, actor=actor)
        ReadingPath.objects.create(id=IDS["hidden_path"], title="PATH58 隐藏路径不得公开", slug="e2e-hidden-reading-path", status="draft")
    return {**IDS, "slug": path.slug, "old_revision": str(old.pk), "latest_revision": str(latest.pk),
            "source_asset": str(asset.pk), "source_document_revision": str(span.document_revision_id), "source_edition": str(asset.edition_id)}
