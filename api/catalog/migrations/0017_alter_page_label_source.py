from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0016_alter_page_text_source")]

    operations = [
        migrations.AlterField(
            model_name="page",
            name="label_source",
            field=models.CharField(
                choices=[
                    ("manual", "人工校对"),
                    ("pdf_page_labels", "PDF PageLabels"),
                    ("embedded_text", "PDF 原生页眉页脚"),
                    ("ocr", "OCR 识别"),
                    ("sequence", "序列推算"),
                    ("file_index", "PDF 页序回退"),
                    ("unknown", "未知"),
                ],
                db_index=True,
                default="unknown",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="pagelabelsegment",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "人工校对"),
                    ("pdf_page_labels", "PDF PageLabels"),
                    ("embedded_text", "PDF 原生页眉页脚"),
                    ("ocr", "OCR 识别"),
                    ("sequence", "序列推算"),
                    ("file_index", "PDF 页序回退"),
                    ("unknown", "未知"),
                ],
                default="manual",
                max_length=24,
            ),
        ),
    ]
