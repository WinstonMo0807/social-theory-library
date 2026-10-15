from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("catalog", "0066_page_geometry")]

    operations = [
        migrations.CreateModel(
            name="PublicFeedback",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(choices=[("content", "内容"), ("function", "功能"), ("citation", "引用"), ("accessibility", "无障碍"), ("other", "其他")], db_index=True, default="other", max_length=24)),
                ("body", models.TextField(max_length=5000)),
                ("contact", models.EmailField(blank=True, max_length=254)),
                ("path", models.CharField(blank=True, max_length=400)),
                ("status", models.CharField(choices=[("submitted", "已提交"), ("reviewing", "处理中"), ("resolved", "已处理")], db_index=True, default="submitted", max_length=20)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="public_feedback", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["status", "-created_at"], name="feedback_status_created_idx")]},
        ),
    ]
