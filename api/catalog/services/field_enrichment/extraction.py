from __future__ import annotations

from hashlib import sha256
import re
from typing import Iterable

from catalog.models import EnrichmentSourceClass
from catalog.services.passage_language import detect_passage_language
from catalog.services.query_lexicon.candidates import extract_explicit_pairs
from catalog.services.query_lexicon.normalization import normalize_term

from .policies import FieldPolicy
from .types import FetchedDocument, FieldObservation
from .values import stable_json


YEAR_RE = re.compile(r"(?<!\d)(1[5-9]\d{2}|20\d{2}|2100)(?!\d)")
ISBN_RE = re.compile(r"(?:ISBN(?:-1[03])?\s*[:：]?\s*)?((?:97[89][\s-]?)?\d[\d\s-]{7,15}[\dXx])")
ORCID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b", re.I)
WIKIDATA_RE = re.compile(r"\b(Q\d{2,})\b", re.I)
VIAF_RE = re.compile(r"(?:VIAF\s*(?:ID)?\s*[:：]?\s*)(\d{3,})", re.I)
OPENALEX_RE = re.compile(r"\b(A\d{5,})\b", re.I)
LOC_RE = re.compile(r"(?:LCCN|LOC)\s*[:：]?\s*([a-z]{0,3}\d{4,})", re.I)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.I)


RELATION_PHRASES = {
    "influenced_by": ("influenced by", "受到", "受其影响", "深受"),
    "criticizes": ("criticizes", "criticised", "批判", "批评"),
    "revises": ("revises", "extends", "修正", "发展了", "推进了"),
    "extends": ("extends", "develops", "扩展", "发展了", "推进了"),
    "inherited_from": ("derived from", "inherits", "继承", "源自"),
    "responds_to": ("responds to", "回应"),
    "competes_with": ("competes with", "竞争", "对立"),
    "synthesizes": ("synthesizes", "综合"),
    "branches_from": ("branches from", "分化自"),
    "borrows_concept_from": ("borrows", "借用"),
    "transferred_to": ("transferred to", "传播到", "引入"),
    "overlaps_with": ("overlaps with", "部分重叠", "交叉"),
}


def _sentences(text: str) -> list[tuple[int, int, str]]:
    output = []
    start = 0
    for match in re.finditer(r"[。！？!?；;\n]+", text):
        end = match.end()
        value = " ".join(text[start:end].split())
        if value:
            output.append((start, end, value[:1600]))
        start = end
    if start < len(text):
        value = " ".join(text[start:].split())
        if value:
            output.append((start, len(text), value[:1600]))
    return output


def _contains_term(text: str, term: str) -> bool:
    term = str(term or "").strip()
    if not term:
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._'’-]*", term):
        return bool(
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                text,
                re.I,
            )
        )
    return normalize_term(term) in normalize_term(text)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if _contains_term(text, term)]


def _identity_claims(document: FetchedDocument, context: dict) -> dict:
    text = document.text
    matched = _matched_terms(text, context.get("canonical_terms") or [])
    claims = {
        "names": matched,
        "matched_target_terms": matched,
        "external_ids": {},
        "affiliations": [],
        "works": _matched_terms(text, context.get("works") or []),
        "authors": _matched_terms(text, context.get("authors") or []),
    }
    birth = re.search(r"(?:born|生于|出生于)[^\d]{0,20}(1[5-9]\d{2}|20\d{2})", text, re.I)
    death = re.search(r"(?:died|卒于|逝世于)[^\d]{0,20}(1[5-9]\d{2}|20\d{2})", text, re.I)
    if birth:
        claims["birth_year"] = int(birth.group(1))
    if death:
        claims["death_year"] = int(death.group(1))
    for scheme, pattern in (
        ("orcid", ORCID_RE),
        ("wikidata", WIKIDATA_RE),
        ("viaf", VIAF_RE),
        ("openalex", OPENALEX_RE),
        ("loc", LOC_RE),
    ):
        match = pattern.search(text)
        if match:
            claims["external_ids"][scheme] = match.group(1)
    if context.get("title") and _contains_term(text, context["title"]):
        claims["title"] = context["title"]
    year = next((int(value) for value in YEAR_RE.findall(text)[:20] if int(value) == context.get("publication_year")), None)
    if year:
        claims["publication_year"] = year
    if context.get("publisher") and _contains_term(text, context["publisher"]):
        claims["publisher"] = context["publisher"]
    for scheme in ("doi", "isbn"):
        value = str(context.get(scheme) or "").strip()
        if value and _contains_term(text.replace("-", ""), value.replace("-", "")):
            claims["external_ids"][scheme] = value
    return claims


