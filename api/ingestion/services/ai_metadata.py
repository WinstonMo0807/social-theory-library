from __future__ import annotations

from hashlib import sha256

from django.utils import timezone

from ingestion.models import SourceRecord

from .ai_client import AIClient, AIServiceError
from .metadata import Candidate


AI_METADATA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": 24,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field_name", "value", "evidence", "reason", "warnings"],
                "properties": {
                    "field_name": {
                        "type": "string",
                        "enum": [
                            "title",
                            "subtitle",
                            "authors",
                            "publisher",
                            "publication_place",
                            "publication_year",
                            "isbn",
                            "doi",
                            "language",
                            "document_type",
                        ],
                    },
                    "value": {},
                    "evidence": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["page_number", "bbox", "text_quote"],
                            "properties": {
                                "page_number": {"type": ["integer", "null"]},
                                "bbox": {"type": "array", "maxItems": 4, "items": {"type": "number"}},
                                "text_quote": {"type": "string"},
                            },
                        },
                    },
                    "reason": {"type": "string"},
                    "warnings": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
                },
            },
        }
    },
}


def _record_ai_source(
    upload_item,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    document_text: str,
    status: str,
    raw_response=None,
    error_code: str = "",
    error_message: str = "",
) -> SourceRecord | None:
    if upload_item is None:
        return None
    return SourceRecord.objects.create(
        upload_item=upload_item,
        provider=f"ai:{provider}"[:80],
        operation="metadata_candidates",
        query={
            "input_sha256": sha256(document_text.encode("utf-8")).hexdigest(),
            "input_chars": len(document_text),
            "prompt_version": prompt_version,
        },
        request_fingerprint=sha256(
            f"{provider}:{model}:{prompt_version}:{document_text}".encode("utf-8")
        ).hexdigest(),
        external_id=model[:255],
        raw_response=raw_response if isinstance(raw_response, (dict, list)) else {},
        provider_version=prompt_version,
        retrieved_at=timezone.now(),
        status=status,
        error_code=error_code[:80],
        error_message=error_message[:4000],
    )


def metadata_candidates_from_ai(
    document_text: str,
    *,
    upload_item=None,
) -> tuple[list[Candidate], dict]:
    """Return review-only candidates. The caller owns persistence and every decision."""

    try:
        client = AIClient()
    except AIServiceError as exc:
        _record_ai_source(
            upload_item,
            provider="configuration",
            model="",
            prompt_version="bibliographic-candidates-v1",
            document_text=document_text,
            status=SourceRecord.Status.FAILED,
            error_code=exc.code,
            error_message=str(exc),
        )
        return [], {"status": "unavailable", "error_code": exc.code, "error": str(exc)[:500]}
    if not client.config.enabled:
        return [], {"status": "disabled", "provider": "none"}
    try:
        result = client.generate_json(
            task="bibliographic-metadata-candidates",
            system_prompt=(
                "你是数字图书馆书目候选提取器。只提取摘录中有直接证据的值。"
                "出版地必须来自该版本的出版项，不得根据出版社当前总部推断。"
                "无法判断时省略候选。所有结果都必须等待管理员确认。"
            ),
            document_text=document_text,
            schema=AI_METADATA_SCHEMA,
            prompt_version="bibliographic-candidates-v1",
        )
    except AIServiceError as exc:
        _record_ai_source(
            upload_item,
            provider=client.config.provider,
            model=client.config.metadata_model,
            prompt_version="bibliographic-candidates-v1",
            document_text=document_text,
            status=SourceRecord.Status.FAILED,
            error_code=exc.code,
            error_message=str(exc),
        )
        return [], {"status": "unavailable", "error_code": exc.code, "error": str(exc)[:500]}

    source_record = _record_ai_source(
        upload_item,
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        document_text=document_text,
        status=SourceRecord.Status.SUCCEEDED,
        raw_response=result.data,
    )
    candidates: list[Candidate] = []
    for proposal in result.data.get("proposals", []):
        evidence_rows = proposal.get("evidence") or []
        first_evidence = evidence_rows[0] if evidence_rows else {}
        candidates.append(
            Candidate(
                field_name=proposal["field_name"],
                value=proposal.get("value"),
                source="ai_metadata_candidate",
                # This is only a neutral input to the calibrated scorer. The
                # model never supplies or controls the system confidence.
                confidence=0.5,
                evidence={
                    "page": first_evidence.get("page_number"),
                    "bbox": first_evidence.get("bbox") or [],
                    "text_quote": first_evidence.get("text_quote") or "",
                    "reason": proposal.get("reason") or "",
                    "warnings": proposal.get("warnings") or [],
                    "model_name": result.model,
                    "model_revision": result.prompt_version,
                    "extraction_method": "ai_json_candidate",
                    "source_record_id": str(source_record.id) if source_record else "",
                },
            )
        )
    return candidates, {
        "status": "succeeded",
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "latency_ms": result.latency_ms,
        "candidate_count": len(candidates),
    }
