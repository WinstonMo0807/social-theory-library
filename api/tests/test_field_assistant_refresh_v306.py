"""An inline contributor save must invalidate the form opened before it."""

import pytest

from catalog.services.cataloging_sessions import open_cataloging_session


@pytest.mark.django_db
@pytest.mark.parametrize("field_name", ["author", "translator"])
def test_inline_person_cannot_be_erased_by_confirmation_from_an_old_form(api_client, admin_user, field_name):
    session, _ = open_cataloging_session(actor=admin_user, source_type="manual", title="同页作者确认")
    api_client.force_authenticate(admin_user)
    workspace_url = f"/api/catalog/admin/library/works/{session.work_id}/?edition={session.edition_id}"
    section_url = f"/api/catalog/admin/library/works/{session.work_id}/sections/contributors/?edition={session.edition_id}"
    old_form = api_client.get(workspace_url).data["data"]["contributors"]
    assert old_form["items"] == []
    created = api_client.post("/api/catalog/admin/field-assistant/create/", {
        "edition_id": str(session.edition_id), "field_name": field_name, "label": f"同页新建{field_name}",
    }, format="json")
    assert created.status_code == 201, created.data
    person_id = created.data["entity"]["id"]
    stale = api_client.patch(section_url, {"data": old_form, "confirm_section": True}, format="json")
    assert stale.status_code == 409, stale.data
    assert stale.data["code"] == "workflow_edit_conflict"
    fresh = api_client.get(workspace_url).data["data"]["contributors"]
    assert fresh["expected_updated_at"] != old_form["expected_updated_at"]
    assert [(row["person_id"], row["role"]) for row in fresh["items"]] == [(person_id, field_name)]
    confirmed = api_client.patch(section_url, {"data": fresh, "confirm_section": True}, format="json")
    assert confirmed.status_code == 200, confirmed.data
    assert session.edition.contributions.filter(person_id=person_id, role=field_name, approved=True).count() == 1
