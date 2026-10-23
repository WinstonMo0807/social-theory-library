"""Deferred until the unified acceptance run; not executed during implementation."""
import copy

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Person, PersonNameVariant
from catalog.services.person_authority import FIELDS, VARIANT_FIELDS, digest, state


@pytest.mark.django_db
def test_alias_preview_preserves_authority_and_exposes_exact_changes():
    actor = User.objects.create_user(username="alias-editor", role="admin")
    person = Person.objects.create(preferred_name="示例人物", authority_status="draft")
    alias = PersonNameVariant.objects.create(person=person, name="Old alias", language="en",
        variant_type="alias", source_kind="editorial", source_note="原始核对记录")
    variant = {key: getattr(alias, key) for key in VARIANT_FIELDS}
    variant.update(id=str(alias.pk), name="Revised alias", source_note="核对后记录")
    payload = {"operation": "update", "person_id": str(person.pk), "expected_version": digest(state(person)),
        "values": {key: getattr(person, key) for key in FIELDS}, "variants": [variant], "reason": "核对原记录"}
    client = APIClient()
    client.force_authenticate(actor)
    result = client.post("/api/catalog/admin/people/workspace/preview/", payload, format="json", HTTP_X_EDITOR_OWNER=str(actor.pk))
    assert result.status_code == 200
    assert result.data["fields"] == ["name_variants"]
    change = result.data["variant_changes"][0]
    assert change["before"]["name"] == "Old alias"
    assert change["before"]["source_note"] == "原始核对记录"
    assert change["after"]["name"] == "Revised alias"
    assert result.data["before"] == result.data["after"]
    alias.refresh_from_db()
    assert alias.name == "Old alias"  # preview cannot apply the edit
    missing = copy.deepcopy(payload)
    missing["variants"] = []
    assert client.post("/api/catalog/admin/people/workspace/preview/", missing, format="json",
        HTTP_X_EDITOR_OWNER=str(actor.pk)).status_code == 400
    assert client.post("/api/catalog/admin/people/workspace/preview/", payload, format="json",
        HTTP_X_EDITOR_OWNER="another-account").status_code == 403
