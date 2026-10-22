from common.private_responses import PrivateAccountResponses
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Max, OuterRef, Subquery
from rest_framework import mixins, serializers, status, viewsets
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib.parse import quote
from uuid import UUID

from .models import (
    Annotation,
    Bookmark,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    SavedItem,
    SavedTopic,
)
from .serializers import (
    AnnotationSerializer,
    BookmarkSerializer,
    ReadingHistorySerializer,
    ReadingListItemSerializer,
    ReadingListSerializer,
    ReadingProgressSerializer,
    SavedItemSerializer,
    SavedTopicSerializer,
)
from .services import RECENT_READING_LIMIT, readable_progress_for_user
from .library_serializers import (
    LibraryConversationSerializer,
    LibraryMessageSerializer,
    LibraryMessageSourceDetailSerializer,
)


class OwnedModelViewSet(PrivateAccountResponses, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        rows = self.queryset.filter(user=self.request.user)
        return rows.select_for_update(of=("self",)) if getattr(self, "action", None) in {"update", "partial_update", "destroy"} else rows

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        from .privacy import lock_owner
        lock_owner(request.user)
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        from .privacy import lock_owner
        lock_owner(request.user)
        return super().destroy(request, *args, **kwargs)


class ReaderRecordPagination(PageNumberPagination):
    page_query_param = "p"


class ReadingProgressViewSet(OwnedModelViewSet):
    queryset = ReadingProgress.objects.select_related("asset")
    serializer_class = ReadingProgressSerializer

    def list(self, request, *args, **kwargs):
        latest_for_work = (
            readable_progress_for_user(request.user)
            .filter(asset__edition__work_id=OuterRef("asset__edition__work_id"))
            .order_by("-updated_at", "-created_at")
            .values("id")[:1]
        )
        recent = (
            readable_progress_for_user(request.user)
            .select_related("asset__edition__work")
            .annotate(latest_for_work_id=Subquery(latest_for_work))
            .filter(id=F("latest_for_work_id"))
            .order_by("-updated_at", "-created_at")[:RECENT_READING_LIMIT]
        )
        serializer = self.get_serializer(recent, many=True)
        return Response(
            {
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
            }
        )


class AnnotationViewSet(OwnedModelViewSet):
    queryset = Annotation.objects.select_related("asset", "page")
    serializer_class = AnnotationSerializer
    filterset_fields = ("asset", "page", "kind")
    pagination_class = ReaderRecordPagination

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        from . import research
        self._privacy_contexts = research.memory_contexts(request.user, lock=True)
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        from . import research
        from .privacy import linked_memories
        from .notebook import annotation_retired
        for memory in linked_memories(self.request.user, instance.id):
            research.revoke_memory_contexts(memory, self._privacy_contexts)
        annotation_retired(self.request.user, instance.pk, retire=True)
        instance.delete()

    @action(detail=False, methods=["get"], url_path="note-groups")
    def note_groups(self, request):
        notes = (
            self.get_queryset()
            .filter(kind=Annotation.Kind.NOTE)
            .select_related("asset__edition__work", "page")
        )
        grouped = (
            notes.values("asset_id")
            .annotate(note_count=Count("id"), latest_at=Max("created_at"))
            .order_by("-latest_at")
        )
        results = []
        for group in grouped[:200]:
            previews = list(
                notes.filter(asset_id=group["asset_id"]).order_by("-created_at")[:3]
            )
            if not previews:
                continue
            serialized = AnnotationSerializer(
                previews,
                many=True,
                context={"request": request},
            ).data
            results.append(
                {
                    "asset": str(group["asset_id"]),
                    "work": serialized[0]["work"],
                    "note_count": group["note_count"],
                    "latest_at": group["latest_at"],
                    "previews": serialized,
                }
            )
        return Response({"count": len(results), "results": results})


class BookmarkViewSet(OwnedModelViewSet):
    queryset = Bookmark.objects.select_related("asset", "page").order_by("-created_at")
    serializer_class = BookmarkSerializer
    filterset_fields = ("asset", "page")
    pagination_class = ReaderRecordPagination


class SavedItemViewSet(OwnedModelViewSet):
    queryset = SavedItem.objects.select_related("work")
    serializer_class = SavedItemSerializer
    filterset_fields = ("work",)

    def get_queryset(self):
        rows = super().get_queryset()
        raw_ids = self.request.query_params.get("work_ids", "")
        if raw_ids:
            from rest_framework.exceptions import ValidationError
            values = raw_ids.split(",")
            if len(values) > 50:
                raise ValidationError({"work_ids": "一次最多读取50部作品的收藏状态。"})
            try:
                ids = [UUID(value) for value in values]
            except (ValueError, TypeError):
                raise ValidationError({"work_ids": "作品标识格式不正确。"})
            rows = rows.filter(work_id__in=ids)
        return rows


class TopicSaveCommand(serializers.Serializer):
    topic = serializers.UUIDField()
    saved = serializers.BooleanField()
    expected_version = serializers.CharField(max_length=100)
    request_id = serializers.UUIDField()

    def to_internal_value(self, data):
        if not hasattr(data, "items") or set(data) - set(self.fields):
            raise serializers.ValidationError("收藏操作包含不支持的字段。")
        if type(data.get("saved")) is not bool:
            raise serializers.ValidationError({"saved": "请传入明确的收藏开关。"})
        return super().to_internal_value(data)


class TopicSaveCreate(serializers.Serializer):
    topic = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100)
    request_id = serializers.UUIDField()

    def to_internal_value(self, data):
        if not hasattr(data, "items") or set(data) - set(self.fields):
            raise serializers.ValidationError("收藏操作包含不支持的字段。")
        return super().to_internal_value(data)


