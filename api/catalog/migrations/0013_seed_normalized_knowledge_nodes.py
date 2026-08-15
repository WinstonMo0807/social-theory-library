from django.db import migrations


ROLE_MAP = {
    "foundational": "foundational_work",
    "development": "theoretical_development",
    "introduction": "systematic_exposition",
    "empirical_application": "empirical_application",
    "method_use": "empirical_application",
    "criticism": "critique",
    "theory_history": "systematic_exposition",
    "local_mention": "general_mention",
    "": "general_mention",
}


def _unique_slug(KnowledgeNode, preferred, kind, legacy_id):
    base = (preferred or f"{kind}-{legacy_id}")[:160]
    candidate = base
    suffix = 2
    while KnowledgeNode.objects.filter(slug=candidate).exists():
        candidate = f"{base[:150]}-{suffix}"
        suffix += 1
    return candidate


def _status(editorial_status):
    return "published" if editorial_status == "published" else "draft"


def _create_aliases(KnowledgeNodeAlias, node, values):
    for value in values:
        alias = str(value or "").strip()
        normalized = " ".join(alias.casefold().split())
        if not normalized:
            continue
        KnowledgeNodeAlias.objects.get_or_create(
            node=node,
            normalized_alias=normalized,
            defaults={
                "alias": alias,
                "language": "en" if alias.isascii() else "zh-CN",
                "alias_type": "translation" if alias.isascii() else "alias",
            },
        )


