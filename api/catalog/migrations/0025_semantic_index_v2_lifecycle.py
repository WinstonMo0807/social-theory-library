from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0024_search_evaluation_relevance_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="semanticindexjob",
            name="pause_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="semanticindexversion",
            name="config_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
