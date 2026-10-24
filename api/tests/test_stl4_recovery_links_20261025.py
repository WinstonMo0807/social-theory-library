"""Deferred acceptance for retained catalog relations; not executed in development."""
import pytest
from rest_framework.test import APIClient
from catalog.models import Work, Edition, Person, ScholarProfile, KnowledgeNode, WorkNodeRelation, PersonNodeRelation, ReadingPath, ReadingPathItem, Contribution
from catalog.services.recycle import recycle_object


def node(index):
    return KnowledgeNode.objects.create(node_type="concept",canonical_name_zh=f"保留概念{index}",slug=f"retained-node-{index}")


def client_for(actor):
    client=APIClient();client.force_authenticate(actor);return client


@pytest.mark.django_db
def test_paged_relationships_include_recycled_targets_without_mutating_status(admin_user,reader_user):
    work=Work.objects.create(title="待恢复作品")
    targets=[node(index) for index in range(25)]
    links=[WorkNodeRelation.objects.create(work=work,node=target,status="pending") for target in targets]
    recycle_object(targets[0],actor=admin_user,kind="knowledge-node",name=targets[0].canonical_name_zh)
    recycle_object(work,actor=admin_user,kind="work",name=work.title)
    client=client_for(admin_user);url=f"/api/catalog/admin/recycle/work/{work.pk}/related/"
    relation="link:catalog.work:catalog.worknoderelation:work"
    pages=[client.get(url,{"relation":relation,"page":page}) for page in (1,2)]
    assert all(response.status_code==200 for response in pages)
    rows=[row for response in pages for row in response.data["dependencies"]]
    assert len(rows)==25 and len({row["relation_id"] for row in rows})==25
    assert {row["object_id"] for row in rows}=={str(target.pk) for target in targets}
    assert next(row for row in rows if row["object_id"]==str(targets[0].pk))["state"]=="deleted"
    assert all(row["blocking"] is False for row in rows)
    assert list(WorkNodeRelation.objects.filter(pk__in=[link.pk for link in links]).values_list("status",flat=True))==["pending"]*25
    assert client_for(reader_user).get(url).status_code==403
    assert client.get(url,{"relation":"link:reading:private_notes"}).status_code==400


@pytest.mark.django_db
def test_scholar_uses_person_identity_and_work_uses_retained_editions(admin_user):
    person=Person.objects.create(preferred_name="关联责任者")
    scholar=ScholarProfile.objects.create(person=person,slug="recovery-link-scholar")
    target=node(40)
    PersonNodeRelation.objects.create(person=person,node=target,status="pending")
    work=Work.objects.create(title="原作品")
    edition=Edition.objects.create(work=work)
    Contribution.objects.create(person=person,edition=edition,role="author")
    path=ReadingPath.objects.create(title="保留阅读路径",slug="recovery-link-path")
    material=ReadingPathItem.objects.create(reading_path=path,edition=edition,node=target,status="withdrawn")
    recycle_object(work,actor=admin_user,kind="work",name=work.title)
    client=client_for(admin_user)
    scholar_result=client.get(f"/api/catalog/admin/recycle/scholar/{scholar.pk}/related/",{"relation":"link:catalog.person:catalog.personnoderelation:person"})
    assert scholar_result.status_code==200 and scholar_result.data["dependencies"][0]["object_id"]==str(target.pk)
    url=f"/api/catalog/admin/recycle/work/{work.pk}/related/"
    authors=client.get(url,{"relation":"link:catalog.edition:catalog.contribution:edition"})
    assert authors.data["dependencies"][0]["object_id"]==str(person.pk)
    materials=client.get(url,{"relation":"link:catalog.edition:catalog.readingpathitem:edition"})
    row=materials.data["dependencies"][0]
    assert row["object_id"]==str(path.pk) and row["relation_id"]==str(material.pk)
    assert any(item["object_id"]==str(target.pk) for item in row["linked_objects"])
    material.refresh_from_db();assert material.status=="withdrawn"