def forwards(apps, schema_editor):
    TheorySchool = apps.get_model("catalog", "TheorySchool")
    Subdiscipline = apps.get_model("catalog", "Subdiscipline")
    Concept = apps.get_model("catalog", "Concept")
    TheoryDisciplineRelation = apps.get_model("catalog", "TheoryDisciplineRelation")
    TheorySubdisciplineRelation = apps.get_model("catalog", "TheorySubdisciplineRelation")
    TheoryRelation = apps.get_model("catalog", "TheoryRelation")
    WorkKnowledgeRelation = apps.get_model("catalog", "WorkKnowledgeRelation")
    PersonKnowledgeRelation = apps.get_model("catalog", "PersonKnowledgeRelation")
    TheoryTimelineEvent = apps.get_model("catalog", "TheoryTimelineEvent")

    KnowledgeNode = apps.get_model("catalog", "KnowledgeNode")
    KnowledgeNodeAlias = apps.get_model("catalog", "KnowledgeNodeAlias")
    KnowledgeNodeDiscipline = apps.get_model("catalog", "KnowledgeNodeDiscipline")
    KnowledgeRelation = apps.get_model("catalog", "KnowledgeRelation")
    WorkNodeRelation = apps.get_model("catalog", "WorkNodeRelation")
    PersonNodeRelation = apps.get_model("catalog", "PersonNodeRelation")
    EvidenceSnippet = apps.get_model("catalog", "EvidenceSnippet")
    TimelineEventRelation = apps.get_model("catalog", "TimelineEventRelation")
    KnowledgeNodeVersion = apps.get_model("catalog", "KnowledgeNodeVersion")
    LegacyKnowledgeMapping = apps.get_model("catalog", "LegacyKnowledgeMapping")

    mapped = {}

    for theory in TheorySchool.objects.all().order_by("created_at"):
        discipline_links = list(
            TheoryDisciplineRelation.objects.filter(theory_school_id=theory.id).order_by("created_at")
        )
        primary_link = next(
            (link for link in discipline_links if link.role == "primary" and link.review_status == "approved"),
            next((link for link in discipline_links if link.review_status == "approved"), None),
        )
        curation = theory.curation if isinstance(theory.curation, dict) else {}
        node = KnowledgeNode.objects.create(
            node_type="theory_tradition",
            canonical_name_zh=theory.name,
            canonical_name_en=theory.foreign_name,
            slug=_unique_slug(KnowledgeNode, theory.slug, "theory", theory.id),
            summary=theory.description,
            definition=theory.description,
            core_questions=theory.core_questions if isinstance(theory.core_questions, list) else [],
            basic_propositions=curation.get("basic_propositions", []),
            theoretical_boundary=str(curation.get("theoretical_boundary", "")),
            period_label=theory.formation_period,
            primary_discipline_id=primary_link.discipline_id if primary_link else None,
            status=_status(theory.editorial_status),
            sort_order=theory.curation_level,
            cover_asset=theory.hero_image,
        )
        mapped[("TheorySchool", str(theory.id))] = node
        LegacyKnowledgeMapping.objects.create(
            legacy_model="TheorySchool",
            legacy_id=theory.id,
            node=node,
            migration_status="mapped",
        )
        _create_aliases(
            KnowledgeNodeAlias,
            node,
            [theory.foreign_name, *(theory.search_aliases or [])],
        )
        for link in discipline_links:
            KnowledgeNodeDiscipline.objects.get_or_create(
                node=node,
                discipline_id=link.discipline_id,
                defaults={
                    "relation_type": link.role if link.role in {"primary", "related"} else "related",
                    "status": "published" if link.review_status == "approved" else "pending",
                    "reviewed_by_id": link.reviewed_by_id,
                    "reviewed_at": link.reviewed_at,
                },
            )
        KnowledgeNodeVersion.objects.create(
            node=node,
            version_number=1,
            snapshot={
                "migration_source": "TheorySchool",
                "legacy_id": str(theory.id),
                "name": theory.name,
                "status": node.status,
            },
            change_note="由旧理论流派记录建立规范节点",
        )

    for subdiscipline in Subdiscipline.objects.all().order_by("created_at"):
        node = KnowledgeNode.objects.create(
            node_type="subdiscipline",
            canonical_name_zh=subdiscipline.name,
            canonical_name_en=subdiscipline.foreign_name,
            slug=_unique_slug(KnowledgeNode, subdiscipline.slug, "subdiscipline", subdiscipline.id),
            summary=subdiscipline.description,
            definition=subdiscipline.research_object or subdiscipline.description,
            core_questions=subdiscipline.core_questions if isinstance(subdiscipline.core_questions, list) else [],
            period_label=subdiscipline.formation_period,
            primary_discipline_id=subdiscipline.discipline_id,
            status=_status(subdiscipline.editorial_status),
            sort_order=subdiscipline.curation_level,
            cover_asset=subdiscipline.hero_image,
        )
        mapped[("Subdiscipline", str(subdiscipline.id))] = node
        LegacyKnowledgeMapping.objects.create(
            legacy_model="Subdiscipline",
            legacy_id=subdiscipline.id,
            node=node,
            migration_status="mapped",
        )
        _create_aliases(
            KnowledgeNodeAlias,
            node,
            [subdiscipline.foreign_name, *(subdiscipline.search_aliases or [])],
        )
        KnowledgeNodeDiscipline.objects.create(
            node=node,
            discipline_id=subdiscipline.discipline_id,
            relation_type="primary",
            status="published" if subdiscipline.editorial_status == "published" else "pending",
        )
        KnowledgeNodeVersion.objects.create(
            node=node,
            version_number=1,
            snapshot={
                "migration_source": "Subdiscipline",
                "legacy_id": str(subdiscipline.id),
                "name": subdiscipline.name,
                "status": node.status,
            },
            change_note="由旧子学科记录建立规范节点",
        )

    for concept in Concept.objects.all().order_by("created_at"):
        node = KnowledgeNode.objects.create(
            node_type="concept",
            canonical_name_zh=concept.name,
            slug=_unique_slug(KnowledgeNode, concept.slug, "concept", concept.id),
            summary=concept.description,
            definition=concept.definition or concept.description,
            status=_status(concept.editorial_status),
            cover_asset=concept.hero_image,
        )
        mapped[("Concept", str(concept.id))] = node
        LegacyKnowledgeMapping.objects.create(
            legacy_model="Concept",
            legacy_id=concept.id,
            node=node,
            migration_status="mapped",
        )
        _create_aliases(KnowledgeNodeAlias, node, concept.search_aliases or [])
        KnowledgeNodeVersion.objects.create(
            node=node,
            version_number=1,
            snapshot={
                "migration_source": "Concept",
                "legacy_id": str(concept.id),
                "name": concept.name,
                "status": node.status,
            },
            change_note="由旧概念记录建立规范节点",
        )

    for relation in WorkKnowledgeRelation.objects.filter(kind="theory_school").order_by("created_at"):
        node = mapped.get(("TheorySchool", str(relation.theory_school_id)))
        if not node:
            continue
        work_relation, _created = WorkNodeRelation.objects.get_or_create(
            work_id=relation.work_id,
            node=node,
            role=ROLE_MAP.get(relation.role, "general_mention"),
            defaults={
                "is_primary": relation.is_primary,
                "strength": relation.strength,
                "confidence": relation.confidence,
                "status": "published" if relation.approved and relation.review_status != "rejected" else "pending",
                "source": relation.source,
                "reviewed_by_id": relation.reviewed_by_id,
                "reviewed_at": relation.reviewed_at,
            },
        )
        if relation.evidence_asset_id and relation.evidence_page and relation.evidence_text:
            EvidenceSnippet.objects.get_or_create(
                work_id=relation.work_id,
                file_id=relation.evidence_asset_id,
                node=node,
                work_node_relation=work_relation,
                page_number=relation.evidence_page,
                quote=relation.evidence_text,
                defaults={
                    "printed_page_label": relation.evidence_printed_label,
                    "extraction_method": "text_layer",
                    "semantic_confidence": relation.confidence,
                    "review_status": "approved" if relation.approved else relation.review_status,
                    "reviewed_by_id": relation.reviewed_by_id,
                    "reviewed_at": relation.reviewed_at,
                },
            )

    for relation in PersonKnowledgeRelation.objects.exclude(theory_school_id=None).order_by("created_at"):
        node = mapped.get(("TheorySchool", str(relation.theory_school_id)))
        if not node:
            continue
        PersonNodeRelation.objects.get_or_create(
            person_id=relation.person_id,
            node=node,
            defaults={
                "relation_label": relation.relation_label,
                "is_representative": relation.approved,
                "confidence": relation.confidence,
                "status": "published" if relation.approved else "pending",
                "source": relation.source,
                "reviewed_by_id": relation.reviewed_by_id,
                "reviewed_at": relation.reviewed_at,
            },
        )

    relation_map = {
        "continuation": ("inherited_from", True, "directed"),
        "influence": ("influenced_by", True, "directed"),
        "split": ("branches_from", True, "directed"),
        "critique": ("criticizes", False, "directed"),
        "synthesis": ("synthesizes", False, "directed"),
        "adjacent": ("overlaps_with", False, "undirected"),
    }
    for relation in TheoryRelation.objects.all().order_by("created_at"):
        relation_type, reverse, direction = relation_map.get(
            relation.relation_type,
            ("overlaps_with", False, "undirected"),
        )
        source = mapped.get(("TheorySchool", str(relation.target_theory_id if reverse else relation.source_theory_id)))
        target = mapped.get(("TheorySchool", str(relation.source_theory_id if reverse else relation.target_theory_id)))
        if not source or not target or source.id == target.id:
            continue
        if direction == "undirected" and str(source.id) > str(target.id):
            source, target = target, source
        KnowledgeRelation.objects.get_or_create(
            source_node=source,
            target_node=target,
            relation_type=relation_type,
            defaults={
                "direction": direction,
                "description": relation.evidence_text,
                "evidence_source": relation.source,
                "confidence": relation.confidence,
                "status": "published" if relation.review_status == "approved" else "pending",
                "reviewed_by_id": relation.reviewed_by_id,
                "published_at": relation.reviewed_at if relation.review_status == "approved" else None,
            },
        )

    for relation in TheorySubdisciplineRelation.objects.all().order_by("created_at"):
        theory_node = mapped.get(("TheorySchool", str(relation.theory_school_id)))
        subdiscipline_node = mapped.get(("Subdiscipline", str(relation.subdiscipline_id)))
        if not theory_node or not subdiscipline_node:
            continue
        source, target = sorted((theory_node, subdiscipline_node), key=lambda item: str(item.id))
        KnowledgeRelation.objects.get_or_create(
            source_node=source,
            target_node=target,
            relation_type="overlaps_with",
            defaults={
                "direction": "undirected",
                "description": relation.role,
                "evidence_source": relation.source,
                "confidence": relation.confidence,
                "status": "published" if relation.review_status == "approved" else "pending",
                "reviewed_by_id": relation.reviewed_by_id,
                "published_at": relation.reviewed_at if relation.review_status == "approved" else None,
            },
        )

    for event in TheoryTimelineEvent.objects.all().order_by("created_at"):
        if event.theory_school_id:
            node = mapped.get(("TheorySchool", str(event.theory_school_id)))
            if node:
                TimelineEventRelation.objects.create(event=event, node=node, relation_type="subject")
        if event.subdiscipline_id:
            node = mapped.get(("Subdiscipline", str(event.subdiscipline_id)))
            if node:
                TimelineEventRelation.objects.create(event=event, node=node, relation_type="subject")
        if event.discipline_id:
            TimelineEventRelation.objects.create(event=event, discipline_id=event.discipline_id, relation_type="context")
        if event.scholar_id:
            TimelineEventRelation.objects.create(event=event, scholar_id=event.scholar_id, relation_type="subject")
        if event.work_id:
            TimelineEventRelation.objects.create(event=event, work_id=event.work_id, relation_type="evidence")


def backwards(apps, schema_editor):
    apps.get_model("catalog", "KnowledgeNodeMergeRecord").objects.all().delete()
    apps.get_model("catalog", "LegacyKnowledgeMapping").objects.all().delete()
    apps.get_model("catalog", "KnowledgeNode").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_knowledgenode_knowledgenodealias_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
