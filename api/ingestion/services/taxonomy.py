import json
import re

from django.utils.text import slugify

from catalog.models import (
    Discipline,
    RelationReviewStatus,
    Subdiscipline,
    TheorySchool,
    Topic,
    WorkKnowledgeRelation,
)


THEORY_RULES = {
    "马克思主义": ("marxism", ("马克思", "阶级斗争", "历史唯物主义", "资本主义批判", "marxism")),
    "女性主义": ("feminism", ("女性主义", "性别秩序", "父权制", "gender inequality", "feminism")),
    "批判理论": ("critical-theory", ("批判理论", "法兰克福学派", "文化工业", "critical theory")),
    "后殖民理论": ("postcolonial-theory", ("后殖民", "殖民主义", "东方主义", "postcolonial", "colonialism")),
    "符号互动论": ("symbolic-interactionism", ("符号互动", "日常互动", "symbolic interaction", "self-presentation")),
    "结构功能主义": ("structural-functionalism", ("结构功能", "社会系统", "functionalism", "social system")),
    "布迪厄社会学": ("bourdieu-inspired-sociology", ("惯习", "场域", "文化资本", "habitus", "bourdieu")),
}

TOPIC_RULES = {
    "监控与社会": ("surveillance-and-society", ("监控", "规训", "全景敞视", "surveillance", "panopticon")),
    "权力": ("power", ("权力", "支配", "power", "domination")),
    "身份认同": ("identity", ("身份认同", "主体性", "identity", "subjectivity")),
    "社会阶层": ("social-stratification", ("阶级", "阶层", "不平等", "stratification", "inequality")),
    "性别": ("gender", ("性别", "女性", "gender", "feminism")),
    "现代性": ("modernity", ("现代性", "现代化", "modernity", "modernization")),
}


CONTROLLED_VOCABULARY_SOURCE = "controlled_vocabulary_match_v1"
_INACTIVE_EDITORIAL_STATUSES = {"archived", "deleted", "retired", "withdrawn"}


def _normalized_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()


def _term_occurrences(text: str, term: str) -> int:
    folded_term = _normalized_match_text(term)
    if len(folded_term) < 2:
        return 0
    if all(character.isascii() for character in folded_term):
        if len(folded_term) < 4:
            return 0
        return len(re.findall(rf"(?<![\w]){re.escape(folded_term)}(?![\w])", text))
    return text.count(folded_term)


