from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0053_v305_knowledge_image_media"),
    ]

    operations = [
        migrations.AlterField(
            model_name="edition",
            name="publication_mode",
            field=models.CharField(
                choices=[("document", "书目与文献"), ("bibliographic", "纯书目")],
                db_default="document",
                default="document",
                max_length=16,
            ),
        ),
    ]
