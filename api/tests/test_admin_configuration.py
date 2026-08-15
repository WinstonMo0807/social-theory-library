import pytest
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from unittest.mock import patch

from accounts.models import User
from catalog.models import Asset, Edition, PublicationState, Topic, Work
from distribution.models import CloudProvider
from ingestion.models import AuditEvent, UploadBatch, UploadItem
from distribution.services import cloud_budget_allows_new_publication, signed_read_url
from reading.models import ReadingHistory


def test_signed_download_url_uses_attachment_filename(monkeypatch):
    captured = {}

    class FakeClient:
        def generate_presigned_url(self, operation, **kwargs):
            captured["operation"] = operation
            captured.update(kwargs)
            return "https://objects.example.org/signed"

    class FakeCloudObject:
        status = "ready"
        provider = type("Provider", (), {"bucket": "library"})()
        object_key = "published/example.pdf"

    monkeypatch.setattr("distribution.services.s3_client", lambda provider: FakeClient())
    url = signed_read_url(
        FakeCloudObject(),
        expires_in=900,
        download_filename="测试著作.pdf",
        attachment=True,
    )
    assert url.endswith("/signed")
    assert captured["operation"] == "get_object"
    assert captured["Params"]["ResponseContentDisposition"].startswith("attachment;")
    assert "%E6%B5%8B%E8%AF%95%E8%91%97%E4%BD%9C.pdf" in captured["Params"]["ResponseContentDisposition"]


def test_public_cdn_read_url_is_direct_but_download_remains_signed(monkeypatch):
    calls = []

    class FakeClient:
        def generate_presigned_url(self, operation, **kwargs):
            calls.append((operation, kwargs))
            return "https://objects.example.org/signed-download"

    class FakeProvider:
        bucket = "library"
        public_base_url = "https://assets.example.org/library/"

    class FakeCloudObject:
        status = "ready"
        provider = FakeProvider()
        object_key = "published/中文著作/current.pdf"
        cdn_enabled = True

    monkeypatch.setattr("distribution.services.s3_client", lambda provider: FakeClient())

    read_url = signed_read_url(FakeCloudObject(), download_filename="中文著作.pdf")
    assert read_url == (
        "https://assets.example.org/library/published/"
        "%E4%B8%AD%E6%96%87%E8%91%97%E4%BD%9C/current.pdf"
    )
    assert calls == []

    download_url = signed_read_url(
        FakeCloudObject(),
        download_filename="中文著作.pdf",
        attachment=True,
    )
    assert download_url.endswith("/signed-download")
    assert calls[0][0] == "get_object"
    assert calls[0][1]["Params"]["ResponseContentDisposition"].startswith("attachment;")


@pytest.mark.django_db
def test_batch_upload_records_each_pdf_and_isolates_rejected_files(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
):
    api_client.force_authenticate(admin_user)
    files = [
        SimpleUploadedFile("first.pdf", b"%PDF-1.4\nfirst", content_type="application/pdf"),
        SimpleUploadedFile("not-a-pdf.pdf", b"plain text", content_type="application/pdf"),
        SimpleUploadedFile("third.pdf", b"%PDF-1.4\nthird", content_type="application/pdf"),
    ]
    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                "/api/ingestion/batches/upload/",
                {"files": files, "notes": "批量隔离测试"},
                format="multipart",
            )

        assert response.status_code == 202
        assert len(response.data["accepted"]) == 2
        assert len(response.data["rejected"]) == 1
        assert response.data["rejected"][0]["id"]
        assert response.data["batch"]["expected_count"] == 3
        assert response.data["batch"]["failed_count"] == 1
        assert queued.call_count == 2
        assert all(call.args[0] for call in queued.call_args_list)

    detail = api_client.get(f"/api/ingestion/batches/{response.data['batch']['id']}/")
    assert detail.status_code == 200
    assert len(detail.data["items"]) == 3
    rejected = next(item for item in detail.data["items"] if item["error_code"] == "upload_rejected")
    assert rejected["status"] == "failed"
    assert rejected["source_filename"] == "not-a-pdf.pdf"


