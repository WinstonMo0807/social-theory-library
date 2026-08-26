from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from catalog.models import (
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    IntelligenceFeedback,
    Work,
)
from catalog.services.dependency_engine import record_canonical_change
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.research.feedback import record_intelligence_feedback
from catalog.services.candidate_decision_protocol import (
    attach_candidate_action_descriptors,
)


MAX_ACTIVE_DECISIONS = 5
MIN_QUALITY = 0.5
MIN_IMPORTANCE = 0.4
_NORMALIZE = re.compile(r"[\W_]+", re.UNICODE)


def _normalized(value: object) -> str:
    return _NORMALIZE.sub("", str(value or "").casefold())


def _cluster_key(claim: DerivedClaim) -> str:
    if claim.cluster_key.strip():
        return claim.cluster_key.strip().casefold()
    structured = "|".join(
        _normalized(value)
        for value in (claim.subject, claim.predicate, claim.object)
        if str(value or "").strip()
    )
    return structured[:480] or _normalized(claim.proposition)[:480]


def _candidate_kind(claim: DerivedClaim) -> str:
    if claim.claim_type == DerivedClaim.ClaimType.CRITICISM:
        return CuratedClaim.Kind.MAJOR_CRITICISM
    if claim.claim_type == DerivedClaim.ClaimType.RESPONSE:
        return CuratedClaim.Kind.MAJOR_RESPONSE
    return CuratedClaim.Kind.CORE_VIEWPOINT


def _kind_field(kind: str) -> str:
    return {
        CuratedClaim.Kind.CORE_VIEWPOINT: "core_viewpoint",
        CuratedClaim.Kind.MAJOR_CRITICISM: "major_criticism",
        CuratedClaim.Kind.MAJOR_RESPONSE: "major_response",
    }[kind]


def _claim_queryset(work: Work):
    return (
        DerivedClaim.objects.filter(
            work=work,
            status=DerivedClaim.Status.ACTIVE,
            shadow=True,
            document_revision__is_active=True,
            primary_evidence__is_stale=False,
            quality_score__gte=MIN_QUALITY,
            importance_score__gte=MIN_IMPORTANCE,
        )
        .exclude(attribution=DerivedClaim.Attribution.UNCERTAIN)
        .select_related(
            "work",
            "edition",
            "document_revision__asset__edition__work",
            "primary_evidence__page",
        )
        .order_by("-importance_score", "-quality_score", "created_at")
    )


