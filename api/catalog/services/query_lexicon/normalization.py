from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from pypinyin import Style, lazy_pinyin
from unidecode import unidecode


NORMALIZATION_VERSION = "query-lexicon-normalize-v1"
GENERATED_VARIANT_VERSION = "query-lexicon-variants-v1"

_REMOVED_FORMAT_CHARACTERS = str.maketrans(
    {
        "\u200b": None,
        "\u200c": None,
        "\u200d": None,
        "\u2060": None,
        "\ufeff": None,
    }
)
_WHITESPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")


@dataclass(frozen=True)
class GeneratedVariant:
    term: str
    generator: str


def normalize_term(value: object) -> str:
    """Return deterministic, low-loss matching text without transliteration."""

    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.translate(_REMOVED_FORMAT_CHARACTERS)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized.casefold()


def normalize_language(value: object) -> str:
    raw = str(value or "").strip().replace("_", "-").casefold()
    mapping = {
        "zh": "zh-Hans",
        "zh-cn": "zh-Hans",
        "zh-sg": "zh-Hans",
        "zh-hans": "zh-Hans",
        "zh-tw": "zh-Hant",
        "zh-hk": "zh-Hant",
        "zh-mo": "zh-Hant",
        "zh-hant": "zh-Hant",
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
        "und": "und",
    }
    return mapping.get(raw, raw or "und")[:24]


def detect_language(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    has_cjk = bool(_CJK_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    if has_cjk and has_latin:
        return "und"
    if has_cjk:
        return "zh-Hans"
    if has_latin:
        return "en"
    return "und"


def generated_search_variants(value: object) -> list[GeneratedVariant]:
    """Build deterministic internal-only variants for one authority term."""

    original = unicodedata.normalize("NFKC", str(value or "")).translate(
        _REMOVED_FORMAT_CHARACTERS
    )
    original = _WHITESPACE_RE.sub(" ", original).strip()
    if not original:
        return []

    candidates: list[GeneratedVariant] = [
        GeneratedVariant(normalize_term(original), "nfkc_casefold"),
    ]
    folded = normalize_term(original)
    ascii_variant = _WHITESPACE_RE.sub(" ", unidecode(folded)).strip().casefold()
    if ascii_variant:
        candidates.append(GeneratedVariant(ascii_variant, "unidecode"))

    if _CJK_RE.search(original):
        full = "".join(lazy_pinyin(original, errors="ignore")).casefold()
        initials = "".join(
            lazy_pinyin(original, style=Style.FIRST_LETTER, errors="ignore")
        ).casefold()
        spaced = " ".join(lazy_pinyin(original, errors="ignore")).casefold()
        candidates.extend(
            [
                GeneratedVariant(full, "pinyin"),
                GeneratedVariant(initials, "pinyin_initials"),
                GeneratedVariant(spaced, "pinyin_spaced"),
            ]
        )

    result: list[GeneratedVariant] = []
    seen: set[str] = set()
    for candidate in candidates:
        term = normalize_term(candidate.term)
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(GeneratedVariant(term, candidate.generator))
    return result
