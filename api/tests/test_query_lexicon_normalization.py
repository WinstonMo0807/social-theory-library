from __future__ import annotations

from uuid import uuid4

import pytest

from catalog.models import KnowledgeNode, KnowledgeNodeAlias, Person, PersonNameVariant
from catalog.services.query_lexicon.normalization import (
    generated_search_variants,
    normalize_term,
)


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
        slug=f"normalize-{uuid4().hex}",
        status="published",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  ＡＢＣ\u3000\tTheory  ", "abc theory"),
        ("制度， Institution；Ａ", "制度, institution;a"),
        ("中文、English。", "中文、english。"),
        ("Émile-Durkheim’s", "émile-durkheim’s"),
        ("a\u200bb\ufeffc", "abc"),
    ],
)
def test_normalize_term_nfkc_casefold_whitespace_and_punctuation(raw, expected):
    assert normalize_term(raw) == expected
    assert normalize_term(normalize_term(raw)) == expected


def test_transliteration_and_pinyin_are_separate_generated_variants():
    assert normalize_term("涂尔干") == "涂尔干"

    variants = {
        (variant.generator, variant.term)
        for variant in generated_search_variants("涂尔干")
    }

    assert ("pinyin", "t涂尔干") not in variants
    assert any(generator == "pinyin" and term == "tuergan" for generator, term in variants)
    assert any(
        generator == "pinyin_initials" and term == "teg"
        for generator, term in variants
    )


def test_person_name_variant_keeps_normalized_name_in_sync_for_all_orm_writes():
    person = _person("名称规范化人物")
    variant = PersonNameVariant.objects.create(
        person=person,
        name="  Ｅ． Durkheim  ",
        language="en",
        variant_type=PersonNameVariant.VariantType.TRANSLATION,
        is_verified=True,
    )
    assert variant.normalized_name == "e. durkheim"

    variant.name = "  Émile  Durkheim "
    variant.save(update_fields=["name"])
    variant.refresh_from_db()
    assert variant.normalized_name == "émile durkheim"

    PersonNameVariant.objects.filter(pk=variant.pk).update(name="DURKHEIM")
    variant.refresh_from_db()
    assert variant.normalized_name == "durkheim"

    second = PersonNameVariant(
        person=person,
        name="  杜尔凯姆  ",
        language="zh-Hans",
        variant_type=PersonNameVariant.VariantType.ALIAS,
        is_verified=True,
    )
    PersonNameVariant.objects.bulk_create([second])
    second.refresh_from_db()
    assert second.normalized_name == "杜尔凯姆"

    second.name = "杜  尔  凯  姆"
    PersonNameVariant.objects.bulk_update([second], ["name"])
    second.refresh_from_db()
    assert second.normalized_name == "杜 尔 凯 姆"


def test_knowledge_alias_keeps_existing_authority_normalization_on_bulk_writes():
    node = _node("规范化知识别名")
    alias = KnowledgeNodeAlias(
        node=node,
        alias="  SOCIAL   THEORY ",
        language="en",
        alias_type=KnowledgeNodeAlias.AliasType.TRANSLATION,
    )
    KnowledgeNodeAlias.objects.bulk_create([alias])
    alias.refresh_from_db()
    assert alias.normalized_alias == "social theory"

    alias.alias = "Critical   Theory"
    KnowledgeNodeAlias.objects.bulk_update([alias], ["alias"])
    alias.refresh_from_db()
    assert alias.normalized_alias == "critical theory"


def test_authority_queryset_primary_key_update_is_rejected():
    person = _person("禁止改主键")

    with pytest.raises(ValueError, match="不允许.*主键"):
        Person.objects.filter(pk=person.pk).update(id=uuid4())

    assert Person.objects.filter(pk=person.pk).exists()
