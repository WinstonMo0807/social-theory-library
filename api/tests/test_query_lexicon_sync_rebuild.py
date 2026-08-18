from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import (
    KnowledgeNode,
    KnowledgeNodeAlias,
    Person,
    PersonNameVariant,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
)
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.resolver import PUBLIC_ACTIVE, resolve_term
from catalog.services.query_lexicon import sync as sync_service


pytestmark = pytest.mark.django_db


def _person(name: str) -> Person:
    return Person.objects.create(
        preferred_name=name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def _node(name: str) -> KnowledgeNode:
    return KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh=name,
        slug=f"sync-{uuid4().hex}",
        status="published",
    )


def _state() -> QueryLexiconState:
    return QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )


def test_full_rebuild_switches_atomically_and_second_build_is_noop():
    person = _person("重建人物")
    before = _state()
    old_generation_id = before.active_generation_id

    first = sync_service.rebuild_query_lexicon()

    after_first = _state()
    assert first["changed"] is True
    assert after_first.active_generation_id != old_generation_id
    assert after_first.revision == before.revision + 1
    assert (
        QueryLexiconGeneration.objects.get(pk=old_generation_id).status
        == QueryLexiconGeneration.Status.RETIRED
    )
    assert after_first.active_generation.status == QueryLexiconGeneration.Status.ACTIVE
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]

    active_generation_id = after_first.active_generation_id
    active_revision = after_first.revision
    second = sync_service.rebuild_query_lexicon()

    after_second = _state()
    discarded = QueryLexiconGeneration.objects.get(pk=second["generation"])
    assert second["changed"] is False
    assert after_second.active_generation_id == active_generation_id
    assert after_second.revision == active_revision
    assert after_second.last_reconciled_at is not None
    assert after_second.last_reconciled_revision == active_revision
    assert after_second.last_reconciled_content_hash == second["content_hash"]
    assert discarded.status == QueryLexiconGeneration.Status.DISCARDED


def test_failed_staging_build_preserves_old_active_generation(monkeypatch):
    person = _person("失败保护人物")
    sync_service.rebuild_query_lexicon()
    before = _state()

    def fail_collection(_keys):
        raise RuntimeError("forced staging failure")

    monkeypatch.setattr(sync_service, "_collect_builds", fail_collection)
    with pytest.raises(RuntimeError, match="forced staging failure"):
        sync_service.rebuild_query_lexicon()

    after = _state()
    failed = QueryLexiconGeneration.objects.filter(
        status=QueryLexiconGeneration.Status.FAILED
    ).latest("created_at")
    assert after.active_generation_id == before.active_generation_id
    assert after.revision == before.revision
    assert after.active_generation.status == QueryLexiconGeneration.Status.ACTIVE
    assert failed.error_message == "forced staging failure"
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]


def test_cutover_write_failure_rolls_back_generation_and_state(monkeypatch):
    person = _person("切换回滚人物")
    sync_service.rebuild_query_lexicon()
    before = _state()
    old_generation_id = before.active_generation_id
    old_revision = before.revision
    person.preferred_name = "切换回滚人物新名"
    person.save()

    def fail_state_save(_self, *args, **kwargs):
        raise RuntimeError("forced state cutover failure")

    monkeypatch.setattr(QueryLexiconState, "save", fail_state_save)
    with pytest.raises(RuntimeError, match="forced state cutover failure"):
        sync_service.rebuild_query_lexicon()

    after = _state()
    failed = QueryLexiconGeneration.objects.filter(
        status=QueryLexiconGeneration.Status.FAILED
    ).latest("created_at")
    assert after.active_generation_id == old_generation_id
    assert after.revision == old_revision
    assert (
        QueryLexiconGeneration.objects.get(pk=old_generation_id).status
        == QueryLexiconGeneration.Status.ACTIVE
    )
    assert failed.status == QueryLexiconGeneration.Status.FAILED


