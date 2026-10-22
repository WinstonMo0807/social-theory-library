import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0021_editorial_comments"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ResearchImportReceipt", fields=[
        ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("request_id", models.UUIDField()),
        ("fingerprint", models.CharField(max_length=64)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ("project", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="import_receipts", to="reading.researchproject")),
    ], options={"constraints": [models.UniqueConstraint(fields=["user", "request_id"], name="research_import_request_unique")]})]
