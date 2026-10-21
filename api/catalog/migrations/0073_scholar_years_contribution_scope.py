from django.db import migrations, models
import catalog.models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0072_reading_path_material_identity")]
    operations = [
        migrations.AlterField(model_name="person", name="birth_year", field=models.SmallIntegerField(blank=True, null=True, validators=[catalog.models.validate_person_year])),
        migrations.AlterField(model_name="person", name="death_year", field=models.SmallIntegerField(blank=True, null=True, validators=[catalog.models.validate_person_year])),
        migrations.AddField(model_name="contribution", name="scope", field=models.JSONField(blank=True, default=dict)),
    ]
