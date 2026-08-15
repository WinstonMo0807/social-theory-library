from django.db import migrations, models

import ingestion.models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0002_alter_uploaditem_file"),
    ]

    operations = [
        migrations.AlterField(
            model_name="uploaditem",
            name="file",
            field=models.FileField(
                blank=True,
                max_length=1000,
                storage=ingestion.models.intake_storage,
                upload_to=ingestion.models.intake_upload_path,
            ),
        ),
    ]
