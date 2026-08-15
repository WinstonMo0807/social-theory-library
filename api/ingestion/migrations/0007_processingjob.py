import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0015_semanticindexversion_asset_processor_and_more'),
        ('ingestion', '0006_uploaditem_dispatch_state'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcessingJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job_type', models.CharField(choices=[('ocr', 'OCR'), ('text_extraction', '文本提取'), ('page_labels', '页码识别'), ('semantic_index', '语义索引'), ('thumbnail', '缩略图'), ('cache_refresh', '公开目录刷新')], db_index=True, max_length=32)),
                ('status', models.CharField(choices=[('pending', '等待处理'), ('running', '处理中'), ('succeeded', '完成'), ('failed', '失败'), ('canceled', '已取消')], db_index=True, default='pending', max_length=20)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('engine', models.CharField(blank=True, max_length=120)),
                ('attempt', models.PositiveSmallIntegerField(default=0)),
                ('max_attempts', models.PositiveSmallIntegerField(default=3)),
                ('settings_version', models.CharField(blank=True, max_length=80)),
                ('task_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('error_code', models.CharField(blank=True, max_length=120)),
                ('error_message', models.TextField(blank=True)),
                ('stats', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processing_jobs', to='catalog.asset')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_processing_jobs', to=settings.AUTH_USER_MODEL)),
                ('edition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processing_jobs', to='catalog.edition')),
                ('upload_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processing_jobs', to='ingestion.uploaditem')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['status', 'created_at'], name='ingestion_p_status_35831b_idx'), models.Index(fields=['job_type', 'status'], name='ingestion_p_job_typ_b0f2f4_idx')],
            },
        ),
    ]
