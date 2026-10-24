"""Deferred role/provenance/visibility acceptance definitions."""
from uuid import uuid4

import pytest
from django.forms.models import model_to_dict

from catalog.models import Contribution, KnowledgeNode, Person, ScholarProfile, TheoryTimelineEvent, TimelineEventRelation
from catalog.serializers import AdminTimelineEventRelationSerializer
from catalog.services.relation_editorial import TIMELINE_RELATION_FIELDS, apply_timeline_relations
from catalog.services.timeline_publication import event_projection
from .test_reading_paths_20261021 import source
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def scholar(name):
    return ScholarProfile.objects.create(person=Person.objects.create(preferred_name=name, authority_status="verified"), slug=f"participant-{uuid4()}", editorial_status="published")


def test_explicit_roles_only_on_scholar_relations_and_original_identity_survives():
    profile = scholar("合成参与者")
    event = TheoryTimelineEvent.objects.create(title="合成事件", event_type="translation")
    row = TimelineEventRelation.objects.create(event=event, scholar=profile, participant_role="translator")
    values = model_to_dict(row, fields=TIMELINE_RELATION_FIELDS)
    values["participant_role"] = "editor"
    apply_timeline_relations(event, [values])
    row.refresh_from_db()
    assert row.participant_role == "editor" and event.normalized_relations.count() == 1
    node = KnowledgeNode.objects.create(canonical_name_zh="合成概念", node_type="concept", slug=f"concept-{uuid4()}")
    incoming = AdminTimelineEventRelationSerializer(data={"node": str(node.pk), "participant_role": "translator"})
    assert not incoming.is_valid() and "participant_role" in incoming.errors


def test_formal_edition_roles_do_not_read_working_names_or_chapter_responsibility():
    profile = scholar("合成作者")
    translator = Person.objects.create(preferred_name="合成译者")
    chapter = Person.objects.create(preferred_name="合成章节作者")
    _work, edition, _asset, _revision = source(fulltext=False)
    edition.publisher = "已发布出版方"
    edition.save(update_fields=["publisher"])
    Contribution.objects.create(edition=edition, person=profile.person, role="author", approved=True)
    Contribution.objects.create(edition=edition, person=translator, role="translator", approved=True)
    Contribution.objects.create(edition=edition, person=chapter, role="author", approved=True, scope={"kind": "chapter", "chapters": []})
    activate_catalog_revision(edition, fulltext_ready=False)
    event = TheoryTimelineEvent.objects.create(title="合成译介事件", event_type="translation", subject_edition=edition, scholar=profile, review_status="approved")
    translator.preferred_name = "尚未发布改名"
    translator.save(update_fields=["preferred_name"])
    edition.publisher = "尚未发布出版方"
    edition.save(update_fields=["publisher"])
    result = event_projection(event, {})["participants"]
    assert any(row["name"] == "合成译者" and row["role"] == "translator" and row["source"] == "edition" for row in result)
    assert any(row["name"] == "已发布出版方" and row["kind"] == "publisher" and row["person_id"] is None for row in result)
    assert not any("尚未发布" in row["name"] or row["name"] == "合成章节作者" for row in result)
    assert any(row["source"] == "event" and row["role"] == "subject" for row in result)
    edition.state = "draft"
    edition.save(update_fields=["state"])
    assert not any(row["source"] == "edition" for row in event_projection(event, {})["participants"])


def test_admin_reads_approved_whole_edition_only_with_owner_guard(api_client, admin_user, reader_user):
    _work, edition, _asset, _revision = source(fulltext=False)
    people = [Person.objects.create(preferred_name=f"合成责任者{index}") for index in range(3)]
    Contribution.objects.create(edition=edition, person=people[0], role="translator", approved=True)
    Contribution.objects.create(edition=edition, person=people[1], role="author", approved=False)
    Contribution.objects.create(edition=edition, person=people[2], role="author", approved=True, scope={"kind": "chapter", "chapters": []})
    url = f"/api/catalog/admin/theory-timeline/editions/{edition.pk}/participants/"
    api_client.force_authenticate(admin_user)
    response = api_client.get(url, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["count"] == 1 and response.data["pending_count"] == 1
    assert response.data["results"][0]["role"] == "translator"
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
