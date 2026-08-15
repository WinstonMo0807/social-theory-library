from django.conf import settings
from django.db.models import Count, F, Max, OuterRef, Subquery
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib.parse import quote

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


class OwnedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


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


class SavedTopicViewSet(OwnedModelViewSet):
    queryset = SavedTopic.objects.select_related("topic")
    serializer_class = SavedTopicSerializer
    filterset_fields = ("topic",)


class ReadingListViewSet(OwnedModelViewSet):
    queryset = ReadingList.objects.prefetch_related("items__work")
    serializer_class = ReadingListSerializer

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        reading_list = self.get_object()
        serializer = ReadingListItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item, created = ReadingListItem.objects.get_or_create(
            reading_list=reading_list,
            work=serializer.validated_data["work"],
            defaults={"order": serializer.validated_data.get("order", reading_list.items.count())},
        )
        return Response(
            ReadingListItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path=r"items/(?P<item_id>[^/.]+)")
    def remove_item(self, request, pk=None, item_id=None):
        reading_list = self.get_object()
        reading_list.items.filter(pk=item_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingHistoryViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = ReadingHistorySerializer
    queryset = ReadingHistory.objects.select_related("asset__edition__work")

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class ReaderDataExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        context = {"request": request}
        conversations = request.user.library_conversations.prefetch_related(
            "messages__sources__asset",
            "messages__sources__edition",
        )
        return Response(
            {
                "profile": {
                    "email": request.user.email,
                    "display_name": request.user.display_name,
                    "created_at": request.user.date_joined,
                    "reading_preferences": request.user.reader_profile.reading_preferences,
                },
                "progress": ReadingProgressSerializer(
                    request.user.reading_progress.all(),
                    many=True,
                    context=context,
                ).data,
                "annotations": AnnotationSerializer(
                    request.user.annotations.all(),
                    many=True,
                    context=context,
                ).data,
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


class ReaderSubmissionView(APIView):
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
