import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0024_reader_sharing"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ReaderMaterialPreference", fields=[
        ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("kind", models.CharField(max_length=16, choices=[(value, value) for value in ("research", "notes", "bookmarks", "plans", "lists", "audits", "confirmed", "saved")])),
        ("object_id", models.UUIDField()),
        ("title_ciphertext", models.BinaryField(blank=True, default=bytes)),
        ("archived", models.BooleanField(default=False)),
        ("revision", models.PositiveIntegerField(default=1)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
    ], options={"constraints": [models.UniqueConstraint(fields=["user", "kind", "object_id"], name="reader_material_preference_unique")],
                "indexes": [models.Index(fields=["user", "kind", "archived"], name="reader_material_archive_idx")]})]
