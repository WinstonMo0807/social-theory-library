from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import re
from typing import Any, Iterable

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    Contribution,
    DocumentRevision,
    EvidenceSpan,
    Page,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.research.evidence_pack import create_evidence_pack
from catalog.services.research.library_synthesis import (
    build_library_synthesis_evidence_pack,
    schedule_library_synthesis,
)
from catalog.services.research.task_profiles import resolve_task_profile
from ingestion.models import UploadBatch, UploadItem
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.metadata import Candidate
from ingestion.services.reconciliation import persist_resolution_candidates


FRONT_MATTER_VERSION = "front-matter-v1"
FRONT_PAGE_LIMIT = 20
BACK_PAGE_LIMIT = 5
MAX_TARGETED_OCR_PAGES = 8

ISBN_RE = re.compile(
    r"(?<!\d)(?:ISBN(?:-1[03])?\s*[:：]?\s*)?((?:97[89][\s-]*)?\d(?:[\s-]*\d){8,11}[\s-]*[\dXx])(?!\d)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(?<!\d)((?:18|19|20)\d{2})(?:[年./-](\d{1,2}))?(?:[月./-](\d{1,2}))?日?",
    re.IGNORECASE,
)

ROLE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "cip": (
        re.compile(r"图书在版编目|圖書在版編目|\bCIP\s*(?:data|数据|資料)", re.IGNORECASE),
    ),
    "copyright_page": (
        re.compile(r"版权所有|版權所有|copyright|all rights reserved", re.IGNORECASE),
        re.compile(r"(?:第\s*[一二三四五六七八九十百\d]+\s*版|印次|印刷|定价|定價)"),
    ),
    "translator_page": (
        re.compile(r"译者|譯者|翻译|翻譯|translated\s+by|translator", re.IGNORECASE),
    ),
    "table_of_contents": (
        re.compile(r"(?:^|\n)\s*(?:目录|目錄|目次|contents|table\s+of\s+contents)\s*(?:\n|$)", re.IGNORECASE),
    ),
    "publisher_imprint": (
        re.compile(r"出版社|出版公司|出版集团|出版集團|\b(?:university\s+)?press\b", re.IGNORECASE),
        re.compile(r"出版发行|出版發行|publisher|imprint", re.IGNORECASE),
    ),
}

