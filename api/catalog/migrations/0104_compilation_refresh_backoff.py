from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0103_curationrun_plan_version")]
    operations = [
        migrations.AddField(model_name="knowledgecompilation", name="next_refresh_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True)),
        migrations.AddField(model_name="knowledgecompilation", name="refresh_failures",
            field=models.PositiveSmallIntegerField(default=0)),
    ]
