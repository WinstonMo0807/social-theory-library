import catalog.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_covercandidate"),
    ]

    operations = [
        migrations.AlterField(
            model_name="concept",
            name="hero_image",
            field=models.ImageField(
                blank=True,
                upload_to="public/knowledge/%Y/%m/",
            ),
        ),
        migrations.AlterField(
            model_name="covercandidate",
            name="thumbnail",
            field=models.ImageField(
                max_length=1000,
                upload_to=catalog.models.cover_candidate_upload_path,
            ),
        ),
        migrations.AlterField(
            model_name="person",
            name="portrait",
            field=models.ImageField(
                blank=True,
                upload_to="public/people/%Y/%m/",
            ),
        ),
        migrations.AlterField(
            model_name="theoryschool",
            name="hero_image",
            field=models.ImageField(
                blank=True,
                upload_to="public/knowledge/%Y/%m/",
            ),
        ),
        migrations.AlterField(
            model_name="topic",
            name="hero_image",
            field=models.ImageField(
                blank=True,
                upload_to="public/knowledge/%Y/%m/",
            ),
        ),
        migrations.AlterField(
            model_name="work",
            name="cover",
            field=models.ImageField(
                blank=True,
                upload_to="public/covers/%Y/%m/",
            ),
        ),
    ]
