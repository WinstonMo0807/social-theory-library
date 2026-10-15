from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PublicFeedback


class PublicFeedbackInput(serializers.Serializer):
    category = serializers.ChoiceField(choices=PublicFeedback.Category.choices, default=PublicFeedback.Category.OTHER)
    body = serializers.CharField(min_length=4, max_length=5000, trim_whitespace=True)
    contact = serializers.EmailField(required=False, allow_blank=True)
    path = serializers.CharField(max_length=400, required=False, allow_blank=True)


class PublicFeedbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = PublicFeedbackInput(data=request.data)
        payload.is_valid(raise_exception=True)
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        feedback = PublicFeedback.objects.create(user=actor, **payload.validated_data)
        return Response({"id": str(feedback.id), "status": feedback.status, "message": "反馈已提交，感谢你的说明。"}, status=status.HTTP_201_CREATED)
