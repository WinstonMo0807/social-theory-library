from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from catalog.models import (
    AboutPageBlock,
    Discipline,
    DocumentType,
    Edition,
    Person,
    PublicationState,
    PersonSubdisciplineRelation,
    RecommendationPolicy,
    RecommendationSnapshot,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheoryRelation,
    TheorySchool,
    TheoryTimelineEvent,
    Topic,
    TopicDisciplineRelation,
    Work,
)
from catalog.services.recommendations import current_snapshot, generate_snapshot


def create_published_work(title: str, document_type: str, year: int):
    work = Work.objects.create(
        document_type=document_type,
        title=title,
        language="zh-CN",
    )
    Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        publication_year=year,
        public_slug=f"work-{year}-{document_type}",
    )
    return work


def create_scholar(name: str, slug: str, *, status: str = "published"):
    person = Person.objects.create(preferred_name=name, original_name=f"{name} Original")
    return ScholarProfile.objects.create(
        person=person,
        slug=slug,
        short_description=f"{name}简介",
        editorial_status=status,
    )


@pytest.mark.django_db
def test_recommendations_are_shared_rotate_together_and_accept_all_document_types(
    api_client,
    admin_user,
):
    works = [
        create_published_work("推荐图书", DocumentType.BOOK, 2020),
        create_published_work("推荐论文", DocumentType.JOURNAL_ARTICLE, 2021),
        create_published_work("推荐学位论文", DocumentType.THESIS, 2022),
        create_published_work("推荐报告", DocumentType.REPORT, 2023),
    ]
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_FEATURED,
    )
    policy.item_count = 4
    policy.rotation_days = 3
    policy.save(update_fields=["item_count", "rotation_days", "updated_at"])

    first = api_client.get("/api/catalog/recommendations/")
    second = api_client.get("/api/catalog/recommendations/")
    assert first.status_code == 200
    assert first.data["shared_for_all_readers"] is True
    first_group = first.data["placements"]["home_featured"]["current"]
    second_group = second.data["placements"]["home_featured"]["current"]
    assert first_group["id"] == second_group["id"]
    assert {item["target"]["document_type"] for item in first_group["items"]} == {
        DocumentType.BOOK,
        DocumentType.JOURNAL_ARTICLE,
        DocumentType.THESIS,
        DocumentType.REPORT,
    }

    api_client.force_authenticate(admin_user)
    manual = api_client.post(
        "/api/catalog/admin/recommendations/home_featured/refresh/",
        {
            "items": [
                {"target_type": "work", "id": str(works[3].id)},
                {"target_type": "work", "id": str(works[0].id)},
            ]
        },
        format="json",
    )
    assert manual.status_code == 200
    snapshot = manual.data["current"]
    assert snapshot["source"] == "manual"
    assert [item["target"]["title"] for item in snapshot["items"]] == ["推荐报告", "推荐图书"]
    starts = datetime.fromisoformat(snapshot["starts_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(snapshot["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=2, hours=23) < expires - starts < timedelta(days=3, minutes=1)

    api_client.force_authenticate(None)
    public_after_manual = api_client.get("/api/catalog/recommendations/")
    assert public_after_manual.data["placements"]["home_featured"]["current"]["id"] == snapshot["id"]


@pytest.mark.django_db
def test_scholar_recommendations_preserve_manual_order_and_reject_invalid_items(
    api_client,
    admin_user,
):
    scholars = [
        create_scholar("推荐学者甲", "recommended-scholar-a"),
        create_scholar("推荐学者乙", "recommended-scholar-b"),
        create_scholar("推荐学者丙", "recommended-scholar-c"),
        create_scholar("推荐学者丁", "recommended-scholar-d"),
    ]
    draft = create_scholar("草稿学者", "draft-scholar", status="draft")
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_SCHOLARS,
    )
    policy.item_count = 3
    policy.rotation_days = 3
    policy.save(update_fields=["item_count", "rotation_days", "updated_at"])
    api_client.force_authenticate(admin_user)

    candidates = api_client.get(
        "/api/catalog/admin/scholars/",
        {"editorial_status": "published", "search": "推荐学者"},
    )
    assert candidates.status_code == 200
    assert candidates.data["count"] == 4
    assert all(item["editorial_status"] == "published" for item in candidates.data["results"])

    ordered_ids = [scholars[2].id, scholars[0].id]
    manual = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {
            "items": [
                {"target_type": "scholar", "id": str(identifier)}
                for identifier in ordered_ids
            ]
        },
        format="json",
    )

    assert manual.status_code == 200
    assert manual.data["current"]["source"] == RecommendationSnapshot.Source.MANUAL
    manual_items = manual.data["current"]["items"]
    assert len(manual_items) == 3
    assert [item["target"]["name"] for item in manual_items[:2]] == [
        "推荐学者丙",
        "推荐学者甲",
    ]
    assert manual_items[2]["target"]["name"] in {"推荐学者乙", "推荐学者丁"}
    assert [item["reason"] for item in manual_items[:2]] == ["管理员策展", "管理员策展"]
    assert manual_items[2]["reason"] == "三天自动补足"
    starts = datetime.fromisoformat(manual.data["current"]["starts_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(manual.data["current"]["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=2, hours=23) < expires - starts < timedelta(days=3, minutes=1)
    current_id = manual.data["current"]["id"]

    duplicate = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {
            "items": [
                {"target_type": "scholar", "id": str(scholars[0].id)},
                {"target_type": "scholar", "id": str(scholars[0].id)},
            ]
        },
        format="json",
    )
    assert duplicate.status_code == 400
    assert "重复" in duplicate.data["items"][0]

    too_many = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {
            "items": [
                {"target_type": "scholar", "id": str(scholar.id)}
                for scholar in scholars
            ]
        },
        format="json",
    )
    assert too_many.status_code == 400
    assert "最多" in too_many.data["items"][0]

    unpublished = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {"items": [{"target_type": "scholar", "id": str(draft.id)}]},
        format="json",
    )
    assert unpublished.status_code == 400
    assert "尚未公开" in unpublished.data["items"][0]

    wrong_type = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {"items": [{"target_type": "work", "id": str(scholars[0].id)}]},
        format="json",
    )
    assert wrong_type.status_code == 400
    assert "类型" in wrong_type.data["items"][0]
    assert str(RecommendationSnapshot.objects.get(policy=policy, is_current=True).id) == current_id

    api_client.force_authenticate(None)
    public = api_client.get("/api/catalog/recommendations/")
    assert public.status_code == 200
    assert public.data["placements"]["home_scholars"]["current"]["id"] == current_id

    manual_snapshot = RecommendationSnapshot.objects.get(pk=current_id)
    automatic = current_snapshot(policy, now=manual_snapshot.expires_at)
    assert automatic.id != manual_snapshot.id
    assert automatic.source == RecommendationSnapshot.Source.AUTOMATIC


