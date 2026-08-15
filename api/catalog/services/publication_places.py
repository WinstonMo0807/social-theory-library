from __future__ import annotations

import re
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    Edition,
    PublicationMetadataRevision,
    PublicationPlaceEvidence,
    PublisherAuthority,
)


CHINESE_STANDARD_RE = re.compile(
    r"(?P<place>[\u3400-\u9fff]{2,16})\s*[：:]\s*"
    r"(?P<publisher>[^\n，,。;；]{2,100}?(?:出版社|出版公司|出版集团|书局|Press))"
    r"\s*[，,]\s*(?P<year>(?:18|19|20)\d{2})",
    re.I,
)
EXPLICIT_PLACE_RE = re.compile(r"(?:出版地|出版地点|Place\s+of\s+publication)\s*[：:]\s*(?P<place>[^\n，,。;；]{2,80})", re.I)
ENGLISH_STANDARD_RE = re.compile(
    r"(?P<place>[A-Z][A-Za-z .'-]{1,50})\s*[：:;,]\s*"
    r"(?P<publisher>[^\n.;]{2,100}?(?:University\s+Press|Press|Publishing|Publishers?))"
    r"(?:\s*[，,]\s*|\s+)(?P<year>(?:18|19|20)\d{2})",
    re.I,
)
PRINT_RE = re.compile(r"(?:印刷地|印刷单位|printed\s+in)\s*[：:]?\s*(?P<place>[^\n，,。;；]{2,80})", re.I)
DISTRIBUTION_RE = re.compile(r"(?:发行地|发行单位|distributed\s+by)\s*[：:]?\s*(?P<place>[^\n，,。;；]{2,80})", re.I)
ADDRESS_RE = re.compile(r"(?:地址|Address)\s*[：:]\s*(?P<place>[^\n]{3,160})", re.I)


def _clean_place(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" ，,。.;；:：")
    value = re.sub(r"^(?:出版地|出版地点)\s*[：:]\s*", "", value)
    return value[:300]


def _compatible(candidate, current) -> bool:
    if not candidate or not current:
        return True
    return str(candidate).casefold().strip() in str(current).casefold().strip() or str(current).casefold().strip() in str(candidate).casefold().strip()


def _page_scope(asset: Asset):
    count = asset.pages.count()
    indexes = set(range(1, min(10, count) + 1))
    indexes.update(range(max(1, count - 4), count + 1))
    return asset.pages.filter(index__in=sorted(indexes)).order_by("index")


def _publication_page_texts(asset: Asset, *, allow_targeted_ocr: bool = True) -> list[dict]:
    pages = list(_page_scope(asset))
    output = [
        {"page": page, "text": page.text or "", "source": "pdf_text_layer"}
        for page in pages
    ]
    missing = [
        row["page"].index
        for row in output
        if len(re.sub(r"\s+", "", row["text"])) < 32
    ]
    if (
        not missing
        or not allow_targeted_ocr
        or asset.extraction_method.startswith("paddleocr")
    ):
        return output
    try:
        from ingestion.services.ocr_provider import parse_pdf_pages_with_ocr

        payload, provider = parse_pdf_pages_with_ocr(asset.file.path, missing)
    except (AttributeError, OSError, RuntimeError, ValueError):
        return output
    ocr_by_page = {
        int(page["index"]): "\n".join(
            block.get("text", "")
            for block in page.get("blocks", [])
            if block.get("text", "").strip()
        )
        for page in payload.get("pages", [])
    }
    for row in output:
        ocr_text = ocr_by_page.get(row["page"].index, "")
        if ocr_text.strip():
            row["text"] = ocr_text
            row["source"] = f"targeted_{provider}"
    return output


