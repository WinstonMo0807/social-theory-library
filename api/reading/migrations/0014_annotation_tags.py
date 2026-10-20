"""Private Reader labels; no data backfill or decryption during migration."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0013_source_follow")]
    operations = [
        migrations.AddField(
            model_name="annotation",
            name="tags_ciphertext",
            field=models.BinaryField(blank=True, default=bytes),
        ),
    ]
