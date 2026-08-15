from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    Discipline,
    DocumentType,
    Edition,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeMergeRecord,
    KnowledgeRelation,
    Page,
    Passage,
    PublicationState,
    ReadingPath,
    ReadingPathItem,
    TheoryTimelineEvent,
    TimelineEventRelation,
    TheoryReviewTask,
    Topic,
    Work,
    WorkKnowledgeRelation,
    WorkNodeRelation,
)
from catalog.serializers import AdminTopicSerializer
from catalog.services.knowledge_nodes import merge_nodes, rollback_merge
from catalog.services.theory_suggestions import generate_theory_review_tasks


def make_work(title="理论测试馆藏"):
    work = Work.objects.create(document_type=DocumentType.BOOK, title=title, language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        publication_year=2026,
        public_slug=f"work-{work.id}",
        state=PublicationState.PUBLISHED,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("test.pdf", b"%PDF-1.4 theory test"),
        sha256=str(work.id).replace("-", "") * 2,
        byte_size=24,
        page_count=12,
        status=Asset.Status.READY,
        extraction_method="text_layer",
    )
    return work, edition, asset


@pytest.mark.django_db
def test_public_nodes_only_show_published_and_support_multiple_disciplines(api_client):
    sociology = Discipline.objects.get(code="sociology")
    anthropology = Discipline.objects.get(code="anthropology")
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="跨学科理论",
        canonical_name_en="Cross-disciplinary Theory",
        slug="cross-disciplinary-theory",
        primary_discipline=sociology,
        status="published",
        published_at=timezone.now(),
    )
    KnowledgeNodeDiscipline.objects.create(
        node=node,
        discipline=sociology,
        relation_type="primary",
        status="published",
    )
    KnowledgeNodeDiscipline.objects.create(
        node=node,
        discipline=anthropology,
        relation_type="related",
        status="published",
    )
    KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="尚待审核的争论",
        slug="pending-debate",
        status="pending",
    )

    response = api_client.get("/api/catalog/theory-system/nodes/", {"discipline": "anthropology"})
    assert response.status_code == 200
    names = [row["canonical_name_zh"] for row in response.data["results"]]
    assert names == ["跨学科理论"]
    assert response.data["results"][0]["primary_discipline"]["slug"] == "sociology"
    assert response.data["results"][0]["related_disciplines"][0]["slug"] == "anthropology"


@pytest.mark.django_db
def test_editor_can_draft_but_only_admin_can_publish_node(api_client, admin_user):
    editor = User.objects.create_user(
        username="editor@theory.test",
        email="editor@theory.test",
        role=User.Role.EDITOR,
        password="Editor-Theory-Test-2026",
    )
    api_client.force_authenticate(editor)
    rejected = api_client.post(
        "/api/catalog/admin/theory-system/nodes/",
        {
            "node_type": "theory_tradition",
            "canonical_name_zh": "编辑直接发布",
            "slug": "editor-direct-publish",
            "status": "published",
        },
        format="json",
    )
    assert rejected.status_code == 400

    draft = api_client.post(
        "/api/catalog/admin/theory-system/nodes/",
        {
            "node_type": "theory_tradition",
            "canonical_name_zh": "编辑草稿",
            "slug": "editor-draft",
            "status": "draft",
            "aliases": [{"alias": "编辑别名", "language": "zh-CN", "alias_type": "alias"}],
        },
        format="json",
    )
    assert draft.status_code == 201
    assert KnowledgeNodeAlias.objects.filter(node_id=draft.data["id"], alias="编辑别名").exists()

    api_client.force_authenticate(admin_user)
    published = api_client.patch(
        f"/api/catalog/admin/theory-system/nodes/{draft.data['id']}/",
        {"status": "published"},
        format="json",
    )
    assert published.status_code == 200
    assert published.data["published_at"]
    assert KnowledgeNode.objects.get(pk=draft.data["id"]).versions.count() == 2


