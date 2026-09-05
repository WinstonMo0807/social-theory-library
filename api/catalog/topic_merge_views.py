from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanMergeAuthority
from catalog.models import Topic
from catalog.services.topics import merge_topics, topic_merge_preview


class TopicMergeRequestSerializer(serializers.Serializer):
    target_topic = serializers.UUIDField()
    fingerprint = serializers.CharField(min_length=64, max_length=64)
    change_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    confirmed = serializers.BooleanField()


class AdminTopicMergePreviewView(APIView):
    permission_classes = [CanMergeAuthority]

    def get(self, request, pk):
        source = get_object_or_404(Topic, pk=pk)
        target_id = request.query_params.get("target_topic")
        target = None
        if target_id:
            identifier = serializers.UUIDField().run_validation(target_id)
            target = get_object_or_404(Topic, pk=identifier)
        try:
            return Response(topic_merge_preview(source, target))
        except ValueError as error:
            return Response({"detail": str(error)}, status=409)


class AdminTopicMergeView(APIView):
    permission_classes = [CanMergeAuthority]

    def post(self, request, pk):
        serializer = TopicMergeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data["confirmed"]:
            return Response({"detail": "请先查看影响范围并确认主题合并。"}, status=400)
        try:
            result = merge_topics(
                pk, data["target_topic"], actor=request.user,
                expected_fingerprint=data["fingerprint"], change_note=data.get("change_note", ""),
            )
        except ValueError as error:
            return Response({"detail": str(error), "code": "topic_merge_conflict"}, status=409)
        return Response(result)
