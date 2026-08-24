from django.urls import path

from common.remote_worker_views import (
    RemoteWorkerClaimView,
    RemoteWorkerCompleteView,
    RemoteWorkerHeartbeatView,
    RemoteWorkerReleaseView,
    RemoteWorkerRenewView,
)


urlpatterns = [
    path("heartbeat/", RemoteWorkerHeartbeatView.as_view(), name="remote-worker-heartbeat"),
    path("claim/", RemoteWorkerClaimView.as_view(), name="remote-worker-claim"),
    path(
        "demands/<uuid:demand_id>/renew/",
        RemoteWorkerRenewView.as_view(),
        name="remote-worker-renew",
    ),
    path(
        "demands/<uuid:demand_id>/complete/",
        RemoteWorkerCompleteView.as_view(),
        name="remote-worker-complete",
    ),
    path(
        "demands/<uuid:demand_id>/release/",
        RemoteWorkerReleaseView.as_view(),
        name="remote-worker-release",
    ),
]
