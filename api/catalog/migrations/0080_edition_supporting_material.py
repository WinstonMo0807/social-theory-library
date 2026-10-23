import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0079_curation_projects"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="EditionSupportingMaterial", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("kind", models.CharField(choices=[("note", "补充说明"), ("link", "相关链接")], max_length=8)),
        ("title", models.CharField(max_length=300)),
        ("note", models.TextField(blank=True)),
        ("url", models.URLField(blank=True, max_length=2000)),
        ("archived", models.BooleanField(db_index=True, default=False)),
        ("edition", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="supporting_materials", to="catalog.edition")),
        ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_supporting_materials", to=settings.AUTH_USER_MODEL)),
        ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="updated_supporting_materials", to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ["-updated_at", "pk"], "constraints": [models.CheckConstraint(condition=(models.Q(kind="note", url="") | (models.Q(kind="link") & ~models.Q(url=""))), name="edition_supporting_kind_valid")]})]