def test_staging_generation_is_not_visible_to_resolver():
    active_person = _person("共享解析名")
    sync_service.rebuild_query_lexicon()
    state = _state()
    staging_person = _person("共享解析名")
    staging = QueryLexiconGeneration.objects.create(
        status=QueryLexiconGeneration.Status.STAGING,
        normalization_version=state.normalization_version,
        source_registry_version=state.source_registry_version,
    )
    build = sync_service.build_entity(
        sync_service.EntityKey(QueryLexiconEntry.EntityType.PERSON, staging_person.pk)
    )
    row = next(
        item
        for item in build.entries
        if item["normalized_term"] == normalize_term("共享解析名")
    )
    QueryLexiconEntry.objects.create(generation=staging, **row)

    result = resolve_term("共享解析名", scope=PUBLIC_ACTIVE)

    assert {
        match["entity"]["entity_id"] for match in result["matches"]
    } == {str(active_person.pk)}
    assert result["revision"] == state.revision


def test_duplicate_events_are_coalesced_and_revision_changes_once():
    person = _person("重复事件人物")
    original = QueryLexiconChangeEvent.objects.get(
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
    )
    QueryLexiconChangeEvent.objects.create(
        entity_type=original.entity_type,
        entity_id=original.entity_id,
        action=QueryLexiconChangeEvent.Action.UPDATE,
        source_model=original.source_model,
        source_object_id=original.source_object_id,
        correlation_id=uuid4(),
    )
    revision_before = _state().revision

    result = sync_service.process_pending_events()

    events = list(
        QueryLexiconChangeEvent.objects.filter(
            entity_type=QueryLexiconEntry.EntityType.PERSON,
            entity_id=person.pk,
        ).order_by("event_seq")
    )
    assert result == {"claimed": 2, "entities": 1, "changed": 1, "failed": 0}
    assert _state().revision == revision_before + 1
    assert all(event.processed_at is not None for event in events)
    assert {event.applied_revision for event in events} == {revision_before + 1}
    assert sync_service.process_pending_events()["claimed"] == 0


def test_failed_event_is_retried_and_expired_lease_is_recoverable(monkeypatch):
    person = _person("可恢复事件人物")
    event = QueryLexiconChangeEvent.objects.get(
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
    )
    original_sync_entity = sync_service.sync_entity
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient worker failure")
        return original_sync_entity(*args, **kwargs)

    monkeypatch.setattr(sync_service, "sync_entity", fail_once)
    first = sync_service.process_pending_events()
    event.refresh_from_db()
    assert first["failed"] == 1
    assert event.attempts == 1
    assert event.processed_at is None
    assert event.lease_token is None
    assert event.next_attempt_at is not None

    event.next_attempt_at = timezone.now() - timedelta(seconds=1)
    event.lease_token = uuid4()
    event.lease_expires_at = timezone.now() - timedelta(seconds=1)
    event.save(
        update_fields=["next_attempt_at", "lease_token", "lease_expires_at"]
    )
    second = sync_service.process_pending_events()
    event.refresh_from_db()
    assert second["changed"] == 1
    assert second["failed"] == 0
    assert event.processed_at is not None
    assert event.lease_token is None
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]


def test_incremental_noop_event_does_not_increase_revision():
    person = _person("无变化事件人物")
    first = sync_service.process_pending_events()
    assert first["changed"] == 1
    revision = _state().revision

    person.biography = "只修改不进入词表的简介"
    person.save(update_fields=["biography", "aliases", "updated_at"])
    second = sync_service.process_pending_events()

    assert second["claimed"] == 1
    assert second["changed"] == 0
    assert second["failed"] == 0
    assert _state().revision == revision


def test_incremental_entity_update_and_delete_advance_revision_monotonically():
    person = _person("增量旧名称")
    sync_service.process_pending_events()
    created_revision = _state().revision

    person.preferred_name = "增量新名称"
    person.save(update_fields=["preferred_name"])
    updated = sync_service.process_pending_events()
    updated_revision = _state().revision

    assert updated["changed"] == 1
    assert updated_revision == created_revision + 1
    assert resolve_term("增量新名称", scope=PUBLIC_ACTIVE)["matches"]

    person.delete()
    deleted = sync_service.process_pending_events()
    deleted_revision = _state().revision

    assert deleted["changed"] == 1
    assert deleted_revision == updated_revision + 1
    assert resolve_term("增量新名称", scope=PUBLIC_ACTIVE)["matches"] == []