def _observation(
    *,
    document: FetchedDocument,
    policy: FieldPolicy,
    value,
    supporting_text: str,
    locator: dict,
    context: dict,
    confidence_factors: dict | None = None,
) -> FieldObservation:
    return FieldObservation(
        field_name=policy.field_name,
        value=value,
        provider="web_fetch",
        source_class=document.source_class,
        source_url=document.source_url,
        canonical_url=document.canonical_url,
        source_title=document.title,
        supporting_text=supporting_text[:4000],
        content_checksum=document.content_checksum,
        retrieved_at=document.retrieved_at,
        locator=locator,
        source_record_id=document.source_record_id,
        identity_claims=_identity_claims(document, context),
        confidence_factors=confidence_factors or {"explicit_text_span": True},
        http_status=document.http_status,
        content_type=document.content_type,
        extraction_method="deterministic_web_text",
    )


def _explicit_name_pairs(
    document: FetchedDocument,
    policy: FieldPolicy,
    context: dict,
) -> list[FieldObservation]:
    pairs, _audit = extract_explicit_pairs(document.text)
    canonical = {normalize_term(value) for value in context.get("canonical_terms") or []}
    output = []
    for pair in pairs:
        left = normalize_term(pair.left)
        right = normalize_term(pair.right)
        if left in canonical and right not in canonical:
            proposed = pair.right
        elif right in canonical and left not in canonical:
            proposed = pair.left
        else:
            continue
        language = detect_passage_language(proposed)
        if policy.field_name == "name_variant":
            value = {
                "name": proposed,
                "language": language,
                "variant_type": "transliteration" if language in {"zh", "en"} else "alias",
            }
        elif policy.field_name == "alias":
            value = {
                "alias": proposed,
                "language": language,
                "alias_type": "translation" if language in {"zh", "en"} else "alias",
            }
        else:
            if language != "en":
                continue
            value = proposed
        output.append(
            _observation(
                document=document,
                policy=policy,
                value=value,
                supporting_text=document.text[pair.start:pair.end],
                locator={"start": pair.start, "end": pair.end, "method": pair.method},
                context=context,
                confidence_factors={"explicit_bilingual_pair": True, "method": pair.method},
            )
        )
    return output


def _labeled_value_sentences(document: FetchedDocument, labels: tuple[str, ...], pattern: re.Pattern):
    for start, end, sentence in _sentences(document.text):
        if not any(label.casefold() in sentence.casefold() for label in labels):
            continue
        match = pattern.search(sentence)
        if match:
            yield start, end, sentence, match.group(1)


