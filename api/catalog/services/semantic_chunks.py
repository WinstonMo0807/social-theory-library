from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, SemanticChunk
from catalog.services.text import normalize_search_text


PARSER_VERSION = "page-blocks-v2"
CHUNK_VERSION = "natural-paragraph-v1"
MIN_CHUNK_CHARS = 180
TARGET_CHUNK_CHARS = 560
MAX_CHUNK_CHARS = 960

PAGE_NUMBER_RE = re.compile(r"^(?:第\s*)?[0-9０-９ivxlcdmIVXLCDM一二三四五六七八九十百]+(?:\s*页)?$")
REFERENCE_HEADING_RE = re.compile(r"^(参考文献|参考资料|bibliography|references|works cited)\s*$", re.I)
TOC_HEADING_RE = re.compile(r"^(目录|目次|contents|table of contents)\s*$", re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\.])\s+(?=[^\s])|(?<=[。！？!?；;])")
LATIN_HYPHEN_RE = re.compile(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])")


@dataclass
class DraftChunk:
    page_start: int
    page_end: int
    chapter_title: str
    section_title: str
    original_text: str
    normalized_text: str
    locators: list[dict] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)


def _clean_block_text(value: str) -> str:
    value = LATIN_HYPHEN_RE.sub("", value or "")
    lines = [line.strip() for line in value.replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        return ""
    output = lines[0]
    for line in lines[1:]:
        if output and line and _is_cjk(output[-1]) and _is_cjk(line[0]):
            output += line
        else:
            output += " " + line
    return re.sub(r"\s+", " ", output).strip()


def _is_cjk(char: str) -> bool:
    return bool(char and "\u3400" <= char <= "\u9fff")


def _looks_like_heading(text: str, block_type: str) -> bool:
    if block_type in {"title", "section_title", "heading", "doc_title"}:
        return True
    if not text or len(text) > 120 or "\n" in text:
        return False
    if text[-1:] in "。！？!?；;，,":
        return False
    if re.match(r"^(第[一二三四五六七八九十百0-9]+[章节编部篇]|[0-9]+(?:\.[0-9]+)*\s+)", text):
        return True
    return len(text) <= 42 and bool(re.search(r"[\u3400-\u9fffA-Za-z]", text))


def _split_long_paragraph(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    sentences = [item.strip() for item in SENTENCE_SPLIT_RE.split(text) if item.strip()]
    if len(sentences) <= 1:
        return [text[index : index + MAX_CHUNK_CHARS] for index in range(0, len(text), MAX_CHUNK_CHARS)]
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > MAX_CHUNK_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _can_merge(previous: DraftChunk, text: str, page_index: int, chapter: str, section: str) -> bool:
    if len(previous.original_text) >= TARGET_CHUNK_CHARS:
        return False
    if len(previous.original_text) + len(text) + 1 > MAX_CHUNK_CHARS:
        return False
    if previous.chapter_title != chapter or previous.section_title != section:
        return False
    if page_index - previous.page_end > 1:
        return False
    return len(previous.original_text) < MIN_CHUNK_CHARS or len(text) < MIN_CHUNK_CHARS


def _dedupe_flags(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _draft_document_id(asset: Asset, draft: DraftChunk, occurrence: int) -> str:
    """Return a stable identity for one locator slot in a chunking revision.

    The identity deliberately excludes extracted text and the embedding model.
    OCR corrections and model changes can therefore update the same database
    row without invalidating reader feedback that points at its UUID.
    """

    first_locator = draft.locators[0] if draft.locators else {}
    bbox = first_locator.get("bbox") if isinstance(first_locator, dict) else []
    bbox_key = json.dumps(bbox or [], ensure_ascii=False, separators=(",", ":"))
    digest_source = "\n".join(
        [
            str(asset.id),
            PARSER_VERSION,
            CHUNK_VERSION,
            str(draft.page_start),
            str(draft.page_end),
            str(first_locator.get("page_index", draft.page_start)),
            bbox_key,
            str(occurrence),
        ]
    )
    return sha256(digest_source.encode("utf-8")).hexdigest()


def build_semantic_chunks(
    asset: Asset,
    *,
    force: bool = False,
    runtime_config: dict | None = None,
) -> list[SemanticChunk]:
    work = asset.edition.work
    model_name = _runtime_model_name(runtime_config)
    existing = list(
        asset.semantic_chunks.filter(
            parser_version=PARSER_VERSION,
            chunk_version=CHUNK_VERSION,
            embedding_model=model_name,
        ).order_by("order")
    )
    if existing and not force:
        return existing

    drafts: list[DraftChunk] = []
    current_section = ""
    in_references = False
    in_toc = False
    pages = asset.pages.prefetch_related("blocks").order_by("index")
    for page in pages:
        chapter = page.chapter_title.strip()
        if chapter:
            current_section = ""
        blocks = list(page.blocks.all())
        if not blocks and page.text.strip():
            blocks = [
                SimpleNamespace(
                    block_type="paragraph",
                    text=page.text,
                    bbox=[],
                    confidence=page.confidence,
                )
            ]
        for block in blocks:
            if block.block_type in {"header", "footer", "page_number"}:
                continue
            text = _clean_block_text(block.text)
            if not text or (len(text) <= 18 and PAGE_NUMBER_RE.fullmatch(text)):
                continue
            if REFERENCE_HEADING_RE.fullmatch(text):
                in_references = True
                in_toc = False
                current_section = text
                continue
            if TOC_HEADING_RE.fullmatch(text):
                in_toc = True
                in_references = False
                current_section = text
                continue
            if _looks_like_heading(text, block.block_type):
                current_section = text
                continue

            flags = []
            if in_references:
                flags.append("references")
            if in_toc:
                flags.append("table_of_contents")
            if block.confidence < 0.72:
                flags.append("low_ocr_confidence")
            for part in _split_long_paragraph(text):
                locator = {
                    "page_index": page.index,
                    "printed_label": page.printed_label,
                    "bbox": block.bbox,
                    "text": part[:500],
                }
                if drafts and _can_merge(drafts[-1], part, page.index, chapter, current_section):
                    previous = drafts[-1]
                    previous.original_text = f"{previous.original_text}\n{part}"
                    previous.normalized_text = normalize_search_text(previous.original_text)
                    previous.page_end = page.index
                    previous.locators.append(locator)
                    previous.quality_flags = _dedupe_flags([*previous.quality_flags, *flags])
                else:
                    drafts.append(
                        DraftChunk(
                            page_start=page.index,
                            page_end=page.index,
                            chapter_title=chapter,
                            section_title=current_section,
                            original_text=part,
                            normalized_text=normalize_search_text(part),
                            locators=[locator],
                            quality_flags=flags,
                        )
                    )

    rows: list[SemanticChunk] = []
    locator_occurrences: dict[tuple[int, int, int, str], int] = {}
    for order, draft in enumerate(drafts):
        previous_text = drafts[order - 1].original_text if order else ""
        next_text = drafts[order + 1].original_text if order + 1 < len(drafts) else ""
        first_locator = draft.locators[0] if draft.locators else {}
        first_page = int(first_locator.get("page_index", draft.page_start))
        bbox_key = json.dumps(
            first_locator.get("bbox") or [],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        locator_slot = (draft.page_start, draft.page_end, first_page, bbox_key)
        occurrence = locator_occurrences.get(locator_slot, 0)
        locator_occurrences[locator_slot] = occurrence + 1
        digest_source = "\n".join(
            [
                str(asset.sha256),
                PARSER_VERSION,
                CHUNK_VERSION,
                model_name,
                draft.chapter_title,
                draft.section_title,
                draft.original_text,
            ]
        )
        rows.append(
            SemanticChunk(
                asset=asset,
                work=work,
                order=order,
                page_start=draft.page_start,
                page_end=draft.page_end,
                chapter_title=draft.chapter_title,
                section_title=draft.section_title,
                paragraph_index=order,
                original_text=draft.original_text,
                normalized_text=draft.normalized_text,
                context_before=previous_text[-700:],
                context_after=next_text[:700],
                language=work.language,
                document_type=work.document_type,
                parser_version=PARSER_VERSION,
                chunk_version=CHUNK_VERSION,
                embedding_model=model_name,
                embedding_version="1",
                document_id=_draft_document_id(asset, draft, occurrence),
                content_hash=sha256(digest_source.encode("utf-8")).hexdigest(),
                locators=draft.locators,
                quality_flags=_dedupe_flags(draft.quality_flags),
            )
        )

    with transaction.atomic():
        existing_rows = list(asset.semantic_chunks.select_for_update())
        existing_by_document_id = {
            row.document_id: row
            for row in existing_rows
            if row.document_id
        }
        reused_ids = set()
        rows_to_create: list[SemanticChunk] = []
        rows_to_update: list[SemanticChunk] = []
        now = timezone.now()

        for row in rows:
            previous = existing_by_document_id.get(row.document_id)
            if previous is None:
                rows_to_create.append(row)
                continue
            row.id = previous.id
            row.updated_at = now
            reused_ids.add(previous.id)
            rows_to_update.append(row)

        stale_rows = [row for row in existing_rows if row.id not in reused_ids]
        for row in existing_rows:
            if row.document_id:
                row.feedback.filter(chunk_document_id="").update(
                    chunk_document_id=row.document_id,
                )

        # The legacy uniqueness rule includes the mutable order. Move locked
        # rows to unused temporary slots before applying a changed locator set,
        # otherwise a new row could collide with the stale row it replaces.
        if existing_rows:
            temporary_order = max(
                [row.order for row in existing_rows]
                + [row.order for row in rows]
                + [0]
            ) + 1
            for offset, row in enumerate(existing_rows):
                row.order = temporary_order + offset
            SemanticChunk.objects.bulk_update(
                existing_rows,
                ["order"],
                batch_size=500,
            )
        if stale_rows:
            SemanticChunk.objects.filter(pk__in=[row.id for row in stale_rows]).delete()
        if rows_to_create:
            SemanticChunk.objects.bulk_create(rows_to_create, batch_size=500)
        if rows_to_update:
            SemanticChunk.objects.bulk_update(
                rows_to_update,
                [
                    "work",
                    "order",
                    "page_start",
                    "page_end",
                    "chapter_title",
                    "section_title",
                    "paragraph_index",
                    "original_text",
                    "normalized_text",
                    "context_before",
                    "context_after",
                    "language",
                    "document_type",
                    "parser_version",
                    "chunk_version",
                    "embedding_model",
                    "embedding_version",
                    "document_id",
                    "content_hash",
                    "locators",
                    "quality_flags",
                    "index_status",
                    "index_error",
                    "indexed_at",
                    "updated_at",
                ],
                batch_size=500,
            )
    return list(asset.semantic_chunks.order_by("order"))


def _current_model_name() -> str:
    from catalog.services.semantic_search import current_semantic_runtime

    return current_semantic_runtime()["model"]


def _runtime_model_name(runtime_config: dict | None) -> str:
    if runtime_config is None:
        return _current_model_name()
    return str(
        runtime_config.get("model_repo_id")
        or runtime_config.get("model")
        or ""
    )
