import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0026_reading_list_topics")]
    operations = [migrations.CreateModel(name="ResearchReplayRevision", fields=[
        ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("revision", models.PositiveIntegerField()),
        ("kind", models.CharField(max_length=12, choices=[("baseline", "Before edit"), ("edit", "Edit"), ("restore", "Restore")])),
        ("data_ciphertext", models.BinaryField(default=bytes)),
        ("turn", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="replay_revisions", to="reading.researchturn")),
    ], options={"ordering": ["-revision"], "constraints": [models.UniqueConstraint(fields=["turn", "revision"], name="research_replay_revision_unique")]})]