def test_incremental_alias_add_update_and_delete(admin_user):
    node = _node("增量别名节点")
    sync_service.process_pending_events()
    revision = _state().revision

    alias = KnowledgeNodeAlias.objects.create(
        node=node,
        alias="Incremental Alias",
        language="en",
        alias_type=KnowledgeNodeAlias.AliasType.TRANSLATION,
        created_by=admin_user,
    )
    added = sync_service.process_pending_events()
    assert added["changed"] == 1
    assert _state().revision == revision + 1
    assert resolve_term("incremental alias", scope=PUBLIC_ACTIVE)["matches"]

    alias.alias = "Updated Incremental Alias"
    alias.save(update_fields=["alias"])
    changed = sync_service.process_pending_events()
    assert changed["changed"] == 1
    assert _state().revision == revision + 2
    assert resolve_term("updated incremental alias", scope=PUBLIC_ACTIVE)["matches"]

    alias.delete()
    removed = sync_service.process_pending_events()
    assert removed["changed"] == 1
    assert _state().revision == revision + 3
    assert resolve_term("updated incremental alias", scope=PUBLIC_ACTIVE)["matches"] == []


def test_dry_run_is_read_only_even_when_pending_events_exist():
    _person("只读核对人物")
    before = _state()
    generation_count = QueryLexiconGeneration.objects.count()
    entry_count = QueryLexiconEntry.objects.count()
    pending = set(
        QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).values_list(
            "event_seq", flat=True
        )
    )

    result = sync_service.dry_run_reconciliation()

    after = _state()
    assert result["dry_run"] is True
    assert QueryLexiconGeneration.objects.count() == generation_count
    assert QueryLexiconEntry.objects.count() == entry_count
    assert after.active_generation_id == before.active_generation_id
    assert after.revision == before.revision
    assert set(
        QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).values_list(
            "event_seq", flat=True
        )
    ) == pending


def test_targeted_entity_rebuild_only_replaces_requested_entity():
    target = _person("定向重建目标")
    untouched = _person("定向重建旁观者")
    sync_service.rebuild_query_lexicon()
    before_state = _state()
    untouched_before = list(
        QueryLexiconEntry.objects.filter(
            generation=before_state.active_generation,
            entity_type=QueryLexiconEntry.EntityType.PERSON,
            entity_id=untouched.pk,
        )
        .order_by("normalized_term")
        .values(*sync_service.ENTRY_LOGICAL_FIELDS)
    )
    variant = PersonNameVariant.objects.create(
        person=target,
        name="Targeted Rebuild Name",
        language="en",
        variant_type=PersonNameVariant.VariantType.TRANSLATION,
        source_kind=PersonNameVariant.SourceKind.EDITORIAL,
        displayable=True,
        is_verified=True,
    )

    result = sync_service.rebuild_query_lexicon(
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=str(target.pk),
    )

    after_state = _state()
    untouched_after = list(
        QueryLexiconEntry.objects.filter(
            generation=after_state.active_generation,
            entity_type=QueryLexiconEntry.EntityType.PERSON,
            entity_id=untouched.pk,
        )
        .order_by("normalized_term")
        .values(*sync_service.ENTRY_LOGICAL_FIELDS)
    )
    assert result["changed"] is True
    assert after_state.active_generation_id != before_state.active_generation_id
    assert untouched_after == untouched_before
    assert resolve_term(variant.name, scope=PUBLIC_ACTIVE)["matches"]


