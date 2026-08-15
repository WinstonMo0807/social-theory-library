from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0009_decision_reversal"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingjob",
            name="pause_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="processingjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("ocr", "OCR"),
                    ("external_enrichment", "联网补充"),
                    ("text_extraction", "文本提取"),
                    ("page_labels", "页码识别"),
                    ("semantic_index", "语义索引"),
                    ("thumbnail", "缩略图"),
                    ("cache_refresh", "公开目录刷新"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="processingjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "等待处理"),
                    ("running", "处理中"),
                    ("paused", "已暂停"),
                    ("succeeded", "完成"),
                    ("failed", "失败"),
                    ("canceled", "已取消"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
