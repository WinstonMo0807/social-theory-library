from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0023_search_evaluation_task_tracking"),
    ]

    operations = [
        migrations.AlterField(
            model_name="searchevaluationjudgment",
            name="relevance",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "不相关"),
                    (1, "同主题但未回应"),
                    (2, "具有实质证据价值"),
                    (3, "直接回应问题"),
                ],
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(3),
                ],
            ),
        ),
    ]
