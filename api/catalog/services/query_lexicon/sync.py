from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import hashlib
import json
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import (
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
)
from catalog.services.query_lexicon.mutations import (
    acquire_entity_lock,
    acquire_generation_lock,
)
from catalog.services.query_lexicon.normalization import NORMALIZATION_VERSION
from catalog.services.query_lexicon.registry import (
    SOURCE_REGISTRY_VERSION,
    SUPPORTED_SOURCE_REGISTRY_VERSIONS,
    EntityBuild,
    EntityKey,
    all_entity_keys,
    audit_person_merges,
    build_entity,
    validate_entity_filter,
)


SUPPORTED_NORMALIZATION_VERSIONS = {NORMALIZATION_VERSION}
ENTRY_LOGICAL_FIELDS = (
    "entity_type",
    "entity_id",
    "term",
    "normalized_term",
    "language",
    "term_type",
    "source_kind",
    "trust_level",
    "source_ref",
    "source_fingerprint",
    "provenance",
    "displayable",
    "public_active",
    "admin_resolvable",
)


class QueryLexiconInvariantError(RuntimeError):
    pass


def latest_event_seq() -> int:
    value = (
        QueryLexiconChangeEvent.objects.order_by("-event_seq")
        .values_list("event_seq", flat=True)
        .first()
    )
    return int(value or 0)


def ensure_query_lexicon_state() -> QueryLexiconState:
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if state is not None:
        return state
    with transaction.atomic():
        state = QueryLexiconState.objects.select_related("active_generation").filter(
            key="default"
        ).first()
        if state is not None:
            return state
        now = timezone.now()
        generation = QueryLexiconGeneration.objects.create(
            status=QueryLexiconGeneration.Status.ACTIVE,
            start_event_seq=latest_event_seq(),
            cutover_event_seq=latest_event_seq(),
            normalization_version=NORMALIZATION_VERSION,
            source_registry_version=SOURCE_REGISTRY_VERSION,
            effective_content_hash=_logical_hash([]),
            entry_count=0,
            built_at=now,
            activated_at=now,
        )
        return QueryLexiconState.objects.create(
            key="default",
            revision=0,
            active_generation=generation,
            normalization_version=NORMALIZATION_VERSION,
            source_registry_version=SOURCE_REGISTRY_VERSION,
            last_reconciled_content_hash=generation.effective_content_hash,
        )


def _validate_state(state: QueryLexiconState) -> None:
    generation = state.active_generation
    if generation.status != QueryLexiconGeneration.Status.ACTIVE:
        raise QueryLexiconInvariantError("QueryLexiconState 指向的 generation 不是 active。")
    if generation.normalization_version != state.normalization_version:
        raise QueryLexiconInvariantError("QueryLexicon normalization version 不一致。")
    if generation.source_registry_version != state.source_registry_version:
        raise QueryLexiconInvariantError("QueryLexicon Source Registry version 不一致。")
    if state.normalization_version not in SUPPORTED_NORMALIZATION_VERSIONS:
        raise QueryLexiconInvariantError("当前代码不支持活动 normalization version。")
    if state.source_registry_version not in SUPPORTED_SOURCE_REGISTRY_VERSIONS:
        raise QueryLexiconInvariantError("当前代码不支持活动 Source Registry version。")


def _logical_row(row) -> dict:
    result = {}
    for field in ENTRY_LOGICAL_FIELDS:
        value = row[field] if isinstance(row, dict) else getattr(row, field)
        result[field] = str(value) if field == "entity_id" else value
    return result


def _logical_rows(rows) -> list[dict]:
    return sorted(
        (_logical_row(row) for row in rows),
        key=lambda row: (
            row["entity_type"],
            row["entity_id"],
            row["normalized_term"],
            row["source_fingerprint"],
        ),
    )


