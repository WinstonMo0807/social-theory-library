from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0017_alter_page_label_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="semanticindexversion",
            name="expected_document_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="semanticindexversion",
            name="validation_details",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
