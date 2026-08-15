from django.db import migrations, models


def initialize_dispatch_state(apps, schema_editor):
    UploadItem = apps.get_model("ingestion", "UploadItem")
    terminal = ["published", "withdrawn", "deleted", "needs_review", "failed"]
    UploadItem.objects.filter(status__in=terminal).update(dispatch_status="completed")
    UploadItem.objects.filter(status="ready").exclude(error_code="queue_unavailable").update(
        dispatch_status="completed"
    )
    # Older releases stored reviewed items as READY when Redis was unavailable.
    # Preserve them as recoverable reviewed work instead of silently treating
    # them as completed.
    UploadItem.objects.filter(status="ready", error_code="queue_unavailable").update(
        dispatch_status="pending",
        dispatch_kind="reviewed",
    )


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0005_uploaditem_batch_processing_token_unique")]

    operations = [
        migrations.AddField(
            model_name="uploaditem",
            name="dispatch_status",
            field=models.CharField(
                choices=[
                    ("pending", "等待派发"),
                    ("queued", "已进入队列"),
                    ("running", "工作者处理中"),
                    ("completed", "任务已完成"),
                    ("failed", "派发失败"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="uploaditem",
            name="dispatch_kind",
            field=models.CharField(
                choices=[("initial", "首次识别"), ("reviewed", "复核后继续")],
                default="initial",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="uploaditem",
            name="dispatch_task_id",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="uploaditem",
            name="dispatch_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="uploaditem",
            name="last_dispatched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="uploaditem",
            name="dispatch_error",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(initialize_dispatch_state, migrations.RunPython.noop),
    ]
