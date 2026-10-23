from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0075_person_authority_context")]
    operations = [
        migrations.AlterField(model_name="theorytimelineevent", name="source", field=models.CharField(max_length=1000, blank=True)),
        migrations.AddField(model_name="theorytimelineevent", name="editorial_details", field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name="theorytimelineevent", name="start_date", field=models.DateField(null=True, blank=True)),
        migrations.AddField(model_name="theorytimelineevent", name="end_date", field=models.DateField(null=True, blank=True)),
        migrations.AlterField(model_name="theorytimelineevent", name="date_precision", field=models.CharField(max_length=16, default="unknown", choices=[('day', '日期'), ('month', '月份'), ('unknown', '精度未确认'), ('year', '确切年份'), ('approximate', '约年'), ('range', '时间区间')])),
        migrations.AlterField(model_name="theorytimelineevent", name="event_type", field=models.CharField(max_length=20, choices=[('birth', '人物出生'), ('death', '人物去世'), ('appointment', '任职任教'), ('scholar', '学者'), ('publication', '重要发表'), ('concept_proposed', '理论概念提出'), ('school_formation', '学派形成'), ('debate', '争论'), ('institution', '机构'), ('theoretical_turn', '理论转向'), ('translation', '重要译介'), ('china_reception', '进入中国学界'), ('institutionalization', '学科制度化'), ('formation', '形成'), ('development', '发展')])),
    ]
