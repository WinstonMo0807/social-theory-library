from django.db import migrations, models

import ingestion.models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uploaditem",
            name="file",
            field=models.FileField(
                blank=True,
                max_length=1000,
                upload_to=ingestion.models.intake_upload_path,
            ),
        ),
    ]