@pytest.mark.django_db
def test_archived_scholar_is_removed_while_valid_manual_priority_is_preserved(
    api_client,
    admin_user,
):
    scholars = [
        create_scholar(f"下线边界学者{index}", f"archive-boundary-scholar-{index}")
        for index in range(5)
    ]
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_SCHOLARS,
    )
    policy.item_count = 3
    policy.save(update_fields=["item_count", "updated_at"])
    api_client.force_authenticate(admin_user)
    manual = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {
            "items": [
                {"target_type": "scholar", "id": str(scholars[0].id)},
                {"target_type": "scholar", "id": str(scholars[1].id)},
            ]
        },
        format="json",
    )
    assert manual.status_code == 200
    old_snapshot_id = manual.data["current"]["id"]

    ScholarProfile.objects.filter(pk=scholars[0].id).update(editorial_status="archived")
    public = api_client.get("/api/catalog/recommendations/")

    assert public.status_code == 200
    current = public.data["placements"]["home_scholars"]["current"]
    assert current["id"] != old_snapshot_id
    assert current["source"] == RecommendationSnapshot.Source.MANUAL
    assert len(current["items"]) == 3
    assert current["items"][0]["target"]["id"] == str(scholars[1].id)
    assert current["items"][0]["reason"] == "管理员策展"
    assert str(scholars[0].id) not in {
        item["target"]["id"]
        for item in current["items"]
    }
    for item in current["items"]:
        detail = api_client.get(f"/api/catalog/scholars/{item['target']['slug']}/")
        assert detail.status_code == 200


