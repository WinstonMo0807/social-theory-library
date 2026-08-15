from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0022_organization_authority"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchevaluationrun",
            name="completed_query_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="searchevaluationrun",
            name="task_id",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
    ]