def high_value_claim_candidates(
    work: Work,
    *,
    reviewer=None,
    limit: int = MAX_ACTIVE_DECISIONS,
) -> list[dict[str, Any]]:
    """Reduce hundreds of machine claims to a few evidence-backed decisions."""

    bounded_limit = max(1, min(int(limit), MAX_ACTIVE_DECISIONS))
    claims = list(_claim_queryset(work)[:500])
    if not claims:
        return []
    adopted = set(
        CuratedClaim.objects.filter(work=work, adopted_from__isnull=False).values_list(
            "adopted_from_id", flat=True
        )
    )
    decided: set[str] = set()
    if reviewer and getattr(reviewer, "is_authenticated", False):
        decided = set(
            IntelligenceFeedback.objects.filter(
                reviewed_by=reviewer,
                candidate_type="derived_claim_curation",
                candidate_id__in=[str(row.id) for row in claims],
            ).values_list("candidate_id", flat=True)
        )

    clusters: defaultdict[str, list[DerivedClaim]] = defaultdict(list)
    for claim in claims:
        if claim.id in adopted or str(claim.id) in decided:
            continue
        clusters[_cluster_key(claim)].append(claim)

    corroboration = {
        str(row["cluster_key"]).casefold(): int(row["work_count"])
        for row in DerivedClaim.objects.filter(
            cluster_key__in=[row.cluster_key for row in claims if row.cluster_key],
            status=DerivedClaim.Status.ACTIVE,
            document_revision__is_active=True,
            primary_evidence__is_stale=False,
        )
        .values("cluster_key")
        .annotate(work_count=Count("work_id", distinct=True))
    }
    candidates: list[tuple[float, DerivedClaim, dict[str, Any]]] = []
    for cluster, rows in clusters.items():
        representative = max(
            rows,
            key=lambda row: (
                row.importance_score,
                row.quality_score,
                row.attribution == DerivedClaim.Attribution.AUTHOR_CLAIM,
            ),
        )
        polarities = {row.polarity for row in rows}
        cross_work_count = corroboration.get(cluster, 1)
        attribution_bonus = 1.0 if representative.attribution == DerivedClaim.Attribution.AUTHOR_CLAIM else 0.6
        score = (
            representative.importance_score * 0.40
            + representative.quality_score * 0.30
            + min(cross_work_count, 4) / 4 * 0.15
            + attribution_bonus * 0.10
            + min(len(rows), 3) / 3 * 0.05
        )
        envelope = evidence_span_envelope(representative.primary_evidence).as_dict()
        kind = _candidate_kind(representative)
        reasons = [
            f"命题重要性 {round(representative.importance_score * 100)}%",
            f"原文证据质量 {round(representative.quality_score * 100)}%",
            f"归因类型 {representative.get_attribution_display()}",
        ]
        if len(rows) > 1:
            reasons.append(f"同一命题簇内有 {len(rows)} 条候选，已去重为一项")
        if cross_work_count > 1:
            reasons.append(f"另有 {cross_work_count - 1} 部馆藏作品提供同簇印证")
        conflicts = []
        if DerivedClaim.Polarity.POSITIVE in polarities and DerivedClaim.Polarity.NEGATIVE in polarities:
            conflicts.append("同一命题簇同时出现肯定与否定表述，需要 Editor 核对语境。")
        payload = {
            "id": str(representative.id),
            "kind": "derived_claim_curation",
            "field_name": _kind_field(kind),
            "label": representative.proposition,
            "proposed_value": representative.proposition,
            "current_value": None,
            "status": "pending",
            "source": "derived_claim",
            "source_tier": "pdf_evidence",
            "confidence": round(score, 6),
            "evidence_count": 1,
            "evidence": [
                {
                    "supporting_text": envelope["text"],
                    "url": envelope["reader_url"],
                    "locator": envelope["locator"],
                    "quality": envelope["quality"],
                    "provenance": envelope["provenance"],
                }
            ],
            "reasons": reasons,
            "conflicts": conflicts,
            "curated_kind": kind,
            "attribution": representative.attribution,
            "claim_type": representative.claim_type,
            "quality_score": representative.quality_score,
            "importance_score": representative.importance_score,
            "cluster_size": len(rows),
            "cross_work_corroboration": cross_work_count,
            "decision_url": (
                f"/catalog/admin/works/{work.id}/claim-candidates/{representative.id}/decision/"
            ),
            "available_actions": ["accept", "accept_with_edit", "reject", "defer"],
        }
        candidates.append((score, representative, payload))

    candidates.sort(key=lambda row: (-row[0], str(row[1].id)))
    output: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    for kind in (
        CuratedClaim.Kind.CORE_VIEWPOINT,
        CuratedClaim.Kind.MAJOR_CRITICISM,
        CuratedClaim.Kind.MAJOR_RESPONSE,
    ):
        selected = next((row for row in candidates if row[2]["curated_kind"] == kind), None)
        if selected:
            output.append(attach_candidate_action_descriptors(selected[2]))
            chosen_ids.add(str(selected[1].id))
    for _score, claim, payload in candidates:
        if len(output) >= bounded_limit:
            break
        if str(claim.id) in chosen_ids:
            continue
        output.append(attach_candidate_action_descriptors(payload))
        chosen_ids.add(str(claim.id))
    return output[:bounded_limit]


def _publishable_draft_claims_queryset(work: Work):
    valid_evidence = ClaimEvidence.objects.filter(
        curated_claim_id=OuterRef("pk"),
        evidence_span__is_stale=False,
        evidence_span__document_revision__is_active=True,
    )
    return (
        CuratedClaim.objects.select_for_update()
        .filter(work=work, status=CuratedClaim.Status.DRAFT)
        .filter(Exists(valid_evidence))
    )


