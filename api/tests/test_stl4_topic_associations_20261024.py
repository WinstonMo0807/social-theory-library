"""Deferred acceptance definitions; no business requests were executed in development."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import CurationProject, RecommendationIssue, Topic
from catalog.services.public_topics import capture_topic_publication, preview_topic, public_topic_detail, validate_topic_curation
from catalog.topic_associations import association_note
from .test_reading_paths_20261021 import source

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/topics/association-choices/"


def arranged(editions):
    return {"edition_ids": [str(row.pk) for row in editions], "association_notes": {
        "edition_ids": {str(row.pk): f"版本说明 {index}" for index, row in enumerate(editions)}}}


def test_notes_reject_wrong_group_removed_ids_and_excess_text():
    edition = source(fulltext=False)[1]
    data = arranged([edition])
    assert validate_topic_curation(data)["association_notes"] == data["association_notes"]
    for entries in ({str(uuid4()): "错误关联"}, {str(edition.pk): "字" * 601}, {str(edition.pk): {"html": "invalid"}}):
        with pytest.raises(ValidationError):
            validate_topic_curation({"edition_ids": [str(edition.pk)], "association_notes": {"edition_ids": entries}})
    with pytest.raises(ValidationError):
        validate_topic_curation({**data, "association_notes": {"private_notes": {str(edition.pk): "invalid"}}})
    assert association_note(SimpleNamespace(curation={"association_notes": data["association_notes"]}), edition.pk, "edition_ids") == ""


def test_draft_order_and_notes_only_appear_in_preview_until_published(admin_user):
    first, second = [source(fulltext=False)[1] for _ in range(2)]
    row = Topic.objects.create(name="合成主题", slug=f"notes-{uuid4()}", editorial_status="published", curation=arranged([first, second]))
    capture_topic_publication(row, actor=admin_user)
    proposed = arranged([second, first])
    proposed["association_notes"]["edition_ids"][str(second.pk)] = "尚未发布的新说明"
    row.curation = proposed
    row.save(update_fields=["curation"])
    formal = public_topic_detail(row.slug)["works"]["results"]
    assert [work["edition_id"] for work in formal] == [str(first.pk), str(second.pk)]
    assert formal[1]["curation_note"] == "版本说明 1"
    preview = preview_topic(row, request=SimpleNamespace(user=admin_user), curation_overrides={"curation": proposed})
    assert preview["works"]["results"][0]["curation_note"] == "尚未发布的新说明"
    capture_topic_publication(row, actor=admin_user)
    assert public_topic_detail(row.slug)["works"]["results"][0]["edition_id"] == str(second.pk)
    second.state = "draft"
    second.save(update_fields=["state"])
    result = public_topic_detail(row.slug)
    assert str(second.pk) not in {work["edition_id"] for work in result["works"]["results"]}
    assert "尚未发布的新说明" not in str(result)


def test_choices_bound_paging_and_never_relabel_edition_as_its_version_only(api_client, admin_user, reader_user):
    editions = [source(fulltext=False, title=f"合成书名 {index:02}")[1] for index in range(25)]
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    result = api_client.get(URL, {"field": "edition_ids", "q": "合成书名"}, **headers)
    assert result.status_code == 200 and result.data["count"] == 25 and len(result.data["results"]) == 24
    assert result.data["results"][0]["name"] == "合成书名 00"
    second = api_client.get(URL, {"field": "edition_ids", "q": "合成书名", "page": 2}, **headers)
    assert len(second.data["results"]) == 1
    assert api_client.get(URL, {"field": "edition_ids", "ids": ",".join([str(editions[0].pk)] * 201)}, **headers).status_code == 400
    assert api_client.get(URL, {"field": "edition_ids"}, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(URL, {"field": "edition_ids"}, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403


def test_private_project_choices_stay_in_current_actor_scope(api_client, admin_user, reader_user):
    private = CurationProject.objects.create(title="私人策划", owner=reader_user, visibility="team")
    issue = RecommendationIssue.objects.create(title="不可见草稿", slug=f"private-{uuid4()}", project=private)
    api_client.force_authenticate(admin_user)
    response = api_client.get(URL, {"field": "issue_ids", "ids": str(issue.pk)}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["count"] == 0
    assert "不可见草稿" not in str(response.data)
