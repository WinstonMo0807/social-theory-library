import json

from django.core.files.uploadedfile import SimpleUploadedFile
import pytest

from accounts.models import User
from catalog.models import DocumentType, Edition, Work
from ingestion.models import AuditEvent, MetadataCandidate, SourceRecord, UploadBatch, UploadItem
from ingestion.services.metadata_import_formats import parse_metadata_import


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("filename", "payload", "expected_format", "expected_title"),
    [
        (
            "record.ris",
            b"TY  - BOOK\nTI  - The Sociological Imagination\nAU  - Mills, C. Wright\nPY  - 1959\nER  -\n",
            "ris",
            "The Sociological Imagination",
        ),
        (
            "record.bib",
            b"@book{mills1959, title={The Sociological Imagination}, author={Mills, C. Wright}, year={1959}}",
            "bibtex",
            "The Sociological Imagination",
        ),
        (
            "record.json",
            json.dumps(
                {
                    "id": "mills1959",
                    "type": "book",
                    "title": "The Sociological Imagination",
                    "author": [{"family": "Mills", "given": "C. Wright"}],
                    "issued": {"date-parts": [[1959]]},
                }
            ).encode(),
            "csl_json",
            "The Sociological Imagination",
        ),
        (
            "record.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "title": "社会学的想象力",
                    "authors": ["C. 赖特·米尔斯"],
                    "publication_year": 1959,
                },
                ensure_ascii=False,
            ).encode(),
            "sidecar_json",
            "社会学的想象力",
        ),
        (
            "record.yaml",
            "schema_version: 1\ntitle: 社会学的想象力\nauthors:\n  - C. 赖特·米尔斯\npublication_year: 1959\n".encode("utf-8"),
            "sidecar_yaml",
            "社会学的想象力",
        ),
    ],
)
def test_supported_metadata_formats_are_parsed_as_one_record(
    filename,
    payload,
    expected_format,
    expected_title,
):
    parsed = parse_metadata_import(payload, filename=filename)
    assert parsed.format == expected_format
    assert parsed.fields["title"] == expected_title
    assert parsed.fields["publication_year"] == 1959


def make_item(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="原题名")
    edition = Edition.objects.create(work=work, publisher="原出版社")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="source.pdf",
    )


def make_editor():
    return User.objects.create_user(
        username="importer@example.org",
        email="importer@example.org",
        role=User.Role.EDITOR,
        password="Importer-Secure-2026",
    )


def test_import_endpoint_creates_review_candidates_and_is_idempotent(
    api_client,
    admin_user,
):
    item = make_item(admin_user)
    api_client.force_authenticate(make_editor())
    content = (
        "TY  - BOOK\n"
        "TI  - 社会学的想象力\n"
        "AU  - C. 赖特·米尔斯\n"
        "PB  - 生活·读书·新知三联书店\n"
        "PY  - 2016\n"
        "SN  - 9787108057259\n"
        "ER  -\n"
    ).encode("utf-8")
    url = f"/api/ingestion/items/{item.id}/metadata-import/"

    first = api_client.post(
        url,
        {"file": SimpleUploadedFile("book.ris", content, content_type="application/x-research-info-systems")},
        format="multipart",
    )

    assert first.status_code == 201
    assert first.data["format"] == "ris"
    assert first.data["reused_source"] is False
    assert first.data["stats"]["added"] >= 5
    assert all(candidate["lifecycle"] == MetadataCandidate.Lifecycle.PROPOSED for candidate in first.data["candidates"])
    assert all(candidate["selected"] is False for candidate in first.data["candidates"])
    item.edition.work.refresh_from_db()
    item.edition.refresh_from_db()
    assert item.edition.work.title == "原题名"
    assert item.edition.publisher == "原出版社"
    assert SourceRecord.objects.filter(upload_item=item, provider="file_import:ris").count() == 1
    assert AuditEvent.objects.filter(action="metadata_file_import", object_id=str(item.id)).count() == 1

    repeated = api_client.post(
        url,
        {"file": SimpleUploadedFile("book.ris", content)},
        format="multipart",
    )
    assert repeated.status_code == 200
    assert repeated.data["reused_source"] is True
    assert repeated.data["stats"]["added"] == 0
    assert SourceRecord.objects.filter(upload_item=item, provider="file_import:ris").count() == 1


def test_import_accepts_safe_yaml_as_review_candidates(api_client, admin_user):
    item = make_item(admin_user)
    api_client.force_authenticate(make_editor())
    response = api_client.post(
        f"/api/ingestion/items/{item.id}/metadata-import/",
        {
            "file": SimpleUploadedFile(
                "book.yaml",
                "title: 中国社会学史\nauthors:\n  - 李明\npublication_year: 2020\n".encode("utf-8"),
            ),
            "format": "yaml",
        },
        format="multipart",
    )
    assert response.status_code == 201
    assert response.data["format"] == "sidecar_yaml"
    assert SourceRecord.objects.filter(upload_item=item, provider="file_import:sidecar_yaml").exists()
    assert item.metadata_candidates.filter(field_name="title", value="中国社会学史").exists()


def test_import_rejects_unsafe_yaml_python_tag(api_client, admin_user):
    item = make_item(admin_user)
    api_client.force_authenticate(make_editor())
    response = api_client.post(
        f"/api/ingestion/items/{item.id}/metadata-import/",
        {
            "file": SimpleUploadedFile(
                "book.yaml",
                b"!!python/object/apply:os.system ['echo unsafe']",
            ),
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert response.data["code"] == "invalid_yaml"
    assert not SourceRecord.objects.filter(upload_item=item).exists()


def test_reviewer_cannot_import_catalog_metadata(api_client, admin_user):
    item = make_item(admin_user)
    reviewer = User.objects.create_user(
        username="metadata-reviewer@example.org",
        email="metadata-reviewer@example.org",
        role=User.Role.REVIEWER,
        password="Reviewer-Secure-2026",
    )
    api_client.force_authenticate(reviewer)
    response = api_client.post(
        f"/api/ingestion/items/{item.id}/metadata-import/",
        {"file": SimpleUploadedFile("book.json", b'{"title":"example"}')},
        format="multipart",
    )
    assert response.status_code == 403
    assert not SourceRecord.objects.filter(upload_item=item).exists()