@pytest.mark.django_db
def test_graph_honors_two_level_and_thirty_node_hard_limits(api_client):
    nodes = [
        KnowledgeNode.objects.create(
            node_type="theory_tradition",
            canonical_name_zh=f"图谱理论 {index}",
            slug=f"graph-theory-{index}",
            status="published",
        )
        for index in range(36)
    ]
    for target in nodes[1:]:
        KnowledgeRelation.objects.create(
            source_node=nodes[0],
            target_node=target,
            relation_type="influenced_by",
            status="published",
        )

    response = api_client.get(
        "/api/catalog/theory-system/graph/",
        {"center": nodes[0].slug, "depth": 9, "limit": 99},
    )
    assert response.status_code == 200
    assert response.data["depth"] == 2
    assert response.data["limit"] == 30
    assert len(response.data["nodes"]) <= 30


@pytest.mark.django_db
def test_review_confirmation_creates_public_relation_and_page_evidence(api_client, admin_user):
    work, _edition, asset = make_work()
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="审核理论",
        slug="reviewed-theory",
        status="published",
    )
    task = TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.WORK_NODE,
        work=work,
        file=asset,
        candidate_node=node,
        suggested_relation_type="systematic_exposition",
        confidence=0.91,
        evidence_pages=[4, 5],
        evidence_text="这段原文系统解释了该理论的核心命题和适用范围。",
    )
    api_client.force_authenticate(admin_user)
    response = api_client.post(
        f"/api/catalog/admin/theory-system/review-tasks/{task.id}/action/",
        {"action": "confirm", "review_note": "证据充分"},
        format="json",
    )
    assert response.status_code == 200
    relation = WorkNodeRelation.objects.get(work=work, node=node)
    assert relation.status == "published"
    evidence = EvidenceSnippet.objects.get(work_node_relation=relation)
    assert evidence.page_number == 4
    assert evidence.page_end == 5
    assert evidence.review_status == "approved"
    assert f"/reader/{asset.id}?page=4" in response.data["viewer_href"]


@pytest.mark.django_db(transaction=True)
def test_node_merge_preserves_source_and_can_roll_back(admin_user):
    source = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="待合并理论",
        slug="source-theory",
        status="published",
    )
    target = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="规范理论",
        slug="target-theory",
        status="published",
    )
    KnowledgeNodeAlias.objects.create(node=source, alias="旧译名")
    work, _edition, _asset = make_work("合并关系测试")
    WorkNodeRelation.objects.create(
        work=work,
        node=source,
        role="foundational_work",
        status="published",
    )

    record = merge_nodes(source.id, target.id, actor=admin_user)
    source.refresh_from_db()
    assert source.status == "archived"
    assert target.aliases.filter(alias="旧译名").exists()
    assert target.work_relations.filter(work=work, role="foundational_work").exists()
    assert KnowledgeNodeMergeRecord.objects.filter(pk=record.pk).exists()

    rollback_merge(record.id, actor=admin_user)
    source.refresh_from_db()
    record.refresh_from_db()
    assert source.status == "published"
    assert record.rolled_back_at is not None
    assert not target.work_relations.filter(work=work, role="foundational_work").exists()


@pytest.mark.django_db
def test_only_published_reading_paths_are_public(api_client):
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="阅读路径理论",
        slug="reading-path-theory",
        status="published",
    )
    public_path = ReadingPath.objects.create(
        title="公开理论入门",
        slug="public-theory-path",
        status="published",
    )
    ReadingPathItem.objects.create(
        reading_path=public_path,
        stage_name="入门",
        node=node,
        reading_order=1,
    )
    ReadingPath.objects.create(title="后台草稿路径", slug="draft-path", status="draft")

    response = api_client.get("/api/catalog/theory-system/reading-paths/")
    assert response.status_code == 200
    assert [row["title"] for row in response.data["results"]] == ["公开理论入门"]
    assert response.data["results"][0]["items"][0]["node_data"]["canonical_name_zh"] == "阅读路径理论"