@pytest.mark.django_db
def test_staged_batch_upload_is_per_file_and_idempotent(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
):
    api_client.force_authenticate(admin_user)
    batch = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 3},
        format="json",
    )
    assert batch.status_code == 201
    batch_id = batch.data["id"]
    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        with django_capture_on_commit_callbacks(execute=True):
            accepted = api_client.post(
                f"/api/ingestion/batches/{batch_id}/items/",
                {
                    "client_token": "client-file-token-1",
                    "file": SimpleUploadedFile(
                        "first.pdf",
                        b"%PDF-1.4\nfirst",
                        content_type="application/pdf",
                    ),
                },
                format="multipart",
            )
        repeated = api_client.post(
            f"/api/ingestion/batches/{batch_id}/items/",
            {"client_token": "client-file-token-1"},
            format="multipart",
        )
        rejected = api_client.post(
            f"/api/ingestion/batches/{batch_id}/items/",
            {
                "client_token": "client-file-token-2",
                "file": SimpleUploadedFile(
                    "broken.pdf",
                    b"not pdf",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
    interrupted = api_client.post(
        f"/api/ingestion/batches/{batch_id}/failures/",
        {
            "client_token": "client-file-token-3",
            "source_filename": "interrupted.pdf",
            "reason": "连接中断",
        },
        format="json",
    )

    assert accepted.status_code == 202
    assert accepted.data["accepted"] is True
    assert repeated.status_code == 200
    assert repeated.data["idempotent"] is True
    assert repeated.data["item"]["id"] == accepted.data["item"]["id"]
    assert rejected.status_code == 202
    assert rejected.data["accepted"] is False
    assert interrupted.status_code == 201
    assert queued.call_count == 1

    detail = api_client.get(f"/api/ingestion/batches/{batch_id}/")
    assert detail.status_code == 200
    assert detail.data["expected_count"] == 3
    assert len(detail.data["items"]) == 3
    assert sum(item["status"] == "failed" for item in detail.data["items"]) == 2


@pytest.mark.django_db
def test_chunked_public_upload_assembles_pdf_and_is_idempotent(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_INCOMING_ROOT = settings.MEDIA_ROOT / "incoming"
    settings.MAX_UPLOAD_BYTES = 1024 * 1024
    settings.MAX_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
    api_client.force_authenticate(admin_user)
    batch = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1},
        format="json",
    )
    assert batch.status_code == 201
    batch_id = batch.data["id"]
    payload = b"%PDF-1.4\nchunked-public-upload"
    pieces = [payload[:12], payload[12:]]

    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        first = api_client.post(
            f"/api/ingestion/batches/{batch_id}/chunks/",
            {
                "client_token": "chunk-token-2026",
                "source_filename": "slow-public-upload.pdf",
                "chunk_index": 0,
                "total_chunks": 2,
                "total_size": len(payload),
                "chunk": SimpleUploadedFile("part-0", pieces[0]),
            },
            format="multipart",
        )
        with django_capture_on_commit_callbacks(execute=True):
            second = api_client.post(
                f"/api/ingestion/batches/{batch_id}/chunks/",
                {
                    "client_token": "chunk-token-2026",
                    "source_filename": "slow-public-upload.pdf",
                    "chunk_index": 1,
                    "total_chunks": 2,
                    "total_size": len(payload),
                    "chunk": SimpleUploadedFile("part-1", pieces[1]),
                },
                format="multipart",
            )
        repeated = api_client.post(
            f"/api/ingestion/batches/{batch_id}/chunks/",
            {
                "client_token": "chunk-token-2026",
                "source_filename": "slow-public-upload.pdf",
                "chunk_index": 1,
                "total_chunks": 2,
                "total_size": len(payload),
                "chunk": SimpleUploadedFile("part-1", pieces[1]),
            },
            format="multipart",
        )

    assert first.status_code == 202
    assert first.data["complete"] is False
    assert second.status_code == 202
    assert second.data["complete"] is True
    assert second.data["accepted"] is True
    assert repeated.status_code == 200
    assert repeated.data["idempotent"] is True
    queued.assert_called_once()
    item = UploadItem.objects.get(pk=second.data["item"]["id"])
    with item.file.open("rb") as uploaded:
        assert uploaded.read() == payload
    audit = AuditEvent.objects.get(action="chunked_batch_item_received", object_id=str(item.id))
    assert audit.after["storage_write"] == "filesystem_hardlink"


@pytest.mark.django_db
def test_chunked_public_upload_accepts_eight_mebibyte_chunks_and_validates_manifest(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
    settings,
    tmp_path,
):
    chunk_size = 8 * 1024 * 1024
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_INCOMING_ROOT = settings.MEDIA_ROOT / "incoming"
    settings.MAX_UPLOAD_BYTES = 16 * 1024 * 1024
    settings.MAX_UPLOAD_CHUNK_BYTES = chunk_size
    api_client.force_authenticate(admin_user)
    batch = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1},
        format="json",
    )
    batch_id = batch.data["id"]
    payload = b"%PDF-" + b"x" * (chunk_size + 17 - 5)
    pieces = [payload[:chunk_size], payload[chunk_size:]]

    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        first = api_client.post(
            f"/api/ingestion/batches/{batch_id}/chunks/",
            {
                "client_token": "chunk-token-eight-mib",
                "source_filename": "large-public-upload.pdf",
                "chunk_index": 0,
                "total_chunks": 2,
                "total_size": len(payload),
                "chunk_size": chunk_size,
                "chunk": SimpleUploadedFile("part-0", pieces[0]),
            },
            format="multipart",
        )
        with django_capture_on_commit_callbacks(execute=True):
            second = api_client.post(
                f"/api/ingestion/batches/{batch_id}/chunks/",
                {
                    "client_token": "chunk-token-eight-mib",
                    "source_filename": "large-public-upload.pdf",
                    "chunk_index": 1,
                    "total_chunks": 2,
                    "total_size": len(payload),
                    "chunk_size": chunk_size,
                    "chunk": SimpleUploadedFile("part-1", pieces[1]),
                },
                format="multipart",
            )

    assert first.status_code == 202
    assert first.data["max_chunk_size"] == chunk_size
    assert second.status_code == 202
    assert second.data["complete"] is True
    queued.assert_called_once()
    item = UploadItem.objects.get(pk=second.data["item"]["id"])
    assert item.file.size == len(payload)


