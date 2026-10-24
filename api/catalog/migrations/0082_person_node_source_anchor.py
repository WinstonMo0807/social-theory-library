from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0081_person_node_relation_direction")]
    operations = [
        migrations.AddField(model_name="personnoderelation", name="evidence_span", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="person_node_relations", to="catalog.evidencespan")),
        migrations.AddField(model_name="personnoderelation", name="source_document_revision", field=models.ForeignKey(blank=True, null=True,
            on_delete=django.db.models.deletion.PROTECT, related_name="person_node_relations", to="catalog.documentrevision")),
        migrations.AddConstraint(model_name="personnoderelation", constraint=models.CheckConstraint(
            condition=models.Q(evidence_span__isnull=True, source_document_revision__isnull=True)
                | models.Q(evidence_span__isnull=False, source_document_revision__isnull=False), name="person_node_source_pair")),
    ]
