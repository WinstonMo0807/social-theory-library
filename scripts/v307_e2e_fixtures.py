"""Small synthetic layout data for the existing disposable local UI server only."""
from django.conf import settings
from django.utils import timezone


def seed_v307(owner):
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3" or "stl-v305-e2e-" not in settings.DATABASES["default"]["NAME"]:
        raise RuntimeError("v307 fixtures require the disposable loopback database")
    from catalog.models import (CatalogPublicationRevision, Contribution, Discipline, Edition, KnowledgeNode,
        KnowledgeNodeDiscipline, KnowledgeNodeSubdiscipline, KnowledgeRelation, Person, ScholarProfile,
        Subdiscipline, TheoryTimelineEvent, TimelineEventRelation, Topic, Work)
    from catalog.services.knowledge_publication import catalog_snapshot
    from catalog.services import editorial_issues

    discipline = Discipline.objects.create(name="社会学 · 隔离演示", slug="v307-sociology", code="v307-sociology", editorial_status="published", introduction="这是用于页面验收的合成内容。由真实API提供，保留学科、理论与文献之间的独立关系。")
    sub = Subdiscipline.objects.create(discipline=discipline, name="文化社会学 · 隔离演示", slug="v307-culture", editorial_status="published", research_object="理解文化实践与社会关系的联系。仅为界面测试说明。", core_questions=["文化意义如何形成？", "如何核对材料与解释？"], methods=["比较阅读", "历史材料"])
    node = KnowledgeNode.objects.create(canonical_name_zh="关系理论 · 隔离演示", canonical_name_en="Relational theory", slug="v307-theory", node_type="theory_tradition", status="published", primary_discipline=discipline, summary="用于核对理论页面、关系图和原文入口的测试对象。", definition="本段是明确标注的合成说明，不作为学术论据。", core_questions=["关系如何组织行动？", "什么材料支持解释？"], basic_propositions=["逐项比较机制与材料。", "保留证据原文及版本。"], theoretical_boundary="理论说明与来源材料分开显示。")
    concept = KnowledgeNode.objects.create(canonical_name_zh="社会关系 · 隔离演示", slug="v307-concept", node_type="concept", status="published", definition="本概念只用于验证独立概念路由。")
    KnowledgeNodeDiscipline.objects.create(node=node, discipline=discipline, relation_type="primary", status="published")
    KnowledgeNodeSubdiscipline.objects.create(node=node, subdiscipline=sub, status="published")
    KnowledgeRelation.objects.create(source_node=node, target_node=concept, relation_type="extends", description="合成关系说明", evidence_source="隔离测试数据", status="published")
    event = TheoryTimelineEvent.objects.create(title="理论讨论与资料整理 · 隔离演示", description="这是一条合成测试事件。事件名称、年份与来源均不用于真实学术判断。", start_year=2026, event_type="development", review_status="approved", discipline=discipline, source="隔离测试数据")
    TimelineEventRelation.objects.create(event=event, node=node)
    scholars = []
    for index, name in enumerate(("陈一", "林二", "周三", "吴四", "郑五", "许六")):
        person = Person.objects.create(preferred_name=f"{name} · 测试人物", original_name=f"Synthetic Scholar {index + 1}", authority_status="verified", birth_year=1900 + index * 5, biography="这是合成测试人物。传记用于检查排版与编辑预览，不描述任何真实人物。")
        scholar = ScholarProfile.objects.create(person=person, slug=f"v307-scholar-{index}", editorial_status="published", short_description="通过真实知识API呈现的合成学者档案。", key_concerns=["社会关系", "理论阅读"], timeline=[["1920", "合成学习记录"], ["1950", "合成研究记录"]], curation={"key_concepts": [{"name": "社会关系", "description": "合成概念说明", "source": "隔离测试数据"}], "concept_map": [{"source": "社会关系", "target": "行动", "relation": "关联", "description": "合成图谱关系"}]})
        scholars.append(scholar)
    works = []
    for index, title in enumerate(("社会关系的阅读", "日常生活与秩序", "文化与解释", "组织与行动")):
        work = Work.objects.create(title=f"{title} · 测试文献", document_type="book", abstract="用于页面视觉与选择操作的合成书目，不是实际馆藏文献。")
        edition = Edition.objects.create(work=work, state="published", public_slug=f"v307-book-{index}", publication_mode="bibliographic", publication_year=2020 + index, publisher="隔离测试出版信息", version_label="合成书目版")
        Contribution.objects.create(edition=edition, person=scholars[index].person, role="author", approved=True, source="isolated-v307")
        snapshot, related = catalog_snapshot(edition)
        revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True, snapshot=snapshot, related_entities=related, activated_at=timezone.now())
        edition.active_catalog_revision = revision
        edition.save(update_fields=["active_catalog_revision", "updated_at"])
        works.append(edition)
    for index, name in enumerate(("现代社会", "文化与意义", "知识与权力", "城市与空间", "劳动与组织")):
        Topic.objects.create(name=f"{name} · 隔离演示", slug=f"v307-topic-{index}", editorial_status="published", description="基于合成内容检验主题页面的真实数据呈现。", problem_statement="如何在材料中识别问题并核对不同解释？", core_questions=["问题如何产生？", "解释与证据如何对应？"], research_dimensions=["制度", "实践", "历史"], methods=["比较阅读", "过程分析"], formation_context="仅用于界面验收的合成形成说明。", timeline=[["2020", "合成起点", "用于时间线显示"]], key_concepts=["关系", "行动", "制度"])
    issue = editorial_issues.create_issue({"title": "关系与日常生活", "slug": "v307-test-issue", "issue_label": "隔离测试期", "public_byline": "测试策展", "introduction": "沿着社会关系的线索，阅读日常生活与组织。本期内容完全为隔离验收所建，不会发布到生产书库。", "body_blocks": [{"type": "paragraph", "text": "从具体问题开始，将概念、作品和原文位置连接起来。此处使用真实的草稿保存与发布服务。"}], "items": [{"kind": "catalog", "work_id": str(edition.work_id), "edition_id": str(edition.pk), "note": "合成推介语，用于核对书目展示与真实跳转。"} for edition in works] + [{"kind": "planned", "title": "待上架的测试文献", "authors": "测试作者", "note": "计划项保留独立编目身份。"}]}, owner)
    editorial_issues.publish_issue(issue.pk, editorial_issues.issue_payload(issue)["edit_version"], owner)
