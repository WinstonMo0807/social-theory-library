"""Synthetic PDF62–66 inputs for the existing disposable runner; never self-run."""
from django.db import transaction


def fixture_id(number):
    return f"61000000-0000-4000-8000-{number:012d}"


IDS = {"profile": fixture_id(1), "namesake": fixture_id(2), "sparse": fixture_id(3),
       "person": fixture_id(11), "namesake_person": fixture_id(12), "sparse_person": fixture_id(13),
       "topic": fixture_id(21), "school": fixture_id(22), "concept": fixture_id(23),
       "work": fixture_id(31), "edition": fixture_id(32), "asset": fixture_id(33),
       "outline": fixture_id(34), "chapter": fixture_id(35), "citation": fixture_id(36)}


def seed_scholars(actor):
    from timeline_e2e_fixtures import _isolated, _source
    from parallel_reader_e2e_fixtures import IDS as parallel_ids
    _isolated()
    from catalog.models import (Asset, Contribution, DocumentOutlineRevision, Edition, EvidenceSpan,
        KnowledgeNode, Page, Person, PersonNameVariant, PersonNodeRelation, PersonTopicRelation, ScholarProfile, Topic, Work)
    from catalog.services import shared_curation
    from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision
    from tests.v304_helpers import activate_catalog_revision
    if ScholarProfile.objects.filter(pk__in=IDS.values()).exists():
        raise RuntimeError("Scholar fixtures already exist; use a fresh isolated runner directory")
    original, excerpt = _source(parallel_ids["left_asset"], 1)
    with transaction.atomic():
        profiles = []
        for index, (key, person_key, slug, name) in enumerate((
            ("profile", "person", "e2e-scholar-public", "SCHOLAR63 合成学者"),
            ("namesake", "namesake_person", "e2e-scholar-namesake", "SCHOLAR63 合成学者"),
            ("sparse", "sparse_person", "e2e-scholar-sparse", "SCHOLAR63 稀疏档案"))):
            person = Person.objects.create(id=IDS[person_key], preferred_name=name, original_name=f"Synthetic Scholar {index + 1}",
                birth_year=1800 + index * 80, death_year=1870 + index * 70, authority_status="verified",
                biography="仅供隔离验收，不是真实学者资料。" if index < 2 else "")
            profiles.append(ScholarProfile.objects.create(id=IDS[key], person=person, slug=slug, editorial_status="published",
                short_description="验证准确人物、职责和出处。" if index < 2 else ""))
        profile = profiles[0]
        PersonNameVariant.objects.create(person=profile.person, name="SCHOLAR63 正式译名", variant_type="translation", source_kind="editorial", is_verified=True, displayable=True)
        PersonNameVariant.objects.create(person=profile.person, name="SCHOLAR63 私有待审译名", variant_type="translation", source_kind="pdf_evidence", is_verified=False)
        topic = Topic.objects.create(id=IDS["topic"], name="SCHOLAR63 合成研究领域", slug="e2e-scholar-field", editorial_status="published")
        school = KnowledgeNode.objects.create(id=IDS["school"], canonical_name_zh="SCHOLAR63 合成理论传统", slug="e2e-scholar-school", node_type="theory_tradition", status="published")
        concept = KnowledgeNode.objects.create(id=IDS["concept"], canonical_name_zh="SCHOLAR63 合成概念", slug="e2e-scholar-concept", node_type="concept", status="published")
        PersonTopicRelation.objects.create(person=profile.person, topic=topic, review_status="approved")
        for node in (school, concept):
            PersonNodeRelation.objects.create(person=profile.person, node=node, status="published", relation_label="隔离验收确认关系")
        work = Work.objects.create(id=IDS["work"], title="SCHOLAR66 责任范围合成文集", document_type="book")
        edition = Edition.objects.create(id=IDS["edition"], work=work, state="published", public_slug="e2e-scholar-work", is_primary=True, version_label="隔离验收版")
        asset = Asset.objects.create(id=IDS["asset"], edition=edition, kind="normalized", status="ready", validation_status="valid", access_status="public",
            file=original.file.name, sha256=original.sha256, page_count=original.page_count, is_current=True)
        pages = {row.index: Page.objects.create(asset=asset, index=row.index, text=row.text, printed_label=row.printed_label) for row in original.pages.order_by("index")}
        revision = activate_catalog_revision(edition, reader_asset=asset)
        DocumentOutlineRevision.objects.create(id=IDS["outline"], asset=asset, document_revision=revision.document_revision, revision=1, source_checksum=asset.sha256,
            is_active=True, reviewed=True, nodes=[{"id": IDS["chapter"], "title": "SCHOLAR66 第一章", "pdf_page": 1, "parent_id": None}])
        scope = {"kind": "chapter", "chapters": [{"title": "SCHOLAR66 第一章", "asset_id": str(asset.pk), "document_revision_id": str(revision.document_revision_id),
            "outline_revision_id": IDS["outline"], "outline_node_id": IDS["chapter"], "page_start": 1, "page_end": 1}]}
        Contribution.objects.create(edition=edition, person=profile.person, role="author", scope=scope, approved=True)
        Contribution.objects.create(edition=edition, person=profiles[1].person, role="editor", approved=True)
        activate_catalog_revision(edition, reader_asset=asset, document_revision=revision.document_revision)
        span = EvidenceSpan.objects.create(document_revision=revision.document_revision, page=pages[1], page_number=1,
            start_offset=excerpt.start_offset, end_offset=excerpt.end_offset, original_text=excerpt.original_text,
            normalized_text=excerpt.normalized_text, content_hash=excerpt.content_hash, printed_page_label=excerpt.printed_page_label)
        curation = shared_curation.save_curation("scholar", profile.pk, {"items": [{"source_type": "span", "source_id": str(span.pk), "group_title": "代表原文", "reason": "来自隔离PDF的准确原文。"}]}, actor)
        shared_curation.publish_curation("scholar", profile.pk, curation["edit_version"], actor)
        curation_values = {"nationalities": ["合成国别"], "occupations": ["合成研究者"], "featured_source_id": curation["items"][0]["id"],
            "profile_sources": [{"id": IDS["citation"], "title": "隔离验收资料说明", "url": "https://example.org/synthetic-scholar", "fields": ["biography"], "note": "合成夹具；不是学术来源。"}]}
        draft = create_editorial_revision(target_type="scholar_profile", target_id=profile.pk, patch={"curation": curation_values}, actor=actor,
            idempotency_key="e2e-scholar-profile-publication", change_note="合成档案正式版本")
        publish_editorial_revision(draft.pk, actor=actor)
        relation = shared_curation.save_relation(None, {"source_scholar": str(profile.pk), "target_scholar": str(profiles[1].pk), "relation_type": "cooperation", "direction": "undirected",
            "summary": "隔离验收正式合作关系。", "source": "合成记录，仅用于验收。"}, actor)
        shared_curation.publish_relation(relation["id"], relation["edit_version"], actor)
        shared_curation.save_relation(None, {"source_scholar": str(profile.pk), "target_scholar": str(profiles[2].pk), "relation_type": "influence", "summary": "SCHOLAR66 待审关系", "source": "待核对合成来源。"}, actor)
    return {**IDS, "slug": profile.slug, "public_revision_id": str(draft.pk)}
