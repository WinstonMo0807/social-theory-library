from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0022_research_import_receipt")]
    operations = [
        migrations.AddField(model_name="readinglist", name="goal", field=models.CharField(max_length=2000, blank=True)),
        migrations.AddField(model_name="readinglist", name="tags", field=models.JSONField(default=list, blank=True)),
        migrations.AddField(model_name="readinglist", name="origin_key", field=models.CharField(max_length=64, blank=True, db_index=True)),
        migrations.AddField(model_name="readinglistitem", name="removed_at", field=models.DateTimeField(null=True, blank=True, db_index=True)),
    ]
