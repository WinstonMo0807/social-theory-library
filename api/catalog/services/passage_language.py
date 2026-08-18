from __future__ import annotations

import re
import unicodedata


LANGUAGE_DETECTOR_VERSION = "passage-script-ratio-v1"
MIN_EFFECTIVE_CHARACTERS = 6
MIXED_MIN_CHARACTERS_PER_SCRIPT = 20
MIXED_MINORITY_RATIO = 0.20
DOMINANT_SCRIPT_RATIO = 0.65

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")


def language_detector_config() -> dict:
    return {
        "version": LANGUAGE_DETECTOR_VERSION,
        "labels": ["zh", "en", "mixed", "unknown"],
        "min_effective_characters": MIN_EFFECTIVE_CHARACTERS,
        "mixed_min_characters_per_script": MIXED_MIN_CHARACTERS_PER_SCRIPT,
        "mixed_minority_ratio": MIXED_MINORITY_RATIO,
        "dominant_script_ratio": DOMINANT_SCRIPT_RATIO,
    }


def passage_language_details(value: object) -> dict:
    """Classify the dominant writing system without remote inference.

    A few names or citations in the secondary script do not make a passage
    mixed. Both scripts must contribute a meaningful amount of text before the
    mixed label is used.
    """

    text = unicodedata.normalize("NFKC", str(value or ""))
    cjk_count = len(_CJK_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))
    effective_count = cjk_count + latin_count
    if effective_count < MIN_EFFECTIVE_CHARACTERS:
        language = "unknown"
    else:
        cjk_ratio = cjk_count / effective_count
        latin_ratio = latin_count / effective_count
        minority_ratio = min(cjk_ratio, latin_ratio)
        if (
            cjk_count >= MIXED_MIN_CHARACTERS_PER_SCRIPT
            and latin_count >= MIXED_MIN_CHARACTERS_PER_SCRIPT
            and minority_ratio >= MIXED_MINORITY_RATIO
        ):
            language = "mixed"
        elif cjk_count == 0:
            language = "en"
        elif latin_count == 0:
            language = "zh"
        elif (
            cjk_count < MIXED_MIN_CHARACTERS_PER_SCRIPT
            and latin_count < MIXED_MIN_CHARACTERS_PER_SCRIPT
            and minority_ratio >= 0.20
        ):
            # Short bilingual headings and labels can still be mixed. The
            # substantial-count rule above protects normal long passages from
            # a single name or citation.
            language = "mixed"
        elif cjk_ratio >= DOMINANT_SCRIPT_RATIO or latin_count < MIXED_MIN_CHARACTERS_PER_SCRIPT:
            language = "zh"
        elif latin_ratio >= DOMINANT_SCRIPT_RATIO or cjk_count < MIXED_MIN_CHARACTERS_PER_SCRIPT:
            language = "en"
        else:
            language = "mixed"
    return {
        "language": language,
        "cjk_count": cjk_count,
        "latin_count": latin_count,
        "effective_count": effective_count,
    }


def detect_passage_language(value: object) -> str:
    return str(passage_language_details(value)["language"])
