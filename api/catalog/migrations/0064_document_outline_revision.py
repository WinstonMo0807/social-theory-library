import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0063_reversible_records_and_long_text_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentOutlineRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField()),
                ("source_checksum", models.CharField(max_length=64)),
                ("parser_version", models.CharField(default="outline-v1", max_length=80)),
                ("nodes", models.JSONField(default=list)),
                ("diagnostics", models.JSONField(blank=True, default=list)),
                ("origin", models.CharField(default="automatic", max_length=20)),
                ("is_active", models.BooleanField(default=False)),
                ("reviewed", models.BooleanField(default=False)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outline_revisions", to="catalog.asset")),
                ("document_revision", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="outline_revisions", to="catalog.documentrevision")),
                ("restored_from", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="restorations", to="catalog.documentoutlinerevision")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_outline_revisions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-revision"],
                "constraints": [
                    models.UniqueConstraint(fields=("asset", "revision"), name="unique_outline_revision"),
                    models.UniqueConstraint(fields=("asset",), condition=models.Q(is_active=True), name="unique_active_outline"),
                ],
            },
        ),
    ]
