# Generated for Social Theory Library 3.0.1 Product Integration Pass.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0034_v3_intelligence_retrieval"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="edition",
            name="publication_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="canonical_revision",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="draft_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="draft_session_id",
            field=models.CharField(blank=True, max_length=96),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="is_current",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="stale_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="superseded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="superseded_runs",
                to="catalog.researchrun",
            ),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="trigger_input_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="researchrun",
            name="trigger_input_values",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="editionworkflowdecision",
            name="step_key",
            field=models.CharField(
                choices=[
                    ("work", "作品识别"),
                    ("bibliography", "书目与出版"),
                    ("contributors", "作者与责任者"),
                    ("classification", "社科分类"),
                    ("knowledge", "理论、主题与知识关系"),
                    ("reader", "文本与阅读文件"),
                    ("curation", "知识策展与前台联动"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="researchrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "等待外部研究"),
                    ("running", "研究中"),
                    ("completed", "完成"),
                    ("degraded", "部分来源不可用"),
                    ("failed", "失败"),
                    ("canceled", "已取消"),
                    ("superseded", "草稿变化后已过期"),
                ],
                db_index=True,
                default="queued",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="researchrun",
            index=models.Index(
                fields=["edition", "draft_session_id", "is_current", "created_at"],
                name="catalog_res_edition_010ded_idx",
            ),
        ),
    ]
