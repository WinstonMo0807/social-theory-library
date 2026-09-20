from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0016_v305_session_metadata_candidates")]
    operations = [migrations.AlterField(model_name="uploadbatch", name="external_enrichment_enabled", field=models.BooleanField(default=False))]
