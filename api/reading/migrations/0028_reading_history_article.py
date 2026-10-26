from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reading", "0027_research_replay_revisions"), ("catalog", "0089_legacy_knowledge_insert_defaults")]
    operations = [
        migrations.AlterField(model_name="readinghistory", name="asset", field=models.ForeignKey(
            to="catalog.asset", null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name="reading_history")),
        migrations.AddField(model_name="readinghistory", name="issue", field=models.ForeignKey(
            to="catalog.recommendationissue", null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name="reading_history")),
        migrations.AddConstraint(model_name="readinghistory", constraint=models.CheckConstraint(
            condition=models.Q(asset__isnull=False, issue__isnull=True) | models.Q(asset__isnull=True, issue__isnull=False),
            name="reading_history_one_source")),
    ]
