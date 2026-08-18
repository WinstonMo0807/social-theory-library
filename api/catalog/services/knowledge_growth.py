from __future__ import annotations

from hashlib import sha256
import json
import re
from uuid import UUID

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import (
    Asset,
    Edition,
    KnowledgeNode,
    KnowledgeNodeAlias,
    NewAuthorityCandidate,
    Page,
    Person,
    PersonNameVariant,
    ScholarProfile,
    Topic,
    UnknownEntityObservation,
)
from catalog.services.query_lexicon.normalization import (
    detect_language,
    normalize_term,
)
from catalog.services.query_lexicon.resolver import ADMIN_RESOLVABLE, resolve_terms
from ingestion.models import AuditEvent


_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


def _digest(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _clean_terms(terms) -> list[str]:
    values = []
    for value in terms or []:
        text = " ".join(str(value or "").split()).strip()
        if text and normalize_term(text) not in {normalize_term(item) for item in values}:
            values.append(text)
    return values[:4]


def infer_entity_guess(terms: list[str]) -> tuple[str, dict]:
    """Make a conservative hint for review; it never links or creates authority."""

    terms = _clean_terms(terms)
    cjk = next((item for item in terms if _CJK_RE.search(item)), "")
    latin = next((item for item in terms if _LATIN_RE.search(item) and not _CJK_RE.search(item)), "")
    if cjk and ("·" in cjk or "・" in cjk) and latin:
        return NewAuthorityCandidate.EntityType.PERSON, {
            "reason": "cjk_middle_dot_and_latin_name",
            "identity_required": True,
        }
    latin_words = latin.split()
    if latin and len(latin_words) in {2, 3, 4} and all(
        word[:1].isupper() for word in latin_words if word
    ) and cjk and len(cjk) <= 12:
        return NewAuthorityCandidate.EntityType.PERSON, {
            "reason": "title_case_multiword_latin_name",
            "identity_required": True,
        }
    return NewAuthorityCandidate.EntityType.KNOWLEDGE_NODE, {
        "reason": "conservative_non_person_pair",
        "identity_required": True,
    }


def _primary_term(terms: list[str]) -> str:
    return next((term for term in terms if _CJK_RE.search(term)), terms[0] if terms else "")


def _candidate_key(terms: list[str], entity_guess: str) -> str:
    normalized = sorted({normalize_term(term) for term in terms if normalize_term(term)})
    return _digest(["new-authority-v1", entity_guess, normalized])


def persist_unknown_observation(
    *,
    asset: Asset,
    edition: Edition,
    work,
    page: Page | None,
    semantic_chunk,
    document_id: str,
    page_number: int | None,
    printed_page_label: str,
    terms: list[str],
    evidence_text: str,
    start_offset: int,
    end_offset: int,
    extraction_method: str,
    extraction_version: str,
    confidence: float,
    confidence_factors: dict,
    source_text_checksum: str,
    bbox=None,
) -> tuple[UnknownEntityObservation, NewAuthorityCandidate, bool]:
    terms = _clean_terms(terms)
    entity_guess, guess_factors = infer_entity_guess(terms)
    normalized_terms = sorted({normalize_term(term) for term in terms if normalize_term(term)})
    candidate, _candidate_created = NewAuthorityCandidate.objects.get_or_create(
        fingerprint=_candidate_key(terms, entity_guess),
        defaults={
            "entity_type": entity_guess,
            "primary_term": _primary_term(terms),
            "normalized_primary_term": normalize_term(_primary_term(terms)),
            "terms": terms,
            "languages": sorted({detect_language(term) for term in terms}),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "confidence_factors": {**guess_factors, **(confidence_factors or {})},
        },
    )
    merged_terms = _clean_terms([*(candidate.terms or []), *terms])
    changed = []
    if merged_terms != candidate.terms:
        candidate.terms = merged_terms
        changed.append("terms")
    merged_languages = sorted({*(candidate.languages or []), *(detect_language(term) for term in terms)})
    if merged_languages != candidate.languages:
        candidate.languages = merged_languages
        changed.append("languages")
    if float(confidence) > float(candidate.confidence):
        candidate.confidence = max(0.0, min(1.0, float(confidence)))
        changed.append("confidence")
    if changed:
        candidate.save(update_fields=[*changed, "updated_at"])

    fingerprint = _digest(
        [
            "unknown-observation-v1",
            str(asset.id),
            str(document_id or ""),
            page_number,
            start_offset,
            end_offset,
            normalized_terms,
            source_text_checksum,
        ]
    )
    observation, created = UnknownEntityObservation.objects.get_or_create(
        fingerprint=fingerprint,
        defaults={
            "candidate": candidate,
            "work": work,
            "edition": edition,
            "asset": asset,
            "page": page,
            "semantic_chunk": semantic_chunk,
            "document_id": str(document_id or ""),
            "page_number": page_number,
            "printed_page_label": str(printed_page_label or "")[:40],
            "terms": terms,
            "languages": sorted({detect_language(term) for term in terms}),
            "entity_guess": entity_guess,
            "evidence_text": str(evidence_text or "")[:12000],
            "start_offset": max(0, int(start_offset or 0)),
            "end_offset": max(0, int(end_offset or 0)),
            "extraction_method": str(extraction_method or "")[:80],
            "extraction_version": str(extraction_version or "")[:80],
            "confidence": max(0.0, min(1.0, float(confidence))),
            "confidence_factors": {**guess_factors, **(confidence_factors or {})},
            "source_text_checksum": str(source_text_checksum or "")[:64],
        },
    )
    if not created:
        updates = []
        if observation.candidate_id != candidate.id:
            observation.candidate = candidate
            updates.append("candidate")
        if not observation.is_current:
            observation.is_current = True
            observation.superseded_at = None
            updates.extend(["is_current", "superseded_at"])
        if updates:
            observation.save(update_fields=[*updates, "updated_at"])
    return observation, candidate, created


def refresh_unknown_candidate(candidate: NewAuthorityCandidate) -> NewAuthorityCandidate:
    current = candidate.observations.filter(is_current=True)
    stats = current.aggregate(
        evidence_count=Count("id"),
        work_count=Count("work_id", distinct=True),
    )
    factors = dict(candidate.confidence_factors or {})
    factors.update(
        {
            "independent_evidence_count": stats["evidence_count"] or 0,
            "independent_work_count": stats["work_count"] or 0,
            "requires_manual_identity": True,
        }
    )
    candidate.confidence_factors = factors
    if not current.exists() and candidate.status == NewAuthorityCandidate.Status.PENDING:
        candidate.status = NewAuthorityCandidate.Status.SUPERSEDED
    candidate.save(update_fields=["confidence_factors", "status", "updated_at"])
    return candidate


def possible_authority_matches(candidate: NewAuthorityCandidate) -> list[dict]:
    terms = _clean_terms(candidate.terms)
    entity_types = [
        "person",
        "knowledge_node",
        "topic",
    ]
    try:
        resolved = resolve_terms(
            terms,
            entity_types=entity_types,
            scope=ADMIN_RESOLVABLE,
            max_results_per_term=8,
            include_scope_diagnostics=True,
        ).get("results", {})
    except Exception:
        resolved = {}
    rows = []
    seen = set()
    for term in terms:
        payload = resolved.get(normalize_term(term), {}) or {}
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        for row in matches:
            entity = row.get("entity") if isinstance(row, dict) else {}
            entity = entity if isinstance(entity, dict) else {}
            entity_type = entity.get("entity_type") or row.get("entity_type")
            entity_id = entity.get("entity_id") or row.get("entity_id")
            key = (str(entity_type), str(entity_id))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "entity_type": key[0],
                "entity_id": key[1],
                "label": entity.get("canonical_label") or row.get("term") or term,
                "matched_term": term,
                "trust_level": row.get("trust_level", ""),
                "admin_resolvable": bool(row.get("admin_resolvable", True)),
            })
    return rows[:24]


