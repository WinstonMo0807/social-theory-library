from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from django.db import transaction
from django.db.models import Count

from catalog.models import (
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    IntelligenceFeedback,
    Work,
)
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
    kind: str = "",
    edition_id=None,
) -> list[dict[str, Any]]:
    """Reduce hundreds of machine claims to a few evidence-backed decisions."""

    bounded_limit = max(1, min(int(limit), MAX_ACTIVE_DECISIONS))
    queryset = _claim_queryset(work)
    if edition_id:
        queryset = queryset.filter(edition_id=edition_id)
    if kind == CuratedClaim.Kind.MAJOR_CRITICISM:
        queryset = queryset.filter(claim_type=DerivedClaim.ClaimType.CRITICISM)
    elif kind == CuratedClaim.Kind.MAJOR_RESPONSE:
        queryset = queryset.filter(claim_type=DerivedClaim.ClaimType.RESPONSE)
    elif kind == CuratedClaim.Kind.CORE_VIEWPOINT:
        queryset = queryset.exclude(claim_type__in=[DerivedClaim.ClaimType.CRITICISM, DerivedClaim.ClaimType.RESPONSE])
    claims = list(queryset[:500])
    if kind:
        claims = [claim for claim in claims if _candidate_kind(claim) == kind]
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
        envelope = evidence_span_envelope(representative.primary_evidence, public_metadata=False).as_dict()
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
                    "source": {**envelope["source"], "title": envelope["source"]["work_title"]},
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
) -> dict | None:
    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionError("观点审核必须记录当前管理员，请先登录。")
    if decision not in IntelligenceFeedback.Decision.values:
        raise ValueError("无法识别本次观点审核操作。")
    work = Work.objects.select_for_update().get(pk=work.pk)
    claim = DerivedClaim.objects.select_for_update().select_related(
        "document_revision", "primary_evidence"
    ).get(pk=claim.pk)
    if claim.work_id != work.id:
        raise ValueError("该观点建议不属于当前作品。")
    if (
        claim.status != DerivedClaim.Status.ACTIVE
        or not claim.document_revision.is_active
        or claim.primary_evidence.is_stale
    ):
        raise ValueError("该观点的原文依据已变化，请重新查找建议。")
    from uuid import uuid5
    from catalog import models as m
    from catalog.services.knowledge_sources import migrate_span, locator_payload, snapshot_revision
    from catalog.services.knowledge_workspace import submit_assertion_draft
    from catalog.services.intelligence_changes import review, apply
    from catalog.services.knowledge_core import require_editor
    require_editor(actor)
    result = None
    edited_proposition = str(proposition or claim.proposition).strip()
    curated_kind = str(kind or _candidate_kind(claim)).strip()
    if curated_kind not in {CuratedClaim.Kind.CORE_VIEWPOINT,CuratedClaim.Kind.MAJOR_CRITICISM,CuratedClaim.Kind.MAJOR_RESPONSE}:
        raise ValueError("当前作品支持核心观点、主要批评和主要回应。")
    if decision in {IntelligenceFeedback.Decision.ACCEPT,IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT}:
        request_id=uuid5(claim.pk,"knowledge-adoption-v1")
        previous=m.ChangeSet.objects.filter(request_id=request_id).first()
        if previous:
            original=previous.items.get(kind="assertion").payload
            if original.get("text") != edited_proposition or original.get("category") != curated_kind:
                raise ValueError("这条候选已保存到知识工作区，请在那里建立新的局部修订，不能重复采用覆盖。")
            result={"changeset_id":str(previous.pk),"review_url":f"/admin/intelligence?changeset={previous.pk}","status":previous.status}
            return result
        snapshot_revision(claim.document_revision)
        mapping=migrate_span(claim.primary_evidence)
        if not mapping.target_id:
            raise ValueError("这条历史证据缺少可恢复的修订定位。请在原文工作区核验后提交陈述，原候选保留。")
        anchor=m.EvidenceAnchor.objects.get(pk=mapping.target_id)
        expression={"author_claim":"author_claim","direct_quote":"direct_quote","paraphrase":"paraphrase",
            "criticized_claim":"criticized_claim"}.get(claim.attribution,"editorial_judgment")
        conditions={"other":"；".join(str(v) for v in claim.qualifiers)} if claim.qualifiers else {}
        payload={"text":edited_proposition,"category":curated_kind,"predicate":claim.predicate,"expression":expression,
            "conditions":conditions,"participants":[],"legacy_candidate_id":str(claim.pk),
            "editorial_note":str(editorial_note or ""),"evidence":[{"stance":"context","segments":locator_payload(anchor)["segments"]}]}
        changeset=submit_assertion_draft(claim.document_revision,payload,actor,request_id=request_id,origin="human")
        ids=list(map(str,changeset.items.values_list("pk",flat=True)))
        changeset=review(changeset.pk,[{"id":key,"decision":"accepted","note":editorial_note} for key in ids],actor,expected_version=changeset.version)
        saved=apply(changeset.pk,ids,actor,request_id=uuid5(claim.pk,"knowledge-adoption-apply-v1"),expected_version=changeset.version)
        result={"changeset_id":str(changeset.pk),"review_url":f"/admin/intelligence?changeset={changeset.pk}",
            "status":"draft" if not saved["blocked"] else "conflict","saved":saved["saved"],"blocked":saved["blocked"]}
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
            "knowledge_draft": result,
        },
    )
    return result


def publish_work_curated_claims(*, work: Work, actor) -> list[CuratedClaim]:
    """Read compatibility only. Knowledge drafts have their own explicit publish."""
    return []
