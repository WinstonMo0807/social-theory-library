import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def initialize_independent_states(apps, schema_editor):
    Asset = apps.get_model('catalog', 'Asset')
    Edition = apps.get_model('catalog', 'Edition')
    Page = apps.get_model('catalog', 'Page')

    Asset.objects.filter(status='ready').update(validation_status='valid')
    for edition in Edition.objects.all().iterator():
        updates = {}
        if edition.published_at:
            updates['first_published_at'] = edition.published_at
            updates['last_published_at'] = edition.published_at

        asset = Asset.objects.filter(
            edition_id=edition.pk,
            kind='normalized',
            is_current=True,
        ).order_by('-version', '-created_at').first()
        if asset is not None:
            method = (asset.extraction_method or '').casefold()
            if method == 'embedded':
                updates['ocr_status'] = 'not_required'
            elif 'ocr' in method:
                updates['ocr_status'] = 'succeeded'
            else:
                updates['ocr_status'] = 'pending'
            updates['page_label_status'] = (
                'needs_review' if Page.objects.filter(asset_id=asset.pk).exists() else 'pending'
            )
            if asset.semantic_chunks.filter(index_status='ready').exists():
                updates['semantic_index_status'] = 'ready'
            elif asset.semantic_chunks.exists():
                updates['semantic_index_status'] = 'pending'
        if updates:
            Edition.objects.filter(pk=edition.pk).update(**updates)

    for page in Page.objects.all().iterator():
        if page.printed_label and page.printed_label != str(page.index):
            Page.objects.filter(pk=page.pk).update(
                label_source='pdf_page_labels',
                label_confidence=0.85,
            )
        else:
            Page.objects.filter(pk=page.pk).update(
                label_source='file_index',
                label_confidence=0.25,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0014_expand_theory_timeline_event_types'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SemanticIndexVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('uid', models.CharField(max_length=255, unique=True)),
                ('provider', models.CharField(max_length=40)),
                ('model_repo_id', models.CharField(blank=True, max_length=300)),
                ('model_local_path', models.CharField(blank=True, max_length=1000)),
                ('model_revision', models.CharField(blank=True, max_length=160)),
                ('dimensions', models.PositiveIntegerField(blank=True, null=True)),
                ('pooling', models.CharField(blank=True, max_length=40)),
                ('document_template', models.TextField(blank=True)),
                ('document_count', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('building', '正在建立'), ('ready', '等待切换'), ('active', '生产使用中'), ('failed', '建立失败'), ('retired', '已停用')], db_index=True, default='building', max_length=20)),
                ('activated_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='asset',
            name='processor',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='asset',
            name='processor_version',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='asset',
            name='source_asset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='derivatives', to='catalog.asset'),
        ),
        migrations.AddField(
            model_name='asset',
            name='validation_details',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='asset',
            name='validation_status',
            field=models.CharField(choices=[('pending', '等待验证'), ('valid', '验证通过'), ('invalid', '验证失败')], db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='edition',
            name='first_published_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='edition',
            name='last_published_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='edition',
            name='ocr_status',
            field=models.CharField(choices=[('not_required', '无需 OCR'), ('pending', '等待 OCR'), ('running', 'OCR 处理中'), ('succeeded', 'OCR 已完成'), ('failed', 'OCR 失败'), ('disabled', 'OCR 已停用')], db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='edition',
            name='page_label_status',
            field=models.CharField(choices=[('pending', '等待识别'), ('ready', '已就绪'), ('needs_review', '需要校对')], db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='edition',
            name='reader_rendition_policy',
            field=models.CharField(choices=[('auto', '自动选择'), ('original', '强制原始 PDF'), ('ocr', '强制 OCR PDF')], default='auto', max_length=20),
        ),
        migrations.AddField(
            model_name='edition',
            name='review_progress',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='edition',
            name='review_status',
            field=models.CharField(choices=[('not_started', '尚未复核'), ('in_progress', '复核中'), ('completed', '复核完成')], db_index=True, default='not_started', max_length=20),
        ),
        migrations.AddField(
            model_name='edition',
            name='semantic_index_status',
            field=models.CharField(choices=[('not_indexed', '尚未建立'), ('pending', '等待建立'), ('running', '正在建立'), ('ready', '已就绪'), ('failed', '建立失败')], db_index=True, default='not_indexed', max_length=20),
        ),
        migrations.AddField(
            model_name='page',
            name='is_label_anchor',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='page',
            name='is_label_manual',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='page',
            name='label_confidence',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='page',
            name='label_segment',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='page',
            name='label_source',
            field=models.CharField(choices=[('manual', '人工校对'), ('pdf_page_labels', 'PDF PageLabels'), ('ocr', 'OCR 识别'), ('sequence', '序列推算'), ('file_index', 'PDF 页序回退'), ('unknown', '未知')], db_index=True, default='unknown', max_length=24),
        ),
        migrations.AlterField(
            model_name='asset',
            name='kind',
            field=models.CharField(choices=[('original', '原始文件'), ('normalized', '规范阅读文件'), ('ocr_pdf', 'OCR 阅读文件'), ('web_derivative', '网页阅读派生文件')], max_length=20),
        ),
        migrations.CreateModel(
            name='SearchQueryAggregate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('period_start', models.DateField(db_index=True)),
                ('period', models.CharField(default='day', max_length=16)),
                ('normalized_query', models.CharField(max_length=500)),
                ('search_count', models.PositiveIntegerField(default=0)),
                ('unique_sessions', models.PositiveIntegerField(default=0)),
                ('click_count', models.PositiveIntegerField(default=0)),
                ('zero_result_count', models.PositiveIntegerField(default=0)),
                ('excluded', models.BooleanField(db_index=True, default=False)),
            ],
            options={
                'ordering': ['-period_start', '-search_count', 'normalized_query'],
                'constraints': [models.UniqueConstraint(fields=('period_start', 'period', 'normalized_query'), name='unique_search_query_aggregate_period')],
            },
        ),
        migrations.AddField(
            model_name='semanticindexjob',
            name='index_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='jobs', to='catalog.semanticindexversion'),
        ),
        migrations.CreateModel(
            name='AnonymousUsageEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_type', models.CharField(choices=[('reader_open', '打开阅读器'), ('search_submit', '提交检索'), ('search_result_click', '点击检索结果'), ('download', '下载')], db_index=True, max_length=32)),
                ('session_hash', models.CharField(db_index=True, max_length=64)),
                ('normalized_query', models.CharField(blank=True, db_index=True, max_length=500)),
                ('result_count', models.PositiveIntegerField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='anonymous_usage_events', to='catalog.asset')),
                ('work', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='anonymous_usage_events', to='catalog.work')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['event_type', 'created_at'], name='catalog_ano_event_t_b13e11_idx'), models.Index(fields=['normalized_query', 'created_at'], name='catalog_ano_normali_53e60a_idx')],
            },
        ),
        migrations.CreateModel(
            name='PageLabelSegment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('start_file_page_index', models.PositiveIntegerField()),
                ('end_file_page_index', models.PositiveIntegerField(blank=True, null=True)),
                ('start_label', models.CharField(blank=True, max_length=40)),
                ('style', models.CharField(choices=[('arabic', '阿拉伯数字'), ('roman_lower', '小写罗马数字'), ('roman_upper', '大写罗马数字'), ('custom', '自定义'), ('none', '无页码')], default='arabic', max_length=20)),
                ('source', models.CharField(choices=[('manual', '人工校对'), ('pdf_page_labels', 'PDF PageLabels'), ('ocr', 'OCR 识别'), ('sequence', '序列推算'), ('file_index', 'PDF 页序回退'), ('unknown', '未知')], default='manual', max_length=24)),
                ('confidence', models.FloatField(default=1)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='page_label_segments', to='catalog.asset')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_page_label_segments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['start_file_page_index'],
                'constraints': [models.UniqueConstraint(fields=('asset', 'start_file_page_index'), name='unique_page_label_segment_start')],
            },
        ),
        migrations.RunPython(initialize_independent_states, migrations.RunPython.noop),
    ]
