from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanPublishAuthority
from . import editorial_comments as service
from .research_views import PrivateResponses
from .source_follow_views import require_owner


class CommentOutput(serializers.Serializer):
    id = serializers.UUIDField()
    public_revision_id = serializers.UUIDField()
    byline = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.DateTimeField()
    revision = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=["pending", "published", "rejected"], required=False)
    moderation_reason = serializers.CharField(required=False, allow_blank=True)


class CommentPage(serializers.Serializer):
    owner_id = serializers.CharField(required=False)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = CommentOutput(many=True)


class CommentCommand(serializers.Serializer):
    request_id = serializers.UUIDField()
    public_revision_id = serializers.UUIDField()
    byline = serializers.CharField(max_length=80)
    body = serializers.CharField(max_length=3000)
    confirm_public = serializers.BooleanField()

    def validate_confirm_public(self, value):
        if value is not True:
            raise serializers.ValidationError("请明确同意这段评论和署名审核后公开。")
        return value


class CommentReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    comment = CommentOutput(allow_null=True)
    notice = serializers.CharField()


class CommentDelete(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=1)


class CommentDeleted(serializers.Serializer):
    owner_id = serializers.CharField()
    deleted = serializers.BooleanField()


class CommentModerate(CommentDelete):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["published", "rejected"])
    reason = serializers.CharField(max_length=240, required=False, allow_blank=True)


def validated(schema, request):
    value = schema(data=request.data)
    value.is_valid(raise_exception=True)
    return value.validated_data


PAGING = [OpenApiParameter("page", int), OpenApiParameter("page_size", int)]
OWNER = [OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)]


class PublicArticleCommentsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(parameters=[*PAGING, OpenApiParameter("public_revision_id", str)], responses=CommentPage)
    def get(self, request, issue_id):
        response = Response(service.public_page(issue_id, request.query_params))
        response["Cache-Control"] = "no-store"
        return response


class OwnArticleCommentsView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[*OWNER, *PAGING], responses=CommentPage)
    def get(self, request, issue_id):
        require_owner(request)
        return Response(service.own_page(request.user, issue_id, request.query_params))

    @extend_schema(parameters=OWNER, request=CommentCommand, responses=CommentReceipt)
    def post(self, request, issue_id):
        require_owner(request)
        return Response(service.submit(request.user, issue_id, validated(CommentCommand, request)))


class ArticleCommentReceiptView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=OWNER, responses=CommentReceipt)
    def get(self, request, issue_id, request_id):
        require_owner(request)
        return Response(service.receipt_state(request.user, issue_id, request_id))


class ArticleCommentDeleteView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=OWNER, request=CommentDelete, responses=CommentDeleted)
    def delete(self, request, issue_id, comment_id):
        require_owner(request)
        data = validated(CommentDelete, request)
        return Response(service.remove(request.user, issue_id, comment_id, data["expected_revision"]))


class AdminArticleCommentsView(PrivateResponses, APIView):
    permission_classes = [CanPublishAuthority]

    @extend_schema(parameters=PAGING, responses=CommentPage)
    def get(self, request, issue_id):
        return Response(service.moderation_page(issue_id, request.query_params))

    @extend_schema(request=CommentModerate, responses=CommentOutput)
    def post(self, request, issue_id):
        return Response(service.moderate(request.user, issue_id, validated(CommentModerate, request)))
