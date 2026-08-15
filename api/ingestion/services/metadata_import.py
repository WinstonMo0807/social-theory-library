from __future__ import annotations

from hashlib import sha256
import json

from django.db import transaction
from django.utils import timezone

from ingestion.models import SourceRecord, UploadItem

from .candidate_store import persist_metadata_candidates
from .metadata import Candidate
from .metadata_import_formats import ParsedMetadataImport, parse_metadata_import


IMPORT_PROVIDER_VERSION = "metadata-import-v1"


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _evidence_text(field_name: str, value, source_field: str) -> str:
    if isinstance(value, list):
        rendered = "; ".join(str(item) for item in value)
    else:
        rendered = str(value)
    return f"{source_field}: {rendered}"[:4000]


def _source_record_for_import(
    item: UploadItem,
    parsed: ParsedMetadataImport,
    *,
    filename: str,
    fingerprint: str,
) -> tuple[SourceRecord, bool]:
    provider = f"file_import:{parsed.format}"
    record = SourceRecord.objects.filter(
        upload_item=item,
        provider=provider,
        operation="metadata_import",
        request_fingerprint=fingerprint,
    ).first()
    if record:
        return record, True
    external_id = parsed.record_key or str(parsed.fields.get("doi") or parsed.fields.get("isbn") or "")
    return (
        SourceRecord.objects.create(
            upload_item=item,
            provider=provider,
            operation="metadata_import",
            query={"filename": filename, "format": parsed.format},
            request_fingerprint=fingerprint,
            external_id=external_id[:255],
            raw_response={
                "format": parsed.format,
                "filename": filename,
                "record": parsed.raw_record,
            },
            provider_version=IMPORT_PROVIDER_VERSION,
            retrieved_at=timezone.now(),
            status=SourceRecord.Status.SUCCEEDED,
        ),
        False,
    )


@transaction.atomic
def import_bibliographic_metadata(
    item: UploadItem,
    data: bytes,
    *,
    filename: str,
    format_hint: str = "",
) -> dict:
    """Import one structured record as review-only metadata candidates."""

    parsed = parse_metadata_import(data, format_hint=format_hint, filename=filename)
    fingerprint = sha256(
        b"\0".join(
            [
                IMPORT_PROVIDER_VERSION.encode("utf-8"),
                parsed.format.encode("utf-8"),
                data,
            ]
        )
    ).hexdigest()
    source_record, reused_source = _source_record_for_import(
        item,
        parsed,
        filename=filename,
        fingerprint=fingerprint,
    )
    source = f"import_{parsed.format}"
    candidates = []
    for field_name, value in parsed.fields.items():
        source_field = parsed.field_sources[field_name]
        evidence = {
            "source_record_id": str(source_record.id),
            "source_field": source_field,
            "text_quote": _evidence_text(field_name, value, source_field),
            "extraction_method": "structured_metadata_import",
            "import_format": parsed.format,
            "import_filename": filename,
        }
        if field_name == "doi":
            evidence["doi"] = value
            evidence["match_type"] = "imported_identifier"
        elif field_name == "isbn":
            evidence["isbn"] = value
            evidence["match_type"] = "imported_identifier"
        candidates.append(
            Candidate(
                field_name=field_name,
                value=value,
                source=source,
                confidence=0.88,
                evidence=evidence,
            )
        )
    stats = persist_metadata_candidates(
        item,
        candidates,
        selected={},
        supersede_sources={source},
    )
    imported = list(
        item.metadata_candidates.filter(source_record=source_record)
        .prefetch_related("evidence_records")
        .order_by("field_name", "-confidence", "created_at")
    )
    return {
        "format": parsed.format,
        "filename": filename,
        "source_record": source_record,
        "reused_source": reused_source,
        "stats": stats,
        "candidates": imported,
        "fingerprint": fingerprint,
        "normalized_record_sha256": sha256(_stable_json(parsed.fields).encode("utf-8")).hexdigest(),
    }
