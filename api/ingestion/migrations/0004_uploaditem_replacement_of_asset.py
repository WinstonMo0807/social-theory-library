import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0003_alter_uploaditem_file_storage"),
    ]

    operations = [
        migrations.AddField(
            model_name="uploaditem",
            name="replacement_of_asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="replacement_uploads",
                to="catalog.asset",
            ),
        ),
    ]