TITLE_EXCLUSIONS = re.compile(
    r"ISBN|CIP|版权所有|版權所有|copyright|目录|目錄|contents|出版社|出版公司|"
    r"定价|定價|印刷|责任编辑|責任編輯|图书在版编目|圖書在版編目",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class FrontMatterPage:
    page_id: str
    page_number: int
    printed_page_label: str
    roles: tuple[str, ...]
    text_source: str
    quality: float
    text_length: int
    evidence_span_ids: tuple[str, ...]


def _compact(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _lines(value: str) -> list[str]:
    return [line for line in (_compact(row) for row in str(value or "").splitlines()) if line]


def _page_roles(page: Page) -> tuple[str, ...]:
    text = str(page.normalized_text or page.text or "")
    roles = [
        role
        for role, patterns in ROLE_PATTERNS.items()
        if any(pattern.search(text[:16000]) for pattern in patterns)
    ]
    line_count = len(_lines(text[:8000]))
    if (
        page.index <= 6
        and 1 <= line_count <= 45
        and "table_of_contents" not in roles
        and not TITLE_EXCLUSIONS.search("\n".join(_lines(text[:1200])[:3]))
    ):
        roles.append("title_page")
    if page.index <= FRONT_PAGE_LIMIT and "front_matter" not in roles:
        roles.append("front_matter")
    return tuple(dict.fromkeys(roles))


def _page_quality(page: Page, spans: Iterable[EvidenceSpan]) -> float:
    values = [float(page.confidence or 0)]
    values.extend(float(span.quality or 0) for span in spans)
    populated = bool(_compact(page.normalized_text or page.text))
    score = sum(values) / max(len(values), 1)
    if not populated:
        score = 0.0
    return round(max(0.0, min(1.0, score)), 4)


def _page_window(asset: Asset) -> list[Page]:
    page_count = int(asset.page_count or 0)
    front = set(range(1, min(page_count, FRONT_PAGE_LIMIT) + 1))
    back_start = max(1, page_count - BACK_PAGE_LIMIT + 1)
    indexes = front | set(range(back_start, page_count + 1))
    return list(asset.pages.filter(index__in=indexes).order_by("index"))


def classify_front_matter_pages(revision: DocumentRevision) -> list[FrontMatterPage]:
    spans_by_page: dict[str, list[EvidenceSpan]] = {}
    for span in revision.evidence_spans.filter(is_stale=False).select_related("page"):
        spans_by_page.setdefault(str(span.page_id), []).append(span)

    results: list[FrontMatterPage] = []
    for page in _page_window(revision.asset):
        spans = spans_by_page.get(str(page.id), [])
        roles = _page_roles(page)
        if not roles:
            continue
        results.append(
            FrontMatterPage(
                page_id=str(page.id),
                page_number=page.index,
                printed_page_label=page.printed_label,
                roles=roles,
                text_source=page.text_source,
                quality=_page_quality(page, spans),
                text_length=len(_compact(page.normalized_text or page.text)),
                evidence_span_ids=tuple(str(span.id) for span in spans),
            )
        )
    return results


def _span_for_quote(
    page: Page,
    spans: list[EvidenceSpan],
    quote: str,
) -> EvidenceSpan | None:
    folded = _compact(quote).casefold()
    if folded:
        for span in spans:
            if folded in _compact(span.normalized_text or span.original_text).casefold():
                return span
    return spans[0] if spans else None


def _candidate_evidence(
    *,
    revision: DocumentRevision,
    page: Page,
    spans: list[EvidenceSpan],
    quote: str,
    page_role: str,
) -> dict[str, Any]:
    span = _span_for_quote(page, spans, quote)
    compact_quote = _compact(quote)[:1200]
    return {
        "document_revision_id": str(revision.id),
        "document_revision": revision.revision,
        "evidence_span_id": str(span.id) if span else "",
        "asset_id": str(revision.asset_id),
        "page": page.index,
        "printed_page_label": page.printed_label,
        "bbox": list(span.bbox or []) if span else [],
        "text_quote": compact_quote,
        "page_role": page_role,
        "extraction_method": span.extraction_method if span else revision.extraction_method,
        "quality": float(span.quality if span else page.confidence or 0),
        "reader_url": f"/reader/{revision.asset_id}?page={page.index}",
    }


def _candidate_source(page: Page) -> str:
    if page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}:
        return "front_matter_ocr_v1"
    return "front_matter_native_v1"


def _split_people(value: str) -> list[str]:
    value = re.sub(r"\([^)]{0,30}\)|（[^）]{0,30}）", " ", str(value or ""))
    output = []
    for part in re.split(r"[、,，;；/&]|\s+(?:and|与|和)\s+", value, flags=re.IGNORECASE):
        name = _compact(part).strip("：:著编編译譯校 ")
        if 1 < len(name) <= 100 and name not in output:
            output.append(name)
    return output


def _normalized_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", str(value or "")).upper()


def _iso_date(match: re.Match[str]) -> str:
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return date(year, 1, 1).isoformat()


def extract_front_matter_candidates(revision: DocumentRevision) -> list[Candidate]:
    spans_by_page: dict[str, list[EvidenceSpan]] = {}
    for span in revision.evidence_spans.filter(is_stale=False).select_related("page"):
        spans_by_page.setdefault(str(span.page_id), []).append(span)

    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    def add(
        field_name: str,
        value: Any,
        *,
        page: Page,
        quote: str,
        role: str,
        confidence: float,
        source: str | None = None,
    ) -> None:
        if value in (None, "", [], {}):
            return
        key = (field_name, repr(value).casefold())
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            Candidate(
                field_name,
                value,
                source or _candidate_source(page),
                confidence,
                _candidate_evidence(
                    revision=revision,
                    page=page,
                    spans=spans_by_page.get(str(page.id), []),
                    quote=quote,
                    page_role=role,
                ),
            )
        )

    language_sample: list[str] = []
    for page in _page_window(revision.asset):
        text = str(page.normalized_text or page.text or "")
        if not _compact(text):
            continue
        roles = _page_roles(page)
        lines = _lines(text[:18000])
        language_sample.append(text[:5000])

        if "title_page" in roles:
            explicit_original = re.search(
                r"(?:原书名|原書名|英文原名|original\s+title)\s*[:：]\s*([^\n]{2,300})",
                text,
                re.IGNORECASE,
            )
            if explicit_original:
                add(
                    "original_title",
                    _compact(explicit_original.group(1)),
                    page=page,
                    quote=explicit_original.group(0),
                    role="title_page",
                    confidence=0.93,
                )
            explicit_subtitle = re.search(
                r"(?:副标题|副標題|subtitle)\s*[:：]\s*([^\n]{2,300})",
                text,
                re.IGNORECASE,
            )
            if explicit_subtitle:
                add(
                    "subtitle",
                    _compact(explicit_subtitle.group(1)),
                    page=page,
                    quote=explicit_subtitle.group(0),
                    role="title_page",
                    confidence=0.91,
                )
            title_lines = [
                line
                for line in lines[:12]
                if 2 <= len(line) <= 240
                and not TITLE_EXCLUSIONS.search(line)
                and not DATE_RE.fullmatch(line)
                and not re.search(r"(?:作者|著者|译者|譯者|translated\s+by)\s*[:：]", line, re.IGNORECASE)
            ]
            if title_lines:
                title = title_lines[0]
                if "：" in title or ": " in title:
                    main, subtitle = re.split(r"\s*[：:]\s*", title, maxsplit=1)
                    if 2 <= len(main) <= 180 and 2 <= len(subtitle) <= 240:
                        add("title", main, page=page, quote=title, role="title_page", confidence=0.86)
                        add("subtitle", subtitle, page=page, quote=title, role="title_page", confidence=0.82)
                    else:
                        add("title", title, page=page, quote=title, role="title_page", confidence=0.82)
                else:
                    add("title", title, page=page, quote=title, role="title_page", confidence=0.82)

        author_values: list[str] = []
        translator_values: list[str] = []
        for line in lines[:100]:
            author_match = re.match(
                r"^(?:作者|著者|编著|編著|主编|主編|authors?)\s*[:：]?\s*(.{2,180})$",
                line,
                re.IGNORECASE,
            ) or re.match(r"^(.{2,120}?)\s+(?:著|编著|編著|主编|主編)$", line)
            if author_match:
                author_values.extend(_split_people(author_match.group(1)))
            translator_match = re.match(
                r"^(?:译者|譯者|翻译|翻譯|translated\s+by|translator)\s*[:：]?\s*(.{2,180})$",
                line,
                re.IGNORECASE,
            ) or re.match(r"^(.{2,120}?)\s+(?:译|譯)$", line)
            if translator_match:
                translator_values.extend(_split_people(translator_match.group(1)))
        author_values = list(dict.fromkeys(author_values))
        translator_values = list(dict.fromkeys(translator_values))
        if author_values:
            quote = next((line for line in lines if any(name in line for name in author_values)), author_values[0])
            add("authors", author_values, page=page, quote=quote, role="title_page", confidence=0.9)
        if translator_values:
            quote = next((line for line in lines if any(name in line for name in translator_values)), translator_values[0])
            add("translators", translator_values, page=page, quote=quote, role="translator_page", confidence=0.92)

        if roles and set(roles) & {"copyright_page", "cip", "publisher_imprint", "front_matter"}:
            for match in ISBN_RE.finditer(text[:16000]):
                isbn = _normalized_isbn(match.group(1))
                if len(isbn) not in {10, 13}:
                    continue
                add("isbn", isbn, page=page, quote=match.group(0), role="cip" if "cip" in roles else "copyright_page", confidence=0.97)
                add(f"isbn{len(isbn)}", isbn, page=page, quote=match.group(0), role="cip" if "cip" in roles else "copyright_page", confidence=0.97)

            publisher_match = re.search(
                r"([\w\u3400-\u9fff·&（）()\- ]{2,100}(?:出版社|出版公司|出版集团|出版集團))",
                text,
            ) or re.search(
                r"([^\n]{2,100}\b(?:University\s+)?Press\b)",
                text,
                re.IGNORECASE,
            )
            if publisher_match:
                add(
                    "publisher",
                    _compact(publisher_match.group(1)),
                    page=page,
                    quote=publisher_match.group(0),
                    role="publisher_imprint",
                    confidence=0.91,
                )

            place_match = re.search(
                r"(?:出版地|出版地点|出版地點|place\s+of\s+publication)\s*[:：]\s*([^\n,，;；]{2,80})",
                text,
                re.IGNORECASE,
            )
            if place_match:
                add(
                    "publication_place",
                    _compact(place_match.group(1)),
                    page=page,
                    quote=place_match.group(0),
                    role="publisher_imprint",
                    confidence=0.9,
                )

            edition_match = re.search(
                r"(?:第\s*[一二三四五六七八九十百\d]+\s*版(?:\s*修订版|\s*修訂版)?|"
                r"(?:first|second|third|fourth|revised|\d+(?:st|nd|rd|th))\s+edition)",
                text,
                re.IGNORECASE,
            )
            if edition_match:
                add(
                    "version_label",
                    _compact(edition_match.group(0)),
                    page=page,
                    quote=edition_match.group(0),
                    role="copyright_page",
                    confidence=0.9,
                )

            series_match = re.search(
                r"(?:丛书名|叢書名|丛书|叢書|series)\s*[:：]\s*([^\n]{2,160})",
                text,
                re.IGNORECASE,
            )
            if series_match:
                add(
                    "series",
                    _compact(series_match.group(1)),
                    page=page,
                    quote=series_match.group(0),
                    role="cip" if "cip" in roles else "front_matter",
                    confidence=0.87,
                )

            date_matches = list(DATE_RE.finditer(text[:16000]))
            if date_matches:
                current = max(date_matches, key=lambda row: int(row.group(1)))
                add(
                    "publication_year",
                    int(current.group(1)),
                    page=page,
                    quote=current.group(0),
                    role="copyright_page" if "copyright_page" in roles else "cip",
                    confidence=0.83,
                )
                add(
                    "publication_date",
                    _iso_date(current),
                    page=page,
                    quote=current.group(0),
                    role="copyright_page" if "copyright_page" in roles else "cip",
                    confidence=0.8,
                )

            first_publication = re.search(
                r"(?:首次出版|初版|first\s+published)\D{0,20}((?:18|19|20)\d{2}(?:[年./-]\d{1,2})?(?:[月./-]\d{1,2})?日?)",
                text,
                re.IGNORECASE,
            )
            if first_publication:
                parsed = DATE_RE.search(first_publication.group(1))
                if parsed:
                    add(
                        "first_publication_date",
                        _iso_date(parsed),
                        page=page,
                        quote=first_publication.group(0),
                        role="copyright_page",
                        confidence=0.88,
                    )

        original_language = re.search(
            r"(?:原文语种|原文語種|original\s+language)\s*[:：]\s*([^\n,，;；]{2,40})",
            text,
            re.IGNORECASE,
        )
        if original_language:
            add(
                "original_language",
                _compact(original_language.group(1)),
                page=page,
                quote=original_language.group(0),
                role="copyright_page",
                confidence=0.9,
            )

        abstract_match = re.search(
            r"(?:^|\n)\s*(?:摘要|內容提要|内容提要|abstract)\s*[:：]?\s*"
            r"(.{60,5000}?)(?=\n\s*(?:关键词|關鍵詞|keywords?|目录|目錄|contents)\s*[:：]?)",
            text[:24000],
            re.IGNORECASE | re.DOTALL,
        )
        if abstract_match:
            abstract = _compact(abstract_match.group(1))
            add(
                "abstract",
                abstract,
                page=page,
                quote=abstract_match.group(0)[:1200],
                role="front_matter",
                confidence=0.92,
                source="source_abstract",
            )

    sample = "\n".join(language_sample)[:30000]
    if sample:
        latin = sum(character.isascii() and character.isalpha() for character in sample)
        cjk = sum("\u3400" <= character <= "\u9fff" for character in sample)
        language = "en" if latin > max(150, cjk * 2) else "zh-CN"
        first_page = _page_window(revision.asset)[0]
        add(
            "language",
            language,
            page=first_page,
            quote=_compact(first_page.normalized_text or first_page.text)[:600],
            role="front_matter",
            confidence=0.82,
        )
    return candidates


