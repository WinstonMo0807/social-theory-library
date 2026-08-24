from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from django.db import transaction

from catalog.models import EvidencePack


REQUIRED_ENVELOPE_KEYS = frozenset({"kind", "source", "text", "locator", "quality", "provenance"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_envelopes(envelopes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in envelopes:
        envelope = dict(raw or {})
        missing = REQUIRED_ENVELOPE_KEYS - envelope.keys()
        if missing:
            raise ValueError(f"EvidenceEnvelope 缺少字段：{', '.join(sorted(missing))}")
        locator = dict(envelope.get("locator") or {})
        if envelope.get("kind") == "collection_text" and not locator.get("page"):
            raise ValueError("馆藏 EvidenceEnvelope 必须包含页码定位。")
        output.append(envelope)
    return output


@transaction.atomic
def create_evidence_pack(
    *,
    task_profile: dict[str, Any],
    envelopes: Iterable[dict[str, Any]],
    retrieval_snapshot: dict[str, Any],
    subject_type: str = "",
    subject_id: str = "",
    research_run=None,
    query_lexicon_revision: str = "",
    semantic_index_uid: str = "",
    actor=None,
) -> EvidencePack:
    normalized = _normalize_envelopes(envelopes)
    minimum = dict(task_profile.get("minimum_evidence_policy") or {})
    minimum_count = int(minimum.get("evidence_count") or minimum.get("collection_evidence_count") or 0)
    if len(normalized) < minimum_count:
        raise ValueError(f"证据不足：当前 {len(normalized)} 条，至少需要 {minimum_count} 条。")
    revision_ids = sorted(
        {
            str((row.get("source") or {}).get("document_revision_id"))
            for row in normalized
            if (row.get("source") or {}).get("document_revision_id")
        }
    )
    immutable_payload = {
        "task_profile_key": task_profile["key"],
        "task_profile_version": int(task_profile.get("version") or 1),
        "retrieval_profile": task_profile["retrieval_profile"],
        "subject_type": subject_type,
        "subject_id": str(subject_id or ""),
        "envelopes": normalized,
        "retrieval": dict(retrieval_snapshot or {}),
        "query_lexicon_revision": query_lexicon_revision,
        "semantic_index_uid": semantic_index_uid,
        "document_revisions": revision_ids,
    }
    fingerprint = hashlib.sha256(_canonical_json(immutable_payload).encode("utf-8")).hexdigest()
    pack, _ = EvidencePack.objects.get_or_create(
        fingerprint=fingerprint,
        defaults={
            "research_run": research_run,
            "task_profile_key": immutable_payload["task_profile_key"],
            "task_profile_version": immutable_payload["task_profile_version"],
            "retrieval_profile": immutable_payload["retrieval_profile"],
            "subject_type": subject_type,
            "subject_id": str(subject_id or ""),
            "envelope_snapshot": normalized,
            "retrieval_snapshot": dict(retrieval_snapshot or {}),
            "query_lexicon_revision": query_lexicon_revision,
            "semantic_index_uid": semantic_index_uid,
            "document_revisions": revision_ids,
            "created_by": actor,
        },
    )
    return pack

