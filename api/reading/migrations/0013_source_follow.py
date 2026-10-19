import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0012_citation_document_preview"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="SourceFollow", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("path", models.CharField(max_length=400)), ("active", models.BooleanField(default=True)),
            ("revision", models.PositiveIntegerField(default=1)), ("state_fingerprint", models.CharField(max_length=64)),
            ("source_status", models.CharField(max_length=32)), ("last_checked_at", models.DateTimeField(blank=True, null=True)),
            ("read_at", models.DateTimeField(blank=True, null=True)), ("check_error", models.CharField(blank=True, max_length=80)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_follows", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-updated_at", "-id"]}),
        migrations.CreateModel(name="SourceFollowEvent", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("action", models.CharField(max_length=20)), ("before_status", models.CharField(blank=True, max_length=32)),
            ("after_status", models.CharField(blank=True, max_length=32)), ("request_id", models.UUIDField(blank=True, null=True)),
            ("request_fingerprint", models.CharField(blank=True, max_length=64)), ("revision", models.PositiveIntegerField()),
            ("follow", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="reading.sourcefollow")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at", "-id"]}),
        migrations.AddConstraint(model_name="sourcefollow", constraint=models.UniqueConstraint(fields=("user", "path"), name="unique_owner_source_follow")),
        migrations.AddIndex(model_name="sourcefollow", index=models.Index(fields=["active", "last_checked_at"], name="source_follow_poll_idx")),
        migrations.AddConstraint(model_name="sourcefollowevent", constraint=models.UniqueConstraint(fields=("user", "request_id"), name="unique_owner_source_request")),
    ]
