from __future__ import annotations

import pytest

from accounts.models import User
from catalog.models import (
    DocumentType,
    Edition,
    KnowledgeNode,
    PublicationState,
    ReadingPath,
    ReadingPathItem,
    ReadingPathStage,
    RecommendationOverride,
    RecommendationPolicy,
    Work,
)
from catalog.services.recommendations import generate_snapshot
from ingestion.models import AuditEvent


def make_work(
    title: str,
    *,
    document_type: str = DocumentType.JOURNAL_ARTICLE,
    published: bool = False,
) -> Work:
    work = Work.objects.create(
        title=title,
        document_type=document_type,
        language="zh-CN",
    )
    if published:
        Edition.objects.create(
            work=work,
            state=PublicationState.PUBLISHED,
            public_slug=f"curation-{work.id}",
            publication_year=2026,
            journal_title="社会理论测试期刊" if document_type == DocumentType.JOURNAL_ARTICLE else "",
            publisher="测试出版社" if document_type == DocumentType.BOOK else "",
        )
    return work


def make_path(title: str, *, status_value: str = "draft"):
    path = ReadingPath.objects.create(
        title=title,
        slug=f"curation-path-{ReadingPath.objects.count()}",
        status=status_value,
    )
    stage = ReadingPathStage.objects.create(
        reading_path=path,
        name="第一阶段",
        description="先建立问题背景。",
        position=0,
    )
    return path, stage


def make_editor(username: str = "curation-editor@example.test") -> User:
    return User.objects.create_user(
        username=username,
        email=username,
        password="Curation-Test-2026",
        role=User.Role.EDITOR,
    )


