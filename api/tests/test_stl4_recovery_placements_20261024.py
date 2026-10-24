"""Deferred recovery references: exact identities, original revisions, project privacy."""
from uuid import uuid4
import pytest
from catalog.models import Work,Edition,RecycleEntry,CurationProject,RecommendationIssue
from catalog.services import content_placements as placements,editorial_issues as ledger
from .test_stl4_person_node_directory_20261024 import node

pytestmark=pytest.mark.django_db


def save(parent,target,actor,kind="node"):
    return ledger._save_revision(placements.KIND,placements.target_id(kind,parent.pk),
        {"page_type":kind,"page_id":str(parent.pk),"items":[{"id":str(uuid4()),"target":target,"area":"materials","group":"引用"}]},actor)


def url(kind,source):
    return f"/api/catalog/admin/recycle/{kind}/{source.pk}/related/?relation=placements"


def test_recycled_work_finds_exact_edition_and_current_published_json_uses(api_client,admin_user):
    work=Work.objects.create(title="回收作品的真实引用")
    edition=Edition.objects.create(work=work,version_label="原版本")
    peer=Work.objects.create(id=edition.pk,title="跨表同编号不同作品")
    parent=node()
    published=save(parent,{"type":"edition","id":str(edition.pk),"edition_id":str(edition.pk)},admin_user)
    ledger._publish_revision(published,admin_user)
    latest=ledger._save_revision(placements.KIND,placements.target_id("node",parent.pk),
        {"page_type":"node","page_id":str(parent.pk),"items":[]},admin_user)
    RecycleEntry.objects.create(model_label="catalog.work",object_id=work.pk,kind="work",name=work.title,deleted_by=admin_user)
    api_client.force_authenticate(admin_user)
    response=api_client.get(url("work",work))
    assert response.status_code==200 and response.data["count"]==1
    row=response.data["dependencies"][0]
    assert row["object_id"]==str(parent.pk) and str(published.pk) in row["destination"] and "公开修订" in row["detail"]
    assert api_client.get(url("work",peer)).data["count"]==0
    assert api_client.get(url("edition",edition)).data["count"]==1
    ledger._publish_revision(latest,admin_user)
    assert api_client.get(url("work",work)).data["count"]==0
    save(parent,{"type":"work","id":str(work.pk),"edition_id":str(edition.pk)},admin_user)
    assert api_client.get(url("edition",edition)).data["count"]==1
    assert RecycleEntry.objects.get(model_label="catalog.work",object_id=work.pk).restored_at is None


def test_recycled_reference_parent_is_visible_but_private_project_counts_are_filtered(api_client,admin_user,reader_user):
    source=node();parent=node()
    save(parent,{"type":"node","id":str(source.pk)},admin_user)
    RecycleEntry.objects.create(model_label="catalog.knowledgenode",object_id=parent.pk,kind="knowledge-node",name=parent.canonical_name_zh,deleted_by=admin_user)
    project=CurationProject.objects.create(title="不可外显的项目",owner=reader_user,visibility="team")
    issue=RecommendationIssue.objects.create(title="不可外显的文章",slug=f"hidden-{uuid4()}",project=project)
    save(issue,{"type":"node","id":str(source.pk)},admin_user,kind="issue")
    api_client.force_authenticate(admin_user)
    response=api_client.get(url("knowledge-node",source))
    assert response.status_code==200 and response.data["count"]==1
    assert response.data["dependencies"][0]["state"]=="deleted"
    assert str(issue.pk) not in str(response.data) and issue.title not in str(response.data)
    project.collaborators.add(admin_user)
    assert api_client.get(url("knowledge-node",source)).data["count"]==2
    project.collaborators.remove(admin_user)
    assert api_client.get(url("knowledge-node",source)).data["count"]==1
    api_client.force_authenticate(reader_user)
    assert api_client.get(url("knowledge-node",source)).status_code==403
