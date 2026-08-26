from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0038_backfill_reading_path_semantics"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderCredentialSecret",
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
                ("alias", models.SlugField(max_length=64, unique=True)),
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("research_source", "Research Source"),
                            ("ai_runtime", "AI Runtime"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("provider_key", models.CharField(blank=True, db_index=True, max_length=120)),
                ("ciphertext", models.BinaryField()),
                ("key_version", models.CharField(default="private-data-fernet-v1", max_length=40)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_test_status", models.CharField(blank=True, max_length=32)),
                ("last_test_message", models.CharField(blank=True, max_length=500)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_provider_credential_secrets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["purpose", "alias"]},
        ),
        migrations.AddIndex(
            model_name="providercredentialsecret",
            index=models.Index(
                fields=["purpose", "provider_key"],
                name="catalog_pro_purpose_61b277_idx",
            ),
        ),
    ]
