import catalog.models
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_normalize_pdf_page_labels"),
    ]

    operations = [
        migrations.CreateModel(
            name="CoverCandidate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("page_index", models.PositiveIntegerField()),
                (
                    "thumbnail",
                    models.ImageField(
                        max_length=1000,
                        upload_to=catalog.models.cover_candidate_upload_path,
                    ),
                ),
                ("score", models.FloatField(default=0)),
                ("reasons", models.JSONField(blank=True, default=list)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("selected", models.BooleanField(default=False)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cover_candidates",
                        to="catalog.asset",
                    ),
                ),
                (
                    "work",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cover_candidates",
                        to="catalog.work",
                    ),
                ),
            ],
            options={"ordering": ["-score", "page_index"]},
        ),
        migrations.AddConstraint(
            model_name="covercandidate",
            constraint=models.UniqueConstraint(
                fields=("asset", "page_index"),
                name="unique_cover_candidate_page",
            ),
        ),
    ]
