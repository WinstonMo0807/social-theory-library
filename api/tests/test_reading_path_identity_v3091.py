from uuid import uuid4

import pytest

from catalog.models import ReadingPathItem, ReadingPathStage
from catalog.services.reading_paths import reading_path_stage_groups

from .editorial_fixtures import editorial_request
from .test_work_curation_v280 import make_path, make_work


@pytest.mark.django_db
def test_reading_path_reorder_keeps_existing_rows_and_only_removes_omitted_items(api_client, admin_user):
    path, first_stage = make_path("稳定书目身份")
    second_stage = ReadingPathStage.objects.create(reading_path=path, name="延伸阅读", position=1)
    rows = [ReadingPathItem.objects.create(
        reading_path=path, stage=first_stage, stage_name=first_stage.name,
        work=make_work(f"作品{index}"), position=index, reading_order=index,
        recommendation_reason=f"人工理由{index}", prerequisite=f"前置条件{index}",
        editorial_note=f"私人备注{index}", is_required=True,
    ) for index in range(3)]
    before = {str(row.id): row.created_at for row in rows}
    groups = reading_path_stage_groups(path)
    groups[1]["items"] = [dict(groups[0]["items"][1], position=0), dict(groups[0]["items"][0], position=1)]
    groups[0]["items"] = []
    api_client.force_authenticate(admin_user)
    saved = editorial_request(api_client, "patch", f"/api/catalog/admin/theory-system/reading-paths/{path.id}/", {"stage_groups": groups}, format="json")
    assert saved.status_code == 200
    assert [str(row["id"]) for row in saved.data["items"]] == [str(rows[1].id), str(rows[0].id)]
    for original in rows[:2]:
        original.refresh_from_db()
        assert original.created_at == before[str(original.id)]
        assert original.stage_id == second_stage.id
        assert original.recommendation_reason == f"人工理由{rows.index(original)}"
        assert original.prerequisite == f"前置条件{rows.index(original)}"
        assert original.editorial_note == f"私人备注{rows.index(original)}"
        assert original.is_required
    assert not ReadingPathItem.objects.filter(pk=rows[2].id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("bad_identity", ["foreign", "missing", "duplicate"])
def test_reading_path_rejects_foreign_missing_or_duplicate_item_ids_without_losing_data(api_client, admin_user, bad_identity):
    path, stage = make_path("书目身份校验")
    work = make_work("保留作品")
    row = ReadingPathItem.objects.create(reading_path=path, stage=stage, stage_name=stage.name, work=work, editorial_note="必须保留的私有备注")
    groups = reading_path_stage_groups(path)
    if bad_identity == "foreign":
        other, other_stage = make_path("另一条路径")
        foreign = ReadingPathItem.objects.create(reading_path=other, stage=other_stage, stage_name=other_stage.name, work=make_work("其他路径作品"))
        groups[0]["items"][0]["id"] = str(foreign.id)
    elif bad_identity == "missing":
        groups[0]["items"][0]["id"] = str(uuid4())
    else:
        groups[0]["items"].append(dict(groups[0]["items"][0], work=str(make_work("第二作品").id), position=1))
    api_client.force_authenticate(admin_user)
    rejected = editorial_request(api_client, "patch", f"/api/catalog/admin/theory-system/reading-paths/{path.id}/", {"stage_groups": groups}, format="json")
    assert rejected.status_code == 400
    assert list(path.items.values_list("id", flat=True)) == [row.id]
    row.refresh_from_db()
    assert row.editorial_note == "必须保留的私有备注"
    assert row.work_id == work.id
