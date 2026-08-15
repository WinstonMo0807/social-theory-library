from django.db import migrations


def backfill_saved_item_progress(apps, schema_editor):
    Asset = apps.get_model("catalog", "Asset")
    ReadingProgress = apps.get_model("reading", "ReadingProgress")
    SavedItem = apps.get_model("reading", "SavedItem")

    for saved_item in SavedItem.objects.all().iterator(chunk_size=500):
        readable_progress = ReadingProgress.objects.filter(
            user_id=saved_item.user_id,
            asset__edition__work_id=saved_item.work_id,
            asset__edition__state="published",
            asset__kind="normalized",
            asset__status="ready",
            asset__is_current=True,
        ).exists()
        if readable_progress:
            continue

        asset = (
            Asset.objects.filter(
                edition__work_id=saved_item.work_id,
                edition__state="published",
                kind="normalized",
                status="ready",
                is_current=True,
            )
            .order_by("-edition__is_primary", "-version", "-updated_at")
            .first()
        )
        if asset is None:
            continue
        ReadingProgress.objects.get_or_create(
            user_id=saved_item.user_id,
            asset_id=asset.id,
            defaults={
                "current_page": 1,
                "progress_ratio": 0,
                "last_position": {"page": 1},
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0018_semanticindexversion_validation"),
        ("reading", "0002_savedtopic"),
    ]

    operations = [
        migrations.RunPython(backfill_saved_item_progress, migrations.RunPython.noop),
    ]
