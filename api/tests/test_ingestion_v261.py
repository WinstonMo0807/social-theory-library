from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from catalog.models import Discipline, Edition, Subdiscipline, TheorySchool, Topic, Work
from ingestion.models import UploadItem
from ingestion.services.metadata import search_google_books_title
from ingestion.services.taxonomy import controlled_vocabulary_candidates


@pytest.mark.django_db
def test_controlled_vocabulary_candidates_cover_all_review_taxonomies():
    discipline = Discipline.objects.create(
        name="平台社会研究学科261",
        slug="platform-society-studies-v261",
        code="platform-society-studies-v261",
        foreign_name="Platform Society Studies V261",
        editorial_status="published",
    )
    Subdiscipline.objects.create(
        name="平台政治子学科261",
        slug="platform-political-subfield-v261",
        discipline=discipline,
        foreign_name="Platform Political Subfield V261",
        editorial_status="published",
    )
    TheorySchool.objects.create(
        name="平台批判理论261",
        slug="platform-critical-theory-v261",
        foreign_name="Platform Critical Theory V261",
        editorial_status="published",
    )
    Topic.objects.create(
        name="平台与社会主题261",
        slug="platform-and-society-v261",
        editorial_status="published",
    )

    candidates = controlled_vocabulary_candidates(
        "本书属于平台政治子学科261，讨论平台批判理论261及平台与社会主题261。Platform Society Studies V261 提供主要学科背景。"
    )
    grouped = {(candidate.field_name, candidate.value): candidate for candidate in candidates}

    for field, value in (
        ("disciplines", "平台社会研究学科261"),
        ("subdisciplines", "平台政治子学科261"),
        ("theory_schools", "平台批判理论261"),
        ("topics", "平台与社会主题261"),
    ):
        candidate = grouped[(field, value)]
        assert candidate.source == "controlled_vocabulary_match_v1"
        assert candidate.evidence["entity_id"]
        assert candidate.evidence["evidence_text"]
        assert candidate.confidence >= 0.76


@pytest.mark.django_db
def test_controlled_vocabulary_candidates_do_not_create_unknown_authorities():
    before = (
        Discipline.objects.count(),
        Subdiscipline.objects.count(),
        TheorySchool.objects.count(),
        Topic.objects.count(),
    )

    assert controlled_vocabulary_candidates("这是一个尚未进入馆内词表的新理论名称。") == []
    assert before == (
        Discipline.objects.count(),
        Subdiscipline.objects.count(),
        TheorySchool.objects.count(),
        Topic.objects.count(),
    )


def test_google_books_title_candidates_keep_source_record_and_mixed_metadata(settings):
    settings.GOOGLE_BOOKS_API_KEY = ""
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "items": [
            {
                "id": "volume-1",
                "volumeInfo": {
                    "title": "弱者的武器",
                    "authors": ["詹姆斯·斯科特", "James C. Scott"],
                    "publisher": "译林出版社",
                    "publishedDate": "2011-06",
                    "language": "zh",
                    "industryIdentifiers": [
                        {"type": "ISBN_13", "identifier": "9787544717250"},
                    ],
                },
            }
        ]
    }

    with patch("ingestion.services.metadata.httpx.get", return_value=response) as request:
        candidates = search_google_books_title("弱者的武器", language="zh-CN")

    assert request.call_args.kwargs["params"]["q"] == 'intitle:"弱者的武器"'
    assert request.call_args.kwargs["params"]["langRestrict"] == "zh"
    values = {(candidate.field_name, str(candidate.value)) for candidate in candidates}
    assert ("publisher", "译林出版社") in values
    assert ("publication_year", "2011") in values
    assert ("isbn", "9787544717250") in values
    title = next(candidate for candidate in candidates if candidate.field_name == "title")
    assert title.confidence >= 0.9
    assert title.evidence["record_url"] == "https://books.google.com/books?id=volume-1"


@pytest.mark.django_db
def test_regular_admin_and_superuser_share_the_ingestion_review_preflight_flow(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    settings.CELERY_TASK_ALWAYS_EAGER = False
    owner = User.objects.create_superuser(
        username="owner@example.org",
        email="owner@example.org",
        password="Owner-Secure-Password-2026",
        display_name="最高管理员",
    )
    results = []

    for index, user in enumerate((owner, admin_user), start=1):
        api_client.force_authenticate(user)
        batch = api_client.post(
            "/api/ingestion/batches/create/",
            {"expected_count": 1},
            format="json",
        )
        assert batch.status_code == 201
        with patch("ingestion.services.dispatch.dispatch_upload_item"):
            uploaded = api_client.post(
                f"/api/ingestion/batches/{batch.data['id']}/items/",
                {
                    "client_token": f"admin-parity-{index}-2026",
                    "file": SimpleUploadedFile(
                        f"admin-parity-{index}.pdf",
                        b"%PDF-1.4\n%%EOF",
                        content_type="application/pdf",
                    ),
                },
                format="multipart",
            )
        assert uploaded.status_code == 202
        item = UploadItem.objects.get(pk=uploaded.data["item"]["id"])
        work = Work.objects.create(title=f"管理员连续入库测试 {index}", document_type="book")
        edition = Edition.objects.create(work=work, publisher="测试出版社")
        item.edition = edition
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.stage_progress = 88
        item.save(update_fields=["edition", "status", "stage_progress", "updated_at"])

        detail = api_client.get(f"/api/ingestion/items/{item.id}/")
        assert detail.status_code == 200
        assert detail.data["can_manage_publication"] is True

        reviewed = api_client.put(
            f"/api/ingestion/items/{item.id}/review/",
            {
                "title": f"管理员确认题名 {index}",
                "document_type": "book",
                "language": "zh-CN",
                "publisher": "测试出版社",
                "publication_place": "北京",
                "publication_year": 2026,
                "authors": ["测试作者"],
                "retry_publication": False,
            },
            format="json",
        )
        assert reviewed.status_code == 200
        assert reviewed.data["status"] == UploadItem.Status.READY

        with patch("ingestion.views.refresh_remote_candidates", return_value=([], [])):
            suggestions = api_client.post(
                f"/api/ingestion/items/{item.id}/metadata-suggestions/",
                {},
                format="json",
            )
        preflight = api_client.get(f"/api/ingestion/items/{item.id}/publish/")
        results.append(
            (
                batch.status_code,
                uploaded.status_code,
                reviewed.status_code,
                suggestions.status_code,
                preflight.status_code,
                reviewed.data["can_manage_publication"],
            )
        )

    assert owner.is_superuser is True
    assert admin_user.is_superuser is False
    assert admin_user.role == User.Role.ADMIN
    assert results[0] == results[1] == (201, 202, 200, 200, 200, True)