@pytest.mark.django_db
def test_reading_path_work_cover_uses_same_origin_public_endpoint(api_client):
    work, _edition, _asset = make_work("带封面的阅读路径馆藏")
    work.cover = "public/covers/reading-path-cover.jpg"
    work.save(update_fields=["cover"])
    reading_path = ReadingPath.objects.create(
        title="带封面的公开路径",
        slug="public-path-with-work-cover",
        status="published",
    )
    ReadingPathItem.objects.create(
        reading_path=reading_path,
        stage_name="入门",
        work=work,
        reading_order=1,
    )

    response = api_client.get(
        "/api/catalog/theory-system/reading-paths/public-path-with-work-cover/",
        secure=True,
        HTTP_HOST="127.0.0.1:18000",
    )

    assert response.status_code == 200
    assert response.data["items"][0]["work_data"]["cover_url"] == (
        f"/api/catalog/works/{work.id}/cover/"
    )


@pytest.mark.django_db
def test_pdf_theory_suggestions_are_pending_and_keep_page_evidence(admin_user):
    work, _edition, asset = make_work("乡村互动的经验研究")
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="象征互动论",
        canonical_name_en="Symbolic Interactionism",
        slug="suggested-symbolic-interactionism",
        status="published",
    )
    KnowledgeNodeAlias.objects.create(node=node, alias="符号互动论")
    texts = {
        3: "本文采用象征互动论分析村民在日常交往中如何解释身份，并基于访谈材料展开经验研究。",
        17: "象征互动论强调行动者对情境意义的解释，本文据此分析仪式互动与角色形成。",
        31: "研究发现，互动秩序需要在持续协商中形成，这与符号互动论的基本判断一致。",
    }
    for index, text in texts.items():
        page = Page.objects.create(
            asset=asset,
            index=index,
            printed_label=str(index),
            chapter_title="理论与研究方法" if index == 3 else "经验分析",
            text=text,
            normalized_text=text.casefold(),
            text_source=Page.TextSource.EMBEDDED,
        )
        Passage.objects.create(
            page=page,
            order=0,
            text=text,
            normalized_text=text.casefold(),
            bbox_union=[20, 30, 500, 160],
        )
    asset.page_count = 40
    asset.save(update_fields=["page_count", "updated_at"])

    result = generate_theory_review_tasks(asset, actor=admin_user)

    assert result["created"] == 1
    task = TheoryReviewTask.objects.get(work=work, candidate_node=node)
    assert task.status == TheoryReviewTask.TaskStatus.PENDING
    assert task.suggested_relation_type == WorkNodeRelation.Role.EMPIRICAL_APPLICATION
    assert task.evidence_pages == [3, 17, 31]
    assert "PDF 第 3 页" in task.evidence_text
    relation = WorkNodeRelation.objects.get(work=work, node=node)
    assert relation.status == "pending"
    assert relation.source == "normalized_theory_candidate_v1"
    assert EvidenceSnippet.objects.filter(
        work_node_relation=relation,
        review_status="suggested",
    ).count() == 3

    # The operation is idempotent and never duplicates review work.
    second = generate_theory_review_tasks(asset, actor=admin_user)
    assert second["created"] == 0
    assert TheoryReviewTask.objects.filter(work=work, candidate_node=node).count() == 1


