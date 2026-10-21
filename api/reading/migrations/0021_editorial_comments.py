import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0020_topic_source_follows"), ("catalog", "0074_topic_hierarchy_media"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="EditorialComment", fields=[
        ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("public_revision_id", models.UUIDField()), ("data_ciphertext", models.BinaryField(default=bytes)),
        ("status", models.CharField(max_length=16, default="pending", choices=[("pending", "待审核"), ("published", "已公开"), ("rejected", "未公开")])),
        ("revision", models.PositiveIntegerField(default=1)), ("moderation_reason", models.CharField(max_length=240, blank=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reader_comments", to="catalog.recommendationissue")),
        ("moderated_by", models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, related_name="moderated_editorial_comments", to=settings.AUTH_USER_MODEL, null=True, blank=True)),
    ], options={"ordering": ["-created_at", "-id"], "indexes": [models.Index(fields=["issue", "public_revision_id", "status", "created_at"], name="editorial_comment_public_idx")]})]
