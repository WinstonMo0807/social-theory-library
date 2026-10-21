"""Personal graph controls only; no catalog or account conversion."""
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
        ("reading", "0016_saved_knowledge_nodes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="SavedGraphView", fields=[*identity_fields(),
            ("revision", models.PositiveIntegerField(default=1)),
            ("data_ciphertext", models.BinaryField(blank=True, default=bytes)),
            ("request_id", models.UUIDField(default=uuid.uuid4)),
        ], options={"ordering": ["-updated_at", "-id"], "constraints": [
            models.UniqueConstraint(fields=["user", "request_id"], name="graph_view_request_unique")],
            "indexes": [models.Index(fields=["user", "-updated_at"], name="graph_view_owner_updated_idx")]}),
        migrations.CreateModel(name="GraphViewReceipt", fields=[*identity_fields(),
            ("record", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="command_receipts", to="reading.savedgraphview")),
            ("request_id", models.UUIDField()),
            ("fingerprint", models.CharField(max_length=64)),
            ("applied_revision", models.PositiveIntegerField()),
        ], options={"constraints": [
            models.UniqueConstraint(fields=["user", "request_id"], name="graph_receipt_request_unique")]}),
    ]
