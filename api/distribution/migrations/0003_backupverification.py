import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("distribution", "0002_backupjob_archive_path"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="BackupVerification", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("status", models.CharField(choices=[("queued", "等待"), ("running", "执行中"), ("completed", "完成"), ("failed", "失败")], db_index=True, default="queued", max_length=20)),
        ("expected_checksum", models.CharField(max_length=64)),
        ("report", models.JSONField(blank=True, default=dict)),
        ("error_message", models.CharField(blank=True, max_length=500)),
        ("started_at", models.DateTimeField(blank=True, null=True)),
        ("completed_at", models.DateTimeField(blank=True, null=True)),
        ("backup", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="verifications", to="distribution.backupjob")),
        ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="backup_verifications", to=settings.AUTH_USER_MODEL)),
    ]), migrations.CreateModel(name="BackupSchedule", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("scope", models.CharField(choices=[("database", "数据库与清单"), ("originals", "数据库、清单与原件")], max_length=20, unique=True)),
        ("enabled", models.BooleanField(default=False)),
        ("interval_hours", models.PositiveIntegerField(default=24)),
        ("next_run_at", models.DateTimeField(blank=True, null=True)),
        ("last_error", models.CharField(blank=True, max_length=500)),
        ("configured_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="backup_schedules", to=settings.AUTH_USER_MODEL)),
        ("last_job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="schedules", to="distribution.backupjob")),
    ])]
