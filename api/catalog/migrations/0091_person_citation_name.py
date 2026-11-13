from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0090_scholar_slug_unicode")]
    operations = [migrations.AddField(
        model_name="person", name="citation_name",
        field=models.CharField(max_length=240, blank=True),
    )]