def missing_bibliographic_fields(asset: Asset) -> list[str]:
    edition = asset.edition
    work = edition.work
    missing: list[str] = []
    for field_name in (
        "title",
        "subtitle",
        "original_title",
        "abstract",
        "language",
        "original_language",
        "first_publication_date",
    ):
        if not getattr(work, field_name, None):
            missing.append(field_name)
    for field_name in (
        "version_label",
        "publication_date",
        "publication_year",
        "publisher",
        "publication_place",
        "isbn10",
        "isbn13",
        "series",
    ):
        if not getattr(edition, field_name, None):
            missing.append(field_name)
    approved_roles = set(
        edition.contributions.filter(approved=True).values_list("role", flat=True)
    )
    if Contribution.Role.AUTHOR not in approved_roles:
        missing.append("authors")
    if Contribution.Role.TRANSLATOR not in approved_roles:
        missing.append("translators")
    return missing


def targeted_front_matter_ocr_pages(
    revision: DocumentRevision,
    *,
    missing_fields: Iterable[str] | None = None,
) -> list[int]:
    missing = set(missing_fields or missing_bibliographic_fields(revision.asset))
    if not missing:
        return []
    page_limit = 6 if missing <= {"title", "subtitle", "original_title", "authors", "translators"} else 15
    assessment = revision.quality_assessments.order_by("-created_at").first()
    critical = {int(value) for value in (assessment.critical_pages if assessment else []) if str(value).isdigit()}
    candidates: list[tuple[int, int]] = []
    for page in _page_window(revision.asset):
        if page.index > page_limit and page.index not in critical:
            continue
        low_quality = (
            page.index in critical
            or not _compact(page.normalized_text or page.text)
            or float(page.confidence or 0) < 0.68
        )
        if not low_quality or page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}:
            continue
        priority = 0 if page.index in critical else 1
        candidates.append((priority, page.index))
    return [index for _priority, index in sorted(candidates)[:MAX_TARGETED_OCR_PAGES]]


