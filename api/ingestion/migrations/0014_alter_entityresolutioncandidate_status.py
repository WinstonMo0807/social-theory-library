# Generated for Social Theory Library 3.0.1 Product Integration Pass.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0013_uploaditem_staging_backend_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entityresolutioncandidate",
            name="status",
            field=models.CharField(
                choices=[
                    ("proposed", "待判断"),
                    ("stale", "草稿变化后已过期"),
                    ("linked", "已关联现有实体"),
                    ("create_draft", "创建新实体草稿"),
                    ("unresolved", "保留未解析名称"),
                    ("ignored", "已忽略"),
                    ("rejected", "已拒绝"),
                ],
                db_index=True,
                default="proposed",
                max_length=24,
            ),
        ),
    ]
