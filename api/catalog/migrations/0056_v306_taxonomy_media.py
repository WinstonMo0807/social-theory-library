import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0055_v306_relation_timeline_editorial")]
    operations = [
        migrations.AddField(model_name=name, name="hero_rendition", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name=f"{name}_images", to="catalog.mediarendition",
        )) for name in ("discipline", "subdiscipline")
    ]
