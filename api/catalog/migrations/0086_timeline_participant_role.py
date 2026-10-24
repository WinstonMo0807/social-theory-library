from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0085_scholar_relation_source_anchor")]
    operations = [migrations.AddField(
        model_name="timelineeventrelation", name="participant_role",
        field=models.CharField(blank=True, default="", max_length=20, choices=[
            ("subject", "事件主体"), ("author", "作者"), ("translator", "译者"),
            ("editor", "编者"), ("participant", "参与者"), ("other", "其他角色")]))]
