from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0061_discovery_index_projection")]

    operations = [
        # Old 3.0.7 processes do not send this column when creating a legacy
        # index version during preparation or rollback. Keep that insert valid.
        migrations.AlterField(
            model_name="semanticindexversion",
            name="index_family",
            field=models.CharField(
                max_length=16, default="semantic", db_default="semantic", db_index=True,
            ),
        ),
    ]
