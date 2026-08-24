from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import re
from typing import Any, Mapping


class ClaimStance(StrEnum):
    DIRECT = "direct"
    SUPPORT = "support"
    OPPOSE = "oppose"
    QUALIFY = "qualify"
    CRITIQUE = "critique"
    EXTEND = "extend"
    REFRAME = "reframe"


@dataclass(frozen=True, slots=True)
class ClaimStatement:
    proposition: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    polarity: str = "uncertain"
    modality: str = ""
    qualifiers: tuple[str, ...] = ()
    temporal_scope: Mapping[str, Any] = field(default_factory=dict)
    geographic_scope: Mapping[str, Any] = field(default_factory=dict)
    population_scope: Mapping[str, Any] = field(default_factory=dict)
    attribution: str = "uncertain"
    claim_type: str = "assertion"


@dataclass(frozen=True, slots=True)
class StanceResult:
    stance: ClaimStance
    confidence: float
    reasons: tuple[str, ...]
    query_polarity: str
    candidate_polarity: str
    deterministic: bool = True

    def as_dict(self) -> dict:
        value = asdict(self)
        value["stance"] = self.stance.value
        return value


_SPACE_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_EN_NEGATION_RE = re.compile(
    r"\b(?:(?:do|does|did|is|are|was|were|can|could|will|would|has|have|had)\s+not|never|cannot)\b",
    re.IGNORECASE,
)
_ZH_NEGATION_RE = re.compile(
    r"(?:并不|并非|不是|没有|未能|无法|不能|不会|不必然|不一定|不可能|不导致|不造成|不支持|不意味着|不决定|不影响|无助于|不属于|不等于)"
)
_QUALIFICATION_RE = re.compile(
    r"(?:可能|未必|不一定|仅在|只有在|条件是|条件下|取决于|部分|有限|程度上|对于|当.+?时|\bmay\b|\bmight\b|\bcould\b|\bunder\b|\bonly\s+if\b|\bdepends?\s+on\b|\bto\s+some\s+extent\b)",
    re.IGNORECASE,
)
_CRITIQUE_RE = re.compile(
    r"(?:批评|批判|质疑|反驳|驳斥|挑战了|问题在于|\bcritic(?:ize|ise|ism|izes|ises|ized|ised)\b|\bchallenge[ds]?\b|\bobjects?\s+to\b)",
    re.IGNORECASE,
)
_EXTEND_RE = re.compile(
    r"(?:进一步|拓展|延伸|补充|在此基础上|\bextends?\b|\bbuilds?\s+on\b|\bdevelops?\s+further\b)",
    re.IGNORECASE,
)
_REFRAME_RE = re.compile(
    r"(?:不是.+?而是|重新界定|重新理解|转而强调|转向|应当看作|应理解为|\breframes?\b|\breconceptuali[sz]es?\b|\bshifts?\s+the\s+focus\b)",
    re.IGNORECASE,
)
_SUPPORT_RE = re.compile(
    r"(?:支持|印证|证实|一致|证据表明|\bsupports?\b|\bcorroborates?\b|\bconfirms?\b|\bconsistent\s+with\b)",
    re.IGNORECASE,
)
_OPPOSE_RE = re.compile(
    r"(?:反对|相斥|相反|否认|与.+?矛盾|\bopposes?\b|\bcontradicts?\b|\brejects?\b|\bcontrary\s+to\b)",
    re.IGNORECASE,
)


