from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0040_v304_cataloging_intelligence")]

    operations = [
        migrations.AddField(
            model_name="asset", name="text_revision",
            field=models.PositiveIntegerField(default=0, db_index=True),
        ),
        migrations.RemoveConstraint(model_name="asset", name="unique_asset_hash_per_kind"),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.UniqueConstraint(
                fields=("sha256", "kind"), condition=models.Q(text_revision=0),
                name="unique_asset_hash_per_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.UniqueConstraint(
                fields=("edition", "kind", "text_revision"),
                condition=models.Q(text_revision__gt=0), name="unique_asset_text_revision",
            ),
        ),
    ]