@pytest.mark.django_db
def test_contextual_journal_placement_supports_summary_patch_conflict_and_delete(
    api_client,
    admin_user,
):
    work = make_work("期刊论文策展测试")
    path, stage = make_path("期刊论文阅读路径")
    initial_updated_at = path.updated_at.isoformat()
    api_client.force_authenticate(admin_user)

    created = api_client.post(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/",
        {
            "reading_path_id": str(path.id),
            "stage_id": str(stage.id),
            "recommendation_reason": "用于理解该争论的经验材料。",
            "is_required": True,
            "editorial_note": "期刊论文 placement",
            "expected_path_updated_at": initial_updated_at,
        },
        format="json",
    )

    assert created.status_code == 201
    assert str(created.data["work"]) == str(work.id)
    assert created.data["stage"]["id"] == str(stage.id)
    assert created.data["is_required"] is True
    item = ReadingPathItem.objects.get(pk=created.data["id"])
    assert item.stage_id == stage.id
    assert item.stage_name == stage.name
    assert item.stage_description == stage.description
    assert item.position == 0
    assert item.reading_order == 0

    summary = api_client.get(f"/api/catalog/admin/works/{work.id}/curation/")
    assert summary.status_code == 200
    assert summary.data["work"]["document_type"] == DocumentType.JOURNAL_ARTICLE
    assert summary.data["reading_path_placements"][0]["id"] == str(item.id)

    stale = api_client.patch(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/{item.id}/",
        {
            "recommendation_reason": "不应覆盖",
            "expected_path_updated_at": initial_updated_at,
        },
        format="json",
    )
    assert stale.status_code == 409
    assert stale.data["code"] == "curation_conflict"

    current_path_version = created.data["path_updated_at"]
    updated = api_client.patch(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/{item.id}/",
        {
            "recommendation_reason": "管理员复核后的推荐理由。",
            "is_required": False,
            "expected_path_updated_at": current_path_version,
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["recommendation_reason"] == "管理员复核后的推荐理由。"
    assert updated.data["is_required"] is False

    deleted = api_client.delete(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/{item.id}/",
        {"expected_path_updated_at": updated.data["path_updated_at"]},
        format="json",
    )
    assert deleted.status_code == 200
    assert deleted.data["deleted"] is True
    assert not ReadingPathItem.objects.filter(pk=item.id).exists()
    assert AuditEvent.objects.filter(
        action="work_reading_path_placement_create",
        object_id=str(item.id),
    ).exists()
    assert AuditEvent.objects.filter(
        action="work_reading_path_placement_delete",
        object_id=str(item.id),
    ).exists()


@pytest.mark.django_db
def test_contextual_placement_enforces_work_identity_and_path_permissions(
    api_client,
    admin_user,
):
    editor = make_editor()
    work = make_work("编辑策展作品")
    another_work = make_work("另一作品")
    draft_path, draft_stage = make_path("编辑可维护的草稿路径")
    public_path, public_stage = make_path("已发布路径", status_value="published")

    api_client.force_authenticate(editor)
    draft_created = api_client.post(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/",
        {
            "reading_path_id": str(draft_path.id),
            "stage_id": str(draft_stage.id),
        },
        format="json",
    )
    assert draft_created.status_code == 201

    wrong_work = api_client.patch(
        f"/api/catalog/admin/works/{another_work.id}/reading-path-placements/{draft_created.data['id']}/",
        {"editorial_note": "不能跨 Work 修改"},
        format="json",
    )
    assert wrong_work.status_code == 404

    denied = api_client.post(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/",
        {
            "reading_path_id": str(public_path.id),
            "stage_id": str(public_stage.id),
        },
        format="json",
    )
    assert denied.status_code == 403
    advanced_denied = api_client.patch(
        f"/api/catalog/admin/theory-system/reading-paths/{public_path.id}/",
        {
            "expected_updated_at": public_path.updated_at.isoformat(),
            "stage_groups": [],
        },
        format="json",
    )
    assert advanced_denied.status_code == 403

    api_client.force_authenticate(admin_user)
    allowed = api_client.post(
        f"/api/catalog/admin/works/{work.id}/reading-path-placements/",
        {
            "reading_path_id": str(public_path.id),
            "stage_id": str(public_stage.id),
        },
        format="json",
    )
    assert allowed.status_code == 201


@pytest.mark.django_db
def test_public_reading_path_filters_unpublished_work_and_node_but_admin_keeps_them(
    api_client,
    admin_user,
    settings,
):
    settings.THEORY_SYSTEM_ENABLED = True
    path, _stage = make_path("公开过滤路径", status_value="published")
    published_work = make_work("已发布期刊论文", published=True)
    draft_work = make_work("未发布期刊论文")
    published_node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="公开概念",
        slug="public-curation-concept",
        status="published",
    )
    draft_node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="草稿概念",
        slug="draft-curation-concept",
        status="draft",
    )
    targets = [
        ("公开作品", published_work, None),
        ("草稿作品", draft_work, None),
        ("公开节点", None, published_node),
        ("草稿节点", None, draft_node),
    ]
    item_ids = []
    stage_ids = []
    for order, (name, work, node) in enumerate(targets):
        stage = ReadingPathStage.objects.create(
            reading_path=path,
            name=name,
            position=order,
        )
        item = ReadingPathItem.objects.create(
            reading_path=path,
            stage=stage,
            stage_name=name,
            work=work,
            node=node,
            position=0,
            reading_order=order,
        )
        item_ids.append(str(item.id))
        stage_ids.append(str(stage.id))

    public = api_client.get(f"/api/catalog/theory-system/reading-paths/{path.slug}/")
    assert public.status_code == 200
    assert [row["id"] for row in public.data["items"]] == [item_ids[0], item_ids[2]]
    assert [row["id"] for row in public.data["stages"]] == [stage_ids[0], stage_ids[2]]

    api_client.force_authenticate(admin_user)
    admin = api_client.get(f"/api/catalog/admin/theory-system/reading-paths/{path.id}/")
    assert admin.status_code == 200
    assert [row["id"] for row in admin.data["items"]] == item_ids
    # The advanced editor keeps intentionally empty stages. Public output only
    # exposes stages with a visible target, while Admin returns the full path.
    assert set(stage_ids).issubset({row["id"] for row in admin.data["stages"]})


