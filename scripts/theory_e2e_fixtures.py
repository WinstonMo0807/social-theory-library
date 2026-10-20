"""Synthetic authority records for the disposable PDF45–49 acceptance run.

The three concept uses reference actual extracted, published parallel-fixture
paragraphs. The relationship quotation is copied from that exact extraction.
This seed never invents source text or quality values, changes existing sources,
starts a worker, or runs outside the isolated E2E database.
"""
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import transaction


IDS = {
    "discipline": "45000000-0000-4000-8000-000000000001",
    "empty_discipline": "45000000-0000-4000-8000-000000000002",
    "other_discipline": "45000000-0000-4000-8000-000000000003",
    "theory": "45000000-0000-4000-8000-000000000011",
    "concept": "45000000-0000-4000-8000-000000000012",
    "debate": "45000000-0000-4000-8000-000000000013",
    "draft": "45000000-0000-4000-8000-000000000014",
    "person_a": "45000000-0000-4000-8000-000000000021",
    "person_b": "45000000-0000-4000-8000-000000000022",
    "scholar_a": "45000000-0000-4000-8000-000000000023",
    "scholar_b": "45000000-0000-4000-8000-000000000024",
    "work": "45000000-0000-4000-8000-000000000031",
    "edition": "45000000-0000-4000-8000-000000000032",
    "usage_a": "45000000-0000-4000-8000-000000000041",
    "usage_b": "45000000-0000-4000-8000-000000000042",
    "usage_c": "45000000-0000-4000-8000-000000000043",
    "relation_related": "45000000-0000-4000-8000-000000000051",
    "relation_distinct": "45000000-0000-4000-8000-000000000052",
    "relation_evidence": "45000000-0000-4000-8000-000000000061",
}


def _isolated():
    database = settings.DATABASES["default"]
    path = Path(database["NAME"]).resolve()
    if (database["ENGINE"] != "django.db.backends.sqlite3"
            or not path.parent.name.startswith("stl-v305-e2e-")
            or path.name != "local_fixture.sqlite3"
            or Path(settings.MEDIA_ROOT).resolve() != path.parent / "media"):
        raise RuntimeError("Theory fixtures require the disposable E2E SQLite database and its media directory")


