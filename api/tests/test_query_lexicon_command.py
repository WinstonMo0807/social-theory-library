from __future__ import annotations

from io import StringIO
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from catalog.models import Person, QueryLexiconGeneration, QueryLexiconState


pytestmark = pytest.mark.django_db


def _person(name: str) -> Person:
    return Person.objects.create(
        preferred_name=name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def test_rebuild_command_dry_run_is_read_only_and_emits_audit_json():
    _person("命令审计人物")
    state = QueryLexiconState.objects.get(key="default")
    generation_count = QueryLexiconGeneration.objects.count()
    output = StringIO()

    call_command("rebuild_query_lexicon", "--dry-run", stdout=output)

    payload = json.loads(output.getvalue())
    state.refresh_from_db()
    assert payload["dry_run"] is True
    assert payload["audit"]["entities"] >= 1
    assert payload["audit"]["generated_search_variant_sources"] >= 1
    assert payload["expected_entries"] >= 1
    assert QueryLexiconGeneration.objects.count() == generation_count
    assert state.revision == 0


def test_rebuild_command_supports_targeted_entity_reconciliation():
    person = _person("命令定向人物")
    output = StringIO()

    call_command(
        "rebuild_query_lexicon",
        "--entity-type",
        "person",
        "--entity-id",
        str(person.pk),
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    state = QueryLexiconState.objects.get(key="default")
    assert payload["changed"] is True
    assert payload["revision"] == state.revision == 1


def test_rebuild_command_rejects_invalid_selector_without_staging_write():
    generation_count = QueryLexiconGeneration.objects.count()

    with pytest.raises(CommandError, match="无效 QueryLexicon entity id"):
        call_command(
            "rebuild_query_lexicon",
            "--entity-type",
            "person",
            "--entity-id",
            "not-a-uuid",
        )

    assert QueryLexiconGeneration.objects.count() == generation_count


def test_rebuild_command_requires_rule_versions_as_a_pair():
    with pytest.raises(CommandError, match="两个版本参数必须同时提供"):
        call_command(
            "rebuild_query_lexicon",
            "--normalization-version",
            "query-lexicon-normalize-v1",
        )