@pytest.mark.django_db
def test_new_node_candidate_can_create_draft_and_followup_relation(api_client, admin_user):
    work, _edition, asset = make_work("新理论候选测试")
    task = TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.NEW_NODE,
        work=work,
        file=asset,
        suggested_node_name="关系过程理论",
        confidence=0.72,
        evidence_pages=[7, 19, 28],
        evidence_text="PDF 第 7 页\n原文讨论关系过程理论如何解释互动秩序。",
    )
    sociology = Discipline.objects.get(code="sociology")
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        f"/api/catalog/admin/theory-system/review-tasks/{task.id}/action/",
        {
            "action": "create_node",
            "node_type": "theory_tradition",
            "primary_discipline": str(sociology.id),
            "relation_type": "systematic_exposition",
        },
        format="json",
    )

    assert response.status_code == 200
    node = KnowledgeNode.objects.get(canonical_name_zh="关系过程理论")
    assert node.status == "draft"
    assert node.primary_discipline == sociology
    assert node.versions.count() == 1
    assert node.discipline_links.filter(discipline=sociology, relation_type="primary").exists()
    relation = WorkNodeRelation.objects.get(
        work=work,
        node=node,
        role="systematic_exposition",
    )
    assert relation.status == "pending"
    assert EvidenceSnippet.objects.filter(
        work_node_relation=relation,
        review_status="suggested",
    ).exists()
    assert TheoryReviewTask.objects.filter(
        task_type=TheoryReviewTask.TaskType.WORK_NODE,
        work=work,
        candidate_node=node,
        status=TheoryReviewTask.TaskStatus.PENDING,
    ).exists()


@pytest.mark.django_db
def test_new_node_candidate_can_become_existing_alias(api_client, admin_user):
    work, _edition, asset = make_work("已有理论别名测试")
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="规范互动理论",
        slug="canonical-interaction-theory",
        status="published",
    )
    task = TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.NEW_NODE,
        work=work,
        file=asset,
        suggested_node_name="互动关系理论",
        confidence=0.68,
        evidence_pages=[9, 16, 22],
        evidence_text="PDF 第 9 页\n原文使用互动关系理论这一译名。",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        f"/api/catalog/admin/theory-system/review-tasks/{task.id}/action/",
        {
            "action": "alias_existing",
            "candidate_node": str(node.id),
            "relation_type": "general_mention",
        },
        format="json",
    )

    assert response.status_code == 200
    assert node.aliases.filter(alias="互动关系理论").exists()
    assert TheoryReviewTask.objects.filter(
        task_type=TheoryReviewTask.TaskType.WORK_NODE,
        work=work,
        candidate_node=node,
        status=TheoryReviewTask.TaskStatus.PENDING,
    ).exists()


