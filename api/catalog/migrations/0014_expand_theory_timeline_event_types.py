from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0013_seed_normalized_knowledge_nodes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="theorytimelineevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("scholar", "学者"),
                    ("publication", "重要发表"),
                    ("concept_proposed", "理论概念提出"),
                    ("school_formation", "学派形成"),
                    ("debate", "争论"),
                    ("institution", "机构"),
                    ("theoretical_turn", "理论转向"),
                    ("translation", "重要译介"),
                    ("china_reception", "进入中国学界"),
                    ("institutionalization", "学科制度化"),
                    ("formation", "形成"),
                    ("development", "发展"),
                ],
                max_length=20,
            ),
        ),
    ]
