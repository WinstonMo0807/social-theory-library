from django.urls import path
from .reader_ocr_views import ReaderOCRStatusView
from .storage_views import StorageWorkspaceView, StorageCommandView, StorageBackupDetailView, StorageReceiptView, VerificationHistoryView

from .views import (
    AdminAssetPreviewView,
    AssetAccessView,
    AssetFileView,
    BackupJobListView,
    CloudProviderDetailView,
    CloudProviderListView,
    CloudUsageListView,
)

urlpatterns = [
    path("storage/", StorageWorkspaceView.as_view(), name="storage-workspace"),
    path("storage/commands/", StorageCommandView.as_view(), name="storage-command"),
    path("storage/commands/<uuid:request_id>/", StorageReceiptView.as_view(), name="storage-receipt"),
    path("storage/verifications/", VerificationHistoryView.as_view(), name="storage-verification-history"),
    path("storage/backups/<uuid:backup_id>/", StorageBackupDetailView.as_view(), name="storage-backup-detail"),
    path("assets/<uuid:asset_id>/ocr-status/", ReaderOCRStatusView.as_view(), name="reader-ocr-status"),
    path("admin/assets/<uuid:asset_id>/preview/", AdminAssetPreviewView.as_view(), name="admin-asset-preview"),
    path("assets/<uuid:asset_id>/access/", AssetAccessView.as_view(), name="asset-access"),
    path("assets/<uuid:asset_id>/file/", AssetFileView.as_view(), name="asset-file"),
    path("providers/", CloudProviderListView.as_view(), name="cloud-provider-list"),
    path("providers/<uuid:pk>/", CloudProviderDetailView.as_view(), name="cloud-provider-detail"),
    path("providers/<uuid:provider_id>/usage/", CloudUsageListView.as_view(), name="cloud-usage-list"),
    path("backups/", BackupJobListView.as_view(), name="backup-job-list"),
]
