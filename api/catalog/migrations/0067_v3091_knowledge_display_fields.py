from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0066_v3091_public_page_usage")]

    operations = [
        migrations.AddField(
            model_name="knowledgenode", name="summary_source",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="knowledgenode", name="core_concepts",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="knowledgenode", name="keywords",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="discipline", name="display_subdiscipline_ids",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
