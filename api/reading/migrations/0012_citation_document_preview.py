from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0011_reader_privacy_operations")]

    operations = [
        migrations.AddField(model_name="citationaudit", name="preview_ciphertext", field=models.BinaryField(blank=True, default=bytes)),
        migrations.AddField(model_name="citationaudit", name="preview_state", field=models.JSONField(blank=True, default=dict)),
    ]