def _candidate_excerpt(text: str, term: str, *, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    position = compact.casefold().find(term.casefold())
    if position < 0:
        return compact[:limit]
    start = max(0, position - limit // 3)
    end = min(len(compact), start + limit)
    return f"{'……' if start else ''}{compact[start:end]}{'……' if end < len(compact) else ''}"


def controlled_vocabulary_candidates(text: str, *, limit_per_field: int = 6):
    """Suggest existing authority records without creating or approving them.

    Only canonical names, foreign names and curated aliases are considered.
    Descriptions and arbitrary web snippets are intentionally excluded so a
    broad topical sentence cannot silently create a formal classification.
    """

    from .metadata import Candidate

    compact = re.sub(r"\s+", " ", text or "").strip()
    folded = compact.casefold()
    if not folded:
        return []
    configs = (
        ("disciplines", Discipline, ("foreign_name",)),
        ("subdisciplines", Subdiscipline, ("foreign_name",)),
        ("theory_schools", TheorySchool, ("foreign_name",)),
        ("topics", Topic, ()),
    )
    results = []
    for field_name, model, additional_fields in configs:
        scored = []
        for entity in model.objects.all().order_by("name"):
            if str(entity.editorial_status or "").casefold() in _INACTIVE_EDITORIAL_STATUSES:
                continue
            terms = [(entity.name, "canonical")]
            for field in additional_fields:
                value = str(getattr(entity, field, "") or "").strip()
                if value:
                    terms.append((value, "foreign_name"))
            terms.extend(
                (str(alias).strip(), "alias")
                for alias in (entity.search_aliases or [])
                if str(alias).strip()
            )
            matches = []
            seen = set()
            for term, source_kind in terms:
                normalized = _normalized_match_text(term)
                if normalized in seen:
                    continue
                seen.add(normalized)
                count = _term_occurrences(folded, term)
                if count:
                    matches.append((term, source_kind, count))
            if not matches:
                continue
            strongest = max(
                matches,
                key=lambda row: (
                    2 if row[1] == "canonical" else 1 if row[1] == "foreign_name" else 0,
                    row[2],
                    len(row[0]),
                ),
            )
            total = sum(row[2] for row in matches)
            base = 0.86 if strongest[1] == "canonical" else 0.81 if strongest[1] == "foreign_name" else 0.76
            confidence = round(min(0.95, base + min(0.09, max(0, total - 1) * 0.025)), 3)
            scored.append(
                Candidate(
                    field_name,
                    entity.name,
                    CONTROLLED_VOCABULARY_SOURCE,
                    confidence,
                    {
                        "entity_id": str(entity.id),
                        "entity_slug": entity.slug,
                        "matched_terms": [row[0] for row in matches[:5]],
                        "occurrence_count": total,
                        "match_scope": "recognized_pdf_text",
                        "evidence_text": _candidate_excerpt(compact, strongest[0]),
                    },
                )
            )
        results.extend(
            sorted(
                scored,
                key=lambda candidate: (-candidate.confidence, str(candidate.value)),
            )[: max(1, min(limit_per_field, 12))]
        )
    return results


def controlled_vocabulary_candidates_for_asset(asset, *, max_chars: int = 250_000):
    chunks = []
    consumed = 0
    for page_index, page_text in asset.pages.order_by("index").values_list("index", "text").iterator():
        page_text = str(page_text or "").strip()
        if not page_text:
            continue
        remaining = max_chars - consumed
        if remaining <= 0:
            break
        chunk = f"PDF 第 {page_index} 页\n{page_text[:remaining]}"
        chunks.append(chunk)
        consumed += len(chunk)
    return controlled_vocabulary_candidates("\n".join(chunks))


def persist_controlled_vocabulary_candidates(upload_item, candidates) -> dict[str, int]:
    """Upsert review-only candidates while preserving all manual metadata."""

    from ingestion.models import MetadataCandidate

    existing = {
        (
            row.field_name,
            json.dumps(row.value, ensure_ascii=False, sort_keys=True, default=str),
        ): row
        for row in upload_item.metadata_candidates.filter(
            source=CONTROLLED_VOCABULARY_SOURCE,
        )
    }
    created = 0
    updated = 0
    for candidate in candidates:
        key = (
            candidate.field_name,
            json.dumps(candidate.value, ensure_ascii=False, sort_keys=True, default=str),
        )
        row = existing.get(key)
        if row is None:
            MetadataCandidate.objects.create(
                upload_item=upload_item,
                field_name=candidate.field_name,
                value=candidate.value,
                source=candidate.source,
                evidence=candidate.evidence,
                confidence=candidate.confidence,
                selected=False,
            )
            created += 1
            continue
        row.evidence = candidate.evidence
        row.confidence = candidate.confidence
        row.selected = False
        row.save(update_fields=["evidence", "confidence", "selected", "updated_at"])
        updated += 1
    return {"created": created, "updated": updated, "total": len(candidates)}


def _matches(text: str, tokens: tuple[str, ...]) -> int:
    folded = text.casefold()
    return sum(1 for token in tokens if token.casefold() in folded)


def _safe_slug(name: str, suggested: str) -> str:
    return suggested or slugify(name) or f"knowledge-{abs(hash(name))}"


def suggest_relations(work, text: str) -> list[WorkKnowledgeRelation]:
    created = []
    theory_matches = [
        (name, slug, _matches(text, tokens))
        for name, (slug, tokens) in THEORY_RULES.items()
        if _matches(text, tokens)
    ]
    topic_matches = [
        (name, slug, _matches(text, tokens))
        for name, (slug, tokens) in TOPIC_RULES.items()
        if _matches(text, tokens)
    ]
    for name, slug, count in sorted(theory_matches, key=lambda item: item[2], reverse=True)[:3]:
        confidence = min(0.97, 0.78 + count * 0.08)
        target, _ = TheorySchool.objects.get_or_create(
            slug=_safe_slug(name, slug),
            defaults={
                "name": name,
                "editorial_status": "draft",
            },
        )
        relation = WorkKnowledgeRelation.objects.filter(
            work=work,
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            theory_school=target,
        ).first()
        if relation is None:
            relation = WorkKnowledgeRelation.objects.create(
                work=work,
                kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
                theory_school=target,
                source="keyword_classifier",
                confidence=confidence,
                approved=False,
                review_status=RelationReviewStatus.SUGGESTED,
                is_primary=not created,
                role="local_mention",
                strength="high" if confidence >= 0.9 else "medium",
            )
        created.append(relation)
    for name, slug, count in sorted(topic_matches, key=lambda item: item[2], reverse=True)[:5]:
        confidence = min(0.97, 0.78 + count * 0.08)
        target, _ = Topic.objects.get_or_create(
            slug=_safe_slug(name, slug),
            defaults={
                "name": name,
                "editorial_status": "draft",
            },
        )
        relation = WorkKnowledgeRelation.objects.filter(
            work=work,
            kind=WorkKnowledgeRelation.Kind.TOPIC,
            topic=target,
        ).first()
        if relation is None:
            relation = WorkKnowledgeRelation.objects.create(
                work=work,
                kind=WorkKnowledgeRelation.Kind.TOPIC,
                topic=target,
                source="keyword_classifier",
                confidence=confidence,
                approved=False,
                review_status=RelationReviewStatus.SUGGESTED,
                is_primary=not any(
                    item.kind == WorkKnowledgeRelation.Kind.TOPIC for item in created
                ),
            )
        created.append(relation)
    return created
