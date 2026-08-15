from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import Asset, Edition, PublicationState, Work
from reading.models import ReadingProgress, SavedItem


def create_readable_work(index):
    work = Work.objects.create(document_type="book", title=f"读者中心测试 {index}")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"reader-center-test-{index}",
        is_primary=True,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/reader-center-test-{index}.pdf",
        sha256=f"{index:064x}",
        status=Asset.Status.READY,
        page_count=20,
        is_current=True,
    )
    return work, asset


@pytest.mark.django_db
def test_continue_reading_returns_five_latest_works_without_deleting_older_progress(
    api_client,
    reader_user,
):
    created = [create_readable_work(index) for index in range(1, 7)]
    baseline = timezone.now() - timedelta(hours=1)
    for index, (_, asset) in enumerate(created):
        progress = ReadingProgress.objects.create(
            user=reader_user,
            asset=asset,
            current_page=index + 1,
            progress_ratio=(index + 1) / 20,
            last_position={"page": index + 1},
        )
        ReadingProgress.objects.filter(pk=progress.pk).update(
            updated_at=baseline + timedelta(minutes=index)
        )

    api_client.force_authenticate(reader_user)
    response = api_client.get("/api/reading/progress/")

    assert response.status_code == 200
    assert response.data["count"] == 5
    assert response.data["next"] is None
    assert [str(row["asset"]) for row in response.data["results"]] == [
        str(asset.id) for _, asset in reversed(created[1:])
    ]
    assert ReadingProgress.objects.filter(user=reader_user).count() == 6


@pytest.mark.django_db
def test_continue_reading_uses_only_the_latest_asset_for_each_work(
    api_client,
    reader_user,
):
    work, first_asset = create_readable_work(10)
    second_edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="reader-center-test-10-second-edition",
        is_primary=False,
    )
    second_asset = Asset.objects.create(
        edition=second_edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/reader-center-test-10-second.pdf",
        sha256=f"{11:064x}",
        status=Asset.Status.READY,
        page_count=20,
        is_current=True,
    )
    ReadingProgress.objects.create(
        user=reader_user,
        asset=first_asset,
        current_page=3,
        progress_ratio=0.15,
    )
    latest = ReadingProgress.objects.create(
        user=reader_user,
        asset=second_asset,
        current_page=9,
        progress_ratio=0.45,
    )

    api_client.force_authenticate(reader_user)
    response = api_client.get("/api/reading/progress/")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert str(response.data["results"][0]["id"]) == str(latest.id)
    assert str(response.data["results"][0]["asset"]) == str(second_asset.id)
    assert ReadingProgress.objects.filter(user=reader_user).count() == 2


@pytest.mark.django_db
def test_saving_an_unopened_work_creates_and_returns_durable_reading_progress(
    api_client,
    reader_user,
):
    work, asset = create_readable_work(20)
    api_client.force_authenticate(reader_user)

    response = api_client.post(
        "/api/reading/saved/",
        {"work": str(work.id)},
        format="json",
    )

    assert response.status_code == 201
    assert SavedItem.objects.filter(user=reader_user, work=work).exists()
    progress = ReadingProgress.objects.get(user=reader_user, asset=asset)
    assert progress.current_page == 1
    assert progress.last_position == {"page": 1}
    assert str(response.data["reading_progress"]["asset"]) == str(asset.id)
    assert response.data["reading_progress"]["current_page"] == 1


@pytest.mark.django_db
def test_saved_work_keeps_its_progress_when_it_falls_out_of_recent_five(
    api_client,
    reader_user,
):
    saved_work, saved_asset = create_readable_work(30)
    saved_progress = ReadingProgress.objects.create(
        user=reader_user,
        asset=saved_asset,
        current_page=12,
        progress_ratio=0.6,
        last_position={"page": 12},
    )
    ReadingProgress.objects.filter(pk=saved_progress.pk).update(
        updated_at=timezone.now() - timedelta(days=1)
    )
    api_client.force_authenticate(reader_user)
    saved_response = api_client.post(
        "/api/reading/saved/",
        {"work": str(saved_work.id)},
        format="json",
    )
    assert saved_response.status_code == 201

    for index in range(40, 45):
        _, asset = create_readable_work(index)
        ReadingProgress.objects.create(
            user=reader_user,
            asset=asset,
            current_page=2,
            progress_ratio=0.1,
            last_position={"page": 2},
        )

    recent_response = api_client.get("/api/reading/progress/")
    favorites_response = api_client.get("/api/reading/saved/")

    assert recent_response.status_code == 200
    assert str(saved_asset.id) not in {
        str(row["asset"]) for row in recent_response.data["results"]
    }
    assert favorites_response.status_code == 200
    assert favorites_response.data["count"] == 1
    favorite = favorites_response.data["results"][0]
    assert str(favorite["work"]) == str(saved_work.id)
    assert str(favorite["reading_progress"]["asset"]) == str(saved_asset.id)
    assert favorite["reading_progress"]["current_page"] == 12
    assert ReadingProgress.objects.filter(pk=saved_progress.pk).exists()


@pytest.mark.django_db
def test_work_without_a_readable_asset_cannot_create_an_incomplete_favorite(
    api_client,
    reader_user,
):
    work = Work.objects.create(document_type="book", title="尚无阅读文件")
    Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug="saved-without-reader-asset",
    )
    api_client.force_authenticate(reader_user)

    response = api_client.post(
        "/api/reading/saved/",
        {"work": str(work.id)},
        format="json",
    )

    assert response.status_code == 400
    assert SavedItem.objects.filter(user=reader_user, work=work).count() == 0
    assert ReadingProgress.objects.filter(user=reader_user).count() == 0