def _update_ocr_targets(asset: Asset, page_indexes: Iterable[int]) -> list[int]:
    requested = {int(value) for value in page_indexes if int(value) > 0}
    if not requested:
        return []
    details = dict(asset.validation_details or {})
    existing = {
        int(value)
        for value in details.get("ocr_required_page_indexes", [])
        if str(value).isdigit() and int(value) > 0
    }
    combined = sorted(existing | requested)
    details.update(
        {
            "ocr_required_page_indexes": combined,
            "front_matter_ocr_page_indexes": sorted(requested),
            "front_matter_ocr_version": FRONT_MATTER_VERSION,
            "front_matter_ocr_requested_at": timezone.now().isoformat(),
        }
    )
    asset.validation_details = details
    asset.save(update_fields=["validation_details", "updated_at"])
    return combined


def build_bibliographic_evidence_pack(
    revision: DocumentRevision,
    *,
    research_run=None,
    actor=None,
):
    page_ids = {row.page_id for row in classify_front_matter_pages(revision) if row.evidence_span_ids}
    spans = list(
        revision.evidence_spans.filter(page_id__in=page_ids, is_stale=False)
        .select_related("document_revision__asset__edition__work", "page")
        .prefetch_related("document_revision__asset__edition__contributions__person")
        .order_by("page_number", "start_offset")[:80]
    )
    if not spans:
        return None
    envelopes = [evidence_span_envelope(span).as_dict() for span in spans]
    return create_evidence_pack(
        task_profile=resolve_task_profile("bibliographic_identity"),
        envelopes=envelopes,
        retrieval_snapshot={
            "profile": "front_matter",
            "version": FRONT_MATTER_VERSION,
            "page_numbers": sorted({span.page_number for span in spans}),
            "local_first": True,
        },
        subject_type="edition",
        subject_id=str(revision.asset.edition_id),
        research_run=research_run,
        actor=actor,
    )


