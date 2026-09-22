import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0059_v307_curation_source_revision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.CreateModel(
        name="DiscoverySearchSession",
        fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("token_hash", models.CharField(max_length=64)),
            ("query", models.TextField()),
            ("filters", models.JSONField(default=dict)),
            ("access_statuses", models.JSONField(default=list)),
            ("status", models.CharField(choices=[("queued", "等待检索"), ("running", "正在检索"), ("partial", "部分完成"), ("completed", "检索完成"), ("failed", "检索失败"), ("canceled", "已取消")], default="queued", max_length=16)),
            ("task_id", models.CharField(blank=True, max_length=64)),
            ("generation", models.PositiveSmallIntegerField(default=1)),
            ("expansion_count", models.PositiveSmallIntegerField(default=0)),
            ("results", models.JSONField(default=dict)),
            ("channels", models.JSONField(default=dict)),
            ("versions", models.JSONField(default=dict)),
            ("warnings", models.JSONField(default=list)),
            ("started_at", models.DateTimeField(blank=True, null=True)),
            ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("expires_at", models.DateTimeField(db_index=True)),
            ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discovery_searches", to=settings.AUTH_USER_MODEL)),
        ],
        options={"indexes": [models.Index(fields=["owner", "status"], name="discovery_owner_status_idx")]},
    )]
