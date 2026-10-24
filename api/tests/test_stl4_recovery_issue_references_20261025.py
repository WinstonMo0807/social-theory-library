"""Deferred structured-body reference acceptance; no development execution."""
from uuid import uuid4
import pytest
from rest_framework.test import APIClient
from catalog.models import Work,Edition,Person,ScholarProfile,EditorialRevision,RecommendationIssue,CurationProject,RecycleEntry
from catalog.services import editorial_issues as ledger

pytestmark=pytest.mark.django_db


def save(issue,actor,blocks=None,items=None):
    return ledger._save_revision("recommendation_issue",issue.pk,{"body_blocks":blocks or [],"items":items or []},actor)


def get(actor,kind,obj):
    client=APIClient();client.force_authenticate(actor)
    return client.get(f"/api/catalog/admin/recycle/{kind}/{obj.pk}/related/",{"relation":"issue-references"})


def test_latest_active_and_scheduled_preserve_distinct_references(admin_user):
    work=Work.objects.create(title="正文中的独立作品");edition=Edition.objects.create(work=work)
    other=Work.objects.create(id=edition.pk,title="同编号的另一作品")
    issue=RecommendationIssue.objects.create(title="编辑策划",slug=f"issue-{uuid4()}")
    active=save(issue,admin_user,[{"type":"work","target":{"type":"work","id":str(work.pk),"edition_id":str(edition.pk)}}])
    ledger._publish_revision(active,admin_user)
    scheduled=save(issue,admin_user,items=[{"work_id":str(work.pk),"edition_id":str(edition.pk)}])
    ledger._publish_revision(scheduled,admin_user)
    latest=save(issue,admin_user)
    issue.active_revision=active;issue.scheduled_revision=scheduled;issue.save()
    RecycleEntry.objects.create(kind="work",model_label="catalog.work",object_id=work.pk,name=work.title,deleted_by=admin_user)
    response=get(admin_user,"work",work)
    assert response.status_code==200 and response.data["count"]==2
    assert {row["relation_id"] for row in response.data["dependencies"]}=={str(active.pk),str(scheduled.pk)}
    assert get(admin_user,"edition",edition).data["count"]==2
    assert get(admin_user,"work",other).data["count"]==0
    issue.active_revision=latest;issue.scheduled_revision=None;issue.save()
    assert get(admin_user,"work",work).data["count"]==0


def test_analysis_and_comparison_person_references_and_project_visibility(admin_user,reader_user):
    person=Person.objects.create(preferred_name="仅按身份引用")
    scholar=ScholarProfile.objects.create(person=person,slug=f"profile-{uuid4()}")
    project=CurationProject.objects.create(title="私人项目",owner=reader_user,visibility="team")
    issue=RecommendationIssue.objects.create(title="私人策划正文",slug=f"private-{uuid4()}",project=project)
    save(issue,admin_user,[{"type":"comparison","rows":[{"person_id":str(person.pk),"cells":[]}]}])
    assert get(admin_user,"person",person).data["count"]==0
    project.collaborators.add(admin_user)
    assert get(admin_user,"person",person).data["count"]==1
    assert get(admin_user,"scholar",scholar).data["count"]==1
    assert "私人策划正文" in str(get(admin_user,"person",person).data)
    save(issue,admin_user,[{"type":"analysis","references":[{"type":"person","id":person.pk.hex}]}])
    assert get(admin_user,"person",person).data["count"]==1
    project.collaborators.remove(admin_user)
    response=get(admin_user,"person",person)
    assert response.data["count"]==0 and str(issue.pk) not in str(response.data) and issue.title not in str(response.data)
    assert get(reader_user,"person",person).status_code==403


def test_malformed_and_prose_uuid_are_not_structured_references(admin_user):
    work=Work.objects.create(title="不能通过全文猜引用")
    issue=RecommendationIssue.objects.create(title="历史异常结构",slug=f"malformed-{uuid4()}")
    revision=save(issue,admin_user)
    for data in ({"body_blocks":[None,"bad",{"type":"paragraph","text":str(work.pk),"target":{"type":"work","id":str(work.pk)}}]},
                 {"body_blocks":{"target":{"type":"work","id":str(work.pk)}}},
                 {"body_blocks":[{"type":"comparison","rows":[None,{"cells":"invalid"}]}]},
                 {"items":[None,"bad"]}):
        EditorialRevision.objects.filter(pk=revision.pk).update(materialized_preview=data)
        response=get(admin_user,"work",work)
        assert response.status_code==200 and response.data["count"]==0
