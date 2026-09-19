"""A14/A32: private draft-aware version checks, not public state guesses."""

import pytest

from catalog.models import Discipline, EditorialRevision, KnowledgeNode, Person, ReadingPath, ScholarProfile, Subdiscipline, Topic

pytestmark = pytest.mark.django_db


def object_editor(kind, published):
    state = "published" if published else "draft"
    if kind == "scholars":
        person = Person.objects.create(preferred_name="版本保护学者", authority_status="verified")
        row = ScholarProfile.objects.create(person=person, slug="version-scholar", editorial_status=state, short_description="旧内容")
        field, target = "short_description", "scholar_profile"
    elif kind == "topics":
        row = Topic.objects.create(name="版本保护主题", slug="version-topic", editorial_status=state, description="旧内容")
        field, target = "description", "topic"
    elif kind == "disciplines":
        row = Discipline.objects.create(name="版本保护学科", code="version-discipline", slug="version-discipline", editorial_status=state, description="旧内容")
        field, target = "description", "discipline"
    elif kind == "subdisciplines":
        row = Subdiscipline.objects.create(name="版本保护子学科", slug="version-subdiscipline", discipline=Discipline.objects.create(name="上级", code="version-parent", slug="version-parent"), editorial_status=state, description="旧内容")
        field, target = "description", "subdiscipline"
    elif kind == "theory-system/nodes":
        row = KnowledgeNode.objects.create(canonical_name_zh="版本保护理论", node_type="theory_tradition", slug="version-theory", status=state, summary="旧内容")
        field, target = "summary", "knowledge_node"
    else:
        row = ReadingPath.objects.create(title="版本保护阅读路径", slug="version-path", status=state, introduction="旧内容")
        field, target = "introduction", "reading_path"
    return row, f"/api/catalog/admin/{kind}/{row.pk}/", field, target


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("kind", ["scholars", "topics", "disciplines", "subdisciplines", "theory-system/nodes", "theory-system/reading-paths"])
def test_two_editors_cannot_overwrite_a_saved_draft_or_unpublished_record(api_client, admin_user, kind, published):
    row, url, field, target = object_editor(kind, published)
    api_client.force_authenticate(admin_user)
    first = api_client.get(url)
    assert first.status_code == 200
    version = first.data["edit_version"]
    assert len(version) == 64 and first["Cache-Control"] == "private, no-store"
    missing = api_client.patch(url, {field: "没有版本不应保存"}, format="json")
    assert missing.status_code == 428
    changed = api_client.patch(url, {field: "第一位编辑保存"}, format="json", HTTP_IF_MATCH=version)
    assert changed.status_code == (202 if published else 200), changed.data
    assert changed.data["edit_version"] != version
    stale = api_client.patch(url, {field: "第二位编辑的旧页面"}, format="json", HTTP_IF_MATCH=version)
    assert stale.status_code == 409 and stale.data["code"] == "edit_conflict"
    assert api_client.get(url).data[field] == "第一位编辑保存"
    row.refresh_from_db()
    if published:
        assert getattr(row, field) == "旧内容"
        assert EditorialRevision.objects.filter(target_type=target, target_id=row.pk, status="draft").count() == 1
        following = api_client.patch(url, {"slug": f"follow-{row.pk}"}, format="json", HTTP_IF_MATCH=changed.data["edit_version"])
        assert following.status_code == 202, following.data
        assert following.data[field] == "第一位编辑保存"
        assert EditorialRevision.objects.filter(target_type=target, target_id=row.pk, status="draft").count() == 1
    else:
        assert getattr(row, field) == "第一位编辑保存"


def test_scholar_person_change_also_invalidates_editor_version(api_client, admin_user):
    row, url, field, _ = object_editor("scholars", True)
    api_client.force_authenticate(admin_user)
    version = api_client.get(url).data["edit_version"]
    row.person.preferred_name = "另一个入口保存的名字"
    row.person.save()
    response = api_client.patch(url, {field: "过时输入"}, format="json", HTTP_IF_MATCH=version)
    assert response.status_code == 409
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()


def test_reader_cannot_obtain_or_use_editorial_versions(api_client, reader_user):
    _row, url, field, _ = object_editor("topics", True)
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    assert api_client.patch(url, {field: "禁止"}, format="json", HTTP_IF_MATCH="*" ).status_code == 403
    api_client.force_authenticate(None)
    public = api_client.get("/api/catalog/topics/version-topic/")
    assert public.status_code == 200
    assert "edit_version" not in public.data and "editorial_revision" not in public.data
