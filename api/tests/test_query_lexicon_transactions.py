from __future__ import annotations

from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from catalog.models import (
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Person,
    PersonNameVariant,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    TheorySchool,
)
from catalog.services.query_lexicon import mutations


pytestmark = pytest.mark.django_db


def _person(name: str = "事务测试人物") -> Person:
    return Person.objects.create(
        preferred_name=name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def _node(name: str) -> KnowledgeNode:
    return KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh=name,
        slug=f"node-{uuid4().hex}",
        status="published",
    )


def test_instance_create_and_queryset_update_write_durable_events():
    person = _person()

    created = QueryLexiconChangeEvent.objects.get()
    assert created.entity_type == QueryLexiconEntry.EntityType.PERSON
    assert created.entity_id == person.pk
    assert created.action == QueryLexiconChangeEvent.Action.CREATE
    assert created.source_model == "catalog.Person"
    assert created.processed_at is None

    QueryLexiconChangeEvent.objects.all().delete()
    updated = Person.objects.filter(pk=person.pk).update(biography="事务字段更新")

    assert updated == 1
    event = QueryLexiconChangeEvent.objects.get()
    assert event.entity_type == QueryLexiconEntry.EntityType.PERSON
    assert event.entity_id == person.pk
    assert event.action == QueryLexiconChangeEvent.Action.UPDATE


def test_queryset_identity_update_requires_normalizing_write_path():
    person = _person("禁止捷径更新人物")
    QueryLexiconChangeEvent.objects.all().delete()

    with pytest.raises(ValueError, match="逐条 save 或 bulk_update"):
        Person.objects.filter(pk=person.pk).update(preferred_name="绕过名称")

    person.refresh_from_db()
    assert person.preferred_name == "禁止捷径更新人物"
    assert QueryLexiconChangeEvent.objects.count() == 0


