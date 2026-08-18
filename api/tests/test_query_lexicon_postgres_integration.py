from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import timedelta
import json
import os
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep
import tracemalloc
from uuid import uuid4

import pytest
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.utils import timezone

from catalog.models import (
    KnowledgeNode,
    KnowledgeNodeAlias,
    LegacyKnowledgeMapping,
    Person,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    TheorySchool,
)
from catalog.services.query_lexicon import mutations
from catalog.services.query_lexicon import sync as sync_service
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.registry import EntityKey
from catalog.services.query_lexicon.resolver import PUBLIC_ACTIVE, resolve_term


pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.django_db(transaction=True),
]


def _thread_connection(callable_):
    close_old_connections()
    try:
        return callable_()
    finally:
        connections.close_all()


def _person(name: str) -> Person:
    return Person.objects.create(
        preferred_name=name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def _key(person: Person) -> EntityKey:
    return EntityKey(QueryLexiconEntry.EntityType.PERSON, person.pk)


@pytest.fixture(autouse=True)
def require_postgres_and_disable_broker_wakeup(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")
    sync_service.ensure_query_lexicon_state()
    monkeypatch.setattr(
        mutations,
        "dispatch_query_lexicon_wakeup",
        lambda _event_seqs: False,
    )


def test_postgres_shared_generation_lock_allows_concurrent_authority_mutations():
    both_inside = Barrier(2, timeout=5)

    def writer(name):
        def run():
            with transaction.atomic():
                person = _person(name)
                both_inside.wait()
                return person.pk

        return _thread_connection(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(writer, "并发人物甲"),
            executor.submit(writer, "并发人物乙"),
        ]
        ids = [future.result(timeout=10) for future in futures]

    assert Person.objects.filter(pk__in=ids).count() == 2
    assert QueryLexiconChangeEvent.objects.filter(entity_id__in=ids).count() == 2


def test_postgres_exclusive_generation_barrier_waits_for_shared_writer():
    shared_acquired = Event()
    release_shared = Event()
    exclusive_acquired = Event()

    def shared_writer():
        def run():
            with transaction.atomic():
                mutations.acquire_generation_lock(shared=True)
                shared_acquired.set()
                assert release_shared.wait(5)

        return _thread_connection(run)

    def exclusive_rebuild_barrier():
        def run():
            with transaction.atomic():
                mutations.acquire_generation_lock(shared=False)
                exclusive_acquired.set()

        return _thread_connection(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(shared_writer)
        assert shared_acquired.wait(5)
        rebuild = executor.submit(exclusive_rebuild_barrier)
        assert not exclusive_acquired.wait(0.3)
        release_shared.set()
        writer.result(timeout=5)
        rebuild.result(timeout=5)

    assert exclusive_acquired.is_set()


def test_postgres_rebuild_cutover_replays_event_and_keeps_staging_invisible(
    monkeypatch,
):
    baseline = _person("活动人物")
    sync_service.rebuild_query_lexicon()
    before = QueryLexiconState.objects.get(key="default")
    old_generation_id = before.active_generation_id
    QueryLexiconChangeEvent.objects.all().delete()

    staging_ready = Event()
    release_build = Event()
    original_replace = sync_service._replace_generation_builds
    replacement_calls = 0

    def pause_first_staging_write(generation, builds):
        nonlocal replacement_calls
        original_replace(generation, builds)
        replacement_calls += 1
        if replacement_calls == 1:
            staging_ready.set()
            assert release_build.wait(10)

    monkeypatch.setattr(
        sync_service,
        "_replace_generation_builds",
        pause_first_staging_write,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _thread_connection,
            sync_service.rebuild_query_lexicon,
        )
        assert staging_ready.wait(10)
        staging = QueryLexiconGeneration.objects.get(
            status=QueryLexiconGeneration.Status.STAGING
        )
        assert resolve_term(baseline.preferred_name, scope=PUBLIC_ACTIVE)["matches"]

        raced = _person("watermark 后提交人物")
        assert not resolve_term(raced.preferred_name, scope=PUBLIC_ACTIVE)["matches"]
        assert QueryLexiconState.objects.get(key="default").active_generation_id == old_generation_id

        release_build.set()
        result = future.result(timeout=20)

    after = QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )
    old_generation = QueryLexiconGeneration.objects.get(pk=old_generation_id)
    staging.refresh_from_db()
    assert result["changed"] is True
    assert after.active_generation_id == staging.pk
    assert staging.status == QueryLexiconGeneration.Status.ACTIVE
    assert old_generation.status == QueryLexiconGeneration.Status.RETIRED
    assert after.revision == before.revision + 1
    assert resolve_term(raced.preferred_name, scope=PUBLIC_ACTIVE)["matches"]
    assert not QueryLexiconEntry.objects.filter(
        generation_id=old_generation_id,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=raced.pk,
    ).exists()
    rows = sync_service._generation_rows(after.active_generation)
    assert after.active_generation.effective_content_hash == sync_service._logical_hash(rows)
    assert after.active_generation.entry_count == len(rows)
    assert QueryLexiconGeneration.objects.filter(
        status=QueryLexiconGeneration.Status.ACTIVE
    ).count() == 1


def test_postgres_revision_updates_are_serialized_across_entities():
    first = _person("revision 并发甲")
    second = _person("revision 并发乙")
    QueryLexiconChangeEvent.objects.all().delete()
    start = Barrier(2, timeout=5)

    def sync(person):
        def run():
            start.wait()
            return sync_service.sync_entity(_key(person))

        return _thread_connection(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(sync, [first, second]))

    state = QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )
    assert sorted(result["revision"] for result in results) == [1, 2]
    assert state.revision == 2
    assert state.active_generation.entry_count == state.active_generation.entries.count()
    assert {
        str(value)
        for value in state.active_generation.entries.filter(
            entity_type=QueryLexiconEntry.EntityType.PERSON
        ).values_list("entity_id", flat=True)
    } == {str(first.pk), str(second.pk)}


def test_postgres_skip_locked_claim_does_not_wait_for_another_consumer():
    people = [_person(f"claim 人物 {index}") for index in range(3)]
    events = list(QueryLexiconChangeEvent.objects.order_by("event_seq"))
    locked_seq = events[0].event_seq
    row_locked = Event()
    release_row = Event()

    def locker():
        def run():
            with transaction.atomic():
                QueryLexiconChangeEvent.objects.select_for_update().get(
                    event_seq=locked_seq
                )
                row_locked.set()
                assert release_row.wait(5)

        return _thread_connection(run)

    def claimant():
        return _thread_connection(lambda: sync_service._claim_events(limit=10))

    with ThreadPoolExecutor(max_workers=2) as executor:
        locked = executor.submit(locker)
        assert row_locked.wait(5)
        claimed = executor.submit(claimant)
        try:
            token, claimed_events = claimed.result(timeout=2)
        except FutureTimeout:
            release_row.set()
            raise AssertionError("SKIP LOCKED claimant blocked on another worker")
        finally:
            release_row.set()
        locked.result(timeout=5)

    assert token is not None
    assert locked_seq not in {event.event_seq for event in claimed_events}
    assert {event.entity_id for event in claimed_events} == {people[1].pk, people[2].pk}


def test_postgres_concurrent_consumers_coalesce_duplicate_entity_events():
    person = _person("多消费者同实体")
    first_event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
    for _index in range(3):
        QueryLexiconChangeEvent.objects.create(
            entity_type=first_event.entity_type,
            entity_id=person.pk,
            action=QueryLexiconChangeEvent.Action.UPDATE,
            source_model=first_event.source_model,
            source_object_id=person.pk,
            correlation_id=uuid4(),
        )
    start = Barrier(2, timeout=5)

    def consume():
        def run():
            start.wait()
            return sync_service.process_pending_events(limit=2)

        return _thread_connection(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: consume(), range(2)))

    assert sorted(result["claimed"] for result in results) == [2, 2]
    assert QueryLexiconChangeEvent.objects.filter(processed_at__isnull=True).count() == 0
    state = QueryLexiconState.objects.get(key="default")
    assert state.revision == 1
    assert QueryLexiconEntry.objects.filter(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
    ).count() >= 1
    normalized = normalize_term(person.preferred_name)
    assert QueryLexiconEntry.objects.filter(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
        normalized_term=normalized,
    ).count() == 1


