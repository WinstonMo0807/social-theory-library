"""Reuse personal plans for path follows; preserve receipts after private erasure."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0017_saved_graph_views"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="personalreadingplan", name="public_path_id",
            field=models.UUIDField(blank=True, null=True)),
        migrations.AddConstraint(model_name="personalreadingplan", constraint=models.UniqueConstraint(
            fields=("user", "public_path_id"), condition=models.Q(public_path_id__isnull=False),
            name="reading_plan_owner_path_unique")),
        migrations.CreateModel(name="PlanCommandReceipt", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("request_id", models.UUIDField()), ("fingerprint", models.CharField(max_length=64)),
            ("applied_revision", models.PositiveIntegerField()),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ("record", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="path_command_receipts", to="reading.personalreadingplan")),
        ], options={"constraints": [models.UniqueConstraint(fields=("user", "request_id"), name="plan_command_request_unique")]}),
    ]
