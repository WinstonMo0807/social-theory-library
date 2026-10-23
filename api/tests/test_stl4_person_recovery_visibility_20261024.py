"""Deferred acceptance: parent recovery never reactivates an old public profile."""
import pytest

from catalog.models import EditorialRevision, Person, RecycleEntry, ScholarProfile
from catalog.recycle_workspace import detail
from catalog.services.recycle import recycle_object, restore_object
from catalog.services.scoped_search import public_scholar_queryset


@pytest.mark.django_db
@pytest.mark.parametrize("legacy", [False, True])
def test_person_restore_retains_identity_and_withdraws_previous_public_profile(admin_user, legacy):
    person = Person.objects.create(preferred_name="恢复人物", authority_status="verified")
    profile = ScholarProfile.objects.create(person=person, slug="recovery-person", editorial_status="published")
    if legacy:
        entry = RecycleEntry.objects.create(model_label="catalog.person", object_id=person.pk,
            kind="person", name=person.preferred_name, deleted_by=admin_user)
        preview = detail("person", person.pk, admin_user)
        assert preview["can_restore"] and "旧公开学者页将一并撤下" in preview["notice"]
    else:
        entry = recycle_object(person, actor=admin_user, kind="person", name=person.preferred_name)
    restore_object(entry.pk, actor=admin_user)
    profile.refresh_from_db()
    person.refresh_from_db()
    assert person.authority_status == "verified"
    assert profile.person_id == person.pk and profile.editorial_status == "archived"
    assert not public_scholar_queryset().filter(pk=profile.pk).exists()
    assert EditorialRevision.objects.filter(target_type="scholar_profile", target_id=profile.pk,
        patch={"editorial_status": "archived"}, status="published").exists()
    assert RecycleEntry.objects.get(pk=entry.pk).restored_at is not None
