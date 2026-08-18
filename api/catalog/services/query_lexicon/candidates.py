from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import unicodedata
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    Contribution,
    KnowledgeNode,
    KnowledgeNodeAlias,
    NewAuthorityCandidate,
    Page,
    Person,
    PersonNameVariant,
    QueryLexiconCandidate,
    QueryLexiconCandidateEvidence,
    QueryLexiconEntry,
    SemanticChunk,
    UnknownEntityObservation,
)
from catalog.services.knowledge_growth import persist_unknown_observation, refresh_unknown_candidate
from catalog.services.query_lexicon.normalization import (
    detect_language,
    normalize_language,
    normalize_term,
)
from catalog.services.query_lexicon.resolver import (
    ADMIN_RESOLVABLE,
    resolve_term,
    resolve_terms,
)


EXTRACTION_VERSION = "query-lexicon-pdf-pairs-v1"
MAX_PAIRS_PER_SOURCE = 128
MAX_PAIRS_PER_ASSET = 2500
MAX_RESOLVER_RESULTS = 50
MAX_AUDIT_SAMPLES = 50
MIN_LINKED_CONFIDENCE = 0.58
MIN_AMBIGUOUS_CONFIDENCE = 0.35
REJECTION_FUNNEL_KEYS = (
    "no_canonical_anchor_match",
    "target_not_admin_resolvable",
    "low_trust_generated_only_match",
    "ambiguous_multi_target",
    "person_identity_insufficient",
    "proposed_term_already_exists",
    "invalid_noisy_pair",
    "valid_candidate_created",
)

_CJK_TERM = r"[\u3400-\u9fff·・]{2,24}"
_LATIN_WORD = r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’.\-]*"
_LATIN_TERM = rf"{_LATIN_WORD}(?:\s+{_LATIN_WORD}){{0,5}}"
_ANY_TERM = rf"(?:{_CJK_TERM}|{_LATIN_TERM})"
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_ALPHA_DIGIT_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]\d[A-Za-zÀ-ÖØ-öø-ÿ]")
_REPEATED_PUNCTUATION_RE = re.compile(r"([^\w\s])\1{2,}", re.UNICODE)
_GLOSSARY_RE = re.compile(
    r"术语表|词汇表|索引|index|glossary|terminology|名词解释",
    re.IGNORECASE,
)
_TRIM_CHARACTERS = " \t\r\n\"'“”‘’《》〈〉「」『』,，;；:：。"
_CJK_CONTEXT_MARKERS = (
    "首先要感谢",
    "特别感谢",
    "主要感谢",
    "还要感谢",
    "也要感谢",
    "我要感谢",
    "我们感谢",
    "感谢",
    "致谢",
    "谢谢",
    "得以加入",
    "加入",
)
_CJK_LEADING_CONNECTIVE_RE = re.compile(
    r"^(?:尤其是|特别是|首先|其次|最后|同时|以及|还有|其中|也|并|和)+"
)


@dataclass(frozen=True, slots=True)
class PairPattern:
    name: str
    relation_hint: str
    base_confidence: float
    expression: re.Pattern


@dataclass(frozen=True, slots=True)
class DetectedPair:
    left: str
    right: str
    start: int
    end: int
    method: str
    relation_hint: str
    base_confidence: float


@dataclass(frozen=True, slots=True)
class SourceText:
    text: str
    asset: Asset
    page: Page | None
    semantic_chunk: SemanticChunk | None
    page_number: int | None
    printed_page_label: str
    bbox: list
    ocr_quality: float | None
    quality_flags: tuple[str, ...]
    section_context: str
    locators: tuple[dict, ...]
    page_lookup: dict[int, Page]


@dataclass(frozen=True, slots=True)
class CandidateDecisionResult:
    candidate: QueryLexiconCandidate
    authority_model: str
    authority_id: UUID
    authority_created: bool
    authority_changed: bool
    idempotent: bool


