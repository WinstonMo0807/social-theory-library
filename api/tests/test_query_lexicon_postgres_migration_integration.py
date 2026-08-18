from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.django_db(transaction=True),
]


def test_postgres_migration_0027_preserves_authority_source_rows():
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")

    executor = MigrationExecutor(connection)
    old_target = [("catalog", "0026_semantic_feedback_deduplication")]
    new_target = [("catalog", "0027_query_lexicon_core")]
    executor.migrate(old_target)
    try:
        old_apps = executor.loader.project_state(old_target).apps
        Person = old_apps.get_model("catalog", "Person")
        KnowledgeNode = old_apps.get_model("catalog", "KnowledgeNode")
        KnowledgeNodeAlias = old_apps.get_model("catalog", "KnowledgeNodeAlias")

        person_id = uuid4()
        node_id = uuid4()
        alias_id = uuid4()
        Person.objects.create(
            id=person_id,
            preferred_name="0027 迁移保留人物",
            original_name="Migration Preserved Person",
            aliases=["migration preserved person", "qian yi bao liu ren wu"],
            authority_status="merged",
        )
        KnowledgeNode.objects.create(
            id=node_id,
            node_type="concept",
            canonical_name_zh="迁移保留概念",
            canonical_name_en="Migration Preserved Concept",
            slug=f"migration-preserved-{uuid4().hex}",
            status="published",
        )
        KnowledgeNodeAlias.objects.create(
            id=alias_id,
            node_id=node_id,
            alias="ASCII suspect seed",
            normalized_alias="ascii suspect seed",
            language="en",
            alias_type="translation",
        )
        before_person = Person.objects.filter(pk=person_id).values().get()
        before_node = KnowledgeNode.objects.filter(pk=node_id).values().get()
        before_alias = KnowledgeNodeAlias.objects.filter(pk=alias_id).values().get()

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        NewPerson = new_apps.get_model("catalog", "Person")
        NewKnowledgeNode = new_apps.get_model("catalog", "KnowledgeNode")
        NewKnowledgeNodeAlias = new_apps.get_model("catalog", "KnowledgeNodeAlias")
        Generation = new_apps.get_model("catalog", "QueryLexiconGeneration")
        State = new_apps.get_model("catalog", "QueryLexiconState")
        Entry = new_apps.get_model("catalog", "QueryLexiconEntry")
        ChangeEvent = new_apps.get_model("catalog", "QueryLexiconChangeEvent")

        after_person = NewPerson.objects.filter(pk=person_id).values().get()
        merged_into_id = after_person.pop("merged_into_id")
        assert after_person == before_person
        assert merged_into_id is None
        assert NewKnowledgeNode.objects.filter(pk=node_id).values().get() == before_node
        assert NewKnowledgeNodeAlias.objects.filter(pk=alias_id).values().get() == before_alias
        state = State.objects.get(pk="default")
        generation = Generation.objects.get(pk=state.active_generation_id)
        assert state.revision == 0
        assert generation.status == "active"
        assert generation.entry_count == 0
        assert Entry.objects.count() == 0
        assert ChangeEvent.objects.count() == 0
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
