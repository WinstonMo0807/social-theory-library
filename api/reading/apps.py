from django.apps import AppConfig


class ReadingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reading"
    verbose_name = "读者数据"

    def ready(self):
        from django.db.models.signals import post_delete
        from . import models
        from .material_preferences import remove_for_deleted_material
        for name in ("ResearchProject", "Annotation", "Bookmark", "PersonalReadingPlan", "ReadingList", "CitationAudit", "ResearchMemory", "SavedItem"):
            post_delete.connect(remove_for_deleted_material, sender=getattr(models, name),
                dispatch_uid=f"reader-material-preference:{name}")
