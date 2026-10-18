import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0068_page_mapping_revision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PageTextRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField()),
                ("source_fingerprint", models.CharField(max_length=64)),
                ("page_index", models.PositiveIntegerField()),
                ("original_text", models.TextField(blank=True)),
                ("text", models.TextField(blank=True)),
                ("note", models.CharField(blank=True, max_length=2000)),
                ("confirmed", models.BooleanField(default=False)),
                ("review_only", models.BooleanField(default=False)),
                ("document_revision", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="text_corrections", to="catalog.documentrevision")),
                ("request_id", models.UUIDField()),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("apply_request_id", models.UUIDField(blank=True, null=True)),
                ("apply_fingerprint", models.CharField(blank=True, max_length=64)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="text_corrections", to="catalog.asset")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_text_corrections", to=settings.AUTH_USER_MODEL)),
                ("applied_asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="applied_text_corrections", to="catalog.asset")),
                ("publication_event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="text_corrections", to="catalog.knowledgepublicationevent")),
            ],
            options={
                "ordering": ["-revision"],
                "constraints": [
                    models.UniqueConstraint(fields=("asset", "revision"), name="unique_page_text_revision"),
                    models.UniqueConstraint(fields=("asset", "request_id"), name="unique_page_text_request"),
                    models.UniqueConstraint(fields=("asset", "apply_request_id"), name="unique_page_text_apply"),
                ],
            },
        ),
        migrations.AddField(model_name="page", name="is_text_manual", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="page", name="manual_text_revision", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="protected_pages", to="catalog.pagetextrevision")),
        migrations.AddField(model_name="page", name="reviewed_text_revision", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_pages", to="catalog.pagetextrevision")),
    ]
