from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0025_reader_material_preferences")]
    operations = [migrations.AddField(model_name="readinglist", name="topic_ids", field=models.JSONField(default=list, blank=True))]
