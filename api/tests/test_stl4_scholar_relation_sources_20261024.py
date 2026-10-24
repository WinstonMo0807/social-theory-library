"""Deferred acceptance for original scholar relation source identity; not executed."""
from uuid import uuid4
import pytest
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, EvidenceSpan, ScholarRelation
from catalog.services import shared_curation as service
from catalog.services.theory_graph import _attach_evidence
from .test_stl4_scholar_relation_commands_20261024 import profiles
from .test_stl4_person_node_sources_20261024 import material

pytestmark = pytest.mark.django_db


def reference(span):
    return {"span_id": str(span.pk), "document_revision_id": str(span.document_revision_id)}


def payload(first, second, span):
    return {"source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "influence",
        "direction": "directed", "summary": "验收用原文说明", "source": "", "source_anchor": reference(span)}


def graph_material(row):
    edge = {"entity_id": str(row.pk), "model": "ScholarRelation", "source_status": "missing"}
    _attach_evidence([edge], None)
    return edge["evidence"]


def test_draft_quote_and_published_quote_keep_separate_original_versions(admin_user):
    first, second = profiles()
    old, _, _ = material()
    new, _, _ = material()
    data = payload(first, second, old)
    saved = service.save_relation(None, data, admin_user)
    row = ScholarRelation.objects.get(pk=saved["id"])
    assert row.evidence_span_id is None and saved["source_material"]["quote"] == old.original_text
    service.publish_relation(row.pk, saved["edit_version"], admin_user)
    changed = service.save_relation(row.pk, {**data, "source_anchor": reference(new), "edit_version": saved["edit_version"]}, admin_user)
    row.refresh_from_db()
    assert row.evidence_span_id == old.pk and changed["source_anchor"] == reference(new)
    public = service.relation_payload(row, public=True)
    assert public["source_anchor"] is None and public["source_material"]["document_revision_id"] == str(old.document_revision_id)
    assert graph_material(row)[0]["id"] == str(old.pk)
    assert service.relation_payload(row, include_source=False)["source_material"] is None
    service.publish_relation(row.pk, changed["edit_version"], admin_user)
    row.refresh_from_db()
    assert row.evidence_span_id == new.pk and graph_material(row)[0]["id"] == str(new.pk)
    with pytest.raises(ProtectedError):
        new.delete()


@pytest.mark.parametrize("damage", ["private", "stale", "wrong_revision"])
def test_invalid_source_fails_closed_but_original_note_and_archive_remain_available(admin_user, damage):
    first, second = profiles()
    span, asset, _ = material()
    data = payload(first, second, span)
    saved = service.save_relation(None, data, admin_user)
    service.publish_relation(saved["id"], saved["edit_version"], admin_user)
    row = ScholarRelation.objects.get(pk=saved["id"])
    if damage == "private":
        Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    elif damage == "stale":
        EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    else:
        other, _, _ = material()
        row.source_document_revision = other.document_revision
        row.save(update_fields=["source_document_revision", "updated_at"])
    public = service.relation_payload(row, public=True)
    assert public["source_anchor"] is None and public["source_material"] is None
    assert not graph_material(row)
    changed = service.save_relation(row.pk, {**data, "summary": "保留原身份并核对", "edit_version": saved["edit_version"]}, admin_user)
    assert changed["source_anchor"] == reference(span)
    if damage != "wrong_revision":
        with pytest.raises(ValidationError):
            service.publish_relation(row.pk, changed["edit_version"], admin_user)
    service.archive_relation(row.pk, changed["edit_version"], admin_user)
    row.refresh_from_db()
    assert service.relation_payload(row, public=True) is None


def test_reference_input_is_strict_and_private_source_cannot_publish(admin_user):
    first, second = profiles()
    span, asset, _ = material()
    data = payload(first, second, span)
    with pytest.raises(ValidationError):
        service.save_relation(None, {**data, "source_anchor": {**reference(span), "quote": "不能改写原文"}}, admin_user)
    with pytest.raises(ValidationError):
        service.save_relation(None, {**data, "source_anchor": {**reference(span), "document_revision_id": str(uuid4())}}, admin_user)
    Asset.objects.filter(pk=asset.pk).update(access_status="registered")
    saved = service.save_relation(None, data, admin_user)
    assert not saved["source_material"]["public_eligible"] and not saved["source_material"]["reader_href"]
    with pytest.raises(ValidationError):
        service.publish_relation(saved["id"], saved["edit_version"], admin_user)
    cleared = service.save_relation(saved["id"], {**data, "source_anchor": None, "source": "独立文字出处", "edit_version": saved["edit_version"]}, admin_user)
    service.publish_relation(saved["id"], cleared["edit_version"], admin_user)
    row = ScholarRelation.objects.get(pk=saved["id"])
    assert row.evidence_span_id is None and row.source_document_revision_id is None