def test_postgres_expired_worker_lease_is_reclaimed_idempotently():
    person = _person("崩溃租约恢复人物")
    first_token, first_claim = sync_service._claim_events(limit=1)
    assert first_token is not None
    assert len(first_claim) == 1
    assert sync_service._claim_events(limit=1) == (None, [])

    QueryLexiconChangeEvent.objects.filter(
        event_seq=first_claim[0].event_seq
    ).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    second_token, second_claim = sync_service._claim_events(limit=1)
    assert second_token is not None
    assert second_token != first_token
    assert [event.event_seq for event in second_claim] == [first_claim[0].event_seq]

    result = sync_service.sync_entity(
        _key(person),
        event_seqs=[second_claim[0].event_seq],
        lease_token=second_token,
    )
    event = QueryLexiconChangeEvent.objects.get(
        event_seq=first_claim[0].event_seq
    )
    assert result["changed"] is True
    assert event.processed_at is not None
    assert event.lease_token is None
    assert sync_service.process_pending_events()["claimed"] == 0
    assert QueryLexiconState.objects.get(key="default").revision == 1


def test_postgres_retry_dead_letter_and_rebuild_recovery(monkeypatch, settings):
    person = _person("dead letter 恢复人物")
    settings.QUERY_LEXICON_EVENT_MAX_ATTEMPTS = 2
    settings.QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS = 1
    settings.QUERY_LEXICON_EVENT_RETRY_MAX_SECONDS = 1
    original_build = sync_service.build_entity

    with monkeypatch.context() as scoped:
        scoped.setattr(
            sync_service,
            "build_entity",
            lambda _key: (_ for _ in ()).throw(RuntimeError("forced worker failure")),
        )
        assert sync_service.process_pending_events()["failed"] == 1
        QueryLexiconChangeEvent.objects.update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        assert sync_service.process_pending_events()["failed"] == 1

    monkeypatch.setattr(sync_service, "build_entity", original_build)
    event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
    assert event.attempts == 2
    assert event.dead_lettered_at is not None
    assert event.processed_at is None
    assert event.lease_token is None

    rebuilt = sync_service.rebuild_query_lexicon()
    event.refresh_from_db()
    assert rebuilt["changed"] is True
    assert event.processed_at is not None
    assert event.applied_revision == rebuilt["revision"]


