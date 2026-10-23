from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0076_timeline_editorial_details")]
    operations = [migrations.AddField(model_name="readingpathitem", name="learning_goal", field=models.TextField(blank=True)),
                  migrations.AddField(model_name="readingpathitem", name="dependencies", field=models.JSONField(default=list, blank=True))]
