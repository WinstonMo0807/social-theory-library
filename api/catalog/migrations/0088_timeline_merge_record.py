import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0087_timeline_evidence_images"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="theorytimelineevent", name="merged_into", field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="merged_sources", to="catalog.theorytimelineevent")),
        migrations.CreateModel(name="TimelineMergeRecord", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("request_fingerprint", models.CharField(max_length=64)),
            ("before", models.JSONField(default=dict)),
            ("rollback_fingerprint", models.CharField(max_length=64)),
            ("rolled_back_at", models.DateTimeField(null=True, blank=True)),
            ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_merges", to="catalog.theorytimelineevent")),
            ("target", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_merges", to="catalog.theorytimelineevent")),
            ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={"constraints": [models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="timeline_merge_distinct_events")]}),
    ]
