"""Deferred coverage: filters must not change the global coverage denominator."""
from uuid import uuid4

import pytest

from catalog.models import QueryLexiconEntry, QueryLexiconGeneration, QueryLexiconState
from catalog.services.query_lexicon.operations import query_lexicon_workspace


@pytest.mark.django_db
def test_rule_categories_and_access_filters_preserve_global_counts():
    generation = QueryLexiconGeneration.objects.create(status="active", normalization_version="fixture", source_registry_version="fixture", entry_count=4)
    QueryLexiconState.objects.create(active_generation=generation, normalization_version="fixture", source_registry_version="fixture")
    rows = [("canonical", True, True), ("alias", True, True), ("translation", False, True), ("search_variant", False, False)]
    for index, (kind, public, admin) in enumerate(rows):
        QueryLexiconEntry.objects.create(generation=generation, entity_type="knowledge_node", entity_id=uuid4(), term=f"fixture {index}",
            normalized_term=f"fixture {index}", language="en", term_type=kind, source_kind="authority_field", trust_level="authoritative",
            source_ref=f"fixture:{index}", source_fingerprint="0"*64, public_active=public, admin_resolvable=admin)
    result = query_lexicon_workspace(term_group="aliases", availability="admin", limit=1)
    assert result["count"] == 1 and result["terms"][0]["term_type"] == "translation"
    assert result["entries"] == 4 and result["public_active_entries"] == 2
    assert result["rule_counts"] == {"canonical": 0, "aliases": 1, "variants": 0}
    assert query_lexicon_workspace(term_group="variants", availability="inactive")["count"] == 1