class TopicSaveReceipt(serializers.Serializer):
    request_id = serializers.UUIDField()
    applied_saved = serializers.BooleanField()


class TopicSaveOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    topic_id = serializers.UUIDField()
    saved = serializers.BooleanField()
    version = serializers.CharField()
    can_save = serializers.BooleanField()
    record = SavedTopicSerializer(allow_null=True)
    receipt = TopicSaveReceipt(allow_null=True)


TOPIC_OWNER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


class SavedTopicViewSet(OwnedModelViewSet):
    queryset = SavedTopic.objects.select_related("topic")
    serializer_class = SavedTopicSerializer
    filterset_fields = ("topic",)
    # A collection never changes identity through generic PATCH/PUT.
    http_method_names = ["get", "post", "delete", "head", "options"]

    def require_owner(self, request):
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请核对当前账户后再读取或修改主题收藏。")

    @extend_schema(parameters=[TOPIC_OWNER, OpenApiParameter("topic", str, required=True),
        OpenApiParameter("request_id", str)], responses=TopicSaveOutput)
    @action(detail=False, methods=["get"])
    def state(self, request):
        from . import topic_saves
        self.require_owner(request)
        return Response(topic_saves.state(request.user, request.query_params.get("topic"), request.query_params.get("request_id")))

    @extend_schema(parameters=[TOPIC_OWNER], request=TopicSaveCommand, responses=TopicSaveOutput)
    @action(detail=False, methods=["post"])
    def command(self, request):
        from . import topic_saves
        self.require_owner(request)
        data = TopicSaveCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(topic_saves.command(request.user, data.validated_data))

    @extend_schema(parameters=[TOPIC_OWNER], request=TopicSaveCreate, responses={201: SavedTopicSerializer, 204: None})
    def create(self, request, *args, **kwargs):
        from . import topic_saves
        self.require_owner(request)
        data = TopicSaveCreate(data=request.data)
        data.is_valid(raise_exception=True)
        result = topic_saves.command(request.user, {**data.validated_data, "saved": True})
        return Response(result["record"], status=201 if result["record"] else 204)

    @extend_schema(parameters=[TOPIC_OWNER, OpenApiParameter("topic", str, required=True),
        OpenApiParameter("expected_version", str, required=True), OpenApiParameter("request_id", str, required=True)],
        responses={204: None})
    def destroy(self, request, *args, **kwargs):
        from . import topic_saves
        self.require_owner(request)
        data = TopicSaveCommand(data={"topic": request.query_params.get("topic"), "saved": False,
            "expected_version": request.query_params.get("expected_version"), "request_id": request.query_params.get("request_id")})
        data.is_valid(raise_exception=True)
        if data.validated_data["expected_version"].split(":", 1)[0] != str(kwargs["pk"]):
            raise serializers.ValidationError("收藏版本与待删除记录不一致。")
        topic_saves.command(request.user, data.validated_data)
        return Response(status=204)


from .booklist_views import BooklistActions