def test_worker_wakeup_is_deferred_until_transaction_commit(
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    dispatched = []

    def capture_dispatch(event_seqs):
        dispatched.append(tuple(event_seqs))
        return True

    monkeypatch.setattr(
        mutations,
        "dispatch_query_lexicon_wakeup",
        capture_dispatch,
    )
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        person = _person("提交后唤醒人物")
        assert dispatched == []

    assert len(callbacks) == 1
    assert len(dispatched) == 1
    event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
    assert dispatched == [(event.event_seq,)]


def test_event_recording_failure_rolls_back_authority_write(monkeypatch):
    def fail_event_recording(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(mutations, "_record_events", fail_event_recording)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        _person("必须回滚的人物")

    assert not Person.objects.filter(preferred_name="必须回滚的人物").exists()
    assert QueryLexiconChangeEvent.objects.count() == 0


def test_outer_transaction_rollback_leaves_no_authority_or_ghost_event():
    with pytest.raises(RuntimeError, match="force rollback"):
        with transaction.atomic():
            _person("外层回滚人物")
            raise RuntimeError("force rollback")

    assert not Person.objects.filter(preferred_name="外层回滚人物").exists()
    assert QueryLexiconChangeEvent.objects.count() == 0


def test_instance_delete_records_the_deleted_canonical_entity():
    person = _person("删除事务人物")
    person_id = person.pk
    QueryLexiconChangeEvent.objects.all().delete()

    person.delete()

    assert not Person.objects.filter(pk=person_id).exists()
    event = QueryLexiconChangeEvent.objects.get()
    assert event.action == QueryLexiconChangeEvent.Action.DELETE
    assert event.entity_type == QueryLexiconEntry.EntityType.PERSON
    assert event.entity_id == person_id
    assert event.source_object_id == person_id


def test_invalid_queryset_merge_rolls_back_authority_and_event():
    person = _person("错误合并人物")
    QueryLexiconChangeEvent.objects.all().delete()

    with pytest.raises((IntegrityError, ValidationError)):
        Person.objects.filter(pk=person.pk).update(
            authority_status=Person.AuthorityStatus.MERGED,
            merged_into=None,
        )

    person.refresh_from_db()
    assert person.authority_status == Person.AuthorityStatus.VERIFIED
    assert person.merged_into_id is None
    assert QueryLexiconChangeEvent.objects.count() == 0


def test_person_merge_update_invalidates_source_and_survivor():
    source = _person("待合并人物")
    survivor = _person("保留人物")
    QueryLexiconChangeEvent.objects.all().delete()

    source.authority_status = Person.AuthorityStatus.MERGED
    source.merged_into = survivor
    source.save()

    keys = set(
        QueryLexiconChangeEvent.objects.values_list("entity_type", "entity_id")
    )
    assert keys == {
        (QueryLexiconEntry.EntityType.PERSON, source.pk),
        (QueryLexiconEntry.EntityType.PERSON, survivor.pk),
    }


@pytest.mark.parametrize("requested_field", ["authority_status", "merged_into"])
def test_person_partial_merge_save_persists_status_and_target_together(
    requested_field,
):
    survivor = _person(f"局部合并目标-{requested_field}")
    source = _person(f"局部合并来源-{requested_field}")
    QueryLexiconChangeEvent.objects.all().delete()

    source.authority_status = Person.AuthorityStatus.MERGED
    source.merged_into = survivor
    source.save(update_fields=[requested_field])
    source.refresh_from_db()

    assert source.authority_status == Person.AuthorityStatus.MERGED
    assert source.merged_into_id == survivor.pk
    assert set(
        QueryLexiconChangeEvent.objects.values_list("entity_type", "entity_id")
    ) == {
        (QueryLexiconEntry.EntityType.PERSON, source.pk),
        (QueryLexiconEntry.EntityType.PERSON, survivor.pk),
    }


@pytest.mark.parametrize("requested_field", ["authority_status", "merged_into"])
def test_person_partial_unmerge_save_persists_status_and_target_together(
    requested_field,
):
    survivor = _person(f"局部撤销目标-{requested_field}")
    source = Person.objects.create(
        preferred_name=f"局部撤销来源-{requested_field}",
        authority_status=Person.AuthorityStatus.MERGED,
        merged_into=survivor,
    )
    QueryLexiconChangeEvent.objects.all().delete()

    source.authority_status = Person.AuthorityStatus.VERIFIED
    source.merged_into = None
    source.save(update_fields=[requested_field])
    source.refresh_from_db()

    assert source.authority_status == Person.AuthorityStatus.VERIFIED
    assert source.merged_into_id is None
    assert set(
        QueryLexiconChangeEvent.objects.values_list("entity_type", "entity_id")
    ) == {
        (QueryLexiconEntry.EntityType.PERSON, source.pk),
        (QueryLexiconEntry.EntityType.PERSON, survivor.pk),
    }


def test_person_bulk_update_persists_merge_status_and_target_together():
    survivor = _person("批量合并目标")
    source = _person("批量合并来源")
    QueryLexiconChangeEvent.objects.all().delete()

    source.authority_status = Person.AuthorityStatus.MERGED
    source.merged_into = survivor
    Person.objects.bulk_update([source], ["authority_status"])
    source.refresh_from_db()

    assert source.authority_status == Person.AuthorityStatus.MERGED
    assert source.merged_into_id == survivor.pk
    assert set(
        QueryLexiconChangeEvent.objects.values_list("entity_type", "entity_id")
    ) == {
        (QueryLexiconEntry.EntityType.PERSON, source.pk),
        (QueryLexiconEntry.EntityType.PERSON, survivor.pk),
    }


def test_bulk_create_and_bulk_update_emit_one_event_per_entity():
    people = [
        Person(
            preferred_name=f"批量人物{i}",
            authority_status=Person.AuthorityStatus.VERIFIED,
        )
        for i in range(2)
    ]
    Person.objects.bulk_create(people)

    assert QueryLexiconChangeEvent.objects.filter(
        action=QueryLexiconChangeEvent.Action.CREATE,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
    ).count() == 2

    QueryLexiconChangeEvent.objects.all().delete()
    for index, person in enumerate(people):
        person.biography = f"批量更新{index}"
    Person.objects.bulk_update(people, ["biography"])

    events = QueryLexiconChangeEvent.objects.filter(
        action=QueryLexiconChangeEvent.Action.UPDATE,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
    )
    assert events.count() == 2
    assert set(events.values_list("entity_id", flat=True)) == {
        person.pk for person in people
    }


def test_person_name_variant_rejects_generated_search_variants():
    person = _person("名称变体人物")
    QueryLexiconChangeEvent.objects.all().delete()

    with pytest.raises(ValidationError):
        PersonNameVariant.objects.create(
            person=person,
            name="ming cheng bian ti ren wu",
            language="und",
            variant_type="search_variant",
            source_kind="generated_search_variant",
        )

    assert PersonNameVariant.objects.count() == 0
    assert QueryLexiconChangeEvent.objects.count() == 0


def test_mapping_retarget_emits_legacy_and_both_node_entity_events():
    first = _node("旧映射节点")
    second = _node("新映射节点")
    legacy = TheorySchool.objects.create(
        name="映射来源理论",
        slug=f"theory-{uuid4().hex}",
        editorial_status="published",
    )
    mapping = LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.pk,
        node=first,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    QueryLexiconChangeEvent.objects.all().delete()

    LegacyKnowledgeMapping.objects.filter(pk=mapping.pk).update(node=second)

    keys = set(
        QueryLexiconChangeEvent.objects.values_list("entity_type", "entity_id")
    )
    assert keys == {
        (QueryLexiconEntry.EntityType.THEORY_SCHOOL, legacy.pk),
        (QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, first.pk),
        (QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, second.pk),
    }
