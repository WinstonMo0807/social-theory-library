"""Create evidence-backed theory suggestions from an already parsed PDF.

This service deliberately works on persisted pages and passages.  It never uses
the upload filename and it never publishes a relation.  The ingestion worker can
therefore call it after text extraction without introducing another OCR path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Page,
    Passage,
    RelationReviewStatus,
    RelationStrength,
    TheoryReviewTask,
    WorkNodeRelation,
)


SOURCE_NAME = "normalized_theory_candidate_v1"
MAX_NODE_CANDIDATES = 8
MAX_EVIDENCE_PER_NODE = 3


@dataclass(frozen=True)
class _Occurrence:
    passage_id: object
    page: int
    printed_label: str
    chapter_title: str
    text: str
    bbox: list[float]
    page_source: str
    page_confidence: float
    matched_terms: tuple[str, ...]
    term_count: int


def _fold(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _terms_for_node(node: KnowledgeNode) -> list[str]:
    values = [node.canonical_name_zh, node.canonical_name_en]
    values.extend(alias.alias for alias in node.aliases.all())
    terms: list[str] = []
    seen = set()
    for value in values:
        term = _fold(value)
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return sorted(terms, key=len, reverse=True)


def _excerpt(text: str, matched_terms: tuple[str, ...], limit: int = 620) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    folded = compact.casefold()
    positions = [folded.find(term) for term in matched_terms if folded.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(compact), start + limit)
    prefix = "……" if start else ""
    suffix = "……" if end < len(compact) else ""
    return f"{prefix}{compact[start:end].strip()}{suffix}"


def _relation_role(work_title: str, node_terms: list[str], occurrences: list[_Occurrence]) -> str:
    title = _fold(work_title)
    combined = " ".join(item.text.casefold() for item in occurrences[:6])
    if any(term in title for term in node_terms):
        return WorkNodeRelation.Role.SYSTEMATIC_EXPOSITION

    critique_cues = (
        "批判", "批评", "反思", "局限", "质疑", "争论", "critique", "criticism",
        "limitation", "challenge", "against",
    )
    application_cues = (
        "运用", "采用", "基于", "研究发现", "访谈", "调查", "样本", "案例", "经验研究",
        "apply", "using", "empirical", "interview", "survey", "case study",
    )
    development_cues = (
        "发展", "修正", "扩展", "推进", "重构", "提出", "进一步", "develop", "revise",
        "extend", "elaborate", "reconstruct",
    )
    comparison_cues = ("比较", "对照", "异同", "compare", "comparison", "versus")
    if any(cue in combined for cue in critique_cues):
        return WorkNodeRelation.Role.CRITIQUE
    if any(cue in combined for cue in application_cues):
        return WorkNodeRelation.Role.EMPIRICAL_APPLICATION
    if any(cue in combined for cue in development_cues):
        return WorkNodeRelation.Role.THEORETICAL_DEVELOPMENT
    if any(cue in combined for cue in comparison_cues):
        return WorkNodeRelation.Role.COMPARATIVE_STUDY
    if len({item.page for item in occurrences}) >= 4 or any(
        any(term in _fold(item.chapter_title) for term in node_terms)
        for item in occurrences
    ):
        return WorkNodeRelation.Role.SYSTEMATIC_EXPOSITION
    return WorkNodeRelation.Role.GENERAL_MENTION


def _confidence(
    *,
    work_title: str,
    node_terms: list[str],
    occurrences: list[_Occurrence],
    asset_page_count: int,
) -> float:
    pages = {item.page for item in occurrences}
    title_match = any(term in _fold(work_title) for term in node_terms)
    chapter_match = any(
        any(term in _fold(item.chapter_title) for term in node_terms)
        for item in occurrences
    )
    term_count = sum(item.term_count for item in occurrences)
    score = 0.34
    score += min(0.22, len(pages) * 0.035)
    score += min(0.13, term_count * 0.012)
    score += 0.18 if title_match else 0
    score += 0.09 if chapter_match else 0
    if asset_page_count and len(pages) / asset_page_count >= 0.08:
        score += 0.06
    return round(min(0.96, score), 3)


def _strong_enough(work_title: str, node_terms: list[str], occurrences: list[_Occurrence]) -> bool:
    if any(term in _fold(work_title) for term in node_terms):
        return True
    pages = {item.page for item in occurrences}
    term_count = sum(item.term_count for item in occurrences)
    return len(pages) >= 2 or term_count >= 3


def _evidence_summary(occurrences: list[_Occurrence]) -> tuple[list[int], str]:
    selected = occurrences[:MAX_EVIDENCE_PER_NODE]
    pages = sorted({item.page for item in selected})
    parts = []
    for item in selected:
        label = f"PDF 第 {item.page} 页"
        if item.chapter_title:
            label += f"，{item.chapter_title}"
        parts.append(f"{label}\n{_excerpt(item.text, item.matched_terms)}")
    return pages, "\n\n".join(parts)


def _unknown_node_candidates(passages: list[Passage], known_terms: set[str]) -> list[dict]:
    """Return conservative, explicit Chinese theory-name candidates.

    A term must recur on at least three pages.  This is intentionally strict so
    an ordinary phrase does not become a suggested knowledge node.
    """

    pattern = re.compile(r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,12}(?:理论|学派|主义))(?![\u4e00-\u9fff])")
    excluded = {
        "社会理论", "理论主义", "理论学派", "研究理论", "本文理论", "相关理论", "一般理论",
    }
    matches: dict[str, list[Passage]] = defaultdict(list)
    for passage in passages:
        for name in set(pattern.findall(passage.text or "")):
            folded = _fold(name)
            if folded in known_terms or name in excluded:
                continue
            matches[name].append(passage)
    result = []
    for name, rows in matches.items():
        pages = sorted({row.page.index for row in rows})
        if len(pages) < 3 or len(rows) < 3:
            continue
        selected = rows[:MAX_EVIDENCE_PER_NODE]
        result.append(
            {
                "name": name,
                "pages": pages[:MAX_EVIDENCE_PER_NODE],
                "text": "\n\n".join(
                    f"PDF 第 {row.page.index} 页\n{_excerpt(row.text, (_fold(name),))}"
                    for row in selected
                ),
                "confidence": round(min(0.78, 0.42 + len(pages) * 0.04), 3),
            }
        )
    return sorted(result, key=lambda item: (-item["confidence"], item["name"]))[:5]


@transaction.atomic
def generate_theory_review_tasks(asset: Asset, *, actor=None, force: bool = False) -> dict:
    """Generate pending theory-review work from a normalized PDF asset."""

    if not getattr(settings, "THEORY_SYSTEM_ENABLED", True):
        return {"enabled": False, "created": 0, "updated": 0, "new_node_tasks": 0}
    if asset.kind != Asset.Kind.NORMALIZED or asset.status != Asset.Status.READY:
        raise ValueError("理论候选只能从已完成文本提取的规范阅读文件生成。")

    passages = list(
        Passage.objects.filter(page__asset=asset)
        .exclude(normalized_text="")
        .select_related("page")
        .order_by("page__index", "order")
    )
    if not passages:
        return {"enabled": True, "created": 0, "updated": 0, "new_node_tasks": 0}

    nodes = list(
        KnowledgeNode.objects.filter(status=KnowledgePublicationStatus.PUBLISHED)
        .prefetch_related("aliases")
        .order_by("sort_order", "canonical_name_zh")
    )
    known_terms: set[str] = set()
    scored: list[tuple[float, KnowledgeNode, list[str], list[_Occurrence]]] = []
    for node in nodes:
        terms = _terms_for_node(node)
        known_terms.update(terms)
        if not terms:
            continue
        occurrences: list[_Occurrence] = []
        for passage in passages:
            folded = (passage.normalized_text or _fold(passage.text)).casefold()
            matched = tuple(term for term in terms if term in folded)
            if not matched:
                continue
            occurrences.append(
                _Occurrence(
                    passage_id=passage.id,
                    page=passage.page.index,
                    printed_label=passage.page.printed_label,
                    chapter_title=passage.page.chapter_title,
                    text=passage.text,
                    bbox=passage.bbox_union,
                    page_source=passage.page.text_source,
                    page_confidence=passage.page.confidence,
                    matched_terms=matched,
                    term_count=sum(folded.count(term) for term in matched),
                )
            )
        if not occurrences or not _strong_enough(asset.edition.work.title, terms, occurrences):
            continue
        confidence = _confidence(
            work_title=asset.edition.work.title,
            node_terms=terms,
            occurrences=occurrences,
            asset_page_count=asset.page_count,
        )
        occurrences.sort(
            key=lambda item: (
                -int(bool(item.chapter_title)),
                -item.term_count,
                item.page,
            )
        )
        scored.append((confidence, node, terms, occurrences))

    created = 0
    updated = 0
    for confidence, node, terms, occurrences in sorted(scored, key=lambda row: -row[0])[:MAX_NODE_CANDIDATES]:
        role = _relation_role(asset.edition.work.title, terms, occurrences)
        if WorkNodeRelation.objects.filter(
            work=asset.edition.work,
            node=node,
            status=KnowledgePublicationStatus.PUBLISHED,
        ).exists():
            continue
        WorkNodeRelation.objects.filter(
            work=asset.edition.work,
            node=node,
            status=KnowledgePublicationStatus.PENDING,
            source=SOURCE_NAME,
        ).exclude(role=role).delete()
        relation, _ = WorkNodeRelation.objects.update_or_create(
            work=asset.edition.work,
            node=node,
            role=role,
            defaults={
                "is_primary": False,
                "strength": (
                    RelationStrength.HIGH if confidence >= 0.82
                    else RelationStrength.MEDIUM if confidence >= 0.62
                    else RelationStrength.LOW
                ),
                "confidence": confidence,
                "status": KnowledgePublicationStatus.PENDING,
                "source": SOURCE_NAME,
                "created_by": actor,
            },
        )
        pages, summary = _evidence_summary(occurrences)
        task = TheoryReviewTask.objects.filter(
            task_type=TheoryReviewTask.TaskType.WORK_NODE,
            work=asset.edition.work,
            file=asset,
            candidate_node=node,
        ).first()
        if task is None:
            task = TheoryReviewTask.objects.create(
                task_type=TheoryReviewTask.TaskType.WORK_NODE,
                work=asset.edition.work,
                file=asset,
                candidate_node=node,
                suggested_relation_type=role,
                confidence=confidence,
                evidence_pages=pages,
                evidence_text=summary,
                status=TheoryReviewTask.TaskStatus.PENDING,
                submitted_at=timezone.now(),
            )
            created += 1
        elif force or task.status in {
            TheoryReviewTask.TaskStatus.PENDING,
            TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
            TheoryReviewTask.TaskStatus.DEFERRED,
            TheoryReviewTask.TaskStatus.INSUFFICIENT_EVIDENCE,
        }:
            task.suggested_relation_type = role
            task.confidence = confidence
            task.evidence_pages = pages
            task.evidence_text = summary
            task.status = TheoryReviewTask.TaskStatus.PENDING
            task.submitted_at = timezone.now()
            task.save(
                update_fields=[
                    "suggested_relation_type", "confidence", "evidence_pages",
                    "evidence_text", "status", "submitted_at", "updated_at",
                ]
            )
            updated += 1

        for occurrence in occurrences[:MAX_EVIDENCE_PER_NODE]:
            EvidenceSnippet.objects.update_or_create(
                work=asset.edition.work,
                file=asset,
                node=node,
                work_node_relation=relation,
                page_number=occurrence.page,
                defaults={
                    "printed_page_label": occurrence.printed_label,
                    "quote": _excerpt(occurrence.text, occurrence.matched_terms),
                    "bounding_box": {"rect": occurrence.bbox} if occurrence.bbox else {},
                    "extraction_method": (
                        EvidenceSnippet.ExtractionMethod.OCR
                        if occurrence.page_source == Page.TextSource.OCR
                        else EvidenceSnippet.ExtractionMethod.TEXT_LAYER
                    ),
                    "ocr_confidence": (
                        occurrence.page_confidence
                        if occurrence.page_source == Page.TextSource.OCR
                        else None
                    ),
                    "semantic_confidence": confidence,
                    "review_status": RelationReviewStatus.SUGGESTED,
                },
            )

    new_node_tasks = 0
    for candidate in _unknown_node_candidates(passages, known_terms):
        existing = TheoryReviewTask.objects.filter(
            task_type=TheoryReviewTask.TaskType.NEW_NODE,
            work=asset.edition.work,
            file=asset,
            suggested_node_name=candidate["name"],
        ).first()
        if existing is None:
            TheoryReviewTask.objects.create(
                task_type=TheoryReviewTask.TaskType.NEW_NODE,
                work=asset.edition.work,
                file=asset,
                suggested_node_name=candidate["name"],
                confidence=candidate["confidence"],
                evidence_pages=candidate["pages"],
                evidence_text=candidate["text"],
                status=TheoryReviewTask.TaskStatus.PENDING,
                submitted_at=timezone.now(),
            )
            new_node_tasks += 1

    return {
        "enabled": True,
        "created": created,
        "updated": updated,
        "new_node_tasks": new_node_tasks,
        "matched_nodes": len(scored),
        "passages_checked": len(passages),
    }