def _direct_candidates(asset: Asset, *, allow_targeted_ocr: bool = True) -> list[dict]:
    edition = asset.edition
    results = []
    for page_data in _publication_page_texts(
        asset,
        allow_targeted_ocr=allow_targeted_ocr,
    ):
        page = page_data["page"]
        text = page_data["text"]
        patterns = (
            (CHINESE_STANDARD_RE, PublicationPlaceEvidence.PlaceType.PUBLICATION, "pdf_copyright_page", 0.97),
            (ENGLISH_STANDARD_RE, PublicationPlaceEvidence.PlaceType.PUBLICATION, "pdf_title_or_copyright_page", 0.94),
            (EXPLICIT_PLACE_RE, PublicationPlaceEvidence.PlaceType.PUBLICATION, "pdf_explicit_field", 0.96),
            (PRINT_RE, PublicationPlaceEvidence.PlaceType.PRINTING, "pdf_printing_statement", 0.91),
            (DISTRIBUTION_RE, PublicationPlaceEvidence.PlaceType.DISTRIBUTION, "pdf_distribution_statement", 0.91),
            (ADDRESS_RE, PublicationPlaceEvidence.PlaceType.PUBLISHER_ADDRESS, "pdf_publisher_address", 0.72),
        )
        for pattern, place_type, source_type, confidence in patterns:
            for match in pattern.finditer(text):
                place = _clean_place(match.group("place"))
                if not place:
                    continue
                publisher = _clean_place(match.groupdict().get("publisher", ""))
                year_text = match.groupdict().get("year")
                year = int(year_text) if year_text else None
                compatible_version = _compatible(publisher, edition.publisher) and _compatible(year, edition.publication_year)
                status = PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW
                if place_type == PublicationPlaceEvidence.PlaceType.PUBLICATION and confidence >= 0.9 and compatible_version:
                    status = PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED
                evidence_text = " ".join(match.group(0).split())[:1000]
                results.append(
                    {
                        "raw_value": place,
                        "normalized_value": place,
                        "city": place,
                        "language": edition.work.language,
                        "place_type": place_type,
                        "source_type": source_type,
                        "source_provider": page_data["source"],
                        "evidence_page": page.index,
                        "evidence_text": evidence_text,
                        "confidence": confidence if compatible_version else max(0.5, confidence - 0.22),
                        "verification_status": status if compatible_version else PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW,
                        "publisher_raw": publisher,
                        "publication_year": year,
                        "relation": "publication" if place_type == PublicationPlaceEvidence.PlaceType.PUBLICATION else place_type,
                    }
                )
    return results


