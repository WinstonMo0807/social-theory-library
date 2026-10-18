from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0009_personal_plan_pending_task")]

    operations = [
        migrations.AddField(model_name="citationaudit", name="purpose", field=models.CharField(
            choices=[("manuscript", "Manuscript"), ("private_source", "Private source")], default="manuscript", max_length=20)),
        migrations.AddField(model_name="citationaudit", name="file_size_bytes", field=models.PositiveIntegerField(default=0)),
        migrations.AddIndex(model_name="citationaudit", index=models.Index(
            fields=["user", "purpose", "-updated_at"], name="citation_owner_purpose_idx")),
    ]
