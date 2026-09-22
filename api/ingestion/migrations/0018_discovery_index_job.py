from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ingestion", "0017_v307_local_upload_default")]
    operations = [migrations.AlterField(model_name="processingjob", name="job_type", field=models.CharField(
        choices=[("ocr", "OCR"), ("external_enrichment", "联网补充"), ("text_extraction", "文本提取"),
                 ("page_labels", "页码识别"), ("semantic_index", "语义索引"), ("discovery_index", "观点检索索引"),
                 ("query_lexicon_candidates", "术语候选提取"), ("query_lexicon_reconcile", "QueryLexicon 重建"),
                 ("projection_refresh", "公开投影刷新"), ("thumbnail", "缩略图"), ("cache_refresh", "公开目录刷新"),
                 ("r2_staging", "R2 上传中转")], db_index=True, max_length=32))]
