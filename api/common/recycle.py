"""One reversible visibility boundary; rows and their historical FKs survive."""
from django.apps import apps
from django.db import models

RECYCLE_MODELS = frozenset({
    "catalog.work", "catalog.edition", "catalog.person", "catalog.scholarprofile",
    "catalog.discipline", "catalog.subdiscipline", "catalog.theoryschool", "catalog.topic",
    "catalog.knowledgenode", "catalog.publisherauthority", "catalog.readingpath",
    "catalog.theorytimelineevent", "catalog.knowledgerelation", "catalog.evidencecuration",
    "catalog.scholarrelation", "catalog.recommendationissue", "catalog.recommendationissueitem",
    "catalog.aboutpageblock", "ingestion.uploaditem",
})


class ActiveRecordManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        label = self.model._meta.label_lower
        if label not in RECYCLE_MODELS:
            return queryset
        entries = apps.get_model("catalog", "RecycleEntry").objects.filter(restored_at__isnull=True)
        queryset = queryset.exclude(pk__in=entries.filter(model_label=label).values("object_id"))
        if label == "catalog.edition":
            queryset = queryset.exclude(work_id__in=entries.filter(model_label="catalog.work").values("object_id"))
        if label == "catalog.scholarprofile":
            queryset = queryset.exclude(person_id__in=entries.filter(model_label="catalog.person").values("object_id"))
        return queryset
