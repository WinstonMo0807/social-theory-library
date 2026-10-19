"""Public submission and administrator-only general feedback handling."""
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from common.permissions import IsLibraryAdmin
from .editorial_read import AdminPrivateResponseMixin
from .feedback_serializers import (FeedbackDetailOutput, FeedbackHistoryQuery, FeedbackListOutput,
    FeedbackListQuery, FeedbackUpdateInput, FeedbackUpdateOutput, PublicFeedbackInput, PublicFeedbackReceipt)
from .models import PublicFeedback
from .services import public_feedback as feedback


class FeedbackBurstThrottle(SimpleRateThrottle):
    scope = "public_feedback_burst"
    rate = "6/min"

    def get_cache_key(self, request, view):
        actor = request.user
        # Forwarding and internal headers supplied by the caller cannot bypass this budget.
        identity = f"user:{actor.pk}" if actor.is_authenticated else f"peer:{request.META.get('REMOTE_ADDR', 'unknown')}"
        opaque = salted_hmac(self.scope, identity, algorithm="sha256").hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": opaque}


class FeedbackDailyThrottle(FeedbackBurstThrottle):
    scope = "public_feedback_daily"
    rate = "30/day"


class PublicFeedbackView(AdminPrivateResponseMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [FeedbackBurstThrottle, FeedbackDailyThrottle]

    @extend_schema(request=PublicFeedbackInput, responses={200: PublicFeedbackReceipt, 201: PublicFeedbackReceipt})
    def post(self, request):
        schema = PublicFeedbackInput(data=request.data)
        schema.is_valid(raise_exception=True)
        actor = request.user if request.user.is_authenticated else None
        result, created = feedback.submit(actor, schema.validated_data)
        return Response(result, status=201 if created else 200)


class AdminFeedbackListView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(operation_id="catalog_admin_public_feedback_list", parameters=[FeedbackListQuery], responses=FeedbackListOutput)
    def get(self, request):
        schema = FeedbackListQuery(data=request.query_params)
        schema.is_valid(raise_exception=True)
        return Response(feedback.listing(schema.validated_data))


class AdminFeedbackDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(parameters=[FeedbackHistoryQuery], responses=FeedbackDetailOutput)
    def get(self, request, feedback_id):
        schema = FeedbackHistoryQuery(data=request.query_params)
        schema.is_valid(raise_exception=True)
        row = get_object_or_404(PublicFeedback.objects.select_related("handled_by"), pk=feedback_id)
        return Response(feedback.detail(row, history_page=schema.validated_data["history_page"]))

    @extend_schema(request=FeedbackUpdateInput, responses=FeedbackUpdateOutput)
    def patch(self, request, feedback_id):
        schema = FeedbackUpdateInput(data=request.data)
        schema.is_valid(raise_exception=True)
        return Response(feedback.update(feedback_id, request.user, schema.validated_data))
