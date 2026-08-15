from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0020_semantic_chunk_stability_and_search_evaluation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="access_status",
            field=models.CharField(
                choices=[
                    ("inherit", "继承版本权限"),
                    ("private", "仅后台可用"),
                    ("registered", "登录读者"),
                    ("restricted", "受限访问"),
                    ("public", "公开访问"),
                ],
                db_index=True,
                default="inherit",
                max_length=20,
            ),
        ),
    ]