def _logical_hash(
    rows,
    *,
    normalization_version: str = NORMALIZATION_VERSION,
    source_registry_version: str = SOURCE_REGISTRY_VERSION,
) -> str:
    payload = json.dumps(
        {
            "normalization_version": normalization_version,
            "source_registry_version": source_registry_version,
            "entries": _logical_rows(rows),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diff_counts(current_rows, expected_rows) -> dict[str, int]:
    def keyed(rows):
        return {
            (
                row["entity_type"],
                str(row["entity_id"]),
                row["normalized_term"],
            ): _logical_row(row)
            for row in rows
        }

    current = keyed(current_rows)
    expected = keyed(expected_rows)
    shared = set(current) & set(expected)
    return {
        "added": len(set(expected) - set(current)),
        "removed": len(set(current) - set(expected)),
        "changed": sum(current[key] != expected[key] for key in shared),
        "unchanged": sum(current[key] == expected[key] for key in shared),
    }


def _entry_objects(generation: QueryLexiconGeneration, rows: list[dict]):
    return [QueryLexiconEntry(generation=generation, **row) for row in rows]


def _sync_entity_locked(
    key: EntityKey,
    *,
    state: QueryLexiconState,
    generation: QueryLexiconGeneration,
) -> tuple[bool, int, dict[str, int]]:
    build = build_entity(key)
    current = list(
        QueryLexiconEntry.objects.filter(
            generation=generation,
            entity_type=key.entity_type,
            entity_id=key.entity_id,
        ).order_by("normalized_term")
    )
    if _logical_rows(current) == _logical_rows(build.entries):
        return False, state.revision, build.audit

    old_count = len(current)
    QueryLexiconEntry.objects.filter(
        generation=generation,
        entity_type=key.entity_type,
        entity_id=key.entity_id,
    ).delete()
    QueryLexiconEntry.objects.bulk_create(
        _entry_objects(generation, build.entries),
        batch_size=500,
    )
    generation.entry_count = max(0, generation.entry_count - old_count + len(build.entries))
    generation.save(update_fields=["entry_count", "updated_at"])
    state.revision += 1
    state.last_successful_sync_at = timezone.now()
    state.save(update_fields=["revision", "last_successful_sync_at", "updated_at"])
    return True, state.revision, build.audit


def sync_entity(
    key: EntityKey,
    *,
    event_seqs: list[int] | None = None,
    lease_token: uuid.UUID | None = None,
) -> dict:
    event_seqs = list(event_seqs or [])
    with transaction.atomic():
        acquire_generation_lock(shared=True)
        acquire_entity_lock(key.entity_type, key.entity_id)
        claimed_events = []
        if event_seqs:
            claimed_events = list(
                QueryLexiconChangeEvent.objects.select_for_update()
                .filter(
                    event_seq__in=event_seqs,
                    processed_at__isnull=True,
                    lease_token=lease_token,
                )
                .order_by("event_seq")
            )
            if len(claimed_events) != len(event_seqs):
                return {"changed": False, "stale_lease": True, "revision": None}

        state = QueryLexiconState.objects.select_for_update().select_related(
            "active_generation"
        ).get(key="default")
        _validate_state(state)
        generation = QueryLexiconGeneration.objects.select_for_update().get(
            pk=state.active_generation_id
        )
        changed, revision, audit = _sync_entity_locked(
            key,
            state=state,
            generation=generation,
        )
        if claimed_events:
            now = timezone.now()
            QueryLexiconChangeEvent.objects.filter(
                event_seq__in=event_seqs,
                lease_token=lease_token,
                processed_at__isnull=True,
            ).update(
                processed_at=now,
                applied_revision=revision,
                lease_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
                last_error_code="",
                last_error_message="",
            )
        return {
            "changed": changed,
            "stale_lease": False,
            "revision": revision,
            "audit": audit,
        }


def _claim_events(*, limit: int) -> tuple[uuid.UUID | None, list[QueryLexiconChangeEvent]]:
    now = timezone.now()
    eligible = QueryLexiconChangeEvent.objects.filter(
        processed_at__isnull=True,
        dead_lettered_at__isnull=True,
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).filter(
        Q(lease_token__isnull=True) | Q(lease_expires_at__lte=now)
    )
    with transaction.atomic():
        if connection.vendor == "postgresql":
            eligible = eligible.select_for_update(skip_locked=True)
        else:
            eligible = eligible.select_for_update()
        events = list(eligible.order_by("event_seq")[: max(1, limit)])
        if not events:
            return None, []
        token = uuid.uuid4()
        expires_at = now + timedelta(seconds=settings.QUERY_LEXICON_EVENT_LEASE_SECONDS)
        QueryLexiconChangeEvent.objects.filter(
            event_seq__in=[event.event_seq for event in events]
        ).update(lease_token=token, lease_expires_at=expires_at)
        for event in events:
            event.lease_token = token
            event.lease_expires_at = expires_at
        return token, events


def _release_failed_events(event_seqs: list[int], lease_token: uuid.UUID, exc: Exception) -> None:
    now = timezone.now()
    with transaction.atomic():
        events = list(
            QueryLexiconChangeEvent.objects.select_for_update().filter(
                event_seq__in=event_seqs,
                processed_at__isnull=True,
                lease_token=lease_token,
            )
        )
        for event in events:
            event.attempts += 1
            event.last_error_code = exc.__class__.__name__[:120]
            event.last_error_message = str(exc)[:4000]
            event.lease_token = None
            event.lease_expires_at = None
            if event.attempts >= settings.QUERY_LEXICON_EVENT_MAX_ATTEMPTS:
                event.dead_lettered_at = now
                event.next_attempt_at = None
            else:
                delay = min(
                    settings.QUERY_LEXICON_EVENT_RETRY_MAX_SECONDS,
                    settings.QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS
                    * (2 ** max(0, event.attempts - 1)),
                )
                event.next_attempt_at = now + timedelta(seconds=delay)
            event.save(
                update_fields=[
                    "attempts",
                    "last_error_code",
                    "last_error_message",
                    "lease_token",
                    "lease_expires_at",
                    "dead_lettered_at",
                    "next_attempt_at",
                ]
            )


def process_pending_events(*, limit: int | None = None) -> dict[str, int]:
    limit = limit or settings.QUERY_LEXICON_EVENT_BATCH_SIZE
    lease_token, events = _claim_events(limit=limit)
    if not events or lease_token is None:
        return {"claimed": 0, "entities": 0, "changed": 0, "failed": 0}

    grouped: dict[EntityKey, list[int]] = defaultdict(list)
    for event in events:
        grouped[EntityKey(event.entity_type, event.entity_id)].append(event.event_seq)
    changed = 0
    failed = 0
    for key in sorted(grouped):
        event_seqs = grouped[key]
        try:
            result = sync_entity(
                key,
                event_seqs=event_seqs,
                lease_token=lease_token,
            )
            changed += int(bool(result.get("changed")))
        except Exception as exc:
            failed += 1
            _release_failed_events(event_seqs, lease_token, exc)
    return {
        "claimed": len(events),
        "entities": len(grouped),
        "changed": changed,
        "failed": failed,
    }


def _collect_builds(keys: list[EntityKey]) -> tuple[list[EntityBuild], dict[str, int]]:
    builds = []
    audit = defaultdict(int)
    for name in (
        "entities",
        "entries",
        "ambiguous_terms",
        "legacy_mixed_alias",
        "generated_search_variant",
        "legacy_mixed_alias_sources",
        "generated_search_variant_sources",
        "suspected_seed_alias",
        "orphan_mapping",
        "unknown_legacy_model",
        "mapped_legacy_identity_suppressed",
        "merge_target_missing_or_invalid",
    ):
        audit[name] = 0
    for key in keys:
        build = build_entity(key)
        builds.append(build)
        audit["entities"] += 1
        audit["entries"] += len(build.entries)
        for name, count in build.audit.items():
            audit[name] += count
    normalized_entities: dict[str, set[tuple[str, str]]] = defaultdict(set)
    legacy_mixed_entries: set[tuple[str, str, str]] = set()
    generated_variant_entries: set[tuple[str, str, str]] = set()
    for build in builds:
        for entry in build.entries:
            normalized_entities[entry["normalized_term"]].add(
                (entry["entity_type"], str(entry["entity_id"]))
            )
            for source in entry.get("provenance", {}).get("sources", []):
                if (
                    source.get("source_kind")
                    == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
                ):
                    audit["legacy_mixed_alias_sources"] += 1
                    legacy_mixed_entries.add(
                        (
                            entry["entity_type"],
                            str(entry["entity_id"]),
                            entry["normalized_term"],
                        )
                    )
                elif (
                    source.get("source_kind")
                    == QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
                ):
                    audit["generated_search_variant_sources"] += 1
                    generated_variant_entries.add(
                        (
                            entry["entity_type"],
                            str(entry["entity_id"]),
                            entry["normalized_term"],
                        )
                    )
    audit["ambiguous_terms"] = sum(
        1 for entities in normalized_entities.values() if len(entities) > 1
    )
    audit["legacy_mixed_count"] = len(legacy_mixed_entries)
    audit["generated_variant_count"] = len(generated_variant_entries)
    audit["suspected_0013_seed_count"] = audit["suspected_seed_alias"]
    audit["mapping_anomaly_count"] = (
        audit["orphan_mapping"] + audit["unknown_legacy_model"]
    )
    return builds, dict(audit)


def _merge_audit_for_filter(
    *,
    entity_type: str | None,
    entity_id: str | None,
) -> dict:
    if entity_type not in {None, QueryLexiconEntry.EntityType.PERSON}:
        return {
            "merged_people_audited": 0,
            "valid_merges": 0,
            "chained_merges": 0,
            "historical_sources_resolvable": 0,
            "anomaly_count": 0,
            "anomaly_counts": {},
            "findings": [],
            "findings_truncated": False,
            "resolved_samples": [],
        }
    return audit_person_merges(entity_id=entity_id)


def _raise_for_merge_anomalies(merge_audit: dict) -> None:
    if not merge_audit["anomaly_count"]:
        return
    summary = ", ".join(
        f"{code}={count}"
        for code, count in merge_audit["anomaly_counts"].items()
    )
    raise QueryLexiconInvariantError(
        "人物合并审计发现致命异常，正式 rebuild 已停止。"
        f"请先运行 --dry-run 核对并修复 authority：{summary}"
    )


def _replace_generation_builds(
    generation: QueryLexiconGeneration,
    builds: list[EntityBuild],
) -> None:
    for build in builds:
        QueryLexiconEntry.objects.filter(
            generation=generation,
            entity_type=build.key.entity_type,
            entity_id=build.key.entity_id,
        ).delete()
        QueryLexiconEntry.objects.bulk_create(
            _entry_objects(generation, build.entries),
            batch_size=500,
        )


def _copy_active_generation(
    source: QueryLexiconGeneration,
    target: QueryLexiconGeneration,
) -> None:
    batch = []
    queryset = QueryLexiconEntry.objects.filter(generation=source).order_by("pk")
    for entry in queryset.iterator(chunk_size=1000):
        row = {field: getattr(entry, field) for field in ENTRY_LOGICAL_FIELDS}
        batch.append(QueryLexiconEntry(generation=target, **row))
        if len(batch) >= 1000:
            QueryLexiconEntry.objects.bulk_create(batch, batch_size=1000)
            batch = []
    if batch:
        QueryLexiconEntry.objects.bulk_create(batch, batch_size=1000)


def _generation_rows(generation: QueryLexiconGeneration) -> list[dict]:
    return list(
        QueryLexiconEntry.objects.filter(generation=generation).values(
            *ENTRY_LOGICAL_FIELDS
        )
    )


def dry_run_reconciliation(
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    normalization_version: str | None = None,
    source_registry_version: str | None = None,
) -> dict:
    state = QueryLexiconState.objects.select_related("active_generation").filter(
        key="default"
    ).first()
    if state is None:
        raise QueryLexiconInvariantError(
            "QueryLexiconState 不存在。dry-run 不会自动创建状态，请先应用 migration。"
        )
    _validate_state(state)
    _validate_rebuild_versions(
        state,
        entity_type=entity_type,
        entity_id=entity_id,
        normalization_version=normalization_version,
        source_registry_version=source_registry_version,
    )
    keys = all_entity_keys(entity_type=entity_type, entity_id=entity_id)
    builds, audit = _collect_builds(keys)
    merge_audit = _merge_audit_for_filter(
        entity_type=entity_type,
        entity_id=entity_id,
    )
    audit["merge_anomaly_count"] = merge_audit["anomaly_count"]
    audit["merge_chain_count"] = merge_audit["chained_merges"]
    expected_rows = [entry for build in builds for entry in build.entries]
    current = QueryLexiconEntry.objects.filter(generation=state.active_generation)
    if entity_type:
        current = current.filter(entity_type=entity_type)
    if entity_id:
        current = current.filter(entity_id=entity_id)
    current_rows = list(current.values(*ENTRY_LOGICAL_FIELDS))
    diff = _diff_counts(current_rows, expected_rows)
    return {
        "dry_run": True,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "normalization_version": normalization_version or state.normalization_version,
        "source_registry_version": source_registry_version or state.source_registry_version,
        "current_entries": len(current_rows),
        "expected_entries": len(expected_rows),
        "content_changed": _logical_rows(current_rows) != _logical_rows(expected_rows),
        "expected_content_hash": _logical_hash(
            expected_rows,
            normalization_version=normalization_version or state.normalization_version,
            source_registry_version=source_registry_version or state.source_registry_version,
        ),
        "diff": diff,
        "audit": audit,
        "merge_audit": merge_audit,
    }


def _validate_rebuild_versions(
    state: QueryLexiconState,
    *,
    entity_type: str | None,
    entity_id: str | None,
    normalization_version: str | None,
    source_registry_version: str | None,
) -> tuple[str, str]:
    if bool(normalization_version) != bool(source_registry_version):
        raise ValueError("两个版本参数必须同时提供。")
    if (normalization_version or source_registry_version) and (entity_type or entity_id):
        raise ValueError("规则版本参数不能与 entity filter 混用。")
    target_normalization = normalization_version or state.normalization_version
    target_registry = source_registry_version or state.source_registry_version
    if target_normalization not in SUPPORTED_NORMALIZATION_VERSIONS:
        raise ValueError(f"当前代码不支持 normalization version：{target_normalization}")
    if target_registry not in SUPPORTED_SOURCE_REGISTRY_VERSIONS:
        raise ValueError(f"当前代码不支持 Source Registry version：{target_registry}")
    return target_normalization, target_registry


def rebuild_query_lexicon(
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    normalization_version: str | None = None,
    source_registry_version: str | None = None,
) -> dict:
    validate_entity_filter(entity_type=entity_type, entity_id=entity_id)
    merge_audit = _merge_audit_for_filter(
        entity_type=entity_type,
        entity_id=entity_id,
    )
    _raise_for_merge_anomalies(merge_audit)
    ensure_query_lexicon_state()
    # PostgreSQL sequences reflect allocation order, not transaction commit
    # order. A short exclusive barrier drains existing authority writers and
    # workers before the starting watermark is read. The expensive build runs
    # after this transaction releases the barrier.
    with transaction.atomic():
        acquire_generation_lock(shared=False)
        base_state = QueryLexiconState.objects.select_for_update().select_related(
            "active_generation"
        ).get(key="default")
        _validate_state(base_state)
        target_normalization, target_registry = _validate_rebuild_versions(
            base_state,
            entity_type=entity_type,
            entity_id=entity_id,
            normalization_version=normalization_version,
            source_registry_version=source_registry_version,
        )
        start_seq = latest_event_seq()
        start_revision = base_state.revision
        base_generation_id = base_state.active_generation_id
    # Entity enumeration follows the watermark. Creates or deletes that race
    # with this snapshot therefore have event_seq > start_seq and are replayed.
    keys = all_entity_keys(entity_type=entity_type, entity_id=entity_id)
    generation = QueryLexiconGeneration.objects.create(
        status=QueryLexiconGeneration.Status.STAGING,
        start_event_seq=start_seq,
        normalization_version=target_normalization,
        source_registry_version=target_registry,
        build_stats={
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "base_generation_id": str(base_generation_id),
            "base_revision": start_revision,
            "merge_audit": merge_audit,
        },
    )
    try:
        if entity_type or entity_id:
            _copy_active_generation(base_state.active_generation, generation)
        builds, audit = _collect_builds(keys)
        if entity_type and not entity_id:
            QueryLexiconEntry.objects.filter(
                generation=generation,
                entity_type=entity_type,
            ).delete()
        _replace_generation_builds(generation, builds)
        generation.entry_count = generation.entries.count()
        generation.build_stats = {**generation.build_stats, "audit": audit}
        generation.save(update_fields=["entry_count", "build_stats", "updated_at"])

        with transaction.atomic():
            acquire_generation_lock(shared=False)
            state = QueryLexiconState.objects.select_for_update().select_related(
                "active_generation"
            ).get(key="default")
            _validate_state(state)
            if (
                state.normalization_version != base_state.normalization_version
                or state.source_registry_version != base_state.source_registry_version
            ):
                raise QueryLexiconInvariantError(
                    "重建期间活动规则版本已变化，请使用当前版本重新运行。"
                )
            if (entity_type or entity_id) and (
                state.active_generation_id != base_generation_id
                or state.revision != start_revision
            ):
                raise QueryLexiconInvariantError(
                    "定向重建期间 active generation 已变化，请重新运行。"
                )
            cutover_seq = latest_event_seq()
            replay_filter = Q(event_seq__gt=start_seq) | Q(processed_at__isnull=True)
            replay_keys = sorted(
                {
                    EntityKey(row[0], row[1])
                    for row in QueryLexiconChangeEvent.objects.filter(
                        replay_filter,
                        event_seq__lte=cutover_seq,
                    ).values_list("entity_type", "entity_id")
                }
            )
            if replay_keys:
                replay_builds, replay_audit = _collect_builds(replay_keys)
                _replace_generation_builds(generation, replay_builds)
                for name, count in replay_audit.items():
                    audit[f"replay_{name}"] = count

            staging_rows = _generation_rows(generation)
            active_rows = _generation_rows(state.active_generation)
            staging_hash = _logical_hash(
                staging_rows,
                normalization_version=target_normalization,
                source_registry_version=target_registry,
            )
            active_hash = _logical_hash(
                active_rows,
                normalization_version=state.normalization_version,
                source_registry_version=state.source_registry_version,
            )
            now = timezone.now()
            generation.entry_count = len(staging_rows)
            generation.cutover_event_seq = cutover_seq
            generation.effective_content_hash = staging_hash
            generation.built_at = now
            generation.build_stats = {**generation.build_stats, "audit": audit}
            if staging_hash == active_hash:
                generation.status = QueryLexiconGeneration.Status.DISCARDED
                generation.save(
                    update_fields=[
                        "status",
                        "cutover_event_seq",
                        "effective_content_hash",
                        "entry_count",
                        "build_stats",
                        "built_at",
                        "updated_at",
                    ]
                )
                state.last_reconciled_at = now
                state.last_reconciled_content_hash = staging_hash
                state.last_reconciled_revision = state.revision
                state.save(
                    update_fields=[
                        "last_reconciled_at",
                        "last_reconciled_content_hash",
                        "last_reconciled_revision",
                        "updated_at",
                    ]
                )
                QueryLexiconChangeEvent.objects.filter(
                    event_seq__lte=cutover_seq,
                    processed_at__isnull=True,
                ).update(
                    processed_at=now,
                    applied_revision=state.revision,
                    lease_token=None,
                    lease_expires_at=None,
                    next_attempt_at=None,
                )
                return {
                    "changed": False,
                    "revision": state.revision,
                    "generation": str(generation.pk),
                    "content_hash": staging_hash,
                    "audit": audit,
                    "merge_audit": merge_audit,
                }

            old_generation = QueryLexiconGeneration.objects.select_for_update().get(
                pk=state.active_generation_id
            )
            old_generation.status = QueryLexiconGeneration.Status.RETIRED
            old_generation.retired_at = now
            old_generation.save(
                update_fields=["status", "retired_at", "updated_at"]
            )
            generation.status = QueryLexiconGeneration.Status.ACTIVE
            generation.activated_at = now
            generation.save(
                update_fields=[
                    "status",
                    "cutover_event_seq",
                    "effective_content_hash",
                    "entry_count",
                    "build_stats",
                    "built_at",
                    "activated_at",
                    "updated_at",
                ]
            )
            state.revision += 1
            state.active_generation = generation
            state.normalization_version = target_normalization
            state.source_registry_version = target_registry
            state.last_reconciled_at = now
            state.last_reconciled_content_hash = staging_hash
            state.last_reconciled_revision = state.revision
            state.save(
                update_fields=[
                    "revision",
                    "active_generation",
                    "normalization_version",
                    "source_registry_version",
                    "last_reconciled_at",
                    "last_reconciled_content_hash",
                    "last_reconciled_revision",
                    "updated_at",
                ]
            )
            QueryLexiconChangeEvent.objects.filter(
                event_seq__lte=cutover_seq,
                processed_at__isnull=True,
            ).update(
                processed_at=now,
                applied_revision=state.revision,
                lease_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
            )
            return {
                "changed": True,
                "revision": state.revision,
                "generation": str(generation.pk),
                "retired_generation": str(old_generation.pk),
                "content_hash": staging_hash,
                "audit": audit,
                "merge_audit": merge_audit,
            }
    except Exception as exc:
        QueryLexiconGeneration.objects.filter(
            pk=generation.pk,
            status=QueryLexiconGeneration.Status.STAGING,
        ).update(
            status=QueryLexiconGeneration.Status.FAILED,
            error_message=str(exc)[:4000],
            built_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise
