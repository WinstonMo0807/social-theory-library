from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0036_editorialrevision_subdiscipline"),
    ]

    operations = [
        migrations.AlterField(
            model_name="editorialrevision",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("work", "作品"),
                    ("knowledge_node", "知识节点"),
                    ("scholar_profile", "学者"),
                    ("discipline", "学科"),
                    ("subdiscipline", "子学科"),
                    ("topic", "主题"),
                    ("reading_path", "阅读路径"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
