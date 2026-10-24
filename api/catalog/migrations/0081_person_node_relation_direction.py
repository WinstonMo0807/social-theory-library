from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0080_edition_supporting_material")]
    operations = [
        migrations.AddField(model_name="personnoderelation", name="relation_type", field=models.CharField(max_length=24,
            choices=[("related", "相关"), ("proposes", "提出"), ("defines", "定义"), ("develops", "发展"), ("criticizes", "批判"), ("interprets", "解释"), ("uses", "运用"), ("influences", "影响")], default="related")),
        migrations.AddField(model_name="personnoderelation", name="direction", field=models.CharField(max_length=20,
            choices=[("directed", "有方向"), ("undirected", "无方向")], default="undirected")),
        migrations.AddField(model_name="personnoderelation", name="node_is_source", field=models.BooleanField(default=False)),
    ]
