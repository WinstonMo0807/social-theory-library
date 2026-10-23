from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0077_reading_path_dependencies")]
    operations = [
        migrations.AlterField(model_name="work", name="document_type", field=models.CharField(max_length=32, db_index=True, choices=[("book", "图书"), ("journal_article", "期刊论文"), ("journal_issue", "整期期刊"), ("thesis", "学位论文"), ("report", "研究报告"), ("chapter", "论文集章节"), ("other", "其他资料")])),
        migrations.AlterField(model_name="semanticchunk", name="document_type", field=models.CharField(max_length=32, choices=[("book", "图书"), ("journal_article", "期刊论文"), ("journal_issue", "整期期刊"), ("thesis", "学位论文"), ("report", "研究报告"), ("chapter", "论文集章节"), ("other", "其他资料")])),
        migrations.AddField(model_name="edition", name="series_number", field=models.CharField(max_length=80, blank=True)),
        migrations.AddField(model_name="edition", name="container_title", field=models.CharField(max_length=600, blank=True)),
    ]
