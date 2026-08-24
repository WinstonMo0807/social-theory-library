from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from catalog.models import (
    Asset,
    CapabilityDemand,
    CapabilityExecutor,
    Concept,
    CuratedClaim,
    DerivedClaim,
    Discipline,
    DocumentRevision,
    EditorialRevision,
    EvidenceSpan,
    EvidenceSnippet,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Page,
    PersonKnowledgeRelation,
    PersonNodeRelation,
    ProjectionState,
    RelationReviewStatus,
    Subdiscipline,
    TheorySchool,
    Topic,
    WorkKnowledgeRelation,
    WorkNodeRelation,
    WorkTopicRelation,
)

from catalog.services.canonical_identity import canonical_work_node_role


def _grouped(queryset, field: str) -> dict[str, int]:
    return {
        str(row[field]): row["count"]
        for row in queryset.values(field).annotate(count=Count("pk")).order_by(field)
    }


_LEGACY_WRITE_MODELS = frozenset({"TheorySchool", "Concept", "WorkKnowledgeRelation"})
_ORM_WRITE_METHODS = frozenset(
    {
        "create",
        "get_or_create",
        "update_or_create",
        "bulk_create",
        "bulk_update",
        "update",
        "delete",
    }
)
_MUTABLE_GENERIC_BASES = frozenset(
    {
        "CreateAPIView",
        "UpdateAPIView",
        "DestroyAPIView",
        "ListCreateAPIView",
        "RetrieveUpdateAPIView",
        "RetrieveDestroyAPIView",
        "RetrieveUpdateDestroyAPIView",
        "ModelViewSet",
    }
)


def _names_in(node) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _legacy_write_call_sites(source_root: Path | None = None) -> list[dict]:
    """Find executable legacy ORM writers and mutable generic API surfaces."""

    source_root = (source_root or Path(settings.BASE_DIR)).resolve()
    sites = []
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        if any(part in {"migrations", "tests", "__pycache__"} for part in relative.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr not in _ORM_WRITE_METHODS:
                    continue
                models = sorted(_names_in(node.func.value) & _LEGACY_WRITE_MODELS)
                for model in models:
                    sites.append(
                        {
                            "model": model,
                            "operation": node.func.attr,
                            "path": relative.as_posix(),
                            "line": node.lineno,
                            "source": lines[node.lineno - 1].strip()[:240],
                        }
                    )
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                base.attr if isinstance(base, ast.Attribute) else base.id
                for base in node.bases
                if isinstance(base, (ast.Attribute, ast.Name))
            }
            if not (base_names & _MUTABLE_GENERIC_BASES):
                continue
            models = set()
            for item in node.body:
                if isinstance(item, ast.Assign):
                    models.update(_names_in(item.value) & _LEGACY_WRITE_MODELS)
            for model in sorted(models):
                sites.append(
                    {
                        "model": model,
                        "operation": "mutable_api_surface",
                        "path": relative.as_posix(),
                        "line": node.lineno,
                        "source": f"class {node.name}",
                    }
                )
    return sorted(
        sites,
        key=lambda row: (row["path"], row["line"], row["model"], row["operation"]),
    )


