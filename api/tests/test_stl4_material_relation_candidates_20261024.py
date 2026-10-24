"""Deferred original candidate pagination and edition-specific scholar scope."""
from uuid import uuid4
import pytest

from catalog.models import Asset, Contribution, Edition, TheoryReviewTask, Work
from .test_stl4_person_node_directory_20261024 import node, scholar

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/theory-system/review-tasks/"


def material(work=None):
    edition = Edition.objects.create(work=work or Work.objects.create(title="候选材料"))
    return Asset.objects.create(edition=edition, kind="normalized", sha256=uuid4().hex + uuid4().hex, status="ready", page_count=5)


def candidate(file, current, status="pending", work=None):
    return TheoryReviewTask.objects.create(task_type="work_node", work=work or file.edition.work, file=file,
        candidate_node=current, status=status, evidence_text="原识别候选摘录，尚未审核。", evidence_pages=[2])


def test_scholar_scope_is_exact_approved_edition_not_same_work_or_name(api_client, admin_user):
    person, current = scholar(), node()
    first = material()
    other_edition = material(first.edition.work)
    unrelated = material()
    Contribution.objects.create(person=person.person, edition=first.edition, role="translator", approved=True)
    Contribution.objects.create(person=person.person, edition=first.edition, role="editor", approved=True)
    unapproved = Contribution.objects.create(person=person.person, edition=unrelated.edition, role="author", approved=False)
    expected = candidate(first, current)
    candidate(other_edition, current)
    candidate(unrelated, current)
    candidate(first, current, work=unrelated.edition.work)
    api_client.force_authenticate(admin_user)
    result = api_client.get(URL, {"scholar":person.pk,"review_only":"true","page_size":6})
    assert result.status_code == 200 and result.data["count"] == 1
    assert result.data["results"][0]["id"] == str(expected.pk)
    unapproved.approved = True
    unapproved.save(update_fields=["approved"])
    assert api_client.get(URL, {"scholar":person.pk,"review_only":"true"}).data["count"] == 2
    Contribution.objects.filter(person=person.person).update(approved=False)
    assert api_client.get(URL, {"scholar":person.pk}).data["count"] == 0


def test_review_states_pagination_input_and_reader_boundary(api_client, admin_user, reader_user):
    current, file = node(), material()
    for state in ("pending", "needs_changes", "deferred", "insufficient_evidence", "confirmed", "rejected"):
        candidate(file, current, status=state)
    for _ in range(3):
        candidate(file, current)
    candidate(file, node())
    api_client.force_authenticate(admin_user)
    params = {"candidate_node":current.pk,"review_only":"true","page_size":6}
    first, second = api_client.get(URL,params).data, api_client.get(URL,{**params,"page":2}).data
    assert first["count"] == second["count"] == 7 and len(first["results"]) == 6 and len(second["results"]) == 1
    assert not {row["id"] for row in first["results"]} & {row["id"] for row in second["results"]}
    for bad in ({"candidate_node":"invalid"},{"scholar":"invalid"},{"review_only":"invalid"},{"page_size":25},{"page_size":0}):
        assert api_client.get(URL,bad).status_code == 400
    api_client.force_authenticate(reader_user)
    assert api_client.get(URL,params).status_code == 403
