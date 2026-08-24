from __future__ import annotations

from io import BytesIO
import hmac

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from catalog.models import CapabilityDemand, CapabilityExecutor
from common.remote_worker import (
    REMOTE_TASK_KINDS,
    RemoteWorkerProtocolError,
    bind_remote_lease_context,
    build_remote_job,
    complete_remote_demand,
    sanitize_metadata,
    sanitize_model_revisions,
)
from common.task_runtime import (
    CAPABILITIES,
    claim_demand,
    register_executor_heartbeat,
    release_demand,
    renew_demand_lease,
)


class WorkerPayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "Remote worker payload exceeds the configured limit."
    default_code = "worker_payload_too_large"


class BoundedWorkerJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        limit = int(settings.CAPABILITY_REMOTE_WORKER_MAX_REQUEST_BYTES)
        payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise WorkerPayloadTooLarge()
        return super().parse(
            BytesIO(payload),
            media_type=media_type,
            parser_context=parser_context,
        )


class RemoteWorkerTokenPermission(BasePermission):
    message = "Remote capability worker authentication failed."

    def has_permission(self, request, view):
        if not settings.CAPABILITY_REMOTE_WORKER_ENABLED:
            return False
        expected = str(settings.CAPABILITY_REMOTE_WORKER_SHARED_SECRET or "")
        supplied = str(request.META.get("HTTP_X_LIBRARY_WORKER_TOKEN") or "")
        return bool(
            len(expected) >= 32
            and supplied
            and hmac.compare_digest(expected, supplied)
        )


class HeartbeatSerializer(serializers.Serializer):
    executor_id = serializers.RegexField(r"^[A-Za-z0-9._:-]{1,160}$")
    display_name = serializers.CharField(max_length=240, required=False, allow_blank=True)
    capabilities = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(CAPABILITIES)),
        min_length=1,
        max_length=len(CAPABILITIES),
    )
    model_revisions = serializers.JSONField(required=False, default=dict)
    concurrency = serializers.IntegerField(min_value=1, max_value=16, default=1)
    current_load = serializers.IntegerField(min_value=0, max_value=16, required=False)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        capabilities = sorted(set(attrs["capabilities"]))
        if attrs.get("current_load", 0) > attrs["concurrency"]:
            raise serializers.ValidationError(
                {"current_load": "current_load cannot exceed concurrency."}
            )
        try:
            revisions = sanitize_model_revisions(
                attrs.get("model_revisions"),
                capabilities=capabilities,
            )
        except RemoteWorkerProtocolError as exc:
            raise serializers.ValidationError({"model_revisions": str(exc)}) from exc
        attrs["capabilities"] = capabilities
        attrs["model_revisions"] = revisions
        attrs["metadata"] = sanitize_metadata(attrs.get("metadata"))
        return attrs


class ExecutorSerializer(serializers.Serializer):
    executor_id = serializers.RegexField(r"^[A-Za-z0-9._:-]{1,160}$")


class LeaseSerializer(ExecutorSerializer):
    lease_token = serializers.UUIDField()


