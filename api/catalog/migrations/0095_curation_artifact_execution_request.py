from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog","0094_knowledge_block_dependencies")]
    operations = [migrations.AddField(model_name="curationartifact",name="execution_request",field=models.JSONField(default=dict))]
