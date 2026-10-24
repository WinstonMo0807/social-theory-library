"""Deferred source-use scope, current revisions and private project boundaries."""
from uuid import uuid4
import pytest
from catalog.models import CurationProject, RecommendationIssue
from catalog.services import content_placements as placements, editorial_issues as ledger
from .test_stl4_person_node_directory_20261024 import node, scholar

pytestmark = pytest.mark.django_db


def saved(kind, parent, source, actor, source_type="node", items=None):
    payload={"page_type":kind,"page_id":str(parent.pk),"items":items if items is not None else [{"id":str(uuid4()),
        "target":{"type":source_type,"id":str(source.pk)},"area":"materials","group":"核对分组"}]}
    return ledger._save_revision(placements.KIND, placements.target_id(kind,parent.pk), payload, actor)


def url(source, kind="node"):
    return f"/api/catalog/admin/content-placements/uses/{kind}/{source.pk}/"


def test_saved_removal_does_not_hide_original_published_reference(api_client, admin_user):
    source, page = node(), node()
    published=saved("node",page,source,admin_user)
    ledger._publish_revision(published,admin_user)
    draft=saved("node",page,source,admin_user,items=[])
    api_client.force_authenticate(admin_user)
    result=api_client.get(url(source)).data
    assert result["count"] == 1 and result["results"][0]["revision_id"] == str(published.pk)
    assert result["results"][0]["is_published"] and not result["results"][0]["is_latest"]
    assert f"revision={published.pk}" in result["results"][0]["edit_url"]
    ledger._publish_revision(draft,admin_user)
    assert api_client.get(url(source)).data["count"] == 0
    current=saved("node",page,source,admin_user)
    result=api_client.get(url(source)).data
    assert result["count"] == 1 and result["results"][0]["revision_id"] == str(current.pk)
    assert not result["results"][0]["is_published"]


def test_private_projects_are_filtered_before_counts_and_only_authorized_readers_may_enter(api_client, admin_user, reader_user):
    source=node()
    project=CurationProject.objects.create(title="不可泄露的团队项目",owner=reader_user,visibility="team")
    hidden=RecommendationIssue.objects.create(title="私人文章",slug=f"private-{uuid4()}",project=project)
    visible=RecommendationIssue.objects.create(title="无私有项目的文章",slug=f"visible-{uuid4()}")
    saved("issue",hidden,source,admin_user)
    saved("issue",visible,source,admin_user)
    api_client.force_authenticate(admin_user)
    result=api_client.get(url(source))
    assert result.status_code == 200 and result.data["count"] == 1
    assert result.data["results"][0]["page_id"] == str(visible.pk)
    assert "私人文章" not in str(result.data) and str(hidden.pk) not in str(result.data)
    assert api_client.post(url(source),{},format="json").status_code == 405
    project.collaborators.add(admin_user)
    assert api_client.get(url(source)).data["count"] == 2
    project.collaborators.remove(admin_user)
    assert api_client.get(url(source)).data["count"] == 1
    api_client.force_authenticate(reader_user)
    assert api_client.get(url(source)).status_code == 403


def test_source_kind_and_revision_pagination_keep_exact_identity(api_client, admin_user):
    source=scholar()
    for _ in range(13):
        saved("node",node(),source,admin_user,source_type="scholar")
    api_client.force_authenticate(admin_user)
    first=api_client.get(url(source,"scholar")).data
    second=api_client.get(url(source,"scholar"),{"page":2}).data
    assert first["count"] == second["count"] == 13 and len(first["results"]) == 12 and len(second["results"]) == 1
    assert not ({row["revision_id"] for row in first["results"]} & {row["revision_id"] for row in second["results"]})
    assert api_client.get(url(source,"scholar"),{"page":3}).status_code == 404
    assert api_client.get(url(source,"issue")).status_code == 400