@pytest.mark.django_db
def test_work_recommendation_override_is_capability_guarded_deduplicated_and_used(
    api_client,
    admin_user,
):
    editor = make_editor("recommendation-editor@example.test")
    work = make_work("推荐 Override 期刊论文", published=True)
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_FEATURED
    )
    policy.item_count = 1
    policy.save(update_fields=["item_count", "updated_at"])

    api_client.force_authenticate(editor)
    denied = api_client.put(
        f"/api/catalog/admin/works/{work.id}/recommendation-overrides/{policy.placement}/",
        {"action": "pin", "position": 0},
        format="json",
    )
    assert denied.status_code == 403

    api_client.force_authenticate(admin_user)
    created = api_client.put(
        f"/api/catalog/admin/works/{work.id}/recommendation-overrides/{policy.placement}/",
        {"action": "pin", "position": 0, "note": "当前作品置顶"},
        format="json",
    )
    assert created.status_code == 200
    canonical_id = created.data["id"]

    RecommendationOverride.objects.create(
        policy=policy,
        work=work,
        action=RecommendationOverride.Action.EXCLUDE,
        active=True,
        created_by=admin_user,
    )
    reconciled = api_client.put(
        f"/api/catalog/admin/works/{work.id}/recommendation-overrides/{policy.placement}/",
        {"action": "pin", "position": 0, "note": "去重后保留"},
        format="json",
    )
    assert reconciled.status_code == 200
    assert reconciled.data["id"] == canonical_id
    assert RecommendationOverride.objects.filter(
        policy=policy,
        work=work,
        active=True,
    ).count() == 1
    active = RecommendationOverride.objects.get(policy=policy, work=work, active=True)
    assert active.action == RecommendationOverride.Action.PIN

    snapshot = generate_snapshot(policy, actor=admin_user)
    assert list(snapshot.items.values_list("work_id", flat=True)) == [work.id]

    summary = api_client.get(f"/api/catalog/admin/works/{work.id}/curation/")
    assert summary.status_code == 200
    assert summary.data["recommendations"]["current"][0]["placement"] == policy.placement
    assert len(
        [row for row in summary.data["recommendations"]["overrides"] if row["active"]]
    ) == 1

    removed = api_client.delete(
        f"/api/catalog/admin/works/{work.id}/recommendation-overrides/{policy.placement}/"
    )
    assert removed.status_code == 200
    assert removed.data["deactivated_count"] == 1
    assert not RecommendationOverride.objects.filter(
        policy=policy,
        work=work,
        active=True,
    ).exists()
    assert AuditEvent.objects.filter(
        action="work_recommendation_override_upsert",
        object_id=canonical_id,
    ).exists()


@pytest.mark.django_db
def test_work_recommendation_override_rejects_non_work_placement(api_client, admin_user):
    work = make_work("无效推荐位置测试", published=True)
    api_client.force_authenticate(admin_user)
    response = api_client.put(
        f"/api/catalog/admin/works/{work.id}/recommendation-overrides/home_scholars/",
        {"action": "pin", "position": 0},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["code"] == "curation_validation_error"


@pytest.mark.django_db
def test_advanced_reading_path_editor_saves_stages_and_multiple_items_with_conflict_guard(
    api_client,
    admin_user,
):
    path, initial_stage = make_path("高级阶段编辑路径")
    first = make_work("阶段一作品甲")
    second = make_work("阶段一作品乙")
    third = make_work("阶段二作品")
    api_client.force_authenticate(admin_user)
    expected = path.updated_at.isoformat()

    saved = api_client.patch(
        f"/api/catalog/admin/theory-system/reading-paths/{path.id}/",
        {
            "expected_updated_at": expected,
            "stage_groups": [
                {
                    "id": str(initial_stage.id),
                    "name": "共同基础",
                    "description": "同一阶段包含两部作品。",
                    "position": 0,
                    "items": [
                        {"work": str(first.id), "position": 0, "recommendation_reason": "先读甲"},
                        {"work": str(second.id), "position": 1, "recommendation_reason": "再读乙"},
                    ],
                },
                {
                    "name": "延伸应用",
                    "description": "进入经验研究。",
                    "position": 1,
                    "items": [
                        {"work": str(third.id), "position": 0, "is_required": True},
                    ],
                },
            ],
        },
        format="json",
    )
    assert saved.status_code == 200
    assert [row["name"] for row in saved.data["stages"]] == ["共同基础", "延伸应用"]
    assert [str(row["work"]) for row in saved.data["items"]] == [
        str(first.id),
        str(second.id),
        str(third.id),
    ]
    assert [row["position"] for row in saved.data["items"]] == [0, 1, 0]

    stale = api_client.patch(
        f"/api/catalog/admin/theory-system/reading-paths/{path.id}/",
        {
            "expected_updated_at": expected,
            "stage_groups": [],
        },
        format="json",
    )
    assert stale.status_code == 400
    assert "expected_updated_at" in stale.data["error"]["detail"]
