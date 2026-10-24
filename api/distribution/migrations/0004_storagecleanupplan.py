import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("distribution", "0003_backupverification"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="StorageCleanupPlan", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("status", models.CharField(choices=[("scanned", "等待确认"), ("queued", "等待"), ("running", "执行中"), ("completed", "完成"), ("partial", "部分完成"), ("failed", "失败"), ("cancelled", "已停止")], db_index=True, default="scanned", max_length=20)),
        ("retention_days", models.PositiveIntegerField()), ("policy_version", models.CharField(max_length=100)),
        ("manifest", models.JSONField(default=list)), ("selected", models.JSONField(default=list)),
        ("outcomes", models.JSONField(default=dict)), ("scan_summary", models.JSONField(default=dict)),
        ("error_message", models.CharField(blank=True, max_length=500)),
        ("started_at", models.DateTimeField(blank=True, null=True)), ("completed_at", models.DateTimeField(blank=True, null=True)),
        ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="storage_cleanup_plans", to=settings.AUTH_USER_MODEL)),
    ])]