@pytest.mark.django_db
def test_work_detail_only_exposes_confirmed_theory_evidence_and_focus(api_client, admin_user):
    work, edition, asset = make_work("理论证据公开测试")
    node = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="证据理论",
        slug="evidence-theory",
        status="published",
    )
    relation = WorkNodeRelation.objects.create(
        work=work,
        node=node,
        role="systematic_exposition",
        status="published",
        reviewed_by=admin_user,
        reviewed_at=timezone.now(),
    )
    Page.objects.create(
        asset=asset,
        index=6,
        printed_label="3",
        text="本页系统说明证据理论。",
        normalized_text="本页系统说明证据理论。",
        text_source=Page.TextSource.EMBEDDED,
        width=600,
        height=900,
    )
    approved = EvidenceSnippet.objects.create(
        work=work,
        file=asset,
        node=node,
        work_node_relation=relation,
        page_number=6,
        printed_page_label="3",
        quote="本页系统说明证据理论。",
        bounding_box={"rect": [40, 70, 520, 150]},
        review_status="approved",
        reviewed_by=admin_user,
        reviewed_at=timezone.now(),
    )
    suggested = EvidenceSnippet.objects.create(
        work=work,
        file=asset,
        node=node,
        work_node_relation=relation,
        page_number=6,
        quote="这条尚未审核。",
        review_status="suggested",
    )

    detail = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert detail.status_code == 200
    assert len(detail.data["theory_associations"]) == 1
    evidence_rows = detail.data["theory_associations"][0]["evidence"]
    assert [row["id"] for row in evidence_rows] == [str(approved.id)]
    assert f"evidence={approved.id}" in evidence_rows[0]["reader_href"]

    focus = api_client.get(f"/api/catalog/theory-system/evidence/{approved.id}/focus/")
    assert focus.status_code == 200
    assert focus.data["page_index"] == 6
    assert focus.data["printed_label"] == "3"
    assert focus.data["bbox"] == [40, 70, 520, 150]
    hidden = api_client.get(f"/api/catalog/theory-system/evidence/{suggested.id}/focus/")
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_timeline_and_graph_apply_backend_filters(api_client):
    sociology = Discipline.objects.get(code="sociology")
    theory = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="二十世纪馆藏理论",
        slug="twentieth-century-collection-theory",
        primary_discipline=sociology,
        start_year=1950,
        status="published",
    )
    outside = KnowledgeNode.objects.create(
        node_type="theory_tradition",
        canonical_name_zh="十九世纪无馆藏理论",
        slug="nineteenth-century-empty-theory",
        primary_discipline=sociology,
        start_year=1880,
        status="published",
    )
    KnowledgeRelation.objects.create(
        source_node=theory,
        target_node=outside,
        relation_type="influenced_by",
        status="published",
    )
    work, _edition, _asset = make_work("图谱筛选馆藏")
    WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        role="foundational_work",
        status="published",
    )
    event = TheoryTimelineEvent.objects.create(
        title="馆藏理论形成",
        event_type=TheoryTimelineEvent.EventType.SCHOOL_FORMATION,
        start_year=1950,
        review_status="approved",
    )
    TimelineEventRelation.objects.create(
        event=event,
        node=theory,
        discipline=sociology,
        work=work,
    )
    TheoryTimelineEvent.objects.create(
        title="尚未审核事件",
        event_type=TheoryTimelineEvent.EventType.DEBATE,
        start_year=1951,
        review_status="suggested",
    )

    timeline = api_client.get(
        "/api/catalog/theory-system/timeline/",
        {
            "discipline": "sociology",
            "node": theory.slug,
            "event_type": "school_formation",
            "has_collection": "true",
        },
    )
    assert timeline.status_code == 200
    assert [row["title"] for row in timeline.data["results"]] == ["馆藏理论形成"]

    graph = api_client.get(
        "/api/catalog/theory-system/graph/",
        {
            "center": theory.slug,
            "node_type": "theory_tradition",
            "start_year": 1940,
            "end_year": 2000,
            "has_collection": "true",
        },
    )
    assert graph.status_code == 200
    node_names = {row["name"] for row in graph.data["nodes"]}
    assert "二十世纪馆藏理论" in node_names
    assert "十九世纪无馆藏理论" not in node_names


@pytest.mark.django_db
def test_topic_excerpt_candidates_include_the_source_text():
    work, _edition, asset = make_work("候选原文说明测试")
    topic = Topic.objects.create(
        name="国家与制度",
        slug="state-and-institutions",
        editorial_status="published",
        key_concepts=["国家", "制度"],
    )
    WorkKnowledgeRelation.objects.create(
        work=work,
        topic=topic,
        approved=True,
        review_status="approved",
    )
    source_text = (
        "国家制度并非抽象规则的简单集合，它通过行政分类、地方组织和日常执行改变社会关系。"
        "本段进一步讨论制度如何塑造行动边界，并说明这种影响为何需要回到具体历史条件中理解。"
        "只有结合行动者的处境与制度执行过程，才能判断规则如何转化为实际的社会秩序。"
    )
    page = Page.objects.create(
        asset=asset,
        index=8,
        printed_label="5",
        text=source_text,
        normalized_text=source_text.casefold(),
        text_source=Page.TextSource.EMBEDDED,
    )
    passage = Passage.objects.create(
        page=page,
        order=0,
        text=source_text,
        normalized_text=source_text.casefold(),
    )

    payload = AdminTopicSerializer(topic).data
    candidate = payload["suggestions"]["passages"][0]

    assert candidate["id"] == str(passage.id)
    assert candidate["description"].startswith("国家制度并非抽象规则")
    assert candidate["page_index"] == 8
    assert candidate["printed_label"] == "5"