def _tuple_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        items = value.values()
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = value
    elif value:
        items = (value,)
    else:
        items = ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def _coerce_statement(value: ClaimStatement | Mapping[str, Any] | str) -> ClaimStatement:
    if isinstance(value, ClaimStatement):
        return value
    if isinstance(value, str):
        return ClaimStatement(proposition=value)
    if not isinstance(value, Mapping):
        raise TypeError("claim 必须是文本、mapping 或 ClaimStatement。")
    return ClaimStatement(
        proposition=str(value.get("proposition") or value.get("text") or "").strip(),
        subject=str(value.get("subject") or "").strip(),
        predicate=str(value.get("predicate") or "").strip(),
        object=str(value.get("object") or "").strip(),
        polarity=str(value.get("polarity") or "uncertain").strip().casefold(),
        modality=str(value.get("modality") or "").strip(),
        qualifiers=_tuple_values(value.get("qualifiers")),
        temporal_scope=value.get("temporal_scope") if isinstance(value.get("temporal_scope"), Mapping) else {},
        geographic_scope=value.get("geographic_scope") if isinstance(value.get("geographic_scope"), Mapping) else {},
        population_scope=value.get("population_scope") if isinstance(value.get("population_scope"), Mapping) else {},
        attribution=str(value.get("attribution") or "uncertain").strip().casefold(),
        claim_type=str(value.get("claim_type") or "assertion").strip().casefold(),
    )


def _normalized(value: str) -> str:
    return _SPACE_PUNCT_RE.sub("", str(value or "").casefold())


