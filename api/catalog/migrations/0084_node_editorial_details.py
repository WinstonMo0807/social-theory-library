from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0083_knowledge_relation_source_anchor")]
    operations = [migrations.AddField(model_name="knowledgenode", name="editorial_details", field=models.JSONField(default=dict, blank=True))]
