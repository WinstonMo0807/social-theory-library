from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("reading", "0006_final_scope_normalization"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReaderAIConnection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(choices=[("openai_compatible", "OpenAI 兼容接口"), ("ollama", "Ollama"), ("vllm", "vLLM")], max_length=32)),
                ("base_url", models.URLField(max_length=2000)),
                ("model", models.CharField(max_length=300)),
                ("api_key_ciphertext", models.BinaryField(blank=True, default=bytes)),
                ("enabled", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("not_tested", "尚未测试"), ("healthy", "可用"), ("unavailable", "暂不可用"), ("invalid", "配置无效")], default="not_tested", max_length=24)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=80)),
                ("last_error_message", models.TextField(blank=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="reader_ai_connection", to=settings.AUTH_USER_MODEL)),
            ],
            options={"indexes": [models.Index(fields=["user", "enabled", "status"], name="reader_ai_user_status_idx")]},
        ),
    ]
