import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0067_publicfeedback"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PageMappingRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField()),
                ("source_fingerprint", models.CharField(max_length=64)),
                ("data", models.JSONField(default=dict)),
                ("origin", models.CharField(default="manual", max_length=20)),
                ("request_id", models.UUIDField()),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("apply_request_id", models.UUIDField(blank=True, null=True)),
                ("apply_fingerprint", models.CharField(blank=True, max_length=64)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="page_mapping_revisions", to="catalog.asset")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_page_mapping_revisions", to=settings.AUTH_USER_MODEL)),
                ("restored_from", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="restorations", to="catalog.pagemappingrevision")),
                ("applied_asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="applied_page_mappings", to="catalog.asset")),
                ("publication_event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="page_mappings", to="catalog.knowledgepublicationevent")),
            ],
            options={
                "ordering": ["-revision"],
                "constraints": [
                    models.UniqueConstraint(fields=("asset", "revision"), name="unique_page_mapping_revision"),
                    models.UniqueConstraint(fields=("asset", "request_id"), name="unique_page_mapping_request"),
                    models.UniqueConstraint(fields=("asset", "apply_request_id"), name="unique_page_mapping_apply"),
                ],
            },
        ),
    ]
