from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0102_merge_citation_name_and_retrieval")]
    operations = [
        migrations.AddField(
            model_name="curationrun", name="plan_version",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "Window fold"), (2, "Ordered chapter batches")], default=1),
        ),
    ]