class CompletionSerializer(LeaseSerializer):
    completion_id = serializers.RegexField(r"^[A-Za-z0-9._:-]{1,120}$")
    result = serializers.JSONField()

    def validate_result(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("result must be an object.")
        return value


class ReleaseSerializer(LeaseSerializer):
    error_code = serializers.RegexField(r"^[A-Za-z0-9._:-]{1,120}$")
    error_message = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    retry = serializers.BooleanField(default=True)
    retry_after_seconds = serializers.IntegerField(min_value=0, max_value=3600, default=60)


def _protocol_error(exc: RemoteWorkerProtocolError) -> Response:
    return Response(
        {"code": exc.code, "detail": str(exc)},
        status=exc.status_code,
    )


def _lease_error(exc: Exception) -> Response:
    if isinstance(exc, CapabilityDemand.DoesNotExist):
        return Response(
            {"code": "demand_not_found", "detail": "Demand was not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {"code": "lease_not_active", "detail": str(exc)},
        status=status.HTTP_409_CONFLICT,
    )


def _remote_executor(executor_id: str) -> CapabilityExecutor | None:
    return CapabilityExecutor.objects.filter(
        executor_id=executor_id,
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        status=CapabilityExecutor.Status.ONLINE,
        heartbeat_expires_at__gt=timezone.now(),
    ).first()


class RemoteWorkerAPIView(APIView):
    authentication_classes = []
    permission_classes = [RemoteWorkerTokenPermission]
    parser_classes = [BoundedWorkerJSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "capability_worker"


class RemoteWorkerHeartbeatView(RemoteWorkerAPIView):
    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        executor = register_executor_heartbeat(
            executor_id=data["executor_id"],
            display_name=data.get("display_name", ""),
            kind=CapabilityExecutor.Kind.REMOTE_GPU,
            capabilities=data["capabilities"],
            model_revisions=data["model_revisions"],
            concurrency=data["concurrency"],
            current_load=data.get("current_load"),
            metadata={**data["metadata"], "transport": "https_pull"},
            ttl_seconds=settings.CAPABILITY_REMOTE_WORKER_HEARTBEAT_TTL_SECONDS,
        )
        return Response(
            {
                "executor_id": executor.executor_id,
                "status": executor.status,
                "capabilities": executor.capabilities,
                "model_revisions": executor.model_revisions,
                "concurrency": executor.concurrency,
                "current_load": executor.current_load,
                "heartbeat_expires_at": executor.heartbeat_expires_at.isoformat(),
                "server_time": timezone.now().isoformat(),
                "poll_after_seconds": 5,
            }
        )


class RemoteWorkerClaimView(RemoteWorkerAPIView):
    def post(self, request):
        serializer = ExecutorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        executor_id = serializer.validated_data["executor_id"]
        if _remote_executor(executor_id) is None:
            return Response(
                {
                    "code": "remote_executor_not_registered",
                    "detail": "Send a current remote GPU heartbeat before claiming work.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        lease = claim_demand(
            executor_id=executor_id,
            lease_seconds=settings.CAPABILITY_REMOTE_WORKER_LEASE_SECONDS,
            allowed_task_kinds=REMOTE_TASK_KINDS,
        )
        if lease is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        try:
            bind_remote_lease_context(lease)
            job = build_remote_job(lease)
        except RemoteWorkerProtocolError as exc:
            release_demand(
                lease.demand_id,
                lease.lease_token,
                executor_id=executor_id,
                error_code=exc.code,
                error_message=str(exc),
                retry=False,
            )
            return _protocol_error(exc)
        return Response(
            {
                "lease": {
                    "demand_id": str(lease.demand_id),
                    "lease_token": str(lease.lease_token),
                    "lease_expires_at": lease.lease_expires_at.isoformat(),
                    "capability": lease.capability,
                    "attempt": CapabilityDemand.objects.only("attempts").get(pk=lease.demand_id).attempts,
                },
                "job": job,
            }
        )


class RemoteWorkerRenewView(RemoteWorkerAPIView):
    def post(self, request, demand_id):
        serializer = LeaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if _remote_executor(data["executor_id"]) is None:
            return _lease_error(ValueError("Remote executor is not registered."))
        try:
            lease = renew_demand_lease(
                demand_id,
                data["lease_token"],
                executor_id=data["executor_id"],
                lease_seconds=settings.CAPABILITY_REMOTE_WORKER_LEASE_SECONDS,
            )
        except (CapabilityDemand.DoesNotExist, ValueError) as exc:
            return _lease_error(exc)
        return Response(
            {
                "demand_id": str(lease.demand_id),
                "lease_expires_at": lease.lease_expires_at.isoformat(),
            }
        )


class RemoteWorkerCompleteView(RemoteWorkerAPIView):
    def post(self, request, demand_id):
        serializer = CompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if _remote_executor(data["executor_id"]) is None:
            return _lease_error(ValueError("Remote executor is not registered."))
        try:
            completed = complete_remote_demand(
                demand_id,
                executor_id=data["executor_id"],
                lease_token=data["lease_token"],
                completion_id=data["completion_id"],
                result=data["result"],
            )
        except CapabilityDemand.DoesNotExist as exc:
            return _lease_error(exc)
        except RemoteWorkerProtocolError as exc:
            return _protocol_error(exc)
        return Response(completed.as_dict())


class RemoteWorkerReleaseView(RemoteWorkerAPIView):
    def post(self, request, demand_id):
        serializer = ReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if _remote_executor(data["executor_id"]) is None:
            return _lease_error(ValueError("Remote executor is not registered."))
        try:
            demand = release_demand(
                demand_id,
                data["lease_token"],
                executor_id=data["executor_id"],
                error_code=data["error_code"],
                error_message=data.get("error_message", ""),
                retry=data["retry"],
                retry_after_seconds=data["retry_after_seconds"],
            )
        except (CapabilityDemand.DoesNotExist, ValueError) as exc:
            return _lease_error(exc)
        return Response(
            {
                "demand_id": str(demand.id),
                "state": demand.state,
                "retry": data["retry"],
                "publication_blocking": demand.publication_blocking,
            }
        )
