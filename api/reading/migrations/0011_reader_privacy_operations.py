import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0010_citation_private_source"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="ReaderDataOperation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("data_ciphertext", models.BinaryField(blank=True, default=bytes)),
                ("request_id", models.UUIDField(default=uuid.uuid4)),
                ("kind", models.CharField(choices=[("export", "Export"), ("erase", "Erase")], max_length=12)),
                ("status", models.CharField(db_index=True, default="preview", max_length=16)),
                ("generation", models.PositiveIntegerField(default=1)),
                ("task_id", models.CharField(blank=True, max_length=64)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"], "constraints": [models.UniqueConstraint(fields=("user", "request_id"), name="reader_data_request_unique")]},
        ),
        migrations.CreateModel(
            name="ReaderSearchRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("data_ciphertext", models.BinaryField(blank=True, default=bytes)),
                ("request_id", models.UUIDField(default=uuid.uuid4)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"], "constraints": [models.UniqueConstraint(fields=("user", "request_id"), name="reader_search_request_unique")]},
        ),
    ]
