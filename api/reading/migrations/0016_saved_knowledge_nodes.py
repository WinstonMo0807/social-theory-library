"""Knowledge bookmarks only; no account or catalog data conversion."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def identity_fields():
    return [
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("reading", "0015_parallel_reading"),
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="SavedKnowledgeNode", fields=[*identity_fields(),
            ("node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name="saved_by", to="catalog.knowledgenode"))],
            options={"ordering": ["-created_at", "-id"], "constraints": [
                models.UniqueConstraint(fields=["user", "node"], name="unique_saved_knowledge_node")]}),
        migrations.CreateModel(name="KnowledgeSaveReceipt", fields=[*identity_fields(),
            ("request_id", models.UUIDField()), ("target_key", models.CharField(max_length=64)),
            ("fingerprint", models.CharField(max_length=64)), ("applied_saved", models.BooleanField())],
            options={"constraints": [
                models.UniqueConstraint(fields=["user", "request_id"], name="knowledge_save_receipt_unique")]}),
    ]