@pytest.mark.django_db
def test_stale_due_check_does_not_replace_a_newer_manual_snapshot():
    scholar = create_scholar("并发人工学者", "concurrent-manual-scholar")
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_SCHOLARS,
    )
    policy.item_count = 1
    policy.save(update_fields=["item_count", "updated_at"])
    stale_checked_at = timezone.now()
    manual_started_at = stale_checked_at + timedelta(seconds=1)
    manual = generate_snapshot(
        policy,
        selected_targets=[scholar],
        source=RecommendationSnapshot.Source.MANUAL,
        now=manual_started_at,
    )

    with patch(
        "catalog.services.recommendations.timezone.now",
        return_value=manual_started_at + timedelta(seconds=1),
    ):
        resolved = current_snapshot(policy, now=stale_checked_at)

    assert resolved.id == manual.id
    assert resolved.source == RecommendationSnapshot.Source.MANUAL
    assert RecommendationSnapshot.objects.filter(policy=policy, is_current=True).count() == 1


@pytest.mark.django_db
def test_admin_random_scholar_refresh_is_automatic_and_due_rotation_is_stable(
    api_client,
    admin_user,
):
    for index in range(6):
        create_scholar(f"自动推荐学者{index}", f"automatic-scholar-{index}")
    policy = RecommendationPolicy.objects.get(
        placement=RecommendationPolicy.Placement.HOME_SCHOLARS,
    )
    policy.item_count = 3
    policy.rotation_days = 3
    policy.save(update_fields=["item_count", "rotation_days", "updated_at"])
    api_client.force_authenticate(admin_user)

    refreshed = api_client.post(
        "/api/catalog/admin/recommendations/home_scholars/refresh/",
        {},
        format="json",
    )
    assert refreshed.status_code == 200
    assert refreshed.data["current"]["source"] == RecommendationSnapshot.Source.AUTOMATIC
    assert len(refreshed.data["current"]["items"]) == 3

    first = RecommendationSnapshot.objects.get(pk=refreshed.data["current"]["id"])
    due_at = first.expires_at + timedelta(seconds=1)
    rotated = current_snapshot(policy, now=due_at)
    repeated = current_snapshot(policy, now=due_at)

    assert rotated.id == repeated.id
    assert rotated.id != first.id
    assert rotated.source == RecommendationSnapshot.Source.AUTOMATIC
    assert RecommendationSnapshot.objects.filter(policy=policy, is_current=True).count() == 1


@pytest.mark.django_db
def test_future_discipline_appears_in_matrix_without_forcing_classification(
    api_client,
    admin_user,
):
    api_client.force_authenticate(admin_user)
    created = api_client.post(
        "/api/catalog/admin/disciplines/",
        {
            "name": "传播学",
            "foreign_name": "Communication Studies",
            "code": "communication-studies",
            "slug": "communication-studies",
            "description": "为后续扩展添加的学科入口。",
            "editorial_status": "published",
            "sort_order": 40,
        },
        format="json",
    )
    assert created.status_code == 201
    api_client.force_authenticate(None)
    matrix = api_client.get("/api/catalog/knowledge-matrix/")
    assert matrix.status_code == 200
    assert any(row["slug"] == "communication-studies" for row in matrix.data["disciplines"])
    work = create_published_work("未归入学科的馆藏", DocumentType.REPORT, 2025)
    assert work.discipline_relations.count() == 0


@pytest.mark.django_db
def test_public_timeline_and_graph_only_use_approved_evidence(api_client):
    discipline = Discipline.objects.get(code="sociology")
    source = TheorySchool.objects.create(
        name="证据源理论",
        slug="evidence-source",
        editorial_status="published",
    )
    approved_target = TheorySchool.objects.create(
        name="已确认理论",
        slug="approved-target",
        editorial_status="published",
    )
    suggested_target = TheorySchool.objects.create(
        name="候选理论",
        slug="suggested-target",
        editorial_status="published",
    )
    TheoryRelation.objects.create(
        source_theory=source,
        target_theory=approved_target,
        relation_type=TheoryRelation.RelationType.INFLUENCE,
        evidence_text="管理员确认的理论史证据。",
        review_status=RelationReviewStatus.APPROVED,
    )
    TheoryRelation.objects.create(
        source_theory=source,
        target_theory=suggested_target,
        relation_type=TheoryRelation.RelationType.ADJACENT,
        evidence_text="尚未确认的系统建议。",
        review_status=RelationReviewStatus.SUGGESTED,
    )
    TheoryTimelineEvent.objects.create(
        discipline=discipline,
        theory_school=source,
        title="已确认事件",
        event_type=TheoryTimelineEvent.EventType.FORMATION,
        start_year=1920,
        evidence_text="有来源的历史事件。",
        review_status=RelationReviewStatus.APPROVED,
    )
    TheoryTimelineEvent.objects.create(
        discipline=discipline,
        theory_school=source,
        title="候选事件",
        event_type=TheoryTimelineEvent.EventType.DEVELOPMENT,
        start_year=1930,
        review_status=RelationReviewStatus.SUGGESTED,
    )

    timeline = api_client.get("/api/catalog/theory-timeline/", {"discipline": "sociology"})
    assert [row["title"] for row in timeline.data["results"]] == ["已确认事件"]
    graph = api_client.get("/api/catalog/theory-graph/")
    edge_targets = {edge["target"] for edge in graph.data["edges"]}
    assert str(approved_target.id) in edge_targets
    assert str(suggested_target.id) not in edge_targets


