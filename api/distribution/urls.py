from django.urls import path

from .views import (
    AssetAccessView,
    AssetFileView,
    BackupJobListView,
    CloudProviderDetailView,
    CloudProviderListView,
    CloudUsageListView,
)

urlpatterns = [
    path("assets/<uuid:asset_id>/access/", AssetAccessView.as_view(), name="asset-access"),
    path("assets/<uuid:asset_id>/file/", AssetFileView.as_view(), name="asset-file"),
    path("providers/", CloudProviderListView.as_view(), name="cloud-provider-list"),
    path("providers/<uuid:pk>/", CloudProviderDetailView.as_view(), name="cloud-provider-detail"),
    path("providers/<uuid:provider_id>/usage/", CloudUsageListView.as_view(), name="cloud-usage-list"),
    path("backups/", BackupJobListView.as_view(), name="backup-job-list"),
]