def _unique_slug(model, value: str) -> str:
    base = slugify(value, allow_unicode=False) or f"draft-{UUID(int=0).hex[:8]}"
    candidate = base[: model._meta.get_field("slug").max_length]
    suffix = 2
    while model.objects.filter(slug=candidate).exists():
        marker = f"-{suffix}"
        candidate = f"{base[: model._meta.get_field('slug').max_length - len(marker)]}{marker}"
        suffix += 1
    return candidate


def _duplicate_matches(target_type: str, term: str) -> list[dict]:
    normalized = normalize_term(term)
    rows = []
    if target_type == NewAuthorityCandidate.EntityType.PERSON:
        rows.extend(
            {
                "entity_type": "person",
                "entity_id": str(row.id),
                "label": row.preferred_name,
            }
            for row in Person.objects.filter(preferred_name__iexact=term).exclude(
                authority_status=Person.AuthorityStatus.REJECTED
            )[:10]
        )
    elif target_type == NewAuthorityCandidate.EntityType.KNOWLEDGE_NODE:
        rows.extend(
            {
                "entity_type": "knowledge_node",
                "entity_id": str(row.id),
                "label": row.canonical_name_zh,
            }
            for row in KnowledgeNode.objects.filter(canonical_name_zh__iexact=term).exclude(
                status="rejected"
            )[:10]
        )
        rows.extend(
            {
                "entity_type": "knowledge_node",
                "entity_id": str(row.node_id),
                "label": row.alias,
            }
            for row in KnowledgeNodeAlias.objects.filter(normalized_alias=normalized)[:10]
        )
    elif target_type == NewAuthorityCandidate.EntityType.TOPIC:
        rows.extend(
            {
                "entity_type": "topic",
                "entity_id": str(row.id),
                "label": row.name,
            }
            for row in Topic.objects.filter(name__iexact=term).exclude(editorial_status="rejected")[:10]
        )
    return rows