def build_inventory() -> dict:
    from catalog.services.canonical_identity import legacy_mapping_safety

    expected_node_types = {
        "TheorySchool": KnowledgeNode.NodeType.THEORY_TRADITION,
        "Concept": KnowledgeNode.NodeType.CONCEPT,
    }
    mapped = {}
    mapping_type_mismatches = {"TheorySchool": 0, "Concept": 0}
    mapping_safety_findings = {}
    mapping_ready_count = 0
    for row in LegacyKnowledgeMapping.objects.filter(
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED
    ).select_related("node"):
        expected_type = expected_node_types.get(row.legacy_model)
        if expected_type and row.node.node_type != expected_type:
            mapping_type_mismatches[row.legacy_model] += 1
        safe, reason = legacy_mapping_safety(row)
        if not safe:
            mapping_safety_findings[reason] = mapping_safety_findings.get(reason, 0) + 1
            continue
        mapping_ready_count += 1
        mapped[(row.legacy_model, str(row.legacy_id))] = row.node_id
    work_node_relations = {
        (work_id, node_id, role): status
        for work_id, node_id, role, status in WorkNodeRelation.objects.values_list(
            "work_id", "node_id", "role", "status"
        )
    }
    person_node_relations = {
        (person_id, node_id): status
        for person_id, node_id, status in PersonNodeRelation.objects.values_list(
            "person_id", "node_id", "status"
        )
    }
    work_topic_relations = {
        (work_id, topic_id): review_status
        for work_id, topic_id, review_status in WorkTopicRelation.objects.values_list(
            "work_id", "topic_id", "review_status"
        )
    }
    evidence_keys = {
        (
            work_id,
            node_id,
            role,
            file_id,
            page_number,
            hashlib.sha256((quote or "").encode("utf-8")).hexdigest(),
            review_status,
        )
        for work_id, node_id, role, file_id, page_number, quote, review_status in (
            EvidenceSnippet.objects.filter(work_node_relation__isnull=False).values_list(
                "work_id",
                "node_id",
                "work_node_relation__role",
                "file_id",
                "page_number",
                "quote",
                "review_status",
            )
        )
    }

    work_relation_parity = {
        "theory_total": 0,
        "theory_reviewed_total": 0,
        "theory_mapped": 0,
        "theory_canonical_peer": 0,
        "theory_role_parity": 0,
        "theory_status_parity": 0,
        "theory_evidence_required": 0,
        "theory_evidence_parity": 0,
        "concept_total": 0,
        "concept_reviewed_total": 0,
        "concept_mapped": 0,
        "concept_canonical_peer": 0,
        "concept_role_parity": 0,
        "concept_status_parity": 0,
        "concept_evidence_required": 0,
        "concept_evidence_parity": 0,
        "topic_total": 0,
        "topic_reviewed_total": 0,
        "topic_canonical_peer": 0,
        "topic_status_parity": 0,
        "topic_evidence_required": 0,
        "topic_evidence_parity": 0,
        "unreviewed_not_backfilled": 0,
        "invalid_target_cardinality": 0,
    }
    for relation in WorkKnowledgeRelation.objects.iterator():
        targets = sum(
            bool(value)
            for value in (relation.theory_school_id, relation.topic_id, relation.concept_id)
        )
        if targets != 1:
            work_relation_parity["invalid_target_cardinality"] += 1
        is_reviewed = bool(
            relation.approved and relation.review_status == RelationReviewStatus.APPROVED
        )
        if not is_reviewed:
            work_relation_parity["unreviewed_not_backfilled"] += 1
        if relation.theory_school_id:
            work_relation_parity["theory_total"] += 1
            if not is_reviewed:
                continue
            work_relation_parity["theory_reviewed_total"] += 1
            node_id = mapped.get(("TheorySchool", str(relation.theory_school_id)))
            role = canonical_work_node_role(relation.role)
            status = work_node_relations.get((relation.work_id, node_id, role)) if node_id else None
            if node_id:
                work_relation_parity["theory_mapped"] += 1
                peer = status is not None
                work_relation_parity["theory_canonical_peer"] += int(peer)
                work_relation_parity["theory_role_parity"] += int(peer)
                work_relation_parity["theory_status_parity"] += int(
                    status == KnowledgePublicationStatus.PUBLISHED
                )
                if relation.evidence_asset_id and relation.evidence_page and relation.evidence_text:
                    work_relation_parity["theory_evidence_required"] += 1
                    evidence_key = (
                        relation.work_id,
                        node_id,
                        role,
                        relation.evidence_asset_id,
                        relation.evidence_page,
                        hashlib.sha256(relation.evidence_text.encode("utf-8")).hexdigest(),
                        RelationReviewStatus.APPROVED,
                    )
                    work_relation_parity["theory_evidence_parity"] += int(
                        evidence_key in evidence_keys
                    )
        elif relation.concept_id:
            work_relation_parity["concept_total"] += 1
            if not is_reviewed:
                continue
            work_relation_parity["concept_reviewed_total"] += 1
            node_id = mapped.get(("Concept", str(relation.concept_id)))
            role = canonical_work_node_role(relation.role)
            status = work_node_relations.get((relation.work_id, node_id, role)) if node_id else None
            if node_id:
                work_relation_parity["concept_mapped"] += 1
                peer = status is not None
                work_relation_parity["concept_canonical_peer"] += int(peer)
                work_relation_parity["concept_role_parity"] += int(peer)
                work_relation_parity["concept_status_parity"] += int(
                    status == KnowledgePublicationStatus.PUBLISHED
                )
                if relation.evidence_asset_id and relation.evidence_page and relation.evidence_text:
                    work_relation_parity["concept_evidence_required"] += 1
                    evidence_key = (
                        relation.work_id,
                        node_id,
                        role,
                        relation.evidence_asset_id,
                        relation.evidence_page,
                        hashlib.sha256(relation.evidence_text.encode("utf-8")).hexdigest(),
                        RelationReviewStatus.APPROVED,
                    )
                    work_relation_parity["concept_evidence_parity"] += int(
                        evidence_key in evidence_keys
                    )
        elif relation.topic_id:
            work_relation_parity["topic_total"] += 1
            if not is_reviewed:
                continue
            work_relation_parity["topic_reviewed_total"] += 1
            review_status = work_topic_relations.get((relation.work_id, relation.topic_id))
            work_relation_parity["topic_canonical_peer"] += int(review_status is not None)
            work_relation_parity["topic_status_parity"] += int(
                review_status == RelationReviewStatus.APPROVED
            )
            if relation.evidence_asset_id and relation.evidence_page and relation.evidence_text:
                work_relation_parity["topic_evidence_required"] += 1
                work_relation_parity["topic_evidence_parity"] += int(
                    WorkTopicRelation.objects.filter(
                        work_id=relation.work_id,
                        topic_id=relation.topic_id,
                        evidence_asset_id=relation.evidence_asset_id,
                        evidence_page=relation.evidence_page,
                        evidence_text=relation.evidence_text,
                        review_status=RelationReviewStatus.APPROVED,
                    ).exists()
                )

    person_relation_parity = {
        "total": 0,
        "reviewed_total": 0,
        "mapped": 0,
        "canonical_peers": 0,
        "status_parity": 0,
        "unreviewed_not_backfilled": 0,
    }
    for relation in PersonKnowledgeRelation.objects.iterator():
        if not (
            relation.approved and relation.review_status == RelationReviewStatus.APPROVED
        ):
            person_relation_parity["unreviewed_not_backfilled"] += 1
            continue
        for legacy_model, legacy_id in (
            ("TheorySchool", relation.theory_school_id),
            ("Concept", relation.concept_id),
        ):
            if not legacy_id:
                continue
            person_relation_parity["total"] += 1
            person_relation_parity["reviewed_total"] += 1
            node_id = mapped.get((legacy_model, str(legacy_id)))
            status = person_node_relations.get((relation.person_id, node_id)) if node_id else None
            if node_id:
                person_relation_parity["mapped"] += 1
            if status is not None:
                person_relation_parity["canonical_peers"] += 1
                person_relation_parity["status_parity"] += int(
                    status == KnowledgePublicationStatus.PUBLISHED
                )

    legacy_write_call_sites = _legacy_write_call_sites()

    page_digest = hashlib.sha256()
    for page_id, asset_id, index in Page.objects.order_by("asset_id", "index").values_list(
        "id", "asset_id", "index"
    ).iterator():
        page_digest.update(f"{asset_id}:{index}:{page_id}\n".encode())

    text_assets = Asset.objects.filter(pages__isnull=False).distinct()
    active_revision_assets = set(
        DocumentRevision.objects.filter(is_active=True).values_list("asset_id", flat=True)
    )
    missing_revision_assets = text_assets.exclude(pk__in=active_revision_assets).count()
    disallowed_node_types = KnowledgeNode.objects.filter(
        node_type__in=[
            KnowledgeNode.NodeType.DISCIPLINE,
            KnowledgeNode.NodeType.SUBDISCIPLINE,
            KnowledgeNode.NodeType.TOPIC,
        ]
    )

    return {
        "canonical_identity": {
            "discipline": Discipline.objects.count(),
            "subdiscipline": Subdiscipline.objects.count(),
            "topic": Topic.objects.count(),
            "legacy_theory_school": TheorySchool.objects.count(),
            "legacy_concept": Concept.objects.count(),
            "knowledge_node_by_type": _grouped(KnowledgeNode.objects.all(), "node_type"),
            "legacy_mapping_by_model": _grouped(
                LegacyKnowledgeMapping.objects.all(), "legacy_model"
            ),
            "legacy_mapping_by_status": _grouped(
                LegacyKnowledgeMapping.objects.all(), "migration_status"
            ),
            "mapping_type_mismatches": mapping_type_mismatches,
            "mapping_safety_findings": dict(sorted(mapping_safety_findings.items())),
            "legacy_mappings_ready_for_backfill": mapping_ready_count,
            "disallowed_identity_copy_nodes": disallowed_node_types.count(),
            "work_relation_parity": work_relation_parity,
            "person_relation_parity": person_relation_parity,
            "legacy_write_call_sites": legacy_write_call_sites,
            "legacy_write_call_site_count": len(legacy_write_call_sites),
        },
        "document_intelligence": {
            "text_assets": text_assets.count(),
            "document_revisions": DocumentRevision.objects.count(),
            "active_document_revisions": DocumentRevision.objects.filter(is_active=True).count(),
            "text_assets_without_active_revision": missing_revision_assets,
            "evidence_spans": EvidenceSpan.objects.count(),
            "stale_evidence_spans": EvidenceSpan.objects.filter(is_stale=True).count(),
            "page_identity_count": Page.objects.count(),
            "page_identity_sha256": page_digest.hexdigest(),
        },
        "claims_and_editorial": {
            "derived_claims": DerivedClaim.objects.count(),
            "active_shadow_claims": DerivedClaim.objects.filter(
                status=DerivedClaim.Status.ACTIVE,
                shadow=True,
            ).count(),
            "curated_claims": CuratedClaim.objects.count(),
            "published_curated_claims": CuratedClaim.objects.filter(
                status=CuratedClaim.Status.PUBLISHED
            ).count(),
            "editorial_revisions_by_status": _grouped(EditorialRevision.objects.all(), "status"),
        },
        "runtime": {
            "projection_states_by_status": _grouped(ProjectionState.objects.all(), "status"),
            "projection_states_by_type": _grouped(
                ProjectionState.objects.all(), "projection_type"
            ),
            "capability_demands_by_state": _grouped(CapabilityDemand.objects.all(), "state"),
            "executors_by_status": _grouped(CapabilityExecutor.objects.all(), "status"),
            "publication_blocking_demands": CapabilityDemand.objects.filter(
                publication_blocking=True
            ).exclude(
                state__in=[CapabilityDemand.State.COMPLETED, CapabilityDemand.State.CANCELED]
            ).count(),
        },
        "retirement_gate": {
            "legacy_write_call_sites_zero": len(legacy_write_call_sites) == 0,
            "legacy_mapping_types_valid": not any(mapping_type_mismatches.values()),
            "legacy_mapping_targets_safe": not mapping_safety_findings,
            "relation_parity_complete": (
                work_relation_parity["theory_reviewed_total"]
                == work_relation_parity["theory_canonical_peer"]
                == work_relation_parity["theory_role_parity"]
                == work_relation_parity["theory_status_parity"]
                and work_relation_parity["concept_reviewed_total"]
                == work_relation_parity["concept_canonical_peer"]
                == work_relation_parity["concept_role_parity"]
                == work_relation_parity["concept_status_parity"]
                and work_relation_parity["topic_reviewed_total"]
                == work_relation_parity["topic_canonical_peer"]
                == work_relation_parity["topic_status_parity"]
                and work_relation_parity["theory_evidence_required"]
                == work_relation_parity["theory_evidence_parity"]
                and work_relation_parity["concept_evidence_required"]
                == work_relation_parity["concept_evidence_parity"]
                and work_relation_parity["topic_evidence_required"]
                == work_relation_parity["topic_evidence_parity"]
                and person_relation_parity["reviewed_total"]
                == person_relation_parity["canonical_peers"]
                == person_relation_parity["status_parity"]
                and work_relation_parity["invalid_target_cardinality"] == 0
            ),
            "document_revision_backfill_complete": missing_revision_assets == 0,
            "identity_copy_nodes_retired": disallowed_node_types.count() == 0,
        },
    }


class Command(BaseCommand):
    help = "只读输出 3.0 canonical、document、claim、projection 迁移 inventory。"

    def add_arguments(self, parser):
        parser.add_argument("--output", help="可选 JSON 输出路径")

    def handle(self, *args, **options):
        payload = json.dumps(build_inventory(), ensure_ascii=False, indent=2, default=str)
        if options.get("output"):
            output = Path(options["output"]).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"inventory 已写入 {output}"))
        self.stdout.write(payload)
