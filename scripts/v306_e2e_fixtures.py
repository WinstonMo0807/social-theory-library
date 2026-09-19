"""Deterministic, synthetic records ONLY for the disposable loopback E2E DB.

Never imported by the application. Publication/worker integration scenarios
must use their real commands; these records are layout/query fixtures only.
"""
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone


LONG_SOURCE = "依据：隔离测试用的长出处，社会理论与历史语境中的关系、版本及页码说明。" * 8
LONG_WORD = "InterdisciplinarySocialTheoreticalReconstructionWithoutWhitespace" * 3


def seed_v306(owner):
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3" or "stl-v305-e2e-" not in settings.DATABASES["default"]["NAME"]:
        raise RuntimeError("Synthetic v306 fixtures require the disposable E2E SQLite database")
    from catalog.models import Person, ScholarProfile, Topic, TheorySchool, KnowledgeNode, KnowledgeRelation, ReadingPath, ReadingPathStage, ReadingPathItem
    from catalog.services.cataloging_sessions import open_cataloging_session
    from ingestion.models import UploadBatch, UploadItem

    person = Person.objects.create(id="30600000-0000-4000-8000-000000000200", preferred_name="V306布局学者", authority_status="verified", biography="长中文传记。" * 90)
    ScholarProfile.objects.create(id="30600000-0000-4000-8000-000000000201", person=person, slug="v306-layout-scholar", editorial_status="published",
        short_description="仅用于布局、保存预览与读取验收的隔离测试人物。",
        timeline=[["1901", "两项时间线的正文应使用剩余宽度。" * 8], ["2026", LONG_WORD]],
        curation={"key_concepts":[{"name":"长中文概念与多版本身份", "description":"概念说明不应隐藏或删减。"*16, "source":LONG_SOURCE}, {"name":LONG_WORD,"description":"英文长词同样需要可阅读。", "source":"独立测试出处"}]})
    Topic.objects.create(id="30600000-0000-4000-8000-000000000202", name="V306布局主题", slug="v306-layout-topic", editorial_status="published",
        description="主题概念和时间线的真实页面测试", timeline=[["1901","起点","标题与正文共同占据第二列。"*15],["2026",LONG_WORD,"长词不能挤掉其他内容。"]], key_concepts=["概念一",LONG_WORD])
    TheorySchool.objects.create(id="30600000-0000-4000-8000-000000000203", name="V306兼容理论", slug="v306-layout-legacy", editorial_status="published",
        description="保留原有兼容理论页面", curation={"core_concepts":[{"name":LONG_WORD,"description":"兼容理论概念正文。"*14,"source":LONG_SOURCE}]})
    node = KnowledgeNode.objects.create(id="30600000-0000-4000-8000-000000000204", canonical_name_zh="V306规范理论长标题"*4, canonical_name_en=LONG_WORD, slug="v306-layout-node", node_type="theory_tradition", status="published", definition="理论定义与证据的边界。"*40, core_questions=["第一问题", "第二问题"], basic_propositions=["命题一", "命题二"])
    related = KnowledgeNode.objects.create(canonical_name_zh=LONG_WORD, canonical_name_en=LONG_WORD, slug="v306-layout-related", node_type="concept", status="published", summary="长名称关系目标")
    KnowledgeRelation.objects.create(source_node=node, target_node=related, relation_type="extends", description="关系说明"*30, status="published")
    # More than one API page, with tied ordering fields. Private synthetic
    # records exercise real pagination; they do not simulate publication jobs.
    from catalog.models import TheoryReviewTask, TheoryTimelineEvent, TimelineEventRelation
    page_nodes = KnowledgeNode.objects.bulk_create([
        KnowledgeNode(canonical_name_zh=f"V306-LIST-{index:02d}", slug=f"v306-list-{index:02d}", node_type="concept", status="draft")
        for index in range(35)
    ])
    KnowledgeRelation.objects.bulk_create([
        KnowledgeRelation(source_node=node, target_node=target, relation_type="criticizes", description=f"V306-LIST-{index:02d}", evidence_source="隔离分页测试资料", status="pending")
        for index, target in enumerate(page_nodes)
    ])
    page_events = TheoryTimelineEvent.objects.bulk_create([
        TheoryTimelineEvent(title=f"V306-LIST-{index:02d}", description="隔离分页测试事件", start_year=1900, event_type="development", review_status="suggested")
        for index in range(35)
    ])
    TimelineEventRelation.objects.bulk_create([TimelineEventRelation(event=event, node=node) for event in page_events])
    TheoryReviewTask.objects.bulk_create([
        TheoryReviewTask(task_type="new_node", suggested_node_name=f"V306-LIST-{index:02d}", evidence_text="隔离分页测试原文", status="pending")
        for index in range(35)
    ])
    reading_path = ReadingPath.objects.create(id="30600000-0000-4000-8000-000000000205", title="V306阅读路径长中文标题"*4, slug="v306-layout-path", status="published", introduction="阅读阶段保留原始身份及完整说明。"*25)
    stage = ReadingPathStage.objects.create(reading_path=reading_path, name=LONG_WORD[:150], position=0)
    ReadingPathItem.objects.create(reading_path=reading_path, stage=stage, stage_name=LONG_WORD[:150], stage_description="阅读阶段说明与长中文材料。"*40, node=node, recommendation_reason="请核对理论和关系的真实内容。", position=0, reading_order=0)
    for index in range(45):
        open_cataloging_session(actor=owner, source_type="manual", title=f"V306-PAGE-{index:02d} 手工书目", document_type="report", language="zh-CN")
    # Synthetic initial active snapshots only; primary UI commands use the real API.
    from tests.test_primary_editions_v306 import pair
    pair()
    batch = UploadBatch.objects.create(created_by=owner, label="V306较早上传异常", source="local-e2e", expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="V306-OLD-ERROR.pdf", status="failed", error_code="fixture_source_missing", error_message="隔离测试：原来源待重新提交，尚未建立版本")
    UploadItem.objects.filter(pk=item.pk).update(updated_at=timezone.now()-timedelta(days=90))

    # Controlled HTTP failure injection for the server-side manifest request.
    # These paths contain no real file/object data and exist only in this test
    # server, never in production URL configuration or a successful response.
    import config.urls
    def fail_response(code):
        return lambda request: JsonResponse({"detail":"Isolated A29 fault injection"}, status=code)
    config.urls.urlpatterns[0:0] = [
        path(f"api/catalog/assets/30600000-0000-4000-8000-000000{code:06d}/manifest/", fail_response(code))
        for code in (401,403,404,409,429,503)
    ]
