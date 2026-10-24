"""Deferred acceptance: legacy recovery must not reactivate catalog publication."""
import pytest
from rest_framework.exceptions import PermissionDenied
from accounts.models import User
from catalog.models import Work,Edition,RecycleEntry,CatalogPublicationRevision,PublicationEvent,Topic
from catalog.recycle_workspace import detail
from catalog.services.publication_eligibility import public_editions
from catalog.services.recycle import restore_object


@pytest.mark.django_db
@pytest.mark.parametrize("kind",["work","edition"])
def test_legacy_restore_withdraws_public_edition_using_original_ledger(admin_user,kind):
    work=Work.objects.create(title="历史回收作品")
    edition=Edition.objects.create(work=work,state="published")
    revision=CatalogPublicationRevision.objects.create(edition=edition,revision=1,status="active",metadata_ready=True,
        snapshot={"work":{"title":work.title}},content_fingerprint="0"*64)
    edition.active_catalog_revision=revision;edition.save(update_fields=["active_catalog_revision","updated_at"])
    obj=work if kind=="work" else edition
    entry=RecycleEntry.objects.create(model_label=obj._meta.label_lower,object_id=obj.pk,kind=kind,name=work.title,deleted_by=admin_user)
    assert not public_editions().filter(pk=edition.pk).exists()
    preview=detail(kind,obj.pk,admin_user,check_files=True)
    assert preview["can_restore"] and "旧公开版本" in preview["notice"]
    restore_object(entry.pk,actor=admin_user)
    edition.refresh_from_db();revision.refresh_from_db()
    assert edition.state!="published" and not public_editions().filter(pk=edition.pk).exists()
    assert PublicationEvent.objects.filter(edition=edition,event_type="withdraw").count()==1
    assert revision.snapshot=={"work":{"title":work.title}}
    assert Work.objects.filter(pk=work.pk).exists() and Edition.objects.filter(pk=edition.pk).exists()


@pytest.mark.django_db
def test_missing_withdraw_permission_rolls_back_recovery(admin_user):
    actor=User.objects.create_user(username="recovery-without-withdraw",role="editor")
    work=Work.objects.create(title="需下架权限")
    edition=Edition.objects.create(work=work,state="published")
    entry=RecycleEntry.objects.create(model_label="catalog.work",object_id=work.pk,kind="work",name=work.title,deleted_by=admin_user)
    assert not detail("work",work.pk,actor)["can_restore"]
    with pytest.raises(PermissionDenied):restore_object(entry.pk,actor=actor)
    entry.refresh_from_db();edition.refresh_from_db()
    assert entry.restored_at is None and edition.state=="published"
    assert not PublicationEvent.objects.filter(edition=edition,event_type="withdraw").exists()


@pytest.mark.django_db
def test_cross_model_same_uuid_is_not_a_deleted_parent(admin_user):
    work=Work.objects.create(title="父作品仍正常")
    edition=Edition.objects.create(work=work)
    topic=Topic.objects.create(id=work.pk,name="同编号主题",slug="same-uuid-recycled-topic")
    RecycleEntry.objects.create(model_label="catalog.topic",object_id=topic.pk,kind="topic",name=topic.name,deleted_by=admin_user)
    entry=RecycleEntry.objects.create(model_label="catalog.edition",object_id=edition.pk,kind="edition",name=work.title,deleted_by=admin_user)
    restored=restore_object(entry.pk,actor=admin_user)
    assert restored.pk==edition.pk and RecycleEntry.objects.get(pk=entry.pk).restored_at is not None
    assert RecycleEntry.objects.get(model_label="catalog.topic",object_id=topic.pk).restored_at is None
