"""Wake the projection queue after commits; reconciliation also catches bulk writes."""
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from catalog import models

logger = logging.getLogger(__name__)


def _wake():
    try:
        if cache.add("discovery:reconcile:dispatch", True, timeout=30):
            from catalog.discovery_index_tasks import reconcile_discovery_index
            reconcile_discovery_index.apply_async(countdown=3,
                queue=getattr(settings, "DISCOVERY_INDEX_TASK_QUEUE", "discovery_index"), expires=240)
    except Exception as exc:
        # Publication remains durable if the derived queue is down. Periodic
        # reconciliation and Processing Center recover/report the missing work.
        logger.warning("Discovery update dispatch unavailable: %s", type(exc).__name__)


def _changed(sender, instance, **kwargs):
    if not getattr(settings, "DISCOVERY_ENABLED", False) or kwargs.get("raw"):
        return
    transaction.on_commit(_wake)


for _model in (
    models.Edition, models.Asset, models.Page, models.DocumentRevision,
    models.EvidenceSpan, models.CatalogPublicationRevision, models.KnowledgePublicationEvent,
    models.Person, models.ScholarProfile, models.KnowledgeNode, models.KnowledgeNodeAlias,
    models.Topic, models.Discipline, models.Subdiscipline, models.Concept,
    models.ReadingPath, models.ReadingPathItem, models.ReadingPathStage,
    models.RecommendationIssue, models.EditorialRevision, models.EvidenceCuration,
    models.TheoryTimelineEvent, models.WorkKnowledgeRelation,
):
    post_save.connect(_changed, sender=_model, weak=False, dispatch_uid=f"discovery:{_model.__name__}:save")
    post_delete.connect(_changed, sender=_model, weak=False, dispatch_uid=f"discovery:{_model.__name__}:delete")
