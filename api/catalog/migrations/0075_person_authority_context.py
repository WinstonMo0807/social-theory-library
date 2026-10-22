from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0074_topic_hierarchy_media")]
    operations = [
        migrations.AddField(model_name="person", name="preferred_language", field=models.CharField(blank=True, max_length=24)),
        migrations.AddField(model_name="person", name="original_language", field=models.CharField(blank=True, max_length=24)),
        migrations.AddField(model_name="person", name="country_region", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="person", name="authority_note", field=models.TextField(blank=True)),
        migrations.AddField(model_name="person", name="identifier_sources", field=models.JSONField(blank=True, default=dict)),
    ]
