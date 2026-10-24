"""Deferred private-note and bound-prose acceptance; no test execution during development."""
from copy import deepcopy
import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import KnowledgeNode
from catalog.node_editorial import normalize_node_editorial, public_node_prose
from catalog.theory_serializers import KnowledgeNodeDetailSerializer
from .test_stl4_node_relations_20261024 import headers, node


def details(text="准确的公开解释"):
    return {"internal_note": "仅内部核对，不能给普通读者显示", "prose": {"summary": {
        "text": text, "text_style": "paragraph", "text_marks": [{"start": 0, "end": 2, "kind": "strong"}],
    }}}


def test_only_formats_for_exact_canonical_text_can_be_projected():
    record = KnowledgeNode(summary="准确的公开解释", definition="", theoretical_boundary="", editorial_details=details())
    result = public_node_prose(record)
    assert set(result) == {"summary"} and result["summary"]["text_marks"][0]["kind"] == "strong"
    assert "internal_note" not in str(result)
    record.summary = "旧客户端已改正文"
    assert public_node_prose(record) == {}
    record.summary = "准确的公开解释"
    record.editorial_details["prose"]["summary"]["text_marks"] = [{"start": 0, "end": 2, "kind": "link", "href": "javascript:alert(1)"}]
    assert public_node_prose(record) == {}


@pytest.mark.parametrize("damage", ["note_limit", "unknown_field", "raw_html", "unsafe_link", "long_format"])
def test_editorial_details_are_bounded_and_reject_untrusted_structure(damage):
    value = deepcopy(details())
    if damage == "note_limit": value["internal_note"] = "字" * 501
    elif damage == "unknown_field": value["owner_id"] = "forged"
    elif damage == "raw_html": value["prose"]["summary"]["html"] = "<script>untrusted</script>"
    elif damage == "unsafe_link": value["prose"]["summary"]["text_marks"] = [{"start": 0, "end": 2, "kind": "link", "href": "javascript:alert(1)"}]
    else: value["prose"]["summary"]["text"] = "字" * 30001
    with pytest.raises(ValidationError): normalize_node_editorial(value)


@pytest.mark.django_db
def test_node_notes_and_rich_prose_share_existing_draft_permission_and_publication(api_client, admin_user, reader_user):
    record = node()
    record.summary = "原公开解释"
    record.save(update_fields=["summary", "updated_at"])
    url = f"/api/catalog/admin/theory-system/nodes/{record.pk}/"
    api_client.force_authenticate(admin_user)
    current = api_client.get(url)
    saved = api_client.patch(url, {"summary": "准确的公开解释", "editorial_details": details()}, format="json",
        HTTP_IF_MATCH=current.data["edit_version"], **headers(admin_user))
    assert saved.status_code == 202
    assert saved.data["editorial_details"]["internal_note"] == details()["internal_note"]
    record.refresh_from_db()
    assert record.summary == "原公开解释" and record.editorial_details == {}
    public = KnowledgeNodeDetailSerializer(record).data
    assert "editorial_details" not in public and public["prose"] == {}
    published = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json", **headers(admin_user))
    assert published.status_code == 200
    record.refresh_from_db()
    public = KnowledgeNodeDetailSerializer(record).data
    assert public["prose"]["summary"]["text"] == record.summary
    assert details()["internal_note"] not in str(public)
    assert record.versions.order_by("-version_number").first().snapshot["editorial_details"]["internal_note"] == details()["internal_note"]
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403


@pytest.mark.django_db
def test_node_and_relation_directories_reject_inherited_write_methods(api_client, admin_user):
    record = node()
    api_client.force_authenticate(admin_user)
    for url in ["/api/catalog/admin/theory-system/nodes/", "/api/catalog/admin/theory-system/relations/",
                f"/api/catalog/admin/theory-system/nodes/{record.pk}/relations/"]:
        assert api_client.patch(url, {}, format="json", **headers(admin_user)).status_code == 405
