import pytest
from django.test import RequestFactory, override_settings

from catalog.models import Edition, KnowledgeNode, TheoryReviewTask, Topic, Work
from config.throttling import is_trusted_internal_request
from ingestion.models import AuditEvent, UploadBatch, UploadItem


@override_settings(INTERNAL_API_TOKEN="a" * 40)
def test_internal_api_token_requires_an_exact_long_server_secret():
    factory = RequestFactory()
    trusted = factory.get("/api/catalog/scholars/", HTTP_X_INTERNAL_API_TOKEN="a" * 40)
    wrong = factory.get("/api/catalog/scholars/", HTTP_X_INTERNAL_API_TOKEN="b" * 40)
    assert is_trusted_internal_request(trusted) is True
    assert is_trusted_internal_request(wrong) is False


@override_settings(INTERNAL_API_TOKEN="short")
def test_short_internal_api_token_never_bypasses_throttling():
    request = RequestFactory().get("/api/catalog/scholars/", HTTP_X_INTERNAL_API_TOKEN="short")
    assert is_trusted_internal_request(request) is False


@pytest.mark.django_db
def test_published_entity_must_be_archived_before_permanent_delete(
    api_client,
    admin_user,
):
    topic = Topic.objects.create(
        name="可下线的研究主题",
        slug="archivable-topic",
        editorial_status="published",
    )
    api_client.force_authenticate(admin_user)

    blocked = api_client.post(
        f"/api/catalog/admin/lifecycle/topic/{topic.id}/",
        {"action": "delete", "confirmed": True},
        format="json",
    )
    assert blocked.status_code == 409

    archived = api_client.post(
        f"/api/catalog/admin/lifecycle/topic/{topic.id}/",
        {"action": "archive"},
        format="json",
    )
    assert archived.status_code == 200
    assert archived.data["status"] == "archived"

    deleted = api_client.post(
        f"/api/catalog/admin/lifecycle/topic/{topic.id}/",
        {"action": "delete", "confirmed": True},
        format="json",
    )
    assert deleted.status_code == 204
    assert not Topic.objects.filter(pk=topic.id).exists()


@pytest.mark.django_db
def test_reader_cannot_change_admin_entity_lifecycle(
    api_client,
    reader_user,
):
    topic = Topic.objects.create(
        name="受权限保护的主题",
        slug="protected-topic",
        editorial_status="published",
    )
    api_client.force_authenticate(reader_user)

    response = api_client.post(
        f"/api/catalog/admin/lifecycle/topic/{topic.id}/",
        {"action": "archive"},
        format="json",
    )
    assert response.status_code == 403
    topic.refresh_from_db()
    assert topic.editorial_status == "published"


@pytest.mark.django_db
def test_removed_upload_item_is_hidden_but_nas_file_reference_is_preserved(
    api_client,
    admin_user,
):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="待移除.pdf",
        file="incoming/preserved.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        f"/api/ingestion/items/{item.id}/delete/",
        {"confirmed": True},
        format="json",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.status == UploadItem.Status.DELETED
    assert item.file.name == "incoming/preserved.pdf"

    listing = api_client.get("/api/ingestion/items/")
    assert listing.status_code == 200
    assert str(item.id) not in {row["id"] for row in listing.data["results"]}

    audit_listing = api_client.get("/api/ingestion/items/?include_deleted=true")
    assert audit_listing.status_code == 200
    assert str(item.id) in {row["id"] for row in audit_listing.data["results"]}


@pytest.mark.django_db
def test_duplicate_intake_can_be_removed_without_withdrawing_published_edition(
    api_client,
    admin_user,
):
    work = Work.objects.create(document_type="book", title="已发布的重复文献")
    edition = Edition.objects.create(work=work, state="published")
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="重复上传.pdf",
        file="incoming/duplicate.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        error_code="duplicate_document",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        f"/api/ingestion/items/{item.id}/delete/",
        {"confirmed": True},
        format="json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    edition.refresh_from_db()
    assert item.status == UploadItem.Status.DELETED
    assert edition.state == "published"
    audit = AuditEvent.objects.get(action="upload_item_delete", object_id=str(item.id))
    assert audit.after["linked_publication_preserved"] is True


@pytest.mark.django_db
def test_public_knowledge_node_does_not_require_a_work(api_client):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="尚无馆藏的理论传统",
        slug="theory-without-work",
        summary="该条目由管理员先行整理，后续可再关联馆藏。",
        status="published",
    )

    response = api_client.get(f"/api/catalog/theory-system/nodes/{node.slug}/")
    assert response.status_code == 200
    assert response.data["canonical_name_zh"] == node.canonical_name_zh
    assert response.data["work_count"] == 0


@pytest.mark.django_db
def test_timeline_event_can_publish_with_theory_but_without_work(
    api_client,
    admin_user,
):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="独立时间轴理论",
        slug="standalone-timeline-theory",
        status="published",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/catalog/admin/theory-timeline/",
        {
            "title": "不依赖馆藏的理论事件",
            "description": "事件可依据人工校订资料发布，日后再补馆藏证据。",
            "event_type": "school_formation",
            "start_year": 1950,
            "date_label": "20世纪中期",
            "source": "管理员校订",
            "review_status": "approved",
            "relations": [
                {
                    "relation_type": "subject",
                    "node": str(node.id),
                    "discipline": None,
                    "scholar": None,
                    "work": None,
                    "evidence": None,
                    "description": "理论事件主体",
                    "sort_order": 0,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["work"] is None
    assert response.data["review_status"] == "approved"


@pytest.mark.django_db
def test_admin_can_delete_an_invalid_theory_review_candidate_with_audit(
    api_client,
    admin_user,
):
    task = TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.NEW_NODE,
        suggested_node_name="错误识别候选",
        suggested_relation_type="general_mention",
        confidence=0.22,
        evidence_pages=[4],
        evidence_text="OCR 噪声造成的错误候选。",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.delete(
        f"/api/catalog/admin/theory-system/review-tasks/{task.id}/"
    )

    assert response.status_code == 204
    assert not TheoryReviewTask.objects.filter(pk=task.id).exists()
    assert AuditEvent.objects.filter(
        action="theory_review_task_delete",
        object_id=str(task.id),
    ).exists()


@pytest.mark.django_db
def test_existing_theory_relation_can_be_edited_and_archived(
    api_client,
    admin_user,
):
    source = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="来源理论",
        slug="relation-source",
        status="published",
    )
    target = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="目标理论",
        slug="relation-target",
        status="published",
    )
    api_client.force_authenticate(admin_user)
    created = api_client.post(
        "/api/catalog/admin/theory-system/relations/",
        {
            "source_node": str(source.id),
            "target_node": str(target.id),
            "relation_type": "criticizes",
            "direction": "directed",
            "description": "初始说明",
            "evidence_source": "管理员校订",
            "confidence": 0.8,
            "status": "published",
        },
        format="json",
    )
    assert created.status_code == 201

    updated = api_client.patch(
        f"/api/catalog/admin/theory-system/relations/{created.data['id']}/",
        {"description": "修改后的说明", "status": "archived"},
        format="json",
    )

    assert updated.status_code == 200
    assert updated.data["description"] == "修改后的说明"
    assert updated.data["status"] == "archived"
