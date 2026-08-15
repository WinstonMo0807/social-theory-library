from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_semanticindexversion_asset_processor_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="page",
            name="text_source",
            field=models.CharField(
                choices=[
                    ("none", "尚无文字"),
                    ("embedded", "PDF 原生文本"),
                    ("ocr", "OCR"),
                    ("hybrid", "混合"),
                ],
                max_length=16,
            ),
        ),
    ]