@transaction.atomic
def decide_claim_curation_candidate(
    *,
    work: Work,
    claim: DerivedClaim,
    decision: str,
    actor,
    proposition: str = "",
    editorial_note: str = "",
    kind: str = "",
) -> CuratedClaim | None:
    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionError("Claim 策展决定必须记录真实 Editor。")
    if decision not in IntelligenceFeedback.Decision.values:
        raise ValueError("未知 Claim 策展决定。")
    claim = DerivedClaim.objects.select_for_update().select_related(
        "document_revision", "primary_evidence"
    ).get(pk=claim.pk)
    if claim.work_id != work.id:
        raise ValueError("DerivedClaim 不属于当前 Work。")
    if (
        claim.status != DerivedClaim.Status.ACTIVE
        or not claim.document_revision.is_active
        or claim.primary_evidence.is_stale
    ):
        raise ValueError("该 Claim 的原文依据已经失效，请等待增量重算。")
    curated = None
    edited_proposition = str(proposition or claim.proposition).strip()
    curated_kind = str(kind or _candidate_kind(claim)).strip()
    allowed_kinds = {
        CuratedClaim.Kind.CORE_VIEWPOINT,
        CuratedClaim.Kind.MAJOR_CRITICISM,
        CuratedClaim.Kind.MAJOR_RESPONSE,
    }
    if curated_kind not in allowed_kinds:
        raise ValueError("当前 Work 策展只支持核心观点、主要批评和主要回应。")
    if decision in {IntelligenceFeedback.Decision.ACCEPT, IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT}:
        if not edited_proposition:
            raise ValueError("采用 Claim 前必须确认命题文本。")
        curated, _ = CuratedClaim.objects.update_or_create(
            work=work,
            adopted_from=claim,
            defaults={
                "kind": curated_kind,
                "proposition": edited_proposition,
                "editorial_note": str(editorial_note or "").strip(),
                "qualifiers": claim.qualifiers,
                "status": CuratedClaim.Status.DRAFT,
                "created_by": actor,
            },
        )
        ClaimEvidence.objects.get_or_create(
            curated_claim=curated,
            evidence_span=claim.primary_evidence,
            role=ClaimEvidence.Role.PRIMARY,
            defaults={
                "confidence": max(claim.quality_score, claim.primary_evidence.quality),
                "validation": {
                    "document_revision_id": str(claim.document_revision_id),
                    "document_revision_active": True,
                    "content_hash": claim.primary_evidence.content_hash,
                },
            },
        )
        record_canonical_change(
            object_type="curated_claim",
            object_id=curated.id,
            change_kind="create",
            changed_fields=["kind", "proposition", "evidence"],
            actor=actor,
            idempotency_key=f"curated-claim-adopt:{claim.id}:{curated.updated_at.isoformat()}",
        )
    record_intelligence_feedback(
        reviewer=actor,
        task_profile_key={
            CuratedClaim.Kind.CORE_VIEWPOINT: "core_viewpoint",
            CuratedClaim.Kind.MAJOR_CRITICISM: "major_criticism",
            CuratedClaim.Kind.MAJOR_RESPONSE: "major_response",
        }[curated_kind],
        candidate_type="derived_claim_curation",
        candidate_id=str(claim.id),
        decision=decision,
        provider=claim.model_provider,
        model=claim.model_name,
        prompt_key=claim.prompt_key,
        prompt_version=claim.prompt_version,
        original_payload={"proposition": claim.proposition, "kind": _candidate_kind(claim)},
        edited_payload={
            "proposition": edited_proposition,
            "kind": curated_kind,
            "editorial_note": editorial_note,
            "curated_claim_id": str(curated.id) if curated else "",
        },
    )
    return curated


@transaction.atomic
def publish_work_curated_claims(*, work: Work, actor) -> list[CuratedClaim]:
    """Publish only evidence-backed human drafts during an explicit Work publish."""

    now = timezone.now()
    claims = list(_publishable_draft_claims_queryset(work))
    for claim in claims:
        claim.status = CuratedClaim.Status.PUBLISHED
        claim.published_by = actor
        claim.published_at = now
        claim.save(update_fields=["status", "published_by", "published_at", "updated_at"])
        record_canonical_change(
            object_type="curated_claim",
            object_id=claim.id,
            change_kind="publish",
            changed_fields=["status", "published_at"],
            actor=actor,
            idempotency_key=f"curated-claim-publish:{claim.id}:{now.isoformat()}",
        )
    return claims
