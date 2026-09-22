"""Forward schema compatibility for the retained 3.0.7 application image."""
from uuid import uuid4

import pytest
from django.db import models
from django.test.utils import isolate_apps

from catalog.models import SemanticIndexVersion


@pytest.mark.django_db
def test_old_orm_insert_without_family_uses_database_semantic_default():
    # Reproduce the old model's INSERT: its field list has no index_family.
    # This catches a Python-only default, which new ORM inserts cannot expose.
    with isolate_apps():
        legacy_fields = {
            field.name: field.clone()
            for field in SemanticIndexVersion._meta.local_fields
            if field.name != "index_family"
        }
        legacy_model = type("LegacySemanticIndexVersion", (models.Model,), {
            "__module__": __name__,
            "Meta": type("Meta", (), {
                "app_label": "compatibility_test",
                "managed": False,
                "db_table": SemanticIndexVersion._meta.db_table,
            }),
            **legacy_fields,
        })
        legacy_row = legacy_model.objects.create(
            uid=f"v307-insert-{uuid4().hex}", provider="compatibility_probe", status="retired",
        )

    current_row = SemanticIndexVersion.all_objects.get(pk=legacy_row.pk)
    assert current_row.index_family == "semantic"
    assert SemanticIndexVersion.objects.filter(pk=legacy_row.pk).exists()
    assert not SemanticIndexVersion.discovery_objects.filter(pk=legacy_row.pk).exists()
