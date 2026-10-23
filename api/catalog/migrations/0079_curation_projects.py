import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0078_manual_catalog_material_fields"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="CurationProject", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("title", models.CharField(max_length=600)),
            ("question", models.TextField(blank=True)),
            ("introduction", models.TextField(blank=True)),
            ("visibility", models.CharField(choices=[("team", "仅项目团队"), ("staff", "馆内编辑")], default="team", max_length=12)),
            ("planned_for", models.DateField(blank=True, null=True)),
            ("archived_at", models.DateTimeField(blank=True, null=True)),
            ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_curation_projects", to=settings.AUTH_USER_MODEL)),
            ("collaborators", models.ManyToManyField(blank=True, related_name="curation_projects", to=settings.AUTH_USER_MODEL)),
            ("cover_rendition", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="curation_projects", to="catalog.mediarendition")),
        ], options={"ordering": ["-updated_at", "pk"]}),
        migrations.AddField(model_name="recommendationissue", name="project", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="articles", to="catalog.curationproject")),
        migrations.AddField(model_name="recommendationissue", name="project_position", field=models.PositiveIntegerField(default=0)),
    ]
