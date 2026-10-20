"""Synthetic PDF50/51 records for the disposable local acceptance database.

This seed depends on the real PDF generation, extraction and publication in
seed_parallel_reader(). It reads those sources without modifying their work,
edition, document revision, file or publication snapshot. Editorial entities
and relationships below are explicitly synthetic, never production content.
"""
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import transaction


def fixture_id(number):
    return f"50000000-0000-4000-8000-{number:012d}"


IDS = {
    "discipline": fixture_id(1), "empty_discipline": fixture_id(2),
    "private_discipline": fixture_id(3), "main": fixture_id(101),
    "no_public_discipline": fixture_id(128), "empty": fixture_id(129),
    "child": fixture_id(130), "draft": fixture_id(131),
    "theory": fixture_id(201), "concept": fixture_id(202),
    "problem": fixture_id(203), "draft_node": fixture_id(204),
    "topic": fixture_id(401), "draft_topic": fixture_id(402),
    "bibliographic_work": fixture_id(501), "bibliographic_edition": fixture_id(502),
    "path": fixture_id(601), "draft_path": fixture_id(602),
}


def _isolated():
    database = settings.DATABASES["default"]
    path = Path(database["NAME"]).resolve()
    if (database["ENGINE"] != "django.db.backends.sqlite3"
            or not path.parent.name.startswith("stl-v305-e2e-")
            or path.name != "local_fixture.sqlite3"
            or Path(settings.MEDIA_ROOT).resolve() != path.parent / "media"):
        raise RuntimeError("Subdiscipline fixtures require the disposable E2E SQLite database and media")


