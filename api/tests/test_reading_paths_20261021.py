"""PDF58–60 acceptance definitions; execute only during unified acceptance."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied

from catalog.models import Asset, Edition, EditorialRevision, KnowledgeNode, Page, ReadingPath, ReadingPathItem, ReadingPathStage, Topic, Work
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.public_reading_paths import capture_reading_path_publication, diff_reading_path_snapshots, preview_reading_path, public_reading_path_snapshot
from catalog.services.reading_paths import ReadingPathStructureError, normalize_reading_path_stage_groups, reading_path_stage_groups, stage_groups_from_items, sync_reading_path_stage_groups
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db
URL = "/api/catalog/theory-system/reading-paths/"


def source(*, fulltext=True, title="合成路径材料"):
    work = Work.objects.create(title=title)
    edition = Edition.objects.create(work=work, state="published", public_slug=f"path-source-{uuid4()}", is_primary=True,
        publication_mode="document" if fulltext else "bibliographic")
    asset = None
    if fulltext:
        asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
            file="acceptance-only/synthetic.pdf", sha256="a" * 64, page_count=2, access_status="public", is_current=True)
        Page.objects.create(asset=asset, index=1, text="Synthetic first chapter.")
        Page.objects.create(asset=asset, index=2, text="Synthetic second chapter.")
    revision = activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext)
    return work, edition, asset, revision


def path_with_items():
    path = ReadingPath.objects.create(title="合成阅读路径", slug=f"path-{uuid4()}", status="published", learning_goal="仅验证路径数据契约。")
    stage = ReadingPathStage.objects.create(reading_path=path, name="第一阶段", learning_questions=["合成学习问题"])
    work, edition, asset, revision = source()
    items = [ReadingPathItem.objects.create(reading_path=path, stage=stage, stage_name=stage.name,
        work=work, edition=edition, asset=asset, document_revision=revision.document_revision,
        material_kind="chapter", chapter_title=f"第{page}章", page_start=page, page_end=page,
        position=page - 1, reading_order=page - 1, is_required=True, editorial_note="私人编辑备注不可公开") for page in (1, 2)]
    return path, stage, items, edition


def test_stable_material_identity_and_distinct_chapters_survive_both_editor_inputs():
    path, stage, items, _ = path_with_items()
    groups = reading_path_stage_groups(path)
    groups[0]["items"][0]["recommendation_reason"] = "更新推荐理由"
    sync_reading_path_stage_groups(path, groups)
    assert set(path.items.values_list("pk", flat=True)) == {row.pk for row in items}
    compatibility = [{**row, "stage": str(stage.pk)} for row in groups[0]["items"]]
    sync_reading_path_stage_groups(path, stage_groups_from_items(path, compatibility))
    assert set(path.items.values_list("pk", flat=True)) == {row.pk for row in items}
    other = ReadingPath.objects.create(title="其他路径", slug=f"other-{uuid4()}")
    with pytest.raises(ReadingPathStructureError, match="另一条"):
        normalize_reading_path_stage_groups(other, groups)


def test_new_draft_ids_are_stable_before_publication(admin_user):
    path, stage, _, _ = path_with_items()
    groups = reading_path_stage_groups(path)
    node = KnowledgeNode.objects.create(canonical_name_zh="新条目", slug=f"new-{uuid4()}", node_type="concept", status="published")
    groups.append({"name": "新阶段", "items": [{"node": str(node.pk)}]})
    draft = save_object_editorial_patch("reading_path", path.pk, {"stage_groups": groups}, actor=admin_user)
    identifiers = draft.patch["stage_groups"][-1]
    again = save_object_editorial_patch("reading_path", path.pk, draft.patch, actor=admin_user)
    assert again.pk == draft.pk and identifiers["id"] and identifiers["items"][0]["id"]
    assert path.stages.count() == 1 and path.stages.get().pk == stage.pk
    sync_reading_path_stage_groups(path, draft.patch["stage_groups"])
    assert str(path.stages.get(name="新阶段").pk) == identifiers["id"]
    assert str(path.items.get(node=node).pk) == identifiers["items"][0]["id"]


def test_public_placeholders_and_revision_snapshot_never_publish_hidden_metadata(admin_user):
    path, stage, items, edition = path_with_items()
    work, no_text, _, _ = source(fulltext=False, title="只有公开书目的材料")
    placeholder = ReadingPathItem.objects.create(reading_path=path, stage=stage, stage_name=stage.name, work=work, edition=no_text, reading_order=2)
    hidden = KnowledgeNode.objects.create(canonical_name_zh="隐藏题名不得出现", slug=f"hidden-{uuid4()}", status="draft")
    secret = ReadingPathItem.objects.create(reading_path=path, stage=stage, stage_name=stage.name, node=hidden,
        reading_order=3, recommendation_reason="隐藏推荐理由不得出现")
    revision = capture_reading_path_publication(path, actor=admin_user)
    data = public_reading_path_snapshot(path.pk)
    assert data["revision"]["token"] == str(revision.pk)
    assert data["counts"] == {"stages": 1, "items": 4, "required": 2, "readable": 2}
    by_id = {row["id"]: row for row in data["items"]}
    assert by_id[str(placeholder.pk)]["source_status"] == "no_fulltext"
    assert by_id[str(placeholder.pk)]["reader_url"] is None
    assert by_id[str(secret.pk)]["title"] == "当前不可用的材料"
    assert by_id[str(items[0].pk)]["reader_url"].endswith(f"page=1&revision={items[0].document_revision_id}")
    assert all(value not in str(data) for value in ("隐藏题名不得出现", "隐藏推荐理由不得出现", "私人编辑备注不可公开"))
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    assert public_reading_path_snapshot(path.pk, revision=str(revision.pk))["items"][0]["source_status"] == "unavailable"


def test_historical_versions_and_replaced_document_do_not_switch_sources(admin_user):
    path, _, items, edition = path_with_items()
    first = capture_reading_path_publication(path, actor=admin_user)
    old = public_reading_path_snapshot(path.pk)
    items[0].status = "withdrawn"
    items[0].save(update_fields=["status"])
    second = capture_reading_path_publication(path, actor=admin_user, change_note="撤回第一章")
    current = public_reading_path_snapshot(path.pk)
    diff = diff_reading_path_snapshots(old, current)
    assert diff["changed"] == [str(items[0].pk)] and diff["removed"] == []
    assert current["items"][0]["source_status"] == "withdrawn"
    history = public_reading_path_snapshot(path.pk, revision=str(first.pk))
    assert not history["is_current_revision"] and history["latest_revision"]["id"] == str(second.pk)
    fresh = deepcopy(edition.active_catalog_revision)
    fresh.pk = None
    fresh.revision += 1
    fresh.document_revision = None
    fresh.fulltext_ready = False
    fresh.save()
    edition.active_catalog_revision = fresh
    edition.save(update_fields=["active_catalog_revision"])
    assert public_reading_path_snapshot(path.pk, revision=str(first.pk))["items"][0]["reader_url"] is None
    assert public_reading_path_snapshot(path.pk, revision=str(first.pk))["items"][0]["source_status"] == "revision_changed"


def test_legacy_get_does_not_write_versions_and_draft_is_not_a_public_revision(admin_user, reader_user):
    path, _, _, _ = path_with_items()
    count = EditorialRevision.objects.count()
    first = public_reading_path_snapshot(path.pk)
    second = public_reading_path_snapshot(path.pk)
    assert first["revision"]["token"] == second["revision"]["token"] and first["revision"]["legacy"]
    assert EditorialRevision.objects.count() == count
    draft = save_object_editorial_patch("reading_path", path.pk, {"curator_note": "未发布策划说明"}, actor=admin_user)
    with pytest.raises(NotFound):
        public_reading_path_snapshot(path.pk, revision=str(draft.pk))
    with pytest.raises(PermissionDenied):
        preview_reading_path(path, snapshot=draft.materialized_preview, request=SimpleNamespace(user=reader_user))
    assert preview_reading_path(path, snapshot=draft.materialized_preview, request=SimpleNamespace(user=admin_user))["curator_note"] == "未发布策划说明"
    assert "未发布策划说明" not in str(public_reading_path_snapshot(path.pk))


@pytest.mark.parametrize("mutation", ["foreign_edition", "foreign_document", "bad_page", "repeated_id"])
def test_material_binding_rejects_inaccurate_or_duplicate_identity(mutation):
    path, _, _, _ = path_with_items()
    groups = reading_path_stage_groups(path)
    row = groups[0]["items"][0]
    _, edition, _, revision = source()
    if mutation == "foreign_edition":
        row["edition"] = str(edition.pk)
    elif mutation == "foreign_document":
        row["document_revision"] = str(revision.document_revision_id)
    elif mutation == "bad_page":
        row["page_end"] = 999
    else:
        groups[0]["items"][1]["id"] = row["id"]
    with pytest.raises(ReadingPathStructureError):
        normalize_reading_path_stage_groups(path, groups)


def test_public_list_filters_count_and_no_empty_stage_loss(api_client):
    path, _, _, _ = path_with_items()
    topic = Topic.objects.create(name="路径合成主题", slug=f"topic-{uuid4()}", editorial_status="published")
    path.topics.add(topic)
    ReadingPathStage.objects.create(reading_path=path, name="尚无材料但仍存在的阶段", position=2)
    ReadingPath.objects.create(title="未公开路径不得计数", slug=f"private-{uuid4()}", status="draft")
    response = api_client.get(URL, {"topic": topic.slug, "difficulty": "beginner"})
    assert response.status_code == 200 and response.data["count"] == 1
    assert response.data["results"][0]["counts"]["stages"] == 2
    assert api_client.get(URL, {"difficulty": "unsupported"}).status_code == 400
    assert api_client.get(URL, {"page": "-1"}).status_code == 400
