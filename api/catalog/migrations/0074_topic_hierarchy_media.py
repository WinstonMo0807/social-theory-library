from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0073_scholar_years_contribution_scope")]

    operations = [
        migrations.AddField(model_name="topic", name="parent", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="children", to="catalog.topic")),
        migrations.AddField(model_name="topic", name="hero_rendition", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="topic_images", to="catalog.mediarendition")),
        migrations.AddConstraint(model_name="topic", constraint=models.CheckConstraint(
            condition=~models.Q(id=models.F("parent_id")), name="topic_parent_not_self")),
    ]
