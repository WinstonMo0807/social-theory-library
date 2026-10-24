from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0082_person_node_source_anchor")]
    operations = [
        migrations.AddField(model_name="knowledgerelation", name="evidence_span", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="knowledge_relations", to="catalog.evidencespan")),
        migrations.AddField(model_name="knowledgerelation", name="source_document_revision", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="knowledge_relations", to="catalog.documentrevision")),
        migrations.AddConstraint(model_name="knowledgerelation", constraint=models.CheckConstraint(
            condition=models.Q(evidence_span__isnull=True, source_document_revision__isnull=True)
                | models.Q(evidence_span__isnull=False, source_document_revision__isnull=False), name="knowledge_relation_source_pair")),
    ]