def test_postgres_rollbacks_do_not_leave_revision_or_ghost_event():
    revision = QueryLexiconState.objects.get(key="default").revision
    with pytest.raises(RuntimeError, match="authority rollback"):
        with transaction.atomic():
            _person("回滚 authority 人物")
            raise RuntimeError("authority rollback")

    assert not Person.objects.filter(preferred_name="回滚 authority 人物").exists()
    assert QueryLexiconChangeEvent.objects.count() == 0
    assert QueryLexiconState.objects.get(key="default").revision == revision

    person = _person("回滚 revision 人物")
    with pytest.raises(RuntimeError, match="revision rollback"):
        with transaction.atomic():
            sync_service.sync_entity(_key(person))
            raise RuntimeError("revision rollback")

    state = QueryLexiconState.objects.get(key="default")
    assert state.revision == revision
    assert not QueryLexiconEntry.objects.filter(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
    ).exists()


def test_postgres_watermark_does_not_use_sequence_as_commit_order():
    inserted = Event()
    release_late_commit = Event()
    details = Queue()

    def late_low_sequence_writer():
        def run():
            with transaction.atomic():
                person = _person("低序号晚提交人物")
                event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
                details.put((person.pk, event.event_seq))
                inserted.set()
                assert release_late_commit.wait(10)

        return _thread_connection(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        late_writer = executor.submit(late_low_sequence_writer)
        assert inserted.wait(5)
        later_sequence = _person("高序号早提交人物")
        high_event = QueryLexiconChangeEvent.objects.get(entity_id=later_sequence.pk)
        low_person_id, low_seq = details.get(timeout=2)
        assert low_seq < high_event.event_seq

        started = monotonic()
        rebuild = executor.submit(
            _thread_connection,
            sync_service.rebuild_query_lexicon,
        )
        sleep(0.3)
        assert not rebuild.done()
        release_late_commit.set()
        late_writer.result(timeout=10)
        result = rebuild.result(timeout=20)

    generation = QueryLexiconGeneration.objects.get(pk=result["generation"])
    assert monotonic() - started >= 0.3
    assert generation.start_event_seq >= high_event.event_seq
    assert QueryLexiconEntry.objects.filter(
        generation=generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id__in=[low_person_id, later_sequence.pk],
    ).values("entity_id").distinct().count() == 2


def test_postgres_merge_audit_resolves_chains_and_preserves_historical_names():
    first = _person("合并链旧名甲")
    second = _person("合并链旧名乙")
    survivor = _person("合并链最终人物")
    table = connection.ops.quote_name(Person._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, second.pk, first.pk],
        )
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, survivor.pk, second.pk],
        )

    dry_run = sync_service.dry_run_reconciliation()
    assert dry_run["merge_audit"]["anomaly_count"] == 0
    assert dry_run["merge_audit"]["valid_merges"] == 2
    assert dry_run["merge_audit"]["chained_merges"] == 1
    assert dry_run["merge_audit"]["historical_sources_resolvable"] == 2

    rebuilt = sync_service.rebuild_query_lexicon()
    generation = QueryLexiconGeneration.objects.get(pk=rebuilt["generation"])
    historical_terms = set(
        QueryLexiconEntry.objects.filter(
            generation=generation,
            entity_type=QueryLexiconEntry.EntityType.PERSON,
            entity_id=survivor.pk,
            term_type=QueryLexiconEntry.TermType.HISTORICAL,
        ).values_list("normalized_term", flat=True)
    )
    assert normalize_term(first.preferred_name) in historical_terms
    assert normalize_term(second.preferred_name) in historical_terms
    assert not QueryLexiconEntry.objects.filter(
        generation=generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id__in=[first.pk, second.pk],
    ).exists()


