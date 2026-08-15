from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0025_semantic_index_v2_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="semanticsearchfeedback",
            name="feedback_key",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddConstraint(
            model_name="semanticsearchfeedback",
            constraint=models.UniqueConstraint(
                condition=~models.Q(feedback_key=""),
                fields=("feedback_key",),
                name="unique_nonempty_semantic_feedback_key",
            ),
        ),
    ]
