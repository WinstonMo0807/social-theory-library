from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0065_content_placement_choice")]
    operations = [migrations.AddField(model_name="page", name="geometry",
                                      field=models.JSONField(default=dict, db_default={}, blank=True))]