PAIR_PATTERNS = (
    PairPattern(
        "parenthetical_cjk_latin",
        "translation",
        0.58,
        re.compile(
            rf"(?P<left>{_CJK_TERM})\s*[（(\[]\s*(?P<right>{_LATIN_TERM})\s*[）)\]]",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "parenthetical_latin_cjk",
        "translation",
        0.58,
        re.compile(
            rf"(?P<left>{_LATIN_TERM})\s*[（(\[]\s*(?P<right>{_CJK_TERM})\s*[）)\]]",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "parenthetical_latin_latin",
        "alias",
        0.44,
        re.compile(
            rf"(?P<left>{_LATIN_TERM})\s*[（(\[]\s*(?P<right>{_LATIN_TERM})\s*[）)\]]",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "slash_cjk_latin",
        "translation",
        0.46,
        re.compile(
            rf"(?P<left>{_CJK_TERM})\s*[／/]\s*(?P<right>{_LATIN_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "slash_latin_cjk",
        "translation",
        0.46,
        re.compile(
            rf"(?P<left>{_LATIN_TERM})\s*[／/]\s*(?P<right>{_CJK_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "slash_latin_latin",
        "alias",
        0.40,
        re.compile(
            rf"(?P<left>{_LATIN_TERM})\s*[／/]\s*(?P<right>{_LATIN_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "explicit_english_original",
        "translation",
        0.66,
        re.compile(
            rf"(?P<left>{_CJK_TERM})\s*[，,；;]?\s*"
            rf"(?:英文原文(?:为|是)|英文(?:为|是))\s*[:：]?\s*"
            rf"(?P<right>{_LATIN_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "explicit_historical",
        "historical",
        0.66,
        re.compile(
            rf"(?P<left>{_ANY_TERM})\s*(?:又译作|亦译作|旧译作|曾译作|旧称)\s*"
            rf"[\"'“”‘’]?\s*(?P<right>{_ANY_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "explicit_alias",
        "alias",
        0.62,
        re.compile(
            rf"(?P<left>{_ANY_TERM})\s*(?:又称|亦称|也称|别称为)\s*"
            rf"[\"'“”‘’]?\s*(?P<right>{_ANY_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "explicit_abbreviation",
        "abbreviation",
        0.68,
        re.compile(
            rf"(?P<left>{_ANY_TERM})\s*[（(，,]?\s*(?:以下简称|简称为)\s*"
            rf"[\"'“”‘’]?\s*(?P<right>{_ANY_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "glossary_colon_cjk_latin",
        "translation",
        0.52,
        re.compile(
            rf"(?P<left>{_CJK_TERM})\s*[:：=]\s*(?P<right>{_LATIN_TERM})",
            re.IGNORECASE,
        ),
    ),
    PairPattern(
        "glossary_colon_latin_cjk",
        "translation",
        0.52,
        re.compile(
            rf"(?P<left>{_LATIN_TERM})\s*[:：=]\s*(?P<right>{_CJK_TERM})",
            re.IGNORECASE,
        ),
    ),
)


def _stable_json(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(*parts: object) -> str:
    return sha256("\n".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _language_family(value: object) -> str:
    language = str(value or "").casefold()
    if language.startswith("zh"):
        return "zh"
    if language.startswith("en"):
        return "en"
    return "unknown"


def _clean_term(value: object) -> str:
    term = " ".join(
        unicodedata.normalize("NFKC", str(value or ""))
        .strip(_TRIM_CHARACTERS)
        .split()
    )
    if term and _CJK_RE.search(term) and not _LATIN_RE.search(term):
        contextual = False
        for marker in _CJK_CONTEXT_MARKERS:
            if marker in term:
                term = term.rsplit(marker, 1)[-1].strip()
                contextual = True
                break
        term = _CJK_LEADING_CONNECTIVE_RE.sub("", term).strip()
        if contextual and "的" in term:
            suffix = term.rsplit("的", 1)[-1].strip()
            if "·" in suffix and len(suffix) >= 3:
                term = suffix
        for marker in (
            "即所谓",
            "所谓",
            "这里的",
            "这种",
            "提出了",
            "提出",
            "称为",
            "称作",
        ):
            if marker in term:
                term = term.rsplit(marker, 1)[-1].strip()
    return term


def term_noise_reason(value: object) -> str:
    term = _clean_term(value)
    normalized = normalize_term(term)
    if len(normalized) < 2:
        return "too_short"
    if len(normalized) > 120:
        return "too_long"
    if not (_CJK_RE.search(term) or _LATIN_RE.search(term)):
        return "no_letters"
    if any(
        unicodedata.category(character).startswith("C")
        for character in term
    ):
        return "control_character"
    if "�" in term or "\ufffd" in term:
        return "replacement_character"
    if term.startswith(("·", "・")):
        return "leading_middle_dot"
    if _ALPHA_DIGIT_ALPHA_RE.search(term):
        return "digit_inside_word"
    if _REPEATED_PUNCTUATION_RE.search(term):
        return "repeated_punctuation"
    digit_count = sum(character.isdigit() for character in term)
    if digit_count and digit_count / max(len(term), 1) > 0.15:
        return "too_many_digits"
    if _CJK_RE.search(term) and digit_count:
        return "cjk_page_number_noise"
    if _CJK_RE.search(term) and not _LATIN_RE.search(term) and len(term) > 18:
        return "cjk_context_too_long"
    return ""


def extract_explicit_pairs(text: str) -> tuple[list[DetectedPair], dict[str, int]]:
    pairs: list[DetectedPair] = []
    seen: set[tuple[int, int, str, str]] = set()
    audit = defaultdict(int)
    for pattern in PAIR_PATTERNS:
        for match in pattern.expression.finditer(text or ""):
            left = _clean_term(match.group("left"))
            right = _clean_term(match.group("right"))
            left_reason = term_noise_reason(left)
            right_reason = term_noise_reason(right)
            if left_reason or right_reason:
                audit[f"noise:{left_reason or right_reason}"] += 1
                continue
            left_normalized = normalize_term(left)
            right_normalized = normalize_term(right)
            if left_normalized == right_normalized:
                audit["same_normalized_term"] += 1
                continue
            key = (match.start(), match.end(), left_normalized, right_normalized)
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                DetectedPair(
                    left=left,
                    right=right,
                    start=match.start(),
                    end=match.end(),
                    method=pattern.name,
                    relation_hint=pattern.relation_hint,
                    base_confidence=pattern.base_confidence,
                )
            )
            if len(pairs) >= MAX_PAIRS_PER_SOURCE:
                audit["source_pair_limit_reached"] += 1
                return pairs, dict(audit)
    pairs.sort(key=lambda row: (row.start, row.end, row.method))
    return pairs, dict(audit)


def candidate_source_checksum(asset: Asset) -> str:
    chunks = list(
        asset.semantic_chunks.order_by("order").values_list(
            "document_id",
            "original_text",
        )
    )
    if chunks:
        payload = [(str(document_id or ""), str(text or "")) for document_id, text in chunks]
        return _digest("semantic_chunks", _stable_json(payload))
    pages = list(asset.pages.order_by("index").values_list("index", "text"))
    payload = [(int(index), str(text or "")) for index, text in pages]
    return _digest("pages", _stable_json(payload))


def _source_texts(asset: Asset) -> list[SourceText]:
    pages = {
        page.index: page
        for page in asset.pages.order_by("index")
    }
    chunks = list(
        asset.semantic_chunks.select_related("work").order_by("order")
    )
    if chunks:
        output = []
        for chunk in chunks:
            first_locator = (
                chunk.locators[0]
                if isinstance(chunk.locators, list)
                and chunk.locators
                and isinstance(chunk.locators[0], dict)
                else {}
            )
            page_number = int(first_locator.get("page_index") or chunk.page_start)
            page = pages.get(page_number)
            flags = list(chunk.quality_flags or [])
            if page and page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}:
                flags.append("ocr_text")
            output.append(
                SourceText(
                    text=chunk.original_text,
                    asset=asset,
                    page=page,
                    semantic_chunk=chunk,
                    page_number=page_number,
                    printed_page_label=str(
                        first_locator.get("printed_label")
                        or (page.printed_label if page else "")
                    ),
                    bbox=(
                        first_locator.get("bbox")
                        if isinstance(first_locator.get("bbox"), list)
                        else []
                    ),
                    ocr_quality=float(page.confidence) if page else None,
                    quality_flags=tuple(dict.fromkeys(flags)),
                    section_context=" ".join(
                        value
                        for value in (chunk.chapter_title, chunk.section_title)
                        if value
                    ),
                    locators=tuple(
                        row
                        for row in (chunk.locators or [])
                        if isinstance(row, dict)
                    ),
                    page_lookup=pages,
                )
            )
        return output

    return [
        SourceText(
            text=page.text,
            asset=asset,
            page=page,
            semantic_chunk=None,
            page_number=page.index,
            printed_page_label=page.printed_label,
            bbox=[],
            ocr_quality=float(page.confidence),
            quality_flags=(
                ("ocr_text",)
                if page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}
                else ()
            ),
            section_context=page.chapter_title,
            locators=(),
            page_lookup=pages,
        )
        for page in pages.values()
        if page.text.strip()
    ]


def _high_trust_entities(resolution: dict) -> list[dict]:
    allowed = {
        QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        QueryLexiconEntry.TrustLevel.VERIFIED,
    }
    by_entity: dict[tuple[str, str], dict] = {}
    for match in resolution.get("matches", []):
        if match.get("trust_level") not in allowed:
            continue
        if match.get("term_type") == QueryLexiconEntry.TermType.SEARCH_VARIANT:
            continue
        entity = match.get("entity") or {}
        key = (str(entity.get("entity_type") or ""), str(entity.get("entity_id") or ""))
        if key[0] not in {
            QueryLexiconEntry.EntityType.PERSON,
            QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        } or not key[1]:
            continue
        current = by_entity.get(key)
        if current is None or match.get("term_type") == QueryLexiconEntry.TermType.CANONICAL:
            by_entity[key] = {
                "entity_type": key[0],
                "entity_id": key[1],
                "canonical_label": entity.get("canonical_label", ""),
                "authority_status": entity.get("authority_status", ""),
                "matched_term": match.get("matched_term", ""),
                "term_type": match.get("term_type", ""),
                "source_kind": match.get("source_kind", ""),
                "trust_level": match.get("trust_level", ""),
            }
    return [by_entity[key] for key in sorted(by_entity)]


def _resolve_cached(term: str, cache: dict[str, dict]) -> dict:
    normalized = normalize_term(term)
    if normalized not in cache:
        cache[normalized] = resolve_term(
            term,
            scope=ADMIN_RESOLVABLE,
            max_results=MAX_RESOLVER_RESULTS,
        )
    return cache[normalized]


def _unresolved_funnel_category(*resolutions: dict) -> str:
    diagnostics = [
        row.get("scope_diagnostics") or {}
        for row in resolutions
    ]
    if any(
        int(row.get("high_trust_not_admin_resolvable_count") or 0) > 0
        for row in diagnostics
    ):
        return "target_not_admin_resolvable"
    if any(int(row.get("derived_row_count") or 0) > 0 for row in diagnostics):
        return "low_trust_generated_only_match"
    return "no_canonical_anchor_match"


def _person_corroborators(
    person_id: str,
    *,
    edition_id,
    evidence_text: str,
    approved_people: set[str],
    person_cache: dict[str, Person | None],
) -> list[str]:
    reasons = []
    if person_id in approved_people:
        reasons.append("approved_contribution_current_edition")
    person = person_cache.get(person_id)
    if person_id not in person_cache:
        person = Person.objects.filter(pk=person_id).first()
        person_cache[person_id] = person
    if person is None:
        return reasons
    for field_name, value in (
        ("birth_year", person.birth_year),
        ("death_year", person.death_year),
    ):
        if value and re.search(rf"(?<!\d){int(value)}(?!\d)", evidence_text):
            reasons.append(f"matching_{field_name}")
    for identifier_type, value in (person.external_ids or {}).items():
        identifier = str(value or "").strip()
        if len(identifier) >= 4 and identifier.casefold() in evidence_text.casefold():
            reasons.append(f"matching_identifier:{identifier_type}")
    return list(dict.fromkeys(reasons))


def _looks_like_abbreviation(anchor_term: str, proposed_term: str) -> bool:
    anchor = normalize_term(anchor_term)
    proposed = normalize_term(proposed_term)
    raw_compact = re.sub(r"[^A-Za-z0-9]", "", proposed_term)
    return bool(
        proposed
        and len(proposed) < len(anchor)
        and (
            "." in proposed_term
            or (raw_compact.isupper() and 2 <= len(raw_compact) <= 12)
            or len(proposed) <= max(4, round(len(anchor) * 0.5))
        )
    )


def _term_type(pair: DetectedPair, entity_type: str, proposed_term: str) -> str:
    anchor = (
        pair.left
        if normalize_term(proposed_term) == normalize_term(pair.right)
        else pair.right
    )
    if pair.relation_hint in {"abbreviation", "historical"}:
        return pair.relation_hint
    proposed_family = _language_family(detect_language(proposed_term))
    anchor_family = _language_family(detect_language(anchor))
    if entity_type == QueryLexiconEntry.EntityType.PERSON and {
        proposed_family,
        anchor_family,
    } == {"zh", "en"}:
        return QueryLexiconEntry.TermType.TRANSLITERATION
    if proposed_family != "unknown" and anchor_family != "unknown" and proposed_family != anchor_family:
        return QueryLexiconEntry.TermType.TRANSLATION
    if _looks_like_abbreviation(anchor, proposed_term):
        return QueryLexiconEntry.TermType.ABBREVIATION
    if pair.relation_hint == "alias":
        return QueryLexiconEntry.TermType.ALIAS
    return QueryLexiconEntry.TermType.ALIAS


def _confidence(
    pair: DetectedPair,
    *,
    anchor_match: dict | None,
    source: SourceText,
    ambiguous: bool,
    person_corroborators: list[str],
) -> tuple[float, dict]:
    additions = []
    penalties = []
    value = pair.base_confidence
    if anchor_match:
        trust_bonus = (
            0.18
            if anchor_match.get("trust_level") == QueryLexiconEntry.TrustLevel.AUTHORITATIVE
            else 0.12
        )
        value += trust_bonus
        additions.append({"factor": "anchor_trust", "value": trust_bonus})
        if anchor_match.get("term_type") == QueryLexiconEntry.TermType.CANONICAL:
            value += 0.08
            additions.append({"factor": "anchor_canonical", "value": 0.08})
    if _language_family(detect_language(pair.left)) != _language_family(detect_language(pair.right)):
        value += 0.06
        additions.append({"factor": "cross_script_pair", "value": 0.06})
    if _GLOSSARY_RE.search(source.section_context):
        value += 0.08
        additions.append({"factor": "glossary_or_index", "value": 0.08})
    if person_corroborators:
        value += 0.08
        additions.append({"factor": "person_identity_corroborated", "value": 0.08})
    if ambiguous:
        value -= 0.25
        penalties.append({"factor": "ambiguous_entity", "value": -0.25})
    if "low_ocr_confidence" in source.quality_flags:
        value -= 0.18
        penalties.append({"factor": "low_ocr_confidence", "value": -0.18})
    if source.ocr_quality is not None and source.ocr_quality < 0.72:
        penalty = min(0.18, round((0.72 - source.ocr_quality) * 0.5, 4))
        value -= penalty
        penalties.append({"factor": "ocr_quality", "value": -penalty})
    value = round(max(0, min(value, 0.99)), 4)
    return value, {
        "pair_structure": pair.method,
        "base": pair.base_confidence,
        "additions": additions,
        "penalties": penalties,
        "person_identity_corroborators": person_corroborators,
        "final": value,
    }


def _candidate_fingerprint(
    *,
    target_entity_type: str,
    target_entity_id: str,
    anchor_term: str,
    proposed_term: str,
    language: str,
    term_type: str,
    possible_targets: list[dict],
) -> str:
    target_key = (
        f"{target_entity_type}:{target_entity_id}"
        if target_entity_id
        else _stable_json(
            sorted(
                f"{row.get('entity_type')}:{row.get('entity_id')}"
                for row in possible_targets
            )
        )
    )
    return _digest(
        target_key,
        normalize_term(anchor_term) if not target_entity_id else "",
        normalize_term(proposed_term),
        normalize_language(language),
        term_type,
    )


def _evidence_location(source: SourceText, pair: DetectedPair) -> dict:
    selected = None
    normalized_left = normalize_term(pair.left)
    normalized_right = normalize_term(pair.right)
    for locator in source.locators:
        locator_text = normalize_term(locator.get("text", ""))
        if normalized_left in locator_text and normalized_right in locator_text:
            selected = locator
            break
    if selected is None and source.locators:
        selected = source.locators[0]
    selected = selected or {}
    page_number = int(selected.get("page_index") or source.page_number or 0) or None
    page = source.page_lookup.get(page_number) if page_number else source.page
    return {
        "page": page,
        "page_number": page_number,
        "printed_page_label": str(
            selected.get("printed_label")
            or (page.printed_label if page else source.printed_page_label)
            or ""
        ),
        "bbox": (
            selected.get("bbox")
            if isinstance(selected.get("bbox"), list)
            else source.bbox
        ),
    }


def _evidence_fingerprint(
    candidate_fingerprint: str,
    source: SourceText,
    pair: DetectedPair,
    source_checksum: str,
    location: dict,
) -> str:
    return _digest(
        candidate_fingerprint,
        source.asset.id,
        location["page_number"] or 0,
        source.semantic_chunk.document_id if source.semantic_chunk else "",
        pair.start,
        pair.end,
        normalize_term(pair.left),
        normalize_term(pair.right),
        source_checksum,
        pair.method,
    )


def _proposal_for_pair(
    pair: DetectedPair,
    source: SourceText,
    *,
    resolve_cache: dict[str, dict],
    approved_people: set[str],
    person_cache: dict[str, Person | None],
) -> tuple[dict | None, str]:
    left_resolution = _resolve_cached(pair.left, resolve_cache)
    right_resolution = _resolve_cached(pair.right, resolve_cache)
    left_matches = _high_trust_entities(left_resolution)
    right_matches = _high_trust_entities(right_resolution)
    left_keys = {(row["entity_type"], row["entity_id"]) for row in left_matches}
    right_keys = {(row["entity_type"], row["entity_id"]) for row in right_matches}

    if not left_matches and not right_matches:
        return None, "unresolved"
    if left_keys and right_keys and left_keys == right_keys:
        return None, "already_known" if len(left_keys) == 1 else "ambiguous"

    if left_matches and not right_matches:
        anchor_term, proposed_term, anchor_matches = pair.left, pair.right, left_matches
    elif right_matches and not left_matches:
        anchor_term, proposed_term, anchor_matches = pair.right, pair.left, right_matches
    else:
        # Both sides already point at different authority objects. Preserve the
        # conflict for review but never select a target automatically.
        anchor_term, proposed_term = pair.left, pair.right
        anchor_matches = [*left_matches, *right_matches]

    unique_targets = {
        (row["entity_type"], row["entity_id"]): row
        for row in anchor_matches
    }
    possible_targets = [unique_targets[key] for key in sorted(unique_targets)]
    target_types = {row["entity_type"] for row in possible_targets}
    if len(target_types) != 1:
        return None, "ambiguous"
    entity_type = next(iter(target_types))
    candidate_type = (
        QueryLexiconCandidate.CandidateType.PERSON_NAME_VARIANT
        if entity_type == QueryLexiconEntry.EntityType.PERSON
        else QueryLexiconCandidate.CandidateType.KNOWLEDGE_NODE_ALIAS
    )
    linked = len(possible_targets) == 1 and not (left_matches and right_matches)
    target = possible_targets[0] if linked else None
    person_corroborators: list[str] = []
    ambiguity_reason = ""
    if linked and entity_type == QueryLexiconEntry.EntityType.PERSON:
        person_corroborators = _person_corroborators(
            target["entity_id"],
            edition_id=source.asset.edition_id,
            evidence_text=source.text,
            approved_people=approved_people,
            person_cache=person_cache,
        )
        if not person_corroborators:
            linked = False
            target = None
            ambiguity_reason = "person_identity_not_corroborated"
    if not linked and not ambiguity_reason:
        ambiguity_reason = (
            "both_sides_resolve_differently"
            if left_matches and right_matches
            else "multiple_canonical_entities"
        )

    anchor_match = possible_targets[0] if len(possible_targets) == 1 else None
    confidence, confidence_factors = _confidence(
        pair,
        anchor_match=anchor_match,
        source=source,
        ambiguous=not linked,
        person_corroborators=person_corroborators,
    )
    threshold = MIN_LINKED_CONFIDENCE if linked else MIN_AMBIGUOUS_CONFIDENCE
    if confidence < threshold:
        return None, "low_confidence"
    term_type = _term_type(pair, entity_type, proposed_term)
    language = normalize_language(detect_language(proposed_term))
    target_entity_type = entity_type
    target_entity_id = target["entity_id"] if target else ""
    fingerprint = _candidate_fingerprint(
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        anchor_term=anchor_term,
        proposed_term=proposed_term,
        language=language,
        term_type=term_type,
        possible_targets=possible_targets,
    )
    return {
        "fingerprint": fingerprint,
        "candidate_type": candidate_type,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id or None,
        "anchor_term": anchor_term,
        "proposed_term": proposed_term,
        "language": language,
        "proposed_term_type": term_type,
        "confidence": confidence,
        "confidence_factors": confidence_factors,
        "linking_status": (
            QueryLexiconCandidate.LinkingStatus.LINKED
            if linked
            else QueryLexiconCandidate.LinkingStatus.AMBIGUOUS
        ),
        "possible_targets": possible_targets,
        "ambiguity": {
            "reason": ambiguity_reason,
            "matching_entity_count": len(possible_targets),
        },
        "displayable": False,
        "extraction_version": EXTRACTION_VERSION,
        "pair": pair,
        "source": source,
    }, "linked" if linked else "ambiguous"


def _candidate_defaults(proposal: dict) -> dict:
    return {
        key: proposal[key]
        for key in (
            "candidate_type",
            "target_entity_type",
            "target_entity_id",
            "anchor_term",
            "proposed_term",
            "language",
            "proposed_term_type",
            "confidence",
            "confidence_factors",
            "linking_status",
            "possible_targets",
            "ambiguity",
            "displayable",
            "extraction_version",
        )
    }


def _persist_proposal(
    proposal: dict,
) -> tuple[QueryLexiconCandidate, QueryLexiconCandidateEvidence, bool, bool]:
    candidate, candidate_created = QueryLexiconCandidate.objects.get_or_create(
        fingerprint=proposal["fingerprint"],
        defaults=_candidate_defaults(proposal),
    )
    if not candidate_created and candidate.status == QueryLexiconCandidate.Status.PENDING:
        candidate.confidence = proposal["confidence"]
        candidate.confidence_factors = proposal["confidence_factors"]
        candidate.possible_targets = proposal["possible_targets"]
        candidate.ambiguity = proposal["ambiguity"]
        candidate.extraction_version = proposal["extraction_version"]
        candidate.save(
            update_fields=[
                "confidence",
                "confidence_factors",
                "possible_targets",
                "ambiguity",
                "extraction_version",
                "updated_at",
            ]
        )
    elif not candidate_created and candidate.status == QueryLexiconCandidate.Status.SUPERSEDED:
        for field_name, value in _candidate_defaults(proposal).items():
            setattr(candidate, field_name, value)
        if candidate.status == QueryLexiconCandidate.Status.SUPERSEDED:
            candidate.status = QueryLexiconCandidate.Status.PENDING
        candidate.save()

    source = proposal["source"]
    pair = proposal["pair"]
    location = _evidence_location(source, pair)
    evidence_text_checksum = _digest(source.text)
    evidence_fingerprint = _evidence_fingerprint(
        candidate.fingerprint,
        source,
        pair,
        evidence_text_checksum,
        location,
    )
    evidence_defaults = {
        "work": source.asset.edition.work,
        "edition": source.asset.edition,
        "asset": source.asset,
        "page": location["page"],
        "semantic_chunk": source.semantic_chunk,
        "document_id": (
            source.semantic_chunk.document_id if source.semantic_chunk else ""
        ),
        "page_number": location["page_number"],
        "printed_page_label": location["printed_page_label"],
        "bbox": location["bbox"],
        "evidence_text": source.text,
        "start_offset": pair.start,
        "end_offset": pair.end,
        "left_term": pair.left,
        "right_term": pair.right,
        "detected_pair": {
            "left": pair.left,
            "right": pair.right,
            "relation_hint": pair.relation_hint,
        },
        "extraction_method": pair.method,
        "confidence": proposal["confidence"],
        "confidence_factors": proposal["confidence_factors"],
        "ocr_quality": source.ocr_quality,
        "quality_flags": list(source.quality_flags),
        "source_text_checksum": evidence_text_checksum,
        "extraction_version": EXTRACTION_VERSION,
        "is_current": True,
        "superseded_at": None,
    }
    evidence, evidence_created = QueryLexiconCandidateEvidence.objects.get_or_create(
        candidate=candidate,
        fingerprint=evidence_fingerprint,
        defaults=evidence_defaults,
    )
    if not evidence_created and not evidence.is_current:
        evidence.is_current = True
        evidence.superseded_at = None
        evidence.save(update_fields=["is_current", "superseded_at", "updated_at"])
    return candidate, evidence, candidate_created, evidence_created


def _refresh_candidate_confidence(candidate_ids: set[UUID]) -> None:
    for candidate in QueryLexiconCandidate.objects.filter(pk__in=candidate_ids):
        evidence = candidate.evidence_records.filter(is_current=True)
        values = list(evidence.values_list("confidence", flat=True))
        if not values:
            if candidate.status == QueryLexiconCandidate.Status.PENDING:
                candidate.status = QueryLexiconCandidate.Status.SUPERSEDED
                candidate.save(update_fields=["status", "updated_at"])
            continue
        evidence_count = len(values)
        work_count = evidence.values("work_id").distinct().count()
        evidence_bonus = min(0.08, 0.02 * max(0, evidence_count - 1))
        diversity_bonus = min(0.12, 0.04 * max(0, work_count - 1))
        candidate.confidence = round(
            min(0.99, max(values) + evidence_bonus + diversity_bonus),
            4,
        )
        candidate.confidence_factors = {
            **(candidate.confidence_factors or {}),
            "evidence_count": evidence_count,
            "independent_work_count": work_count,
            "evidence_bonus": round(evidence_bonus, 4),
            "source_diversity_bonus": round(diversity_bonus, 4),
            "final": candidate.confidence,
        }
        candidate.save(
            update_fields=["confidence", "confidence_factors", "updated_at"]
        )


def _update_review_task(asset: Asset) -> None:
    from ingestion.models import ReviewTask, UploadItem

    pending = QueryLexiconCandidate.objects.filter(
        status=QueryLexiconCandidate.Status.PENDING,
        evidence_records__work_id=asset.edition.work_id,
        evidence_records__is_current=True,
    ).distinct()
    count = pending.count()
    if not count:
        return
    details = {
        "work_id": str(asset.edition.work_id),
        "asset_id": str(asset.id),
        "extraction_version": EXTRACTION_VERSION,
        "pending_candidate_count": count,
        "candidate_ids": [str(value) for value in pending.values_list("id", flat=True)[:100]],
    }
    task = ReviewTask.objects.filter(
        task_type="query_lexicon_candidates",
        target_type="work",
        target_id=str(asset.edition.work_id),
        status__in=[ReviewTask.Status.PENDING, ReviewTask.Status.IN_PROGRESS],
    ).first()
    if task:
        task.details = details
        task.title = f"术语候选复核 · {asset.edition.work.title}"
        task.save(update_fields=["details", "title", "updated_at"])
        return
    upload_item = UploadItem.objects.filter(
        edition_id=asset.edition_id,
    ).order_by("-created_at").first()
    ReviewTask.objects.create(
        upload_item=upload_item,
        task_type="query_lexicon_candidates",
        target_type="work",
        target_id=str(asset.edition.work_id),
        title=f"术语候选复核 · {asset.edition.work.title}",
        details=details,
        priority=40,
    )


def scan_asset_for_query_lexicon_candidates(
    asset: Asset,
    *,
    commit: bool = True,
    create_review_task: bool = True,
) -> dict:
    asset = Asset.objects.select_related("edition__work").get(pk=asset.pk)
    sources = _source_texts(asset)
    source_checksum = candidate_source_checksum(asset)
    approved_people = {
        str(value)
        for value in Contribution.objects.filter(
            edition_id=asset.edition_id,
            approved=True,
        ).values_list("person_id", flat=True)
    }
    person_cache: dict[str, Person | None] = {}
    proposals: list[dict] = []
    detected: list[tuple[DetectedPair, SourceText]] = []
    audit = defaultdict(int)
    audit_samples: dict[str, list[dict]] = defaultdict(list)
    unknown_observations: list[tuple[DetectedPair, SourceText, str]] = []
    funnel = {key: 0 for key in REJECTION_FUNNEL_KEYS}
    pair_count = 0
    invalid_extracted_count = 0

    for source in sources:
        pairs, source_audit = extract_explicit_pairs(source.text)
        for key, value in source_audit.items():
            audit[key] += value
            if key.startswith("noise:") or key == "same_normalized_term":
                funnel["invalid_noisy_pair"] += int(value)
                invalid_extracted_count += int(value)
        for pair in pairs:
            pair_count += 1
            if pair_count > MAX_PAIRS_PER_ASSET:
                audit["asset_pair_limit_reached"] += 1
                break
            detected.append((pair, source))
        if pair_count > MAX_PAIRS_PER_ASSET:
            break

    batch_resolution = resolve_terms(
        [term for pair, _source in detected for term in (pair.left, pair.right)],
        entity_types=[
            QueryLexiconEntry.EntityType.PERSON,
            QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        ],
        scope=ADMIN_RESOLVABLE,
        max_results_per_term=MAX_RESOLVER_RESULTS,
        include_scope_diagnostics=True,
    ) if detected else {"revision": None, "results": {}}
    resolve_cache: dict[str, dict] = batch_resolution["results"]
    for pair, source in detected:
        proposal, outcome = _proposal_for_pair(
            pair,
            source,
            resolve_cache=resolve_cache,
            approved_people=approved_people,
            person_cache=person_cache,
        )
        audit[outcome] += 1
        if outcome == "linked":
            funnel_key = "valid_candidate_created"
        elif outcome == "already_known":
            funnel_key = "proposed_term_already_exists"
        elif outcome == "low_confidence":
            funnel_key = "invalid_noisy_pair"
        elif outcome == "unresolved":
            funnel_key = _unresolved_funnel_category(
                _resolve_cached(pair.left, resolve_cache),
                _resolve_cached(pair.right, resolve_cache),
            )
        elif (
            proposal is not None
            and (proposal.get("ambiguity") or {}).get("reason")
            == "person_identity_not_corroborated"
        ):
            funnel_key = "person_identity_insufficient"
        else:
            funnel_key = "ambiguous_multi_target"
        funnel[funnel_key] += 1
        if outcome == "unresolved" and funnel_key in {
            "no_canonical_anchor_match",
            "low_trust_generated_only_match",
        }:
            unknown_observations.append((pair, source, funnel_key))
        if proposal is not None:
            proposals.append(proposal)
        elif len(audit_samples[outcome]) < MAX_AUDIT_SAMPLES:
            audit_samples[outcome].append(
                {
                    "left": pair.left,
                    "right": pair.right,
                    "page": source.page_number,
                    "method": pair.method,
                }
            )

    explicit_pair_observations = pair_count + invalid_extracted_count
    if sum(funnel.values()) != explicit_pair_observations:
        raise RuntimeError("QueryLexicon candidate rejection funnel 数量不守恒。")
    unique_pair_fingerprints = sorted(
        {
            _digest(
                normalize_term(pair.left),
                normalize_term(pair.right),
                pair.method,
            )
            for pair, _source in detected
        }
    )

    if not commit:
        unique = {row["fingerprint"]: row for row in proposals}
        return {
            "asset_id": str(asset.id),
            "work_id": str(asset.edition.work_id),
            "work_title": asset.edition.work.title,
            "extraction_version": EXTRACTION_VERSION,
            "query_lexicon_revision": batch_resolution["revision"],
            "source_checksum": source_checksum,
            "source_count": len(sources),
            "detected_pair_count": pair_count,
            "explicit_pair_observations": explicit_pair_observations,
            "unique_pair_count": len(unique_pair_fingerprints),
            "_unique_pair_fingerprints": unique_pair_fingerprints,
            "rejection_funnel": funnel,
            "candidate_count": len(unique),
            "linked_candidate_count": sum(
                row["linking_status"] == QueryLexiconCandidate.LinkingStatus.LINKED
                for row in unique.values()
            ),
            "ambiguous_candidate_count": sum(
                row["linking_status"] == QueryLexiconCandidate.LinkingStatus.AMBIGUOUS
                for row in unique.values()
            ),
            "unknown_entity_observation_count": len(unknown_observations),
            "new_authority_candidate_count": len({
                _digest(
                    sorted({normalize_term(pair.left), normalize_term(pair.right)}),
                    pair.relation_hint,
                )
                for pair, _source, _reason in unknown_observations
            }),
            "unknown_entity_samples": [
                {
                    "terms": [pair.left, pair.right],
                    "page": source.page_number,
                    "method": pair.method,
                    "reason": reason,
                }
                for pair, source, reason in unknown_observations[:MAX_AUDIT_SAMPLES]
            ],
            "audit": dict(sorted(audit.items())),
            "audit_samples": dict(audit_samples),
            "candidates": [
                {
                    "candidate_type": row["candidate_type"],
                    "target_entity_type": row["target_entity_type"],
                    "target_entity_id": row["target_entity_id"],
                    "anchor_term": row["anchor_term"],
                    "proposed_term": row["proposed_term"],
                    "language": row["language"],
                    "term_type": row["proposed_term_type"],
                    "linking_status": row["linking_status"],
                    "confidence": row["confidence"],
                    "page": row["source"].page_number,
                    "method": row["pair"].method,
                }
                for row in unique.values()
            ][:200],
        }

    seen_evidence_ids: set[UUID] = set()
    seen_unknown_observation_ids: set[UUID] = set()
    affected_unknown_candidate_ids: set[UUID] = set()
    affected_candidate_ids: set[UUID] = set()
    added_candidates = 0
    added_evidence = 0
    with transaction.atomic():
        for proposal in proposals:
            candidate, evidence, candidate_created, evidence_created = _persist_proposal(
                proposal,
            )
            seen_evidence_ids.add(evidence.id)
            affected_candidate_ids.add(candidate.id)
            added_candidates += int(candidate_created)
            added_evidence += int(evidence_created)

        for pair, source, reason in unknown_observations:
            context_start = max(0, pair.start - 240)
            context_end = min(len(source.text), pair.end + 240)
            evidence_text = source.text[context_start:context_end]
            observation, unknown_candidate, observation_created = persist_unknown_observation(
                asset=asset,
                edition=asset.edition,
                work=asset.edition.work,
                page=source.page,
                semantic_chunk=source.semantic_chunk,
                document_id=(
                    str(source.semantic_chunk.document_id)
                    if source.semantic_chunk is not None
                    else ""
                ),
                page_number=source.page_number,
                printed_page_label=source.printed_page_label,
                terms=[pair.left, pair.right],
                evidence_text=evidence_text,
                start_offset=max(0, pair.start - context_start),
                end_offset=max(0, pair.end - context_start),
                extraction_method=pair.method,
                extraction_version=EXTRACTION_VERSION,
                confidence=pair.base_confidence,
                confidence_factors={
                    "pair_method": pair.method,
                    "relation_hint": pair.relation_hint,
                    "unresolved_reason": reason,
                    "page_level_language": detect_language(evidence_text),
                },
                source_text_checksum=_digest(source.text),
                bbox=source.bbox,
            )
            seen_unknown_observation_ids.add(observation.id)
            affected_unknown_candidate_ids.add(unknown_candidate.id)

        stale = QueryLexiconCandidateEvidence.objects.select_for_update().filter(
            asset=asset,
            is_current=True,
        )
        if seen_evidence_ids:
            stale = stale.exclude(pk__in=seen_evidence_ids)
        stale_candidate_ids = set(stale.values_list("candidate_id", flat=True))
        stale_count = stale.update(
            is_current=False,
            superseded_at=timezone.now(),
            updated_at=timezone.now(),
        )
        affected_candidate_ids.update(stale_candidate_ids)
        stale_unknown = UnknownEntityObservation.objects.select_for_update().filter(
            asset=asset,
            is_current=True,
        )
        if seen_unknown_observation_ids:
            stale_unknown = stale_unknown.exclude(pk__in=seen_unknown_observation_ids)
        stale_unknown_candidate_ids = set(stale_unknown.values_list("candidate_id", flat=True))
        stale_unknown.update(
            is_current=False,
            superseded_at=timezone.now(),
            updated_at=timezone.now(),
        )
        affected_unknown_candidate_ids.update(
            value for value in stale_unknown_candidate_ids if value is not None
        )
        for unknown_candidate_id in affected_unknown_candidate_ids:
            refresh_unknown_candidate(
                NewAuthorityCandidate.objects.select_for_update().get(pk=unknown_candidate_id)
            )
        _refresh_candidate_confidence(affected_candidate_ids)
        if create_review_task:
            _update_review_task(asset)

    candidate_ids = {
        proposal["fingerprint"]
        for proposal in proposals
    }
    current_candidates = QueryLexiconCandidate.objects.filter(
        fingerprint__in=candidate_ids,
    )
    return {
        "asset_id": str(asset.id),
        "work_id": str(asset.edition.work_id),
        "work_title": asset.edition.work.title,
        "extraction_version": EXTRACTION_VERSION,
        "query_lexicon_revision": batch_resolution["revision"],
        "source_checksum": source_checksum,
        "source_count": len(sources),
        "detected_pair_count": pair_count,
        "explicit_pair_observations": explicit_pair_observations,
        "unique_pair_count": len(unique_pair_fingerprints),
        "_unique_pair_fingerprints": unique_pair_fingerprints,
        "rejection_funnel": funnel,
        "candidate_count": current_candidates.count(),
        "linked_candidate_count": current_candidates.filter(
            linking_status=QueryLexiconCandidate.LinkingStatus.LINKED
        ).count(),
        "ambiguous_candidate_count": current_candidates.filter(
            linking_status=QueryLexiconCandidate.LinkingStatus.AMBIGUOUS
        ).count(),
        "person_candidate_count": current_candidates.filter(
            candidate_type=QueryLexiconCandidate.CandidateType.PERSON_NAME_VARIANT
        ).count(),
        "knowledge_node_candidate_count": current_candidates.filter(
            candidate_type=QueryLexiconCandidate.CandidateType.KNOWLEDGE_NODE_ALIAS
        ).count(),
        "added_candidates": added_candidates,
        "added_evidence": added_evidence,
        "unknown_entity_observation_count": len(seen_unknown_observation_ids),
        "new_authority_candidate_count": NewAuthorityCandidate.objects.filter(
            observations__asset=asset,
            observations__is_current=True,
        ).distinct().count(),
        "unknown_entity_samples": [
            {
                "terms": [pair.left, pair.right],
                "page": source.page_number,
                "method": pair.method,
                "reason": reason,
            }
            for pair, source, reason in unknown_observations[:MAX_AUDIT_SAMPLES]
        ],
        "stale_evidence": stale_count,
        "audit": dict(sorted(audit.items())),
        "audit_samples": dict(audit_samples),
    }


def _validated_target(candidate: QueryLexiconCandidate) -> tuple[str, Person | KnowledgeNode]:
    if (
        candidate.linking_status != QueryLexiconCandidate.LinkingStatus.LINKED
        or not candidate.target_entity_type
        or not candidate.target_entity_id
    ):
        raise ValueError("候选尚未唯一关联 canonical entity。")
    resolution = resolve_term(
        candidate.anchor_term,
        entity_type=candidate.target_entity_type,
        scope=ADMIN_RESOLVABLE,
        max_results=MAX_RESOLVER_RESULTS,
    )
    valid_ids = {
        str(row["entity"]["entity_id"])
        for row in resolution.get("matches", [])
        if row.get("trust_level")
        in {
            QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            QueryLexiconEntry.TrustLevel.VERIFIED,
        }
        and row.get("term_type") != QueryLexiconEntry.TermType.SEARCH_VARIANT
    }
    if str(candidate.target_entity_id) not in valid_ids:
        raise ValueError("canonical target 已变化或不再由高可信 anchor term 支持。")
    if candidate.target_entity_type == QueryLexiconEntry.EntityType.PERSON:
        target = Person.objects.select_for_update().filter(pk=candidate.target_entity_id).first()
    elif candidate.target_entity_type == QueryLexiconEntry.EntityType.KNOWLEDGE_NODE:
        target = KnowledgeNode.objects.select_for_update().filter(pk=candidate.target_entity_id).first()
    else:
        target = None
    if target is None:
        raise ValueError("canonical target 已不存在。")
    expected_candidate_type = (
        QueryLexiconCandidate.CandidateType.PERSON_NAME_VARIANT
        if candidate.target_entity_type == QueryLexiconEntry.EntityType.PERSON
        else QueryLexiconCandidate.CandidateType.KNOWLEDGE_NODE_ALIAS
    )
    if candidate.candidate_type != expected_candidate_type:
        raise ValueError("候选 destination type 与 canonical target 不一致。")
    return candidate.target_entity_type, target


def _authority_source_note(candidate: QueryLexiconCandidate) -> str:
    current = candidate.evidence_records.filter(is_current=True)
    return _stable_json(
        {
            "source": "pdf",
            "query_lexicon_candidate_id": str(candidate.id),
            "evidence_count": current.count(),
            "work_ids": [
                str(value)
                for value in current.values_list("work_id", flat=True).distinct()[:20]
            ],
        }
    )


@transaction.atomic
def accept_query_lexicon_candidate(
    candidate: QueryLexiconCandidate,
    *,
    actor,
    reason: str = "",
) -> CandidateDecisionResult:
    candidate = QueryLexiconCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status == QueryLexiconCandidate.Status.ACCEPTED:
        if not candidate.accepted_authority_model or not candidate.accepted_authority_id:
            raise ValueError("已接受候选缺少 authority 审计引用。")
        return CandidateDecisionResult(
            candidate=candidate,
            authority_model=candidate.accepted_authority_model,
            authority_id=candidate.accepted_authority_id,
            authority_created=False,
            authority_changed=False,
            idempotent=True,
        )
    if candidate.status != QueryLexiconCandidate.Status.PENDING:
        raise ValueError("只有待审核候选可以接受。")
    if term_noise_reason(candidate.proposed_term):
        raise ValueError("修正后的候选术语仍不符合质量要求。")
    entity_type, target = _validated_target(candidate)
    source_note = _authority_source_note(candidate)
    authority_created = False
    authority_changed = False

    if entity_type == QueryLexiconEntry.EntityType.PERSON:
        canonical_terms = {
            normalize_term(target.preferred_name),
            normalize_term(target.original_name),
        }
        if candidate.normalized_term in canonical_terms:
            authority = target
            authority_model = "catalog.Person"
        else:
            authority = PersonNameVariant.objects.select_for_update().filter(
                person=target,
                normalized_name=candidate.normalized_term,
            ).first()
            desired = {
                "name": candidate.proposed_term,
                "language": normalize_language(candidate.language),
                "variant_type": candidate.proposed_term_type,
                "displayable": candidate.displayable,
                "is_verified": True,
            }
            if authority is None:
                authority = PersonNameVariant.objects.create(
                    person=target,
                    created_by=actor,
                    source_kind=PersonNameVariant.SourceKind.PDF_EVIDENCE,
                    source_note=source_note,
                    **desired,
                )
                authority_created = True
                authority_changed = True
            else:
                updates = []
                was_verified = authority.is_verified
                if not was_verified:
                    desired["displayable"] = bool(
                        authority.displayable or candidate.displayable
                    )
                    for field_name, value in desired.items():
                        if getattr(authority, field_name) != value:
                            setattr(authority, field_name, value)
                            updates.append(field_name)
                if authority.created_by_id is None and not was_verified:
                    authority.created_by = actor
                    updates.append("created_by")
                if updates:
                    authority.save(update_fields=[*updates, "updated_at"])
                    authority_changed = True
            authority_model = "catalog.PersonNameVariant"
    else:
        canonical_terms = {
            normalize_term(target.canonical_name_zh),
            normalize_term(target.canonical_name_en),
        }
        if candidate.normalized_term in canonical_terms:
            authority = target
            authority_model = "catalog.KnowledgeNode"
        else:
            alias_normalized = " ".join(candidate.proposed_term.casefold().split())
            authority = KnowledgeNodeAlias.objects.select_for_update().filter(
                node=target,
                normalized_alias=alias_normalized,
            ).first()
            desired = {
                "alias": candidate.proposed_term,
                "language": normalize_language(candidate.language)[:16],
                "alias_type": candidate.proposed_term_type,
            }
            if authority is None:
                authority = KnowledgeNodeAlias.objects.create(
                    node=target,
                    created_by=actor,
                    source_kind=KnowledgeNodeAlias.SourceKind.PDF_EVIDENCE,
                    is_verified=True,
                    **desired,
                )
                authority_created = True
                authority_changed = True
            else:
                updates = []
                if authority.created_by_id is None:
                    for field_name, value in desired.items():
                        if getattr(authority, field_name) != value:
                            setattr(authority, field_name, value)
                            updates.append(field_name)
                    authority.created_by = actor
                    authority.source_kind = KnowledgeNodeAlias.SourceKind.PDF_EVIDENCE
                    authority.is_verified = True
                    updates.extend(["created_by", "source_kind", "is_verified"])
                if updates:
                    authority.save(update_fields=[*updates, "updated_at"])
                    authority_changed = True
            authority_model = "catalog.KnowledgeNodeAlias"

    candidate.status = QueryLexiconCandidate.Status.ACCEPTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = timezone.now()
    candidate.review_reason = str(reason or "")[:4000]
    candidate.accepted_authority_model = authority_model
    candidate.accepted_authority_id = authority.id
    candidate.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "accepted_authority_model",
            "accepted_authority_id",
            "updated_at",
        ]
    )
    return CandidateDecisionResult(
        candidate=candidate,
        authority_model=authority_model,
        authority_id=authority.id,
        authority_created=authority_created,
        authority_changed=authority_changed,
        idempotent=False,
    )


@transaction.atomic
def reject_query_lexicon_candidate(
    candidate: QueryLexiconCandidate,
    *,
    actor,
    reason: str = "",
) -> tuple[QueryLexiconCandidate, bool]:
    candidate = QueryLexiconCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.status == QueryLexiconCandidate.Status.REJECTED:
        return candidate, True
    if candidate.status == QueryLexiconCandidate.Status.ACCEPTED:
        raise ValueError("已接受候选不能直接拒绝；authority 回滚需要独立人工操作。")
    if candidate.status not in {
        QueryLexiconCandidate.Status.PENDING,
        QueryLexiconCandidate.Status.SUPERSEDED,
    }:
        raise ValueError("该候选当前不能拒绝。")
    candidate.status = QueryLexiconCandidate.Status.REJECTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = timezone.now()
    candidate.review_reason = str(reason or "")[:4000]
    candidate.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_reason",
            "updated_at",
        ]
    )
    return candidate, False