def test_postgres_merge_audit_reports_anomalies_and_blocks_formal_rebuild():
    missing_target = _person("缺失合并目标")
    cycle_left = _person("循环人物甲")
    cycle_right = _person("循环人物乙")
    rejected_survivor = Person.objects.create(
        preferred_name="已拒绝 survivor",
        authority_status=Person.AuthorityStatus.REJECTED,
    )
    rejected_source = _person("指向已拒绝 survivor")
    table = connection.ops.quote_name(Person._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, missing_target.pk],
        )
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, cycle_right.pk, cycle_left.pk],
        )
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, cycle_left.pk, cycle_right.pk],
        )
        cursor.execute(
            f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
            [Person.AuthorityStatus.MERGED, rejected_survivor.pk, rejected_source.pk],
        )

    generation_count = QueryLexiconGeneration.objects.count()
    dry_run = sync_service.dry_run_reconciliation()
    merge_audit = dry_run["merge_audit"]
    assert merge_audit["anomaly_counts"] == {
        "merged_cycle": 2,
        "merged_survivor_rejected": 1,
        "merged_target_missing": 1,
    }
    assert {finding["person_id"] for finding in merge_audit["findings"]} == {
        str(missing_target.pk),
        str(cycle_left.pk),
        str(cycle_right.pk),
        str(rejected_source.pk),
    }
    with pytest.raises(sync_service.QueryLexiconInvariantError, match="正式 rebuild 已停止"):
        sync_service.rebuild_query_lexicon()
    assert QueryLexiconGeneration.objects.count() == generation_count