def _metadata_candidates(asset: Asset) -> list[dict]:
    from ingestion.models import MetadataCandidate

    edition = asset.edition
    item = edition.upload_items.order_by("-created_at").first() if hasattr(edition, "upload_items") else None
    if item is None:
        from ingestion.models import UploadItem

        item = UploadItem.objects.filter(edition=edition).order_by("-created_at").first()
    if item is None:
        return []
    output = []
    for candidate in MetadataCandidate.objects.filter(
        upload_item=item,
        field_name="publication_place",
    ).order_by("-confidence"):
        evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
        field = str(evidence.get("field") or evidence.get("marc_field") or "").strip()
        indicator2 = str(evidence.get("indicator2") or evidence.get("second_indicator") or "").strip()
        relation = str(evidence.get("relation") or "publication").strip().casefold()
        place_type = PublicationPlaceEvidence.PlaceType.PUBLICATION
        if candidate.source == "marc21" and field == "264":
            if indicator2 == "0":
                place_type = PublicationPlaceEvidence.PlaceType.PRODUCTION
                relation = "production"
            elif indicator2 == "1":
                place_type = PublicationPlaceEvidence.PlaceType.PUBLICATION
                relation = "publication"
            elif indicator2 == "2":
                place_type = PublicationPlaceEvidence.PlaceType.DISTRIBUTION
                relation = "distribution"
            elif indicator2 == "3":
                place_type = PublicationPlaceEvidence.PlaceType.PRINTING
                relation = "manufacture"
            else:
                place_type = PublicationPlaceEvidence.PlaceType.PRODUCTION
                relation = "copyright_or_other"
        elif relation in {"distribution", "distributed"}:
            place_type = PublicationPlaceEvidence.PlaceType.DISTRIBUTION
        elif relation in {"printing", "manufacture", "manufacturing"}:
            place_type = PublicationPlaceEvidence.PlaceType.PRINTING
        elif relation in {"production", "produced"}:
            place_type = PublicationPlaceEvidence.PlaceType.PRODUCTION
        values = candidate.value if isinstance(candidate.value, list) else [candidate.value]
        for order, raw in enumerate(values):
            place = _clean_place(str(raw or ""))
            if not place:
                continue
            authoritative = (
                candidate.source in {"openlibrary", "marc21", "onix"}
                and place_type == PublicationPlaceEvidence.PlaceType.PUBLICATION
            )
            source_type = "isbn_authority_record" if authoritative else "metadata_candidate"
            if candidate.source == "marc21":
                source_type = f"marc21_{field or 'unknown'}_{relation}"
            elif candidate.source == "onix":
                source_type = f"onix_{relation}"
            version_matches = (
                _compatible(evidence.get("publisher"), edition.publisher)
                and _compatible(evidence.get("publication_year") or evidence.get("year"), edition.publication_year)
            )
            confidence = min(0.98, max(float(candidate.confidence), 0.9 if authoritative else 0.6))
            if not version_matches:
                confidence = max(0.5, confidence - 0.22)
            output.append(
                {
                    "raw_value": place,
                    "normalized_value": place,
                    "city": place,
                    "language": edition.work.language,
                    "place_type": place_type,
                    "source_type": source_type,
                    "source_provider": candidate.source,
                    "source_record_id": str(evidence.get("record_id") or edition.isbn or ""),
                    "evidence_text": str(
                        evidence.get("raw_text")
                        or evidence.get("evidence_text")
                        or (f"ISBN {edition.isbn} 的版本记录给出{relation}地点 {place}" if edition.isbn else "外部书目候选")
                    )[:1000],
                    "confidence": confidence,
                    "verification_status": (
                        PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED
                        if authoritative and edition.isbn and confidence >= 0.9 and version_matches
                        else PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW
                    ),
                    "is_primary": order == 0,
                    "publisher_raw": edition.publisher,
                    "publication_year": edition.publication_year,
                    "relation": relation,
                }
            )
    return output


def _authority_candidates(asset: Asset) -> list[dict]:
    publisher = asset.edition.publisher.strip()
    if not publisher:
        return []
    authority = PublisherAuthority.objects.filter(canonical_name__iexact=publisher).first()
    if authority is None:
        for item in PublisherAuthority.objects.all()[:1000]:
            if publisher.casefold() in {str(value).casefold() for value in item.aliases or []}:
                authority = item
                break
    if authority is None:
        return []
    year = asset.edition.publication_year
    if authority.valid_from and year and year < authority.valid_from:
        return []
    if authority.valid_to and year and year > authority.valid_to:
        return []
    return [
        {
            "raw_value": _clean_place(str(place)),
            "normalized_value": _clean_place(str(place)),
            "city": _clean_place(str(place)),
            "country": authority.country,
            "language": asset.edition.work.language,
            "place_type": PublicationPlaceEvidence.PlaceType.PUBLICATION,
            "source_type": "publisher_authority",
            "source_provider": "local_authority_table",
            "source_record_id": str(authority.id),
            "evidence_text": "出版社规范库候选。当前 PDF 未找到直接出版关系证据。",
            "confidence": 0.6,
            "verification_status": PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW,
            "publisher_raw": publisher,
            "publication_year": year,
            "relation": "publication",
        }
        for place in authority.possible_places or []
        if _clean_place(str(place))
    ]


def _deduplicate(candidates: list[dict]) -> list[dict]:
    best = {}
    for item in candidates:
        key = (
            item.get("normalized_value", "").casefold(),
            item.get("place_type"),
            item.get("source_type"),
            item.get("evidence_page"),
        )
        previous = best.get(key)
        if previous is None or item.get("confidence", 0) > previous.get("confidence", 0):
            best[key] = item
    return sorted(best.values(), key=lambda item: (-item.get("confidence", 0), item.get("evidence_page") or 99999))