def seed_theory(actor):
    _isolated()
    from catalog.models import (
        Asset, Discipline, Edition, EvidenceSnippet, EvidenceSpan, KnowledgeNode,
        KnowledgeNodeAlias, KnowledgeNodeDiscipline, KnowledgeRelation, Person, PersonNodeRelation,
        ScholarProfile, Work, WorkNodeRelation,
    )
    from catalog.services import content_placements
    from tests.v304_helpers import activate_catalog_revision
    from parallel_reader_e2e_fixtures import IDS as parallel_ids

    if any(model.objects.filter(pk__in=IDS.values()).exists()
           for model in (Discipline, KnowledgeNode, Person, ScholarProfile, Work, Edition,
                         KnowledgeRelation, EvidenceSnippet)):
        raise RuntimeError("Theory fixture identifiers already exist; use a fresh disposable E2E directory")
    with transaction.atomic():
        disciplines = {}
        for key, name, slug in (
            ("discipline", "E2E理论学科", "e2e-theory-discipline"),
            ("empty_discipline", "E2E空学科", "e2e-theory-empty"),
            ("other_discipline", "E2E比较学科", "e2e-theory-other"),
        ):
            disciplines[key] = Discipline.objects.create(id=IDS[key], code=slug, slug=slug, name=name,
                description=f"{name}只用于隔离验收，不是正式学术资料。", editorial_status="published")
        nodes = {}
        for key, kind, name, status in (
            ("theory", "theory_tradition", "E2E理论传统", "published"),
            ("concept", "concept", "E2E测试概念", "published"),
            ("debate", "debate", "E2E关键争论", "published"),
            ("draft", "concept", "E2E未公开概念", "draft"),
        ):
            nodes[key] = KnowledgeNode.objects.create(id=IDS[key], node_type=kind,
                canonical_name_zh=name, canonical_name_en=f"Synthetic {key}", slug=f"e2e-theory-{key}",
                summary=f"{name}的合成说明，仅用于隔离页面验收。", definition=f"{name}的合成定义。",
                primary_discipline=disciplines["discipline"], status=status)
            KnowledgeNodeDiscipline.objects.create(node=nodes[key], discipline=disciplines["discipline"],
                relation_type="primary", status="published")
        KnowledgeNodeAlias.objects.create(node=nodes["concept"], alias="E2E概念别名",
            is_verified=True, source_kind="editorial", created_by=actor)
        KnowledgeNodeAlias.objects.create(node=nodes["concept"], alias="ＰＡＲＡＬＬＥＬ",
            language="en", is_verified=True, source_kind="editorial", created_by=actor)
        people = []
        for suffix, name in (("a", "E2E代表学者甲"), ("b", "E2E代表学者乙")):
            person = Person.objects.create(id=IDS[f"person_{suffix}"], preferred_name=name,
                original_name=f"Synthetic scholar {suffix}", authority_status="verified")
            ScholarProfile.objects.create(id=IDS[f"scholar_{suffix}"], person=person,
                slug=f"e2e-theory-scholar-{suffix}", editorial_status="published",
                short_description="仅用于隔离验收的合成人物。")
            PersonNodeRelation.objects.create(person=person, node=nodes["concept"],
                is_representative=True, relation_label="合成用法归属", status="published")
            people.append(person)
        PersonNodeRelation.objects.create(person=people[0], node=nodes["theory"],
            is_representative=True, relation_label="合成代表关系", status="published")
        work = Work.objects.create(id=IDS["work"], title="E2E理论馆藏书目", language="zh-CN", document_type="book")
        edition = Edition.objects.create(id=IDS["edition"], work=work, state="published",
            is_primary=True, publication_mode="bibliographic", public_slug="e2e-theory-bibliographic")
        WorkNodeRelation.objects.create(work=work, node=nodes["theory"], status="published",
            role="foundational_work", reviewed_by=actor, source="isolated-theory-fixture")
        activate_catalog_revision(edition, fulltext_ready=False)

        # Reuse exact existing published source spans without mutating that
        # source's catalog revision, authorship, text, or publication state.
        items, extracted = [], {}
        for suffix, person, source_key, reference_page, span_offset in (
            ("a", people[0], "left_asset", 1, 0),
            ("b", people[1], "right_asset", 2, 2),
            ("c", people[0], "left_asset", 1, 1),
        ):
            asset = Asset.objects.select_related("edition__active_catalog_revision").get(pk=parallel_ids[source_key])
            revision = asset.edition.active_catalog_revision
            if not revision or not revision.fulltext_ready or revision.reader_asset_id != asset.pk:
                raise RuntimeError("The real parallel PDF fixture must be extracted and formally published first")
            span = EvidenceSpan.objects.filter(document_revision_id=revision.document_revision_id,
                page_number=reference_page, is_stale=False).order_by("start_offset", "pk")[span_offset:span_offset + 1].first()
            if span is None or not span.original_text or not span.content_hash:
                raise RuntimeError("A real extracted paragraph is required for each concept use")
            if "PARALLEL" not in span.original_text:
                raise RuntimeError("The real paragraph must contain the declared concept-use term")
            extracted[suffix] = (asset, span)
            items.append({
                "id": IDS[f"usage_{suffix}"], "target": {"type": "span", "id": str(span.pk)},
                "concept_usage": {
                    "term": "PARALLEL", "language": "en", "usage_type": "definition" if suffix == "a" else "application",
                    "title": f"E2E用法{suffix.upper()}", "explanatory_object": f"合成解释对象{suffix.upper()}",
                    "period": "2026", "context": f"合成语境{suffix.upper()}",
                    "interpretation": f"这是用法{suffix.upper()}的合成编辑解释，与下方真实提取的测试原文分开展示。",
                    "source_person_id": str(person.pk), "attribution_note": "隔离夹具明确归属给合成人物，不表示真实著作关系。",
                    "review_status": "confirmed",
                },
            })
        saved = content_placements.command("node", nodes["concept"].pk, {
            "action": "save", "request_id": str(uuid4()), "expected_revision": "0", "items": items,
        }, actor)
        if saved["source_problems"] or not saved["can_publish"]:
            raise RuntimeError("Concept fixture references did not satisfy the actual publication checks")
        content_placements.command("node", nodes["concept"].pk, {
            "action": "publish", "request_id": str(uuid4()), "expected_revision": saved["expected_revision"],
        }, actor)
        public = content_placements.read("node", nodes["concept"].pk, public=True)["public_detail"]
        if len(public["usages"]) != 3 or public["unavailable_usage_count"]:
            raise RuntimeError("The three concept uses did not survive current public source validation")

        # These are explicitly synthetic editorial relationships, not assertions
        # about real scholars. One has a real extracted quotation; the other
        # deliberately has only an editorial note, so the UI must disclose that.
        KnowledgeRelation.objects.create(id=IDS["relation_related"], source_node=nodes["theory"],
            target_node=nodes["concept"], relation_type="extends", status="published",
            description="仅用于隔离验收的合成扩展关系。",
            evidence_source="合成编辑说明，尚未提供定位原文。", created_by=actor, reviewed_by=actor)
        distinct = KnowledgeRelation.objects.create(id=IDS["relation_distinct"], source_node=nodes["theory"],
            target_node=nodes["debate"], relation_type="criticizes", status="published",
            description="仅用于隔离验收的合成区别关系。",
            evidence_source="隔离 PDF 的真实提取段落，用于核对版本与定位，不作真实学术论断。",
            created_by=actor, reviewed_by=actor)
        asset, span = extracted["b"]
        EvidenceSnippet.objects.create(id=IDS["relation_evidence"], work=asset.edition.work, file=asset,
            knowledge_relation=distinct, page_number=span.page_number, page_end=span.page_number,
            quote=span.original_text, extraction_method="text_layer", review_status="approved", reviewed_by=actor)
    return IDS
