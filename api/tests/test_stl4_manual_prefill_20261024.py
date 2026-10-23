"""Deferred acceptance for material-first prefill. Not run during development."""
from uuid import uuid4
from django.core import signing
import pytest
from catalog.manual_catalog_candidates import SALT
from catalog.models import Work, Edition, Person, CatalogFieldDecision
from ingestion.models import MetadataCandidate, SourceRecord

pytestmark = pytest.mark.django_db
PATH = "/api/catalog/admin/manual-catalog/"


def body(actor, fields=None):
    source = SourceRecord.objects.create(provider="crossref", operation="whole_record_doi", status="succeeded")
    values = fields or {"title": "来源题名", "publisher": "来源出版社"}
    token = signing.dumps({"owner_id": str(actor.pk), "source": "crossref", "source_label": "Crossref DOI记录", "fields": values,
        "evidence": [{"source_record_id": str(source.pk), "doi": "10.1234/example"}], "source_url": "https://doi.org/10.1234/example"}, salt=SALT)
    return {"request_id": str(uuid4()), "mode": "new_work", "acknowledge_similar": True,
        "form": {"work": {"title": "人工核对后的题名", "document_type": "book", "language": "zh-CN", "subtitle": "", "abstract": ""},
                 "bibliography": {"publisher": "来源出版社"}, "contributors": []},
        "prefills": [{"token": token, "fields": list(values)}]}


def authenticate(client, actor):
    client.force_authenticate(actor); client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))


def test_prefill_records_source_and_manual_change_once(api_client, admin_user):
    authenticate(api_client, admin_user); payload = body(admin_user)
    response = api_client.post(PATH, payload, format="json")
    assert response.status_code == 200, response.data
    edition = Edition.objects.get(pk=response.data["edition_id"])
    decisions = {row.field_name: row for row in CatalogFieldDecision.objects.filter(edition=edition)}
    assert decisions["title"].provenance["outcome"] == "used_after_edit"
    assert decisions["publisher"].provenance["outcome"] == "used_unchanged"
    assert decisions["title"].status == "needs_review"
    assert MetadataCandidate.objects.filter(cataloging_session_id=response.data["session_id"], source_record__isnull=False).count() == 2
    assert api_client.post(PATH, payload, format="json").data == response.data
    assert MetadataCandidate.objects.filter(cataloging_session_id=response.data["session_id"]).count() == 2


def test_other_owner_or_tampered_source_cannot_create(api_client, admin_user, reader_user):
    authenticate(api_client, admin_user); payload = body(reader_user)
    initial = Work.objects.count()
    assert api_client.post(PATH, payload, format="json").status_code == 403
    payload["prefills"][0]["token"] += "broken"
    assert api_client.post(PATH, payload, format="json").status_code == 400
    assert Work.objects.count() == initial


def test_duplicate_source_fields_roll_back_new_book(api_client, admin_user):
    authenticate(api_client, admin_user); payload = body(admin_user)
    payload["prefills"] *= 2
    initial = Work.objects.count()
    assert api_client.post(PATH, payload, format="json").status_code == 400
    assert Work.objects.count() == initial


def test_author_prefill_never_establishes_an_identity(api_client, admin_user):
    authenticate(api_client, admin_user); payload = body(admin_user, {"authors": ["尚未核对的人物"]})
    payload["form"]["contributors"] = [{"name": "尚未核对的人物", "role": "author", "create_new": False}]
    assert api_client.post(PATH, payload, format="json").status_code == 400
    assert not Person.objects.filter(preferred_name="尚未核对的人物").exists()


def test_missing_source_can_be_removed_without_losing_manual_input(api_client, admin_user):
    authenticate(api_client, admin_user); payload = body(admin_user)
    SourceRecord.objects.filter(provider="crossref").delete()
    initial = Work.objects.count()
    assert api_client.post(PATH, payload, format="json").status_code == 400
    assert Work.objects.count() == initial
    payload["request_id"] = str(uuid4()); payload["prefills"] = []
    response = api_client.post(PATH, payload, format="json")
    assert response.status_code == 200, response.data
    assert response.data["form"]["work"]["title"] == "人工核对后的题名"