class ReadingListViewSet(BooklistActions, OwnedModelViewSet):
    queryset = ReadingList.objects.prefetch_related("items__work")
    serializer_class = ReadingListSerializer

    def get_queryset(self):
        rows = super().get_queryset()
        return rows.prefetch_related(None) if self.action in {"workspace", "directory", "export"} else rows

    @transaction.atomic
    def perform_create(self, serializer):
        from .privacy import require_retention
        require_retention(self.request.user, "saved_knowledge")
        super().perform_create(serializer)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        from .privacy import require_retention
        from .booklists import add_work
        require_retention(request.user, "saved_knowledge")
        reading_list = self.get_object()
        serializer = ReadingListItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item, created = add_work(reading_list, serializer.validated_data["work"].pk)
        return Response(
            ReadingListItemSerializer(item, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @transaction.atomic
    @extend_schema(parameters=[OpenApiParameter("item_id", str, location=OpenApiParameter.PATH)])
    @action(detail=True, methods=["delete"], url_path=r"items/(?P<item_id>[^/.]+)")
    def remove_item(self, request, pk=None, item_id=None):
        from .privacy import lock_owner
        lock_owner(request.user)
        reading_list = self.get_object()
        from django.utils import timezone
        from .booklists import touch
        changed = reading_list.items.filter(pk=item_id, removed_at__isnull=True).update(removed_at=timezone.now())
        if changed:
            touch(reading_list)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingHistoryViewSet(
    PrivateAccountResponses,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = ReadingHistorySerializer
    queryset = ReadingHistory.objects.select_related("asset__edition__work")

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        from .privacy import lock_owner, retention_enabled
        lock_owner(request.user)
        if not retention_enabled(request.user, "reading_history"):
            return Response({"recorded": False, "reason": "reading_history_disabled"})
        return super().create(request, *args, **kwargs)


class ReaderDataExportView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        context = {"request": request}
        from .research import research_export, serialize_record
        from .privacy import annotation_export, operation_output, profile_data, export_item
        from .editorial_comment_models import EditorialComment
        from .models import ReaderDataOperation, ReaderSearchRecord
        conversations = request.user.library_conversations.prefetch_related(
            "messages__sources__asset",
            "messages__sources__edition",
        )
        return Response(
            {
                "research_data": research_export(request.user),
                "article_comments": [export_item(request.user, "article_comments", row) for row in EditorialComment.objects.filter(user=request.user)],
                "search_history": [serialize_record(row, request.user) for row in ReaderSearchRecord.objects.filter(user=request.user)],
                "data_operations": [operation_output(row) for row in ReaderDataOperation.objects.filter(user=request.user)],
                "profile": {
                    "email": request.user.email,
                    "display_name": request.user.display_name,
                    "created_at": request.user.date_joined,
                    "reading_preferences": profile_data(request.user),
                },
                "progress": ReadingProgressSerializer(
                    request.user.reading_progress.all(),
                    many=True,
                    context=context,
                ).data,
                "annotations": [annotation_export(request.user, row) for row in
                    request.user.annotations.select_related("asset", "page").all()],
                "bookmarks": BookmarkSerializer(
                    request.user.bookmarks.all(),
                    many=True,
                    context=context,
                ).data,
                "saved_items": SavedItemSerializer(
                    request.user.saved_items.all(),
                    many=True,
                    context=context,
                ).data,
                "saved_topics": SavedTopicSerializer(
                    request.user.saved_topics.all(),
                    many=True,
                    context=context,
                ).data,
                "reading_lists": ReadingListSerializer(
                    request.user.reading_lists.all(),
                    many=True,
                    context=context,
                ).data,
                "reading_history": ReadingHistorySerializer(
                    request.user.reading_history.all(),
                    many=True,
                    context=context,
                ).data,
                "library_conversations": [
                    {
                        **LibraryConversationSerializer(
                            conversation,
                            context=context,
                        ).data,
                        "messages": [
                            {
                                **LibraryMessageSerializer(
                                    message,
                                    context=context,
                                ).data,
                                "sources": LibraryMessageSourceDetailSerializer(
                                    [source for source in message.sources.all() if source.cited],
                                    many=True,
                                    context=context,
                                ).data,
                            }
                            for message in conversation.messages.all()
                        ],
                    }
                    for conversation in conversations
                ],
            }
        )


class ReaderSubmissionView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        title = str(request.data.get("title", "")).strip()
        note = str(request.data.get("note", "")).strip()
        if not title:
            return Response({"title": ["请填写拟投稿文献题名。"]}, status=400)
        from catalog.models import SiteSetting

        stored = SiteSetting.objects.filter(key="reader_submission_email").first()
        submission_email = (
            stored.value
            if stored and isinstance(stored.value, str)
            else settings.READER_SUBMISSION_EMAIL
        )
        if not submission_email:
            return Response(
                {
                    "detail": "管理员尚未配置投稿邮箱。",
                    "mailto": None,
                },
                status=503,
            )
        subject = f"社会理论书库读者荐书：{title}"
        body = (
            f"读者：{request.user.display_name}\n"
            f"联系邮箱：{request.user.email}\n\n"
            f"拟投稿文献：{title}\n\n"
            f"推荐说明与合法来源：\n{note}"
        )
        mailto = (
            f"mailto:{submission_email}"
            f"?subject={quote(subject)}&body={quote(body)}"
        )
        return Response(
            {
                "detail": "已生成投稿邮件，请在你的邮件客户端确认发送。",
                "email": submission_email,
                "mailto": mailto,
            }
        )
