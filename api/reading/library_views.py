from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .library_assistant import assistant_status, stream_conversation_answer
from .library_serializers import (
    LibraryConversationSerializer,
    LibraryMessageSerializer,
    LibraryMessageSourceDetailSerializer,
    LibraryMessageSourceSerializer,
    LibraryQuestionSerializer,
)
from .models import LibraryConversation, LibraryMessage, LibraryMessageSource


class LibraryConversationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = LibraryConversationSerializer

    def get_queryset(self):
        return (
            LibraryConversation.objects.filter(user=self.request.user)
            .annotate(message_count=Count("messages", distinct=True))
            .order_by("-last_message_at", "-updated_at")
        )


class LibraryConversationMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            LibraryConversation,
            pk=conversation_id,
            user=request.user,
        )
        messages = conversation.messages.annotate(
            cited_source_count=Count("sources", filter=Q(sources__cited=True))
        ).all()
        serializer = LibraryMessageSerializer(messages, many=True, context={"request": request})
        return Response({"count": len(serializer.data), "results": serializer.data})


class LibraryConversationStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            LibraryConversation,
            pk=conversation_id,
            user=request.user,
            archived=False,
        )
        serializer = LibraryQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assist_mode = serializer.validated_data.get("assist_mode", conversation.assist_mode)
        response = StreamingHttpResponse(
            stream_conversation_answer(
                conversation=conversation,
                question=serializer.validated_data["question"],
                assist_mode=assist_mode,
            ),
            content_type="text/event-stream; charset=utf-8",
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        return response


class LibraryMessageSourcesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):
        message = get_object_or_404(
            LibraryMessage.objects.select_related("conversation"),
            pk=message_id,
            conversation__user=request.user,
            role=LibraryMessage.Role.ASSISTANT,
        )
        sources = message.sources.filter(cited=True).select_related("asset", "edition").order_by("ordinal")
        serializer = LibraryMessageSourceSerializer(sources, many=True, context={"request": request})
        return Response({"count": len(serializer.data), "results": serializer.data})


class LibraryMessageSourceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, message_id, source_id):
        source = get_object_or_404(
            LibraryMessageSource.objects.select_related("message__conversation", "asset", "edition"),
            pk=source_id,
            message_id=message_id,
            message__conversation__user=request.user,
            cited=True,
        )
        serializer = LibraryMessageSourceDetailSerializer(source, context={"request": request})
        return Response(serializer.data)


class LibraryMessageCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        message = get_object_or_404(
            LibraryMessage,
            pk=message_id,
            conversation__user=request.user,
            role=LibraryMessage.Role.ASSISTANT,
        )
        if message.status not in {LibraryMessage.Status.PENDING, LibraryMessage.Status.STREAMING}:
            return Response(
                {"detail": "该回答已经结束，无法取消。", "status": message.status},
                status=status.HTTP_409_CONFLICT,
            )
        message.cancel_requested_at = timezone.now()
        message.save(update_fields=["cancel_requested_at", "updated_at"])
        return Response({"detail": "已请求停止生成。", "status": message.status})


class LibraryAssistantStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(assistant_status())
