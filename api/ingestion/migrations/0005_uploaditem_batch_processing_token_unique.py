from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0004_uploaditem_replacement_of_asset"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="uploaditem",
            constraint=models.UniqueConstraint(
                condition=models.Q(("processing_token", ""), _negated=True),
                fields=("batch", "processing_token"),
                name="unique_batch_processing_token",
            ),
        ),
    ]