def test_entity_type_rebuild_removes_stale_rows_without_an_event():
    person = _person("类型重建人物")
    sync_service.rebuild_query_lexicon()
    state = _state()
    stale_entity_id = uuid4()
    QueryLexiconEntry.objects.create(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=stale_entity_id,
        term="已删除人物残留词条",
        normalized_term=normalize_term("已删除人物残留词条"),
        language="zh-Hans",
        term_type=QueryLexiconEntry.TermType.CANONICAL,
        source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
        trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        source_ref="catalog.Person.preferred_name",
        source_fingerprint="f" * 64,
        provenance={},
        displayable=True,
        public_active=True,
        admin_resolvable=True,
    )
    state.active_generation.entry_count = state.active_generation.entries.count()
    state.active_generation.save(update_fields=["entry_count", "updated_at"])

    dry_run = sync_service.dry_run_reconciliation(
        entity_type=QueryLexiconEntry.EntityType.PERSON
    )
    assert dry_run["diff"]["removed"] >= 1

    rebuilt = sync_service.rebuild_query_lexicon(
        entity_type=QueryLexiconEntry.EntityType.PERSON
    )
    active = _state().active_generation
    assert rebuilt["changed"] is True
    assert not QueryLexiconEntry.objects.filter(
        generation=active,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=stale_entity_id,
    ).exists()
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]


def test_resolver_keeps_ambiguity_true_when_results_are_truncated():
    first = _person("截断歧义名")
    second = _person("截断歧义名")
    sync_service.rebuild_query_lexicon()

    result = resolve_term("截断歧义名", scope=PUBLIC_ACTIVE, max_results=1)

    assert result["truncated"] is True
    assert result["ambiguous"] is True
    assert len(result["matches"]) == 1
    assert result["matches"][0]["entity"]["entity_id"] in {
        str(first.pk),
        str(second.pk),
    }


def test_invalid_rebuild_filter_fails_before_creating_staging_metadata():
    generation_count = QueryLexiconGeneration.objects.count()

    with pytest.raises(ValueError, match="未知 QueryLexicon entity type"):
        sync_service.rebuild_query_lexicon(entity_type="not_registered")

    assert QueryLexiconGeneration.objects.count() == generation_count


def test_older_full_rebuild_cannot_replace_a_newer_rule_version(monkeypatch):
    _person("并发版本人物")
    state = _state()
    old_normalization = state.normalization_version
    old_registry = state.source_registry_version
    new_normalization = "query-lexicon-normalize-test-v2"
    new_registry = "query-lexicon-registry-test-v2"
    monkeypatch.setattr(
        sync_service,
        "SUPPORTED_NORMALIZATION_VERSIONS",
        {old_normalization, new_normalization},
    )
    monkeypatch.setattr(
        sync_service,
        "SUPPORTED_SOURCE_REGISTRY_VERSIONS",
        {old_registry, new_registry},
    )
    collect_builds = sync_service._collect_builds
    newer_build_completed = False

    def interleave_newer_version(keys):
        nonlocal newer_build_completed
        result = collect_builds(keys)
        if not newer_build_completed:
            newer_build_completed = True
            sync_service.rebuild_query_lexicon(
                normalization_version=new_normalization,
                source_registry_version=new_registry,
            )
            current = _state()
            assert current.normalization_version == new_normalization
            assert current.source_registry_version == new_registry
        return result

    monkeypatch.setattr(sync_service, "_collect_builds", interleave_newer_version)

    with pytest.raises(sync_service.QueryLexiconInvariantError):
        sync_service.rebuild_query_lexicon()

    after = _state()
    assert after.normalization_version == new_normalization
    assert after.source_registry_version == new_registry


def test_full_rebuild_replays_entity_created_during_initial_key_scan(monkeypatch):
    _person("扫描前人物")
    all_entity_keys = sync_service.all_entity_keys
    created_during_scan = None

    def create_after_key_snapshot(*args, **kwargs):
        nonlocal created_during_scan
        keys = all_entity_keys(*args, **kwargs)
        if created_during_scan is None:
            created_during_scan = _person("扫描期间新增人物")
            processed = sync_service.process_pending_events()
            assert processed["failed"] == 0
            assert resolve_term(
                created_during_scan.preferred_name,
                scope=PUBLIC_ACTIVE,
            )["matches"]
        return keys

    monkeypatch.setattr(sync_service, "all_entity_keys", create_after_key_snapshot)

    sync_service.rebuild_query_lexicon()

    assert created_during_scan is not None
    assert resolve_term(
        created_during_scan.preferred_name,
        scope=PUBLIC_ACTIVE,
    )["matches"]