@transaction.atomic
def detect_publication_places(
    asset: Asset,
    *,
    force: bool = False,
    allow_targeted_ocr: bool = True,
) -> list[PublicationPlaceEvidence]:
    edition = Edition.objects.select_for_update().select_related("work").get(pk=asset.edition_id)
    manual_statuses = {
        PublicationPlaceEvidence.VerificationStatus.MANUALLY_CONFIRMED,
        PublicationPlaceEvidence.VerificationStatus.MANUALLY_CORRECTED,
    }
    if force:
        edition.publication_place_evidence.exclude(verification_status__in=manual_statuses).delete()
    elif edition.publication_place_evidence.exclude(verification_status__in=manual_statuses).exists():
        return list(edition.publication_place_evidence.all())

    candidates = _deduplicate([
        *_direct_candidates(asset, allow_targeted_ocr=allow_targeted_ocr),
        *_metadata_candidates(asset),
        *_authority_candidates(asset),
    ])
    manual_exists = edition.publication_place_evidence.filter(verification_status__in=manual_statuses).exists()
    publication_candidates = [
        item for item in candidates
        if item["place_type"] == PublicationPlaceEvidence.PlaceType.PUBLICATION
    ]
    confirmed_groups = defaultdict(set)
    for item in publication_candidates:
        if item["verification_status"] != PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED:
            continue
        source_key = (
            item.get("source_provider") or item.get("source_type"),
            item.get("source_record_id") or item.get("evidence_page"),
            item.get("source_type"),
        )
        confirmed_groups[source_key].add(item["normalized_value"].casefold())
    source_value_sets = list(confirmed_groups.values())
    sources_conflict = bool(
        len(source_value_sets) > 1
        and not set.intersection(*source_value_sets)
    )
    if sources_conflict:
        for item in publication_candidates:
            item["verification_status"] = PublicationPlaceEvidence.VerificationStatus.NEEDS_REVIEW
    rows = []
    for order, item in enumerate(candidates):
        item["display_order"] = order
        item["is_primary"] = bool(
            item.get("is_primary")
            or (
                order == 0
                and item["place_type"] == PublicationPlaceEvidence.PlaceType.PUBLICATION
                and item["verification_status"] == PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED
            )
        )
        rows.append(PublicationPlaceEvidence.objects.create(edition=edition, asset=asset, **item))
    if not rows:
        rows.append(
            PublicationPlaceEvidence.objects.create(
                edition=edition,
                asset=asset,
                place_type=PublicationPlaceEvidence.PlaceType.PUBLICATION,
                source_type="recognition_result",
                evidence_text="当前 PDF 与已配置书目来源中没有足够的出版地证据。",
                verification_status=PublicationPlaceEvidence.VerificationStatus.UNKNOWN,
                confidence=0,
            )
        )
    if not manual_exists:
        apply_confirmed_primary(edition)
    return list(edition.publication_place_evidence.all())


def confirmed_publication_places(edition: Edition) -> list[str]:
    statuses = [
        PublicationPlaceEvidence.VerificationStatus.MANUALLY_CORRECTED,
        PublicationPlaceEvidence.VerificationStatus.MANUALLY_CONFIRMED,
        PublicationPlaceEvidence.VerificationStatus.AUTO_CONFIRMED,
    ]
    values = list(
        edition.publication_place_evidence.filter(
            place_type=PublicationPlaceEvidence.PlaceType.PUBLICATION,
            verification_status__in=statuses,
        )
        .order_by("-is_primary", "display_order", "-confidence")
        .values_list("normalized_value", flat=True)
    )
    values = list(dict.fromkeys(value for value in values if value))
    if not values and edition.publication_place:
        values = [_clean_place(edition.publication_place)]
    return values


def apply_confirmed_primary(edition: Edition) -> str:
    places = confirmed_publication_places(edition)
    primary = places[0] if places else ""
    if edition.publication_place != primary:
        edition.publication_place = primary
        citation_data = dict(edition.citation_data or {})
        if primary:
            citation_data["publisher-place"] = primary
        else:
            citation_data.pop("publisher-place", None)
        edition.citation_data = citation_data
        edition.save(update_fields=["publication_place", "citation_data", "updated_at"])
    return primary


