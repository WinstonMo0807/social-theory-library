from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "馆藏与知识关系"

    def ready(self):
        import config.schema  # noqa: F401 - register authentication schema extension
        import catalog.discovery_signals  # noqa: F401 - after-commit projection updates