@pytest.mark.django_db
def test_public_subdiscipline_list_serializes_related_scholars(api_client):
    discipline = Discipline.objects.get(code="sociology")
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="城市社会学测试",
        slug="urban-sociology-test",
        editorial_status="published",
    )
    person = Person.objects.create(preferred_name="城市学者测试")
    scholar = ScholarProfile.objects.create(
        person=person,
        slug="urban-scholar-test",
        editorial_status="published",
    )
    PersonSubdisciplineRelation.objects.create(
        person=scholar.person,
        subdiscipline=subdiscipline,
        review_status=RelationReviewStatus.APPROVED,
    )

    response = api_client.get("/api/catalog/subdisciplines/")

    assert response.status_code == 200
    row = next(item for item in response.data["results"] if item["slug"] == subdiscipline.slug)
    assert row["scholars"][0]["slug"] == scholar.slug


@pytest.mark.django_db
def test_public_topic_list_filters_by_approved_discipline_relation(api_client):
    discipline = Discipline.objects.get(code="sociology")
    approved_topic = Topic.objects.create(
        name="已确认学科主题",
        slug="approved-discipline-topic",
        editorial_status="published",
    )
    suggested_topic = Topic.objects.create(
        name="候选学科主题",
        slug="suggested-discipline-topic",
        editorial_status="published",
    )
    TopicDisciplineRelation.objects.create(
        topic=approved_topic,
        discipline=discipline,
        review_status=RelationReviewStatus.APPROVED,
    )
    TopicDisciplineRelation.objects.create(
        topic=suggested_topic,
        discipline=discipline,
        review_status=RelationReviewStatus.SUGGESTED,
    )

    response = api_client.get(
        "/api/catalog/topics/",
        {"discipline": discipline.slug, "sort": "works"},
    )

    assert response.status_code == 200
    assert [row["slug"] for row in response.data["results"]] == [approved_topic.slug]


@pytest.mark.django_db
def test_about_page_reports_configured_even_when_a_slot_is_hidden(api_client):
    AboutPageBlock.objects.filter(key="about-why").update(visible=False)
    response = api_client.get("/api/catalog/about-blocks/")
    assert response.status_code == 200
    assert response.data["configured"] is True
    assert not any(row["key"] == "about-why" for row in response.data["results"])


@pytest.mark.django_db
def test_admin_can_upload_scholar_portrait(api_client, admin_user, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_API_URL = "http://testserver"
    api_client.force_authenticate(admin_user)
    created = api_client.post(
        "/api/catalog/admin/scholars/",
        {
            "preferred_name": "测试学者肖像",
            "original_name": "Portrait Scholar",
            "editorial_status": "draft",
        },
        format="json",
    )
    assert created.status_code == 201

    output = BytesIO()
    Image.new("RGB", (240, 320), color=(80, 80, 80)).save(output, format="PNG")
    portrait = SimpleUploadedFile(
        "portrait.png",
        output.getvalue(),
        content_type="image/png",
    )
    updated = api_client.patch(
        f"/api/catalog/admin/scholars/{created.data['id']}/",
        {"portrait": portrait},
        format="multipart",
    )
    assert updated.status_code == 200
    assert updated.data["portrait"].endswith(".png")
    profile = ScholarProfile.objects.select_related("person").get(pk=created.data["id"])
    assert profile.person.portrait.name.startswith("public/people/")