@transaction.atomic
def run_front_matter_intelligence(
    asset: Asset,
    *,
    upload_item: UploadItem | None = None,
    actor=None,
    schedule_ocr: bool = False,
) -> dict[str, Any]:
    if asset.kind != Asset.Kind.NORMALIZED:
        raise ValueError("FrontMatterIntelligence 只读取规范阅读 Asset，不修改 ORIGINAL PDF。")
    revision = (
        DocumentRevision.objects.select_for_update()
        .filter(asset=asset, is_active=True)
        .order_by("-revision")
        .first()
    )
    if revision is None:
        return {
            "status": "no_reliable_candidate",
            "reason": "active_document_revision_missing",
            "candidates": 0,
            "ocr_page_indexes": [],
        }

    pages = classify_front_matter_pages(revision)
    candidates = extract_front_matter_candidates(revision)
    candidate_stats = {"added": 0, "updated": 0, "preserved": 0, "superseded": 0}
    if upload_item is not None:
        candidate_stats = persist_metadata_candidates(
            upload_item,
            candidates,
            selected={},
            supersede_sources={"front_matter_native_v1", "front_matter_ocr_v1", "source_abstract"},
        )
        for candidate in candidates:
            role = {
                "authors": Contribution.Role.AUTHOR,
                "translators": Contribution.Role.TRANSLATOR,
            }.get(candidate.field_name)
            if role is None:
                continue
            names = candidate.value if isinstance(candidate.value, list) else [candidate.value]
            for name in names:
                normalized_name = _compact(str(name or ""))
                if not normalized_name:
                    continue
                persist_resolution_candidates(
                    upload_item,
                    target_type="person",
                    source_name=normalized_name,
                    supporting_properties={
                        "research_field": f"contributors.{candidate.field_name}",
                        "contribution_role": role,
                        "candidate_group": "in_library_evidence",
                    },
                )
    evidence_pack = build_bibliographic_evidence_pack(revision, actor=actor)
    missing = missing_bibliographic_fields(asset)
    ocr_allowed = not (
        upload_item is not None
        and upload_item.batch.ocr_strategy == UploadBatch.OcrStrategy.SKIP
    )
    targeted_pages = (
        targeted_front_matter_ocr_pages(revision, missing_fields=missing)
        if ocr_allowed
        else []
    )
    combined_targets = _update_ocr_targets(asset, targeted_pages) if targeted_pages else []

    queued_job = None
    if schedule_ocr and targeted_pages and ocr_allowed:
        from ingestion.services.processing import queue_ocr_job

        queued_job = queue_ocr_job(asset, upload_item=upload_item, actor=actor)

    source_abstract = next(
        (candidate for candidate in candidates if candidate.field_name == "abstract" and candidate.source == "source_abstract"),
        None,
    )
    if source_abstract:
        abstract_status = {
            "kind": "source_abstract",
            "reason": "source_abstract_found",
            "evidence_span_id": str(source_abstract.evidence.get("evidence_span_id") or ""),
        }
    elif "abstract" not in missing:
        abstract_status = {
            "kind": "current_value",
            "reason": "canonical_abstract_already_present",
        }
    else:
        synthesis_pack = build_library_synthesis_evidence_pack(
            revision,
            field_name="abstract",
            actor=actor,
        )
        if synthesis_pack is not None and upload_item is not None:
            synthesis = schedule_library_synthesis(
                synthesis_pack,
                upload_item=upload_item,
                field_name="abstract",
            )
            abstract_status = {
                "kind": "library_synthesis",
                "label": "馆藏综合",
                "reason": (
                    "waiting_for_ai_capability"
                    if synthesis["status"] == "waiting_for_capability"
                    else "library_synthesis_scheduled"
                ),
                **synthesis,
            }
        else:
            abstract_status = {
                "kind": "no_reliable_candidate",
                "reason": (
                    "library_synthesis_requires_upload_context"
                    if synthesis_pack is not None
                    else "insufficient_collection_evidence_for_library_synthesis"
                ),
                "evidence_available": bool(synthesis_pack or evidence_pack),
                "publication_blocking": False,
            }
    result = {
        "status": "ready" if candidates else "no_reliable_candidate",
        "reason": "front_matter_candidates_found" if candidates else "front_matter_evidence_did_not_support_fields",
        "revision_id": str(revision.id),
        "revision": revision.revision,
        "page_roles": [asdict(row) for row in pages],
        "candidate_count": len(candidates),
        "candidate_fields": sorted({candidate.field_name for candidate in candidates}),
        "candidate_stats": candidate_stats,
        "missing_fields": missing,
        "evidence_pack_id": str(evidence_pack.id) if evidence_pack else "",
        "abstract": abstract_status,
        "ocr_page_indexes": targeted_pages,
        "combined_ocr_targets": combined_targets,
        "ocr_job_id": str(queued_job.id) if queued_job else "",
        "publication_blocking": False,
    }
    if upload_item is not None:
        summary = dict(upload_item.preflight_summary or {})
        summary["front_matter_intelligence"] = {
            key: result[key]
            for key in (
                "status",
                "reason",
                "revision_id",
                "candidate_count",
                "candidate_fields",
                "missing_fields",
                "evidence_pack_id",
                "abstract",
                "ocr_page_indexes",
                "publication_blocking",
            )
        }
        upload_item.preflight_summary = summary
        upload_item.save(update_fields=["preflight_summary", "updated_at"])
    return result
