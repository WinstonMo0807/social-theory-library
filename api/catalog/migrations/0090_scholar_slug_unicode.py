from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0089_legacy_knowledge_insert_defaults")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="scholarprofile",
                    name="slug",
                    field=models.SlugField(max_length=180, unique=True, allow_unicode=True),
                ),
            ],
        ),
    ]