@pytest.mark.django_db
def test_chunked_public_upload_rejects_chunk_larger_than_configured_limit(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_INCOMING_ROOT = settings.MEDIA_ROOT / "incoming"
    settings.MAX_UPLOAD_BYTES = 4096
    settings.MAX_UPLOAD_CHUNK_BYTES = 1024
    api_client.force_authenticate(admin_user)
    batch = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1},
        format="json",
    )
    response = api_client.post(
        f"/api/ingestion/batches/{batch.data['id']}/chunks/",
        {
            "client_token": "chunk-token-too-large",
            "source_filename": "too-large.pdf",
            "chunk_index": 0,
            "total_chunks": 1,
            "total_size": 1025,
            "chunk_size": 1025,
            "chunk": SimpleUploadedFile("part-0", b"%PDF-" + b"x" * 1020),
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert "文件名、大小或分段编号无效" in response.data["detail"]


@pytest.mark.django_db
def test_reader_can_save_and_remove_a_published_topic(api_client, reader_user):
    topic = Topic.objects.create(
        name="可收藏主题",
        slug="saved-topic",
        description="读者收藏接口测试",
        editorial_status="published",
    )
    api_client.force_authenticate(reader_user)

    created = api_client.post(
        "/api/reading/saved-topics/",
        {"topic": str(topic.id)},
        format="json",
    )
    assert created.status_code == 201
    listing = api_client.get("/api/reading/saved-topics/", {"topic": str(topic.id)})
    assert listing.status_code == 200
    assert listing.data["results"][0]["slug"] == "saved-topic"

    exported = api_client.get("/api/reading/export/")
    assert exported.status_code == 200
    assert exported.data["saved_topics"][0]["name"] == "可收藏主题"

    removed = api_client.delete(f"/api/reading/saved-topics/{created.data['id']}/")
    assert removed.status_code == 204


@pytest.mark.django_db
def test_site_config_is_public_but_only_admin_can_update(api_client, admin_user, reader_user):
    default_response = api_client.get("/api/catalog/site-config/")
    assert default_response.status_code == 200
    assert default_response.data["site_name"] == "社会理论书库"

    payload = dict(default_response.data)
    payload["site_name"] = "可编辑测试书库"
    api_client.force_authenticate(reader_user)
    assert api_client.put("/api/catalog/site-config/", payload, format="json").status_code == 403

    api_client.force_authenticate(admin_user)
    updated = api_client.put("/api/catalog/site-config/", payload, format="json")
    assert updated.status_code == 200
    api_client.force_authenticate(user=None)
    assert api_client.get("/api/catalog/site-config/").data["site_name"] == "可编辑测试书库"


@pytest.mark.django_db
def test_admin_configures_reader_submission_mailto_without_smtp(
    api_client,
    admin_user,
    reader_user,
    settings,
):
    settings.READER_SUBMISSION_EMAIL = ""
    api_client.force_authenticate(admin_user)
    saved = api_client.put(
        "/api/catalog/admin/reader-submission/",
        {"email": "submissions@example.com"},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.data["email"] == "submissions@example.com"

    api_client.force_authenticate(reader_user)
    submission = api_client.post(
        "/api/reading/submit/",
        {"title": "测试荐书", "note": "合法来源待管理员核查"},
        format="json",
    )
    assert submission.status_code == 200
    assert submission.data["email"] == "submissions@example.com"
    assert submission.data["mailto"].startswith("mailto:submissions@example.com?")


@pytest.mark.django_db
def test_admin_can_manage_taxonomy_and_scholar_profiles(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    theory = api_client.post(
        "/api/catalog/admin/theory-schools/",
        {
            "name": "关系社会学",
            "slug": "",
            "description": "测试流派",
            "symbol": "关系",
            "key_themes": ["关系", "网络"],
            "editorial_status": "published",
        },
        format="json",
    )
    assert theory.status_code == 201
    assert theory.data["slug"]
    neighbor_theory = api_client.post(
        "/api/catalog/admin/theory-schools/",
        {
            "name": "邻接理论",
            "slug": "",
            "description": "用于测试流派关系",
            "symbol": "邻",
            "key_themes": ["关系"],
            "editorial_status": "published",
        },
        format="json",
    )
    assert neighbor_theory.status_code == 201

    topic = api_client.post(
        "/api/catalog/admin/topics/",
        {
            "name": "数字劳动",
            "slug": "",
            "description": "测试主题",
            "key_concepts": ["平台", "劳动"],
            "timeline": [],
            "editorial_status": "published",
        },
        format="json",
    )
    assert topic.status_code == 201

    scholar = api_client.post(
        "/api/catalog/admin/scholars/",
        {
            "slug": "",
            "preferred_name": "测试人物",
            "original_name": "Test Person",
            "aliases": ["测试学者译名"],
            "birth_year": 1970,
            "death_year": None,
            "biography": "完整传记",
            "short_description": "简短说明",
            "affiliations": ["测试大学"],
            "key_concerns": ["数字劳动"],
            "timeline": [],
            "featured_quote": "",
            "quote_source": "",
            "editorial_status": "published",
        },
        format="json",
    )
    assert scholar.status_code == 201
    assert scholar.data["preferred_name"] == "测试人物"
    related_scholar = api_client.post(
        "/api/catalog/admin/scholars/",
        {
            "slug": "",
            "preferred_name": "关联人物",
            "original_name": "Related Person",
            "aliases": [],
            "birth_year": 1980,
            "death_year": None,
            "biography": "关系网络测试人物",
            "short_description": "关系网络测试",
            "affiliations": [],
            "key_concerns": [],
            "timeline": [],
            "featured_quote": "",
            "quote_source": "",
            "editorial_status": "published",
        },
        format="json",
    )
    assert related_scholar.status_code == 201

    scholar_curation = api_client.patch(
        f"/api/catalog/admin/scholars/{scholar.data['id']}/",
        {
            "curation": {
                "essential_work_ids": [],
                "key_concepts": [
                    {
                        "name": "平台劳动",
                        "description": "测试概念说明",
                        "source": "管理员核对",
                    }
                ],
                "concept_map": [
                    {
                        "source": "劳动",
                        "target": "平台",
                        "relation": "嵌入",
                        "description": "连接经验研究",
                    }
                ],
                "network": [
                    {
                        "scholar_id": related_scholar.data["id"],
                        "relation": "合作研究",
                        "source": "测试资料",
                    }
                ],
                "frequently_read_scholar_ids": [],
            }
        },
        format="json",
    )
    assert scholar_curation.status_code == 200
    assert scholar_curation.data["curation"]["key_concepts"][0]["name"] == "平台劳动"

    topic_curation = api_client.patch(
        f"/api/catalog/admin/topics/{topic.data['id']}/",
        {
            "curation": {
                "hero_caption": "测试主题图片说明",
                "foundational_work_ids": [],
                "recent_work_ids": [],
                "related_scholar_ids": [scholar.data["id"]],
                "linked_theory_ids": [theory.data["id"]],
                "reading_paths": [
                    {
                        "title": "主题入门",
                        "description": "测试路径",
                        "level": "初级",
                        "work_ids": [],
                    }
                ],
            }
        },
        format="json",
    )
    assert topic_curation.status_code == 200

    theory_curation = api_client.patch(
        f"/api/catalog/admin/theory-schools/{theory.data['id']}/",
        {
            "curation": {
                "hero_caption": "测试流派图片说明",
                "foundational_work_ids": [],
                "curated_reading_work_ids": [],
                "key_scholar_ids": [scholar.data["id"]],
                "neighbor_school_ids": [neighbor_theory.data["id"]],
                "neighbor_relations": [
                    {
                        "school_id": neighbor_theory.data["id"],
                        "relation": "概念邻近",
                        "source": "测试资料",
                    }
                ],
                "core_concepts": [
                    {
                        "name": "关系",
                        "description": "测试核心概念",
                        "source": "测试资料",
                    }
                ],
                "conceptual_map": [
                    {
                        "source": "关系",
                        "target": "网络",
                        "relation": "组织",
                        "description": "测试关系",
                    }
                ],
            }
        },
        format="json",
    )
    assert theory_curation.status_code == 200

    public_scholars = api_client.get("/api/catalog/scholars/")
    public_scholar = next(
        row
        for row in public_scholars.data["results"]
        if row["person"]["preferred_name"] == "测试人物"
    )
    assert public_scholar["curated"]["key_concepts"][0]["name"] == "平台劳动"
    assert public_scholar["curated"]["network"][0]["relation"] == "合作研究"
    public_topic = api_client.get(f"/api/catalog/topics/{topic.data['slug']}/")
    assert public_topic.data["curated"]["reading_paths"][0]["title"] == "主题入门"
    public_theory = api_client.get(f"/api/catalog/theory-schools/{theory.data['slug']}/")
    assert public_theory.data["curated"]["key_scholars"][0]["name"] == "测试人物"
    assert public_theory.data["curated"]["core_concepts"][0]["name"] == "关系"
    assert public_theory.data["curated"]["neighbors"][0]["relation"] == "概念邻近"
    assert public_theory.data["curated"]["conceptual_map"][0]["target"] == "网络"


@pytest.mark.django_db
def test_cloud_budget_snapshot_blocks_only_new_publications(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    provider_response = api_client.post(
        "/api/distribution/providers/",
        {
            "name": "测试 S3",
            "provider_type": "s3",
            "endpoint_url": "https://s3.example.org",
            "bucket": "library",
            "region": "test-1",
            "public_base_url": "",
            "credential_reference": "TEST_S3",
            "enabled": True,
            "is_default": True,
            "budget": {
                "monthly_budget": "100.00",
                "warning_ratio": 0.8,
                "stop_new_publications_ratio": 1,
                "pause_new_cdn_on_limit": True,
                "preserve_existing_reads": True,
                "notification_emails": [],
            },
        },
        format="json",
    )
    assert provider_response.status_code == 201
    provider = CloudProvider.objects.get(pk=provider_response.data["id"])
    assert cloud_budget_allows_new_publication(provider)

    usage = api_client.post(
        f"/api/distribution/providers/{provider.id}/usage/",
        {
            "period": timezone.now().strftime("%Y-%m"),
            "storage_bytes": 100,
            "egress_bytes": 200,
            "request_count": 3,
            "estimated_cost": "100.00",
            "source_payload": {"source": "test"},
        },
        format="json",
    )
    assert usage.status_code == 201
    assert not cloud_budget_allows_new_publication(provider)
    assert provider.budget_policy.preserve_existing_reads is True


@pytest.mark.django_db
def test_admin_updates_user_without_exposing_old_password(api_client, admin_user, reader_user):
    api_client.force_authenticate(admin_user)
    listing = api_client.get("/api/auth/users/")
    row = next(item for item in listing.data["results"] if item["id"] == reader_user.id)
    assert "password" not in row

    update = api_client.patch(
        f"/api/auth/users/{reader_user.id}/",
        {"display_name": "更新读者", "role": "editor", "is_active": True},
        format="json",
    )
    assert update.status_code == 200
    reader_user.refresh_from_db()
    assert reader_user.role == User.Role.EDITOR

    reset = api_client.post(
        f"/api/auth/users/{reader_user.id}/set-password/",
        {"new_password": "New-Reader-Secure-Password-2026"},
        format="json",
    )
    assert reset.status_code == 200
    reader_user.refresh_from_db()
    assert reader_user.check_password("New-Reader-Secure-Password-2026")
    assert not reader_user.check_password("Reader-Secure-Password-2026")


@pytest.mark.django_db
def test_only_configured_owner_can_promote_or_demote_administrators(
    api_client,
    admin_user,
    reader_user,
    settings,
):
    settings.LIBRARY_OWNER_EMAIL = "owner@example.com"
    owner = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        display_name="Winston",
        role=User.Role.ADMIN,
        password="Owner-Secure-Password-2026",
    )

    api_client.force_authenticate(admin_user)
    denied = api_client.patch(
        f"/api/auth/users/{reader_user.id}/",
        {"role": "admin"},
        format="json",
    )
    assert denied.status_code == 403
    reader_user.refresh_from_db()
    assert reader_user.role == User.Role.READER

    api_client.force_authenticate(owner)
    promoted = api_client.patch(
        f"/api/auth/users/{reader_user.id}/",
        {"role": "admin"},
        format="json",
    )
    assert promoted.status_code == 200
    reader_user.refresh_from_db()
    assert reader_user.role == User.Role.ADMIN

    api_client.force_authenticate(admin_user)
    owner_protected = api_client.patch(
        f"/api/auth/users/{owner.id}/",
        {"is_active": False},
        format="json",
    )
    assert owner_protected.status_code == 400
    owner.refresh_from_db()
    assert owner.is_active is True


@pytest.mark.django_db
def test_reading_history_coalesces_recent_page_updates(api_client, reader_user):
    work = Work.objects.create(document_type="book", title="阅读历史测试")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="history-test",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/history.pdf",
        sha256="b" * 64,
        status=Asset.Status.READY,
        page_count=10,
    )
    api_client.force_authenticate(reader_user)
    first = api_client.post(
        "/api/reading/history/",
        {"asset": str(asset.id), "page_index": 2, "session_seconds": 5},
        format="json",
    )
    second = api_client.post(
        "/api/reading/history/",
        {"asset": str(asset.id), "page_index": 4, "session_seconds": 7},
        format="json",
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert ReadingHistory.objects.filter(user=reader_user, asset=asset).count() == 1
    history = ReadingHistory.objects.get(user=reader_user, asset=asset)
    assert history.page_index == 4
    assert history.session_seconds == 12


@pytest.mark.django_db
def test_processing_center_marks_stalled_queue_item_and_retries_it(
    api_client,
    admin_user,
    settings,
    django_capture_on_commit_callbacks,
):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.INGESTION_QUEUE_STALLED_SECONDS = 60
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        status=UploadBatch.Status.PROCESSING,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="waiting.pdf",
        file="incoming/waiting.pdf",
        status=UploadItem.Status.RECEIVED,
    )
    UploadItem.objects.filter(pk=item.pk).update(
        updated_at=timezone.now() - timedelta(minutes=5),
    )
    api_client.force_authenticate(admin_user)

    listing = api_client.get("/api/ingestion/items/?scope=processing")
    row = next(entry for entry in listing.data["results"] if entry["id"] == str(item.id))
    assert row["is_stalled"] is True
    assert row["suggested_action"] == "retry"
    assert row["queue_mode"] == "worker"

    health = api_client.get("/api/ingestion/queue-health/")
    assert health.status_code == 200
    assert health.data["stalled_count"] == 1
    assert health.data["worker_required"] is True

    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        with django_capture_on_commit_callbacks(execute=True):
            retried = api_client.post(f"/api/ingestion/items/{item.id}/retry/")
    assert retried.status_code == 202
    queued.assert_called_once()
    assert queued.call_args.args[0] == str(item.id)
    item.refresh_from_db()
    assert item.retry_count == 1
    assert item.stage_progress == 0


@pytest.mark.django_db
def test_retry_reuses_a_recent_received_dispatch(
    api_client,
    admin_user,
    settings,
    django_capture_on_commit_callbacks,
):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.INGESTION_QUEUE_STALLED_SECONDS = 60
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="recently-queued.pdf",
        file="incoming/recently-queued.pdf",
        status=UploadItem.Status.RECEIVED,
        dispatch_status=UploadItem.DispatchStatus.QUEUED,
        dispatch_task_id="existing-task-id",
        dispatch_attempts=1,
        last_dispatched_at=timezone.now(),
    )
    api_client.force_authenticate(admin_user)

    with patch("ingestion.services.dispatch.dispatch_upload_item") as queued:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    assert response.status_code == 202
    assert response.data["reused"] is True
    assert response.data["task_id"] == "existing-task-id"
    queued.assert_not_called()
    item.refresh_from_db()
    assert item.dispatch_task_id == "existing-task-id"
    assert item.dispatch_attempts == 1
    assert item.retry_count == 0
