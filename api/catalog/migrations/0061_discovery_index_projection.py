import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0060_discovery_search_session"), ("ingestion", "0017_v307_local_upload_default")]
    operations = [
        migrations.AddField(model_name="semanticindexversion", name="index_family",
            field=models.CharField(db_index=True, default="semantic", max_length=16)),
        migrations.CreateModel(name="DiscoveryDocument", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("channel", models.CharField(db_index=True, max_length=16)), ("source_type", models.CharField(max_length=32)),
            ("source_id", models.UUIDField()), ("source_revision", models.CharField(max_length=64)),
            ("scope_token", models.CharField(db_index=True, max_length=180)),
            ("access_status", models.CharField(db_index=True, default="public", max_length=20)),
            ("input_hash", models.CharField(db_index=True, max_length=64)),
            ("text", models.TextField()), ("normalized_text", models.TextField()),
            ("token_count", models.PositiveIntegerField(default=0)), ("start_offset", models.PositiveIntegerField(default=0)),
            ("end_offset", models.PositiveIntegerField(default=0)), ("payload", models.JSONField(default=dict)),
            ("keyword_ready", models.BooleanField(db_index=True, default=False)),
            ("vector_ready", models.BooleanField(db_index=True, default=False)),
            ("indexed_at", models.DateTimeField(blank=True, null=True)),
            ("document_revision", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="discovery_documents", to="catalog.documentrevision")),
            ("edition", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discovery_documents", to="catalog.edition")),
            ("generation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discovery_documents", to="catalog.semanticindexversion")),
        ], options={"indexes": [models.Index(fields=["generation", "source_type", "source_id"], name="discovery_source_generation"),
                                models.Index(fields=["generation", "channel", "scope_token"], name="discovery_channel_scope")]}),
        migrations.CreateModel(name="DiscoverySourceState", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("source_type", models.CharField(max_length=32)), ("source_id", models.UUIDField()),
            ("source_revision", models.CharField(blank=True, max_length=64)),
            ("expected_count", models.PositiveIntegerField(default=0)), ("completed_count", models.PositiveIntegerField(default=0)),
            ("indexed_at", models.DateTimeField(blank=True, null=True)), ("error", models.CharField(blank=True, max_length=500)),
            ("generation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discovery_sources", to="catalog.semanticindexversion")),
            ("job", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="discovery_sources", to="ingestion.processingjob")),
        ], options={"constraints": [models.UniqueConstraint(fields=("generation", "source_type", "source_id"), name="unique_discovery_source_state")]}),
    ]
