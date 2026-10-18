from django.urls import path

from catalog.content_placement_views import (AdminPlacementView, PlacementHistoryView,
                                             PlacementSourcesView, PublicPlacementView)

urlpatterns = [
    path("admin/content-placements/sources/", PlacementSourcesView.as_view(), name="content-placement-sources"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/", AdminPlacementView.as_view(), name="admin-content-placements"),
    path("admin/content-placements/<str:page_type>/<uuid:page_id>/history/", PlacementHistoryView.as_view(), name="content-placement-history"),
    path("content-placements/<str:page_type>/<uuid:page_id>/", PublicPlacementView.as_view(), name="public-content-placements"),
]