def test_postgres_merge_audit_handles_dangling_target_and_self_constraint():
    person = _person("失联 survivor 人物")
    table = connection.ops.quote_name(Person._meta.db_table)
    dangling_id = uuid4()

    with pytest.raises(RuntimeError, match="rollback dangling target"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {table} SET authority_status = %s, merged_into_id = %s WHERE id = %s",
                    [Person.AuthorityStatus.MERGED, dangling_id, person.pk],
                )
            dry_run = sync_service.dry_run_reconciliation(
                entity_type=QueryLexiconEntry.EntityType.PERSON,
                entity_id=str(person.pk),
            )
            assert dry_run["merge_audit"]["anomaly_counts"] == {
                "merged_survivor_missing": 1
            }
            raise RuntimeError("rollback dangling target")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {table} SET authority_status = %s, merged_into_id = id WHERE id = %s",
                    [Person.AuthorityStatus.MERGED, person.pk],
                )


def test_postgres_legacy_0013_audit_stays_low_trust_and_not_displayable():
    legacy = TheorySchool.objects.create(
        name="批判理论旧记录",
        foreign_name="Critical Theory",
        slug=f"legacy-seed-{uuid4().hex}",
        editorial_status="published",
        search_aliases=["critical theory ascii seed", "pi pan li lun"],
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="批判理论",
        canonical_name_en="Critical Theory",
        slug=f"node-seed-{uuid4().hex}",
        status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    alias = KnowledgeNodeAlias.objects.create(
        node=node,
        alias="critical theory ascii seed",
        language="en",
        alias_type=KnowledgeNodeAlias.AliasType.TRANSLATION,
    )

    dry_run = sync_service.dry_run_reconciliation()
    assert dry_run["audit"]["suspected_0013_seed_count"] >= 1
    assert dry_run["audit"]["legacy_mixed_count"] >= 1
    assert dry_run["audit"]["generated_variant_count"] >= 1
    assert dry_run["audit"]["mapping_anomaly_count"] == 0

    rebuilt = sync_service.rebuild_query_lexicon()
    entry = QueryLexiconEntry.objects.get(
        generation_id=rebuilt["generation"],
        entity_type=QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        entity_id=node.pk,
        normalized_term=normalize_term(alias.alias),
    )
    assert entry.term_type == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert entry.source_kind == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
    assert entry.trust_level == QueryLexiconEntry.TrustLevel.LEGACY
    assert entry.displayable is False
    public_match = resolve_term(alias.alias, scope=PUBLIC_ACTIVE)["matches"][0]
    assert public_match["term_type"] == QueryLexiconEntry.TermType.SEARCH_VARIANT
    assert public_match["source_kind"] == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
    assert public_match["trust_level"] == QueryLexiconEntry.TrustLevel.LEGACY
    assert public_match["displayable"] is False


@pytest.mark.skipif(
    os.getenv("RUN_QUERY_LEXICON_LARGE_TEST") != "1",
    reason="set RUN_QUERY_LEXICON_LARGE_TEST=1 for the bounded large-data rehearsal",
)
def test_postgres_large_dataset_rebuild_cutover_smoke(monkeypatch):
    entity_count = int(os.getenv("QUERY_LEXICON_LARGE_TEST_ENTITIES", "1000"))
    people = [
        Person(
            preferred_name=f"规模演练人物 {index:05d}",
            original_name=f"Scale Rehearsal Person {index:05d}",
            authority_status=Person.AuthorityStatus.VERIFIED,
        )
        for index in range(entity_count)
    ]
    tracemalloc.start()
    started = monotonic()
    Person.objects.bulk_create(people, batch_size=250)
    bulk_seconds = monotonic() - started

    started = monotonic()
    first = sync_service.rebuild_query_lexicon()
    first_rebuild_seconds = monotonic() - started
    baseline_state = QueryLexiconState.objects.select_related("active_generation").get(
        key="default"
    )
    baseline_revision = baseline_state.revision
    baseline_generation_id = baseline_state.active_generation_id
    baseline_entry_count = baseline_state.active_generation.entry_count
    assert baseline_entry_count == baseline_state.active_generation.entries.count()
    assert baseline_entry_count > entity_count

    newcomer = _person("规模演练 watermark 新人物")
    staging_ready = Event()
    release_staging = Event()
    original_replace = sync_service._replace_generation_builds
    calls = 0

    def pause_after_staging_insert(generation, builds):
        nonlocal calls
        original_replace(generation, builds)
        calls += 1
        if calls == 1:
            staging_ready.set()
            assert release_staging.wait(20)

    monkeypatch.setattr(
        sync_service,
        "_replace_generation_builds",
        pause_after_staging_insert,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        rebuild = executor.submit(
            _thread_connection,
            sync_service.rebuild_query_lexicon,
        )
        assert staging_ready.wait(30)
        assert QueryLexiconState.objects.get(key="default").active_generation_id == baseline_generation_id
        assert resolve_term(people[0].preferred_name, scope=PUBLIC_ACTIVE)["matches"]
        assert not resolve_term(newcomer.preferred_name, scope=PUBLIC_ACTIVE)["matches"]
        cutover_started = monotonic()
        release_staging.set()
        second = rebuild.result(timeout=60)
        cutover_seconds = monotonic() - cutover_started

    assert second["changed"] is True
    state_after_cutover = QueryLexiconState.objects.select_related(
        "active_generation"
    ).get(key="default")
    assert state_after_cutover.revision == baseline_revision + 1
    assert resolve_term(newcomer.preferred_name, scope=PUBLIC_ACTIVE)["matches"]
    assert QueryLexiconGeneration.objects.get(
        pk=baseline_generation_id
    ).status == QueryLexiconGeneration.Status.RETIRED

    active_id = state_after_cutover.active_generation_id
    active_revision = state_after_cutover.revision
    with monkeypatch.context() as scoped:
        scoped.setattr(
            sync_service,
            "_collect_builds",
            lambda _keys: (_ for _ in ()).throw(RuntimeError("large build failure")),
        )
        with pytest.raises(RuntimeError, match="large build failure"):
            sync_service.rebuild_query_lexicon()
    state_after_failure = QueryLexiconState.objects.get(key="default")
    assert state_after_failure.active_generation_id == active_id
    assert state_after_failure.revision == active_revision
    assert QueryLexiconGeneration.objects.filter(
        status=QueryLexiconGeneration.Status.FAILED,
        error_message="large build failure",
    ).exists()

    retry_started = monotonic()
    retry = sync_service.rebuild_query_lexicon()
    retry_seconds = monotonic() - retry_started
    repeated = sync_service.rebuild_query_lexicon()
    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    final_state = QueryLexiconState.objects.get(key="default")
    assert retry["changed"] is False
    assert repeated["changed"] is False
    assert retry["content_hash"] == repeated["content_hash"]
    assert final_state.active_generation_id == active_id
    assert final_state.revision == active_revision

    print(
        "QUERY_LEXICON_LARGE_METRICS="
        + json.dumps(
            {
                "entities": entity_count + 1,
                "entries": state_after_cutover.active_generation.entry_count,
                "bulk_seconds": round(bulk_seconds, 3),
                "first_rebuild_seconds": round(first_rebuild_seconds, 3),
                "cutover_seconds": round(cutover_seconds, 3),
                "retry_seconds": round(retry_seconds, 3),
                "python_peak_mib": round(peak_bytes / 1024 / 1024, 2),
                "first_hash": first["content_hash"],
                "stable_hash": retry["content_hash"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
