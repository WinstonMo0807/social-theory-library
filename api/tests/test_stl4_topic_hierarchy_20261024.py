"""Deferred M22 hierarchy confirmation and readonly path acceptance definitions."""
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import Topic
from catalog.services.public_topics import inspect_topic_parent, validate_topic_parent
from catalog.topic_editor import topic_organization_preview

pytestmark = pytest.mark.django_db


def topic(name, parent=None):
    return Topic.objects.create(name=name, slug=f"hierarchy-{uuid4()}", parent=parent)


def test_cycle_preview_returns_real_identity_path_and_does_not_move_topic():
    root = topic("根主题")
    child = topic("子主题", root)
    grandchild = topic("孙主题", child)
    preview = topic_organization_preview(root, {"parent": grandchild.pk})
    assert [row["id"] for row in preview["cycle_path"]] == [str(root.pk), str(grandchild.pk), str(child.pk), str(root.pk)]
    assert preview["problems"] and not preview["can_publish"]
    assert preview["descendant_count"] == 2
    root.refresh_from_db()
    assert root.parent_id is None
    with pytest.raises(ValidationError):
        validate_topic_parent(root, grandchild.pk)


def test_same_parent_uuid_string_is_not_reported_as_changed_and_old_cycles_fail():
    root = topic("根主题")
    child = topic("子主题", root)
    preview = topic_organization_preview(child, {"parent": str(root.pk)})
    assert not preview["parent_changed"] and not preview["problems"]
    assert [row["name"] for row in preview["parent_path"]] == ["子主题", "根主题"]
    Topic.objects.filter(pk=root.pk).update(parent=child)
    other = topic("另一主题")
    assert inspect_topic_parent(other, child.pk)["cycle_path"]
    with pytest.raises(ValidationError):
        validate_topic_parent(other, child.pk)


def test_owner_and_reader_cannot_query_admin_hierarchy_impact(api_client, admin_user, reader_user):
    row = topic("合成主题")
    url = f"/api/catalog/admin/topics/{row.pk}/organization-preview/"
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, {"parent": None}, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    response = api_client.post(url, {"parent": None}, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and not response.data["parent_changed"]
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, {"parent": None}, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