@transaction.atomic
def decide_new_authority_candidate(
    candidate: NewAuthorityCandidate,
    *,
    action: str,
    actor,
    target_type: str = "",
    target_id: str = "",
    canonical_term: str = "",
    node_type: str = "theory_tradition",
    confirm_new: bool = False,
    reason: str = "",
) -> NewAuthorityCandidate:
    candidate = NewAuthorityCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status != NewAuthorityCandidate.Status.PENDING:
        raise ValueError("该新实体候选已经有审核决定。")
    action = str(action or "").strip().casefold()
    now = timezone.now()
    if action == "reject":
        candidate.status = NewAuthorityCandidate.Status.REJECTED
        candidate.review_reason = str(reason or "管理员拒绝未知实体候选")[:4000]
    elif action == "match_existing":
        if target_type not in {
            NewAuthorityCandidate.EntityType.PERSON,
            NewAuthorityCandidate.EntityType.KNOWLEDGE_NODE,
            NewAuthorityCandidate.EntityType.TOPIC,
        }:
            raise ValueError("请选择已有的人物、知识节点或主题。")
        try:
            target_uuid = UUID(str(target_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("已有实体 ID 无效。") from exc
        if target_type == "person":
            target = Person.objects.filter(pk=target_uuid).first()
            if target is None or target.authority_status in {"rejected", "archived", "merged"}:
                raise ValueError("该人物不能作为后台解析目标。")
        elif target_type == "knowledge_node":
            target = KnowledgeNode.objects.filter(pk=target_uuid).first()
            if target is None or target.status in {"rejected", "archived"}:
                raise ValueError("该知识节点不能作为后台解析目标。")
        else:
            target = Topic.objects.filter(pk=target_uuid).first()
            if target is None or str(target.editorial_status) in {"rejected", "archived"}:
                raise ValueError("该主题不能作为后台解析目标。")
        candidate.entity_type = target_type
        candidate.matched_entity_type = target_type
        candidate.matched_entity_id = target_uuid
        candidate.status = NewAuthorityCandidate.Status.MATCHED
        candidate.review_reason = str(reason or "管理员关联已有实体")[:4000]
    elif action == "create_draft":
        target_type = target_type or candidate.entity_type
        if target_type not in {"person", "knowledge_node", "topic"}:
            raise ValueError("创建草稿前请选择实体类型。")
        canonical_term = " ".join((canonical_term or candidate.primary_term).split()).strip()
        if not canonical_term:
            raise ValueError("草稿规范名称不能为空。")
        duplicates = _duplicate_matches(target_type, canonical_term)
        if duplicates and not confirm_new:
            raise ValueError("发现可能的已有实体，请先选择 Match Existing，或明确确认创建新的草稿。")
        terms = _clean_terms([canonical_term, *(candidate.terms or [])])
        if target_type == "person":
            person = Person.objects.create(
                preferred_name=canonical_term,
                sort_name=canonical_term,
                authority_status=Person.AuthorityStatus.DRAFT,
            )
            ScholarProfile.objects.get_or_create(
                person=person,
                defaults={
                    "slug": _unique_slug(ScholarProfile, canonical_term),
                    "short_description": "待补充的馆藏人物档案",
                    "editorial_status": "draft",
                },
            )
            for term in terms:
                if normalize_term(term) == normalize_term(canonical_term):
                    continue
                PersonNameVariant.objects.get_or_create(
                    person=person,
                    normalized_name=normalize_term(term),
                    defaults={
                        "name": term,
                        "language": detect_language(term),
                        "variant_type": "alias",
                        "source_kind": PersonNameVariant.SourceKind.PDF_EVIDENCE,
                        "source_note": f"来自未知实体候选 {candidate.id}，尚未核验",
                        "displayable": False,
                        "is_verified": False,
                        "created_by": actor,
                    },
                )
            draft_type, draft_id = "person", person.id
        elif target_type == "knowledge_node":
            allowed = {value for value, _label in KnowledgeNode.NodeType.choices}
            node_type = node_type if node_type in allowed else KnowledgeNode.NodeType.CONCEPT
            node = KnowledgeNode.objects.create(
                node_type=node_type,
                canonical_name_zh=canonical_term,
                slug=_unique_slug(KnowledgeNode, canonical_term),
                status="draft",
                created_by=actor,
            )
            for term in terms:
                if normalize_term(term) == normalize_term(canonical_term):
                    continue
                KnowledgeNodeAlias.objects.get_or_create(
                    node=node,
                    normalized_alias=normalize_term(term),
                    defaults={
                        "alias": term,
                        "language": detect_language(term),
                        "alias_type": KnowledgeNodeAlias.AliasType.ALIAS,
                        "source_kind": KnowledgeNodeAlias.SourceKind.PDF_EVIDENCE,
                        "is_verified": False,
                        "created_by": actor,
                    },
                )
            draft_type, draft_id = "knowledge_node", node.id
        else:
            topic = Topic.objects.create(
                name=canonical_term,
                slug=_unique_slug(Topic, canonical_term),
                editorial_status="draft",
            )
            draft_type, draft_id = "topic", topic.id
        candidate.entity_type = target_type
        candidate.draft_entity_type = draft_type
        candidate.draft_entity_id = draft_id
        candidate.status = NewAuthorityCandidate.Status.DRAFT_CREATED
        candidate.review_reason = str(reason or "管理员创建草稿实体")[:4000]
    else:
        raise ValueError("未知新实体候选审核动作。")

    candidate.reviewed_by = actor
    candidate.reviewed_at = now
    candidate.save(
        update_fields=[
            "entity_type",
            "matched_entity_type",
            "matched_entity_id",
            "draft_entity_type",
            "draft_entity_id",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "updated_at",
        ]
    )
    AuditEvent.objects.create(
        actor=actor,
        action=f"new_authority_candidate_{action}",
        object_type="NewAuthorityCandidate",
        object_id=str(candidate.id),
        after={
            "status": candidate.status,
            "entity_type": candidate.entity_type,
            "matched_entity_id": str(candidate.matched_entity_id or ""),
            "draft_entity_id": str(candidate.draft_entity_id or ""),
        },
        reason=candidate.review_reason,
    )
    return candidate
