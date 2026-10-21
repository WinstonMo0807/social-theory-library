from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0071_timeline_subject_edition_date_precision")]
    operations = [
        migrations.AddField(model_name="readingpath", name="estimated_weeks", field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="readingpath", name="prerequisite", field=models.TextField(blank=True)),
        migrations.AddField(model_name="readingpath", name="topics", field=models.ManyToManyField(blank=True, related_name="reading_paths", to="catalog.topic")),
        migrations.AddField(model_name="readingpath", name="learning_questions", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="readingpath", name="related_debate_ids", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="readingpath", name="curator_note", field=models.TextField(blank=True)),
        migrations.AddField(model_name="readingpath", name="credits", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="readingpathstage", name="estimated_reading", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="readingpathstage", name="learning_questions", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="readingpathstage", name="related_debate_ids", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="readingpathitem", name="material_kind", field=models.CharField(choices=[("work", "整部作品"), ("chapter", "章节"), ("paper", "论文"), ("node", "知识条目")], default="work", max_length=16)),
        migrations.AddField(model_name="readingpathitem", name="edition", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reading_path_items", to="catalog.edition")),
        migrations.AddField(model_name="readingpathitem", name="asset", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reading_path_items", to="catalog.asset")),
        migrations.AddField(model_name="readingpathitem", name="document_revision", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reading_path_items", to="catalog.documentrevision")),
        migrations.AddField(model_name="readingpathitem", name="chapter_title", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="readingpathitem", name="page_start", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="readingpathitem", name="page_end", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="readingpathitem", name="printed_page_label", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="readingpathitem", name="status", field=models.CharField(choices=[("active", "在读材料"), ("withdrawn", "已撤回材料")], default="active", max_length=16)),
        migrations.AddField(model_name="readingpathitem", name="substitute_edition_ids", field=models.JSONField(blank=True, default=list)),
    ]
