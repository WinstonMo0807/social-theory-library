from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from catalog.models import DerivedClaim


_CRITICIZED_RE = re.compile(
    r"(?:批评|批判|质疑|反驳|驳斥|所谓.+?(?:错误|局限)|"
    r"\bcritic(?:ize|ise|ism|ized|ised)s?\b|\bchallenge[ds]?\b|\brejects?\b)",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(
    r"(?:[“\"「『].{2,600}[”\"」』]|"
    r"直接引用|引文|原话|写道|强调道|"
    r"\bquote[ds]?\b|\bin (?:his|her|their) words\b)",
    re.IGNORECASE,
)
_REPORTED_RE = re.compile(
    r"(?:据.+?(?:认为|指出|主张|声称)|"
    r".+?(?:认为|指出|主张|声称|写道)|"
    r"\baccording to\b|\breports? that\b|\bargues? that\b|\bclaims? that\b)",
    re.IGNORECASE,
)
_AUTHOR_RE = re.compile(
    r"(?:本文|本书|本章|我们|我)(?:认为|主张|指出|将证明|强调)|"
    r"\b(?:we|i) (?:argue|claim|show|demonstrate|contend)\b",
    re.IGNORECASE,
)
_HISTORICAL_RE = re.compile(
    r"(?:历史上|当时|在\d{3,4}年|世纪|时期|阶段|曾经|"
    r"\bhistorically\b|\bin the \d{1,2}(?:st|nd|rd|th) century\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AttributionDecision:
    attribution: str
    confidence: float
    reasons: tuple[str, ...]
    deterministic: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


def normalize_attribution(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in DerivedClaim.Attribution.values:
        return normalized
    return DerivedClaim.Attribution.UNCERTAIN


def infer_attribution(
    text: str,
    *,
    explicit: object = "",
    claim_type: str = "",
    context: str = "",
) -> AttributionDecision:
    """Return a bounded attribution decision without inventing an author.

    A model-provided enum is preserved when it is valid.  Deterministic rules
    only fill an absent or uncertain value.  They intentionally prefer
    ``criticized_claim`` and quoted/reported speech over ``author_claim`` so a
    nearby author name cannot silently turn a quotation into the book author's
    own position.
    """

    normalized = normalize_attribution(explicit)
    if normalized != DerivedClaim.Attribution.UNCERTAIN:
        return AttributionDecision(normalized, 1.0, ("explicit_valid_enum",))

    value = " ".join(part for part in (str(context or ""), str(text or "")) if part)
    if (
        str(claim_type or "").strip().casefold() == DerivedClaim.ClaimType.CRITICISM
        or _CRITICIZED_RE.search(value)
    ):
        return AttributionDecision(
            DerivedClaim.Attribution.CRITICIZED_CLAIM,
            0.94,
            ("explicit_criticism_marker",),
        )
    if _QUOTED_RE.search(value):
        return AttributionDecision(
            DerivedClaim.Attribution.QUOTED_CLAIM,
            0.9,
            ("quotation_marker",),
        )
    if _REPORTED_RE.search(value):
        return AttributionDecision(
            DerivedClaim.Attribution.REPORTED_CLAIM,
            0.86,
            ("reported_speech_marker",),
        )
    if _AUTHOR_RE.search(value):
        return AttributionDecision(
            DerivedClaim.Attribution.AUTHOR_CLAIM,
            0.88,
            ("first_party_argument_marker",),
        )
    if _HISTORICAL_RE.search(value):
        return AttributionDecision(
            DerivedClaim.Attribution.HISTORICAL_DESCRIPTION,
            0.78,
            ("historical_description_marker",),
        )
    return AttributionDecision(
        DerivedClaim.Attribution.UNCERTAIN,
        0.35,
        ("insufficient_attribution_evidence",),
    )