@transaction.atomic
def confirm_publication_place(evidence: PublicationPlaceEvidence, *, actor, corrected_value="", reason=""):
    edition = Edition.objects.select_for_update().get(pk=evidence.edition_id)
    before = {"publication_place": edition.publication_place, "evidence_id": str(evidence.id)}
    value = _clean_place(corrected_value) or evidence.normalized_value
    edition.publication_place_evidence.filter(
        place_type=PublicationPlaceEvidence.PlaceType.PUBLICATION,
        is_primary=True,
    ).update(is_primary=False, updated_at=timezone.now())
    evidence.normalized_value = value
    evidence.city = value
    evidence.is_primary = True
    evidence.verification_status = (
        PublicationPlaceEvidence.VerificationStatus.MANUALLY_CORRECTED
        if corrected_value and value != evidence.raw_value
        else PublicationPlaceEvidence.VerificationStatus.MANUALLY_CONFIRMED
    )
    evidence.verified_by = actor
    evidence.verified_at = timezone.now()
    evidence.save()
    apply_confirmed_primary(edition)
    PublicationMetadataRevision.objects.create(
        edition=edition,
        actor=actor,
        action="publication_place_corrected" if corrected_value else "publication_place_confirmed",
        before=before,
        after={"publication_place": edition.publication_place, "evidence_id": str(evidence.id)},
        reason=reason,
    )
    return evidence


@transaction.atomic
def record_manual_publication_places(edition: Edition, value: str, *, actor, reason="metadata_review"):
    before = {"publication_place": edition.publication_place}
    values = [_clean_place(item) for item in re.split(r"[;；·]", value or "")]
    values = list(dict.fromkeys(item for item in values if item))
    edition.publication_place_evidence.filter(
        verification_status__in=[
            PublicationPlaceEvidence.VerificationStatus.MANUALLY_CONFIRMED,
            PublicationPlaceEvidence.VerificationStatus.MANUALLY_CORRECTED,
        ]
    ).delete()
    edition.publication_place_evidence.filter(
        place_type=PublicationPlaceEvidence.PlaceType.PUBLICATION,
        is_primary=True,
    ).update(is_primary=False, updated_at=timezone.now())
    for order, place in enumerate(values):
        PublicationPlaceEvidence.objects.create(
            edition=edition,
            raw_value=place,
            normalized_value=place,
            city=place,
            language=edition.work.language,
            place_type=PublicationPlaceEvidence.PlaceType.PUBLICATION,
            source_type="manual_metadata_review",
            source_provider="administrator",
            evidence_text="管理员在元数据复核页填写。",
            confidence=1,
            verification_status=PublicationPlaceEvidence.VerificationStatus.MANUALLY_CORRECTED,
            is_primary=order == 0,
            display_order=order,
            publisher_raw=edition.publisher,
            publication_year=edition.publication_year,
            verified_by=actor,
            verified_at=timezone.now(),
        )
    edition.publication_place = values[0] if values else ""
    citation_data = dict(edition.citation_data or {})
    if values:
        citation_data["publisher-place"] = values[0]
    else:
        citation_data.pop("publisher-place", None)
    edition.citation_data = citation_data
    edition.save(update_fields=["publication_place", "citation_data", "updated_at"])
    PublicationMetadataRevision.objects.create(
        edition=edition,
        actor=actor,
        action="publication_place_manual_review",
        before=before,
        after={"publication_place": edition.publication_place, "all_places": values},
        reason=reason,
    )


def serialize_publication_place_evidence(evidence: PublicationPlaceEvidence) -> dict:
    return {
        "id": str(evidence.id),
        "raw_value": evidence.raw_value,
        "normalized_value": evidence.normalized_value,
        "place_type": evidence.place_type,
        "source_type": evidence.source_type,
        "source_provider": evidence.source_provider,
        "source_record_id": evidence.source_record_id,
        "evidence_page": evidence.evidence_page,
        "evidence_text": evidence.evidence_text,
        "confidence": evidence.confidence,
        "verification_status": evidence.verification_status,
        "is_primary": evidence.is_primary,
        "publisher_raw": evidence.publisher_raw,
        "publication_year": evidence.publication_year,
        "verified_at": evidence.verified_at,
    }