def extract_web_observations(
    *,
    document: FetchedDocument,
    policy: FieldPolicy,
    context: dict,
    form_context: dict,
) -> list[FieldObservation]:
    if policy.field_name in {"name_variant", "alias", "foreign_name"}:
        return _explicit_name_pairs(document, policy, context)
    output: list[FieldObservation] = []
    if policy.field_name == "external_identifier":
        for scheme, pattern in (
            ("orcid", ORCID_RE),
            ("wikidata", WIKIDATA_RE),
            ("viaf", VIAF_RE),
            ("openalex", OPENALEX_RE),
            ("loc", LOC_RE),
        ):
            for match in pattern.finditer(document.text):
                start = max(0, match.start() - 180)
                end = min(len(document.text), match.end() + 180)
                output.append(
                    _observation(
                        document=document,
                        policy=policy,
                        value={"scheme": scheme, "value": match.group(1)},
                        supporting_text=document.text[start:end],
                        locator={"start": match.start(), "end": match.end(), "pattern": scheme},
                        context=context,
                    )
                )
    elif policy.field_name == "affiliation":
        pattern = re.compile(
            r"(?:Professor|Researcher|Faculty member|现任|任职于|就职于|隶属于)\s*(?:at|of|为|：|:)?\s*([^。；;\n]{3,120})",
            re.I,
        )
        for match in pattern.finditer(document.text):
            name = " ".join(match.group(1).split()).strip(" ,，。")
            if len(name) < 3:
                continue
            start = max(0, match.start() - 100)
            end = min(len(document.text), match.end() + 100)
            claims = _identity_claims(document, context)
            claims["affiliations"] = [{"name": name}]
            row = _observation(
                document=document,
                policy=policy,
                value={"name": name},
                supporting_text=document.text[start:end],
                locator={"start": match.start(), "end": match.end(), "pattern": "affiliation"},
                context=context,
            )
            output.append(FieldObservation(**{**row.__dict__, "identity_claims": claims}))
    elif policy.field_name == "publication_year":
        for start, end, sentence, value in _labeled_value_sentences(
            document,
            ("published", "publication", "出版", "发行"),
            YEAR_RE,
        ):
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=int(value),
                    supporting_text=sentence,
                    locator={"start": start, "end": end, "pattern": "publication_year"},
                    context=context,
                )
            )
    elif policy.field_name == "publisher":
        pattern = re.compile(
            r"(?:Publisher|Published by|出版社|出版者)\s*[:：]?\s*([^。；;\n]{2,120})",
            re.I,
        )
        for match in pattern.finditer(document.text):
            value = " ".join(match.group(1).split()).strip(" ,，。")
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=value,
                    supporting_text=document.text[max(0, match.start() - 80):min(len(document.text), match.end() + 80)],
                    locator={"start": match.start(), "end": match.end(), "pattern": "publisher"},
                    context=context,
                )
            )
    elif policy.field_name in {"isbn", "isbn10", "isbn13"}:
        for match in ISBN_RE.finditer(document.text):
            if "ISBN" not in document.text[max(0, match.start() - 20):match.start() + 8].upper():
                continue
            value = re.sub(r"[^0-9Xx]", "", match.group(1)).upper()
            if policy.field_name == "isbn10" and len(value) != 10:
                continue
            if policy.field_name == "isbn13" and len(value) != 13:
                continue
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=value,
                    supporting_text=document.text[max(0, match.start() - 80):min(len(document.text), match.end() + 80)],
                    locator={"start": match.start(), "end": match.end(), "pattern": "isbn"},
                    context=context,
                )
            )
    elif policy.field_name == "doi":
        for match in DOI_RE.finditer(document.text):
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=match.group(1).rstrip(".,;)]}"),
                    supporting_text=document.text[max(0, match.start() - 120):min(len(document.text), match.end() + 120)],
                    locator={"start": match.start(), "end": match.end(), "pattern": "doi"},
                    context=context,
                )
            )
    elif policy.field_name in {
        "journal_title",
        "volume",
        "issue",
        "page_range",
        "publication_place",
        "series",
        "degree_institution",
        "degree_type",
        "report_institution",
    }:
        labels = {
            "journal_title": ("journal", "期刊", "刊名"),
            "volume": ("volume", "vol.", "卷"),
            "issue": ("issue", "no.", "期"),
            "page_range": ("pages", "pp.", "页码"),
            "publication_place": ("place of publication", "出版地"),
            "series": ("series", "丛书"),
            "degree_institution": ("institution", "university", "学位授予单位"),
            "degree_type": ("degree", "学位类型"),
            "report_institution": ("issuing institution", "研究机构", "报告机构"),
        }[policy.field_name]
        pattern = re.compile(
            rf"(?:{'|'.join(re.escape(label) for label in labels)})\s*[:：]?\s*([^。；;\n]{{1,180}})",
            re.I,
        )
        for match in pattern.finditer(document.text):
            value = " ".join(match.group(1).split()).strip(" ,，。")
            if policy.field_name in {"volume", "issue"}:
                value = value.split()[0][:40]
            elif policy.field_name == "page_range":
                page_match = re.search(r"\d+\s*[-–—]\s*\d+", value)
                if not page_match:
                    continue
                value = page_match.group(0)
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=value,
                    supporting_text=document.text[max(0, match.start() - 100):min(len(document.text), match.end() + 100)],
                    locator={"start": match.start(), "end": match.end(), "pattern": policy.field_name},
                    context=context,
                )
            )
    elif policy.field_name == "first_publication_date":
        for start, end, sentence, value in _labeled_value_sentences(
            document,
            ("first published", "首次出版", "初版"),
            YEAR_RE,
        ):
            output.append(
                _observation(
                    document=document,
                    policy=policy,
                    value=f"{value}-01-01",
                    supporting_text=sentence,
                    locator={"start": start, "end": end, "pattern": "first_publication_year"},
                    context=context,
                    confidence_factors={"year_precision_only": True},
                )
            )
    elif policy.field_name in {"discipline", "subdiscipline"}:
        options_key = "discipline_options" if policy.field_name == "discipline" else "subdiscipline_options"
        for option in form_context.get(options_key) or []:
            if not isinstance(option, dict) or not option.get("id") or not option.get("name"):
                continue
            for start, end, sentence in _sentences(document.text):
                if not _matched_terms(sentence, context.get("canonical_terms") or []):
                    continue
                if not _contains_term(sentence, option["name"]):
                    continue
                if policy.field_name == "discipline":
                    value = {"discipline_id": option["id"], "relation_type": option.get("relation_type") or "related"}
                else:
                    value = {"subdiscipline_node_id": option["id"]}
                output.append(
                    _observation(
                        document=document,
                        policy=policy,
                        value=value,
                        supporting_text=sentence,
                        locator={"start": start, "end": end, "pattern": options_key},
                        context=context,
                    )
                )
    elif policy.field_name == "relation":
        target_name = str(form_context.get("related_entity_name") or "").strip()
        target_id = str(form_context.get("target_node_id") or "").strip()
        relation_type = str(form_context.get("relation_type") or "").strip().casefold()
        phrases = RELATION_PHRASES.get(relation_type, ())
        if target_name and target_id and phrases:
            for start, end, sentence in _sentences(document.text):
                if not _matched_terms(sentence, context.get("canonical_terms") or []):
                    continue
                if not _contains_term(sentence, target_name):
                    continue
                if not any(phrase.casefold() in sentence.casefold() for phrase in phrases):
                    continue
                output.append(
                    _observation(
                        document=document,
                        policy=policy,
                        value={
                            "target_node_id": target_id,
                            "relation_type": relation_type,
                            "description": sentence,
                        },
                        supporting_text=sentence,
                        locator={"start": start, "end": end, "pattern": "explicit_relation_phrase"},
                        context=context,
                        confidence_factors={"explicit_relation_phrase": True, "cooccurrence_only": False},
                    )
                )
    elif policy.field_name in {"timeline_fact", "timeline_interpretation", "item"}:
        proposed = form_context.get("proposed_value")
        if proposed:
            for start, end, sentence in _sentences(document.text):
                if not _matched_terms(sentence, context.get("canonical_terms") or []):
                    continue
                if policy.field_name == "timeline_fact" and not YEAR_RE.search(sentence):
                    continue
                output.append(
                    _observation(
                        document=document,
                        policy=policy,
                        value=proposed,
                        supporting_text=sentence,
                        locator={"start": start, "end": end, "pattern": "editorial_proposal_support"},
                        context=context,
                        confidence_factors={"editorial_value_not_inferred": True},
                    )
                )
                break
    return output


def observation_fingerprint(observation: FieldObservation) -> str:
    payload = stable_json(
        {
            "field": observation.field_name,
            "value": observation.value,
            "canonical_url": observation.canonical_url,
            "supporting_text": observation.supporting_text,
            "content_checksum": observation.content_checksum,
        }
    )
    return sha256(payload.encode("utf-8")).hexdigest()
