from django.urls import path
from catalog.placement_directory import PlacementPageDirectoryView
from catalog.placement_parent_preview import PlacementParentPreviewView

from catalog.content_placement_views import (AdminPlacementView, PlacementHistoryView,
                                             PlacementSourcesView, PublicPlacementView, PlacementReceiptView)

urlpatterns = [
    path("admin/content-placements/pages/", PlacementPageDirectoryView.as_view(), name="content-placement-pages"),
    path("admin/content-placements/sources/", PlacementSourcesView.as_view(), name="content-placement-sources"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/", AdminPlacementView.as_view(), name="admin-content-placements"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/history/", PlacementHistoryView.as_view(), name="content-placement-history"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/parent-preview/", PlacementParentPreviewView.as_view(), name="content-placement-parent-preview"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/commands/<uuid:request_id>/", PlacementReceiptView.as_view(), name="content-placement-receipt"),
    path("content-placements/<str:page_type>/<uuid:page_id>/", PublicPlacementView.as_view(), name="public-content-placements"),
]
