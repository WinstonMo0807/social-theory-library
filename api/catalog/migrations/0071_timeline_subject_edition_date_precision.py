from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0070_public_feedback_workflow")]

    operations = [
        migrations.AddField(
            model_name="theorytimelineevent", name="subject_edition",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="subject_timeline_events", to="catalog.edition",
            ),
        ),
        migrations.AddField(
            model_name="theorytimelineevent", name="date_precision",
            field=models.CharField(
                choices=[("unknown", "精度未确认"), ("year", "确切年份"),
                         ("approximate", "约年"), ("range", "时间区间")],
                default="unknown", max_length=16,
            ),
        ),
    ]
