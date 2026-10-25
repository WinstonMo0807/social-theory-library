"""Fail closed before a node rollback can overwrite later editorial work."""
from django.db.models import Q
from catalog import models
from catalog.services.person_authority import digest


def merge_scope_queries(source_id, target_id):
    ids = [source_id, target_id]
    relations = models.KnowledgeRelation.objects.filter(Q(source_node_id__in=ids) | Q(target_node_id__in=ids))
    work_relations = models.WorkNodeRelation.objects.filter(node_id__in=ids)
    rows = {
        "KnowledgeNode": models.KnowledgeNode.objects.filter(pk__in=ids),
        "KnowledgeRelation": relations,
        "WorkNodeRelation": work_relations,
        "ReadingPathItem": models.ReadingPathItem.objects.filter(node_id__in=ids),
        "TheoryReviewTask": models.TheoryReviewTask.objects.filter(candidate_node_id__in=ids),
        "KnowledgeNodeVersion": models.KnowledgeNodeVersion.objects.filter(node_id__in=ids),
        "KnowledgeRelationVersion": models.KnowledgeRelationVersion.objects.filter(relation_id__in=relations.values("pk")),
        "EvidenceSnippet": models.EvidenceSnippet.objects.filter(Q(node_id__in=ids)
            | Q(knowledge_relation_id__in=relations.values("pk")) | Q(work_node_relation_id__in=work_relations.values("pk"))),
        "EditorialRevision": models.EditorialRevision.objects.filter(Q(target_type="knowledge_node", target_id__in=ids)
            | Q(target_type="knowledge_relation", target_id__in=relations.values("pk"))),
    }
    for model in (models.PersonNodeRelation, models.KnowledgeNodeAlias, models.KnowledgeNodeDiscipline,
            models.KnowledgeNodeSubdiscipline, models.KnowledgeNodeTopic, models.TimelineEventRelation, models.LegacyKnowledgeMapping):
        rows[model.__name__] = model.objects.filter(node_id__in=ids)
    return rows


def merge_scope_fingerprint(source_id, target_id, *, lock=True):
    # ponytail: bounded original graph snapshot, no second history store. Large
    # merges need an explicit staged recovery workflow instead of an unsafe truncation.
    snapshots = {}
    for name, rows in sorted(merge_scope_queries(source_id, target_id).items()):
        if lock:
            rows = rows.select_for_update()
        values = list(rows.order_by("pk").values()[:5001])
        if len(values) > 5000:
            raise ValueError("相关记录超过单次安全回退范围，请先缩小合并范围；本次没有改写数据。")
        snapshots[name] = [digest(row) for row in values]
    return digest(snapshots)
