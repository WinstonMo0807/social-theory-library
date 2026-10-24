import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0086_timeline_participant_role")]
    operations = [migrations.CreateModel(
        name="TimelineEvidenceImage",
        fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("source_key", models.CharField(max_length=36)),
            ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence_images", to="catalog.theorytimelineevent")),
            ("rendition", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="timeline_evidence_references", to="catalog.mediarendition")),
        ],
        options={"constraints": [models.UniqueConstraint(fields=("event", "source_key"), name="unique_timeline_evidence_image")]},
    )]
