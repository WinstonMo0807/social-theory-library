from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0028_query_lexicon_candidates"),
        ("ingestion", "0010_processing_pause_controls"),
    ]

    operations = [
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
                    ("query_lexicon_candidates", "术语候选提取"),
                    ("thumbnail", "缩略图"),
                    ("cache_refresh", "公开目录刷新"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
