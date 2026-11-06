from uuid import uuid4
import pytest
from catalog.models import Person, ScholarProfile
from catalog.services.recycle import recycle_object
from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision, EditorialRevisionError

pytestmark = pytest.mark.django_db


def test_legacy_unicode_url_can_be_withdrawn_without_changing_identity(admin_user):
    person = Person.objects.create(preferred_name="示例学者")
    profile = ScholarProfile.objects.create(person=person, slug="示例学者", editorial_status="published")
    recycle_object(profile, actor=admin_user, kind="scholar", name="示例学者")
    assert not ScholarProfile.objects.filter(pk=profile.pk).exists()
    profile = ScholarProfile.all_objects.get(pk=profile.pk)
    assert profile.slug == "示例学者" and profile.person_id == person.pk
    assert profile.editorial_status == "archived"


def test_withdrawal_with_content_edits_still_validates_the_url(admin_user):
    profile = ScholarProfile.objects.create(person=Person.objects.create(preferred_name="另一示例"), slug="原网址", editorial_status="published")
    revision = create_editorial_revision(target_type="scholar_profile", target_id=profile.pk,
        patch={"editorial_status":"archived", "short_description":"改动内容"}, actor=admin_user, idempotency_key=str(uuid4()))
    with pytest.raises(EditorialRevisionError, match="slug"):
        publish_editorial_revision(revision.pk, actor=admin_user)
    profile.refresh_from_db()
    assert profile.editorial_status == "published" and profile.short_description == ""