def seed_subdisciplines(actor):
    _isolated()
    from catalog.models import (
        Asset, Discipline, Edition, EvidenceSpan, KnowledgeNode, KnowledgeNodeSubdiscipline,
        Person, PersonSubdisciplineRelation, ReadingPath, ReadingPathItem, ScholarProfile,
        Subdiscipline, Topic, TopicSubdisciplineRelation, Work, WorkSubdisciplineRelation,
    )
    from catalog.serializers import SubdisciplineSerializer
    from catalog.services import content_placements
    from parallel_reader_e2e_fixtures import IDS as parallel_ids
    from tests.v304_helpers import activate_catalog_revision

    models = (Discipline, Edition, KnowledgeNode, Person, ReadingPath, ScholarProfile,
              Subdiscipline, Topic, Work)
    identifiers = [fixture_id(index) for index in range(1, 603)]
    if any(model.objects.filter(pk__in=identifiers).exists() for model in models):
        raise RuntimeError("Subdiscipline fixture identifiers exist; use a fresh disposable directory")
    with transaction.atomic():
        disciplines = {}
        for key, label, status in (
            ("discipline", "E2E子学科学科", "published"),
            ("empty_discipline", "E2E子学科空学科", "published"),
            ("private_discipline", "E2E子学科未公开学科", "draft"),
        ):
            slug = f"e2e-subdiscipline-{key.replace('_', '-')}"
            disciplines[key] = Discipline.objects.create(id=IDS[key], name=label, slug=slug,
                code=slug, description="隔离子学科验收用合成学科。", editorial_status=status)
        subdisciplines = {}
        for index in range(1, 32):
            name = {
                28: "E2E子学科无公开学科", 29: "E2E子学科空条目",
                30: "E2E子学科已确认下级", 31: "E2E子学科未公开条目",
            }.get(index, f"E2E子学科{index:02d}")
            subdisciplines[index] = Subdiscipline.objects.create(
                id=fixture_id(100 + index), name=name, slug=f"e2e-subdiscipline-{index:02d}",
                discipline=disciplines["private_discipline" if index == 28 else "discipline"],
                description=f"{name}的合成说明，仅用于隔离页面验收。",
                editorial_status="draft" if index == 31 else "published",
                curation_level=2 if index <= 3 else 0,
            )
        main = subdisciplines[1]
        main.core_questions = ["E2E只有编辑说明的问题", "E2E子学科关联问题"]
        main.research_object = "仅用于检查草稿预览兼容的合成研究对象。"
        main.methods = ["合成方法字段"]
        main.save(update_fields=["core_questions", "research_object", "methods", "updated_at"])
        subdisciplines[30].parent = main
        subdisciplines[30].save(update_fields=["parent", "updated_at"])
        subdisciplines[28].parent = subdisciplines[31]
        subdisciplines[28].save(update_fields=["parent", "updated_at"])

        nodes = {}
        for key, kind, label, status in (
            ("theory", "theory_tradition", "E2E子学科关联理论", "published"),
            ("concept", "concept", "E2E子学科关联概念", "published"),
            ("problem", "research_problem", "E2E子学科关联问题", "published"),
            ("draft_node", "concept", "E2E子学科未公开概念", "draft"),
        ):
            nodes[key] = KnowledgeNode.objects.create(id=IDS[key], node_type=kind,
                canonical_name_zh=label, slug=f"e2e-subdiscipline-{key.replace('_', '-')}",
                summary=f"{label}的合成说明。", status=status,
                primary_discipline=disciplines["discipline"])
            KnowledgeNodeSubdiscipline.objects.create(node=nodes[key], subdiscipline=main,
                relation_role="related", source="isolated-subdiscipline-fixture",
                status="published", reviewed_by=actor)
        for index in range(1, 4):
            person = Person.objects.create(id=fixture_id(300 + index),
                preferred_name=f"E2E子学科学者{index}", authority_status="verified")
            ScholarProfile.objects.create(id=fixture_id(310 + index), person=person,
                slug=f"e2e-subdiscipline-scholar-{index}", editorial_status="published",
                short_description="合成人物；没有肖像文件与可定位来源。")
            PersonSubdisciplineRelation.objects.create(person=person, subdiscipline=main,
                relation_label="合成代表关系", source="人工确认的合成关联说明，尚未提供原文。",
                review_status="approved", reviewed_by=actor)
        for key, label, status in (
            ("topic", "E2E子学科关联主题", "published"),
            ("draft_topic", "E2E子学科未公开主题", "draft"),
        ):
            topic = Topic.objects.create(id=IDS[key], name=label,
                slug=f"e2e-subdiscipline-{key.replace('_', '-')}", description="合成主题说明。",
                editorial_status=status)
            TopicSubdisciplineRelation.objects.create(topic=topic, subdiscipline=main,
                relation_label="合成主题关联", review_status="approved", reviewed_by=actor)

        extracted = {}
        for key, page in (("left", 1), ("right", 2)):
            asset = Asset.objects.select_related("edition__active_catalog_revision").get(pk=parallel_ids[f"{key}_asset"])
            current = asset.edition.active_catalog_revision
            if not current or not current.fulltext_ready or current.reader_asset_id != asset.pk:
                raise RuntimeError("Parallel sources must be actually extracted and formally published first")
            span = EvidenceSpan.objects.filter(document_revision_id=current.document_revision_id,
                page_number=page, is_stale=False).order_by("start_offset", "pk").first()
            if span is None or not span.original_text or not span.content_hash:
                raise RuntimeError("Subdiscipline sources require a real extracted paragraph")
            extracted[key] = (asset, span)
        asset, span = extracted["left"]
        WorkSubdisciplineRelation.objects.create(work=asset.edition.work, subdiscipline=main,
            is_primary=True, review_status="approved", reviewed_by=actor,
            source="隔离夹具原文依据", evidence_asset=asset,
            evidence_page=span.page_number, evidence_text=span.original_text)
        work = Work.objects.create(id=IDS["bibliographic_work"], title="E2E子学科仅书目文献",
            document_type="book", language="zh-CN")
        edition = Edition.objects.create(id=IDS["bibliographic_edition"], work=work,
            state="published", publication_mode="bibliographic", is_primary=True,
            public_slug="e2e-subdiscipline-bibliographic", version_label="合成书目版本")
        WorkSubdisciplineRelation.objects.create(work=work, subdiscipline=main,
            review_status="approved", reviewed_by=actor, source="合成书目关联，无可读原文")
        activate_catalog_revision(edition, fulltext_ready=False)

        _, right_span = extracted["right"]
        saved = content_placements.command("subdiscipline", main.pk, {
            "action": "save", "request_id": str(uuid4()), "expected_revision": "0",
            "items": [{"target": {"type": "span", "id": str(right_span.pk)}}],
        }, actor)
        if saved["source_problems"] or not saved["can_publish"]:
            raise RuntimeError("Subdiscipline placement failed the actual publication checks")
        content_placements.command("subdiscipline", main.pk, {
            "action": "publish", "request_id": str(uuid4()),
            "expected_revision": saved["expected_revision"],
        }, actor)
        for key, status in (("path", "published"), ("draft_path", "draft")):
            path = ReadingPath.objects.create(id=IDS[key], title=f"E2E子学科{'阅读路径' if key == 'path' else '未公开路径'}",
                slug=f"e2e-subdiscipline-{key.replace('_', '-')}", status=status,
                introduction="只用于隔离验收的合成路径，包含实际已关联节点。", created_by=actor)
            ReadingPathItem.objects.create(reading_path=path, node=nodes["theory"],
                stage_name="合成入门步骤", reading_order=1)

        public = SubdisciplineSerializer(main).data
        if (len(public["core_works"]) != 2 or len(public["sources"]) != 2
                or len(public["scholars"]) != 3 or len(public["reading_paths"]) != 1
                or {row["source_kind"] for row in public["sources"]} != {"work_relation", "placement_span"}):
            raise RuntimeError("Subdiscipline fixture did not produce its intended real public projection")
        if any(not row["reader_href"] or not row["document_revision_id"] for row in public["sources"]):
            raise RuntimeError("All fixture excerpts must preserve exact current document revisions")
        if public["works_pagination"] != {"count": 2, "page": 1, "total_pages": 1}:
            raise RuntimeError("Subdiscipline work pagination must describe the real public result")
        redacted = SubdisciplineSerializer(subdisciplines[28]).data
        if redacted["discipline"] is not None or redacted["parent"] is not None:
            raise RuntimeError("Unpublished parent and discipline identities must not be exposed")
    return IDS
