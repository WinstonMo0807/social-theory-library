"""Canonical search transport uses the existing durable first/deep sessions."""
from django.urls import path
from catalog.discovery_views import (DiscoverySearchView, DiscoverySearchDetailView,
    DiscoverySearchContextView, DiscoverySearchCancelView, DiscoverySearchRetryView)

urlpatterns = [
    path("sessions/", DiscoverySearchView.as_view()),
    path("sessions/<uuid:session_id>/", DiscoverySearchDetailView.as_view()),
    path("sessions/<uuid:session_id>/context/", DiscoverySearchContextView.as_view()),
    path("sessions/<uuid:session_id>/cancel/", DiscoverySearchCancelView.as_view()),
    path("sessions/<uuid:session_id>/retry/", DiscoverySearchRetryView.as_view()),
]