def _without_negation(value: str) -> str:
    value = _EN_NEGATION_RE.sub("", str(value or ""))
    replacements = (
        ("并不", ""),
        ("并非", ""),
        ("不导致", "导致"),
        ("不造成", "造成"),
        ("不支持", "支持"),
        ("不意味着", "意味着"),
        ("不决定", "决定"),
        ("不影响", "影响"),
        ("不属于", "属于"),
        ("不等于", "等于"),
        ("不是", "是"),
        ("没有", ""),
        ("未能", ""),
        ("无法", ""),
        ("不能", ""),
        ("不会", ""),
        ("不必然", ""),
        ("不一定", ""),
        ("不可能", ""),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return _normalized(value)


def _effective_polarity(statement: ClaimStatement) -> str:
    explicit = statement.polarity.casefold()
    if explicit in {"positive", "affirmed", "affirmative", "support"}:
        return "positive"
    if explicit in {"negative", "negated", "deny", "denied", "oppose"}:
        return "negative"
    if explicit == "mixed":
        return "mixed"
    text = " ".join(
        value
        for value in (
            statement.proposition,
            statement.predicate,
            statement.modality,
        )
        if value
    )
    if _EN_NEGATION_RE.search(text) or _ZH_NEGATION_RE.search(text):
        return "negative"
    return "positive" if text.strip() else "uncertain"


def _field_alignment(query: ClaimStatement, candidate: ClaimStatement) -> tuple[int, int]:
    compared = 0
    matched = 0
    for left, right in (
        (query.subject, candidate.subject),
        (query.predicate, candidate.predicate),
        (query.object, candidate.object),
    ):
        if not left or not right:
            continue
        compared += 1
        left_core = _without_negation(left)
        right_core = _without_negation(right)
        if left_core and right_core and (
            left_core == right_core
            or left_core in right_core
            or right_core in left_core
        ):
            matched += 1
    return matched, compared


def _character_bigrams(value: str) -> set[str]:
    folded = _without_negation(value)
    if len(folded) < 2:
        return {folded} if folded else set()
    return {folded[index:index + 2] for index in range(len(folded) - 1)}


def _propositions_align(query: ClaimStatement, candidate: ClaimStatement) -> bool:
    matched, compared = _field_alignment(query, candidate)
    if compared >= 2 and matched == compared:
        return True
    query_core = _without_negation(query.proposition)
    candidate_core = _without_negation(candidate.proposition)
    if query_core and query_core == candidate_core:
        return True
    left = _character_bigrams(query.proposition)
    right = _character_bigrams(candidate.proposition)
    if not left or not right:
        return False
    overlap = len(left & right) / max(1, len(left | right))
    return overlap >= 0.72


def _has_scope_or_qualification(statement: ClaimStatement) -> bool:
    text = " ".join((statement.proposition, statement.modality, *statement.qualifiers))
    return bool(
        statement.qualifiers
        or statement.temporal_scope
        or statement.geographic_scope
        or statement.population_scope
        or _QUALIFICATION_RE.search(text)
    )


def _result(
    stance: ClaimStance,
    confidence: float,
    reasons: tuple[str, ...],
    query_polarity: str,
    candidate_polarity: str,
) -> StanceResult:
    return StanceResult(
        stance=stance,
        confidence=max(0, min(round(confidence, 3), 1)),
        reasons=reasons,
        query_polarity=query_polarity,
        candidate_polarity=candidate_polarity,
    )


def classify_stance(
    query: ClaimStatement | Mapping[str, Any] | str,
    candidate: ClaimStatement | Mapping[str, Any] | str,
) -> StanceResult:
    """Classify stance from explicit claim structure and lexical operators.

    This deterministic layer is intentionally independent of embeddings.  A
    later model may add evidence-bound signals, but cosine similarity cannot
    override explicit negation, attribution, or scope qualifiers.
    """

    query_claim = _coerce_statement(query)
    candidate_claim = _coerce_statement(candidate)
    if not query_claim.proposition or not candidate_claim.proposition:
        raise ValueError("query 和 candidate claim 都必须包含 proposition。")
    query_polarity = _effective_polarity(query_claim)
    candidate_polarity = _effective_polarity(candidate_claim)
    text = " ".join(
        (
            candidate_claim.proposition,
            candidate_claim.predicate,
            candidate_claim.modality,
            *candidate_claim.qualifiers,
        )
    )
    aligned = _propositions_align(query_claim, candidate_claim)

    if (
        candidate_claim.attribution == "criticized_claim"
        or candidate_claim.claim_type == "criticism"
        or _CRITIQUE_RE.search(text)
    ):
        return _result(
            ClaimStance.CRITIQUE,
            0.96 if aligned else 0.84,
            ("explicit_criticism", "proposition_aligned" if aligned else "lexical_criticism"),
            query_polarity,
            candidate_polarity,
        )
    if _REFRAME_RE.search(text):
        return _result(
            ClaimStance.REFRAME,
            0.9,
            ("explicit_reframing",),
            query_polarity,
            candidate_polarity,
        )
    if _EXTEND_RE.search(text):
        return _result(
            ClaimStance.EXTEND,
            0.88,
            ("explicit_extension",),
            query_polarity,
            candidate_polarity,
        )
    if aligned and {query_polarity, candidate_polarity} == {"positive", "negative"}:
        return _result(
            ClaimStance.OPPOSE,
            0.99,
            ("same_proposition", "opposite_explicit_polarity"),
            query_polarity,
            candidate_polarity,
        )
    if _OPPOSE_RE.search(text):
        return _result(
            ClaimStance.OPPOSE,
            0.9,
            ("explicit_opposition",),
            query_polarity,
            candidate_polarity,
        )
    if aligned and _has_scope_or_qualification(candidate_claim):
        return _result(
            ClaimStance.QUALIFY,
            0.94,
            ("same_proposition", "scope_or_modality_qualification"),
            query_polarity,
            candidate_polarity,
        )
    if _QUALIFICATION_RE.search(text):
        return _result(
            ClaimStance.QUALIFY,
            0.82,
            ("explicit_qualification",),
            query_polarity,
            candidate_polarity,
        )
    normalized_query = _normalized(query_claim.proposition)
    normalized_candidate = _normalized(candidate_claim.proposition)
    if aligned and normalized_query == normalized_candidate:
        return _result(
            ClaimStance.DIRECT,
            0.98,
            ("exact_proposition",),
            query_polarity,
            candidate_polarity,
        )
    if aligned or _SUPPORT_RE.search(text):
        return _result(
            ClaimStance.SUPPORT,
            0.9 if aligned else 0.82,
            ("aligned_proposition" if aligned else "explicit_support",),
            query_polarity,
            candidate_polarity,
        )
    return _result(
        ClaimStance.DIRECT,
        0.35,
        ("direct_relevance_requires_validation",),
        query_polarity,
        candidate_polarity,
    )
