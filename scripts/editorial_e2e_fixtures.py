"""Synthetic articles for the disposable acceptance database only."""
def seed_editorial(actor):
    from timeline_e2e_fixtures import _isolated
    from uuid import uuid4
    _isolated()
    from catalog.services import editorial_issues, shared_curation
    from catalog.services.publication_eligibility import public_editions
    from catalog.models import Topic, ScholarProfile, ReadingPath

    span = shared_curation.sources("span", public=True).filter(is_stale=False,document_revision_id__isnull=False).first()
    edition = span.page.asset.edition if span else public_editions().first()
    metadata = {"keywords": ["EDITORIAL74测试"], "curator_role": "测试策划者", "curator_affiliation": "隔离验收环境",
        "topic_ids": [str(row.pk) for row in Topic.objects.filter(editorial_status="published")[:1]],
        "scholar_ids": [str(row.pk) for row in ScholarProfile.objects.filter(editorial_status="published")[:1]],
        "reading_path_ids": [str(row.pk) for row in ReadingPath.objects.filter(status="published")[:1]]}
    for index in range(14):
        section_id = str(uuid4())
        blocks = [{"id":section_id,"type":"heading", "text":"测试章节一"}, {"type":"paragraph", "text":"这是隔离环境的策划测试内容，不是真实学术论述。"},
            {"type":"heading", "text":"测试章节二"}, {"type":"paragraph", "text":"用于目录与移动阅读验收。"}]
        if index == 0 and span:
            blocks.append({"type":"evidence", "text":"测试原文入口", "target":{"type":"span","id":str(span.pk),"document_revision_id":str(span.document_revision_id)}})
        if index == 1:
            blocks.append({"type":"image", "text":"测试缺图展项", "alt_text":"没有图片时保留的测试说明", "source":"本地测试资料，不是历史图像", "image_rendition_id":None})
        row = editorial_issues.create_issue({"title":f"EDITORIAL74测试文章{index:02}", "slug":f"stl4-editorial-{index}", "introduction":"仅供本地隔离验收，禁止用于生产内容。",
            "public_byline":"测试署名, 甲", "article_metadata":{**metadata,"kind":"exhibition" if index == 1 else "article"}, "body_blocks":blocks,
            "items":[{"kind":"catalog","work_id":str(edition.work_id),"edition_id":str(edition.pk),"section_id":section_id}] if edition else []},actor)
        editorial_issues.publish_issue(row.pk, editorial_issues.edit_version("recommendation_issue",row.pk),actor)
