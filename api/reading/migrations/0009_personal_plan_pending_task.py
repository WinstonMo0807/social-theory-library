from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reading", "0008_private_research")]

    operations = [
        migrations.AddField(
            model_name="personalreadingplan",
            name="task_pending",
            field=models.BooleanField(db_index=True, default=None, null=True),
        ),
    ]
